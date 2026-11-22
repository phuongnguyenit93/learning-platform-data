# Kiểm chứng mô hình bằng CQL, dữ liệu đại diện và số liệu đọc/ghi

## Mục tiêu bài học

Một schema Apache Cassandra trông hợp lý trên giấy chưa đủ để chứng minh nó phù hợp với sản phẩm. Câu CQL có thể hợp lệ nhưng truy vấn vẫn chậm ở **partition lớn nhất**; một bucket thời gian có thể giúp giảm số hàng/partition nhưng làm tăng số partition phải đọc; một bảng projection có thể giảm fan-out nhưng tạo thêm mutation, tombstone và nguy cơ lệch dữ liệu khi ghi thất bại.

Trong chương **Thiết kế theo truy vấn** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`, bài này xây dựng một **quy trình kiểm chứng thực nghiệm**: viết hợp đồng truy vấn, tạo CQL cho các phương án, chuẩn bị dữ liệu đại diện, chạy workload đọc/ghi có kiểm soát, đo thông lượng và p95/p99, rồi kết luận bằng tiêu chí chấp nhận định trước. Kiến thức liên quan gồm partition key, clustering, replication, consistency level, compaction, repair, TTL, xử lý lỗi và Java Driver.

Sau bài học, bạn có thể:

1. Tạo **ma trận kiểm chứng** nối từng truy vấn nghiệp vụ với partition key, câu CQL, điều kiện sắp xếp và giới hạn tài nguyên.
2. Phân biệt kiểm chứng **đúng dữ liệu**, **đúng đường truy cập**, **hiệu năng ở tải mục tiêu** và **khả năng chịu lỗi**.
3. Thiết kế dữ liệu thử nghiệm có độ lệch tải, thiết bị nóng, timestamp trùng, dữ liệu đến muộn, payload lớn, TTL và tombstone.
4. So sánh hai schema Cassandra bằng kết quả đo có thể tái lập, không chỉ bằng thời gian chạy một câu `SELECT` trên vài hàng mẫu.
5. Dùng CQL và Java Driver 4.x để minh họa đường ghi/đọc, paging và cách ghi nhận độ trễ.
6. Đọc chỉ số vận hành để phát hiện hot partition, compaction backlog, replica lag và giới hạn của mô hình.
7. Viết báo cáo **PASS/FAIL/NEEDS_MORE_EVIDENCE** có ngưỡng và bằng chứng rõ ràng.

## 1. Xác định chính xác điều phải chứng minh

Ví dụ hệ thống IoT nhiều tenant ghi sự kiện thiết bị:

```text
tenant_id, device_id, site_id, event_id,
event_time, received_at, event_type, severity, payload
```

Các API đang được cân nhắc:

| Mã | Truy vấn hoặc thao tác | Đầu vào có sẵn | Kết quả mong đợi |
| --- | --- | --- | --- |
| Q01 | Xem 50 sự kiện mới nhất của một thiết bị trong một giờ UTC | Tenant, device, giờ | Mới nhất trước, tối đa 50 |
| Q02 | Xem sự kiện trong khoảng `[09:15, 09:45)` UTC | Tenant, device, khoảng và giờ | Đúng khoảng, có phân trang |
| Q03 | Xem sự kiện của một thiết bị trong cửa sổ trượt 6 giờ | Tenant, device, from/to | Sắp xếp toàn khoảng, giới hạn fan-out |
| Q04 | Xem cảnh báo `CRITICAL` của toàn site trong ngày | Tenant, site, ngày | Danh sách mới nhất, không thăm dò mọi device |
| Q05 | Tra một sự kiện chỉ bằng event ID | Tenant, event ID | Một event nếu còn được lưu |
| W01 | Ingest telemetry liên tục | Dữ liệu nhận từ gateway | Ghi đúng khóa, có retry và giới hạn tải |
| W02 | Ghi sự kiện đến muộn hoặc bị phát lại | Event ID và event time ổn định | Không mất/nhân bản ngoài hợp đồng |

Q01–Q03 gợi ý partition theo **tenant + device + bucket thời gian**. Q04 và Q05 là các **đường đọc khác**: chúng không tự được bảo đảm bởi bảng theo thiết bị/giờ. Có thể cần bảng projection theo site hoặc lookup theo event ID; không nên làm méo một bảng duy nhất để đáp ứng mọi filter.

### 1.1. Đặt tiêu chí kiểm chứng trước khi benchmark

Ví dụ nhóm dự án **giả định** các ngưỡng sau để thiết kế thử nghiệm; đây **không phải SLO mặc định của Cassandra**:

| Kiểm chứng | Ngưỡng minh họa | Bằng chứng |
| --- | --- | --- |
| Q01 trên một partition bình thường | p95 dưới 40 ms | Latency end-to-end của request ở tải mục tiêu |
| Q01 trên thiết bị nóng nhất | p99 dưới 150 ms | Phân bố latency của riêng nhóm khóa nóng |
| Q03 cửa sổ 6 giờ | Đọc không quá 7 bucket giờ; p95 dưới 250 ms | Query count/fan-out và request latency |
| W01 | Ghi bền vững ở tải mục tiêu với tỷ lệ lỗi trong SLO | Throughput đã hoàn tất, timeout, CPU/I/O, backlog |
| W02 | Retry cùng event không tạo khóa hàng mới | So khớp toàn bộ primary key |
| Dữ liệu hết hạn | Không trả giá trị đã hết TTL, disk không tăng ngoài dự báo vận hành | Kiểm tra kết quả, tombstone, compaction |
| Một node tạm vắng | Có hành vi đọc/ghi được dự đoán theo CL/RF | Chaos test và metric phục hồi |

Ngưỡng phải được chủ sản phẩm/vận hành phê duyệt theo phần cứng, topology và tải thật. Nếu chưa có SLO, cần nêu rõ giả định chứ không tuyên bố một schema “nhanh”.

### 1.2. Bốn lớp bằng chứng

1. **CQL hợp lệ:** bảng tạo được; câu `SELECT` có đủ điều kiện cho primary key; driver bind đúng kiểu.
2. **Kết quả chính xác:** đúng tập hàng, đúng thứ tự, đúng khoảng nửa mở, xử lý timestamp trùng và bucket qua nửa đêm.
3. **Chi phí truy cập có giới hạn:** số partition, kích thước hàng/partition, rows/tombstones scanned và fan-out được kiểm soát.
4. **Vận hành đạt SLO:** thông lượng, p95/p99, CPU, disk, compaction, network, retry, repair và chịu lỗi vẫn trong ngưỡng ở dữ liệu đại diện.

Một schema chỉ đạt lớp 1 hoặc 2 **chưa đủ điều kiện đưa vào sản xuất**.

## 2. Chốt môi trường để số đo có thể so sánh

Benchmark chỉ có ý nghĩa khi biết số đo xuất phát từ đâu. Hai lần chạy có cùng CQL nhưng khác số node, RF hoặc phần trăm thiết bị nóng không phải một phép so sánh công bằng.

| Nhóm thông tin | Cần ghi nhận |
| --- | --- |
| Cassandra | Phiên bản/nhánh triển khai, schema, keyspace, compaction, compression, TTL, index |
| Topology | Số datacenter/node, số CPU/RAM, loại ổ đĩa, network, placement, RF mỗi DC |
| Client | Phiên bản Java Driver, số instance, connection/config, consistency level, timeout, retry policy |
| Workload | Đọc/ghi mỗi giây, số device/site, phân bố khóa nóng, kích thước payload, batch/replay |
| Dữ liệu | Tuổi dữ liệu, số hàng sống, tỷ lệ bản ghi hết TTL, số thao tác UPDATE/DELETE |
| Phép đo | Warm-up, thời gian steady state, burst, số vòng lặp, thời gian lấy mẫu |
| Mục tiêu | SLO đã thống nhất, mức tải cao điểm, biên độ tăng trưởng, tình huống node lỗi |

**Không chạy stress test bão hòa trên cụm production đang xử lý người dùng thực** nếu chưa có kế hoạch vận hành được phê duyệt. Nên dùng cụm/staging tương đương về topology và tài nguyên; nếu đo tại production, chọn kiểm chứng có kiểm soát và giới hạn tác động.

### 2.1. Thứ tự thí nghiệm nên tuân thủ

```text
Hợp đồng truy vấn + SLO
          |
          v
Thiết kế schema A / schema B
          |
          v
CQL correctness tests với vài hàng dễ đối chiếu
          |
          v
Nạp dữ liệu đại diện + TTL/tombstone/partition nóng
          |
          v
Warm-up -> tải mục tiêu -> đỉnh -> recovery
          |
          v
Gom latency, QPS, partition size, traces và hệ thống
          |
          v
So sánh có kiểm soát -> PASS / FAIL / thử lại
```

Tránh chọn schema dựa trên một truy vấn chạy rất nhanh lúc cache nóng, khi bảng chỉ có vài chục hàng và không có tombstone.

## 3. Hai ứng viên schema cho cùng một workload

Chúng ta so sánh **bucket ngày** và **bucket giờ**. Cả hai cùng nhóm theo tenant/device và cùng clustering time/ID; khác biệt nằm ở kích thước partition và số partition phải đọc cho một khoảng dài.

### 3.1. Ứng viên A — theo thiết bị/ngày UTC

```sql
CREATE TABLE device_events_by_day (
    tenant_id text,
    device_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, day_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Truy vấn trong ngày:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
LIMIT 50;
```

Ứng viên A phù hợp với API theo ngày nếu partition không quá lớn/hot. Nhưng Q01 hỏi **một giờ**, nên cần thêm điều kiện clustering time để chỉ lấy giờ cần đọc, chứ không chỉ dùng `LIMIT` trên cả ngày:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND day_bucket = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 50;
```

**Chú ý:** `day_bucket` luôn là **ngày UTC của `event_time`**. Nếu giờ nằm qua 00:00 UTC, phải chia khoảng thành các phần đúng ngày.

### 3.2. Ứng viên B — theo thiết bị/giờ UTC

```sql
CREATE TABLE device_events_by_hour (
    tenant_id text,
    device_id uuid,
    hour_bucket timestamp,
    event_time timestamp,
    event_id uuid,
    site_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, device_id, hour_bucket),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Q01 của ứng viên B:

```sql
SELECT event_time, event_id, event_type, severity
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 50;
```

Q02 của ứng viên B:

```sql
SELECT event_time, event_id, event_type, severity, payload
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
  AND event_time >= ?
  AND event_time < ?;
```

Giả định `hour_bucket` là thời điểm **đầu giờ UTC** từ `event_time`, ví dụ `2026-11-21T09:00:00Z`. Q01 đọc đúng một partition giờ; Q03 sáu giờ trượt có thể chạm **tối đa bảy partition giờ** vì lệch biên.

### 3.3. Những gì cần so sánh giữa A và B

| Khía cạnh | A — ngày | B — giờ |
| --- | --- | --- |
| Một ngày lịch UTC | Một partition/device | 24 partition/device |
| Một giờ của một device | Một partition ngày + range | Một partition giờ |
| Lịch sử 7 ngày lịch | Tối đa 7 partition ngày | Tối đa 168 partition giờ |
| Partition của device nóng | Có thể rất lớn | Nhỏ hơn nếu tải phân bố theo thời gian |
| Phân trang qua bucket | Ít luồng hơn | Nhiều luồng hơn với khoảng dài |
| Tải ghi tập trung | Tập replica của partition ngày | Tập replica có thể thay đổi theo mỗi giờ |
| Khả năng trả lời Q04 theo site | Không trực tiếp | Không trực tiếp |

**Cần kiểm chứng cả hai chiều:** giảm kích thước partition nhờ bucket giờ có thể đổi lấy fan-out và chi phí định tuyến cao hơn. Câu trả lời “bucket giờ luôn tốt hơn” hoặc “bucket ngày luôn tốt hơn” đều không đủ bằng chứng.

## 4. Kiểm chứng CQL bằng bộ dữ liệu nhỏ có đáp án biết trước

Trước stress test, tạo một tập event ngắn để kiểm tra chính xác ranh giới và sắp xếp. Dữ liệu sau chỉ là **seed kiểm thử chức năng**, chưa phải dữ liệu đại diện để đo hiệu năng.

### 4.1. Những ca bắt buộc có

| Sự kiện | `event_time` UTC | `received_at` UTC | Mục tiêu |
| --- | --- | --- | --- |
| E01 | 21/11 09:10:00.000 | 21/11 09:10:01 | Hàng bình thường trong giờ 09 |
| E02 | 21/11 09:10:00.000 | 21/11 09:10:02 | Trùng timestamp E01, khác event ID |
| E03 | 21/11 09:59:59.999 | 21/11 10:00:01 | Ngay trước biên giờ |
| E04 | 21/11 10:00:00.000 | 21/11 10:00:02 | Đúng đầu giờ kế tiếp |
| E05 | 20/11 23:58:00.000 | 21/11 10:10:00 | Sự kiện đến muộn, khác ngày |
| E06 | 21/11 09:20:00.000 | 21/11 09:20:01 | Kiểm tra khoảng và TTL |

`event_id` phải ổn định khi phát lại; timestamp trùng nhau được phân biệt bởi cột clustering thứ hai. Một UUID ngẫu nhiên **không** chứng minh thứ tự nhân quả khi timestamp trùng; nó chỉ tạo tie-break theo khóa.

### 4.2. Seed CQL cho ứng viên B

Đoạn dưới dùng một UUID thiết bị hợp lệ và bốn event ID khác nhau. Các giá trị UTC là **literal CQL để kiểm thử**, không dùng `?`.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:10:00.000Z',
    00000000-0000-4000-8000-000000000011,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T09:10:01Z', 'MEASURE', 'INFO', 'E01'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:10:00.000Z',
    00000000-0000-4000-8000-000000000012,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T09:10:02Z', 'MEASURE', 'WARN', 'E02'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T09:00:00Z',
    '2026-11-21T09:59:59.999Z',
    00000000-0000-4000-8000-000000000013,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T10:00:01Z', 'MEASURE', 'INFO', 'E03'
);

INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (
    'tenant-A',
    00000000-0000-4000-8000-000000000001,
    '2026-11-21T10:00:00Z',
    '2026-11-21T10:00:00.000Z',
    00000000-0000-4000-8000-000000000014,
    00000000-0000-4000-8000-000000000100,
    '2026-11-21T10:00:02Z', 'MEASURE', 'INFO', 'E04'
);
```

Chạy truy vấn đã biết toàn bộ khóa:

```sql
SELECT event_time, event_id, payload
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001
  AND hour_bucket = '2026-11-21T09:00:00Z'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time <  '2026-11-21T10:00:00Z';
```

**Kỳ vọng:** có E03, E02 và E01; không có E04. E03 đứng đầu vì timestamp mới nhất. E02 và E01 cùng timestamp, được sắp theo `event_id DESC`. Nếu hai event ID dùng ở ví dụ này như literal trên, E02 đứng trước E01. Câu query vào bucket 10:00 phải có E04 và không có E03.

Để kiểm tra E05 đến muộn, seed event với `event_time = 2026-11-20T23:58Z` và `hour_bucket = 2026-11-20T23:00Z`, dù `received_at` là ngày 21. Tương tự cần seed bảng ngày A bằng `day_bucket = 2026-11-20`; không đưa E05 vào bucket ngày nhận.

### 4.3. Thử replay cùng khóa

Gửi lại E01 với **cùng** tenant, device, hour bucket, event time và event ID. Kỳ vọng chỉ còn **một hàng logic** với primary key đó trong partition; một lần `INSERT` nữa là **upsert**, không tạo thêm hàng khác khóa.

Sau đó thử một lỗi cố ý: đổi `event_id` mỗi lần retry. Kết quả có thể xuất hiện hai hàng cho cùng sự kiện nghiệp vụ. Thử thêm trường hợp cùng event ID nhưng `event_time` hoặc bucket khác: vì toàn bộ primary key khác, Cassandra không tự bảo đảm duy nhất trên mỗi `event_id` toàn tenant.

Nếu nghiệp vụ cần định danh duy nhất chỉ bằng event ID, phải có quy tắc cấp ID/dedupe hoặc bảng lookup theo event ID được thiết kế riêng; không thể suy từ primary key của bảng timeline.

### 4.4. Những truy vấn phải bị đánh dấu là sai đường đọc

Ví dụ ý định sau không cung cấp đầy đủ partition key của bảng theo thiết bị/giờ:

```sql
-- KHÔNG PHẢI đường truy vấn theo khóa của bảng device_events_by_hour:
SELECT event_time, event_id
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A' AND severity = 'CRITICAL';
```

Đây không phải vấn đề chỉ thiếu `LIMIT 50` hoặc một lời gọi Java tối ưu. Muốn trả Q04 toàn site, hãy kiểm chứng một bảng `alerts_by_site_day` hoặc đường index/search phù hợp với tính chọn lọc và SLO. Không mặc định `ALLOW FILTERING` là giải pháp: dù một số query được cho phép, chi phí lọc ở phạm vi lớn có thể khó dự đoán.

**CQL không có một cơ chế `EXPLAIN` chuẩn tương đương mọi hệ SQL.** Đọc schema, kiểm tra predicate, dùng truy vết và chỉ số server trên một workload có kiểm soát thay vì suy rằng ngắn gọn là nhanh.

## 5. Dữ liệu đại diện phải phản ánh độ lệch tải thực tế

Seed vài hàng để xác nhận kết quả; benchmark phải có **phân bố dữ liệu** giống thực tế. Một dataset đồng đều thường che giấu partition nóng, payload lớn và tình huống sự kiện dồn về sau mất mạng.

### 5.1. Thiết kế ba nhóm thiết bị

Ví dụ một workload giả định gồm **1.000 thiết bị**:

| Nhóm | Số thiết bị | Tốc độ trung bình mỗi thiết bị | Tổng event/giây |
| --- | ---: | ---: | ---: |
| Bình thường | 900 | 0,02/s | 18 |
| Hoạt động mạnh | 90 | 0,5/s | 45 |
| Nóng | 10 | 25/s | 250 |
| **Tổng giả định** | **1.000** | — | **313** |

Đây chỉ là dataset minh họa để thấy ảnh hưởng của **skew**, không phải phân bố mặc định cho IoT. Nếu cứ gửi đều 0,313 event/giây cho cả 1.000 thiết bị thì tổng vẫn xấp xỉ 313/s, nhưng **không tạo được cùng hotspot**.

### 5.2. Tính partition lớn nhất trước khi chạy

Với một thiết bị nóng tạo **25 event/giây** và payload nghiệp vụ thô **600 B/event**:

```text
Trong 1 giờ:
    25 × 3.600 = 90.000 event
    90.000 × 600 B = 54.000.000 B = 54 MB thô

Trong 1 ngày:
    25 × 86.400 = 2.160.000 event
    2.160.000 × 600 B = 1.296.000.000 B ≈ 1,30 GB thô
```

Khi so A và B:

- Partition ngày của thiết bị nóng có thể chứa khoảng **2,16 triệu hàng** nếu tải đó duy trì cả ngày.
- Partition giờ có thể chứa khoảng **90.000 hàng** ở cùng tốc độ.
- Số byte trên SSTable thực tế khác byte thô do primary key, metadata, compression, TTL, tombstone, index, compaction và replica.

Không có ngưỡng “partition 54 MB luôn an toàn” hoặc “1,3 GB luôn gây lỗi” áp dụng cho mọi cluster. Cần đo **partition lớn nhất và tốc độ ghi**, chứ không chỉ tổng dung lượng hay trung bình toàn cụm.

### 5.3. Các biến thể dữ liệu bắt buộc có

| Trường hợp | Cách tạo | Cần kiểm tra |
| --- | --- | --- |
| Tenant lớn và tenant nhỏ | Phân phối device lệch giữa tenant | Không làm mất tenant scope, không chỉ đo tenant nhỏ |
| Thiết bị rất nóng | 1% thiết bị ghi phần lớn sự kiện | Hot partition, p99, replica CPU/I/O |
| Payload đa kích thước | Phần lớn nhỏ, một phần rất lớn | p99 row size, network, heap, disk |
| Timestamp trùng | Nhiều event cùng millisecond | Clustering tie-break và không mất hàng |
| Qua biên giờ/ngày | 09:59:59.999 → 10:00 và 23:59 → 00:00 | Bucket đúng UTC, khoảng không trùng/lọt |
| Sự kiện đến muộn | `event_time` cũ nhưng `received_at` mới | Bucket/TTL tính đúng nguồn thời gian |
| Replay | Ghi lại cùng ID, rồi thử ID sai | Idempotency theo toàn bộ primary key |
| TTL hết hạn | Nạp data nhiều tuổi và để hết hạn | Tombstone, latency và thời điểm không còn đọc được |
| UPDATE/DELETE | Xóa/sửa một tỷ lệ hàng xác định | Tombstone scanned, compaction, replay |
| Mất node/timeout | Cô lập một node trong thử nghiệm có phép | Behavior theo RF/CL, lỗi và recovery |

Không chỉ tạo 100 triệu hàng **mới tinh** rồi đo một lần. Bảng production có thể chứa dữ liệu qua nhiều chu kỳ TTL, update/xóa và compaction; cần dataset **có tuổi** và thử steady state. Nếu mô phỏng tuổi bằng backfill, phải xét timestamp ghi/TTL thực tế để mô phỏng không làm thay đổi ngữ nghĩa.

### 5.4. Biết nguồn gốc của dữ liệu thử

Ưu tiên dữ liệu tổng hợp không nhạy cảm, nhưng mô phỏng đúng **độ dài khóa, tỷ lệ null, kích thước payload, phân bố timestamp và skew theo tenant/device**. Nếu sử dụng dữ liệu thật cần tuân thủ chính sách bảo mật, xóa hoặc ẩn định danh và hạn chế quyền truy cập; dữ liệu hiệu năng không nên gây rò rỉ dữ liệu người dùng.

## 6. Benchmark có thể tái lập: không chỉ một lần cqlsh SELECT

Một phép thử nên có **nhiều giai đoạn** và giữ các điều kiện giống nhau giữa A và B. Ví dụ:

| Giai đoạn | Cách chạy | Điều cần ghi |
| --- | --- | --- |
| Chuẩn bị | Tạo schema, nạp dữ liệu theo phân bố đã chốt | Số rows, bytes, partition và thời gian nạp |
| Warm-up | Sinh tải tương tự mục tiêu trong thời gian đã định | Cache/connection ổn định, tránh đo cold-start lẫn steady state |
| Đọc đơn lẻ | Q01, Q02 trên normal/hot keys | Correctness, p50/p95/p99, bytes và tombstones |
| Mixed workload | Tỷ lệ đọc/ghi giống ứng dụng | Throughput hoàn tất, timeout, p95/p99 và tài nguyên |
| Burst | Tăng ingest và đọc lên mức đỉnh đã thống nhất | Queue, backpressure, lỗi, recovery |
| Aged-data test | TTL, DELETE/UPDATE, compaction qua nhiều cửa sổ | Tombstone, SSTables per read, disk và latency |
| Fault injection | Node chậm/mất liên lạc trong môi trường thử | Availability theo CL/RF, timeout và repair |
| Cooldown/đối chiếu | Hạ tải, đối soát và đo lại | Có hội tụ về trạng thái đúng và tài nguyên phục hồi? |

Số phút warm-up, số vòng thử và thời gian mỗi giai đoạn là **tham số thí nghiệm** phải ghi lại; không có một con số đủ cho mọi cluster. Chạy ít nhất nhiều vòng có điều kiện tương đương để nhận diện nhiễu, độ lệch tải và biến động compaction.

### 6.1. Đo latency thế nào cho đúng?

Với mỗi query shape, cần ghi:

- **Throughput thực sự hoàn tất** (requests/s), không chỉ requests đã gửi.
- `p50`, `p95`, `p99` và lỗi/timeout; không chỉ average.
- Client-side end-to-end request latency và, nếu có thể, server-side latency riêng.
- Tỷ lệ retry, request speculative/retried, số partition/bucket/shard chạm và page fetch.
- Số hàng **trả về** so với chi phí hàng/tombstone **được quét**.
- Phân biệt normal keys và hot keys; p99 toàn cluster có thể che p99 riêng của nhóm nóng.

Độ trễ đo ở client có thể bao gồm serialization, network, coordinator, replica, retry và paging. Nếu API trả **một trang đầu tiên**, đừng ghi nhãn số đo đó là “thời gian tải toàn bộ lịch sử”.

### 6.2. Giới hạn tải để không benchmark một mô hình phi thực tế

Một generator phát request không giới hạn với số thread tăng mãi có thể đo **khả năng gây quá tải** chứ không đo SLO ở lưu lượng mục tiêu. Cần định nghĩa rõ:

```text
target_ingest_events_per_second
target_Q01_requests_per_second
target_Q02_requests_per_second
target_Q03_requests_per_second
client_concurrency_limit
max_queued_requests
payload_size_distribution
hot_key_distribution
page_size
consistency_level
test_duration
```

Đặt **backpressure** và ghi cả request bị từ chối/quá hạn. Tăng concurrency không có kiểm soát có thể làm latency giả tạo tăng, timeout và pressure trên coordinator; so sánh hai schema phải dùng cùng tải đầu vào và cùng retry policy.

### 6.3. Kiểm chứng phân trang

Trong Cassandra:

| Khái niệm | Điều phải kiểm |
| --- | --- |
| `LIMIT 50` | Tổng số hàng tối đa của câu CQL |
| Driver `page size = 50` | Mục tiêu số hàng ở một fetch page; có thể fetch tiếp |
| API `limit = 50` | Số hàng trả về cho người gọi; phải enforce độc lập |
| Cursor/paging state | Ràng buộc query shape, bind values, tenant và phạm vi |
| Nhiều bucket | Cần duy trì vị trí mỗi partition và hợp nhất kết quả |

Truy vấn sáu giờ trượt có thể đi qua **bảy bucket giờ**. Nếu mỗi bucket trả một trang 50 hàng rồi ứng dụng gom toàn bộ và sort, tổng số hàng trung gian có thể lên tới 350 hàng trước khi trả 50 kết quả; cần quản lý chi phí và dừng/đọc tiếp theo thiết kế merge. Đừng dùng cursor của một partition cho truy vấn tổng hợp nhiều bucket.

Khi dữ liệu tiếp tục đến hoặc TTL hết hạn, phân trang nhiều lần **không mặc nhiên tạo một snapshot bất biến**. API cần mô tả semantics: có thể chấp nhận danh sách thay đổi hay cần watermark/điều kiện cửa sổ cố định.

## 7. Đọc metric Cassandra và truy vết có mục đích

Ngoài client latency, cần quan sát Cassandra để tìm lý do một query nhanh/chậm. Tên lệnh/metric cụ thể có thể thay đổi theo phiên bản và công cụ vận hành; luôn ghi rõ phiên bản và phạm vi khi chạy.

### 7.1. Những chỉ số nên thu

| Nhóm | Metric/công cụ tham khảo | Câu hỏi trả lời |
| --- | --- | --- |
| Phân bố dữ liệu | `nodetool status`, metric per-node | Node nào có nhiều dữ liệu/tải hơn? |
| Dung lượng bảng | `nodetool tablestats` | Live space, total space, số partition/ước lượng |
| Histogram bảng | `nodetool tablehistograms` | Kích thước partition/độ trễ phân bố ra sao? |
| CPU, heap, GC | Metric hệ điều hành/JVM | Chậm do CPU/GC thay vì riêng CQL? |
| Read/write latency | Metric Cassandra và client | Server và client thấy độ trễ thế nào? |
| Tombstone scanned | Metric/tracing có hỗ trợ | Query đang phải đi qua bao nhiêu dấu xóa? |
| SSTables per read | Histogram/metric bảng | Đọc một truy vấn chạm nhiều SSTable không? |
| Compaction | `nodetool compactionstats`, pending tasks | Compaction có tụt lại khi TTL/xóa tăng? |
| Thread pool | `nodetool tpstats` và metric tương ứng | Có hàng đợi/drop do quá tải không? |
| Network/streaming | Metric mạng, repair/streaming | Node chậm hoặc data movement ảnh hưởng? |

`nodetool` cho biết góc nhìn server, nhưng một số metric tổng hợp theo node/table hoặc sampling theo khoảng. Hãy đồng bộ thời gian giữa client/cluster và ghi **mốc thời gian thử** để nối hiện tượng latency với CPU, compaction và tombstone.

### 7.2. Tracing trong cqlsh chỉ dùng có chọn lọc

Trong môi trường thử có kiểm soát, có thể bật tracing để xem những bước xử lý của một câu:

```sql
TRACING ON;

SELECT event_time, event_id
FROM device_events_by_hour
WHERE tenant_id = 'tenant-A'
  AND device_id = 00000000-0000-4000-8000-000000000001
  AND hour_bucket = '2026-11-21T09:00:00Z'
LIMIT 10;

TRACING OFF;
```

Lệnh `TRACING ON/OFF` là thao tác **cqlsh**, không phải phần của câu `SELECT` gửi bằng Java Driver. Tracing có overhead; không bật rộng hoặc liên tục trên toàn bộ traffic production chỉ để benchmark. Dùng mẫu có mục đích để kiểm tra tuyến truy cập và hành vi xử lý cùng metric server.

**Không suy luận “tracing chạy một lần nhanh” là p99 của hệ thống.** Thời gian truy vấn bị tác động bởi load, cache, compaction, network và replica.

### 7.3. Đọc dấu hiệu để truy ngược quyết định mô hình

| Quan sát | Giả thuyết đáng kiểm tra | Hành động tiếp theo |
| --- | --- | --- |
| p99 tăng chỉ trên 10 device nóng | Partition/replica nóng, payload lớn | Kiểm tra per-key QPS, partition size, thử bucket nhỏ/shard |
| Q03 chậm dù Q01 nhanh | Fan-out nhiều bucket hoặc merge/paging | Đếm partition/page fetch và byte trung gian |
| Số row trả về ít nhưng latency cao | Tombstone/TTL đã hết hoặc nhiều SSTable | Xem tombstone scanned, compaction và tuổi dữ liệu |
| Disk tăng dù retention giữ nguyên | SSTable cũ, compaction backlog, snapshot, ghi đè | Phân loại thành phần disk; thử steady state |
| Mọi query chậm lúc burst | Node/CPU/network, client concurrency hoặc GC | Giảm tải, xem bottleneck trước khi đổi schema |
| Q04 phải quét mọi device trong site | Sai partition key cho query shape | Thêm projection/index/search phù hợp và đo mutation |
| Query trả sai ngày khi gateway offline | Reader/writer dùng khác nguồn thời gian | So event_time, received_at và bucket UTC |
| Sau node lỗi, read/write timeout tăng | RF/CL và khả năng phục hồi theo topology | Thử fault behavior và repair, không quy tất cả về schema |

## 8. Java Driver 4.x: đo trang đầu và kiểm tra bind

Ví dụ dưới minh họa đo **độ trễ tới trang kết quả đầu tiên** của Q02. Nó dùng Java Driver 4.x, giữ `CqlSession` theo vòng đời ứng dụng và gọi `executeAsync`. Không tự coi thời gian này là thời gian tải hết mọi trang.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import java.util.concurrent.CompletionStage;

public final class DeviceQueryProbe {
    private final CqlSession session;
    private final PreparedStatement byHourRange;

    public DeviceQueryProbe(CqlSession session) {
        this.session = session;
        this.byHourRange = session.prepare(
            "SELECT event_time, event_id, event_type, severity " +
            "FROM device_events_by_hour " +
            "WHERE tenant_id = ? AND device_id = ? AND hour_bucket = ? " +
            "AND event_time >= ? AND event_time < ?"
        );
    }

    public record FirstPageMeasurement(
        long latencyMicros, int rowsOnFirstPage, boolean morePages
    ) {}

    public CompletionStage<FirstPageMeasurement> probeOneHour(
        String tenantId, UUID deviceId,
        Instant fromInclusive, Instant toExclusive
    ) {
        if (!fromInclusive.isBefore(toExclusive)) {
            throw new IllegalArgumentException("Invalid time range");
        }

        Instant bucket = fromInclusive.truncatedTo(ChronoUnit.HOURS);
        if (toExclusive.isAfter(bucket.plus(1, ChronoUnit.HOURS))) {
            throw new IllegalArgumentException("Split range into hour buckets");
        }

        BoundStatement bound = byHourRange.bind(
            tenantId, deviceId, bucket, fromInclusive, toExclusive
        ).setPageSize(50);

        long started = System.nanoTime();
        return session.executeAsync(bound).thenApply((AsyncResultSet page) -> {
            long latencyMicros =
                Duration.ofNanos(System.nanoTime() - started).toNanos() / 1_000L;
            int rows = 0;
            for (Row ignored : page.currentPage()) {
                rows++;
            }
            return new FirstPageMeasurement(
                latencyMicros, rows, page.hasMorePages()
            );
        });
    }
}
```

**Phạm vi chính xác của phép đo:**

- `System.nanoTime()` đo elapsed time ở client theo đồng hồ monotonic, không phải timestamp tuyệt đối.
- `executeAsync` hoàn tất khi có **trang kết quả hiện tại**, không có nghĩa toàn bộ các trang đã được đọc. `page.hasMorePages()` cho biết còn trang có thể lấy.
- `page.currentPage()` chỉ duyệt những hàng **đã có trong trang hiện tại**. Ví dụ không gọi `fetchNextPage()` nên không đo tổng thời gian đọc toàn bộ khoảng.
- `setPageSize(50)` là page-size mục tiêu; Cassandra có thể trả ít hàng hơn vì dữ liệu, kích thước page hoặc giới hạn khác.
- `fromInclusive` và `toExclusive` được kiểm tra để không âm thầm đọc sai bucket; nếu khoảng vượt giờ, service phải phân rã và đo từng nhánh/fan-out.
- Không nên chạy callback nặng trên thread xử lý kết quả của driver; thu số đo tối thiểu, đưa phân tích/ghi metric sang hệ phù hợp nếu tải lớn.

Với Java 11 hoặc phiên bản không hỗ trợ `record`, thay `record FirstPageMeasurement` bằng một lớp dữ liệu thông thường. Trong benchmark thực tế, nên dùng histogram latency có độ phân giải phù hợp, thu đủ mẫu cho p99 và ghi lại tỷ lệ timeout; không chỉ lấy số trung bình từ vài lời gọi.

### 8.1. Benchmark đường ghi từ Java cần thêm gì?

Đường ghi không chỉ gọi `session.execute` nhiều lần:

1. Sinh các event ID, event time và bucket theo **cùng phân bố** ở phần 5.
2. Cố định tỷ lệ normal/hot keys; có cơ chế gửi retry **cùng primary key** khi mô phỏng timeout.
3. Giới hạn concurrency/queue, cho hệ thống thời gian warm-up và ghi **actual completions/s**.
4. Tách thời gian chuẩn bị payload/serialization khỏi thời gian client request nếu muốn phân tích từng thành phần.
5. Theo dõi write timeout, `NoNodeAvailable`/connection errors theo ngữ cảnh driver và node metrics; không tự retry vô hạn.
6. Nếu có hai projection, đo cả mutation bổ sung, lag và trạng thái sau khi một mutation thất bại.

Việc một `executeAsync` hoàn tất không tự chứng minh dữ liệu đã hiện diện ở **mọi replica** hoặc mọi bảng phụ. Chọn consistency level theo RF/topology/SLA và xác minh bằng readback/đối soát phù hợp.

## 9. Kiểm chứng TTL, tombstone, compaction và repair

### 9.1. Chính sách TTL phải được chứng minh bằng sự kiện đến muộn

Giả sử giữ event **7 ngày kể từ `event_time`**. Khi gateway offline hai ngày, không được tự dùng TTL 7 ngày kể từ lúc nhận nếu muốn giữ đúng tuổi dữ liệu nghiệp vụ.

```sql
INSERT INTO device_events_by_hour (
    tenant_id, device_id, hour_bucket, event_time, event_id,
    site_id, received_at, event_type, severity, payload
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

```text
expires_at = event_time + 7 ngày
remaining_seconds = expires_at - clock_now_at_write

remaining_seconds > 0:
    ghi với TTL còn lại, trong miền giá trị hợp lệ
remaining_seconds <= 0:
    không ghi vào bảng retention này; áp chính sách dữ liệu quá hạn
```

Sự kiện đã xảy ra hai ngày trước khi nhận chỉ còn khoảng **năm ngày TTL**. Trong kiểm thử, so mốc hết hạn dự kiến với dữ liệu đọc thực tế, chấp nhận sai số giây/clock đã được quy định. Không diễn giải `TTL 0` là “xóa ngay”; phải kiểm soát trường hợp TTL không dương ở ứng dụng.

### 9.2. Đọc hàng còn sống và xem TTL còn lại

Với cột có TTL như `payload`, có thể kiểm tra:

```sql
SELECT event_time, event_id, TTL(payload)
FROM device_events_by_hour
WHERE tenant_id = ?
  AND device_id = ?
  AND hour_bucket = ?
LIMIT 10;
```

`TTL(payload)` trả thời gian còn lại của **ô cụ thể** nếu ô có TTL và còn sống; `null` có thể vì không có TTL hoặc ô không hiện diện. Không suy luận mọi ô của hàng có cùng TTL chỉ từ một cột.

TTL áp dụng tới giá trị được ghi, không tự xóa file SSTable ngay khi hết hạn. Trong quá trình thử, theo dõi tombstone, compaction backlog, disk used và read latency **trước và sau khi dữ liệu hết hạn**. Nếu chỉ benchmark toàn hàng mới và không có TTL, sẽ đánh giá thấp chi phí của bảng có churn.

### 9.3. Chọn compaction strategy bằng workload, không bằng tên bảng

Với telemetry phần lớn append-only, TTL khá đồng đều và ít cập nhật dữ liệu cũ, **TimeWindowCompactionStrategy (TWCS)** là ứng viên có thể benchmark. Nhưng cửa sổ TWCS dựa trên timestamp ghi trong storage, **không** dựa trực tiếp trên `hour_bucket`. Ghi lại event cũ, backfill và trộn TTL có thể ảnh hưởng khả năng dọn SSTable theo thời gian.

Khi so A/B, phải giữ compaction strategy nhất quán nếu mục tiêu chỉ là so bucket. Nếu muốn so cả chiến lược compaction, lập thí nghiệm **riêng**, vì đổi đồng thời bucket, compaction và payload khiến không xác định được yếu tố nào tạo lợi ích.

### 9.4. Replication và consistency trong phép thử lỗi

Giả sử một DC có `RF=3`. Có thể đánh giá đọc/ghi với `LOCAL_QUORUM` nếu mục tiêu và topology phù hợp. Trong môi trường lý tưởng, local quorum với RF=3 cần ít nhất hai replica xác nhận cho mỗi thao tác tương ứng; nhưng nó không bảo đảm ứng dụng có giao dịch xuyên nhiều bảng hay tránh mọi vấn đề đồng thời.

Để kiểm chứng:

- Ghi và đọc cùng một partition theo CL đã chọn, cả khi một replica chậm hoặc vắng.
- Đo timeout, latency, áp lực retry, khả năng phục hồi và readback sau sự cố.
- Xem trạng thái repair/streaming sau khi node trở lại.
- Nếu có projection theo site, kiểm tra riêng việc **ghi thiếu bảng phụ** khi consumer lỗi: repair của Cassandra không tự bổ sung mutation nghiệp vụ chưa gửi.

Không thay đổi `gc_grace_seconds` tùy tiện chỉ để làm giảm tombstone trong benchmark. An toàn xóa liên quan tới replica có thể bỏ lỡ delete và quy trình repair của phiên bản/cụm đang dùng.

## 10. Chứng minh truy vấn phụ: một projection có đáng giá không?

Q04 hỏi cảnh báo CRITICAL tại site/ngày. Nếu schema chính theo device/hour, muốn trả Q04 phải biết trước các device/hour, rồi lọc event trong nhiều partition. Nếu Q04 thường xuyên, có SLO chặt, hãy thử một bảng phụ:

```sql
CREATE TABLE critical_events_by_site_day (
    tenant_id text,
    site_id uuid,
    day_bucket date,
    shard_id int,
    event_time timestamp,
    event_id uuid,
    device_id uuid,
    severity text,
    payload text,
    PRIMARY KEY ((tenant_id, site_id, day_bucket, shard_id),
                 event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
```

Giả định site lớn dùng 8 shard, thuật toán tính `shard_id` từ event ID và được version hóa. Một event CRITICAL cần được ghi ở bảng device/hour **và** bảng site/day; reader Q04 đọc tới 8 partition rồi hợp nhất. Nếu site nhỏ, thử bản không shard để tránh fan-out không cần thiết.

### 10.1. Thử nghiệm đường đọc và đường ghi phải đi cùng nhau

| Thí nghiệm | Cần chứng minh |
| --- | --- |
| Q04 không projection | Thăm dò bao nhiêu partition, p95/p99 và bytes đọc? |
| Q04 có projection 8 shard | p95/p99, merge/paging có giới hạn và hotspot mỗi shard? |
| Tạo event CRITICAL | Có đủ cả bản gốc và projection, đúng key/TTL? |
| Ghi bảng gốc thành công, bảng phụ lỗi | Có durable retry và đối soát hàng thiếu? |
| Event đến lại hoặc revision cũ | Không làm sai trạng thái/bản sao cuối? |
| Hết TTL hoặc xóa event | Không giữ bản phụ quá chính sách hoặc tái tạo dữ liệu hết hạn? |
| Tenant lớn nhất/site nhiều alert nhất | Chưa tạo partition quá nóng, SLO còn đạt? |

Lợi ích giảm **read amplification** phải được so với số mutation, dung lượng replica, tombstone và chi phí duy trì projection. Tăng consistency level trên bảng site không tự khắc phục sự kiện chưa bao giờ được consumer ghi sang đó.

### 10.2. Không kiểm chứng query shape hiếm bằng full scan sản xuất

Một yêu cầu phân tích “đếm cảnh báo toàn tenant trong hai năm, nhóm theo site và tháng” khác Q04. Nó có thể cần pipeline tổng hợp hoặc kho OLAP; không nên tải mọi event theo device/hour về một Java service chỉ để `GROUP BY` ở bộ nhớ.

Nếu truy vấn có full-text, nhiều filter tùy ý và sắp xếp linh hoạt, cân nhắc search/index phù hợp thay vì thêm bảng cho mọi tổ hợp UI. Vẫn phải đo độ mới, backlog, ACL tenant và khả năng đối soát giữa Cassandra nguồn với hệ phụ.

## 11. Phân tích kết quả thử và quyết định mô hình

Giả sử hai phương án A/B được đo trên **cùng phần cứng, RF, payload, tỷ lệ hot devices, tải và chính sách compaction**. Bảng dưới là **số liệu minh họa giả định**, không phải kết quả benchmark Cassandra thực tế:

| Chỉ số ở tải mục tiêu | A: ngày | B: giờ | Cách hiểu |
| --- | ---: | ---: | --- |
| Q01 p95 | 52 ms | 28 ms | Bucket giờ nhanh hơn trong giả định |
| Q01 hot-key p99 | 260 ms | 115 ms | A vượt ngưỡng hot-key giả định 150 ms |
| Q03 p95 | 82 ms | 170 ms | A nhanh hơn vì fan-out ít partition |
| W01 hoàn tất | 300 event/s | 300 event/s | Cả hai đạt throughput minh họa |
| Partition hot lớn nhất (raw) | ~1,3 GB/ngày | ~54 MB/giờ | Không phải byte SSTable thực tế |
| Số partition tối đa cho Q03 | 1 ngày, có thể 2 khi qua UTC midnight | 7 giờ | Fan-out phụ thuộc khoảng thực tế |
| Tombstone scanned ở dataset có tuổi | Cần đo | Cần đo | Không thể kết luận từ chỉ số raw size |

**Không tự kết luận B thắng trên mọi mặt.** Nếu Q01 và hot-key p99 là ưu tiên và Q03 vẫn dưới ngưỡng giả định 250 ms, B có thể đáp ứng tốt hơn. Nếu Q03 là API chủ đạo ở tải cao, A có thể hữu ích nếu hot partition được kiểm soát hoặc cần phương án khác. Điều quan trọng là **quyết định dựa trên ngưỡng đã chốt**, không chỉ “chỉ số nào nhỏ nhất”.

### 11.1. Viết kết luận theo dạng có thể kiểm toán

```text
Candidate: device_events_by_hour
Workload: 1.000 devices, skew 90/9/1,
          313 new events/s, payload distribution = ...
Topology: Cassandra version ..., DC/node/RF = ...
CL: read ..., write ...
Compaction: ...
Duration: warm-up ..., steady ..., burst ...

Q01 hot p99: ... ms (target <= ... ms)
Q03 p95: ... ms (target <= ... ms)
W01 completed throughput: ... /s, timeout: ... %
Largest partition: ... rows / ... SSTable bytes
Tombstone scanned / SSTables per read: ...
Compaction backlog / disk headroom: ...

Decision: PASS / FAIL / NEEDS_MORE_EVIDENCE
Open questions: ...
Next action: ...
```

Nếu dữ liệu test không có sự kiện hết hạn hoặc chưa thử node lỗi mà production có cả hai, ghi **NEEDS_MORE_EVIDENCE**, không đánh dấu PASS toàn bộ.

### 11.2. Khi nào phải quay lại thiết kế?

- Câu CQL chủ đạo không thể cung cấp đầy đủ partition key, hoặc buộc quét quá nhiều partition.
- Partition lớn nhất/hot nhất vượt latency hoặc tài nguyên mục tiêu.
- Bucket quá nhỏ làm fan-out/paging vượt SLA ở đường đọc thực.
- Tỷ lệ tombstone và compaction làm latency tăng khi dữ liệu già đi.
- Projection tạo write amplification lớn hơn khả năng chịu tải hoặc không có cơ chế sửa lỗi.
- Retention/TTL theo event time không được giữ đúng khi event đến muộn hoặc replay.
- SLO chỉ đạt được khi không có lỗi node, trong khi yêu cầu sẵn sàng phải chịu được sự cố đã định.

Khi không đủ bằng chứng, hãy thay **một biến tại một thời điểm** (bucket, shard count, compaction, index, cấu hình driver) rồi đo lại trong cùng điều kiện đầu vào; không kết luận nguyên nhân từ một phép thử thay đổi nhiều thứ cùng lúc.

## 12. Checklist trước khi chọn mô hình sản xuất

| Câu hỏi | Trạng thái kiểm chứng cần có |
| --- | --- |
| Mỗi API có query shape rõ chưa? | Input, sort, LIMIT, range, QPS, SLO và giới hạn |
| CQL có hợp lệ và đủ partition key không? | Test CREATE/INSERT/SELECT trên schema thật |
| Có test timestamp trùng và ranh giới UTC không? | Kết quả đối chiếu bằng event ID/giờ/ngày |
| Dữ liệu test có skew và thiết bị nóng không? | Phân bố per-key thực tế/giả định được ghi |
| Có payload p99, replay và late arrivals không? | Dataset có mẫu tương ứng, kết quả đúng |
| Đã tính hàng/byte của partition lớn nhất chưa? | Có công thức và số đo SSTable, không chỉ byte JSON |
| Có thử dữ liệu già, TTL và tombstone không? | Đo qua nhiều chu kỳ ghi/xóa/compaction |
| Đã đo p95/p99 và throughput hoàn tất chưa? | So với ngưỡng được định trước và nhiều vòng |
| Đã giới hạn fan-out/paging chưa? | Có cap số bucket/shard, byte, concurrency và cursor |
| Có quan sát replica và node nóng không? | Metric per-node/table, lỗi, CPU/I/O và network |
| Có thử lỗi node và consistency level không? | Đọc/ghi/recovery theo RF/CL dự kiến |
| Có projection không? | Đã đo write cost, lag, retry và reconciliation |
| Có headroom vận hành không? | Disk, compaction, repair, snapshot/backfill được tính |
| Có thể tái lập benchmark không? | Schema, data seed, cấu hình, workload, kết quả được lưu trong báo cáo |

## 13. Bài tập thực hành

Một dịch vụ Java ghi log trạng thái kiện hàng. Các cột:

```text
tenant_id, parcel_id, scan_id, scanned_at, received_at,
site_id, status, payload
```

Yêu cầu nghiệp vụ:

- **R1:** 50 lần quét gần nhất của một kiện trong **một giờ UTC**.
- **R2:** Lịch sử của kiện trong cửa sổ trượt **4 giờ**, tối đa 100 hàng ở API.
- **R3:** Tìm quét `FAILED` của một site trong ngày.
- **R4:** Giữ scan **7 ngày kể từ `scanned_at`**, có thể đến muộn hai ngày.

Dữ liệu thử giả định:

- 1.000 kiện đang hoạt động.
- 10 kiện nóng nhất có **30 scan/giây** trong nhiều giờ; mỗi scan có khoảng **700 B dữ liệu thô**.
- Phần lớn kiện còn lại có lưu lượng thấp.
- 5% scan có timestamp trùng với scan khác trên cùng kiện.
- Một tỷ lệ scan bị replay; dữ liệu cũ hết TTL và có một số DELETE.

**Yêu cầu:**

1. Viết ít nhất hai schema ứng viên: bucket **ngày** và bucket **giờ**, với clustering `(scanned_at DESC, scan_id DESC)`.
2. Viết CQL `SELECT` cho R1 trên cả hai schema và giải thích đầy đủ partition key/range.
3. Tính số hàng và dung lượng thô của **một kiện nóng** theo bucket giờ và ngày, nếu tốc độ 30/s duy trì. Chỉ ra vì sao raw bytes khác SSTable disk bytes.
4. Với một khoảng trượt bốn giờ, tối đa bao nhiêu bucket giờ có thể bị chạm khi khoảng lệch biên? Ứng dụng cần phân trang/hợp nhất thế nào?
5. Thiết kế tối thiểu sáu ca dữ liệu correctness (biên giờ, trùng timestamp, retry, event đến muộn, TTL, xóa).
6. Đề xuất một bảng projection cho R3, nêu điều kiện chọn shard và cách xử lý khi ghi bảng nguồn thành công nhưng bảng phụ thất bại.
7. Thiết kế hai vòng benchmark so A/B với cùng RF, CL, hardware và workload, gồm metric p95/p99, write throughput, tombstone, largest partition, disk headroom.
8. Nêu các tình huống nào bạn sẽ đánh dấu `PASS`, `FAIL` và `NEEDS_MORE_EVIDENCE`; vì sao không chỉ nhìn average latency.

**Gợi ý đối chiếu:**

```text
Ứng viên ngày:
    PRIMARY KEY ((tenant_id, parcel_id, day_bucket),
                 scanned_at, scan_id)

Ứng viên giờ:
    PRIMARY KEY ((tenant_id, parcel_id, hour_bucket),
                 scanned_at, scan_id)

Một kiện nóng 30 scan/s:
    1 giờ = 30 × 3.600 = 108.000 scan
    raw 1 giờ = 108.000 × 700 B = 75,6 MB
    1 ngày = 30 × 86.400 = 2.592.000 scan
    raw 1 ngày = 2.592.000 × 700 B = 1.814,4 MB ≈ 1,81 GB

Cửa sổ trượt 4 giờ:
    Có thể giao với tối đa 5 bucket giờ nếu lệch biên.

Retention:
    Scan đến muộn 2 ngày còn khoảng 5 ngày TTL
    nếu policy là 7 ngày kể từ scanned_at.
```

Một candidate chỉ được xem là đạt khi **trả đúng kết quả** và **thỏa ngưỡng đọc/ghi trên dữ liệu đại diện**, bao gồm tải lệch, tombstone, retry và khả năng chịu lỗi được yêu cầu. Không nên chọn bucket chỉ từ phép tính dung lượng thô; cần đo cả hot partition, fan-out và trạng thái compaction.

## Kết luận

Kiểm chứng mô hình Cassandra là một quy trình liên kết **hợp đồng truy vấn → CQL cụ thể → dữ liệu đại diện → workload có kiểm soát → số liệu đọc/ghi → quyết định có căn cứ**. Khóa phân vùng và clustering quyết định đường đọc, nhưng schema chỉ được xem là phù hợp khi kết quả đúng, partition nóng nhất vẫn đáp ứng SLA, TTL/tombstone không làm hiệu năng suy thoái và hệ thống chịu được lỗi trong phạm vi đã cam kết. Đừng dùng vài hàng mẫu, một câu `LIMIT` hay độ trễ trung bình để thay cho bằng chứng. Hãy giữ báo cáo tái lập được, có ngưỡng chấp nhận và nêu rõ những phần chưa kiểm chứng trước khi đưa mô hình vào sản xuất.
