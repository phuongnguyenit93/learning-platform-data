# SimpleStatement và thực thi truy vấn đồng bộ

## Mục tiêu bài học

Apache Cassandra sử dụng CQL (*Cassandra Query Language*) để đọc và ghi dữ liệu theo **partition key**, clustering key và mô hình wide-column. Trong ứng dụng Java, Cassandra Java Driver giúp chuyển câu CQL thành request gửi đến một **coordinator**, nhận phản hồi theo **consistency level** và ánh xạ dữ liệu trả về sang kiểu Java.

Bài học thuộc chương **Java driver cơ bản**, trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Trọng tâm là cách dùng **`SimpleStatement`** và **`CqlSession.execute(...)` đồng bộ**: tạo câu truy vấn, truyền tham số đúng kiểu, đọc `ResultSet`, xử lý lỗi, điều chỉnh consistency, paging và kiểm chứng dữ liệu. Những ví dụ này đồng thời củng cố kiến thức về partition key, thiết kế bảng theo truy vấn, replication, compaction, repair và chẩn đoán lỗi.

Sau khi học, bạn có thể:

1. Mô tả quan hệ giữa `CqlSession`, `SimpleStatement`, coordinator, replica và `ResultSet`.
2. Tạo `SimpleStatement` bằng `newInstance(...)` hoặc builder, truyền **positional values** thay vì ghép chuỗi chứa dữ liệu người dùng.
3. Thực thi đồng bộ với `session.execute(statement)`, đọc một hàng hoặc duyệt nhiều hàng mà không vô tình tải toàn bộ partition.
4. Đọc đúng kiểu CQL: `text` → `String`, `uuid` → `UUID`, `timestamp` → `Instant`, `date` → `LocalDate`, `bigint` → `long` và `decimal` → `BigDecimal`.
5. Đặt `LOCAL_QUORUM`, `pageSize`, `idempotence` và hiểu giới hạn của từng tùy chọn.
6. Phân biệt **không có hàng**, **lỗi đọc**, **lỗi ghi chưa rõ kết quả** và **ghi đã nhận ACK**.
7. Biết khi nào `SimpleStatement` phù hợp và khi nào nên dùng `PreparedStatement` hoặc thực thi bất đồng bộ.

> **Phạm vi phiên bản:** mã minh họa dùng giao diện **Cassandra Java Driver 4.x** với các package `com.datastax.oss.driver.api.core...` và Java 17. Bản phân phối/phiên bản driver cụ thể, tọa độ dependency, JDK, TLS và protocol phải được chọn theo compatibility matrix của cluster đang vận hành. Chỉ chạy ví dụ ghi dữ liệu trên **lab/staging** được cấp quyền.

## 1. SimpleStatement nằm ở đâu trong đường đi của một truy vấn?

Một ứng dụng Java không gửi trực tiếp `SELECT` tới từng replica. Nó gửi câu lệnh qua driver tới node được chọn làm **coordinator**. Coordinator xác định replica của partition từ token và replication strategy, liên lạc với các replica cần thiết rồi trả kết quả cho driver.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Session as CqlSession / Driver
    participant Coord as Cassandra Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    App->>Session: SimpleStatement + execute()
    Session->>Coord: Native CQL request
    Coord->>R1: Data request
    Coord->>R2: Digest / data request
    R1-->>Coord: Data response
    R2-->>Coord: Digest / data response
    Coord-->>Session: CQL rows / error
    Session-->>App: ResultSet hoặc exception
~~~

Sơ đồ trên là mô hình đơn giản cho một phép đọc; số replica và loại request thay đổi theo **RF, read CL, trạng thái node, speculative execution và phiên bản Cassandra**. `LOCAL_ONE` có thể hoàn thành từ một replica, còn `LOCAL_QUORUM` với RF=3 trong một DC cần hai phản hồi local. **Đừng hiểu một lần gọi Java là đúng một message mạng giữa các node.**

### Ba đối tượng chính

| Đối tượng | Vai trò | Lưu ý |
| --- | --- | --- |
| `CqlSession` | Quản lý kết nối, metadata cluster, node discovery, routing, execution | **Tái sử dụng lâu dài**, không tạo trên mỗi HTTP request |
| `SimpleStatement` | Mô tả một câu CQL, các giá trị và tùy chọn thực thi | Không yêu cầu bước `PREPARE` trước khi gửi |
| `ResultSet` / `Row` | Đọc kết quả truy vấn thành công và metadata thực thi | Kết quả có thể **phân trang**; đọc toàn bộ có thể phát sinh request tiếp |

Ngoài `SimpleStatement`, driver có `PreparedStatement`/`BoundStatement`. `SimpleStatement` phù hợp cho **truy vấn đơn giản, công cụ quản trị hoặc bài tập**; với query shape dùng lặp lại và tải lớn, prepared statement thường có lợi hơn về cache metadata, việc bind và xử lý câu lệnh tại server.

### Đồng bộ khác bất đồng bộ ở đâu?

~~~text
Đồng bộ:
  ResultSet rs = session.execute(statement);
  // Luồng gọi đợi tới khi request trả kết quả/trang đầu hoặc lỗi.

Bất đồng bộ:
  CompletionStage<AsyncResultSet> future = session.executeAsync(statement);
  // Có thể tiếp tục công việc khác mà không chặn luồng hiện tại.
~~~

`execute(...)` **chặn luồng Java đang gọi**. Tuy nhiên, nó không mặc định đọc hết **mọi trang** của kết quả trong một lần. Khi code duyệt `ResultSet`, driver có thể thực hiện **fetch trang tiếp** và tiếp tục chặn luồng ở những điểm đó.

Đồng bộ là lựa chọn đơn giản, dễ hiểu cho lab, tác vụ có giới hạn và ứng dụng ít concurrency. Trong event-loop/reactive framework, không gọi `execute` trực tiếp trên luồng event loop: việc chặn luồng có thể làm các request không liên quan bị trễ.

## 2. Chuẩn bị môi trường Java và cluster

### 2.1. Dependency và yêu cầu tương thích

Chọn một bản **Java Driver 4.x** được tài liệu nhà cung cấp hỗ trợ với phiên bản Cassandra và JVM đang chạy. Nhiều bản driver 4.x sử dụng API package:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
~~~

**Không nhầm package API với tọa độ Maven cố định**: các bản phát hành DataStax và Apache Cassandra Java Driver có thể có group/artifact/version khác nhau. Dùng dependency phù hợp với bản phát hành được phê duyệt; đừng tự lấy phiên bản mới nhất nếu cluster còn protocol/version cũ.

Cần xác minh tối thiểu:

- Java runtime hỗ trợ phiên bản driver đã chọn.
- Server đang bật **native transport** và cổng CQL thực tế (thường TCP `9042`).
- Contact points có thể truy cập; sau khi khám phá cluster, các endpoint được quảng bá cũng phải reachable.
- Tên **local datacenter** trùng metadata/snitch Cassandra.
- Production sử dụng TLS, xác thực, secret management và role **quyền tối thiểu**; không tắt xác minh chứng chỉ để khắc phục lỗi mạng.
- Có timeout, giới hạn request đồng thời và metrics phù hợp nhu cầu.

### 2.2. Kiểm tra cluster lab bằng cqlsh

Giả sử lab có **ba node** cùng DC tên `datacenter1`. Trên node có quyền quản trị:

~~~bash
nodetool status
~~~

Ba node dự kiến đều `UN` trước khi thử ở RF3. Trong `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` chỉ mô tả node trả lời câu truy vấn; nếu cần kiểm phiên bản của từng node, phải kiểm từng node hoặc dùng công cụ topology phù hợp.

**Nếu lab không có ba node**, hãy chỉnh RF và consistency level theo số replica thật. Không tạo RF3 trên một node rồi kỳ vọng `LOCAL_QUORUM` tự hoạt động với hai replica khác không tồn tại.

## 3. Tạo bảng lab theo truy vấn Java

Ứng dụng muốn đọc **các sự kiện của một tenant trong một ngày**, sắp theo thời gian giảm dần, và đọc một sự kiện cụ thể theo khóa đầy đủ.

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_driver_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS java_driver_lab.events_by_tenant_day (
    tenant_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    amount_minor bigint,
    note text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

### Giải thích primary key

- `(tenant_id, event_day)` là **composite partition key**. Cassandra hash cả cặp để tìm token; phải biết **cả hai** khi đọc một partition.
- `event_time` và `event_id` là **clustering keys**, cho thứ tự các hàng trong partition; `event_id` phân biệt các sự kiện có cùng timestamp.
- `event_type`, `amount_minor` và `note` là regular columns. API danh sách có thể chỉ cần hai cột đầu để giảm payload.
- `amount_minor bigint` biểu diễn số tiền bằng đơn vị nhỏ nhất để không đưa tiền qua `double`.
- Mô hình theo ngày giúp giới hạn kích thước partition **nếu số sự kiện/ngày hợp lý**. Một tenant rất nóng vẫn có thể cần chia bucket theo giờ hoặc shard theo truy vấn.

`IF NOT EXISTS` không đổi keyspace/bảng đã tồn tại. Để chắc chắn lab dùng RF3 như dự kiến:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'java_driver_lab';
~~~

### Nạp hai bản ghi mẫu

Trong `cqlsh` với RF3 khỏe, có thể đặt:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO java_driver_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id,
     event_type, amount_minor, note)
VALUES (
    'tenant-lab', '2026-11-21', '2026-11-21T09:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'CREATED', 25000, 'Đơn hàng mới'
);

INSERT INTO java_driver_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id,
     event_type, amount_minor, note)
VALUES (
    'tenant-lab', '2026-11-21', '2026-11-21T09:05:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAID', 25000, 'Đã thanh toán'
);
~~~

Chỉ coi lệnh ghi **được ACK** nếu `cqlsh` trả thành công ở CL đã chọn. Khi timeout, không được kết luận mutation chắc chắn chưa được ghi.

~~~sql
SELECT event_time, event_id, event_type, amount_minor
FROM java_driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-lab'
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Với dữ liệu mẫu, kết quả dự kiến gồm hai event, `PAID` trước `CREATED` theo `event_time DESC`. Nếu có ghi cạnh tranh trong lab, kết quả có thể khác; hãy dùng partition/run ID mới để giữ thí nghiệm độc lập.

## 4. Tạo và quản lý CqlSession đúng cách

`CqlSession` quản lý connection pools, metadata và định tuyến. Nó có chi phí khởi tạo; vì vậy **không khởi tạo một session mới cho mỗi câu SELECT hoặc mỗi request HTTP**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class LabSession {
    public static CqlSession open() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

Địa chỉ IP chỉ là **ví dụ**, phải thay bằng endpoint của cluster lab. Contact points hỗ trợ **khám phá** các node; không phải danh sách cứng những coordinator mà driver luôn dùng. Sau discovery, driver có thể chọn các node khác theo load balancing/routing.

Trong một chương trình command-line ngắn:

~~~java
try (CqlSession session = LabSession.open()) {
    // Thực thi CQL đồng bộ.
} // Session được đóng khi ra khỏi khối.
~~~

Trong Java service chạy lâu dài, tạo session theo **lifecycle ứng dụng**, chia sẻ giữa các component cần thiết rồi đóng có kiểm soát khi shutdown. Không gọi `close()` sau từng query nếu session còn đang được dùng.

**Bảo mật production:** thay vì hard-code secret, cấu hình authentication/TLS từ secret manager và truststore, kiểm tra SAN/hostname, giới hạn quyền CQL theo keyspace/table. Một TCP connection thành công không chứng minh TLS hoặc authorization đã đúng.

## 5. Khởi tạo SimpleStatement bằng hai cách

### 5.1. Cách ngắn: SimpleStatement.newInstance

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.LocalDate;

SimpleStatement list = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type, amount_minor " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setPageSize(20)
 .setIdempotence(true);
~~~

**Hai dấu `?` là bind markers cho giá trị**, không phải chuỗi thay thế bằng `String.replace`. Driver nhận `String` và `LocalDate`, mã hóa theo CQL type tương ứng và gửi qua native protocol.

### 5.2. Dùng builder khi có nhiều tùy chọn

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.LocalDate;

SimpleStatement list = SimpleStatement.builder(
        "SELECT event_time, event_id, event_type, amount_minor " +
        "FROM java_driver_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND event_day = ? LIMIT 20")
    .addPositionalValue("tenant-lab")
    .addPositionalValue(LocalDate.of(2026, 11, 21))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(20)
    .setIdempotence(true)
    .build();
~~~

Hai cách tạo ở trên mô tả **cùng query shape và giá trị**. Builder dễ đọc hơn khi cấu hình nhiều tùy chọn hoặc dựng statement từ các giá trị đã được validate. Tạo statement mới cho các bộ tham số khác nhau không yêu cầu tạo `CqlSession` mới.

### Những tùy chọn thường cần biết

| Tùy chọn | Ý nghĩa | Điều không nên suy ra |
| --- | --- | --- |
| `setConsistencyLevel(LOCAL_QUORUM)` | Yêu cầu quorum trong local DC | Mọi replica của mọi DC đều đã hội tụ |
| `setPageSize(20)` | Gợi ý số hàng mỗi trang trả về | Giới hạn **tổng** số hàng là 20 |
| `setIdempotence(true)` | Cho driver/policy biết statement có thể lặp lại an toàn theo định nghĩa ứng dụng | Driver chắc chắn sẽ retry hoặc ghi exactly-once |
| `setTimeout(...)` nếu API/version hỗ trợ | Deadline phía client cho request | Mọi mutation chắc chắn đã hủy khi deadline hết |
| `setExecutionProfileName(...)` | Chọn profile cấu hình cho loại request | Thay đổi schema, RF hoặc quyền CQL |

Hành vi cuối cùng còn phụ thuộc **driver configuration, retry policy, speculative execution, schema và trạng thái cluster**. Việc đánh dấu idempotent không tự tạo idempotency cho lệnh ghi nghiệp vụ.

## 6. Truyền tham số an toàn: bind markers, không nối chuỗi

### Phản ví dụ: nối dữ liệu người dùng vào CQL

~~~java
String tenantFromHttp = requestTenant;  // Ví dụ đầu vào từ API.
String cql = "SELECT * FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = '" + tenantFromHttp + "'";
// KHÔNG dùng: không có đủ partition key, ghép chuỗi không an toàn.
~~~

Code trên có hai vấn đề:

1. **Không có `event_day`**, nên query không khớp đầy đủ partition key; không thể thay thế thiết kế theo truy vấn bằng `ALLOW FILTERING`.
2. Dữ liệu người dùng được ghép vào text CQL, dễ hỏng cú pháp/escaping và mở rộng rủi ro injection.

Thay bằng positional values:

~~~java
SimpleStatement safe = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    tenantFromHttp,
    dayFromRequest
);
~~~

`dayFromRequest` phải là `LocalDate` đã parse và kiểm tra. Tham số chỉ dùng cho **giá trị dữ liệu**; không thể dùng dấu `?` để bind **tên bảng, tên cột, keyword hoặc cả mảnh CQL**.

Nếu ứng dụng thực sự cần chọn bảng động, hãy dùng **allowlist cố định** do server quản lý (ví dụ hai tên bảng được định nghĩa trước), thay vì nhận nguyên tên bảng hoặc mảnh `WHERE` từ người dùng.

### SimpleStatement khác prepared statement ra sao?

~~~text
SimpleStatement:
  Client gửi query string + values cho từng lần thực thi.
  Không cần chuẩn bị query ở server trước.

PreparedStatement:
  Client prepare query shape, server trả metadata/prepared ID.
  Mỗi lượt dùng BoundStatement bind values và thực thi.
  Thích hợp khi query shape được gọi lặp đi lặp lại.
~~~

**SimpleStatement vẫn hỗ trợ values qua bind markers**, không bắt buộc ghép literal vào CQL. Nhưng khi gọi rất nhiều lần trong workload thật, hãy cân nhắc `PreparedStatement` để tái sử dụng query shape, metadata và tránh chi phí parse/prepare lặp lại theo giao thức/server.

## 7. Thực thi SELECT đồng bộ và đọc ResultSet

### 7.1. Đọc một hàng bằng khóa đầy đủ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventLookup {
    public static void readOne(CqlSession session) {
        SimpleStatement query = SimpleStatement.newInstance(
            "SELECT event_type, amount_minor, note " +
            "FROM java_driver_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? " +
            "AND event_time = ? AND event_id = ?",
            "tenant-lab",
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T09:05:00Z"),
            UUID.fromString("22222222-2222-4222-8222-222222222222")
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotence(true);

        ResultSet result = session.execute(query);
        Row row = result.one();

        if (row == null) {
            System.out.println("Query thành công nhưng không có hàng");
            return;
        }

        String eventType = row.getString("event_type");
        Long amount = row.isNull("amount_minor")
            ? null : row.getLong("amount_minor");
        String note = row.getString("note");

        System.out.printf("type=%s amount_minor=%s note=%s%n",
            eventType, amount, note);
    }
}
~~~

**Vì sao `one() == null` không đồng nghĩa query thất bại?** Khi `execute` trả về `ResultSet` thành công nhưng không có hàng phù hợp với khóa, `one()` trả `null`. Ngược lại, khi không đủ replica, timeout, lỗi phân quyền hoặc query không hợp lệ, `execute` có thể **ném exception**; không được đổi những lỗi ấy thành “dữ liệu không tồn tại”.

### 7.2. Đọc nhiều hàng với giới hạn rõ ràng

~~~java
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.time.LocalDate;

SimpleStatement query = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type, amount_minor " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setPageSize(10)
 .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotence(true);

ResultSet rows = session.execute(query);
for (Row row : rows) {
    System.out.printf("%s %s %s%n",
        row.getInstant("event_time"),
        row.getUuid("event_id"),
        row.getString("event_type"));
}
~~~

CQL `LIMIT 20` là **giới hạn số hàng truy vấn trả về**, còn `setPageSize(10)` là **số hàng mục tiêu mỗi trang**. Nếu đủ 20 hàng và server trả trang 10 hàng, vòng `for` có thể yêu cầu thêm trang thứ hai trong quá trình duyệt.

**Hệ quả quan trọng:** `session.execute(...)` trả về `ResultSet` sau khi có **trang đầu**; duyệt đến cuối có thể thực hiện thêm round-trip và chặn luồng tiếp. Không dùng `for (Row row : result)` với query thiếu partition key hoặc không có giới hạn mà tưởng nó chỉ đọc 10 hàng.

### 7.3. Tách projection và kích thước kết quả

Nếu API danh sách chỉ cần thời gian, ID và trạng thái, hãy chỉ `SELECT` ba cột đó; đừng chọn `note` hoặc blob lớn rồi bỏ đi tại Java. `SELECT *` có thể làm response size và GC tăng, đặc biệt với row nhiều text/blob.

Tối ưu phải đo cùng lúc:

- Số câu CQL từ ứng dụng;
- Số hàng và số trang thực sự fetch;
- Số byte trong response;
- Latency p50/p95/p99, timeout, retry;
- CPU/GC phía Java và read latency/tombstone ở replica.

Giảm projection không tự khắc phục việc thiếu partition key, hot partition, compaction backlog hay replica chậm.

## 8. Kiểu dữ liệu và null khi lấy Row

Một `Row` là dữ liệu **theo schema CQL**, không phải một map JSON tùy ý. Dùng getter khớp kiểu để tránh làm tròn, lệch timezone hoặc lỗi codec.

| CQL | Java Driver 4.x thường dùng | Ví dụ lấy giá trị |
| --- | --- | --- |
| `text` / `varchar` / `ascii` | `String` | `row.getString("event_type")` |
| `uuid` | `UUID` | `row.getUuid("event_id")` |
| `timestamp` | `Instant` | `row.getInstant("event_time")` |
| `date` | `LocalDate` | `row.getLocalDate("event_day")` |
| `time` | `LocalTime` | `row.getLocalTime("clock_time")` |
| `int` | `int` | `row.getInt("version")` |
| `bigint` | `long` | `row.getLong("amount_minor")` |
| `decimal` | `BigDecimal` | `row.getBigDecimal("amount")` |
| `varint` | `BigInteger` | `row.getBigInteger("sequence_no")` |
| `boolean` | `boolean` | `row.getBoolean("enabled")` |

Các cột `clock_time`, `version`, `amount`, `sequence_no` và `enabled` trong bảng trên **chỉ minh họa getter**; chúng không có trong schema lab hiện tại.

### Null và field không được chọn

- `row == null`: query thành công nhưng **không có hàng**.
- `row.isNull("amount_minor")`: có hàng, nhưng **cell được chọn không có giá trị**.
- `row.getString("note")` có thể trả `null` nếu cột text null.
- Truy cập tên cột **không nằm trong projection** sẽ là lỗi thao tác ánh xạ, không phải “cột trong Cassandra bị mất”.
- Với getter primitive như `getLong`, kiểm `isNull` trước nếu schema cho phép null và nghiệp vụ cần phân biệt null với 0.

CQL `timestamp` lưu một **instant** ở độ phân giải millisecond, không lưu tên timezone IANA gốc. Không so giá trị timestamp bằng chuỗi hiển thị phụ thuộc timezone của client; so `Instant` hoặc epoch milliseconds khi đối soát.

Với tiền, không chuyển `decimal` sang `double` để tính toán chính xác. Dùng `BigDecimal` và thống nhất quy tắc scale/rounding. Với UUID, giữ kiểu `UUID` ổn định để retry không tạo primary key mới.

## 9. INSERT đồng bộ: đã ACK khác đã lưu trên mọi replica

`SimpleStatement` cũng dùng được cho `INSERT` và `UPDATE`. Ví dụ thêm một event mới với khóa định danh đã biết:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

SimpleStatement insert = SimpleStatement.newInstance(
    "INSERT INTO java_driver_lab.events_by_tenant_day " +
    "(tenant_id, event_day, event_time, event_id, " +
    "event_type, amount_minor, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
    "tenant-lab",
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:10:00Z"),
    UUID.fromString("33333333-3333-4333-8333-333333333333"),
    "SHIPPED",
    25000L,
    "Đã giao hàng"
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotence(false);

session.execute(insert);
// Nếu không ném lỗi: server xác nhận write theo CL yêu cầu.
~~~

**`INSERT` không phải thao tác “thêm nếu chưa tồn tại” mặc định**. Trong Cassandra, ghi cùng primary key có thể cập nhật/ghi đè các cột theo timestamp. Nếu cần điều kiện chỉ ghi khi chưa có, hãy nghiên cứu **LWT: `INSERT ... IF NOT EXISTS`** với điều kiện consistency/latency tương ứng.

### RF/CL và kết quả write

Giả sử `NetworkTopologyStrategy` có **RF=3 trong datacenter1**:

| Write CL | Số ACK tối thiểu trong local DC | Điều được bảo đảm khi thành công |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 | Ít nhất một replica local đáp ứng theo CL |
| `LOCAL_QUORUM` | 2 | Đủ quorum local ACK; không cần cả ba ACK |
| `ALL` | 3 | Cả ba replica thuộc phạm vi RF phải ACK |

Số ACK cần đợi **không phải** số replica mà coordinator cố gửi mutation tới. Việc replica còn lại bắt kịp liên quan hints/repair/replication và tình trạng mạng. Nếu một node tạm down, một write `LOCAL_QUORUM` có thể vẫn thành công khi hai replica local còn lại ACK.

### Ghi timeout và vấn đề retry

Nếu `session.execute(insert)` báo timeout, trạng thái thực tế có thể là:

~~~text
UNKNOWN_WRITE:
    client không nhận ACK theo CL trước deadline
    -> một số replica có thể đã ghi mutation
    -> không được kết luận chắc chắn "chưa ghi"
~~~

Với thao tác **upsert cùng primary key/cùng giá trị** trong môi trường không có concurrent writers, retry có thể an toàn nếu đã định nghĩa timestamp/TTL và idempotency phù hợp. Nhưng khi có ghi cạnh tranh, counter, LWT, tạo ID mới trong mỗi lần thử hoặc side effect ngoài Cassandra, retry bừa có thể làm sai dữ liệu. **Không bật `setIdempotence(true)` cho mọi write chỉ để driver thử lại nhanh hơn.**

## 10. Phân biệt lỗi đồng bộ và kết quả dữ liệu

Một ứng dụng không nên chỉ có hai trạng thái “thành công” và “không có dữ liệu”. Tối thiểu cần phân biệt:

| Kết quả ứng dụng | Điều kiện | Quyết định |
| --- | --- | --- |
| `READ_MATCH` | SELECT hoàn tất và row đúng kỳ vọng | PASS cho khóa/CL đang kiểm |
| `READ_MISSING` | SELECT hoàn tất nhưng `one() == null` | Xác minh khóa, TTL, DELETE và manifest |
| `READ_MISMATCH` | SELECT hoàn tất, giá trị khác kỳ vọng | Điều tra timestamp, writer và replica |
| `READ_ERROR` | SELECT ném timeout/unavailable/driver exception | Chưa thể kết luận hàng có hay không |
| `WRITE_ACKNOWLEDGED` | INSERT/UPDATE hoàn tất theo CL | Ghi ACK với CL/thời điểm |
| `UNKNOWN_WRITE` | Write không nhận được kết quả thành công sau gửi | Đối soát trước retry có giới hạn |
| `VALIDATION_ERROR` | Đầu vào sai kiểu/PK/null/format trước khi gửi | Sửa nguồn, không retry như lỗi mạng |

### Các loại sự cố thường gặp

| Triệu chứng | Khả năng đầu tiên | Bằng chứng nên kiểm |
| --- | --- | --- |
| Không mở được `CqlSession` | Contact point, firewall, TLS/auth, local DC | Endpoint, cert, driver logs, node listeners |
| `InvalidQuery` | Sai CQL, thiếu partition key, schema không khớp | Query text không có secret, `system_schema` |
| `Unauthorized` | Role không có quyền hoặc auth sai | Role grants, identity, audit |
| `Unavailable` | Không đủ replica sống theo CL | RF, DC, `nodetool status` |
| `ReadTimeout` | Replica trả lời chậm/không đủ trong deadline | Trace, I/O/compaction, CL, network |
| `WriteTimeout` | Không đủ ACK ghi trong deadline | Lưu UNKNOWN, xem tình trạng replica |
| `ReadFailure/WriteFailure` | Replica báo lỗi thực thi | Logs đúng node, storage/network |
| Dữ liệu đọc khác | CL thấp, replica lag, concurrent writes, TTL | Manifest, timestamp, tracing và repair |
| Lỗi codec | Java type/codec không khớp kiểu CQL | Schema và kiểu được bind/get |

Tên class exception cụ thể có thể khác theo phiên bản/driver, vì vậy hãy phân loại dựa trên **exception type thực tế, error code và ngữ cảnh**, không chỉ đối chiếu chuỗi message. Không log password, toàn bộ CQL values hoặc PII nhạy cảm khi xử lý exception.

### Ví dụ đo kết quả đọc có phân loại lỗi

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class SyncReadProbe {
    public enum State { MATCH, MISSING, MISMATCH, READ_ERROR }
    public record Outcome(
        State state, long latencyMicros,
        String coordinator, String errorType) {}

    public static Outcome check(
            CqlSession session, String tenant, LocalDate day,
            Instant time, UUID eventId, String expectedType) {
        SimpleStatement query = SimpleStatement.newInstance(
            "SELECT event_type FROM java_driver_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? " +
            "AND event_time = ? AND event_id = ?",
            tenant, day, time, eventId
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotence(true);

        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(query);
            ExecutionInfo info = result.getExecutionInfo();
            String coordinator = info.getCoordinator() == null
                ? "unknown" : info.getCoordinator().getEndPoint().toString();
            Row row = result.one();
            long us = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
            if (row == null) {
                return new Outcome(State.MISSING, us, coordinator, null);
            }
            State state = expectedType.equals(row.getString("event_type"))
                ? State.MATCH : State.MISMATCH;
            return new Outcome(state, us, coordinator, null);
        } catch (RuntimeException error) {
            long us = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
            return new Outcome(
                State.READ_ERROR, us, "unknown",
                error.getClass().getSimpleName());
        }
    }
}
~~~

Trong ví dụ, `expectedType` phải đến từ **manifest hoặc đầu vào đáng tin cậy bên ngoài kết quả SELECT**. `MATCH` chỉ xác nhận giá trị của một khóa tại CL/thời điểm hiện tại, không chứng minh mọi replica đã hội tụ.

Hàm dùng `System.nanoTime()` để đo duration (không phụ thuộc đồng hồ hệ thống bị chỉnh giờ). Để tạo p95/p99 cần thu **nhiều mẫu cùng workload**, phân nhóm theo query và lưu **error rate riêng**; không chỉ tính latency trên các request thành công rồi bỏ lỗi timeout.

## 11. Paging khi thực thi đồng bộ

### 11.1. LIMIT khác page size

~~~java
SimpleStatement query = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 50",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setPageSize(10);
~~~

Giới hạn tổng của truy vấn là **50 hàng**, còn mục tiêu kích thước **mỗi trang** là 10 hàng. Nếu có đủ dữ liệu, việc đọc hết có thể yêu cầu nhiều lần fetch. Server cũng có thể trả trang ngắn hơn page size do tình trạng truy vấn/giới hạn server, vì vậy **không suy ra “trang nhỏ hơn 10 nghĩa là hết dữ liệu”**.

### 11.2. Tránh tải tất cả khi chỉ cần trang đầu

~~~java
// Phản mẫu với tập kết quả lớn:
// List<Row> everything = session.execute(query).all();
// all() có thể fetch hết các trang còn lại.

ResultSet result = session.execute(query);
int available = result.getAvailableWithoutFetching();
java.util.Iterator<Row> current = result.iterator();
for (int i = 0; i < available; i++) {
    Row row = current.next();
    // Chỉ xử lý các hàng đã có trong trang hiện tại.
}
~~~

`getAvailableWithoutFetching()` cho biết số hàng hiện có mà driver không phải fetch tiếp tại thời điểm đó. Trong ví dụ, số này được lấy **trước khi duyệt**; vòng lặp chỉ gọi `next()` đúng số lần có hàng sẵn, không gọi `hasNext()` để vô tình kích hoạt fetch khi hết trang. Để xây API phân trang có cursor production, hãy quản lý **paging state opaque** và contract đi kèm một cách rõ ràng; đừng tự tạo `OFFSET` hoặc xem paging state là số trang.

**Cẩn trọng về vòng lặp:** một cấu trúc `for-each` thông thường có thể tự fetch khi đi hết trang. Đối với API trả trang đầu rồi chờ người dùng “xem tiếp”, sử dụng API paging/result state được driver cung cấp theo phiên bản thay vì duyệt toàn bộ `ResultSet` rồi cắt `subList` tại Java.

### 11.3. Paging state không phải snapshot giao dịch

Paging state phải được coi là **token opaque** liên quan đến truy vấn, tham số và protocol. Không đưa token của một tenant cho tenant khác, không chỉnh sửa byte tùy ý, không kỳ vọng token tồn tại vô thời hạn hoặc tương thích giữa mọi phiên bản Cassandra/driver.

Khi dữ liệu thay đổi giữa hai trang, kết quả có thể khác một snapshot bất biến. Nếu nghiệp vụ yêu cầu đối soát toàn bộ event không mất/trùng, hãy chốt nguồn dữ liệu/định danh, kiểm soát cửa sổ thay đổi và so manifest sau khi đọc.

## 12. Chỉ định consistency level theo yêu cầu nghiệp vụ

### 12.1. Đọc sau ghi ở cùng DC

Với RF3 tại `datacenter1`:

~~~text
Ứng dụng:
    INSERT @ LOCAL_QUORUM -> đợi 2/3 ACK local
    SELECT @ LOCAL_QUORUM -> đợi 2/3 replica local đáp ứng
~~~

Nếu không có ghi cạnh tranh hoặc lỗi hiếm, cặp quorum đọc/ghi giúp giảm nguy cơ đọc lại dữ liệu cũ so với `ONE`. Tuy nhiên, điều này **không biến Cassandra thành hệ thống giao dịch serializable**, không tự giải quyết lost update và không thay LWT/ứng dụng kiểm phiên bản khi ghi cạnh tranh.

`LOCAL_QUORUM` ở DC A **không dùng ACK từ DC B để bù** quorum local. Nó cũng không bảo đảm một write vừa ACK local đã hiện diện trên tất cả replica ở DC remote. Nếu Java Driver khai báo local DC sai, nó có thể chọn coordinator từ DC không mong muốn và tạo độ trễ WAN hoặc điều kiện nhất quán khác.

### 12.2. Đừng giảm CL chỉ để tránh timeout

| Lựa chọn | Lợi ích có thể có | Đánh đổi |
| --- | --- | --- |
| `LOCAL_ONE` | Có thể đọc nhanh và sẵn sàng hơn khi một số replica chậm | Có nguy cơ đọc dữ liệu cũ |
| `LOCAL_QUORUM` | Tăng điều kiện đáp ứng trong local DC | Chịu latency của quorum; có thể timeout khi không đủ replica |
| `ALL` | Yêu cầu tất cả replica phản hồi | Nhạy với một replica chậm/down, không phù hợp mặc định cho mọi API |

Chọn CL dựa trên RF, DC, đặc tính dữ liệu và SLA. **Không chỉ nhìn thời gian chạy một truy vấn trong lab rồi tự hạ consistency level production**.

## 13. Những lỗi sử dụng SimpleStatement dễ mắc

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo `CqlSession` mới trên từng request | Tăng handshake, pool churn, CPU/GC | Tái sử dụng session |
| Nối giá trị người dùng vào CQL | Sai escaping, rủi ro injection | Positional values với `?` |
| Dùng `SELECT *` không có WHERE theo PK | Truy vấn bị từ chối hoặc quét rộng nếu cố filtering | Thiết kế bảng theo truy vấn, đầy đủ partition key |
| Dùng `ALLOW FILTERING` để “sửa” thiếu khóa | Đọc quá nhiều partition/SSTable, timeout | Chọn primary key/bảng/index phù hợp |
| Dùng `LIMIT 20` với cột blob rất lớn | 20 hàng vẫn có thể tạo response lớn | Giảm projection, tách list/detail |
| Dùng `setPageSize(10)` như tổng row limit | Vòng lặp có thể fetch nhiều trang | Kết hợp LIMIT và giới hạn ứng dụng |
| Gọi `all()` trên kết quả lớn | Fetch nhiều trang, tăng RAM/GC | Duyệt có giới hạn/cursor |
| Xem `row == null` và exception là cùng lỗi | Báo mất dữ liệu sai | MISSING tách READ_ERROR |
| Retry `INSERT` sau timeout không kiểm tra | Ghi trùng/ghi đè hoặc side effect lặp | UNKNOWN_WRITE, idempotency và đối soát |
| Dùng `double` cho số tiền | Mất độ chính xác nhị phân | `bigint` đơn vị nhỏ nhất hoặc `decimal` |
| Dùng `timestamp` như timezone gốc | Hiển thị hoặc kiểm tra lệch ý nghĩa | `Instant` + zone ID nghiệp vụ riêng |
| Chạy đồng bộ trên event loop | Chặn luồng, làm chậm nhiều request | Sử dụng `executeAsync` hoặc luồng phù hợp |
| Bật idempotent cho mọi thao tác | Retry/speculative có thể thay đổi nghiệp vụ | Đánh giá từng statement |
| Tin `nodetool status UN` là dữ liệu đúng | Replica có thể chưa hội tụ | Đối soát CQL theo CL/manifest, repair khi cần |

## 14. Quy trình thực hành hoàn chỉnh

### Bước 1 — Khởi tạo

Xác nhận Cassandra lab, tên DC và kết nối CQL; tạo `java_driver_lab.events_by_tenant_day`. Nạp hai marker bằng cqlsh và ghi lại **event IDs, thời gian, trạng thái kỳ vọng**. Nếu muốn thử ghi từ Java, dùng event ID mới cố định; không sinh UUID mới khi retry cùng sự kiện.

### Bước 2 — Tạo session

Mở một `CqlSession` với **local DC** chính xác. Nếu phải dùng TLS/auth, áp dụng cấu hình từ môi trường được cấp quyền. Đo thời gian khởi tạo **riêng** với thời gian query để không làm sai benchmark.

### Bước 3 — Đọc một hàng

Tạo `SimpleStatement.newInstance(...)` với **bốn thành phần khóa**: tenant, ngày, timestamp và UUID. Gọi `execute(...)` rồi `one()`, phân loại FOUND/MISSING/READ_ERROR và đọc typed columns.

### Bước 4 — Đọc danh sách

Tạo `SimpleStatement.builder(...)` cho một partition theo tenant/ngày, projection nhỏ, `LIMIT 20` và `pageSize 10`. Duyệt `ResultSet` và quan sát số row, thứ tự clustering và số page fetch (qua metrics/instrumentation).

### Bước 5 — Thực thi một INSERT

Ghi một event mới bằng positional parameters. Chỉ công bố `ACKNOWLEDGED` nếu `execute` hoàn tất thành công tại CL đã chọn; nếu timeout ghi `UNKNOWN_WRITE`. Sau đó đọc lại **đúng primary key**.

### Bước 6 — Diễn tập lỗi một cách an toàn

Trên **lab** RF3, nếu có runbook cho phép, thử tạm ngừng một replica rồi so đọc `LOCAL_QUORUM` và `ALL`. Đừng gây partition mạng/ngừng node trên production. Quan sát `nodetool status`, errors, latency và sự khác nhau giữa **Unavailable**, **ReadTimeout** và giá trị `MISSING`.

### Bước 7 — Báo cáo

~~~text
Lab name: java-driver-basics-008
Driver version: <phiên bản thực tế>
Cassandra version / DC / RF: <thực tế>
Query shape: point-read / list-read / insert
CL: LOCAL_QUORUM hoặc giá trị đã chọn
Partition key: tenant_id + event_day
Rows returned: <số đã đo>
Page size / pages fetched: <số đã đo>
Latency client p50/p95/p99: <số đã đo>
READ_MATCH: <số đã kiểm>
READ_MISSING: <số đã kiểm>
READ_ERROR: <số đã kiểm>
WRITE_ACKNOWLEDGED: <số đã kiểm>
UNKNOWN_WRITE: <số đã kiểm>
Coordinator / DC: <từ ExecutionInfo và metadata>
Conclusion: PASS / GAP / NEEDS_INVESTIGATION
~~~

Các số ở trên là **placeholder**; không bịa latency. Muốn đo p99 phải có đủ request cùng loại, tải đại diện và phân tách thời gian khởi tạo session khỏi request latency. Không dùng một lần `cqlsh` trả nhanh để kết luận Java service đã đạt SLO.

## 15. Câu hỏi và bài tập tự kiểm tra

**Bài 1 — Session lifecycle.** Vì sao một service không nên tạo/đóng `CqlSession` trên mỗi HTTP request? Contact points có phải danh sách coordinator cố định sau discovery không?

**Bài 2 — Tạo statement.** Viết hai phiên bản tương đương của SELECT một partition bằng `SimpleStatement.newInstance` và `SimpleStatement.builder`. Chỉ ra positional values và consistency level.

**Bài 3 — Partition key.** Với bảng `events_by_tenant_day`, tại sao WHERE chỉ có `tenant_id` không đủ? Một câu `SELECT * ... ALLOW FILTERING` có tự trở thành truy vấn hiệu quả không?

**Bài 4 — Null và lỗi.** So sánh `row == null`, `row.isNull("amount_minor")` và exception từ `session.execute`. Trường hợp nào là MISSING, trường hợp nào là READ_ERROR?

**Bài 5 — Paging.** `LIMIT 50` và `pageSize 10` khác nhau thế nào? Vì sao vòng `for (Row row : result)` có thể tiếp tục chặn luồng sau khi `execute` đã trả `ResultSet`?

**Bài 6 — Projection.** API danh sách chỉ cần `event_id` và `event_type`. Vì sao trả cả `note` và blob dữ liệu có thể làm p95 tăng dù partition key đúng?

**Bài 7 — Consistency.** RF=3 tại `datacenter1`, một replica down. SELECT `LOCAL_QUORUM` có thể thành công không? SELECT `ALL` thì sao? Việc đọc ở DC khác có được tính vào LOCAL_QUORUM của DC này không?

**Bài 8 — Retry.** Một `INSERT` timeout nhưng replica đã áp dụng một phần. Tại sao không được tự tạo event ID mới rồi retry? Đề xuất cách phân biệt UNKNOWN_WRITE với chưa từng gửi.

**Bài 9 — Kiểu dữ liệu.** Đọc `amount_minor bigint` bằng `double` có rủi ro gì? Vì sao timestamp CQL được đọc bằng `Instant` không lưu tên timezone của nguồn?

**Bài 10 — Đồng bộ và concurrency.** Một endpoint web phục vụ nhiều request trên event loop. Điều gì xảy ra nếu gọi `session.execute` đồng bộ trên chính event loop? Khi nào nên chuyển sang `executeAsync`?

**Bài 11 — Đo đạc.** Viết probe ghi `latencyMicros`, `coordinator` và trạng thái MATCH/MISMATCH/MISSING/READ_ERROR cho cùng primary key trước/sau một lần ngừng node lab. Vì sao không cộng READ_ERROR vào MISSING?

**Bài 12 — Simple vs prepared.** Một query shape được gọi 10.000 lần/giây với giá trị khác nhau. Vì sao `PreparedStatement`/`BoundStatement` thường hợp lý hơn `SimpleStatement`, và vì sao vẫn phải giữ partition key, CL, LIMIT và page size đúng?

## Ghi nhớ

**`SimpleStatement` mô tả một câu CQL có tham số và cấu hình thực thi; `CqlSession.execute(...)` thực thi đồng bộ, trả `ResultSet` hoặc ném lỗi.** Hãy **tái sử dụng CqlSession**, bind giá trị bằng `?` thay vì nối chuỗi, truy vấn có đủ partition key, chọn projection/LIMIT/page size rõ ràng, đọc `Row` đúng kiểu và đặt consistency level phù hợp RF/local DC. **`one() == null` không giống read timeout; write timeout không chứng minh mutation chưa được áp dụng.** Khi workload nhiều và lặp lại query shape, cân nhắc `PreparedStatement` và thực thi bất đồng bộ, nhưng luôn giữ **idempotency, retry budget, đo latency và kiểm chứng dữ liệu** theo hợp đồng ứng dụng.
