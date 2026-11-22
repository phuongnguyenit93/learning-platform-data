# Giới hạn tác động đến compaction, dung lượng và tải replica khi di chuyển dữ liệu Cassandra

## 1. Vì sao di chuyển schema có thể làm cluster quá tải dù từng câu CQL đều hợp lệ?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, đặt partition theo **partition key** và giữ nhiều bản sao dựa trên replication strategy. Ứng dụng Java truy vấn bằng CQL, lựa chọn consistency level và chịu ảnh hưởng của SSTable, compaction, repair, streaming và trạng thái các replica.

Khi thay đổi schema, chẳng hạn chuyển từ một bảng có partition quá rộng sang bảng bucket theo tháng, đội phát triển thường muốn làm ba việc:

1. Tạo bảng mới với partition key phù hợp cách truy vấn.
2. **Backfill** dữ liệu lịch sử từ bảng cũ sang bảng mới.
3. Chuyển ứng dụng sang đọc/ghi bảng mới rồi thu hồi bảng cũ.

Nếu backfill chạy hết tốc độ, hệ thống có thể gặp vòng phản hồi nguy hiểm:

~~~mermaid
flowchart TD
    A["Backfill đọc dữ liệu nguồn"] --> B["Read I/O và network tăng"]
    A --> C["Ghi mutation vào bảng đích"]
    C --> D["Memtable flush sinh thêm SSTable"]
    D --> E["Compaction backlog tăng"]
    E --> F["Disk I/O và dung lượng tạm tăng"]
    F --> G["Replica phản hồi chậm"]
    G --> H["p99, timeout và retry tăng"]
    H --> I["Tải request lên replica tăng thêm"]
    I --> F
    J["Repair, streaming hoặc backup đồng thời"] --> F
~~~

**Vấn đề không chỉ nằm ở số dòng di chuyển.** Cần tính cả hệ số replication, write amplification, file tạm trong compaction, mức song song của Java driver, đường đọc nguồn và thao tác vận hành khác cùng diễn ra.

Bài thuộc chương **Di chuyển và schema** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Mục tiêu là xây dựng quy trình di chuyển có kiểm soát, tránh đánh đổi hiệu năng, dung lượng hay tính đúng chỉ để rút ngắn thời gian backfill.

## 2. Phân biệt thay đổi metadata và di chuyển dữ liệu thực

Không phải mọi thay đổi schema đều có chi phí giống nhau.

| Loại thay đổi | Ví dụ | Tải dữ liệu dự kiến | Lưu ý |
|---|---|---|---|
| Thay đổi metadata được CQL hỗ trợ | Thêm cột thường bằng `ALTER TABLE ... ADD` | Không nhất thiết đọc/ghi lại toàn bảng ngay | Phải xét phiên bản, khả năng tương thích client và semantic |
| Tạo bảng phục vụ truy vấn mới | `CREATE TABLE ...` rồi backfill | Đọc nguồn và ghi dữ liệu đích với RF của đích | Có thể gần như nhân đôi dung lượng trong giai đoạn chuyển tiếp |
| Thay partition key/clustering key | Chuyển partition theo ngày/tháng | Thường phải tạo bảng mới và viết lại logical rows | Cassandra không cho sửa tùy ý primary key của bảng hiện hữu |
| Đổi định dạng hoặc kiểu dữ liệu | Chuẩn hóa timestamp, chuyển kiểu field | Có thể cần parse, transform và rewrite dữ liệu | Không chỉ copy SSTable trực tiếp |
| Thêm index hoặc materialized view | Tạo đường truy vấn phụ | Có thể cần xây dựng dữ liệu nền riêng | Tác động I/O và tính năng tùy phiên bản |
| Thay replication factor | RF=2 sang RF=3 | Thay số replica cần giữ, kèm quy trình đồng bộ dữ liệu | Không phải bài toán giống backfill bảng ứng dụng |
| Chuyển cluster/DC | Thay nơi đặt dữ liệu | Có thể streaming hoặc import/export lớn | Tính topology, network và token ranges |

**Đừng viết kế hoạch chung “schema change ít tốn tài nguyên”**. Một lệnh thay metadata có thể rất nhẹ, nhưng một migration đi kèm backfill tất cả partition là workload đọc/ghi quy mô lớn.

### 2.1. Thí dụ nghiệp vụ: thay bảng truy vấn đơn hàng

Bảng cũ:

~~~cql
CREATE KEYSPACE commerce
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE commerce.orders_by_customer_v1 (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Với khách hàng có lịch sử nhiều năm, **một partition `customer_id`** có thể rất rộng. Để giới hạn phạm vi đọc và SSTable merge theo tháng, tạo bảng mới:

~~~cql
CREATE TABLE commerce.orders_by_customer_month_v2 (
    customer_id uuid,
    order_month date,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

`order_month` là **ngày đầu tiên của tháng theo UTC** trong ví dụ, do ứng dụng tính từ `created_at`. Mỗi tổ hợp `(customer_id, order_month)` là một partition riêng, giúp API lấy đơn của một tháng cụ thể thay vì quét partition nhiều năm.

**Cassandra không tự chuyển dữ liệu v1 sang v2** khi câu `CREATE TABLE` hoàn thành. Đó là phần cần thiết kế backfill, đồng bộ ghi mới và chuyển đọc.

### 2.2. Query phục vụ truy vấn phải đúng cả hai phía

~~~cql
-- Nguồn: đọc lịch sử của một customer.
SELECT created_at, order_id, amount, status
FROM commerce.orders_by_customer_v1
WHERE customer_id = 11111111-1111-1111-1111-111111111111;

-- Đích: đọc một tháng của customer.
SELECT created_at, order_id, amount, status
FROM commerce.orders_by_customer_month_v2
WHERE customer_id = 11111111-1111-1111-1111-111111111111
  AND order_month = '2026-11-01'
LIMIT 50;
~~~

Query nguồn chỉ nên được chạy **theo một danh sách customer/partition đã biết hoặc một cơ chế quét được thiết kế riêng có kiểm soát**. Nếu v1 chứa partition cực rộng, ngay cả việc đọc đúng partition key vẫn có thể đắt; phải giới hạn paging, nhịp đọc và đo dung lượng mỗi partition.

## 3. Ba khoản chi phí cần dự báo trước khi chạy

### 3.1. Tải đọc nguồn

Backfill phải đọc dữ liệu từ v1:

- Read tại replica có thể phải merge memtable và nhiều SSTable.
- Tombstone/TTL khiến số entry phải quét nhiều hơn số row được trả.
- Query theo partition rộng có thể đòi nhiều page và làm client giữ buffer.
- Consistency level đọc ảnh hưởng số replica tham gia và độ trễ.
- Nếu lấy nhiều partition song song, load không nhất thiết trải đều giữa các token ranges.

### 3.2. Tải ghi đích

Mỗi mutation vào v2 có thể được gửi tới nhiều replica theo RF và placement:

- Replica ghi commit log và memtable.
- Memtable flush thành SSTable khi cần.
- Compaction ghi lại các SSTable theo strategy.
- Hints, repair và các tác vụ nền có thể cần xử lý các replica thiếu dữ liệu.
- Ở multi-DC, traffic liên DC có thể lớn dù worker chỉ kết nối từ một datacenter.

**RF=3 không đồng nghĩa một mutation tạo đúng ba thao tác I/O đĩa cố định.** Nó cho biết số bản sao được đặt theo replication strategy; số message, ACK, flush và compaction còn phụ thuộc CL, routing, workload và trạng thái node.

### 3.3. Dung lượng lưu trữ tạm thời

Trong giai đoạn hai bảng cùng tồn tại, nhiều tài nguyên có thể chiếm chỗ:

- SSTable và snapshot của bảng v1.
- SSTable v2 đang tăng theo backfill.
- SSTable đầu ra được tạo trong compaction **khi file đầu vào cũ chưa được giải phóng**.
- Commit log, hints, temporary files, streaming/repair.
- Dữ liệu tăng thêm từ traffic mới trong lúc migration kéo dài.

Vì vậy **không chỉ lấy tổng dữ liệu logic nhân RF rồi coi đó là peak disk usage**.

## 4. Mô hình tính dung lượng và headroom

### 4.1. Công thức lập ngân sách sơ bộ

Với cùng một cluster giữ v1 và v2:

~~~text
Peak physical storage (ước lượng)
≈ physical_bytes(v1, còn phải giữ)
 + physical_bytes(v2 sau backfill)
 + temporary_bytes(compaction/streaming/flush)
 + snapshots/backups đang giữ trên cùng filesystem
 + tăng trưởng dữ liệu mới
 + biên an toàn vận hành
~~~

Các biến phải lấy từ **storage metrics theo node**; đây không phải công thức chính xác cho từng compaction strategy. Kích thước SSTable vật lý chịu ảnh hưởng nén, TTL, tombstone và mức trùng lặp vật lý.

### 4.2. Ví dụ capacity theo cluster

Giả sử có **6 node** và các con số vật lý sau:

| Hạng mục | Tổng toàn cluster | Bình quân một node nếu phân phối đều |
|---|---:|---:|
| Dữ liệu SSTable bảng cũ | 6,0 TiB | 1,00 TiB |
| Dữ liệu SSTable bảng mới sau migration | 5,4 TiB | 0,90 TiB |
| Peak tạm do compaction/flush/streaming (giả định) | 1,5 TiB | 0,25 TiB |
| **Tổng chưa cộng snapshot và biên an toàn** | **12,9 TiB** | **2,15 TiB** |

Nếu mỗi node chỉ có **2,5 TiB dung lượng usable**, bình quân 2,15 TiB tương đương **86%** trước snapshot và dữ liệu tăng trưởng. Đây là mức đáng lo trong ví dụ, nhất là khi compaction cần thêm dung lượng tạm.

Nếu mỗi node có **4 TiB usable**, phần dự trữ lớn hơn, nhưng **không được kết luận an toàn chỉ dựa vào trung bình**. Hot node có thể chứa dữ liệu nhiều hơn và chạm giới hạn trước các node khác.

**Các số liệu trong bảng là giả định**, không phải benchmark Cassandra. Phải thay bằng thống kê thực tế, kiểm tra per-node skew, snapshot/hard link và hướng tăng trưởng.

### 4.3. Tính tới replication factor

Giả sử v2 chứa **1 TiB logical rows sau nén ở mức một bản sao** và keyspace RF=3 trong DC:

~~~text
Dung lượng ước lượng của 3 replica
≈ 1 TiB × 3 = 3 TiB

Đây mới là baseline vật lý tương đối,
chưa gồm compaction temporary space,
metadata, commit log, hints, snapshots hoặc skew.
~~~

Nếu keyspace đặt RF=3 ở **hai** datacenter, tổng số bản sao cho một partition có thể là 6, nên cần tính capacity riêng cho mỗi DC. Không lấy dung lượng còn trống ở DC1 để bù cho volume đầy ở DC2.

### 4.4. Ngưỡng dừng theo disk

Trước migration, thống nhất ngưỡng cảnh báo và **hard stop** dựa trên free bytes hoặc phần trăm usable của **node xấu nhất**, không chỉ giá trị cluster trung bình.

Ví dụ quy tắc vận hành **minh họa, không phải ngưỡng khuyến nghị chung**:

~~~text
Nếu bất kỳ replica target nào:
    free disk < 25% usable capacity
    hoặc disk write latency p99 tăng quá SLO
    hoặc compaction backlog tăng liên tục > 30 phút
=> PAUSE backfill, điều tra, không gửi thêm tải.
~~~

Số 25% và 30 phút phải được xác nhận qua baseline, compaction strategy, disk size và policy của tổ chức. Trong một cluster khác, ngưỡng phù hợp có thể khác.

## 5. Compaction amplification: vì sao ghi 1 GiB có thể gây nhiều hơn 1 GiB I/O?

### 5.1. Vòng đời dữ liệu mới

~~~mermaid
flowchart LR
    A["Backfill mutation"] --> B["Commit log + memtable"]
    B --> C["Memtable flush: SSTable mới"]
    C --> D["Compaction đọc SSTable cũ"]
    D --> E["Compaction ghi SSTable mới"]
    E --> F["SSTable nguồn được thu hồi khi an toàn"]
    G["TTL / DELETE / update"] --> D
~~~

Khi backfill ghi các row vào v2, chúng không xuất hiện ngay thành một tệp đích cuối cùng đã tối ưu. Dữ liệu đi qua flush và có thể được viết lại trong những lần compaction tiếp theo.

**Write amplification** là tổng lượng bytes ghi xuống storage lớn hơn lượng payload logic ban đầu. Con số phụ thuộc:

- Compaction strategy và kích thước SSTable.
- Thứ tự ghi/backfill và số partition đồng thời.
- Update, deletion, TTL/tombstone.
- Compression, partition width và tốc độ ingest.
- I/O của streaming, repair và flush đồng thời.

### 5.2. STCS, LCS và TWCS có tác động khác nhau

| Strategy | Khi có thể phù hợp | Rủi ro dưới migration |
|---|---|---|
| **STCS** (SizeTieredCompactionStrategy) | Workload ghi nhiều, SSTable được gộp theo kích thước | Các đợt compaction lớn có thể cần headroom; đọc có thể chạm nhiều SSTable |
| **LCS** (LeveledCompactionStrategy) | Muốn kiểm soát read amplification ở một số workload | Update/backfill có thể tạo write amplification cao, nhiều việc nền |
| **TWCS** (TimeWindowCompactionStrategy) | Dữ liệu gần như bất biến, TTL/time-series và cửa sổ thời gian phù hợp | Backfill dữ liệu cũ vào thời điểm mới hoặc update cũ có thể phá kỳ vọng về window/tombstone |

Không tự chuyển v2 sang TWCS chỉ vì partition key có trường `order_month`. Nếu dữ liệu liên tục bị UPDATE status cũ, đặc tính bất biến theo thời gian có thể không còn phù hợp. Hãy kiểm tra loại mutation, TTL, late arrival và lựa chọn strategy theo phiên bản.

### 5.3. Quan sát compaction thay vì tăng concurrency theo cảm tính

~~~bash
# Backlog/active compaction trên một node.
nodetool compactionstats

# SSTable count, read/write metrics và table-level information.
nodetool tablestats commerce.orders_by_customer_month_v2

# Histogram theo table nếu phiên bản hỗ trợ.
nodetool tablehistograms commerce orders_by_customer_month_v2
~~~

`Pending tasks` không phải số byte cần ghi hoặc ETA. Một queue 100 task nhỏ và một queue 10 task rất lớn có thể có tác động trái ngược. Cần xem progress, disk latency, bytes/s và số SSTable thực tế.

**Đừng tăng `concurrent_compactors` hay throughput compaction để “đẩy nhanh” khi disk đang bão hòa.** Nhiều tác vụ có thể chỉ tranh cùng I/O, làm read p99 và free space xấu hơn. Ngược lại, giảm quá mạnh có thể khiến backlog v2 tăng vô hạn. Mọi thay đổi cần thử nghiệm và phương án rollback.

## 6. Replica load: đọc nguồn và ghi đích không phải lúc nào cũng trải đều

### 6.1. Token range và partition key

Partition key được băm thành token; replica placement quyết định node nào giữ dữ liệu. Một job backfill đọc **toàn bộ customer lớn** liên tiếp có thể tập trung vào vài replica chứa những partition đó, dù tổng cluster còn dư CPU.

Ở bảng v1, một partition có thể gồm nhiều năm đơn của một customer. Sang v2, cùng lịch sử được chia thành các partition theo tháng; điều này **thay đổi phân bố token và các replica đích**. Nút phục vụ read nguồn không nhất thiết là nút nhận write v2.

Do đó, giới hạn chỉ số lượng **worker JVM** chưa chắc đủ. Cần quan sát:

- Read/write throughput theo **node** và DC.
- Pending/active ở các stage liên quan trong `nodetool tpstats`.
- Disk free và disk latency trên **node xấu nhất**.
- In-flight requests và retries ở driver.
- Hot partitions, wide partitions và mức skew token.

### 6.2. CL làm thay đổi số ACK, không thay mô hình truy vấn

Với RF=3 một DC:

- `ONE` cần ACK theo ngưỡng một replica cho thao tác tương ứng.
- `LOCAL_QUORUM` cần ACK từ hai replica trong DC đó.
- `ALL` cần mọi replica liên quan.

Một write `ONE` **không có nghĩa** mutation chỉ được gửi tới đúng một replica và không gây tải cho những replica khác. CL quyết định khi nào request có thể thành công, còn coordinator vẫn phân phối mutation theo replication strategy và xử lý replica lỗi/hints theo cơ chế hệ thống.

Backfill **không nên tự hạ CL** để tăng throughput mà bỏ qua yêu cầu correctness. Đọc nguồn ở `ONE` có thể gặp dữ liệu chậm hội tụ tại replica, trong khi `LOCAL_QUORUM` tốn nhiều phản hồi hơn; cần chọn theo thiết kế migration, độ khỏe replica và đối soát dữ liệu.

### 6.3. Tải xuyên datacenter

Khi keyspace dùng `NetworkTopologyStrategy` nhiều DC:

- Mutation vào v2 có thể được nhân bản qua nhiều DC.
- Network WAN và disk của DC xa có thể trở thành giới hạn.
- `LOCAL_QUORUM` trả ACK từ DC cục bộ nhưng **không chứng minh DC xa đã có quorum bản sao tại thời điểm trả về**.
- `EACH_QUORUM` áp dụng cho những **ghi** được hỗ trợ, cần quorum ở từng DC và chịu tác động WAN/availability mạnh hơn.
- Repair và streaming có thể cùng dùng băng thông liên DC trong đợt migration.

Phải lập capacity/throughput theo **mỗi DC**, không chỉ số liệu tổng cluster.

## 7. Thiết kế luồng migration tránh dồn cả tải vào một thời điểm

### 7.1. Lộ trình thường dùng: expand → backfill → verify → switch → contract

| Giai đoạn | Thao tác chính | Rủi ro cần kiểm soát | Điều kiện chuyển tiếp |
|---|---|---|---|
| **Expand** | Tạo v2, deploy code hiểu cả v1/v2 | Schema agreement, app compatibility | v2 tồn tại, client cũ vẫn hoạt động |
| **Capture writes** | Thiết kế dual write hoặc CDC/event log/upstream replay | Ghi thiếu hoặc sai thứ tự giữa hai bảng | Có cơ chế xử lý mutation đang diễn ra |
| **Backfill** | Copy dữ liệu lịch sử theo partition/range | Read/write/compaction/disk pressure | Có throttle, checkpoint và alert |
| **Verify** | Đối soát partition, row, value và invariant | Bỏ sót dữ liệu, TTL/tombstone | Sai lệch dưới ngưỡng được phê duyệt |
| **Switch reads** | Chuyển API sang v2 theo feature flag/canary | Read p99, query logic, duplicate/missing row | SLO tốt, rollback đường đọc sẵn sàng |
| **Contract** | Ngừng đường cũ, rồi xóa v1 khi đủ điều kiện | Mất đường rollback và backup | Retention, restore test và phê duyệt |

**Chưa xong backfill thì không được coi bảng mới đã đủ dữ liệu** chỉ vì vài SELECT mẫu trả đúng.

### 7.2. Vì sao dual write không tự động là giao dịch nguyên tử?

Một service có thể ghi v1 rồi v2:

~~~text
Write v1  -> SUCCESS
Write v2  -> TIMEOUT
API       -> trả gì? retry v2 thế nào? rollback v1 được không?
~~~

Cassandra không cung cấp transaction ACID nhiều bảng tùy ý chỉ bằng việc gọi hai lệnh `INSERT` liên tiếp. Logged batch cũng không thay thế thiết kế transaction nghiệp vụ xuyên bảng; điều kiện atomicity/visibility của batch không tương đương snapshot isolation hoặc CAS tổng quát.

Vì thế cần:

- **Nguồn sự thật** rõ ràng trong giai đoạn chuyển tiếp.
- Idempotent writes hoặc cơ chế deduplication có thể kiểm chứng.
- Event/outbox/CDC hay log mutation đáng tin để phát lại thiếu hụt nếu phù hợp.
- Cách xử lý mutation **UPDATE, DELETE, TTL** chứ không chỉ INSERT bất biến.
- Đối soát song song và một thời điểm cutover có ranh giới rõ.

### 7.3. Backfill và dữ liệu đang cập nhật cùng lúc

Giả sử đơn O1 được cập nhật status từ `CREATED` sang `PAID` trong lúc job đang copy snapshot cũ:

~~~text
10:00  Backfill đọc v1: O1.status = CREATED
10:01  Live writer ghi v1 và v2: O1.status = PAID
10:02  Backfill ghi v2: O1.status = CREATED
~~~

Nếu backfill thực hiện mutation với timestamp mới hơn live writer, giá trị cũ có thể **ghi đè giá trị mới** theo cơ chế reconciliation timestamp của Cassandra. Đây là lỗi tính đúng nghiêm trọng dù job không gây timeout.

Giải pháp có thể bao gồm:

- Phát lại mutation từ log có thứ tự và barrier/cutover rõ ràng.
- Chỉ backfill phần dữ liệu đã bất biến hoặc đã đóng băng.
- Bảo toàn timestamp/TTL có kiểm soát khi cần, hiểu semantics và chống tombstone resurrection.
- Dùng version logic/cơ chế CAS ở những điểm nghiệp vụ đòi so sánh trạng thái.
- Đối soát và sửa sai lệch sau khi backfill.

**Không áp dụng `USING TIMESTAMP` cho mọi dòng như một mẹo chung.** Sai lệch clock, timestamp đang được dùng cho DELETE/TTL, và update cạnh tranh cần được phân tích theo data model. Một query `SELECT` thông thường cũng không tự mang toàn bộ metadata mutation cần cho replay chính xác.

## 8. Checkpoint, tính idempotent và khả năng dừng/tiếp tục

### 8.1. Một job an toàn phải dừng được

Một backfill tốt có thể:

1. Hoàn thành một đơn vị công việc nhỏ.
2. Ghi checkpoint **chỉ sau khi dữ liệu của đơn vị đó được xử lý và xác nhận theo chính sách**.
3. Dừng khi alert hoặc mất quorum.
4. Tiếp tục từ checkpoint mà không làm sai dữ liệu.
5. Đối soát phần đã xử lý và phần còn lại.

Đơn vị checkpoint có thể là một partition nhỏ, một nhóm primary key hoặc một token range đã chia nhỏ. Không nên dùng **số row đã đọc** làm bằng chứng đã ghi đủ bản sao.

### 8.2. Checkpoint theo partition và xử lý lỗi giữa chừng

~~~text
Work item:
    customer_id = C123

Status:
    PENDING -> RUNNING -> VERIFIED -> COMPLETE

Chỉ đánh COMPLETE khi:
    các row thuộc phạm vi snapshot/replay đã được xử lý;
    tất cả ghi được xác nhận theo CL mục tiêu;
    validation cần thiết thành công.

Nếu worker chết:
    claim work item lại theo lease/retry policy;
    thực hiện lại phần chưa xác minh bằng operation idempotent.
~~~

Bảng trạng thái checkpoint là thiết kế logic; không nhất thiết phải đặt checkpoint trong Cassandra target. Nếu đặt trong Cassandra, cần xem consistency và race giữa worker, có thể dùng LWT/lease phù hợp.

**Ghi lặp cùng primary key với cùng nội dung có thể idempotent về giá trị cuối**, nhưng không có nghĩa an toàn khi row có TTL, update timestamp, counter, DELETE hoặc side effect ngoài database. Cần phân tích cụ thể trước khi retry.

### 8.3. Pagination cũng cần checkpoint hợp lý

Page size của driver giúp **giới hạn số row mỗi lần nhận**, không giới hạn tổng số row của query. Paging state là token opaque dùng để tiếp tục truy vấn tương thích; không coi nó là checkpoint nghiệp vụ bền vững vĩnh viễn.

Nếu worker bị restart:

- Có thể đọc lại một partition từ đầu nếu operation idempotent và dữ liệu nằm trong phạm vi kiểm soát.
- Với phạm vi lớn, lưu cursor nghiệp vụ theo clustering key và điều kiện cutoff nếu hợp lệ.
- Không để paging state cũ vượt qua thay đổi query shape, schema hoặc phiên bản mà chưa kiểm chứng.
- Phải xét mutation mới trong lúc đọc nhiều page; paging không cho snapshot giao dịch toàn bảng.

## 9. Tốc độ giới hạn: worker count, in-flight, rate và bytes phải đi cùng nhau

### 9.1. Bốn giới hạn thực dụng

| Cơ chế | Cái nó chặn | Vì sao chỉ một cơ chế chưa đủ |
|---|---|---|
| **Worker count** | Số tiến trình/thread xử lý song song | Mỗi worker có thể tự tạo hàng trăm request async |
| **Max in-flight** | Số request Cassandra đang chờ phản hồi | Row lớn có thể tạo bytes/s quá cao dù concurrency thấp |
| **Rate limit** | Mutation hoặc read request mỗi giây | Không giới hạn peak dung lượng bytes nếu record khác kích thước |
| **Bytes budget** | Lượng data đọc/ghi mỗi giây hoặc mỗi batch | Không ngăn nhiều query nhỏ tạo overhead coordinator |

Ví dụ khởi đầu **giả định để thử nghiệm**, không phải cấu hình mặc định:

~~~text
Per migration job:
    max_worker_count     = 4
    max_in_flight_writes = 16
    write_rate_limit     = 500 mutations/s
    read_rate_limit      = 100 partitions/s

Global stop:
    free disk node xấu nhất dưới ngưỡng đã phê duyệt;
    write p99 hoặc timeout vượt SLO;
    backlog compaction tăng không hồi phục.
~~~

Khi có nhiều job hoặc nhiều pod, **500 mutations/s mỗi pod không phải 500 mutations/s toàn cluster**. Phải dùng một ngân sách chung hoặc cơ chế điều phối để tránh autoscaling nhân tải migration ngoài dự tính.

### 9.2. Ưu tiên adaptive throttle

Một bộ điều khiển hữu ích:

~~~mermaid
flowchart TD
    A["Bắt đầu ở rate thấp"] --> B["Chạy một khoảng đo đủ mẫu"]
    B --> C{"p99/error/disk/free space/compaction OK?"}
    C -->|Có| D["Tăng rate nhỏ theo bước, có trần"]
    C -->|Không| E["Giảm rate hoặc PAUSE"]
    D --> B
    E --> F["Điều tra bottleneck"]
    F --> G{"An toàn để tiếp tục?"}
    G -->|Có| A
    G -->|Không| H["Giữ PAUSE, escalations/rollback"]
~~~

**Đừng dùng chỉ CPU bình quân** làm điều kiện tăng rate. Một node có SSTable count và disk write p99 rất xấu có thể bị quá tải trước khi CPU toàn cluster cao.

## 10. Ví dụ Java Driver 4.x: backfill chậm có chủ ý và bounded memory

Đoạn code sau minh họa **một work item theo customer**, đọc dữ liệu v1 theo trang và ghi v2 tuần tự. Nó cố tình ưu tiên **giới hạn tải** hơn thông lượng tối đa; để chạy production cần thêm job scheduler, checkpoint, metrics, auth/TLS và quy trình đảm bảo không ghi đè mutation mới.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.UUID;

public final class ConservativeOrderBackfill {
    private final CqlSession session;
    private final PreparedStatement source;
    private final PreparedStatement target;

    public ConservativeOrderBackfill(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.source = session.prepare(
            "SELECT created_at, order_id, amount, status " +
            "FROM commerce.orders_by_customer_v1 " +
            "WHERE customer_id = ?"
        );
        this.target = session.prepare(
            "INSERT INTO commerce.orders_by_customer_month_v2 " +
            "(customer_id, order_month, created_at, order_id, amount, status) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );
    }

    public long copyCustomer(UUID customerId) throws InterruptedException {
        BoundStatement read = source.bind(customerId)
            .setPageSize(100)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        long written = 0;
        ResultSet rows = session.execute(read);

        for (Row row : rows) {
            Instant createdAt = row.getInstant("created_at");
            UUID orderId = row.getUuid("order_id");
            BigDecimal amount = row.getBigDecimal("amount");
            String status = row.getString("status");

            // UTC là quy tắc bucket của migration này.
            LocalDate month = createdAt
                .atOffset(ZoneOffset.UTC)
                .toLocalDate()
                .withDayOfMonth(1);

            BoundStatement write = target
                .bind(customerId, month, createdAt,
                      orderId, amount, status)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM);

            session.execute(write);
            written++;

            // Demo tối đa ~50 writes/s cho MỘT luồng,
            // chưa phải quota toàn cluster hoặc bytes/s.
            Thread.sleep(20);
        }

        return written; // Chưa đánh dấu COMPLETE nếu chưa đối soát.
    }
}
~~~

### 10.1. Mã trên giải quyết gì?

- `PreparedStatement` tái sử dụng cho source/target.
- `WHERE customer_id = ?` tránh scan vô hướng; mỗi work item biết đúng partition cần đọc.
- `setPageSize(100)` hạn chế lượng row nhận mỗi page nhưng **không** khiến một partition rất rộng trở thành rẻ.
- Vòng lặp chỉ giữ row đang xử lý, không dùng `ResultSet.all()` để gom toàn bộ.
- Ghi **tuần tự** nên mỗi job chỉ có một write in-flight tại một thời điểm.
- Delay 20 ms là throttle minh họa cho một worker; phải thay bằng **rate limiter được chia sẻ** nếu nhiều worker/pod.
- Ghi cùng primary key có thể làm row đích bị cập nhật lại; cần cơ chế chống ghi đè trạng thái mới và preserve TTL/timestamp theo thiết kế thực tế.

### 10.2. Mã chưa giải quyết điều gì?

- Không có CDC/replay hay barrier để bảo vệ UPDATE/DELETE diễn ra đồng thời.
- Không kiểm tra khách hàng/partition quá rộng trước khi đọc.
- Không có checkpoint, cancellation hoặc backpressure xuyên nhiều worker.
- Không xử lý riêng timeout không chắc chắn; chỉ cho exception lan ra.
- Không giới hạn tổng bytes/s, số partitions đồng thời và CPU/GC toàn cluster.
- Không xác minh rằng row count/value đích đã bằng phạm vi nguồn.
- Không duy trì write timestamp/TTL của source; vì vậy **không được chạy như một migration correctness-preserving tổng quát** khi có update/TTL/delete.

Bản production cần được bổ sung các quy tắc đó **trước** khi sử dụng.

### 10.3. Async Driver: đừng tạo vô hạn future

Nếu chuyển sang `executeAsync()`, một lỗi thường gặp là:

~~~java
// ANTI-PATTERN: tạo quá nhiều request đang chờ.
for (BackfillRow row : millionsOfRows) {
    session.executeAsync(buildWrite(row));
}
~~~

`buildWrite` và `BackfillRow` là ký hiệu minh họa. Mã trên không chờ kết quả, không giới hạn số request đang bay và không bảo đảm xử lý lỗi.

Hướng đúng:

~~~text
Semaphore permits = MAX_IN_FLIGHT (ví dụ 16)

for each source row:
    acquire permit (hoặc chờ downstream sẵn sàng)
    send asynchronous write
    on completion:
        record outcome and latency
        release permit
    on error:
        apply bounded retry/stop policy

Chỉ checkpoint sau khi toàn bộ write cần thiết
của work item đã được xác nhận và kiểm chứng.
~~~

Không thực hiện I/O chặn dài trong callback thread của driver. Nếu dùng executor riêng, queue executor cũng phải được giới hạn; **semaphore chỉ có ý nghĩa nếu được acquire trước khi submit**.

## 11. Timeout, retry và backoff: giữ hệ thống khỏe hơn thay vì dồn thêm tải

### 11.1. Timeout không có nghĩa write thất bại ở mọi replica

Một write timeout có thể xảy ra **sau khi mutation đã đến một số replica**, nhưng chưa đủ ACK trước hạn. Nếu retry không kiểm soát, backfill tạo nhiều thao tác giống nhau và tăng load.

Vì vậy:

1. Phân biệt **unavailable**, **write timeout**, **read timeout**, **overload** và lỗi kiểu dữ liệu/schema.
2. Chỉ retry khi operation có semantics phù hợp và đã giới hạn attempts.
3. Dùng **exponential backoff có jitter** và tổng deadline.
4. Giảm rate hoặc pause khi timeout tăng; không chỉ tăng request timeout để che vấn đề.
5. Đối soát kết quả khi timeout không rõ mutation đã áp dụng hay chưa.

### 11.2. Không dùng counter increment làm backfill idempotent

~~~cql
-- Không dùng làm cơ chế backfill retry mù:
UPDATE commerce.some_counters
SET counter_value = counter_value + 1
WHERE counter_id = 11111111-1111-1111-1111-111111111111;
~~~

Counter increment không idempotent theo cách một write cùng primary key và cùng giá trị có thể đạt được. Với dữ liệu counter, cần thiết kế migration riêng để tái lập logical value và tránh cộng trùng.

### 11.3. Tránh logged batch nhiều partition

Một câu CQL `BEGIN BATCH` rất lớn chứa hàng nghìn mutation của nhiều partition **không phải công cụ bulk import**. Nó có thể gây batchlog pressure, message lớn, network/disk write và timeout.

Nếu nhiều row cùng partition và nghiệp vụ cần batch có giới hạn, hãy đánh giá semantics theo phiên bản và đo tải. Với backfill phân tán, thường hiệu quả hơn dùng **prepared write đơn, rate/concurrency bounded** hoặc công cụ bulk import phù hợp đã thử nghiệm.

## 12. Dung lượng snapshot, backup và thời điểm xóa bảng cũ

Trong đợt migration, việc giữ v1 thường là **điều kiện rollback**. Nhưng xóa v1 quá sớm hoặc giữ snapshot quá lâu đều có rủi ro.

### 12.1. Snapshot có thể giữ SSTable cũ dù đã DROP dữ liệu

Cassandra snapshot thường dùng hard link tới SSTable components. Trong nhiều trường hợp, file dữ liệu vẫn chiếm disk cho tới khi snapshot/hard link tương ứng được loại bỏ theo chính sách. Do đó:

- Disk usage không nhất thiết giảm ngay sau `TRUNCATE` hoặc `DROP` nếu snapshot còn giữ SSTable.
- Độ lớn hiển thị của thư mục snapshot và data có thể trùng physical blocks do hard link; phải hiểu công cụ đo.
- `nodetool clearsnapshot` là thao tác có thể xóa bản snapshot cần cho rollback/restore; **không chạy chỉ để “lấy chỗ” khi chưa có phê duyệt**.
- Backup lưu ở nơi độc lập giúp phục hồi sau lỗi disk/cluster, không thể chỉ dựa vào snapshot nằm cùng volume.

### 12.2. Thời điểm xóa v1

Điều kiện trước khi bỏ bảng cũ nên gồm:

- Dữ liệu v2 được đối soát theo partition/token ranges và bất biến nghiệp vụ.
- Read traffic đã chuyển và ổn định qua thời gian đủ để phát hiện edge cases.
- Những mutation sau snapshot/backfill đã được capture và replay/đối soát.
- Không còn code/job cần đọc v1.
- Có backup được kiểm chứng restore và retention được phê duyệt.
- Disk/compaction headroom đủ để cleanup theo quy trình.

**Không dùng `DROP TABLE` làm thao tác rollback nhanh.** Nếu xóa v1, quyền quay lại đường đọc cũ mất hoặc trở nên tốn kém; phải đi qua change management riêng.

## 13. Metrics và nodetool để giám sát tác động migration

### 13.1. Dashboard nên chia làm ba tầng

| Tầng | Metric cần xem | Điều có thể phát hiện |
|---|---|---|
| **Ứng dụng** | API read/write p50/p95/p99, timeout, unavailable, retry rate, QPS | Migration có làm SLO của người dùng xấu đi không |
| **Job migration** | Rows đọc/ghi, bytes/s, partitions/s, in-flight, checkpoint lag, error rate | Tốc độ, tiến độ và backlog riêng của job |
| **Cluster/node** | Disk free/latency, compaction backlog, SSTables per read, commitlog, flush queue, network, CPU/GC | Bottleneck ở replica và hoạt động nền |

Không chỉ nhìn số rows migrated/s. Một job chạy nhanh nhưng làm API timeout tăng là **không đạt mục tiêu vận hành**.

### 13.2. Bộ lệnh đọc trạng thái

~~~bash
# Tình trạng các replica và phân bố DC/rack.
nodetool status

# Các thread pools, pending queues và dropped messages.
nodetool tpstats

# Công việc compaction đang chạy và backlog.
nodetool compactionstats

# Table-level storage và latency.
nodetool tablestats commerce.orders_by_customer_month_v2

# Histogram theo table nếu phiên bản hỗ trợ.
nodetool tablehistograms commerce orders_by_customer_month_v2

# SSTable streaming khi repair/bootstrap/relocation (nếu có).
nodetool netstats

# Thông tin node và disk/heap tổng quan.
nodetool info
~~~

`netstats` không hiện các request CQL backfill thông thường như một phiên SSTable streaming. Nếu netstats trống, **vẫn có thể đang có read/write traffic rất lớn** do Java job. Dùng node/network metrics và driver telemetry để thấy lưu lượng đó.

### 13.3. Chụp số liệu theo thời gian

~~~text
UTC          Job writes/s    Compaction pending   Worst-node free   API p99
09:00             100                 10              38%           80 ms
09:20             500                 45              34%          110 ms
09:40           1.000                130              27%          420 ms
09:45         PAUSED                135              26%          500 ms
10:15               0                 70              26%          120 ms
~~~

Đây là **dữ liệu giả định** để minh họa: tăng tốc gây áp lực, pause cho cluster cơ hội tiêu hóa backlog. Nó **không đủ chứng minh nhân quả một mình**; cần đọc disk latency, traffic mix, compaction throughput và các thay đổi đồng thời.

### 13.4. Theo dõi node xấu nhất, không dùng average để che mất dung lượng

Nếu năm node còn 40% disk và một node chỉ còn 5%, **average free** có thể vẫn trông chấp nhận được. Nhưng node 5% có thể mất khả năng compaction trước khi những node khác gặp vấn đề.

Cần cảnh báo theo **minimum free bytes/percentage**, trạng thái replica, node role và dự báo tăng trưởng. Không lấy trung bình p99 mỗi node để tính p99 cluster; phải dùng histogram/phân bố phù hợp.

## 14. Runbook: backfill làm compaction pending và write p99 tăng

**Tình huống:** Ứng dụng vừa bật migration v1→v2 ở 1.000 mutations/s. Trong 40 phút, pending compactions tăng mạnh, một node còn 18% disk và write p99 từ 40 ms lên 700 ms.

### Bước 1 — Xác định ảnh hưởng

Ghi lại timestamp, job version, feature flags, CL, table source/target, write/read QPS, timeout, disk headroom, RF và DC. Ưu tiên xác định **API người dùng nào** đang vi phạm SLO.

### Bước 2 — Dừng tăng tải, rồi pause nếu ngưỡng đã chạm

Dùng cơ chế pause của job, tránh giết tiến trình giữa một đơn vị công việc mà không có checkpoint. Nếu ngưỡng hard stop chạm hoặc disk sắp đầy, **pause ngay theo runbook** và bảo toàn dữ liệu/manifest/checkpoint.

### Bước 3 — Kiểm tra bottleneck

- `compactionstats`: pending và tiến độ có cải thiện khi job pause không?
- `tpstats`: mutation/flush/read queue có giảm?
- Disk telemetry: write/read latency, free bytes, throttling.
- `tablestats`: SSTables per read và dung lượng v2.
- `netstats`: có thêm repair/bootstrap streaming đang tranh I/O không?
- Client: retries có tăng gấp nhiều lần không?

### Bước 4 — Giảm tác vụ cạnh tranh có thể kiểm soát

Theo quyền và lịch vận hành, cân nhắc giảm/pause import khác, điều tiết repair/streaming không khẩn cấp hoặc phân bố lịch job. **Không tự tắt compaction dài hạn**, xóa SSTable, commit log hoặc hạ CL để “chữa” timeout.

### Bước 5 — Tái khởi động ở mức an toàn

Nếu backlog đang giảm và disk/latency ổn, resume từ checkpoint với rate thấp hơn; tăng dần theo bước nhỏ. Duy trì stop conditions và giám sát cả traffic người dùng.

### Bước 6 — Báo cáo

Ghi lại peak pending tasks, min free bytes, p99/timeouts, số work items hoàn thành, mức rate an toàn và lỗ hổng capacity planning. Dùng số liệu này cho lần migration sau, không chỉ xem job cuối cùng đã xong hay chưa.

## 15. Runbook: dữ liệu v2 có row bị thiếu hoặc trạng thái cũ

**Tình huống:** Backfill báo hoàn thành, nhưng API v2 thiếu các đơn mới hoặc hiển thị `CREATED` thay vì `PAID`.

1. **Dừng chuyển đọc toàn bộ** và giữ v1 làm nguồn sự thật theo kế hoạch đã định.
2. So danh sách primary key, phiên bản nghiệp vụ và timestamps ở v1/v2 theo các partition mẫu và phạm vi lỗi.
3. Kiểm tra source read có bị paged incomplete, timeout bỏ qua hay checkpoint quá sớm không.
4. Kiểm tra dual-write failure, CDC/event replay lag và độ trễ fanout tới replica.
5. Tìm trường hợp backfill timestamp mới ghi đè mutation live mới hơn.
6. Kiểm tra TTL và DELETE/tombstone: có thể row đã hết hạn hoặc bị xóa hợp lệ.
7. Sửa cơ chế đối soát/replay và chạy lại work items nhỏ bằng operation an toàn.
8. Chỉ switch reads sau khi invariant và phạm vi dữ liệu được xác minh.

Không mặc định dùng `SELECT COUNT(*)` trên toàn bảng lớn để so sánh, vì query có thể là full scan tốn tài nguyên. Cần sample theo token/partition, kiểm tra identity và logical checksum hoặc job đối soát có kiểm soát.

## 16. Kiểm thử rollout và rollback

### 16.1. Canary theo phạm vi nhỏ

Một canary tốt:

- Chọn một tập customer/partition đại diện, gồm nhỏ, rộng và nhiều update.
- Xác định trước số row/bytes ước lượng và deadline.
- Bật dual write/capture có kiểm chứng.
- Backfill ở rate rất thấp, đo ảnh hưởng lên các node được chạm.
- So dữ liệu v1/v2 và API output theo invariant nghiệp vụ.
- Tăng phạm vi từng đợt, không nhảy từ 1% lên 100% nếu disk headroom chưa được xác minh.

**Đừng chỉ chọn partition nhỏ để canary**: chúng không phản ánh rủi ro wide partition, compaction debt hoặc outlier.

### 16.2. Phân biệt rollback read và rollback schema

| Việc cần đảo ngược | Cách xử lý thường hợp lý | Rủi ro |
|---|---|---|
| API v2 chậm/sai | Chuyển đọc về v1 nếu còn đầy đủ cập nhật | Phải chứng minh v1 vẫn là nguồn đúng |
| Job backfill gây quá tải | Pause và giảm rate | Cần checkpoint/idempotency khi resume |
| Dual write bị lỗi | Tắt/rollback code theo quy trình, replay thiếu hụt | Dữ liệu v1/v2 có thể đã lệch |
| Schema v2 sai | Giữ v1, tạo v2 sửa đổi/di chuyển có kế hoạch | Không tự sửa primary key của v2 tùy tiện |
| Muốn giải phóng disk | Thu hồi v1 **sau khi đủ điều kiện** | Có thể mất đường rollback, snapshot còn chiếm space |

Rollback phải được viết **trước khi migration chạy**, không phải sau khi cluster đã đầy đĩa.

### 16.3. Phân kỳ áp lực tài nguyên

Một kế hoạch production có thể tách:

~~~text
Giai đoạn 1: Tạo schema, triển khai code hiểu v1/v2
Giai đoạn 2: Bắt mutation mới, canary read/dual write
Giai đoạn 3: Backfill lịch sử theo từng phạm vi có throttle
Giai đoạn 4: Đối soát và repair nếu cần, tránh peak traffic
Giai đoạn 5: Switch reads canary -> toàn bộ theo SLO
Giai đoạn 6: Giữ v1 qua retention/rollback window
Giai đoạn 7: Xóa v1/snapshot theo change và backup policy
~~~

Không chạy đồng thời backfill lớn, topology change, repair toàn cluster, major compaction và backup nếu chúng tranh tài nguyên mà không có capacity plan phù hợp. Tuy nhiên **không bỏ lịch repair quan trọng vô thời hạn** chỉ để migration nhanh; phải phối hợp an toàn dữ liệu theo policy.

## 17. Những sai lầm phổ biến

| Nhận định/hành động | Vấn đề | Cách thay thế |
|---|---|---|
| “Cassandra tự copy dữ liệu khi CREATE v2.” | Tạo bảng mới không tự backfill v1 | Thiết kế job migration riêng |
| “RF=3 nên ghi chỉ tốn như một bản copy.” | Replica fanout và storage amplification | Tính RF, DC và physical bytes |
| “Còn 20% disk trung bình là đủ.” | Node skew, compaction temporary space và snapshot | Xem node xấu nhất và dự phòng |
| “Backfill càng nhiều worker càng nhanh.” | Saturation, retries và pending queue có thể tăng | Rate/in-flight/bytes budgets |
| “Compaction pending cao thì tăng threads.” | Disk có thể đã bão hòa | Đo disk I/O và backlog trend |
| “Page size 100 chặn query ở 100 row.” | Paging không giới hạn tổng kết quả | Work items/ranges, LIMIT và stop condition phù hợp |
| “Mọi INSERT lại đều idempotent.” | TTL, timestamp, UPDATE/DELETE và side effects | Phân tích write semantics và replay |
| “Logged batch hàng nghìn partition giúp import.” | Batchlog/message pressure, timeout | Prepared write có throttle hoặc công cụ chuyên dụng |
| “LOCAL_QUORUM thành công nghĩa mọi DC đã có mutation.” | Chỉ quorum DC cục bộ | Theo dõi replication và yêu cầu consistency |
| “Job đã đọc N row nghĩa là đã ghi N row.” | Timeout/checkpoint/duplicate/skip | Verify logical content và outcome |
| “Có thể DROP v1 ngay sau khi chuyển read.” | Mất rollback path và dữ liệu chưa đối soát | Retention + restore test |
| “netstats trống nghĩa là không có migration traffic.” | CQL backfill không phải SSTable streaming | Driver, node network và write metrics |
| “Tắt compaction để ưu tiên backfill mãi.” | Tích lũy SSTables, disk pressure, read amplification | Cân bằng throughput và I/O theo runbook |
| “Thay CL giảm p99 mà không có đánh đổi.” | Thay đổi consistency/correctness | Tách vấn đề performance và data guarantees |

## 18. Bài tập có đáp án

### Câu 1 — Tính storage peak

Cluster có 6 TiB SSTable v1, dự kiến v2 là 5,4 TiB và 1,5 TiB peak tác vụ tạm. Tổng trước snapshot, log và biên an toàn?

**Đáp án:** `6 + 5,4 + 1,5 = 12,9 TiB`. Nếu sáu node phân bố đều, bình quân 2,15 TiB/node; vẫn phải xem node xấu nhất.

### Câu 2 — RF ảnh hưởng thế nào?

Dữ liệu v2 tương đương 1 TiB dung lượng một bản sao và RF=3. Có thể chỉ chuẩn bị 1 TiB toàn cluster không?

**Đáp án:** Không. Baseline xấp xỉ 3 TiB vật lý trước compaction temporary space, commit log, snapshot và skew.

### Câu 3 — LIMIT có thay backpressure?

Job có `LIMIT 500` trên mỗi partition và page size 100 nhưng chạy 1.000 customer đồng thời. Có an toàn không?

**Đáp án:** Không chắc. Mỗi query có giới hạn nhưng tổng in-flight, bytes/s và replica hotspots vẫn có thể quá tải; cần giới hạn worker, rate, concurrency và quan sát node.

### Câu 4 — Pending compaction tăng

`compactionstats` có pending tăng nhanh, disk write p99 cũng tăng. Có nên tăng compaction concurrency ngay?

**Đáp án:** Không. Nếu disk đã bão hòa, concurrency cao hơn có thể tăng contention. Nên giảm tải backfill, quan sát tiến độ và capacity trước khi thay tuning.

### Câu 5 — Dual write bị timeout

v1 đã thành công, v2 bị timeout. Có thể khẳng định v2 hoàn toàn chưa được ghi không?

**Đáp án:** Không. Một số replica có thể đã áp dụng mutation dù client chưa đủ ACK; cần retry có kiểm soát, idempotency, đối soát và chính sách nguồn sự thật.

### Câu 6 — Backfill ghi đè dữ liệu mới

Live writer cập nhật O1 thành `PAID`, backfill sau đó ghi bản cũ `CREATED` với timestamp mới hơn. Có thể sai ra sao?

**Đáp án:** Cassandra có thể chọn mutation có timestamp mới hơn của backfill, khiến trạng thái cũ xuất hiện. Cần ranh giới replay, timestamp policy, versioning hoặc các cơ chế tránh race.

### Câu 7 — Netstats rỗng

`netstats` không có stream nhưng disk/network của các replica tăng mạnh trong lúc Java backfill. Điều này có mâu thuẫn không?

**Đáp án:** Không. Backfill qua CQL client là read/write traffic, không nhất thiết tạo SSTable streaming session được báo ở `netstats`.

### Câu 8 — Kiểm tra thành công

Job ghi 20 triệu row rồi báo đã xong. Một số query v2 trả đúng dữ liệu. Có đủ để xóa v1 không?

**Đáp án:** Không. Cần kiểm tra đầy đủ work items, logical keys/values, cập nhật đồng thời, TTL/DELETE và bất biến nghiệp vụ, rồi giữ rollback window và backup có thể restore.

### Câu 9 — Compaction strategy

Mọi đơn hàng cũ vẫn được cập nhật status nhiều tháng sau khi tạo. Có nên mặc định TWCS chỉ vì v2 partition theo tháng?

**Đáp án:** Không. TWCS cần workload và TTL/window phù hợp, đặc biệt tránh update lâu dài phá giả định dữ liệu ít thay đổi. Phải đánh giá chiến lược trên workload thực.

### Câu 10 — Hạ CL cho nhanh

Worker dùng `LOCAL_QUORUM` và bị timeout do replica chậm. Đổi sang `ONE` có phải chỉ là tối ưu tốc độ không?

**Đáp án:** Không. Nó thay đổi bảo đảm đọc/ghi và hậu quả khi replica sai lệch. Cần đánh giá correctness, không tự hạ CL để che bottleneck.

### Câu 11 — Checkpoint quá sớm

Một work item đọc 10.000 row, ghi thành công 9.000 nhưng job đánh dấu COMPLETE trước khi 1.000 write còn lại được ACK. Rủi ro gì?

**Đáp án:** Job resume có thể bỏ qua 1.000 row chưa rõ kết quả. Chỉ checkpoint sau khi các write được xác nhận và kiểm chứng theo chính sách.

### Câu 12 — Snapshot giữ disk

Sau khi DROP v1, filesystem vẫn chưa giảm nhiều bytes. Điều gì cần kiểm tra?

**Đáp án:** Snapshot/hard links, backup/staging, pending compaction và cơ chế thu hồi file của phiên bản. Không xóa snapshot nếu vẫn cần rollback/restore.

## 19. Checklist trước, trong và sau migration

### Trước migration

~~~text
[ ] Tài liệu schema v1/v2, partition key, clustering key, query shapes
[ ] RF/topology/DC, consistency levels của read/write
[ ] Danh sách nguồn sự thật và cơ chế dual write/CDC/replay
[ ] Chiến lược idempotency, UPDATE/DELETE/TTL và timestamp conflict
[ ] Ước lượng dữ liệu v1/v2 vật lý, temporary space và snapshots
[ ] Disk headroom per-node, compaction strategy, SSTables per read
[ ] Quota worker, in-flight, rate/bytes và stop condition
[ ] Baseline QPS, p50/p95/p99, timeout, free disk và compaction
[ ] Checkpoint/lease, resume và rollback được diễn tập trong staging
[ ] Quyền vận hành, change window, on-call, backup/restore plan
~~~

### Trong migration

~~~text
[ ] Theo dõi node xấu nhất, không chỉ số trung bình cluster
[ ] Job rows/s, bytes/s, errors, retry và checkpoint lag
[ ] Client SLO và Cassandra read/write p99 cùng thời điểm
[ ] tpstats pending/dropped, compactionstats progress/backlog
[ ] Disk free/latency, flush/commit log, streaming/repair khác
[ ] Giảm hoặc pause rate khi vi phạm ngưỡng đã phê duyệt
[ ] Đối soát ngẫu nhiên và theo token/partition mỗi đợt
[ ] Không chạy các thay đổi storage/topology lớn thiếu capacity plan
~~~

### Sau migration

~~~text
[ ] V2 đáp ứng query pattern và SLO ở canary và full traffic
[ ] Dữ liệu và invariant được verify, gồm mutation đồng thời
[ ] Backfill/replay lag về mức được chấp nhận
[ ] Compaction backlog, disk headroom, GC và errors trở về baseline
[ ] Còn backup/restore và rollback path đủ lâu
[ ] Chỉ thu hồi v1/snapshot sau phê duyệt và retention
[ ] Rút kinh nghiệm rate an toàn, chi phí thực, thời gian và sự cố
~~~

## 20. Tổng kết

Di chuyển dữ liệu Cassandra an toàn đòi hỏi nhìn **ba ngân sách cùng lúc**:

1. **Compaction budget:** backfill tạo SSTable mới và write amplification; phải quan sát pending tasks, SSTables per read và I/O trước khi tăng throughput.
2. **Storage budget:** giữ v1 và v2 đồng thời, thêm compaction temporary space, commit log, snapshots và headroom theo **node có ít dung lượng nhất**.
3. **Replica/load budget:** mỗi thao tác đọc/ghi tác động tới nhiều node theo token, RF, consistency level và datacenter; giới hạn worker, in-flight, rate và bytes/s trên phạm vi thực.
4. **Correctness budget:** dual write không mặc định nguyên tử; UPDATE/DELETE, TTL, timestamp, concurrent writes và retry có thể tạo dữ liệu sai dù migration hoàn tất nhanh.
5. **Observability budget:** cần đo ứng dụng, job và cluster cùng thời gian; các công cụ `tpstats`, `compactionstats`, `tablestats` và `netstats` bổ trợ nhưng không thay dữ liệu p99/error.
6. **Rollback budget:** v1, backup, checkpoint và feature flags phải còn hoạt động cho đến khi v2 được xác minh đầy đủ.

Câu hỏi quyết định không phải “đẩy được bao nhiêu triệu row mỗi giờ?”, mà là **“tốc độ nào giữ được khả năng phục vụ người dùng, đủ dung lượng cho compaction, không dồn tải lên một replica và vẫn bảo toàn trạng thái nghiệp vụ khi job dừng hoặc chạy lại?”**. Một migration thành công là migration có thể **giảm tốc, tạm dừng, tiếp tục và rollback theo kế hoạch**, với bằng chứng về cả dữ liệu lẫn sức khỏe cluster.
