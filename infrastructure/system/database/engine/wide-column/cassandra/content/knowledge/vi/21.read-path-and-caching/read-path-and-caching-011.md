# Đọc theo khoảng/token so với truy vấn một phân vùng

## 1. Hai kiểu đọc, hai phạm vi công việc

Trong **Apache Cassandra**, hai câu CQL đều có thể trả về các hàng từ một bảng wide-column, nhưng đường đi và chi phí rất khác nhau:

- **Truy vấn một phân vùng** (*single-partition read*): biết **đầy đủ partition key** nên Cassandra tính được token của partition, tìm nhóm replica chịu trách nhiệm rồi đọc các hàng thuộc partition đó. Đây là đường đọc ưu tiên cho phần lớn API phục vụ người dùng.
- **Đọc theo khoảng token** (*token-range read / partition-range scan*): truy vấn các partition có token rơi vào một khoảng trên vòng token, thường gồm **nhiều partition** trên **nhiều nhóm replica**. Kiểu đọc này có ích cho quét dữ liệu theo lô, di chuyển dữ liệu hoặc kiểm kê, nhưng không tự động hiệu quả cho một yêu cầu người dùng.

Trong mô hình dữ liệu Cassandra, **partition key xác định nơi lưu dữ liệu**, còn **clustering columns quyết định thứ tự và phạm vi hàng bên trong một partition**. Chọn đúng kiểu đọc phụ thuộc câu hỏi của ứng dụng và thiết kế bảng theo truy vấn, không chỉ vào cú pháp `SELECT`.

**Mục tiêu bài học:** phân biệt cách định tuyến của hai kiểu truy vấn, hiểu chúng sử dụng memtable/SSTable và bộ đệm như thế nào, viết CQL `token(...)` hợp lệ, chọn consistency level, thực hành Java Driver và tránh sai lầm khi quét lượng lớn dữ liệu.

**Phạm vi:** ví dụ dùng `Murmur3Partitioner`, full replica thông thường và Apache Cassandra/CQL; chi tiết triển khai bộ đệm hay tối ưu đọc có thể khác theo phiên bản, cấu hình và workload.

## 2. Nền tảng: từ partition key đến token và replica

Xét bảng lưu các phép đo theo cảm biến và ngày:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_lab.readings_by_sensor_day (
    sensor_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    reading decimal,
    PRIMARY KEY ((sensor_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Ý nghĩa primary key:**

| Thành phần | Vai trò | Hệ quả đối với truy vấn |
| --- | --- | --- |
| `(sensor_id, event_day)` | **Partition key kép** (*composite partition key*) | Hai giá trị cùng nhau xác định **một partition** và token của partition. |
| `event_time` | Clustering column đầu tiên, sắp xếp giảm dần | Cho phép đọc hàng theo khoảng thời gian **trong partition đã biết**. |
| `event_id` | Clustering column tiếp theo | Phân biệt các hàng có cùng thời điểm đo. |
| `reading` | Regular column | Giá trị dữ liệu; không dùng để định tuyến partition nếu không thiết kế thêm đường truy vấn. |

Ví dụ `('sensor-9', '2026-11-21')` là **một** partition; `('sensor-9', '2026-11-22')` là **partition khác** dù cùng cảm biến. Cassandra tính token từ **toàn bộ hai thành phần partition key theo đúng thứ tự**; với `Murmur3Partitioner`, token thuộc miền số nguyên có dấu 64 bit.

Với replication strategy, token và topology DC/rack, Cassandra biết những **replica** giữ partition đó. RF = 3 trong `dc1` nghĩa là mục tiêu ba node replica khác nhau cho partition, nếu cluster có đủ node đáp ứng. Một node nhận request làm **coordinator** cho request đó; node này có thể là replica hoặc chỉ điều phối đọc đến replica.

~~~mermaid
flowchart TD
    PK["Partition key: (sensor-9, 2026-11-21)"] --> H["Partitioner tính một token"]
    H --> T["Token xác định vùng trên vòng"]
    T --> R["Replication strategy + topology chọn replica"]
    R --> P["Đọc một partition tại tập replica đó"]
    T --> S["Truy vấn khoảng token đi qua nhiều vùng"]
    S --> M["Nhiều partition, có thể nhiều tập replica"]
~~~

**Đừng nhầm ba loại khoảng:** khoảng **clustering key** (thời gian bên trong partition), khoảng **token** (nhiều partition phân tán), và khoảng **giá trị business** (ví dụ ngày 1–30). Chúng không tương đương nhau.

## 3. Truy vấn một phân vùng: đường đọc chính cho ứng dụng

### 3.1. CQL xác định chính xác một partition

Muốn lấy các phép đo của cảm biến `sensor-9` trong ngày 21/11:

~~~sql
SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Ở đây cả hai thành phần partition key đều dùng điều kiện bằng nhau; Cassandra có thể tính **một token** và xác định **một tập replica**. `LIMIT 50` giới hạn số hàng trả về, nhưng không thay vị trí lưu partition.

Muốn truy vấn một **khoảng thời gian trong chính partition ấy**:

~~~sql
SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

Đây là **clustering-range read trong một partition**, không phải quét khoảng token. Cassandra tận dụng thứ tự clustering key để thu hẹp các hàng cần truy cập. Việc đặt partition key kép với `event_day` là một dạng **bucketing** giúp không dồn tất cả sự kiện của cảm biến vào partition vô hạn.

### 3.2. Các bước logic của đường đọc

1. **Driver chọn coordinator.** Với prepared statement có đủ partition key, Java Driver có thể tính routing key/token để **ưu tiên replica phù hợp** trong data center cục bộ (*token-aware routing*), tùy chính sách và topology.
2. **Coordinator xác định replica và consistency level.** Ví dụ RF = 3, `LOCAL_QUORUM` cần hai phản hồi replica phù hợp trong DC cục bộ; `LOCAL_ONE` cần một.
3. **Replica truy cập dữ liệu.** Nó kiểm tra nguồn dữ liệu hiện có trong memtable và các SSTable có thể chứa partition, sử dụng những cấu trúc tra cứu/bộ đệm khi phù hợp.
4. **Coordinator đối chiếu kết quả.** Đường đọc có thể dùng phản hồi dữ liệu và digest, reconcile các phiên bản dữ liệu và thực hiện read repair nếu cần theo phiên bản/cấu hình.
5. **Trả về hàng theo yêu cầu.** Trật tự clustering áp dụng **bên trong partition**; cần quản lý paging nếu kết quả dài.

Đọc partition cụ thể thường có ít việc phải định tuyến và ít dữ liệu phải duyệt hơn so với quét nhiều partition. Tuy nhiên, **partition quá lớn** vẫn có thể khiến một single-partition read chậm hoặc quá tải; “biết partition key” không phải bảo đảm mọi truy vấn đều rẻ.

## 4. Bộ đệm và các lớp tra cứu giúp đọc partition

Cassandra chủ yếu lưu bền dữ liệu trong **SSTable bất biến**, trong khi các ghi mới có thể vẫn ở **memtable**. Khi đọc, replica phải kết hợp trạng thái logic hiện hành từ nhiều nguồn; SSTable có thể chứa phiên bản cũ, tombstone hoặc dữ liệu đã hết TTL.

| Thành phần | Tác dụng trong read path | Khi đọc một partition | Khi quét khoảng token |
| --- | --- | --- | --- |
| **Memtable** | Cung cấp dữ liệu ghi gần đây chưa flush thành SSTable. | Đối chiếu các hàng liên quan của partition. | Có thể phải đi qua nhiều partition thuộc khoảng đang đọc. |
| **Bloom filter** theo SSTable | Bộ lọc xác suất giúp loại nhanh SSTable **chắc chắn không chứa** một partition key; có thể báo dương tính giả. | Hữu ích khi kiểm tra một partition trên nhiều SSTable. | Đọc tuần tự nhiều partition không hưởng cùng lợi thế loại trừ theo một khóa cụ thể. |
| **Partition index / index summary** | Giúp tìm vị trí partition trong SSTable. | Có thể định vị nhanh partition cần đọc. | Hỗ trợ định vị/di chuyển trong khoảng, nhưng nhiều partition vẫn cần duyệt. |
| **Key cache** | Lưu metadata/vị trí tra cứu của các partition hay truy cập. | Có lợi khi lặp lại truy vấn hot partition, nếu cache phù hợp. | Tỷ lệ hit thường kém hơn nếu mỗi partition chỉ đọc một lần. |
| **Row cache** (nếu bật) | Có thể giữ dữ liệu partition/hàng theo cách phiên bản cấu hình hỗ trợ. | Hữu ích cho tập partition nhỏ đọc lặp lại. | Quét diện rộng có thể làm giảm hiệu quả cache hoặc đẩy dữ liệu hot ra ngoài. |
| **Cache cho dữ liệu/chunk nén** (tùy phiên bản) | Hạn chế một phần đọc/giải nén lặp lại. | Có ích với khối dữ liệu thường được đọc. | Ít hữu ích khi đọc rất nhiều khối chỉ một lần. |
| **Hệ điều hành / filesystem cache** | Giữ trang dữ liệu mới đọc trong bộ nhớ. | Đọc lặp lại có thể được lợi. | Quét rộng dễ gây áp lực bộ nhớ và I/O. |

**Bloom filter không lưu kết quả của câu `SELECT`**, và key cache không phải bản sao dữ liệu hoàn chỉnh của cả partition. Không nên suy luận “cache hit = không cần đọc replica” hoặc “đã bật cache thì token scan rẻ”. Một read vẫn chịu consistency level do coordinator yêu cầu.

Sơ đồ đơn giản của một **replica read**:

~~~mermaid
flowchart TD
    R["Read request tới replica"] --> M["Kiểm tra memtable"]
    R --> C{"Có thể phục vụ từ cache phù hợp?"}
    C -->|"Cache hit cho nội dung hợp lệ"| P["Nguồn dữ liệu được lấy nhanh hơn"]
    C -->|"Cache miss / cần đối chiếu"| B["SSTable: Bloom filter và partition index"]
    B --> S["Đọc dữ liệu / tombstone liên quan"]
    M --> X["Reconcile theo timestamp/tombstone/TTL"]
    P --> X
    S --> X
    X --> A["Trả dữ liệu hoặc digest cho coordinator"]
~~~

Sơ đồ mô tả ý tưởng tra cứu; Cassandra tối ưu đường đọc khác nhau tùy loại query, cấu hình cache, phiên bản và số SSTable. **Compaction** có thể giảm số SSTable cần kiểm tra nhưng không làm `COUNT(*)` hoặc quét token trở thành truy vấn chi phí hằng số. **Repair** giải quyết khác biệt giữa replica, không thay thế bộ đệm đọc.

## 5. Đọc theo khoảng token là gì?

Thay vì xác định chính xác `sensor_id` và `event_day`, ta yêu cầu Cassandra đọc **tất cả partition có token nằm trong một khoảng**. Điều này đặc biệt hữu ích cho tiến trình **scan dữ liệu theo lô**: xuất dữ liệu, backfill, đối chiếu, tái tính toán hoặc di chuyển.

Với partition key kép của bảng trên, biểu thức token phải liệt kê **đủ hai cột và đúng thứ tự**:

~~~sql
-- Khoảng token minh họa khi dùng Murmur3Partitioner.
-- Có thể trả về nhiều partition, không phải chỉ một cảm biến/ngày.
SELECT sensor_id, event_day, event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) > -4611686018427387904
  AND token(sensor_id, event_day) <= 0
LIMIT 100;
~~~

**Các điểm quan trọng của cú pháp và ngữ nghĩa:**

- `token(sensor_id, event_day)` áp dụng lên **toàn bộ partition key**. `token(sensor_id)` không thay thế được nó với schema có partition key kép.
- `>`, `>=`, `<`, `<=` so sánh **giá trị token**, không so sánh `sensor_id`, `event_day` theo thứ tự từ điển hay thời gian.
- Khoảng ví dụ là **một phần** của miền token `Murmur3Partitioner`, không có nghĩa khoảng ngày hay khoảng `sensor_id` cụ thể.
- `LIMIT 100` chỉ lấy một mẫu kết quả tối đa 100 hàng cho truy vấn này; **không thể coi đó là đã xử lý xong toàn bộ khoảng token**.
- Một partition có thể chứa nhiều hàng; quét một khoảng token sẽ trả về các hàng phù hợp từ **nhiều partition**, tùy điều kiện đọc.

### 5.1. Khoảng token khác khoảng thời gian

Một hiểu lầm phổ biến:

~~~sql
-- Ý tưởng sai: tưởng rằng so sánh token giữa hai ngày sẽ lọc ngày tháng.
-- Hai token dưới đây không tạo ra "khoảng ngày 01..30/11".
SELECT *
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) >
      token('sensor-9', '2026-11-01')
  AND token(sensor_id, event_day) <=
      token('sensor-9', '2026-11-30');
~~~

Hash token **không giữ thứ tự theo thời gian** hoặc tên cảm biến. Giữa hai giá trị token tương ứng các ngày trên có thể có partition của rất nhiều cảm biến/ngày khác. Để đọc ngày 1–30 cho một cảm biến, mô hình phù hợp hơn thường là truy vấn **các partition ngày đã biết** (hoặc bucket tháng) và hợp nhất kết quả ở ứng dụng.

Trong cùng một ngày, giới hạn `event_time >= ... AND event_time < ...` ở mục 3 mới là ví dụ **lọc khoảng theo clustering column**, nhờ biết partition key.

### 5.2. Vì sao token-range read tốn nhiều tài nguyên hơn?

Ở truy vấn một partition, coordinator biết chính xác bộ replica của partition đó. Trong truy vấn khoảng token, một khoảng có thể giao với **nhiều dải token được phân bổ và nhiều bộ replica**, khiến coordinator phải điều phối đọc từ nhiều nguồn. Replica cũng có thể đọc nhiều partition và nhiều SSTable trên khoảng đó.

~~~mermaid
flowchart LR
    C["Client yêu cầu token trong (A, B]"] --> K["Coordinator"]
    K --> R1["Range 1: replica set X"]
    K --> R2["Range 2: replica set Y"]
    K --> R3["Range 3: replica set Z"]
    R1 --> OUT["Tập hàng từ nhiều partition"]
    R2 --> OUT
    R3 --> OUT
    OUT --> C
~~~

Sơ đồ mô tả **đường đi logic**; cách phân chia subrange, merge kết quả và tối ưu hóa có thể khác theo phiên bản. Đặc biệt, token-range read **không có một partition key duy nhất** để Java Driver áp dụng token-aware routing như đối với single-partition read.

Không nên dùng token-range scan như cách thay thế mặc định cho một câu hỏi mà ứng dụng đã biết partition key.

## 6. So sánh trực tiếp hai đường đọc

| Tiêu chí | Truy vấn **một partition** | Truy vấn **khoảng token** |
| --- | --- | --- |
| Điều kiện định tuyến | Biết đầy đủ partition key; có thể giới hạn clustering columns. | Ràng buộc `token(...)` bằng biên của khoảng token. |
| Phạm vi dữ liệu | Một partition và các hàng được chọn trong đó. | Nhiều partition trong một/một số dải token. |
| Số nhóm replica liên quan | Thường một nhóm replica của partition. | Có thể nhiều nhóm replica do range trải trên vòng token. |
| Token-aware driver routing | Thường có thể chọn replica dựa trên partition key. | Không có một routing key/replica duy nhất để chọn tương tự. |
| Khả năng tận dụng cache | Thường tốt hơn với partition hot và query lặp lại. | Quét nhiều partition một lần nên cache hit thấp hơn trong nhiều workload. |
| Chi phí chính | Số hàng trong partition, tombstone, SSTable, CL, kích thước page. | Tổng số partition/hàng, nhiều SSTable/replica, network, paging và thời gian scan. |
| Trật tự dữ liệu | Clustering order **trong partition**. | Không phải sắp xếp toàn cục theo ngày/cảm biến; token order không phải business order. |
| Ứng dụng thích hợp | API truy vấn theo khách hàng, cảm biến, tài khoản, bucket thời gian. | Batch export, backfill, reindex, kiểm tra dữ liệu theo vùng token. |
| Tính nhất quán | Theo CL cho request; vẫn cần cân nhắc ghi đồng thời. | CL áp dụng cho các phần dữ liệu được đọc, **không tạo snapshot toàn bảng**. |

**Một partition có thể rất lớn.** Nếu một partition chứa hàng triệu hàng hoặc nhiều tombstone, ngay cả một query có đủ partition key cũng có thể chậm. Cần thiết kế partition key/bucket, clustering restrictions, TTL và paging tương ứng với truy vấn thực tế.

## 7. Thực hành CQL trên cùng một bảng

### 7.1. Chuẩn bị dữ liệu

Giả sử đã tạo keyspace/table ở mục 2 và cluster có ít nhất ba node trong DC tên `dc1`. Dữ liệu mẫu:

~~~sql
INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174001, 21.70);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-21', '2026-11-21T09:15:00Z',
     123e4567-e89b-42d3-a456-426614174002, 21.85);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-9', '2026-11-22', '2026-11-22T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174003, 22.10);

INSERT INTO telemetry_lab.readings_by_sensor_day
    (sensor_id, event_day, event_time, event_id, reading)
VALUES
    ('sensor-10', '2026-11-21', '2026-11-21T08:15:00Z',
     123e4567-e89b-42d3-a456-426614174004, 19.90);
~~~

Ba partition của ví dụ là:

1. `('sensor-9', '2026-11-21')` chứa **hai** hàng.
2. `('sensor-9', '2026-11-22')` chứa **một** hàng.
3. `('sensor-10', '2026-11-21')` chứa **một** hàng.

Không thể dự đoán partition nào nằm trong một khoảng token cho trước chỉ từ tên cảm biến hoặc ngày; phải tính token theo partitioner để biết.

### 7.2. Đọc một partition và quan sát trace

Trong `cqlsh`:

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE sensor_id = 'sensor-9'
  AND event_day = '2026-11-21';

TRACING OFF;
~~~

Kỳ vọng **hai hàng** trong cùng partition. Tracing có thể cho biết coordinator, các replica tham gia, thời điểm yêu cầu và một số sự kiện read path (phụ thuộc phiên bản). Với RF = 3 tại `dc1`, `LOCAL_QUORUM` yêu cầu hai phản hồi replica thích hợp trong data center cục bộ.

### 7.3. Quét một khoảng token và đối chiếu

~~~sql
CONSISTENCY LOCAL_ONE;
TRACING ON;

SELECT sensor_id, event_day, event_time, reading
FROM telemetry_lab.readings_by_sensor_day
WHERE token(sensor_id, event_day) > -4611686018427387904
  AND token(sensor_id, event_day) <= 0
LIMIT 100;

TRACING OFF;
~~~

**Không kỳ vọng kết quả cố định là bốn hàng**: chỉ những partition có token thuộc khoảng trên mới được trả về. Thực hiện với dataset lab nhỏ, quan sát các partition xuất hiện rồi so sánh trace và độ trễ với truy vấn ở mục 7.2. Trong cluster thực tế, kết quả và số request nội bộ còn phụ thuộc topology, token ownership và CL.

Để xem phân bố node/range:

~~~bash
nodetool status
nodetool ring
~~~

`nodetool ring` hiển thị những token/range do các node giữ, **không tự nói một khoảng token là một khoảng ngày**. `CONSISTENCY` và `TRACING` là lệnh của **cqlsh**, không phải câu CQL gửi nguyên văn từ Java.

## 8. Đọc nhiều dữ liệu: chia range, paging và checkpoint

Một token scan hoàn chỉnh thường phục vụ công việc batch và cần quản lý vòng đời xử lý riêng. Không nên gửi một truy vấn toàn vòng token và giữ tất cả kết quả trong RAM.

### 8.1. Chia khoảng không trùng nhau

Ví dụ chia một phần miền token thành hai khoảng:

~~~text
(A, M]   và   (M, B]
~~~

Điều kiện nửa kín này tránh đếm hai lần token đúng bằng `M`. Với `Murmur3Partitioner`, các token là số nguyên có dấu 64 bit; cần lập kế hoạch bao phủ **đúng toàn bộ vòng**, bao gồm vùng có dấu âm, dương, ranh giới và **điểm vòng về đầu** nếu muốn scan mọi partition. Không dùng so sánh `start < end` theo trực giác ngày tháng để suy ra toàn bộ vòng được bao phủ.

Phân vùng công việc theo `nodetool ring` hay metadata token map chỉ là cách **chia trách nhiệm quét**, không phải phép phân chia theo business key. Việc thêm/xóa node, đổi token ownership hoặc repair khi scan đang chạy có thể làm dữ liệu quan sát thay đổi; batch cần thiết kế checkpoint và khả năng chạy lại.

**Tránh mất/trùng dữ liệu khi resume:** nhiều partition key có thể có cùng token (hash collision hiếm nhưng có thể xảy ra), và một token có thể có rất nhiều hàng trong một partition. Chỉ nhớ **token của hàng cuối** rồi dùng `>` khi chạy tiếp có thể bỏ sót những hàng/partition còn lại cùng token. Sử dụng paging state và checkpoint theo công việc, cùng cơ chế idempotency/deduplication ở nơi đích.

### 8.2. Dùng paging đúng ý nghĩa

- **Page size** giới hạn lượng dữ liệu driver yêu cầu trong từng lượt, giúp giữ bộ nhớ và thời gian phản hồi của mỗi trang có kiểm soát. Nó **không giảm tổng số hàng** cần đọc để xử lý toàn bộ range.
- **Paging state** là con trỏ do driver/protocol cung cấp để tiếp tục cùng statement và bind values. Không tự giải mã paging state thành token, và không dùng nó cho câu truy vấn khác.
- **`LIMIT`** giới hạn số hàng trả về của một statement, vì vậy phù hợp lấy mẫu nhưng không thích hợp nếu mục tiêu là quét đủ mọi hàng.
- **Giới hạn mức song song:** quét quá nhiều range hoặc page đồng thời có thể làm nghẽn disk, network, CPU, coordinator và gây timeout cho traffic ứng dụng.
- **Bản ghi thay đổi trong khi quét:** Cassandra không cung cấp snapshot toàn bảng giống một transaction MVCC. Batch cần chấp nhận và xử lý cập nhật/xóa đồng thời hoặc có chiến lược snapshot/pipeline phù hợp.

### 8.3. Những dấu hiệu cần quan sát

| Chỉ số/hiện tượng | Câu hỏi cần trả lời |
| --- | --- |
| Read latency, timeout, unavailable | Có quá nhiều range/read đang chạy hoặc CL vượt số replica khả dụng? |
| Cache hit ratio, filesystem cache pressure | Quét có đẩy các partition hot khỏi cache hay không? |
| SSTable per read và tombstone scan | Có cần tối ưu compaction, TTL, bucket hoặc mô hình bảng? |
| CPU, disk IOPS, network, pending read tasks | Range scan có tranh tài nguyên với truy vấn API? |
| Paging throughput và resume failures | Checkpoint/khả năng retry của job có đáng tin cậy? |
| Replica health, repair và topology changes | Có khoảng nào chưa đồng bộ hoặc bị thay đổi ownership trong quá trình scan? |

Số liệu cụ thể nên đo trong lab/staging và kiểm tra theo phiên bản Cassandra đang chạy. **Không dùng `ALLOW FILTERING` như một cách cải thiện hiệu năng token scan**: nó không làm bộ quét tự chuyển thành đọc một partition.

## 9. Ví dụ Java Driver 4.x: định tuyến một partition và quét một khoảng

Ví dụ dưới đây cho thấy **hai prepared statement** cho cùng bảng. Phần scan chỉ lấy mẫu một khoảng nhỏ với `LIMIT 100` và page size 50 để tránh vô tình tạo một vòng lặp xuất dữ liệu không giới hạn:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public class CassandraReadPaths {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            // 1) Biết đủ partition key: query phục vụ API.
            PreparedStatement onePartition = session.prepare(
                    "SELECT event_time, event_id, reading " +
                    "FROM telemetry_lab.readings_by_sensor_day " +
                    "WHERE sensor_id = ? AND event_day = ? LIMIT 50");

            BoundStatement pointRead = onePartition.bind(
                            "sensor-9", LocalDate.of(2026, 11, 21))
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            for (Row row : session.execute(pointRead)) {
                System.out.println("point: " + row.getInstant("event_time")
                        + " = " + row.getBigDecimal("reading"));
            }

            // 2) Không có một partition key duy nhất:
            //    quét mẫu các partition theo token, không dùng làm API point-read.
            PreparedStatement tokenScan = session.prepare(
                    "SELECT sensor_id, event_day, event_time, reading " +
                    "FROM telemetry_lab.readings_by_sensor_day " +
                    "WHERE token(sensor_id, event_day) > ? " +
                    "AND token(sensor_id, event_day) <= ? LIMIT 100");

            BoundStatement sampleRange = tokenScan.bind(
                            -4611686018427387904L, 0L)
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_ONE)
                    .setPageSize(50);

            for (Row row : session.execute(sampleRange)) {
                System.out.println("range: " + row.getString("sensor_id")
                        + " / " + row.getLocalDate("event_day")
                        + " = " + row.getBigDecimal("reading"));
            }
        }
    }
}
~~~

**Cách đọc ví dụ:**

1. `onePartition.bind(sensor_id, event_day)` cho driver đủ thông tin partition key để áp dụng token-aware routing khi được hỗ trợ.
2. `tokenScan.bind(startToken, endToken)` chỉ ràng buộc **biên token kiểu bigint**; nó không chỉ ra một partition key của hàng cần đọc.
3. `LOCAL_QUORUM` và `LOCAL_ONE` là **lựa chọn minh họa** để thấy chúng áp dụng cho cả hai đường đọc; production phải chọn CL theo yêu cầu nhất quán, không mặc định scan dùng CL thấp hơn.
4. `setPageSize(50)` cho phép nhận kết quả theo page, nhưng vẫn cần kiểm soát toàn bộ job nếu bỏ `LIMIT`. Iterator đồng bộ của driver có thể tự tải page tiếp theo.
5. Giá trị `127.0.0.1`, `dc1` và ngưỡng token chỉ dùng cho lab. Cấu hình thực tế cần đúng contact point, local DC, authentication/TLS và chính sách timeout.

Đối với **backfill production**, cần quản lý checkpoint theo range/page, số worker đồng thời, retry idempotent và đối soát tổng số bản ghi ở đích. Code mẫu này **không phải** bộ quét production hoàn chỉnh.

## 10. Lỗi suy luận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “`WHERE token(pk) BETWEEN ...` là truy vấn một partition.” | **Sai** | Khoảng token có thể chứa nhiều partition, mỗi partition có nhiều hàng. |
| “Token tăng theo `event_day` nên token range tương đương khoảng ngày.” | **Sai** | Token là kết quả partitioner/hash; không giữ thứ tự business key. |
| “Một partition đã xác định thì mọi hàng luôn đọc nhanh.” | **Sai** | Partition lớn, SSTable nhiều và tombstone có thể làm đọc chậm. |
| “Bloom filter chắc chắn cho biết partition có trong SSTable.” | **Sai** | Bloom filter có thể dương tính giả; kết quả âm mới là khẳng định không chứa khóa. |
| “Row cache/key cache có thể thay consistency level.” | **Sai** | Replica vẫn phải được đọc/đối chiếu đủ theo CL của request. |
| “`LIMIT 100` nghĩa là đã quét hết range sau khi nhận 100 hàng.” | **Sai** | Đó chỉ là giới hạn số hàng trong kết quả statement. |
| “Page size 50 nghĩa cả công việc chỉ đọc 50 hàng.” | **Sai** | Driver có thể tải nhiều page liên tiếp. |
| “`LOCAL_QUORUM` tạo snapshot nhất quán trên nhiều partition.” | **Sai** | CL không cung cấp transaction snapshot toàn bảng. |
| “Có thể dùng cùng token cuối để resume an toàn mọi trường hợp.” | **Sai** | Còn hàng trong partition và khả năng token collision; dùng paging/checkpoint và deduplication. |

## 11. Bài tập có đáp án

**Bài 1.** Bảng có `PRIMARY KEY ((sensor_id, event_day), event_time, event_id)`. Muốn đọc phép đo của `sensor-9` ngày 21/11 từ 08:00 đến 09:00, chọn token scan hay single-partition read?

**Đáp án:** Chọn **single-partition read** vì biết cả `sensor_id` và `event_day`; dùng `event_time >= ... AND event_time < ...` để giới hạn **clustering range**.

**Bài 2.** Vì sao `token(sensor_id)` không đúng cho bảng ví dụ khi cần lọc token?

**Đáp án:** Partition key gồm **hai** thành phần `sensor_id` và `event_day`. Phải dùng `token(sensor_id, event_day)` với đủ các cột theo thứ tự schema.

**Bài 3.** Một ứng dụng muốn đọc tất cả sự kiện trong tháng 11 từ mọi cảm biến và sắp theo `event_time`. Có nên lấy một token range rồi nghĩ rằng kết quả đã được sắp theo thời gian?

**Đáp án:** **Không.** Khoảng token phân nhóm theo hash của partition key, không theo thời gian. Phải dùng mô hình dữ liệu phục vụ truy vấn tháng, thu thập từng bucket rồi tổng hợp/sắp xếp, hoặc dùng hệ phân tích chuyên dụng khi cần truy vấn xuyên nhiều partition.

**Bài 4.** Job scan tăng `setPageSize` từ 100 lên 1.000. Có tự giảm tổng số hàng phải đọc không?

**Đáp án:** **Không.** Chỉ thay lượng dữ liệu lấy trong một page và cách phân bổ round-trip/bộ nhớ. Cần đo latency, memory và độ ổn định, đồng thời hạn chế song song.

**Bài 5.** Nếu có 20.000 partition trong một khoảng token và mỗi partition chỉ đọc đúng một lần, vì sao key cache/row cache có thể ít giá trị hơn so với API liên tục đọc 10 partition hot?

**Đáp án:** Cache có lợi nhất khi truy cập lặp lại cùng dữ liệu/metadata. Quét diện rộng ít tái sử dụng và có thể gây eviction dữ liệu hot; chi phí scan chủ yếu còn ở I/O, xử lý nhiều partition và điều phối replica.

**Bài 6.** RF = 3 ở `dc1`. Một token-range read dùng `LOCAL_QUORUM` có nghĩa toàn bộ kết quả là snapshot tức thời của cùng một thời điểm?

**Đáp án:** **Không.** Với mỗi phần dữ liệu được đọc, coordinator cần phản hồi đủ CL, nhưng các partition có thể được đọc ở những thời điểm khác nhau; ghi/xóa đồng thời làm trạng thái thay đổi trong lúc scan.

## 12. Chọn đường đọc từ câu hỏi nghiệp vụ

~~~mermaid
flowchart TD
    A["Cần đọc dữ liệu Cassandra"] --> B{"Biết đầy đủ partition key?"}
    B -->|Có| C{"Có điều kiện về clustering columns?"}
    C -->|Có| D["Đọc một partition + clustering range"]
    C -->|Không| E["Đọc một partition theo khóa"]
    B -->|Không| F{"Mục tiêu là batch scan / backfill?"}
    F -->|Có| G["Chia token range + paging + checkpoint"]
    F -->|Không| H["Thiết kế lại bảng theo truy vấn / bucket / analytics"]
    D --> I["Đo latency, tombstone và cache hit"]
    E --> I
    G --> J["Giới hạn đồng thời, retry an toàn, đối soát"]
~~~

**Ghi nhớ:** biết **đầy đủ partition key** là đường ngắn nhất để Cassandra xác định replica và tra cứu partition. Dùng `token(...)` là cách **duyệt nhiều partition theo vị trí trên vòng phân phối**, phù hợp công việc batch hơn API đọc thông thường. Cả hai vẫn đi qua coordinator/replica, chịu consistency level, SSTable, tombstone và chi phí cache; sự khác biệt lớn nhất nằm ở **phạm vi dữ liệu cần quét** và **khả năng định tuyến chính xác đến một partition**.
