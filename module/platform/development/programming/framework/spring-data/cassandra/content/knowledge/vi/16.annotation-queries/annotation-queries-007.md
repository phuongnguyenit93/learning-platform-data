# USING TTL và USING TIMESTAMP trong câu lệnh ghi

Trong **Apache Cassandra**, câu lệnh ghi CQL có thể mang theo hai thông tin thời gian rất khác nhau: **`USING TTL`** quy định thời gian một giá trị còn hiệu lực, còn **`USING TIMESTAMP`** cung cấp *write timestamp* dùng để giải quyết các phiên bản ghi cạnh tranh. Khi truy cập Cassandra bằng **Spring Data Cassandra**, ta có thể khai báo CQL trực tiếp trong **`@Query`** của repository và bind cả hai giá trị từ Java.

Bài thuộc chương **Truy vấn @Query** của module **SPRING_DATA_CASSANDRA**. Ngoài cú pháp và ví dụ thực hành, bài làm rõ vì sao TTL không phải là thời gian sự kiện, vì sao write timestamp không phải cột CQL `timestamp`, cách dùng `@Modifying`, tác động của upsert/tombstone, consistency, retry và kiểm thử trên một hệ thống dữ liệu phân tán.

## 1. Hai cơ chế thời gian: giống tên nhưng khác mục đích

| Nội dung | `USING TTL` | `USING TIMESTAMP` |
| --- | --- | --- |
| Ý nghĩa | Thời hạn tồn tại của những giá trị/cell được ghi | Write timestamp phục vụ phân giải phiên bản ghi |
| Đơn vị | **Giây** | **Micro giây** tính từ Unix epoch |
| Ví dụ | `USING TTL 86400` | `USING TIMESTAMP 1795593600000000` |
| Tác động chính | Giá trị được ghi có thể hết hạn và trở thành tombstone | Giá trị có timestamp mới/cũ hơn có thể thắng/thua khi xung đột |
| Có phải thời gian sự kiện? | Không | Không; trừ khi ứng dụng cố tình chọn cùng mốc, và vẫn phải hiểu rủi ro |
| Có làm Cassandra tự chia partition theo thời gian? | Không | Không |
| Dùng chung được? | Có, với câu `INSERT`/`UPDATE` phù hợp | Có, với câu `INSERT`/`UPDATE` phù hợp |

Ví dụ một sự kiện được nhận lúc 10:00, cần giữ 24 giờ. `TTL = 86400` diễn đạt thời hạn tồn tại tính theo thời điểm ghi được áp dụng. Nếu ghi đồng thời với một writer khác, `TIMESTAMP` được dùng để xét các phiên bản cell nào được ưu tiên. Hai cơ chế không thay thế nhau.

**Tình huống dễ nhầm:** gửi một `TIMESTAMP` cũ không biến `TTL 86400` thành “hết hạn sau 24 giờ kể từ thời điểm sự kiện cũ”. Khi tính retention theo event time, ứng dụng phải tự tính thời gian còn lại và kiểm tra chính sách hết hạn.

## 2. Chuẩn bị schema theo truy vấn

Giả sử ứng dụng quản lý những sự kiện của mỗi tenant theo ngày, muốn ghi trạng thái với TTL và đọc lại lịch sử trong một partition.

~~~sql
CREATE KEYSPACE IF NOT EXISTS activity_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS activity_ks.events_by_tenant_day (
    tenant_id   uuid,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    status      text,
    details     text,
    PRIMARY KEY ((tenant_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Ở đây:

- **Partition key** là cặp `(tenant_id, event_day)`: sự kiện của cùng tenant và cùng ngày thuộc cùng partition.
- **Clustering columns** là `occurred_at` và `event_id`: xác định hàng và hỗ trợ đọc theo thứ tự thời gian trong một ngày.
- `status` và `details` là các cột thường; chúng có thể được cập nhật qua `UPDATE` mà không thay đổi primary key.
- `occurred_at timestamp` lưu **thời điểm sự kiện**; giá trị này **khác** write timestamp truyền bởi `USING TIMESTAMP`.

Tên datacenter `dc1` và replication factor 3 chỉ để minh họa; cluster thực tế cần cấu hình replica, datacenter và consistency phù hợp. Ở production, quản lý schema bằng migration thay vì để từng instance ứng dụng tự tạo lại bảng.

Truy vấn đọc một tenant/ngày:

~~~sql
SELECT occurred_at, event_id, event_type, status, details
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ? AND event_day = ?
LIMIT 50;
~~~

Các dấu `?` là bind marker của CQL. Đọc theo ngày chỉ liên quan partition key; lựa chọn TTL và timestamp **không làm giảm số partition phải truy cập** khi API muốn tìm lịch sử nhiều ngày.

## 3. Cú pháp USING TTL với INSERT

Giả sử một sự kiện cần tự hết hạn sau **một ngày**:

~~~sql
INSERT INTO activity_ks.events_by_tenant_day (
    tenant_id, event_day, occurred_at, event_id,
    event_type, status, details
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TTL 86400;
~~~

`86400` là số **giây**, không phải số mili giây, cũng không phải một timestamp tuyệt đối. TTL áp dụng cho những giá trị được ghi với lệnh này theo ngữ nghĩa Cassandra; khi chúng hết hạn, Cassandra xem chúng không còn là dữ liệu sống. Dữ liệu vật lý trong SSTable thường **không được thu hồi ngay**: việc dọn dẹp tùy thuộc tombstone, compaction và trạng thái replica.

Có thể dùng bind marker:

~~~sql
INSERT INTO activity_ks.events_by_tenant_day (
    tenant_id, event_day, occurred_at, event_id,
    event_type, status, details
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TTL ?;
~~~

Điều này cho phép ứng dụng chọn thời gian sống có kiểm soát, thay vì ghép TTL vào chuỗi CQL từ input. **Nên validate TTL ở service**: không nhận số âm hoặc thời gian vượt chính sách nghiệp vụ, và không cho client tùy ý giữ dữ liệu vĩnh viễn khi hệ thống yêu cầu retention.

### TTL thuộc về giá trị được ghi, không phải “ngày của partition”

Một partition có thể chứa nhiều hàng, và mỗi hàng chứa nhiều cell với **TTL khác nhau**. Một sự kiện mới trong ngày có thể còn hiệu lực khi sự kiện cũ hơn cùng partition đã hết TTL.

**Time bucketing** bằng `event_day` giúp quản lý kích thước partition theo thời gian; **TTL** giúp dữ liệu hết hạn. Hai cơ chế phối hợp nhưng không đồng nghĩa. TTL không tự xóa đúng một bucket theo lịch, và time bucket không tự cấp TTL cho các hàng.

## 4. Cú pháp USING TTL với UPDATE

Khi chỉ muốn cập nhật `status` và cho giá trị mới hết hạn sau một giờ:

~~~sql
UPDATE activity_ks.events_by_tenant_day
USING TTL 3600
SET status = 'PROCESSED'
WHERE tenant_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

**Thứ tự cú pháp quan trọng:** với `UPDATE`, mệnh đề `USING` đứng **trước `SET`**; với `INSERT`, mệnh đề `USING` đứng **sau `VALUES`**.

Hành vi cần hiểu:

- TTL của lần update liên quan tới những **cell được ghi trong lần đó**, ở đây là `status`.
- Các cột không được đưa vào `SET`, như `details`, không mặc nhiên được gia hạn cùng TTL.
- Ghi lại một cell có thể thay write timestamp và thời gian sống của cell đó theo quy tắc Cassandra.
- `UPDATE` thông thường có tính **upsert**: nó không tự bảo đảm hàng đã tồn tại. Nếu khóa chưa có, Cassandra có thể tạo dữ liệu tại khóa đó.

Không dùng `repository.save(entity)` rồi giả định Spring Data chỉ cập nhật một field mới thay đổi giống dirty checking của JPA. Nếu muốn TTL chỉ áp dụng cho `status`, câu CQL tường minh với `SET status = ...` cho biết rõ phạm vi hơn.

### Đừng gộp TTL vào câu DELETE

`DELETE` là thao tác xóa, không phải ghi giá trị với thời gian sống. CQL có thể cho phép xác định write timestamp của thao tác xóa:

~~~sql
DELETE FROM activity_ks.events_by_tenant_day
USING TIMESTAMP ?
WHERE tenant_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Nhưng **`USING TTL` không phải tùy chọn dùng cho `DELETE`**. Muốn cho dữ liệu tự hết hạn, đặt TTL tại thời điểm ghi phù hợp thay vì chờ đến khi xóa.

## 5. USING TIMESTAMP: timestamp của cell, không phải event time

Cassandra dùng **write timestamp** để giải quyết các ghi cạnh tranh trên cùng dữ liệu. Trong cơ chế phân giải xung đột thông thường, phiên bản có timestamp cao hơn được ưu tiên; trường hợp bằng timestamp còn có các quy tắc phân giải riêng, vì thế không nên chủ động tạo xung đột timestamp bằng nhau với dữ liệu khác nhau.

Ví dụ CQL:

~~~sql
INSERT INTO activity_ks.events_by_tenant_day (
    tenant_id, event_day, occurred_at, event_id,
    event_type, status
) VALUES (?, ?, ?, ?, ?, ?)
USING TIMESTAMP 1795593600000000;
~~~

`1795593600000000` chỉ là **ví dụ số micro giây từ Unix epoch**, không phải “TTL” hay thời điểm sự kiện của row. Nếu không chỉ định `USING TIMESTAMP`, Cassandra/driver sử dụng cơ chế gán write timestamp theo cấu hình và phiên bản để phục vụ quá trình ghi.

So sánh hai trường thời gian:

| Dữ liệu | Kiểu/ví dụ | Vai trò |
| --- | --- | --- |
| `occurred_at` trong primary key | CQL `timestamp`; Java `Instant` | Xác định thời điểm sự kiện và vị trí hàng theo clustering |
| `USING TIMESTAMP` | CQL số nguyên `bigint` ở đơn vị **micro giây** | Định thứ tự thắng/thua của các bản ghi cell cạnh tranh |
| `USING TTL` | CQL số nguyên đơn vị **giây** | Cho giá trị được ghi hết hạn |

Không nhầm CQL `timestamp` (thời gian được biểu diễn ở cấp độ mili giây trong driver/kiểu thời gian) với **micro giây của write timestamp**. Nếu truyền `System.currentTimeMillis()` trực tiếp làm `USING TIMESTAMP`, số đó nhỏ hơn khoảng **1.000 lần** so với giá trị micro giây ở cùng thời điểm: ghi có thể thua những ghi khác một cách khó hiểu.

## 6. Dùng TTL và TIMESTAMP đồng thời

Cassandra hỗ trợ kết hợp hai tùy chọn trên một câu `INSERT` phù hợp:

~~~sql
INSERT INTO activity_ks.events_by_tenant_day (
    tenant_id, event_day, occurred_at, event_id,
    event_type, status, details
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TTL ? AND TIMESTAMP ?;
~~~

Với `UPDATE`:

~~~sql
UPDATE activity_ks.events_by_tenant_day
USING TTL ? AND TIMESTAMP ?
SET status = ?
WHERE tenant_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Hai giá trị ở `USING` có **vai trò độc lập**. TTL là thời gian sống; timestamp là thứ tự phiên bản. Một write với timestamp cũ hơn giá trị đã lưu có thể **không thay thế** giá trị hiện hữu, kể cả khi đưa TTL dài hơn. Do đó không được hiểu rằng “gọi lại UPDATE với TTL mới sẽ chắc chắn gia hạn dữ liệu”.

**Ví dụ thời điểm xảy ra và thời điểm xử lý khác nhau:**

~~~text
Sự kiện thực tế xảy ra:     2026-11-24 23:58 UTC
Hệ thống nhận và ghi:      2026-11-25 00:06 UTC
Retention mong muốn:       7 ngày từ thời điểm xảy ra
Write timestamp:           giá trị dùng cho phân giải ghi
TTL cần tính:              thời gian còn lại đến hạn retention
~~~

Không gán TTL mặc định 7 ngày từ lúc nhận nếu chính sách yêu cầu hết hạn tính từ event time. Ngược lại, cũng đừng tùy tiện lấy event time làm write timestamp; dữ liệu đến muộn có thể bị ghi với timestamp thấp và thua cập nhật đã có.

## 7. @Query và @Modifying trong Spring Data Cassandra

Annotation `@Query` cho phép khai báo CQL tại repository. Với câu lệnh **thay đổi dữ liệu** như `INSERT`, `UPDATE` hoặc `DELETE`, nên dùng thêm **`@Modifying`** theo API của Spring Data Cassandra phiên bản dự án để repository xử lý câu lệnh như thao tác ghi, không phải truy vấn ánh xạ entity.

Ví dụ repository thực thi **INSERT có TTL và write timestamp**:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Modifying;
import org.springframework.data.cassandra.repository.Query;

public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Modifying
    @Query("""
        INSERT INTO events_by_tenant_day
          (tenant_id, event_day, occurred_at, event_id,
           event_type, status, details)
        VALUES (?0, ?1, ?2, ?3, ?4, ?5, ?6)
        USING TTL ?7 AND TIMESTAMP ?8
        """)
    void insertWithExpiry(
        UUID tenantId,
        LocalDate eventDay,
        Instant occurredAt,
        UUID eventId,
        String eventType,
        String status,
        String details,
        int ttlSeconds,
        long writeTimestampMicros
    );
}
~~~

**Điểm cần đọc đúng:**

1. `?0` đến `?6` bind vào các cột theo thứ tự khai báo.
2. `?7` là số giây TTL, dùng kiểu Java `int`.
3. `?8` là số micro giây write timestamp, dùng kiểu Java `long`.
4. Tham số `occurredAt` là `Instant` dành cho **cột CQL `timestamp`**, không được tự động dùng làm write timestamp.
5. `@Modifying` không làm câu INSERT thành conditional insert. Nếu trùng primary key, Cassandra có ngữ nghĩa upsert thông thường.

Ví dụ dùng **Java text block** nên cần Java 15+. Nếu ứng dụng sử dụng Java cũ hơn, thay bằng chuỗi nối; khi dự án dùng phiên bản Spring Data Cassandra khác, kiểm tra package/khả năng hỗ trợ của `@Modifying` và phương thức binding.

### Entity và primary key tương ứng

Một bản mapping rút gọn đủ để hiểu kiểu ID của repository:

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "event_day", ordinal = 1,
                      type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(name = "occurred_at", ordinal = 2,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(name = "event_id", ordinal = 3,
                      type = PrimaryKeyType.CLUSTERED,
                      ordering = Ordering.DESCENDING)
    private UUID eventId;

    // Constructor, getters/setters, equals/hashCode phù hợp.
}

@Table("events_by_tenant_day")
public class EventRow {
    @PrimaryKey
    private EventKey key;

    @Column("event_type")
    private String eventType;

    @Column("status")
    private String status;

    @Column("details")
    private String details;
}
~~~

Để biên dịch, bổ sung import cho `Serializable`, các annotation mapping, `Ordering`, `PrimaryKeyType`, constructor và accessor theo version thực tế. Với ví dụ, ứng dụng phải được cấu hình **keyspace mặc định `activity_ks`** hoặc viết tên bảng đầy đủ trong `@Query`.

Chọn CQL trực tiếp tại repository ở đây giúp chủ động **TTL/timestamp và danh sách cột**, thay vì giả định `repository.save(entity)` sẽ tự dùng TTL hoặc timestamp giống nghiệp vụ yêu cầu.

## 8. @Query UPDATE chỉ ghi đúng một cột

Nếu cần cập nhật riêng `status` (không muốn gán TTL cho `details`), viết statement rõ ràng:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Modifying
    @Query("""
        UPDATE events_by_tenant_day
        USING TTL ?0 AND TIMESTAMP ?1
        SET status = ?2
        WHERE tenant_id = ?3
          AND event_day = ?4
          AND occurred_at = ?5
          AND event_id = ?6
        """)
    void updateStatusWithExpiry(
        int ttlSeconds,
        long writeTimestampMicros,
        String status,
        UUID tenantId,
        LocalDate eventDay,
        Instant occurredAt,
        UUID eventId
    );
}
~~~

Hai khai báo interface ở mục 7 và 8 là **hai đoạn minh họa phương thức**; trong dự án, khai báo cả hai trong **cùng một `EventRepository`**, không tạo hai interface Java trùng tên.

Với full primary key, câu UPDATE có mục tiêu rõ ràng. Nếu chỉ cung cấp `tenant_id` và bỏ `event_day` hoặc các clustering column, câu lệnh có thể không hợp lệ hoặc mang ý nghĩa khác mong đợi. Không dùng `ALLOW FILTERING` để sửa một câu ghi sai khóa: điều kiện ghi phải tuân thủ cú pháp CQL.

### Khi không truyền TIMESTAMP

Nếu nghiệp vụ chỉ cần TTL, hãy dùng bản CQL đơn giản hơn:

~~~java
@Modifying
@Query("""
    UPDATE events_by_tenant_day
    USING TTL ?0
    SET status = ?1
    WHERE tenant_id = ?2 AND event_day = ?3
      AND occurred_at = ?4 AND event_id = ?5
    """)
void updateStatusWithTtl(
    int ttlSeconds,
    String status,
    UUID tenantId,
    LocalDate eventDay,
    Instant occurredAt,
    UUID eventId
);
~~~

**Đây thường là lựa chọn dễ vận hành hơn** khi không có yêu cầu đặc biệt về client-assigned timestamp. Để driver/Cassandra quản lý write timestamp theo cấu hình nhất quán giảm rủi ro đồng hồ máy ứng dụng lệch và ghi có timestamp “nhảy” quá xa vào tương lai.

## 9. Chuyển Instant thành micro giây một cách rõ ràng

Java `Instant` gồm **giây Unix epoch và phần nano giây**. `USING TIMESTAMP` cần **micro giây**. Nếu thật sự phải gán write timestamp ở tầng ứng dụng, chuyển đổi có kiểm tra tràn số:

~~~java
import java.time.Instant;

public final class WriteTimestamps {
    private WriteTimestamps() {}

    public static long toEpochMicros(Instant instant) {
        return Math.addExact(
            Math.multiplyExact(instant.getEpochSecond(), 1_000_000L),
            instant.getNano() / 1_000L
        );
    }
}
~~~

Ví dụ:

~~~java
Instant timestampForWrite = Instant.now();
long writeTimestampMicros =
        WriteTimestamps.toEpochMicros(timestampForWrite);

// Giá trị này chỉ dùng nếu nghiệp vụ yêu cầu tự gán write timestamp.
repository.updateStatusWithExpiry(
    3600,
    writeTimestampMicros,
    "PROCESSED",
    tenantId,
    eventDay,
    occurredAt,
    eventId
);
~~~

**Không khuyến khích tự cấp timestamp cho mọi thao tác một cách máy móc.** Đồng hồ của nhiều instance có thể lệch nhau. Nếu một writer vô tình ghi write timestamp quá xa trong tương lai, những ghi bình thường về sau có thể thua giá trị cũ trong một thời gian dài. Đồng bộ thời gian, chính sách retry và chọn timestamp cần được xác định rõ nếu hệ thống thực sự phải kiểm soát timestamp.

## 10. Retention theo event time và dữ liệu đến muộn

Giả sử hợp đồng nghiệp vụ là **giữ sự kiện 30 ngày kể từ khi xảy ra**, không phải 30 ngày kể từ khi worker nhận được nó. Nếu sự kiện được ghi trễ hai ngày, TTL cho lần ghi phải tính theo **thời gian còn lại**.

Ví dụ lớp service tính TTL gần đúng với độ phân giải giây:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

public final class Retention {

    public static int remainingTtlSeconds(
            Instant occurredAt, Instant now) {

        Instant expiresAt = occurredAt.plus(30, ChronoUnit.DAYS);
        long seconds = Duration.between(now, expiresAt).getSeconds();

        if (seconds <= 0) {
            throw new IllegalArgumentException(
                "Sự kiện đã hết thời gian lưu giữ");
        }
        if (seconds > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("TTL vượt giới hạn");
        }
        return Math.toIntExact(seconds);
    }
}
~~~

Trong triển khai thực tế cần kiểm tra mức TTL tối đa của Cassandra/version và **chính sách làm tròn** khi chỉ còn một phần giây. Clock skew giữa ứng dụng và cluster cũng có thể tạo chênh lệch nhỏ; nếu yêu cầu hạn hết hạn chính xác chặt chẽ, cần thiết kế kiểm soát bổ sung thay vì chỉ dựa vào TTL.

Nếu sự kiện đã quá hạn trước khi nhận, có thể **bỏ qua ghi**, đưa vào hàng đợi xử lý riêng hoặc ghi vào kho lưu trữ khác tùy nghiệp vụ. Không biến TTL âm thành một giá trị hợp lệ, cũng không cho phép một sự kiện cũ tái xuất hiện vô thời hạn chỉ vì mới được replay.

### Vì sao không dùng event time làm write timestamp?

Một sự kiện đến muộn có thể mang `occurred_at` trước thời điểm một service khác đã cập nhật cùng cell. Nếu dùng event time làm `USING TIMESTAMP`, bản ghi đến muộn **có thể thua** theo quy tắc last-write-wins ngay cả khi đây là lần xử lý mới nhất về mặt hệ thống.

**Event time**, **processing time**, **retention deadline** và **write timestamp** là bốn khái niệm khác nhau; chỉ gộp chúng nếu có thiết kế nghiệp vụ rõ ràng về ordering và conflict resolution.

## 11. Kiểm tra TTL và write timestamp sau khi ghi

Cassandra cung cấp các hàm hữu ích để quan sát những cột đơn giản:

~~~sql
SELECT
    status,
    TTL(status),
    WRITETIME(status)
FROM activity_ks.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?;
~~~

Ý nghĩa:

- `TTL(status)` trả số giây còn lại của giá trị `status` nếu có TTL áp dụng; khi không có TTL, kết quả thường là `null`.
- `WRITETIME(status)` thể hiện write timestamp của cell `status`, ở đơn vị micro giây.
- Các hàm này không phải phép tính cho toàn bộ entity; những cột được ghi vào các thời điểm khác nhau có thể có TTL/write timestamp khác nhau.

Kiểm thử có thể đi theo trình tự:

1. Tạo một event với TTL ngắn **chỉ trong môi trường thử nghiệm**, ví dụ 120 giây.
2. Đọc `TTL(status)` ngay sau ghi; kỳ vọng giá trị gần 120 và giảm dần theo thời gian.
3. Đọc `WRITETIME(status)`, xác minh đơn vị micro giây và giá trị tương ứng với write timestamp được yêu cầu nếu đã dùng `USING TIMESTAMP`.
4. Thử update **chỉ cột `status`** với TTL khác, đối chiếu với `TTL(details)` để nhận thấy mỗi cột có vòng đời riêng.
5. Thực hiện một ghi có write timestamp thấp hơn cell hiện có trong môi trường test; quan sát liệu giá trị mới có thực sự thắng không.
6. Kiểm tra dữ liệu sau khi TTL hết hạn, đồng thời hiểu rằng giải phóng dung lượng đĩa còn phụ thuộc compaction.

Khi dùng Java Driver hoặc `CqlTemplate` để gọi hàm hệ thống, đừng nhầm `WRITETIME` của cell với ngày hiển thị của `occurred_at`. Các phép `TTL()`/`WRITETIME()` có hạn chế đối với một số cấu trúc phức hợp/collection và cột đặc biệt; ví dụ trên cố ý dùng cột scalar `status text`.

## 12. TTL mặc định của bảng và TTL trong câu ghi

Cassandra còn có table option **`default_time_to_live`**. Ví dụ:

~~~sql
ALTER TABLE activity_ks.events_by_tenant_day
WITH default_time_to_live = 604800;
~~~

Đây là ví dụ chính sách mặc định **7 ngày** cho các ghi phù hợp; không nên áp dụng bừa bãi lên một bảng sản xuất. Thay đổi option có thể ảnh hưởng các ghi tương lai, nhưng **không tự cập nhật toàn bộ TTL của dữ liệu đã có**.

So sánh:

| Cơ chế | Ai quyết định? | Phạm vi |
| --- | --- | --- |
| `default_time_to_live` | Cấu hình bảng | Chính sách TTL mặc định cho những ghi thuộc phạm vi áp dụng |
| `USING TTL ...` | Câu `INSERT`/`UPDATE` | TTL tường minh cho các giá trị được ghi bởi câu đó |
| Không dùng TTL | Câu ghi/tham số mặc định | Có thể không có TTL, trừ khi table default quy định khác |

Khi ứng dụng ghi dữ liệu quan trọng, đừng cho rằng “không truyền TTL” luôn đồng nghĩa “sống mãi”: **table default TTL** có thể đang được bật. Việc dùng TTL bằng 0 để xóa TTL hoặc override mặc định có ngữ nghĩa/ràng buộc riêng theo phiên bản và policy; hãy kiểm chứng trước khi triển khai.

Tương tự, không chọn TTL lớn chỉ vì muốn tránh tombstone. TTL, compaction và giữ dữ liệu là quyết định vận hành phải đo trên workload thực tế.

## 13. Retry, consistency và timestamp trong hệ phân tán

Giả sử một client ghi `status='READY'` với timestamp T1; client khác ghi `status='PROCESSED'` với timestamp T2. Cassandra so sánh phiên bản giá trị theo timestamp của các ghi, chứ không mặc định theo thứ tự request được ứng dụng gửi hoặc thời gian HTTP response tới client.

~~~text
Writer A: status=READY,     write timestamp=T1
Writer B: status=PROCESSED, write timestamp=T2

Nếu T2 > T1: PROCESSED có thể thắng theo write timestamp.
Nếu T2 < T1: ghi của B có thể không thay giá trị hiện tại.
Nếu T2 = T1: quy tắc tie-break cần được xét; tránh cố ý tạo xung đột.
~~~

**Consistency level** quyết định số replica phải phản hồi cho yêu cầu đọc/ghi, không biến write timestamp thành thứ tự giao dịch toàn cục. Với replication factor 3 trong một datacenter, `LOCAL_QUORUM` cần phản hồi từ đa số replica cục bộ (2/3), nhưng độ đúng còn phụ thuộc workload, lỗi và cách chọn write timestamp.

**Timeout không khẳng định ghi chưa xảy ra.** Một request có thể đã tới một số replica trước khi client hết thời gian chờ. Retry cần cân nhắc:

- Giữ **primary key ổn định**, không phát sinh `event_id` mới cho mỗi lần retry cùng một sự kiện.
- Nếu tự gán timestamp với mục tiêu idempotency, giữ quy tắc chọn timestamp nhất quán; nhưng không dùng cùng timestamp với hai giá trị khác nhau một cách vô tình.
- Ghi với TTL ở nhiều thời điểm khác nhau có thể làm thay đổi thời điểm hết hạn; kiểm thử các lần replay/ghi lại.
- Không để một timestamp quá cao “khóa” các lần cập nhật hợp lệ về sau.
- Nếu cần conditional write/LWT, kiểm tra tính tương thích của client-supplied timestamps với loại conditional statement và Cassandra version; không mặc định kết hợp tùy ý.

**`@Query` và `@Modifying` không cung cấp transaction ACID nhiều bảng**. Nếu cập nhật đồng thời nhiều bảng đọc denormalized, ứng dụng vẫn cần thiết kế đồng bộ, retry và reconciliation.

## 14. Cách áp dụng trong Spring Data Cassandra

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Ghi theo entity, không cần TTL/timestamp đặc biệt | `CassandraRepository.save(...)` | Đơn giản, dùng mapping có sẵn |
| Ghi một cột với TTL theo từng request | `@Modifying` + `@Query` UPDATE tường minh | Kiểm soát cột chịu TTL và bind giá trị |
| INSERT với TTL và timestamp chỉ định rõ | `@Modifying` + `@Query` INSERT tường minh | Rõ mệnh đề `USING` và kiểu tham số |
| Ghi nhiều field theo entity, cần options | `CassandraTemplate` với write options được version hỗ trợ | Tận dụng mapping và kiểm soát tùy chọn ghi |
| CQL/statement đặc biệt, mã hóa tham số chi tiết | `CqlTemplate` hoặc Java Driver `CqlSession` | Chủ động bind, consistency, timeout, timestamp |
| Tầng reactive | `ReactiveCassandraRepository` / `ReactiveCassandraTemplate` | Cùng ngữ nghĩa CQL, khác mô hình thực thi |

Khi dùng `@Query` trong repository, hãy đảm bảo statement đã được tham số hóa và các giá trị đầu vào được validate. Tên bảng/cột không thể thay bằng bind marker tùy tiện; chỉ **giá trị** là đối tượng bind thông thường.

Một số version Spring Data Cassandra cung cấp API/annotation riêng để áp dụng TTL hoặc write timestamp trên thao tác entity. Tuy nhiên điều đó **không thay thế** việc hiểu CQL thực tế khi nghiệp vụ cần cập nhật một cột hay gán timestamp theo một quy tắc cụ thể.

## 15. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Truyền TTL theo mili giây | Thời hạn lớn hơn dự định rất nhiều | TTL trong CQL là **giây** |
| Truyền `System.currentTimeMillis()` trực tiếp làm write timestamp | Timestamp nhỏ hơn thời gian hiện tại khoảng 1.000 lần | Chuyển chính xác sang **micro giây** |
| Nghĩ `USING TIMESTAMP` ghi vào cột `occurred_at` | Cột sự kiện và write timestamp có mục đích khác | Bind cột thời gian sự kiện riêng |
| Dùng TTL 7 ngày cho sự kiện đến muộn khi retention theo event time | Dữ liệu tồn tại lâu hơn hợp đồng | Tính TTL còn lại đến deadline |
| Dùng TTL cho `DELETE` | Không đúng mục đích/cú pháp CQL | Dùng TTL khi INSERT/UPDATE; DELETE có thể dùng timestamp |
| Nghĩ TTL áp dụng cho toàn partition | Một partition có thể có nhiều cell TTL khác nhau | Kiểm tra phạm vi câu ghi và `TTL(column)` |
| Nghĩ TIMESTAMP cao luôn tốt | Write tương lai có thể đè các ghi hợp lệ về sau | Chỉ cấp timestamp có chiến lược, đồng bộ clock |
| Coi `@Modifying` như transaction | Nhiều ghi và read-before-write vẫn có race | Xử lý consistency, LWT đúng chỗ, reconciliation |
| Nghĩ timeout là chắc chắn ghi thất bại | Có thể retry tạo ghi ngoài ý muốn | Dùng khóa ổn định, hiểu idempotency |
| Đổi TTL trong UPDATE rồi mong mọi cột được gia hạn | Cột không được ghi lại không tự thay TTL | Update rõ các cột cần gia hạn |
| Nghĩ TTL hết hạn thì disk giảm ngay | Tombstone/compaction cần thời gian | Theo dõi metrics và compaction |
| Chọn `@Query` nhưng bỏ partition key | CQL không phù hợp data model | Ghi theo full key, thiết kế bảng theo truy vấn |

## 16. Quy trình kiểm thử end-to-end

Với cluster test và Spring Data Cassandra phù hợp phiên bản:

1. **Chuẩn bị schema:** tạo keyspace/bảng ở mục 2, kiểm tra replica/datacenter, không chạy các DDL phá hủy trên dữ liệu production.
2. **Ghi bằng repository:** gọi `insertWithExpiry(...)` với một `event_id` cố định, TTL 120 giây, timestamp micro giây hợp lệ.
3. **Đọc bằng CQL:** xác minh `status` và dùng `TTL(status)`, `WRITETIME(status)` để kiểm chứng.
4. **Partial update:** gọi `updateStatusWithExpiry(...)` với một TTL khác và timestamp đủ mới; kiểm tra `status` thay đổi mà `details` không bị ghi lại ngoài ý muốn.
5. **Thử ghi timestamp cũ:** cố tình dùng timestamp thấp hơn trong môi trường test, quan sát quy tắc phân giải ghi.
6. **Kiểm tra hết hạn:** xác minh dữ liệu sống không còn được trả về sau hạn TTL; không dùng việc dung lượng đĩa chưa giảm để kết luận TTL thất bại.
7. **Kiểm tra ranh giới thời gian:** sự kiện xảy ra sát nửa đêm UTC và đến muộn; đảm bảo `event_day` đúng partition và TTL đúng deadline retention.
8. **Thử retry:** dùng lại khóa và thông tin ghi theo chính sách idempotency; đo xung đột timestamp và tình huống timeout.
9. **Kiểm tra pagination:** truy vấn nhiều hàng trong partition bằng paging state, không suy ra rằng TTL hoặc timestamp sửa được partition quá lớn.

### Câu hỏi tự kiểm tra

**Câu 1.** `USING TTL 300` nghĩa là 300 mili giây hay 300 giây?

**Đáp án:** 300 **giây**. TTL là thời gian sống, không phải timestamp tuyệt đối.

**Câu 2.** `USING TIMESTAMP 1795593600000000` có tự ghi giá trị đó vào cột `occurred_at` không?

**Đáp án:** Không. Nó là write timestamp dùng khi phân giải ghi. Cột `occurred_at` cần được gán/bind riêng.

**Câu 3.** Khi `UPDATE ... USING TTL 3600 SET status = 'READY' ...`, liệu `details` có tự được gia hạn TTL không?

**Đáp án:** Không mặc định. TTL áp dụng cho các giá trị được ghi trong câu lệnh, ở đây là `status`.

**Câu 4.** Tại sao replay sự kiện đến muộn không nên mặc định dùng `occurred_at` làm `USING TIMESTAMP`?

**Đáp án:** Vì timestamp cũ có thể thua cập nhật đã lưu, bất kể replay xảy ra mới hơn ở tầng ứng dụng. Event time và write timestamp có vai trò khác nhau.

**Câu 5.** Dùng `@Query` cho INSERT/UPDATE cần chú ý annotation và binding nào?

**Đáp án:** Dùng `@Modifying` theo version Spring Data Cassandra, bind từng giá trị vào đúng marker, đảm bảo TTL là số giây, timestamp là số micro giây, và CQL có điều kiện khóa đầy đủ.

**Câu 6.** Làm sao kiểm tra TTL thực tế của cột `status`?

**Đáp án:** Dùng `TTL(status)` để quan sát số giây còn lại và `WRITETIME(status)` để kiểm tra write timestamp của cell; thử trên dữ liệu test có schema và version phù hợp.

---

**Ghi nhớ:** **`USING TTL`** quyết định thời gian tồn tại của **giá trị được ghi**, tính bằng **giây**; **`USING TIMESTAMP`** quyết định write timestamp cho phân giải các phiên bản ghi, tính bằng **micro giây**. Trong Spring Data Cassandra, kết hợp `@Modifying` và `@Query` giúp thể hiện rõ CQL `INSERT`/`UPDATE`, nhưng vẫn cần chuẩn hóa kiểu tham số, phân biệt event time với write time, kiểm soát retry/consistency, giới hạn partition và kiểm thử bằng `TTL()`/`WRITETIME()` trước khi triển khai thực tế.
