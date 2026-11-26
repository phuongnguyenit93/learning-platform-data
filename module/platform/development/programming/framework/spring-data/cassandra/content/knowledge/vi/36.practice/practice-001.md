# Thực hành: Thiết kế bảng sự kiện theo thiết bị và nhóm thời gian từ mẫu truy vấn

Trong **Spring Data Cassandra**, cách thiết kế bảng hiệu quả bắt đầu từ **những câu hỏi ứng dụng phải trả lời**, không bắt đầu từ danh sách entity rồi tìm cách JOIN. Bài thực hành này xây dựng một luồng lưu và đọc sự kiện thiết bị trên **Apache Cassandra**, sử dụng partition key theo thiết bị và nhóm thời gian (time bucket), clustering key để sắp xếp sự kiện mới nhất trước, cùng repository, `CassandraTemplate` và truy vấn CQL khi cần kiểm soát khoảng thời gian hoặc paging.

Đích đến là một thiết kế có thể giải thích và kiểm chứng: tại sao chọn bucket ngày, câu truy vấn nào hợp lệ, lúc nào phải thêm bảng khác, giới hạn về kích thước partition, TTL, tính nhất quán và hiệu năng khi hệ thống được phân tán trên nhiều node.

## 1. Đề bài và tiêu chí hoàn thành

Giả sử một hệ thống quản lý thiết bị IoT nhận sự kiện đo đạc từ nhiều khách hàng doanh nghiệp (tenant). Mỗi sự kiện có:

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `tenant_id` | Định danh tenant sở hữu thiết bị | UUID của tổ chức |
| `device_id` | Định danh thiết bị trong tenant | UUID thiết bị |
| `event_id` | Định danh duy nhất do producer cấp, giữ nguyên khi retry | UUID sự kiện |
| `occurred_at` | Thời điểm sự kiện **xảy ra**, chuẩn hóa UTC | `2026-11-25T10:15:30Z` |
| `received_at` | Thời điểm hệ thống **tiếp nhận** | `2026-11-25T10:15:34Z` |
| `event_type` | Loại sự kiện | `TEMPERATURE`, `BATTERY_LOW`, `DISCONNECTED` |
| `severity` | Mức cảnh báo | `INFO`, `WARN`, `ERROR` |
| `value_numeric` | Giá trị đo, nếu có | `28.5` |

Các yêu cầu ban đầu:

1. **Q1 – Xem mới nhất:** lấy tối đa 50 sự kiện mới nhất của **một thiết bị thuộc một tenant** trong một ngày UTC.
2. **Q2 – Xem theo khoảng:** lấy sự kiện của thiết bị trong khoảng `[from, to)`, tối đa 7 ngày, mới nhất trước; trả kết quả từng trang.
3. **Q3 – Tra cứu chi tiết:** lấy một sự kiện khi đã biết đủ tenant, thiết bị, thời điểm xảy ra và `event_id`.
4. **Q4 – Xem cảnh báo:** lấy sự kiện `BATTERY_LOW` hoặc `ERROR` theo thời gian, nếu đây trở thành luồng truy cập thường xuyên.

Các giả định về tải và vận hành để thực hành:

- Có nhiều tenant; mỗi tenant có nhiều thiết bị. Đường đọc từ ứng dụng luôn biết tenant và device.
- Thiết bị thông thường tạo trung bình **1 sự kiện mỗi 30 giây**; đôi lúc tăng đột biến. Thiết bị đặc biệt có thể gửi nhanh hơn rất nhiều.
- Cần giữ dữ liệu sự kiện **30 ngày kể từ `occurred_at`**; chấp nhận sự kiện đến muộn tối đa **48 giờ**, nếu thời điểm thiết bị hợp lệ.
- Producer có thể gửi lặp cùng sự kiện do timeout. `event_id` và `occurred_at` phải ổn định giữa các lần gửi lại.
- API đọc danh sách cần phân trang và kiểm tra tenant/thiết bị theo danh tính đã xác thực.

**Sản phẩm cần nộp:** bảng ánh xạ truy vấn → khóa, câu lệnh tạo bảng, CQL đọc/ghi, mã Java minh họa cách tính bucket và gọi Cassandra, kế hoạch paging, phép tính kích thước partition, test plan và phần giải thích sự đánh đổi.

> Mục tiêu là luyện cách ra quyết định có số liệu. Các giá trị tải và retention ở trên là giả định của bài, không phải ngưỡng giới hạn phổ quát của Cassandra.

## 2. Bắt đầu từ mẫu truy vấn

Trước khi định nghĩa schema, viết điều kiện của từng đường đọc:

| Truy vấn | Điều kiện bắt buộc | Thứ tự | Đặc điểm thiết kế |
| --- | --- | --- | --- |
| Q1 | `tenant_id`, `device_id`, ngày UTC | `occurred_at` giảm dần | Một partition theo thiết bị và ngày |
| Q2 | `tenant_id`, `device_id`, `from`, `to` | Mới nhất trước | Tách khoảng thành nhiều bucket có giới hạn |
| Q3 | Toàn bộ khóa sự kiện | Không cần | Lookup theo primary key đầy đủ |
| Q4 | Thiết bị, loại sự kiện và ngày | Mới nhất trước | Có thể cần bảng đọc riêng nếu thường xuyên |

Từ bảng này, **thiết bị** là đơn vị đọc chính, còn **ngày** giới hạn phạm vi dữ liệu của mỗi partition. Vì yêu cầu đọc theo thời gian mới nhất trước, `occurred_at` phù hợp làm clustering key đầu tiên.

Không chọn một trong hai thiết kế sau:

```sql
-- Phản ví dụ 1: Tất cả sự kiện của tenant trong một partition lớn.
PRIMARY KEY ((tenant_id), device_id, occurred_at, event_id)

-- Phản ví dụ 2: Mọi sự kiện lịch sử của một thiết bị vào một partition.
PRIMARY KEY ((tenant_id, device_id), occurred_at, event_id)
```

Phản ví dụ 1 khiến một tenant đông thiết bị có partition tăng không giới hạn và việc đọc một thiết bị phải phụ thuộc vào hình dạng clustering key. Phản ví dụ 2 tránh trộn thiết bị nhưng **partition vẫn tăng liên tục theo thời gian**. Việc Cassandra không có JOIN tùy ý và không phù hợp `ALLOW FILTERING` trên dữ liệu lớn khiến ta phải tạo khóa từ những truy vấn được phép.

## 3. Lựa chọn time bucket và tính giới hạn partition

### 3.1. Bucket ngày theo UTC

Với khối lượng giả định thông thường, chọn ngày UTC làm bucket:

```text
bucket_day = UTC_DATE(occurred_at)

Sự kiện 2026-11-25T23:59:59Z -> bucket_day = 2026-11-25
Sự kiện 2026-11-26T00:00:00Z -> bucket_day = 2026-11-26
```

Tại sao phải thống nhất UTC? Nếu thiết bị ở nhiều múi giờ tự dùng ngày địa phương, cùng một khoảng truy vấn sẽ không xác định được bucket rõ ràng. Lưu `occurred_at` dưới dạng thời điểm tuyệt đối, rồi tính `bucket_day` theo UTC ở producer đáng tin cậy hoặc ingestion service.

**Lưu ý đồng hồ thiết bị:** timestamp lấy từ thiết bị có thể sai. Nếu nghiệp vụ dùng thời gian sự kiện, kiểm tra lệch đồng hồ, khoảng quá khứ/tương lai và định nghĩa cách xử lý timestamp bất thường. Nếu không tin được đồng hồ thiết bị, cân nhắc lập bảng theo `received_at` và đổi yêu cầu truy vấn tương ứng. Không âm thầm dùng hai loại thời gian để tính bucket.

### 3.2. Ước lượng số hàng và dung lượng

Ước lượng thô kích thước partition:

\[
\text{rows/bucket} \approx \text{events/second/device} \times \text{seconds/bucket}
\]

\[
\text{payload bytes/bucket} \approx \text{rows/bucket} \times \text{bytes/event}
\]

Với **1 sự kiện / 30 giây**, một thiết bị có khoảng `24 × 60 × 2 = 2.880` sự kiện/ngày. Nếu giả định mỗi hàng có 500 byte dữ liệu hữu ích thì dung lượng payload khoảng **1,44 MB/ngày** cho mỗi device, chưa tính overhead, index và các cấu trúc lưu trữ khác.

Nếu một thiết bị liên tục gửi **50 sự kiện/giây**:

| Bucket | Số sự kiện ước lượng | Payload @ 500 byte/sự kiện |
| --- | ---: | ---: |
| 1 ngày | 4.320.000 | ~2,16 GB |
| 1 giờ | 180.000 | ~90 MB |
| 5 phút | 15.000 | ~7,5 MB |

Đây là phép tính tham khảo, chưa phải kích thước `SSTable` hoặc ngưỡng tối ưu cố định. Dữ liệu thực cần đo **phân phối theo từng thiết bị**, số hàng, kích thước hàng, độ trễ đọc, tombstone và tải trên replica. Không lấy mức tải trung bình toàn hệ thống để che một vài thiết bị cực nóng.

**Quyết định của bài:** dùng bucket ngày cho lớp thiết bị thông thường. Nếu thiết bị gửi liên tục ở mức 50/s, cần thiết kế bucket giờ hoặc nhỏ hơn, hoặc một mô hình ingestion khác phù hợp. Việc thay đổi độ rộng bucket cần được version hóa rõ trong API/schema hoặc có quy tắc phân loại thiết bị ổn định; không tự đổi kích thước bucket ngẫu nhiên mà không biết cách tìm dữ liệu khi đọc.

### 3.3. Hệ quả đối với thao tác đọc

Bucket ngày nghĩa là truy vấn 7 ngày có thể phải đọc **tối đa 8 bucket** nếu hai mốc thời gian nằm ở các ngày không tròn và khoảng thực dài đúng 7×24 giờ. Ứng dụng phải liệt kê các ngày UTC giao với khoảng `[from, to)`; không thể thực hiện một câu `SELECT` với phạm vi timestamp trải qua tất cả partition và mong Cassandra tự duyệt theo thời gian toàn cục.

Khi đã chọn bucket, **partition key** chính xác là `(tenant_id, device_id, bucket_day)`. Mọi truy vấn được đưa ra trong bài sẽ cung cấp đủ ba giá trị này.

## 4. Thiết kế bảng Cassandra theo Q1–Q3

### 4.1. Schema đề xuất

```sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.device_events_by_day (
    tenant_id uuid,
    device_id uuid,
    bucket_day date,
    occurred_at timestamp,
    event_id uuid,
    received_at timestamp,
    event_type text,
    severity text,
    value_numeric double,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Tên datacenter `dc1` và RF=3 chỉ là ví dụ cho cụm có **ít nhất ba replica phù hợp trong dc1**. Khi thực hành trên Cassandra một node, tạo keyspace riêng với RF=1. Phải dùng đúng tên data center của môi trường thực tế; không đặt RF=3 rồi yêu cầu `LOCAL_QUORUM` trên một node và kết luận schema hỏng.

Tác dụng của từng thành phần khóa:

- **Partition key:** `tenant_id` + `device_id` + `bucket_day` đặt các sự kiện của một thiết bị trong một ngày vào cùng nhóm truy vấn.
- **Clustering key 1:** `occurred_at DESC` giúp lấy sự kiện mới nhất trước trong **một partition**.
- **Clustering key 2:** `event_id DESC` phân biệt hai sự kiện có cùng thời điểm và tạo thứ tự xác định khi các timestamp trùng nhau.
- **`received_at`:** trường bình thường để quan sát độ trễ ingestion; không tham gia chọn bucket.

CQL `timestamp` có độ chính xác đến **mili giây**. Hai sự kiện rất sát nhau có thể có cùng `occurred_at` sau khi lưu. `event_id` trong clustering key cho phép hai bản ghi cùng timestamp được lưu riêng và tạo thứ tự ổn định. Thứ tự UUID là cách phân giải khi bằng timestamp, không biểu diễn “sự kiện nào đến trước”.

### 4.2. Bảng đáp ứng truy vấn nào?

| Đường đọc | Bảng này phù hợp? | Giải thích |
| --- | --- | --- |
| Một thiết bị trong một ngày | Có | Chỉ một partition, clustering đã sắp mới nhất trước |
| Một thiết bị trong 7 ngày | Có, qua service | Duyệt các bucket ngày rồi ghép kết quả |
| Một sự kiện biết đủ khóa | Có | Lookup theo primary key |
| Tất cả thiết bị của tenant trong một giờ | Không trực tiếp | Cần bảng/luồng tổng hợp theo tenant và bucket phù hợp |
| Sự kiện `ERROR` trong tất cả thiết bị | Không trực tiếp | Cần bảng đọc/công cụ tìm kiếm chuyên biệt |
| Lọc `event_type` trong bảng trên | Không hiệu quả khi không có mô hình bổ sung | `event_type` là cột thường, không nằm trong khóa tìm kiếm |

Đừng khắc phục các dòng “không trực tiếp” bằng cách chèn `ALLOW FILTERING` cho workload lớn. Cần xác nhận mẫu truy vấn mới đủ thường xuyên và quan trọng trước khi tạo bảng phục vụ nó.

## 5. Ghi sự kiện và duy trì khóa ổn định

### 5.1. CQL ghi một sự kiện

```sql
INSERT INTO telemetry.device_events_by_day (
    tenant_id, device_id, bucket_day,
    occurred_at, event_id, received_at,
    event_type, severity, value_numeric
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
```

Tất cả thành phần primary key phải có giá trị. Đừng dùng thời điểm hiện tại tại mỗi lần retry để tạo `occurred_at` mới; cùng `event_id` nhưng `occurred_at` khác sẽ hình thành **một primary key khác** và tạo hàng trùng.

Một quy trình ingestion:

```text
1. Nhận event + danh tính tenant và device đã xác thực.
2. Kiểm tra event_id, occurred_at, event_type và schema.
3. Chuẩn hóa occurred_at theo UTC; từ chối thời điểm ngoài chính sách.
4. Tính bucket_day = UTC_DATE(occurred_at).
5. Tạo mutation với primary key bất biến giữa các lần gửi lại.
6. Ghi Cassandra bằng prepared statement; ghi nhận kết quả/timeout.
7. Chỉ publish hoặc phản hồi trạng thái dựa trên hợp đồng idempotency đã định.
```

### 5.2. Idempotency khác việc kiểm tra tồn tại trước

Một `INSERT` không có `IF NOT EXISTS` là upsert theo khóa trong Cassandra. Gửi lại **cùng primary key và nội dung ổn định** giúp hạn chế trùng hàng, nhưng không tự bảo đảm semantics “xử lý chính xác một lần” trên toàn workflow. Ghi lại với TTL khác, timestamp khác hoặc phát thêm sự kiện ra broker có thể gây hậu quả khác.

`INSERT ... IF NOT EXISTS` là LWT và có thể chặn overwrite theo primary key, nhưng đắt hơn write thường. Không dùng LWT cho mọi sự kiện telemetry ở lưu lượng cao nếu không có yêu cầu chống overwrite đủ mạnh. Thay vào đó, cân nhắc ID sự kiện ổn định, kiểm tra trùng ở ingestion hoặc ledger theo phạm vi cần thiết, và giới hạn các side effect.

## 6. Viết truy vấn CQL tương ứng với mẫu đọc

### 6.1. Q1: sự kiện mới nhất trong một ngày

```sql
SELECT occurred_at, event_id, event_type, severity, value_numeric
FROM telemetry.device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
LIMIT 50;
```

Không cần `ORDER BY` khi schema đã khai báo clustering order giảm dần. Nếu thêm `ORDER BY occurred_at DESC`, Cassandra chỉ hỗ trợ sắp theo clustering key trong **một partition**, không phải sort toàn bộ dữ liệu của tenant trên nhiều partition.

### 6.2. Q2: lấy một đoạn thời gian trong một ngày

```sql
SELECT occurred_at, event_id, event_type, severity, value_numeric
FROM telemetry.device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 50;
```

Khoảng thời gian có dạng **`[from, to)`**, gồm `from` và không gồm `to`. Cách này giúp hai trang/ngày hoặc hai khung thời gian kề nhau có ranh giới xác định. Đây là range scan trên clustering key `occurred_at` bên trong **một partition**, không phải lọc các hàng của toàn cluster.

Ví dụ khoảng `[2026-11-25T23:50:00Z, 2026-11-26T00:10:00Z)` cần chạy hai query:

| Bucket | `from` trong bucket | `to` trong bucket |
| --- | --- | --- |
| `2026-11-26` | `2026-11-26T00:00:00Z` | `2026-11-26T00:10:00Z` |
| `2026-11-25` | `2026-11-25T23:50:00Z` | `2026-11-26T00:00:00Z` |

Mặc dù giới hạn trên của query đầu ngày có thể là mốc ngày kế tiếp, Cassandra vẫn quét **partition có `bucket_day` đã cung cấp**. Ứng dụng tính đoạn giao giữa khoảng người dùng yêu cầu và từng bucket để các query không bỏ sót dữ liệu.

### 6.3. Q3: tra một sự kiện bằng đủ khóa

```sql
SELECT tenant_id, device_id, bucket_day, occurred_at, event_id,
       received_at, event_type, severity, value_numeric
FROM telemetry.device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
  AND occurred_at = ?
  AND event_id = ?;
```

Vì `event_id` **không nằm ở partition key duy nhất** mà đứng sau `occurred_at` trong clustering key, một API “chỉ biết event_id” **không thể** tra trực tiếp trên bảng này. Nếu cần đường lookup đó, thiết kế bảng `device_events_by_id`/ledger khác có khóa phù hợp và cập nhật nhất quán theo quy trình nghiệp vụ.

### 6.4. Những truy vấn không nên viết

```sql
-- Thiếu bucket_day, Cassandra không thể xác định partition:
SELECT * FROM telemetry.device_events_by_day
WHERE tenant_id = ? AND device_id = ?;

-- event_type không là phần khóa truy vấn:
SELECT * FROM telemetry.device_events_by_day
WHERE tenant_id = ? AND device_id = ? AND event_type = 'ERROR'
ALLOW FILTERING;

-- Không thể ORDER BY xảy ra trên nhiều partition tùy ý:
SELECT * FROM telemetry.device_events_by_day
WHERE tenant_id = ? ORDER BY occurred_at DESC;
```

Câu truy vấn thứ hai có thể được một số cấu hình cho chạy với `ALLOW FILTERING` nhưng không đáp ứng mục tiêu truy vấn dự đoán được về hiệu năng; đây là **phản ví dụ**, không phải gợi ý sử dụng.

## 7. Đọc qua nhiều bucket và phân trang

### 7.1. Duyệt các bucket từ mới đến cũ

Với `from`, `to` hợp lệ, bước đầu là xác định tất cả ngày UTC giao với `[from, to)`, liệt kê **giảm dần**. Nếu có đúng một thiết bị và mỗi sự kiện được đặt vào ngày của `occurred_at`, mọi sự kiện trong ngày mới hơn sẽ có thời gian lớn hơn mọi sự kiện trong ngày cũ. Vì vậy có thể **nối kết quả theo thứ tự bucket giảm dần** mà không cần sort toàn bộ dữ liệu của 7 ngày.

```text
validate tenant, device, 0 < (to - from) <= 7 days
days = intersectingUtcDays(from, to), newest first
remaining = 50

for day in days:
    bounds = intersect([from, to), [startOf(day), startOf(nextDay)))
    query ONE partition by (tenant, device, day)
          with clustering bounds and descending order
    append rows until remaining == 0
    if full page: return rows + opaque continuation cursor

return rows + no cursor
```

**Cảnh báo về quy mô:** 7 ngày có thể tương ứng 8 partition do khoảng tính bằng giờ đi qua hai ngày biên. Giới hạn **cửa sổ thời gian** và **số bucket** ở API để một người dùng không khởi động hàng nghìn truy vấn.

### 7.2. Cassandra paging khác phân trang của API

Java Driver có **fetch size/page size** và paging state cho từng câu truy vấn. API của bài cần tối đa 50 bản ghi **tổng cộng** xuyên nhiều bucket, nên không được coi một `PagingState` của Cassandra là con trỏ duy nhất cho nhiều partition.

Một continuation cursor do ứng dụng quản lý có thể chứa:

```json
{
  "cursorVersion": 1,
  "bucketDay": "2026-11-25",
  "driverPagingState": "opaque-or-null",
  "lastOccurredAt": "2026-11-25T10:15:30Z",
  "lastEventId": "79c39a11-2dfe-4e46-bf85-7a0cf63ead79"
}
```

Đây là **mô hình khái niệm**, không phải mã hóa token dùng nguyên văn trong production. Phải chọn một chiến lược nhất quán: dùng paging state của query hiện tại **hoặc** dùng cặp khóa cuối cùng để làm keyset continuation, quản lý chuyển bucket đúng cách; không trộn ngẫu nhiên cả hai mà thiếu quy tắc tránh lặp và bỏ sót.

Nếu dùng paging state của driver, token ứng dụng cần mang/tra cứu **bucket hiện tại, các tham số truy vấn bất biến, trạng thái query trong bucket và vị trí chuyển bucket**. Token phải có thời hạn, được ký hoặc lưu phía server, gắn với tenant/người dùng và bộ lọc; không coi nó là giấy phép vượt quyền. Nếu dùng keyset cursor, điều kiện so sánh trên `occurred_at` và `event_id` cần phù hợp clustering order và được kiểm chứng bằng CQL trong phiên bản Cassandra đang chạy.

**Giới hạn consistency:** paging state không tạo snapshot cố định qua nhiều request. Các mutation mới trong lúc user lật trang có thể làm kết quả thay đổi. Nếu sản phẩm yêu cầu ảnh chụp bất biến, phải thiết kế hợp đồng snapshot hoặc một luồng dữ liệu chuyên biệt, không hứa chỉ nhờ Cassandra paging.

### 7.3. Mẫu Java tính ngày giao khoảng

```java
public static List<LocalDate> utcDaysDescending(
        Instant fromInclusive, Instant toExclusive) {
    Objects.requireNonNull(fromInclusive);
    Objects.requireNonNull(toExclusive);

    if (!fromInclusive.isBefore(toExclusive)) {
        throw new IllegalArgumentException("Khoảng thời gian phải dương");
    }
    if (Duration.between(fromInclusive, toExclusive)
            .compareTo(Duration.ofDays(7)) > 0) {
        throw new IllegalArgumentException("Tối đa 7 ngày");
    }

    LocalDate first = fromInclusive.atZone(ZoneOffset.UTC).toLocalDate();
    LocalDate last = toExclusive.minusNanos(1)
        .atZone(ZoneOffset.UTC).toLocalDate();

    List<LocalDate> result = new ArrayList<>();
    for (LocalDate d = last; !d.isBefore(first); d = d.minusDays(1)) {
        result.add(d);
    }
    return result;
}
```

Đoạn mã trên chỉ tính bucket, **chưa phải implementation phân trang hoàn chỉnh**. Vì Cassandra `timestamp` có độ chính xác mili giây, nên chuẩn hóa/kiểm tra `from`, `to` đến độ chính xác được API hỗ trợ trước khi query để tránh mong đợi khác nhau ở ranh giới nano giây.

## 8. Thực hành Spring Data Cassandra: entity, repository và CQL

### 8.1. Mapping composite partition key và clustering key

Ví dụ rút gọn với Spring Data Cassandra:

```java
@PrimaryKeyClass
public class DeviceEventKey implements Serializable {
    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "device_id", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "bucket_day", ordinal = 2,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate bucketDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getter/setter, equals() và hashCode()
}

@Table("device_events_by_day")
public class DeviceEvent {
    @PrimaryKey
    private DeviceEventKey key;

    @Column("received_at")
    private Instant receivedAt;

    @Column("event_type")
    private String eventType;

    private String severity;

    @Column("value_numeric")
    private Double valueNumeric;

    // Constructor và getter/setter
}

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
```

Những kiểu quan trọng đến từ `java.util` và `java.time`, cùng `org.springframework.data.cassandra.core.mapping`, `org.springframework.data.cassandra.core.cql.Ordering` và `org.springframework.data.cassandra.repository.CassandraRepository`. Code rút gọn phần boilerplate; khi chạy, bổ sung constructor có thể được framework sử dụng, getter/setter, `equals/hashCode` cho key, cấu hình keyspace và dependency phù hợp với phiên bản dự án.

Repository `save` và `findById` hữu ích cho thao tác theo primary key. `CassandraTemplate` cung cấp cách khác để thao tác trên entity đã ánh xạ, ví dụ `cassandraTemplate.insert(event)` và `cassandraTemplate.selectOneById(key, DeviceEvent.class)` khi API phiên bản đang dùng hỗ trợ. Không mặc định rằng entity mapping tự tạo điều kiện lọc thời gian, authorization hoặc tự thêm `bucket_day` nếu ứng dụng không cung cấp.

### 8.2. Tính bucket trước khi tạo entity

```java
public DeviceEvent toEntity(
        UUID tenantId, UUID deviceId, IncomingEvent incoming,
        Clock clock) {
    Instant occurredAt = incoming.occurredAt();
    LocalDate bucketDay = occurredAt
        .atZone(ZoneOffset.UTC)
        .toLocalDate();

    DeviceEventKey key = new DeviceEventKey(
        tenantId, deviceId, bucketDay,
        occurredAt, incoming.eventId()
    );
    return new DeviceEvent(
        key, clock.instant(), incoming.eventType(),
        incoming.severity(), incoming.valueNumeric()
    );
}
```

Ví dụ minh họa giả định có constructor tương ứng với các field trong `DeviceEvent`/`DeviceEventKey`. `IncomingEvent` là DTO đầu vào cần được tự định nghĩa. `Clock` có thể inject để kiểm thử độ trễ và giới hạn timestamp. Phải kiểm tra `incoming.eventId()` không rỗng và timestamp hợp lệ trước khi ghi.

### 8.3. Đọc bằng prepared CQL khi cần khoảng thời gian

Khi cần điều kiện range và kiểm soát page, dùng `CqlSession` cùng prepared statement:

```java
PreparedStatement selectByDay = cqlSession.prepare(
    "SELECT occurred_at, event_id, event_type, severity, value_numeric " +
    "FROM telemetry.device_events_by_day " +
    "WHERE tenant_id = ? AND device_id = ? AND bucket_day = ? " +
    "AND occurred_at >= ? AND occurred_at < ?");

BoundStatement query = selectByDay.bind(
        tenantId, deviceId, bucketDay, fromInclusive, toExclusive)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);

ResultSet rows = cqlSession.execute(query);
for (Row row : rows) {
    Instant when = row.getInstant("occurred_at");
    UUID eventId = row.getUuid("event_id");
    // Ánh xạ từng row sang response DTO được phép công bố.
}
```

**Để ý:** vòng `for (Row row : rows)` của result set đồng bộ có thể **tự fetch thêm các trang phía driver**. Vì vậy đây là ví dụ về truy vấn và mapping, chưa phải handler giới hạn đúng 50 row rồi tạo continuation token. Trong endpoint thực, nên dùng các API fetch trang tường minh (chẳng hạn `executeAsync` và `AsyncResultSet.currentPage()` của Driver 4), quản lý paging state và dừng khi đủ page size của API.

Không đưa toàn bộ entity hoặc `Row` ra REST response; trả DTO chỉ có những trường người xem được quyền thấy. Tenant phải lấy từ identity đã xác thực, còn thiết bị phải thuộc phạm vi cho phép của người đó.

## 9. Khi mẫu truy vấn thay đổi: tạo bảng đọc bổ sung

Giả sử sản phẩm thường xuyên yêu cầu: “Xem 100 sự kiện `BATTERY_LOW` mới nhất của thiết bị trong một ngày”. Nếu lọc toàn bộ `device_events_by_day` ở Java, thiết bị nhiều sự kiện `TEMPERATURE` có thể phải đọc hàng nghìn row mới tìm được vài cảnh báo.

Đề xuất thêm bảng phục vụ **Q4**:

```sql
CREATE TABLE telemetry.device_events_by_type_day (
    tenant_id uuid,
    device_id uuid,
    event_type text,
    bucket_day date,
    occurred_at timestamp,
    event_id uuid,
    severity text,
    value_numeric double,
    PRIMARY KEY (
        (tenant_id, device_id, event_type, bucket_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
```

Truy vấn:

```sql
SELECT occurred_at, event_id, severity, value_numeric
FROM telemetry.device_events_by_type_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_type = ?
  AND bucket_day = ?
LIMIT 100;
```

Thiết kế này **tăng chi phí ghi và lưu trữ** vì mỗi sự kiện có thể xuất hiện ở hai bảng. Nếu chỉ cần xem `ERROR` rất hiếm, một bảng chỉ lưu cảnh báo có thể tiết kiệm hơn so với nhân bản mọi loại sự kiện. Nếu cần báo cáo toàn bộ thiết bị của tenant theo loại, lại phải xem xét đường truy vấn và phân vùng khác.

Không có giao dịch nguyên tử tổng quát giữa hai partition của hai bảng. Khi ghi bảng gốc thành công nhưng bảng theo loại thất bại, danh sách Q4 có thể trễ/thiếu tạm thời. Cần quy trình retry idempotent, reconciliation và đánh giá độ trễ chấp nhận được. Trước khi thêm bảng, đo thực tế tần suất truy vấn Q4 và khả năng chấp nhận một truy vấn từ dữ liệu đã cache/tổng hợp.

## 10. TTL và retention cho dữ liệu time-series

### 10.1. TTL tính từ thời điểm ghi, không tự dựa vào `occurred_at`

Yêu cầu giữ dữ liệu **30 ngày kể từ khi sự kiện xảy ra** khác với “đặt TTL 30 ngày kể từ khi Cassandra nhận bản ghi”. Một event xảy ra 48 giờ trước nhưng đến bây giờ, nếu dùng TTL 30 ngày tại thời điểm ghi sẽ bị giữ khoảng **32 ngày kể từ lúc xảy ra**.

Nếu business yêu cầu hạn tuyệt đối, ứng dụng cần tính:

```java
Instant expiresAt = occurredAt.plus(Duration.ofDays(30));
long remainingSeconds =
    Duration.between(clock.instant(), expiresAt).getSeconds();

if (remainingSeconds <= 0) {
    // Từ chối hoặc bỏ qua sự kiện đã quá hạn lưu trữ.
} else {
    int ttlSeconds = Math.toIntExact(remainingSeconds);
    // Dùng TTL này cho toàn bộ các giá trị cần cùng vòng đời.
}
```

Làm tròn theo giây và sai lệch clock có thể ảnh hưởng thời điểm hết hiệu lực ở ranh giới; nếu cần đúng giây tuyệt đối, lưu thêm thời điểm hết hạn và kiểm soát khi đọc. Nếu không có yêu cầu giữ chính xác theo `occurred_at`, có thể chọn chính sách đơn giản “30 ngày từ lúc nhận”, nhưng phải ghi rõ sự khác biệt trong hợp đồng retention.

CQL:

```sql
INSERT INTO telemetry.device_events_by_day (
    tenant_id, device_id, bucket_day, occurred_at, event_id,
    received_at, event_type, severity, value_numeric
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
```

TTL gắn với ô dữ liệu được ghi (không phải toàn bộ object Java theo một đồng hồ riêng). Các lệnh cập nhật về sau có thể thay đổi TTL của ô được ghi, nên phải thống nhất chính sách ghi lại. Nếu nhân bản sang bảng `device_events_by_type_day`, tính TTL theo **cùng hạn tuyệt đối** để tránh một bảng sống lâu hơn bảng kia ngoài dự kiến.

### 10.2. Tombstone, compaction và late arrivals

TTL hết hạn không có nghĩa ô dữ liệu biến mất tức thì khỏi ổ đĩa; tombstone và compaction quyết định khi nào dữ liệu được thu gom an toàn. Truy vấn quét nhiều dữ liệu hết hạn trong một partition có thể gặp độ trễ cao. Cần đo tombstone-scanned, read latency, kích thước partition và compaction backlog.

`TimeWindowCompactionStrategy` (TWCS) có thể phù hợp với chuỗi thời gian append-only và TTL tương đối đồng nhất, nhưng **không chọn chỉ vì bảng có cột thời gian**. Event đến muộn hoặc cập nhật lại ô cũ có thể tạo SSTable chứa dữ liệu thuộc nhiều thời điểm; cần kiểm chứng chiến lược compaction với mẫu ghi, bucket size, retention và cách sửa dữ liệu thực tế.

Không giảm `gc_grace_seconds` tùy tiện khi chưa hiểu replica ngừng hoạt động, repair và nguy cơ dữ liệu đã xóa xuất hiện lại.

## 11. Tính nhất quán và xử lý lỗi trong đường ingestion

Trong hệ nhiều replica, consistency level quyết định điều kiện phản hồi và sự đánh đổi độ trễ/khả dụng. Ví dụ ở một DC với RF=3:

| Ghi/đọc | Ý nghĩa thực tế | Lưu ý |
| --- | --- | --- |
| `ONE` | Một replica phản hồi là đủ cho thao tác tương ứng | Có thể gặp dữ liệu chưa hội tụ khi đọc ở replica khác |
| `LOCAL_QUORUM` | Cần hai trong ba replica ở DC cục bộ | Mạnh hơn về điều kiện phản hồi nhưng chi phí/khả dụng khác |
| `ALL` | Cần đủ cả ba replica | Mất một replica có thể khiến request không hoàn tất |

Việc chọn CL phải dựa vào SLO, yêu cầu tính đúng và topology. Không thể suy ra mọi truy vấn `LOCAL_QUORUM` là tuyến tính hóa tuyệt đối khi có các ghi đồng thời và timestamp. Nếu sự kiện chỉ là dữ liệu append-only và mỗi event có khóa riêng, thường không cần LWT cho mọi ghi; nếu một trạng thái nghiệp vụ cần compare-and-set, thiết kế LWT hoặc `@Version` riêng cho invariant đó.

Các trường hợp bắt buộc phân biệt:

- **Ghi thành công:** mutation đã được Cassandra xác nhận theo CL được yêu cầu.
- **Timeout khi ghi:** client có thể **không biết** mutation đã áp dụng tới replica nào. Retry phải giữ ổn định khóa, idempotency và chính sách TTL.
- **Unavailable:** không đủ replica/đường truy cập đáp ứng CL; cần báo lỗi hạ tầng, không giả vờ “sự kiện đã lưu”.
- **Duplicate event ID:** nếu cùng `event_id` nhưng khác `occurred_at`, bảng hiện tại không tự phát hiện là cùng sự kiện; kiểm tra quy tắc định danh đầu vào hoặc dùng ledger khi thật sự cần.
- **Cập nhật hai bảng đọc:** một bên thành công không bảo đảm bên còn lại đã xong; cần reconciliation.

Để tránh quá tải trong sự cố, retry cần deadline tổng, số lần giới hạn và backoff có jitter. Tránh đồng thời retry ở API, queue consumer và Java Driver mà không tính số lần thực tế.

## 12. Bảo mật: không dùng partition key thay cho phân quyền

Thiết kế bảng có `tenant_id` trong khóa giúp định vị dữ liệu, nhưng không tự bảo đảm người gọi được xem sự kiện. Endpoint cần lấy tenant từ identity đã xác thực, xác minh device thuộc người/nhóm được cấp quyền và chỉ công bố những trường cần thiết.

Không đưa tất cả nội dung telemetry, token thiết bị hoặc ghi chú nhạy cảm vào log lỗi CQL. Các log hữu ích nên có `operation`, loại event, kết quả, duration, loại lỗi và correlation ID; cân nhắc hash/pseudonym với chính sách rõ ràng nếu cần truy vết device. Đừng dùng `device_id` hay `event_id` làm nhãn metric Prometheus vì cardinality quá cao.

Continuation token của API phải ràng buộc với tenant, device, query và thời hạn sử dụng. Không cho người dùng thay `bucket_day` hoặc paging state của người khác để vượt phạm vi quyền.

## 13. Dữ liệu mẫu và các bài kiểm tra truy vấn

Tạo hai UUID cụ thể trong môi trường thực hành: `tenantA` và `deviceA`. Giả sử các sự kiện sau được chấp nhận (mỗi dòng có `event_id` khác nhau):

| `occurred_at` (UTC) | `event_type` | `severity` | `bucket_day` |
| --- | --- | --- | --- |
| `2026-11-25T23:59:59Z` | `BATTERY_LOW` | `WARN` | `2026-11-25` |
| `2026-11-25T23:58:00Z` | `TEMPERATURE` | `INFO` | `2026-11-25` |
| `2026-11-25T10:15:30Z` | `DISCONNECTED` | `ERROR` | `2026-11-25` |
| `2026-11-25T10:15:30Z` | `TEMPERATURE` | `INFO` | `2026-11-25` |
| `2026-11-24T23:59:59Z` | `TEMPERATURE` | `INFO` | `2026-11-24` |
| `2026-11-24T02:00:00Z` | `BATTERY_LOW` | `WARN` | `2026-11-24` |

### Bài kiểm tra A: Q1 một ngày

Với `bucket_day = 2026-11-25`, kỳ vọng 4 sự kiện, mới nhất trước. Hai sự kiện cùng `10:15:30Z` được phân biệt và sắp ổn định bằng `event_id`. Không khẳng định sự kiện nào của cặp này “xảy ra trước” chỉ dựa vào UUID.

### Bài kiểm tra B: Q2 qua nửa đêm

Truy vấn `[2026-11-24T23:59:59Z, 2026-11-25T10:15:31Z)`. Kết quả phải chứa một sự kiện cuối ngày 24 và hai sự kiện lúc 10:15:30 ngày 25; không chứa sự kiện ngày 25 lúc 23:58 hoặc sự kiện ngày 24 lúc 02:00.

### Bài kiểm tra C: Tenant isolation

Tạo `tenantB` có một `device_id` trùng UUID với `deviceA` của tenant A. Truy vấn bằng `tenantA` và `tenantB` phải độc lập, và endpoint của người dùng tenant A không được nhận dữ liệu tenant B.

### Bài kiểm tra D: Retry và dữ liệu đến muộn

Gửi một sự kiện với cùng khóa hai lần; xác minh không tạo thêm hàng. Gửi sự kiện xảy ra 36 giờ trước và kiểm tra nó nằm trong bucket của **`occurred_at`**, đồng thời TTL còn lại được tính từ thời điểm xảy ra. Thử event ID trùng nhưng timestamp khác để kiểm tra chính sách từ chối hoặc ledger nếu yêu cầu chống trùng toàn cục.

### Bài kiểm tra E: Paging

Tạo ít nhất 125 sự kiện trong một partition, query page size 50; kiểm tra lần lượt 50, 50, 25 sự kiện **trên tập dữ liệu không đổi**. Sau đó tạo 125 sự kiện trải trên hai bucket và kiểm tra cursor API chuyển bucket đúng khi trang kết thúc giữa một ngày. Kiểm tra riêng việc dữ liệu được thêm trong lúc phân trang để xác định giới hạn của hợp đồng.

## 14. Test một node và test nhiều node chứng minh khác nhau

| Nhóm test | Môi trường | Điều được kiểm chứng |
| --- | --- | --- |
| Unit test | Fake/repository mock | Tính `bucket_day` UTC, validation, retention, danh sách bucket và business response |
| Integration một node | Cassandra thật/Testcontainers, RF=1 | CQL, mapping, thứ tự clustering, range, paging cơ bản, TTL, repository/`CassandraTemplate` |
| Integration nhiều node | Cụm RF=3 thật, CL được cấu hình rõ | Hành vi khi một replica mất, latency/error theo `ONE` và `LOCAL_QUORUM`, kết quả sau retry |
| Fault test | Network delay/partition, timeout trong ghi | Đối soát outcome chưa biết, duplicate handling, đồng bộ bảng phụ |
| Load test | Phân phối thiết bị thường + hot devices | Partition size, p95/p99 query latency, tombstone và throughput ingestion |

Không gọi một container Cassandra là phép thử “quorum nhiều replica”. Nếu kiểm tra CL trên RF=1, quorum chỉ có ý nghĩa của một replica. Để đo chịu lỗi node phải dựng nhiều node **trong cùng cluster**, RF phù hợp, có kiểm tra `nodetool status` và theo dõi coordinator/replica thực sự.

Trong bài test tải, cần ít nhất hai profile: thiết bị gửi ít đều đặn và thiết bị gửi bùng nổ. Kiểm tra trường hợp `LIMIT 50` thường nhanh nhưng truy vấn range 7 ngày trên partition cực lớn có thể tốn nhiều fetch; lưu số partition đã đọc, page được tải, latency, tombstone-scanned và kích thước partition.

## 15. Quy trình thực hành theo từng bước

1. **Chốt query contract:** ghi rõ Q1–Q4, khoảng `[from,to)`, số ngày tối đa, quyền truy cập và thứ tự yêu cầu.
2. **Đo hoặc giả định tải:** ước tính sự kiện/thiết bị/giây, kích thước hàng, đỉnh tải, ngày giữ lại và số bucket phải truy cập.
3. **Chọn partition/clustering:** giải thích vì sao `((tenant_id,device_id,bucket_day),occurred_at,event_id)` đáp ứng Q1–Q3.
4. **Tạo schema:** chạy CQL trên keyspace RF tương ứng môi trường; xác nhận schema và tên DC.
5. **Ghi thử:** tạo ID ổn định, tính bucket UTC, insert sự kiện có timestamp trùng và sự kiện đi qua nửa đêm.
6. **Đọc thử:** chạy Q1, Q2, Q3; xác minh kết quả và thứ tự như dữ liệu mẫu.
7. **Tích hợp Spring:** tạo entity/key, repository; dùng prepared CQL cho range/paging; giới hạn DTO theo quyền.
8. **Thiết kế cursor:** xác định bucket, state, tính toàn vẹn và cách chuyển bucket; kiểm tra không trùng/mất row trên dữ liệu cố định.
9. **Áp retention:** kiểm thử TTL tuyệt đối từ `occurred_at` và dữ liệu đến muộn; đánh giá tombstone/compaction.
10. **Đánh giá Q4:** nếu truy vấn loại sự kiện phổ biến, tạo bảng theo loại và kế hoạch đồng bộ; nếu không, ghi rõ chưa cần.
11. **Thử tải và sự cố:** đo partition, latency, xử lý timeout/duplicate; chỉ kết luận consistency nhiều replica nếu đã thực sự chạy cluster nhiều node.
12. **Viết báo cáo quyết định:** ghi assumption, sơ đồ khóa, query, metric và những trường hợp chưa được kiểm chứng.

## 16. Tiêu chí chấm bài và câu hỏi tự đánh giá

| Tiêu chí | Bằng chứng mong đợi |
| --- | --- |
| Phù hợp query-first | Mỗi Q1–Q4 được map rõ tới bảng, khóa và điều kiện CQL |
| Partition có giới hạn | Có phép tính số row/byte theo tốc độ thiết bị và độ rộng bucket |
| Thứ tự đúng | Clustering `occurred_at DESC, event_id DESC`; hiểu phạm vi thứ tự theo partition |
| Khóa ổn định khi retry | `event_id`, `occurred_at`, bucket và tenant không đổi; có chính sách duplicate |
| API khoảng thời gian | Đúng `[from,to)`, UTC, truy vấn nhiều bucket và giới hạn số ngày |
| Paging | Cursor tiếp tục được trong bucket và qua bucket, giữ quyền theo tenant |
| Lifecycle | TTL từ thời gian được định nghĩa, xử lý late events và tombstone |
| Spring Data Cassandra | Mapping khóa ghép hợp lý, repository/template và CQL được dùng đúng mục đích |
| Vận hành phân tán | Hiểu RF/CL, timeout chưa rõ kết quả và giới hạn bằng chứng một node |
| An toàn và hiệu năng | Tenant authorization, projection/DTO, quan sát hot partition và lỗi tải |

**Câu hỏi kiểm tra tư duy:**

1. Nếu tăng tải lên 500 sự kiện/giây/thiết bị liên tục, tại sao bucket ngày và ngay cả bucket giờ có thể không còn phù hợp?
2. Nếu thiết bị gửi sự kiện cũ hơn 30 ngày, việc dùng `USING TTL 2592000` có đúng chính sách giữ 30 ngày từ `occurred_at` không?
3. Vì sao truy vấn “sự kiện mới nhất trên toàn bộ thiết bị trong tenant” không thể tự động lấy từ bảng `device_events_by_day` bằng một `ORDER BY`?
4. Vì sao hai sự kiện cùng `occurred_at` vẫn cần `event_id` trong clustering key?
5. Vì sao `LOCAL_QUORUM` trên một cluster RF=1 không chứng minh hệ thống chịu lỗi một replica?
6. Vì sao API có thể trả trùng row khi phân trang nếu dữ liệu mới được ghi giữa các request hoặc cursor chuyển bucket sai?
7. Nếu ghi bảng nguồn thành công còn bảng theo loại thất bại, ứng dụng cần cơ chế nào để Q4 không sai mãi?

**Kết luận:** Bảng sự kiện tốt trong Spring Data Cassandra được thiết kế từ đường đọc có thật: **partition theo tenant, thiết bị và bucket thời gian; clustering theo thời điểm giảm dần và ID để phân biệt sự kiện**. Khi số liệu tải thay đổi, phải đánh giá lại bucket, số partition truy cập, TTL và chi phí bảng bổ sung. Thực hành hoàn chỉnh còn cần mapping đúng, CQL hợp lệ, phân trang qua bucket, phân quyền tenant và kiểm thử phân tán tương xứng với những cam kết của API.
