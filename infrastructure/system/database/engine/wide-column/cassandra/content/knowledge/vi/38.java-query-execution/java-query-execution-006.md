# Routing key và điều kiện định tuyến theo token trong Apache Cassandra Java Driver

## 1. Định tuyến một truy vấn Cassandra: vấn đề nằm ở đâu?

Trong Apache Cassandra, dữ liệu theo mô hình **wide-column** được phân phối trên nhiều node dựa vào **partition key**. Khi ứng dụng Java chạy CQL, một node **coordinator** tiếp nhận request và làm việc với các **replica** nắm giữ partition liên quan. Replication factor, datacenter, rack và consistency level quyết định những phản hồi nào cần thiết để request hoàn thành.

Với một câu `SELECT` theo đúng partition key, Java Driver có thể dùng **routing key** để suy ra **token**, đối chiếu **token map** của cluster và **ưu tiên một node có dữ liệu làm coordinator**. Đây là nền tảng của *token-aware routing*.

Mục tiêu của bài thuộc chương **Truy vấn từ Java**, module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**:

1. Phân biệt **partition key**, **routing key**, **token**, **replica** và **coordinator**.
2. Hiểu đường đi từ các giá trị CQL đã bind đến routing key và token.
3. Xác định **điều kiện để Java Driver 4.x tự định tuyến theo token**.
4. Giải thích những truy vấn **không có một routing key duy nhất** như nhiều partition, scan theo token range hoặc query không đủ thông tin khóa.
5. Sử dụng `PreparedStatement`, `BoundStatement` và thông tin thực thi để chẩn đoán routing.
6. Hiểu mối liên hệ giữa token-aware routing, **LOCAL_QUORUM**, multi-DC, topology change và tải replica.
7. Thiết kế kiểm thử, metric và quy trình xử lý p99 hoặc hotspot mà không tự suy diễn mọi query đều được gửi trực tiếp tới replica tối ưu.

**Lưu ý phiên bản:** ví dụ Java dùng **Apache Cassandra Java Driver 4.x** với package `com.datastax.oss.driver.api.*`. Driver 3.x có package và cấu hình load-balancing khác; không áp dụng máy móc các tùy chọn của `TokenAwarePolicy` đời cũ cho 4.x.

## 2. Năm khái niệm bắt buộc phải tách biệt

| Khái niệm | Nghĩa | Điều không nên nhầm |
|---|---|---|
| **Partition key** | Một hoặc nhiều cột CQL thuộc thành phần partition của primary key | Không phải clustering key hoặc toàn bộ primary key |
| **Routing key** | Chuỗi **bytes mã hóa** đại diện giá trị partition key cho một request | Không phải tên table, raw UUID string hoặc token số |
| **Token** | Giá trị do **partitioner** tính từ routing key, dùng định vị trên vòng token | Không phải địa chỉ IP hay ID của một replica duy nhất |
| **Replica** | Node giữ bản sao partition, theo keyspace replication strategy và topology | Không đồng nghĩa coordinator của mọi query |
| **Coordinator** | Node nhận và điều phối request CQL tới replica cần thiết | Không nhất thiết phải giữ partition đó |

Ví dụ sơ đồ logic:

~~~mermaid
flowchart LR
    A["CQL: WHERE device_id = ? AND event_day = ?"] --> B["Java Driver: bind UUID + date"]
    B --> C["Routing key: binary partition-key components"]
    C --> D["Partitioner: token"]
    D --> E["Token map + RF + DC/rack"]
    E --> F["Replica set của partition"]
    F --> G["Load-balancing ưu tiên coordinator phù hợp"]
    G --> H["Coordinator gửi request tới replica theo CL"]
~~~

Sơ đồ này trình bày luồng **quyết định định tuyến ở phía client**; Cassandra server vẫn tự xác minh token, replica placement và điều kiện nhất quán khi thực thi. Routing key ở client là **thông tin hỗ trợ chọn node**, không trao quyền cho client tự quyết định dữ liệu nằm ở đâu.

### 2.1. Phân biệt primary key và partition key

Một bảng có khóa:

~~~cql
PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
~~~

thì:

- Partition key: **`tenant_id`, `device_id`, `event_day`**.
- Clustering key: **`event_time`**.
- Primary key toàn bộ: cả bốn cột.
- Routing key: mã hóa **ba giá trị partition key**, không gồm `event_time`.
- Mọi row cùng `(tenant_id, device_id, event_day)` nằm trong **cùng logical partition**, dù có hàng nghìn `event_time` khác nhau.

Do đó, thay `event_time` trong `WHERE` không làm đổi token nếu ba giá trị partition key giữ nguyên. Ngược lại, đổi `event_day` thường đổi routing key và token, ngay cả khi `device_id` vẫn giữ.

## 3. Dữ liệu thực hành: một bảng telemetry theo tenant, thiết bị và ngày

Giả sử datacenter lab tên `dc1`, cluster có đủ node đáp ứng RF=3:

~~~cql
-- Chỉ tạo trong môi trường lab được cấp phép.
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_tenant_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Ví dụ ghi dữ liệu:

~~~cql
INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value, status)
VALUES (
    22222222-2222-2222-2222-222222222222,
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value, status)
VALUES (
    22222222-2222-2222-2222-222222222222,
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1,
    'OK'
);
~~~

Cả hai row có chung partition key và thường đi đến **cùng một tập replica**, vì `event_time` chỉ là clustering key.

Truy vấn tương ứng:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = 22222222-2222-2222-2222-222222222222
  AND device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Đây là một truy vấn có **đủ cả ba giá trị partition key** và một logical partition đích rõ ràng. Nó là trường hợp điển hình để driver hỗ trợ token-aware routing.

## 4. Routing key được tạo như thế nào?

### 4.1. Không phải phép nối ba chuỗi UUID/ngày

Partition key là các giá trị được Cassandra mã hóa theo **CQL type**. Java Driver có codec để biến `UUID`, `LocalDate`, `String` và các kiểu dữ liệu khác thành biểu diễn bytes phù hợp giao thức.

Với partition key **một thành phần** như `device_id uuid`, routing key gắn với bytes mã hóa UUID đó.

Với partition key **nhiều thành phần** như `(tenant_id, device_id, event_day)`, routing key cần **mã hóa tổng hợp có ranh giới từng thành phần**, không được nối nguyên các chuỗi người dùng nhìn thấy.

Ở mức khái niệm:

~~~text
Partition values:
    tenant_id = UUID(...)
    device_id = UUID(...)
    event_day = LocalDate(...)

CQL codecs:
    tenant_id -> byte sequence A
    device_id -> byte sequence B
    event_day -> byte sequence C

Composite routing key:
    encoded component A + boundary metadata
    encoded component B + boundary metadata
    encoded component C + boundary metadata
~~~

Phương thức mã hóa cụ thể tuân theo quy tắc composite partition key của protocol/Cassandra. **Không tự viết `tenant + ":" + device + ":" + day`** rồi hash: cách đó không tạo routing key Cassandra hợp lệ.

### 4.2. Thứ tự thành phần quan trọng

Giá trị `(tenant_id=A, device_id=B, event_day=C)` khác `(tenant_id=A, device_id=C, event_day=B)`. Các thành phần phải được mã hóa **đúng thứ tự partition key trong schema**, không phải theo thứ tự ngẫu nhiên của JSON hay Map.

Với prepared statement, driver dựa trên **metadata của statement và schema** để biết bind marker nào tương ứng thành phần partition key. Điều này an toàn và ít lỗi hơn tự lắp routing key từ các tham số HTTP.

### 4.3. Routing key không phải thông tin xác thực tenant

Một request có routing key đúng chỉ chứng tỏ nó có thể được định tuyến tới replica của partition tương ứng. Nó **không chứng minh người dùng có quyền đọc partition**.

Nếu ứng dụng multi-tenant, `tenant_id` phải được lấy từ **principal đã xác thực** hoặc kiểm quyền rõ ràng; không chấp nhận một `tenant_id` khác do caller gửi chỉ vì Java đã bind thành UUID hợp lệ.

## 5. Routing key biến thành token ra sao?

### 5.1. Vai trò của partitioner

**Partitioner** biến routing key bytes thành **token**. Nhiều cluster Cassandra hiện đại dùng `Murmur3Partitioner`, tạo token trong không gian số nguyên 64-bit có dấu. Những partitioner khác có thể tồn tại theo phiên bản/cluster, vì vậy không nên hard-code một hàm hash hoặc kích thước token cho mọi môi trường.

Đường đi logic:

~~~text
Serialized routing key (bytes)
       |
       v
Configured partitioner, ví dụ Murmur3Partitioner
       |
       v
Token trên vòng phân vùng
       |
       v
Token ownership + replication strategy
       |
       v
Một tập replica cho keyspace cụ thể
~~~

**Token không phải khóa duy nhất của row.** Một token đại diện vị trí trên ring; có thể có collision giữa các partition keys khác nhau, và một node thường sở hữu **nhiều token ranges** khi dùng vnodes.

### 5.2. Token không bằng địa chỉ replica

Ví dụ minh họa (không phải token thật được tính từ các UUID):

| Partition key | Token giả định | Hệ quả |
|---|---:|---|
| Tenant A / Device X / 21-11 | -7.100.000 | Đi tới một vùng trên token ring |
| Tenant A / Device X / 22-11 | 4.300.000 | Có thể đi tới vùng/node khác |
| Tenant A / Device Y / 21-11 | 4.100.000 | Có thể ở gần token của dòng trước |

Một token map **chỉ nói về vị trí và node** khi kết hợp với replication strategy và topology hiện tại. Không thể suy trực tiếp “token dương thuộc node B” hay “token nhỏ hơn nghĩa dữ liệu cũ hơn”.

### 5.3. Local datacenter và replica placement

Với keyspace `NetworkTopologyStrategy` và RF=3 ở `dc1`, token map kết hợp RF/topology để xác định **ba replica** cho một partition trong DC đó.

Nếu cùng token nhưng hỏi cho **keyspace có replication settings khác**, tập replica có thể khác. Vì vậy thông tin định tuyến thường cần đồng thời:

- **Routing key hoặc token**.
- **Routing keyspace**, để biết replication strategy/RF cần áp dụng.
- **Token map, DC/rack và node liveness** theo metadata.
- **Load-balancing policy** của Java Driver.

**Không dùng token để bỏ qua khái niệm keyspace.** Một token đơn lẻ không đủ cho mọi quyết định replica placement.

## 6. Token-aware routing trong Java Driver 4.x

### 6.1. Vấn đề chọn coordinator

Một câu truy vấn có partition đích rõ nhưng gửi đến coordinator **không phải replica** vẫn có thể hoạt động:

~~~text
Java Client -> Coordinator N4 (không giữ partition)
                         |
                         +-> Replica N1
                         +-> Replica N2
                         +-> Replica N3
~~~

Nếu driver ưu tiên coordinator là một **replica** phù hợp, đường đi có thể giảm một số bước chuyển tiếp liên node:

~~~text
Java Client -> Coordinator N2 (đồng thời là replica)
                         |
                         +-> Replica N1
                         +-> Replica N3
~~~

Đây là **lợi ích có điều kiện**, không phải cam kết loại bỏ tất cả network hops: consistency level có thể cần nhiều replica; speculative execution, replica health, DC routing và các ràng buộc khác vẫn ảnh hưởng.

### 6.2. Java Driver 4.x có token awareness trong load balancing

Trong Java Driver 4.x, load-balancing mặc định thường kết hợp **datacenter awareness** và **token awareness** theo metadata của cluster; ứng dụng không cần sao chép nguyên cách cấu hình `TokenAwarePolicy` của Java Driver 3.x.

Khi có routing key/token và routing keyspace hợp lệ, policy có thể **ưu tiên những replica phù hợp trong local datacenter** để tạo query plan. Nếu không đủ thông tin hoặc metadata chưa cập nhật, driver vẫn có thể chọn một node hợp lệ làm coordinator theo policy và trạng thái kết nối.

**Token-aware là ưu tiên chọn coordinator, không phải một bảo đảm cứng rằng mọi request đều đi tới replica.**

### 6.3. Contact point không phải đích của mọi query

Khi tạo `CqlSession`, contact points chủ yếu dùng để **khởi tạo kết nối và khám phá cluster**. Sau đó driver xây dựng connections tới các node thích hợp và dùng query plan của load-balancing policy.

Nếu ứng dụng cấu hình một contact point N1, điều đó **không đồng nghĩa mọi SELECT sẽ có coordinator N1**.

~~~mermaid
flowchart TD
    A["Java CqlSession"] --> B["Contact points: khám phá cluster"]
    B --> C["Metadata: token map, keyspace, nodes"]
    D["BoundStatement"] --> E{"Có routing key và keyspace?"}
    E -->|Có| F["Ưu tiên replica theo token và local DC"]
    E -->|Không| G["Fallback query plan theo policy"]
    C --> F
    C --> G
    F --> H["Coordinator được chọn"]
    G --> H
    H --> I["Replica read/write theo CL"]
~~~

## 7. Khi nào driver tự biết routing key?

Driver có khả năng suy ra routing key tốt nhất khi một **prepared statement** cung cấp đủ thông tin để xác định **một partition key duy nhất**.

### 7.1. Điều kiện thường cần

1. Query được **prepare** trên cluster và có metadata đủ để nhận biết partition key columns.
2. `WHERE` hoặc giá trị tương ứng trong mutation xác định **toàn bộ partition key**.
3. Các thành phần partition key đều là **giá trị cụ thể, bind hợp lệ**, không `null`/unset trái quy tắc.
4. CQL query tương ứng **một logical partition**, không phải nhiều partition tùy ý.
5. Driver có thể biết **routing keyspace** và token map để gắn partition với replica placement.
6. Load-balancing policy đang sử dụng **có áp dụng token-aware query planning** cho request đó.
7. Node/replica phù hợp đang có thể sử dụng; nếu không, policy có thể fallback.

Điều kiện trên là **mô hình nhận biết thực dụng**, không phải hợp đồng mọi dạng CQL biểu thức đều cho ra routing key trên mọi phiên bản driver. Các câu có biểu thức phức tạp, named markers, batch hoặc cấu trúc ít phổ biến cần được kiểm chứng thực tế.

### 7.2. Query điển hình: đủ partition key và dùng markers

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Ba marker đầu được dùng cho partition key. Marker `LIMIT` **không tham gia routing key**; thay LIMIT không đổi token của partition.

### 7.3. Không cần SELECT chính partition key để routing

Query sau vẫn có partition key trong `WHERE` dù projection chỉ lấy hai cột:

~~~cql
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

Driver có thể suy ra routing key từ **bind markers và prepared metadata**; không cần đưa `tenant_id`, `device_id` và `event_day` vào danh sách `SELECT` chỉ để hỗ trợ routing.

### 7.4. Clustering range không phá routing một partition

~~~cql
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT ?;
~~~

Bởi tất cả thành phần partition key vẫn là equality và được bind, truy vấn chỉ nằm trong **một partition**, dù clustering range có hàng nghìn row. Giá trị `event_time` giúp tìm phạm vi bên trong partition chứ không đổi routing token.

**Định tuyến đúng không đồng nghĩa truy vấn rẻ:** một partition rộng, nhiều tombstone hoặc SSTable vẫn có read amplification.

## 8. Java Driver 4.x: prepared, bind và kiểm tra routing key

### 8.1. Ví dụ repository dùng typed markers

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.nio.ByteBuffer;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class RoutedReadingRepository {
    private final CqlSession session;
    private final PreparedStatement readQuery;

    public RoutedReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.readQuery = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_tenant_device_day " +
            "WHERE tenant_id = ? AND device_id = ? " +
            "AND event_day = ? LIMIT ?"
        );
    }

    public void read(UUID tenantId, UUID deviceId,
                     LocalDate day, int maxRows) {
        if (maxRows < 1 || maxRows > 100) {
            throw new IllegalArgumentException(
                "maxRows must be in [1, 100]");
        }

        BoundStatement statement = readQuery
            .bind(tenantId, deviceId, day, maxRows)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(maxRows, 50));

        // Chỉ kiểm tra SỰ CÓ MẶT, không log bytes
        // vì routing key có thể tiết lộ partition ID.
        ByteBuffer key = statement.getRoutingKey();
        if (key == null) {
            System.out.println(
                "No routing key inferred for this statement");
        } else {
            System.out.println(
                "Routing key available; bytes=" + key.remaining());
        }

        ResultSet rs = session.execute(statement);
        for (Row row : rs) {
            handle(row.getInstant("event_time"),
                   row.getDouble("reading_value"),
                   row.getString("status"));
        }
    }

    private void handle(java.time.Instant at,
                        double value, String status) {
        // Demo: thực hiện xử lý có giới hạn, không lưu mọi row.
    }
}
~~~

Đoạn code chỉ minh họa request đồng bộ; session được tạo/đóng theo vòng đời service, có cấu hình local DC/auth/TLS và kiểm thử tương thích bản driver thực tế.

### 8.2. Giải thích từng điểm quan trọng

- Query template được `prepare` **một lần** và tái sử dụng.
- Ba giá trị partition key được bind bằng đúng kiểu `UUID`, `UUID`, `LocalDate`.
- `maxRows` được bind nhưng **không nằm trong routing key**.
- `getRoutingKey()` kiểm tra liệu statement có routing key khả dụng ở phía Java.
- Nếu trả `null`, đó là tín hiệu cần chẩn đoán, không nhất thiết là query sai hoặc bị server từ chối.
- `LOCAL_QUORUM` quyết định điều kiện replica responses, không phải “yêu cầu driver luôn chọn node X”.
- `setPageSize` giới hạn mục tiêu mỗi page, không thay số row tổng của `LIMIT`.
- Code duyệt `ResultSet` từng row thay vì dùng `all()` trên một kết quả lớn.

### 8.3. Có nên log routing key hoặc token?

**Không ghi raw routing key bytes** vào log/metric label production: chúng có thể encode trực tiếp tenant ID, UUID hoặc partition key nhạy cảm. Token cũng có thể phản ánh phân bố dữ liệu và làm tăng cardinality.

Thay vào đó, ghi **operation ID**, boolean `routing_key_present`, local DC, coordinator DC và duration. Nếu cần phân tích một token cụ thể, dùng trace có hạn chế quyền, thời gian giữ và masking thích hợp.

## 9. Đo coordinator thực tế sau execute

### 9.1. Lấy ExecutionInfo

Java Driver 4.x cho phép đọc thông tin thực thi từ ResultSet. Ví dụ:

~~~java
import com.datastax.oss.driver.api.core.metadata.Node;
import com.datastax.oss.driver.api.core.cql.ResultSet;

ResultSet rs = session.execute(statement);
Node coordinator = rs.getExecutionInfo().getCoordinator();

if (coordinator != null) {
    System.out.println(
        "Coordinator DC=" + coordinator.getDatacenter() +
        ", rack=" + coordinator.getRack());
}
~~~

`Node` ở đây là metadata phía driver. Nó hữu ích để biết coordinator được ghi nhận cho request, nhưng **không cho biết mọi replica đã ACK** hoặc mọi bước network bên trong server.

### 9.2. Muốn biết coordinator có phải replica không?

Cần xác minh dựa trên:

1. **Routing key/token** của statement.
2. **Routing keyspace** và replication settings.
3. **Token map** hiện thời của driver/cluster.
4. Tập replica phù hợp với token và keyspace.
5. Coordinator được ghi nhận từ execution info.

Đây là một phép đối chiếu **tại một thời điểm**, không phải một hằng số. Bootstrap, replace, decommission, thay RF, node down và thay topology làm replica set hoặc tính khả dụng thay đổi.

Nếu dashboard muốn có chỉ số “token-aware hit”, phải **tự định nghĩa chính xác metric** và đối chiếu với topology lúc thực thi. Không mặc định Java Driver 4.x cung cấp sẵn một metric tên `token_aware_hit_rate` ở mọi phiên bản.

### 9.3. Lưu ý về nhiều attempt và speculative execution

Một request có thể có retry hoặc speculative execution theo cấu hình. Coordinator cuối cùng được ghi trong `ExecutionInfo` không nhất thiết diễn đạt toàn bộ lịch sử các attempt.

Để chẩn đoán sâu hơn, có thể dùng driver request tracking/instrumentation được phiên bản hỗ trợ, kèm retry/timeout metrics. **Không coi một địa chỉ coordinator đơn lẻ là bằng chứng mọi attempt đều gửi tới đó**.

## 10. Những trường hợp driver không có một routing key duy nhất

### 10.1. Thiếu một thành phần partition key

Với PK `(tenant_id, device_id, event_day)`, đoạn điều kiện sau **chưa xác định một partition duy nhất**:

~~~cql
-- Đây là ví dụ mô tả dạng WHERE KHÔNG ĐỦ partition key;
-- trên bảng đã cho, truy vấn có thể bị Cassandra từ chối.
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?;
~~~

Không có `event_day`, driver không thể tính routing key đầy đủ của partition đó. Cassandra thông thường cũng không cho phép một SELECT tùy ý thiếu thành phần partition key nếu không có access path phù hợp.

**Không thêm `ALLOW FILTERING` chỉ để “làm query chạy”** và kỳ vọng sẽ có token-aware routing như khi đủ partition key. Nó có thể dẫn tới scan rộng và tải replica lớn.

### 10.2. Truy vấn nhiều partition qua IN

Ví dụ với một bảng có partition key đơn:

~~~cql
CREATE TABLE telemetry_lab.latest_by_device (
    device_id uuid PRIMARY KEY,
    last_seen timestamp
);
~~~

Một query nhiều partition:

~~~cql
SELECT device_id, last_seen
FROM telemetry_lab.latest_by_device
WHERE device_id IN (?, ?, ?);
~~~

Ba `device_id` có thể map tới **ba token khác nhau**, nên không tồn tại một routing key đại diện cho cả ba. Cassandra/driver có thể tối ưu một số trường hợp `IN` tùy version, nhưng **không được mặc định cả query là single-partition token-aware**.

Nếu ứng dụng cần đọc rất nhiều device, cần đánh giá:

- Gửi các prepared point reads theo từng device với **concurrency bounded**.
- Query strategy/data model phù hợp access pattern.
- Mức fanout coordinator/replica và network.
- Có nên gom dữ liệu theo partition key mới hay không.

Không tự bắn hàng nghìn future async vô hạn chỉ để mỗi request có routing key riêng.

### 10.3. Không có prepared metadata đáng tin

Một `SimpleStatement` được tạo bằng nối chuỗi raw CQL có thể không có đầy đủ thông tin để driver suy ra routing key. Một số trường hợp driver/tooling có thể nhận routing hints thủ công, nhưng **không nên dựa vào parser tự đoán mọi biểu thức WHERE**.

Ưu tiên `PreparedStatement`, `BoundStatement` với typed markers. Việc **prepare một string đã bị nối raw input** không bảo vệ được khỏi injection và cũng không đảm bảo routing metadata đúng.

### 10.4. Query có nhiều partition, range scan hoặc secondary access path

Các kiểu query có thể không cho một routing key duy nhất:

- Quét theo **token range**.
- Query không hạn chế partition key.
- Query qua secondary index/search cho nhiều partitions.
- Multi-partition operation hoặc batch nhiều partition.
- Một số biểu thức WHERE/operation mà prepared metadata không đủ để suy ra PK.
- Lệnh schema/administration không gắn một logical partition thông thường.

Không suy luận “`getRoutingKey() == null`” nghĩa tất cả những query này đều sai. Một số chúng hợp lệ cho batch/analytics/admin, nhưng **chi phí và cách định tuyến khác với point read**.

## 11. CQL token(): truy vấn theo vị trí ring, không phải theo thời gian

### 11.1. Hàm token() biểu diễn điều gì?

CQL có hàm `token(...)` để xét token của partition key. Với bảng có partition key composite, phải dùng **đúng các cột partition key và đúng thứ tự**:

~~~cql
-- Ví dụ đọc token của các row thuộc partition đã biết.
SELECT tenant_id, device_id, event_day,
       token(tenant_id, device_id, event_day) AS partition_token,
       event_time
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = 22222222-2222-2222-2222-222222222222
  AND device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 5;
~~~

Mọi row cùng partition key có **cùng token**, dù clustering key `event_time` khác nhau.

**Token không phải timestamp, row sequence hay giá trị có ý nghĩa nghiệp vụ.** Không dùng token để lấy “20 sự kiện mới nhất” hoặc điều hướng theo thời gian.

### 11.2. Token-range scan

Một truy vấn quét phạm vi token, ví dụ trong cluster dùng `Murmur3Partitioner`:

~~~cql
-- Chỉ minh họa cho JOB ĐỌC DỮ LIỆU ĐÃ GIỚI HẠN TẢI.
-- Hai cận token dưới đây là số ví dụ trong signed 64-bit range.
SELECT tenant_id, device_id, event_day,
       event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE token(tenant_id, device_id, event_day) > -5000000000000000000
  AND token(tenant_id, device_id, event_day) <= 0;
~~~

Truy vấn này có thể chạm **nhiều partition trên nhiều node**. Định tuyến của nó không tương đương với một prepared SELECT theo equality của toàn bộ partition key.

Nó có thể hữu ích cho **data export, backfill hoặc kiểm kê theo token ranges** nếu có capacity plan, read concurrency, page size, checkpoint và giới hạn tài nguyên. Không dùng làm API tương tác mặc định.

### 11.3. Ranh giới token cần được quản lý cẩn thận

Nếu job chia ring thành nhiều ranges:

- Chọn convention như **`(start, end]`** và áp dụng nhất quán.
- Không tạo **lỗ hổng** giữa ranges hoặc đếm lặp boundary.
- Xử lý **wrap-around** của token ring khi range qua min/max.
- Dùng partitioner tương ứng với cluster, không assume Murmur3 mọi nơi.
- Theo dõi node/topology thay đổi nếu job chạy nhiều giờ.
- Không cho rằng mỗi token range có cùng **bytes hoặc số partition**, dù chúng có độ dài token bằng nhau.
- Giới hạn số range chạy đồng thời theo **node chịu tải xấu nhất**, không chỉ tổng worker.

### 11.4. Token-range scan khác keyset pagination

| Khía cạnh | Token-range scan | Keyset theo clustering key |
|---|---|---|
| Trục chia dữ liệu | Token/partition placement | Thứ tự clustering trong partition |
| Mục đích tốt | Export/backfill/parallel scan | UI “xem tiếp” theo thời gian/sort |
| Có bao quát nhiều partition? | Có thể | Thường một partition hoặc tập có thiết kế riêng |
| Có thứ tự nghiệp vụ? | Không | Có thể, nếu clustering schema hỗ trợ |
| Dễ token-aware single partition? | Không | Có, nếu đủ PK equality |
| Cần giới hạn tải? | Rất cần | Vẫn cần, nhất là partition rộng |

**Không dùng token như `OFFSET` hoặc cursor UI.** Token giải quyết phân phối dữ liệu, không giải quyết thứ tự diễn tiến bản ghi.

## 12. Routing token thủ công: lợi ích và rủi ro

Một số kiểu statement/driver cho phép bổ sung **routing key hoặc routing token hint** khi caller biết chắc partition đích, chẳng hạn trong query builder hoặc custom statement.

Đây là kỹ thuật nâng cao; chỉ dùng khi:

1. Có lý do thực tế để không thể dùng prepared statement đủ PK.
2. Partition key đã được mã hóa **đúng kiểu CQL và đúng thành phần**.
3. Biết **routing keyspace** chính xác, phù hợp RF và replica placement.
4. Routing hint **trùng với partition key thực sự trong statement**.
5. Có kiểm thử trên cluster lab và đo coordinator/latency trước–sau.
6. Có kế hoạch bỏ hint nếu schema, partitioner hoặc routing logic thay đổi.

**Không tự tạo token bằng Java `hashCode()`, `UUID.hashCode()` hay MD5 tùy ý.** Token Cassandra phụ thuộc partitioner và encoding partition key.

### 12.1. Routing hint không sửa được câu WHERE sai

Giả sử query có `WHERE device_id = A` nhưng bạn tự đặt routing hint thuộc partition B. Driver có thể ưu tiên coordinator không phù hợp; **server vẫn thực thi query theo WHERE và metadata của cluster**, chứ không tự thay dữ liệu của A thành B.

Một hint không chính xác thường làm **hiệu năng tệ đi**, gây extra hops hoặc chẩn đoán khó, không phải phương pháp sửa missing partition key.

### 12.2. Đừng cố “ép tất cả request đến cùng một node”

Sử dụng một routing key cố định cho mọi query sẽ làm mất ích lợi token-aware, có thể tạo hotspot coordinator hoặc gửi các query vào node không giữ dữ liệu.

Nếu cần **pin** một thao tác quản trị tới node cụ thể, đó là bài toán khác với routing key theo dữ liệu. Đừng dùng mẹo thay token để thay thế kiến trúc quản trị hoặc load-balancing được thiết kế.

## 13. Token-aware routing, consistency level và replica responses

### 13.1. Ví dụ RF=3, LOCAL_QUORUM

Giả sử token của partition P thuộc các replica N1, N2, N3 trong `dc1`.

~~~text
Java Driver chọn coordinator N2 theo token-aware routing
    |
    +-- N2 là một replica có partition P
    +-- N2 có thể trao đổi với N1 và N3
    +-- LOCAL_QUORUM cần số phản hồi tương ứng
        với quorum RF của dc1: 2/3
~~~

**Không suy ra chỉ N2 nhận mutation hoặc chỉ N2 đọc dữ liệu.** Coordinator vẫn phải đáp ứng quy tắc CL và hành vi đọc/ghi của Cassandra.

### 13.2. Token-aware không thay đổi CL

| Cấu hình | Quyết định gì? | Không quyết định gì? |
|---|---|---|
| Routing key/token | Gợi ý partition liên quan để chọn coordinator/replica ưu tiên | Không tăng/giảm RF |
| Token-aware load balancing | Ưu tiên coordinator phù hợp theo replica metadata | Không tự làm dữ liệu fresh hơn |
| `LOCAL_ONE` | Điều kiện phản hồi trong local DC | Không đảm bảo đọc mới nhất mọi trường hợp |
| `LOCAL_QUORUM` | Quorum trong local DC | Không tự sửa routing key thiếu |
| `QUORUM` | Quorum theo RF/chiến lược của request | Không chọn một “home node” cố định |
| `EACH_QUORUM` khi thao tác hỗ trợ | Quorum tương ứng tại mỗi DC | Không làm một multi-partition scan rẻ hơn |

**Hạ CL để giảm p99** là thay đổi yêu cầu consistency, không phải “sửa token routing”. Hai quyết định cần được tách biệt trong thiết kế Java service.

### 13.3. Multi-DC

Với keyspace được replicate ở `dc1` và `dc2`, ứng dụng trong `dc1` thường cấu hình **local datacenter** phù hợp. Driver có thể ưu tiên các replica trong DC cục bộ khi routing metadata hợp lệ.

Nếu local DC bị cấu hình sai, ứng dụng có thể gặp kết nối/định tuyến khác mong đợi. Tuy nhiên chỉ cần thấy coordinator ở DC khác **chưa đủ** kết luận nguyên nhân là routing key: phải kiểm tra session config, load-balancing policy, node health, request profile và failover policy.

## 14. Token-aware không chữa được hot partition và skew

### 14.1. Trường hợp hot partition

Giả sử 1 thiết bị tạo **30% tổng traffic** dù cluster có 100 thiết bị. Nếu partition key không được bucket hợp lý, phần lớn request sẽ chạm cùng tập replica.

Token-aware routing làm những request ấy **đến đúng replica nhanh hơn**, nhưng không tự phân chia một partition nóng sang nhiều token khác nhau.

Ví dụ thiết kế:

~~~cql
-- Partition cố định theo device có thể quá rộng theo thời gian.
PRIMARY KEY ((device_id), event_time)

-- Bucket theo ngày có thể chia tải theo nhiều partition/token.
PRIMARY KEY ((device_id, event_day), event_time)
~~~

Việc bucket có lợi hoặc không phải dựa trên **truy vấn, write pattern và nhu cầu đọc xuyên ngày**, không áp dụng vô điều kiện. Với thiết bị ghi cực nhiều trong một ngày, có thể cần bucket nhỏ hơn hoặc sharding có kiểm soát, đổi lại đọc phải fanout nhiều partition.

### 14.2. Token distribution không đồng nghĩa load distribution hoàn hảo

Murmur3 giúp phân phối token tương đối đều theo hash, nhưng:

- Partition có **kích thước khác nhau**.
- QPS giữa partition có thể **rất chênh lệch**.
- Các node có dung lượng/IOPS khác nhau hoặc đang compaction/repair.
- Một số partition bị đọc ở CL cao, nhiều tombstone hoặc collection lớn.

Do đó, “token ownership tương đối cân” không có nghĩa CPU/disk/latency theo node sẽ cân.

### 14.3. Định tuyến còn phụ thuộc row size và pagination

Hai truy vấn cùng routing key nhưng khác số row trả về có thể tải rất khác:

~~~cql
-- Cùng partition:
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT 20;

-- Cùng partition nhưng range rộng có thể trả nhiều trang:
SELECT event_time, reading_value
FROM telemetry_lab.readings_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?;
~~~

Routing key bằng nhau không có nghĩa resource cost bằng nhau. Phải xem `LIMIT`, page size, số SSTable được đọc, tombstone, concurrency và backpressure.

## 15. Batch và nhiều mutation có routing key ra sao?

### 15.1. Single-partition operation

Một prepared `INSERT` hoặc `UPDATE` với đầy đủ partition key có thể mang routing key tương ứng.

~~~cql
INSERT INTO telemetry_lab.readings_by_tenant_device_day
(tenant_id, device_id, event_day, event_time, reading_value)
VALUES (?, ?, ?, ?, ?);
~~~

Routing key được xác định bởi ba giá trị đầu; `event_time` là clustering key và `reading_value` là payload.

### 15.2. Multi-partition batch

Một CQL batch gồm mutation cho nhiều partition **không có một routing key đại diện chính xác cho tất cả**. Ngay cả khi một số driver có thể suy ra hint cho những loại batch được cấu trúc chặt, không giả định một batch nhiều partition luôn token-aware như point write.

Hơn nữa, **logged batch nhiều partition không phải bulk loader lý tưởng**. Nó có thể tạo batchlog overhead, request lớn và nhiều replica fanout.

Với bulk import/backfill, thường cần:

- Chia work items theo partition/token range hợp lý.
- Prepared point writes.
- Concurrency, rate và bytes/s giới hạn.
- Checkpoint và retry có kiểm soát.
- Quan sát compaction, commit log, replica p99 và disk free.

**Đừng ghép nhiều partition vào batch lớn chỉ để “ít request hơn”.**

## 16. Ứng dụng Java: truy vấn async vẫn cần routing metadata

Java Driver 4.x hỗ trợ `executeAsync`; sử dụng async không làm mất routing key của một `BoundStatement` nếu các điều kiện suy luận vẫn được thỏa mãn.

~~~java
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import java.util.concurrent.CompletionStage;

BoundStatement bound = prepared.bind(
        tenantId, deviceId, eventDay, 50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);

CompletionStage<AsyncResultSet> stage =
    session.executeAsync(bound);
~~~

Trong ví dụ, `prepared` là prepared SELECT theo ba cột partition key, còn các biến có kiểu `UUID`, `UUID`, `LocalDate` và `int` tương ứng.

**Lưu ý:**

- Async routing vẫn do driver load-balancing thực hiện.
- Token awareness không chặn ứng dụng tạo **hàng nghìn future** cùng lúc.
- Cần backpressure/in-flight limit và deadline khi bulk read.
- Nếu có nhiều page, `AsyncResultSet` có `currentPage()`, `hasMorePages()` và `fetchNextPage()`; nên lấy tiếp theo năng lực xử lý downstream.
- Không block callback thread của driver bằng I/O dài hoặc `Thread.sleep`.

### 16.1. Routing key + rate limit

Một ứng dụng có thể có routing key hoàn hảo nhưng gửi 10.000 request/s vào cùng partition, làm quá tải chính tập replica đó. **Token-aware chỉ chọn đường đi, không làm rate limiting**.

Với hotspot, cần đo **requests/s hoặc bytes/s theo query shape/partition group**, dùng quota và cân nhắc thay data model.

## 17. Metadata thay đổi: bootstrap, replace, repair và nâng cấp

### 17.1. Ring không bất biến

Trong Cassandra, các thao tác như:

- **Bootstrap** thêm node.
- **Decommission/replace** thay đổi membership/placement.
- **Đổi RF** và topology DC/rack.
- **Streaming, rebuild và repair**.

có thể làm thay đổi chủ sở hữu token/range hoặc trạng thái replica.

Java Driver theo dõi cluster metadata để cập nhật thông tin định tuyến. Tuy vậy **metadata phía driver có thể trễ trong một thời điểm**, nhất là ngay sau thay đổi topology hoặc sự cố network.

### 17.2. Không cache replica mapping vĩnh viễn ở ứng dụng

Anti-pattern:

~~~text
Startup:
  token T -> node A
  cache mapping này vào HashMap tĩnh

Nhiều giờ sau:
  cluster bootstrap/replace node
  vẫn gửi mọi query token T theo mapping cũ
~~~

Hướng đúng là để driver/load-balancing cập nhật metadata; nếu ứng dụng cần một cache hỗ trợ vận hành, nó phải có cơ chế refresh/invalidations phù hợp.

### 17.3. Tracing và kiểm tra topology

Các lệnh giúp xác minh cluster:

~~~bash
# Trạng thái node, DC/rack, token ownership.
nodetool status

# Thông tin node và release đang chạy.
nodetool info

# Streaming khi bootstrap/rebuild/repair.
nodetool netstats

# Thread pool và dropped messages.
nodetool tpstats

# Compaction backlog và tiến độ.
nodetool compactionstats
~~~

Không lấy `nodetool status` từ một node làm “chân lý bất biến” của toàn cluster: gossip view có thể lệch tạm thời. Cần đối chiếu node liên quan, metadata và logs trong một cửa sổ thời gian.

## 18. Quan sát token-aware routing: những metric nào thực sự hữu ích?

### 18.1. Tầng Java client

Nên có:

- Request QPS, p50/p95/p99 và timeout/unavailable theo **query ID**.
- Số retries/speculative executions và kết quả cuối.
- Request in-flight, queue, connection failures.
- `routing_key_present` theo query template (boolean/counter, không log raw key).
- Coordinator DC/rack hoặc nhóm node (cardinality được kiểm soát).
- Bằng chứng query có full partition key và keyspace hợp lệ.

Không mặc định mọi version driver có sẵn metric tên “token-aware hit”; có thể xây dựng instrumentation riêng khi cần.

### 18.2. Tầng server

Nên có:

- Read/write latency của coordinator và table/node.
- `nodetool tpstats`: Pending/Active/Dropped theo stage.
- `nodetool tablehistograms` hoặc thống kê SSTables per read phù hợp phiên bản.
- `nodetool compactionstats`: backlog và disk pressure.
- Disk IOPS/latency, network RTT/retransmits, CPU/GC.
- Node DOWN/UP, streaming/repair và RF/DC topology.

**Không dùng p99 trung bình từ các node để tính p99 cluster.** Percentile cần phân bố/histogram được tổng hợp đúng và phải xét cả timeout bị loại khỏi những histogram chỉ ghi nhận thành công.

### 18.3. Bảng chẩn đoán

| Triệu chứng | Giả thuyết | Kiểm tra |
|---|---|---|
| `getRoutingKey()==null` với point SELECT | Prepared metadata không đủ, query shape không xác định PK, marker chưa bind | WHERE đủ các thành phần PK, prepared metadata, keyspace |
| Coordinator thường không thuộc replica của token | Load-balancing fallback, metadata stale, local DC, replica health | Query plan, token map, execution info, node status |
| Coordinator ở DC xa | Local DC/session policy sai, failover/routing rule | Driver config, contact points, DC/rack metadata |
| p99 cao dù coordinator là replica | Hot partition, tombstone, disk/GC/network, CL | Query profile, SSTables per read, metrics |
| p99 tăng sau bootstrap | Token/replica placement đổi, streaming tranh I/O | `netstats`, `compactionstats`, topology metadata |
| Nhiều timeout khi chạy IN | Fanout nhiều partition/replica | Phân rã point reads có giới hạn, query model |
| CQL scan theo token range rất chậm | Range lớn, bytes phân bố không đều, concurrency cao | Token range size, disk/CPU, request rate |
| Một node quá nóng nhưng token ownership gần đều | Hot keys hoặc skew QPS/row size | Partition workload, trace, bytes/partition |
| Client retry tăng mạnh | Nút chậm, timeout, chính sách retry quá gắt | Driver retry metrics, overload, backpressure |

**Đừng quy mọi latency về routing.** Token-aware có thể hoạt động đúng mà một replica vẫn chậm do compaction, tombstone, repair hoặc lỗi hạ tầng.

## 19. Runbook A: prepared point read không có routing key

**Tình huống:** Repository có truy vấn theo tenant, device, day nhưng quan sát `BoundStatement.getRoutingKey() == null` sau bind.

**Bước 1 — Xác nhận query thực tế.** Ghi operation ID, query template đã normalize, keyspace/table và phiên bản driver. Tránh log giá trị tenant/device nhạy cảm.

**Bước 2 — Kiểm tra đủ partition key.** Đối chiếu PRIMARY KEY của schema với `WHERE`; query có đủ tenant_id, device_id, event_day không? Các marker có được bind đúng kiểu và đúng thứ tự?

**Bước 3 — Kiểm tra prepared metadata.** Có thật đang dùng `session.prepare` rồi `prepared.bind`, hay trước đó code chuyển sang `SimpleStatement`/string concat? Query có dấu `IN`, biểu thức hoặc filter khiến driver không suy ra single partition không?

**Bước 4 — Kiểm tra keyspace và schema.** Keyspace có tồn tại, routing keyspace có được xác định, schema metadata đã cập nhật sau DDL/upgrade không?

**Bước 5 — Kiểm tra điều kiện runtime.** Có bind null/unset trái quy tắc, nhiều giá trị trong một marker, hoặc custom codec sai không? Nếu query chạy trên replica nhưng không route token-aware, xem fallback/load balancing.

**Bước 6 — Sửa cấu trúc trước khi ép hint.** Ưu tiên prepared statement xác định đầy đủ PK. Chỉ cân nhắc routing hint thủ công khi hiểu encoding/schema và đã test trên lab.

**Bước 7 — Xác minh.** Kiểm tra routing key present, coordinator selection, p95/p99/timeout và correctness; đừng chỉ xác nhận `getRoutingKey()!=null` rồi đóng sự cố.

## 20. Runbook B: p99 tăng sau topology change

**Tình huống:** Sau bootstrap node mới, client p99 tăng và một số coordinator không nằm trong replica set cũ.

1. **Xác nhận change window:** node nào joining/replacing, tokens và RF có thay đổi đúng kế hoạch?
2. **So topology mới:** `nodetool status`, DC/rack, token ownership, gossip và logs.
3. **So client metadata:** driver đã thấy node/host IDs mới và đúng local DC chưa?
4. **Xác định query shape:** request là point read token-aware hay token-range/IN scan vốn không có một routing key?
5. **Kiểm tra background:** `netstats` có streaming, `compactionstats` có backlog, disk/network có saturation không?
6. **Xem request attempts:** coordinator, retry/speculative execution, timeout và time to first page.
7. **Áp dụng biện pháp có rollback:** giảm backfill hoặc concurrency nếu quá tải, xử lý network/metadata qua runbook, không tự sửa token hoặc ép routing giả.
8. **Xác minh SLO:** so p50/p95/p99 và timeout trước–sau, kiểm tra replica health, không chỉ nhìn node `UN`.

**Quan trọng:** sau topology change, coordinator “không nằm trong replica set cũ” có thể là trạng thái **bình thường** vì replica set đã thay đổi. Phải đối chiếu với **token map hiện tại**, không với danh sách hard-code trước bootstrap.

## 21. Runbook C: token-range export làm quá tải cluster

**Tình huống:** Job Java quét token ranges với nhiều workers. Disk latency trên một vài replica tăng, `ReadStage Pending` và timeout cũng tăng.

**Bước 1:** Tạm dừng tăng workers và kiểm tra ngưỡng bảo vệ production.

**Bước 2:** Ghi lại các ranges, partitioner, cách chia boundary, số bytes/s, rows/s và số request in-flight.

**Bước 3:** Xác minh không có lỗ hổng/đếm trùng giữa ranges; xử lý wrap-around của token ring.

**Bước 4:** Tính độ lệch kích thước range theo số bytes thực, không dựa trên khoảng cách token số học.

**Bước 5:** Giảm concurrency/rate theo **node chịu tải xấu nhất**; cân nhắc giờ ít tải và job checkpoint/resume.

**Bước 6:** Theo dõi `tpstats`, `compactionstats`, disk/GC, driver retries và p99 API người dùng.

**Bước 7:** Khi cluster khỏe, tăng rate theo bước nhỏ, duy trì hard-stop. Không nâng CL/giảm CL mù quáng để chữa scan overload.

**Bước 8:** Sau export, đối soát token coverage, logical row/partition identifiers, checksum và các biến đổi xảy ra khi dữ liệu được ghi/xóa giữa các lần page.

**Không mặc định token-range scan có snapshot nhất quán toàn cluster.** Nếu cần point-in-time export, cần thêm cơ chế snapshot/backup hoặc event log/reconciliation phù hợp.

## 22. Những hiểu nhầm thường gặp

| Nhận định | Đánh giá | Lý do |
|---|---|---|
| “Routing key chính là tên partition key.” | **Sai** | Nó là bytes mã hóa **giá trị** partition key |
| “Routing key = token.” | **Sai** | Token được partitioner tính từ routing key |
| “Clustering key là một phần routing key.” | **Sai** | Routing key chỉ dựa trên partition key |
| “Một token luôn chỉ một node duy nhất.” | **Sai** | Replica placement phụ thuộc keyspace RF/topology |
| “Contact point luôn là coordinator.” | **Sai** | Driver dùng metadata và load-balancing query plan |
| “Prepared statement luôn token-aware.” | **Sai** | Cần PK/keyspace/metadata hợp lệ, query có một partition |
| “SELECT không cần đủ PK vẫn biết token nếu có LIMIT.” | **Sai** | LIMIT không xác định partition |
| “IN với nhiều partition có một routing key duy nhất.” | **Không thể mặc định** | Nhiều partition có thể thuộc nhiều token |
| “Routing key đúng nghĩa client sẽ đọc từ đúng một replica.” | **Sai** | CL có thể cần nhiều replica |
| “LOCAL_QUORUM chỉ quyết định coordinator.” | **Sai** | CL quyết định điều kiện phản hồi replica |
| “Token càng lớn thì event càng mới.” | **Sai** | Token là kết quả hashing, không phải thời gian |
| “token() range scan rẻ vì token-aware.” | **Sai** | Có thể quét nhiều partition/replica |
| “Token awareness giải quyết hot partition.” | **Sai** | Một partition nóng vẫn tập trung vào tập replica |
| “getRoutingKey()!=null bảo đảm query đúng.” | **Sai** | Chưa chứng minh quyền, CL, data model và p99 |
| “Coordinator không là replica nghĩa query sai.” | **Sai** | Fallback/coordinator khác vẫn có thể thực thi đúng |
| “Replica mapping không đổi sau bootstrap.” | **Sai** | Topology/token map có thể thay đổi |
| “Tự dùng Java hashCode để tính token.” | **Sai** | Phải đúng encoding và partitioner Cassandra |
| “Routing hint cho phép bypass authorization.” | **Sai** | Quyền truy cập vẫn do server/ứng dụng kiểm soát |
| “Lấy trung bình p99 các node là p99 cluster.” | **Sai** | Phân vị cần tổng hợp phân bố/histogram đúng |

## 23. Bài tập và đáp án

### Câu 1 — Thành phần của routing key

Bảng có khóa `PRIMARY KEY ((tenant_id, device_id, event_day), event_time)`. Những cột nào tạo routing key?

**Đáp án:** `tenant_id`, `device_id`, `event_day` theo thứ tự partition key. `event_time` là clustering key và không tham gia routing key.

### Câu 2 — Hai row khác event_time

Hai row chỉ khác `event_time`. Chúng có cùng routing key/token không?

**Đáp án:** Có, nếu mọi thành phần partition key giống nhau. Chúng thuộc cùng logical partition; clustering key không đổi token.

### Câu 3 — Limit và token

Một query đủ partition key có `LIMIT ?`. Đổi limit từ 20 lên 100 có đổi routing key không?

**Đáp án:** Không. `LIMIT` không phải thành phần partition key; nó ảnh hưởng số row tối đa được trả.

### Câu 4 — Partition key thiếu ngày

Query có `tenant_id = ? AND device_id = ?` nhưng thiếu `event_day`. Java Driver có thể tính một routing key duy nhất của bảng ví dụ không?

**Đáp án:** Không. Chưa xác định đủ partition key. Truy vấn cũng có thể không hợp lệ theo hạn chế CQL của bảng này.

### Câu 5 — Cluster RF=3

Token thuộc replica N1/N2/N3. Client chọn N2 làm coordinator và CL=`LOCAL_QUORUM`. Chỉ N2 cần phản hồi là đủ?

**Đáp án:** Không. LOCAL_QUORUM trên RF=3 cần quorum hai replica trong DC cục bộ. Coordinator N2 có thể đồng thời là replica, nhưng đó không thay số ACK cần thiết.

### Câu 6 — Contact point

CqlSession dùng contact point N1. Mọi CQL request có coordinator N1 không?

**Đáp án:** Không. Contact point dùng khám phá/kết nối ban đầu; driver chọn coordinator theo load-balancing policy và metadata.

### Câu 7 — IN

CQL `WHERE device_id IN (?, ?, ?)` trên bảng có `device_id` là partition key đơn. Có thể mặc định một token cho cả query không?

**Đáp án:** Không. Ba device có thể hash tới ba token và replica sets khác nhau.

### Câu 8 — Routing bytes

Một đồng nghiệp nối `tenant + ":" + device + ":" + day` rồi gọi `String.hashCode()` để tạo token. Có đúng không?

**Đáp án:** Không. Routing key cần CQL binary encoding đúng kiểu/thứ tự; token cần partitioner của Cassandra. Java hashCode không tương đương Murmur3 token.

### Câu 9 — Coordinator không giữ partition

Driver chọn node N4 không nằm trong replica set. Truy vấn có phải luôn thất bại không?

**Đáp án:** Không. Coordinator có thể gửi request tới replica đích. Nhưng có thể thêm network hop và latency; cần xem liveness, DC, CL và load balancing.

### Câu 10 — Token range và thời gian

Muốn xem 20 sự kiện mới nhất, có nên `ORDER BY token(...) DESC` hoặc lấy token lớn nhất không?

**Đáp án:** Không. Token không biểu thị thời gian. Dùng clustering `event_time DESC` trong partition phù hợp và `LIMIT 20`.

### Câu 11 — Async

Ứng dụng gửi 20.000 `executeAsync` point reads cùng lúc; mỗi request có routing key đúng. Có thể bảo đảm cluster không bị quá tải không?

**Đáp án:** Không. Token awareness không thay backpressure, bounded in-flight, rate limit và capacity per replica.

### Câu 12 — Bootstrap

Node mới gia nhập cluster, token owner/replica set thay đổi. Có nên giữ cached mapping token→node từ lúc service startup không?

**Đáp án:** Không. Cần dùng metadata/load-balancing cập nhật của driver; cache thủ công có thể lỗi thời.

### Câu 13 — Multi-DC

Ứng dụng ở `dc1` dùng `LOCAL_QUORUM`. Vì vậy mọi replica ở `dc2` chắc chắn đã ACK trước khi request thành công?

**Đáp án:** Không. LOCAL_QUORUM yêu cầu quorum tại DC cục bộ; replication tới DC khác có thể chưa đạt điều kiện tương đương lúc ACK.

### Câu 14 — Security

Một request có `tenant_id` hợp lệ nhưng thuộc tenant khác. Việc bind đúng và tính routing key thành công có chứng minh được quyền đọc không?

**Đáp án:** Không. Cần authentication/authorization theo principal; token routing là cơ chế vị trí dữ liệu, không phải phân quyền.

### Câu 15 — Hotspot

Một partition được truy vấn nhiều hơn tất cả partition khác cộng lại. Bật token-aware routing có hết hotspot không?

**Đáp án:** Không. Nó giúp chọn coordinator phù hợp nhưng partition vẫn thuộc tập replica của mình. Cần cân nhắc bucketing/sharding, caching, rate limit và thiết kế truy vấn.

### Câu 16 — Nhận biết nguyên nhân chậm

`getRoutingKey()` khác null, coordinator nằm trong replica set, nhưng p99 read là 900 ms. Những nguyên nhân nào còn có thể xảy ra?

**Đáp án:** Wide/hot partition, SSTable/tombstone read amplification, disk/GC, network, compaction/repair/streaming, CL hoặc payload lớn. Định tuyến đúng không bảo đảm read nhanh.

## 24. Checklist code review và vận hành

### 24.1. Ứng dụng Java

~~~text
[ ] Dùng Java Driver 4.x API đúng phiên bản và local DC.
[ ] CqlSession được tái sử dụng; không tạo mới mỗi request.
[ ] CQL được prepare; bind marker có kiểu dữ liệu đúng.
[ ] Query xác định đầy đủ partition key khi muốn point routing.
[ ] Tên keyspace/schema và routing metadata được kiểm tra.
[ ] Không tự ghép bytes partition key hoặc hash token bằng Java hashCode.
[ ] Không dùng raw tenant_id từ request mà bỏ kiểm tra quyền.
[ ] Không ghi raw routing key bytes vào log/metric label.
[ ] LIMIT, page size và max in-flight đều có giới hạn hợp lý.
[ ] Với async, có backpressure và deadline, không tạo vô hạn future.
[ ] Đã test request đi qua coordinator/replica phù hợp ở lab.
[ ] Retry/speculative execution được quan sát và cấu hình theo SLO.
~~~

### 24.2. Cluster Cassandra

~~~text
[ ] RF, NetworkTopologyStrategy, DC/rack và snitch đúng thiết kế.
[ ] Driver biết node/host ID/token map hiện tại.
[ ] Không có topology change ngoài kế hoạch hoặc node UJ/DN chưa xử lý.
[ ] Query workload được đo theo node/DC, không chỉ cluster average.
[ ] Token distribution được kiểm tra cùng bytes/QPS theo partition.
[ ] tpstats/compactionstats/netstats và disk/GC/network ổn định.
[ ] Read/write p95/p99 và timeout nằm trong SLO đã phê duyệt.
[ ] Token-range jobs có ranges, checkpoint, throttle và stop condition.
[ ] Sau bootstrap/repair/replace có kiểm chứng replica health.
~~~

## 25. Tổng kết

Để Java Driver định tuyến CQL hiệu quả trong Cassandra:

1. **Partition key** là các cột quyết định một logical partition; **routing key** là bytes mã hóa giá trị của các cột ấy.
2. **Partitioner** biến routing key thành token; **replication strategy + topology** biến token thành tập replica.
3. **Token-aware load balancing** có thể ưu tiên một replica làm coordinator, giảm một số network hops, nhưng **không thay thế tính đúng của CL**.
4. **Prepared/bound statements với đầy đủ partition key** là cách tốt nhất để driver thường tự suy ra routing key. Nếu thiếu thành phần PK, dùng `IN` nhiều partition hoặc token-range scan, không mặc định có một routing key duy nhất.
5. **Routing key không gồm clustering key, LIMIT hay page size**. Đổi những thứ đó có thể thay tải query, nhưng không đổi token của partition nếu partition key giữ nguyên.
6. **CQL `token(...)` phù hợp cho token-range processing**, không phải sắp xếp theo thời gian hoặc phân trang UI.
7. **Contact point không cố định coordinator**, và một coordinator không phải replica vẫn có thể thực thi request đúng.
8. **Token map và replica placement thay đổi khi topology thay đổi**. Đừng cache mãi token→node ở application.
9. **Routing đúng không ngăn hot partition hoặc read/write amplification**. Cần giám sát node/replica, p99, compaction, streaming và rate limit.
10. **Security, consistency và routing là ba lớp khác nhau**: bind đúng không tự cấp quyền; routing hint không sửa WHERE; CL quyết định điều kiện replica phản hồi.

Câu hỏi thực dụng khi đánh giá một truy vấn Java–Cassandra là: **“Statement có định danh được đúng một partition, driver có đủ bytes và keyspace để tính token, replica hiện tại ở đâu, và coordinator được chọn có phục vụ tốt workload theo consistency yêu cầu không?”**. Trả lời được từng bước sẽ giúp định tuyến theo token hiệu quả mà vẫn giữ đúng mô hình dữ liệu, bảo mật và độ ổn định của cluster.
