# Chia nhóm theo thời gian để giới hạn kích thước partition

Trong **Apache Cassandra**, các hàng có cùng **partition key** thuộc một partition. Nếu khóa phân vùng chỉ gồm mã thiết bị, mã khách hàng hoặc mã tài khoản, dữ liệu sự kiện có thể dồn vào một partition ngày càng lớn. Khi ứng dụng sử dụng **Spring Data Cassandra** qua entity, repository, `CassandraTemplate` hoặc CQL, framework không tự động chia nhỏ partition: việc đó phải được thiết kế ở **khóa phân vùng** và **đường truy vấn**.

**Time bucketing** (chia nhóm theo thời gian) là kỹ thuật đưa một khoảng thời gian, chẳng hạn ngày, giờ hoặc tháng, vào partition key. Nhờ vậy dữ liệu của cùng một đối tượng được tách thành nhiều partition có giới hạn tăng trưởng theo từng khoảng. Bài học thuộc chương **Khóa và phân vùng**, tập trung vào cách chọn bucket theo truy vấn, ước tính kích thước, thiết kế CQL, xử lý dữ liệu đến muộn và đọc/phân trang qua nhiều bucket trong mô hình phân tán.

## 1. Vì sao partition key chỉ có ID dễ trở thành vấn đề?

Giả sử hệ thống thu thập sự kiện của thiết bị IoT. Màn hình cần hiển thị **100 sự kiện mới nhất của một thiết bị**, đôi khi lọc theo khoảng ngày.

Một bảng ban đầu có thể được thiết kế như sau:

~~~sql
-- Minh họa lựa chọn dễ dẫn tới partition tăng liên tục.
CREATE TABLE telemetry_ks.events_by_device (
    device_id   uuid,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload_ref text,
    PRIMARY KEY (device_id, occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Ở đây, **partition key chỉ là `device_id`**; `occurred_at` và `event_id` là **clustering columns**, được dùng để phân biệt và sắp xếp các hàng trong partition. Vì thế mọi sự kiện của một thiết bị có thể nằm trong **một partition duy nhất** bất kể chúng trải dài bao nhiêu tháng.

~~~text
Partition (device_id=A)
  ├── sự kiện tháng 11
  ├── sự kiện tháng 10
  ├── sự kiện tháng 09
  ├── ...
  └── sự kiện những năm trước
~~~

Partition lớn có thể làm tăng chi phí đọc/ghi, thao tác với SSTable, compaction, streaming và repair, đặc biệt khi có nhiều tombstone hoặc các truy vấn đọc rộng. Ngoài ra, cùng một partition key có thể tạo **hot partition** nếu thiết bị A ghi quá nhanh: các replica chứa partition đó phải xử lý một tỷ lệ lưu lượng lớn.

Thêm `LIMIT 100` không làm giảm số hàng đang được lưu trong partition. Nó chỉ giới hạn kết quả của lần đọc. Cũng không thể dùng clustering key để Cassandra tự phân tán những tháng khác nhau thành các partition khác nhau.

## 2. Time bucket làm thay đổi partition key như thế nào?

Thay khóa `device_id` bằng **`(device_id, bucket_day)`**, trong đó `bucket_day` là ngày được tính thống nhất từ thời điểm sự kiện.

~~~text
Trước khi bucketing:
  (device A)
     └── mọi sự kiện qua nhiều năm

Sau khi bucketing theo ngày:
  (device A, 2026-11-23) ── sự kiện ngày 23
  (device A, 2026-11-24) ── sự kiện ngày 24
  (device A, 2026-11-25) ── sự kiện ngày 25
~~~

Với cùng một thiết bị, mỗi ngày trở thành một partition khác nhau. Nếu thêm nhiều sự kiện trong ngày 25/11, partition của ngày đó lớn lên; sự kiện ngày 26/11 được ghi vào partition khác.

**Phân biệt hai lớp khóa:**

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Partition key | `(device_id, bucket_day)` | Nhóm sự kiện cùng thiết bị và cùng ngày; quyết định token phân phối |
| Clustering key | `(occurred_at, event_id)` | Xác định hàng và thứ tự sự kiện trong partition |
| Toàn bộ primary key | `(device_id, bucket_day, occurred_at, event_id)` | Định danh duy nhất một hàng trong bảng |

**Bucket không nhất thiết là một bảng mới.** Tất cả ngày vẫn nằm trong cùng bảng; khác nhau ở giá trị partition key. Các replica vẫn được Cassandra lựa chọn theo token và cấu hình replication của keyspace.

## 3. Thiết kế bảng CQL với bucket theo ngày

Kịch bản: biết `device_id`, muốn đọc sự kiện trong ngày theo thời gian giảm dần.

~~~sql
CREATE TABLE telemetry_ks.events_by_device_day (
    device_id   uuid,
    bucket_day  date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload_ref text,
    PRIMARY KEY ((device_id, bucket_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Hai dấu ngoặc quanh `(device_id, bucket_day)` chỉ **partition key tổng hợp**. Nếu viết:

~~~sql
PRIMARY KEY (device_id, bucket_day, occurred_at, event_id)
~~~

thì **chỉ `device_id` là partition key**; `bucket_day` trở thành clustering column, và mục tiêu chia partition theo ngày **không đạt được**. Đây là lỗi mô hình dữ liệu dễ gặp khi chuyển từ thiết kế SQL quan hệ sang Cassandra.

Truy vấn trong đúng một bucket:

~~~sql
SELECT occurred_at, event_id, event_type, payload_ref
FROM telemetry_ks.events_by_device_day
WHERE device_id = ? AND bucket_day = ?
LIMIT 100;
~~~

Dấu `?` đại diện tham số bound trong prepared statement. Truy vấn cung cấp **đủ hai thành phần partition key**, cho phép Cassandra định tuyến tới các replica của partition tương ứng. Do bảng có `CLUSTERING ORDER BY (... DESC)`, các hàng được đọc theo thứ tự clustering đã khai báo.

Lọc tiếp khoảng thời gian trong partition đã biết:

~~~sql
SELECT occurred_at, event_id, event_type
FROM telemetry_ks.events_by_device_day
WHERE device_id = ?
  AND bucket_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
~~~

Điều kiện range trên clustering column đầu tiên là phù hợp với mô hình khóa ở trên. Vẫn cần chú ý CQL có quy tắc riêng về thứ tự và điều kiện trên các clustering columns; không thể tùy ý lọc theo một cột bất kỳ rồi mong Cassandra xử lý như hệ quản trị quan hệ.

## 4. Chọn độ rộng bucket dựa trên tải và truy vấn

Một bucket ngày không phải lúc nào cũng tốt nhất. Khoảng thời gian càng ngắn, mỗi partition thường càng ít dữ liệu nhưng số partition phải đọc cho truy vấn dài càng tăng.

| Bucket | Phần dữ liệu của một thiết bị trong partition | Chi phí đọc khi xem 30 ngày |
| --- | --- | --- |
| **Theo tháng** | Sự kiện một tháng | Có thể cần 1–3 partition tùy ranh giới tháng |
| **Theo ngày** | Sự kiện một ngày | Có thể cần khoảng 30–31 partition |
| **Theo giờ** | Sự kiện một giờ | Có thể cần khoảng 720 partition |
| **Theo 15 phút** | Sự kiện trong 15 phút | Có thể cần khoảng 2.880 partition |

Số partition trên chỉ là **số bucket tối đa cần xét cho một khoảng thời gian điển hình**, có thể khác do biên khoảng, múi giờ và những bucket không có dữ liệu. Không nên đọc hàng trăm hoặc hàng nghìn partition chỉ để hiển thị vài sự kiện nếu một bucket lớn hơn đã đáp ứng yêu cầu vận hành.

### Tính số hàng và dung lượng dự kiến

Gọi:

- `R`: số **hàng mới, khác primary key**, do một thiết bị tạo ra trong một giây trung bình.
- `T`: số giây của một bucket.
- `B`: byte/hàng trung bình dựa trên đo đạc hoặc giả định lập kế hoạch.

Công thức ước lượng ban đầu:

~~~text
Số hàng/bucket ≈ R × T
Dung lượng/bucket ≈ số hàng/bucket × B + overhead
~~~

Ví dụ giả định: một thiết bị tạo **360.000 sự kiện mỗi ngày**, mỗi hàng trung bình **400 byte** ở mức ước lượng lập kế hoạch.

| Phương án | Hàng/partition khi phân bố đều | Dung lượng dữ liệu ước lượng |
| --- | ---: | ---: |
| Một bucket ngày | 360.000 | 144 MB |
| Một bucket 6 giờ | 90.000 | 36 MB |
| Một bucket giờ | 15.000 | 6 MB |

Đơn vị MB ở đây là **thập phân**, chưa cộng metadata, compression, tombstone, các SSTable tạm thời hoặc chi phí vận hành. Đây là **kịch bản minh họa**, không phải ngưỡng tối đa hoặc kích thước thực tế bắt buộc của Cassandra.

**Đừng chỉ tính trung bình.** Nếu 80% sự kiện dồn vào một giờ cao điểm, bucket giờ cao điểm có thể chứa khoảng **288.000 hàng** (115,2 MB theo giả định) thay vì 15.000 hàng. Độ lệch tải và kích thước partition lớn nhất đáng chú ý hơn nhiều so với giá trị trung bình.

Khi chốt độ rộng bucket, cần đo đồng thời:

1. Số hàng/partition lớn nhất và phân vị p95/p99 cho từng loại thiết bị, tenant.
2. Byte/hàng thực tế, mức độ biến động payload, update, delete và TTL.
3. Tốc độ đọc/ghi cao điểm vào **một partition**, không chỉ tổng lưu lượng cluster.
4. Khoảng thời gian mà giao diện hoặc API thường truy vấn.
5. Số bucket phải truy cập cho một trang kết quả và khả năng gộp dữ liệu.
6. Tăng trưởng trong 3, 6, 12 tháng và thời gian lưu giữ.

Cassandra không có một giá trị “MB/partition luôn an toàn” áp dụng cho mọi hệ thống; cần đo với kích thước hàng, khối lượng truy vấn, phần cứng, phiên bản và chiến lược compaction cụ thể.

## 5. Tính bucket nhất quán khi ghi

Thời điểm sự kiện (`occurred_at`) và thời điểm hệ thống nhận sự kiện (`received_at`) **có thể khác nhau**. Trước khi lập bucket, cần quyết định dữ liệu được nhóm theo thời điểm nào.

**Nếu truy vấn theo thời điểm sự kiện:** bucket được tính từ `occurred_at`. Một sự kiện phát sinh ngày 24 nhưng gửi chậm đến máy chủ ngày 25 vẫn thuộc bucket 24. Cách này phù hợp lịch sử sự kiện đúng theo thời gian thực tế.

**Nếu truy vấn theo thời điểm tiếp nhận:** có thể dùng `received_at` để tính bucket, nhưng phải thiết kế clustering column và nghiệp vụ theo cùng quy ước. Nếu trộn hai cách tính giữa ghi và đọc, ứng dụng có thể không tìm thấy bản ghi dù dữ liệu đã được lưu.

Ví dụ xác định ngày theo **UTC** trong Java:

~~~java
Instant occurredAt = event.occurredAt();
LocalDate bucketDay =
    occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
~~~

Trong triển khai thực tế cần quy định rõ múi giờ của bucket:

- **UTC:** ổn định cho dữ liệu kỹ thuật, sự kiện xuyên khu vực; xác định ngày theo UTC ở cả writer và reader.
- **Ngày nghiệp vụ địa phương:** dùng `ZoneId` cố định theo tenant/quy tắc nghiệp vụ; đặc biệt kiểm tra ranh giới ngày và những vùng có thay đổi giờ mùa hè.

Với bucket **theo giờ**, nên lưu chính xác định danh khung giờ, ví dụ timestamp UTC đã làm tròn xuống đầu giờ hoặc một số nguyên epoch-hour. Tránh dùng “giờ 01” trần trụi vì giờ địa phương có thể lặp hoặc không tồn tại khi đổi giờ mùa hè.

### Tạo khóa khi retry và ghi trùng

Nếu cùng một sự kiện được gửi lại, dùng cùng `device_id`, bucket, `occurred_at` và `event_id` giúp lần ghi đi tới **cùng một primary key** thay vì vô tình tạo hàng mới. Đây là một phần thiết kế idempotency ở mức khóa; vẫn phải kiểm tra ngữ nghĩa update/timestamp và các side effect liên quan.

Thay đổi định nghĩa bucket của dữ liệu đã ghi, chẳng hạn từ UTC sang múi giờ khác, làm **thay đổi partition key**. Phải có kế hoạch tương thích hoặc migration; không thể chỉ sửa hàm tính bucket rồi mong reader cũ tìm thấy dữ liệu.

## 6. Đọc khoảng thời gian qua nhiều bucket

Một truy vấn muốn lấy sự kiện từ **23:50 ngày 24/11 đến 00:10 ngày 25/11** sẽ đi qua hai partition ngày:

~~~text
[2026-11-24 23:50, 2026-11-25 00:00) -> bucket_day = 2026-11-24
[2026-11-25 00:00, 2026-11-25 00:10) -> bucket_day = 2026-11-25
~~~

Tầng ứng dụng cần xác định những bucket giao với khoảng `[from, to)`, rồi truy vấn từng partition bằng đủ thành phần partition key:

~~~sql
-- Chạy riêng cho từng bucket, với from/to phù hợp khoảng đang đọc.
SELECT occurred_at, event_id, event_type, payload_ref
FROM telemetry_ks.events_by_device_day
WHERE device_id = ?
  AND bucket_day = ?
  AND occurred_at >= ?
  AND occurred_at < ?
LIMIT 100;
~~~

Lược đồ thực thi:

~~~text
HTTP: /devices/A/events?from=...&to=...&limit=100
   |
   +--> xác định các ngày cần đọc theo quy tắc bucket
           |
           +--> ngày 25: query partition (A, 25)
           +--> ngày 24: query partition (A, 24)
                  |
                  +--> hợp nhất và sắp xếp theo occurred_at, event_id
                           |
                           +--> trả tối đa 100 sự kiện
~~~

Đối với bài toán “sự kiện mới nhất”, có thể đọc từ bucket mới đến bucket cũ rồi dừng khi đủ kết quả, nếu thứ tự bucket và giới hạn lọc cho phép. Nếu cần đọc song song nhiều bucket, phải **merge kết quả theo khóa sắp xếp**; thứ tự clustering là **cục bộ của từng partition**, không tự tạo thứ tự toàn cục.

**Tránh các lối tắt không phù hợp:**

- Truy vấn chỉ theo `occurred_at` và bỏ `device_id`/`bucket_day` không khớp partition key đã thiết kế.
- Dùng `ALLOW FILTERING` để “tìm tất cả ngày” thường biến đường đọc thành quét/lọc lớn và khó đoán độ trễ.
- Dùng `IN` cho nhiều partition key không thay thế một kế hoạch đọc/bounded fan-out; tính năng và hiệu năng cụ thể phụ thuộc mẫu truy vấn và phiên bản Cassandra.
- Tự động truy vấn mọi bucket trong vài năm để đáp ứng một thao tác UI tức thời là dấu hiệu truy vấn và mô hình dữ liệu chưa được căn chỉnh.

Khi cần thống kê toàn bộ thiết bị theo khoảng thời gian, đây là **truy vấn khác** với lịch sử của một thiết bị. Có thể cần bảng đọc riêng, hệ thống phân tích, hoặc index phù hợp với workload; không nên ép một bảng phục vụ mọi truy vấn.

## 7. Paging khi kết quả vượt qua ranh giới bucket

Cassandra hỗ trợ phân trang theo **paging state** ở driver/API phù hợp, trong khi mỗi bucket là một partition riêng. Khi API trả 100 sự kiện mỗi trang, cần phân biệt:

1. **Paging trong một partition:** driver có thể tiếp tục đọc bằng paging state tương ứng với truy vấn đó.
2. **Paging qua nhiều bucket:** ứng dụng phải biết đang đọc bucket nào, đã hoàn thành bucket nào và còn paging state nào đang dùng.
3. **Paging qua các partition/shard song song:** phải có cơ chế giữ trạng thái từng nguồn và merge theo thứ tự tổng thể.

Ví dụ response API có continuation token **do ứng dụng định nghĩa** (minh họa, không phải định dạng token của driver):

~~~json
{
  "items": [
    {"occurredAt": "2026-11-25T09:20:00Z", "eventId": "example-1"}
  ],
  "nextCursor": "<opaque-application-cursor>"
}
~~~

Cursor của ứng dụng có thể gói bucket hiện tại, continuation phù hợp và điều kiện lọc; phải được mã hóa/ký và ràng buộc với chính truy vấn, không nên để client sửa tùy ý. Cần quản lý lúc cursor hết hiệu lực và thay đổi schema/query.

**Không mặc định `PageRequest.of(50, 100)` tương đương bỏ qua tức thì 5.000 hàng** như kỳ vọng trong một số hệ SQL. CQL paging không tạo truy cập ngẫu nhiên giá rẻ theo offset. Dữ liệu được ghi/xóa trong lúc phân trang cũng có thể khiến các trang không đại diện cho một snapshot cố định; nếu nghiệp vụ cần kết quả bất biến, phải thiết kế snapshot/checkpoint riêng.

## 8. Time bucket không tự xử lý hot partition

Giả sử một thiết bị gửi 200.000 sự kiện trong 5 phút. Dù dùng bucket theo giờ hay ngày, **toàn bộ 5 phút vẫn thuộc một partition**, nên partition hiện tại có thể nóng về writes/s hoặc reads/s.

Khi đó cân nhắc bổ sung **shard** bên trong time bucket:

~~~sql
CREATE TABLE telemetry_ks.events_by_device_day_shard (
    device_id   uuid,
    bucket_day  date,
    shard       smallint,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    PRIMARY KEY ((device_id, bucket_day, shard), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Ví dụ phân 4 shard gần đều với 200.000 sự kiện trong cùng ngày:

~~~text
(A, 2026-11-25, 0) -> ~50.000 hàng
(A, 2026-11-25, 1) -> ~50.000 hàng
(A, 2026-11-25, 2) -> ~50.000 hàng
(A, 2026-11-25, 3) -> ~50.000 hàng
~~~

Nếu shard được chọn từ hash ổn định của `event_id`, writer phải dùng cùng quy tắc cho retry và reader phải biết cần đọc shard nào. Với truy vấn lịch sử cả ngày, reader có thể phải đọc **tất cả shard** rồi merge theo `occurred_at` và `event_id`. Đổi lại, kích thước và tải trên một partition có thể giảm khi phân phối tương đối đều.

Không có công thức “càng nhiều shard càng tốt”: tăng shard cũng làm tăng số partition/query, số paging state và chi phí merge. Hãy dựa vào **tải cực đại đã đo**, không tự đặt số shard chỉ vì có nhiều node. RF = 3 lưu ba replica của partition; nó không thay thế ba hoặc bốn shard độc lập.

## 9. TTL, dữ liệu đến muộn và compaction

Time bucketing **giới hạn mức tăng mỗi partition theo khoảng thời gian**; nó **không tự xóa** partition cũ. Nếu cần retention 30 ngày, ứng dụng phải có chính sách lưu giữ riêng, thường dùng TTL hoặc cơ chế quản lý dữ liệu phù hợp.

Ví dụ TTL mặc định 30 ngày cho các cột mới được ghi trong bảng (giá trị tính bằng giây):

~~~sql
ALTER TABLE telemetry_ks.events_by_device_day
WITH default_time_to_live = 2592000;
~~~

Đây là ví dụ chính sách TTL theo **thời điểm ghi**, không tự động có nghĩa “xóa đúng sau 30 ngày tính từ occurred_at”. Sự kiện phát sinh ngày 01 nhưng đến ngày 03 mới được ghi có thể hết hạn muộn hơn so với retention tính từ **ngày xảy ra sự kiện**. Nếu yêu cầu retention bám sát event time, cần thiết kế TTL còn lại hoặc cơ chế dọn dữ liệu thích hợp và xử lý các trường hợp sự kiện quá hạn.

**Sự kiện đến muộn:** nếu bucket xác định từ `occurred_at`, một sự kiện đến ngày 26 nhưng xảy ra ngày 24 sẽ được ghi vào partition ngày 24. Nó vẫn thuộc đúng lịch sử theo event time; nhưng dữ liệu của bucket cũ có thể tiếp tục thay đổi sau khi đã “kết thúc ngày”.

**Tombstone và compaction:** hết TTL hoặc xóa có thể sinh tombstone; dữ liệu vật lý trong SSTable không nhất thiết được thu hồi ngay khi TTL hết hạn. Độ trễ đọc và không gian đĩa phụ thuộc kiểu ghi, tombstone, compaction và trạng thái replica. Với workload time-series chủ yếu **append-only, TTL và ít ghi muộn**, có thể đánh giá **TimeWindowCompactionStrategy (TWCS)** như một lựa chọn; cần kiểm tra điều kiện áp dụng, phiên bản và hành vi thực tế. TWCS cũng không thay thế cách chọn partition key.

Nếu thiết bị thường xuyên cập nhật dữ liệu cũ hoặc sự kiện liên tục đến rất muộn, việc dùng compaction window cần được xem xét kỹ. Không coi “bucket đã kết thúc” là bảo đảm partition sẽ bất biến.

## 10. Mapping time bucket trong Spring Data Cassandra

Entity phải phản ánh đúng primary key đã khai báo ở CQL. Ví dụ rút gọn cho bảng `events_by_device_day`; các import, constructor, accessor và `equals/hashCode` được lược bỏ để tập trung vào annotation:

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 0, type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "bucket_day", ordinal = 1, type = PrimaryKeyType.PARTITIONED)
    private LocalDate bucketDay;

    @PrimaryKeyColumn(
        name = "occurred_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private UUID eventId;
}

@Table("events_by_device_day")
public class EventRow {

    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload_ref")
    private String payloadRef;
}
~~~

Điểm cốt lõi:

- Hai cột `PARTITIONED` tạo **composite partition key**. Nếu Java mapping quên `bucketDay` hoặc đánh nhầm thành `CLUSTERED`, nó không còn phản ánh đúng bảng.
- `occurredAt` và `eventId` là các clustering columns. `ordinal` và `ordering` phải phù hợp thứ tự trong schema CQL.
- Việc tính `bucketDay` phải diễn ra **trước ghi**, tại một lớp nghiệp vụ/mapper dùng chung, không suy đoán tùy tiện sau khi truy vấn.
- `CassandraRepository<EventRow, EventKey>` dùng khóa đầy đủ cho các thao tác theo hàng; để lấy lịch sử theo ngày, repository query hoặc `CassandraTemplate` cần cung cấp đủ partition key và giới hạn phù hợp.
- Với truy vấn nhiều ngày, tầng service cần ghép các truy vấn theo bucket. Framework không tự động biến một truy vấn range thời gian xuyên nhiều partition thành đường đọc tối ưu.

Ví dụ một query method trực tiếp với partition key đầy đủ:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("SELECT * FROM events_by_device_day " +
           "WHERE device_id = ?0 AND bucket_day = ?1 LIMIT 100")
    List<EventRow> latestInDay(UUID deviceId, LocalDate bucketDay);
}
~~~

Ví dụ giả định Spring Data đã được cấu hình truy cập đúng keyspace. Với bảng khác keyspace mặc định, cần khai báo keyspace đầy đủ trong CQL hoặc cấu hình mapping tương ứng. Cách phân trang và API repository/`CassandraTemplate` cụ thể cần khớp với phiên bản Spring Data và Java Driver của dự án.

## 11. Ví dụ quy trình lựa chọn bucket cho API lịch sử

Giả sử tính năng cần xem sự kiện của một thiết bị trong 7 ngày gần nhất, 100 sự kiện/trang; tải dự kiến lớn nhất là 120.000 sự kiện/ngày/thiết bị.

**Bước 1 — Chốt truy vấn:** lọc đúng `device_id`, thứ tự `occurred_at DESC, event_id DESC`, thời gian giới hạn 7 ngày. Nếu còn yêu cầu tìm toàn hệ thống theo `event_type`, coi đó là một access pattern riêng.

**Bước 2 — Đo khối lượng:** lấy số sự kiện/ngày và đỉnh theo giờ của thiết bị nhiều nhất; đo byte/hàng trên payload thực. Với 120.000 hàng/ngày và giả định 500 byte/hàng, một partition ngày có khoảng `60 MB` dữ liệu logic; chưa có overhead.

**Bước 3 — So sánh phương án:** bucket ngày tạo khoảng 7–8 partition cho 7 ngày, bucket giờ có thể tạo 168 partition. Nếu bucket ngày đáp ứng các kiểm tra size, throughput và latency, không cần chia nhỏ hơn chỉ để “an toàn”.

**Bước 4 — Định nghĩa khóa và lịch:** `(device_id, bucket_day)`, thống nhất UTC hoặc múi giờ nghiệp vụ. Chọn `occurred_at` làm clustering column và `event_id` làm tie-breaker.

**Bước 5 — Thiết kế fan-out có giới hạn:** service xác định những bucket giao với 7 ngày, đọc từ mới tới cũ, có tối đa số truy vấn/bucket phù hợp giới hạn sản phẩm. Hỗ trợ continuation token khi sang bucket khác.

**Bước 6 — Kiểm thử điều kiện biên:** sự kiện đúng 00:00, sự kiện đến muộn, retry, ngày không có dữ liệu, thời gian có đổi DST, bucket cực lớn, trang tiếp theo đúng ranh giới bucket và dữ liệu đang ghi song song.

**Bước 7 — Theo dõi sản xuất:** giám sát số hàng/partition, tải theo partition, độ trễ p95/p99, tombstone, SSTable và kích thước replica; điều chỉnh bucket hoặc shard có kế hoạch khi workload tăng.

### Các sai lầm thường gặp

| Sai lầm | Hệ quả hoặc cách sửa |
| --- | --- |
| Dùng `PRIMARY KEY (device_id, bucket_day, occurred_at)` và tưởng đã chia ngày | `bucket_day` thực tế là clustering column; cần `PRIMARY KEY ((device_id, bucket_day), occurred_at)` |
| Chọn bucket theo ngày nhưng đọc lịch sử “toàn bộ nhiều năm” mọi lần | Fan-out lớn; phải giới hạn thời gian, đổi access pattern hoặc thêm bảng/giải pháp truy vấn khác |
| Tính bucket theo giờ server ở nơi ghi và theo UTC ở nơi đọc | Có thể tìm sai partition; chuẩn hóa timestamp và múi giờ |
| Cho rằng bucket ngày luôn dưới một mức dung lượng cố định | Một ngày bùng nổ vẫn có thể rất lớn; đo đỉnh và cân nhắc bucket ngắn/shard |
| Cho rằng `LIMIT` hoặc paging làm partition bé lại | Chúng chỉ giới hạn hoặc chia lần nhận kết quả, không thay đổi số hàng đang được lưu |
| Cho rằng TTL xóa vật lý ngay tại ngày hết hạn | Việc thu hồi đĩa phụ thuộc tombstone và compaction |
| Tăng RF để giải quyết hot partition | RF tạo thêm replica, không chia partition key thành nhiều phần độc lập |

## 12. Tự kiểm tra

**Câu 1.** Với `PRIMARY KEY ((account_id, event_month), occurred_at, event_id)`, khóa nào xác định partition?

**Đáp án:** Cặp `(account_id, event_month)`. Hai cột sau là clustering columns. Tháng khác nhau của cùng tài khoản thuộc partition khác nhau.

**Câu 2.** Một thiết bị tạo 72.000 sự kiện/ngày, đều theo giờ, mỗi hàng 600 byte theo giả định. Một partition theo giờ chứa bao nhiêu hàng và dữ liệu?

**Đáp án:** `72.000 / 24 = 3.000` hàng và khoảng `1,8 MB` dữ liệu/partition giờ, chưa tính overhead.

**Câu 3.** Người dùng cần 50 sự kiện mới nhất từ 23:55 hôm trước tới 00:05 hôm sau, bucket ngày. Có thể đọc một partition không?

**Đáp án:** Không, khoảng này giao với hai bucket ngày. Cần truy vấn các partition tương ứng, sắp xếp/ghép kết quả và trả tối đa 50 hàng.

**Câu 4.** Sự kiện xảy ra ngày 20 nhưng đến ngày 22 mới nhận. Nếu bucket tính từ `occurred_at`, sự kiện phải vào partition nào?

**Đáp án:** Bucket ngày 20 theo múi giờ đã thống nhất. Writer và reader phải dùng cùng quy tắc tính bucket.

**Câu 5.** Chuyển từ bucket ngày sang bucket giờ có chắc chắn làm giảm hot partition do 100.000 sự kiện đến trong 2 phút không?

**Đáp án:** Không. Hai phút đó vẫn nằm trong một bucket giờ. Có thể cần chia thêm shard và đánh giá chi phí fan-out, hoặc giải pháp hấp thụ tải ở tầng ghi.

---

**Ghi nhớ:** time bucketing là đưa khoảng thời gian vào **partition key**, giúp giới hạn thời gian tích lũy dữ liệu của một partition. Chọn độ rộng bucket dựa trên **truy vấn thật, số hàng/byte lớn nhất, tốc độ ghi/đọc cực đại và retention**; đồng thời phải thiết kế việc tìm bucket, truy vấn nhiều partition, paging và xử lý sự kiện đến muộn. Trong Spring Data Cassandra, các annotation mapping và repository phải nhất quán với primary key CQL và quy tắc tính bucket của ứng dụng.
