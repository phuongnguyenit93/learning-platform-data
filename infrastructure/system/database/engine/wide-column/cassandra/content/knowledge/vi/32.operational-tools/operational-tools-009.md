# sstabledump, sstableverify và điều kiện dùng theo từng công cụ

## Mục tiêu và phạm vi

Apache Cassandra ghi dữ liệu vào **memtable** rồi flush thành các **SSTable bất biến** trên đĩa. Khi đọc hoặc sửa dữ liệu, Cassandra phải xét nhiều phiên bản hàng/cột, timestamp, TTL và tombstone trong các SSTable. Khi hệ thống có dấu hiệu dữ liệu bất thường, lỗi đọc SSTable hoặc nghi ngờ tệp hỏng, người vận hành cần phân biệt hai câu hỏi:

1. **Bên trong một SSTable cụ thể có gì?** — dùng `sstabledump` để quan sát dữ liệu được mã hóa trong tệp ở dạng có thể đọc.
2. **Các SSTable của một bảng có vượt qua phép kiểm tra tính hợp lệ không?** — dùng `sstableverify` theo quy trình kiểm tra **offline** được hỗ trợ.

Hai công cụ đều thuộc nhóm **công cụ SSTable cục bộ**, khác `cqlsh` và khác `nodetool repair`. Chúng **không** tự đồng bộ replica, không chứng minh toàn bộ dữ liệu nghiệp vụ đầy đủ, và không phải lệnh sửa chữa tệp. Đặc biệt, dùng công cụ sai lúc Cassandra đang compaction hoặc thay file có thể tạo kết luận sai hoặc rủi ro vận hành.

Bài học thuộc chương **Công cụ vận hành**, trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nội dung liên kết kiến trúc wide-column, thiết kế bảng theo partition key và truy vấn, đường ghi/đọc CQL, replication/consistency, compaction, repair, xử lý lỗi và cách ứng dụng Java ghi nhận dữ liệu kỳ vọng.

Sau bài học, bạn có thể:

- Nhận diện **Data.db**, các thành phần SSTable liên quan và giới hạn của ảnh chụp SSTable so với trạng thái CQL.
- Chọn đúng `sstabledump` khi cần đọc nội dung một SSTable và `sstableverify` khi cần kiểm tra tính hợp lệ của các SSTable của bảng.
- Phân biệt **đọc snapshot có thể làm khi Cassandra còn chạy** với **quy trình kiểm tra offline yêu cầu dừng Cassandra trên node đích**.
- Lập kế hoạch quyền truy cập, tương thích phiên bản, disk/I/O, backup, số replica còn hoạt động và phạm vi tác động.
- Thực hành tạo dữ liệu CQL, flush/snapshot, dump SSTable và diễn giải timestamp/tombstone mà không hiểu nhầm “giá trị vật lý” thành “hàng đang sống”.
- Xử lý kết quả nghi corruption bằng quy trình giữ bằng chứng, xác nhận độc lập, restore/replace và repair có kiểm soát.

> **Nguyên tắc an toàn:** mọi lệnh minh họa nhằm phục vụ lab hoặc bảo trì đã được duyệt. Không dừng một node sản xuất, không xóa/di chuyển/sửa SSTable, không chạy `scrub` hay ép compaction chỉ vì thấy nội dung khó hiểu trong dump. Hướng dẫn chi tiết và cờ CLI phải được đối chiếu với **đúng phiên bản Cassandra và bản phân phối** đang dùng.

## 1. Một SSTable gồm nhiều thành phần

SSTable là tập tệp trên đĩa, thường có cùng **descriptor** và các hậu tố thể hiện thành phần. Ví dụ hình thức tên thường gặp là `<descriptor>-Data.db`. Tùy phiên bản/format, bên cạnh thành phần dữ liệu còn có các thành phần chỉ mục, thống kê, bloom filter, compression và mục lục.

~~~text
/var/lib/cassandra/data/
  sstable_lab/
    events_by_run-<table_uuid>/
      <descriptor>-Data.db
      <descriptor>-Index.db
      <descriptor>-Summary.db
      <descriptor>-Filter.db
      <descriptor>-Statistics.db
      <descriptor>-TOC.txt
      ... các thành phần phụ thuộc phiên bản/format ...
      snapshots/
        inspect-01/
          <descriptor>-Data.db
          <descriptor>-Index.db
          ...
~~~

Đường dẫn này chỉ **minh họa cho cài đặt Linux phổ biến**; Cassandra có thể dùng thư mục dữ liệu khác, nhiều data volumes hoặc layout/format khác nhau. `<table_uuid>` là định danh vật lý của bảng trong tên thư mục, **không phải partition key**. Không đoán tên thư mục chỉ từ `keyspace.table` khi đã từng drop/recreate bảng.

| Thành phần | Vai trò thường gặp | Có phải nguồn sự thật duy nhất? |
| --- | --- | --- |
| `Data.db` | Chứa dữ liệu được serialize: partition, hàng, cell, tombstone và metadata gắn với chúng | Không; các mutation còn có thể ở memtable và nhiều SSTable khác |
| `Index.db` | Hỗ trợ định vị partition/điểm truy cập trong dữ liệu | Không chứng minh dữ liệu logic ở tất cả replica |
| `Summary.db` và `Filter.db` | Hỗ trợ định vị/bỏ qua SSTable không phù hợp khi đọc | Có thể thay đổi theo format/version |
| `Statistics.db` | Metadata/thống kê SSTable, repair/compaction-related state | Không phải toàn bộ nội dung CQL |
| `CompressionInfo.db` và thành phần khác | Giải thích bố trí/nén/checksum theo format | Không phải thành phần nào cũng tồn tại trong mọi cấu hình |

**`sstabledump` không đọc trực tiếp toàn bộ cluster.** Nó giải mã một SSTable được chỉ định bằng đường dẫn tệp, không tự mở mọi SSTable của bảng và cũng không đọc những thay đổi còn nằm trong memtable. Một phân vùng có thể tồn tại trong nhiều SSTable, thậm chí ở nhiều node/replica; dump một tệp là **một lát cắt vật lý**, không phải kết quả SELECT cuối cùng.

~~~mermaid
flowchart LR
    W["Mutation CQL"] --> M["Commit log + memtable"]
    M -->|Flush| A["SSTable A"]
    M -->|Flush sau| B["SSTable B"]
    A --> C["Compaction"]
    B --> C
    C --> N["SSTable mới"]
    A -. "Dump một tệp" .-> D["sstabledump"]
    N -. "Dump một tệp" .-> D
    A -. "Kiểm tra trên đĩa" .-> V["sstableverify offline"]
    B -.-> V
    N -.-> V
~~~

Compaction có thể tạo SSTable mới, rồi loại các file đầu vào khi an toàn. Do vậy **đọc đường dẫn tệp live theo đúng thời điểm compaction** có nguy cơ file biến mất/đổi trạng thái. Việc dùng **snapshot có tên** giúp giữ những thành phần SSTable được snapshot tham chiếu ổn định trong lúc phân tích.

## 2. Chọn công cụ theo câu hỏi chẩn đoán

| Nhu cầu | Công cụ ưu tiên | Điều kiện quan trọng | Giới hạn kết luận |
| --- | --- | --- | --- |
| Xem cell, timestamp, deletion info, TTL của **một SSTable** | `sstabledump` | Có đường dẫn thành phần `Data.db` thích hợp, công cụ tương thích format | Không phải kết quả CQL sau hòa giải nhiều SSTable/replica |
| Xem một tệp SSTable khi node đang phục vụ | `sstabledump` **trên snapshot/copy ổn định** | Snapshot đã tạo an toàn; kiểm soát quyền/đường dẫn/I/O | Snapshot chỉ phản ánh SSTable trong phạm vi tại thời điểm tạo |
| Nghi các thành phần SSTable của **bảng trên một node** không hợp lệ | `sstableverify` | Theo quy trình **offline**: dừng Cassandra trên node đích, có backup và chuẩn bị nguồn lực | PASS không chứng minh replica khác cùng dữ liệu; FAIL chưa tự xác định bước sửa |
| Muốn xem metadata của SSTable | `sstablemetadata` (nếu phiên bản cung cấp) | Tệp phù hợp, công cụ/version tương thích | Metadata không thay nội dung cell hoặc kiểm tra toàn bộ |
| Muốn kiểm tra SSTable khi Cassandra vẫn chạy | `nodetool verify` theo phiên bản | Đánh giá tải tác động và cờ của bản đang dùng | Khác `sstableverify` offline, không thay repair |
| Muốn đồng bộ các replica đang lệch | `nodetool repair` theo kế hoạch | RF/DC, token ranges, tải I/O/network, tombstone và sức khỏe replica | Không phải công cụ sửa byte SSTable hỏng một cách tùy ý |
| Muốn sửa/tạo lại SSTable bị lỗi | Quy trình restore/replace/scrub **được phê duyệt** | Đánh giá mất dữ liệu và tính toàn vẹn trước | `scrub` có thể thay đổi/loại dữ liệu; không phải thao tác chỉ đọc |

**Phân biệt mức tác động:** `sstabledump` là công cụ **xem** nội dung; `sstableverify` là công cụ **kiểm tra** tính hợp lệ; `repair` là công việc **đồng bộ** replica; `scrub` là thao tác **biến đổi/sửa SSTable** có rủi ro. Các công cụ không thể hoán đổi chỉ vì cùng có chữ “SSTable”.

### Một cây quyết định ngắn

~~~mermaid
flowchart TD
    A["Thấy kết quả CQL hoặc lỗi lưu trữ bất thường"] --> B{"Muốn biết điều gì?"}
    B -->|Một tệp chứa gì| C["Tạo snapshot ổn định\nDùng sstabledump"]
    B -->|Tệp có hợp lệ không| D["Đánh giá nodetool verify online\nhoặc sstableverify offline"]
    B -->|Replica có khác nhau không| E["Kiểm tra RF/CL, hints\nvà anti-entropy repair"]
    B -->|Thiếu dữ liệu nghiệp vụ| F["Đối soát manifest/outbox/backup"]
    C --> G["Đọc kết quả + CQL/logs"]
    D --> G
    E --> G
    F --> G
    G --> H{"Có bằng chứng corruption hoặc mất dữ liệu?"}
    H -->|Có| I["Dừng xử lý tự phát\nLập kế hoạch restore/replace"]
    H -->|Chưa rõ| J["Thu thêm bằng chứng có giới hạn"]
~~~

## 3. Điều kiện sử dụng `sstabledump`

`sstabledump` nhận **đường dẫn của một SSTable Data component** và in ra nội dung giải mã, thường dưới dạng JSON hoặc biến thể đầu ra theo option/phiên bản. Hữu ích khi phải điều tra:

- Một timestamp cũ/mới đã được lưu trong một SSTable hay chưa.
- Tombstone của hàng/cột/partition xuất hiện ra sao trong tệp.
- Phân vùng hoặc clustering row có dấu hiệu bất thường, TTL hết hạn hoặc bản ghi không còn thấy khi SELECT.
- Kết quả cần so với metadata, log mutation, CQL và lịch compaction/repair.

### 3.1. Các điều kiện phải đạt

1. **Biết đúng node, keyspace/table và Data.db:** đường dẫn thuộc SSTable của bảng cần kiểm tra. Với RF lớn hơn một, kết quả của một node không tự đại diện mọi replica.
2. **Có tệp ổn định:** ưu tiên snapshot/copy đã chốt; không đuổi theo đường dẫn live vừa thay đổi bởi compaction.
3. **Đúng phiên bản và format:** chạy công cụ đi cùng bản Cassandra/bản phân phối tương thích với SSTable, không tự dùng binary cũ đọc format mới.
4. **Đủ quyền đọc và tài nguyên:** công cụ có thể đọc nhiều byte, tốn CPU/RAM/I/O; file lớn tạo đầu ra JSON rất lớn.
5. **Kiểm soát dữ liệu nhạy cảm:** dump có thể chứa plaintext từ column; quyền truy cập, log, file kết quả và thời hạn lưu phải được giới hạn.
6. **Hiểu phạm vi dữ liệu:** SSTable không bao gồm mutation chưa flush, và một bản ghi có thể nằm ở nhiều SSTable với timestamp/tombstone khác nhau.

**Node có cần dừng không?** Khi đọc **bản snapshot ổn định**, có thể điều tra SSTable trong lúc dịch vụ Cassandra trên node vẫn chạy, nếu chính sách vận hành và I/O cho phép. Tránh đọc/can thiệp trực tiếp những file live có thể đang được thay thế; nếu cần chẩn đoán mức độ hỏng ở toàn bảng, nên xem xét quy trình verify phù hợp hơn.

### 3.2. Tra cú pháp của phiên bản thực tế

~~~bash
# Chạy trên máy có bộ công cụ Cassandra tương thích.
sstabledump --help

# Đầu vào thường là đường dẫn đầy đủ đến thành phần Data.db.
sstabledump "/path/to/snapshot/<descriptor>-Data.db"
~~~

Một số phiên bản hỗ trợ lọc khóa/đổi kiểu đầu ra bằng option; **tên cờ và format JSON không bảo đảm giống nhau trên Cassandra 3.x, 4.x, 5.x**. Trước khi dùng option, kiểm tra `sstabledump --help` của máy chạy và kiểm tra chính xác encoding của partition key.

**Không gửi output nguyên trạng lên issue tracker hoặc chat công khai**: trường `payload`, dữ liệu định danh khách hàng, access token hoặc JSON nghiệp vụ có thể xuất hiện trong dump dù CQL đã ẩn bớt cột ở ứng dụng.

## 4. Điều kiện sử dụng `sstableverify`

`sstableverify` là công cụ kiểm tra SSTable theo **keyspace/table cục bộ trên một node**. Nó dùng bộ thư viện/metadata Cassandra để đọc và kiểm tra tính hợp lệ của SSTable được tìm thấy cho bảng; các mức kiểm tra/cờ “quick/extended” (nếu có) tùy phiên bản.

Điều kiện quan trọng nhất về vận hành là **offline**: lên kế hoạch **dừng tiến trình Cassandra trên chính node sẽ được kiểm tra**, để không có flush, compaction, streaming hay tiến trình khác thay đổi tập SSTable trong lúc công cụ làm việc. Đừng chạy `sstableverify` trên thư mục dữ liệu đang được node Cassandra sử dụng mà không có quy trình tương thích đã được xác nhận.

### 4.1. Checklist trước khi dừng node

- **Trạng thái RF/CL:** sau khi đưa node ra khỏi phục vụ, số replica còn lại có đủ đáp ứng workload hiện tại? Với RF=3, `LOCAL_QUORUM` cần hai replica local; nếu đã có một node khác down, dừng thêm một node có thể làm quorum không đạt.
- **Tài nguyên vận hành:** đủ đĩa trống, I/O và CPU để các node còn lại phục vụ thêm tải; tránh chạy đồng thời nhiều node.
- **Backup/snapshot đáng tin:** có phương án restore/replace nếu phát hiện corruption; snapshot từ tệp đã hỏng không tự tạo bản sao lành.
- **Điểm dừng và người phụ trách:** có cửa sổ bảo trì, quan sát, kế hoạch restart, tài liệu cấu hình/version và lộ trình escalation.
- **Không có topology change đồng thời:** bootstrap, decommission, remove, streaming, repair lớn hoặc compaction bất thường có thể tăng rủi ro và gây khó phân tích.
- **Phiên bản và đường dẫn:** dùng bộ công cụ đúng bản, đúng Cassandra home/config, đúng keyspace/table trên node.
- **Quyền và log:** công cụ có thể cần quyền đọc data dir; phải lưu exit code, stdout/stderr, version, thời gian và tên node được kiểm tra.

### 4.2. Quy trình offline minh họa

~~~bash
# CHỈ VÍ DỤ CHO LAB / MAINTENANCE ĐƯỢC DUYỆT.
# 1. Trên node khỏe, ghi baseline:
nodetool status

# 2. Tắt ứng dụng Cassandra trên node đích bằng hệ quản lý dịch vụ.
# Dòng dưới chỉ là ví dụ cho Linux dùng systemd:
sudo systemctl stop cassandra

# 3. Xác minh tiến trình đã dừng hoàn toàn, không còn ghi/compaction.
# Kiểm tra tùy hệ điều hành, container runtime, bản phân phối.
sudo systemctl is-active cassandra

# 4. Chạy công cụ từ bộ cài phù hợp, khi node đã offline:
sstableverify sstable_lab events_by_run

# 5. Thu exit code/log, đánh giá kết quả rồi mới restart có kiểm soát.
# Đừng tự khởi động lại nếu nghi dữ liệu hỏng cần giữ bằng chứng.
~~~

**Trước bước 2, vận hành production phải có quy trình drain/shutdown được duyệt**, kiểm tra tiến trình đã thật sự dừng và đánh giá tác động của việc giảm một node trong DC. `nodetool drain` là thao tác phục vụ shutdown có kiểm soát, không phải phép kiểm chứng corruption; việc gọi drain có thể thay đổi trạng thái flush, nên phải ghi rõ thời điểm lấy snapshot/manifest.

`sstableverify sstable_lab events_by_run` là **mẫu cú pháp phổ biến**. Một số bản phân phối/phiên bản có tham số hoặc quy tắc tìm data directory khác; kiểm tra `sstableverify --help` trước khi chạy. Không coi đây là phép kiểm tra tự động mọi keyspace/bảng trong cluster.

### 4.3. PASS và FAIL có nghĩa gì?

| Kết quả | Có thể kết luận | Không thể kết luận |
| --- | --- | --- |
| Verify hoàn tất thành công | Các SSTable mà công cụ thực sự kiểm tra vượt qua tiêu chí được kích hoạt theo phiên bản/cờ | Mọi replica giống nhau, mọi event nghiệp vụ đã có, dữ liệu không thể mất về sau |
| Verify báo checksum/index/decode/error | Có tín hiệu bất thường cần điều tra ở file/thành phần/phạm vi đã chỉ ra | Có thể khắc phục an toàn bằng việc tự xóa một file |
| Verify bị dừng vì version/schema/permission | Quy trình/tool không hoàn tất; kết quả **UNKNOWN** | Tệp chắc chắn hỏng |
| Verify tốn lâu/nhiều I/O | Tải đọc/giải mã lớn có thể xảy ra | Càng chạy nhanh càng kiểm tra kỹ hơn |

**Verify không sửa dữ liệu.** Nếu phát hiện corruption, bước tiếp theo là **giữ bằng chứng, khoanh vùng, xác định bản sao còn tin cậy và chọn phương án phục hồi**; không xem FAIL như hướng dẫn lập tức chạy `scrub`.

## 5. Lab CQL: tạo dữ liệu, tombstone và snapshot

### 5.1. Yêu cầu lab

Chuẩn bị Cassandra với DC tên `datacenter1`, lý tưởng ba node/RF=3; nếu chỉ có một node, chỉnh replication của keyspace để phản ánh topology thật thay vì cố RF=3. Chỉ chạy lab trên môi trường được phép thao tác flush/snapshot và có đủ disk.

~~~bash
nodetool status
~~~

Kiểm tra tên DC từ `nodetool status` và thông tin node kết nối:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

Tạo keyspace và bảng theo partition key `run_id`, clustering key `item_id`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sstable_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS sstable_lab.events_by_run (
    run_id text,
    item_id int,
    value text,
    updated_at timestamp,
    PRIMARY KEY ((run_id), item_id)
) WITH gc_grace_seconds = 864000;
~~~

`run_id` giúp cô lập mỗi lần thử trong một partition; `item_id` xác định một hàng trong partition. `updated_at` chỉ là **cột nghiệp vụ**, **không tự là timestamp của mutation** mà Cassandra dùng hòa giải. Khi muốn phân tích timestamp xóa/ghi phải hiểu thông tin nội bộ được dump.

Nếu `IF NOT EXISTS` gặp keyspace/bảng đã tồn tại, schema cũ **không tự thay đổi**. Kiểm tra replication/grace trước khi diễn giải:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'sstable_lab';

SELECT table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'sstable_lab'
  AND table_name = 'events_by_run';
~~~

### 5.2. Ghi và cập nhật một khóa

~~~sql
INSERT INTO sstable_lab.events_by_run
    (run_id, item_id, value, updated_at)
VALUES ('dump-demo-01', 1, 'DRAFT',
        '2026-11-21T09:00:00Z');

INSERT INTO sstable_lab.events_by_run
    (run_id, item_id, value, updated_at)
VALUES ('dump-demo-01', 2, 'CONTROL',
        '2026-11-21T09:00:00Z');
~~~

Trong **lab** có thể tạo ranh giới SSTable bằng flush:

~~~bash
# Flush có chủ đích để dễ có SSTable riêng, không dùng như
# thao tác định kỳ vô điều kiện trong production.
nodetool flush sstable_lab events_by_run
~~~

Tiếp tục:

~~~sql
UPDATE sstable_lab.events_by_run
SET value = 'PAID',
    updated_at = '2026-11-21T09:05:00Z'
WHERE run_id = 'dump-demo-01' AND item_id = 1;

DELETE FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01' AND item_id = 2;
~~~

Thực hiện flush lần nữa trong lab:

~~~bash
nodetool flush sstable_lab events_by_run
~~~

Việc này tạo **cơ hội** có nhiều SSTable chứa các trạng thái khác nhau. Nó **không bảo đảm** hai SSTable còn tách biệt mãi: compaction có thể chạy nền. Nếu cần bằng chứng chắc chắn về từng thời điểm, tạo snapshot trước/sau giai đoạn theo quy trình lab, thay vì đoán theo số file hiện tại.

Đọc kết quả logic qua CQL:

~~~sql
SELECT item_id, value, updated_at
FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01';
~~~

Nếu mọi mutation đã thành công và không có ghi cạnh tranh, kỳ vọng thấy hàng `item_id=1` với `PAID` và **không thấy** `item_id=2`. Nhưng SSTable cũ vẫn có thể chứa `DRAFT` hoặc `CONTROL`, còn SSTable mới có timestamp mới hoặc tombstone. **Đọc dump thấy giá trị cũ không chứng minh Cassandra đã trả dữ liệu cũ cho client.**

### 5.3. Tạo snapshot an toàn để dump

~~~bash
# Chỉ tạo snapshot của bảng lab và ghi rõ tag.
nodetool snapshot -t inspect-01 -cf events_by_run sstable_lab
~~~

Lệnh trên minh họa cú pháp thường dùng; option `-cf`/`--table`, vị trí keyspace và yêu cầu quyền có thể khác giữa phiên bản, vì vậy kiểm tra `nodetool help snapshot` của chính cluster trước khi chạy. Snapshot thường tham chiếu đến các SSTable trên đĩa bằng hard link hoặc cơ chế tương đương theo hệ thống tệp; nó **không phải bản sao backup độc lập đã kiểm thử restore**.

Xác định **đúng thư mục bảng** bằng cấu hình data directories và tên `events_by_run-<table_uuid>`, rồi tìm `snapshots/inspect-01`. Không đọc một thư mục snapshot của lần thử khác có chung tên bảng.

**Lưu ý memtable:** snapshot lưu trạng thái SSTable được tạo tại thời điểm chụp theo hành vi phiên bản/cờ; nếu có mutation chưa flush và snapshot không flush chúng, nội dung dump có thể không phản ánh mutation mới. Trong lab, hai lần `nodetool flush` đã giúp tách các mốc thử; không nên tự suy ra mọi snapshot của production luôn có toàn bộ mutation in-memory.

### 5.4. Chạy sstabledump trên tệp snapshot

~~~bash
# Thay toàn bộ đường dẫn placeholder bằng đường dẫn thật đã xác minh.
sstabledump \
  "/var/lib/cassandra/data/sstable_lab/events_by_run-<table_uuid>/snapshots/inspect-01/<descriptor>-Data.db"
~~~

Một snapshot có thể chứa **nhiều descriptor**; muốn kiểm tra đủ các SSTable liên quan phải lập danh sách và dump từng tệp trong phạm vi cho phép, không chỉ chọn tệp đầu tiên rồi tuyên bố đã kiểm tra toàn bộ bảng.

Đầu ra có thể dài: dùng phương pháp lưu/redact log được tổ chức cho phép hoặc lọc khóa bằng option **có trong `sstabledump --help`** của phiên bản. Không giả định có tham số `WHERE` giống CQL. Khi chia sẻ kết quả, loại bỏ payload/PII trước.

## 6. Diễn giải dump đúng: timestamp, tombstone và dữ liệu cũ

### 6.1. Dạng nội dung mong đợi

JSON do `sstabledump` trả về thường mô tả **partition**, **rows**, **clustering**, **cells** và metadata liên quan đến liveness/deletion. Dưới đây là **sơ đồ khái niệm**, không phải output JSON chuẩn của mọi phiên bản:

~~~text
SSTable cũ:
  partition key = dump-demo-01
  row item_id=1: value="DRAFT", timestamp=t1
  row item_id=2: value="CONTROL", timestamp=t1

SSTable mới:
  partition key = dump-demo-01
  row item_id=1: value="PAID", timestamp=t2 > t1
  row item_id=2: tombstone, deletion timestamp=t3 > t1

Kết quả SELECT sau reconciliation:
  item_id=1 -> PAID
  item_id=2 -> không trả hàng
~~~

**Giá trị trong SSTable cũ không phải “dữ liệu zombie” theo định nghĩa.** Cassandra lưu phiên bản cũ trong các SSTable bất biến rồi hòa giải khi đọc, và compaction chỉ loại bỏ khi đủ điều kiện. Zombie xảy ra trong tình huống bản ghi cũ **thực sự có thể tái xuất hiện** khi tombstone đã bị purge trước khi replica bỏ lỡ DELETE được đồng bộ, không phải chỉ vì `sstabledump` in ra chữ `CONTROL`.

### 6.2. Phân biệt ba mốc thời gian

| Thông tin | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `updated_at` trong CQL | Cột do ứng dụng gửi; phục vụ nghiệp vụ | Không tự bằng write timestamp nội bộ |
| **Write timestamp / deletion timestamp** | Được dùng trong hòa giải mutation/cell/tombstone theo quy tắc Cassandra | Không tự chứng minh client đã nhận ACK |
| **Local deletion time / TTL expiration** | Tham gia điều kiện hết hạn/thu hồi dữ liệu | Không có nghĩa dữ liệu được xóa vật lý ngay tại mốc hết hạn |

Cassandra có thể làm việc với timestamp tính ở độ phân giải microsecond; cách biểu diễn trong dump khác theo flag/version. Khi so giá trị, ghi rõ **đơn vị**, múi giờ, nguồn timestamp và có client-side timestamp hay không. Tránh so trực tiếp một microsecond epoch với một cột CQL biểu diễn giờ phút mà không chuyển đổi.

### 6.3. Đọc dump không thể thay SELECT ở CL mong muốn

`sstabledump` cho bạn cái nhìn vào **một SSTable của một node**. Còn một lệnh `SELECT` có thể:

1. Được coordinator gửi tới một hoặc nhiều replica theo CL.
2. Đọc dữ liệu từ memtable **và** nhiều SSTable.
3. Hòa giải timestamp, tombstone, TTL và các cell liên quan.
4. Trả kết quả logic đã qua bộ lọc projection, partition/clustering range.

Với RF=3 và `LOCAL_QUORUM`, client cần hai replica local phản hồi; dump từ một replica không xác nhận được mức nhất quán của truy vấn, tình trạng của replica thứ hai hoặc kết quả read repair. Nếu cần kết luận về replica divergence, phải đối chiếu tracing/repair/metrics và kết quả CQL có giới hạn.

## 7. Thực hành sstableverify offline cho bảng lab

### 7.1. Chuẩn bị tình huống

Trong lab RF=3, chọn một node cụ thể để kiểm tra, ví dụ `cass-3`. Trước khi dừng, ghi:

~~~bash
nodetool status
nodetool tablestats sstable_lab.events_by_run
nodetool compactionstats
~~~

Kiểm tra **hai replica còn lại của các partition liên quan đủ khỏe** nếu ứng dụng thử cần `LOCAL_QUORUM`. Không chủ động dừng hai node cùng lúc trong cluster chỉ có ba node/RF3. Nếu lab một node, không thể vừa tắt node vừa mong hệ thống tiếp tục phục vụ CQL; điều đó phù hợp với đặc tính topology, không phải lỗi verify.

### 7.2. Dừng và chạy công cụ

~~~bash
# Chỉ chạy bên trong lab ở node đã chọn.
# Cách dừng thực tế tùy systemd, Docker, Kubernetes hoặc supervisor.
sudo systemctl stop cassandra

# Xác nhận tiến trình đã dừng; không chỉ suy từ node DN.
sudo systemctl is-active cassandra

# Bộ công cụ phải tương thích với SSTable/metadata trên đĩa.
sstableverify sstable_lab events_by_run
~~~

Khi dùng container, cách dừng dịch vụ phải phù hợp image/runtime; **không gõ `systemctl` vô điều kiện bên trong image không dùng systemd**. Vì verify có thể đọc nhiều SSTable và kiểm tra sâu hơn tùy option, ghi lại thời gian hoàn tất, I/O, exit code và thông báo lỗi.

### 7.3. Sau khi verify

Nếu PASS và không có dấu hiệu rủi ro khác, khởi động lại theo runbook của môi trường, quan sát node trở về `UN`, kiểm tra hints/repair và đọc marker từ CQL. Nếu FAIL hoặc tool không đọc được tệp, **đừng restart/repair tự động mà không đánh giá loại lỗi và tính toàn vẹn của bản sao còn lại**; cần bảo toàn bằng chứng và có lựa chọn restore/replace.

Ví dụ lệnh kiểm tra sau restart ở node còn sống:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Đọc lại dữ liệu logic:

~~~sql
SELECT item_id, value
FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01';
~~~

**Kết luận đúng:** verify đánh giá tính hợp lệ của các SSTable được kiểm tra trên **một node**, CQL trả kết quả tại **CL và thời điểm xác định**, còn repair kiểm tra/đồng bộ **phạm vi giữa replica**. Ba mảnh bằng chứng bổ sung nhau, không cái nào một mình chứng minh toàn bộ hệ thống không mất dữ liệu.

## 8. So sánh với nodetool verify, scrub và repair

| Công cụ | Online/offline | Có chủ ý sửa dữ liệu? | Khi nào cân nhắc |
| --- | --- | --- | --- |
| `sstabledump` | Đọc snapshot khi node online; ưu tiên copy ổn định | Không | Phân tích một SSTable, timestamp, tombstone, giá trị vật lý |
| `sstableverify` | **Offline** theo quy trình an toàn | Không | Nghi SSTable bảng trên node hỏng; cần kiểm tra cục bộ có kiểm soát |
| `nodetool verify` | Chạy qua node Cassandra đang hoạt động | Không phải lệnh phục hồi dữ liệu | Muốn kiểm tra SSTable theo khả năng online và cờ hỗ trợ |
| `nodetool scrub` / `sstablescrub` | Tùy công cụ/phiên bản, có điều kiện offline | **Có thể thay đổi dữ liệu/SSTable** | Chỉ sau đánh giá corruption, backup, replica và rủi ro mất dữ liệu |
| `nodetool repair` | Phối hợp node/replica theo phạm vi | **Có truyền/sửa khác biệt replica** | Dữ liệu replica lệch hoặc lịch anti-entropy repair |
| `nodetool snapshot` | Thường thực hiện khi node online | Tạo snapshot tham chiếu dữ liệu | Chốt SSTable để phân tích/backup theo quy trình |

**Vì sao không dùng scrub như bước “verify nâng cao”?** Scrub có thể bỏ phần dữ liệu hỏng hoặc viết lại cấu trúc lưu trữ; nếu các replica khác không giữ dữ liệu tương ứng, tác động có thể không đảo ngược. Khi lỗi thật, cần tính **độ tin cậy dữ liệu nguồn**, không chỉ làm cho công cụ báo xanh.

**Vì sao repair không thay verify?** Repair so sánh và trao đổi dữ liệu giữa replica. Nó không cho phép kết luận các thành phần file trên đĩa hợp lệ theo mọi tiêu chí của verify, và có thể thất bại hoặc lan truyền vấn đề khi nguồn dữ liệu đã hỏng. Ngược lại, verify PASS trên mọi node cũng không chứng minh các replica giữ **cùng phiên bản mutation**.

## 9. Quy trình chẩn đoán khi nghi SSTable corruption

Một tình huống thực tế: ứng dụng Java thỉnh thoảng nhận read failure khi truy vấn partition `customer-X`, logs của một node nhắc đến checksum/đọc SSTable. Không nên ngay lập tức xóa file có tên trong log.

### Bước 1 — Xác minh triệu chứng

- Ghi **request ID**, query shape, partition key đã ẩn danh, CL, giờ lỗi, node/coordinator và message từ driver.
- Kiểm tra node status, disk errors, filesystem/I/O, CPU, compaction và repair đang chạy.
- Phân loại lỗi: `ReadTimeout`, `ReadFailure`, `Unavailable` hoặc lỗi ứng dụng không đồng nghĩa nhau; chỉ **file/log có bằng chứng** mới đủ cơ sở nghi corruption.

### Bước 2 — Khoanh vùng SSTable và giữ bằng chứng

- Ghi keyspace/table, node, SSTable descriptor/tệp được báo, phiên bản Cassandra, đường dẫn dữ liệu và thời gian.
- Đánh giá snapshot/copy ổn định; nếu nghi chính file dữ liệu có corruption, snapshot hard link **có thể chỉ trỏ tới cùng byte đã hỏng**. Cần backup/replica độc lập nếu mục tiêu là phục hồi.
- Không để log và dump chứa thông tin nhạy cảm lan ra ngoài phạm vi được phép.

### Bước 3 — Chọn công cụ có rủi ro phù hợp

- Cần xem phần dữ liệu, timestamp/tombstone: `sstabledump` trên snapshot ổn định, hiểu rằng tool **có thể không giải mã được file hỏng**.
- Cần kiểm tra file khi node vẫn online: đánh giá `nodetool verify` với tác động tài nguyên theo bản đang chạy.
- Cần kiểm tra offline sâu hơn: chuẩn bị downtime, RF/CL, nguồn restore, sau đó `sstableverify` theo đúng phiên bản.

### Bước 4 — Diễn giải, không sửa vội

| Kết quả quan sát | Diễn giải hợp lý | Hành động tiếp |
| --- | --- | --- |
| Dump đọc được nội dung | Một tệp có thể giải mã; có giá trị để xem timestamp/tombstone | Đối chiếu CQL và các SSTable khác; không tuyên bố toàn bảng lành |
| Dump lỗi giải mã | Có thể sai phiên bản/đường dẫn/thành phần hoặc file hỏng | Kiểm tra tương thích và logs, không xóa file |
| Offline verify FAIL | Có bằng chứng cần điều tra theo file/điểm kiểm tra | Đánh giá backup/replica, restore/replace/scrub theo runbook |
| Verify PASS nhưng SELECT thiếu hàng | Có thể do CL, tombstone, ghi chưa ACK, dữ liệu thiếu trên mọi replica | Đối chiếu manifest, query và repair; verify không tái tạo dữ liệu |
| SELECT đúng ở quorum nhưng một node báo lỗi | Replica khác có thể trả lời đủ CL | Khoanh vùng node hỏng, chuẩn bị sửa/replace, tránh kết luận cả cụm khỏe |

### Bước 5 — Phục hồi theo nguồn tin cậy

Nếu tệp cần phục hồi, xác định các replica còn tốt, snapshot/backup có thể restore, phạm vi token và lịch tombstone/repair. Có thể cần **replace/rebuild node** hoặc quy trình scrub/restore được hỗ trợ; lựa chọn phụ thuộc mức độ hỏng và bản Cassandra. Cần lập kế hoạch để không đưa **replica stale** quay lại sau khi tombstone đã bị purge (nguy cơ zombie).

### Bước 6 — Kiểm chứng sau khắc phục

Đọc các partition mục tiêu ở CL phù hợp, so với **manifest event/operation ID đã ACK** ở nguồn ngoài cluster. Ghi riêng `FOUND_MATCH`, `MISSING`, `MISMATCH` và `READ_ERROR`. Đồng thời kiểm tra repair coverage, trạng thái node, I/O và lỗi Cassandra. Không dùng `COUNT(*)` toàn bảng để chứng minh dữ liệu được giữ nguyên, vì truy vấn đó có thể quét rộng và hai tập dữ liệu khác nhau vẫn có count bằng nhau.

## 10. Java: thu bằng chứng đọc logic bên cạnh kết quả công cụ

Hai công cụ SSTable phân tích **file trên node**, còn Java Driver kiểm tra **kết quả mà ứng dụng thật nhìn thấy**. Ví dụ Java Driver 4.x dưới đây truy vấn một partition/clustering key được biết trước, không quét toàn bảng và không biến read error thành “không có dữ liệu”.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class SstableEvidenceProbe {
    public enum Outcome { MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement read;

    public SstableEvidenceProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT value FROM sstable_lab.events_by_run " +
            "WHERE run_id = ? AND item_id = ?");
    }

    public Outcome verify(String runId, int itemId, String expectedValue) {
        BoundStatement statement = read.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        try {
            Row row = session.execute(statement).one();
            if (row == null) {
                return Outcome.MISSING;
            }
            String actual = row.getString("value");
            return expectedValue.equals(actual)
                ? Outcome.MATCH : Outcome.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf(
                "READ_ERROR run=%s item=%d cause=%s%n",
                runId, itemId, error.getClass().getSimpleName());
            return Outcome.READ_ERROR;
        }
    }
}
~~~

Điểm cần hiểu:

- `MATCH` nghĩa là **SELECT tại LOCAL_QUORUM** trả đúng giá trị mong đợi, không phải mọi SSTable trên mọi node đã được verify.
- `MISSING` chỉ có nghĩa câu CQL hoàn tất nhưng không có hàng; nếu hàng đã DELETE thì đây có thể là kết quả **đúng**. Với manifest expected, cần ghi cả thao tác **DELETE đã ACK** để tránh báo false missing.
- `MISMATCH` có thể do timestamp/ghi khác, dữ liệu từ replica chưa hội tụ, nhầm khóa hoặc nguồn kỳ vọng sai; **không mặc nhiên là corruption**.
- `READ_ERROR` bao gồm timeout, unavailable hoặc lỗi khác; **không được cộng vào MISSING** khi thống kê mất dữ liệu.
- `LOCAL_QUORUM` giả định RF trong DC local có đủ replica, và client đã đặt local DC đúng. Khi node đang verify offline, các replica còn lại phải đủ đáp ứng.
- `CqlSession` và `PreparedStatement` cần được tái sử dụng; code ví dụ không tự tạo workload nặng và không thay nhiệm vụ backup/repair.

Khi dùng trong incident, lưu ít nhất: `operation_id`, keyspace.table, primary key đã ẩn danh, CL, timestamp, coordinator, exception type, kết quả đối soát, cùng tên node/descriptor từ logs của công cụ SSTable. **Đừng gửi giá trị payload bí mật vào log**; chỉ lưu marker hoặc hash phù hợp để chứng minh kết quả.

## 11. Giới hạn bằng chứng: bốn điều không thể suy ra

### 11.1. Dump thấy dữ liệu không có nghĩa SELECT phải trả dữ liệu

Một SSTable có `DRAFT` nhưng SSTable mới có `PAID` với timestamp cao hơn; hoặc có tombstone đã che `DRAFT`. Kết quả CQL là kết quả hòa giải theo rule của Cassandra, không phải một hàng được lựa chọn từ một file bất kỳ.

### 11.2. Verify PASS không có nghĩa replica đã hội tụ

Hai node có thể chứa SSTable đều hợp lệ nhưng giữ hai mutation phiên bản khác nhau. `sstableverify` kiểm tra file theo phạm vi cục bộ; `nodetool repair` và việc đối soát theo CL/manifest mới trả lời câu hỏi về khác biệt replica và dữ liệu mong đợi.

### 11.3. Không có lỗi verify không chứng minh không mất dữ liệu nghiệp vụ

Nếu một event chưa từng được ghi thành công vào Cassandra, tất cả SSTable có thể hợp lệ nhưng cùng thiếu event đó. Cần event log/outbox/backup hoặc nguồn nghiệp vụ tin cậy để xác định **expected IDs**, không chỉ kiểm tra dữ liệu đang có.

### 11.4. Tool thất bại không chứng minh data file hỏng

Sai Cassandra version, quyền file, classpath/config, schema mismatch hoặc đường dẫn không khớp cũng có thể khiến `sstabledump`/`sstableverify` không hoàn tất. Giữ riêng trạng thái **TOOL_ERROR/INCOMPLETE** với **VERIFIED_CORRUPTION** dựa trên bằng chứng cụ thể.

## 12. Mẫu biên bản chẩn đoán SSTable

| Trường | Ví dụ/điều cần lưu |
| --- | --- |
| Incident / request ID | `INC-...` hoặc ID từ hệ giám sát |
| Cassandra version / SSTable format | Bản chạy thực tế của từng node, descriptor |
| Keyspace/table | `sstable_lab.events_by_run` |
| Node/DC/rack | Tên node bị kiểm tra và topology |
| Thời gian | Giờ lỗi, giờ snapshot, giờ verify, timezone |
| Consistency level | `LOCAL_QUORUM` cho kiểm chứng CQL, RF/DC liên quan |
| File/snapshot path | Đường dẫn `<descriptor>-Data.db` đã xác minh |
| Tool/flags | `sstabledump` hoặc `sstableverify` cùng option thực dùng |
| Trạng thái node khi chạy | Online snapshot / offline verify; tiến trình đã dừng? |
| Kết quả | SUCCESS, FAIL có thông điệp, TOOL_ERROR hoặc INCOMPLETE |
| Tác động tài nguyên | I/O, CPU, dung lượng snapshot, thời gian |
| Đối soát logic | Expected/actual marker, found/missing/mismatch/read error |
| Hướng xử lý | Giữ nguyên, repair, restore, replace hoặc escalation có căn cứ |

Lưu biên bản ngoài node cần cứu, giới hạn quyền xem output dump, và không bỏ qua việc **dọn snapshot có kiểm soát** sau khi hết nhu cầu giữ bằng chứng. Snapshot thường giữ các SSTable hard link, làm dung lượng cũ khó được giải phóng dù compaction đã thay file. Không xóa toàn bộ snapshot của một keyspace chỉ vì muốn thu hồi vài GiB của lab.

## 13. Bài tập thực hành

**Bài 1 — Chọn công cụ đúng.** Một khách hàng báo `SELECT` trả `PAID` nhưng một node vẫn có SSTable chứa `DRAFT`. Bạn nên chạy `sstabledump` hay `sstableverify` trước? Giải thích vì sao nhìn thấy `DRAFT` vật lý không đủ kết luận lỗi.

**Bài 2 — Snapshot và phạm vi.** Tạo dữ liệu, cập nhật rồi xóa một hàng trong bảng lab. Flush và snapshot, dùng `sstabledump` với những `Data.db` tương ứng. Ghi rõ bạn đã đọc **bao nhiêu SSTable** và thời điểm snapshot; đối chiếu với câu CQL có partition key.

**Bài 3 — Điều kiện offline.** Cluster ba node RF3 đang có một node down. Bạn có nên dừng thêm node để chạy `sstableverify` nếu ứng dụng yêu cầu `LOCAL_QUORUM` không? Hãy tính số replica còn sẵn sàng và lập phương án dừng/lùi.

**Bài 4 — Kết quả verify.** Công cụ trả lỗi không tìm thấy metadata schema hoặc không đọc được data directory. Có thể tuyên bố corruption không? Bạn cần ghi những thông tin nào để phân biệt `TOOL_ERROR` với file hỏng?

**Bài 5 — Tombstone và zombie.** Một replica từng down quá `gc_grace_seconds`, dump của nó vẫn có hàng cũ; các node khác có thể đã purge tombstone. Vì sao không nên cho node cũ trở lại hoặc repair mù quáng? Đề xuất điều kiện rebuild/replace từ nguồn còn tin cậy.

**Bài 6 — Restore.** `sstableverify` FAIL trên một SSTable của node A, nhưng B và C vẫn đọc dữ liệu đúng ở `LOCAL_QUORUM`. Những điều gì phải xác minh trước khi replace/rebuild A? Vì sao chỉ một truy vấn thành công không chứng minh B/C có tất cả dữ liệu?

**Bài 7 — Security.** Output `sstabledump` chứa `email`, token hoặc payload khách hàng. Thiết kế quy trình redaction, quyền truy cập, lưu trữ tạm, thời hạn xóa và biên bản incident để dùng chứng cứ mà không lộ dữ liệu.

**Bài 8 — Đo chi phí công cụ.** Trên lab, dump một SSTable nhỏ và một SSTable lớn; đo thời gian/I/O và kích thước output. Vì sao chỉ nên dump tệp/partition nghi vấn thay vì export toàn bộ SSTable khi node đang gặp incident?

## Ghi nhớ

**`sstabledump` giúp xem nội dung vật lý của một SSTable; `sstableverify` kiểm tra tính hợp lệ của SSTable trên node theo quy trình offline.** Dump nên thực hiện trên **snapshot/copy ổn định** và phải diễn giải cùng timestamp, tombstone, TTL và các SSTable khác. Verify cần dừng Cassandra trên node đích, đánh giá RF/CL/downtime, có backup/nguồn replica tin cậy và lưu đầy đủ logs/exit code. Cả hai **không sửa dữ liệu, không thay anti-entropy repair và không tự chứng minh dữ liệu nghiệp vụ đầy đủ**. Chẩn đoán an toàn là đối chiếu **file + CQL + topology + manifest ngoài cluster**, rồi mới quyết định restore, replace hoặc sửa chữa theo đúng phiên bản.
