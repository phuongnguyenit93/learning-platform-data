# Kiểm thử múi giờ, timestamp, TTL và dữ liệu hết hạn trong Apache Cassandra

## 1. Mục tiêu và phạm vi của bài

Trong Apache Cassandra, một row thường được định vị bằng **partition key** và **clustering key**, đọc/ghi thông qua coordinator và các replica theo **replication factor (RF)** và **consistency level (CL)**. Với ứng dụng Java, việc lưu một mốc thời gian đúng nhưng gán sai **bucket theo ngày** có thể khiến query trả kết quả rỗng; việc hiểu sai TTL lại có thể làm bài kiểm thử flake hoặc khiến nghiệp vụ tưởng dữ liệu đã bị xóa vật lý.

Bài thuộc chương **Kiểm thử tích hợp** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**; mục tiêu là xây dựng những phép thử kết nối **Cassandra thật**, không chỉ mock Java Driver, để xác minh:

1. CQL `timestamp` và Java `Instant` biểu diễn **cùng một thời điểm tuyệt đối**.
2. CQL `date` và Java `LocalDate` biểu diễn **ngày lịch, không có timezone**.
3. Một thời điểm UTC có thể thuộc **hai ngày khác nhau** theo múi giờ; partition key dạng `(device_id, event_day)` phải có chính sách bucket nhất quán.
4. CQL literal có `Z` hoặc offset tường minh được chuẩn hóa đúng; literal không ghi timezone dễ làm test phụ thuộc môi trường.
5. Timestamp của sự kiện (**event_time**) khác **write timestamp** của Cassandra (`WRITETIME`, microseconds).
6. `USING TTL`, `TTL(column)`, `default_time_to_live` và dữ liệu hết hạn có semantics riêng.
7. Cell hết hạn có thể được đọc như **không còn giá trị sống** trong khi SSTable/tombstone còn tồn tại cho đến compaction.
8. Kiểm thử TTL với **polling, deadline và margin**, không so cứng từng giây hoặc làm lệch clock máy chủ production.
9. Kết hợp Testcontainers/JUnit 5, Java Driver, Spring Data (nếu dùng), CL và observability để tìm lỗi.
10. Xây dựng test matrix, quy trình ứng phó và checklist trước deploy.

**Phiên bản tham chiếu:** ví dụ Java dùng Java Driver **4.x** với namespace `com.datastax.oss.driver.api.*`, Java 17/JUnit 5, Testcontainers Cassandra và Awaitility. Tọa độ Maven/API cụ thể phải khớp phiên bản được chọn; Cassandra server 4.x dùng trong ví dụ lab không đồng nghĩa mọi tính năng và định dạng timestamp/TTL giống mọi Cassandra 3.x/5.x. Test một node không xác nhận đầy đủ hành vi multi-DC hay quorum production.

## 2. Năm khái niệm thời gian không được đánh đồng

| Khái niệm | Ý nghĩa | Kiểu Java / CQL thường dùng | Sai lầm phổ biến |
|---|---|---|---|
| **Instant / mốc tuyệt đối** | Một thời điểm trên trục UTC | `java.time.Instant`, CQL `timestamp` | Xem timestamp như chuỗi giờ local không có offset |
| **Local date / ngày lịch** | Ngày trong một hệ lịch, không mang timezone | `LocalDate`, CQL `date` | Nghĩ bản thân ngày có UTC offset |
| **ZoneId / múi giờ** | Quy tắc offset/DST theo địa lý | `ZoneId`, `ZonedDateTime` | Chỉ dùng offset cố định cho mọi ngày/năm |
| **Write timestamp** | Timestamp dùng khi Cassandra hòa giải mutation | `WRITETIME(column)`, microseconds | Nhầm với `event_time` nghiệp vụ |
| **TTL/deadline hết hạn** | Tuổi thọ cell/row marker theo quy tắc Cassandra | `USING TTL`, `TTL(column)` | Tin rằng hết TTL đồng nghĩa SSTable bị xóa ngay |

Trong CQL, `timestamp` biểu diễn mốc thời gian (độ chính xác lưu trữ là **mili giây**); Java `Instant` có thể mang nanosecond. Vì vậy **không kiểm tra round-trip nanosecond** bằng cách ghi một Instant có precision nanosecond rồi kỳ vọng Cassandra giữ nguyên mọi chữ số.

`date` lại là kiểu khác: `2026-11-21` **không phải** `2026-11-21T00:00:00Z` hay một timestamp zero-offset.

### 2.1. Minh họa một Instant nhưng hai ngày lịch

~~~text
Instant: 2026-11-21T17:30:00Z

Theo UTC:
  2026-11-21, 17:30

Theo Asia/Ho_Chi_Minh (+07:00):
  2026-11-22, 00:30

Nếu partition key chứa event_day:
  UTC-day bucket   = 2026-11-21
  VN-day bucket    = 2026-11-22

=> Hai partition khác nhau nếu quy ước bị trộn.
~~~

Trong hệ thống, **phải quy định bucket-day** là UTC hay timezone nghiệp vụ rồi áp dụng ở writer, repository, backfill, query và integration tests. Không để từng JVM/host chọn `ZoneId.systemDefault()` theo môi trường.

## 3. Sơ đồ sai lệch giữa writer, reader và Cassandra

~~~mermaid
flowchart TD
    A["Event Instant UTC"] --> B["Writer tính event_day theo ZoneId"]
    A --> C["Reader tính event_day theo ZoneId"]
    B --> D["Partition key: device_id + event_day"]
    C --> E["WHERE device_id=? AND event_day=?"]
    D --> F["Cassandra Murmur3 token + replica placement"]
    E --> G{"Hai zone policies có trùng?"}
    G -->|Có| H["Truy vấn đúng logical partition"]
    G -->|Không| I["Truy vấn partition khác: có thể 0 row"]
    F --> H
~~~

Cassandra không tự “sửa” `event_day` chỉ vì `event_time` có UTC offset đúng. Partition key là **giá trị CQL đã ghi**, không phải field sinh tự động từ một cột timestamp khác, trừ khi bạn thiết kế logic như vậy.

### 3.1. Sai lầm cần tránh

~~~java
// ANTI-PATTERN: ngày thay đổi theo timezone mặc định mỗi máy.
LocalDate eventDay =
    LocalDateTime.ofInstant(eventTime, ZoneId.systemDefault())
        .toLocalDate();
~~~

Một service chạy container UTC và một batch job ở timezone khác có thể ghi/đọc hai partition khác nhau, dù cùng UUID/Instant.

Thay bằng quy ước tường minh:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

static LocalDate utcDay(Instant instant) {
    return instant.atZone(ZoneId.of("UTC")).toLocalDate();
}
~~~

Nếu yêu cầu nghiệp vụ theo Asia/Ho_Chi_Minh, dùng một `ZoneId` cố định trong cấu hình được kiểm soát và test boundary. **Không** vừa ghi theo giờ địa phương vừa query theo ngày UTC.

## 4. Mô hình CQL cho integration test

### 4.1. Keyspace và table lab

~~~cql
-- CHỈ LAB: RF=1 SimpleStrategy phục vụ test container một node.
-- Production cần RF/DC thích hợp, thường dùng NetworkTopologyStrategy.
CREATE KEYSPACE IF NOT EXISTS temporal_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS temporal_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    note text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Trong bảng này:

- **Partition key:** `(device_id, event_day)`.
- **Clustering key:** `event_time`.
- **CQL `timestamp`:** ứng dụng Java nên bind `Instant`.
- **CQL `date`:** ứng dụng Java nên bind `LocalDate`.
- **`reading_value`, `status`, `note`:** cột thường, có thể có TTL khác nhau.
- Mỗi integration test nên dùng `device_id` riêng (UUID random) để tránh làm rò trạng thái qua test song song.
- TTL ngắn chỉ dùng cho test. Trong production, chính sách retention phải theo nhu cầu nghiệp vụ và capacity.

**Lưu ý:** RF=1 trong Testcontainers là sự đánh đổi để chạy nhanh trên một container; nó **không thử được quorum/replication repair như cluster RF=3**. Những trường hợp đó thuộc test cluster đa node riêng.

### 4.2. CQL query theo partition/key

~~~cql
SELECT event_time, reading_value, status, note
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Với key đầy đủ, query nhắm đúng một row. Nếu ngày bucket bị tính lệch, query có thể trả `null` dù row thực sự tồn tại trong partition của ngày khác.

### 4.3. Ghi một row có timestamp rõ ràng

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, note
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK',
    'permanent'
);
~~~

Literal `2026-11-21T10:30:00Z` có hậu tố UTC rõ, ít phụ thuộc môi trường hơn một chuỗi không ghi offset.

## 5. Kiểm thử CQL timestamp có offset

### 5.1. Hai cách viết cùng một thời điểm

~~~cql
-- Với ngày partition là 2026-11-21:
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, note
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'UTC_LITERAL',
    'same instant'
);

-- Kiểm tra đúng row bằng một timestamp cùng instant:
SELECT event_time, status
FROM temporal_lab.readings_by_device_day
WHERE device_id =
    11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T17:30:00+0700';
~~~

`10:30Z` và `17:30+07:00` là cùng một mốc tuyệt đối; chúng không phải hai row độc lập. Phép thử cần xác nhận **trả đúng row đã chèn**, không chỉ in string rồi so nội dung hiển thị.

### 5.2. CQL literal không timezone là nguồn lỗi

~~~cql
-- Không khuyến khích dùng làm fixture độc lập môi trường:
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21 10:30:00',
    24.6
);
~~~

Khi literal không chỉ rõ timezone, kết quả parsing/hiển thị có thể phụ thuộc client/server/tool và cấu hình phiên bản. **Trong integration tests, dùng ISO 8601 có `Z`/offset hoặc bind `Instant` trực tiếp.**

### 5.3. Không lấy định dạng cqlsh làm nguồn chân lý duy nhất

`cqlsh` có thiết lập timezone/hiển thị riêng tùy phiên bản. Hai môi trường có thể in cùng timestamp với chuỗi giờ khác nhau nhưng giữ **cùng epoch milliseconds**.

Khi kiểm thử, đọc dữ liệu qua Java Driver:

~~~java
Instant actual = row.getInstant("event_time");
assertEquals(expectedInstant, actual);
~~~

Dùng `Instant` có precision mili giây để tránh sai lệch do Cassandra `timestamp` không giữ nanosecond.

## 6. Java `Instant`, `OffsetDateTime`, `LocalDateTime` và `LocalDate`

### 6.1. Chọn kiểu theo semantics

| Kiểu Java | Chứa thông tin gì? | Dùng khi |
|---|---|---|
| `Instant` | Mốc tuyệt đối UTC | Lưu/so sánh CQL timestamp |
| `OffsetDateTime` | Date-time kèm một UTC offset | Input có offset rõ, chuyển về Instant khi lưu |
| `ZonedDateTime` | Date-time theo region/DST rules | Tính ngày nghiệp vụ, hiển thị |
| `LocalDateTime` | Date-time không có zone/offset | Chỉ dùng khi đã có timezone policy bên ngoài |
| `LocalDate` | Ngày lịch | CQL date, partition bucket ngày |
| `Clock` | Nguồn thời gian có thể inject | Test logic tính “now”, không thay server clock |

**`LocalDateTime` không tự xác định được một Instant**. Muốn chuyển thành mốc tuyệt đối phải có timezone hoặc offset và chính sách xử lý DST.

### 6.2. Test bắt buộc: một mốc, hai múi giờ

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class TimeBucketPolicyTest {
    @Test
    void oneInstantCanFallIntoDifferentCalendarDates() {
        Instant instant = Instant.parse("2026-11-21T17:30:00Z");

        LocalDate utc = instant
            .atZone(ZoneId.of("UTC"))
            .toLocalDate();

        LocalDate vietnam = instant
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertEquals(LocalDate.of(2026, 11, 21), utc);
        assertEquals(LocalDate.of(2026, 11, 22), vietnam);
        assertNotEquals(utc, vietnam);
    }
}
~~~

Đây là **unit test** của quy tắc bucket; nó là test tốt nhưng chưa đủ để chứng minh mapping CQL. Integration test cần thực sự ghi `event_day` và đọc row theo partition key.

### 6.3. Chọn timezone cố định bằng cấu hình

~~~java
public final class EventDayPolicy {
    private final ZoneId zone;

    public EventDayPolicy(ZoneId zone) {
        this.zone = zone;
    }

    public LocalDate bucket(Instant eventTime) {
        return eventTime.atZone(zone).toLocalDate();
    }
}

// Production ví dụ:
// new EventDayPolicy(ZoneId.of("UTC"))
// hoặc ZoneId.of("Asia/Ho_Chi_Minh")
// theo hợp đồng được các service cùng sử dụng.
~~~

Ưu tiên `ZoneId.of("Area/City")` nếu timezone nghiệp vụ có DST lịch sử/tương lai; không hardcode số giờ cộng/trừ vào timestamp bằng phép `plusHours`.

## 7. Precision: CQL timestamp lưu mili giây, Java Instant có nano

### 7.1. Một trường hợp test dễ bị sai

~~~java
Instant expected = Instant.parse(
    "2026-11-21T10:30:00.123456789Z");

// Cassandra CQL timestamp thường có precision milliseconds.
// Không expect đọc lại chính xác 123456789 nanoseconds.
~~~

Với dữ liệu được ghi qua driver, giá trị lưu thường tương đương theo độ chính xác mili giây:

~~~java
import java.time.temporal.ChronoUnit;

Instant expectedAtMillis =
    expected.truncatedTo(ChronoUnit.MILLIS);
~~~

**Chiều chính xác và cách codec xử lý sub-millisecond phải xác minh theo driver/version.** Đối với integration test chính, đơn giản chọn giá trị `Instant.parse("...123Z")` đã đúng độ chính xác để không phụ thuộc chi tiết làm tròn.

### 7.2. Đừng nhầm epoch seconds với epoch milliseconds

~~~text
Unix time (seconds):       1795257000       (ví dụ)
Unix time (milliseconds):  1795257000000    (ví dụ)
Unix time (microseconds):  1795257000000000 (ví dụ)

CQL timestamp:   milliseconds từ Unix epoch.
WRITETIME(cell):  microseconds từ Unix epoch.
USING TIMESTAMP:  thường nhận microsecond write timestamp.
~~~

Các số trên chỉ minh họa **bậc đơn vị**; khi viết test, dùng `Instant` và `toEpochMilli()` thay vì nhập số tay có thể nhầm ngày thực tế. Đừng đưa `WRITETIME` (microseconds) trực tiếp vào `Instant.ofEpochMilli`.

### 7.3. Hàm chuyển đổi đúng cho write timestamp

~~~java
import java.time.Instant;

static Instant fromWriteTimestampMicros(long micros) {
    long seconds = Math.floorDiv(micros, 1_000_000L);
    long microPart = Math.floorMod(micros, 1_000_000L);

    return Instant.ofEpochSecond(
        seconds,
        microPart * 1_000L);
}
~~~

Dùng `floorDiv`/`floorMod` để hỗ trợ cả giá trị trước Unix epoch, không chỉ chia số nguyên theo hướng truncate-to-zero rồi giả định remainder luôn dương.

**Không coi thời điểm WRITETIME là event_time.** Write có thể đến trễ, được replay hoặc có write timestamp do client chỉ định.

## 8. `WRITETIME` và timestamp của sự kiện là hai trục độc lập

### 8.1. Đọc write timestamp của cell

~~~cql
SELECT event_time,
       reading_value,
       WRITETIME(reading_value) AS write_time_us
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Với một cột thường không-null, `WRITETIME(reading_value)` trả timestamp dùng trong reconciliation của cell, thông thường ở **microseconds**. Nếu cột không có giá trị, kết quả có thể `null`.

Lưu ý:

- Không gọi `WRITETIME` trên primary key column để thay thế timestamp của dữ liệu.
- Không giả định `WRITETIME` của hai cột thường luôn bằng nhau nếu chúng được cập nhật ở những lần ghi khác nhau.
- CQL write timestamp được gắn với mutation và dùng cho last-write-wins reconciliation; nó không nhất thiết bằng giờ thực tế mà business event xảy ra.
- Dùng `USING TIMESTAMP` thủ công có thể tạo timestamp nằm ở quá khứ hoặc tương lai so với server, ảnh hưởng thắng/thua khi cập nhật.

### 8.2. Ví dụ nghiệp vụ ghi sự kiện cũ sau một giờ

~~~text
Sự kiện cảm biến:             2026-11-21T08:00:00Z
Client gửi dữ liệu vào DB:     2026-11-21T09:00:00Z
Server nhận mutation:          quanh 09:00Z
Write timestamp (nếu auto):    quanh thời điểm ghi, tùy clock/node

event_time != WRITETIME(reading_value) là bình thường.
~~~

Một test so `WRITETIME = event_time` là **test giả định sai semantics**. Dùng event_time để sắp thứ tự nghiệp vụ nếu thiết kế clustering phù hợp, không dùng write timestamp làm thứ tự cảm biến trừ khi có lý do được mô tả.

### 8.3. TTL không được định nghĩa bằng cách trừ event_time

Nếu sự kiện cũ được ingest hôm nay với TTL 60 giây, TTL của cell thường bắt đầu từ **thời điểm mutation được áp dụng theo cơ chế server**, không tính đơn thuần từ cột `event_time` của sự kiện. Khi cần “hết hạn 30 ngày sau lúc sự kiện xảy ra”, phải thiết kế expiry policy riêng (ví dụ tính TTL còn lại từ event_time tại ingest) và xử lý late arrival/future events rõ ràng.

Không viết test:

~~~text
event_time = 7 ngày trước
INSERT USING TTL 1 giờ hôm nay
=> row chắc chắn đã hết hạn ngay
~~~

Giả định trên không đúng với TTL thông thường của Cassandra.

## 9. TTL: điều gì thật sự hết hạn?

### 9.1. CQL `USING TTL`

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, status
) VALUES (?, ?, ?, ?, ?)
USING TTL 8;
~~~

`8` là số **giây** của TTL trong ví dụ lab, không phải milliseconds. Với prepared statement và driver version hỗ trợ, có thể bind TTL:

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, status
) VALUES (?, ?, ?, ?, ?)
USING TTL ?;
~~~

Các cột thường và thông tin row liveness chịu ảnh hưởng TTL theo semantics Cassandra. **Không coi primary key column bản thân có một TTL độc lập giống cột thường**; primary key dùng để định danh row/partition.

### 9.2. TTL cấp bảng và cấp mutation

Cassandra cũng có table option `default_time_to_live`, tùy phiên bản:

~~~cql
-- CHỈ dùng cho bảng test RIÊNG, không alter bảng chung vô ý.
CREATE TABLE temporal_lab.ttl_only_demo (
    id uuid PRIMARY KEY,
    value text
) WITH default_time_to_live = 600;
~~~

Ở đây mặc định 600 giây cho dữ liệu thuộc bảng theo semantics table TTL. TTL đặt rõ trong mutation có thể tương tác/ghi đè default theo quy tắc của Cassandra version. **Đừng sửa `default_time_to_live` của bảng production để làm test chạy nhanh hơn.**

### 9.3. TTL là cấp cell, không phải “hẹn giờ xóa cả bảng”

Một row có thể gồm:

- `reading_value` **không có TTL**.
- `status` có TTL 8 giây.
- `note` có TTL khác hoặc không có TTL.

Khi `status` hết hạn, row **vẫn có thể tồn tại** vì `reading_value` còn sống. Kiểm thử phải xác minh **cell mong đợi** thay vì mặc định `ResultSet.one()==null`.

### 9.4. `TTL(column)` chỉ là giá trị còn lại tại lúc đọc

~~~cql
SELECT reading_value,
       status,
       TTL(status) AS status_ttl_seconds
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Nếu `status` còn TTL, `TTL(status)` thường trả về **số giây còn lại** dưới dạng integer. Nếu cell không có TTL hoặc không có giá trị sống, kết quả có thể `null`. Một số ràng buộc hàm/collection phụ thuộc phiên bản, nên test trên đúng type supported.

**Đừng assert TTL == 8 đúng ngay sau INSERT**. Thời gian đi qua driver, network, scheduler và server khiến TTL quan sát được có thể đã giảm. Kiểm tra trong **khoảng hợp lý** hoặc chờ đến khi không còn cell sống.

## 10. Hết TTL không đồng nghĩa xóa SSTable ngay

### 10.1. TTL chuyển cell thành dữ liệu không còn sống

Cassandra xử lý expiration/tombstone theo mô hình phân tán. Tại thời điểm đọc sau khi TTL hết hạn, cell thường không còn được trả như **giá trị sống**. Tuy nhiên dữ liệu vật lý và tombstone có thể vẫn nằm trong SSTable/memtable cho đến lúc compaction thỏa điều kiện an toàn.

~~~mermaid
flowchart TD
    A["INSERT / UPDATE có TTL"] --> B["Cell sống, TTL đếm ngược"]
    B --> C{"TTL hết hạn?"}
    C -->|Chưa| D["SELECT thấy giá trị sống"]
    C -->|Rồi| E["Read path coi cell đã hết hạn"]
    E --> F["Tombstone / expired state còn trong storage"]
    F --> G["Compaction + quy tắc an toàn"]
    G --> H["Có thể reclaim dung lượng vật lý"]
~~~

**Sai lầm nghiêm trọng:** assertion “`SELECT` không thấy row ⇒ SSTable đã giảm số byte” là vô căn cứ. Disk reclaim phụ thuộc compaction, tombstone safety, repair, RF, gc grace và chiến lược lưu trữ.

### 10.2. Cẩn thận với dữ liệu cũ và TTL ghi đè

Một update có TTL tạo phiên bản cell mới; khi phiên bản này hết hạn, không nên tự giả định phiên bản cũ xuất hiện trở lại như một database MVCC. Tombstone/expiration tham gia reconciliation, bảo vệ khỏi việc dữ liệu cũ sống lại trong cửa sổ thích hợp.

Test đúng nên thiết kế **giá trị cũ và mới**, điều kiện đọc sau hết hạn, và không kỳ vọng hành vi resurrection không được CQL bảo đảm.

### 10.3. TTL và consistency

Đối với cluster RF=3:

- Replica có thể nhận mutation/TTL ở các thời điểm khác nhau; clock skew ảnh hưởng xác định thời gian hết hạn.
- CL đọc/ghi quyết định điều kiện phản hồi, không bảo đảm mọi clock node đồng bộ hoàn hảo.
- Repair và hinted handoff giúp đồng bộ trạng thái replica theo semantics của Cassandra nhưng không thay NTP/clock discipline.
- Test một node với RF=1 không phát hiện lỗi cross-replica/time-skew; production-like test cần topology đa node có kiểm soát.

## 11. Tại sao `Thread.sleep(TTL * 1000)` gây flaky test?

### 11.1. Vấn đề

~~~java
// ANTI-PATTERN:
insertWithTtl(3);
Thread.sleep(3000);
assertNull(findExpired());
~~~

Bài test này giả định:

- TTL bắt đầu đúng khi method Java return.
- Clock server và client đồng bộ từng mili giây.
- Scheduling/network không biến động.
- Response read không bị cache/paging/replication delay.
- Assertion đang kiểm tra đúng cell hoặc row liveness.

Những giả định đó không an toàn. Nếu scheduler chạy hơi sớm, test fail; nếu sleep kéo dài quá mức, test suite chậm và không chẩn đoán tốt nguyên nhân.

### 11.2. Dùng polling có deadline

Một chiến lược thực tế:

1. Ghi dữ liệu có **TTL đủ dài** để kiểm tra nó xuất hiện trước khi hết hạn.
2. Đọc lần đầu và xác nhận cell **đang sống**.
3. Poll `SELECT` mỗi vài trăm milliseconds.
4. Dừng khi điều kiện expiry được quan sát hoặc **đạt deadline**.
5. Nếu hết deadline, in query ID/CL/row status/type và metrics (không ghi PII).
6. Dùng UUID riêng, cleanup test resources và tránh chạy quá nhiều test TTL song song.

Ví dụ với Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

insertStatusWithTtl(deviceId, day, eventTime, "TEMP", 8);

assertEquals("TEMP", findStatus(deviceId, day, eventTime));

await()
    .atMost(Duration.ofSeconds(25))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() ->
        assertNull(findStatus(deviceId, day, eventTime)));
~~~

Đây là ví dụ cấu trúc test; `insertStatusWithTtl` và `findStatus` phải được định nghĩa, có timeout phù hợp với CI. **Không dùng Awaitility để “làm yên” một test có lỗi schema hoặc clock drift nghiêm trọng**: deadline và logs phải làm failures quan sát được.

### 11.3. Chọn TTL đủ để đảm bảo trạng thái trước hết hạn

Nếu TTL=1 giây trên CI có thể khởi động chậm, query đầu tiên đôi khi đã tới sau hết hạn. Khi bạn cần test cả *trạng thái trước* và *trạng thái sau*, dùng TTL ví dụ 8–10 giây và giới hạn upper bound (20–30 giây). Đây là trade-off **độ ổn định ↔ thời gian chạy test**; số cụ thể phải điều chỉnh theo CI.

Đừng chạy đồng thời 100 bài TTL mỗi bài ngủ 30 giây và tin rằng đó là kiểm thử đáng tin cậy.

## 12. Một bộ integration test dùng Cassandra Testcontainers

### 12.1. Tư duy kiến trúc của bộ test

~~~text
JUnit 5 / Testcontainers
  |
  +-- Cassandra container (một node, keyspace lab RF=1)
  |
  +-- CqlSession dùng Java Driver 4.x
  |     |
  |     +-- Prepared INSERT / SELECT
  |     +-- SET TTL / read TTL(column)
  |
  +-- Tests
        +-- timestamp round-trip
        +-- timezone bucket
        +-- partial-cell TTL expiry
        +-- row toàn bộ TTL expiry
        +-- WRITETIME vs event_time
        +-- negative/pre-epoch timestamp
~~~

Không cần mock `CqlSession` khi muốn kiểm tra **CQL codec, Cassandra expiration và query execution**. Mock vẫn hữu ích cho unit tests về business logic, nhưng không xác nhận dữ liệu thực sự lưu và hết hạn như thế nào.

### 12.2. Dependencies cần có

Ví dụ `pom.xml` tối giản (không gắn version để tránh xung đột BOM):

~~~xml
<!-- Khai báo dependencies theo BOM/versions tương thích đã chọn. -->
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>cassandra</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.awaitility</groupId>
        <artifactId>awaitility</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Java Driver 4.x phải nằm trong classpath ứng dụng/test theo BOM riêng. **Không giả định tất cả Testcontainers 1.x/2.x có cùng artifact coordinates và import**; kiểm tra changelog theo release. Không hardcode test secret trong production config.

### 12.3. Quy tắc CI

- Docker-compatible runtime phải sẵn; nếu không, test phải báo thiếu môi trường rõ ràng, không chuyển thành test giả passing.
- Container startup có thể chậm; phân biệt **startup timeout** và **TTL wait timeout**.
- Gắn Cassandra server version/driver version có chủ đích, không dùng một tag trôi nổi không kiểm soát.
- Không cho test tự kết nối cluster production từ biến môi trường.
- Test trên cùng một container RF=1 không đánh giá cross-DC, repair hay quorum.
- Dữ liệu sample dùng UUID random; schema/table names chỉ dành cho test.

## 13. Fixture JUnit 5 + Testcontainers + Java Driver 4.x

### 13.1. Bộ test có kết nối Cassandra thật

Ví dụ dùng `CassandraContainer` của một bản Testcontainers hỗ trợ constructor/metadata methods tương ứng, Cassandra **4.1.x** trong lab, Java Driver 4.x và JUnit 5. Keyspace RF=1 chỉ dùng cho lab **một node**, không thay thế test production nhiều replica.

~~~java
package demo.cassandra.temporal;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.UUID;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class CassandraTemporalIntegrationTest {

    @Container
    static final CassandraContainer<?> DB =
        new CassandraContainer<>(
            DockerImageName.parse("cassandra:4.1.6"));

    static CqlSession session;
    static PreparedStatement insertPermanent;
    static PreparedStatement insertTtl;
    static PreparedStatement updateStatusTtl;
    static PreparedStatement selectRow;
    static PreparedStatement selectStatusTtl;

    @BeforeAll
    static void startSessionAndSchema() {
        // Xác minh API getContactPoint/getLocalDatacenter
        // trong bản Testcontainers được chọn.
        session = CqlSession.builder()
            .addContactPoint(DB.getContactPoint())
            .withLocalDatacenter(DB.getLocalDatacenter())
            .build();

        session.execute(
            "CREATE KEYSPACE IF NOT EXISTS temporal_lab " +
            "WITH replication = {" +
            "'class': 'SimpleStrategy', " +
            "'replication_factor': 1} " +
            "AND durable_writes = true"
        );

        session.execute(
            "CREATE TABLE IF NOT EXISTS " +
            "temporal_lab.readings_by_device_day (" +
            "device_id uuid, " +
            "event_day date, " +
            "event_time timestamp, " +
            "reading_value double, " +
            "status text, note text, " +
            "PRIMARY KEY ((device_id, event_day), event_time)) " +
            "WITH CLUSTERING ORDER BY (event_time DESC)"
        );

        insertPermanent = session.prepare(
            "INSERT INTO temporal_lab.readings_by_device_day " +
            "(device_id, event_day, event_time, " +
            " reading_value, status, note) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );

        insertTtl = session.prepare(
            "INSERT INTO temporal_lab.readings_by_device_day " +
            "(device_id, event_day, event_time, " +
            " reading_value, status) " +
            "VALUES (?, ?, ?, ?, ?) USING TTL ?"
        );

        updateStatusTtl = session.prepare(
            "UPDATE temporal_lab.readings_by_device_day " +
            "USING TTL ? SET status = ? " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );

        selectRow = session.prepare(
            "SELECT event_time, reading_value, status, note " +
            "FROM temporal_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );

        selectStatusTtl = session.prepare(
            "SELECT TTL(status) AS seconds_left " +
            "FROM temporal_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time = ?"
        );
    }

    static Row read(UUID id, LocalDate day, Instant at) {
        BoundStatement query = selectRow
            .bind(id, day, at)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);
        return session.execute(query).one();
    }

    @AfterAll
    static void closeSession() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void timestampRoundTripUsesInstantAtMillisecondPrecision() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T10:30:00.123Z");
        LocalDate day = at.atZone(ZoneId.of("UTC"))
            .toLocalDate();

        session.execute(insertPermanent.bind(
            id, day, at, 24.6, "OK", "persistent"));

        Row row = read(id, day, at);
        assertNotNull(row);
        assertEquals(at, row.getInstant("event_time"));
        assertEquals(24.6, row.getDouble("reading_value"), 0.00001);
        assertEquals("OK", row.getString("status"));
    }

    @Test
    void twoTimezonesCanPointToDifferentDatePartitions() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T17:30:00Z");
        LocalDate utcDay = at.atZone(ZoneId.of("UTC"))
            .toLocalDate();
        LocalDate localDay = at
            .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
            .toLocalDate();

        assertNotEquals(utcDay, localDay);
        session.execute(insertPermanent.bind(
            id, utcDay, at, 25.0, "OK", "UTC bucket"));

        assertNotNull(read(id, utcDay, at));
        // Sai bucket -> không thấy row dù event_time chính xác.
        assertNull(read(id, localDay, at));
    }

    @Test
    void fullyExpiringInsertedRowEventuallyDisappears() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T11:00:00Z");
        LocalDate day = LocalDate.of(2026, 11, 21);

        session.execute(insertTtl
            .bind(id, day, at, 26.0, "TEMP", 12)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE));

        Row first = read(id, day, at);
        assertNotNull(first);
        assertEquals("TEMP", first.getString("status"));

        await()
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(300))
            .untilAsserted(() ->
                assertNull(read(id, day, at)));
    }

    @Test
    void expiringOneCellDoesNotRemoveAnotherLiveCell() {
        UUID id = UUID.randomUUID();
        Instant at = Instant.parse("2026-11-21T12:00:00Z");
        LocalDate day = LocalDate.of(2026, 11, 21);

        session.execute(insertPermanent.bind(
            id, day, at, 22.5, null, "KEEP"));

        session.execute(updateStatusTtl.bind(
            12, "TEMP", id, day, at));

        Row before = read(id, day, at);
        assertNotNull(before);
        assertEquals("TEMP", before.getString("status"));
        assertEquals(22.5,
            before.getDouble("reading_value"), 0.00001);

        Row ttlRow = session.execute(
            selectStatusTtl.bind(id, day, at)).one();
        assertNotNull(ttlRow);
        assertFalse(ttlRow.isNull("seconds_left"));
        int secondsLeft = ttlRow.getInt("seconds_left");
        // Gần ranh giới giây, TTL remaining có thể tiến sát 0.
        assertTrue(secondsLeft >= 0 && secondsLeft <= 12);

        await()
            .atMost(Duration.ofSeconds(40))
            .pollInterval(Duration.ofMillis(300))
            .untilAsserted(() -> {
                Row after = read(id, day, at);
                assertNotNull(after);
                assertNull(after.getString("status"));
                assertEquals(22.5,
                    after.getDouble("reading_value"), 0.00001);
                assertEquals("KEEP", after.getString("note"));
            });
    }
}
~~~

Đây là **fixture minh họa**: chưa xác minh compile/runtime trên mọi combination Testcontainers/Driver. Pin các artifacts tương thích, kiểm tra JUnit extension/container startup và điều chỉnh tên local DC/constructor theo image/version.

### 13.2. Mỗi test cần primary key riêng

Nếu nhiều bài test ghi cùng partition/time, TTL hoặc update từ test này có thể ảnh hưởng test khác. Dùng `UUID.randomUUID()` giúp tạo partition khác, không biến integration test thành stateful test ngẫu nhiên. Vẫn cần keyspace/table chỉ dành cho test và cleanup có kiểm soát.

### 13.3. Tách test nhanh khỏi test storage dài hạn

- Một container dùng chung giảm startup, nhưng nhiều mutation/TTL có thể làm tombstone tích lũy.
- Không `TRUNCATE` table đang được nhiều test song song sử dụng.
- Không đổi `default_time_to_live` của bảng chung để test một case.
- Không thử repair/compaction chủ động trên container có test khác.
- Đóng `CqlSession` sau suite, cleanup container disposable.
- Kiểm chứng purge vật lý/tombstone compaction cần suite storage riêng.

## 14. Kiểm thử cell expiry và row expiry khác nhau

### 14.1. Một cell có TTL, cell khác không

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, note
) VALUES (?, ?, ?, ?, ?);

UPDATE temporal_lab.readings_by_device_day
USING TTL 8
SET status = 'TEMP'
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

Sau expiration:

- Row **còn** vì `reading_value` và `note` còn sống.
- `status` hết hạn: `row.getString("status")` trả `null`.
- `TTL(status)` không còn countdown của cell sống.
- Không assert `ResultSet.one()==null` cho **partial TTL**.

### 14.2. Tất cả regular cells có TTL

Nếu `INSERT ... USING TTL` cho mọi regular cells và row marker, khi chúng đều hết hạn có thể không còn row sống. Đây là một test riêng với partial TTL; static column hoặc nhiều TTL khác nhau có thể tạo tình trạng phức tạp hơn.

### 14.3. `TTL(column)` null không chứng minh expiry

~~~cql
SELECT reading_value, status,
       TTL(status) AS remaining
FROM temporal_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time = ?;
~~~

| Giá trị cell | TTL(column) | Diễn giải có thể |
|---|---|---|
| Có giá trị | Integer dương | Cell sống và có TTL |
| Có giá trị | Null | Cell sống không TTL |
| Null | Null | Chưa có/đã hết hạn/đã xóa |
| Row không tồn tại | Không có row | Không có row sống phù hợp |

Chỉ thấy `TTL(...) == null` **chưa đủ** để kết luận dữ liệu đã hết hạn; cần biết fixture/lịch sử ghi và kiểm tra giá trị cell.

## 15. Fake `Clock` của ứng dụng khác đồng hồ TTL của server

### 15.1. Fake Clock tốt cho business rules

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

Clock fixed = Clock.fixed(
    Instant.parse("2026-11-21T10:00:00Z"),
    ZoneOffset.UTC);

Instant deadline =
    Instant.now(fixed).plus(Duration.ofDays(7));

assertEquals(
    Instant.parse("2026-11-28T10:00:00Z"),
    deadline);
~~~

`Clock.fixed` dùng để unit test service quyết định ngày bucket, retention deadline hoặc input validation. Nó loại bỏ phụ thuộc vào “bây giờ” trên máy CI.

### 15.2. Fake Clock **không** thúc TTL Cassandra trôi nhanh

~~~text
Java service:
    Instant.now(injectedClock) -> có thể mock

Cassandra node:
    Server clock và expiration -> độc lập với mock Java

Đổi injected Clock tiến 10 ngày:
    KHÔNG có nghĩa TTL trong Cassandra đã trôi 10 ngày.
~~~

Vì vậy **không** thay `Clock` trong service rồi expect một row có `USING TTL 600` biến mất ngay. Test behavior của server bằng TTL ngắn/polling trên container hoặc môi trường cô lập; test business logic bằng fake Clock riêng.

### 15.3. Tính TTL từ một hạn tuyệt đối

Nếu nghiệp vụ muốn dữ liệu sống đến **đầu ngày UTC tiếp theo**, có thể có hàm:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

static long ttlSecondsUntilUtcMidnight(
        Instant now, LocalDate eventDay) {

    Instant nextMidnight = eventDay.plusDays(1)
        .atStartOfDay(ZoneOffset.UTC)
        .toInstant();

    long seconds =
        Duration.between(now, nextMidnight).getSeconds();

    return Math.max(0L, seconds);
}
~~~

**Cảnh báo:**

- `TTL=0` có semantics riêng trong Cassandra tùy version/table default, không nên coi đây là “expire immediately”.
- Nếu deadline đã qua, service cần nhánh **không ghi/loại bỏ/archive** có chủ đích.
- Kiểm tra max TTL (tính bằng giây) và các ranh giới ngày tháng theo server version.
- `Duration.getSeconds()` không phải phép làm tròn lên; test các deadline còn dưới 1 giây.
- Nếu retry sau 30 giây, TTL tính lại từ deadline cố định có thể khác TTL ban đầu; điều này cần được ghi trong hợp đồng retention.

### 15.4. Late events: expiration “từ lúc ingest” khác “từ event time”

~~~text
event_time: 2026-11-10T10:00:00Z
ingested_at: 2026-11-21T10:00:00Z

Policy A: giữ 7 ngày từ ingest
Policy B: giữ 7 ngày từ event time
~~~

Với Policy A, row vẫn có thể sống nhiều ngày sau khi ingest. Với Policy B, event đã quá hạn và cần quyết định **từ chối/archive/không ghi**, không đơn giản cứ đặt `USING TTL 0`.

Test phải cover event cũ, event tương lai do source clock-skew và cùng một event được replay.

## 16. DST, ambiguous local time và cập nhật tzdb

### 16.1. Một local time không nhất thiết ánh xạ duy nhất sang Instant

Với zone có Daylight Saving Time:

- **Gap:** một khoảng local time không tồn tại khi đồng hồ được chỉnh lên.
- **Overlap:** một khoảng local time xuất hiện hai lần khi đồng hồ lùi.

Ví dụ trong `America/New_York` năm 2026 theo tzdb thường dùng:

- `2026-03-08 02:30` nằm trong gap.
- `2026-11-01 01:30` rơi vào overlap.

### 16.2. Test `ZoneRules.getValidOffsets`

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.zone.ZoneRules;
import org.junit.jupiter.api.Test;

class DstPolicyTest {
    private static final ZoneId NEW_YORK =
        ZoneId.of("America/New_York");

    @Test
    void detectGapAndOverlapBeforeResolvingInstant() {
        ZoneRules rules = NEW_YORK.getRules();

        LocalDateTime springGap =
            LocalDateTime.of(2026, 3, 8, 2, 30);

        LocalDateTime autumnOverlap =
            LocalDateTime.of(2026, 11, 1, 1, 30);

        assertEquals(0,
            rules.getValidOffsets(springGap).size());

        assertEquals(2,
            rules.getValidOffsets(autumnOverlap).size());
    }
}
~~~

Nếu user gửi chuỗi local không offset, service phải có chính sách cụ thể: từ chối gap/ambiguous input, yêu cầu offset hoặc áp dụng một rule đã được nghiệp vụ chấp thuận.

Không mặc định `LocalDateTime.atZone(zone)` tự chọn đúng Instant mong muốn ở overlap; API có thể resolve theo quy tắc mặc định.

### 16.3. Tzdb có thể thay đổi

Các quốc gia có thể điều chỉnh quy tắc DST trong tương lai; JDK chứa timezone database theo release. Test dùng lịch tương lai cần quan sát khi nâng JDK/tzdb, không lấy fixed offset làm sự thật cho mọi năm.

Gợi ý:

- API event timestamp nên dùng ISO 8601 có `Z` hoặc explicit offset.
- Scheduling/booking nên giữ **ZoneId** nghiệp vụ, không chỉ UTC offset.
- Ghi nhận JDK/tzdb version trong báo cáo compatibility tests.
- Không dùng timezone mặc định CI host trong logic partition key.

## 17. Clock skew giữa replica và CL

### 17.1. Vì sao đồng hồ node quan trọng?

Cassandra sử dụng thời gian/timestamp cho mutation, TTL, reconciliation và nhiều hoạt động vận hành. Đồng hồ các node lệch có thể làm behavior gần thời điểm expiry khó dự đoán:

- Replica có thể đánh giá thời điểm expiration khác nhau trong cửa sổ sát hạn theo version/implementation.
- Mutation dùng timestamp tự động hoặc do client chỉ định có thể thắng/thua không như logic nghiệp vụ nghĩ.
- Log timeline/timeout và việc so `WRITETIME` với event_time trở nên khó diễn giải.
- Test đọc với CL khác nhau có thể bộc lộ các điều kiện bất nhất.

Production cần time synchronization (NTP/chrony hoặc cơ chế đã được tổ chức phê duyệt), giám sát clock offset và alert skew.

### 17.2. Không chỉnh clock của cluster production để thử TTL

Một test không được:

~~~text
SSH vào Cassandra production
chỉnh clock tiến 1 giờ để TTL hết hạn
đọc dữ liệu
đổi clock về
~~~

Việc này ảnh hưởng rộng đến DB, logs, certificates, token/replica hoạt động và các request đang chạy. Test clock skew phải có **cluster cô lập, fault injection có giới hạn, operator chịu trách nhiệm và rollback**.

### 17.3. Một-node Testcontainers không chứng minh quorum

| Trường hợp | Test một node RF=1 đủ? | Cần gì thêm |
|---|---|---|
| Java codec `Instant`/`LocalDate` | Có trong version được thử | Test driver/server versions khác |
| UTC/VN date bucket | Có | Kiểm tra mọi writer/reader policy |
| Basic `USING TTL` và `TTL(column)` | Có | Thử thêm table default TTL/version |
| `LOCAL_QUORUM` khi một replica down | **Không** | Cluster RF=3, lỗi node có kiểm soát |
| Multi-DC quorum/placement | **Không** | Nhiều DC với NetworkTopologyStrategy |
| Hints, repair, bootstrap | **Không** | Cluster integration suite riêng |
| Clock skew cross-node | **Không** | Fault injection trong lab riêng |
| Purge tombstone vật lý | Không thích hợp cho test vài giây | Storage/compaction suite dài hạn |

Đừng lấy việc `CL=ONE` hoặc `QUORUM` chạy thành công trong RF=1 làm chứng cứ rằng **RF=3 LOCAL_QUORUM** trong production cũng an toàn với replica failure.

## 18. Isolation và parallel execution

### 18.1. Nguồn flake thường gặp

- Test A/B ghi cùng primary key; TTL A làm cell B biến mất.
- Test A gọi `TRUNCATE` trong khi test B đang SELECT.
- CI chạy song song khiến container disk/CPU và JVM GC tranh tài nguyên.
- Test dùng `ZoneId.systemDefault()` trên máy lập trình UTC nhưng CI khác timezone.
- Test assert `TTL(...) == 8` ngay sau INSERT.
- Test bắt đầu deadline TTL trước khi container khởi động hoàn tất.
- Test tưởng `event_time` và `WRITETIME` luôn giống nhau.
- Test đóng session/container khi future/async test chưa hoàn thành.

### 18.2. Thiết kế test cô lập

1. Mỗi case có `device_id` riêng và timestamp được chọn tường minh.
2. Không dùng row shared hoặc dữ liệu fixture sống nhiều tuần không có owner.
3. Không alter table default TTL trong test khác đang chạy.
4. Keyspace test có tên rõ và quyền ghi giới hạn.
5. Java/CI timezone được khai báo rõ; ứng dụng không dựa vào default.
6. TTL đủ dài cho assertion “trước khi hết hạn”.
7. Polling có deadline và failure message rõ, tránh sleep cố định.
8. Test chỉnh server settings/clock phải chạy tuần tự trong cluster riêng.
9. Tắt job backfill/repair ngoài kế hoạch khi benchmark latency.
10. Close session và cleanup chỉ đúng môi trường lab được tạo cho test.

### 18.3. Pre-epoch timestamp và conversion âm

~~~java
Instant historic =
    Instant.parse("1965-04-01T12:00:00Z");

assertTrue(historic.toEpochMilli() < 0);
~~~

Đây là unit test. Integration test muốn xác minh Cassandra/codec xử lý mốc trước epoch cần ghi/đọc `historic` trên server version được hỗ trợ. Khi chuyển microsecond `WRITETIME` sang Instant, dùng `Math.floorDiv`/`floorMod` thay cho phép chia/remainder giả định dương.

## 19. Retry, concurrent writes, TTL và dữ liệu đến muộn

### 19.1. Một retry có thể thay đổi deadline expiry

Giả sử:

~~~text
Attempt 1: INSERT ... USING TTL 600
  Đã apply, client timeout.

Attempt 2 sau 30 giây:
  INSERT lại cùng key ... USING TTL 600

Hạn expiry có thể thay đổi tùy reconciliation/timestamps.
~~~

Do đó, **idempotent theo primary key** chưa đủ để chứng minh idempotent theo **expiry policy**. Nếu deadline phải tuyệt đối, lưu/đối chiếu `expires_at` và tính TTL có chủ đích; đánh giá `USING TIMESTAMP` và concurrent mutation trước khi retry.

### 19.2. UPDATE chỉ một cell không reset TTL mọi cell

~~~cql
INSERT INTO temporal_lab.readings_by_device_day (
    device_id, event_day, event_time, reading_value, note
) VALUES (?, ?, ?, ?, ?);

UPDATE temporal_lab.readings_by_device_day
USING TTL 30
SET status = ?
WHERE device_id = ? AND event_day = ? AND event_time = ?;
~~~

Sau 30 giây, test phải đọc lại row và xác minh `status` đã hết hạn, còn `reading_value`/`note` sống. Không coi cả row đã biến mất chỉ vì một cột TTL hết.

### 19.3. LWT kết hợp TTL

`INSERT ... IF NOT EXISTS` sử dụng conditional/LWT semantics; nếu lần đầu thành công nhưng client timeout, retry có thể trả `wasApplied()==false` khi row vẫn sống. Nếu row đã hết hạn sau đó, điều kiện có thể đổi kết quả theo trạng thái hiện tại.

Để test nghiệp vụ:

- Dùng operation ID và primary key cố định.
- Ghi rõ điều kiện trước write.
- Nêu CL/serial consistency phù hợp phiên bản.
- Đo deadline/cancel/retry; không suy “timeout tức rollback”.
- Đối soát row/invariant thay vì tin riêng cờ LWT lần retry.

Không bật LWT cho mọi bài TTL đơn giản; nó thêm chi phí đồng thuận và làm test khó phân lập.

## 20. Ma trận kiểm thử tối thiểu

| ID | Kịch bản | Điều mong đợi | Lớp kiểm thử |
|---|---|---|---|
| T01 | `Instant` có millisecond ghi/đọc | Round-trip đúng milli | Integration |
| T02 | `10:30Z` so `17:30+07:00` | Một Instant, một CQL row | Unit + integration |
| T03 | `17:30Z` theo UTC/VN | Hai LocalDate khác nhau | Unit |
| T04 | Writer UTC day, reader VN day | Wrong partition trả 0 row | Integration |
| T05 | Nanosecond Instant | Chuẩn hóa hoặc kiểm tra policy milli | Unit + integration |
| T06 | Timestamp trước epoch | Không lỗi sign/overflow | Unit + integration |
| T07 | `WRITETIME(reading_value)` | Microsecond write timestamp | Integration |
| T08 | Event_time cũ, ingest hôm nay | TTL không tự tính từ event time | Integration |
| T09 | INSERT toàn regular cells với TTL | Row hết hạn theo kỳ vọng | Integration |
| T10 | UPDATE TTL một cell | Row vẫn tồn tại nếu cell khác sống | Integration |
| T11 | `TTL(column)` trước expiry | Integer còn lại theo khoảng | Integration |
| T12 | `TTL(column)` null | Phân biệt no TTL và expired | Integration |
| T13 | Table `default_time_to_live` | Semantics được thử ở bảng riêng | Integration |
| T14 | Retry mutation TTL | Không hiểu sai expiry deadline | Integration |
| T15 | DST gap/overlap | Có chính sách xử lý offset | Unit |
| T16 | JVM timezone khác UTC | Bucket không lệ thuộc systemDefault | Unit |
| T17 | Expired row nhưng disk chưa giảm | Không assert physical deletion ngay | Storage/observability |
| T18 | RF=3, một replica down | CL/availability đúng | Cluster đa node |
| T19 | Clock skew có kiểm soát | Nhận biết divergence gần expiry | Cluster cô lập |
| T20 | Hai tests chạy song song | Không tranh key/table | Integration |

## 21. Runbook A — Cùng event_time nhưng query không tìm thấy row

**Tình huống:** Writer ghi dữ liệu lúc `2026-11-21T17:30:00Z`, service Java ở timezone UTC đọc được; service khác ở Asia/Ho_Chi_Minh trả `404`. Cả hai đều bind đúng `event_time`.

**Bước 1 — Xác minh CQL thực:** query có đủ `device_id`, `event_day` và `event_time`? Các giá trị được bind theo type `UUID`, `LocalDate`, `Instant` hay ghép chuỗi?

**Bước 2 — So bucket policy:** writer có dùng `UTC` còn reader dùng `ZoneId.systemDefault()` không? Kiểm tra thời điểm nằm sát ranh giới midnight.

**Bước 3 — Đối chiếu thời điểm:** log an toàn `event_time` đã được chuẩn hóa hoặc correlation ID được cấp quyền; không ghi raw device/tenant IDs ra metrics nhãn high-cardinality.

**Bước 4 — Tìm partition thực:** trong môi trường điều tra có quyền, truy vấn hai giá trị `event_day` hợp lệ theo UTC/zone nghiệp vụ. Không scan toàn cluster để “tìm row mất” bằng `ALLOW FILTERING`.

**Bước 5 — Sửa nơi tính bucket:** tạo một `EventDayPolicy` dùng chung trong writer, reader và backfill; chọn zone rõ ràng, có test qua midnight/DST.

**Bước 6 — Migration nếu dữ liệu đã ghi sai:** đánh giá phạm vi ngày/partition; tạo kế hoạch copy/backfill sang partition đúng có checkpoint, rate limit và đối soát; đừng đổi Java code rồi mặc định SSTable cũ tự chuyển chỗ.

**Bước 7 — Xác minh:** đọc cùng row từ mọi service, kiểm tra p99, số partition read và tỷ lệ not-found; bổ sung regression test vùng ranh giới.

### Ví dụ nhận diện

~~~text
event_time UTC:      2026-11-21T17:30:00Z
writer event_day:    2026-11-21 (UTC)
reader event_day:    2026-11-22 (Asia/Ho_Chi_Minh)

Kết luận:
  Không có bằng chứng replica mất dữ liệu.
  Hai query nhắm tới hai partition khác nhau.
~~~

## 22. Runbook B — Test TTL flaky hoặc thất bại trên CI

**Tình huống:** Test dùng `USING TTL 2`, `Thread.sleep(2000)` rồi assert row null. Laptop pass, CI chậm thỉnh thoảng fail; có khi assertion “row còn sống” cũng fail.

1. **Tách startup và TTL timing:** container có thực sự sẵn trước khi bắt đầu insert không? Cassandra schema agreement/prepare đã xong chưa?
2. **Ghi thời điểm có kiểm soát:** measurement tại client gửi/nhận, TTL requested, query ID, nhưng không coi client timestamp là server expiration chính xác.
3. **Tăng TTL test vừa đủ:** ví dụ 8–12 giây để assertion “trước expiry” có cơ hội ổn định; không cố test dưới 1 giây trừ khi feature yêu cầu.
4. **Thay sleep bằng polling:** `await().atMost(...).pollInterval(...).untilAsserted(...)` để dừng sớm khi điều kiện đạt và có deadline khi không đạt.
5. **Đo đúng đối tượng:** partial TTL → `status==null` nhưng row vẫn còn; full TTL → có thể `one()==null` nếu không còn live cells.
6. **Kiểm tra đồng hồ server/CI:** NTP offset, Docker host load, GC, network và retries. Không chỉnh clock production để chữa test.
7. **Kiểm tra điều kiện TTL:** `default_time_to_live` có tồn tại không? Mutation này có đặt TTL rõ? Có update lại cell trước khi nó expire?
8. **Khử nhiễu:** UUID/keyspace riêng, tránh parallel test dùng cùng key hoặc TRUNCATE lẫn nhau.
9. **Kết luận bằng evidence:** một test chờ lâu hơn rồi pass không chứng minh root cause chỉ là scheduling; nếu p99/network/server clock bất thường, phải xử lý.

**Điều không nên làm:** thêm `Thread.sleep(60000)` vào mọi test để “chắc chắn” và che lỗi update timestamp/TTL conflict.

## 23. Runbook C — Dữ liệu đã hết TTL nhưng dung lượng đĩa chưa giảm

**Tình huống:** `SELECT` không còn trả một số dữ liệu; dashboard disk utilization vẫn cao, SSTable size không giảm ngay. Đội vận hành nghi TTL “không chạy”.

1. **Phân biệt logical expiry với physical purge:** query row/cell còn sống không? `TTL(column)` còn countdown hay đã hết?
2. **Xem table-level metrics:** `nodetool tablestats`, tombstone/read latency, SSTable count và disk free.
3. **Xem compaction:** `nodetool compactionstats`, backlog, I/O headroom và compaction strategy.
4. **Kiểm tra retention policy:** `default_time_to_live`, TTL mutation, gc grace, repair/replica outage và khả năng dữ liệu cũ sống lại.
5. **Không chạy major compaction/repair mù quáng:** các thao tác này tiêu thụ disk/CPU/IO; cần SOP, capacity và rollback.
6. **Xác minh dung lượng:** so read-liveness, compaction progress, disk usage theo thời gian; không dùng một counter duy nhất kết luận “TTL hỏng”.
7. **Nếu áp lực disk khẩn cấp:** theo quy trình capacity/cleanup đã duyệt; đừng hạ gc grace tùy ý để ép purge và làm rủi ro dữ liệu.

**TTL giúp giảm dữ liệu sống**, nhưng không bảo đảm byte reclamation lập tức. Trong Cassandra, tombstone và compaction là một phần của sự an toàn phân tán.

## 24. Runbook D — Timestamp sai một ngày hoặc xuất hiện bản ghi “trùng”

**Tình huống:** Một collector gán event_day theo local date, một collector khác theo UTC. Có thể có hai row chứa cùng event_time nhưng nằm tại hai partition khác nhau, hoặc nhiều sự kiện cùng millisecond đè nhau.

1. **Xác minh đơn vị:** seconds/milliseconds/microseconds có bị nhầm khi chuyển dữ liệu không?
2. **Xác minh offset:** input có `Z` hoặc `+0700` không? Có `LocalDateTime` không zone bị hiểu ngầm?
3. **Xác minh precision:** event source có nanosecond nhưng Cassandra `timestamp` chính xác millisecond; nhiều sự kiện cùng ms có thể trùng full primary key.
4. **Xác minh key modeling:** nếu nhiều event thật xảy ra trong cùng ms, có cần `event_id` hoặc clustering component khác để phân biệt không?
5. **Xác minh writer timestamp:** `USING TIMESTAMP` có được client set? `WRITETIME` khác event_time là bình thường.
6. **Lập kế hoạch migration:** không tự ghi hai bản vào partition bất kỳ; xác định source of truth, dedup logic, backfill và consistency.
7. **Thêm tests:** mốc quanh UTC midnight, DST, pre-epoch và hai event cùng millisecond.
8. **Đo lại:** row counts theo ngày hợp lệ, độ lệch dữ liệu, driver timeout và compaction ảnh hưởng từ backfill.

Nếu logic phải lưu nhiều event cùng millisecond, **khóa `(device_id, event_day, event_time)` có thể không đủ**. Một bài test không cứu được sai lầm về uniqueness trong schema.

## 25. Công cụ quan sát cho timestamp/TTL

### 25.1. Những lệnh đọc trạng thái

~~~bash
# RF/DC/rack và các node đang lên/xuống.
nodetool status

# Pending/Active/Dropped ở các executor.
nodetool tpstats

# Backlog và tiến độ compaction.
nodetool compactionstats

# Thống kê dung lượng/table theo version.
nodetool tablestats temporal_lab.readings_by_device_day

# Histogram theo table nếu được version hỗ trợ.
nodetool tablehistograms temporal_lab readings_by_device_day

# Streaming trong bootstrap/repair/rebuild.
nodetool netstats
~~~

`nodetool` có cú pháp/output thay đổi theo Cassandra version; kiểm tra `nodetool help`. `netstats` chủ yếu giám sát SSTable streaming, **không** chứng minh native CQL traffic bằng 0. `status` hiển thị UP cũng không bảo đảm replica latency/clock đã chuẩn.

### 25.2. Chỉ số ứng dụng nên có

| Lớp | Chỉ số | Ý nghĩa |
|---|---|---|
| Java application | Query ID, operation, p95/p99, timeout | Vấn đề query vs infrastructure |
| Timestamp ingest | Số event late/future, bucket day theo policy | Phát hiện source clock/bucketing |
| TTL writes | Số mutation TTL, policy ID, TTL buckets | Phát hiện cấu hình retention bất thường |
| TTL reads | Số cell có TTL/không TTL, expected vs observed expiry | Theo dõi logic |
| Cassandra | Tombstone warnings, SSTables/read, compaction pending | Chi phí đọc/purge |
| Storage | Disk free/IOPS/latency, GC và CPU | Khả năng phục vụ/purge |
| Clock | NTP/chrony offset theo node, JVM/server time | Skew gần deadline |
| Test CI | Duration, flakes, container startup, retry count | Test infrastructure vs logic |

Không đưa raw `device_id`/`tenant_id`, timestamp mọi sự kiện hoặc token từng partition vào **metric labels**: cardinality có thể nổ. Dùng query-template ID và policy version có tập giá trị hữu hạn.

### 25.3. Log schema minh họa

~~~text
event=temporal_integration_failure
test_case=T10_partial_cell_expiry
query_template=read_device_day_by_timestamp
expected=partial_cell_expired
observed=row_exists_status_non_null
ttl_requested_seconds=12
elapsed_since_ack_ms=15320
server_clock_skew_ms=unknown
cassandra_release=4.1.x
driver_release=4.x
~~~

**Đây là format log đề xuất**, không phải output mặc định Cassandra. Ghi `unknown` nếu chưa đo server clock skew, không đoán từ elapsed client. Logs phải tuân thủ quyền/retention và không lộ giá trị thiết bị nhạy cảm.

## 26. Các ngộ nhận thường gặp

| Nhận định | Đúng hơn nên hiểu |
|---|---|
| “CQL timestamp lưu múi giờ của người dùng.” | Timestamp biểu diễn instant, không tự giữ zone ID nghiệp vụ |
| “LocalDate luôn là nửa đêm UTC.” | Là ngày lịch không timezone |
| “UTC+7 và UTC là cùng event_day.” | Một Instant có thể thuộc hai ngày khác nhau |
| “Bind Instant xong Cassandra sẽ tự tính event_day.” | Partition key event_day phải do ứng dụng ghi đúng |
| “LocalDateTime có thể chuyển thành Instant mà không cần zone.” | Phải có offset/ZoneId và chính sách DST |
| “Cassandra timestamp lưu nanosecond như Instant.” | CQL timestamp thông thường có precision millisecond |
| “WRITETIME cùng nghĩa event_time.” | WRITETIME là mutation/cell timestamp, thường microseconds |
| “Giá trị của WRITETIME là epoch milliseconds.” | Thông thường là microseconds |
| “TTL được tính bằng now - event_time.” | TTL dựa vào mutation/expiration semantics, không tự đọc cột event_time |
| “TTL=0 luôn có nghĩa xóa ngay.” | Phụ thuộc semantics/version/default TTL; không dùng mù |
| “Sau USING TTL 8, TTL(column) phải đúng 8.” | Thời gian trôi giữa write/read; dùng khoảng |
| “TTL của status hết, toàn row biến mất.” | Các cột khác không TTL vẫn sống |
| “TTL(column) null nghĩa chắc chắn đã expire.” | Có thể chưa có TTL hoặc cell vắng |
| “SELECT hết row nghĩa disk lập tức trống.” | Physical purge qua compaction và quy tắc tombstone |
| “Thread.sleep(TTL) đủ ổn định.” | Dễ flake; polling có deadline tốt hơn |
| “Mock Clock Java làm Cassandra expire ngay.” | Server clock độc lập |
| “Test một node chứng minh RF3 LOCAL_QUORUM.” | Cần multi-node fault tests |
| “Clock skew chỉ làm sai log.” | Có thể ảnh hưởng write ordering/TTL/consistency |
| “Paging đồng nghĩa snapshot thời gian.” | Các page có thể được đọc ở thời điểm khác nhau |
| “Tăng retry sẽ sửa test TTL.” | Có thể refresh TTL hoặc tạo mutation mới |
| “Mọi múi giờ chỉ khác nhau fixed offset.” | DST/tzdb rules thay đổi |
| “Ngày UTC cũ bị đổi chỉ cần ALTER TABLE.” | Thay partition key đòi backfill/reconciliation |
| “Hai sự kiện trong 1 ms sẽ có hai row riêng.” | Cùng full primary key có thể overwrite |
| “`nodetool netstats` trống nghĩa CQL idle.” | Netstats chủ yếu SSTable streaming |

## 27. Câu hỏi và đáp án

### Câu 1 — Event timestamp và bucket date

Một event có `event_time = 2026-11-21T17:30:00Z`. Ngày UTC và Asia/Ho_Chi_Minh lần lượt là gì?

**Đáp án:** UTC: `2026-11-21`; HCM (+07): `2026-11-22`. Nếu partition key gồm event_day, chúng chỉ đến hai partition khác nhau.

### Câu 2 — Instant với offset

`2026-11-21T10:30:00Z` và `2026-11-21T17:30:00+07:00` có cùng Instant không?

**Đáp án:** Có. Khác biểu diễn local/offset, cùng mốc thời gian tuyệt đối.

### Câu 3 — LocalDate

CQL `date` có lưu timezone hoặc giờ/phút không?

**Đáp án:** Không. Nó lưu ngày lịch; ứng dụng phải quy định timezone khi suy ngày từ Instant.

### Câu 4 — Mili giây

Java lưu `2026-11-21T10:30:00.123456789Z` vào CQL timestamp. Có thể assert chính xác nanosecond sau round-trip không?

**Đáp án:** Không. CQL timestamp thông thường có precision milliseconds; cần chính sách truncate/round và fixture milli.

### Câu 5 — WRITETIME

`WRITETIME(reading_value)` trả về 16 chữ số trong khi `event_time` là Instant. Có nên coi hai giá trị luôn giống nhau không?

**Đáp án:** Không. WRITETIME là microsecond mutation timestamp dùng reconciliation; event_time là dữ liệu nghiệp vụ. Khác đơn vị và semantics.

### Câu 6 — TTL của sự kiện cũ

Sự kiện xảy ra một tháng trước nhưng hôm nay mới INSERT với `USING TTL 60`. Có tự hết hạn ngay vì event_time cũ không?

**Đáp án:** Không. TTL thông thường tính từ thời điểm mutation theo cơ chế server, không tự trừ từ trường event_time.

### Câu 7 — TTL(column) trả null

`TTL(status) == null`. Có chắc status vừa hết hạn không?

**Đáp án:** Không. Cell có thể không gắn TTL, chưa có giá trị, đã xóa hoặc đã hết hạn. Đọc giá trị và dựa trên fixture/lịch sử ghi.

### Câu 8 — Partial TTL

Row có reading_value không TTL, status TTL 8 giây. Sau 10 giây, `Row` có chắc bằng null không?

**Đáp án:** Không. Row có thể còn vì reading_value sống, còn status đã null.

### Câu 9 — Full TTL

INSERT một row mà tất cả giá trị sống đều có TTL. Sau TTL và khi không còn live cell, query theo full PK có thể trả gì?

**Đáp án:** Có thể trả không có row sống; nhưng không có nghĩa SSTable đã được xóa vật lý ngay.

### Câu 10 — Polling

Vì sao `Thread.sleep(3000)` với TTL 3 giây dễ flake?

**Đáp án:** Biên server/client clock, network, scheduling và start time không trùng tuyệt đối. Dùng polling có deadline và đủ margin.

### Câu 11 — Fake Clock

Đổi `Clock.fixed` trong Java tiến một ngày có khiến Cassandra TTL 600 giây hết ngay không?

**Đáp án:** Không. Server clock/expiration độc lập với injected Java Clock.

### Câu 12 — DST gap

`America/New_York` tại `2026-03-08 02:30` có thể biểu diễn một Instant duy nhất không?

**Đáp án:** Thời điểm local này nằm trong DST gap theo tzdb phổ biến; cần policy xử lý input không tồn tại hoặc yêu cầu offset rõ.

### Câu 13 — DST overlap

`America/New_York` tại `2026-11-01 01:30` có vấn đề gì?

**Đáp án:** Có thể tương ứng hai UTC offsets/Instants. Cần chọn/ghi offset rõ, không âm thầm lấy một giá trị mặc định nếu nghiệp vụ yêu cầu chính xác.

### Câu 14 — Testcontainers RF=1

Một test TTL pass trên một Cassandra container RF=1. Có chứng minh behavior với RF=3, replica down và LOCAL_QUORUM không?

**Đáp án:** Không. Cần integration suite nhiều node/topology đúng với failure scenarios.

### Câu 15 — Disk

Sau expiration, SELECT không còn dữ liệu nhưng disk free không tăng. Có đủ chứng minh TTL không hoạt động không?

**Đáp án:** Không. Logical expiry khác physical purge; compaction/tombstone và điều kiện an toàn điều khiển việc reclaim bytes.

### Câu 16 — TTL retry

Một INSERT dùng TTL 600 được retry sau 30 giây. Expiry deadline có chắc giữ nguyên không?

**Đáp án:** Không. Retry có thể tạo mutation/timestamp/TTL mới theo semantics; cần operation ID và retention policy tuyệt đối nếu nghiệp vụ yêu cầu.

### Câu 17 — Cùng millisecond

Hai event có Instant khác nhau 100 nanoseconds nhưng cùng millisecond và cùng device/day. Nếu `event_time` là clustering key duy nhất, có thể ghi đè nhau không?

**Đáp án:** Có thể. CQL timestamp có precision ms; nếu mapping làm hai khóa đầy đủ trùng nhau thì mutation cùng row, cần event_id hoặc key design khác.

### Câu 18 — Clock skew

Có nên dịch clock một replica production tới tương lai để test TTL nhanh không?

**Đáp án:** Không. Phải dùng cluster cô lập và fault injection an toàn; clock production là tài nguyên nền tảng của hệ phân tán.

### Câu 19 — Wrong partition

Query đúng event_time nhưng sai event_day trả 0 row. Có thể kết luận đã mất bản sao dữ liệu trên mọi replica không?

**Đáp án:** Không. Truy vấn đang đi đến partition/token khác. Đối chiếu bucket policy và key values trước.

### Câu 20 — Retention policy

Business cần hết hạn 7 ngày sau event_time; server TTL lại bắt đầu từ lúc ingest. Nên làm gì?

**Đáp án:** Định nghĩa `expires_at`/policy, tính TTL còn lại tại ingest, xử lý events đã quá hạn và kiểm thử late arrival/retries; không mặc định TTL=7 ngày từ ingest là tương đương.

## 28. Checklist trước khi merge integration tests

### 28.1. Time types và timezone

~~~text
[ ] CQL timestamp ↔ Java Instant được kiểm tra precision milli.
[ ] CQL date ↔ Java LocalDate, không tự gắn timezone.
[ ] Bucket event_day có ZoneId policy dùng chung writer/reader.
[ ] Test quanh UTC midnight và timezone nghiệp vụ.
[ ] Test offset rõ trong input và round-trip Instant.
[ ] Test DST gap/overlap khi business dùng DST zone.
[ ] Không phụ thuộc ZoneId.systemDefault của host CI.
[ ] Phân biệt event_time và WRITETIME microseconds.
[ ] Test nhiều event trong cùng millisecond nếu có thể xảy ra.
~~~

### 28.2. TTL/expiration

~~~text
[ ] TTL là giây, không nhầm với milliseconds.
[ ] Có test trạng thái trước và sau expiry.
[ ] Dùng Awaitility polling/deadline, không sleep đúng biên.
[ ] Test per-cell TTL và full-row TTL riêng.
[ ] TTL(column) null không bị hiểu là expired chắc chắn.
[ ] Default table TTL được test trên table cô lập nếu cần.
[ ] Fake Clock chỉ cho Java domain, không giả là server time.
[ ] Test late events và absolute expiry policy nếu có.
[ ] Retry/TTL/LWT được xét cùng operation identity.
[ ] Không assert disk physical deletion ngay sau expiry.
[ ] Không ép compaction/repair/clock shift trên production.
~~~

### 28.3. Cassandra/Java/CI

~~~text
[ ] Testcontainers, Java Driver, JDK và Cassandra versions pinned.
[ ] Docker runtime sẵn; test không skip giả khi thiếu môi trường.
[ ] Session close đúng vòng đời; mỗi test có UUID riêng.
[ ] CL/RF cho test một node được ghi rõ là giới hạn phạm vi.
[ ] Multi-node replication/time skew tests nằm ở suite riêng.
[ ] Không có test TRUNCATE/ALTER bảng chung khi chạy parallel.
[ ] Metrics có timeout, p99, compaction, disk, clock offset.
[ ] Logs không chứa PII, raw partition IDs hoặc secrets.
[ ] Có runbook wrong bucket, TTL flake, physical purge, precision.
[ ] Không chạy Content QA STEP 6 trong bước viết bài.
~~~

## 29. Tổng kết

Để kiểm thử **múi giờ, timestamp, TTL và dữ liệu hết hạn** đúng trong Java–Cassandra:

1. **Dùng `Instant` cho CQL timestamp** và `LocalDate` cho CQL date; không coi LocalDateTime không zone là một mốc tuyệt đối.
2. **Quy ước timezone để tính partition bucket ngày**; một Instant có thể thuộc ngày UTC và ngày địa phương khác nhau, kéo theo token/replica khác.
3. **CQL timestamp có precision milliseconds**, còn `WRITETIME` của cell thường tính bằng microseconds; hai trường phục vụ mục đích khác nhau.
4. **TTL là chính sách hết hạn của cell/row liveness**, không tự tính từ cột event_time và không có nghĩa xóa SSTable tức thời.
5. **`TTL(column)` không phải bằng chứng duy nhất** để phân biệt cell không có TTL, chưa có hoặc đã expire.
6. **Kiểm thử expiration bằng polling và deadline**, có assertion trước/sau; tránh sleep đúng bằng TTL và test song song cùng primary key.
7. **Mock Java Clock không mock Cassandra server clock**; kiểm tra business time bằng unit tests, expiration thật bằng cluster cô lập.
8. **Cần test DST, timestamp precision, late events, retries và nhiều mutation** nếu nghiệp vụ nhạy với thời gian.
9. **Single-node Testcontainers không chứng minh RF3/quorum/clock-skew**; kiểm thử correctness phân tán cần môi trường multi-node có kiểm soát.
10. **Quan sát logical expiry và physical purge tách biệt**, gắn với compaction/tombstone, RF/CL, disk headroom và thời gian đồng bộ replica.

Câu hỏi quan trọng nhất của một integration test thời gian không phải “ngủ bao nhiêu giây trước khi assert?”, mà là **“Tôi đang đo instant nào, ngày partition được tính theo timezone nào, TTL áp dụng lên cell nào và theo clock nào, và assertion đang kiểm tra dữ liệu sống hay dung lượng vật lý sau compaction?”**. Khi cả bốn điều này được mô tả và kiểm chứng rõ, test mới có thể giúp phát hiện lỗi thật thay vì tạo flake trong CI.
