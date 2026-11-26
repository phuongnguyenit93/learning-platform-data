# Replication factor và consistency level của thao tác

Trong **Apache Cassandra**, một partition thường có nhiều bản sao (*replica*) được lưu trên những node khác nhau. **Replication factor (RF)** cho biết số replica mục tiêu của dữ liệu theo cấu hình keyspace; **consistency level (CL)** cho biết mức phản hồi cần có từ các replica trước khi một **thao tác đọc/ghi** được coi là hoàn tất. Hai khái niệm liên quan nhưng không thay thế cho nhau.

Bài thuộc chương **Tính nhất quán** của module **SPRING_DATA_CASSANDRA**. Ta sẽ xem cách thiết lập RF bằng CQL, tính quorum, so sánh các mức CL trong một hoặc nhiều datacenter, xử lý lỗi và timeout, rồi áp dụng bằng Spring Data Cassandra, `CassandraTemplate` và Java Driver. Mục tiêu không phải chọn mức CL cao nhất, mà chọn **đánh đổi phù hợp giữa khả năng đọc dữ liệu mới, độ trễ và tính sẵn sàng** theo yêu cầu nghiệp vụ.

## 1. Ba lớp cần phân biệt: partition, replication và consistency

Cassandra xác định nhóm replica của một partition từ **partition key** và topology/token ring. Một query đi qua **coordinator**, sau đó coordinator điều phối các replica liên quan. RF và CL tác động ở hai lớp:

~~~text
Ứng dụng Spring Data Cassandra
             |
       CqlSession / Driver
             |
             v
        Coordinator
             |
   +---------+---------+
   |         |         |
   v         v         v
Replica A Replica B Replica C

RF=3              : mục tiêu có ba replica cho partition
CL=ONE            : cần một replica phản hồi
CL=LOCAL_QUORUM   : cần hai trong ba replica ở DC cục bộ
CL=ALL            : cần cả ba replica phản hồi
~~~

Coordinator **không nhất thiết là một replica** của partition. Các replica đích còn được chọn theo replication strategy và topology. CL không có nghĩa Cassandra chỉ gửi mutation đến đúng số replica cần xác nhận; đó là số phản hồi cần thiết để **trả kết quả theo mức CL**.

| Câu hỏi | Khái niệm trả lời |
| --- | --- |
| Partition nằm ở những node nào? | Partition key, token ring, replication strategy |
| Mỗi partition có mục tiêu bao nhiêu bản sao? | **RF** của keyspace |
| Lần ghi này cần bao nhiêu replica báo thành công? | **Write CL** của statement |
| Lần đọc này cần bao nhiêu replica phản hồi? | **Read CL** của statement |
| Có thể ghi có điều kiện dựa trên giá trị cũ không? | LWT/serial consistency, không chỉ CL thường |

## 2. Định nghĩa bảng theo truy vấn

Giả sử ứng dụng quản lý lịch sử sự kiện thiết bị, thường đọc **những sự kiện gần nhất của một thiết bị trong một ngày**.

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS telemetry_ks.events_by_device_day (
    device_id   text,
    event_day   date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY ((device_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC);
~~~

Phân tích khóa:

- `(device_id, event_day)` là **composite partition key**; dữ liệu một thiết bị trong một ngày cùng thuộc một partition.
- `occurred_at` và `event_id` là **clustering columns**; thứ tự các hàng trong partition là thời điểm giảm dần, tiếp theo là ID để phân biệt các sự kiện cùng thời điểm.
- `event_type` và `payload` là cột thường. Chúng không tham gia phân phối replica.
- `dc1: 3` là mục tiêu ba bản sao **trong datacenter dc1**; ví dụ này giả định dc1 thực sự có đủ node.

Truy vấn đúng access pattern:

~~~sql
SELECT occurred_at, event_id, event_type
FROM telemetry_ks.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Một truy vấn thiếu `device_id` hoặc `event_day` không được sửa bằng việc tăng CL. **CL quyết định phản hồi replica, không thay đổi quy tắc WHERE/partition key của Cassandra.**

## 3. RF được khai báo trên keyspace, không phải entity

RF nằm trong cấu hình replication của **keyspace**. Với `NetworkTopologyStrategy`, có thể đặt số bản sao theo từng datacenter. Một số ví dụ:

~~~sql
-- Một datacenter.
CREATE KEYSPACE sample_dc1
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

-- Hai datacenter.
CREATE KEYSPACE sample_two_dc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Hai câu trên minh họa ý nghĩa RF, không phải một yêu cầu tạo các keyspace phụ trong dự án. Để kiểm tra keyspace thực tế:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'telemetry_ks';
~~~

Hoặc trong tiện ích `cqlsh`:

~~~text
DESCRIBE KEYSPACE telemetry_ks;
~~~

`DESCRIBE` là lệnh của `cqlsh`, không phải CQL tiêu chuẩn có thể gửi nguyên văn qua mọi API Java Driver.

### RF không bằng số node và cũng không phải số partition

| Topology | RF(dc1) | Điều cần hiểu |
| --- | ---: | --- |
| dc1 có 5 node | 3 | Một partition được nhắm tới ba node phù hợp, không phải cả năm |
| dc1 có 3 node | 3 | Một partition có mục tiêu bản sao trên cả ba node |
| dc1 chỉ có 1 node | 3 | Không thể có ba replica độc lập trong một DC chỉ có một node |
| dc1 có 4 node, dc2 có 4 node | 3 tại mỗi DC | Mục tiêu ba replica ở dc1 và ba ở dc2 |

**Thêm node không tự tăng RF.** Thay đổi RF cũng không có nghĩa mọi bản sao bổ sung đã đồng bộ đầy đủ ngay lập tức; cần quy trình streaming/repair và xác minh topology theo phiên bản Cassandra. Trong production, phối hợp với người vận hành trước khi chạy `ALTER KEYSPACE` hoặc thay đổi nhiều replica.

## 4. CL là lựa chọn theo thao tác

Khác RF, consistency level được áp dụng **theo request**, theo statement hoặc theo execution profile/cấu hình mặc định của Java Driver.

~~~text
Ứng dụng ghi event        -> LOCAL_QUORUM
Dashboard đọc event       -> LOCAL_ONE
API đọc trạng thái mới    -> LOCAL_QUORUM
Job xóa dữ liệu hết hạn   -> LOCAL_QUORUM (tùy nhu cầu)
~~~

Đây chỉ là các ví dụ để thảo luận, không phải công thức dùng cho mọi hệ thống. Mỗi thao tác có thể có yêu cầu khác nhau về tính mới của dữ liệu, độ trễ, khả năng chịu lỗi và chi phí.

Với RF=3, ghi ở CL=ONE **không chứng minh** mọi replica đều đã nhận mutation trước lúc client nhận phản hồi thành công. Tương tự, đọc ở CL=ONE có thể được phục vụ từ replica chưa thấy lần ghi gần nhất.

## 5. Những consistency level phổ biến

| CL | Đọc hay ghi? | Điều kiện phản hồi chính | Đánh đổi quan trọng |
| --- | --- | --- | --- |
| `ONE` | Đọc, ghi | 1 replica | Có thể nhanh/khả dụng hơn, nhưng dễ thấy dữ liệu cũ |
| `TWO` | Đọc, ghi | 2 replica | Số lượng cố định, không tự điều chỉnh theo RF |
| `THREE` | Đọc, ghi | 3 replica | Cần đủ replica đáp ứng |
| `QUORUM` | Đọc, ghi | Đa số trong phạm vi **tổng RF** liên quan | Với nhiều DC, có thể phụ thuộc replica xa |
| `LOCAL_ONE` | Đọc, ghi | 1 replica trong DC cục bộ | Giảm phụ thuộc DC xa |
| `LOCAL_QUORUM` | Đọc, ghi | Đa số replica của DC cục bộ | Phổ biến khi ứng dụng đặt gần một DC |
| `EACH_QUORUM` | Ghi | Quorum tại **mỗi** DC | Giảm khả năng ghi nếu một DC không đáp ứng |
| `ALL` | Đọc, ghi | Tất cả replica liên quan | Nhạy với node lỗi hoặc chậm |
| `ANY` | Chỉ ghi | Có thể được xác nhận bằng hint | Không bảo đảm đọc ngay thấy ghi đó |
| `SERIAL` / `LOCAL_SERIAL` | Pha tuần tự hóa LWT | Điều phối Paxos cho thao tác có điều kiện | Không thay thế read/write CL thông thường |

Mỗi phiên bản Cassandra có những tính năng và giới hạn cụ thể cần đối chiếu theo phiên bản đang chạy. Đặc biệt, `ANY` không phải CL dành cho `SELECT` và việc một hint được chấp nhận không có nghĩa dữ liệu đã được ghi vào replica đích. Hinted handoff không thay thế quy trình repair.

## 6. Tính quorum từ RF

Quorum là **đa số** replica trong phạm vi đang xét:

\[
Q = \left\lfloor\frac{RF}{2}\right\rfloor + 1
\]

| RF | Quorum |
| ---: | ---: |
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 3 |

Ví dụ với một DC có RF=3:

~~~text
Replica A: phản hồi thành công
Replica B: phản hồi thành công
Replica C: chưa phản hồi

ONE          -> đủ (1 trong 3)
LOCAL_QUORUM -> đủ (2 trong 3)
ALL          -> chưa đủ (3 trong 3)
~~~

Quorum không phải “đa số node của cả cluster”, vì mỗi partition có tập replica riêng. `LOCAL_QUORUM` được tính theo RF của **DC cục bộ**, còn `QUORUM` dùng tổng RF liên quan đến keyspace trong cấu hình nhiều DC.

## 7. Hai datacenter: LOCAL_QUORUM khác QUORUM

Giả sử keyspace có:

~~~sql
CREATE KEYSPACE telemetry_two_dc
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

~~~text
Datacenter dc1                    Datacenter dc2
   A     B     C                     X     Y     Z
   |     |     |                     |     |     |
   +-----+-----+                     +-----+-----+
       RF=3                              RF=3

LOCAL_QUORUM tại dc1: cần 2 replica dc1
LOCAL_QUORUM tại dc2: cần 2 replica dc2
QUORUM toàn cục:       cần 4 replica trên tổng 6
EACH_QUORUM (write):   cần 2 replica dc1 VÀ 2 replica dc2
ALL:                   cần cả 6 replica
~~~

Không nhầm `EACH_QUORUM` với `QUORUM`: cả hai có thể cần ít nhất bốn phản hồi trong ví dụ này, nhưng **EACH_QUORUM có yêu cầu riêng từng DC**, còn QUORUM tính theo tổng.

Nếu ứng dụng và coordinator ở dc1, `LOCAL_QUORUM` thường không phải chờ hai replica dc2 để báo thành công. Điều đó giúp giảm phụ thuộc vào mạng xuyên datacenter, **nhưng không bảo đảm dữ liệu đã được replica dc2 ghi xong** lúc ứng dụng dc1 nhận acknowledgment.

Nếu hệ thống chuyển traffic từ dc1 sang dc2 sau sự cố, phải xác định yêu cầu RPO/RTO và nguy cơ những mutation chỉ mới được xác nhận ở dc1. Không thiết kế failover đa vùng chỉ từ bảng CL; cần kiểm thử thời gian propagation và kịch bản mất kết nối thực tế.

## 8. R + W > RF: giao nhau giữa nhóm đọc và nhóm ghi

Gọi `W` là số replica cần phản hồi cho một **write**, `R` là số replica cần phản hồi cho một **read** trong cùng phạm vi RF. Nếu:

\[
R + W > RF
\]

thì hai tập replica phản hồi phải có ít nhất một replica **giao nhau** theo phép đếm.

| RF | Write CL (W) | Read CL (R) | R + W | Có giao nhau chắc chắn? |
| ---: | --- | --- | ---: | --- |
| 3 | ONE (1) | ONE (1) | 2 | Không |
| 3 | ONE (1) | QUORUM (2) | 3 | Không |
| 3 | QUORUM (2) | ONE (1) | 3 | Không |
| 3 | QUORUM (2) | QUORUM (2) | 4 | **Có** |
| 3 | ALL (3) | ONE (1) | 4 | **Có** |

Đây là lý do RF=3 kết hợp **write LOCAL_QUORUM và read LOCAL_QUORUM** được cân nhắc khi cần đọc gần với trạng thái vừa ghi trong **cùng DC**.

### Công thức này KHÔNG biến Cassandra thành SQL transaction

Lập luận giao nhau phụ thuộc các giả định phù hợp và không tự bảo đảm:

- Không có writer khác đang ghi đè hoặc xóa cùng cell.
- Giá trị được chọn theo đúng “thời điểm request đến server”; Cassandra còn dùng **write timestamp** và quy tắc tie-break.
- Một chuỗi read-check-update là thao tác nguyên tử.
- Mọi datacenter có dữ liệu đồng bộ ngay sau khi một DC trả thành công.
- Phân trang nhiều request cung cấp snapshot bất biến.

Nếu nghiệp vụ cần so sánh/đổi giá trị một cách nguyên tử, phải xem xét **lightweight transaction (LWT)**, thay vì chỉ tăng CL.

## 9. Khi replica bị lỗi, CL ảnh hưởng thế nào?

Giả sử một partition có RF=3 ở dc1, trong đó A và B còn hoạt động, C bị down:

~~~text
A: UP    B: UP    C: DOWN
RF=3
~~~

| CL | Số phản hồi cần | Kết quả có thể xảy ra |
| --- | ---: | --- |
| `ONE` | 1 | Có thể thành công nhờ A hoặc B |
| `LOCAL_QUORUM` | 2 | Có thể thành công nếu A và B phản hồi đúng hạn |
| `ALL` | 3 | Không thể đáp ứng vì C không phản hồi |

Nếu **chỉ còn một replica** của partition hoạt động, `LOCAL_QUORUM` (2/3) sẽ không đủ phản hồi, còn `ONE` có thể vẫn phục vụ một số thao tác. Đây là đánh đổi **availability và consistency**, không phải căn cứ để hạ CL toàn hệ thống một cách tự động khi xảy ra sự cố.

Ngay cả khi đủ số node sống, request vẫn có thể timeout vì mạng chậm, coordinator/replica quá tải, tombstone nhiều hoặc partition nóng. **Có đủ replica theo lý thuyết không bảo đảm mọi request thành công.**

## 10. Ghi và đọc qua coordinator

### Ghi

Client gửi mutation tới coordinator; coordinator xác định replica của partition, chuyển mutation tới các node cần thiết và thu nhận phản hồi.

~~~text
UPDATE status=PROCESSED
      |
      v
  Coordinator
   /   |    \
  v    v     v
  A    B     C
 ack  ack  timeout

RF=3 / LOCAL_QUORUM -> có thể hoàn tất
RF=3 / ALL          -> không đủ ack
~~~

Ở replica, Cassandra sử dụng cơ chế lưu ghi như commit log/memtable theo phiên bản/cấu hình. CL xác định thời điểm request được báo thành công, **không phải lời hứa rằng tất cả replica đã đồng bộ ngay**.

### Đọc

Coordinator phối hợp các phản hồi cần thiết, và Cassandra hòa giải dữ liệu theo timestamp/tombstone. Một lần đọc CL thấp có thể nhận dữ liệu từ replica chưa theo kịp ghi gần nhất:

~~~text
T0: Replica A nhận ghi event-123 ở CL=ONE
T1: Replica B chưa thấy mutation mới
T2: Một SELECT CL=ONE được phục vụ từ B
T3: Client có thể tạm thời thấy bản cũ hoặc chưa thấy hàng
~~~

Đọc/ghi ở CL quorum trong cùng phạm vi tạo khả năng giao nhau replica tốt hơn, nhưng **concurrent writes, timestamp và xóa/TTL** vẫn phải được xét riêng.

## 11. Timeout không đồng nghĩa mutation chưa được ghi

Ví dụ:

~~~text
Client ghi event-123 với CL=LOCAL_QUORUM
  - Replica A nhận mutation
  - Replica B nhận chậm
  - Client hết thời gian chờ phản hồi

Điều client biết: không nhận xác nhận CL đúng hạn.
Điều client CHƯA biết chắc: dữ liệu đã tới đâu, request có thể đã hoàn tất muộn hay không.
~~~

Hệ quả:

1. **Đừng sinh ID mới cho cùng một sự kiện mỗi lần retry**, nếu muốn tránh tạo nhiều hàng với các primary key khác nhau.
2. Phân biệt `UnavailableException` (thiếu replica đủ theo nhận định coordinator) với read/write timeout và lỗi mạng; cách xử lý có thể khác.
3. Chỉ tự động retry statement thực sự **idempotent** và có chính sách giới hạn số lần/timeout.
4. Counter, list mutation, LWT và side effect ngoài Cassandra không có cùng ngữ nghĩa retry như một upsert theo khóa ổn định.
5. Nếu cần biết kết quả, đọc kiểm tra đúng primary key với CL phù hợp, kết hợp quy tắc nghiệp vụ và reconciliation khi cần.

Không tự cho rằng tăng CL sẽ chữa được timeout do partition nóng hay query không phù hợp schema. Cần phân tích số replica, tải coordinator, packet loss, latency, tombstone và backpressure.

## 12. Áp dụng CL với Java Driver trong Spring Boot

Spring Boot 3.x thường dùng starter đồng bộ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Ví dụ cấu hình session:

~~~yaml
spring:
  cassandra:
    contact-points: cassandra-dc1.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: telemetry_ks
    schema-action: none
~~~

Trong Java Driver 4.x, đặt CL trên một bound statement:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class EventReader {
    private final CqlSession session;
    private final PreparedStatement recent;

    public EventReader(CqlSession session) {
        this.session = session;
        this.recent = session.prepare("""
            SELECT occurred_at, event_id, event_type
            FROM telemetry_ks.events_by_device_day
            WHERE device_id = ? AND event_day = ?
            LIMIT 50
            """);
    }

    public ResultSet read(String deviceId, LocalDate day) {
        BoundStatement statement = recent.bind(deviceId, day)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(25);

        return session.execute(statement);
    }
}
~~~

Ở đây:

- `CqlSession` nên được Spring quản lý và tái sử dụng, không tạo lại trên từng request.
- `LOCAL_QUORUM` chỉ áp dụng cho **statement** đang chạy, không cập nhật replication strategy của keyspace.
- `setPageSize(25)` điều chỉnh fetch size, không thay đổi CL và không tạo transaction snapshot.
- Prepared statement giúp tái sử dụng query/bind đúng kiểu nhưng **không sửa được câu SELECT thiếu partition key**.

Ghi có thể chọn mức CL riêng:

~~~java
PreparedStatement update = session.prepare("""
    UPDATE telemetry_ks.events_by_device_day
    SET event_type = ?
    WHERE device_id = ?
      AND event_day = ?
      AND occurred_at = ?
      AND event_id = ?
    """);

BoundStatement write = update.bind(
    newEventType, deviceId, day, occurredAt, eventId
).setConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_QUORUM
);

session.execute(write);
~~~

Các biến như `newEventType`, `occurredAt`, `eventId` cần có đúng kiểu Java/CQL và được khai báo trong phương thức sử dụng. CQL trên dùng **đầy đủ primary key**; ghi `UPDATE` vẫn thường là upsert, không mặc định kiểm tra hàng đã tồn tại.

Driver còn hỗ trợ **execution profiles** để áp dụng CL mặc định theo nhóm request. Cần đối chiếu namespace cấu hình, profile và API của đúng phiên bản driver/Spring Boot trước khi đưa vào production.

## 13. Repository, CassandraTemplate và CL

Ví dụ khai báo entity/repository theo composite key:

~~~java
@PrimaryKeyClass
public class EventKey implements Serializable {
    @PrimaryKeyColumn(name = "device_id", ordinal = 0,
                      type = PrimaryKeyType.PARTITIONED)
    private String deviceId;

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

    // Constructor/getter/setter/equals/hashCode phù hợp.
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

Các import và phần Java boilerplate đã lược bỏ; ví dụ cần tách class thành file phù hợp, hoàn thiện constructor/accessor và kiểm tra mapping trên phiên bản Spring Data Cassandra dự án.

Repository thông thường:

~~~java
public interface EventRepository
        extends CassandraRepository<EventRow, EventKey> {

    @Query("""
        SELECT * FROM events_by_device_day
        WHERE device_id = ?0 AND event_day = ?1
        LIMIT 50
        """)
    List<EventRow> recentByDeviceAndDay(
        String deviceId, LocalDate day);
}
~~~

**Tên method hay annotation `@Query` không tự chọn RF hoặc CL.** RF thuộc keyspace; CL thường lấy từ cấu hình driver/execution profile hoặc options được phiên bản Spring Data Cassandra hỗ trợ. `CassandraTemplate` và `CqlTemplate` là các mức API khác nhau nhưng vẫn thực thi qua driver và **cùng giới hạn CQL/consistency**.

Nếu cần đặt CL cực kỳ rõ ràng cho một thao tác mà repository/template chưa cung cấp options tiện lợi, có thể dùng `CqlSession` và `BoundStatement` như ví dụ phần trước. Không tự bịa một YAML property rồi kỳ vọng tất cả repository method sẽ dùng CL đó.

## 14. Chọn CL theo access pattern và nghiệp vụ

| Trường hợp | Hướng cân nhắc | Rủi ro cần hiểu |
| --- | --- | --- |
| Dashboard telemetry chấp nhận trễ vài giây | Đọc `LOCAL_ONE` | Có thể thấy dữ liệu cũ |
| Xem ngay trạng thái vừa ghi trong cùng DC | Ghi và đọc `LOCAL_QUORUM` khi RF local=3 | Quorum giao nhau dưới giả định phù hợp, không phải transaction |
| Ghi sự kiện với ID ổn định, có retry | CL theo SLO, thường cân nhắc `LOCAL_QUORUM` | Timeout không chứng minh chưa ghi |
| Ghi và đọc trên hai DC khác nhau | Thiết kế RF/CL và failover đa DC riêng | LOCAL_QUORUM ở DC ghi không buộc DC đọc đã theo kịp |
| Cần so sánh điều kiện trước khi cập nhật | **LWT**, không chỉ CL cao | Chi phí đồng thuận, độ trễ |
| Bất cứ replica nào lỗi đều muốn request thất bại | `ALL` trong trường hợp đặc biệt | Tính sẵn sàng thấp |

**LOCAL_QUORUM thường có ích cho ứng dụng gắn với một DC**, nhưng không phải đáp án đúng tuyệt đối. Chọn CL dựa trên RPO/RTO, số node, độ trễ liên vùng, SLA, mức chấp nhận đọc cũ và khả năng phục hồi khi replica down.

## 15. Vì sao CL cao không đủ cho compare-and-set?

Giả sử hai request cùng đọc trạng thái `NEW` rồi muốn đổi thành `PROCESSED` và `CANCELLED`. Kể cả `LOCAL_QUORUM`, chuỗi **read → kiểm tra trong Java → update** vẫn có race condition.

Cassandra cung cấp **lightweight transaction (LWT)**:

~~~sql
UPDATE telemetry_ks.events_by_device_day
SET event_type = 'PROCESSED'
WHERE device_id = ?
  AND event_day = ?
  AND occurred_at = ?
  AND event_id = ?
IF event_type = 'NEW';
~~~

Ví dụ cấu hình statement cho pha CL và serial consistency:

~~~java
BoundStatement conditional = conditionalPrepared.bind(
    deviceId, day, occurredAt, eventId
).setConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_QUORUM
).setSerialConsistencyLevel(
    DefaultConsistencyLevel.LOCAL_SERIAL
);
~~~

`conditionalPrepared` ở đây là `PreparedStatement` đã được chuẩn bị cho CQL `UPDATE ... IF ...` bên trên. Ứng dụng phải kiểm tra cột/kết quả **applied** để biết điều kiện có thực sự được áp dụng. LWT sử dụng cơ chế đồng thuận có chi phí cao hơn ghi bình thường; không dùng cho mọi mutation chỉ vì muốn “CL mạnh hơn”.

Trong nhiều DC, chọn `LOCAL_SERIAL` hay `SERIAL` còn liên quan phạm vi đồng thuận/nhất quán theo phiên bản Cassandra. Cần đánh giá kỹ nếu nhiều datacenter cùng thực hiện conditional writes hoặc có failover.

## 16. Khi thấy dữ liệu không như mong đợi: chẩn đoán đúng nguyên nhân

**Đọc sai partition:** writer tính `event_day` theo UTC, reader theo múi giờ khác. Tăng CL không giúp tìm đúng dữ liệu.

**Converter lệch biểu diễn:** writer lưu enum thành `'paid'`, reader bind `'PAID'`. Cassandra so sánh giá trị CQL, không tự chuẩn hóa chuỗi.

**Ghi có timestamp đặc biệt:** một writer dùng `USING TIMESTAMP` quá xa vào tương lai, khiến ghi bình thường về sau có thể thua dù CL cao.

**TTL và tombstone:** dữ liệu thực sự đã hết hạn hoặc bị xóa. Đọc quorum có thể đúng mà vẫn không trả giá trị.

**Khác DC:** ghi `LOCAL_QUORUM` tại dc1 không chứng minh replica dc2 đã nhận đầy đủ; đọc từ dc2 ngay lúc đó có thể thấy trạng thái khác.

**Concurrent writes:** Cassandra phân giải cell theo timestamp và các quy tắc tie-break; CL không tạo thứ tự giao dịch toàn cục theo thời điểm HTTP request.

**Partition quá lớn:** không thể chữa latency do hot partition bằng tăng CL. Cần thiết kế lại bucket/shard, giới hạn query, paging và payload.

Khi gặp lỗi, kiểm tra **khóa và giá trị bind thực tế**, RF, CL của cả read/write, datacenter, TTL, timestamp, replica health, driver metrics và CQL schema trước khi kết luận.

## 17. Kiểm thử và quan sát trên cluster

Các bước có thể thực hiện trên môi trường test có quyền:

1. Đọc replication config qua `system_schema.keyspaces`.
2. Dùng tiện ích quản trị như `nodetool status` để quan sát DC và node đang hoạt động.
3. Trong `cqlsh`, xem/đặt CL của phiên làm việc:

~~~text
CONSISTENCY;
CONSISTENCY LOCAL_QUORUM;
~~~

4. Ghi sự kiện với primary key ổn định; đọc cùng khóa ở các CL phù hợp.
5. Trong môi trường thử nghiệm, mô phỏng một replica không sẵn sàng để so hành vi RF=3 giữa `ONE`, `LOCAL_QUORUM` và `ALL`.
6. Thử ghi timeout/retry và bảo đảm không phát sinh `event_id` mới cho cùng một yêu cầu nghiệp vụ.
7. Quan sát unavailable/read timeout/write timeout, latency p95/p99, request rate và trạng thái repair/tombstone.

Không gây lỗi node hoặc thay đổi replication trên production chỉ để kiểm tra lý thuyết; các thao tác đó cần quy trình vận hành và kế hoạch phục hồi.

| Test | Kỳ vọng |
| --- | --- |
| RF local=3, một replica down | LOCAL_QUORUM có thể còn hoạt động, ALL không đủ phản hồi |
| RF local=3, hai replica down | LOCAL_QUORUM không đạt |
| Write ONE, read ONE | Có thể không thấy ghi gần nhất khi replica chưa đồng bộ |
| Write LOCAL_QUORUM, read LOCAL_QUORUM | Tăng khả năng thấy dữ liệu mới nhờ replica giao nhau |
| Hai DC, local RF=3 mỗi DC | LOCAL_QUORUM cục bộ cần 2, QUORUM tổng cần 4 |
| LWT khi hai writer cạnh tranh | Chỉ conditional write thỏa điều kiện được áp dụng |
| Dữ liệu hết TTL | CL cao không làm giá trị đã hết hạn xuất hiện lại |

## 18. Checklist lựa chọn replication và consistency

- [ ] Đã biết topology, số datacenter và node, yêu cầu chịu lỗi.
- [ ] RF của keyspace phù hợp với topology thực, không nhầm RF với tổng số node.
- [ ] Đã tính quorum theo RF cục bộ hoặc tổng đúng phạm vi CL.
- [ ] Java Driver cấu hình đúng local datacenter.
- [ ] Có CL rõ ràng cho từng nhóm đọc/ghi quan trọng, không chỉ dựa vào default chưa được kiểm tra.
- [ ] Đã xác định mức chấp nhận dữ liệu cũ, độ trễ và tính sẵn sàng.
- [ ] Hiểu giới hạn của `R + W > RF` khi có concurrent writes, timestamp và cross-DC.
- [ ] Có chính sách retry/idempotency/timeout và ID nghiệp vụ ổn định.
- [ ] Dùng LWT khi cần điều kiện nguyên tử thay vì chỉ tăng CL.
- [ ] Query cung cấp partition key đúng; không lạm dụng `ALLOW FILTERING`.
- [ ] Có kế hoạch repair và kiểm thử failover khi thay đổi RF/topology.
- [ ] Theo dõi latency, timeout, unavailable, tombstone và replica health.

## 19. Tự kiểm tra

**Câu 1.** RF=3 trong dc1; `LOCAL_QUORUM` cần bao nhiêu replica phản hồi?

**Đáp án:** Hai trong ba replica của dc1.

**Câu 2.** Với RF=3 và một replica down, `ALL` có còn đạt được không?

**Đáp án:** Không, vì ALL cần cả ba replica; LOCAL_QUORUM vẫn có thể đạt nếu hai replica còn lại phản hồi đúng hạn.

**Câu 3.** Hai DC có RF=3 mỗi DC. `LOCAL_QUORUM` tại dc1 khác `QUORUM` toàn cục như thế nào?

**Đáp án:** LOCAL_QUORUM cần hai phản hồi ở dc1; QUORUM toàn cục cần bốn phản hồi trong tổng sáu replica.

**Câu 4.** Tại sao write ONE và read ONE không bảo đảm luôn thấy lần ghi mới nhất?

**Đáp án:** Lần đọc có thể được phục vụ từ replica chưa nhận mutation được ghi ở replica khác.

**Câu 5.** `R + W > RF` có tương đương transaction SQL tuyến tính nhiều bảng không?

**Đáp án:** Không. Đó là lập luận về giao nhau giữa nhóm replica trong một phạm vi; concurrent writes, timestamp, TTL, LWT và nhiều bảng vẫn cần xử lý riêng.

**Câu 6.** CL=ALL có tự giúp `UPDATE ... IF event_type='NEW'` hoạt động khi không dùng LWT không?

**Đáp án:** Không. Điều kiện compare-and-set cần CQL conditional write/LWT và phải kiểm tra kết quả applied.

**Câu 7.** Request ghi timeout thì có nên tạo event_id mới rồi retry không?

**Đáp án:** Không mặc định. Ghi trước có thể đã xảy ra; ID mới có thể tạo bản ghi trùng sự kiện nghiệp vụ. Dùng khóa ổn định và chính sách retry thích hợp.

**Câu 8.** Tăng CL có sửa được truy vấn `WHERE event_type='PAID'` trên bảng theo device/day khi thiếu partition key không?

**Đáp án:** Không. CL không thay đổi mô hình khóa/index; phải thiết kế đúng đường truy cập hoặc bảng đọc khác.

---

**Ghi nhớ:** **RF** là số bản sao mục tiêu của một partition theo keyspace và datacenter; **CL** là số replica cần phản hồi để một request đọc/ghi được xác nhận. Với RF=3, `LOCAL_QUORUM` cần 2/3, còn `ALL` cần 3/3. Trong môi trường nhiều DC, phải phân biệt `LOCAL_QUORUM`, `QUORUM` và `EACH_QUORUM`. Spring Data Cassandra dùng RF của keyspace và CL từ driver/statement/options; **CL không thay thế thiết kế partition key, retry/idempotency, phân giải timestamp hay LWT**.
