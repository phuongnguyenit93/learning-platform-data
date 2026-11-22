# Thay đổi compaction strategy và tải chuyển đổi phát sinh

## Mục tiêu và bối cảnh

Trong Apache Cassandra, mỗi lần ghi thường được bổ sung vào **commit log** và **memtable**; khi flush, memtable tạo một tệp **SSTable** mới. SSTable là cấu trúc lưu trữ bất biến: thay đổi hoặc xóa một hàng không sửa trực tiếp các byte trong SSTable cũ. Vì vậy, theo thời gian, một partition có thể có nhiều phiên bản của dữ liệu trong nhiều SSTable khác nhau. **Compaction** đọc các SSTable đầu vào, hợp nhất nội dung và ghi SSTable đầu ra theo chính sách của một **compaction strategy**.

Thay đổi strategy là một quyết định vận hành có tác động thực tế: số lượng SSTable, mức khuếch đại đọc/ghi, dung lượng đĩa tạm, I/O nền, CPU, độ trễ của ứng dụng và khả năng dọn tombstone đều có thể thay đổi. Bản thân câu lệnh `ALTER TABLE` thường nhanh; **công việc chuyển đổi dữ liệu trên đĩa mới là phần có thể tốn nhiều tài nguyên**.

Bài học thuộc chương **SSTable và compaction** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Ta sẽ liên hệ với kiến trúc phân tán, partition key, bảng thiết kế theo truy vấn, replication, consistency level, CQL, repair và ứng dụng Java. Mục tiêu là:

- Giải thích compaction strategy quyết định **SSTable nào được hợp nhất khi nào**, và khác gì replication hoặc repair.
- Chọn giữa **STCS**, **LCS**, **TWCS** và, khi phiên bản hỗ trợ, **UCS** dựa trên kiểu ghi/đọc/TTL.
- Viết CQL để xem và đổi strategy ở cấp **bảng**, không nhầm cấu hình schema với việc chuyển dữ liệu đã hoàn tất.
- Dự đoán tải I/O, CPU, dung lượng đĩa, tombstone và latency trong giai đoạn chuyển đổi.
- Lập kế hoạch triển khai, giám sát, dừng/giảm tải và quay lui có điều kiện, kèm thực hành đo trước/sau.

## 1. Compaction hoạt động ra sao?

Hình dung một hàng được cập nhật ba lần và sau đó bị xóa:

~~~text
Lần ghi 1  -> Memtable -> SSTable A: value = "draft"
Lần ghi 2  -> Memtable -> SSTable B: value = "review"
Lần ghi 3  -> Memtable -> SSTable C: value = "published"
Lần xóa    -> Memtable -> SSTable D: tombstone

Khi đọc, Cassandra phải hòa giải phiên bản/tombstone liên quan.
Khi compaction đủ điều kiện, dữ liệu đầu vào được hợp nhất sang
SSTable mới và các SSTable cũ được bỏ sau khi đầu ra hoàn tất.
~~~

~~~mermaid
flowchart LR
    W["INSERT/UPDATE/DELETE"] --> M["Commit log + memtable"]
    M --> F["Flush"]
    F --> A["SSTable A"]
    F --> B["SSTable B"]
    F --> C["SSTable C"]
    A --> X["Compaction"]
    B --> X
    C --> X
    X --> N["SSTable đầu ra"]
    N --> Q["Đường đọc về sau"]
~~~

Trong lúc compaction, **SSTable đầu vào và đầu ra có thể cùng chiếm dung lượng đĩa**. Cassandra cần bảo đảm đầu ra được tạo và hoàn tất an toàn trước khi bỏ dữ liệu cũ. Vì vậy một bảng còn đủ chỗ để tiếp nhận ghi bình thường vẫn có thể **thiếu đĩa để compaction**. Việc thay đổi chiến lược cũng có thể thay đổi cách chọn nhóm SSTable, kéo theo nhiều lần rewrite trên cùng lượng dữ liệu.

Compaction diễn ra **cục bộ trên node** và dữ liệu replica của node đó. Nó không phải thao tác gửi dữ liệu đến mọi replica:

| Cơ chế | Nhiệm vụ chính |
| --- | --- |
| **Compaction** | Hợp nhất/viết lại SSTable trên một node, kiểm soát số tệp, tombstone và chi phí đọc/ghi theo strategy. |
| **Replication** | Phân phối bản sao theo replication factor, token và datacenter. |
| **Repair** | So sánh/đồng bộ dữ liệu giữa replica; có thể tạo tải ghi/streaming và ảnh hưởng compaction. |
| **Flush** | Ghi nội dung memtable thành SSTable mới; không thay thế quá trình hợp nhất các SSTable đã có. |
| **Backup/snapshot** | Lưu các thành phần để phục hồi; snapshot liên quan đến SSTable và có thể giữ lại tệp, ảnh hưởng dung lượng thu hồi. |

Thay đổi compaction strategy **không thay partition key, replication factor, dữ liệu CQL hay consistency level của client**. Nhưng nó tác động đến hiệu năng đọc/ghi của chính các truy vấn đang dùng những thành phần đó.

## 2. So sánh các strategy thường gặp

| Strategy | Nguyên tắc chọn SSTable | Phù hợp khi | Đánh đổi cần theo dõi |
| --- | --- | --- | --- |
| **SizeTieredCompactionStrategy (STCS)** | Gộp các SSTable có kích thước tương đương thành nhóm | Ghi nhiều, ít đọc ngẫu nhiên, dữ liệu không có mô hình TTL theo thời gian rõ ràng | Có thể tích lũy nhiều SSTable chồng lắp, làm tăng read amplification và cần dung lượng tạm khi gộp lớn |
| **LeveledCompactionStrategy (LCS)** | Tổ chức SSTable theo các level, giới hạn sự chồng lắp ở các level cao hơn | Đọc ngẫu nhiên/đọc điểm thường xuyên, cần kiểm soát số SSTable phải xét | Có thể rewrite nhiều dữ liệu hơn, tăng write amplification, I/O và CPU |
| **TimeWindowCompactionStrategy (TWCS)** | Gộp SSTable theo cửa sổ thời gian gắn với **timestamp của dữ liệu ghi/SSTable** | Time-series phần lớn ghi nối tiếp, TTL tương đối đồng đều, ít cập nhật dữ liệu cũ | Dữ liệu đến muộn/ghi đè/xóa cũ có thể tạo chồng lắp, trì hoãn dọn hết dữ liệu hết hạn |
| **UnifiedCompactionStrategy (UCS)** | Cơ chế thống nhất có tham số điều chỉnh đánh đổi read/write/space amplification | Workload đa dạng trên bản Cassandra **có hỗ trợ UCS** | Cần hiểu phiên bản, tham số và số liệu thực tế trước khi dùng, nhất là khi chuyển từ strategy cũ |

**Kiểm tra phiên bản:** STCS, LCS và TWCS đã tồn tại trên nhiều phiên bản Cassandra; **UCS được giới thiệu trong Apache Cassandra 5.0**. Không sao chép cấu hình UCS vào Cassandra 4.x hoặc hệ phân phối không hỗ trợ. Giá trị mặc định, thông số và khuyến nghị cụ thể có thể thay đổi theo phiên bản.

### Chọn strategy từ đặc điểm truy vấn, không từ tên gọi

1. **Ghi liên tục nhưng ít đọc từng khóa:** STCS có thể giảm chi phí rewrite so với LCS; cần xem số SSTable tích lũy và latency đọc.
2. **Đọc điểm hoặc đọc phạm vi nhỏ thường xuyên:** LCS có thể giảm số SSTable chồng lắp, nhưng đổi lại sử dụng tài nguyên nền nhiều hơn khi ghi.
3. **Sự kiện theo ngày, TTL 7–30 ngày, hiếm cập nhật lại:** TWCS đáng cân nhắc nếu thời điểm ghi, window và thời hạn lưu phù hợp.
4. **Tải trộn, Cassandra 5.0+:** xem xét UCS và đo trên workload thực tế; đừng giả định luôn tốt hơn mọi strategy ở mọi trường hợp.

**Chú ý với TWCS:** cửa sổ compaction dựa trên timestamp gắn với SSTable/mutation, **không phải** cột `event_time` bất kỳ do ứng dụng khai báo. Việc một hàng có `day = '2026-11-01'` không có nghĩa nó được xếp vào cửa sổ ngày đó nếu ứng dụng ghi hàng này vào ngày 21/11 bằng timestamp ghi hiện tại. Backfill, cập nhật cũ, xóa rải rác hoặc ghi với timestamp do client tự đặt có thể khiến các SSTable chồng lắp các kỳ và cản trở việc thu hồi dữ liệu hết TTL.

## 3. Hai dạng khuếch đại và bài toán dung lượng tạm

### 3.1. Read amplification

Một truy vấn theo **partition key** và clustering range được lợi từ việc biết vị trí dữ liệu, nhưng khi cùng partition hiện diện trong nhiều SSTable, Cassandra vẫn có thể phải kiểm tra nhiều nơi, kể cả bloom filter/index và tombstone. Đổi sang LCS đôi khi giúp giảm SSTable chồng lắp cho read path; đổi sang STCS có thể tăng số tệp cần xét tùy workload.

Nếu truy vấn thiếu partition key và buộc quét rộng, đổi strategy **không tự chữa được thiết kế bảng**. Ưu tiên truy vấn có phạm vi rõ ràng, sau đó mới đo tác động của compaction.

### 3.2. Write amplification

Một mutation ban đầu được ghi vào memtable/SSTable, nhưng các byte của nó có thể được **viết lại nhiều lần** trong compaction. LCS thường đòi thêm rewrite để duy trì các level; TWCS có thể ít rewrite hơn sau khi một window đóng và dữ liệu không còn thay đổi. Write amplification ảnh hưởng băng thông đĩa, tuổi thọ thiết bị, CPU và khả năng ghi mới khi job nền tranh I/O.

### 3.3. Space amplification và chuyển đổi strategy

Giả sử một node đang giữ **600 GiB** dữ liệu Cassandra, trong đó bảng cần đổi strategy chiếm **240 GiB**. Dung lượng có thể tăng tạm trong lúc tạo SSTable mới; mức tăng phụ thuộc nhóm SSTable được chọn, concurrency, snapshot, dữ liệu hết hạn và chiến lược đích. Không thể lấy một công thức cố định “cần thêm đúng 240 GiB” để bảo đảm an toàn.

Một cách đánh giá thực tế:

- Xem **free space thấp nhất của từng node**, không chỉ tổng dung lượng cả cluster.
- Đo kích thước các compaction đang chạy/đang đợi và tốc độ tạo đầu ra trên chính node đó.
- Dành khoảng dự phòng cho **ghi mới**, commit log, memtable flush, streaming/repair, snapshot và dao động hằng ngày.
- Nếu dung lượng không đủ cho việc viết đầu ra trước khi xóa tệp đầu vào, phải **giảm tốc độ hoặc dừng kế hoạch chuyển đổi**; đừng thử dùng `nodetool compact` để “giải phóng chỗ” khi không còn chỗ ghi đầu ra.

Không nhầm **dung lượng bảng** với số byte sẽ phải viết lại trong quá trình chuyển đổi: cùng dữ liệu có thể trải qua nhiều lần compaction. Dữ liệu đã ghi theo strategy cũ **không nhất thiết được sắp xếp lại tức thì** sau khi `ALTER TABLE`.

## 4. Chuẩn bị bảng và đo baseline

Lab sau dành cho môi trường Cassandra có một keyspace thử nghiệm; không thay đổi strategy trên bảng sản xuất khi chưa có baseline và kế hoạch giám sát.

~~~sql
-- Thay datacenter1 bằng tên datacenter thực tế.
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id text,
    device_id uuid,
    day date,
    event_time timestamp,
    event_id timeuuid,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC)
  AND default_time_to_live = 604800
  AND compaction = {
      'class': 'SizeTieredCompactionStrategy'
  };
~~~

Ở đây:

- `(tenant_id, device_id, day)` là **partition key**; cùng thiết bị/ngày thường được đọc trong một phạm vi nhỏ.
- `event_time` và `event_id` là clustering columns; giúp lấy một khoảng thời gian đã biết.
- `default_time_to_live = 604800` tức TTL mặc định **7 ngày** cho các giá trị thông thường; cần bảo đảm yêu cầu lưu trữ có chấp nhận TTL này.
- Bảng khởi đầu với STCS để có đường chuyển đổi sang TWCS minh họa.
- Câu `IF NOT EXISTS` **không chỉnh schema của bảng đã tồn tại**. Nếu chạy lại lab, cần kiểm tra schema hiện có trước khi so sánh.

Ghi mẫu:

~~~sql
INSERT INTO telemetry.events_by_device_day
    (tenant_id, device_id, day, event_time, event_id, payload)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:30:00Z',
    now(), 'sensor=21.5'
);

SELECT event_time, event_id, payload, TTL(payload)
FROM telemetry.events_by_device_day
WHERE tenant_id = 'tenant-a'
  AND device_id = 11111111-1111-4111-8111-111111111111
  AND day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z';
~~~

**Dữ liệu ít như một hàng sẽ không đủ để quan sát quá trình compaction.** Để thực hành hiệu năng, cần tạo tải thực nghiệm có nhiều flush/SSTable và chu kỳ ghi/TTL tương tự sản xuất, nhưng giữ trong lab được phép và không bơm lượng dữ liệu quá khả năng đĩa.

### Thu thập baseline

~~~bash
# Chạy trên từng node đang giữ dữ liệu của bảng.
nodetool status
nodetool tablestats telemetry.events_by_device_day
nodetool compactionstats
nodetool getcompactionthroughput
~~~

Đọc cấu hình strategy từ metadata schema qua CQL:

~~~sql
SELECT keyspace_name, table_name, compaction, default_time_to_live
FROM system_schema.tables
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Lưu baseline trong biên bản riêng: số SSTable sống, dung lượng bảng, bytes đọc/ghi, p95/p99 latency, compaction đang chạy/đợi, dung lượng trống từng node, read/write timeout và tốc độ ingest. Một số phiên bản `nodetool` hiển thị tên chỉ số hoặc đơn vị khác nhau; hãy ghi rõ phiên bản khi đối chiếu.

## 5. Thay đổi compaction strategy bằng CQL

### 5.1. Ví dụ STCS → TWCS cho dữ liệu sự kiện theo thời gian

Chỉ tiến hành nếu dữ liệu **chủ yếu append**, TTL gần đồng nhất, có ít cập nhật/xóa cũ và cửa sổ compaction phù hợp nhịp ingest:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
~~~

Thay đổi này là **schema change** được truyền trong cluster. Nó cấu hình việc chọn và xử lý compaction **từ thời điểm áp dụng trở đi**; không có nghĩa toàn bộ SSTable cũ đã được viết lại theo cửa sổ một ngày ngay khi CQL trả về. SSTable đã tạo từ strategy trước có thể khiến giai đoạn chuyển đổi mất thời gian và tạo việc nền; tốc độ thực tế phụ thuộc số file, cách phân bố timestamp và tải hiện có.

Nếu schema thay đổi chưa hội tụ trên các node, đừng suy luận mọi node đã dùng strategy mới chỉ vì một `ALTER TABLE` thành công ở coordinator. Kiểm tra schema agreement theo công cụ quản lý/driver và trạng thái các node.

### 5.2. Ví dụ STCS → LCS cho truy vấn đọc điểm thường xuyên

Một bảng phục vụ nhiều truy vấn chính xác theo partition key với SLA độ trễ chặt có thể cân nhắc:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'LeveledCompactionStrategy'
};
~~~

Trong chiến lược này, quá trình sắp xếp dữ liệu theo level có thể **ghi lại lượng dữ liệu đáng kể**, nhất là khi bảng lớn và ghi tiếp tục. Cần đo write amplification, compaction backlog và độ trễ đọc; không mặc định LCS tốt hơn TWCS chỉ vì nó giảm SSTable chồng lắp trong một loại truy vấn.

### 5.3. Ví dụ dùng UCS khi server hỗ trợ

Trên cluster Apache Cassandra **5.0+** có UCS khả dụng:

~~~sql
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'UnifiedCompactionStrategy'
};
~~~

Ví dụ chỉ minh họa việc chọn **class**. Các tham số như `scaling_parameters` và cấu hình khác của UCS cần dựa vào tài liệu phiên bản và benchmark; không tự áp dụng một giá trị tham số chung cho mọi workload. Nếu server chưa hỗ trợ, câu lệnh có thể bị từ chối: đó là vấn đề tương thích phiên bản, không phải lỗi dữ liệu.

**Quy tắc cấu hình:** mỗi câu `ALTER TABLE ... WITH compaction = {...}` thiết lập bản đồ tùy chọn compaction của bảng. Khi đổi strategy, cần khai báo đầy đủ các tùy chọn muốn giữ của strategy mới; đừng giả định các khóa tùy chọn của strategy cũ được chuyển đổi có ý nghĩa tương đương.

### 5.4. Xác minh sau ALTER

~~~sql
SELECT table_name, compaction
FROM system_schema.tables
WHERE keyspace_name = 'telemetry'
  AND table_name = 'events_by_device_day';
~~~

Tiếp tục đo `nodetool compactionstats`, `nodetool tablestats` và metrics từng node. **Đọc thấy tên strategy mới chỉ xác nhận cấu hình schema**, không phải toàn bộ SSTable đã hoàn tất chuyển đổi. Sự kiện migration có thể diễn ra nền trong lúc ứng dụng vẫn đọc/ghi.

## 6. Tải chuyển đổi phát sinh và biểu hiện thường thấy

| Nguồn tải | Vì sao tăng sau khi đổi strategy? | Biểu hiện cần theo dõi |
| --- | --- | --- |
| **Disk write I/O** | Compaction tạo SSTable đầu ra và có thể rewrite dữ liệu cũ nhiều lần | Throughput ghi đĩa, disk utilization, pending compactions |
| **Disk read I/O** | Đọc lại nhiều SSTable đầu vào | Thời gian đọc, cạnh tranh với query, disk queue |
| **CPU** | Giải nén/nén, merge và dựng lại cấu trúc lưu trữ | CPU cao, query latency tăng |
| **Dung lượng đĩa** | Đầu vào vẫn tồn tại trong lúc viết đầu ra, snapshot có thể giữ tệp | Free disk giảm, lưu lượng flush thất bại nếu quá thiếu chỗ |
| **Độ trễ ứng dụng** | Đọc/ghi cạnh tranh tài nguyên với compaction | p95/p99 tăng, timeout, dropped messages |
| **Bộ nhớ/cache** | Nhiều tệp/chỉ mục và I/O có thể thay đổi hiệu quả cache | Cache hit rate và read latency dao động |
| **Tombstone** | Dọn tombstone phụ thuộc `gc_grace_seconds`, overlap, TTL và điều kiện an toàn | SSTable count và không gian thu hồi không giảm ngay |
| **Repair/streaming** | Công việc bảo trì khác cũng tạo I/O/SSTable, tranh tài nguyên | Thời gian repair/streaming dài hơn, compaction backlog |

**Tải trên mạng** chủ yếu đến từ replication, streaming, repair và traffic client; compaction thông thường là công việc **nội bộ node**, vì vậy không nên nói mỗi lần compaction đều sao chép SSTable qua mạng. Tác động lên mạng có thể **gián tiếp** nếu query/streaming bị chậm hoặc cụm đang làm nhiều công việc song song.

### Tombstone không biến mất ngay sau khi đổi strategy

Một cột xóa hoặc hết TTL có thể để lại tombstone. Cassandra chỉ được dọn tombstone khi đáp ứng điều kiện an toàn, bao gồm thời gian ân hạn `gc_grace_seconds` và quan hệ với dữ liệu cũ trong các SSTable có thể chồng lắp, tùy strategy và loại dữ liệu. Không nên giảm `gc_grace_seconds` tùy tiện để “làm sạch nhanh”, vì replica bỏ lỡ thao tác xóa có thể làm dữ liệu cũ xuất hiện lại nếu quá hạn an toàn trước khi đồng bộ/repair.

TWCS có thể thu hồi nguyên SSTable đã hết hạn hiệu quả **khi dữ liệu cùng cửa sổ có vòng đời tương đồng và không có bản ghi còn sống cản trở**. Nếu thường xuyên backfill bằng timestamp muộn, cập nhật lại sự kiện cũ hoặc trộn TTL khác nhau, việc thu hồi trở nên khó dự đoán. Cần phân biệt **tốc độ xóa logic** với **tốc độ đĩa được giải phóng thực tế**.

## 7. Kế hoạch thay đổi có kiểm soát

### Trước khi thay đổi

1. **Đo workload:** tỷ lệ đọc/ghi, kiểu truy vấn theo partition, kích thước partition, số SSTable, TTL, xóa, backfill và thời điểm ingest.
2. **Xác nhận phiên bản:** tên class và options có được hỗ trợ ở tất cả node không; ghi lại schema hiện tại để có thể quay lui.
3. **Đặt tiêu chí:** ví dụ p95 đọc không tăng quá ngưỡng chấp nhận, disk free không xuống dưới mức dự phòng, số pending compactions không tăng liên tục.
4. **Lập ngân sách tài nguyên theo node:** free disk, I/O và tốc độ ghi mới; đánh giá snapshot/backup đang giữ SSTable.
5. **Chọn thời điểm:** tránh đồng thời chạy repair quy mô lớn, bootstrap/decommission/streaming hoặc backup nặng nếu không đủ tài nguyên.
6. **Chuẩn bị quan sát và phương án quay lui:** dashboard theo node/bảng, logs, truy vấn so sánh và người chịu trách nhiệm ra quyết định.

### Trong khi chuyển đổi

~~~mermaid
flowchart TD
    B["Baseline và kiểm tra đủ tài nguyên"] --> C["ALTER TABLE trong lab/canary"]
    C --> O["Theo dõi schema, compaction, p95/p99, disk"]
    O --> D{"Tài nguyên và SLA\ncòn trong giới hạn?"}
    D -->|Có| E["Quan sát đến khi ổn định,\nso sánh cùng workload"]
    D -->|Không| F["Giảm tải/điều chỉnh kế hoạch,\nđánh giá quay lui"]
    E --> G["Triển khai trên phạm vi lớn hơn\nkhi có bằng chứng"]
    F --> O
~~~

- **Canary trước:** thử với bảng hoặc môi trường tương đương có tải thực tế trước khi làm ở bảng lớn. Compaction strategy là thuộc tính **bảng**, không phải công tắc riêng của một replica, nên việc “rollout từng node” phải được hiểu là kiểm soát tải/triển khai môi trường, không phải đặt cùng bảng hai strategy khác nhau trong một cluster.
- **Giữ tốc độ ingest trong khả năng đĩa:** backlog tăng kéo dài là dấu hiệu tài nguyên compaction không theo kịp ghi. Hạn chế các job nền khác nếu có thể.
- **Quan sát nhiều thời điểm:** ngay sau ALTER, khi backlog cao nhất và sau khi ổn định; so sánh dữ liệu/tải có cùng kỳ đo.
- **Giới hạn công việc nền có chủ đích:** cấu hình throughput/concurrency tùy phiên bản và ngân sách máy. Ví dụ, lệnh `nodetool setcompactionthroughput` có thể điều chỉnh thông lượng compaction, nhưng không áp dụng một con số cố định cho mọi cluster.

### Sau khi chuyển đổi

1. Xác minh schema được các node chấp nhận.
2. Ghi lại số SSTable, bytes ghi đọc, pending compactions và dung lượng đĩa ở nhiều thời điểm.
3. Chạy cùng nhóm truy vấn CQL/Java theo partition key để so sánh độ trễ/timeout.
4. Đánh giá tốc độ thu hồi TTL/tombstone sau đủ thời gian quan sát; không kết luận ngay khi các window chưa hết hạn.
5. Theo dõi thêm một chu kỳ ingest/TTL đủ đại diện để thấy xu hướng dài hạn.

## 8. Đọc số liệu bằng nodetool và ứng dụng Java

### 8.1. Lệnh quan sát, không ép major compaction

~~~bash
nodetool status
nodetool compactionstats
nodetool tablestats telemetry.events_by_device_day
nodetool getcompactionthroughput
~~~

**Không dùng `nodetool compact` như bước bắt buộc ngay sau `ALTER TABLE`.** Major compaction có thể tạo tệp lớn, tiêu tốn CPU/I/O và dung lượng đĩa; với một số chiến lược/time-series, nó còn gây bất lợi cho việc chia cửa sổ hoặc thu hồi SSTable hết hạn. Chỉ chủ động ép compaction khi đã hiểu tác động của lệnh, phiên bản và đủ headroom.

### 8.2. Mẫu Java để đo truy vấn không quét rộng

Ví dụ Java Driver 4.x sau kiểm tra một truy vấn đọc nhỏ, sử dụng đúng partition key và khoảng clustering. Đây là **mẫu đo latency của đường đọc**, không phải phép đo trực tiếp tất cả công việc compaction:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class CompactionReadProbe {
    private final CqlSession session;
    private final PreparedStatement query;

    public CompactionReadProbe(CqlSession session) {
        this.session = session;
        this.query = session.prepare(
            "SELECT event_time, payload " +
            "FROM telemetry.events_by_device_day " +
            "WHERE tenant_id = ? AND device_id = ? AND day = ? " +
            "AND event_time >= ? AND event_time < ?");
    }

    public long measureMillis(String tenantId, UUID deviceId,
                              LocalDate day, Instant from, Instant to) {
        long started = System.nanoTime();
        int seen = 0;

        for (Row row : session.execute(
                query.bind(tenantId, deviceId, day, from, to)
                    .setPageSize(100)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))) {
            if (++seen > 1_000) {
                throw new IllegalStateException("Phạm vi đo quá lớn");
            }
            // Chạm dữ liệu thực để đo cả phần giải mã kết quả.
            row.getString("payload");
        }

        long elapsed = TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
        System.out.printf("rows=%d latency_ms=%d%n", seen, elapsed);
        return elapsed;
    }
}
~~~

Tái sử dụng `PreparedStatement` và `CqlSession`. Thu nhiều mẫu rồi tính p50/p95/p99 ở phía đo, kiểm soát tỷ lệ request, dữ liệu và trạng thái cluster; không đưa kết luận từ một phép đo duy nhất. Chọn `LOCAL_QUORUM` phù hợp RF/DC thực tế; consistency level không làm strategy tự tối ưu. Đo đồng thời read và write latency, vì một strategy có thể cải thiện đọc nhưng tăng chi phí ghi.

**Giới hạn của ví dụ:** số trang và số hàng có trần logic, nhưng driver vẫn cần fetch để lấy các hàng trước khi phát hiện vượt trần. Trong bài đo tải lớn, giới hạn khoảng thời gian/partition ngay từ dữ liệu thử và giữ bộ đo tách khỏi ứng dụng sản xuất.

## 9. Khi nào quay lui và quay lui thực sự có nghĩa gì?

Giả sử bảng đổi từ STCS sang LCS rồi backlog compaction tăng liên tục, disk free xuống gần ngưỡng cảnh báo và p99 ghi vượt SLA. Có thể cân nhắc quay về strategy trước đó:

~~~sql
-- Ví dụ quay lại STCS sau khi đã quyết định dựa trên số liệu.
ALTER TABLE telemetry.events_by_device_day
WITH compaction = {
    'class': 'SizeTieredCompactionStrategy'
};
~~~

Nhưng **quay lui schema không hoàn nguyên ngay toàn bộ SSTable**. Các file đã được ghi theo chiến lược mới vẫn tồn tại cho đến khi các quá trình compaction khác xử lý chúng; thay đổi lần nữa có thể tạo **thêm** công việc nền. Vì vậy:

- Ưu tiên **ngăn thiếu đĩa**, giảm tốc độ công việc cạnh tranh, giữ các replica khỏe và đánh giá khả năng hoàn tất trước khi tiếp tục đổi strategy.
- Nếu quyết định quay lui, ghi lại thời điểm, cấu hình cũ, trạng thái compaction và theo dõi tới khi hệ thống ổn định.
- Không xem việc rollback CQL thành công là tín hiệu đã hết rủi ro; vẫn có thể còn backlog, SSTable cũ và tác động độ trễ.
- Nếu migration kéo dài vì dữ liệu cũ rất lớn, cần kế hoạch có ngân sách I/O/disk, thay vì đổi strategy qua lại nhiều lần.

**Không tự xóa SSTable bằng tay để lấy chỗ.** SSTable thuộc đường lưu trữ của Cassandra; xóa nhầm có thể gây mất dữ liệu hoặc làm replica sai lệch. Dùng quy trình vận hành được hỗ trợ, giám sát và sao lưu phù hợp.

## 10. Bảng quyết định theo tình huống

| Hiện tượng | Câu hỏi cần điều tra | Hướng hành động |
| --- | --- | --- |
| Đọc điểm chậm, nhiều SSTable chồng lắp | Truy vấn đã có partition key chưa? STCS có nhiều tệp cần xét không? | Tối ưu truy vấn trước; thử LCS/UCS trên workload tương đương |
| Ghi cao, compaction tranh I/O | Tỷ lệ rewrite/throughput ra sao? | Đánh giá STCS/UCS, phân bổ I/O và kiểm soát concurrency |
| TTL time-series không thu hồi đĩa | Có backfill/late updates, TTL không đồng nhất, SSTable chứa dữ liệu khác window không? | Kiểm tra TWCS, cách ghi timestamp và chính sách TTL |
| Đổi strategy xong disk free giảm nhanh | Compaction nào đang tạo đầu ra lớn? Snapshot còn giữ file không? | Giảm tải, kiểm tra headroom, điều chỉnh kế hoạch/quay lui khi cần |
| Số pending compactions tăng | Ghi có vượt throughput compaction? Có repair/streaming cùng lúc? | Đo nút nghẽn và lên lịch lại công việc |
| `ALTER TABLE` thành công nhưng latency chưa cải thiện | SSTable đã được viết lại/ổn định chưa? Tải thử có tương đương? | Tiếp tục quan sát có thời hạn, so sánh nhiều chỉ số |
| Muốn dùng UCS trên cluster cũ | Server và bản phân phối có hỗ trợ UCS không? | Xác minh phiên bản trước; không ép dùng option không tồn tại |

## 11. Bài tập thực hành

**Bài 1 — Giải thích nguyên nhân.** Một bảng có cùng partition xuất hiện trong 40 SSTable, đọc điểm thường xuyên phải hòa giải nhiều tệp. Phân biệt read amplification với write amplification; dự đoán tác động khi thử LCS và các chỉ số phải đo để kiểm chứng.

**Bài 2 — Thay đổi strategy.** Tạo bảng lab ở mục 4, kiểm tra schema, chạy `ALTER TABLE` từ STCS sang TWCS trong môi trường hỗ trợ, rồi đọc lại `system_schema.tables`. Giải thích vì sao kết quả `compaction` đúng không có nghĩa SSTable cũ đã được phân chia thành các window mới.

**Bài 3 — Time-series có backfill.** Thiết bị offline 10 ngày rồi gửi lại dữ liệu cũ trong một lần ingest hôm nay. Phân tích vì sao cột `event_time` cũ không nhất thiết quyết định cửa sổ TWCS; đề xuất cách kiểm soát backfill và đánh giá hiệu quả TTL.

**Bài 4 — Ngân sách I/O.** Một node có free disk giảm trong lúc compaction đang tạo đầu ra. Lập bảng đo disk free, compaction pending, bytes read/write, p99 và throughput theo thời điểm; đưa tiêu chí cụ thể để tiếp tục, giảm tải hoặc quay lui.

**Bài 5 — Kết hợp repair và lỗi node.** Một node vừa được khôi phục, đang có repair/streaming, đồng thời bảng đổi sang LCS. Vì sao workload này có thể làm p99 tăng? Phác thảo thứ tự bảo trì để tránh tranh tài nguyên và phân biệt việc repair với compaction.

**Bài 6 — Quyết định giữa STCS/LCS/TWCS/UCS.** Cho ba bảng: (a) bảng session được cập nhật liên tục và đọc ngẫu nhiên; (b) bảng log có TTL đồng nhất 14 ngày và ít sửa; (c) bảng ghi nặng ít đọc. Chọn chiến lược *ban đầu* cho từng bảng, ghi giả định, mức phiên bản và kế hoạch benchmark để xác minh.

## Ghi nhớ

**`ALTER TABLE ... WITH compaction` chỉ đổi chính sách chọn SSTable; quá trình chuyển đổi trên đĩa có thể kéo dài và tạo tải CPU, I/O, dung lượng tạm, compaction backlog và biến động latency.** Chọn strategy theo truy vấn, mô hình ghi, TTL và phiên bản Cassandra; đo baseline ở từng node, giữ headroom, quan sát đến khi ổn định và hiểu rằng quay lui schema cũng không xóa ngay chi phí chuyển đổi. Compaction tối ưu lưu trữ cục bộ, còn replication và repair giải quyết vấn đề khác trong hệ phân tán.
