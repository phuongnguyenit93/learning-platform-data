# Xóa cột, xóa hàng, giá trị null và sự hình thành tombstone

Trong **Apache Cassandra**, câu lệnh `DELETE` không đơn giản là tìm một hàng rồi xóa ngay mọi byte khỏi ổ đĩa. Cassandra là cơ sở dữ liệu phân tán, dùng nhiều replica và các tệp SSTable bất biến. Để một thao tác xóa có thể được hòa giải với các bản sao dữ liệu cũ, hệ thống ghi **tombstone** — dấu xóa có timestamp — và chỉ thu dọn dữ liệu vật lý sau khi đáp ứng các điều kiện phù hợp.

Điểm dễ gây bất ngờ là **gán `null` cho một cột cũng có thể tạo tombstone**, trong khi **không đưa cột vào câu lệnh ghi** hoặc gửi tham số **UNSET** thường có nghĩa *không thay đổi cột đó*. Xóa **một cột**, xóa **một hàng**, xóa **cả partition**, và để một giá trị **hết TTL** có phạm vi ảnh hưởng khác nhau, mặc dù kết quả `SELECT` có thể đều hiển thị `null` hoặc không còn hàng.

Bài học thuộc chương **TTL và tombstone** của module **SPRING_DATA_CASSANDRA**. Bạn sẽ thực hành CQL, Java Driver, `CqlTemplate`, repository và entity mapping; kết nối các thao tác xóa với thiết kế partition key, write timestamp, consistency, paging, tombstone scan và hiệu năng của mô hình dữ liệu phân tán.

Sau bài, bạn cần phân biệt được:

1. Cột chưa từng được ghi, cột được ghi `null`, cột bị `DELETE`, và cột hết hạn TTL.
2. Tombstone của **cell**, **row**, **partition** và các khoảng clustering (range tombstone).
3. **CQL `NULL` và prepared-statement `UNSET`** trong các lần ghi một phần.
4. Vì sao đọc không thấy dữ liệu không có nghĩa tombstone đã biến mất; `gc_grace_seconds`, repair và compaction tác động ra sao.
5. Cách kiểm thử đúng phạm vi xóa và tránh tạo tombstone không cần thiết trong Spring Data Cassandra.

## 1. Bối cảnh: bảng sự kiện theo thiết bị và ngày

Giả sử một hệ thống IoT cần hiển thị sự kiện của một thiết bị theo ngày và xóa những thông tin nhạy cảm khi hết thời hạn lưu giữ. Đường đọc là: “Lấy 50 sự kiện mới nhất của thiết bị D trong ngày N”.

~~~sql
CREATE TABLE device_events_by_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    detail text,
    source text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

| Cột | Vai trò trong schema | Ý nghĩa |
|---|---|---|
| `tenant_id` | Partition key, thành phần 1 | Cô lập dữ liệu theo tenant |
| `device_id` | Partition key, thành phần 2 | Chọn thiết bị |
| `event_day` | Partition key, thành phần 3 | Time bucket giới hạn partition |
| `occurred_at` | Clustering column 1, DESC | Thứ tự sự kiện mới trước |
| `event_id` | Clustering column 2, ASC | Phân biệt sự kiện cùng thời gian |
| `event_type` | Cột thường | Loại sự kiện, ví dụ `SCAN` |
| `detail` | Cột thường | Nội dung có thể cần xóa trước các trường khác |
| `source` | Cột thường | Nguồn tạo sự kiện |

**Phân biệt hai bộ khóa:**

~~~text
Partition key:
    (tenant_id, device_id, event_day)

Clustering key:
    (occurred_at, event_id)

Primary key đầy đủ của MỘT hàng:
    (tenant_id, device_id, event_day, occurred_at, event_id)
~~~

Đường đọc thông thường:

~~~sql
SELECT occurred_at, event_id, event_type, detail, source
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Truy vấn xác định **một partition**, rồi đọc tối đa 50 hàng theo clustering order. Khi xóa, **số lượng thành phần khóa trong `WHERE` quyết định phạm vi xóa**, nên phải hiểu schema trước khi viết DAO.

## 2. Tombstone là gì và tại sao Cassandra cần nó?

Giả sử cùng một hàng có mặt trên ba replica. Trong lúc node C tạm ngừng hoạt động, client yêu cầu xóa cột `detail` trên các replica có thể truy cập.

Nếu node A chỉ “bỏ hẳn” `detail`, khi C trở lại và phản hồi với giá trị `detail` cũ, hệ thống sẽ khó biết liệu đó là dữ liệu cần giữ hay bản sao đã bị xóa. **Tombstone** là dấu xóa có metadata thời gian để replica có thể hòa giải dữ liệu:

~~~text
Trước DELETE:

    Replica A: detail = "old"
    Replica B: detail = "old"
    Replica C: detail = "old"  (đang offline)

DELETE detail với write timestamp T=200:

    Replica A: tombstone(detail, T=200)
    Replica B: tombstone(detail, T=200)
    Replica C: detail = "old"  (chưa nhận delete)

C hội nhập lại / có repair phù hợp:

    Tombstone(T=200) thắng giá trị cũ(T=100).
    Giá trị đã xóa không được xem là dữ liệu hiện tại.
~~~

Tombstone **không phải một bản sao của giá trị đã xóa**. Nó là metadata thể hiện một lệnh xóa hoặc một trạng thái hết hạn, được lưu/di chuyển trong quá trình đọc, ghi và compaction theo cơ chế của Cassandra.

Ba điều hệ quả:

- **Logic xóa** và **thu hồi dung lượng vật lý** là hai thời điểm khác nhau.
- Các replica có thể tạm có nội dung khác nhau; mức nhất quán và repair ảnh hưởng khả năng đọc thấy dữ liệu đúng.
- Nhiều tombstone phải được quét trong đường đọc có thể làm tăng CPU, I/O, độ trễ và cảnh báo hoặc lỗi từ Cassandra.

### 2.1. Phân biệt write timestamp và cột timestamp

Cột `occurred_at timestamp` lưu **thời điểm nghiệp vụ** với độ chính xác mili giây; nó đồng thời là clustering key trong bảng ví dụ. Một tombstone, giống các mutation khác, có **write timestamp** dùng để hòa giải phiên bản, thường tính bằng micro giây kể từ Unix epoch.

~~~text
occurred_at = 2026-11-25T09:00:00Z
    → thời điểm sự kiện, giá trị CQL

write timestamp của DELETE = 1795597200123000
    → metadata của mutation, đơn vị micro giây
~~~

Một lệnh xóa gửi hôm nay có thể xóa dữ liệu sự kiện xảy ra từ năm trước. Cassandra không so sánh `occurred_at` để quyết định delete nào thắng; nó dùng **timestamp metadata** và quy tắc hòa giải, trong đó tombstone thắng live cell khi có cùng timestamp theo những trường hợp tương ứng.

## 3. Xóa một cột: DELETE tên_cột

Giả sử sự kiện đã ghi với đầy đủ khóa và `detail = 'GPS: ...'`. Nghiệp vụ chỉ muốn **loại bỏ chi tiết nhạy cảm** nhưng vẫn giữ event ID, loại sự kiện và nguồn.

~~~sql
DELETE detail
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Ở đây:

1. `DELETE detail` chỉ định **cột thường** cần xóa.
2. `WHERE` chứa **đầy đủ primary key của một hàng**.
3. Cassandra ghi metadata xóa cho `detail`, không mặc định xóa `event_type` hay `source`.
4. Khi đọc lại, `detail` thường xuất hiện là `null` nếu các cột còn lại giữ hàng tồn tại.

Ví dụ trước và sau:

| Cột | Trước khi xóa | Sau `DELETE detail` |
|---|---|---|
| `event_type` | `SCAN` | `SCAN` |
| `detail` | `GPS: 10.77,106.70` | `null` khi đọc |
| `source` | `gateway-1` | `gateway-1` |
| Primary key | Giữ nguyên | Giữ nguyên |

**Không gán `null` cho các cột primary key**. Khóa partition và clustering là định danh/đường truy cập, không phải field tùy chọn được xóa riêng như `detail`.

### 3.1. Đọc lại bằng CQL

~~~sql
SELECT occurred_at, event_id, event_type, detail, source
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

`detail = null` trong kết quả **không chứng minh** cột có tombstone: một cột chưa từng được ghi cũng có thể đọc là `null`. Muốn xác minh thao tác xóa, cần biết dữ liệu trước đó, câu lệnh đã chạy và điều kiện phiên bản; không chỉ xem một ảnh chụp trạng thái hiện tại.

### 3.2. Xóa nhiều cột thường

Khi cần loại bỏ `detail` và `source` nhưng giữ `event_type`:

~~~sql
DELETE detail, source
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Đây vẫn là **xóa chọn lọc các cột**, không phải xóa toàn bộ hàng. Tùy schema, cột static và các kiểu collection có các quy tắc riêng; ví dụ minh họa dùng những cột scalar thông thường để làm rõ phạm vi.

## 4. Xóa cả hàng: DELETE FROM ... WHERE đầy đủ primary key

Để loại bỏ **một event cụ thể**, bỏ danh sách cột sau từ khóa `DELETE` và giữ **đầy đủ primary key** trong `WHERE`:

~~~sql
DELETE FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Kết quả logic: hàng có chính xác năm thành phần khóa đó **không còn hiển thị** sau khi delete được áp dụng và việc đọc đáp ứng consistency phù hợp. Cassandra thường biểu diễn thao tác bằng **row tombstone**, che các giá trị cột của hàng ở cùng khóa có write timestamp không mới hơn delete.

Điều khác với `DELETE detail`:

| Thao tác | Phạm vi | `event_type` có còn? | `detail` có còn? |
|---|---|---|---|
| `DELETE detail FROM ...` | Một cell/cột chọn lọc | Có thể còn | Bị xóa |
| `DELETE detail, source FROM ...` | Hai cột chọn lọc | Có thể còn | Bị xóa |
| `DELETE FROM ...` với đầy đủ khóa hàng | **Cả hàng** | Không còn hàng để đọc | Không còn hàng để đọc |

**Thận trọng với `repository.deleteById(key)`:** nếu `key` là composite primary key, nó phải chứa đủ thành phần phân vùng và clustering; một `eventId` đơn lẻ không xác định được hàng trong bảng này.

### 4.1. Delete một hàng không phải một phép đếm số hàng kiểu SQL

`DELETE` vô điều kiện có thể được thực thi ngay cả khi khóa không có dữ liệu hiện hữu. Phản hồi thành công của câu CQL **không phải affected-row-count** đáng tin cậy chứng minh “đã xóa đúng một hàng tồn tại”.

Nếu hợp đồng yêu cầu “chỉ xóa khi hàng đang tồn tại”, Cassandra hỗ trợ conditional delete trong những trường hợp phù hợp:

~~~sql
DELETE FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?
IF EXISTS;
~~~

`IF EXISTS` dùng **lightweight transaction (LWT)**, có chi phí cao hơn. Ứng dụng phải kiểm tra kết quả `[applied]`, phân biệt điều kiện không thỏa với lỗi/timeout. Một `SELECT` trước `DELETE` vô điều kiện **không thay thế** điều kiện nguyên tử, vì writer khác có thể thay đổi hàng giữa hai lệnh.

## 5. Xóa cả partition: thiếu clustering key có thể làm mất nhiều hàng

Với bảng `device_events_by_day`, câu sau chỉ định **đủ ba thành phần partition key** nhưng **không có clustering columns**:

~~~sql
-- CẢNH BÁO: XÓA TẤT CẢ SỰ KIỆN CỦA THIẾT BỊ TRONG NGÀY.
DELETE FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?;
~~~

Đây là một **partition delete**: mọi hàng trong partition được đánh dấu xóa theo phạm vi tương ứng. Cassandra có thể dùng **partition tombstone** để biểu diễn thao tác; nó khác một chuỗi câu lệnh xóa từng event ID ở mức biểu diễn và chi phí.

~~~text
Partition (tenant=T1, device=D1, day=2026-11-25)

  09:30 — event C
  09:20 — event B
  09:10 — event A

DELETE FROM ... WHERE tenant_id=T1 AND device_id=D1 AND day=2026-11-25

  => Cả A, B, C thuộc phạm vi bị xóa.
     Các partition ngày khác vẫn là đường dữ liệu khác.
~~~

**Đừng đặt tên DAO mơ hồ** như `deleteEvents(deviceId)` nếu thực tế đó là delete cả một partition. Nên phân biệt `deleteOneEvent(fullKey)` với `deleteDeviceDay(tenant, device, day)`, validate quyền và phạm vi, có policy bảo vệ các thao tác xóa quy mô lớn.

### 5.1. Range tombstone là gì?

Khi xóa theo **một khoảng clustering** được Cassandra/CQL và phiên bản cụ thể hỗ trợ, storage engine có thể biểu diễn phạm vi bị xóa bằng **range tombstone** thay vì ghi tombstone riêng cho từng cell. Nó liên quan tới thứ tự clustering và các giới hạn CQL; không được mặc định mọi `WHERE occurred_at < ?` đều là câu `DELETE` hợp lệ trên mọi version/schema.

Các phạm vi quan trọng cần phân biệt về mặt khái niệm:

| Loại | Phạm vi logic thường gặp |
|---|---|
| Cell tombstone | Một cột thường trong một hàng |
| Row tombstone | Một hàng có đầy đủ primary key |
| Partition tombstone | Mọi hàng thuộc một partition |
| Range tombstone | Một khoảng hàng theo clustering, khi thao tác được hỗ trợ |

Nội bộ storage có thể có những marker/cell structures khác nhau tùy phiên bản và loại dữ liệu. Để học thiết kế API, hãy tập trung vào **phạm vi dữ liệu bị che/xóa** thay vì suy đoán một tombstone luôn tương ứng với một byte hay một đối tượng vật lý cố định.

## 6. CQL NULL khác với cột chưa từng được ghi

Xét một hàng hiện có:

~~~text
event_type = SCAN
detail     = "Gate opened"
source     = gateway-1
~~~

Ba thao tác sau **không tương đương**:

~~~sql
-- A: Chỉ cập nhật event_type, KHÔNG đề cập detail.
UPDATE device_events_by_day
SET event_type = 'ALERT'
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;

-- B: Gán NULL cho detail.
UPDATE device_events_by_day
SET detail = null
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;

-- C: Xóa tường minh detail.
DELETE detail FROM device_events_by_day
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

So sánh:

| Trường hợp | `detail` sau khi cập nhật | Có mutation xóa `detail`? |
|---|---|---|
| A — không nhắc đến `detail` | **Giữ giá trị cũ** | **Không** vì lệnh không chạm tới cột đó |
| B — `detail = null` | Trở thành `null` khi đọc | **Có**, gán null cho cột thường tạo tombstone |
| C — `DELETE detail` | Trở thành `null` khi đọc | **Có**, xóa tường minh |

**Lưu ý về upsert:** `UPDATE` và `INSERT` thông thường của Cassandra không yêu cầu hàng tồn tại trước, vì chúng có ngữ nghĩa upsert. Bỏ qua một cột trong lệnh ghi **không** có nghĩa xóa nó. Gán null **có** ý nghĩa khác trong mutation, kể cả khi kết quả `SELECT` đều hiển thị `null`.

### 6.1. INSERT thiếu cột và INSERT cột = NULL

~~~sql
-- Chỉ ghi event_type, không đụng detail:
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day, occurred_at, event_id, event_type
) VALUES (?, ?, ?, ?, ?, ?);

-- Ghi cột detail với NULL:
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day, occurred_at, event_id,
    event_type, detail
) VALUES (?, ?, ?, ?, ?, ?, null);
~~~

Vì `INSERT` của Cassandra cũng là upsert, nếu khóa hàng đã tồn tại:

- Lệnh thứ nhất thường **giữ nguyên cột `detail` cũ** vì không ghi lên nó.
- Lệnh thứ hai biểu thị **xóa giá trị `detail`** ở timestamp của mutation (tạo tombstone).

Nếu hàng chưa tồn tại, cả hai trường hợp đều có thể khiến `detail` đọc là `null`; điều đó **không chứng minh** tác động storage giống nhau. Không viết quy tắc nghiệp vụ dựa trên việc “thấy null thì dữ liệu chưa được ghi lần nào”.

### 6.2. NULL không dùng được cho thành phần primary key

~~~sql
-- Sai: một thành phần của partition key không thể NULL.
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day, occurred_at, event_id, event_type
) VALUES (null, ?, ?, ?, ?, 'SCAN');
~~~

Primary key dùng để định vị hàng và phải được cung cấp hợp lệ. Không có cơ chế “xóa cột khóa bằng null” để biến một event sang khóa khác. Muốn đổi `event_day` hoặc `occurred_at`, đó là **đổi primary key** và cần xử lý ghi sang hàng mới, xóa hàng cũ cùng consistency/idempotency phù hợp.

## 7. Prepared statement: NULL và UNSET là hai ý định khác nhau

Java Driver cho phép một biến trong prepared statement được:

- **Gán giá trị cụ thể**: ghi một giá trị mới.
- **Gán NULL**: yêu cầu Cassandra xóa giá trị cột thường ở vị trí đó.
- **Đánh dấu UNSET**: bỏ qua biến đó trong mutation; không tạo tombstone cho cột bị UNSET.

`UNSET` ở đây là **trạng thái của bind marker phía driver**, không phải một giá trị text `"UNSET"` được lưu vào Cassandra và không phải lệnh CQL `SET col = UNSET` có thể viết tùy tiện.

Ví dụ với cùng khóa:

~~~sql
UPDATE device_events_by_day
SET detail = ?, event_type = ?
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Java Driver 4:

~~~java
package example.telemetry;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatementBuilder;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class EventDetailWriter {
    private final CqlSession session;
    private final PreparedStatement update;

    public EventDetailWriter(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
                "UPDATE device_events_by_day " +
                "SET detail = ?, event_type = ? " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND event_day = ? AND occurred_at = ? AND event_id = ?");
    }

    private BoundStatementBuilder base(
            UUID tenantId, UUID deviceId, LocalDate day,
            Instant occurredAt, UUID eventId) {
        return update.boundStatementBuilder()
                .setString(1, "SCAN")
                .setUuid(2, tenantId)
                .setUuid(3, deviceId)
                .setLocalDate(4, day)
                .setInstant(5, occurredAt)
                .setUuid(6, eventId);
    }

    public void keepExistingDetail(
            UUID tenantId, UUID deviceId, LocalDate day,
            Instant occurredAt, UUID eventId) {

        BoundStatement request = base(
                tenantId, deviceId, day, occurredAt, eventId)
                .unset(0)
                .build();

        session.execute(request);
    }

    public void removeDetail(
            UUID tenantId, UUID deviceId, LocalDate day,
            Instant occurredAt, UUID eventId) {

        BoundStatement request = base(
                tenantId, deviceId, day, occurredAt, eventId)
                .setToNull(0)
                .build();

        session.execute(request);
    }
}
~~~

Các chỉ số `0..6` ở đây là **vị trí bind marker, bắt đầu từ 0**, theo thứ tự dấu `?` trong CQL. Chúng **không phải** thứ tự `ordinal` của primary key trong entity. Cả hai phương thức đều ghi `event_type='SCAN'` để làm rõ mutation có nội dung; chỉ **`detail`** được xử lý khác nhau:

- `unset(0)`: không cập nhật `detail` ở request này.
- `setToNull(0)`: gửi ý định xóa `detail`, tạo tombstone.

`BoundStatementBuilder` được dùng để minh họa API setter dạng mutable trong driver; với `BoundStatement` bất biến, cần giữ lại object trả về của các setter. Hãy đối chiếu phiên bản Java Driver trong dự án nếu API có thay đổi.

### 7.1. Vì sao UNSET rất hữu ích với PATCH?

Giả sử API nhận payload cập nhật một phần:

~~~json
{
  "eventType": "ALERT"
}
~~~

`detail` **không có trong request** khác với:

~~~json
{
  "eventType": "ALERT",
  "detail": null
}
~~~

Một contract có chủ đích có thể quy định:

| Input API | Ý nghĩa | Bind/statement |
|---|---|---|
| `detail` không xuất hiện | Giữ giá trị hiện có | **UNSET** hoặc bỏ cột khỏi CQL |
| `detail: null` | Xóa chi tiết | **NULL** hoặc `DELETE detail` |
| `detail: "new value"` | Ghi giá trị mới | Bind string cụ thể |

Để thực hiện đúng, DTO/JSON parser phải **phân biệt field vắng mặt với field null**. Dùng duy nhất một `String detail` mặc định `null` sau deserialization có thể làm mất thông tin này. Có thể dùng một wrapper ba trạng thái, update command riêng, hoặc kiểm tra sự hiện diện field theo cơ chế JSON đã được chọn.

Đừng áp dụng quy tắc này một cách âm thầm cho mọi API. PATCH của từng sản phẩm phải định nghĩa rõ `null` có nghĩa “xóa”, “không thay đổi” hay “dữ liệu không hợp lệ”, rồi ánh xạ nhất quán.

## 8. Spring Data mapping và rủi ro ghi null ngoài ý muốn

Một entity Spring Data Cassandra cho bảng ví dụ gồm khóa ghép và các cột thường:

~~~java
package example.telemetry;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class DeviceEventKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "device_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID eventId;

    public DeviceEventKey() {}

    public DeviceEventKey(UUID tenantId, UUID deviceId,
            LocalDate eventDay, Instant occurredAt, UUID eventId) {
        this.tenantId = tenantId;
        this.deviceId = deviceId;
        this.eventDay = eventDay;
        this.occurredAt = occurredAt;
        this.eventId = eventId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }
    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }
    public Instant getOccurredAt() { return occurredAt; }
    public void setOccurredAt(Instant value) { occurredAt = value; }
    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof DeviceEventKey)) return false;
        DeviceEventKey other = (DeviceEventKey) candidate;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(deviceId, other.deviceId)
                && Objects.equals(eventDay, other.eventDay)
                && Objects.equals(occurredAt, other.occurredAt)
                && Objects.equals(eventId, other.eventId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, deviceId, eventDay,
                occurredAt, eventId);
    }
}
~~~

Entity:

~~~java
package example.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("device_events_by_day")
public class DeviceEvent {

    @PrimaryKey
    private DeviceEventKey id;

    @Column("event_type")
    private String eventType;

    @Column("detail")
    private String detail;

    @Column("source")
    private String source;

    public DeviceEvent() {}

    public DeviceEvent(DeviceEventKey id, String eventType,
                       String detail, String source) {
        this.id = id;
        this.eventType = eventType;
        this.detail = detail;
        this.source = source;
    }

    public DeviceEventKey getId() { return id; }
    public void setId(DeviceEventKey value) { id = value; }
    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }
    public String getDetail() { return detail; }
    public void setDetail(String value) { detail = value; }
    public String getSource() { return source; }
    public void setSource(String value) { source = value; }
}
~~~

Repository:

~~~java
package example.telemetry;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface DeviceEventRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {
}
~~~

`repository.findById(fullKey)` đọc một event theo đủ khóa; `repository.deleteById(fullKey)` diễn đạt ý định xóa hàng. Các class public trên cần được đặt trong **file Java riêng**, cùng package và cấu hình keyspace/entity scan phù hợp.

### 8.1. Không suy luận semantics null của save()

Ví dụ:

~~~java
DeviceEvent event = new DeviceEvent(
        fullKey, "SCAN", null, "gateway-1");

repository.save(event);
~~~

Không nên suy luận **chỉ từ code này** rằng `detail=null` chắc chắn:

- Đã bị gửi thành CQL `NULL` và tạo tombstone; **hoặc**
- Đã bị bỏ qua hoàn toàn như `UNSET`.

Hành vi thực tế phụ thuộc phiên bản Spring Data Cassandra, kiểu entity, `InsertOptions`/`UpdateOptions`, cách `save` ánh xạ các giá trị null và custom converters. Đặc biệt khi đang làm **PATCH**, một entity được dựng từ DTO thiếu field có thể gây mất dữ liệu nếu ghi rộng ngoài ý định.

**Quy tắc an toàn:** với một update chọn lọc, thể hiện chính xác cột cần thay đổi bằng `CqlTemplate`, `CassandraTemplate` với API/update options đã được kiểm chứng, hoặc `CqlSession` prepared statement. Kiểm tra CQL thực sự gửi và đọc lại dữ liệu trong integration test; không coi `save` như “merge mọi field mà client đã đề cập” nếu chưa chứng minh được hành vi.

### 8.2. CqlTemplate cho xóa cột và xóa hàng

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.CqlOperations;

public final class EventDeletionDao {
    private final CqlOperations cql;

    public EventDeletionDao(CqlOperations cql) {
        this.cql = cql;
    }

    public boolean deleteDetail(
            UUID tenantId, UUID deviceId, LocalDate day,
            Instant occurredAt, UUID eventId) {

        return cql.execute(
                "DELETE detail FROM device_events_by_day " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND event_day = ? AND occurred_at = ? AND event_id = ?",
                tenantId, deviceId, day, occurredAt, eventId);
    }

    public boolean deleteOneEvent(
            UUID tenantId, UUID deviceId, LocalDate day,
            Instant occurredAt, UUID eventId) {

        return cql.execute(
                "DELETE FROM device_events_by_day " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND event_day = ? AND occurred_at = ? AND event_id = ?",
                tenantId, deviceId, day, occurredAt, eventId);
    }
}
~~~

**Không diễn giải `boolean` trả về bởi `cql.execute` như số hàng đã xóa.** Với mutation vô điều kiện, thành công không có nghĩa hàng tồn tại trước đó. Nếu cần kiểm tra tồn tại và delete nguyên tử, cân nhắc LWT `IF EXISTS` với chi phí tương ứng.

Khi xóa cả partition, nên có một API riêng, xác thực chặt và cảnh báo rõ ràng, thay vì lặng lẽ bỏ `occurredAt/eventId` khỏi một method trên.

## 9. TTL: hết hạn cũng tạo tombstone

**TTL (Time To Live)** quy định thời hạn sống của dữ liệu được ghi. Khi TTL hết hạn, giá trị không còn được xem là live; cơ chế storage cần ghi nhận **thông tin hết hạn để hòa giải dữ liệu**, gắn với tombstone và quá trình dọn dẹp sau đó.

Ví dụ đặt TTL 3.600 giây cho `detail`:

~~~sql
UPDATE device_events_by_day
USING TTL 3600
SET detail = 'temporary location'
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Ở đây:

- TTL của giá trị `detail` là **3.600 giây** kể từ lúc mutation được áp dụng theo quy tắc TTL của Cassandra.
- Hết TTL, `detail` không còn được đọc như một giá trị live.
- `event_type` và `source` **không tự hết hạn** chỉ vì `detail` được cập nhật với TTL.
- Dữ liệu vật lý và metadata hết hạn có thể vẫn hiện diện cho tới các lần compaction/dọn dẹp an toàn.

### 9.1. INSERT với TTL

~~~sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day, occurred_at, event_id,
    event_type, detail, source
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
USING TTL 86400;
~~~

Trong ví dụ, các **giá trị không thuộc khóa** được ghi trong mutation có TTL một ngày theo semantics của Cassandra; primary key không trở thành một loại “cột nullable” hay “cột có thể cập nhật TTL tùy ý” giống dữ liệu thường.

Nếu muốn chỉ `detail` hết hạn sau một giờ nhưng giữ `event_type` lâu dài, hãy tách mutation như ví dụ `UPDATE ... USING TTL 3600 SET detail=...`; không đặt TTL 86400 cho mọi field rồi kỳ vọng chỉ một field hết hạn.

### 9.2. TTL có thể được cấu hình ở cấp bảng

~~~sql
CREATE TABLE temporary_device_events (
    device_id uuid,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id), event_id)
) WITH default_time_to_live = 604800;
~~~

`default_time_to_live = 604800` tương ứng một tuần. Đây là **ví dụ bảng riêng** cho dữ liệu có chính sách retention đồng nhất, không phải khuyến nghị thay đổi bảng `device_events_by_day` đang chứa dữ liệu cần lưu giữ lâu dài.

Default TTL và explicit TTL trên từng lệnh ghi cần được hiểu theo quy tắc phiên bản Cassandra. Đặt hay thay TTL của bảng đã chạy production có thể ảnh hưởng vòng đời dữ liệu, tombstones và kế hoạch retention; cần migration, kiểm thử và thống kê dung lượng.

### 9.3. TTL() không phải WRITETIME()

~~~sql
SELECT event_type, detail,
       TTL(detail) AS detail_ttl_seconds,
       WRITETIME(detail) AS detail_write_micros
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

| Biểu thức | Đơn vị/ý nghĩa |
|---|---|
| `detail` | Giá trị text đang live, hoặc `null` nếu không có giá trị live |
| `TTL(detail)` | Số giây TTL còn lại của cell live có TTL, nếu áp dụng |
| `WRITETIME(detail)` | Write timestamp micro giây của cell live theo CQL |

`TTL(detail)` có thể `null` khi không có TTL hoặc cell không có giá trị live; **không** thể lấy `TTL() = null` làm chứng nhận không có tombstone. `WRITETIME` không phải công cụ liệt kê các tombstone đã tồn tại trong SSTable.

## 10. Vì sao null, DELETE và TTL ảnh hưởng hiệu năng đọc?

SSTable của Cassandra về nguyên tắc là bất biến sau khi ghi. Một hàng có thể có nhiều phiên bản cell trong memtable/SSTables và trên các replica. Khi đọc, hệ thống phải hợp nhất phiên bản phù hợp, trong đó có các tombstone.

~~~text
SSTable cũ:
    (event A, detail = "v1", writetime = 100)

Memtable / SSTable mới:
    (event A, tombstone(detail), writetime = 200)

SELECT detail:
    Cần hòa giải phiên bản và tombstone.
    Kết quả logic: detail = null.

Compaction sau đó:
    Có thể loại bỏ dữ liệu cũ và tombstone
    khi các điều kiện an toàn được đáp ứng.
~~~

Nếu một partition chứa hàng nghìn/millions cell đã xóa hoặc hết TTL, các truy vấn có thể phải **quét nhiều tombstone** để tìm đủ các hàng còn live. Một câu `LIMIT 20` không luôn đồng nghĩa Cassandra chỉ cần đọc đúng 20 cell từ storage.

Các chỉ số cần theo dõi:

- p50/p95/p99 latency của `SELECT` theo partition key và clustering range.
- Tombstones scanned per read, live cells scanned và cảnh báo tombstone threshold.
- Kích thước partition, số SSTable cần tham gia đọc, hot partition.
- Tốc độ update/delete/TTL, số mutation ghi vô nghĩa và write amplification.
- Disk usage, compaction backlog, repair status, replica availability và timeout.
- Số fetch/page và lượng dữ liệu đọc thực tế khi dùng `Slice` hoặc driver paging.

Trong cluster thật, tên metric và công cụ quan sát thay đổi theo phiên bản/distribution. Có thể kiểm tra **table metrics**, log cảnh báo và công cụ quản trị của Cassandra; không suy đoán tỷ lệ tombstone từ việc chỉ nhìn số hàng trả về.

### 10.1. Một nghịch lý thường gặp

~~~text
Client hỏi: 20 event mới nhất của thiết bị.
Partition có 1.000 event, 980 event mới nhất đã hết TTL.
Client thấy ít dữ liệu live.

Nhưng Cassandra vẫn có thể phải xử lý rất nhiều dấu hết hạn
để xác định hàng nào còn hợp lệ trước khi trả kết quả.
~~~

Đây là lý do cần **thiết kế retention và partitioning phù hợp**. Giảm `pageSize` hoặc tăng timeout vô hạn không giải quyết triệt để một partition chứa quá nhiều dữ liệu đã hết hạn.

## 11. gc_grace_seconds, compaction và nguy cơ zombie data

Cassandra không thể dọn tombstone quá sớm một cách tùy tiện, vì một replica offline có thể vẫn giữ bản sao dữ liệu **trước khi bị xóa**. Một trong những cấu hình liên quan là **`gc_grace_seconds`**, khoảng thời gian nhằm hỗ trợ an toàn cho việc đồng bộ dấu xóa trước khi chúng có thể trở thành ứng viên được thu dọn.

~~~sql
-- Ví dụ kiểm tra schema/retention. Không thay đổi production vô cớ.
SELECT table_name, gc_grace_seconds, default_time_to_live
FROM system_schema.tables
WHERE keyspace_name = 'app_data'
  AND table_name = 'device_events_by_day';
~~~

Chú ý:

1. **`gc_grace_seconds` không phải TTL**. TTL quyết định thời điểm dữ liệu hết hiệu lực; grace liên quan đến an toàn dọn dấu xóa.
2. **Hết grace không có nghĩa tombstone lập tức biến mất**. Compaction, SSTable overlap, điều kiện dữ liệu liên quan và phiên bản storage ảnh hưởng khả năng purge.
3. **Compaction không thay repair**. Replica bỏ lỡ delete có thể làm dữ liệu cũ sống lại (*zombie data*) nếu tombstone bị purge khi các bản sao chưa được đồng bộ theo điều kiện an toàn.
4. **Không hạ `gc_grace_seconds` về 0 theo thói quen** để tiết kiệm dung lượng; chính sách repair và các điều kiện đặc thù của hệ thống phải được đánh giá với đội vận hành.
5. TTL dài hay ngắn, compaction strategy và repair cadence là **một quyết định vận hành gắn với dữ liệu**, không phải một “setting Java” giải quyết được bằng annotation.

### 11.1. Minh họa nguy cơ zombie

~~~text
T0: Row có giá trị "old" tại replica A, B, C.

T1: C offline. DELETE đến A và B.
    A/B giữ tombstone; C còn "old".

T2: Tombstone bị thu dọn khi điều kiện an toàn chưa thỏa.

T3: C trở lại và đưa "old" vào quá trình đồng bộ/hòa giải.
    Nếu không còn tombstone chặn, dữ liệu cũ có thể xuất hiện lại.
~~~

Mô hình này giải thích **vì sao phải phối hợp thời gian grace, repair, mức nhất quán và sự cố replica**. Nó không phải dự đoán rằng mọi lần hạ grace đều gây zombie, nhưng là rủi ro phải phân tích trước khi thay cấu hình.

### 11.2. Compaction strategy và time series

Với dữ liệu sự kiện dùng time buckets và retention đều, **TimeWindowCompactionStrategy (TWCS)** có thể là một lựa chọn cần benchmark trên phiên bản Cassandra hỗ trợ. Tuy nhiên:

- Phân phối ghi đến muộn, TTL khác nhau giữa các cột và cập nhật/xóa ngẫu nhiên có thể ảnh hưởng hiệu quả windowing.
- Một partition quá nóng vẫn có thể là vấn đề dù dùng TWCS.
- Không có một compaction strategy “tốt nhất” cho mọi bảng.
- Việc thay strategy hoặc TTL trên production phải có kế hoạch migration/đo đạc.

Không bật TWCS hoặc rút ngắn grace chỉ vì bài học nói tới tombstone; phải đánh giá access pattern và operational constraints thật.

## 12. DELETE với timestamp và dữ liệu đến muộn

Tombstone cũng có **write timestamp** giống mutation. Giả sử cùng một cell `detail`, ta có:

| Mutation | Write timestamp (µs, giả lập) | Tác động sau hòa giải |
|---|---:|---|
| Ghi `detail='old'` | 100 | Giá trị ban đầu |
| `DELETE detail` | 300 | **Tombstone thắng** giá trị cũ |
| Ghi đến muộn `detail='late'` | 200 | **Không làm giá trị sống lại** nếu tombstone 300 vẫn có hiệu lực |
| Ghi mới thực sự `detail='new'` | 400 | Có thể thắng tombstone 300 theo quy tắc hòa giải |

~~~sql
-- Chỉ minh họa thứ tự metadata.
UPDATE device_events_by_day
USING TIMESTAMP 100
SET detail = 'old'
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;

DELETE detail FROM device_events_by_day
USING TIMESTAMP 300
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;

UPDATE device_events_by_day
USING TIMESTAMP 200
SET detail = 'late'
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

Các giá trị `100/200/300` là micro giây kể từ Unix epoch, **chỉ dành cho sơ đồ so sánh**. Không chạy những timestamps quá cũ trên một hàng production đang được ghi với timestamp hiện hành. Khi test thực tế, dùng một hàng fixture mới và timestamp theo micro giây có phạm vi được kiểm soát.

**Không coi tombstone là lệnh cấm ghi vĩnh viễn.** Một mutation mới có write timestamp lớn hơn có thể ghi lại cell. Nếu nghiệp vụ yêu cầu “sự kiện đã bị xóa vĩnh viễn, không bao giờ được tạo lại”, phải có chính sách quyền, idempotency, lifecycle và validation riêng, không chỉ dựa vào DELETE.

### 12.1. LWW theo cell không thay invariant nghiệp vụ

Nếu hai writer cập nhật `detail` và `source` với timestamps khác nhau, kết quả có thể là tổ hợp cột từ hai command. Đổi `detail` sang null không tự đổi `source`, và ngược lại.

Với quy tắc “chỉ cho xóa chi tiết nếu event còn trạng thái OPEN”, nên cân nhắc CQL conditional mutation/LWT khi semantics phù hợp, kiểm tra `[applied]` và xử lý conflict. LWT tốn thêm chi phí và không tạo giao dịch ACID nhiều bảng một cách tự động. Không kết hợp tùy tiện `USING TIMESTAMP` với LWT.

## 13. Delete, TTL và truy vấn theo nhiều partition

Một bảng time series có **ngày là thành phần partition key**. Xóa cả partition của ngày 25/11 khác hoàn toàn với xóa một ngày trước đó. Muốn xóa lịch sử của thiết bị trong 30 ngày, hệ thống phải biết **các day buckets liên quan** và xây một quy trình có giới hạn tải.

Không viết:

~~~sql
-- Sai ý định: thiếu các thành phần partition key,
-- không phải cách xóa mọi sự kiện của một thiết bị.
DELETE FROM device_events_by_day
WHERE device_id = ?;
~~~

Muốn retention dài hạn:

1. Xác định **thời gian giữ dữ liệu** theo tenant/device và yêu cầu pháp lý.
2. Chọn TTL hợp lý khi dữ liệu có vòng đời thống nhất.
3. Nếu xóa partition theo lịch, lên danh sách buckets/cột khóa hợp lệ và giới hạn tốc độ.
4. Tránh tạo hàng triệu câu DELETE nhỏ trên cùng partition khi có cách xử lý retention/bucket hiệu quả hơn.
5. Theo dõi số tombstone, disk/compaction/repair sau đợt dọn dữ liệu.
6. Với yêu cầu xóa thông tin nhạy cảm, đừng đồng nhất “không truy vấn thấy” với **bảo đảm xóa vật lý tức thời trên mọi replica, backup và snapshot**; cần chính sách bảo mật/lưu giữ phù hợp.

**Batch statement không phải phép màu** cho một chiến dịch delete khổng lồ. Batch xuyên nhiều partition có thể tăng tải coordinator và không biến nhiều câu lệnh thành một thao tác xóa vật lý tức thời. Ưu tiên thiết kế theo bucket và xử lý có kiểm soát.

## 14. Pagination không chữa được tombstone scan

Spring Data Cassandra hỗ trợ `Slice<T>` và `CassandraPageRequest` cho việc đọc nhiều hàng:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface DeviceEventPageRepository
        extends CassandraRepository<DeviceEvent, DeviceEventKey> {

    @Query("SELECT * FROM device_events_by_day " +
           "WHERE tenant_id = ?0 AND device_id = ?1 AND event_day = ?2")
    Slice<DeviceEvent> findInDay(
            UUID tenantId, UUID deviceId, LocalDate day,
            Pageable pageable);
}
~~~

Lấy trang đầu và tiếp tục:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Slice;

Slice<DeviceEvent> first = repository.findInDay(
        tenantId, deviceId, day, CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<DeviceEvent> second = repository.findInDay(
            tenantId, deviceId, day, first.nextPageable());
}
~~~

**Phân biệt:**

- Page size giới hạn số hàng trên **một trang fetch**, không phải số tombstone tối đa storage cần xét.
- `LIMIT 20` giới hạn tổng số hàng trả về của câu truy vấn, **không chứng minh chỉ quét 20 cell**.
- Paging state gắn với cùng CQL/bind values; không dùng cursor của ngày này cho ngày khác.
- Xóa/TTL trong lúc phân trang có thể làm tập dữ liệu thay đổi. Paging state không bảo đảm snapshot bất biến qua nhiều request.

Nếu p99 cao vì tombstones trong hot partition, giảm page size chỉ tác động một phần hành vi fetch. Cần phân tích partition design, tỷ lệ dữ liệu sống, lifecycle TTL và compaction.

## 15. Kiểm chứng bằng CQL: kết quả NULL chưa đủ để kết luận

Giả sử một row đã được tạo:

~~~sql
INSERT INTO device_events_by_day (
    tenant_id, device_id, event_day, occurred_at, event_id,
    event_type, detail, source
) VALUES (?, ?, ?, ?, ?, 'SCAN', 'secret', 'gateway-1');
~~~

Sau đó thực thi `DELETE detail`, dùng:

~~~sql
SELECT event_type, detail, source,
       WRITETIME(event_type) AS type_write_us,
       WRITETIME(detail) AS detail_write_us,
       TTL(detail) AS detail_ttl_s
FROM device_events_by_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Kết quả sau khi delete được áp dụng:

~~~text
event_type     = SCAN
detail         = null
source         = gateway-1
detail_write_us  = null (không có cell live để WRITETIME trả về)
detail_ttl_s     = null (không có TTL của cell live)
~~~

**Không suy ra từ `detail_write_us=null` rằng “không có tombstone”.** `WRITETIME` là hàm CQL dành cho dữ liệu cell còn live theo khả năng hỗ trợ, không phải công cụ kiểm kê tombstone. Để điều tra storage sâu cần metrics/diagnostics của Cassandra, không chỉ `SELECT` một hàng.

### 15.1. Kiểm tra schema và TTL cấu hình

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'app_data'
  AND table_name = 'device_events_by_day';

SELECT default_time_to_live, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'app_data'
  AND table_name = 'device_events_by_day';
~~~

`app_data` chỉ là keyspace ví dụ; cần thay bằng keyspace đã provision cho ứng dụng. `DESCRIBE TABLE` là lệnh của `cqlsh`, không phải một prepared CQL statement thông thường để gửi qua `CqlSession`.

## 16. Integration test: NULL tạo xóa, UNSET giữ giá trị

Để kiểm chứng đúng semantics, hãy dùng một **Cassandra test instance** với bảng đã được tạo và fixture có khóa riêng. Một test có thể:

1. Ghi `detail='initial'`, `event_type='SCAN'`.
2. Prepared `UPDATE` với `detail` là UNSET, đồng thời `event_type='ALERT'`; kiểm tra `detail` vẫn là `initial`.
3. Prepared `UPDATE` với `detail` là NULL; kiểm tra `detail` trở thành `null` trong khi `event_type` còn hiện diện.
4. Ghi lại `detail` bằng mutation **mới hơn** khi hợp đồng cho phép; kiểm tra giá trị có thể sống lại.
5. Xóa **đúng hàng** bằng đầy đủ primary key; kiểm tra các hàng khác trong partition không bị xóa.
6. Trong test cô lập khác, xóa **cả partition** và kiểm tra tất cả hàng trong partition bị ảnh hưởng, partition khác vẫn còn.

### 16.1. Khung test tích hợp bằng Java Driver

~~~java
package example.telemetry;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class NullUnsetTombstoneIntegrationTest {

    @Autowired CqlSession session;

    @Test
    void unsetPreservesColumnButNullDeletesIt() {
        UUID tenant = UUID.randomUUID();
        UUID device = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 25);
        Instant occurredAt = Instant.parse("2026-11-25T09:00:00Z");

        PreparedStatement insert = session.prepare(
                "INSERT INTO device_events_by_day " +
                "(tenant_id, device_id, event_day, occurred_at, event_id, " +
                "event_type, detail, source) " +
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)");

        session.execute(insert.bind(
                tenant, device, day, occurredAt, eventId,
                "SCAN", "initial", "gateway-1"));

        PreparedStatement update = session.prepare(
                "UPDATE device_events_by_day " +
                "SET detail = ?, event_type = ? " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND event_day = ? AND occurred_at = ? AND event_id = ?");

        var unsetBuilder = update.boundStatementBuilder()
                .unset(0)
                .setString(1, "ALERT")
                .setUuid(2, tenant)
                .setUuid(3, device)
                .setLocalDate(4, day)
                .setInstant(5, occurredAt)
                .setUuid(6, eventId);
        session.execute(unsetBuilder.build());

        PreparedStatement select = session.prepare(
                "SELECT detail, event_type FROM device_events_by_day " +
                "WHERE tenant_id = ? AND device_id = ? " +
                "AND event_day = ? AND occurred_at = ? AND event_id = ?");

        Row afterUnset = session.execute(
                select.bind(
                        tenant, device, day, occurredAt, eventId)).one();
        assertNotNull(afterUnset);
        assertEquals("initial", afterUnset.getString("detail"));
        assertEquals("ALERT", afterUnset.getString("event_type"));

        var nullBuilder = update.boundStatementBuilder()
                .setToNull(0)
                .setString(1, "ALERT")
                .setUuid(2, tenant)
                .setUuid(3, device)
                .setLocalDate(4, day)
                .setInstant(5, occurredAt)
                .setUuid(6, eventId);
        session.execute(nullBuilder.build());

        Row afterNull = session.execute(
                select.bind(
                        tenant, device, day, occurredAt, eventId)).one();
        assertNotNull(afterNull);
        assertTrue(afterNull.isNull("detail"));
        assertEquals("ALERT", afterNull.getString("event_type"));
    }
}
~~~

Test trên dùng `var` của Java 10+ và driver 4, giả định schema/keyspace đã có. Với Cassandra nhiều replica, nên chọn consistency và môi trường test phù hợp để tránh nhầm lỗi dữ liệu chưa hội tụ với lỗi semantics. **Đây là code minh họa, chưa được chạy trong STEP 4**.

Một integration test chỉ xác nhận **kết quả logic** qua CQL; nó không đo được số tombstone vật lý. Nếu cần so sánh tombstone scan trước/sau, hãy dùng metrics/benchmark ở môi trường riêng, với tải và compaction policy được kiểm soát.

### 16.2. Kiểm thử DELETE đúng hàng và đúng partition

Fixture đề xuất:

~~~text
Partition P1 = (tenant A, device X, day 25):
    event e1, e2, e3

Partition P2 = (tenant A, device X, day 24):
    event e4

Partition P3 = (tenant A, device Y, day 25):
    event e5
~~~

Test thứ nhất:

~~~sql
-- Xóa duy nhất e2 khi đã biết đủ clustering key:
DELETE FROM device_events_by_day
WHERE tenant_id = ? AND device_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

Kỳ vọng `e1/e3` còn trong P1; `e4/e5` ở P2/P3 không bị ảnh hưởng. Test thứ hai, với fixture **mới**, chỉ cung cấp partition key khi `DELETE` và xác nhận cả P1 bị xóa nhưng P2/P3 không bị ảnh hưởng. Không dùng production hoặc dữ liệu chung cho negative/destructive tests.

## 17. Những lỗi dễ gặp khi thiết kế CRUD

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Gán `null` khi muốn “không cập nhật” | Tạo tombstone, có thể xóa dữ liệu cũ | Phân biệt field vắng mặt và null; dùng UNSET/bỏ cột |
| Dùng `save(entity)` cho PATCH mà không kiểm tra null mapping | Có thể ghi rộng ngoài ý định | Dùng update có danh sách cột rõ ràng và integration test |
| `DELETE` thiếu clustering key | Có thể xóa cả partition thay vì một event | Ràng buộc đầy đủ khóa hàng với thao tác delete-one |
| Nghĩ `DELETE` thành công là affected-row-count = 1 | Trả kết quả nghiệp vụ sai | Dùng contract phù hợp hoặc LWT `IF EXISTS` nếu cần |
| Nghĩ `detail=null` chứng minh tombstone không có | Nhầm thiếu cell với xóa cell | Dựa vào lịch sử mutation, schema, diagnostics |
| Đặt TTL cho cả event khi chỉ muốn xóa `detail` | Mất luôn các cột cần giữ | Chỉ TTL cột cần hết hạn hoặc tách read model |
| Quên TTL trên một bản ghi upsert | Dữ liệu tồn tại lâu hơn policy dự kiến | Thiết kế lifecycle và test từng lệnh ghi |
| Retry TTL write liên tục | Thời điểm hết hạn bị thay đổi | Chọn chính sách retry/idempotency có tính tới TTL |
| Giảm `gc_grace_seconds` vô căn cứ | Nguy cơ zombie nếu replica bỏ lỡ delete | Phối hợp repair/compaction/availability |
| Xóa hàng triệu hàng từng row trong một hot partition | Tombstone scan, write amplification và p99 tăng | Time bucket, retention, rate limit và giám sát |
| Nghĩ `LIMIT 20` chỉ quét 20 cell | Query vẫn có thể quét nhiều tombstone | Theo dõi metrics, sửa mô hình dữ liệu |
| Đổi primary key bằng cách gán `null` | CQL không hợp lệ | Ghi sang khóa mới rồi xử lý khóa cũ |
| Đọc qua `LOCAL_ONE` rồi cho rằng mọi replica đã xóa | Có thể đọc từ replica chưa hội tụ | Chọn consistency/repair theo yêu cầu |
| Coi tombstone là xóa vật lý tức thời ở mọi backup | Rủi ro hiểu sai retention/privacy | Quản lý replica, snapshots, backups và lifecycle |

## 18. Bài tập thực hành

Một ứng dụng logistics lưu các lần quét kiện hàng:

~~~sql
CREATE TABLE package_scans_by_day (
    tenant_id uuid,
    package_id uuid,
    scan_day date,
    scanned_at timestamp,
    scan_id uuid,
    scan_type text,
    location_note text,
    operator_id uuid,
    PRIMARY KEY (
        (tenant_id, package_id, scan_day),
        scanned_at, scan_id
    )
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id ASC);
~~~

### Bài tập A — xóa nội dung nhạy cảm, giữ sự kiện

Quy định: sau 24 giờ, phải xóa `location_note`, nhưng giữ `scan_type`, `operator_id`, `scanned_at` và khóa. Hãy:

1. Viết `UPDATE ... USING TTL 86400 SET location_note=?` với toàn bộ primary key.
2. Viết `DELETE location_note FROM ... WHERE` để xóa chủ động trước TTL.
3. Giải thích vì sao `DELETE FROM ... WHERE fullPrimaryKey` là thao tác **khác**.
4. Nêu chính sách compaction/repair/retention phải kiểm tra nếu dữ liệu cần xóa thật sự khỏi mọi bản sao và backup.

Lời giải CQL khung:

~~~sql
-- Đặt TTL một ngày chỉ cho cột location_note trong lệnh này.
UPDATE package_scans_by_day
USING TTL 86400
SET location_note = ?
WHERE tenant_id = ? AND package_id = ? AND scan_day = ?
  AND scanned_at = ? AND scan_id = ?;

-- Xóa chủ động đúng một cột của đúng hàng.
DELETE location_note FROM package_scans_by_day
WHERE tenant_id = ? AND package_id = ? AND scan_day = ?
  AND scanned_at = ? AND scan_id = ?;
~~~

### Bài tập B — PATCH và ba trạng thái

Endpoint:

~~~text
PATCH /tenants/{tenantId}/packages/{packageId}/scans/{scanId}
~~~

Nếu client gửi:

~~~json
{"scanType":"REVIEWED"}
~~~

thì `location_note` cần **giữ nguyên**. Nếu client gửi:

~~~json
{"locationNote":null}
~~~

thì `location_note` cần **bị xóa**. Nếu gửi:

~~~json
{"locationNote":"verified"}
~~~

thì ghi giá trị mới. Thiết kế một DTO phân biệt *absent/null/value* và map sang **UNSET/NULL/bind value** hoặc các CQL mutation được chọn. Vì URL không có `scan_day`/`scanned_at`, phải giải thích cách tìm đủ khóa bằng locator/read model hoặc thay API contract; không dùng mỗi `scanId` để xóa trên bảng này.

### Bài tập C — xóa một ngày và kiểm tra blast radius

Viết `DELETE` cho **một hàng** và `DELETE` cho **cả partition** theo `(tenant_id, package_id, scan_day)`. Tạo fixture hai ngày, hai kiện hàng. Kiểm tra rõ dữ liệu ngoài phạm vi delete vẫn còn.

### Bài tập D — tombstone scan và retention

Một thiết bị có 2 triệu scan/ngày, 95% cột `location_note` hết TTL trong một ngày. Trang danh sách 50 scan mới nhất có p99 cao. Hãy đề xuất:

- Chia bucket theo giờ hoặc shard nếu phân phối dữ liệu phù hợp.
- Chỉ giữ cột thật sự cần thiết và tách dữ liệu có TTL khác nhau khi hữu ích.
- Kiểm tra tombstone scan, partition size, compaction/repair/TTL và tải.
- Benchmark không đồng nhất `LIMIT 50` với “quét 50 cell”.
- Đánh giá table compaction/retention strategy theo yêu cầu production.

### Câu hỏi tự kiểm tra

1. Vì sao `UPDATE detail=null` khác `UPDATE event_type='SCAN'` khi không nhắc đến detail?
2. `UNSET` trong prepared statement có đồng nghĩa `NULL` không?
3. `DELETE detail FROM ...` và `DELETE FROM ...` khác nhau ở phạm vi nào?
4. Khi chỉ cung cấp partition key cho `DELETE FROM`, điều gì có thể xảy ra?
5. Một hàng đọc `detail=null` có chắc chứa tombstone không?
6. Sau TTL hết hạn, có bảo đảm dung lượng trên đĩa được thu hồi ngay không?
7. `TTL(detail)` khác `WRITETIME(detail)` thế nào?
8. `gc_grace_seconds` có phải TTL của dữ liệu nghiệp vụ không?
9. Vì sao cần repair trước khi tombstone bị purge theo điều kiện an toàn?
10. `LIMIT 20` có bảo đảm Cassandra chỉ xét 20 cell không?
11. `repository.save(entity)` với field null có chắc dùng UNSET trong mọi phiên bản không?
12. Dùng `IF EXISTS` cho DELETE giải quyết gì và đánh đổi gì?

**Đáp án gợi ý:** (1) gán null là ý định xóa; bỏ cột là giữ nguyên; (2) không; (3) một cột vs cả hàng; (4) xóa cả partition; (5) không; (6) không; (7) thời hạn còn lại tính giây vs timestamp ghi micro giây; (8) không; (9) tránh bản sao cũ làm dữ liệu sống lại; (10) không; (11) không, phải kiểm tra behavior thực tế; (12) kiểm tra tồn tại nguyên tử qua LWT, chi phí cao hơn.

## 19. Checklist trước khi triển khai

- [ ] Nắm đúng **partition key và clustering columns** trước khi viết mọi `DELETE`.
- [ ] Phân biệt delete **cột**, **hàng**, **partition** và **khoảng clustering**.
- [ ] Xóa một hàng bằng **đầy đủ primary key**, không bỏ sót clustering key.
- [ ] Không gán `null` khi ý định là “không thay đổi giá trị hiện có”.
- [ ] API PATCH phân biệt rõ field **vắng mặt / null / có giá trị**.
- [ ] Prepared statements dùng `UNSET` cho trường muốn giữ nguyên và `NULL` cho xóa có chủ đích.
- [ ] Không coi `save(entity)` là merge từng field nếu chưa kiểm thử cách mapping null.
- [ ] Nếu dùng `CqlTemplate` hoặc driver trực tiếp, bind đúng thứ tự và kiểu tham số.
- [ ] Hiểu TTL tạo dữ liệu hết hạn/tombstone; không coi TTL là thu hồi byte tức thời.
- [ ] Kiểm tra `default_time_to_live`, `gc_grace_seconds` và compaction strategy của bảng thật.
- [ ] Có repair cadence và quy trình sự cố replica phù hợp trước khi thay grace period.
- [ ] Không dùng `WRITETIME`/`TTL` để kết luận tombstone vật lý đã biến mất.
- [ ] Đã xét retry, write timestamps và rủi ro cập nhật/xóa đến muộn.
- [ ] Không chạy batch delete không giới hạn trên nhiều partition.
- [ ] Có integration tests cho `UNSET` vs `NULL`, delete-one vs delete-partition và TTL.
- [ ] Theo dõi tombstones scanned, p95/p99, partition size, compaction/repair và timeout.
- [ ] Đã xác định chính sách backup/snapshot nếu cần xóa dữ liệu nhạy cảm theo yêu cầu.
- [ ] Không suy từ trạng thái `WRITTEN` của bài rằng code ví dụ đã được chạy QA/production.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — Storage Engine](https://cassandra.apache.org/doc/latest/cassandra/architecture/storage-engine.html).
- [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/compaction/index.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra Java Driver 4 — Prepared Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/).
