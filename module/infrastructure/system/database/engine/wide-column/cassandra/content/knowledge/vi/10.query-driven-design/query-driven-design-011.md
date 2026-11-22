# Tính dung lượng từ kích thước bản ghi, RF, chỉ mục và thời gian lưu

## Mục tiêu bài học

Khi thiết kế Apache Cassandra, câu hỏi “mỗi bản ghi khoảng 1 KB, vậy cần bao nhiêu ổ đĩa?” chưa đủ để lập kế hoạch dung lượng. Cần biết **bao nhiêu bản ghi được ghi trong một đơn vị thời gian**, chúng được giữ bao lâu, mỗi bản ghi thực tế chiếm bao nhiêu byte trên SSTable, có bao nhiêu **replica**, có các bảng nhân bản theo truy vấn hoặc index bổ sung không, và cụm phải dành bao nhiêu dung lượng trống cho **compaction, repair, tăng trưởng và lỗi node**.

Trong chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này trình bày quy trình ước tính và đo dung lượng cho Cassandra wide-column: từ partition key và clustering key, CQL, replication factor (RF), TTL/retention tới tombstone, compaction, repair và cách một ứng dụng Java cung cấp số liệu đầu vào đáng tin cậy.

Sau bài học, bạn có thể:

- Phân biệt **dung lượng dữ liệu nghiệp vụ**, **dung lượng một bản sao trên đĩa**, **tổng dung lượng các replica** và **dung lượng cần cấp phát cho cụm**.
- Ước tính số hàng còn sống từ tốc độ ghi, thời hạn lưu và tốc độ cập nhật/xóa; không nhầm lưu lượng ghi đỉnh với dung lượng trung bình.
- Tính RF theo từng datacenter, cộng chi phí index/bảng projection và phân chia tải theo node.
- Đánh giá **kích thước partition lớn nhất**, không chỉ tổng byte của toàn cụm.
- Hiểu vì sao TTL không đồng nghĩa giải phóng đĩa ngay, và vì sao tombstone/compaction ảnh hưởng dung lượng thực tế.
- Lập bảng tính capacity có giả định rõ, kế hoạch benchmark, metric theo dõi, hệ số an toàn và ngưỡng phải xem lại thiết kế.

## 1. Bốn mức dung lượng cần phân biệt

Ví dụ một hệ thống nhận sự kiện từ thiết bị:

```text
Thiết bị -> Cassandra
              |
              +-- bảng sự kiện chính (query theo device + ngày)
              +-- bảng lookup hoặc projection phụ (nếu nghiệp vụ cần)
              +-- index cho một số cột (nếu được hỗ trợ và có sử dụng)

Mỗi partition của từng bảng
              |
              +-- replica tại node A
              +-- replica tại node B
              +-- replica tại node C     (RF=3, ví dụ)
```

Trong phép tính cần tách bốn tầng:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Logical payload** | Có bao nhiêu hàng và bao nhiêu byte nghiệp vụ trước lưu trữ Cassandra? | 200 triệu sự kiện, mỗi sự kiện trung bình 900 B |
| **On-disk một bản sao** | SSTable, khóa, index, metadata, compression và các thành phần thực tế chiếm bao nhiêu? | 750 B/hàng sống trung bình, đo trên mẫu có tải đại diện |
| **Replicated storage** | Những bản sao đó được đặt ở bao nhiêu replica/DC? | RF=3 có thể xấp xỉ gấp ba phần dữ liệu của một bản sao |
| **Provisioned capacity** | Cần cấp bao nhiêu ổ đĩa để giữ mức sử dụng an toàn và còn chỗ vận hành? | Dung lượng đang dùng chia cho tỷ lệ sử dụng mục tiêu, rồi cộng phần dự phòng chưa mô hình hóa |

**Không được nhân RF hai lần.** Nếu số liệu đo “tổng disk used của toàn cụm” đã gồm mọi replica, không được nhân tiếp RF. Ngược lại, nếu số liệu là kích thước **một bản sao logic của bảng**, phải tính replication tương ứng.

**Không đồng nhất byte qua mạng với byte trên đĩa.** CQL row có thể có nhiều cột, độ dài khóa và metadata; serialization của Java/JSON khác biểu diễn trên SSTable. Compression có thể giảm dung lượng; index, tombstone và cập nhật có thể tăng. Vì thế, đầu vào 900 B/sự kiện chỉ là bước đầu.

## 2. Thu thập hợp đồng truy vấn và đặc điểm ghi trước khi tính

Dung lượng Cassandra chịu ảnh hưởng mạnh bởi **mô hình bảng theo truy vấn**. Một thực thể được lưu vào ba bảng query-driven phải được tính thành ba biểu diễn logic, không chỉ một bản ghi nguồn.

Ví dụ danh mục ban đầu:

| ID | Thao tác | Đường truy cập | Ảnh hưởng tới capacity |
| --- | --- | --- | --- |
| Q01 | Xem 50 sự kiện mới nhất của một device/ngày UTC | Partition `(tenant,device,day)`, clustering thời gian | Xác định kích thước partition theo ngày |
| Q02 | Xem sự kiện của device trong 7 ngày | Đọc tối đa một số bucket ngày đã biết | Ảnh hưởng fan-out, page size và số hàng đọc |
| Q03 | Tra cứu event bằng ID | Bảng lookup `(tenant,event_id)` nếu cần | Thêm dung lượng bảng projection |
| Q04 | Tìm theo severity toàn tenant | Index hoặc bảng theo truy vấn khác nếu có SLA | Chi phí index/ghi bổ sung |
| W01 | Ghi telemetry liên tục | Append sự kiện | Quyết định số hàng/ngày |
| W02 | Xóa/hết TTL | Tombstone và compaction | Quyết định phần đĩa không còn chứa hàng sống nhưng chưa thu hồi |

Với từng bảng cần thu thập:

1. **Tốc độ tạo mới:** sự kiện/giây trung bình, p95 và **giờ cao điểm**; nên phân theo tenant, device, vùng và loại dữ liệu.
2. **Kích thước hàng:** trung bình, p95/p99, kích thước tối đa; riêng payload lớn, khóa dài, text/`blob`, cột nullable và số cột.
3. **Retention:** giữ 7 ngày, 30 ngày hay 1 năm; TTL tính từ lúc ghi hay thời điểm sự kiện xảy ra.
4. **Thao tác thay đổi:** phần trăm upsert/xóa, số bản ghi đến muộn, replay, backfill, chuyển trạng thái tạo tombstone.
5. **Replication:** số DC, RF cho mỗi DC, số node và khả năng phân bố token.
6. **Index/projection:** có bao nhiêu bảng lặp, cột nào được index, kích thước index và chi phí bảo trì.
7. **SLO/SLA:** độ trễ đọc/ghi, write availability, RPO/RTO, thời gian repair, tốc độ tăng trưởng và mức sử dụng đĩa tối đa chấp nhận.

Chỉ hỏi “bao nhiêu TB dữ liệu?” mà không biết **đường truy vấn và cách dữ liệu được giữ/xóa** dễ dẫn tới tính sai cả dung lượng lẫn thiết kế partition.

## 3. Bắt đầu từ số hàng được ghi và thời hạn lưu

Ký hiệu:

```text
R = số bản ghi mới trung bình/giây toàn workload
D = số giây/ngày = 86.400
T = thời hạn lưu tính theo ngày
S = kích thước dữ liệu nghiệp vụ trung bình/bản ghi, đơn vị byte

new_rows_per_day = R × D
live_rows_steady_state ≈ R × D × T
logical_payload_bytes ≈ live_rows_steady_state × S
```

Giả định **lưu lượng ghi ổn định**, **không có nhiều cập nhật/xóa sớm**, **không có backfill lớn** và retention theo thời gian cho phép, đây là ước lượng của **dữ liệu đang sống ở trạng thái ổn định**, không phải tổng số byte SSTable đã cấp phát.

### 3.1. Ví dụ telemetry 30 ngày

Giả sử **1.000 thiết bị**, mỗi thiết bị tạo trung bình **0,1 sự kiện/giây**. Tổng tốc độ trung bình là **100 sự kiện/giây**. Mỗi sự kiện có trung bình **900 byte dữ liệu nghiệp vụ**.

```text
Tốc độ toàn hệ thống: 1.000 × 0,1 = 100 sự kiện/giây
Một ngày: 100 × 86.400 = 8.640.000 sự kiện
30 ngày: 8.640.000 × 30 = 259.200.000 hàng sống
Dung lượng thô: 259.200.000 × 900 B
               = 233.280.000.000 B
               = 233,28 GB (đơn vị thập phân)
```

**233,28 GB chưa phải kích thước Cassandra trên đĩa**, và cũng chưa nhân RF. Đây là dung lượng thô của **một representation** theo giả định.

Nếu ứng dụng tạo thêm bảng tra event theo ID và mỗi event thêm một hàng mapping có payload nhỏ, phải tính **thêm số hàng × kích thước mapping thực tế**, rồi nhân RF cho mỗi bảng. Nếu chỉ có 1% event cần lookup, số hàng mapping phải lấy theo chính sách nghiệp vụ, không tự mặc định 100%.

### 3.2. Sự thay đổi theo thời gian

Nếu lưu lượng tăng, công thức `R × D × T` với một `R` duy nhất không đủ. Cách tính chính xác hơn:

```text
live_rows(t) ≈ tổng số bản ghi còn trong cửa sổ retention
             = tổng hoặc tích phân rate(τ) theo τ ∈ [t - T, t]
```

Ví dụ 30 ngày gần nhất có lưu lượng cao gấp đôi 30 ngày trước, dung lượng hiện tại phải lấy theo **30 ngày mới nhất**, không thể dùng trung bình cả năm. Khi dự báo 6 hoặc 12 tháng, áp dụng một đường tăng trưởng theo tháng và tính retention theo **cửa sổ trượt** để tránh đếm mọi dữ liệu lịch sử như còn sống.

Đối với TTL tính từ `event_time`, sự kiện đến muộn có thể chỉ còn một phần thời gian được lưu; đối với TTL cố định từ lúc ghi, số hàng còn sống phụ thuộc thời điểm ingest. Hai quy tắc có thể tạo dung lượng và hành vi đọc khác nhau.

### 3.3. Phân biệt trung bình và đỉnh

**Dung lượng dài hạn** phụ thuộc tổng hàng được tạo trong cửa sổ lưu. **Tốc độ ghi và hot partition** phụ thuộc lưu lượng đỉnh:

| Số liệu | Dùng để |
| --- | --- |
| Sự kiện/giây trung bình toàn cụm | Ước tính dung lượng sống dài hạn |
| Sự kiện/giây đỉnh toàn cụm | Đánh giá throughput, CPU, network và tốc độ commit log |
| Sự kiện/giây đỉnh của **một partition key logic** | Kiểm tra nguy cơ partition nóng |
| Kích thước hàng p99 | Dự phòng các bản ghi payload lớn và giới hạn API |
| Đợt backfill/replay | Tính chi phí ghi đột biến và dữ liệu cũ chưa hết TTL |

Không thiết kế chỉ dựa trên `average events/s`. Một thiết bị có thể chiếm phần lớn lưu lượng vào một thời điểm dù trung bình của toàn tenant thấp.

## 4. Đo kích thước bản ghi thực tế trên SSTable

Sơ đồ dung lượng cho một bảng Cassandra:

```text
Payload nghiệp vụ, khóa và cột
        |
        +-- serialization/encoding của Cassandra
        +-- partition key và clustering key
        +-- row/cell metadata, timestamps và thông tin TTL
        +-- SSTable data, partition index, summary và thành phần liên quan
        +-- compression (có thể giảm Data.db)
        +-- tombstone và dữ liệu cũ chưa được compaction
        +-- index phụ nếu có
        |
        v
Dung lượng thật trên một replica phải được đo
```

Kích thước trên disk phụ thuộc **schema, phân bố dữ liệu, compression, compaction, TTL, số partition và cách update/xóa**. Không có phép cộng cố định “mỗi row thêm đúng N byte metadata” cho mọi phiên bản Cassandra.

### 4.1. Hệ số đo thay vì hệ số bịa

Có thể định nghĩa:

```text
S_raw = byte nghiệp vụ thô trung bình/hàng
S_disk = byte thực tế/hàng sống của MỘT bản sao bảng
         (được đo trên sample đại diện ở trạng thái ổn định)
k = S_disk / S_raw

storage_one_copy ≈ live_rows × S_disk
                 = live_rows × S_raw × k
```

`k` có thể **nhỏ hơn 1** khi compression hiệu quả, hoặc **lớn hơn 1** khi metadata/index, partition nhỏ, nhiều cột/TTL hay tombstone tạo overhead. Không mặc định `k = 0,5` hay `k = 2` nếu chưa có benchmark.

Nếu `S_disk` được đo bằng tổng bytes trên disk **đã bao gồm index phụ**, không cộng index lần thứ hai. Nếu `S_disk` chỉ gồm base table, cần đo index/bảng projection riêng. Đặc biệt phải ghi rõ số liệu đang tính cho **một replica**, **một node** hay **toàn cluster**.

### 4.2. Thiết kế mẫu đo

Để có hệ số đáng tin cậy:

1. Dùng **schema dự kiến**, loại dữ liệu, độ dài khóa, payload thật và cách chia bucket thật.
2. Nạp dữ liệu đủ lớn để có số partition, clustering rows và SSTables đại diện; không chỉ vài trăm hàng.
3. Ghi theo **tải tương tự thực tế**, gồm update, TTL, replay và xóa nếu workload có các thao tác đó.
4. Đo sau khi dữ liệu đi qua memtable/flush và hoạt động compaction phù hợp; không suy từ kích thước commit log tạm thời.
5. Ghi lại cấu hình compression, strategy compaction, trạng thái index, số node/RF và tuổi dữ liệu.
6. So sánh số byte trên đĩa (ở đúng phạm vi đo) với số hàng sống và số hàng/tombstone kỳ vọng; tính khoảng `S_disk` thay vì một số tuyệt đối.

Đối với retention 30 ngày, mẫu nạp vài phút rồi đo ngay sau flush **không đại diện** cho trạng thái có nhiều sự kiện hết hạn và SSTable đã compaction qua nhiều cửa sổ. Nên chạy thử đủ lâu hoặc tạo workload tuổi dữ liệu tương ứng trong môi trường đo phù hợp.

## 5. Ví dụ CQL: schema, bucket, TTL và cách kiểm tra

Giả sử Q01 thường đọc sự kiện của **một thiết bị trong một ngày UTC**, mới nhất trước:

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload blob,
    PRIMARY KEY ((tenant_id, device_id, day_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

`(tenant_id, device_id, day_bucket)` xác định partition; `(event_time, event_id)` xác định thứ tự và định danh hàng. Mỗi sự kiện tạo **một hàng**, còn byte trên đĩa bao gồm cả payload, khóa và overhead Cassandra.

Đọc 50 sự kiện mới nhất của đúng một ngày:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Dấu `?` là bind marker của prepared statement, không phải literal để dán trực tiếp vào `cqlsh`. Truy vấn có đủ partition key và đọc theo clustering; tuy nhiên `LIMIT 50` **không** bảo đảm chỉ đọc 50 hàng vật lý nếu có tombstone.

### 5.1. Retention tính từ thời điểm ghi

Nếu giữ mọi sự kiện **30 ngày kể từ khi ghi**, có thể cấu hình mặc định:

```sql
ALTER TABLE device_events_by_day
WITH default_time_to_live = 2592000;
```

`2.592.000` giây tương đương 30 × 24 × 60 × 60 giây. TTL mặc định không tự tính từ `event_time` và **không có nghĩa dữ liệu trên SSTable được thu hồi ngay tại ngày thứ 30**.

### 5.2. Retention tính từ thời điểm sự kiện xảy ra

Nếu nghiệp vụ nói “30 ngày kể từ `event_time`” và sự kiện có thể đến muộn, có thể **không đặt TTL mặc định** rồi tính TTL còn lại ở đường ghi:

```sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, day_bucket, event_time, event_id,
    received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

```text
expires_at = event_time + 30 ngày
ttl_seconds = expires_at - thời điểm ghi

ttl_seconds > 0  -> ghi với TTL còn lại
ttl_seconds <= 0 -> đã hết hạn; xử lý theo chính sách dữ liệu quá hạn
```

Hai mục 5.1 và 5.2 là **hai phương án khác nhau** để chọn theo chính sách nghiệp vụ. Không áp dụng cả hai tùy tiện rồi giả định TTL luôn tính từ cùng một mốc; việc thay `default_time_to_live` cũng không bảo đảm mọi dữ liệu đã ghi trước đó có thời gian hết hạn được tính lại theo chính sách mới.

Để kiểm tra TTL còn lại của một cột trên hàng sống:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 10;
```

`TTL(payload)` cho số giây còn lại của ô có TTL. Giá trị `null` có thể do ô không có TTL hoặc không tồn tại; không dùng duy nhất một cột để suy diễn mọi ô trong hàng có cùng expiry.

## 6. Nhân dung lượng với replication factor đúng cách

Replication factor là số replica Cassandra duy trì cho dữ liệu theo cấu hình keyspace/đặt replica. Nếu tính **một bản sao logic của bảng** là `L` byte, với một datacenter có `RF = 3`, mô hình cấp cao:

```text
replicated_disk_bytes_in_dc ≈ L × 3
average_data_bytes_per_node ≈ (L × 3) / node_count_in_dc
```

Đây là **trung bình lý tưởng** trước khi xét phân bố token, partition nóng/lớn, node khác dung lượng, index và các thành phần không đồng đều. Chia đều để lập kế hoạch không có nghĩa mọi node thật sự dùng đúng bằng nhau.

### 6.1. Ví dụ NetworkTopologyStrategy

Một keyspace triển khai trên hai datacenter có thể có:

```sql
-- Ví dụ minh họa: tên DC phải khớp topology thực tế.
CREATE KEYSPACE telemetry_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_primary': 3,
    'dc_backup': 2
};
```

Trong ví dụ, **mỗi partition có 3 replica tại `dc_primary` và 2 tại `dc_backup`**, nếu topology có đủ node và cấu hình hoạt động phù hợp. Khi lập capacity:

```text
Dung lượng dc_primary ≈ L × 3
Dung lượng dc_backup  ≈ L × 2
Tổng hai DC           ≈ L × (3 + 2) = L × 5
```

Không lấy RF của DC chính rồi tự áp cho DC dự phòng, và không dùng `L × 5 / tổng số node` để quyết định riêng ổ đĩa mỗi DC nếu số node và phân bố khác nhau. **Mỗi DC phải được tính riêng** với số node, mức dự phòng và traffic tại đó.

### 6.2. Consistency level không nhân thêm dung lượng lưu

`LOCAL_QUORUM`, `ONE` hoặc các consistency level khác quyết định mức xác nhận replica cho mỗi thao tác theo topology. Chúng có thể ảnh hưởng độ trễ, lưu lượng và khả năng đọc/ghi khi replica lỗi, nhưng **không tạo thêm một bản sao vật lý chỉ vì chọn consistency level cao hơn**. RF/replication strategy mới là đầu vào của số replica được duy trì.

Repair giúp đồng bộ dữ liệu giữa các replica theo cơ chế Cassandra; nó không thay RF hay tạo dung lượng “miễn phí”. Khi node lỗi hoặc phục hồi, quá trình repair/streaming có thể tạo tải network, I/O và nhu cầu dung lượng tạm, cần tính trong phần dự phòng.

## 7. Index, bảng projection và những hệ số nhân khác

Một bảng query-driven có thể có cả **lookup table**, bảng thời gian, bảng theo status và secondary index/SAI. Chúng đều tiêu thụ tài nguyên nhưng không có cùng cách tính.

| Thành phần | Là gì? | Cách đưa vào ước lượng |
| --- | --- | --- |
| **Primary-key/partition index của SSTable** | Metadata phục vụ định vị partition và clustering | Thường nằm trong đo `S_disk` của base table; **đừng cộng lại** |
| **Bloom filter / summary** | Thành phần hỗ trợ đọc, có thể chiếm memory/disk tùy loại | Đo footprint và memory riêng; không chỉ tính dung lượng payload |
| **Secondary index / SAI** | Cấu trúc index bổ sung để hỗ trợ một số bộ lọc | Đo dung lượng index trên mỗi node/replica cùng write amplification |
| **Bảng lookup theo event ID** | Bảng Cassandra khác với partition key khác | Tính độc lập số hàng, kích thước và RF của bảng |
| **Bảng nhân bản theo truy vấn** | Denormalized representation cho màn hình khác | Tính tổng dung lượng, chi phí cập nhật/xóa và TTL của từng bảng |
| **Snapshot/backup/CDC files** | Dữ liệu phục vụ khôi phục hoặc luồng thay đổi | Dự trù ngoài dữ liệu bảng đang sống; có thể dùng chung block do hard link tùy cơ chế |

Đừng đồng nhất **index phụ** với **bảng projection**. Một index có cấu trúc và chi phí phụ thuộc phiên bản Cassandra/cách triển khai; một projection là một bảng query-driven do ứng dụng duy trì, thường có khóa và tập cột riêng.

### 7.1. Index không có hệ số cố định

Nếu benchmark cho thấy một chỉ mục bổ sung tốn thêm **25% dung lượng của base table** trong cấu hình thực tế, có thể thử mô hình:

```text
base_one_copy = L
measured_index_ratio = 0,25
base_plus_index_one_copy ≈ L × (1 + 0,25)
```

**25% chỉ là giả định minh họa**; các index của Cassandra có thể có tỷ lệ hoàn toàn khác theo loại cột, cardinality, phân bố giá trị, compression, update/delete và phiên bản. Không sử dụng 25% như con số mặc định cho SAI.

Nếu `S_disk` đã đo bao gồm index, hệ số này **không được cộng thêm lần nữa**. Nếu index chỉ có ở một bảng và không có ở bảng khác, tính riêng từng bảng.

### 7.2. Projection có thể tăng chi phí ghi mạnh hơn dung lượng sống

Giả sử một order được lưu vào ba bảng, trong đó một projection theo `status`. Mỗi lần đổi trạng thái có thể phải:

1. Cập nhật hàng nguồn.
2. Cập nhật danh sách theo customer.
3. Xóa hàng khỏi partition status cũ.
4. Ghi hàng vào partition status mới.

Ngay cả khi số hàng đang sống không tăng, **tombstone, commit log, memtable, SSTable và compaction** vẫn chịu tải của các mutation. Khi lập kế hoạch, ghi riêng **bytes live** và **write/delete churn** thay vì tính đúng một lần “kích thước mỗi order”.

## 8. TTL, tombstone và compaction thay đổi dung lượng như thế nào?

### 8.1. Hàng hết hạn không được dọn vật lý ngay

Trong Cassandra, TTL và `DELETE` tạo trạng thái xóa/tombstone để replica và SSTable cũ không tái hiện dữ liệu đã xóa. Sau khi hết TTL, dữ liệu không còn được trả về như hàng sống, nhưng byte vật lý có thể vẫn nằm trong SSTable cho tới khi compaction và các điều kiện an toàn cho phép thu hồi.

Vì vậy:

```text
disk_used ≠ live_rows × current_row_size

disk_used có thể bao gồm:
  dữ liệu sống
  + bản ghi hết hạn/chưa được dọn
  + tombstone
  + dữ liệu ghi đè còn trong SSTable cũ
  + index và metadata
  + dữ liệu tạm thời từ compaction/streaming/snapshot
```

`gc_grace_seconds` và việc replica đã nhận/đồng bộ các delete liên quan đến an toàn dọn tombstone. Không giảm tham số này tùy tiện chỉ để giảm disk used; cần chính sách repair/node downtime phù hợp và kiểm tra cơ chế của phiên bản Cassandra đang dùng.

### 8.2. Compaction tạo thêm nhu cầu dung lượng tạm

Compaction đọc các SSTable hiện có, tạo SSTable mới rồi mới thu hồi file cũ khi đủ điều kiện. Trong lúc đó, **cả đầu vào và đầu ra** có thể cùng tồn tại trên đĩa. Cần chừa headroom cho:

- Compaction đang chạy và compaction backlog.
- Repair, rebuild/streaming hoặc thay node.
- Tăng tải đột biến, replay/backfill và thời gian downtime.
- Snapshot, backup hoặc file CDC đang giữ trên local disk (tùy triển khai).

Không tự dùng `100% disk capacity` làm dung lượng có thể lấp bằng dữ liệu sống. Một cụm đã gần đầy có thể khó compaction hoặc streaming khi node lỗi, dù phép tính `live_rows × RF` vẫn “vừa”.

### 8.3. TimeWindowCompactionStrategy và retention

Với time-series chủ yếu append-only, TTL tương đối đồng nhất và ít sửa dữ liệu cũ, **TimeWindowCompactionStrategy (TWCS)** là ứng viên đáng khảo sát. Tuy nhiên:

- Cửa sổ compaction được tổ chức theo **timestamp ghi trên storage**, không tự lấy từ `day_bucket` của partition key.
- Sự kiện đến muộn/backfill, sửa dữ liệu cũ và TTL rất khác nhau có thể làm SSTable không hết hạn đồng loạt như dự kiến.
- Một bảng lookup cập nhật thường xuyên có mẫu ghi khác bảng lịch sử; không mặc định cùng compaction strategy.
- TWCS không sửa được partition key thiếu bucket hoặc một partition đang nhận quá nhiều tải.

Đo dung lượng ở trạng thái sau nhiều chu kỳ TTL/compaction, không tuyên bố “bản ghi hết hạn ngày 30 thì ngay ngày 31 ổ đĩa chắc chắn giảm đúng tương ứng”.

## 9. Ví dụ tính capacity hoàn chỉnh

Áp dụng dữ liệu ở phần 3, giả sử benchmark của **một replica base table** cho thấy `S_disk = 750 B/hàng sống`, **đã gồm** primary key, các thành phần SSTable base và ảnh hưởng compression trên mẫu đại diện; chưa gồm secondary index, snapshot, compaction headroom và bảng projection khác.

Giả định triển khai **một DC, RF=3, 6 node cùng loại**; mục tiêu chỉ dùng **70% dung lượng đĩa cấp phát** cho phần dữ liệu đã được mô hình hóa. Tỷ lệ 70% là **giả định lập kế hoạch**, không phải quy tắc bắt buộc của Cassandra.

| Bước | Công thức | Kết quả |
| --- | --- | ---: |
| 1. Hàng mới/ngày | `100 × 86.400` | 8.640.000 hàng |
| 2. Hàng sống sau retention 30 ngày | `8.640.000 × 30` | 259.200.000 hàng |
| 3. Dữ liệu nghiệp vụ thô | `259.200.000 × 900 B` | 233,28 GB |
| 4. Base table trên **một bản sao** | `259.200.000 × 750 B` | 194,40 GB |
| 5. Base table trên **RF=3** | `194,40 × 3` | 583,20 GB |
| 6. Dung lượng phải cấp nếu chỉ dùng 70% | `583,20 / 0,70` | ~833,14 GB toàn DC |
| 7. Bình quân theo 6 node | `833,14 / 6` | ~138,86 GB/node cấp phát |

**Diễn giải đúng:** đây là **phép tính baseline của một bảng**. Nó chưa có secondary index, bảng lookup, audit log, snapshot/CDC local, phần chênh do tải không đều và các đợt compaction/streaming vượt mức dự phòng đã giả định. Không được kết luận “ổ 140 GB/node chắc chắn đủ” chỉ từ phép tính này.

### 9.1. Nếu thêm index với tỷ lệ đã đo

Giả sử benchmark thực tế cho index của chính bảng này cho ra **25% dung lượng base** (giả định minh họa):

```text
Base cả RF:                      583,20 GB
Index cả RF:   583,20 × 0,25 =   145,80 GB
Base + index:                   729,00 GB
Provisioned ở 70%: 729 / 0,70 ≈ 1.041,43 GB toàn DC
Trung bình 6 node:             ≈ 173,57 GB/node
```

Một chỉ mục có thể tăng khoảng cấp phát baseline từ ~833 GB lên ~1.041 GB **trong kịch bản giả định**. Nếu thay vào đó tạo một bảng lookup nhỏ, phải tính kích thước lookup và RF **theo số hàng của bảng lookup**, không lấy tỷ lệ 25% của index để áp cho bảng mới.

### 9.2. Cấp phát theo DC và theo node

Tổng disk capacity không thể thay thế kiểm tra từng node. Với một DC gồm 6 node mà dữ liệu phân bố không đều, node lớn nhất có thể cao hơn trung bình. Kế hoạch cần:

- Quan sát **dung lượng dùng của node lớn nhất**, không chỉ trung bình.
- Dự trù một node có thể vắng và dữ liệu cần streaming khi thay node; xác định kịch bản sự cố đã được hệ thống chấp nhận.
- Tính riêng keyspace/table có RF khác nhau hoặc các DC có RF khác nhau.
- Dành chỗ cho hệ điều hành, commit log, cache trên disk, snapshot và các thành phần ngoài SSTable nếu dùng cùng ổ.

### 9.3. MB và MiB không giống nhau

Trong ví dụ trên, **GB dùng đơn vị thập phân**:

```text
1 GB  = 1.000.000.000 byte
1 GiB = 1.073.741.824 byte
```

Đĩa thương mại, hệ điều hành, tool đo và dashboard có thể hiển thị GB hoặc GiB khác nhau. Khi báo cáo, **ghi rõ đơn vị** và không trộn giá trị decimal với binary trong cùng phép tính.

## 10. Tính kích thước và độ nóng của partition riêng biệt

Tổng dung lượng cụm có thể nhìn hợp lý trong khi một partition của thiết bị rất nóng lại quá lớn. Giả sử thiết bị nặng nhất phát **25 sự kiện/giây liên tục**, mỗi event 900 B thô:

| Bucket | Số hàng trong bucket | Dữ liệu thô/partition |
| --- | ---: | ---: |
| 1 phút | 1.500 | 1,35 MB |
| 1 giờ | 90.000 | 81 MB |
| 1 ngày | 2.160.000 | 1.944 MB (~1,94 GB) |

Nếu bảng dùng `PRIMARY KEY ((tenant_id, device_id, day_bucket), event_time, event_id)`, toàn bộ **2,16 triệu hàng/ngày** của thiết bị đó vào một partition logic; hash/token **không chia partition đó** thành 24 phần độc lập.

Bucket giờ tạo khoảng **90.000 hàng/partition** theo giả định và làm số partition cần đọc một ngày tăng từ 1 lên tối đa 24 bucket giờ cho đúng một ngày lịch. Một cửa sổ trượt 24 giờ **có thể chạm 25 bucket giờ** do lệch biên. Bucket nhỏ hơn làm giảm độ lớn partition, nhưng **fan-out, pagination và chi phí truy vấn khoảng dài tăng**.

Độ lớn “81 MB thô” không tự là ngưỡng tốt/xấu. Cần đo:

- Partition lớn nhất theo **số hàng, byte trên SSTable và tombstone**.
- Tốc độ ghi đỉnh vào partition và tập replica tương ứng.
- p95/p99 latency khi lấy mới nhất, đọc khoảng và paging qua bucket.
- Độ rộng bucket và yêu cầu xem lịch sử nhiều giờ/ngày của sản phẩm.

Nếu một bucket giờ vẫn quá nóng, có thể cân nhắc `shard_id` ổn định trong partition key, nhưng đọc danh sách sự kiện của cả giờ sẽ phải hợp nhất từ nhiều shard. Sharding giải quyết tải phân bố, **không tạo dung lượng miễn phí**.

## 11. Dự báo tăng trưởng, retention và dự phòng vận hành

Capacity planning không nên dừng ở một con số hôm nay. Cần xem các kịch bản:

| Kịch bản | Giả định thay đổi | Tác động cần tính lại |
| --- | --- | --- |
| Thêm 50% thiết bị | Tăng sự kiện/giây nếu hành vi giữ nguyên | Tăng rows/day, disk/network và có thể cần thêm node |
| Retention 30 → 90 ngày | Giữ thêm dữ liệu sống | Hàng sống xấp xỉ gấp 3 ở tải ổn định, chưa kể tombstone |
| Payload trung bình tăng 900 → 1.800 B | Event chứa thêm trường | Tăng raw bytes; `S_disk` phải benchmark lại vì compression thay đổi |
| Thêm bảng lookup cho toàn bộ event | Mỗi event có representation thứ hai | Thêm table bytes, RF, mutation và chi phí vận hành |
| Thêm SAI trên một số cột | Thêm cấu trúc index | Đo index bytes, mem và write amplification |
| Thay RF ở một DC | Thêm hoặc bớt replica | Thay dung lượng và chi phí streaming/repair |
| Giữ nhiều snapshot hơn | Tăng bản sao/khối dữ liệu chưa thu hồi | Cần dự phòng local/backup theo chính sách |
| Backfill 100 triệu event cũ | Tăng write burst, có thể tác động TTL và compaction | Thử tải nhập, quota và disk headroom tạm |

### 11.1. Công thức lập kế hoạch theo bảng và DC

Với mỗi bảng `i` và datacenter `dc`:

```text
base_bytes_i = expected_live_rows_i × measured_bytes_per_live_row_i

dc_table_bytes_i =
    (base_bytes_i + measured_secondary_index_bytes_i)
    × RF_i,dc

dc_modeled_used_bytes =
    tổng dc_table_bytes_i
    + estimated_expired_or_obsolete_bytes_not_yet_reclaimed
    + other_local_disk_usage_in_scope

dc_required_capacity ≈
    dc_modeled_used_bytes / target_disk_utilization
    + additional_reserve_not_covered_by_utilization_target
```

Đây là **mô hình cấp cao** chứ không phải công thức đo được chính xác mọi thời điểm. Phần “obsolete chưa thu hồi” phải lấy từ **thử nghiệm TTL/compaction**, không cộng trùng nếu `measured_bytes_per_live_row` đã được đo ở steady state và bao gồm nó. Phần dự phòng thêm phải ghi rõ nó dùng cho compaction, streaming, snapshot hay tăng trưởng để tránh **đếm chồng** với tỷ lệ target utilization.

### 11.2. Tránh dự báo chỉ theo tổng cluster

Nên lập bảng theo **mỗi DC**, **mỗi keyspace/table**, và với tải lệch theo **tenant/partition lớn nhất**. Một node có thể đầy trước những node khác do placement, topology và các dữ liệu không phân đều. RF cũng làm tăng nhu cầu tài nguyên khi chuyển replica sau sự cố; tính đúng trung bình chưa bảo đảm an toàn trong trạng thái degraded.

Không có một tỷ lệ headroom “70%” bắt buộc cho mọi Cassandra. Mục tiêu sử dụng đĩa cần phản ánh loại ổ, tốc độ compaction, repair/streaming, khả năng thay node, retention và quy trình vận hành thực tế.

## 12. Java: công cụ ước lượng baseline và kiểm soát đầu vào

Một ứng dụng Java hoặc script nội bộ có thể tính baseline từ **số đo đã thu thập**, thay vì cộng tay dễ nhầm. Mã Java thuần sau dùng đơn vị **byte thập phân**, có kiểm tra một số phép nhân `long` và gắn nhãn rõ assumptions:

```java
import java.util.Locale;

public final class CassandraCapacityEstimate {
    private static final long SECONDS_PER_DAY = 86_400L;
    private static final double BYTES_PER_GB = 1_000_000_000d;

    public static void main(String[] args) {
        long averageEventsPerSecond = 100L;
        int retentionDays = 30;
        double measuredDiskBytesPerLiveRow = 750d;
        int replicationFactor = 3;
        int nodesInDc = 6;
        double targetUtilization = 0.70d;

        long rowsPerDay = Math.multiplyExact(
            averageEventsPerSecond, SECONDS_PER_DAY
        );
        long liveRows = Math.multiplyExact(rowsPerDay, retentionDays);

        // Số đo của một bản sao base table, chưa tính index phụ.
        double oneCopyGb =
            liveRows * measuredDiskBytesPerLiveRow / BYTES_PER_GB;
        double replicatedGb = oneCopyGb * replicationFactor;
        double provisionedGb = replicatedGb / targetUtilization;
        double averageGbPerNode = provisionedGb / nodesInDc;

        System.out.printf(Locale.ROOT, "rows/day: %,d%n", rowsPerDay);
        System.out.printf(Locale.ROOT, "live rows: %,d%n", liveRows);
        System.out.printf(Locale.ROOT, "one copy: %.2f GB%n", oneCopyGb);
        System.out.printf(Locale.ROOT, "RF copies: %.2f GB%n", replicatedGb);
        System.out.printf(Locale.ROOT, "provisioned: %.2f GB%n", provisionedGb);
        System.out.printf(Locale.ROOT, "average per node: %.2f GB%n",
                          averageGbPerNode);
    }
}
```

Giá trị kỳ vọng ở ví dụ:

```text
rows/day: 8,640,000
live rows: 259,200,000
one copy: 194.40 GB
RF copies: 583.20 GB
provisioned: 833.14 GB
average per node: 138.86 GB
```

Đây **không phải** công cụ tự đo cụm Cassandra; nó chỉ tính từ đầu vào đã cho. Với đầu vào lớn hơn phạm vi `long`, `Math.multiplyExact` sẽ báo lỗi thay vì tràn số âm thầm. Trong công cụ thực tế cần thêm kiểm tra `targetUtilization > 0`, số node/RF hợp lệ, kịch bản tăng trưởng và khả năng nhiều DC/bảng/index riêng.

### 12.1. Đo và đưa số liệu thực vào estimator

Với DataStax Java Driver 4.x, ứng dụng có thể thu thập metadata nghiệp vụ trên đường ghi (số event, kích thước payload trước ghi, phân bố theo device/tenant) và dùng prepared statement để ghi đúng partition. Tuy nhiên, **driver không tự biết số byte SSTable mà một event sẽ chiếm sau compaction**.

Để có `measuredDiskBytesPerLiveRow` đáng tin:

- Dựng workload benchmark với các CQL table/index/TTL dự kiến.
- Dùng metric Cassandra và công cụ vận hành như `nodetool tablestats`, `nodetool tablehistograms` (cú pháp và tập metric phụ thuộc phiên bản) để quan sát disk, kích thước partition và latency.
- Đo kích thước SSTable/base/index theo node, cộng đúng phạm vi bản sao, và kiểm tra số liệu với trạng thái flush/compaction.
- Theo dõi `nodetool status`/metric phân bố dữ liệu từng node, không coi một con số toàn cụm là đại diện cho node nặng nhất.
- Không chạy `SELECT COUNT(*)` không giới hạn trên bảng hàng tỷ sự kiện của sản xuất chỉ để đếm hàng cho bài toán capacity.

Các metric Cassandra chỉ phản ánh trạng thái tại thời điểm đo; lưu cùng chúng **schema, RF, retention, compaction strategy, số hàng sống, số tombstone và thời gian chạy tải** để so sánh được khi mô hình thay đổi.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Lấy kích thước JSON/HTTP làm byte SSTable | Sai overhead/compression/index | Benchmark `S_disk` theo schema và workload thật |
| Lấy `rows × size` rồi quên RF | Thiếu số replica và dung lượng từng DC | Tính riêng RF của mỗi DC |
| Nhân RF vào số `disk used` đã đo trên toàn cụm | Đếm số bản sao hai lần | Ghi rõ phạm vi số đo |
| Không tính bảng lookup/projection | Thiếu nhiều representation của cùng event | Lập danh sách tất cả bảng theo query shape |
| Mặc định index chiếm 25% hoặc 100% | Có thể cấp phát dư hoặc thiếu | Đo theo cột, phiên bản, cardinality và tải |
| Tưởng TTL hết là disk free ngay | Thiếu phần tombstone/SSTable chưa được dọn | Đo steady-state compaction và dự phòng |
| Dùng `gc_grace_seconds` thấp tùy ý để tiết kiệm đĩa | Tăng nguy cơ lỗi xóa/resurrection trong một số tình huống | Thiết kế repair, downtime và grace an toàn |
| Lấy tốc độ trung bình để chọn bucket | Thiết bị nóng tạo partition lớn và hotspot | Đo peak per-key, p99 payload, size/partition |
| Cộng gộp DC rồi chia cho tổng node | Một DC có thể hết disk sớm | Tính RF, node và headroom riêng từng DC |
| Dùng toàn bộ ổ cho dữ liệu sống | Không còn chỗ compaction/rebuild/streaming | Mục tiêu utilization và dự phòng có chứng cứ |
| Nhầm `LIMIT 50` với đọc 50 cell vật lý | Tombstone/range scan vẫn có thể đắt | Theo dõi tombstone scanned và read p99 |
| Dự báo tuyến tính khi ingestion đang tăng nhanh | Thiếu dung lượng cuối kỳ | Mô hình theo cửa sổ retention và growth scenario |
| Coi một cluster test chưa có TTL là mẫu sản xuất | Thiếu churn/compaction của dữ liệu hết hạn | Benchmark qua nhiều tuổi dữ liệu và update/delete |

## 14. Checklist thẩm định capacity

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Có danh sách mọi bảng theo query shape chưa? | Mapping Q01–Qn → bảng, index, số hàng và retention riêng |
| Đã biết tốc độ ghi chưa? | Trung bình/peak theo cụm, DC, tenant và khóa nóng nhất |
| Payload có phân bố ra sao? | Average/p95/p99/max bytes và cơ chế nén |
| Có kích thước SSTable thực tế chưa? | Mẫu benchmark, `S_disk` và số liệu index rõ phạm vi |
| Dữ liệu được giữ bao lâu? | TTL từ write time/event time, late arrivals và backfill |
| RF được tính theo DC chưa? | NTS/RF, số node, placement và kịch bản một node lỗi |
| Đã tách live data khỏi tombstone/compaction chưa? | Có số đo ở steady state và dự phòng disk |
| Partition nóng nhất có giới hạn không? | Rows/bytes/peak writes cho bucket và shard dự kiến |
| Có chừa chỗ ngoài SSTable không? | Snapshot/backup/CDC, commit log, OS và streaming |
| Có kịch bản tăng trưởng không? | 3/6/12 tháng, retention và schema thay đổi |
| Có ngưỡng mở rộng/tối ưu không? | Alert cho node disk, compaction backlog, p99 và hot partitions |
| Có kiểm thử khi node lỗi không? | Repair/rebuild/streaming và thời gian khôi phục đã đo |

## 15. Bài tập thực hành

Một nền tảng giao nhận ghi sự kiện quét mã với các cột:

```text
tenant_id, parcel_id, scan_id, scan_time, received_at,
location_id, status, payload
```

Thông số giả định:

| Tham số | Giá trị |
| --- | ---: |
| Tốc độ trung bình | 250 sự kiện/giây toàn hệ thống |
| Kích thước nghiệp vụ thô | 1.200 B/sự kiện |
| Dung lượng đo được của một bản sao base table | 950 B/hàng sống |
| Thời gian lưu | 14 ngày từ thời điểm ghi |
| RF | 3 trong một DC |
| Số node DC | 8 node |
| Tỷ lệ sử dụng mục tiêu | 65% |
| Bảng tra cứu thêm | Có thể cần, chưa đo kích thước |
| Lưu lượng nóng nhất của một parcel | 15 sự kiện/giây trong vài giờ |

**Yêu cầu:**

1. Tính số hàng tạo ra trong một ngày và số hàng sống xấp xỉ sau 14 ngày nếu tốc độ ổn định.
2. Tính dung lượng thô của một representation và dung lượng một bản sao base table dựa trên `950 B/hàng`.
3. Tính tổng dung lượng base table trên RF=3, dung lượng cấp phát ở mục tiêu 65% và trung bình cấp phát/node nếu phân bố lý tưởng.
4. Nếu có thêm SAI đo được bằng 15% base table (giả định riêng của bài), tính capacity mới. Nêu vì sao không tự áp 15% cho mọi index.
5. Đề xuất partition/clustering key cho API “xem 50 lần quét gần nhất của parcel trong một giờ UTC”. Tính hàng/byte thô ở bucket giờ và ngày cho parcel nóng nhất. Bucket nào đáng benchmark trước?
6. Liệt kê những hạng mục phép tính trên **chưa bao gồm**: dữ liệu hết TTL chưa dọn, compaction, snapshot/CDC, bảng lookup, tăng trưởng, skew và kịch bản node lỗi.
7. Giải thích sự khác nhau khi retention đổi từ **14 ngày kể từ lúc ghi** sang **14 ngày kể từ `scan_time`** trong trường hợp scan gửi muộn ba ngày.

**Gợi ý đối chiếu:**

```text
250 × 86.400 = 21.600.000 sự kiện/ngày
21.600.000 × 14 = 302.400.000 hàng sống

Raw một representation:
  302.400.000 × 1.200 B = 362,88 GB

Base một bản sao:
  302.400.000 × 950 B = 287,28 GB
Base RF=3:
  287,28 × 3 = 861,84 GB
Cấp phát nếu target 65%:
  861,84 / 0,65 ≈ 1.325,91 GB/DC
Trung bình 8 node:
  1.325,91 / 8 ≈ 165,74 GB/node

Nếu index bổ sung 15% dung lượng base:
  861,84 × 1,15 = 991,116 GB
  991,116 / 0,65 ≈ 1.524,79 GB/DC
  ≈ 190,60 GB/node

Parcel nóng 15 event/s:
  một giờ = 54.000 event; raw ≈ 64,8 MB
  một ngày = 1.296.000 event; raw ≈ 1.555,2 MB (~1,56 GB)
```

Ứng viên theo giờ: `PRIMARY KEY ((tenant_id, parcel_id, hour_bucket), scan_time, scan_id)` với clustering giảm dần, `hour_bucket` là mốc UTC đầu giờ. Nếu sự kiện đến muộn ba ngày, retention tính từ `scan_time` chỉ còn khoảng **11 ngày** tại lúc ghi, thay vì đủ 14 ngày kể từ khi ghi.

## Kết luận

Dung lượng Cassandra phải được tính **từ đường truy vấn và tốc độ ghi**, sau đó chuyển qua **số hàng sống trong retention**, **byte trên đĩa đo được cho từng bảng/index**, **RF của mỗi datacenter** và **dung lượng dự phòng vận hành**. TTL, tombstone, compaction, repair, streaming và sự phân bố không đều có thể làm kết quả thực tế khác xa phép tính `rows × raw bytes × RF` đơn giản. Một bản dự báo tốt ghi rõ giả định, không đếm trùng index hoặc replica, xét node và partition nóng nhất, đồng thời được hiệu chỉnh liên tục bằng phép đo trên dữ liệu đại diện.
