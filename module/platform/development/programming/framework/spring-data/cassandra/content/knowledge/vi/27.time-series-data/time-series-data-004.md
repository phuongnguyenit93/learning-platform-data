# Ước lượng kích thước nhóm dữ liệu theo tốc độ ghi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **time bucket**, **partition**, **partition key**, **clustering key**, sharding và cách các khái niệm này liên quan tới dữ liệu chuỗi thời gian trong Apache Cassandra.
- Tính số hàng trong một partition từ tốc độ ghi trên **một stream**, số giây trong bucket và số shard; phân biệt tốc độ trung bình, giờ cao điểm và burst.
- Ước lượng dung lượng logic/on-disk bằng kích thước row đo được, metadata, compression, hệ số dự phòng; không coi một kích thước partition mục tiêu là giới hạn chính thức của Cassandra.
- Tính thời gian bucket phù hợp với ngân sách kích thước và giới hạn tải, đồng thời hiểu khi nào bucket thời gian **không** giải quyết hot partition.
- Phân biệt dung lượng một bucket, tổng dung lượng retained data, replication factor, overhead compaction/repair và dung lượng cần cấp phát.
- Thiết kế bảng time-series theo truy vấn với partition key `((tenant_id, device_id, bucket_start), event_time, event_id)` và clustering order.
- Kết hợp TTL, TWCS, xử lý sự kiện trễ, late writes, timestamp, paging, read amplification và Spring Data Cassandra vào quyết định sizing.
- Tạo worksheet dự báo, kiểm tra bằng số đo thực, rồi điều chỉnh bucket/shard an toàn khi tốc độ ghi hoặc độ rộng dữ liệu thay đổi.

Bài nằm trong chương **Dữ liệu thời gian** của **SPRING_DATA_CASSANDRA**. Mô-đun học cách truy cập Apache Cassandra qua Spring Data Cassandra entity mapping, repository, `CassandraTemplate` và CQL, đồng thời thiết kế bảng theo truy vấn, partition key, consistency, paging và kiểm soát hiệu năng trong hệ phân tán. Với Cassandra, đưa bucket vào partition key là **quyết định phân bố dữ liệu**, không chỉ là định dạng thời gian.

> **Nguyên tắc:** Sizing phải bắt đầu bằng **tốc độ ghi của một logical stream/partition**, không nhầm tốc độ ghi toàn cluster với tốc độ ghi của một partition. Công thức là phương án sàng lọc ban đầu; muốn vận hành cần đo kích thước hàng/partition, phân bố tải và p95/p99 thực tế.

## 1. Bài toán time-series: khi một partition tăng không giới hạn

Giả sử hệ thống IoT có các event:

~~~json
{
  "tenantId": "tenant-a",
  "deviceId": "sensor-42",
  "eventId": "11111111-1111-4111-8111-111111111111",
  "eventTime": "2026-11-25T10:00:15.123Z",
  "temperature": 29.5,
  "humidity": 66.1,
  "status": "OK"
}
~~~

Các đường đọc chính là: lấy **50 mẫu mới nhất** của một thiết bị; tìm các mẫu trong khoảng 10:00–11:00; giữ dữ liệu 7–30 ngày; hỗ trợ một số cảm biến có tốc độ ghi vượt xa mức bình thường.

Một bảng ngây thơ:

~~~sql
CREATE TABLE readings_by_device_unbounded (
    tenant_id text,
    device_id text,
    event_time timestamp,
    event_id uuid,
    temperature double,
    humidity double,
    PRIMARY KEY ((tenant_id, device_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
~~~

Với khóa `(tenant_id, device_id)`, mọi event của thiết bị nằm trong **một partition**. Khi dữ liệu tăng lâu ngày, partition quá rộng có thể ảnh hưởng đường đọc, compaction, repair, streaming và quản lý tombstone. Xóa một phần dữ liệu bằng TTL không tự bảo đảm partition trên đĩa lập tức nhỏ trở lại.

### 1.1. Đưa bucket vào partition key

Thay bằng:

~~~sql
CREATE TABLE readings_by_device_bucket (
    tenant_id text,
    device_id text,
    bucket_start timestamp,
    event_time timestamp,
    event_id uuid,
    temperature double,
    humidity double,
    status text,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_start),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
~~~

Mỗi `(tenant_id, device_id, bucket_start)` là **một partition khác nhau**. Trong partition, dữ liệu được sắp theo `event_time` và `event_id` giảm dần, phù hợp lấy mẫu gần nhất khi đã biết bucket.

Nếu `bucket_start` chỉ là **cột thường** mà không có trong partition key, nó không chia partition. Nếu muốn chia đồng thời một bucket thành nhiều partition, cần thêm `shard_id` vào **partition key**, kèm cơ chế định tuyến/merge.

### 1.2. Query quyết định mô hình

| Đường đọc | Thiết kế phù hợp |
| --- | --- |
| Mẫu mới nhất của thiết bị | Đọc bucket hiện tại, khi thiếu thì lùi về bucket trước |
| Lịch sử một thiết bị trong khoảng thời gian | Xác định các bucket giao với khoảng, query trong từng partition |
| Dashboard tổng của hàng nghìn thiết bị | Bảng aggregate/read model riêng, không quét toàn bảng sự kiện |
| Tra cứu event ID khi chỉ biết ID | Bảng lookup theo ID hoặc đường truy cập riêng |
| Lịch sử có nhiều shards/bucket | Hợp nhất, sắp xếp và giữ cursor theo nguồn ở tầng ứng dụng |

Bucket quá lớn có nguy cơ wide partition; bucket quá nhỏ khiến đọc một giờ phải mở rất nhiều partitions. **Chọn bucket đồng thời theo ghi và đọc**.

## 2. Các đại lượng và công thức sizing

| Ký hiệu | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `λ_stream` | event/giây | Tốc độ ghi của **một device/stream** |
| `λ_peak` | event/giây | Tốc độ đỉnh của stream trong khoảng cần bảo vệ |
| `T` | giây | Độ dài một time bucket |
| `K` | partition/bucket | Số shard đang nhận ghi cho stream trong bucket |
| `S_row` | byte/row | Kích thước row logic hoặc on-disk, phải ghi rõ loại |
| `F` | hệ số | Hệ số dự phòng/ước lượng do nhóm hiệu chỉnh bằng đo đạc |
| `N_p` | row/partition | Số row dự kiến một partition |
| `B_p` | byte/partition | Dung lượng dự kiến của một partition |
| `RF` | số bản sao | Replication factor trong topology cụ thể |
| `R` | ngày | Thời gian lưu dữ liệu |

### 2.1. Công thức số hàng

Với routing đồng đều vào `K` shard:

\[
N_{\text{bucket}} \approx \lambda_{\text{stream}}\times T
\]

\[
N_{\text{partition}} \approx
\frac{\lambda_{\text{stream}}\times T}{K}
\]

Đối với đỉnh tải:

\[
N_{\text{partition,peak}} \approx
\frac{\lambda_{\text{peak}}\times T}{K}
\]

Diễn giải:

~~~text
rowsPerBucket = eventsPerSecondPerStream * secondsPerBucket
rowsPerPartition = rowsPerBucket / shardCount
peakRowsPerPartition = peakEventsPerSecond * secondsPerBucket
                       / shardCount
~~~

**Điều kiện:** Phép chia cho `K` chỉ đáng tin khi sharding thực tế cân bằng. Nếu một shard nhận 70% traffic, kích thước partition nóng có thể lớn hơn dự báo chia đều nhiều lần. Nên thống kê shard có p95/p99 write count cao nhất.

### 2.2. Công thức dung lượng

Nếu đo `S_on_disk` là kích thước trung bình hiệu dụng của một row trên đĩa:

\[
B_p \approx N_p\times S_{\text{on-disk}}
\]

Nếu `S_row` chỉ là payload/ước lượng logic:

\[
B_{\text{planning,peak}}\approx
\frac{\lambda_{\text{peak}}\times T}{K}
\times S_{\text{logical row}}\times F
\]

`F` **không phải hằng số do Cassandra quy định**. Metadata per cell, số cột, kích thước key, compression, độ rộng UDT/collection, tombstone và sự biến thiên của payload đều ảnh hưởng. Compression có thể làm on-disk bytes nhỏ hơn logical bytes, trong khi overhead/tombstone có thể làm nó lớn hơn. Sizing production phải đo row/partition thật để chọn `F`.

Đặc biệt, cần phân biệt:

- **Logical payload bytes** trong ứng dụng.
- **Bytes của một partition đã đo** tại thời điểm kiểm tra.
- **SSTable disk footprint** có thể chứa dữ liệu cũ/tombstone/overhead.
- **Transient disk usage** trong flush/compaction/repair/streaming.
- **Replicated bytes** của toàn bộ DC/cluster.

### 2.3. Quy đổi bucket

| Khoảng bucket | `T` (giây) | Bucket/ngày |
| --- | ---: | ---: |
| 10 giây | 10 | 8.640 |
| 30 giây | 30 | 2.880 |
| 1 phút | 60 | 1.440 |
| 2 phút | 120 | 720 |
| 5 phút | 300 | 288 |
| 15 phút | 900 | 96 |
| 1 giờ | 3.600 | 24 |
| 1 ngày UTC | 86.400 | 1 |

Bucket “một tháng” có độ dài thay đổi theo lịch. Bucket theo **ngày địa phương** có thể bị ảnh hưởng bởi daylight saving time ở một số timezone; để sizing theo giây cố định, dùng UTC bucket hoặc định nghĩa rõ contract.

## 3. Ví dụ cụ thể: thiết bị gửi 120 event/giây

Giả sử một stream có:

~~~text
Average rate/device:     120 event/giây
Peak rate/device:        360 event/giây (3x)
Estimated logical row:   420 byte
Planning factor F:       1,5 (giả định minh họa)
Shard count K:           1
Target planning size:    16.000.000 byte/partition
~~~

**16 MB chỉ là mục tiêu giả định của một dự án**, không phải ngưỡng tối đa phổ quát của Apache Cassandra. Phải định nghĩa target bằng benchmark, nhu cầu đọc, GC/I/O, repair/compaction, cấu hình và kiến trúc thật.

### 3.1. Bucket 10 phút

`T = 600` giây:

~~~text
Average rows = 120 * 600 = 72.000
Peak rows    = 360 * 600 = 216.000

Average logical bytes = 72.000 * 420 = 30.240.000 B (~30,24 MB)
Peak logical bytes    = 216.000 * 420 = 90.720.000 B (~90,72 MB)
Peak planned bytes    = 90.720.000 * 1,5
                      = 136.080.000 B (~136,08 MB)
~~~

Bucket 10 phút vượt mục tiêu ví dụ; không hợp với ngân sách 16 MB nếu thực sự có peak như giả định.

### 3.2. Bucket 2 phút

`T = 120` giây:

~~~text
Average rows = 120 * 120 = 14.400
Peak rows    = 360 * 120 = 43.200

Average planned bytes = 14.400 * 420 * 1,5
                      = 9.072.000 B (~9,07 MB)
Peak planned bytes    = 43.200 * 420 * 1,5
                      = 27.216.000 B (~27,22 MB)
~~~

Theo trung bình bucket 2 phút có vẻ đủ, nhưng ở peak nó vượt mục tiêu. **Chỉ dùng write-rate trung bình là một lỗi sizing thường gặp.**

### 3.3. Bucket 1 phút

`T = 60` giây:

~~~text
Average rows = 120 * 60 = 7.200
Peak rows    = 360 * 60 = 21.600

Average planned bytes = 7.200 * 420 * 1,5
                      = 4.536.000 B (~4,54 MB)
Peak planned bytes    = 21.600 * 420 * 1,5
                      = 13.608.000 B (~13,61 MB)
~~~

Theo các **giả định** trên, bucket 1 phút thỏa target 16 MB. Nhưng đó mới là ứng viên thử nghiệm: burst thực tế có thể cao hơn 3x, row p99 có thể rộng hơn, và 360 writes/s vào **cùng một partition** có thể tạo hotspot.

### 3.4. Tính ngược độ dài bucket

Với mục tiêu `B_max`:

\[
T_{\max}\approx\frac{B_{\max}K}
{\lambda_{\text{peak}}\times S_{\text{logical row}}\times F}
\]

Trong ví dụ `K=1`:

~~~text
T_max = 16.000.000 / (360 * 420 * 1,5)
      ≈ 70,55 giây
~~~

Chọn 60 giây để thử, thay vì làm tròn lên 120 giây khi target được dùng như giới hạn dự báo. Có thể giảm bucket hoặc thêm shards, nhưng đổi lại làm tăng số partition phải truy vấn.

### 3.5. Bốn kiểu bất định của phép tính

1. **Peak window:** Số đo peak một phút khác burst peak trong một giây; bucket có thể hứng burst lệch phân bố.
2. **Row width:** Payload 420 byte trung bình không bảo vệ trước giá trị 5 KB p99, collection lớn hoặc fields tùy chọn.
3. **Hot key:** Dung lượng 13 MB không chứng minh 360 writes/s trên partition đáp ứng p99.
4. **Read pattern:** 60 buckets/giờ có thể làm API đọc một giờ tốn nhiều round-trip so với 6 buckets/giờ.

## 4. Kích thước partition không đồng nghĩa throughput partition

Hai partition cùng 10 MB nhưng một partition tích lũy 10 MB trong 24 giờ, partition khác tích lũy chỉ trong 20 giây sẽ có tải ghi rất khác nhau.

### 4.1. Time bucket không chia concurrent writes

Với khóa `(tenant_id, device_id, bucket_start)`, mọi event của thiết bị tại 10:05 vẫn ghi vào **bucket đang hoạt động**. Khi sang 10:06, ghi chuyển sang partition tiếp theo; partition 10:05 không được chia nhỏ trong thời gian nó còn active.

Muốn phân phối **đồng thời**, cần thêm shard:

~~~sql
PRIMARY KEY (
    (tenant_id, device_id, bucket_start, shard_id),
    event_time, event_id
)
~~~

và routing shard được kiểm chứng bằng metrics. Nếu đã có hàng trăm nghìn device, mỗi device chậm, việc thêm shards có thể chỉ làm số partition và công việc đọc tăng mà không cải thiện throughput.

### 4.2. Sharding làm đọc khó hơn

Một yêu cầu “50 sự kiện mới nhất” trên 8 shards có thể cần:

1. Query một số row đầu từ **từng shard**.
2. Merge theo `(event_time, event_id)`.
3. Giữ tiến độ/cursor cho các shard để phân trang.
4. Giới hạn fan-out, số query đồng thời, bytes giải mã.
5. Kiểm soát timestamp trùng nhau, late arrivals và page boundaries.

Cassandra chỉ sắp theo clustering columns **trong một partition**, không có một global ORDER BY giữa các shards/buckets. Sharding là đánh đổi write scalability lấy read complexity.

## 5. Tổng dung lượng cluster phải tính riêng

### 5.1. Logical retained data

Với `λ_total` là **tốc độ ingest toàn hệ thống** và `R` ngày:

\[
N_{\text{total}} \approx \lambda_{\text{total}}\times 86\,400\times R
\]

\[
B_{\text{logical}}\approx N_{\text{total}}\times S_{\text{logical row}}
\]

Ví dụ có **50.000 devices**, mỗi device gửi trung bình **1 event/5 giây**:

~~~text
Device rate             = 0,2 event/s
Total rate              = 50.000 * 0,2 = 10.000 event/s
Row logical size        = 400 B
Retention               = 7 ngày

Events/day              = 10.000 * 86.400
                        = 864.000.000 events

Logical bytes/day       = 864.000.000 * 400
                        = 345.600.000.000 B (~345,6 GB)

Logical bytes/7 days    = 2.419.200.000.000 B (~2,42 TB)
~~~

Nhưng mỗi **partition theo device và giờ** chỉ nhận:

~~~text
0,2 * 3.600 = 720 events/giờ/device
720 * 400 = 288.000 B (~0,288 MB logical/partition)
~~~

Nếu nhầm 10.000 events/s của toàn cluster là 10.000 events/s của **một device**, ước lượng partition sẽ sai hàng chục nghìn lần.

### 5.2. RF là hệ số nhân dung lượng vật lý, không nhân size partition logic

Trong một DC có `RF=3`, nếu tạm **bỏ qua compression/overhead**:

~~~text
Logical retained payload ~2,42 TB
Replicated payload       ~2,42 * 3 = 7,26 TB
~~~

Đây chưa phải dung lượng disk phải cấp. Một ước lượng tốt hơn cần đo hệ số on-disk:

\[
B_{\text{replicated}}\approx
B_{\text{logical}}\times C_{\text{storage}}\times RF
\]

`C_storage` là tỷ lệ on-disk bytes mỗi replica so với logical payload, có thể lớn hoặc nhỏ hơn 1. Cần cộng dự phòng cho flush/compaction/repair, snapshots, dữ liệu TTL chưa được dọn và node failure/streaming. Không có hệ số mặc định đúng cho mọi cụm.

### 5.3. Partition sizing khác capacity sizing

~~~text
Partition sizing:
  λ per stream × bucket duration ÷ shard count × effective row bytes

Cluster capacity sizing:
  total ingest × retention × effective storage bytes × RF
  + compaction/repair/snapshot headroom

Query sizing:
  buckets touched × shards × page requests × row width
  + network/serialization and concurrency
~~~

Một quyết định bucket tốt phải thỏa **cả ba** góc nhìn.


## 6. Thiết kế bảng time-series theo partition key và bucket

Với access pattern “50 sự kiện mới nhất của một thiết bị”, dùng:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.readings_by_device_bucket (
    tenant_id text,
    device_id text,
    bucket_start timestamp,
    event_time timestamp,
    event_id uuid,
    temperature double,
    humidity double,
    status text,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_start),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
~~~

`dc1` và RF=3 chỉ là ví dụ, phải thay bằng topology thật. Mỗi `(tenant_id, device_id, bucket_start)` là một partition; `event_time, event_id` tạo thứ tự bên trong partition.

### 6.1. Truy vấn có đầy đủ partition key

~~~sql
SELECT event_time, event_id, temperature, humidity
FROM telemetry.readings_by_device_bucket
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_start = ?
LIMIT 50;
~~~

Với một khoảng trong cùng bucket:

~~~sql
SELECT event_time, event_id, temperature
FROM telemetry.readings_by_device_bucket
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_start = ?
  AND event_time >= ?
  AND event_time < ?;
~~~

Nếu khoảng cắt qua nhiều bucket, service phải tính từng bucket, query riêng và merge theo timestamp. Cassandra không tự có global `ORDER BY` giữa các partitions. Nếu cần 50 event mới nhất mà bucket hiện tại chưa đủ, lùi tiếp bucket cũ thay vì quét toàn bảng.

### 6.2. Cần event_id bên cạnh event_time

Cột CQL `timestamp` giữ độ phân giải **milliseconds**. Nhiều event có thể cùng một millisecond; nếu chỉ `event_time` là clustering key thì primary key trùng và có thể upsert lên cùng row. `event_id` là tie-breaker để row khác nhau không đè nhau và để cursor có thứ tự xác định. Nếu retry tạo UUID khác cho cùng event logic, vẫn có nguy cơ lưu duplicate; ID phải ổn định khi nguồn hỗ trợ.

## 7. Tính bucket_start ổn định bằng Java

~~~java
import java.time.Instant;

public final class BucketTime {
    private BucketTime() {}

    public static Instant start(
            Instant eventTime,
            long bucketSeconds) {

        if (bucketSeconds <= 0) {
            throw new IllegalArgumentException(
                "bucketSeconds must be positive");
        }

        long epochSeconds = Math.multiplyExact(
            Math.floorDiv(eventTime.getEpochSecond(), bucketSeconds),
            bucketSeconds
        );

        return Instant.ofEpochSecond(epochSeconds);
    }
}
~~~

~~~java
Instant t = Instant.parse("2026-11-25T10:05:47.123Z");

Instant minute = BucketTime.start(t, 60L);
// 2026-11-25T10:05:00Z

Instant fiveMinutes = BucketTime.start(t, 300L);
// 2026-11-25T10:05:00Z

Instant hour = BucketTime.start(t, 3600L);
// 2026-11-25T10:00:00Z
~~~

`Math.floorDiv` giúp xử lý đúng thời điểm âm trước Unix epoch, `Math.multiplyExact` phát hiện overflow. Mọi writer/reader phải dùng cùng thuật toán bucket, timezone và version; khi đổi độ dài bucket, dữ liệu ở khóa cũ **không tự di chuyển**.

### 7.1. Event time hay ingest time?

~~~text
eventTime = 10:00:15 UTC
ingestTime = 10:04:10 UTC (đến trễ)
~~~

Nếu bucket theo `eventTime`, lịch sử theo thời điểm xảy ra dễ truy vấn nhưng late event ghi vào partition cũ, có thể làm phức tạp TTL/TWCS. Nếu bucket theo `ingestTime`, ghi thường theo thứ tự nhận nhưng query theo event time cần biết khoảng chênh lệch hoặc read model riêng. Định nghĩa lateness SLA và quy tắc xử lý backfill.

### 7.2. Tránh nhầm millis và micros

CQL `timestamp` lưu epoch milliseconds; `USING TIMESTAMP` và `WRITETIME` của mutation dùng epoch microseconds. Nếu lấy micros đưa vào `Instant.ofEpochMilli`, bucket có thể nằm rất xa tương lai.

~~~java
// SAI nếu writeTimeMicros là microseconds:
Instant wrong = Instant.ofEpochMilli(writeTimeMicros);

// Đổi microseconds đúng sang Instant:
Instant correct = Instant.ofEpochSecond(
    Math.floorDiv(writeTimeMicros, 1_000_000L),
    Math.floorMod(writeTimeMicros, 1_000_000L) * 1_000L
);
~~~

Một bucket sai là sai **địa chỉ partition**, không chỉ sai ngày trong giao diện.

## 8. Bucket quá ngắn cũng gây chi phí đọc

| Time bucket | Partition/giờ/device | Nhận xét |
| --- | ---: | --- |
| 10 giây | 360 | Row/partition nhỏ, read fan-out lớn |
| 1 phút | 60 | Phù hợp một số stream nhanh, read range dài tốn query |
| 5 phút | 12 | Giảm fan-out, size tăng |
| 15 phút | 4 | Thuận lợi đọc, có thể vượt target size |
| 1 giờ | 1 | Dễ query một giờ, có nguy cơ wide/hot partition |

Mục tiêu sizing nên kiểm tra đồng thời **bytes/partition**, **rows/partition**, **writes/s của hot partition** và **p99 khi đọc số bucket/shard thật**. Không coi một ngưỡng byte bất kỳ là tiêu chuẩn cố định của Cassandra.

Một stream có event mỗi phút và bucket một phút tạo khoảng **43.200 partition trong 30 ngày**. Nếu có 50.000 devices hoạt động như vậy, có thể là **2,16 tỷ logical partitions** trước replication. Vì vậy thiết bị chậm có thể phù hợp bucket giờ/ngày, thiết bị nhanh mới cần bucket phút hoặc shards. Khi dùng nhiều tiers, ứng dụng phải biết policy/phiên bản bucket của dữ liệu cũ.

**Đo peak theo cửa sổ:** peak một giây, một phút và một giờ không tương đương. Tốt nhất đo số event tối đa/p95/p99 rơi vào **cửa sổ T thực sự** thay vì nhân peak một giây ngắn ngủi với thời gian một giờ hoặc bỏ qua burst bằng average toàn ngày.

## 9. TTL và retention

Ví dụ giữ dữ liệu bảy ngày:

~~~sql
ALTER TABLE telemetry.readings_by_device_bucket
WITH default_time_to_live = 604800;
~~~

TTL đo bằng **giây**. Nó không phải lệnh “đến cuối ngày thứ bảy thì xóa ngay cả partition”. Khi hết hạn, row/cell có thể để lại tombstones; compaction, repair và snapshots quyết định khi nào bytes vật lý được thu hồi.

Nếu một event xảy ra **sáu ngày trước** nhưng mới được ingest hôm nay, TTL bảy ngày tính từ ghi có thể làm event sống tới **13 ngày kể từ event time**. Nếu hợp đồng retention tính theo event time, phải tính TTL còn lại hoặc loại/archive event đã quá hạn. TTL không tự trùng với ranh giới bucket.

Giảm `gc_grace_seconds` bừa để thu hồi đĩa nhanh có thể gây rủi ro tombstone/repair. Capacity plan phải tính dữ liệu hết hạn chưa compact, backup và transient disk footprint.

## 10. TWCS không phải time bucket trong primary key

TimeWindowCompactionStrategy (TWCS) nhóm SSTables theo các cửa sổ compaction, không tạo partitions, không tự tính `bucket_start`.

~~~sql
ALTER TABLE telemetry.readings_by_device_bucket
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
~~~

Một table có bucket **một phút** có thể dùng TWCS window **một ngày**. Hai “cửa sổ” cần tối ưu độc lập dựa trên retention, số SSTables, flush, TTL, late arrivals và I/O.

TWCS có thể hữu ích cho workload gần append-only, TTL tương đối đồng đều, các SSTables có expiry gần nhau. Nhưng late/backfill ghi nhiều dữ liệu cũ xen với mới, TTL không đồng đều, timestamp tùy chỉnh và repair/compaction có thể giảm hiệu quả thu hồi dữ liệu. Không mặc định “TTL hết là disk giảm ngay” và không đổi compaction strategy trên production khi chưa benchmark.


## 11. Worksheet sizing cho từng nhóm thiết bị

Không nên cấp một độ dài bucket cho mọi thiết bị dựa trên average toàn fleet. Ghi lại một dòng cho mỗi nhóm nguồn ghi:

| Biến | Ví dụ fast-sensor | Nguồn đo |
| --- | --- | --- |
| Device count | 4.000 | Inventory |
| Average event/s/device | 120 | Ingest metrics theo key |
| Sustained peak event/s/device | 360 | Sliding-window rates |
| Logical bytes/row | 420 B | Event fixture |
| Row size p95/p99 | 700 B / 1.200 B | Payload/storage sampling |
| Bucket seconds | 60 | Phương án sizing |
| Shards | 1 | Routing policy |
| Planning factor | 1,5 | Giả định cần hiệu chỉnh |
| Target bytes/partition | 16 MB | SLO và benchmark |
| Peak rows/partition | 21.600 | `360 × 60 / 1` |
| Peak planned size | 13,608 MB | `21.600 × 420 × 1,5` |
| Retention | 7 ngày | Business SLA |
| RF/DC | 3 tại dc1 | Keyspace metadata |
| Read pattern | Latest 50, range 1 giờ | API |
| Late arrivals | Thường dưới 10 phút | Pipeline metrics |

Phải phân biệt **dữ liệu đã đo** với **giả định**. Nếu row p99 lớn gấp ba average, thiết kế chỉ theo 420 byte có thể kém an toàn. Cần dự báo cho normal, busy, peak và tăng trưởng tương lai.

### 11.1. Estimator Java có kiểm tra đầu vào

~~~java
public final class BucketEstimator {
    private BucketEstimator() {}

    public record Estimate(
        double rowsPerPartition,
        double plannedBytes,
        double plannedMegabytes
    ) {}

    public static Estimate estimate(
            double peakEventsPerSecond,
            long bucketSeconds,
            long bytesPerLogicalRow,
            double factor,
            int shards) {

        if (!Double.isFinite(peakEventsPerSecond)
                || peakEventsPerSecond < 0
                || bucketSeconds <= 0
                || bytesPerLogicalRow <= 0
                || !Double.isFinite(factor)
                || factor <= 0
                || shards <= 0) {
            throw new IllegalArgumentException("Invalid sizing input");
        }

        double rows = Math.ceil(
            peakEventsPerSecond * bucketSeconds / shards
        );
        double bytes = rows * bytesPerLogicalRow * factor;

        return new Estimate(rows, bytes, bytes / 1_000_000.0);
    }

    public static void main(String[] args) {
        Estimate e = estimate(360, 60, 420, 1.5, 1);

        System.out.println(e.rowsPerPartition()); // 21600
        System.out.println(e.plannedMegabytes());   // 13.608
    }
}
~~~

Đây là estimator **gần đúng** dùng `double` cho capacity planning, không phải phép tính kế toán byte chính xác. Với số liệu khổng lồ hoặc tính toán cần kiểm tra overflow, sử dụng `BigDecimal`/checked long và measurement trực tiếp trên môi trường Cassandra.

### 11.2. Bốn kịch bản để kiểm soát sai số

1. **Normal:** average event rate và mean payload.
2. **Busy:** p95 rate theo cửa sổ bucket + payload p95.
3. **Incident/peak:** burst kéo dài, payload p99, replica chậm.
4. **Growth:** thiết bị tăng số lượng, tăng retention, đổi schema/field.

Khi số lượng thiết bị tăng 20 lần nhưng tốc độ từng device không đổi, **logical volume của cluster** có thể tăng khoảng 20 lần, trong khi partition size/device/bucket không nhất thiết tăng. Khi **một device** tăng 100 lần, hotspot và partition sizing đổi ngay cả khi global QPS chưa tăng nhiều.

## 12. Spring Data Cassandra: mapping và tính bucket trước khi ghi

Spring Data ánh xạ entity vào bảng nhưng không tự quyết định bucket nào phù hợp. Service cần tạo khóa nhất quán từ `eventTime` hoặc `ingestTime` đã được xác minh.

### 12.1. Entity với composite primary key

~~~java
import java.time.Instant;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("readings_by_device_bucket")
public class ReadingByDeviceBucket {

    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private String tenantId;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private String deviceId;

    @PrimaryKeyColumn(
        name = "bucket_start", ordinal = 2,
        type = PrimaryKeyType.PARTITIONED
    )
    private Instant bucketStart;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private UUID eventId;

    @Column("temperature")
    private Double temperature;

    @Column("humidity")
    private Double humidity;

    @Column("status")
    private String status;

    public ReadingByDeviceBucket() {}
    // Constructors, getters, setters...
}
~~~

Khi dùng `@PrimaryKeyClass` để đóng gói khóa thay vì nhiều `@PrimaryKeyColumn` trực tiếp, repository ID và converter phải phù hợp với mapping thực tế. Không dùng `UUID` đơn làm toàn bộ ID nếu bảng có khóa ghép gồm tenant/device/bucket/time/event.

### 12.2. Service ghi đúng bucket

~~~java
Instant eventTime = reading.getEventTime();
Instant bucketStart = BucketTime.start(eventTime, 60L);

reading.setBucketStart(bucketStart);
cassandraTemplate.insert(reading);
~~~

Ví dụ giả định entity có getters/setters tương ứng. `CassandraTemplate.insert` hoặc repository `save` không tự chống duplicate event nếu retry dùng event ID hoặc bucket khác. Cần quy ước event ID ổn định và định nghĩa cách xử lý TTL/replay.

### 12.3. Driver 4.x khi cần chủ động consistency và timeout

~~~java
PreparedStatement insert = session.prepare(
    "INSERT INTO telemetry.readings_by_device_bucket " +
    "(tenant_id, device_id, bucket_start, event_time, " +
    "event_id, temperature, humidity, status) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
);

BoundStatement stmt = insert.bind(
    tenantId, deviceId, bucketStart,
    eventTime, eventId, temperature, humidity, status
)
.setConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_QUORUM
)
.setTimeout(Duration.ofSeconds(2))
.setIdempotent(false);

session.execute(stmt);
~~~

Ví dụ dùng Java Driver 4.x với import `DefaultConsistencyLevel`, `BoundStatement`, `PreparedStatement` và `Duration` phù hợp. `LOCAL_QUORUM`/2s chỉ là thông số minh họa, cần chọn theo RF/DC/SLA. Đánh dấu idempotent đúng theo **mutation thật**: ghi cùng primary key không phải luôn an toàn khi có TTL, nhiều writer hoặc payload khác. Timeout sau mutation có kết quả không rõ; không retry bừa rồi tạo event ID mới.

### 12.4. Template đọc một bucket

~~~java
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

Query query = Query.query(
    Criteria.where("tenant_id").is(tenantId)
        .and("device_id").is(deviceId)
        .and("bucket_start").is(bucketStart)
).limit(50);

List<ReadingByDeviceBucket> rows = cassandraTemplate.select(
    query, ReadingByDeviceBucket.class
);
~~~

Đọc nhiều buckets cần lặp partition, hợp nhất sort và quản lý cursor. `setPageSize` của driver điều khiển mỗi fetch, không tương đương `LIMIT` của CQL hay `OFFSET` ngẫu nhiên. Không dùng `PageRequest.of(100,50)` rồi giả định Cassandra tự nhảy đến trang 101.

## 13. Đo đạc thực tế thay vì chỉ dùng công thức

Một kế hoạch staging nên nạp dữ liệu theo **phân bố thật**, không chỉ chạy đều 1 event/s:

1. Dùng cùng schema, compaction/compression options, TTL và row widths.
2. Mô phỏng nhiều nhóm device: chậm, bình thường, hot, burst, late-arriving.
3. Ghi lại rows/bucket và byte payload từ generator.
4. Quan sát histogram partition sizes, SSTables và tombstones qua nhiều chu kỳ flush/compaction.
5. Benchmark last-50 và range 1 giờ khi nhiều bucket/shard.
6. So sánh `B_observed` với `B_planned`; hiệu chỉnh factor, bucket duration hoặc shard policy.
7. Kiểm tra node/DC health, RF, consistency và p95/p99 chứ không chỉ average latency.

### 13.1. Lệnh quan sát tham khảo

~~~text
nodetool tablestats telemetry.readings_by_device_bucket
nodetool tablehistograms telemetry readings_by_device_bucket
nodetool status
~~~

Cú pháp/metrics tùy Cassandra version. `tablestats` và `tablehistograms` hỗ trợ thông tin bảng/histogram, **không tự trả kích thước byte chính xác của một primary key tùy ý**. Không chạy `SELECT COUNT(*)` toàn bảng lớn để “đo bytes”: đó là phép đếm row có thể phải scan tốn kém, không phải phép đo kích thước.

Các metrics nên kết hợp:

| Metric | Công dụng |
| --- | --- |
| Partition size p50/p95/p99, cực trị | Bắt wide partitions, phân bố lệch |
| Cells/rows per partition | Bắt nhiều row nhỏ, metadata overhead |
| Write QPS per device/shard | Bắt hot key và shard skew |
| Read/write latency p95/p99 | Xác minh SLA thực tế |
| SSTable count/compaction pending | Nhìn lifecycle/độ trễ dọn dữ liệu |
| Tombstone warnings/TTL expirations | Đánh giá TTL và đọc lịch sử |
| Disk free, GC/CPU, I/O | Capacity và backpressure |
| Driver retry, timeout, unavailable | Xác định failure pressure |
| Read bucket/shard fan-out | Đo hiệu quả bucket nhỏ |

Không suy kích thước toàn cluster chỉ từ một node/replica khi compaction/repair đang ở các trạng thái khác nhau. Muốn đo có ý nghĩa phải quan sát nhiều node/zone và các khoảng thời gian đại diện.

## 14. Dấu hiệu thiết kế bucket có vấn đề

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| p99 đọc lịch sử tăng | Wide partition, tombstone hoặc quá nhiều partitions | Histogram size, fan-out và SSTables |
| Partition p99 vượt target | Peak/payload cao hơn dự báo | Rate p99, row width, bucket length |
| Write latency tăng ở một device | Hot active bucket | Per-device QPS, sharding benchmark |
| Range một giờ chậm dù bucket nhỏ | Read 60–360 partitions/giờ | Count queries, bytes, concurrency |
| Dữ liệu ở UI bị thiếu | Reader chỉ đọc bucket hiện tại | Lùi các bucket cũ, giữ cursor |
| Cùng timestamp bị ghi đè | Thiếu event ID tie-breaker | Primary key và event identity |
| Event trễ không tìm thấy | Event/ingest time policy khác nhau | Bucket calculation/lateness |
| Đĩa không giảm sau TTL | Tombstone/compaction/snapshot | Disk và TWCS metrics |
| Ngày/tháng bucket sai | Epoch ms/µs hoặc timezone | Trace input Instant và key |
| Đổi độ dài bucket làm mất lịch sử | Reader chỉ hiểu policy mới | Version hóa/dual-read |

## 15. Đổi bucket khi tốc độ ghi thay đổi

Ví dụ thiết bị ban đầu 0,2 event/s dùng bucket giờ; sau đó một nhóm tăng lên 200 event/s và bucket giờ vượt ngân sách. **Không** chỉ đổi hằng số `bucketSeconds=3600` sang `60` rồi kỳ vọng dữ liệu cũ vẫn đọc được.

Quy trình kiểm soát:

1. Phân loại device/tenant bị ảnh hưởng và chọn tier mới theo metrics.
2. Version hóa bucket policy theo giai đoạn hiệu lực hoặc tạo bảng v2 nếu thay layout primary key.
3. Writer dùng policy mới từ cutover có kiểm soát.
4. Reader hỗ trợ cả buckets cũ và mới trong retention window.
5. Nếu cần, backfill/dual-write có event ID ổn định, chống duplicate và đối soát.
6. Giới hạn workload backfill, đo disk/compaction/streaming.
7. Test đúng ranh giới cutover, late event, UTC bucket, cursor/paging.
8. Chỉ loại bỏ đường đọc cũ khi dữ liệu cũ đã hết hạn hoặc đã migrate đầy đủ.

Khi dual-read hai bảng, một event có thể xuất hiện hai lần và cần dedup theo event ID. Khi dual-write, một bên thành công một bên lỗi cần replay/compensation; batch Cassandra không tự là transaction end-to-end cho mọi read models.

## 16. Bài thực hành sizing và test

### 16.1. Bài tập A: bucket 5 phút

Một device ghi **50 event/s** trung bình, **200 event/s peak**, payload **600 B/row**, factor **1,4**, không shard. Bucket 5 phút:

~~~text
T = 300 s
Peak rows = 200 * 300 = 60.000
Planned bytes = 60.000 * 600 * 1,4
              = 50.400.000 B (~50,4 MB)
~~~

Nếu target **20 MB**/partition (mục tiêu ví dụ):

~~~text
T_max = 20.000.000 / (200 * 600 * 1,4)
      ≈ 119,05 s
~~~

Bucket 60 giây là ứng viên an toàn hơn target; 120 giây nằm sát/vượt dự báo. Nhưng phải đo hot partition throughput và read fan-out trước khi chốt.

### 16.2. Bài tập B: sharding

Nếu muốn giữ bucket 5 phút với budget 20 MB:

~~~text
Required shards >= ceil(50,4 / 20) = 3
~~~

Ba shards cân bằng có thể giảm kích thước dự kiến mỗi partition, nhưng API đọc một giờ có thể phải query **12 buckets × 3 shards = 36 partitions** trước khi merge. Shard không tự giảm tổng bytes hoặc khử trùng duplicate events.

### 16.3. Unit test ranh giới bucket

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class BucketTimeTest {
    @Test
    void minuteBucketsHaveHalfOpenBoundaries() {
        assertEquals(
            Instant.parse("2026-11-25T10:05:00Z"),
            BucketTime.start(
                Instant.parse("2026-11-25T10:05:59.999Z"), 60L)
        );

        assertEquals(
            Instant.parse("2026-11-25T10:06:00Z"),
            BucketTime.start(
                Instant.parse("2026-11-25T10:06:00Z"), 60L)
        );
    }

    @Test
    void handlesPreEpochTime() {
        assertEquals(
            Instant.parse("1969-12-31T23:59:00Z"),
            BucketTime.start(
                Instant.parse("1969-12-31T23:59:59Z"), 60L)
        );
    }
}
~~~

Đoạn trên minh họa cách kiểm tra hàm thuần, không phải test đã chạy trong nhiệm vụ STEP_4 này. Integration test Cassandra vẫn cần để xác minh CQL mapping, payload, latency, TTL, TWCS và driver paging.

### 16.4. Ma trận test production-like

| Ca | Kỳ vọng |
| --- | --- |
| Event tại 10:05:59.999 và 10:06:00 | Chuyển bucket đúng |
| Hai events trùng millisecond | Event ID phân biệt rows |
| Device có peak gấp 3 average | Kích thước/latency vẫn trong target |
| Một burst 1 giây cực lớn | Không làm partition active quá tải |
| Payload p99 rộng | Factor/estimate được hiệu chỉnh |
| Device chậm dùng bucket phút | Overhead partition count được đánh giá |
| 4 shards/bucket | Routing đều, merge/cursor đúng |
| Event đến trễ 20 phút | Theo đúng event-time/ingest-time contract |
| UTC vs local time | Cùng Instant tạo key nhất quán |
| RF3, một replica chậm | Latency/availability theo CL |
| TTL hết hạn | Không kỳ vọng xóa disk tức thì |
| TWCS + backfill | Có số đo SSTables/compaction |
| Change bucket policy | Đọc được dữ liệu cả trước và sau cutover |

## 17. Những ngộ nhận thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Global 10.000 event/s là rate của một partition.” | Phải đo **rate theo stream/key**. |
| “Average đủ để chọn bucket.” | Peak, burst, heavy-tailed payload quan trọng. |
| “Bucket càng nhỏ càng tốt.” | Partition count và read fan-out có thể tăng mạnh. |
| “Bucket phút tự giải hot write.” | Active bucket vẫn là một key nếu không shard. |
| “Thêm shard làm tổng data nhỏ hơn.” | Shard phân bố dữ liệu, thường tăng metadata/read complexity. |
| “420B JSON bằng 420B SSTable.” | Compression, metadata, tombstones ảnh hưởng. |
| “RF3 làm một logical partition có ba lần row.” | RF tạo bản sao vật lý. |
| “TTL hết là disk giảm ngay.” | Compaction/tombstone/snapshot lifecycle riêng. |
| “TWCS window phải bằng time bucket.” | Hai cơ chế độc lập. |
| “Partition nhỏ luôn có p99 tốt.” | Hot writes/replicas/read fan-out vẫn quan trọng. |
| “Đổi bucketSeconds không ảnh hưởng dữ liệu cũ.” | Primary key cũ vẫn giữ địa chỉ cũ. |
| “COUNT(*) đo dung lượng partition.” | Count không phải bytes và có thể scan đắt. |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `λ_stream` quan trọng hơn `λ_total` khi tính một partition?

*Gợi ý:* Mỗi partition nhận traffic của một khóa logic, không của toàn cluster.

**Câu 2.** Công thức số row với `K` shards cân bằng là gì?

*Đáp án:* `λ × T / K`.

**Câu 3.** 360 event/s với bucket 60 giây tạo bao nhiêu row?

*Đáp án:* 21.600 row nếu peak được duy trì cả phút.

**Câu 4.** 21.600 row × 420 B × 1,5 là bao nhiêu?

*Đáp án:* 13.608.000 B, khoảng 13,61 MB.

**Câu 5.** Vì sao một bucket 1 phút không tự phân phối 360 writes/s tới nhiều partitions?

*Gợi ý:* Cùng device và thời gian đó có cùng bucket key.

**Câu 6.** Thêm 3 shards làm phát sinh đánh đổi gì?

*Gợi ý:* Đọc phải fan-out/merge nhiều partition.

**Câu 7.** RF=3 ảnh hưởng logical row count hay replicated disk footprint?

*Đáp án:* Replicated disk footprint, không làm row logic nhân ba.

**Câu 8.** TWCS window có bắt buộc bằng độ dài time bucket không?

*Đáp án:* Không.

**Câu 9.** Một event xảy ra sáu ngày trước mới ghi hôm nay, TTL mặc định bảy ngày có giữ nó tới sau event time + 7 ngày không?

*Gợi ý:* Có thể, vì TTL gắn với write/expiry semantics; cần late-event policy.

**Câu 10.** Khi đổi bucket một giờ sang một phút cần xử lý gì?

*Gợi ý:* Version policy và đọc/migrate khóa cũ.

## 19. Checklist production

- **Queries:** Biết last-N, time range, aggregation và phân trang mong muốn.
- **Per-key rate:** Có p50/p95/p99, peak/burst theo device, không chỉ total QPS.
- **Row width:** Đo logical/on-disk bytes và các phân vị kích thước.
- **Bucket:** Tính bytes/rows theo `λ × T / K` bằng đúng đơn vị.
- **Hot key:** Benchmark writes/s vào partition active; shard nếu cần.
- **Read fan-out:** Đo số buckets/shards và p99 của query khoảng dài.
- **Global capacity:** Kết hợp retention, RF, compression, compaction/repair/snapshot headroom.
- **Time basis:** Thống nhất UTC, event time/ingest time, late arrival.
- **Clustering:** Event time + ID ổn định để tránh va chạm primary key.
- **TTL/TWCS:** Chọn policy theo workload, không đánh đồng hai loại window.
- **Consistency:** Regular CL/RF/DC theo SLA, không sửa bucket sai bằng tăng CL.
- **Spring Data:** Ánh xạ partition/clustering keys đúng; service sở hữu bucket algorithm.
- **Monitoring:** Tablehistograms/metrics, p99, disk free, compaction, tombstones, shard skew.
- **Change management:** Version policy, dual-read/backfill/reconciliation, rollback.
- **Testing:** Peak, burst, ranh giới, duplicate, late arrivals, TTL và failover.
- **QA:** Đây là STEP_4 tạo knowledge, chưa thực hiện vòng Content QA chuyên sâu STEP_6.

## Tài liệu tham khảo

- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/): partition keys, clustering, thiết kế theo truy vấn.
- [Apache Cassandra — CQL Reference](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html): CQL schema, SELECT, LIMIT, TTL và compaction options.
- [Apache Cassandra — Operations](https://cassandra.apache.org/doc/latest/cassandra/managing/): nodetool, compaction, repair và tài nguyên.
- [Spring Data Cassandra — Reference](https://docs.spring.io/spring-data/cassandra/reference/): mapping, repository và CassandraTemplate.
- [Apache Cassandra Java Driver 4.x](https://apache.github.io/cassandra-java-driver/): prepared statements, consistency và paging.

## Kết luận

**Kích thước time bucket trong Cassandra phải được ước lượng từ tốc độ ghi của từng stream, không phải tốc độ toàn cluster.** Với tốc độ `λ`, thời gian bucket `T` và `K` shards, số row/partition xấp xỉ `λ × T / K`; từ đó suy dung lượng bằng row bytes hiệu dụng và các giả định đã được đo. Chỉ dùng average hoặc chỉ nhìn byte size có thể bỏ qua peak, hot partitions và chi phí đọc xuyên nhiều buckets.

Trong **SPRING_DATA_CASSANDRA**, hãy kết hợp bucket trong partition key, clustering theo thời gian, event ID làm tie-breaker, bucket calculation nhất quán, TTL/TWCS, replication factor, consistency, paging và quan sát histogram/p99. Chọn phương án sau khi thử trên workload đại diện, và version hóa bucket policy khi tốc độ hoặc read pattern thay đổi. **Công thức giúp lọc phương án; số liệu thực và hợp đồng nghiệp vụ quyết định thiết kế bền vững.**
