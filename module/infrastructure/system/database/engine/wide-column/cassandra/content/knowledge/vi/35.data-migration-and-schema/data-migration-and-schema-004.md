# Thiết kế bảng mới khi cần đổi partition/clustering key

## 1. Tình huống: thiết kế đúng lúc ban đầu nhưng không còn phù hợp sau hai năm

Giả sử một ứng dụng **Apache Cassandra** lưu sự kiện IoT. Khi triển khai, mỗi thiết bị chỉ gửi vài sự kiện mỗi ngày nên nhóm phát triển dùng `device_id` làm **partition key**, `event_time` làm **clustering key**. Hai năm sau, một số thiết bị gửi hàng chục sự kiện mỗi giây. Người dùng cũng chuyển từ xem toàn bộ lịch sử sang xem **sự kiện theo ngày, theo loại và theo khoảng thời gian**.

Các dấu hiệu bắt đầu xuất hiện:

- Partition của thiết bị hoạt động lâu năm ngày càng lớn, tạo áp lực đọc SSTable, compaction và repair.
- Truy vấn “các sự kiện loại `ALARM` trong ngày” phải đọc/lọc nhiều sự kiện khác loại.
- API phân trang lịch sử với `LIMIT` vẫn gặp tombstone scan và độ trễ p99 khó dự đoán.
- Một số phân vùng nóng gây tải không đồng đều cho các nhóm replica.
- Dữ liệu cũ cần được di chuyển mà ứng dụng vẫn tiếp tục ghi hàng mới, cập nhật hoặc xóa.

Ý tưởng dễ nghĩ tới là sửa primary key bằng `ALTER TABLE`. **Cassandra không hỗ trợ thay đổi cấu trúc partition key hoặc clustering key của bảng hiện hữu theo cách đó.** Muốn thay cách định tuyến và sắp xếp dữ liệu, ta thường phải **tạo bảng mới**, ghi dữ liệu theo schema mới, di chuyển dữ liệu cũ, chuyển đường đọc/ghi và kiểm chứng trước khi loại bảng cũ.

Bài trong chương **Di chuyển và schema** giải thích toàn bộ chu trình ấy, gắn với bản chất wide-column Cassandra: token/replica, thiết kế bảng theo truy vấn, CQL, replication, consistency, SSTable, tombstone, repair và Java Driver.

**Mục tiêu học tập:**

1. Giải thích được vì sao đổi partition/clustering key là **thay đổi mô hình lưu trữ**, không phải đổi tên một cột.
2. Thiết kế được bảng **v2** theo workload mới, kể cả khi cần nhiều projection.
3. Phân biệt các bước **expand → dual-write/CDC → backfill → reconcile → cutover → contract**.
4. Đảm bảo không bỏ sót event mới, event đến muộn, update và delete; hiểu giới hạn consistency khi hai bảng cùng tồn tại.
5. Viết CQL và một ví dụ **Java Driver 4.x** để backfill có kiểm soát.
6. Định nghĩa phép đo, tiêu chí go/no-go, rollback và thời điểm an toàn để dừng bảng cũ.

**Giả định lab:** một datacenter tên `dc1`, keyspace dùng `NetworkTopologyStrategy` với RF = 3 và đủ node cho `LOCAL_QUORUM`. Các ví dụ Java/CQL chỉ để học và thử nghiệm trong môi trường riêng; phiên bản Cassandra, driver, chức năng CDC và công cụ backfill cần được xác minh trên hệ thống thật.

## 2. Partition key và clustering key quyết định điều gì?

Một primary key Cassandra có hai lớp:

~~~sql
PRIMARY KEY ((partition_key_part_1, partition_key_part_2),
             clustering_column_1, clustering_column_2)
~~~

- **Partition key** được phân vùng và băm thành **token**. Token ring và replication strategy chọn **natural replicas** giữ toàn bộ partition.
- **Clustering columns** xác định **định danh và thứ tự các hàng bên trong partition**; truy vấn range hiệu quả phải tuân quy tắc truy cập theo tiền tố clustering.
- **Regular columns** chứa payload, không tự thay đổi token hoặc thứ tự clustering.

~~~mermaid
flowchart TD
    A["PRIMARY KEY của bảng v1"] --> B["Partition key = device_id"]
    B --> C["Token và replica set cho mọi event của device"]
    A --> D["Clustering = event_time, event_id"]
    D --> E["Thứ tự event trong partition device"]
    F["PRIMARY KEY của bảng v2"] --> G["Partition key = device_id + event_day"]
    G --> H["Token/replica set có thể khác theo ngày"]
    F --> I["Clustering = event_time, event_id"]
    I --> J["Thứ tự event trong từng ngày"]
~~~

| Thay đổi mong muốn | Có thể chỉ dùng `ALTER TABLE` trên bảng cũ? | Vì sao? |
| --- | --- | --- |
| Thêm một regular column độc lập | Thường **có**, với ràng buộc phiên bản/schema. | Không làm đổi cách xác định partition/hàng. |
| Đổi `device_id` thành `(device_id, event_day)` | **Không**. | Dữ liệu phải được phân bổ lại theo token của khóa mới. |
| Đổi thứ tự clustering từ `(event_time, event_id)` thành `(event_type, event_time, event_id)` | **Không**. | Định danh hàng, thứ tự lưu trữ và khả năng query đổi. |
| Đổi giá trị partition/clustering key của một hàng | Không phải cập nhật một regular column thông thường. | Về logic cần tạo hàng tại khóa mới và xử lý hàng cũ; có các rủi ro consistency/tombstone. |
| Chỉ đổi tên cột khóa | Có thể có hỗ trợ `RENAME` với điều kiện tùy phiên bản. | **Đổi tên không đổi số lượng, thứ tự hay thành phần primary key.** |
| Tạo projection phục vụ một truy vấn khác | **Tạo bảng mới**. | Một bố cục primary key không tự tối ưu được mọi truy vấn. |

**Hệ quả cốt lõi:** metadata của bảng không thể “biến” SSTable đã ghi theo khóa A thành dữ liệu được lưu theo khóa B mà không đọc, biến đổi và ghi lại. Việc đổi key luôn phải tính tới **backfill và đồng bộ các mutation phát sinh trong thời gian chuyển đổi**.

## 3. Xuất phát từ truy vấn, không xuất phát từ tên cột muốn thêm

Trước khi định nghĩa bảng v2, liệt kê những truy vấn **đang được người dùng thực sự gọi**, giới hạn thời gian và số hàng:

| Mẫu truy vấn | Độ thường xuyên | Thiết kế có thể cân nhắc |
| --- | --- | --- |
| A. Lấy 50 event mới nhất của một thiết bị | Rất cao | `events_by_device_day`; tìm ở bucket hiện tại rồi lùi ngày nếu cần. |
| B. Đọc sự kiện của thiết bị trong [08:00, 09:00) UTC | Cao | `(device_id, event_day)` + range trên `event_time`. |
| C. Chỉ lấy loại `ALARM` của thiết bị trong một ngày | Cao | Bảng riêng theo `(device_id, event_day)`, clustering `event_type, event_time, event_id` hoặc projection phù hợp. |
| D. Xem mọi thiết bị của site có cảnh báo trong giờ | Trung bình | Bảng/projection theo `(site_id, bucket_hour)`, phải kiểm soát hotspot. |
| E. Tổng cảnh báo của site theo ngày trong 12 tháng | Trung bình | Rollup/aggregate riêng, tránh quét tất cả raw events. |

**Không cố biến một bảng thành lời giải cho A–E.** Cassandra thường thiết kế **một hoặc nhiều bảng theo truy vấn**, chấp nhận nhân bản dữ liệu có chủ đích và quản lý nhất quán trong ingestion pipeline.

### 3.1. Ba câu hỏi đánh giá khóa mới

1. **Partition bounded?** Với peak events/second, kích thước event trung bình và TTL, mỗi partition sẽ lớn tới mức nào?
2. **Query bounded?** Một API phải mở bao nhiêu partition/bucket, trả bao nhiêu byte và merge bao nhiêu danh sách?
3. **Write bounded?** Có một partition bị ghi quá nóng không; thêm bucket hay shard có giúp phân tán thực sự, và chi phí fan-out khi đọc là bao nhiêu?

Mọi thay đổi schema cần benchmark **read p95/p99, write rate, phân phối partition size, tombstones, SSTable count, compaction/repair cost**, chứ không chỉ nhìn truy vấn mẫu chạy nhanh.

## 4. Ví dụ CQL: bảng v1 và hai bảng v2

### 4.1. Keyspace lab và bảng v1

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_migration
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_migration.events_v1 (
  device_id text,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Tất cả sự kiện của `device-7` cùng partition key `device-7`. Dữ liệu được sắp theo thời gian **trong partition này**, nhưng partition có thể phát triển nhiều năm.

### 4.2. Bảng v2 cho truy vấn theo thiết bị/ngày

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_migration.events_by_device_day_v2 (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Điểm khác biệt duy nhất trong primary key so với v1:** `event_day` nằm **trong partition key** chứ không phải một regular column. Cùng thiết bị, hai ngày khác nhau có thể map vào hai token/nhóm replica khác nhau. `event_time` vẫn phục vụ range scan và `event_id` phân biệt hai sự kiện có cùng timestamp.

### 4.3. Bảng v2 thứ hai khi truy vấn theo loại sự kiện

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_migration.events_by_device_day_type_v2 (
  device_id text,
  event_day date,
  event_type text,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_type, event_time, event_id)
) WITH CLUSTERING ORDER BY (
  event_type ASC, event_time DESC, event_id ASC
);
~~~

Trong bảng này, `event_type` là **clustering column đầu tiên**. Câu truy vấn theo `event_type = 'ALARM'` rồi khoảng `event_time` sẽ phù hợp. Nhưng câu “mọi loại sự kiện trong ngày theo thời gian mới nhất” không còn có thứ tự toàn cục mong muốn khi bỏ qua `event_type`; vì vậy **vẫn cần bảng `events_by_device_day_v2`** cho truy vấn A/B.

~~~sql
SELECT event_time, event_id, payload
FROM telemetry_migration.events_by_device_day_type_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_type = 'ALARM'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z';
~~~

Không thể chuyển đổi hai kiểu clustering bằng **một `ALTER TABLE`**. Hai bảng là hai bố cục vật lý phục vụ hai mẫu truy vấn. Nếu ứng dụng không cần query C thường xuyên, bảng thứ hai chỉ làm tăng chi phí write/storage/repair; **đừng tạo projection nếu chưa có lý do đo được**.

## 5. Chọn kích thước bucket và thứ tự clustering trước khi migrate

Với `events_by_device_day_v2`, tính `event_day` bằng **UTC date** của `event_time`:

~~~text
event_time = 2026-11-20T23:59:59.999Z -> event_day = 2026-11-20
event_time = 2026-11-21T00:00:00.000Z -> event_day = 2026-11-21
~~~

Nếu service viết dùng ngày địa phương UTC+7 nhưng job backfill dùng ngày UTC, **cùng event có thể được ghi vào hai partition khác nhau**. Vì thế hàm `bucket(event_time)` phải là **một hợp đồng dữ liệu được version hóa**, dùng thống nhất trên mọi writer và job.

### 5.1. Ước lượng partition size

Đặt:

- `λ`: tốc độ sự kiện/giây ở **thiết bị nóng**, không chỉ trung bình cluster.
- `T`: thời lượng bucket tính bằng giây.
- `B`: byte/event/replica ước lượng sau khi tính overhead phù hợp.

~~~text
events_per_bucket ≈ λ × T
partition_bytes   ≈ λ × T × B

Ví dụ peak duy trì: λ = 25 events/s, B = 500 bytes/event.
Theo ngày: 25 × 86.400 × 500 = 1.080.000.000 B ≈ 1,08 GB/partition
Theo giờ : 25 ×  3.600 × 500 =    45.000.000 B ≈ 45 MB/partition
~~~

Đây là **ước lượng đơn giản**, không phải kích thước SSTable chính xác. Nếu partition theo ngày vẫn quá lớn, hãy cân nhắc bucket theo giờ hoặc shard có kiểm soát. Đổi lại, truy vấn ba ngày sẽ cần khoảng 72–73 bucket giờ thay vì 3–4 bucket ngày; phải đo **fan-out và p99**.

### 5.2. Đọc nhiều bucket không có ORDER BY toàn cục

Với khoảng `[2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)`, ứng dụng phải đọc **hai** partition ngày:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:45:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:15:00Z';
~~~

Hai tập kết quả được sắp **trong từng partition**; Java service phải merge/sort theo `event_time`, rồi `event_id` khi cần tie-breaker. `LIMIT 50` ở mỗi bucket cũng không tự trở thành `LIMIT 50` toàn bộ hai bucket. Trước khi chuyển schema, cần nâng phiên bản ứng dụng để **biết fan-out, deadline, pagination và giới hạn số bucket**.

## 6. Đánh giá tác động trước khi tạo bảng mới

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| **CQL/schema** | Bảng nào đọc/ghi v1? Những prepared statement nào chứa tên bảng/cột/primary key cũ? |
| **Partition/query** | Có truy vấn thiếu `event_day`, theo một device hay nhiều device, last N hay time range? |
| **Tính đúng** | `event_id` có ổn định? Có update/delete, TTL, event đến muộn hoặc thay đổi timestamp không? |
| **Đồng bộ** | Những mutation mới sẽ tới v2 qua dual-write, CDC, event stream hay outbox? Ai giữ trạng thái retry? |
| **Lưu trữ** | Trong giai đoạn song song có đủ disk cho v1 + v2 + compaction + snapshot + streaming? |
| **Replica/CL** | Cùng keyspace RF nào theo DC? Thay partition key sẽ dẫn tới nhóm replica khác? |
| **Bảo mật** | Role nào cần `CREATE`/schema migration, role app cần `SELECT`/`MODIFY` ở v2? |
| **Dịch vụ phụ** | Batch jobs, analytics, dashboard, backup/export, monitoring, CDC consumer có phụ thuộc bảng cũ? |
| **Rollback** | Khi đã chuyển read sang v2, vẫn có thể quay lại v1 mà không mất mutation mới không? |
| **Kiểm chứng** | Tiêu chí dữ liệu đủ, độ trễ đạt, replica ổn định và khả năng sửa chênh lệch là gì? |

**Đặc biệt:** đổi partition key không chỉ đổi tên hàng. Cassandra tính token từ khóa phân vùng, do đó cùng event có thể được gửi đến **những natural replicas khác** sau chuyển đổi. Không được suy “cùng RF = 3 nên chuyển dữ liệu tại chỗ không cần ghi/stream lại”.

## 7. Chiến lược nhiều giai đoạn: expand, migrate và contract

Phương án an toàn cho ứng dụng đang chạy là **thêm trước, chuyển dần, xóa sau** (*expand–migrate–contract*):

~~~mermaid
flowchart TD
    A["V1 đang đọc/ghi"] --> B["EXPAND: tạo bảng V2, chuẩn hóa mapping/key"]
    B --> C["Bật capture/dual-write cho mutation mới"]
    C --> D["BACKFILL: quét V1 có giới hạn và ghi V2"]
    D --> E["CATCH-UP: replay mutation chưa áp dụng"]
    E --> F["RECONCILE: đối soát + sửa chênh lệch"]
    F --> G["SHADOW READ: so V1/V2, giữ V1 làm nguồn chính"]
    G --> H{"Đạt tiêu chí cutover?"}
    H -->|Chưa| D
    H -->|Đạt| I["Chuyển read sang V2 theo canary"]
    I --> J["Ổn định, theo dõi, giữ rollback path"]
    J --> K["CONTRACT: dừng V1 write sau retention"]
    K --> L["Backup, phê duyệt rồi mới drop V1"]
~~~

**Không nên làm:** dừng ứng dụng, `CREATE TABLE v2`, chạy vài `INSERT` mẫu rồi `DROP TABLE v1`; cũng không coi một lần copy dữ liệu cũ là đủ khi có ghi mới diễn ra đồng thời.

### 7.1. State machine vận hành

| Giai đoạn | Đường ghi | Đường đọc | Điều kiện tiến giai đoạn |
| --- | --- | --- | --- |
| **V1_ONLY** | V1 | V1 | Baseline và mapping chuẩn. |
| **DUAL_WRITE** | V1 và V2, có retry/durable log nếu một nhánh lỗi | V1 | Dữ liệu mới không bị bỏ sót ở V2. |
| **BACKFILL** | V1 và V2 | V1 | Phần lịch sử V1 đã quét đúng scope. |
| **CATCH_UP** | V1 và V2 | V1, so V2 ngầm | Backlog mutation và độ lệch đã được xử lý. |
| **V2_CANARY** | Tiếp tục giữ V1/V2 | Một phần traffic V2, có fallback | p99/error/data correctness đạt SLO. |
| **V2_PRIMARY** | Tiếp tục giữ rollback path | V2 | Qua một khoảng ổn định được định nghĩa trước. |
| **V2_ONLY** | V2 | V2 | Chấp nhận không thể rollback về V1 bằng cách đổi feature flag đơn thuần. |
| **RETIRED** | V2 | V2 | V1 đã backup và loại bỏ theo change được duyệt. |

Thứ tự có thể biến thể tùy workload nhưng **điều kiện dữ liệu đúng và đường rollback** phải được định nghĩa trước. Dừng ghi V1 quá sớm khiến quay lại v1 không còn an toàn nếu các mutation mới chỉ có ở v2.

## 8. Giai đoạn EXPAND: tạo schema v2 và xác minh trước khi copy

Tạo bảng mới **không làm phát sinh dữ liệu lịch sử**. `CREATE TABLE IF NOT EXISTS` cũng không đảm bảo định nghĩa hiện có đã khớp schema mong muốn nếu có người tạo bảng cùng tên khác.

Trong `cqlsh` trên lab:

~~~sql
DESCRIBE KEYSPACE telemetry_migration;
DESCRIBE TABLE telemetry_migration.events_v1;
DESCRIBE TABLE telemetry_migration.events_by_device_day_v2;
DESCRIBE TABLE telemetry_migration.events_by_device_day_type_v2;
~~~

`DESCRIBE` là lệnh của **cqlsh**, không phải CQL statement gửi nguyên văn qua Java Driver. Nên xác nhận:

1. Các cột có kiểu dữ liệu tương thích và đúng nullable/TTL semantics.
2. Partition key và clustering order của v2 khớp pattern đọc.
3. RF, snitch/DC/rack và trạng thái replica phù hợp.
4. Role ứng dụng có `MODIFY` trên v2; reader canary có `SELECT`, không vô tình cấp toàn bộ quyền.
5. Schema agreement và client prepared statements được refresh/triển khai đúng quy trình.
6. Baseline disk free, CPU/GC, compaction backlog, read/write p95/p99 được ghi lại.

**Schema agreement chỉ xác nhận metadata schema đã hội tụ theo cơ chế cluster**, không có nghĩa dữ liệu của v1 đã nằm trong v2. Ngoài ra, nhiều bảng mới sẽ làm **tổng dung lượng các replica tăng đáng kể** trong thời gian song song; phải tính cả snapshot và compaction headroom.

## 9. Mutation mới: dual-write phải xử lý thất bại một nhánh

### 9.1. Ghi sự kiện bất biến dễ hơn update tùy ý

Nếu mỗi event là **immutable**, `event_id` và `event_time` được gán một lần, rồi producer ghi lên v1 và v2:

~~~mermaid
sequenceDiagram
    participant App as Ingestion service
    participant Log as Durable mutation log
    participant V1 as Table v1
    participant V2 as Table v2
    App->>Log: Lưu event với ID bất biến
    Log-->>App: Đã bền vững
    App->>V1: Upsert với key v1
    App->>V2: Upsert với key v2
    V1-->>App: ACK hoặc lỗi
    V2-->>App: ACK hoặc lỗi
    Note over App: Nếu một nhánh lỗi: giữ mutation để retry/reconcile
~~~

**Chạy hai `INSERT` riêng không phải transaction phân tán nguyên tử giữa hai bảng.** Nếu v1 thành công nhưng v2 lỗi, muốn an toàn cần **durable retry queue, outbox/event stream, CDC hoặc reconciliation job** được thiết kế cho tình huống ấy.

### 9.2. Các lựa chọn đồng bộ mutation

| Phương án | Điểm mạnh | Giới hạn/rủi ro |
| --- | --- | --- |
| **Dual-write trực tiếp trong service** | Dễ hiểu, kiểm soát mapping và metric riêng cho v1/v2. | Không atomic giữa bảng; request timeout có kết quả chưa rõ; phải có retry bền vững. |
| **Durable event stream / outbox** | Có log mutation với ID/offset để replay, kiểm soát lag và khôi phục. | Cần vận hành stream, định nghĩa thứ tự theo key và idempotency. |
| **Cassandra CDC theo phiên bản** | Có thể lấy mutation từ đường ghi Cassandra để xây projection. | Phụ thuộc phiên bản/hệ thống consumer, retention và khả năng bắt kịp; không mặc nhiên là pipeline exactly-once. |
| **Tạm dừng ghi có bảo trì** | Làm điểm cắt rõ hơn cho hệ thống nhỏ, giảm cạnh tranh trong lúc copy. | Downtime có thể không chấp nhận; vẫn phải kiểm tra dữ liệu/rollback. |
| **Logged batch hai bảng** | Có thể cung cấp atomicity theo semantics batch của Cassandra trong tình huống phù hợp. | Không phải transaction có isolation/snapshot, và multi-partition batch gây overhead lớn; không dùng như giải pháp mặc định để migrate. |

Nếu hệ thống đã có **event source bền vững** (message log hay nguồn dữ liệu chuẩn khác), đôi khi xây v2 bằng **replay có checkpoint** đáng tin hơn đọc lại v1. Nhưng phải hiểu thứ tự mutation, retention, delete và khả năng tái dựng đầy đủ state.

### 9.3. Quy tắc idempotency

~~~text
event_id = ID ổn định qua mọi retry
event_time = thời điểm sự kiện bất biến và được chuẩn hóa UTC
event_day = UTC_DATE(event_time)

v1 key = (device_id, event_time, event_id)
v2 key = (device_id, event_day, event_time, event_id)
~~~

Ghi lại **cùng một event bất biến** với cùng khóa giúp giảm rủi ro tạo hàng trùng trong migration. Tuy nhiên, từ “idempotent” chỉ đúng khi semantics của payload/timestamp/TTL và các mutation cạnh tranh cũng được định nghĩa rõ. Ghi lặp với TTL mới có thể **gia hạn thời gian sống**, và backfill bằng timestamp mới có thể ghi đè bản cập nhật trẻ hơn trên cùng cell.

## 10. Giai đoạn BACKFILL: quét v1 theo partition và ghi v2

### 10.1. Chọn nguồn đọc và đơn vị checkpoint

Với schema v1 `PRIMARY KEY ((device_id), event_time, event_id)`, muốn đọc hiệu quả phải biết `device_id`. Nếu hệ thống có **device registry/catalog authoritative**, có thể lấy danh sách ID từ đó và backfill theo từng thiết bị + khoảng thời gian.

~~~sql
-- Một đoạn thời gian của một partition V1:
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

**Không giả định có thể dùng `SELECT DISTINCT device_id FROM ...` trên bảng cực lớn như một danh bạ miễn phí** hoặc thêm `ALLOW FILTERING` để quét cluster trên production. Nếu không có catalog, cần một kế hoạch full scan **theo token range** với công cụ/export framework hỗ trợ đúng phiên bản và khả năng chia nhỏ công việc; đo áp lực đọc, network, tombstone và replica.

Đơn vị checkpoint nên phản ánh **phần dữ liệu đã đọc và đã ghi thành công**, ví dụ:

~~~text
job_id              = migration-2026-11-21
source_table        = telemetry_migration.events_v1
target_table        = telemetry_migration.events_by_device_day_v2
device_id           = device-7
window_start_utc    = 2026-11-20T00:00:00Z
window_end_utc      = 2026-11-21T00:00:00Z
last_verified_key   = (event_time, event_id)
source_rows_seen    = 5000
target_writes_ok    = 5000
checkpoint_state    = VERIFIED
~~~

Checkpoint này là **mẫu metadata của migration system**, không phải bảng Cassandra tự tạo. Một checkpoint chỉ được đánh dấu xong khi các target writes cần thiết đã **nhận ACK theo CL** và lỗi đã được retry/đưa vào hàng đợi xử lý. Với update/delete hoặc replica lệch, cần kiểm chứng bổ sung; ACK không chứng minh mọi replica đều giống nhau.

### 10.2. Những nguyên tắc backfill phải giữ

1. **Chia nhỏ công việc:** theo `device_id`, khoảng UTC và/hoặc token range; không nạp một partition nhiều năm vào bộ nhớ một lần.
2. **Đọc có paging:** fetch size hữu hạn, đo số row/byte/s và response latency.
3. **Ghi có bounded concurrency/rate:** không tạo vô số asynchronous requests; limit theo năng lực replica.
4. **Giữ định danh:** không sinh `event_id` mới khi copy; chuyển cùng `event_time`.
5. **Ghi vào mọi projection được yêu cầu:** nếu v2 có cả bảng theo ngày và theo loại, mỗi event hợp lệ cần được xử lý tương ứng.
6. **Theo dõi lỗi chưa xác định:** timeout là **trạng thái có thể đã ghi một phần**; retry phải an toàn.
7. **Tránh cạnh tranh với repair/compaction/streaming:** lên lịch khi disk headroom, CPU và network cho phép.
8. **Có thể tạm dừng/tiếp tục:** checkpoint độc lập và trạng thái từng window, không dựa vào “tiến trình có còn sống”.

### 10.3. Đặc điểm quan trọng của paging

CQL result paging giúp không tải toàn bộ kết quả một lúc, nhưng **không tạo snapshot isolation của dữ liệu v1** trong quá trình scan. Mutation xảy ra giữa các page có thể làm kết quả khác so với thời điểm scan bắt đầu.

Không coi **paging state** là con trỏ lưu trữ lâu dài hợp lệ qua mọi lần restart/version/schema. Muốn resume chắc chắn cần hợp đồng checkpoint riêng, ví dụ các window cố định, khóa clustering cuối đã xác minh và logic chống duplicate/gap. Khi sử dụng descending clustering với `event_time, event_id`, điều kiện resume phải xét **cả hai cột**; chỉ lưu `event_time` có thể bỏ sót các hàng cùng timestamp.

## 11. Java Driver 4.x: ví dụ backfill một thiết bị trong một ngày

Ví dụ sau dành cho **lab có dữ liệu sự kiện bất biến, không có TTL/update/delete cạnh tranh**. Nó đọc các hàng của `device-7` trong một khoảng UTC từ v1 và ghi vào bảng ngày v2. **Không** dùng đoạn code này làm migration production nếu chưa bổ sung durable checkpoints, throttling, retry, validation và cơ chế xử lý mutation đồng thời.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

public final class BackfillEventsV1ToV2 {
    public static void main(String[] args) {
        String deviceId = "device-7";
        Instant from = Instant.parse("2026-11-20T00:00:00Z");
        Instant until = Instant.parse("2026-11-21T00:00:00Z");

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement source = session.prepare(
                "SELECT event_time, event_id, event_type, payload " +
                "FROM telemetry_migration.events_v1 " +
                "WHERE device_id = ? AND event_time >= ? AND event_time < ?");

            PreparedStatement target = session.prepare(
                "INSERT INTO telemetry_migration.events_by_device_day_v2 " +
                "(device_id, event_day, event_time, event_id, event_type, payload) " +
                "VALUES (?, ?, ?, ?, ?, ?)");

            BoundStatement scan = source.bind(deviceId, from, until)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setPageSize(200);

            long copied = 0;
            for (Row row : session.execute(scan)) {
                Instant eventTime = row.getInstant("event_time");
                UUID eventId = row.getUuid("event_id");
                LocalDate day = eventTime.atZone(ZoneOffset.UTC).toLocalDate();

                BoundStatement upsert = target.bind(
                    deviceId,
                    day,
                    eventTime,
                    eventId,
                    row.getString("event_type"),
                    row.getString("payload"))
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

                // Đồng bộ và tuần tự chỉ để ví dụ dễ đọc; production cần
                // bounded concurrency, kiểm soát lỗi/retry và checkpoint bền.
                session.execute(upsert);
                copied++;
            }
            System.out.println("source_device=" + deviceId
                + " from=" + from + " until=" + until
                + " target_writes_acknowledged=" + copied);
        }
    }
}
~~~

### 11.1. Những gì code thực hiện đúng

- `PreparedStatement` tránh ghép literal dữ liệu vào CQL, giúp quản lý kiểu `Instant`, `LocalDate`, `UUID`.
- `event_day` được tính **từ thời điểm UTC của sự kiện**, không phải từ giờ chạy job.
- Truy vấn nguồn có `device_id` và giới hạn clustering range; không cần `ALLOW FILTERING`.
- `setPageSize(200)` giúp lấy dữ liệu theo page, tránh mặc định nạp toàn bộ tập kết quả vào một collection.
- Ghi bằng **primary key v2 ổn định** cho event, không tạo ID ngẫu nhiên khi backfill.
- `LOCAL_QUORUM` trong lab RF = 3 yêu cầu **hai phản hồi replica tại dc1** cho từng read/write, nhưng không thay thế repair.

### 11.2. Những gì code **chưa** giải quyết

| Hạn chế | Vì sao quan trọng trong production? |
| --- | --- |
| Chạy tuần tự, không có rate/throughput budget | Có thể quá chậm trên dataset lớn; tăng concurrency mù lại có thể làm cluster quá tải. |
| Không có durable checkpoint | Nếu process chết, khó biết window đã verified và phần nào phải làm lại. |
| Không xử lý delete/update cùng lúc | V2 có thể chứa hàng đã xóa ở v1 hoặc ghi đè bản mới hơn. |
| Không giữ TTL/writetime gốc | Độ sống của dữ liệu có thể thay đổi; `INSERT` mới không tự mang TTL cũ. |
| Không xử lý error DLQ/replay | Một write thất bại có thể làm job dừng, còn write timeout có trạng thái chưa rõ. |
| Không so dữ liệu v1/v2 | `copied = N` chỉ đếm ACK của job, không chứng minh không thiếu/khác hàng. |
| Không viết bảng v2 theo loại | Nếu hệ thống cần projection thứ hai, phải triển khai mapping/ghi riêng. |
| Không có cutover/rollback | Copy thành công một window chưa đủ để đổi toàn bộ application reads. |

**Một sự kiện immutable đã copy có thể được ghi lại cùng key** nếu job retry, nhưng nếu payload được update hoặc TTL đang chạy thì vẫn cần chính sách conflict/expiry rõ ràng.

## 12. Phần khó nhất: update, delete và TTL trong lúc migration

### 12.1. Backfill có thể làm “hồi sinh” dữ liệu đã xóa

Giả sử:

1. Lúc 10:00, backfill đọc event E từ v1.
2. Lúc 10:01, ứng dụng xóa E ở v1 và ghi delete tương ứng vào v2.
3. Lúc 10:02, backfill dùng `INSERT` mới vào v2 với cùng key E.

Nếu timestamp của backfill **mới hơn tombstone**, event E ở v2 có thể xuất hiện trở lại. **Không có phép kiểm tra `event_id` ổn định nào tự ngăn việc này**, vì đó là xung đột mutation và timestamp.

~~~mermaid
sequenceDiagram
    participant BF as Backfill
    participant Old as V1
    participant App as Application
    participant New as V2
    BF->>Old: Read event E (10:00)
    Old-->>BF: E hiện còn sống
    App->>Old: DELETE E (10:01)
    App->>New: DELETE E (10:01)
    Note over BF: Giữ E trong job queue
    BF->>New: INSERT E với timestamp mới hơn (10:02)
    Note over New: E có thể xuất hiện lại nếu mutation thắng tombstone
~~~

Giải pháp phải xét **nguồn sự kiện, thứ tự mutation và chính sách timestamp**:

- Với **append-only immutable events không xóa/sửa** trong migration, rủi ro giảm đáng kể.
- Nếu có update/delete, cần một **durable changelog/CDC** hoặc cơ chế reconciliation có thể tái áp dụng tất cả mutation theo semantics của nguồn.
- Nếu dùng `USING TIMESTAMP` cho backfill để giữ thứ tự, phải biết **writetime gốc của từng cell**, timestamp của delete, TTL và giới hạn Cassandra; không suy một timestamp duy nhất từ `event_time`.
- Có thể cần **tạm dừng cập nhật/xóa** trong cửa sổ cutover được duyệt hoặc dùng nguồn dữ liệu chuẩn khác để tái dựng state.

**Không đổi nguyên tắc last-write-wins bằng cách đặt `USING TIMESTAMP` bằng giá trị thời gian nghiệp vụ một cách mù quáng.** Timestamp dùng cho hòa giải mutation khác `event_time` trong bảng.

### 12.2. TTL: copy dữ liệu không tự copy thời gian hết hạn

Nếu v1 dùng `default_time_to_live` hoặc `USING TTL`, những cell đang sống có thể còn **thời gian sống ngắn**. Chép chúng bằng `INSERT` mới ở v2 (không cùng TTL semantics) có thể:

- Khiến dữ liệu sống **lâu hơn** yêu cầu retention nếu không gắn TTL.
- Hoặc nếu v2 có TTL mặc định, tính lại TTL **từ lúc backfill**, gia hạn tuổi thọ của dữ liệu đã tồn tại lâu.

Với bảng có nhiều cell, `TTL(column)` và `WRITETIME(column)` là thông tin **ở cấp cell** đối với những trường hợp được hỗ trợ, không phải một snapshot của mọi deletion/tombstone trong partition. Một hàng có thể có nhiều TTL khác nhau cho các cột.

Ví dụ cách quan sát trên hàng còn sống:

~~~sql
SELECT event_time, event_id,
       TTL(payload) AS payload_ttl_seconds,
       WRITETIME(payload) AS payload_write_time_us
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-20T00:00:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

`TTL(payload)` có thể trả `null` khi cell không có TTL. Nó **không cho bạn biết đầy đủ mọi delete đã xảy ra**, cũng không khôi phục được các tombstone đã purge. Muốn bảo toàn tuyệt đối retention, phải thiết kế chiến lược theo loại dữ liệu: nguồn event stream có `expiry_at`, TTL còn lại khi replay, hoặc migration với thời điểm đóng băng/đối soát có kiểm soát. Không tự coi `SELECT` current live rows là phương án giữ nguyên toàn bộ lịch sử mutation.

### 12.3. “Move row” không có atomicity giữa hai primary key

Nếu cùng một event cần chuyển từ `device_id=old` sang `device_id=new`, thao tác là **ghi key mới** rồi **xóa key cũ** theo quy trình. Với một số keyspace/table, hai mutations có thể thuộc **hai partitions và những replica sets khác nhau**. Một `UPDATE` đơn giản không thể sửa partition key tại chỗ; và Cassandra không cung cấp giao dịch SQL cách ly đầy đủ cho việc chuyển hàng giữa hai bảng.

**Vì vậy:** schema migration cần kế hoạch xử lý **trạng thái chuyển tiếp** và idempotency/reconciliation, không giả định một lệnh sẽ làm thay đổi cả v1/v2 nguyên tử.

## 13. CATCH-UP: dữ liệu mới, event đến muộn và watermark

Backfill chia theo ngày dựa trên `event_time` **không** tự xử lý mọi mutation mới. Một event được ghi hôm nay có thể mang `event_time` của tuần trước do thiết bị offline; nó đi vào **bucket quá khứ** mà backfill đã đánh dấu hoàn thành.

### 13.1. Watermark phải dựa trên nguồn mutation, không chỉ thời gian sự kiện

~~~text
event_time     = thời điểm sự kiện diễn ra (có thể cũ)
ingested_at    = thời điểm hệ thống nhận event
stream_offset  = vị trí mutation trong nguồn bền vững có thứ tự
backfill_range = phần dữ liệu lịch sử đã quét
~~~

Nếu dùng event stream:

1. Lấy một **offset/checkpoint bắt đầu** trước khi mở nguồn ghi v2 hoặc trước bước backfill.
2. Bật consumer cập nhật v2 và lưu **offset đã áp dụng thành công**.
3. Backfill dữ liệu cũ bằng key/semantics nhất quán.
4. **Catch-up/replay** mọi mutation phát sinh trong thời gian backfill và xử lý retry.
5. Tiến sang shadow read chỉ khi **lag nhỏ, error DLQ được xử lý và reconciliation đạt ngưỡng**.

**Đừng chỉ chọn một `event_time > cutoff` để catch-up.** Late-arriving events, backfill theo thứ tự không tuyến tính và mutation xóa/cập nhật có thể mang event_time cũ nhưng được ghi mới.

### 13.2. Thứ tự và exactly-once

Một nguồn stream có thể bảo đảm thứ tự **trong một partition của stream**, không nhất thiết trong mọi thiết bị hoặc trên mọi stream partition. Dual-write, CDC và retry thường là **at least once**; cần ánh xạ stable key, idempotent mutation và logic conflict thích hợp.

Không tuyên bố “exactly-once” chỉ vì mỗi message có ID. Với **counter, LWT, TTL cập nhật, read-modify-write** hoặc delete cạnh tranh, retry có thể làm kết quả thay đổi theo semantics. Cần lựa chọn hợp đồng dữ liệu cho từng loại mutation và kiểm chứng lại khi restore/replay.

## 14. RECONCILE: chứng minh v2 đủ dữ liệu thay vì tin số dòng đã copy

Không có một lệnh CQL chuẩn nào xác nhận “mọi hàng v1 và v2 tương đương theo logic nghiệp vụ” trên toàn cluster mà không phải đọc/so dữ liệu. Việc đối soát nên kết hợp **nhiều tầng**:

| Tầng kiểm chứng | Thực hiện | Hạn chế |
| --- | --- | --- |
| **Schema** | `DESCRIBE TABLE`, so primary key/order/TTL và quyền. | Không nói dữ liệu đủ hay không. |
| **Backfill progress** | Số window hoàn tất, rows scanned, writes ACK, retry/dead-letter. | Có thể copy trùng hoặc bỏ hàng, ACK không phải dữ liệu chuẩn hóa. |
| **Count theo scope** | Count ở device/day hoặc từ hệ tính toán độc lập. | Count giống nhau chưa chứng minh cùng nội dung; `COUNT(*)` lớn có thể rất tốn tài nguyên. |
| **So sánh tập khóa** | Lấy tập `(device_id,event_time,event_id)`, chuyển sang khóa v2 rồi so. | Cần memory/disk/scan theo window và consistency phù hợp. |
| **Fingerprint/hash có thứ tự** | Chuẩn hóa key/payload rồi tính hash cho từng window. | Cần định nghĩa serialization/TTL/null/deletes; hash chỉ là bằng chứng theo phương pháp đã thiết kế. |
| **Sample query/functional test** | Đọc time range, last N, ALARM-only từ v1/v2 và so. | Sampling không thay kiểm tra toàn dữ liệu. |
| **Health/repair** | Node health, compaction, repair theo runbook nếu replica lệch. | Repair nội bộ v2 không so logic v1 với v2. |

**Không chạy `SELECT COUNT(*)` không giới hạn trên bảng khổng lồ chỉ để xác nhận migration.** Với Cassandra, đếm thường phải đọc rất nhiều dữ liệu, dễ gây scan/cost lớn; nên dùng pipeline phân vùng, aggregate kiểm đếm ở bên ngoài hoặc thống kê có scope và rate limit.

### 14.1. Đối soát truy vấn cụ thể

Với dữ liệu immutable không TTL trong lab:

~~~sql
-- V1: cùng device, cùng khoảng thời gian.
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_v1
WHERE device_id = 'device-7'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z';

-- V2: một partition ngày.
SELECT event_time, event_id, event_type, payload
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z';
~~~

Điều cần so sánh là **bộ khóa và giá trị chuẩn hóa**, không chỉ `LIMIT` hay row count. Nếu có write diễn ra đồng thời, hai lần SELECT **không có một snapshot nguyên tử chung**. Cần đối soát tại **watermark có nghĩa**, đợi consumer catch-up và lặp lại với các window bị ảnh hưởng.

### 14.2. Chênh lệch nào đủ để chặn cutover?

Ví dụ điều kiện go/no-go cần thiết kế theo sản phẩm:

- Không còn window lịch sử nào ở trạng thái `FAILED` hoặc `UNKNOWN`.
- Retry queue và dead-letter queue không còn **mutation chưa xử lý** trong phạm vi cutover.
- Tập khóa và payload giữa nguồn chuẩn và v2 **khớp theo quy tắc đối soát đã công bố**; dữ liệu TTL/deletes có chính sách riêng.
- Cả hai DC/replica scope được kiểm chứng với CL thích hợp và repair/streaming health bình thường.
- p95/p99 latency, timeout/error rate và tài nguyên disk/GC/compaction đạt SLO trong load test/canary.

Không sử dụng một tỷ lệ khớp 99,9% như ngưỡng mặc định cho mọi nghiệp vụ: **0,1% event bị mất có thể không chấp nhận được** đối với dữ liệu tài chính hoặc sự kiện bảo mật.

## 15. SHADOW READ và CUTOVER: đổi đường đọc không tạo snapshot chung

### 15.1. Shadow read

Trong shadow mode, ứng dụng **vẫn trả kết quả v1** cho người dùng, đồng thời phát một tỷ lệ nhỏ read vào v2 để đo:

- Kết quả và thứ tự event: `event_time`, `event_id`, payload và filter theo loại.
- p50/p95/p99, số partition/bucket đọc, số page, bytes và timeouts.
- Tính nhất quán khi query cắt qua nửa đêm UTC hoặc event đến muộn.
- Độ ổn định khi node/replica bị chậm, GC pause hoặc đang compaction.

Không nên nhân đôi 100% request production ngay lập tức vì shadow read **tăng tải**. Chọn sampling/canary và giới hạn concurrency, không log dữ liệu nhạy cảm ở mức hàng.

### 15.2. Canary cutover

~~~mermaid
flowchart LR
    A["Application read router"] --> B{"Feature flag by service/tenant"}
    B -->|Phần lớn| C["Đọc V1 và trả kết quả"]
    B -->|Canary| D["Đọc V2 + merge bucket"]
    C --> E["Metrics query V1"]
    D --> F["Metrics query V2"]
    E --> G["So SLO/error/data correctness"]
    F --> G
    G --> H["Tăng canary hoặc rollback flag"]
~~~

Trong thời gian còn đường rollback, **đừng dừng ghi v1**. Nếu chuyển sang v2 nhưng mutation mới chỉ được ghi v2, một cú đảo feature flag về v1 có thể làm ứng dụng **mất nhìn thấy dữ liệu mới**.

### 15.3. Read fallback có giới hạn

Đọc v2 thất bại và chuyển về v1 có thể giúp giảm downtime, nhưng cần thận trọng:

- **Timeout không có nghĩa không có dữ liệu**; không dùng fallback vô hạn khiến hai query cùng chiếm tài nguyên.
- V1 và v2 không có snapshot đồng nhất, vì vậy fallback có thể trả giá trị khác nếu mutation vẫn đang hội tụ.
- Cần **deadline tổng**, retry budget và metric riêng `fallback_rate`.
- Khi v2 trả **rỗng**, không tự fallback v1 cho mọi request mãi mãi; có thể che lỗi migration và tăng tải gấp đôi.

## 16. ROLLBACK và CONTRACT: giữ bảng v1 bao lâu?

Rollback thành công phụ thuộc **đường ghi v1 còn được duy trì**:

| Trạng thái | Quay về v1 dễ không? | Điều kiện |
| --- | --- | --- |
| V2 canary, vẫn dual-write v1/v2 | **Có thể**, qua feature flag có kiểm soát. | V1 vẫn nhận đủ mutation và retention/tombstone hợp lệ. |
| V2 primary, vẫn dual-write | **Có thể**, nhưng cần kiểm tra data drift và lỗi một nhánh. | Reconciliation cả hai hướng theo nguồn chuẩn. |
| Đã dừng write v1, chỉ write v2 | **Không thể chỉ đổi flag**. | Phải backfill ngược/catch-up hoặc dùng event log replay; có chi phí và rủi ro. |
| V1 đã DROP và backup chưa xác minh | **Rủi ro rất cao**. | Không còn đường rollback đơn giản; restore từ nguồn độc lập nếu có. |

### 16.1. Không vội `DROP TABLE`

~~~sql
-- CẢNH BÁO: phá hủy schema/dữ liệu bảng cũ.
-- KHÔNG chạy nếu chưa có approval, backup, retention và hậu kiểm.
DROP TABLE telemetry_migration.events_v1;
~~~

Trong Cassandra, `DROP TABLE` có thể đi kèm chính sách **auto_snapshot** tùy phiên bản/cấu hình, nhưng **không được dựa vào auto-snapshot làm kế hoạch backup duy nhất**. Phải có bản sao lưu độc lập, khôi phục được và tài liệu schema/mapping cần thiết.

Trước khi contract:

1. Tất cả client/batch/analytics/automation đã chuyển sang v2.
2. Không còn write/read v1 hợp lệ theo telemetry, bao gồm consumer ít chạy như job cuối tháng.
3. Đường rollback được chính thức đóng sau **khoảng ổn định đã duyệt**.
4. Dữ liệu v2 hoàn chỉnh, repair/streaming bình thường, backup/restore đã thử.
5. Retention, quy định pháp lý và quyền xóa dữ liệu được xác minh.
6. Có change ticket, người duyệt, snapshot/backup và mốc UTC trước/sau khi xóa.

**Không xóa thủ công SSTable của v1** để giải phóng dung lượng. Quản lý vòng đời bảng/file phải đi qua CQL/operations có kiểm soát và được xác minh sau đó.

## 17. Quan sát tài nguyên và độ trễ trong quá trình migration

Giai đoạn tồn tại v1 + v2 cùng lúc có thể **gần như nhân đôi đường ghi logic** (hoặc hơn nếu có nhiều projection), nhưng dung lượng/IO thực tế còn phụ thuộc compression, RF, backfill, compaction và snapshots. Những tác dụng phụ cần nhìn cùng lúc:

| Chỉ số | Rủi ro khi migration | Hành động |
| --- | --- | --- |
| **Disk free theo node/volume** | Hai bảng cùng tồn tại, snapshots giữ SSTable cũ, compaction cần output tạm. | Đặt headroom, giảm rate/đổi lịch nếu gần ngưỡng. |
| **Write latency/timeouts** | Dual-write + backfill tăng request và replica I/O. | Bounded concurrency, per-DC rate limit, tách traffic. |
| **Read p95/p99** | Backfill scans tranh tài nguyên với request thật; v2 fan-out nhiều bucket. | Throttle, shadow-sample, kiểm tra query shape. |
| **Compaction backlog/SSTable count** | V2 tạo thêm SSTable, các bảng v1/v2 đều được compaction. | Theo dõi `compactionstats`, strategy và disk I/O. |
| **Heap/GC, thread pools** | Paging quá lớn, queue tăng, deserialize payload nhiều. | Page size phù hợp, giới hạn in-flight và batch. |
| **Hints/repair/replica health** | Một replica bỏ lỡ mutation hoặc remote DC lag. | Theo dõi handoff, repair và scope từng DC. |
| **Migration queue/DLQ** | Một nhánh dual-write lỗi mà không được retry. | Alert backlog/oldest mutation age, dừng cutover nếu thiếu. |
| **Data drift** | Mapping UTC sai, TTL khác, update/delete race. | Reconciliation theo window và điều tra mismatch classes. |

### 17.1. Bộ lệnh quan sát lab

~~~bash
nodetool status
nodetool info
nodetool tablestats telemetry_migration.events_v1
nodetool tablestats telemetry_migration.events_by_device_day_v2
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool gcstats
~~~

`nodetool` đầu ra và tham số chi tiết thay đổi theo phiên bản. **`tablestats` cho thấy số liệu của bảng, không phải phép so dữ liệu logic v1/v2**. Chạy lệnh theo quyền vận hành, không nhúng user/password admin trong script công khai.

### 17.2. Bổ sung tracing có chọn lọc

Trong `cqlsh` lab:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_migration.events_by_device_day_v2
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

Tracing có thể hỗ trợ kiểm tra coordinator/replica và hoạt động xử lý của **một truy vấn**, không phải bằng chứng thống kê toàn bộ SLO. Bật tracing 100% traffic khi đang backfill sẽ tạo thêm tải, không phải phép đo trung lập.

## 18. Một cuộc migration giả lập: từ lỗi bề ngoài tới nguyên nhân

**Bối cảnh:** nhóm đã triển khai dual-write cho v1/v2 lúc 10:00 UTC, sau đó backfill các ngày cũ. Đến 14:00, số lượng rows v2 thấp hơn v1 khoảng 0,2% ở một số window. Nhóm muốn tăng read timeout và tiếp tục cutover.

| Sự kiện | Bằng chứng | Cách diễn giải |
| --- | --- | --- |
| 10:00 | Dual-write bật, write success V1 = 100%; V2 = 99,8%. | Có mutation chỉ V1 nhận ACK; cần retry bền. |
| 11:00 | Backfill hoàn tất các window theo event_time trước 10:00. | Không chứng minh event **đến muộn sau 11:00** đã vào window cũ. |
| 12:00 | V2 DLQ còn 5.000 mutation chưa replay. | Không được chuyển read toàn bộ sang v2. |
| 13:00 | Một device ghi sự kiện có `event_time` của hôm trước. | Watermark theo event_time có thể bỏ lỡ nếu window cũ đã đóng. |
| 14:00 | Snapshot/query sample cho thấy V2 thiếu event. | Không nên tăng timeout để che dữ liệu thiếu. |

**Nguyên nhân khả dĩ:** pipeline dual-write/catch-up chưa bắt kịp; event đến muộn cũng không được đưa lại vào window đã verified. Tăng timeout **không tạo hàng bị thiếu**. Cần:

1. Dừng tiến trình cutover, giữ read V1.
2. Xử lý DLQ/retry với idempotency đúng, xác nhận offsets theo nguồn mutation.
3. Quét lại những window có late writes và so tập khóa.
4. Kiểm tra v2 không bị tombstone/TTL race hoặc sai `event_day`.
5. Chỉ bật canary khi dữ liệu đạt tiêu chí và p99/storage còn an toàn.

**Nếu v2 có hàng thừa thay vì hàng thiếu**, đừng chỉ xóa theo đếm chênh lệch. Phải điều tra backfill hồi sinh delete, retry dùng event ID mới hoặc TTL bị gia hạn, vì các trường hợp ấy cần hướng sửa khác nhau.

## 19. Những phản mẫu đặc biệt nguy hiểm

| Nhận định/hành động | Vấn đề | Hướng đúng |
| --- | --- | --- |
| “Đổi `PRIMARY KEY ((device_id))` thành `((device_id, day))` qua `ALTER TABLE`.” | Cassandra không hỗ trợ đổi thành phần primary key theo cách này. | Tạo v2 và di chuyển dữ liệu. |
| “Đổi clustering order chỉ cần `ALTER TABLE ... RENAME`.” | Rename không đổi bố cục và thứ tự clustering. | Tạo bảng/projection có primary key mới. |
| “Chạy `CREATE TABLE v2` xong là dữ liệu đã sang.” | Metadata schema khác dữ liệu vật lý. | Backfill, catch-up, reconcile. |
| “Dual-write đã có hai câu `INSERT` thì chắc chắn atomic.” | Một nhánh có thể fail/timeout. | Durable log/CDC/outbox + retry và giám sát. |
| “Backfill xong các ngày trước hôm nay là đủ.” | Late events có event_time cũ. | Watermark theo mutation source, catch-up/replay. |
| “Retry với event ID mới để chắc không đụng dữ liệu cũ.” | Tạo duplicate logic và khó đối soát. | Stable event ID và conflict policy. |
| “Backfill bằng timestamp hiện tại luôn an toàn.” | Có thể ghi đè update/delete mới hơn. | Thiết kế ordering/writetime và reconciliation. |
| “Copy không có TTL cũng giữ được retention.” | Có thể gia hạn tồn tại dữ liệu. | Preserve expiry/TTL semantics theo thiết kế. |
| “`COUNT(*)` giống nhau chứng minh dữ liệu giống.” | Có thể thiếu và thừa những key khác nhau. | So key/value theo scope và fingerprint. |
| “`LOCAL_QUORUM` cho hai SELECT là snapshot chung.” | Hai bảng/partition không có atomic snapshot. | Reconcile tại watermark và nguồn mutation bền. |
| “Canary v2 rồi dừng ghi v1 là vẫn rollback bằng flag.” | V1 mất mutation phát sinh sau thời điểm dừng. | Giữ dual-write đến hết rollback window. |
| “Thêm nhiều bucket luôn nhanh hơn.” | Đọc lịch sử có thể fan-out quá lớn. | Benchmark partition size, bucket count và SLO. |
| “`nodetool repair` của v2 tự so dữ liệu với v1.” | Repair đồng bộ replicas của phạm vi dữ liệu, không biến đổi model giữa hai bảng. | Reconciliation ứng dụng/migration riêng. |
| “Có snapshot trên node là đủ để drop v1.” | Node mất disk thì snapshot cùng máy cũng mất. | Backup độc lập và thử restore. |

## 20. Bài tập có đáp án

**Bài 1.** Bảng v1 có `PRIMARY KEY ((device_id), event_time, event_id)`. Nhóm muốn lấy `event_day` làm một phần partition key. Có thể dùng `ALTER TABLE ADD event_day date` rồi coi đã bucket hóa không?

**Đáp án:** **Không.** `ADD` tạo regular column, không đổi partition key. Phải tạo bảng v2 có `PRIMARY KEY ((device_id,event_day), ...)` và chuyển dữ liệu.

**Bài 2.** Vì sao thay partition key có thể làm dữ liệu của cùng event chuyển sang nhóm replica khác dù RF không đổi?

**Đáp án:** Token được tính từ **partition key**. Khóa `device_id` và khóa kép `(device_id,event_day)` có token khác nhau, nên natural replica placement có thể khác.

**Bài 3.** Bảng mới có clustering `(event_type, event_time, event_id)`. Query chỉ biết device/day và muốn tất cả loại event theo timestamp DESC. Có đảm bảo thứ tự thời gian toàn partition không?

**Đáp án:** **Không.** Thứ tự clustering ưu tiên `event_type` trước. Cần bảng theo `(event_time,event_id)` hoặc projection riêng cho truy vấn tổng hợp mọi loại.

**Bài 4.** Sau 2 giờ backfill, một `DELETE` trên v1/v2 đã chạy, rồi job ghi `INSERT` cũ vào v2 với timestamp mới hơn. Rủi ro gì?

**Đáp án:** **Hồi sinh hàng đã xóa** khi mutation backfill thắng tombstone theo timestamp. Cần preserve mutation ordering, CDC/replay/controlled freeze hoặc reconciliation phù hợp.

**Bài 5.** Event xảy ra hôm qua nhưng đến hệ thống lúc 14:00 hôm nay. Vì sao chỉ catch-up với điều kiện `event_time > 10:00 hôm nay` là sai?

**Đáp án:** Sự kiện đến muộn có `event_time` cũ nhưng mutation mới. Watermark cần dựa trên nguồn mutation/ingestion offset, không chỉ event time.

**Bài 6.** Hai lần `SELECT` v1/v2 đều dùng `LOCAL_QUORUM` và trả số hàng bằng nhau. Đã đủ để cutover chưa?

**Đáp án:** **Chưa.** Số lượng không khẳng định cùng khóa/giá trị; hai SELECT không có snapshot chung; còn TTL, delete, late event và DLQ. Cần reconciliation theo watermark và SLO.

**Bài 7.** Vì sao backfill 1 triệu hàng bằng `INSERT` không TTL vào v2 có thể vi phạm retention khi v1 có TTL còn 2 ngày?

**Đáp án:** V2 có thể giữ dữ liệu lâu hơn hoặc tính lại TTL từ lúc copy. Phải xác định `expiry_at`/remaining TTL và semantics của từng cell, thay vì chỉ copy giá trị sống.

**Bài 8.** Trong dual-write, v1 đã ACK nhưng v2 timeout. Có thể coi v2 chắc chắn chưa ghi không?

**Đáp án:** **Không.** Timeout có thể xảy ra sau khi một số replica v2 đã áp dụng mutation. Hệ thống cần retry an toàn, stable event identity và đối soát; không tạo ID mới.

**Bài 9.** Sau cutover read sang v2, nhóm đã dừng ghi v1 một tuần. Có thể rollback bằng cách đổi feature flag sang v1 mà không làm gì khác không?

**Đáp án:** **Không.** V1 có thể thiếu mutation một tuần; cần replay/backfill ngược từ nguồn chuẩn hoặc kế hoạch rollback dữ liệu riêng.

**Bài 10.** Vì sao không dùng `COUNT(*)` toàn bảng để xác nhận migration khi cluster đang chịu tải?

**Đáp án:** Cassandra không duy trì counter số hàng chính xác cho mọi bảng một cách miễn phí; count có thể phải quét lượng dữ liệu rất lớn. Dùng đối soát theo scope/window và kiểm soát rate/metrics.

**Bài 11.** Mỗi thiết bị nóng ghi 25 event/giây, event 500 byte/replica. Bucket một giờ có kích thước ước tính bao nhiêu?

**Đáp án:** `25 × 3600 × 500 = 45.000.000 byte ≈ 45 MB` trên một replica, trước các biến động compression/SSTable/TTL. RF là chi phí nhân bản toàn cluster, không nhân ba kích thước logic của một partition trên một replica.

**Bài 12.** Sau khi tạo bảng v2, `DESCRIBE TABLE` đúng và `nodetool status` đều `UN`. Điều gì vẫn chưa được chứng minh?

**Đáp án:** Chưa chứng minh lịch sử đã được backfill đầy đủ, mutation mới đã catch-up, data drift bằng không, TTL/delete semantics đúng hay read/write p99 đạt SLO. Cần reconciliation và canary.

## 21. Checklist quyết định trước khi DROP bảng v1

~~~text
[ ] V2 primary key đúng theo truy vấn, không dùng ALLOW FILTERING để che query sai.
[ ] Bucket(time) chuẩn UTC/zone nghiệp vụ giống nhau giữa ingestion và backfill.
[ ] Source inventory bao phủ mọi device/token range; checkpoint đầy đủ.
[ ] Mọi projection V2 cần thiết đã được populate.
[ ] Dual-write/CDC/event log xử lý retry và mutation order có bằng chứng.
[ ] Update/delete/tombstone và TTL/expiry được xác định rõ chính sách.
[ ] Late-arriving events không bị bỏ qua bởi watermark event_time.
[ ] Backfill windows VERIFIED, không còn UNKNOWN/FAILED.
[ ] DLQ và retry backlog trước cutover đã được xử lý.
[ ] Reconciliation key/value theo scope đạt tiêu chí nghiệp vụ.
[ ] Shadow reads và V2 canary đạt p95/p99, timeout và chức năng mong muốn.
[ ] Data disks/headroom, compaction, GC, hints, repair ổn định.
[ ] RF/CL và kiểm tra DC/replicas phù hợp với yêu cầu availability.
[ ] Tất cả client/jobs/exports/metrics/schema references đã chuyển sang V2.
[ ] Rollback window đã hết hoặc có phương án data recovery thay thế.
[ ] V1 còn phục vụ rollback thì chưa dừng ghi V1.
[ ] Có backup độc lập, manifest, restore test và change approval.
[ ] Hành động DROP có audit actor/UTC/target và hậu kiểm sau thực hiện.
~~~

~~~mermaid
flowchart TD
    A["Cần đổi partition/clustering key"] --> B["Thiết kế bảng V2 từ query và sizing"]
    B --> C["EXPAND: schema, role, RF/CL và capacity"]
    C --> D["Bật dual-write hoặc durable mutation capture"]
    D --> E["Backfill có paging/checkpoint/rate limit"]
    E --> F["Catch-up event mới, late event, update/delete"]
    F --> G["Reconcile keys/values/TTL và replica health"]
    G --> H{"Data correctness và SLO đạt?"}
    H -->|Không| I["Giữ V1 primary; sửa mapping/lag và đối soát lại"]
    I --> E
    H -->|Có| J["Shadow/canary read V2"]
    J --> K{"Ổn định và rollback khả dụng?"}
    K -->|Không| I
    K -->|Có| L["V2 primary, giữ V1 theo rollback window"]
    L --> M["Contract/backup/retire V1 sau phê duyệt"]
~~~

**Tổng kết:** đổi **partition key** hoặc **clustering key** của Cassandra không phải thao tác sửa tên trường; nó thay **identity, token placement, thứ tự lưu trữ và đường đọc**. Giải pháp thông thường là **tạo bảng mới theo truy vấn**, đồng bộ mutation mới, backfill dữ liệu cũ, xử lý riêng **timestamp/TTL/delete/event đến muộn**, đối soát có checkpoint và **chuyển traffic bằng canary**. Chỉ sau khi dữ liệu, tài nguyên, SLO, replica và rollback được xác minh mới loại bảng cũ. Trong migration, **schema agreement không đồng nghĩa data migration**, **timeout không đồng nghĩa không ghi**, và **lệnh thành công không thay thế hậu kiểm**.
