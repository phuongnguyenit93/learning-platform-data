# SAI gắn với memtable/SSTable và vòng đời dữ liệu trong Apache Cassandra

> **Chương:** Chỉ mục  
> **Phạm vi:** Apache Cassandra 5.0+, Storage-Attached Indexing (SAI), write/read path, flush, compaction, update/delete/TTL, index build, streaming và ứng dụng Java.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **memtable index**, **per-SSTable index**, **per-column index** và dữ liệu gốc.
2. Giải thích vì sao dữ liệu mới có thể tìm thấy qua SAI **trước khi flush**, và vì sao SAI luôn đi cùng vòng đời SSTable.
3. Phân tích đường đi của một mutation qua **commit log → memtable → flush → SSTable → compaction**.
4. Mô tả cách SAI kết hợp ứng viên từ nhiều SSTable và memtable, rồi **post-filter** theo timestamp/tombstone/TTL.
5. Dự đoán ảnh hưởng của tạo chỉ mục trên dữ liệu cũ, cập nhật/xóa hàng, compaction, rebuild và streaming.
6. Thực hành CQL, giám sát SAI, xử lý lỗi và đọc chỉ mục từ ứng dụng Java.

**Điều kiện:** SAI được tích hợp vào Apache Cassandra mã nguồn mở từ **5.0**. Cassandra 4.x mã nguồn mở không có cùng tính năng SAI tích hợp này. Bài dùng cú pháp và cách quan sát phù hợp Cassandra 5.0; cần đối chiếu môi trường thực tế trước khi chạy vận hành.

## 2. Trực giác nền tảng: chỉ mục đi cùng dữ liệu

Cassandra là cơ sở dữ liệu wide-column phân tán: partition key quyết định token và tập replica, còn dữ liệu tại mỗi replica đi qua commit log và memtable trước khi được flush thành **SSTable bất biến**. SAI là chỉ mục **cục bộ theo replica**, nằm cùng vòng đời lưu trữ của dữ liệu bảng tại replica đó. Nó không phải một chỉ mục tập trung duy nhất của toàn cluster.

~~~text
            CQL INSERT / UPDATE / DELETE
                         |
                  Coordinator + CL
                         |
                    Một replica
                      /      \
                 Commit log   Memtable dữ liệu
                                  |
                           Memtable index SAI
                                  |
                            (flush đồng bộ)
                                  v
                       SSTable-A + SAI-A
                       SSTable-B + SAI-B
                            \       /
                            Compaction
                                |
                                v
                       SSTable-C + SAI-C

Đọc WHERE trên cột có SAI:
  Memtable index + tất cả SAI-SSTable đang active
       -> danh sách ứng viên
       -> đọc hàng gốc và hợp nhất phiên bản
       -> kiểm điều kiện, TTL, tombstone
       -> trả dữ liệu hợp lệ
~~~

SAI được gọi là *storage-attached* bởi mỗi SSTable có các thành phần chỉ mục gắn với nó. Nhưng SAI **không chỉ hoạt động sau flush**: các mutation mới còn nằm trong memtable cũng được index để đọc ngay.

### Ba lớp phải phân biệt

| Lớp | Nơi lưu | Nội dung/ý nghĩa | Vòng đời |
|---|---|---|---|
| Dữ liệu bảng | Memtable, SSTable | Primary key, cột, timestamp, TTL, tombstone | Ghi, flush, compaction, repair |
| Memtable index | Bộ nhớ, gắn với memtable | Giá trị cột được index → primary key | Cập nhật cùng mutation, flush theo memtable |
| SSTable index | File SAI gắn với từng SSTable | Term → row ID; thông tin token/offset để tìm dữ liệu gốc | Sinh khi flush/build/compaction, thay thế cùng SSTable |

Một index SAI được tạo **trên một cột**. Nhiều index SAI trên cùng bảng dùng chung dữ liệu gốc và có thể dùng chung một số thành phần ánh xạ ở mức SSTable.

## 3. Bên trong một SSTable index

Khi tạo SSTable mới, SAI gán **row ID cục bộ** cho các hàng và lưu cấu trúc giúp chuyển từ row ID sang token/vị trí partition. Với mỗi cột có index, SAI lưu các **postings**, tức danh sách row ID ứng với một giá trị được tìm.

~~~text
SSTable-001
  Data.db             : dữ liệu bảng thật
  SAI shared mappings : row ID -> token / partition offset
  SAI status          : 'FAILED' -> {row 3, row 10}
  SAI latency_ms      : [1000..2000] -> {row 3, row 7}
                                               |
                                  lookup row ID vào Data.db
~~~

Hình chỉ nêu thành phần **logic**, không phải danh sách tên file cần thao tác bằng tay. File SAI không lưu một bản sao đầy đủ của bảng.

- **Cột text:** SAI dùng cấu trúc trie theo byte và postings cho các phép lọc văn bản được hỗ trợ.
- **Cột số:** SAI dùng cấu trúc dạng *kd-tree* cùng postings để tra cứu, kể cả điều kiện numeric range.
- **Per-SSTable shared files:** ánh xạ từ row ID đến token/partition offset được dùng chung giữa nhiều index cột, hạn chế lặp primary key đầy đủ.
- **Segment:** khi xây index từ luồng dữ liệu lớn, SAI giới hạn bộ nhớ bằng cách chia thành nhiều segment trong file chỉ mục; segment không phải replica hoặc partition mới.

**Đừng nhầm với primary index của Cassandra:** biết partition key vẫn là cách xác định phân vùng chủ động và hiệu quả nhất. SAI hỗ trợ lọc cột khác nhưng không tạo khả năng JOIN, ORDER BY toàn cục hay tìm kiếm full-text tùy ý.

## 4. Write path: mutation cập nhật cả index trong bộ nhớ

Giả sử bảng có SAI trên `status` và `latency_ms`, rồi nhận:

~~~sql
INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 1, 'FAILED', 1250, 'timeout');
~~~

Tại replica nhận ghi, Cassandra đưa mutation vào **commit log** để hỗ trợ khôi phục và cập nhật **memtable**. SAI nhận mutation, bổ sung giá trị cột được index và primary key liên quan vào **memtable index**. Cơ chế cập nhật chỉ mục của mutation là **đồng bộ**: khi replica xác nhận ghi, phần index của dữ liệu vừa ghi đã được cập nhật; không có job “xây chỉ mục sau vài phút” cho từng INSERT bình thường.

~~~text
Ghi team_a/1, status=FAILED, latency_ms=1250:

  CommitLog           Memtable dữ liệu        Memtable SAI
  [mutation]  ----->  team_a/1 : FAILED  ---> status: FAILED -> team_a/1
                          1250           ---> latency: 1250 -> team_a/1
~~~

Vì vậy truy vấn sau đây có thể tìm hàng **trước khi có SSTable mới**:

~~~sql
SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

Ở cluster nhiều replica, consistency level (ONE/LOCAL_QUORUM/...) và trạng thái replica vẫn chi phối kết quả như các thao tác Cassandra khác; index không bỏ qua yêu cầu nhất quán.

### Chi phí của memtable index

SAI cần xử lý thêm một lần cho từng cột được index và ước lượng bộ nhớ index được **tính vào ngân sách bộ nhớ memtable**. Khi thêm nhiều cột SAI, memtable có thể đạt ngưỡng flush sớm hơn, làm **số SSTable và file SAI tăng**. Chi phí write CPU, heap, disk I/O và compaction cần được đo trong điều kiện tải thực tế.

## 5. Flush: dữ liệu và SAI được ghi thành cùng thế hệ SSTable

Flush được kích hoạt do ngưỡng bộ nhớ, quản trị hoặc điều kiện khác của storage engine. Thay vì sửa SSTable cũ, Cassandra ghi **SSTable mới**; SAI đồng thời sinh index gắn với SSTable đó.

Cassandra 5.0 mô tả quá trình flush SAI thành hai pha:

1. **Ghi hàng dữ liệu và mapping dùng chung:** khi viết SSTable, engine cấp row ID, ghi mapping row ID → token/partition offset và ánh xạ tạm primary key → row ID.
2. **Ghi index cho từng cột:** SAI duyệt memtable index theo term, đổi primary key sang row ID, ghi postings và trie/kd-tree tương ứng.

Sau khi hoàn tất index cột, SAI tạo **marker hoàn tất**. Marker có ý nghĩa kể cả trường hợp SSTable không có giá trị index được, chẳng hạn chỉ có tombstone: engine cần phân biệt “không có gì để index” với “thiếu index vì lỗi build”.

~~~text
Trước flush                          Sau flush
------------                         -------------------------------
Memtable base row       ------->     SSTable-002 / base data
Memtable SAI status     ------->     SSTable-002 / SAI status
Memtable SAI latency    ------->     SSTable-002 / SAI latency
                                    SSTable-002 / shared mapping

SSTable-001 + SAI-001 vẫn còn nếu chưa được compaction.
~~~

Khi flush xong, cùng hàng vẫn truy vấn qua SAI được, nhưng nguồn index giờ là file SSTable thay vì memtable index. Không cần chạy rebuild_index thủ công sau mỗi flush.

Lệnh dùng để quan sát trên **một node** trong lab:

~~~bash
nodetool flush sai_lab events
~~~

Trong cluster phân tán, gọi nodetool ở một node không flush memtable trên các node khác.

## 6. Read path: tìm ứng viên rồi xác minh dữ liệu gốc

Khi nhận WHERE trên cột có SAI:

1. **Coordinator** phân tích điều kiện và lựa chọn index/độ chọn lọc để lập kế hoạch truy vấn trên token range cần thiết.
2. **Mỗi replica được hỏi** dùng query plan cục bộ để tra memtable index và các per-SSTable index có range liên quan.
3. Với một điều kiện (ví dụ `status='FAILED'`), SAI hợp nhất **union** ứng viên của các memtable/SSTable. Với nhiều điều kiện AND, có thể tạo **intersection** của ứng viên thuộc các cột.
4. SAI chuyển từ postings/row IDs sang partition và đọc hàng dữ liệu gốc, áp dụng quy tắc timestamp của Cassandra.
5. **Post-filter** loại những ứng viên không còn phù hợp vì UPDATE, DELETE, TTL, các điều kiện không index hoặc độ hạt partition.

~~~text
WHERE status = 'FAILED' AND latency_ms >= 1000

Memtable status index   ───┐
SSTable-A status index  ───┼─> union(status='FAILED') ──┐
SSTable-B status index  ───┘                           │
                                                     intersect
Memtable/SSTable latency indexes -> >= 1000 ──────────┘
                                                         |
                                                     row IDs
                                                         |
                                           đọc base row và post-filter
                                                         |
                                             hàng thỏa WHERE thật sự
~~~

SAI là **filtering engine**. Việc một giá trị có postings trong một SSTable chưa chứng minh giá trị đó vẫn là phiên bản mới nhất và còn sống. Đọc hàng gốc là bước cần thiết để bảo đảm semantics Cassandra.

### 6.1. UPDATE: postings cũ có thể vẫn còn

Giả sử cùng primary key `team_a/1`:

| Thời điểm | Mutation | Index có thể chứa | Kết quả của WHERE status='FAILED' |
|---|---|---|---|
| t1 | status=FAILED, flush vào A | A: FAILED → team_a/1 | Có team_a/1 |
| t2 | UPDATE status=OK ở memtable | A: FAILED; memtable: OK | **Không** có team_a/1 |
| t3 | Flush UPDATE vào B | A: FAILED; B: OK | **Không** có team_a/1 |
| t4 | Compaction A+B thành C | C chỉ index giá trị còn sống thích hợp | **Không** có team_a/1 |

Ở t2/t3, index cũ có thể trả team_a/1 như **ứng viên**. Khi đọc base row, Cassandra biết giá trị mới nhất là OK và loại ứng viên FAILED. Không cần sửa file SAI của SSTable-A tại chỗ.

### 6.2. DELETE và TTL: cần post-filter tombstone

DELETE sinh tombstone; TTL hết hạn làm dữ liệu trở thành không còn hiệu lực theo quy tắc sống/chết của Cassandra. SAI **không lưu tombstone như một term cần tìm**. Candidate từ SSTable cũ có thể bị tombstone mới che khuất, nên engine phải xét thông tin xóa và TTL khi lọc. Tombstone chưa chắc được thu hồi vật lý ngay; dọn bỏ an toàn phụ thuộc compaction, grace period và trạng thái dữ liệu giữa replica.

Post-filter nhiều làm tăng I/O vì phải kiểm những ứng viên cuối cùng bị loại. Metrics `RowsFiltered` và tracing giúp tìm tình huống này.

### 6.3. Có hoặc không có partition key

~~~sql
-- Chỉ định partition: đã biết phạm vi dữ liệu cần tìm.
SELECT event_id, status
FROM sai_lab.events
WHERE tenant_id = 'team_a' AND status = 'FAILED';

-- Không có partition key: có thể cần nhiều token range/replica.
SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

Nếu status FAILED xuất hiện tại hầu hết partition, index có độ chọn lọc kém. Câu truy vấn vẫn có thể hợp lệ nhưng tốn tài nguyên trên cluster lớn. **SAI không miễn phí việc quét phân tán**.

## 7. Compaction: SSTable mới đi kèm index mới

SSTable là immutable nên UPDATE/DELETE không ghi đè bản cũ. Sau nhiều đợt flush, một row có thể tồn tại trong nhiều SSTable. Compaction hợp nhất các thế hệ, giải quyết phiên bản/tombstone đủ điều kiện, ghi **SSTable đầu ra mới**.

Khi compaction chạy, SAI nhận các hàng đầu ra để **xây index mới**. Khác với memtable index đã sắp theo term, luồng dữ liệu compaction cần buffer và sort term/postings; SAI sử dụng **segment buffer** với giới hạn bộ nhớ để xây các cấu trúc on-disk.

~~~text
    Trước compaction                Sau compaction thành công

 SSTable-A + SAI-A ----┐
                      ├---->       SSTable-C + SAI-C
 SSTable-B + SAI-B ----┘            (dữ liệu sau hợp nhất)

 Không cập nhật index A/B tại chỗ.
 Index C trở thành active cùng SSTable-C.
~~~

Sau khi hoàn tất, Cassandra/SAI **chuyển view SSTable và index** sang thế hệ mới một cách nguyên tử. Truy vấn đang dùng A/B giữ tham chiếu cho đến khi an toàn để giải phóng; vì thế file cũ có thể chưa được xóa khỏi đĩa ngay lập tức.

### Lựa chọn compaction strategy

- **STCS (SizeTieredCompactionStrategy):** phù hợp nhiều workload SAI; giảm số SSTable cần dò bằng cách hợp nhất nhóm SSTable kích thước tương đương.
- **TWCS (TimeWindowCompactionStrategy):** cân nhắc cho dữ liệu time series/TTL với vòng đời theo cửa sổ; giúp giới hạn phạm vi file theo thời gian nếu dữ liệu có đặc điểm phù hợp.
- Compaction quá ít làm số SSTable/segment tăng; compaction quá nhiều gây disk I/O, CPU và công việc build index đầu ra.
- Không chạy major compaction đại trà để chữa chậm SAI: cần xem chiến lược hiện tại, khoảng trống đĩa, tombstone, mức tải và khả năng thu hồi.

## 8. Các sự kiện khác trong vòng đời dữ liệu và SAI

| Sự kiện | Dữ liệu gốc | Hành vi của SAI | Điều cần kiểm tra |
|---|---|---|---|
| INSERT/UPDATE | Mutation vào memtable và commit log | Cập nhật memtable index đồng bộ | Memory, write latency |
| Flush | Memtable thành SSTable mới | Viết index gắn với SSTable vừa tạo | Flush rate, số SSTable |
| DELETE/TTL hết hạn | Tombstone/giá trị không còn sống | Posting cũ có thể còn, read post-filter loại | RowsFiltered, compaction |
| Compaction | Hợp nhất các SSTable đủ điều kiện | Xây index trên SSTable đầu ra, đổi view | Disk I/O, backlog, số segment |
| CREATE INDEX trên bảng đã có dữ liệu | Dữ liệu cũ vẫn nguyên | **Backfill/build** index cho SSTable đã tồn tại | is_building, is_queryable |
| DROP INDEX | Bảng dữ liệu giữ nguyên | Xóa cấu trúc index tương ứng | Các query lệ thuộc index |
| Bootstrap/decommission, streaming SSTable | SSTable được truyền qua node | SAI hỗ trợ zero-copy streaming cùng SSTable | Tính tương thích, trạng thái node nhận |
| Snapshot/restore | Tái sử dụng các file SSTable | File SAI thuộc vòng đời SSTable | Quy trình backup/restore của phiên bản đang dùng |
| Repair | Đối chiếu và đồng bộ dữ liệu giữa replica | Các index SSTable được quản lý theo file dữ liệu, xây lại nếu cần | Repair của dữ liệu và trạng thái index là hai kiểm tra riêng |
| Index bị lỗi hoặc thiếu component | Dữ liệu gốc có thể vẫn hợp lệ | Index có thể không queryable | Log, disk, rebuild_index đúng node |

### 8.1. CREATE INDEX sau khi dữ liệu đã tồn tại

Cassandra cho phép tạo SAI **sau** khi bảng có dữ liệu. Khi đó, SAI phải đọc dữ liệu hiện có để tạo các index cục bộ cho SSTable và memtable liên quan. Lệnh CREATE INDEX trả về không bảo đảm toàn bộ index trên mọi replica đã xây xong; cần quan sát trạng thái build và queryable trên **các node liên quan** trước khi cho ứng dụng dựa vào index.

Một chỉ mục SAI không thể thay đổi tùy chọn bằng ALTER INDEX. Khi cần đổi cấu hình index, quy trình là DROP rồi CREATE lại, tạo giai đoạn index chưa queryable cần lên kế hoạch cho ứng dụng.

### 8.2. Streaming và repair

Vì index gắn với SSTable, SAI hỗ trợ **zero-copy streaming** khi bootstrap/decommission và trong các đường streaming tương thích của engine: dữ liệu cùng các thành phần index có thể đi theo nhau mà không cần đẩy mọi hàng qua một pipeline lập chỉ mục trung tâm. Tuy nhiên, mọi node vẫn cần có trạng thái index cục bộ đúng trước khi phục vụ query.

Phân biệt hai tác vụ vận hành:

- `nodetool repair`: sửa khác biệt **dữ liệu giữa các replica** và có thể kéo theo streaming SSTable.
- `nodetool rebuild_index`: xây lại **chỉ mục cục bộ** của một bảng trên node được gọi; không thay thế repair.

Nếu query qua SAI có vấn đề sau streaming/repair, kiểm tra cả **sức khỏe dữ liệu replica** lẫn **index queryability**. Chỉ rebuild index không chữa được dữ liệu gốc bị thiếu trên replica.

## 9. Thực hành CQL trên Cassandra 5.0

**Môi trường:** Cassandra 5.0 một node, cqlsh và quyền chạy nodetool. Cấu hình SimpleStrategy RF=1 bên dưới **chỉ dành cho lab đơn node**; production nên dùng NetworkTopologyStrategy và RF phù hợp topology.

### Bước 1 — Tạo bảng và dữ liệu *trước khi* có index

~~~sql
CREATE KEYSPACE IF NOT EXISTS sai_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS sai_lab.events (
    tenant_id text,
    event_id int,
    status text,
    latency_ms int,
    payload text,
    PRIMARY KEY ((tenant_id), event_id)
);

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 1, 'FAILED', 1250, 'timeout');

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_a', 2, 'OK', 100, 'accepted');

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_b', 3, 'FAILED', 2200, 'upstream');

SELECT * FROM sai_lab.events WHERE tenant_id = 'team_a';
~~~

Yêu cầu flush **trước khi tạo SAI** để thấy index build cho SSTable đã có từ trước:

~~~bash
nodetool flush sai_lab events
~~~

### Bước 2 — Tạo hai index SAI

~~~sql
CREATE INDEX IF NOT EXISTS events_status_sai
ON sai_lab.events (status)
USING 'sai';

CREATE INDEX IF NOT EXISTS events_latency_sai
ON sai_lab.events (latency_ms)
USING 'sai';
~~~

Index được xây cho các cột của dữ liệu có sẵn. Kiểm tra trạng thái qua virtual table:

~~~sql
SELECT index_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'sai_lab'
  AND table_name = 'events'
  AND index_name = 'events_status_sai';

SELECT index_name, is_building, is_queryable
FROM system_views.indexes
WHERE keyspace_name = 'sai_lab'
  AND table_name = 'events'
  AND index_name = 'events_latency_sai';
~~~

Virtual table mô tả trạng thái cục bộ theo node. Chỉ thử query sử dụng SAI **sau khi** index tương ứng trên node/replica có thể phục vụ truy vấn (`is_queryable = true`).

### Bước 3 — Query qua một hoặc hai SAI

~~~sql
SELECT tenant_id, event_id, status, latency_ms
FROM sai_lab.events
WHERE status = 'FAILED';

SELECT tenant_id, event_id, status, latency_ms
FROM sai_lab.events
WHERE status = 'FAILED' AND latency_ms >= 1000;
~~~

Với dữ liệu vừa tạo, cả hai câu trả về hai hàng thuộc `team_a/1` và `team_b/3` (không giả định thứ tự giữa các partition). Trong môi trường nhiều node, cùng mẫu query thiếu partition key có thể phải đọc nhiều token range.

### Bước 4 — UPDATE khi SSTable cũ vẫn có giá trị FAILED

~~~sql
UPDATE sai_lab.events
SET status = 'OK', latency_ms = 200
WHERE tenant_id = 'team_a' AND event_id = 1;

SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';
~~~

Kết quả đúng sau UPDATE chỉ còn `team_b/3`. SSTable cũ chưa bị sửa và có thể vẫn giữ posting FAILED của `team_a/1`, nhưng read path loại hàng đó nhờ dữ liệu mới nhất và post-filter.

~~~bash
nodetool flush sai_lab events
~~~

Chạy lại SELECT; kết quả logic vẫn như trước dù mutation đã chuyển từ memtable sang một SSTable/index mới.

### Bước 5 — DELETE và TTL

~~~sql
DELETE FROM sai_lab.events
WHERE tenant_id = 'team_b' AND event_id = 3;

SELECT tenant_id, event_id, status
FROM sai_lab.events
WHERE status = 'FAILED';

INSERT INTO sai_lab.events
    (tenant_id, event_id, status, latency_ms, payload)
VALUES ('team_c', 4, 'FAILED', 1700, 'temporary')
USING TTL 60;
~~~

Hàng `team_b/3` đã xóa không xuất hiện trong truy vấn, kể cả khi postings cũ vẫn còn ở SSTable. Hàng `team_c/4` sẽ hết hiệu lực sau TTL; không có nghĩa Cassandra chạy compaction ngay tại thời điểm đủ 60 giây.

### Bước 6 — Theo dõi trước/sau compaction

Trong lab, khi muốn minh họa việc thay thế thế hệ SSTable và index:

~~~bash
# Chỉ làm trên lab để quan sát; production cần đánh giá I/O.
nodetool compact sai_lab events
~~~

Kiểm tra lại trạng thái index bằng các câu SELECT ở Bước 2. Hai virtual table khác có thể dùng để quan sát SSTable và segment index là `system_views.sstable_indexes` và `system_views.sstable_index_segments`. Cột và cách lọc có thể thay đổi giữa phiên bản; xem schema virtual table của cluster thực tế trước khi viết câu truy vấn chẩn đoán.

### Bước 7 — Xây lại index cục bộ khi được phép

~~~bash
# Trên node cần xây lại index, không thao tác trực tiếp trên file *.db.
nodetool rebuild_index sai_lab events events_status_sai
~~~

Lệnh này xây lại chỉ mục `events_status_sai` của bảng `sai_lab.events` tại node đang gọi. Theo dõi index status và log trong suốt quá trình. Đây là bài thực hành về rebuild, không phải tình huống khuyến nghị chạy định kỳ nếu index vẫn khỏe.

## 10. Giám sát và xử lý lỗi SAI

### 10.1. Quan sát bằng virtual tables, tracing và JMX

| Tín hiệu | Nguồn quan sát | Ý nghĩa |
|---|---|---|
| `is_building`, `is_queryable` | `system_views.indexes` | Phân biệt schema đã tạo với index đã sẵn sàng |
| Kích thước và số SSTable index | `system_views.sstable_indexes` | Số file và khoảng token có index |
| Số segment và chi phí chia segment | `system_views.sstable_index_segments` | Mức phân mảnh của cấu trúc index |
| `DiskUsedBytes` | SAI JMX | Dung lượng các file index |
| `ColumnIndexBuildsInProgress` | SAI JMX | Số index build đang chạy |
| `SSTableIndexesHit` | SAI JMX | Mức độ truy vấn phải chạm nhiều SSTable index |
| `RowsFiltered` hoặc `TotalRowsFiltered` | SAI JMX | Số ứng viên bị post-filter loại |
| `PartitionReads`, `TotalPartitionReads` | SAI JMX | Phân vùng phải đọc sau khi dùng index |
| `QueryLatency`, `TotalQueryTimeouts` | SAI JMX | Trải nghiệm truy vấn SAI và timeout |

Tracing từ cqlsh là cách học tốt để quan sát luồng query:

~~~sql
TRACING ON;

SELECT tenant_id, event_id
FROM sai_lab.events
WHERE status = 'FAILED';

TRACING OFF;
~~~

Trace có thể cho thấy số memtable index, SSTable index, segment được duyệt và số hàng post-filter. **Không bật tracing đại trà** ở production vì nó tăng overhead.

### 10.2. Chẩn đoán theo triệu chứng

| Triệu chứng | Cần kiểm tra | Hành động phù hợp |
|---|---|---|
| CREATE INDEX xong nhưng query không dùng được | Build chưa hoàn tất, `is_queryable=false` trên một số node | Xác minh trạng thái mọi replica và log build |
| Tạo index mới làm CPU/disk tăng mạnh | Backfill SSTable lịch sử | Đặt lịch thấp tải, kiểm memory và I/O |
| Query SAI chậm dù số hàng cuối ít | Nhiều SSTable hoặc post-filter nhiều | Trace, đo `SSTableIndexesHit` và `RowsFiltered` |
| Thêm index làm flush xảy ra dày | Memtable tính thêm heap cho SAI | Đo flush rate, cân nhắc bớt index không cần |
| DELETE rồi vẫn thấy file cũ trên đĩa | Tombstone, snapshot, compaction chưa dọn | Kiểm grace period, compaction và snapshot |
| Sau compaction file index cũ chưa biến mất | Reader/snapshot giữ SSTable cũ | Quan sát active compaction, snapshot, disk |
| Index không queryable sau lỗi file | Build/streaming lỗi hoặc index component thiếu | Xem log/disk, rebuild_index có kiểm soát |
| Truy vấn khác nhau giữa các replica | Dữ liệu chưa đồng bộ hoặc tình trạng index khác nhau | Xác minh repair, replica health và trạng thái index |

Không xóa/sửa trực tiếp các file SAI trên đĩa để “đồng bộ lại” và không coi `nodetool compact` là công cụ chữa tất cả lỗi. **Đồng bộ dữ liệu replica** và **xây lại index cục bộ** là hai công việc khác nhau.

## 11. Tối ưu thiết kế truy vấn khi dùng SAI

SAI rất hữu ích cho bộ lọc linh hoạt trên các cột không thuộc partition key, nhưng Cassandra vẫn ưu tiên **mô hình bảng theo truy vấn chính**. Trước khi tạo nhiều index, hãy trả lời:

1. **Độ chọn lọc:** điều kiện trả về ít hay nhiều partition? Giá trị phổ biến trên toàn cluster có thể rất đắt.
2. **Phạm vi:** WHERE có partition key không? Nếu không, có chấp nhận query qua nhiều token range không?
3. **Tỷ lệ đọc/ghi:** mỗi index cột có thêm chi phí mutation, heap, flush và compaction.
4. **Tình trạng SSTable:** có backlog compaction khiến một truy vấn phải tra nhiều per-SSTable index không?
5. **TTL/DELETE/UPDATE:** có nhiều bản ghi hết hiệu lực phải post-filter không?
6. **Khả năng của CQL:** ứng dụng có cần JOIN, sắp xếp toàn cục, ranking văn bản hoặc pagination tùy ý không? SAI là filter, không phải search engine tổng quát.

Nên benchmark bằng **dữ liệu và phân bố partition thật**, RF/CL dự kiến, concurrency, SAI hit rate, latency và số SSTable thực tế. Việc một câu SELECT chạy được trong lab không bảo đảm truy vấn đó kinh tế trên production.

## 12. Dùng SAI từ ứng dụng Java

Với Cassandra Java Driver 4.x, truy vấn dựa trên SAI vẫn là CQL thông thường; driver không quản lý một bộ index riêng. Ví dụ sử dụng `CqlSession` được ứng dụng tạo sẵn:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

public final class EventSearch {
    public static ResultSet findSlowEvents(
            CqlSession session, int minLatencyMs) {
        SimpleStatement query = SimpleStatement.builder(
                "SELECT tenant_id, event_id, latency_ms " +
                "FROM sai_lab.events WHERE latency_ms >= ?")
            .addPositionalValue(minLatencyMs)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
            .setPageSize(100)
            .build();

        return session.execute(query);
    }
}
~~~

Đây là ví dụ cách gán CL và page size, không phải cấu hình production mặc định: `LOCAL_ONE` phù hợp minh họa lab, còn production phải lựa chọn theo SLA và mức nhất quán. Tái sử dụng session theo vòng đời ứng dụng, cấu hình local datacenter đúng, và xử lý phân trang để không đưa quá nhiều kết quả vào bộ nhớ. Trước khi bật query mới trong ứng dụng Java, xác minh SAI đã **queryable** tại tất cả node có thể phục vụ nó.

## 13. Câu hỏi kiểm tra hiểu biết

**1.** Vì sao vừa INSERT xong, chưa flush vẫn SELECT được theo chỉ mục SAI?  
*Đáp án:* Vì mutation cập nhật memtable index đồng bộ với memtable dữ liệu.

**2.** Sau UPDATE status=FAILED → OK, vì sao postings cũ trong SSTable không gây trả lại hàng sai?  
*Đáp án:* Index chọn candidate; bước đọc base row/post-filter kiểm phiên bản hiện hành.

**3.** Compaction giữa SSTable A và B có viết sửa postings trong A/B không?  
*Đáp án:* Không; nó tạo SSTable C và index C mới, rồi chuyển view khi thành công.

**4.** Tại sao tạo SAI trên bảng đã có hàng có thể chậm?  
*Đáp án:* Cassandra phải backfill/build index cho dữ liệu lịch sử đang nằm trên SSTable.

**5.** `rebuild_index` và `repair` khác nhau thế nào?  
*Đáp án:* Rebuild xây chỉ mục cục bộ; repair đối chiếu và đồng bộ dữ liệu của các replica.

**6.** Nhiều SSTable ảnh hưởng SAI ra sao?  
*Đáp án:* Query có thể phải kiểm nhiều index/segment, sau đó post-filter và đọc base row nhiều hơn.

**7.** TTL hết hạn có lập tức xóa posting cũ trên SSTable không?  
*Đáp án:* Không; đọc phải xét thời hạn và tombstone; compaction chỉ dọn vật lý khi đủ điều kiện.

## 14. Ghi nhớ

~~~text
Mutation → memtable + SAI trong RAM → flush
         → SSTable bất biến + SAI gắn với SSTable
         → nhiều thế hệ SSTable khi UPDATE/DELETE/TTL
         → đọc: hợp/giao index candidate + post-filter base row
         → compaction: sinh SSTable và SAI mới, đổi view nguyên tử
~~~

Hai nguyên lý cốt lõi: **SAI được cập nhật theo đúng vòng đời lưu trữ của dữ liệu**, từ memtable đến SSTable; **index chỉ trả ứng viên**, còn giá trị mới nhất, TTL và tombstone được quyết định khi Cassandra đọc và hợp nhất dữ liệu gốc.

## Tài liệu tham khảo

- [Apache Cassandra 5.0 — SAI write path and read path](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-read-write-paths.html) — memtable index, flush, compaction và post-filter.
- [Apache Cassandra 5.0 — SAI concepts](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-concepts.html) — kiến trúc storage-attached, streaming.
- [Apache Cassandra 5.0 — Working with SAI](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/sai-working-with.html) — tạo, dùng và bỏ SAI trong CQL.
- [Apache Cassandra 5.0 — Monitor SAI indexes](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/indexing/sai/operations/monitoring.html) — virtual tables, tracing, JMX.
- [Apache Cassandra 5.0 — rebuild_index](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/rebuild_index.html) — cú pháp rebuild index.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtable, SSTable.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — DELETE, TTL và compaction.
