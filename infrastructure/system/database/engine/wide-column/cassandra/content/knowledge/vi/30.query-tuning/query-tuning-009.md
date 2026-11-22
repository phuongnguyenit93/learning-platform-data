# Tối ưu truy vấn dữ liệu theo thời gian bằng bucket

## 1. Vấn đề: đọc 20 sự kiện mới nhất nhưng partition chứa nhiều năm lịch sử

Một ứng dụng **Apache Cassandra** nhận dữ liệu cảm biến liên tục. Mỗi thiết bị gửi hàng chục sự kiện mỗi giây; người dùng thường yêu cầu **20 sự kiện mới nhất** hoặc các sự kiện trong **15 phút gần đây**. Thiết kế ban đầu:

~~~sql
CREATE TABLE events_by_sensor_unbounded (
    sensor_id text,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Thiết kế này có một ưu điểm: biết `sensor_id` là xác định được partition và các hàng được sắp theo thời gian. Tuy nhiên, nếu cảm biến hoạt động nhiều năm, **toàn bộ sự kiện của cùng cảm biến thuộc một partition logic**. Partition có thể trở nên rất lớn, bị truy cập nóng, tạo nhiều SSTable, làm tăng bộ nhớ/chi phí đọc và khiến bảo trì khó dự đoán.

**Time bucketing** giải quyết vấn đề bằng cách thêm một đơn vị thời gian — giờ, ngày, tuần hoặc khoảng cố định — **vào partition key**. Thay vì một partition vô hạn cho mỗi cảm biến, dữ liệu được chia thành nhiều partition có giới hạn theo thời gian:

~~~text
Trước:
  partition (sensor-7) → sự kiện từ 2020 ... 2026 ... không giới hạn

Sau (bucket theo ngày):
  partition (sensor-7, 2026-11-19) → sự kiện của ngày 19/11
  partition (sensor-7, 2026-11-20) → sự kiện của ngày 20/11
  partition (sensor-7, 2026-11-21) → sự kiện của ngày 21/11
~~~

Như vậy, truy vấn có thể chọn **đúng partition thời gian liên quan** thay vì để một partition tích tụ lịch sử không kiểm soát. Đổi lại, khi truy vấn trải qua nhiều ngày/giờ, ứng dụng phải **đọc nhiều bucket và ghép kết quả**.

**Mục tiêu học tập:**

- Hiểu bucket theo thời gian liên hệ thế nào với **partition key**, clustering key, token và replica.
- Chọn kích thước bucket dựa trên **tốc độ ghi, dung lượng một partition, khoảng thời gian truy vấn và fan-out**.
- Viết CQL truy vấn theo khoảng **nửa kín [start, end)**, kể cả khi khoảng đi qua ranh giới hai bucket.
- Triển khai Java Driver 4.x đọc nhiều bucket, áp `LIMIT` đúng và merge/sort kết quả.
- Phân biệt bucket thời gian với **shard cho hot partition**, TTL/TWCS, index và quét token.
- Dùng tracing/metrics đo hiệu quả thay vì chỉ suy đoán từ schema.

Bài thuộc chương **Tối ưu truy vấn** của hệ cơ sở dữ liệu wide-column Cassandra. Các ví dụ là lab; tên DC, RF và tính năng theo phiên bản cần điều chỉnh theo môi trường thực tế.

## 2. Những khái niệm phải phân biệt trước khi thiết kế

### 2.1. Partition key định tuyến, clustering key sắp xếp

Trong Cassandra, **partition key** được băm thành **token**. Token, `NetworkTopologyStrategy` và replication factor quyết định những replica nào giữ partition. **Clustering columns** quyết định các hàng được sắp xếp ra sao **trong cùng partition**.

| Thành phần | Ví dụ | Công dụng | Giới hạn |
| --- | --- | --- | --- |
| **Partition key** | `(sensor_id, bucket_day)` | Chọn partition để định tuyến read/write. | Thiếu một thành phần partition key thường không còn truy vấn một partition cụ thể. |
| **Clustering key** | `(event_time, event_id)` | Sắp theo thời gian, định danh hàng trùng thời điểm, đọc một khoảng liên tục. | Không thay đổi token/nhóm replica của partition. |
| **Bucket** | `2026-11-21` (UTC) | Phân nhỏ lịch sử một sensor thành nhiều partition. | Không tự tạo thứ tự toàn cục giữa các partition. |
| **Token range** | Một đoạn trên vòng token | Phân phối partition giữa node, quét/repair theo token. | Không phải khoảng thời gian nghiệp vụ. |
| **TTL** | 30 ngày kể từ lúc mutation được ghi | Hết hiệu lực dữ liệu theo thời gian. | Không thay đổi partition key và không xóa SSTable tức thì. |

**Điểm then chốt:** thêm `bucket_day` vào **partition key** mới là time bucketing theo nghĩa phân chia partition. Nếu chỉ thêm cột `bucket_day` như một regular column trong bảng có `PRIMARY KEY ((sensor_id), event_time)`, partition của sensor vẫn không được chia nhỏ.

### 2.2. Tại sao chỉ `LIMIT 20` chưa đủ?

`SELECT ... WHERE sensor_id=? LIMIT 20` có thể nhanh khi các hàng mới nhất nằm đầu thứ tự clustering. Nhưng `LIMIT` giới hạn **số hàng trả về**, không đặt trần cho **kích thước partition**, **dữ liệu cũ tích lũy**, **chi phí compaction** hay **số tombstone phải duyệt** để tìm đủ 20 hàng còn sống.

Với TTL hoặc `DELETE`, Cassandra có thể cần hòa giải hàng ở nhiều SSTable và bỏ qua tombstone. Partition quá lớn còn làm các hoạt động scan khoảng rộng, streaming, repair và phục hồi nặng hơn. Bucketing là **biện pháp thiết kế mô hình dữ liệu** nhằm giới hạn những rủi ro ấy, không phải thay thế tối ưu SSTable/TTL.

## 3. Chọn bucket theo giờ, ngày hay khoảng ngắn hơn?

Không có quy tắc “Cassandra luôn dùng bucket theo ngày”. Kích thước hợp lý phụ thuộc hai chiều cạnh tranh:

1. **Bucket càng dài:** ít partition cần đọc nhưng mỗi partition có thể càng lớn/nóng.
2. **Bucket càng ngắn:** mỗi partition nhỏ hơn nhưng một truy vấn dài phải đọc nhiều partition hơn; metadata và request fan-out tăng.

### 3.1. Công thức ước lượng sơ bộ

Giả sử một sensor có:

- `λ`: tốc độ ghi trung bình/đỉnh, đơn vị **events/second**.
- `T`: thời lượng một bucket, đơn vị **giây**.
- `B`: kích thước lưu trữ ước lượng cho một event **trên một replica**, gồm phần overhead muốn tính, đơn vị byte.

Kích thước sơ bộ của một partition theo bucket:

~~~text
events_per_bucket  ≈ λ × T
bytes_per_partition ≈ λ × T × B

Ví dụ λ = 50 sự kiện/giây, B = 600 byte/sự kiện:

Bucket 1 ngày  : 50 × 86.400 × 600 = 2.592.000.000 B ≈ 2.592 MB
Bucket 1 giờ   : 50 ×  3.600 × 600 =   108.000.000 B ≈   108 MB
Bucket 15 phút : 50 ×    900 × 600 =    27.000.000 B ≈    27 MB
~~~

Đây là **ước lượng**, không phải dự báo chính xác: kích thước thực phụ thuộc compression, encoding, metadata, tombstone, độ dài payload, update, SSTable và compaction. **RF = 3 không làm partition trên một replica lớn gấp ba**, nhưng làm tổng lượng lưu trữ toàn cluster cho dữ liệu nhân bản tăng theo số replica. Tốc độ ghi **đỉnh/hot sensor**, không chỉ trung bình toàn cluster, mới quyết định rủi ro partition quá lớn.

### 3.2. Fan-out khi đọc dữ liệu theo khoảng

Một truy vấn kéo dài `W` giây có thể chạm khoảng `ceil(W/T)` bucket, **cộng thêm một bucket nếu biên bắt đầu và kết thúc cắt qua các ranh giới**. Số bucket chính xác phụ thuộc vị trí của hai đầu khoảng.

| Kích thước bucket | Đọc 15 phút | Đọc 3 giờ | Đọc 7 ngày |
| --- | --- | --- | --- |
| 1 ngày | Thường 1, đôi khi 2 partition | Thường 1, đôi khi 2 | Khoảng 7–8 partition |
| 1 giờ | Thường 1, đôi khi 2 | Khoảng 3–4 partition | Có thể 168–169 partition |
| 15 phút | Thường 1–2 partition | Khoảng 12–13 partition | Có thể 672–673 partition |

Con số là minh họa cho **một sensor** và khoảng nửa kín. Nếu phải đọc 10.000 sensor, tổng số request/partition cần xem xét còn lớn hơn rất nhiều. Do đó **không thể chỉ tối ưu partition size mà bỏ qua fan-out**.

### 3.3. Cách ra quyết định thực tế

| Workload chủ đạo | Bucket cân nhắc | Cần đo thêm |
| --- | --- | --- |
| Vài sự kiện/phút, truy vấn theo một ngày | Theo ngày | Kích thước partition sau nhiều tháng, TTL, tombstone. |
| Hàng chục/giây tại một sensor, đọc vài phút–giờ | Theo giờ hoặc 15 phút | Peak partition size, số partition/request, latency p99. |
| Sensor rất nóng, nhiều writer, một giờ vẫn quá lớn | Giờ ngắn hơn hoặc time bucket + **shard** | Write hotspot, concurrency, read fan-out tăng. |
| Báo cáo lịch sử 6 tháng | Bảng tổng hợp/rollup riêng theo ngày/tuần | Tránh quét hàng nghìn bucket raw events. |
| Truy vấn “mọi sensor của site trong 1 giờ” | Bảng được thiết kế riêng theo `site_id` và bucket | Dùng bảng theo truy vấn thay vì cố filter trên bảng `sensor_id`. |

Đừng coi một mốc kích thước cố định là SLA chung cho mọi Cassandra. Kích thước partition chấp nhận được cần kiểm tra bằng **độ trễ đọc, số hàng, SSTable, heap/off-heap, áp lực compaction/repair và phần cứng thật**.

## 4. Thiết kế bảng bucket theo ngày để phục vụ truy vấn

### 4.1. Schema CQL đầy đủ

Giả sử lab có data center `dc1` với đủ ba node để dùng RF = 3 và `LOCAL_QUORUM`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_tuning
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_day (
    sensor_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Giải thích schema:**

- `sensor_id` và `bucket_day` cùng tạo **partition key kép**. Cùng sensor nhưng khác ngày có token/replica set có thể khác nhau.
- `event_time` là clustering column đầu, giúp đọc một khoảng thời gian trong partition. Chỉ số ngày ở partition key **không thay thế** điều kiện khoảng trên `event_time`.
- `event_id` giúp các sự kiện có cùng `event_time` không ghi đè nhau. Client phải cấp **ID ổn định** cho retry để tránh nhân đôi sự kiện.
- `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` cho phép đọc sự kiện mới trước **bên trong mỗi bucket**. Không tạo thứ tự toàn cục giữa các bucket.
- `payload` là regular column: nếu payload lớn, cân nhắc bảng phục vụ danh sách chỉ chứa các trường cần hiển thị và một bảng chi tiết riêng; tránh `SELECT *` trong hot path.

### 4.2. Xác định bucket một cách nhất quán

Chọn **UTC** làm múi giờ bucket cho ví dụ:

~~~text
bucket_day(event_time) = LocalDate của event_time khi chuyển sang UTC

2026-11-20T23:59:59.999Z -> bucket_day 2026-11-20
2026-11-21T00:00:00.000Z -> bucket_day 2026-11-21
2026-11-21T23:59:59.999Z -> bucket_day 2026-11-21
~~~

Mọi writer Java, Python, ingestion job và backfill phải áp dụng **cùng hàm tính bucket**. Nếu client ở Việt Nam dùng ngày địa phương (UTC+7) còn backend dùng UTC, một event lúc 00:30 giờ Việt Nam có thể bị gắn vào ngày UTC trước đó; truy vấn theo bucket UTC sẽ bỏ sót nếu ứng dụng không thống nhất.

Nếu nghiệp vụ cần bucket theo **ngày địa phương của cửa hàng**, hãy lưu rõ **time zone IANA của cửa hàng**, quy tắc daylight-saving và định nghĩa ngày kinh doanh. Không tự suy bucket bằng cộng cố định 24 giờ tại mọi timezone vì ngày có chuyển DST có thể dài 23 hoặc 25 giờ. Trong bài này tất cả tính toán bucket đều dùng **UTC**.

### 4.3. Bucket theo thời gian sự kiện hay thời gian nhận?

| Trường hợp | Tính bucket từ `event_time` | Tính bucket từ `ingested_at` |
| --- | --- | --- |
| Người dùng hỏi “sự kiện thực sự xảy ra từ 08:00 đến 09:00” | Phù hợp hơn. | Có thể bỏ sót sự kiện gửi muộn. |
| Hệ thống cần kiểm tra tốc độ ingestion theo phút | Không phản ánh chính xác thời điểm hệ thống nhận. | Phù hợp hơn. |
| Sự kiện backfill từ tháng trước | Phải ghi vào bucket quá khứ; có thể làm workload TWCS phức tạp hơn. | Ghi vào bucket hiện tại; truy vấn theo event time phải thiết kế lại. |
| Đồng hồ thiết bị lệch | Có nguy cơ đặt vào bucket sai. | Dễ quan sát quá trình nhận, nhưng khác nghĩa nghiệp vụ. |

**Chọn một semantics và ghi rõ.** Nếu cả hai kiểu truy vấn đều quan trọng, thường cần **hai bảng projection** với partition key khác nhau hoặc pipeline tổng hợp, thay vì lạm dụng `ALLOW FILTERING` để tìm mọi dữ liệu theo một cột không thuộc key.

## 5. Truy vấn đúng ở ranh giới bucket: khoảng nửa kín

### 5.1. Vì sao dùng [start, end)?

Quy ước:

~~~text
[startInclusive, endExclusive)

Điều kiện CQL:
  event_time >= startInclusive
  AND event_time < endExclusive
~~~

Khoảng nửa kín giúp chia các cửa sổ liền nhau mà **không đếm trùng mốc biên**:

~~~text
Ngày UTC 2026-11-20: [2026-11-20T00:00:00Z, 2026-11-21T00:00:00Z)
Ngày UTC 2026-11-21: [2026-11-21T00:00:00Z, 2026-11-22T00:00:00Z)

Một event đúng 2026-11-21T00:00:00Z chỉ thuộc ngày 21/11.
~~~

`CLUSTERING ORDER BY ... DESC` **không làm toán tử `>=` đổi nghĩa**. Nó chỉ tác động thứ tự sắp/đọc bên trong partition.

### 5.2. Insert dữ liệu trải hai ngày

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-20', '2026-11-20T23:45:00Z',
   123e4567-e89b-42d3-a456-426614174001, 'temperature', '20.5');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-20', '2026-11-20T23:59:59Z',
   123e4567-e89b-42d3-a456-426614174002, 'temperature', '20.8');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-21', '2026-11-21T00:00:00Z',
   123e4567-e89b-42d3-a456-426614174003, 'temperature', '21.0');

INSERT INTO telemetry_tuning.events_by_sensor_day
  (sensor_id, bucket_day, event_time, event_id, event_type, payload)
VALUES
  ('sensor-7', '2026-11-21', '2026-11-21T00:40:00Z',
   123e4567-e89b-42d3-a456-426614174004, 'temperature', '21.2');
~~~

### 5.3. Truy vấn một bucket

~~~sql
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:30:00Z'
  AND event_time < '2026-11-21T00:00:00Z';
~~~

Kết quả trong lab có **23:45** và **23:59:59**. Vì `bucket_day` đã cố định, truy vấn định tuyến tới **một partition**, rồi dùng clustering range để lấy đoạn phù hợp.

### 5.4. Đọc qua mốc nửa đêm phải truy vấn hai bucket

Để lấy khoảng **[20/11 23:30 UTC, 21/11 00:45 UTC)**:

~~~sql
-- Bucket ngày 20/11:
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20'
  AND event_time >= '2026-11-20T23:30:00Z'
  AND event_time < '2026-11-21T00:00:00Z';

-- Bucket ngày 21/11:
SELECT event_time, event_id, event_type, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-21T00:45:00Z';
~~~

Hai kết quả là **hai danh sách được sắp bên trong hai partition khác nhau**. Cassandra không tự ghép chúng thành một danh sách `ORDER BY event_time DESC` **toàn cục**. Ứng dụng phải hợp nhất/sort hoặc thực hiện thuật toán k-way merge.

**Lỗi thường gặp:** chỉ truy vấn `bucket_day` ứng với `start`, rồi đặt `event_time < end` xuyên sang ngày hôm sau. Một partition ngày 20/11 không chứa các sự kiện đã được phân vào partition ngày 21/11, vì vậy truy vấn sẽ bỏ sót chúng.

## 6. Không dùng `ALLOW FILTERING` như lời giải thay cho bucket key

Ví dụ:

~~~sql
-- Không phải cách đọc một khoảng thời gian hiệu quả trên schema này:
SELECT event_time, payload
FROM telemetry_tuning.events_by_sensor_day
WHERE event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T09:00:00Z'
ALLOW FILTERING;
~~~

Điều kiện thiếu **toàn bộ partition key** `(sensor_id, bucket_day)`. Cassandra không thể định tuyến trực tiếp tới một partition; nếu execution plan/phiên bản chấp nhận truy vấn dạng filtering, nó có thể phải quét lượng dữ liệu rất lớn. `ALLOW FILTERING` **không biến truy vấn phân tán thành tra cứu theo chỉ mục rẻ**.

| Truy vấn nghiệp vụ | Bảng nên cân nhắc |
| --- | --- |
| “Sensor S có sự kiện nào trong 15 phút?” | `events_by_sensor_day` hoặc `events_by_sensor_hour`. |
| “Mọi sensor thuộc site X gửi sự kiện nào trong giờ H?” | Projection riêng theo `(site_id, bucket_hour)` với clustering key phù hợp; đo partition size/hotspot. |
| “Tổng số cảnh báo mỗi ngày của site?” | Bảng **aggregate/rollup** theo site/ngày, cập nhật qua pipeline có kiểm soát. |
| “Tra sự kiện bằng `event_id` chính xác?” | Projection `event_by_id` với `event_id` là partition key nếu nhu cầu chính. |

Cassandra thường **nhân bản dữ liệu theo mẫu truy vấn**, thay vì dựa vào một bảng chung rồi mong bộ tối ưu có thể join/filter tùy ý như SQL quan hệ. Secondary index/SAI (ở phiên bản hỗ trợ) có những trường hợp sử dụng riêng, nhưng không tự giải quyết một read phải duyệt hàng nghìn bucket vì thiếu partition key phù hợp.

## 7. Java Driver 4.x: đọc nhiều bucket và giữ thứ tự đúng

Ví dụ dưới đây dùng bảng bucket theo **ngày UTC**, thực hiện truy vấn trên mọi ngày giao với khoảng `[start, end)`, giới hạn tối đa **8 bucket**, rồi sắp xếp kết quả mới nhất trước. Để trả **50 sự kiện mới nhất trên toàn khoảng**, mỗi bucket chỉ cần lấy tối đa **50 sự kiện mới nhất của bucket đó**: một event nằm ngoài top 50 của chính bucket không thể nằm trong top 50 toàn bộ tập hợp, với thứ tự so sánh nhất quán.

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
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

public final class ReadEventsAcrossDayBuckets {
    private static final int GLOBAL_LIMIT = 50;
    private static final int MAX_BUCKETS = 8;

    private static final class Event {
        final Instant time;
        final UUID id;
        final String type;

        Event(Instant time, UUID id, String type) {
            this.time = time;
            this.id = id;
            this.type = type;
        }
    }

    public static void main(String[] args) {
        Instant from = Instant.parse("2026-11-20T23:30:00Z");
        Instant to = Instant.parse("2026-11-21T00:45:00Z");

        if (!from.isBefore(to)) {
            throw new IllegalArgumentException("empty or reversed time range");
        }

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement readBucket = session.prepare(
                "SELECT event_time, event_id, event_type " +
                "FROM telemetry_tuning.events_by_sensor_day " +
                "WHERE sensor_id = ? AND bucket_day = ? " +
                "AND event_time >= ? AND event_time < ? LIMIT ?");

            List<Event> collected = new ArrayList<>();
            int bucketsVisited = 0;

            for (LocalDate day = from.atZone(ZoneOffset.UTC).toLocalDate();
                 day.atStartOfDay(ZoneOffset.UTC).toInstant().isBefore(to);
                 day = day.plusDays(1)) {

                if (++bucketsVisited > MAX_BUCKETS) {
                    throw new IllegalArgumentException(
                        "time range touches too many buckets");
                }

                Instant bucketStart =
                    day.atStartOfDay(ZoneOffset.UTC).toInstant();
                Instant bucketEnd =
                    day.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant();

                Instant sliceStart = from.isAfter(bucketStart)
                    ? from : bucketStart;
                Instant sliceEnd = to.isBefore(bucketEnd)
                    ? to : bucketEnd;

                BoundStatement query = readBucket.bind(
                        "sensor-7",
                        day,
                        sliceStart,
                        sliceEnd,
                        GLOBAL_LIMIT)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM);

                for (Row row : session.execute(query)) {
                    collected.add(new Event(
                        row.getInstant("event_time"),
                        row.getUuid("event_id"),
                        row.getString("event_type")));
                }
            }

            // Mỗi bucket được trả theo event_time DESC; danh sách gộp
            // vẫn cần thứ tự tổng thể (và tie-breaker ổn định).
            collected.sort(Comparator
                .comparing((Event e) -> e.time).reversed()
                .thenComparing(e -> e.id));

            int count = Math.min(GLOBAL_LIMIT, collected.size());
            for (int i = 0; i < count; i++) {
                Event event = collected.get(i);
                System.out.println(event.time + " " + event.id
                    + " " + event.type);
            }
        }
    }
}
~~~

**Các quyết định quan trọng trong ví dụ:**

1. `LocalDate` được tính từ **UTC event timestamp**, đúng quy tắc lúc ghi. `date` của CQL nhận `LocalDate`, `timestamp` nhận `Instant`.
2. Vòng lặp dừng tại bucket có **start >= endExclusive**; nhờ đó khoảng kết thúc đúng 00:00 UTC không đọc thêm một ngày không liên quan.
3. Mỗi lần đọc cung cấp **đầy đủ partition key** và giới hạn clustering range chỉ nằm trong ngày đó.
4. `MAX_BUCKETS` giúp tránh request vô tình fan-out quá lớn; production nên kiểm soát thêm **deadline, concurrency, tổng số byte, số result rows và rate limit**.
5. `LIMIT 50` trong mỗi bucket không phải **global limit 50**: sau khi gộp, code vẫn phải sắp xếp và chỉ chọn 50 kết quả mới nhất.
6. Ví dụ chạy tuần tự để dễ hiểu. Nếu cần tối ưu latency, có thể dùng asynchronous requests với **số lượng đồng thời hữu hạn**, theo dõi tải coordinator/replica và hủy request khi deadline hết; không tạo hàng trăm request vô hạn.
7. `LOCAL_QUORUM` ở `dc1` với RF = 3 yêu cầu hai replica phản hồi cho **mỗi truy vấn bucket**. Nó không tạo transaction snapshot nhất quán tại một thời điểm chung cho mọi bucket.

**Giới hạn cần nắm:** ví dụ giữ tối đa `MAX_BUCKETS × GLOBAL_LIMIT` event trong RAM, thích hợp cho danh sách ngắn. Với dashboard hàng triệu sự kiện hoặc pagination sâu, cần **streaming merge/bounded heap và cursor đa bucket** thay vì gom toàn bộ vào list. Comparator theo `event_id` là tie-breaker minh họa; nếu quy tắc ordering cần đồng nhất tuyệt đối giữa nhiều ngôn ngữ, hãy chuẩn hóa tie-breaker/kiểu UUID và xác minh thứ tự tại Cassandra. Nếu `bucket_day` được dẫn xuất đúng từ `event_time`, cùng một `event_time` không nằm ở hai bucket ngày khác nhau.

## 8. Phân trang và lấy “mới nhất” trên nhiều bucket

### 8.1. Tránh hiểu nhầm `LIMIT` và page size

| Khái niệm | Ý nghĩa | Điều không bảo đảm |
| --- | --- | --- |
| `LIMIT 50` trong CQL | Trả tối đa 50 hàng **còn sống** theo truy vấn của một partition/bucket. | Replica chỉ đọc tối đa 50 item vật lý; tombstone có thể làm nhiều hơn. |
| Driver `page size = 100` | Chia kết quả một statement thành những page để tránh nhận hết cùng lúc. | Không hạn chế tổng số hàng của toàn bộ request nếu tiếp tục fetch. |
| “Global top 50” từ 8 bucket | Chọn 50 event mới nhất từ hợp các bucket. | Không thể đạt chỉ bằng một `ORDER BY` trên nhiều partition. |
| Cursor ứng dụng | Ghi lại vị trí đọc tiếp trong toàn bộ các bucket. | Không phải cùng một thứ với paging state của riêng một CQL statement. |

### 8.2. Một cách phân trang có kiểm soát

Đối với bảng có clustering `event_time DESC, event_id ASC`:

1. Chọn rõ **khoảng thời gian truy vấn cố định** và **số bucket tối đa**.
2. Mỗi bucket có một **cursor** gồm vị trí clustering cuối đã đọc (và trạng thái truy vấn/page phù hợp).
3. Lấy một phần ứng viên từ từng bucket, đưa vào **priority queue** có thứ tự thống nhất.
4. Lần lượt phát ra những event mới nhất cho tới khi đủ page size của API; giữ lại cursor của từng bucket chưa cạn.
5. Sang page tiếp theo, tiếp tục **từ vị trí chưa tiêu thụ** của từng bucket, không bắt đầu lại từ đầu.

Sơ đồ ý tưởng:

~~~mermaid
flowchart LR
    A["Bucket ngày 19"] --> M["Merge theo event_time + event_id"]
    B["Bucket ngày 20"] --> M
    C["Bucket ngày 21"] --> M
    M --> L["API page: 50 hàng mới nhất"]
    L --> P["Cursor: vị trí đọc tiếp của mỗi bucket"]
    P --> M
~~~

**Không có `OFFSET` toàn cục tiện dụng** cho các partition khác nhau. Cassandra paging state là trạng thái riêng của statement/page, có thể không phù hợp để chia sẻ công khai hoặc lưu rất lâu, và không tự biểu diễn thứ tự merge đa bucket. Nếu ứng dụng cần cursor dài hạn, nên thiết kế token cursor riêng có xác thực/tamper protection và quy tắc hết hạn; khi dùng clustering resume, cần xử lý đúng cặp `(event_time, event_id)` để tránh bỏ sót các hàng cùng timestamp.

### 8.3. Ghi đồng thời khiến kết quả giữa các page thay đổi

Cassandra không tự cung cấp **snapshot isolation xuyên nhiều partition** cho một chuỗi SELECT thông thường. Trong lúc API đọc bucket A rồi bucket B, writer khác có thể ghi thêm sự kiện hoặc cập nhật/xóa hàng. Do đó:

- Hai page có thể thấy tập dữ liệu hơi khác nhau.
- Một event đến muộn có `event_time` cũ có thể xuất hiện trong bucket đã duyệt trước đó.
- Dùng cùng timestamp và event ID cho retry để giảm duplicate; nếu nghiệp vụ yêu cầu nhất quán theo một watermark, thiết kế **ingestion watermark** hoặc ảnh chụp dữ liệu ở tầng ứng dụng.
- Cursor nên gắn với **time window cố định** thay vì liên tục cập nhật `end = now` giữa các lần fetch.

Đây là đặc tính của **nhiều truy vấn phân tán**, không phải lỗi riêng của Java Driver hay bucket.

## 9. Nếu một bucket vẫn quá nóng: thêm shard có kiểm soát

Time bucket giới hạn lịch sử theo thời gian, nhưng một sensor có 50.000 sự kiện/giây vẫn có thể làm partition của **một phút** nóng. Khi đó, ngoài bucket còn có thể cần **shard**:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_hour_sharded (
    sensor_id text,
    bucket_hour timestamp,
    shard int,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id, bucket_hour, shard), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Quy ước:

~~~text
bucket_hour = event_time làm tròn xuống đầu giờ UTC
shard = stable_hash(event_id) modulo S

Ví dụ S = 4:
  (sensor-7, 2026-11-21T08:00:00Z, shard=0)
  (sensor-7, 2026-11-21T08:00:00Z, shard=1)
  (sensor-7, 2026-11-21T08:00:00Z, shard=2)
  (sensor-7, 2026-11-21T08:00:00Z, shard=3)
~~~

**Lợi ích:** nhiều partition/shard có thể phân bố writes theo các token/replica set khác nhau, giảm áp lực một partition. **Đánh đổi:** muốn đọc toàn bộ sự kiện của sensor trong giờ đó phải truy vấn **cả S shard** và merge/sort; số request tăng khoảng S lần cho mỗi bucket. `stable_hash` phải được định nghĩa **thống nhất ở tất cả client/ngôn ngữ**, không chỉ dựa vào một hàm hash mặc định không có hợp đồng ổn định.

Không tự coi shard count là tham số có thể thay từ 4 lên 8 bất kỳ lúc nào mà không ảnh hưởng dữ liệu cũ. Nếu đổi số shard, cần **schema/version trong key hoặc logic đọc tương thích cả hai giai đoạn** để tìm đủ event. Sharding chỉ hợp khi đã đo bottleneck về write rate/hot partition; nếu workload đọc là chủ đạo, shard vô cớ có thể làm hiệu năng xấu đi.

## 10. TTL, xóa bucket và TWCS: tối ưu giữ dữ liệu, không đồng nghĩa bucket

### 10.1. Time bucket và TTL giải quyết hai bài toán khác nhau

- **Bucket theo thời gian:** giới hạn dữ liệu của một partition và giúp truy vấn chọn đúng partition.
- **TTL:** quy định khi nào cell/hàng không còn sống về mặt logic; thời gian TTL thường được tính từ **thời điểm ghi**.
- **Compaction:** quản lý SSTable, phiên bản và tombstone trên từng node; có thể purge những nội dung đủ điều kiện.
- **Anti-entropy repair:** đồng bộ replica lệch, đặc biệt quan trọng khi có tombstone.

Nếu hệ thống giữ dữ liệu 30 ngày, có thể dùng bảng có TTL mặc định:

~~~sql
CREATE TABLE IF NOT EXISTS telemetry_tuning.events_by_sensor_day_ttl (
    sensor_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC)
  AND default_time_to_live = 2592000
  AND gc_grace_seconds = 864000
  AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
  };
~~~

Đây là **minh họa** của `TimeWindowCompactionStrategy` (TWCS) trong time-series append-mostly; không phải công thức cấu hình tối ưu cho mọi workload. `default_time_to_live = 2592000` tương ứng 30 ngày, còn `gc_grace_seconds = 864000` tương ứng 10 ngày. Việc giảm grace phải dựa trên lịch repair, replication, phiên bản và rủi ro zombie data; không dùng 0 chỉ để dọn đĩa nhanh.

### 10.2. Bẫy backfill: event-time retention khác write-time TTL

Giả sử ngày **21/11** mới import sự kiện thực sự xảy ra **01/10**. Nếu ghi với TTL 30 ngày mặc định, thông thường dữ liệu được tính thời gian sống **từ write mới**, không phải tự hết hạn ngay vì `event_time` cũ. Tương tự, TWCS sử dụng thông tin timestamp của mutation cho việc nhóm SSTable; cần hiểu **write timestamp CQL** khác **giá trị cột `event_time`**.

Nếu yêu cầu nghiệp vụ là giữ **30 ngày tính từ event_time**, ingestion pipeline nên kiểm tra:

~~~text
expiry_at = event_time + 30 ngày theo quy tắc nghiệp vụ
remaining_ttl = expiry_at - now

Nếu remaining_ttl <= 0: không nạp event đã hết hạn,
hoặc xử lý bằng chính sách backfill/archival riêng.
Nếu > 0: cân nhắc ghi với TTL được tính và giới hạn hợp lệ.
~~~

TTL CQL tính bằng giây và có giới hạn về giá trị/phiên bản; cần làm tròn, kiểm tra timestamp thiết bị lệch và chính sách idempotency. Không tự sửa `USING TIMESTAMP` của mutation về event time để giải bài toán retention: thao tác ấy còn ảnh hưởng **last-write-wins**, tombstone hòa giải và TWCS, có thể làm dữ liệu cũ bị che hoặc kéo dài vòng đời SSTable không mong đợi.

### 10.3. Xóa nguyên bucket không phải “drop partition file”

~~~sql
-- Xóa toàn một partition bucket (trong lab), không xóa vật lý ngay:
DELETE FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-20';
~~~

Đây là **partition deletion**, tạo tombstone theo semantics Cassandra. Nó không lập tức xóa mọi byte trong SSTable, không phải lệnh drop một file riêng và không tự thực hiện repair. **Đừng tạo một bảng Cassandra riêng cho mỗi ngày chỉ để `DROP TABLE` hàng ngày** nếu chưa đánh giá schema churn, metadata và số bảng; time bucketing bằng partition key thường đơn giản hơn.

TWCS có thể thu hồi cả SSTable hết hạn thuận lợi với dữ liệu chủ yếu append-only, TTL đồng nhất và write timestamp hợp lý. **Mixed TTL, backfill, cập nhật dữ liệu quá khứ, dữ liệu sống xen tombstone và replica lệch** có thể cản việc drop an toàn. Bucket day cũng không có quan hệ một-một bắt buộc với TWCS time window.

## 11. Tracing và metrics để biết bucket thực sự tối ưu chưa

Đừng kết luận “query nhanh hơn” chỉ dựa vào việc có `bucket_day` trong primary key. Cần đo **cùng workload trước/sau** và nhìn cả read/write/maintenance.

### 11.1. Thử tracing ở lab

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time, event_id, event_type
FROM telemetry_tuning.events_by_sensor_day
WHERE sensor_id = 'sensor-7'
  AND bucket_day = '2026-11-21'
  AND event_time >= '2026-11-21T00:00:00Z'
  AND event_time < '2026-11-22T00:00:00Z'
LIMIT 50;

TRACING OFF;
~~~

`CONSISTENCY` và `TRACING` là lệnh của **cqlsh**. Tracing session có thể cho biết coordinator, replica/hoạt động đọc, số dữ liệu duyệt và thời gian các bước tùy phiên bản, nhưng bản trace chỉ là **một mẫu truy vấn**, không phải phép đo SLO toàn workload. Tracing tạo overhead nên không bật liên tục cho toàn traffic production.

### 11.2. Các lệnh và số liệu quan sát

~~~bash
nodetool tablestats telemetry_tuning.events_by_sensor_day
nodetool tablehistograms telemetry_tuning events_by_sensor_day
nodetool proxyhistograms
nodetool compactionstats
nodetool status
~~~

| Nhóm chỉ số | Câu hỏi cần trả lời |
| --- | --- |
| **Partition size / cell count** | Bucket thực có kích thước bao nhiêu ở p50/p95/max, có hot sensor không? |
| **Read latency p95/p99** | SLO cải thiện không? Đọc 3 giờ có phải mở nhiều bucket hơn dự kiến? |
| **Tombstones scanned per read** | Có quét nhiều hàng hết TTL hoặc range/partition tombstone dù `LIMIT` nhỏ? |
| **SSTable count/read amplification** | Một partition phải hòa giải nhiều SSTable không? |
| **Coordinator/replica CPU, I/O** | Fan-out có làm tăng network và số request nội bộ? |
| **Pending compactions/flush** | Ghi nhiều partition có gây compaction backlog hoặc SSTable pressure? |
| **Per-sensor write rate** | Có thiết bị nào gửi dữ liệu gấp 100 lần trung bình không? |
| **Requests/buckets per API call** | Một request giao cắt bao nhiêu bucket; có bị phép đọc 7 ngày mở 169 partition không? |

Tên trường và cách tính metric `nodetool` khác giữa các bản Cassandra. Khi đo, ghi **phiên bản, schema, CL, RF, kích thước dữ liệu, số node, caching trạng thái ấm/lạnh và concurrency**. So sánh trước/sau khi workload hoặc data shape khác nhau dễ dẫn đến kết luận sai.

### 11.3. Kịch bản benchmark A/B

1. Dựng dữ liệu lab có **phân phối thời gian, TTL/delete và sensor hot/cold** gần production, không chỉ 100 event đẹp.
2. Đo baseline với schema chưa bucket: read last 15m, last 3h, last 7d; insert và compaction load.
3. Tạo bảng bucket ngày và nhập cùng một dataset; đo p50/p95/p99, bytes read, partition size và tombstone scan.
4. Nếu ngày quá lớn, thử bucket giờ; đo **đổi lại fan-out** khi đọc 7 ngày.
5. Nếu giờ quá nóng, thử giờ + shard nhưng đánh giá thêm merge/latency/cost.
6. Thử boundary 00:00 UTC, late-arriving event, event-time trùng, retry và đọc xuyên nhiều bucket.
7. Xác nhận SLO API, write throughput, replica disk usage và khả năng repair/backup; không chỉ nhìn trung bình read latency.

## 12. Những phản mẫu thiết kế cần tránh

| Phản mẫu | Hậu quả | Hướng thay |
| --- | --- | --- |
| `PRIMARY KEY ((sensor_id), event_time)` cho dữ liệu nhiều năm | Partition tăng mãi, nhiều SSTable/tombstone, maintenance nặng. | Thêm bucket thời gian vào partition key. |
| Chọn bucket 1 phút cho mọi sensor dù đọc lịch sử nhiều tuần | Request fan-out lớn, metadata/overhead tăng. | Chọn độ dài phù hợp hoặc dùng rollup cho truy vấn lịch sử. |
| Chỉ dùng `event_time` trong `WHERE` và `ALLOW FILTERING` | Quét phân tán khó dự đoán, timeout. | Dùng đủ partition key hoặc projection phục vụ mẫu truy vấn khác. |
| Ghi `bucket_day` theo ngày máy client, đọc theo UTC | Bỏ sót sự kiện ở ranh giới ngày. | Một hàm tính bucket UTC/zone nghiệp vụ thống nhất trên mọi writer. |
| Dùng `event_time` mà không có `event_id` phân biệt | Các sự kiện cùng timestamp có thể ghi đè nhau. | Thêm ID ổn định vào clustering key. |
| Query nhiều bucket rồi nối list theo thứ tự nhận response | Danh sách không được sort toàn cục. | Merge/sort theo khóa thứ tự chung. |
| Global `LIMIT 50` được hiểu là `LIMIT 50` cho toàn bộ 8 bucket | Có thể thu 400 hàng hoặc trả sai top N nếu merge sai. | Top K per bucket và merge top K toàn cục. |
| Tăng shard từ 4 lên 8 nhưng reader chỉ đọc shard mới | Bỏ sót dữ liệu ở những shard cũ. | Version shard scheme/migration hoặc reader hỗ trợ cả hai. |
| TTL 30 ngày được hiểu là “xóa 30 ngày sau event time” | Backfill tồn tại lâu hơn nghiệp vụ dự kiến. | Tính retention đúng semantics hoặc pipeline archival riêng. |
| `LIMIT` được xem là phương án xóa tombstone scan | Có thể duyệt nhiều marker trước khi trả đủ hàng sống. | Giảm tombstone/partition quá lớn, điều chỉnh dữ liệu và maintenance. |
| Mọi truy vấn nhiều sensor dùng một partition theo sensor | Phải fan-out tới từng sensor rồi ghép, có thể rất tốn. | Bảng theo site/tenant hoặc aggregate cho đúng query pattern. |

## 13. Case study: tối ưu timeline 3 giờ và báo cáo 30 ngày

**Bài toán:** 20.000 sensor; phần lớn gửi 1 event/5 giây, một nhóm 100 sensor gửi đỉnh 50 event/giây. API phổ biến:

- **A.** Lấy 50 sự kiện mới nhất của **một sensor**.
- **B.** Lấy mọi sự kiện của **một sensor** trong 3 giờ.
- **C.** Xem **tổng số cảnh báo/ngày** trên site trong 30 ngày.

**Thiết kế chưa hợp lý:** một bảng duy nhất `events_by_sensor` giữ toàn lịch sử theo sensor, sau đó dùng `ALLOW FILTERING` hoặc cố quét nhiều sensor để tính tổng.

**Phương án có phân tầng:**

1. **Raw events của sensor thường:** cân nhắc bucket theo ngày, đo partition size và retention.
2. **Raw events của 100 sensor nóng:** thử bucket theo giờ; nếu giờ vẫn quá lớn/hot, cân nhắc shard có kiểm soát.
3. **API A:** đọc bucket hiện tại trước; nếu dưới 50 hàng sống, đọc ngược về các bucket trước trong giới hạn cho phép. Không cần đọc 30 ngày ngay từ đầu.
4. **API B:** với bucket giờ, đọc khoảng 3–4 partition, merge theo thời gian; so với bucket ngày, chọn dựa trên partition size thực.
5. **API C:** xây một bảng aggregate theo `(site_id, month_or_window)` hoặc `(site_id)` với clustering theo ngày tùy quy mô và truy vấn, có pipeline cập nhật/reconciliation; không quét raw events của tất cả sensor để dựng dashboard mỗi lần.

### Tính toán chi phí để ra quyết định

Với một sensor nóng ở đỉnh **50 event/s**, ước lượng **600 byte/event/replica**:

| Thiết kế | Dữ liệu logic ước tính mỗi bucket trên một replica | Số bucket phải đọc cho 3 giờ |
| --- | --- | --- |
| Bucket ngày | Khoảng 2.592 MB/ngày nếu duy trì đỉnh suốt ngày | 1–2 |
| Bucket giờ | Khoảng 108 MB/giờ nếu duy trì đỉnh suốt giờ | 3–4 |
| Bucket 15 phút | Khoảng 27 MB/15 phút | 12–13 |
| Bucket giờ + 4 shard | Trung bình khoảng 27 MB/shard/giờ nếu hash phân đều | Khoảng 12–16 partition |

**Không có hàng nào mặc định là “tối ưu nhất”.** Bucket ngày có thể quá lớn; 15 phút hoặc nhiều shard tăng lượng request. Thử nghiệm thực tế nên quyết định với các ràng buộc **partition size, SLO p99, write rate, memory và maintenance**.

### Một cải tiến thường đáng giá hơn bucket nhỏ vô hạn

Nếu 95% người dùng xem **50 sự kiện mới nhất** và chỉ 5% xem báo cáo 30 ngày, cân nhắc **một projection dành cho recent events và một rollup lịch sử**. Điều này giữ hot read ít fan-out, đồng thời tránh truy vấn lịch sử quét raw dữ liệu khổng lồ. Đổi lại, phải thiết kế pipeline cập nhật projection, xử lý duplicate/idempotency, sai lệch giữa bảng và reconciliation.

## 14. Các bài tập tự kiểm tra có đáp án

**Bài 1.** Bảng dùng `PRIMARY KEY ((sensor_id, bucket_day), event_time, event_id)`. Một sự kiện xảy ra `2026-11-21T00:00:00Z` thuộc bucket nào nếu dùng ngày UTC? Có thuộc khoảng `[2026-11-20T23:00:00Z, 2026-11-21T00:00:00Z)` không?

**Đáp án:** Bucket `2026-11-21`. **Không** thuộc khoảng nửa kín kết thúc đúng 00:00 ngày 21/11, nhưng thuộc khoảng bắt đầu tại 00:00 ngày 21/11.

**Bài 2.** Sensor ghi 20 event/giây, kích thước ước tính 400 byte/event trên một replica. Một bucket một giờ có kích thước sơ bộ bao nhiêu, bỏ qua biến động?

**Đáp án:** `20 × 3600 × 400 = 28.800.000 byte ≈ 28,8 MB` trên một replica. Kích thước thực có thể khác do SSTable/compaction/compression.

**Bài 3.** API cần đọc 7 ngày từ bảng bucket giờ. Vì sao query có thể chậm dù từng partition nhỏ?

**Đáp án:** Một khoảng 7 ngày có thể chạm khoảng **168–169 partition** cho một sensor. Chi phí fan-out, network, merge, concurrency và metadata cộng dồn; có thể cần bucket lớn hơn cho workload này hoặc projection/rollup riêng.

**Bài 4.** Truy vấn từ 23:30 UTC đến 00:45 UTC ngày sau có thể chỉ dùng `bucket_day` của ngày bắt đầu không?

**Đáp án:** **Không.** Phải đọc bucket của cả hai ngày với hai clustering ranges tương ứng, rồi merge/sort kết quả theo timestamp.

**Bài 5.** Khi query dùng `LIMIT 20` nhưng phía Cassandra báo tombstone scanned cao, có thể kết luận driver đã đọc sai số hàng không?

**Đáp án:** **Không.** `LIMIT` giới hạn hàng trả về, không phải marker/hàng cũ phải xử lý để tìm đủ 20 hàng còn sống.

**Bài 6.** Vì sao `event_id` nên là phần clustering key sau `event_time`?

**Đáp án:** Nhiều event có thể có cùng timestamp; không có ID phân biệt, cùng partition + timestamp có thể trở thành cùng một primary key và ghi đè nhau. ID ổn định còn hữu ích khi retry idempotent.

**Bài 7.** Nếu chọn bốn shard cho mỗi bucket và đọc 24 bucket giờ, tổng số partition có thể phải truy vấn cho một sensor là bao nhiêu?

**Đáp án:** Tối đa **96 partition** (`24 × 4`) nếu phải đọc tất cả shard của mọi bucket; cần giới hạn concurrency và merge theo thứ tự toàn cục.

**Bài 8.** Một sự kiện xảy ra cách đây 45 ngày, hôm nay mới được ingest vào bảng TTL mặc định 30 ngày. Nó có tự hết hạn ngay vì cột `event_time` cũ không?

**Đáp án:** **Không.** TTL thường đếm từ lúc write, không tự suy ra `event_time`. Phải áp quy tắc retention theo event time ở pipeline nếu đó là yêu cầu nghiệp vụ.

**Bài 9.** Khi Java Driver đọc 3 bucket với `LOCAL_QUORUM`, có bảo đảm cả ba SELECT nhìn thấy một snapshot duy nhất tại cùng một thời điểm không?

**Đáp án:** **Không.** Mỗi truy vấn bucket có consistency level riêng; các mutation đồng thời có thể khiến dữ liệu giữa những lần SELECT khác nhau. Cần watermark/logic ứng dụng nếu đòi kết quả ổn định.

## 15. Checklist triển khai bucket cho production

~~~text
[ ] Ghi rõ 3–5 truy vấn chủ đạo và giới hạn time window của từng API.
[ ] Đo tốc độ events/second và bytes/event ở sensor trung bình và nóng nhất.
[ ] Ước lượng partition size theo ngày/giờ/15 phút, không coi là số chính xác.
[ ] Đo số partition/bucket mỗi request, bao gồm các truy vấn lịch sử.
[ ] Chọn quy tắc UTC/zone nghiệp vụ và bucket(event_time) thống nhất mọi writer.
[ ] Có event_id ổn định để phân biệt cùng timestamp và retry an toàn.
[ ] Mọi SELECT hot path có đủ partition key + clustering range nửa kín.
[ ] Khi đọc xuyên bucket: giới hạn fan-out, merge top K và xử lý pagination.
[ ] Có kế hoạch cho late event, backfill, dữ liệu trùng và cursor giữa các page.
[ ] TTL/retention xét đúng write time vs event time, TWCS và repair.
[ ] Nếu bucket vẫn hot, benchmark shard và chi phí đọc S shard/bucket.
[ ] Theo dõi p95/p99, partition size, tombstones, SSTable, compaction và CL.
[ ] Benchmark load, boundary UTC, failover, khả năng stream/repair và backup.
~~~

~~~mermaid
flowchart TD
    A["Workload time series cần tối ưu"] --> B["Xác định truy vấn và cửa sổ thời gian"]
    B --> C["Ước lượng λ × T × B cho từng bucket"]
    C --> D{"Partition có quá lớn/nóng?"}
    D -->|Có| E["Thu nhỏ T hoặc thêm shard có kiểm soát"]
    D -->|Không| F["Đánh giá fan-out khi truy vấn qua nhiều bucket"]
    E --> F
    F --> G{"Fan-out có vượt SLO?"}
    G -->|Có| H["Bucket lớn hơn, projection hoặc rollup riêng"]
    G -->|Không| I["CQL đủ partition key + khoảng [start,end)"]
    H --> I
    I --> J["Java merge/sort/paginate, giới hạn concurrency"]
    J --> K["Đo p99, tombstone, SSTable, compaction, write rate"]
    K --> L["Chọn thiết kế đáp ứng cả read, write và maintenance"]
~~~

**Ghi nhớ:** time bucketing trong Cassandra là cách đưa **thời gian đã chuẩn hóa** vào **partition key** để giới hạn kích thước partition và định tuyến các read theo khoảng. Không nên chọn bucket nhỏ nhất có thể: một bucket nhỏ giảm dữ liệu mỗi partition nhưng làm tăng số partition cần đọc và chi phí merge. Thiết kế tốt phải đồng thời thỏa **partition size, write hotspot, số bucket mỗi truy vấn, khoảng [start,end), pagination, TTL/TWCS và SLO p99**. Hãy quyết định kích thước bucket từ **workload và số liệu đo**, không phải chỉ từ thói quen đặt partition theo ngày.
