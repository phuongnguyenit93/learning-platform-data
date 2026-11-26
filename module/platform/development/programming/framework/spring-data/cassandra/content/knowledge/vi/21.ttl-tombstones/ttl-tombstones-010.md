# Thiết kế lưu giữ dữ liệu theo cửa sổ thời gian

Trong **Apache Cassandra**, dữ liệu sự kiện, log, telemetry và lịch sử hoạt động thường có giá trị chủ yếu trong **một khoảng thời gian hữu hạn**: 7 ngày cho log kỹ thuật, 30 ngày cho sự kiện thiết bị, hoặc 90 ngày cho dữ liệu hỗ trợ vận hành. Ứng dụng muốn vừa đọc nhanh những sự kiện mới nhất, vừa tự động hết hạn dữ liệu cũ, vừa không để tombstone và compaction làm chậm cả cluster.

Thiết kế tốt phải kết hợp **ba cơ chế có trách nhiệm khác nhau**:

1. **Time bucketing**: đưa ngày/giờ hoặc một cửa sổ thời gian vào **partition key** để giới hạn kích thước partition và phạm vi đọc.
2. **TTL (time to live)**: cho các **giá trị được ghi** hết hạn sau số giây hoặc theo chính sách mặc định của bảng.
3. **TimeWindowCompactionStrategy (TWCS)**: tổ chức SSTable theo **cửa sổ thời gian ghi** nhằm thuận lợi hơn cho các workload dữ liệu tuần tự, có TTL và ít sửa dữ liệu cũ.

Ba cơ chế **không hoán đổi được**: TTL không tự tạo partition mới; chia bucket không tự xóa dữ liệu; TWCS không tự áp đặt thời hạn lưu giữ. Bài thuộc chương **TTL và tombstone** của module **SPRING_DATA_CASSANDRA**, bao gồm thiết kế khóa, CQL, entity mapping, `CassandraTemplate`, repository, truy vấn theo nhiều cửa sổ, dữ liệu đến muộn và kiểm soát vận hành trong hệ phân tán.

## 1. Trước tiên, đặc tả chính sách lưu giữ

Ví dụ nghiệp vụ: hệ thống lưu sự kiện cho từng thiết bị trong **30 ngày**, hiển thị 100 sự kiện gần nhất theo ngày, và đôi khi đọc một khoảng ba ngày để chẩn đoán.

Trước khi chọn schema, cần trả lời:

| Câu hỏi | Ví dụ quyết định | Tác động |
| --- | --- | --- |
| Giữ bao lâu? | 30 ngày | TTL và dung lượng dữ liệu sống |
| Tính từ mốc nào? | Lúc sự kiện xảy ra, hay lúc hệ thống tiếp nhận? | TTL động hoặc table default TTL |
| Phạm vi truy vấn? | Một tenant/thiết bị trong 1–3 ngày | Partition key và số bucket cần đọc |
| Tần suất ghi? | Trung bình 100 sự kiện/giây/thiết bị | Dung lượng partition, hot partition |
| Có cập nhật sự kiện cũ? | Hiếm, gần như append-only | Có phù hợp TWCS không |
| Sự kiện đến muộn bao lâu? | Thường dưới 2 giờ, đôi lúc nhiều ngày | TTL còn lại, SSTable chứa dữ liệu đến muộn |
| Xóa sớm ngoài TTL? | Có thể có yêu cầu xóa dữ liệu cá nhân | Tombstone và quy trình bảo đảm xóa |
| Cần khôi phục từ snapshot? | Backup 7 ngày | Dữ liệu vật lý có thể tồn tại sau khi hết TTL |

Phải phân biệt **retention logic** (không còn hiện diện trong kết quả đọc) và **physical reclamation** (không gian đĩa được thu hồi). TTL giúp dữ liệu hết hiệu lực về mặt đọc; SSTable, tombstone, compaction, repair và bản sao lưu quyết định phần dữ liệu còn nằm trên đĩa trong bao lâu.

## 2. Time bucket là một phần của partition key

Giả sử ta đặt một partition cho toàn bộ lịch sử thiết bị:

~~~sql
-- Ví dụ KHÔNG phù hợp cho luồng thiết bị tồn tại nhiều năm.
PRIMARY KEY ((tenant_id, device_id), event_time, event_id)
~~~

Partition này có thể tăng mãi khi thiết bị liên tục gửi dữ liệu. Paging chỉ đọc từng phần **không làm partition vật lý nhỏ lại**. Để giới hạn tăng trưởng, thêm ngày vào partition key:

~~~text
Partition 1: (tenant=A, device=42, bucket_day=2026-11-24)
Partition 2: (tenant=A, device=42, bucket_day=2026-11-25)
Partition 3: (tenant=A, device=42, bucket_day=2026-11-26)

Trong mỗi partition:
  event_time DESC, event_id DESC
~~~

Ngày `bucket_day` là **giá trị khóa** chứ không phải cột tùy ý. Cùng một thiết bị, dữ liệu ngày khác nhau nằm ở **partition khác nhau** và có thể được phân phối tới replica khác nhau.

Chọn bucket ngày là quyết định minh họa, không phải mặc định cho mọi tải. Nếu một thiết bị sinh nhiều dữ liệu trong một ngày, bucket theo **giờ** hoặc **ngày + shard** có thể hợp lý hơn; nếu thiết bị rất ít ghi, bucket ngày có thể tạo nhiều partition nhỏ và tăng fan-out khi đọc lịch sử dài.

## 3. Schema CQL phục vụ truy vấn theo ngày

Một bảng cụ thể:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_ks.events_by_device_day (
    tenant_id    uuid,
    device_id    text,
    bucket_day   date,
    event_time   timestamp,
    event_id     uuid,
    event_type   text,
    payload      text,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id DESC
);
~~~

Ở đây:

- **Composite partition key** gồm `tenant_id`, `device_id`, `bucket_day`; cần biết đủ cả ba để truy vấn chính xác một partition.
- **Clustering columns** là `event_time`, `event_id`; thời gian giảm dần bên trong partition, còn `event_id` phân biệt các sự kiện cùng thời điểm.
- `payload` được minh họa bằng `text`; khi payload rất lớn, nên cân nhắc projection hoặc lưu dữ liệu nặng trong đường truy cập khác.
- `dc1` và replication factor 3 chỉ là ví dụ; áp dụng theo topology và số node thực tế.

Truy vấn phù hợp:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_ks.events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
LIMIT 100;
~~~

Truy vấn range trong cùng bucket:

~~~sql
SELECT event_time, event_id, event_type
FROM telemetry_ks.events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
~~~

Điều kiện `>= from AND < to` là **khoảng nửa mở**: giảm rủi ro đếm trùng tại ranh giới hai request/khoảng. Không dùng `ALLOW FILTERING` để tránh đưa `bucket_day` vào `WHERE`.

## 4. Cửa sổ ngày phải có cùng quy tắc ở writer và reader

Với sự kiện mang thời điểm UTC, tính bucket từ `Instant`:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

Instant eventTime =
    Instant.parse("2026-11-25T00:15:00Z");

LocalDate bucketDay = eventTime
    .atZone(ZoneOffset.UTC)
    .toLocalDate();
// 2026-11-25
~~~

**Không** để writer dùng UTC nhưng reader dùng mặc định timezone của JVM. Một sự kiện gần nửa đêm có thể bị tìm trong **partition khác** dù dữ liệu chưa hề hết TTL.

Nếu nghiệp vụ định nghĩa “ngày” theo múi giờ người dùng, phải đặc tả timezone rõ ràng và dùng cùng quy tắc khi ghi, đọc, tính retention. Những ngày có thay đổi DST không nhất thiết dài đúng 86.400 giây; đừng đánh đồng **ngày lịch** với một khoảng `Duration.ofDays(1)` trong mọi timezone.

### Chọn kích thước bucket bằng số liệu

Một ước lượng ban đầu:

\[
\text{Số hàng mỗi partition}
\approx
\text{Số sự kiện/giây của thiết bị}
\times
\text{Số giây của bucket}
\]

Ví dụ thiết bị ghi trung bình **10 sự kiện/giây** trong một ngày UTC:

\[
10 \times 86{,}400 = 864{,}000\ \text{hàng/ngày}
\]

Đây có thể là partition lớn tùy kích thước hàng và tốc độ truy cập; không được chọn bucket ngày chỉ vì phép tính dễ. Nên đo kích thước **byte**, số row/cell, tốc độ ghi đỉnh, read latency và tombstone; nếu cần chia theo giờ hoặc thêm shard, số bucket cần đọc sẽ tăng và phải được xử lý có giới hạn.

**Không có một ngưỡng kích thước partition duy nhất đúng cho mọi cluster**. Tránh dùng con số tùy ý để thay thế profiling/workload thực.

## 5. Đọc một khoảng thời gian trải qua nhiều bucket

Giả sử API yêu cầu khoảng `[2026-11-23T20:00Z, 2026-11-25T03:00Z)`. Truy vấn một partition ngày **không thể** tự trả dữ liệu của ba ngày:

~~~text
23/11: đọc 20:00 -> hết ngày
24/11: đọc toàn khoảng ngày
25/11: đọc đầu ngày -> 03:00
~~~

Service có thể:

1. Validate `from < to`, tenant, device và giới hạn tổng số ngày cho phép.
2. Xác định các ngày UTC giao với khoảng.
3. Query từng partition với đủ `tenant_id, device_id, bucket_day` và khoảng `event_time`.
4. Giới hạn concurrency, tổng số hàng và thời gian xử lý.
5. Gộp kết quả theo `event_time DESC, event_id DESC` nếu API cần thứ tự toàn cục.
6. Quản lý paging state **riêng cho mỗi partition**, hoặc một cursor cấp ứng dụng có thể tiếp tục từ ngày hiện tại.

Ví dụ Java biểu diễn tập bucket (giới hạn số ngày phải được áp dụng trước khi lặp):

~~~java
LocalDate day = from
    .atZone(ZoneOffset.UTC).toLocalDate();
List<LocalDate> buckets = new ArrayList<>();

while (day.atStartOfDay(ZoneOffset.UTC).toInstant()
          .isBefore(toExclusive)) {
    buckets.add(day);
    day = day.plusDays(1);
}
~~~

Với `from` và `toExclusive` là `Instant` hợp lệ, vòng lặp trả về các bucket liên quan. **Không để client yêu cầu khoảng hàng chục năm rồi fan-out không giới hạn.** Pagination không thay thế việc giới hạn phạm vi dữ liệu.

## 6. TTL của Cassandra có ý nghĩa ở cấp giá trị/cell

TTL được tính bằng **giây**. Ghi một sự kiện với TTL 30 ngày:

~~~sql
INSERT INTO telemetry_ks.events_by_device_day (
    tenant_id, device_id, bucket_day,
    event_time, event_id, event_type, payload
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TTL 2592000;
~~~

Số `2592000` là `30 × 24 × 60 × 60` giây. Với ví dụ này, dữ liệu được ghi với một TTL tương ứng khoảng 30 ngày từ khi ghi được áp dụng. Nó **không** tự hiểu thời điểm sự kiện trong cột `event_time`.

TTL thuộc về **giá trị được ghi**, không phải một thao tác “DROP PARTITION vào đúng ngày”:

- Những cell khác nhau trong cùng hàng có thể được ghi với TTL khác nhau.
- Một `UPDATE` chỉ ghi `payload` không mặc nhiên thay TTL của `event_type`.
- Việc ghi lại một cell có thể làm thay đổi TTL/ thời điểm hết hạn của giá trị theo ngữ nghĩa mutation và write timestamp.
- Hết TTL không có nghĩa không gian vật lý của SSTable được giải phóng ngay.
- Partition key không được hiểu như một “đối tượng Java có TTL” riêng biệt; Cassandra quản lý sự tồn tại của hàng/cell theo dữ liệu và metadata lưu trữ.

Để xem thời gian sống còn lại của một cột scalar:

~~~sql
SELECT event_time, event_id,
       TTL(payload), WRITETIME(payload)
FROM telemetry_ks.events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
  AND event_time = ?
  AND event_id = ?;
~~~

`TTL(payload)` cho số giây còn lại nếu cột có TTL; `WRITETIME(payload)` cho write timestamp ở đơn vị **micro giây**, khác với kiểu CQL `timestamp` của `event_time`.

## 7. Table default TTL hay TTL cho từng statement?

Cassandra có table option `default_time_to_live`. Ví dụ đặt retention mặc định 30 ngày:

~~~sql
ALTER TABLE telemetry_ks.events_by_device_day
WITH default_time_to_live = 2592000;
~~~

Hai cách áp dụng chính:

| Chính sách | Cách thể hiện | Phù hợp khi |
| --- | --- | --- |
| **30 ngày từ lúc ghi** | `default_time_to_live = 2592000` | Luồng ingest ổn định, mọi giá trị nên hết hạn theo thời gian ghi |
| **30 ngày từ lúc xảy ra** | Tính TTL còn lại và dùng `USING TTL ?` | Sự kiện đến muộn, yêu cầu retention theo event time |
| Một số bản ghi ngoại lệ | Statement-specific TTL theo quy tắc kiểm soát | Có loại dữ liệu giữ thời gian khác |
| Dữ liệu vĩnh viễn | Bảng hoặc policy không áp TTL tương ứng | Không trộn tùy tiện với dữ liệu ngắn hạn của TWCS |

Table default TTL giúp giảm rủi ro quên TTL ở một đường ghi, nhưng **không tự sửa các giá trị đã ghi trước đó** khi thay đổi cấu hình. Cần kiểm tra override và hành vi TTL bằng 0 theo **phiên bản Cassandra** nếu muốn viết dữ liệu không hết hạn vào bảng có default TTL.

**Đừng dùng table default TTL = 0 và giả định dữ liệu tự hết hạn.** Giá trị mặc định bằng 0 thường mang ý nghĩa không có TTL mặc định. Đồng thời, đừng đổi TTL bảng trên production khi chưa đánh giá các writer đang dùng default khác, dữ liệu cũ và vòng đời backup.

## 8. Chọn mốc retention: ingest time hay event time?

Đây là quyết định nghiệp vụ quan trọng hơn nhiều so với tên method của repository.

**Ingest-time retention**: dữ liệu tồn tại 30 ngày kể từ **lúc ghi vào Cassandra**.

~~~text
Event xảy ra:      2026-11-20 10:00 UTC
Được ingest:       2026-11-25 10:00 UTC
TTL lúc ghi:       30 ngày
Hết hạn logic:     xấp xỉ 2026-12-25 10:00 UTC
~~~

**Event-time retention**: dữ liệu tồn tại đến **30 ngày kể từ khi sự kiện xảy ra**, nên TTL phụ thuộc vào độ trễ ingest.

~~~text
Event xảy ra:      2026-11-20 10:00 UTC
Được ingest:       2026-11-25 10:00 UTC
Deadline:          2026-12-20 10:00 UTC
TTL cần cấp:       khoảng 25 ngày còn lại
~~~

Hai chính sách cho **kết quả khác nhau** khi backfill, replay hoặc nhận dữ liệu từ thiết bị offline. Nếu một event đến khi đã quá deadline, hệ thống phải có quy tắc **không ghi dữ liệu đã hết hạn**, hoặc đưa nó vào một đường lưu giữ khác theo yêu cầu nghiệp vụ.

**“30 ngày”** cũng cần được đặc tả: 30 × 24 giờ tuyệt đối kể từ `Instant`, hay tới hết ngày lịch thứ 30 trong timezone nghiệp vụ? Hai cách có thể khác nhau tại ranh giới ngày và DST.

## 9. Tính TTL còn lại từ deadline ở tầng Java

Ví dụ Java 17 dùng chính sách **30 × 24 giờ kể từ event time** và làm tròn TTL lên giây để không tạo TTL bằng 0 khi còn ít hơn một giây:

~~~java
import java.time.Duration;
import java.time.Instant;

public final class EventRetention {
    private static final Duration RETENTION = Duration.ofDays(30);
    private static final int MAX_ALLOWED_TTL_SECONDS =
            30 * 24 * 60 * 60;

    private EventRetention() {}

    public static int remainingTtl(
            Instant eventTime, Instant now) {

        Instant deadline = eventTime.plus(RETENTION);
        Duration remaining = Duration.between(now, deadline);
        if (remaining.isZero() || remaining.isNegative()) {
            throw new IllegalArgumentException(
                "Sự kiện đã quá hạn retention");
        }

        long seconds = remaining.getSeconds();
        if (remaining.getNano() > 0) {
            seconds = Math.addExact(seconds, 1L);
        }
        if (seconds < 1 || seconds > MAX_ALLOWED_TTL_SECONDS) {
            throw new IllegalArgumentException(
                "TTL ngoài chính sách cho phép");
        }
        return Math.toIntExact(seconds);
    }
}
~~~

Điểm cần nhớ:

- Dùng đồng hồ/UTC thống nhất để tính `now` và `eventTime`.
- Validate event time không quá xa tương lai, payload không vô lý và độ trễ ingest không vượt quy tắc.
- TTL là **số nguyên giây**; chính sách làm tròn có thể làm deadline lệch dưới một giây.
- Giới hạn tối đa còn phụ thuộc phiên bản Cassandra và cấu hình; ví dụ Java trên chỉ giới hạn theo **chính sách 30 ngày của ứng dụng**.
- Không tự động thêm lại 30 ngày nguyên vẹn cho event cũ chỉ vì lần replay xảy ra muộn.

Đây là tính toán cho retention theo event time. Nếu retention bắt đầu từ ingest time, một TTL cố định theo table default thường đơn giản hơn.

## 10. Viết TTL động bằng prepared statement

Java Driver 4.x là đường đi rõ ràng khi cần bind giá trị TTL cho một statement. Với `CqlSession` do Spring Boot quản lý:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class EventWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare("""
            INSERT INTO telemetry_ks.events_by_device_day (
              tenant_id, device_id, bucket_day, event_time,
              event_id, event_type, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            USING TTL ?
            """);
    }

    public void write(
            UUID tenantId, String deviceId,
            Instant eventTime, UUID eventId,
            String eventType, String payload,
            Instant now) {

        LocalDate day = eventTime
            .atZone(ZoneOffset.UTC).toLocalDate();
        int ttlSeconds = EventRetention.remainingTtl(eventTime, now);

        BoundStatement statement = insert.bind(
            tenantId, deviceId, day, eventTime,
            eventId, eventType, payload, ttlSeconds
        );
        session.execute(statement);
    }
}
~~~

Ví dụ trên:

1. Giữ **cùng tenant, device, eventTime, eventId** cho các retry của cùng một sự kiện.
2. Tính bucket từ **event time**, không từ `Instant.now()`.
3. Tính TTL từ deadline chính sách và **thời điểm ingest**.
4. Bind tham số, không lắp TTL hay giá trị người dùng trực tiếp vào chuỗi CQL.
5. Chưa gồm retry policy/metrics/kiểm tra quyền/authorization: cần bổ sung ở ứng dụng thực.

Nếu muốn dùng **Spring Data Cassandra entity mapping**, có thể dùng `CassandraRepository` hoặc `CassandraTemplate` cho thao tác thường. Nhưng khi TTL theo từng event, phải bảo đảm đường ghi đó thật sự truyền TTL/WriteOptions theo API phiên bản dự án; không mặc định `repository.save(entity)` sẽ tự đọc retention policy trong Java.

## 11. Entity mapping cho bảng chia bucket

Ví dụ cấu trúc khóa trong Spring Data Cassandra:

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {
    @PrimaryKeyColumn(
        name = "tenant_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "device_id", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

    @PrimaryKeyColumn(
        name = "bucket_day", ordinal = 2,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate bucketDay;

    @PrimaryKeyColumn(
        name = "event_time", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant eventTime;

    @PrimaryKeyColumn(
        name = "event_id", ordinal = 4,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor/accessor/equals/hashCode theo mapping thực tế.
}

@Table("events_by_device_day")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("payload")
    private String payload;
}
~~~

Mã lược bỏ import/constructor và phải được tách class vào file Java thích hợp trong dự án thật. Tên cột và thứ tự primary key phải khớp CQL; `event_time` là clustering column, **không phải write timestamp `USING TIMESTAMP`**. Một entity có đầy đủ key không giúp API đọc 30 ngày bằng một partition: reader vẫn cần duyệt bucket.

Một repository:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT * FROM events_by_device_day
        WHERE tenant_id = ?0
          AND device_id = ?1
          AND bucket_day = ?2
        LIMIT 100
        """)
    List<EventRow> recentForDay(
        UUID tenantId, String deviceId, LocalDate day);
}
~~~

Mặc dù code gọn, câu `SELECT *` có thể làm tăng chi phí truyền nếu `payload` lớn; dùng projection hoặc chọn những cột cần thiết cho trang danh sách. Với partition lớn, `List` và `LIMIT` chỉ là giải pháp giới hạn hiển thị, không thay đổi kích thước partition vật lý.

## 12. TWCS giải quyết vấn đề gì?

Cassandra lưu dữ liệu bất biến trên **SSTable**, và compaction kết hợp các SSTable theo chiến lược bảng. **TimeWindowCompactionStrategy (TWCS)** được thiết kế cho những luồng ghi có tính tuần tự theo thời gian, ít cập nhật dữ liệu cũ và thường dùng TTL.

Ví dụ bật TWCS với cửa sổ compaction theo ngày:

~~~sql
ALTER TABLE telemetry_ks.events_by_device_day
WITH compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
~~~

Ở bảng có retention theo **ingest time**, có thể kết hợp:

~~~sql
ALTER TABLE telemetry_ks.events_by_device_day
WITH default_time_to_live = 2592000
 AND compaction = {
    'class': 'TimeWindowCompactionStrategy',
    'compaction_window_unit': 'DAYS',
    'compaction_window_size': '1'
};
~~~

Đây là cấu hình **minh họa**, không phải lời khuyên thay đổi bảng production ngay. Phải xem phiên bản Cassandra, retention, tốc độ flush, số SSTable và profile công việc trước khi chọn kích thước cửa sổ.

### Time bucket không phải TWCS window

| Khái niệm | Dựa trên | Ý nghĩa |
| --- | --- | --- |
| `bucket_day` trong partition key | **event time** đã quy ước | Nhóm hàng để định tuyến/đọc theo ngày |
| TTL 30 ngày | Thời điểm giá trị được ghi và TTL được áp dụng | Khi giá trị hết hiệu lực logic |
| TWCS window 1 ngày | Mốc thời gian của **dữ liệu ghi/SSTable theo write timestamp** | Gom SSTable để compaction và có thể loại bỏ khi hết hạn |

Các “cửa sổ” này **không tự đồng bộ**. Event xảy ra ngày 10 nhưng đến Cassandra ngày 20 vẫn thuộc partition của ngày 10, trong khi SSTable có thể thuộc cửa sổ ghi ngày 20. TWCS không đọc `bucket_day` để chọn window.

## 13. Vì sao TWCS có thể giúp thu hồi dữ liệu hết hạn?

Với dữ liệu gần như append-only, TTL đồng nhất và write timestamps theo dòng thời gian, SSTable trong một cửa sổ TWCS có xu hướng chứa những giá trị có tuổi tương tự nhau.

~~~text
TWCS, ví dụ dữ liệu được ghi tuần tự:

SSTable window ngày 01  ----\
SSTable window ngày 02   ----+--> sau khi toàn bộ nội dung hết hạn
SSTable window ngày 03  ----/    và thỏa điều kiện an toàn,
                                compaction có thể bỏ SSTable cũ
SSTable window ngày 04  ---------> vẫn chứa dữ liệu sống
~~~

Điểm có ích là có thể **loại bỏ cả SSTable** sau khi toàn bộ dữ liệu của nó đủ điều kiện hết hạn, thay vì phải trộn/đọc lại từng giá trị với SSTable mới trong nhiều vòng compaction.

Tuy nhiên:

- TWCS **không tự thực hiện DELETE** vào ngày bucket cũ.
- Một SSTable chứa dù chỉ một phần dữ liệu **chưa hết hạn** có thể chưa được loại bỏ nguyên khối.
- Dữ liệu có TTL khác nhau, cập nhật cột cũ, ghi đến muộn hoặc viết write timestamp bất thường có thể làm lẫn nhiều vòng đời trong cùng SSTable.
- Tombstone và điều kiện chống “zombie” vẫn quan trọng; việc đủ điều kiện loại bỏ SSTable phụ thuộc cơ chế compaction/phiên bản, không chỉ vào ngày lịch.
- Xóa SSTable khỏi dữ liệu sống không tự xóa các snapshot/backups đang giữ file tương ứng.

Không kích hoạt các tùy chọn “aggressive expiration” không an toàn chỉ để giảm dung lượng nhanh hơn nếu chưa hiểu ràng buộc chống hồi sinh dữ liệu và topology replica.

## 14. Dữ liệu đến muộn làm thay đổi bài toán retention

Sự kiện IoT có thể bị buffer tại thiết bị rồi gửi lên sau vài ngày:

~~~text
Ngày xảy ra event:          2026-11-01
Ngày Cassandra nhận event:  2026-11-20
Chính sách retention:       30 ngày từ event time
Deadline:                   2026-12-01
TTL còn lại lúc nhận:       khoảng 11 ngày
~~~

Nếu áp dụng table default TTL 30 ngày từ lúc ghi, dữ liệu trên có thể còn sống đến **20/12**, không khớp deadline **01/12**. Cần chọn rõ ràng chính sách, sau đó áp dụng TTL động hoặc xử lý dữ liệu quá hạn ở ingestion pipeline.

Với TWCS:

- Partition được xác định từ `bucket_day=2026-11-01`.
- SSTable mới được ghi trong cửa sổ gần 20/11 nếu sử dụng write timestamp hiện hành.
- TTL còn lại ngắn hơn một event vừa xảy ra ngày 20/11, nên SSTable có thể chứa dữ liệu với **thời điểm hết hạn khác nhau**.

Do đó, **backfill dữ liệu cũ và TWCS cần kế hoạch riêng**. Có thể dùng pipeline/bảng tạm phù hợp, batch có giới hạn hoặc một chiến lược compaction khác nếu workload thường xuyên sửa dữ liệu lịch sử. Không mặc định TWCS là lựa chọn tối ưu cho dữ liệu cập nhật ngẫu nhiên theo thời gian.

### Cẩn thận với USING TIMESTAMP

Write timestamp dùng cho phân giải xung đột cell và có thể ảnh hưởng cách TWCS nhóm dữ liệu vào cửa sổ. **Đừng tự gán `USING TIMESTAMP` bằng event time cũ** chỉ vì muốn SSTable đi vào window lịch sử: điều đó có thể làm mutation thua những ghi mới hơn và tạo ra hành vi không mong muốn.

Event time, ingest time, write timestamp và retention deadline là **bốn giá trị khác nhau**; chúng chỉ nên trùng nhau nếu nghiệp vụ thật sự yêu cầu và đã được kiểm thử.

## 15. Tombstone hình thành thế nào khi dữ liệu hết TTL?

Khi TTL hết hạn, Cassandra coi giá trị đã ghi như **giá trị bị xóa theo ngữ nghĩa lưu trữ**, liên quan tới tombstone. Cassandra cần giữ thông tin xóa đủ lâu để replica chậm hoặc từng offline không đưa dữ liệu cũ quay lại.

~~~text
T0: INSERT payload với TTL 30 ngày
T1: Dữ liệu còn sống -> SELECT thấy payload
T2: TTL hết hạn -> SELECT thông thường không còn thấy giá trị sống
T3: Tombstone/dữ liệu hết hạn còn trong SSTable
T4: Khi thỏa điều kiện an toàn và compaction phù hợp,
    SSTable/giá trị hết hạn có thể được loại bỏ vật lý
~~~

**Không nhầm:**

- TTL hết hạn **không** có nghĩa `DELETE` CQL đã được gửi vào đúng giờ đó.
- Logically expired **không** bằng đã xóa khỏi SSTable, backup, snapshot hoặc mọi bản sao.
- Những tombstone xuất hiện trong đường đọc có thể gây chi phí CPU/I/O và ảnh hưởng latency.
- Một hàng có nhiều cột và nhiều thời điểm cập nhật có thể mang **những trạng thái hết hạn khác nhau**.

Các truy vấn quét một partition quá rộng có nhiều dữ liệu đã hết hạn có thể tốn kém dù số hàng trả về ít. Vì vậy **TTL không cứu một data model đọc sai partition hoặc partition quá lớn**.

## 16. gc_grace_seconds, repair và nguy cơ zombie

Table option `gc_grace_seconds` liên quan đến thời gian giữ thông tin xóa trong một số điều kiện trước khi an toàn loại bỏ qua compaction. Ví dụ xem cấu hình:

~~~sql
SELECT table_name, default_time_to_live,
       gc_grace_seconds, compaction
FROM system_schema.tables
WHERE keyspace_name = 'telemetry_ks'
  AND table_name = 'events_by_device_day';
~~~

**Đừng xem `gc_grace_seconds` như một TTL thứ hai**, và cũng đừng giảm nó xuống 0 để “xóa nhanh hơn” mà không hiểu yêu cầu đồng bộ replica.

Tình huống nguy hiểm có thể xảy ra:

~~~text
Replica A: nhận DELETE/tombstone
Replica B: offline, giữ giá trị cũ
Replica A: tombstone bị loại bỏ quá sớm
Replica B: trở lại với dữ liệu cũ
=> rủi ro dữ liệu đã xóa xuất hiện trở lại ("zombie")
~~~

Vận hành đúng cần xét **khoảng thời gian replica có thể offline**, chiến lược repair/anti-entropy, consistency, dữ liệu TTL và phiên bản Cassandra. Một số cấu hình/phiên bản có tối ưu xử lý tombstone riêng, nhưng điều đó không làm thay đổi nghĩa vụ đánh giá replication/repair.

**Không có công thức “đặt gc_grace = retention / 2” áp dụng chung**. Đặt giá trị thấp chỉ khi đội vận hành nắm được các điều kiện an toàn và có quy trình bảo đảm replica được sửa chữa đủ thường xuyên.

## 17. Định nghĩa cửa sổ compaction dựa trên workload

Nếu TTL khoảng 30 ngày và dữ liệu liên tục được ghi, có thể **bắt đầu đánh giá** TWCS window một ngày, vì nó tạo ra số cửa sổ ở mức có thể quan sát. Nhưng kích thước tối ưu tùy số lượng SSTable, flush cadence, tốc độ ghi, memory, đợt backfill và cách dữ liệu hết hạn.

| Thuộc tính | Cửa sổ rất ngắn | Cửa sổ rất dài |
| --- | --- | --- |
| Số window trong retention | Nhiều | Ít |
| Số nhóm SSTable cần quản lý | Có thể cao | Có thể thấp |
| Mức trộn dữ liệu có tuổi khác nhau | Có thể ít hơn | Có thể lớn hơn |
| Khả năng loại bỏ cả SSTable | Có thể hạt mịn hơn | Có thể phải đợi phần dữ liệu trẻ nhất trong SSTable |
| Độ phù hợp | Phải đo | Phải đo |

Hướng kiểm tra:

1. Có thực sự **append-mostly** hay thường cập nhật/xóa sự kiện cũ?
2. Các cell có TTL tương tự nhau hay trộn nhiều chính sách retention?
3. Dữ liệu đến muộn và replay chiếm bao nhiêu phần trăm?
4. Số lượng SSTable, read amplification và compaction pending ra sao?
5. Dữ liệu cần giữ bao lâu và việc thu hồi đĩa có bị snapshot/backups giữ lại không?

**TWCS tối ưu theo write timestamp/SSTable, không theo khóa bucket ngày.** Nếu workload ghi quá nhiều dữ liệu cũ, dùng timestamp không tuần tự hoặc cập nhật qua nhiều cửa sổ, cần đánh giá chiến lược khác thay vì cố giữ TWCS vì tên “time window”.

## 18. Định lượng kích thước partition và tổng dung lượng

Một mô hình ước lượng đơn giản:

\[
\text{Dữ liệu sống (logic)}
\approx
\text{Tốc độ ghi byte/giây} \times \text{TTL giây}
\]

Với dòng ghi ví dụ 1 MiB/giây và TTL 30 ngày, lượng dữ liệu sống ở mức **hàng terabyte trước replication và overhead**. Dung lượng vật lý còn có RF, index/metadata, memtable/SSTable, compaction headroom, tombstone, repair và backup/snapshot.

Để sizing một partition:

\[
\text{Byte/partition}
\approx
\text{Events/s của thiết bị}
\times
\text{Giây/bucket}
\times
\text{Byte/event trung bình}
\]

Ví dụ thiết bị ghi 20 event/giây, mỗi event sau mã hóa khoảng 500 byte, bucket ngày:

~~~text
20 × 86.400 × 500 ≈ 864.000.000 byte/partition
~~~

Đây là partition rất lớn đối với nhiều workload; nên cân nhắc bucket giờ hoặc shard thay vì chỉ trông chờ TTL. Cần đo **đỉnh tải** và phân bố, không chỉ trung bình: vài thiết bị nóng có thể ảnh hưởng nhiều replica dù phần lớn thiết bị bình thường.

Lưu ý `RF=3` không phải số ba nhân vào **một partition trong một node**; nó là số bản sao của partition trên các node mục tiêu. Khi tính dung lượng toàn cluster, phải dự trù overhead/phân bố và capacity headroom tương ứng.

## 19. Khi nào xóa theo ngày, khi nào để TTL?

Có hai cách lưu giữ hay gặp:

**A. TTL per-cell / table default:** đơn giản để dữ liệu tự hết hạn logic và phù hợp luồng append-mostly. Tuy nhiên việc thu hồi vật lý không có thời điểm chính xác, có tombstone và có thể cần compaction/repair thích hợp.

**B. Tách dữ liệu theo đơn vị quản trị có thể loại bỏ:** ví dụ tách bảng hoặc keyspace theo một số giai đoạn khi yêu cầu xóa vật lý khối lượng lớn có kế hoạch. Phương án này tăng độ phức tạp schema, routing, triển khai, backup và truy vấn nhiều giai đoạn; không nên tạo một bảng mới mỗi ngày theo thói quen.

Trong Cassandra, **bucket ngày trong partition key không có nghĩa có thể `DROP PARTITION` trực tiếp như một bảng**. Một câu `DELETE` theo partition key có thể tạo **partition tombstone** và yêu cầu compaction; không phải thao tác xóa tức thì toàn bộ SSTable tương ứng.

Không thay TTL bằng việc chạy job `DELETE` từng hàng cũ ở tốc độ cao nếu không đánh giá tombstone và chi phí coordinator/replica. Với workload phần lớn append-only, TTL và chiến lược compaction phù hợp thường dễ kiểm soát hơn.

## 20. Dữ liệu đã hết hạn có còn trong snapshot, backup không?

Có thể. Cơ chế TTL/tombstone của Cassandra quản lý dữ liệu trong vòng đời lưu trữ và compaction, nhưng **backup, snapshot và bản sao ngoài cluster** có chính sách tồn tại riêng.

Nếu dữ liệu nhạy cảm phải được xóa sau một thời hạn:

- Đặc tả thời điểm **không còn được đọc qua API**, thời điểm **dọn dữ liệu vật lý** và thời hạn **backup/snapshot** riêng.
- Kiểm tra chính sách snapshot trước/sau compaction, thời gian lưu backup và quy trình phục hồi.
- Tránh tái nạp snapshot cũ làm dữ liệu hết hạn xuất hiện trở lại ngoài kỳ vọng; cần áp dụng quy tắc retention khi restore/backfill.
- Với yêu cầu pháp lý/xóa cá nhân, TTL đơn thuần có thể **không đáp ứng** mọi ràng buộc; phối hợp chính sách mã hóa, backup lifecycle và quy trình kiểm chứng xóa.

Không hứa “dữ liệu được xóa vĩnh viễn ngay tại giây TTL=0” nếu chưa có cơ chế chứng minh trên toàn chuỗi lưu trữ.

## 21. Vận hành: các chỉ số cần theo dõi

| Nhóm chỉ số | Mục tiêu quan sát |
| --- | --- |
| Dung lượng partition (byte/row) | Phát hiện bucket ngày/giờ quá lớn và thiết bị nóng |
| Read latency p95/p99 | Biết khi nào tombstone/partition lớn làm chậm truy vấn |
| Tombstone scanned / tombstone warnings | Phát hiện truy vấn phải quét nhiều giá trị hết hạn |
| Số SSTable và pending compactions | Đánh giá TWCS và áp lực dọn dữ liệu |
| Disk usage và compaction headroom | Tránh hết đĩa trước khi SSTable hết hạn được dọn |
| Tỷ lệ event đến muộn | Biết mức trộn dữ liệu qua window và hiệu quả TTL động |
| TTL remaining / retention audit | Xác nhận chính sách hết hạn logic |
| Replica health, repair status | Giảm rủi ro dữ liệu xóa xuất hiện trở lại |
| Backup/snapshot retention | Kiểm soát dữ liệu tồn tại ngoài vòng đời đọc thường |

Không đặt cảnh báo tombstone chỉ từ một số đếm cố định mà thiếu thông tin về query shape, version cluster, tỷ lệ lỗi và độ trễ. Cần kết hợp metrics driver, truy vấn mẫu và công cụ vận hành Cassandra.

### Checklist trước production

- [ ] Đã chọn retention theo **ingest time hay event time** và định nghĩa “ngày”/timezone.
- [ ] Bucket size được tính từ lượng dữ liệu đỉnh và kích thước hàng; partition không tăng mãi.
- [ ] Query có đủ partition key và có giới hạn trang/khoảng thời gian.
- [ ] Cấu hình table default TTL hoặc statement TTL nhất quán giữa mọi writer.
- [ ] Dữ liệu late arrival và replay có quy tắc deadline, không tự gia hạn vô ý.
- [ ] Chỉ dùng TWCS nếu write pattern/TTL phù hợp; đã kiểm tra write timestamps.
- [ ] Đã đánh giá tombstone, gc_grace_seconds, repair và điều kiện compaction.
- [ ] Có capacity headroom cho replication/compaction/backup.
- [ ] Có test retention logic và chính sách xóa snapshot/backup nếu dữ liệu nhạy cảm.
- [ ] Không dựa vào TTL để sửa truy vấn thiếu khóa hoặc làm nhỏ partition quá lớn.

## 22. Kiểm thử end-to-end trên Cassandra

Làm trên môi trường test có schema, driver và cấu hình tương đồng môi trường đích:

1. **Schema:** tạo bảng, kiểm tra partition key và `CLUSTERING ORDER BY`; xác định RF của keyspace.
2. **Bucket UTC:** ghi các event ở 23:59:59Z và 00:00:01Z ngày kế tiếp; xác minh chúng vào đúng hai partition.
3. **TTL:** dùng TTL nhỏ cho dữ liệu test, ví dụ 120 giây; kiểm tra `TTL(payload)` giảm dần.
4. **Hết hạn:** sau thời hạn, query thường không còn trả giá trị sống; không dùng disk usage làm tiêu chí duy nhất.
5. **Per-cell:** cập nhật riêng `payload`; kiểm tra `TTL(payload)` và `TTL(event_type)` có thể khác nhau.
6. **Late arrival:** gửi event từ nhiều ngày trước; xác minh TTL còn lại theo event time, không gia hạn nguyên 30 ngày.
7. **Expired event:** gửi event quá hạn; ingest pipeline từ chối hoặc xử lý theo chính sách, không ghi TTL âm/0 tùy tiện.
8. **Range qua ba ngày:** kiểm tra API chia bucket, giới hạn fan-out, gộp thứ tự và paging.
9. **TWCS:** quan sát số SSTable, pending compaction và tuổi dữ liệu; không kỳ vọng file đĩa biến mất ngay tại deadline.
10. **Repair/replica:** trên cluster test, kiểm tra hành vi khi một replica chậm hoặc phục hồi, không cố ý giảm `gc_grace_seconds` vô điều kiện.
11. **Restore:** xác minh quy trình khôi phục tôn trọng deadline retention và không cho dữ liệu quá hạn xuất hiện lại ngoài hợp đồng.

Ví dụ đọc dữ liệu và TTL một partition:

~~~sql
SELECT event_time, event_id, event_type,
       TTL(payload), WRITETIME(payload)
FROM telemetry_ks.events_by_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND bucket_day = ?
LIMIT 50;
~~~

Trong kiểm thử, hãy kiểm tra **giá trị CQL thực tế** thay vì chỉ so sánh entity Java đã được converter ánh xạ. Đừng thử TTL 120 giây trên dữ liệu sản xuất cần giữ 30 ngày.

## 23. Các sai lầm thường gặp

| Sai lầm | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| “Có TTL thì partition tự nhỏ lại.” | Partition key không đổi; SSTable/tombstone có vòng đời riêng. | Thiết kế time bucket và giới hạn kích thước. |
| “Bucket ngày nghĩa là TWCS theo ngày.” | Bucket dựa event time; TWCS nhóm theo write timestamp/SSTable. | Thiết kế/đo hai cơ chế độc lập. |
| “TTL 30 ngày luôn là 30 ngày từ event time.” | TTL gắn với lần ghi; event có thể đến muộn. | Tính deadline theo chính sách, cấp TTL còn lại. |
| “Hết TTL là dữ liệu đã xóa khỏi disk và backup.” | Còn compaction, tombstone, snapshot/backup. | Quản trị vòng đời lưu trữ và backup. |
| “TWCS phù hợp cả với update dữ liệu cũ liên tục.” | Các window có thể bị trộn tuổi, giảm hiệu quả expiry. | Đo workload, xem xét chiến lược khác. |
| “Giảm gc_grace_seconds về 0 luôn an toàn.” | Replica cũ có thể làm dữ liệu xóa hồi sinh. | Đánh giá repair/phiên bản/quy trình vận hành. |
| “Cứ chia partition theo ngày là luôn đủ nhỏ.” | Thiết bị nóng có thể tạo hàng triệu row/ngày. | Ước lượng byte và tải, đổi bucket/shard. |
| “Query qua 30 ngày chỉ cần một paging state.” | Có 30 partition; state gắn query/parameter. | Cursor quản lý từng bucket và giới hạn fan-out. |
| “Ghi lại TTL giống nhau không đổi deadline.” | Thời điểm ghi/write timestamp có thể khác. | Chính sách retry và retention deadline rõ ràng. |
| “Tăng CL sẽ dọn tombstone nhanh hơn.” | CL là yêu cầu phản hồi replica, không phải compaction. | Theo dõi compaction/repair/data model. |

## 24. Tự kiểm tra

**Câu 1.** Vì sao TTL 30 ngày không thay thế việc đưa `bucket_day` vào partition key?

**Đáp án:** TTL điều khiển vòng đời giá trị, không định tuyến dữ liệu hay giới hạn số hàng được ghi vào một partition trong thời gian bucket. Cần partition key phù hợp truy vấn và sizing.

**Câu 2.** Thiết bị gửi event ngày 01/11 nhưng server nhận ngày 20/11; retention là 30 ngày từ event time. Có nên cấp TTL nguyên 30 ngày tại 20/11?

**Đáp án:** Không. Phải tính thời gian còn lại tới deadline 01/12 theo chính sách, hoặc bỏ ghi nếu đã quá hạn.

**Câu 3.** TWCS window 1 ngày có đồng nghĩa một SSTable chứa đúng một partition ngày không?

**Đáp án:** Không. TWCS nhóm SSTable theo thời gian ghi/write timestamps, không theo giá trị `bucket_day`.

**Câu 4.** Khi `TTL(payload)` hết hạn, có thể khẳng định file SSTable và mọi snapshot đã bị xóa không?

**Đáp án:** Không. Hết hạn logic khác thu hồi vật lý và khác chính sách backup/snapshot.

**Câu 5.** Vì sao cập nhật những sự kiện rất cũ có thể làm TWCS kém hiệu quả?

**Đáp án:** Ghi mới của dữ liệu lịch sử có thể rơi vào cửa sổ SSTable hiện tại hoặc trộn dữ liệu có TTL/tuổi khác nhau, khiến khó loại bỏ nguyên SSTable khi hết hạn.

**Câu 6.** Có nên đặt `gc_grace_seconds = 0` chỉ để reclaim đĩa nhanh?

**Đáp án:** Không mặc định. Cần xét repair, thời gian replica offline, topology và cơ chế chống hồi sinh dữ liệu đã xóa.

**Câu 7.** API đọc 7 ngày từ bảng partition theo tenant/device/day cần bao nhiêu partition?

**Đáp án:** Thường ít nhất những partition ngày giao với khoảng, tối đa khoảng 7–8 ngày tùy ranh giới của khoảng nửa mở; phải tính chính xác từ `from/to` và dùng query/paging state cho từng partition.

**Câu 8.** Vì sao retention theo event time cần xác định múi giờ và chính sách ngày lịch?

**Đáp án:** Nếu ứng dụng dùng ngày lịch theo timezone khác UTC, ranh giới ngày và DST có thể khác 24 giờ. Writer, reader và deadline phải thống nhất cùng quy tắc.

---

**Ghi nhớ:** thiết kế lưu giữ dữ liệu theo cửa sổ thời gian cần phối hợp **time bucket trong partition key**, **TTL để giá trị hết hạn**, và **TWCS nếu workload ghi gần tuần tự, ít cập nhật dữ liệu cũ**. Phải quyết định retention từ **event time hay ingest time**, xử lý late arrivals, giới hạn kích thước partition và số bucket đọc, hiểu tombstone/`gc_grace_seconds`/repair/compaction, đồng thời quản lý vòng đời snapshot và backup. Spring Data Cassandra giúp mapping, repository và thực thi CQL, nhưng **không thay thế một chính sách retention được đặc tả và kiểm chứng trên toàn hệ thống phân tán**.
