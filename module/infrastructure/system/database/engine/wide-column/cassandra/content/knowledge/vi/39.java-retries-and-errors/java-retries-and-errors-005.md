# ReadFailure/WriteFailure, Overloaded và tải server

> **Chương:** Retry và lỗi Java  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Bối cảnh:** Apache Cassandra là hệ cơ sở dữ liệu phân tán wide-column. Lỗi từ Java driver cần được hiểu theo partition key, thiết kế bảng theo truy vấn, replica, consistency level, commitlog, memtable, SSTable, compaction và repair.

## 1. Mục tiêu và tình huống mở đầu

Một ứng dụng Java ghi sự kiện vào Cassandra bằng **LOCAL_QUORUM**. Trong đợt cao điểm, dashboard có ba nhóm lỗi: **ReadFailure**, **WriteFailure** và **Overloaded**. Một lập trình viên đề xuất sửa bằng cách tăng timeout, giảm consistency level xuống **ONE**, rồi retry tất cả request thật nhanh.

Giải pháp đó có thể làm sự cố nặng hơn:

- **ReadFailure/WriteFailure** nói rằng một hoặc nhiều thành phần xử lý đã báo thất bại; không chỉ đơn thuần là “đợi chưa đủ lâu”.
- **Overloaded** là tín hiệu một thành phần Cassandra không thể tiếp nhận/xử lý lượng công việc hiện tại; retry tức thì có thể tạo **retry storm**.
- **WriteFailure hoặc WriteTimeout không khẳng định mutation chắc chắn chưa được áp dụng** ở bất kỳ replica nào. Ghi lại một thao tác không idempotent có thể gây dữ liệu trùng hoặc tác dụng phụ.
- Hạ consistency level có thể đổi cam kết nhất quán của API mà không xử lý hotspot, I/O, GC, compaction hay nguyên nhân tải lớn.

Bài học này giúp bạn:

1. Phân biệt **ReadFailure**, **WriteFailure**, **Overloaded**, **ReadTimeout**, **WriteTimeout** và **Unavailable**.
2. Hiểu vai trò coordinator, replica và consistency level trong đường đi request.
3. Viết xử lý lỗi ở **Java Driver 4.x** theo loại lỗi và yêu cầu nghiệp vụ.
4. Thiết kế retry/backoff/jitter, giới hạn concurrency, idempotency và backpressure.
5. Chẩn đoán nguyên nhân ở server bằng log, metrics, nodetool và số liệu ứng dụng.
6. Chọn hướng xử lý khi quá tải do hot partition, collection, batch, compaction, repair hoặc tài nguyên hệ thống.

> **Giới hạn phiên bản:** Tên exception, thông tin chi tiết có thể đọc từ exception và hành vi retry mặc định phụ thuộc phiên bản Java driver, native protocol và Cassandra. Ví dụ dùng **Java Driver 4.x** với namespace **com.datastax.oss.driver.api**. Cần kiểm tra tài liệu đúng bản đang chạy trước khi áp chính sách sản xuất.

## 2. Bức tranh đường đọc và đường ghi

Cassandra phân bố các hàng theo **partition key**; coordinator dùng replication strategy/topology để liên hệ các replica sở hữu partition. Client đặt **consistency level (CL)** để quy định mức phản hồi cần có trước khi coi request hoàn tất.

~~~mermaid
flowchart LR
    A["Java service / BoundStatement"] --> B["Driver chọn coordinator"]
    B --> C["Coordinator định vị partition key"]
    C --> R1["Replica 1"]
    C --> R2["Replica 2"]
    C --> R3["Replica 3"]
    R1 --> D["Commitlog + memtable / SSTable"]
    R2 --> D
    R3 --> D
    C --> E["Phản hồi hoặc lỗi về driver"]
~~~

Với **ghi**, replica có thể cần thực hiện công việc commitlog/memtable và báo kết quả. Với **đọc**, replica phải tìm dữ liệu qua memtable, SSTable, index và tombstone; coordinator hợp nhất thông tin theo cơ chế đọc. Đường này có nhiều điểm thất bại:

- Node chậm hoặc bị ngắt mạng;
- Disk I/O/commitlog lỗi, disk full, GC pause hoặc áp lực native/heap;
- Quá nhiều request đến một coordinator hay một số replica;
- Partition nóng/lớn, tombstone nhiều, compaction/repair chiếm tài nguyên;
- Giá trị hoặc truy vấn vượt giới hạn/guardrail của phiên bản;
- Tăng timeout và retry của client làm lượng request tồn đọng tăng.

**CL không quyết định partition nằm ở đâu**; nó tác động tới điều kiện phản hồi. Ví dụ với RF = 3 trong một local DC, **LOCAL_QUORUM** thường cần phản hồi từ **2 trong 3 replica** trong DC đó. Nếu hai replica lỗi/chậm, request có thể thất bại dù replica thứ ba vẫn hoạt động.

## 3. Sáu lỗi cần phân biệt trước khi retry

| Tín hiệu | Ý nghĩa ở mức ứng dụng | Điểm mấu chốt |
|---|---|---|
| **ReadFailure** | Coordinator/server nhận thông báo thất bại trong quá trình đọc và không thể thỏa yêu cầu CL | Không đồng nghĩa chỉ thiếu thời gian chờ; cần tìm nguyên nhân thất bại |
| **WriteFailure** | Lỗi xảy ra trong xử lý ghi tại thành phần tham gia và không đạt điều kiện thành công của request | Một số replica có thể đã áp dụng ghi; không mặc định chưa ghi |
| **Overloaded** | Thành phần server báo không đủ năng lực tiếp nhận/xử lý yêu cầu hiện tại | Tín hiệu áp lực tải; đẩy thêm retry ngay thường bất lợi |
| **ReadTimeout** | Không thu đủ phản hồi đọc cần thiết trong thời hạn server xử lý | Có thể do node chậm, mạng, tombstone, I/O hoặc áp lực truy vấn |
| **WriteTimeout** | Không thu đủ phản hồi ghi cần thiết trong thời hạn server xử lý | Không biết chắc dữ liệu đã được ghi đến đâu |
| **Unavailable** | Coordinator đánh giá không đủ replica khả dụng để thực hiện theo CL được yêu cầu | Khác với timeout sau khi đã đợi phản hồi; kiểm tra topology/replica |

**Cần tách lỗi từ server và lỗi phía client.** Java driver cũng có thể hết thời gian chờ request, không liên hệ được node hoặc gặp lỗi TLS/auth. Một **driver-side request timeout** không nhất thiết là **ReadTimeoutException** hay **WriteTimeoutException** do Cassandra trả về. Phân loại exception thực tế bằng class/error code tương ứng, không chỉ dò chuỗi “timeout” trong message.

### 3.1. ReadFailure khác ReadTimeout

**ReadTimeout** thường cho biết coordinator không nhận đủ phản hồi đáp ứng yêu cầu trước deadline, nhưng không nhất thiết được thông báo một lỗi rõ ràng từ replica. **ReadFailure** cho biết có tín hiệu thất bại trong quá trình xử lý đọc.

Các nguyên nhân ReadFailure có thể khác theo bản Cassandra, ví dụ lỗi đường đọc, giới hạn tombstone hoặc sự cố bên dưới. Không đoán nguyên nhân chính xác chỉ từ tên exception; phải đối chiếu **server log ở coordinator/replica, bảng, partition, mức CL và metrics cùng thời điểm**.

### 3.2. WriteFailure khác WriteTimeout

**WriteTimeout** có thể xảy ra khi write đã đi tới một phần replica nhưng chưa đủ xác nhận đúng CL. **WriteFailure** phản ánh server nhận thông báo thất bại liên quan xử lý ghi; vẫn phải xem có replica khác đã nhận mutation hay không.

Ví dụ một INSERT vào partition có RF = 3, write CL = LOCAL_QUORUM. Replica A báo thành công, B báo lỗi khi ghi commitlog, C chưa có kết quả. Nếu request thất bại, client **không thể kết luận mutation chưa có ở A**. Một retry tạo **event_id mới** có thể sinh một hàng mới, không phải hoàn thành hàng cũ.

### 3.3. Overloaded khác Unavailable

- **Overloaded:** vấn đề năng lực xử lý, hàng đợi, resource saturation hoặc cơ chế load shedding của server. Replica có thể vẫn UP nhưng không đủ tài nguyên xử lý đúng tốc độ.
- **Unavailable:** số replica sẵn sàng theo đánh giá coordinator không đáp ứng consistency level; thường liên quan sức khỏe node, topology hoặc DC/RF.

Một node **UP/NORMAL** vẫn có thể quá tải. Tăng replication factor hoặc hạ CL chỉ để làm lỗi biến mất không thay thế việc tìm **nguồn tải, phân phối partition và giới hạn tài nguyên**.

### 3.4. Không suy ra kết quả write từ loại lỗi

| Kết quả nhận từ Java | Có thể kết luận chắc chắn điều gì? |
|---|---|
| Ghi thành công theo CL | Đã thỏa điều kiện xác nhận của CL cho request theo ngữ nghĩa Cassandra |
| WriteTimeout | Không thỏa điều kiện phản hồi trước deadline; trạng thái ghi có thể đã thay đổi |
| WriteFailure | Request thất bại theo thông tin server; vẫn cần xử lý khả năng ghi một phần |
| Overloaded | Server báo quá tải; cần theo dõi xem request có được từ chối ở đâu và tác động gì, không tự suy ra mọi request đều chưa ghi |
| Lỗi kết nối/client timeout | Không có phản hồi đầy đủ tới client; kết quả có thể không xác định tùy thời điểm lỗi |

Điều này là nền tảng của **idempotent retry** và xử lý lỗi nghiệp vụ. Với một câu UPDATE giá trị cố định trên khóa đã xác định, việc thử lại thường dễ kiểm soát hơn một counter increment, list append hoặc thao tác tạo ID mới.

## 4. Consistency level, RF và tính sẵn sàng

### 4.1. Ví dụ RF = 3, LOCAL_QUORUM

Giả sử keyspace dùng **NetworkTopologyStrategy** tại **dc1** với RF = 3:

~~~sql
CREATE KEYSPACE IF NOT EXISTS app_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
~~~

Chỉ chạy như minh họa trên môi trường có topology và số node phù hợp. Với LOCAL_QUORUM trong dc1, thường cần **2 phản hồi** từ các replica của partition. Vì vậy:

- Một node tắt, hai replica còn khỏe: có thể tiếp tục đáp ứng LOCAL_QUORUM.
- Hai node tắt: không còn đủ replica cho mức đó.
- Một node tắt, node khác vẫn UP nhưng bị disk saturation: số node đủ theo cấu hình, nhưng độ trễ/khả dụng có thể không đáp ứng.
- Nếu chọn **LOCAL_ONE** cho endpoint đọc có cho phép dữ liệu hơi cũ, điều kiện phản hồi nhẹ hơn, nhưng nghiệp vụ cũng phải chấp nhận sự đánh đổi.

**Không tự động giảm CL từ LOCAL_QUORUM xuống LOCAL_ONE khi retry** nếu API đã cam kết nhất quán cao hơn. Đó là thay đổi ngữ nghĩa, phải được quyết định có chủ đích.

### 4.2. Phạm vi DC quan trọng

**QUORUM** và **LOCAL_QUORUM** không tương đương khi cluster nhiều datacenter. LOCAL_QUORUM xét đa số replica trong local DC; QUORUM xét theo phạm vi toàn bộ bản sao như server định nghĩa. Trước khi suy luận số replica cần phản hồi, kiểm tra:

- Replication strategy của **keyspace**;
- RF của từng DC;
- DC mà Java driver chọn làm local;
- Consistency level thực sự gắn trên statement hoặc execution profile;
- Khả năng liên lạc internode và tình trạng replica.

**Consistency level không phải giải pháp cho schema sai hoặc truy vấn thiếu partition key.** Phải sửa mô hình theo access pattern trước.

## 5. Phân biệt lỗi do dữ liệu, do tải và do hạ tầng

| Triệu chứng | Giả thuyết cần kiểm tra | Chỉ số/bằng chứng |
|---|---|---|
| ReadFailure xuất hiện ở một bảng nhiều tombstone | Đọc quét quá nhiều tombstone hoặc lỗi đường đọc | Server log, tombstone metrics, tablehistograms, query shape |
| ReadTimeout tăng vào giờ ingest | Read path cạnh tranh I/O với flush/compaction | Disk latency, compactionstats, GC, p99, pending tasks |
| WriteFailure tập trung ở một node | Commitlog/disk/replica I/O hoặc lỗi trong xử lý ghi | Node log, disk free, filesystem errors, JVM |
| Overloaded tăng trên nhiều coordinator | Admission/backpressure, request concurrency quá cao | Driver inflight, pending tasks, CPU/heap/native, queue/drop |
| Lỗi nhiều ở một tenant | Hot partition hoặc partition quá rộng | Tần suất theo partition key, partition size, token distribution |
| Lỗi tăng khi chạy LOGGED BATCH lớn | Fan-out nhiều partition, batchlog/coordinator quá tải | Batch size/partition count, write latency, log warn |
| Tải tăng sau TTL/delete hàng loạt | Tombstone và compaction/repair backlog | SSTable counts, tombstones, disk I/O |
| App Java bị timeout nhưng server không báo tương ứng | Driver timeout, pool/queue/network, tải phía client | Driver metrics/log, client CPU/GC, network path |

Đây là **giả thuyết chẩn đoán**, không phải ánh xạ một-một giữa exception và nguyên nhân. Một vấn đề có thể gây nhiều loại lỗi: hot partition vừa làm read timeout, vừa khiến coordinator/replica quá tải và tăng retry.

### 5.1. Hot partition không được chia tự động theo RF

Cassandra dùng partition key để chọn token và nhóm replica. Nếu 90% request cùng ghi vào một partition của một khách hàng, nhóm replica của partition đó có thể quá tải trong khi node khác nhàn rỗi. **Tăng số node không tự cắt một partition lớn thành nhiều mảnh**.

Giải pháp nên bắt đầu từ:

- Phân tích access pattern (đọc theo tenant/ngày/giờ/thiết bị?);
- Chia bucket thời gian, shard có quy tắc hoặc thay primary key khi cần;
- Giới hạn collection và payload;
- Điều tiết tốc độ request vào hot key;
- Đánh đổi fan-out khi đọc nhiều bucket, có thử nghiệm trên dữ liệu thực.

### 5.2. Tác động của compaction và repair

Cassandra lưu dữ liệu theo mô hình LSM: ghi vào commitlog/memtable, flush thành SSTable và compaction ở nền. Nếu backlog compaction tăng, I/O cho đọc/ghi có thể bị cạnh tranh. **Repair** tiêu tốn disk/network/CPU, đặc biệt trên dữ liệu lớn hoặc có nhiều tombstone.

Không xem repair như câu lệnh “sửa mọi lỗi” khi có ReadFailure/WriteFailure. Repair cần lịch, quyền, kiểm soát tải và đánh giá dữ liệu. Nếu dữ liệu bị DELETE sai, repair cũng **không quay ngược thao tác nghiệp vụ đó**.

## 6. CQL lab: một truy vấn đúng partition key

Mô hình sự kiện theo tenant/ngày:

~~~sql
CREATE TABLE IF NOT EXISTS app_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

- **(tenant_id, event_day)** là composite partition key. Hai giá trị phải được tính nhất quán khi ghi/đọc.
- **happened_at, event_id** là clustering columns. Chúng hỗ trợ đọc theo thứ tự trong partition và xác định row.
- Một tenant ghi hàng triệu sự kiện/ngày vẫn có thể làm partition theo ngày quá lớn; cần đo kích thước, tốc độ đỉnh và cân nhắc bucket nhỏ hơn.
- Không lưu mọi sự kiện trong một **list** vô hạn chỉ vì Java driver có thể encode collection.

Ghi một fixture ổn định:

~~~sql
INSERT INTO app_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id,
    event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"order":"lab-001"}'
);
~~~

Truy vấn đọc:

~~~sql
SELECT happened_at, event_id, event_type
FROM app_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

CQL chạy trong cqlsh cần thay **?** bằng literal hoặc dùng câu đã prepare/bind từ Java. **LIMIT** chỉ giới hạn row trả về, không chữa được partition lớn hoặc tombstone nhiều. Kiểm thử phải so **event_id mong đợi**, không chỉ kiểm tra truy vấn không ném exception.

## 7. Java Driver 4.x: bắt đúng exception và ghi log có ích

Ví dụ sau đọc một partition, dùng **LOCAL_QUORUM** và phân biệt các lỗi server. Đây là demo một lần trong môi trường lab; ứng dụng dài hạn nên tái sử dụng **CqlSession** và **PreparedStatement**.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.servererrors.ReadFailureException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;

public class CassandraReadErrorDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM app_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement request = select
                .bind(tenantId, eventDay, 20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            try {
                ResultSet rows = session.execute(request);
                System.out.println(
                    "SELECT completed; rows=" + rows.all().size());
            } catch (ReadFailureException ex) {
                System.err.println(
                    "READ_FAILURE: inspect replica/server logs");
            } catch (ReadTimeoutException ex) {
                System.err.println(
                    "READ_TIMEOUT: insufficient read responses in time");
            } catch (OverloadedException ex) {
                System.err.println(
                    "OVERLOADED: shed load and apply backpressure");
            } catch (UnavailableException ex) {
                System.err.println(
                    "UNAVAILABLE: check RF/DC/live replicas and CL");
            }
        }
    }
}
~~~

**Giới hạn và lưu ý:**

- Chỉ đọc **20 row** nên dùng **rows.all()** để minh họa. Trên truy vấn nhiều trang, **all()** có thể kéo các trang về và giữ nhiều dữ liệu; trong production dùng giới hạn/page processing phù hợp.
- **ReadFailureException**, **ReadTimeoutException**, **OverloadedException** và **UnavailableException** là các nhóm exception trong package **servererrors** của driver 4.x. Tên/chi tiết phụ thuộc bản driver/protocol.
- Code log **loại lỗi**, không ghi partition key thật, payload, password hoặc raw BoundStatement. Hệ thật thêm operation ID, trace ID có kiểm soát, version và metrics.
- **setIdempotent(true)** ở đây dùng cho SELECT chỉ đọc. Không gán idempotent=true bừa cho các write có counter/list append hay tác dụng phụ.
- Ngoài các lỗi nêu trên, còn có lỗi **client-side request timeout, network, authentication/TLS, schema, codec**. Không chỉ catch bốn loại rồi xem mọi lỗi khác là retry được.
- Mẫu cho RF = 3 và LOCAL_QUORUM cần đủ replica trong **dc1**; phải điều chỉnh lab nếu không có topology tương ứng.

### 7.1. Ghi log theo query shape, không theo dữ liệu khách hàng

Nên ghi:

~~~json
{
  "event": "cassandra_request_failed",
  "operation": "events_by_tenant_day.read",
  "error_class": "ReadFailureException",
  "consistency": "LOCAL_QUORUM",
  "query_shape": "read_one_tenant_day",
  "duration_ms": 1250,
  "retry_count": 0,
  "request_id": "req-example-31"
}
~~~

Đây là **JSON log ứng dụng minh họa**. Không ghi UUID khách hàng, payload, signed token hoặc chuỗi CQL có dữ liệu nhúng; log và tracing cũng phải được phân quyền/retention.

## 8. Java: WriteFailure và kết quả không chắc chắn

Với câu INSERT giá trị cố định, tạo khóa ổn định **trước** khi thực thi, để nếu timeout/retry thì cùng nghiệp vụ không sinh row khác.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;

UUID eventId = UUID.fromString(
    "22222222-2222-4222-8222-222222222222");
UUID tenantId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
Instant happenedAt = Instant.parse("2026-11-21T08:00:00Z");

PreparedStatement insert = session.prepare(
    "INSERT INTO app_lab.events_by_tenant_day " +
    "(tenant_id, event_day, happened_at, event_id, " +
    "event_type, payload) VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement write = insert.bind(
        tenantId, LocalDate.of(2026, 11, 21),
        happenedAt, eventId, "ORDER_CREATED",
        "{\"order\":\"lab-001\"}")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true);

try {
    session.execute(write);
    System.out.println("Write acknowledged at requested CL");
} catch (WriteFailureException ex) {
    System.err.println(
        "WRITE_FAILURE: outcome may be partial; investigate");
} catch (WriteTimeoutException ex) {
    System.err.println(
        "WRITE_TIMEOUT: do not assume write was not applied");
} catch (OverloadedException ex) {
    System.err.println(
        "OVERLOADED: stop flooding server; apply backpressure");
}
~~~

Đoạn này nằm trong method có **session** là CqlSession đã khởi tạo. Nó dùng **INSERT** không TTL, cùng primary key và cùng giá trị; việc đánh dấu idempotent giúp driver có thể cân nhắc theo chính sách retry/speculative execution, **không tự làm mọi retry an toàn trong mọi trường hợp**. Khi retry, nên giữ **eventId, happenedAt, payload** ổn định và đánh giá timestamp/TTL, cạnh tranh ghi và các side effects nghiệp vụ. Một câu INSERT có timestamp tự sinh có thể có khác biệt trong giải quyết concurrent writes; cần thiết kế idempotency theo hệ thống.

**Không nên thực hiện ngay một vòng lặp vô hạn trong catch**. Mỗi lỗi phải đi qua một quyết định retry có giới hạn, backoff/jitter và circuit breaker/backpressure nếu hệ thống dùng chúng.

### 8.1. Tránh retry các thao tác không idempotent

Ví dụ nguy hiểm:

~~~sql
-- Không mặc định retry an toàn khi kết quả không rõ.
UPDATE app_lab.counters_by_tenant
SET total = total + 1
WHERE tenant_id = ?;
~~~

Cú pháp trên là minh họa cho bảng counter **nếu đã định nghĩa total counter và khóa phù hợp**; nó không thể chạy trên bảng sự kiện ở mục 6. Counter update có thể đã được áp dụng trước timeout, nên gửi lại dễ tăng thêm một lần. Tương tự, thao tác **list append** hoặc client tạo **eventId mới** mỗi lần retry có thể gây trùng logic.

Một số bài toán cần mô hình sự kiện có định danh ổn định, deduplication hoặc hàng ghi bảo đảm bằng thao tác có điều kiện. **LWT IF NOT EXISTS** cũng có trường hợp outcome không rõ khi timeout; retry có thể trả **[applied] = false** vì lần trước đã thành công, nên phải đối soát trạng thái thay vì hiểu false là lỗi hạ tầng.

## 9. Khi nào được retry, khi nào phải dừng?

Một chiến lược retry tốt phải xét **loại request, idempotency, dạng lỗi, deadline và tải thực tế**, không chỉ tên exception.

| Trường hợp | Hướng xử lý thận trọng | Vì sao |
|---|---|---|
| SELECT idempotent bị lỗi tạm thời | Có thể retry có giới hạn nếu còn deadline và server không quá tải | Đọc lại không tạo ghi mới, nhưng retry vẫn tốn tài nguyên |
| ReadFailure lặp lại cùng partition | Dừng retry hàng loạt; điều tra log/table/replica | Có thể là lỗi dữ liệu, tombstone hoặc node I/O |
| WriteTimeout/WriteFailure trên INSERT ổn định | Retry **chỉ nếu** ngữ nghĩa ghi đã được xác định idempotent, có backoff và bounded attempts | Kết quả lần đầu có thể đã áp dụng một phần |
| Counter increment / list append | Không tự retry khi outcome mơ hồ | Dễ nhân đôi tác dụng |
| Overloaded xuất hiện hàng loạt | Giảm tốc, backpressure, tạm chặn request mới, retry rất thận trọng | Retry storm làm server nặng hơn |
| Unavailable do không đủ replica | Giảm tải không làm replica xuất hiện; kiểm tra topology/CL và phục hồi node | Retry tức thì thường không đổi trạng thái |
| Lỗi auth, schema, codec, CQL syntax | Không retry tự động; sửa lỗi cấu hình/code | Retry không làm mật khẩu/kiểu dữ liệu đúng hơn |
| Deadline HTTP/gRPC đã hết | Không tiếp tục retry vô ích | Caller không còn chờ, request mới chiếm tài nguyên |

**Đừng thay đổi consistency level ngầm trong retry policy.** Nếu endpoint cam kết đọc LOCAL_QUORUM, retry tại LOCAL_ONE có thể vi phạm tính đúng đắn. Việc cho phép degradation cần là chính sách nghiệp vụ rõ ràng, có telemetry, chứ không phải “mặc định phục hồi lỗi”.

### 9.1. Exponential backoff và jitter

Ví dụ thuật toán ứng dụng:

~~~text
base_delay = 100 ms
max_delay = 2 seconds
max_attempts = 3  (bao gồm lần đầu)

attempt 1: request bình thường
nếu lỗi được phân loại là transient, request idempotent,
còn deadline và chưa mở circuit:
    delay = min(max_delay, base_delay * 2^(attempt-1))
    sleep một thời gian ngẫu nhiên phù hợp [0, delay]
    kiểm tra lại deadline/load-budget
    thử lại
nếu không:
    trả lỗi có phân loại, không retry
~~~

Các số **100 ms, 2 giây, 3 lần** chỉ minh họa; phải xác định theo SLO và khả năng phục vụ. **Jitter** giúp tránh nhiều client cùng đánh thức sau một khoảng thời gian cố định. Tính tổng thời gian retry **cả timeout của từng lần, queue delay và backoff**; không vượt deadline của yêu cầu nghiệp vụ.

Với Java Driver 4.x, trước khi viết thêm một lớp retry ở ứng dụng, phải biết **driver retry policy hiện tại, tính idempotent của statement và số lần driver có thể đã retry**. Nếu cả driver lẫn application đều retry độc lập, số request thực có thể tăng nhiều lần. Khi không chắc, ưu tiên **tắt hoặc giới hạn việc retry chồng lớp** theo thiết kế đã review.

### 9.2. Backpressure không chỉ là sleep

Một server quá tải vẫn có thể tiếp tục bị ngập nếu application có queue không giới hạn. Backpressure gồm:

- Giới hạn số request **in-flight** từ ứng dụng/instance;
- Có queue hữu hạn, từ chối hoặc giảm chất lượng có chủ đích khi vượt sức chứa;
- Điều tiết theo tenant hoặc endpoint để không để một hot key ảnh hưởng tất cả người dùng;
- Timeout/deadline nhất quán từ caller đến database;
- Retry budget theo tỷ lệ request, không để các lần thử lại lấn át request mới;
- Theo dõi áp lực đến **coordinator, replica và Java driver connection pool**.

Không chỉ tăng kích thước queue/connection pool vô hạn. Hệ thống có thể trông như ít lỗi hơn trong vài phút nhưng RAM, p99 latency và số request chưa hoàn thành tăng liên tục.

## 10. Java async: giới hạn in-flight bằng Semaphore

Ví dụ sau không triển khai retry; nó minh họa **điều tiết concurrency trước khi gửi request**. Mỗi instance giới hạn số request bất đồng bộ đang chờ nhận phản hồi.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedCassandraRequests {
    private final CqlSession session;
    private final Semaphore inFlight;

    public BoundedCassandraRequests(
            CqlSession session, int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrent must be positive");
        }
        this.session = session;
        this.inFlight = new Semaphore(maxConcurrent);
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {

        if (!inFlight.tryAcquire()) {
            CompletableFuture<AsyncResultSet> rejected =
                new CompletableFuture<>();
            rejected.completeExceptionally(
                new RejectedExecutionException(
                    "Cassandra client concurrency limit reached"));
            return rejected;
        }

        try {
            return session.executeAsync(statement)
                .whenComplete((result, error) ->
                    inFlight.release());
        } catch (RuntimeException error) {
            inFlight.release();
            throw error;
        }
    }
}
~~~

Điểm cần hiểu:

1. Khi hết permit, ứng dụng **từ chối có kiểm soát** thay vì tích vô hạn request.
2. Permit được trả lại khi **stage của lần executeAsync này hoàn thành** dù thành công hay lỗi.
3. Nếu query có nhiều trang, stage đầu chỉ hoàn thành khi một trang được xử lý; các request lấy trang tiếp theo cần được quản lý riêng để tính đầy đủ in-flight.
4. Giới hạn trên là **mỗi instance Java**, không phải tổng toàn bộ service. Có 20 instance thì tổng request có thể cao hơn nhiều; cần quota/throttling ở hệ thống khi phù hợp.
5. **maxConcurrent** phải được đo theo topology, payload, CL, latency, connection pool và replica load. Không có một con số chuẩn dùng cho mọi Cassandra cluster.
6. Lỗi **RejectedExecutionException** ở đây do **client tự từ chối**, không phải **OverloadedException từ Cassandra**. Phải phân biệt trong log/metrics.

Đoạn ví dụ chỉ hỗ trợ đường request đơn giản. Trong production cần tích hợp deadline, hủy/từ chối, tracing và bảo đảm callback không vô tình giữ dữ liệu nhạy cảm hoặc tạo queue khác không giới hạn.

## 11. Chẩn đoán server: công cụ và thứ tự điều tra

### 11.1. Lấy bằng chứng ở ba tầng

**Tầng ứng dụng/driver:**

- Mỗi endpoint hoặc query shape: throughput, p95/p99, lỗi theo exception type;
- Consistency level, local DC, execution profile, request timeout, retry policy;
- Số request in-flight, queue, rate-limit rejection, retry attempt, số client;
- Kích thước payload/batch/collection, số partition được truy vấn;
- Thời điểm bắt đầu sự cố và thay đổi deploy/config gần đây.

**Tầng Cassandra node:**

- Node health, CPU, GC pauses, heap/native/RSS, disk free, disk latency/IOPS, network;
- Thread pools/pending tasks, dropped messages, overload/admission;
- Commitlog/memtable flush, compaction backlog, repair/streaming và tombstone;
- Server logs với nguyên nhân tại coordinator/replica ở cùng thời điểm;
- Phân phối kích thước partition, hot key, SSTable count và tần suất request.

**Tầng hạ tầng:**

- Mạng giữa client↔coordinator và coordinator↔replica;
- Container memory/cgroup OOM kill, throttling CPU;
- Storage latency và lỗi filesystem, capacity;
- Topology rack/DC/AZ và các thay đổi trong cluster.

**Một lỗi ở ứng dụng có thể là triệu chứng của node khác với coordinator**, nên tránh chỉ đọc log của node client kết nối đầu tiên.

### 11.2. Lệnh nodetool minh họa

Dùng trên node Cassandra được phép và đối chiếu cú pháp phiên bản:

~~~bash
# Node đang UP/DOWN, token và DC/rack.
nodetool status

# Thông tin một node.
nodetool info

# Thread pools, pending/active tasks và dropped messages.
nodetool tpstats

# Compaction đang chạy/chờ.
nodetool compactionstats

# Streaming / network tasks theo khả năng phiên bản.
nodetool netstats

# Thống kê bảng, SSTable, partition size và các chỉ số liên quan.
nodetool tablestats app_lab.events_by_tenant_day

# Phân phối kích thước/row count partition, tùy bản.
nodetool tablehistograms app_lab events_by_tenant_day
~~~

Kết quả thống kê là **điểm bắt đầu**, không tự cho kết luận. Ví dụ **mean partition size** nhỏ có thể che một partition rất lớn. Tương tự một node có CPU trung bình thấp nhưng disk latency rất cao vẫn có thể gây WriteFailure/ReadTimeout. Kết hợp log, JMX/Prometheus và workload của đúng thời điểm.

### 11.3. Quy trình 8 bước

1. **Phân loại lỗi:** ReadFailure, WriteFailure, Overloaded, Timeout, Unavailable hay driver/network.
2. **Xác định phạm vi:** một endpoint, một query shape, một tenant, một table, một DC hay mọi client.
3. **Đọc topology/CL:** replication strategy, RF, local DC, node health, coordinator/replica.
4. **Kiểm tra tải và tài nguyên:** CPU/GC/native memory, disk I/O, pending/dropped, compaction/repair.
5. **Kiểm tra data model:** partition key, hot partition, tombstone, collection, batch và payload.
6. **Kiểm tra client amplification:** retry budget, số instance, concurrency, profile/timeout, queue.
7. **Giảm áp lực an toàn:** điều tiết nguồn tải/stop bulk import, giữ SLA/consistency, phục hồi node/disk nếu lỗi.
8. **Đo lại và xác minh:** p95/p99, số lỗi từng nhóm, đúng dữ liệu qua nhiều partition, repair/backup sau sự cố.

Không vội chạy repair hoặc restart toàn cluster chỉ vì thấy lỗi đọc/ghi. Nếu có dấu hiệu corrupt/mất dữ liệu, cần bảo toàn evidence và phương án khôi phục trước các thao tác thay đổi trạng thái.

## 12. Tối ưu từ nguyên nhân gốc: workload, schema và capacity

### 12.1. Hot partition / partition quá lớn

Ví dụ một tenant sinh 100 sự kiện/giây và mỗi row ~1 KiB:

~~~text
Trong 1 ngày:
100 x 86.400 x 1 KiB
= 8.640.000 KiB
≈ 8,24 GiB payload/ngày

Trong 1 giờ:
100 x 3.600 x 1 KiB
= 360.000 KiB
≈ 351,56 MiB payload/giờ

Trong 5 phút:
100 x 300 x 1 KiB
= 30.000 KiB
≈ 29,30 MiB payload/5 phút
~~~

Đây là phép tính **payload thô**, chưa bao gồm metadata, compression, tombstone và peak skew. Nếu partition theo ngày quá lớn, cần cân nhắc bucket giờ/5 phút và đánh đổi khi đọc nhiều bucket. Không lấy các con số trên làm ngưỡng Cassandra chính thức.

### 12.2. Batch quá lớn

Một **LOGGED BATCH** nhiều nghìn INSERT trải hàng nghìn partition có thể gây áp lực coordinator, batchlog và replica. CQL batch **không phải bulk loader phổ quát**.

- Với các ghi độc lập sang nhiều partition, dùng **prepared statement + bounded concurrency** thường phù hợp hơn một batch khổng lồ.
- Nếu cần atomicity trong một partition, đánh giá batch nhỏ cùng partition theo ngữ nghĩa Cassandra.
- Giới hạn theo **byte, số statement và số partition**, không chỉ theo số câu.
- Server có thể có warning/fail thresholds cho batch/mutation tùy phiên bản; không nâng ngưỡng để che thiết kế dữ liệu.

### 12.3. Collection, tombstone và TTL

Map/list/set lớn hoặc update/delete liên tục có thể tạo nhiều cell/tombstone. TTL hết hạn cũng tạo công việc đọc/compaction liên quan. Một request ReadFailure do vấn đề đọc tombstone không nên được “sửa” bằng retry 100 lần.

Hãy đưa dữ liệu phát triển vô hạn thành **nhiều row** với clustering columns và bucket hợp lý; giới hạn collection thuộc tính nhỏ của một thực thể. Đo tombstone, partition histogram, compaction backlog và latency đọc theo query shape.

### 12.4. Heap/native memory và disk

- **Heap lớn hơn** không tự chữa network overload hoặc disk saturation. Cần để chỗ cho native/off-heap và page cache.
- **Disk free** phải đủ cho SSTable, compaction và repair. Full disk hoặc I/O lỗi có thể gây sự cố ghi.
- **GC pause** làm node phản hồi chậm, dẫn tới timeout và retry từ client.
- **Container memory limit** có thể giết tiến trình dù số liệu heap riêng vẫn có vẻ ổn.
- Nếu nhiều node cùng quá tải, xem cả **tổng lưu lượng từ app, số replica ghi, CL và thời điểm maintenance**.

## 13. Tình huống có số liệu: Overloaded khi giờ cao điểm

Giả sử cluster có RF = 3 tại dc1, Java app dùng LOCAL_QUORUM cho phần lớn ghi. SLO đặt p99 write dưới 300 ms. Sau một đợt mở rộng application từ 10 lên 25 instance:

| Chỉ số | Trước | Khi có lỗi |
|---|---:|---:|
| Request ghi từ app | 6.000/s | 15.000/s |
| p99 write | 170 ms | 1.900 ms |
| Retry từ app | 1% | 25% |
| Overloaded | Rất ít | Tăng mạnh |
| Pending tasks | Thấp | Cao |
| Disk utilization | 55% | Gần bão hòa |
| Compaction backlog | Ổn định | Tăng liên tục |

**Giả thuyết mạnh:** tổng lưu lượng tăng, retry tiếp tục nhân tải, đường ghi/disk và compaction không theo kịp. Cần kiểm chứng bằng metrics/log trước khi kết luận không còn nguyên nhân khác.

**Phương án ưu tiên:**

1. Dừng tự động mở rộng ingest hoặc điều tiết số request **in-flight** trên mỗi instance.
2. Giảm retry amplification; không retry tức thì khi Overloaded.
3. Nếu cần, giảm tốc ingest bulk và ưu tiên request cần SLA cao hơn theo chính sách.
4. Kiểm tra disk/GC/compaction, hot partition, batch size, write distribution.
5. Chỉ sau khi tải ổn định mới đánh giá capacity planning, thay schema/bucket hoặc bổ sung node và phân phối lại token.
6. Đo lại p99, error rate, queue, dropped messages, backlog và throughput **thực** sau can thiệp.

**Không ưu tiên hạ CL từ LOCAL_QUORUM xuống ONE** nếu ứng dụng có hợp đồng về xác nhận ghi ở local quorum. Việc đó có thể đổi yêu cầu phục hồi/đọc dữ liệu mà không xử lý nguồn quá tải.

## 14. Tình huống thứ hai: ReadFailure chỉ ở một phân vùng

Ứng dụng Java truy vấn lịch sử giao dịch của một khách hàng và nhận ReadFailure, trong khi các khách hàng khác vẫn đọc được. Các chỉ số cho thấy partition của khách hàng này rất lớn, số SSTable cao và nhiều tombstone từ việc xóa các giao dịch cũ.

**Các bước chẩn đoán:**

1. Kiểm tra query shape và **partition key đầy đủ**; có dùng ALLOW FILTERING hoặc truy vấn quét rộng không?
2. Xem server log tại thời điểm ReadFailure, nhất là coordinator và replica liên quan đến token.
3. Đọc histogram partition, tombstone, SSTable count và compaction stats.
4. Thử truy vấn nhỏ hơn trên **môi trường cho phép** để phân biệt phạm vi đọc; không ngầm gửi hàng loạt truy vấn gây thêm tải.
5. Xem thiết kế bảng: có thể chia **(tenant_id, bucket_day/hour)**, TTL và retention hợp lý hơn không?
6. Lập kế hoạch migration table theo truy vấn, kiểm thử đúng dữ liệu, không tự sửa primary key tại chỗ khi đã có dữ liệu.
7. Sau khi giảm áp lực, đo lại latency/error và xem compaction/repair cùng lịch vận hành.

**Retry không giúp một phân vùng thu nhỏ**. Cũng không nên chỉnh guardrail hay ngưỡng tombstone vô hạn để che thiết kế dữ liệu xấu.

## 15. LWT, retry và những giới hạn của “idempotent”

### 15.1. IF NOT EXISTS vẫn cần nhận diện outcome không rõ

Một Java service thực thi:

~~~sql
INSERT INTO app_lab.orders_by_id (
    tenant_id, order_id, status
) VALUES (?, ?, ?) IF NOT EXISTS;
~~~

Đây là ví dụ trên **bảng khác được định nghĩa riêng**, không phải bảng sự kiện ở mục 6. LWT kiểm tra điều kiện trong phạm vi mà Cassandra hỗ trợ, nhưng timeout của thao tác có điều kiện vẫn có thể xảy ra ở nhiều giai đoạn.

Nếu lần đầu tạo order thành công nhưng client không nhận phản hồi, retry cùng order ID có thể trả **[applied] = false** vì row đã tồn tại. Ứng dụng phải đối soát nội dung order/request ID thay vì đơn giản kết luận request thất bại.

### 15.2. Idempotent ở cấp database và ở cấp nghiệp vụ

Một INSERT cùng khóa và cùng giá trị có thể idempotent đối với trạng thái row, nhưng nếu mỗi lần client retry lại gửi email, thu tiền hoặc tạo event ID mới thì **toàn workflow không idempotent**.

Các biện pháp thường cần:

- Khóa nghiệp vụ cố định (orderId/eventId) được lưu trước lần thử đầu tiên;
- Bảng/nguồn kiểm soát request ID hay deduplication theo thiết kế;
- Outbox/event processing có cơ chế chống xử lý lặp;
- Kiểm tra trạng thái sau kết quả không xác định;
- Giới hạn retry và chính sách xử lý dead-letter/quarantine với lỗi không tự phục hồi.

**setIdempotent(true)** của driver là một khai báo để driver áp chính sách của nó; nó **không biến CQL có tác dụng không idempotent thành an toàn**. Người phát triển phải chứng minh điều kiện đó là đúng.

## 16. Kịch bản kiểm thử có kiểm soát

Trên staging có topology RF/DC tương ứng và dữ liệu tổng hợp:

1. **Baseline:** đo read/write p50/p95/p99 và error count ở tải bình thường.
2. **Một replica chậm:** giả lập tác động I/O hoặc mạng bằng cơ chế thử nghiệm được phê duyệt, so LOCAL_ONE và LOCAL_QUORUM.
3. **Một replica không khả dụng:** quan sát Unavailable/timeout theo RF và CL; không thực hiện trên production.
4. **Tăng tải có giới hạn:** đo thời điểm Overloaded, pending tasks và backlog bắt đầu tăng.
5. **Retry storm:** kiểm tra với traffic generator có trần tổng request; đo sự khuếch đại khi backoff có/không có jitter.
6. **Idempotent write:** tạo event ID cố định, giả lập timeout, retry có điều tiết và kiểm tra chỉ có một row logic.
7. **Non-idempotent counter/list operation:** kiểm thử giả lập trên dữ liệu lab để nhận diện nguy cơ xử lý lặp.
8. **Hot partition:** so nhiều tenant phân bố đều với một tenant tập trung tải; không giả định thêm node sẽ tự phân tán hot key.
9. **Compaction/repair pressure:** quan sát tác động của công việc nền đã lên lịch; không chạy repair như một phương tiện cố tình gây lỗi nếu chưa có runbook.
10. **Java bounded concurrency:** xác minh khi hết permit thì client giảm/từ chối tải, không tạo queue vô hạn.

Kết luận bài thử phải có **version Cassandra/driver/JDK, số node, RF, CL, workload, payload, latency, error type, retry budget, metrics server và phạm vi không kiểm chứng**. Một lab một node không chứng minh được hành vi quorum của cluster production nhiều DC.

## 17. Bài tập tình huống

### Bài 1 — ReadFailure khác ReadTimeout ra sao?

Ứng dụng nhận ReadFailure ở một phân vùng có nhiều tombstone, còn một truy vấn khác nhận ReadTimeout khi replica bị disk I/O chậm.

**Câu hỏi:** Vì sao không nên xử lý cả hai bằng vòng lặp retry liên tục?

**Đáp án gợi ý:** ReadFailure có thể liên quan lỗi xử lý cụ thể, ReadTimeout thiếu phản hồi trước deadline. Cả hai cần log/metrics để tìm nguyên nhân; retry hàng loạt không sửa tombstone, I/O hay data model và có thể tăng tải.

### Bài 2 — WriteFailure có nghĩa chưa ghi?

Ghi LOCAL_QUORUM trên RF = 3; một replica báo thành công, replica khác báo lỗi, không đủ phản hồi. Client bắt WriteFailure.

**Câu hỏi:** Có thể tạo event ID khác và retry không?

**Đáp án gợi ý:** Không mặc nhiên. Một replica có thể đã áp dụng ghi. Giữ event ID ổn định, đánh giá idempotency và đối soát trạng thái nếu kết quả mơ hồ.

### Bài 3 — Overloaded và mở rộng ứng dụng

Một cluster bị Overloaded sau khi số instance Java tăng gấp đôi, mỗi instance có thể giữ 1.000 request in-flight.

**Câu hỏi:** Tại sao thêm application instance có thể làm tình hình nặng hơn?

**Đáp án gợi ý:** Tổng concurrency/request rate tăng; coordinator/replica, disk và queue không tự mở rộng theo client. Giới hạn in-flight per instance và tổng thể, backpressure, giảm retry storm và capacity planning.

### Bài 4 — Điều kiện LOCAL_QUORUM

RF = 3 ở dc1. Một replica DOWN, một replica còn UP nhưng thường xuyên timeout.

**Câu hỏi:** LOCAL_QUORUM còn được bảo đảm chỉ vì cấu hình RF 3 không?

**Đáp án gợi ý:** Không. Cần 2 phản hồi trong local DC, trong khi chỉ một replica đáp ứng ổn. Khôi phục replica hoặc xử lý disk/GC/network; hạ CL phải là quyết định nghiệp vụ có kiểm soát.

### Bài 5 — Một counter increment timeout

Một request cộng counter bị WriteTimeout. Driver được cấu hình retry đến 3 lần.

**Câu hỏi:** Điều gì nguy hiểm?

**Đáp án gợi ý:** Phép tăng không idempotent; lần đầu có thể đã được áp dụng. Retry có thể cộng thêm. Cần thiết kế xử lý trùng hoặc mô hình sự kiện phù hợp, không chỉ chỉnh retry count.

### Bài 6 — Retry budget theo deadline

Endpoint có deadline 2 giây, mỗi thử Cassandra có timeout tối đa 1,5 giây. Một lập trình viên muốn retry 3 lần với backoff 1 giây.

**Câu hỏi:** Vì sao kế hoạch không phù hợp?

**Đáp án gợi ý:** Tổng thời gian chờ có thể vượt deadline nhiều lần. Phải lập retry budget gồm thời gian từng request, backoff và chi phí xử lý; có thể không retry khi không còn đủ thời gian.

### Bài 7 — Hot partition và RF

Một tenant nhận 80% request. Đội vận hành tăng RF từ 3 lên 5 để giảm hot partition.

**Câu hỏi:** RF cao hơn có tự chia partition thành các mảnh và tăng throughput theo tỷ lệ 5/3 không?

**Đáp án gợi ý:** Không. Mỗi replica vẫn giữ bản sao partition, ghi có thể cần thêm tài nguyên duy trì. Cần phân phối partition key/bucket/shard theo access pattern và đo lại tải.

### Bài 8 — Phân loại lỗi ở hai tầng

Ứng dụng ghi log một **RejectedExecutionException** từ semaphore do hết permit; metric Cassandra Overloaded không tăng.

**Câu hỏi:** Có thể khẳng định Cassandra gửi OverloadedException không?

**Đáp án gợi ý:** Không. Đây là **client-side admission rejection**. Cần phân biệt với phản hồi Overloaded của Cassandra; ứng dụng giảm tải có thể đang bảo vệ cluster thành công.

## 18. Checklist vận hành và lập trình

- [ ] Phân loại chính xác ReadFailure, WriteFailure, Overloaded, ReadTimeout, WriteTimeout, Unavailable và timeout/client/network.
- [ ] Có RF, topology/DC, consistency level và tình trạng replica ở thời điểm lỗi.
- [ ] Không xem WriteFailure/WriteTimeout là bằng chứng **không có replica nào đã ghi**.
- [ ] Retry chỉ khi an toàn theo ngữ nghĩa nghiệp vụ, idempotency, deadline và retry budget.
- [ ] Không auto retry vô hạn khi Overloaded, không tạo retry storm.
- [ ] Không hạ consistency level ngầm để che lỗi availability.
- [ ] Prepared/bind có đủ partition key, dữ liệu theo bucket/shard hợp lý.
- [ ] Collection, mutation, batch và partition được giới hạn kích thước.
- [ ] Java driver có bounded in-flight, queue hữu hạn và backpressure.
- [ ] Phân biệt driver retry với application retry, thống kê tổng attempts.
- [ ] Theo dõi p95/p99, timeout/error type, queue/dropped messages, disk I/O, GC, memory và compaction.
- [ ] Dùng server logs ở coordinator/replica liên quan, không chỉ log application.
- [ ] Có công cụ nodetool/metrics phù hợp phiên bản và runbook bảo vệ dữ liệu.
- [ ] Kiểm tra TTL/tombstone, repair và backup khi có nguy cơ mất/sai dữ liệu.
- [ ] Test trên topology đại diện trước khi thay retry policy, timeout hoặc concurrency trong production.
- [ ] Log query shape và operation metadata, không ghi dữ liệu nhạy cảm/raw bind values.

## 19. Tổng kết

**ReadFailure** và **WriteFailure** là các dấu hiệu thất bại trong quá trình server xử lý đọc/ghi; **ReadTimeout/WriteTimeout** liên quan không đủ phản hồi trong thời hạn, còn **Overloaded** báo áp lực tiếp nhận/xử lý. Các loại lỗi này không nên bị gộp thành một câu lệnh “retry càng nhanh càng tốt”. Đặc biệt, kết quả ghi thất bại hoặc timeout có thể **không xác định** đối với client.

Trong Cassandra, xử lý lỗi hiệu quả bắt đầu từ **partition key, topology/RF, consistency level, tình trạng replica, hot partition, tombstone, compaction và repair**. Ở Java Driver 4.x, cần bắt đúng exception, giữ idempotency, đặt giới hạn retry/deadline, điều tiết in-flight và theo dõi cả phía client lẫn server. **Mục tiêu không chỉ giảm số exception được ghi nhận, mà là phục hồi khả năng phục vụ với dữ liệu đúng và tải bền vững.**
