# ResultSet, Row và lấy giá trị theo tên/chỉ số cột trong Java Driver Cassandra

## 1. Mục tiêu và bối cảnh

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Ứng dụng thiết kế bảng theo truy vấn, dùng **partition key** để tìm replica thích hợp, thực hiện CQL thông qua coordinator và chọn **consistency level** theo yêu cầu tính đúng/khả dụng.

Từ phía Java, khi chạy `SELECT` bằng **Apache Cassandra Java Driver 4.x**, một luồng cơ bản là:

~~~text
CqlSession
    |
    | execute(Statement)
    v
ResultSet
    |
    | one() / iterator()
    v
Row
    |
    | getUuid("device_id")
    | getInstant("event_time")
    | getDouble("reading_value")
    v
Java values / DTO
~~~

Bài thuộc chương **Java driver cơ bản** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trọng tâm là hiểu **ResultSet chứa gì, cách lấy Row an toàn, và sự khác nhau khi truy cập giá trị theo tên hay theo vị trí cột**.

Sau bài, bạn có thể:

1. Giải thích `CqlSession.execute()` trả về gì và phân biệt `ResultSet` với `Row`.
2. Sử dụng `one()`, vòng lặp và `all()` đúng theo số kết quả mong đợi.
3. Đọc giá trị bằng getter **đúng kiểu Java/CQL**, theo **tên cột** hoặc **chỉ số 0-based**.
4. Kiểm tra `null`, cột không được `SELECT` và alias để tránh lỗi chuyển đổi âm thầm.
5. Hiểu phân trang tự động của `ResultSet` và nguy cơ giữ quá nhiều Row trong RAM.
6. Dùng `ColumnDefinitions`, kiểm thử và log an toàn khi schema hoặc query thay đổi.
7. Phân biệt trường hợp SELECT thường với phản hồi của **LWT** (`IF NOT EXISTS`, `IF ...`).

**Phạm vi phiên bản:** các ví dụ Java dùng API của DataStax/Apache Cassandra Java Driver **4.x**, với package `com.datastax.oss.driver.api.*`. Driver **3.x** dùng `com.datastax.driver.core.*` và một số phương thức/kiểu Java khác; không sao chép mã 4.x vào project 3.x mà không chuyển đổi.

## 2. Chuẩn bị bảng và dữ liệu CQL để thực hành

### 2.1. Bảng có partition key và clustering key rõ ràng

Giả sử cluster lab có datacenter tên `dc1` và đủ node cho RF=3:

~~~cql
-- Chạy trên CLUSTER LAB được cấp quyền, không tạo lại
-- keyspace production đã có dữ liệu.
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    tags list<text>,
    calibration_factor decimal,
    valid boolean,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

- **Partition key** là `(device_id, event_day)`. Truy vấn biết cả hai giá trị có thể nhắm tới một partition.
- **Clustering key** `event_time` sắp các bản ghi trong partition từ mới về cũ.
- `reading_value` là `double`, `status` là `text`, `calibration_factor` là `decimal`, `tags` là collection.
- Các cột không thuộc primary key có thể không có giá trị trong một row; ứng dụng phải xử lý khả năng `null`.

Ví dụ chèn hai row:

~~~cql
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time,
    reading_value, status, tags, calibration_factor, valid
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6, 'OK', ['indoor', 'sample'], 1.02, true
);

-- Không cung cấp status, tags hoặc calibration_factor.
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time, reading_value, valid
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1, true
);
~~~

Dữ liệu này giúp phân biệt **row tồn tại nhưng một số cột bằng null** với **truy vấn không tìm thấy row**.

### 2.2. Truy vấn cơ sở và thứ tự cột

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 10;
~~~

Bốn cột được chọn và thứ tự của chúng là:

| Chỉ số `Row` (0-based) | Tên cột | CQL type | Java getter |
|---:|---|---|---|
| 0 | `event_time` | `timestamp` | `getInstant(0)` |
| 1 | `reading_value` | `double` | `getDouble(1)` |
| 2 | `status` | `text` | `getString(2)` |
| 3 | `valid` | `boolean` | `getBoolean(3)` |

**Chỉ số dựa trên danh sách cột trong kết quả SELECT**, không dựa vào vị trí cột khai báo trong `CREATE TABLE` hoặc thứ tự lưu trên SSTable.

## 3. Vai trò của CqlSession, ResultSet và Row

### 3.1. Một sơ đồ xử lý

~~~mermaid
sequenceDiagram
    participant A as Ứng dụng Java
    participant D as CqlSession / Driver
    participant C as Coordinator
    participant R as Replica
    A->>D: execute(boundStatement)
    D->>C: CQL request
    C->>R: Đọc partition theo CL
    R-->>C: Dữ liệu phù hợp
    C-->>D: Trang kết quả đầu
    D-->>A: ResultSet
    A->>A: one() hoặc duyệt Row
    Note over A,D: Có thể tự fetch trang kế tiếp khi cần
    A->>A: Row.getString / getInstant / getDouble
~~~

`CqlSession` quản lý kết nối, metadata, request và vòng đời driver. Nó nên được **tái sử dụng** xuyên nhiều request của service thay vì tạo mới cho mỗi truy vấn HTTP.

`ResultSet` là **giao diện tiêu thụ kết quả đồng bộ** của một lần thực thi statement. Nó cung cấp các row theo thứ tự kết quả, kết hợp cơ chế paging và thông tin thực thi. ResultSet **không đồng nghĩa một bảng dữ liệu đầy đủ đã nằm trong heap**.

`Row` là **một hàng trong phần kết quả**; nó chứa các giá trị ứng với những cột/projection được SELECT hoặc được statement trả về. Row không tự có thêm những cột bạn không yêu cầu.

### 3.2. Bảng phương thức trọng tâm

| API Driver 4.x | Công dụng | Lưu ý |
|---|---|---|
| `session.execute(statement)` | Thực thi đồng bộ, trả `ResultSet` | Có thể chờ network; không tạo session mỗi request |
| `resultSet.one()` | Lấy **row tiếp theo**, hoặc `null` nếu hết kết quả | Có thể tiêu thụ row và làm iterator bắt đầu từ vị trí sau đó |
| `for (Row row : resultSet)` | Duyệt từng row còn lại | Có thể kích hoạt fetch trang kế tiếp |
| `resultSet.all()` | Lấy **toàn bộ row còn lại** vào List | Nguy cơ chiếm bộ nhớ lớn |
| `resultSet.getColumnDefinitions()` | Metadata các cột của kết quả | Dùng khi cần kiểm tra tên/thứ tự/type |
| `row.getString("status")` | Đọc giá trị cột theo tên | Cột phải được trả về và type phù hợp |
| `row.getString(2)` | Đọc giá trị cột theo index | Index bắt đầu từ 0, dễ sai khi SELECT đổi thứ tự |
| `row.isNull("status")` | Kiểm tra cell có null không | Tránh nhầm null với giá trị mặc định |
| `resultSet.getAvailableWithoutFetching()` | Số row đang có thể lấy mà không fetch thêm | **Không phải tổng row** của query |
| `resultSet.isFullyFetched()` | Đã lấy hết các page chưa | Có thể vẫn còn row đã fetch mà chưa tiêu thụ |
| `resultSet.wasApplied()` | Trạng thái áp dụng của conditional query/LWT | Không thay cho `one()` khi đọc SELECT thường |

Trong bài này ta dùng `ResultSet` **đồng bộ**. Java Driver 4.x còn có `AsyncResultSet` cho async, nhưng nó có cách xử lý page khác; không dùng `ResultSet` và `AsyncResultSet` như hai kiểu có chung mọi phương thức.

## 4. Ví dụ Java đầy đủ: truy vấn và lấy Row đầu tiên

### 4.1. Một repository đơn giản

Đoạn sau giả định `CqlSession` đã được cấu hình đúng contact points, local DC, authentication và TLS theo môi trường; nó được truyền vào repository ở thời điểm khởi tạo.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public final class ReadingRepository {
    private final CqlSession session;
    private final PreparedStatement latestQuery;

    public ReadingRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.latestQuery = session.prepare(
            "SELECT event_time, reading_value, status, valid " +
            "FROM telemetry.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 1"
        );
    }

    public void printLatest(UUID deviceId, LocalDate day) {
        BoundStatement statement = latestQuery.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        ResultSet result = session.execute(statement);
        Row row = result.one();

        if (row == null) {
            System.out.println("Không có dữ liệu trong partition/ngày");
            return;
        }

        Instant time = row.getInstant("event_time");
        double value = row.getDouble("reading_value");
        String status = row.getString("status");
        boolean valid = row.getBoolean("valid");

        System.out.println(
            "At " + time + ": " + value +
            ", status=" + status + ", valid=" + valid);
    }
}
~~~

Ở đây `SELECT ... LIMIT 1` giới hạn tổng số row trả về. Để đọc đúng `getInstant("event_time")`, `SELECT` phải trả về cột đó. Giá trị `status` có thể `null`; ví dụ in ra chuỗi `null` chỉ để trình bày, production nên có chính sách null/mapping riêng.

### 4.2. Điều gì xảy ra nếu không có Row?

~~~java
ResultSet rs = session.execute(statement);
Row first = rs.one();

if (first == null) {
    // Không có row phù hợp với truy vấn.
    return;
}

// Không gọi first.getString(...) nếu first == null.
String status = first.getString("status");
~~~

**`Row == null`** khác hoàn toàn **`Row != null` nhưng `row.getString("status") == null`**:

- Row không tồn tại: WHERE không khớp bản ghi sống nào, hoặc LIMIT/trạng thái khác khiến tập kết quả rỗng.
- Row tồn tại nhưng cột null: row được SELECT nhưng cell đó không có giá trị sống ở thời điểm đọc.

Điều này rất quan trọng khi ứng dụng Java quyết định trả HTTP `404` hay trả bản ghi có một trường chưa được ghi.

## 5. Lấy giá trị theo **tên cột**

### 5.1. Getter theo tên dễ đọc và ít phụ thuộc thứ tự SELECT

~~~java
Instant at = row.getInstant("event_time");
double value = row.getDouble("reading_value");
String status = row.getString("status");
boolean valid = row.getBoolean("valid");
~~~

Ưu điểm:

- Mã nguồn thể hiện ý nghĩa nghiệp vụ của trường.
- Nếu đổi thứ tự SELECT mà giữ đủ tên cột, mapping theo tên vẫn đúng.
- Code review dễ nhận ra đang lấy kiểu dữ liệu nào.
- Khi thêm bớt cột, có thể tập trung kiểm tra schema và các getter liên quan.

Nhược điểm:

- Cần bảo đảm tên hoặc **alias** thực sự xuất hiện trong kết quả.
- Khi SELECT nhiều cột trùng tên từ expression/alias, truy cập theo tên có thể không còn rõ ràng.
- Tên có chữ hoa/thường được quote trong CQL có semantics khác tên thông thường.

**Thực hành tốt:** dùng `SELECT` liệt kê tường minh các cột và giữ tên/alias ổn định như một phần hợp đồng giữa repository và DTO.

### 5.2. Column alias thay đổi tên nhìn từ ResultSet

Ví dụ:

~~~cql
SELECT event_time AS occurred_at,
       reading_value AS measured_value,
       status
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 10;
~~~

Kết quả được ánh xạ theo các **tên cột trả về**:

~~~java
Instant occurredAt = row.getInstant("occurred_at");
double measuredValue = row.getDouble("measured_value");
String status = row.getString("status");
~~~

Không nên tiếp tục gọi `row.getInstant("event_time")` nếu projection chỉ đặt tên `occurred_at` cho cột đó. Khi đổi alias, phải cập nhật mapper/test tương ứng.

### 5.3. Quoted identifiers và chữ hoa/thường

CQL thông thường xử lý **unquoted identifier** theo quy tắc chuẩn hóa tên; với **quoted identifier**, chữ hoa/thường có thể được giữ nguyên.

~~~cql
-- Minh họa một bảng đặc biệt do schema cũ tạo.
-- Nếu column được khai báo là "SensorValue", phải dùng tên
-- quoted chính xác trong CQL, không nhầm thành sensorvalue.
SELECT "SensorValue"
FROM legacy.samples
WHERE device_id = ?;
~~~

Ở Java, nếu tên trả về có quy tắc quote đặc biệt, có thể sử dụng `CqlIdentifier.fromCql(...)` sau khi đã biết schema/alias thực tế. **Không dùng việc tự lower-case mọi chuỗi** làm giải pháp chung, vì có thể làm sai các tên được quote.

Đối với bài tập cơ bản, nên dùng định danh lowercase `snake_case` rõ ràng và tránh quoted identifiers khi không có lý do nghiệp vụ.

## 6. Lấy giá trị theo **chỉ số cột**

### 6.1. Index bắt đầu từ 0

Với:

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

Java:

~~~java
Instant at = row.getInstant(0);     // event_time
double value = row.getDouble(1);    // reading_value
String status = row.getString(2);   // status
boolean valid = row.getBoolean(3); // valid
~~~

Kết quả có bốn vị trí: **0, 1, 2, 3**. Vị trí `4` không hợp lệ ở projection này.

### 6.2. Index là vị trí trong kết quả, không phải thứ tự DDL

Nếu đổi thành:

~~~cql
SELECT status, event_time, valid, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

thì mapping thay đổi:

| Index | Tên sau khi đổi projection | Getter đúng |
|---:|---|---|
| 0 | `status` | `getString(0)` |
| 1 | `event_time` | `getInstant(1)` |
| 2 | `valid` | `getBoolean(2)` |
| 3 | `reading_value` | `getDouble(3)` |

Code cũ `row.getInstant(0)` sẽ không còn đúng vì index 0 giờ là `text`. Lỗi có thể xuất hiện khi decode codec, thay vì một lỗi có thông báo rõ “bạn đổi thứ tự SELECT”.

### 6.3. Nên dùng index khi nào?

Truy cập theo index hữu ích khi:

- Viết mapper cho **projection cố định** đã có unit/integration tests.
- Đọc một biểu thức duy nhất mà tên cột khó dùng hoặc không ổn định.
- Xử lý column definitions động có kiểm soát, ví dụ trình hiển thị metadata của một query đã được allowlist.

Tuy vậy, **getter theo index không tự đảm bảo nhanh hơn đáng kể** trên toàn bộ hệ thống. Hiệu năng Cassandra thường bị chi phối bởi network, replica, tombstone/SSTable, pagination và lượng dữ liệu hơn là việc tra tên một cột ở một row.

### 6.4. Chọn index an toàn từ metadata

Không hard-code `2` nếu có thể tra tên qua `ColumnDefinitions`:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

ColumnDefinitions defs = row.getColumnDefinitions();
int statusIndex =
    defs.firstIndexOf(CqlIdentifier.fromCql("status"));

if (statusIndex < 0) {
    throw new IllegalStateException(
        "SELECT result did not contain status");
}

String status = row.getString(statusIndex);
~~~

Hàm `firstIndexOf` tìm vị trí đầu tiên của tên cột. Nếu projection có nhiều cột/alias trùng tên, ứng dụng cần làm rõ projection thay vì hy vọng “first” là cột mong muốn.

## 7. `ColumnDefinitions`: biết Row đang chứa những cột nào

### 7.1. Khảo sát metadata của một Row

~~~java
import com.datastax.oss.driver.api.core.cql.ColumnDefinition;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

ColumnDefinitions defs = row.getColumnDefinitions();

for (int i = 0; i < defs.size(); i++) {
    ColumnDefinition def = defs.get(i);
    System.out.println(
        "index=" + i +
        " name=" + def.getName().asInternal() +
        " cqlType=" + def.getType());
}
~~~

`ColumnDefinitions` có thể được lấy từ `ResultSet` hoặc `Row`. Những thông tin thường cần khi debug:

- **Số cột**: đã SELECT bao nhiêu projection?
- **Tên/alias thực tế**: mapper đang gọi đúng tên không?
- **CQL data type**: getter đang đòi đúng Java type không?
- **Thứ tự trả về**: code index-based còn hợp lệ sau query change không?

Không ghi bừa toàn bộ dữ liệu Row ra log production chỉ vì đang debug metadata. **Tên và kiểu cột** thường ít nhạy cảm hơn **giá trị**; vẫn cần tuân thủ chính sách an toàn schema của hệ thống.

### 7.2. Phân biệt cột không được SELECT với giá trị null

Trường hợp A:

~~~cql
SELECT event_time, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 1;
~~~

`status` **không thuộc `ColumnDefinitions`**. Nếu Java cố `getString("status")`, đó là lỗi mapping/projection chứ **không** phải giá trị `null` hợp lệ.

Trường hợp B:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 1;
~~~

`status` thuộc projection. Nếu cell không có giá trị, `row.isNull("status")` có thể `true` và `getString("status")` có thể là `null`.

Sự phân biệt này giúp thiết kế API trả “không có thuộc tính” hay “đã chọn nhưng chưa có giá trị” chính xác hơn.

### 7.3. Tránh tên cột trùng lặp

Một projection có các alias trùng nhau có thể khiến truy cập theo tên không rõ ràng. Nếu cần lấy hai biểu thức khác nhau, đặt **hai alias khác nhau** hoặc truy cập theo index đã được kiểm chứng.

Không coi `row.getString("x")` là truy cập một cột có danh tính duy nhất nếu `ColumnDefinitions` chứa nhiều projection cùng tên `x`.

## 8. Getter phải tương thích kiểu CQL

### 8.1. Những ánh xạ thường gặp trong Driver 4.x

| Kiểu CQL | Kiểu Java dùng phổ biến | Getter `Row` |
|---|---|---|
| `text` / `varchar` / `ascii` | `String` | `getString(...)` |
| `uuid` / `timeuuid` | `UUID` | `getUuid(...)` |
| `tinyint` | `byte` | `getByte(...)` |
| `smallint` | `short` | `getShort(...)` |
| `int` | `int` | `getInt(...)` |
| `bigint` / `counter` | `long` | `getLong(...)` |
| `varint` | `BigInteger` | `getBigInteger(...)` |
| `float` | `float` | `getFloat(...)` |
| `double` | `double` | `getDouble(...)` |
| `decimal` | `BigDecimal` | `getBigDecimal(...)` |
| `boolean` | `boolean` | `getBoolean(...)` |
| `timestamp` | `Instant` | `getInstant(...)` |
| `date` | `LocalDate` | `getLocalDate(...)` |
| `time` | `LocalTime` | `getLocalTime(...)` |
| `blob` | `ByteBuffer` | `getByteBuffer(...)` |
| `list<text>` | `List<String>` | `getList(..., String.class)` |
| `set<uuid>` | `Set<UUID>` | `getSet(..., UUID.class)` |
| `map<text,int>` | `Map<String,Integer>` | `getMap(..., String.class, Integer.class)` |

Bảng sử dụng **codec mặc định** thường gặp. Với custom codec hoặc user-defined types, API có thể khác; cần đối chiếu với Java Driver version thực tế.

Ví dụ:

~~~java
java.util.UUID id = row.getUuid("device_id");
java.time.Instant time = row.getInstant("event_time");
java.time.LocalDate day = row.getLocalDate("event_day");
java.math.BigDecimal factor =
    row.getBigDecimal("calibration_factor");
java.util.List<String> tags =
    row.getList("tags", String.class);
~~~

Những ví dụ chỉ đúng khi **các cột tương ứng có trong SELECT**. Nếu SELECT không trả `device_id`, dòng `getUuid("device_id")` vẫn không hợp lệ dù `device_id` là partition key của bảng.

### 8.2. `timestamp` không phải `LocalDateTime`

CQL `timestamp` biểu diễn mốc thời gian theo epoch; trong Driver 4.x, `getInstant(...)` phù hợp để đọc mốc tuyệt đối. `LocalDateTime` không có timezone nên **không phải ánh xạ mặc định thay thế `Instant`**.

Khi cần hiển thị theo timezone:

~~~java
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;

Instant eventTime = row.getInstant("event_time");
ZonedDateTime local =
    eventTime.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Bước này chỉ dành cho hiển thị/nghiệp vụ. Không tự đổi timezone trước khi so timestamp giữa các replica hoặc ghi nhận event order.

### 8.3. `decimal` và `double` không cùng semantics

- `double` là số dấu phẩy động nhị phân, phù hợp đo lường nhưng không lý tưởng cho tiền.
- `decimal` ánh xạ `BigDecimal`, phù hợp trường cần precision thập phân.

Không tự thay `getBigDecimal("amount")` bằng `getDouble("amount")` vì cả hai “đều là số”. Với tiền tệ và so sánh chính xác, hãy giữ type/scale và quy tắc làm tròn rõ ràng.

### 8.4. Collections, UDT và blob

Ví dụ dữ liệu có tags:

~~~cql
SELECT tags, calibration_factor
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 10;
~~~

Java:

~~~java
List<String> tags = row.getList("tags", String.class);
BigDecimal factor =
    row.getBigDecimal("calibration_factor");

if (tags != null) {
    for (String tag : tags) {
        useTag(tag); // Hàm xử lý minh họa.
    }
}
~~~

Collection có thể gây allocation lớn nếu mỗi row chứa nhiều phần tử. Với blob, cần xét kích thước, khả năng giữ reference và quota trước khi biến nó thành một `byte[]` cực lớn.

Với UDT, người dùng thường lấy `UdtValue` rồi đọc từng field theo tên/type hoặc dùng custom codec. **Không ép mọi UDT thành String** bằng `getString` khi CQL type không phải text.

## 9. Xử lý null an toàn và tránh mất nghĩa dữ liệu

### 9.1. `isNull` trước getter kiểu primitive

CQL cho phép một cell không có giá trị sống. Một getter trả về **primitive** Java như `getDouble` hay `getBoolean` không có cách biểu diễn `null` trong kiểu trả về.

Vì thế, khi null mang ý nghĩa nghiệp vụ, luôn kiểm tra:

~~~java
Double value = row.isNull("reading_value")
    ? null
    : row.getDouble("reading_value");

Boolean valid = row.isNull("valid")
    ? null
    : row.getBoolean("valid");

String status = row.getString("status");
// status có thể null.
~~~

**Không mặc định “không có số đo” tương đương giá trị 0.0** hoặc “không có trạng thái valid” tương đương `false`. Nếu mapper bỏ qua null, dữ liệu nghiệp vụ có thể bị sai mà không có exception.

### 9.2. Một DTO thể hiện null có chủ đích

~~~java
import java.time.Instant;

public record ReadingDto(
    Instant eventTime,
    Double value,
    String status,
    Boolean valid
) {}

static ReadingDto mapReading(Row row) {
    return new ReadingDto(
        row.getInstant("event_time"),
        row.isNull("reading_value")
            ? null : row.getDouble("reading_value"),
        row.getString("status"),
        row.isNull("valid")
            ? null : row.getBoolean("valid")
    );
}
~~~

Ví dụ dùng Java `record` (Java 16+). Nếu project dùng Java 11 hoặc release driver/JDK khác, chuyển sang class DTO thường. Trước khi nâng JDK, kiểm tra compatibility matrix của Cassandra driver/library và nền tảng ứng dụng.

Trong một codebase lớn, có thể dùng `Optional` ở return boundary hoặc đối tượng domain có trạng thái đặc biệt. Nhưng **đừng lấy giá trị mặc định giả** chỉ để tránh nullable field.

### 9.3. Null, missing row và missing projection

| Tình huống | Cách phát hiện | Cách diễn giải |
|---|---|---|
| Query không trả row | `resultSet.one() == null` | Không có bản ghi sống phù hợp |
| Row có cột `status` nhưng không có giá trị | `row.isNull("status")` | Cell null theo kết quả CQL |
| `status` không được SELECT | `ColumnDefinitions` không chứa cột | Mapper/projector không khớp |
| Java đọc nhầm kiểu | Getter/codec báo lỗi | Schema hoặc mapper sai |
| Row tồn tại, `valid=false` | `isNull("valid")==false` và `getBoolean(...)==false` | Giá trị false hợp lệ, không phải null |

Không dùng chuỗi `"null"` thay cho null thật trong dữ liệu hoặc JSON chỉ vì thấy logger in `null`.

## 10. `one()`, iterator và `all()`: ba cách tiêu thụ khác nhau

### 10.1. `one()` đọc row tiếp theo

~~~java
ResultSet rs = session.execute(statement);

Row first = rs.one();
Row second = rs.one();

// Nếu còn row, iterator bắt đầu từ row tiếp theo.
for (Row rest : rs) {
    process(rest);
}
~~~

`one()` **tiêu thụ** row theo vị trí hiện tại của `ResultSet`. Vì vậy code:

~~~java
Row first = rs.one();
for (Row row : rs) {
    // Không duyệt lại first, trừ khi query được thực thi lại.
}
~~~

không tương đương “xem thử first rồi duyệt từ đầu”. Nếu muốn xử lý toàn bộ, hãy xử lý `first` hoặc bắt đầu vòng lặp từ đầu.

### 10.2. Duyệt từng row phù hợp với kết quả lớn

~~~java
ResultSet rs = session.execute(statement);
long count = 0;

for (Row row : rs) {
    Instant at = row.getInstant("event_time");
    Double value = row.isNull("reading_value")
        ? null : row.getDouble("reading_value");

    writeToBoundedSink(at, value); // Hàm minh họa.
    count++;
}

System.out.println("Processed rows: " + count);
~~~

Cách này giữ ít dữ liệu trong application code **nếu `writeToBoundedSink` không gom toàn bộ row vào bộ nhớ**. Driver vẫn có page buffers và tài nguyên riêng; xử lý từng row không có nghĩa peak heap bằng đúng một Row.

### 10.3. `all()` gom toàn bộ phần còn lại

~~~java
ResultSet rs = session.execute(statement);
List<Row> allRemaining = rs.all();
~~~

`all()` thuận tiện cho query **có giới hạn nhỏ, đã biết**, nhưng có thể gây vấn đề với hàng trăm nghìn/hàng triệu row:

- Driver có thể phải fetch nhiều page còn lại.
- Java List giữ toàn bộ row và references tới dữ liệu đã decode/buffer.
- Tăng heap allocation, GC pause và nguy cơ `OutOfMemoryError`.
- Query chạy dài gây ảnh hưởng replica/network khi client tự kéo hết dữ liệu.

**Page size 100 không ngăn `all()` lấy 100.000 row qua 1.000 page.** Page size giới hạn mục tiêu mỗi page, không giới hạn tổng kết quả.

### 10.4. Một ResultSet không phải container để duyệt lại tùy ý

Đừng viết code giả định có thể gọi `rs.iterator()` nhiều lần để đọc lại cùng tất cả row từ đầu. `ResultSet` là giao diện tiêu thụ có trạng thái; row đã được lấy ra qua `one()` hoặc iterator **không phải một bản ghi có thể reset như ArrayList**.

Nếu cần duyệt lại dữ liệu:

- Thực thi lại query với điều kiện phù hợp.
- Giữ một tập nhỏ đã giới hạn vào DTO/List nếu nghiệp vụ thật sự cần.
- Với tập lớn, lưu kết quả tới stream/file/sink có giới hạn và xét consistency giữa hai lần đọc.

## 11. Phân trang: ResultSet không nhất thiết chứa mọi row từ đầu

### 11.1. Cơ chế sync paging

Java Driver 4.x có thể tự **fetch page kế tiếp khi iterator/`one()` cần thêm row**. Ví dụ query:

~~~cql
SELECT event_time, reading_value, status, valid
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 200;
~~~

Java:

~~~java
BoundStatement bs = prepared.bind(deviceId, eventDay)
    .setPageSize(50)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

ResultSet rs = session.execute(bs);
for (Row row : rs) {
    process(row);
}
~~~

Trong điều kiện lý tưởng, tối đa 200 row có thể chia thành khoảng 4 page, mỗi page 50 row. Thực tế có thể có page ít row hơn do byte limit, dữ liệu/phiên bản và các điều kiện server.

**`LIMIT 200`** hạn chế *tổng row* của query. **`setPageSize(50)`** đặt *mục tiêu số row mỗi page*. Chúng không thay thế nhau.

### 11.2. Hai phương thức kiểm tra page

~~~java
int ready = rs.getAvailableWithoutFetching();
boolean fullyFetched = rs.isFullyFetched();

System.out.println(
    "Ready locally=" + ready + ", fullyFetched=" + fullyFetched);
~~~

- `getAvailableWithoutFetching()` trả về số row có thể lấy từ trạng thái hiện tại mà **không cần network fetch tiếp**.
- `isFullyFetched()` cho biết đã lấy tất cả page của query hay chưa.
- `ready == 0` **không tự chứng minh hết kết quả** khi `fullyFetched == false`.
- `fullyFetched == true` **không tự chứng minh mọi row đã được application tiêu thụ**; một số row có thể đang sẵn ở client.

Đừng sử dụng những giá trị trên như `COUNT(*)` hay tổng số row của table.

### 11.3. Time to first page khác total consume time

~~~text
T0: session.execute(statement) bắt đầu
T1: trang đầu sẵn sàng, ResultSet được trả
T2: ứng dụng duyệt/fetch đủ các page cần thiết
T3: xử lý hết kết quả

Latency execute: thường gần khoảng T1 - T0
Consume latency: gần khoảng T3 - T0
~~~

Đối với truy vấn nhiều page, chỉ đo `session.execute()` có thể bỏ sót thời gian fetch các page sau. Khi logging slow query hoặc benchmark, phải nêu rõ **đo đến trang đầu hay đến khi tiêu thụ hết**.

### 11.4. Page không phải snapshot transaction

Các page có thể được lấy ở **những thời điểm khác nhau**. Trong lúc duyệt, ghi/xóa hoặc TTL có thể làm thay đổi dữ liệu đọc được. Paging không tạo một snapshot toàn bảng có isolation như một transaction RDBMS dài.

Nếu cần phân trang API ổn định theo thứ tự thời gian, thiết kế theo partition/clustering keys và đánh giá **paging state hoặc keyset pagination** phù hợp. Đừng mô phỏng `OFFSET` SQL bằng cách kéo bỏ hàng nghìn row mỗi lần.

## 12. Row trả về từ SELECT thường, aggregate và LWT

### 12.1. SELECT thường

~~~cql
SELECT event_time, reading_value
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

Kết quả là các `Row` có **hai cột**: `event_time` và `reading_value`.

### 12.2. Aggregate trả về kiểu khác

Ví dụ đếm bản ghi trong **một partition nhỏ đã biết**:

~~~cql
SELECT COUNT(*) AS total
FROM telemetry.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

Java:

~~~java
Row countRow = session.execute(statement).one();
if (countRow == null) {
    throw new IllegalStateException(
        "Aggregate query returned no row");
}
long total = countRow.getLong("total");
~~~

`COUNT(*)` thường có kiểu kết quả tương ứng **bigint/long**, không phải `int`. **Không dùng COUNT(*) toàn bảng lớn làm cách đo kích thước Cassandra**: aggregation có thể phải đọc nhiều dữ liệu và tốn CPU/I/O.

### 12.3. Conditional write/LWT: `wasApplied()`

Ví dụ conditional insert:

~~~cql
INSERT INTO telemetry.readings_by_device_day (
    device_id, event_day, event_time, reading_value
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Java:

~~~java
ResultSet rs = session.execute(conditionalInsertStatement);

if (rs.wasApplied()) {
    System.out.println("Conditional insert applied");
} else {
    System.out.println("Condition was not satisfied");
}
~~~

`wasApplied()` là phương thức rõ nghĩa để biết **conditional statement có được áp dụng hay không**. Không dùng `resultSet.one()==null` như dấu hiệu kiểm tra thành công của LWT.

Khi điều kiện không đạt, một số phản hồi conditional chứa thông tin row hiện hữu; schema của phần row đó phụ thuộc statement/phiên bản. Nếu cần đọc, phải kiểm tra `ColumnDefinitions` và xử lý cẩn thận. LWT có chi phí đồng thuận khác ghi thông thường; **không dùng IF NOT EXISTS cho mọi INSERT chỉ để có cờ thành công**.

## 13. Getter theo tên hay theo index: lựa chọn nào hợp lý hơn?

| Tiêu chí | Theo tên, ví dụ `getString("status")` | Theo index, ví dụ `getString(2)` |
|---|---|---|
| Độ dễ đọc | Cao, tên thể hiện ý nghĩa | Cần đối chiếu thứ tự SELECT |
| Đổi thứ tự projection | Thường vẫn đúng nếu tên giữ nguyên | Có thể đọc sai type/cột |
| Đổi alias | Phải đổi tên trong mapper | Có thể không ảnh hưởng nếu thứ tự giữ nguyên |
| Projection cố định, ít cột | Rất phù hợp | Có thể phù hợp khi đã test |
| Query được chọn động trong tập allowlist | Dễ kiểm soát nếu alias ổn định | Cần map index theo từng template |
| Debug lỗi mapping | Dễ phát hiện cột bị thiếu | Dễ lỗi off-by-one hoặc lệch thứ tự |
| Tối ưu hiệu năng | Thường đủ tốt | Không tự thay đổi latency Cassandra đáng kể |
| Nguy cơ cột trùng tên | Phải tránh hoặc kiểm tra definitions | Index rõ vị trí nhưng cần hợp đồng projection |

**Khuyến nghị cơ bản:** đối với repository nghiệp vụ, ưu tiên **getter theo tên** và projection tường minh. Nếu dùng getter theo index vì lý do kỹ thuật, lưu một định nghĩa projection cố định và test để phát hiện schema/query drift.

### 13.1. Không lấy Row bằng cách dựa vào thứ tự SELECT *

~~~cql
SELECT *
FROM telemetry.readings_by_device_day
WHERE device_id = ? AND event_day = ?
LIMIT 10;
~~~

`SELECT *` có thể giúp thăm dò schema, nhưng trong code production nó tạo coupling không rõ ràng:

- Trả cột không cần thiết, làm tăng network/decoding.
- Thứ tự và tập cột không nên được xem là hợp đồng mapper bền vững.
- Khi schema thêm cột, ứng dụng có thể tải thêm dữ liệu ngoài dự kiến.
- Index-based mapper đặc biệt dễ sai khi query projection thay đổi.

**Liệt kê đúng những cột cần dùng** thường giúp bảo trì và hiệu năng ổn định hơn.

## 14. PreparedStatement, Row mapper và tái sử dụng mã

### 14.1. Không viết mapping lặp lại ở mọi controller

Một repository có thể trả DTO thay vì truyền `Row` lên HTTP layer:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;

public final class ReadingMapper {
    private ReadingMapper() {}

    public static ReadingDto map(Row row) {
        if (row == null) {
            throw new IllegalArgumentException("row cannot be null");
        }
        return new ReadingDto(
            row.getInstant("event_time"),
            row.isNull("reading_value")
                ? null : row.getDouble("reading_value"),
            row.getString("status"),
            row.isNull("valid")
                ? null : row.getBoolean("valid")
        );
    }
}
~~~

Khi dùng mapper, đảm bảo repository SELECT đủ bốn cột `event_time`, `reading_value`, `status`, `valid`. Nếu một API chỉ cần timestamp và value, có thể tạo projection/DTO khác thay vì kéo mọi cột.

### 14.2. Prepared statement không thay thế type safety của Row

~~~java
PreparedStatement ps = session.prepare(
    "SELECT event_time, reading_value " +
    "FROM telemetry.readings_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 1");

BoundStatement bs = ps.bind(deviceId, day);
Row row = session.execute(bs).one();

if (row != null) {
    Instant t = row.getInstant("event_time");
    double d = row.getDouble("reading_value");
}
~~~

Prepared statement giúp cố định CQL shape và bind giá trị. Tuy nhiên nếu người lập trình đổi `getDouble("reading_value")` thành `getString("reading_value")`, driver không tự biến CQL `double` thành String theo kiểu tùy ý. Cần **codec/getter tương thích**, kiểm thử và xử lý lỗi.

### 14.3. Query shape liên quan schema

Một bảng theo partition key giúp truy vấn có phạm vi định vị rõ. Nhưng nếu partition quá rộng, có hàng triệu row hoặc nhiều tombstone, vòng lặp `ResultSet` vẫn phải fetch nhiều dữ liệu và có thể làm latency xấu đi.

**Row API chỉ là cách đọc kết quả**, không phải công cụ tối ưu query tự động. Cần thiết kế bảng theo truy vấn, giữ partition vừa phải và chọn CL phù hợp.

## 15. Kết nối với consistency, replication và giới hạn ResultSet

`ResultSet` phản ánh **kết quả một lần thực thi CQL** qua coordinator. Cơ chế lấy dữ liệu phía server chịu ảnh hưởng:

- **Partition key** xác định token và replica placement.
- **Replication factor** quyết định số bản sao tồn tại.
- **Consistency level** điều khiển điều kiện phản hồi của thao tác.
- **Read path** có thể merge memtable/SSTable và xử lý tombstone.
- **Compaction/repair** ảnh hưởng tải và khả năng phục vụ.
- **Paging** tạo những request tiếp theo khi còn kết quả.

Ví dụ:

~~~java
BoundStatement query = prepared.bind(deviceId, day)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(50);
~~~

Điều này đặt CL và mục tiêu page size, nhưng **không làm một SELECT thiếu partition key trở thành truy vấn tốt** và không tạo snapshot toàn bộ các trang.

### 15.1. Row rỗng không tự chứng minh dữ liệu đã mất

Nếu `one()` trả `null` hoặc iterator hết row, các khả năng cần xét gồm:

- WHERE/bind values không đúng partition/date.
- Row đã bị DELETE hoặc TTL hết hạn.
- Dữ liệu chưa được ghi hoặc chưa đến replica có thể trả kết quả theo CL.
- Một schema/query migration thay đổi bảng được đọc.
- Dữ liệu bị thiếu do lỗi replication/recovery, cần kiểm chứng riêng.

Không tự sửa dữ liệu chỉ vì một SELECT `LIMIT 1` không thấy row; phải xác định yêu cầu consistency và thời điểm ghi.

### 15.2. Chuyển đổi index sau ALTER TABLE

Nếu ứng dụng dùng `SELECT *` + `getString(5)`, một thay đổi schema có thể làm mapper đọc sai hoặc gây lỗi khi cột được thêm/xóa.

Với rollout schema:

1. Ưu tiên explicit SELECT và getter theo tên.
2. Ghi schema version và query template trong test.
3. Đảm bảo compatibility của ứng dụng cũ/mới trong giai đoạn chuyển tiếp.
4. Không tự suy cột mới luôn có giá trị khác null trong dữ liệu lịch sử.
5. Kiểm tra codec và nullable fields khi nâng cấp driver/JDK.

## 16. Quan sát và xử lý lỗi khi đọc ResultSet/Row

### 16.1. Những lỗi thường gặp

| Triệu chứng | Giả thuyết | Bước xử lý |
|---|---|---|
| `NullPointerException` khi gọi `row.get...` | `one()` trả `null` | Kiểm tra null row trước |
| Lỗi lookup tên cột | Column không có trong projection hoặc alias đổi | In `ColumnDefinitions` trong lab, sửa SELECT/mapper |
| Lỗi index ngoài phạm vi | Dùng index >= số cột hoặc âm | Kiểm tra `defs.size()` và 0-based |
| Lỗi codec/type conversion | Getter không tương thích CQL type | So `defs.get(i).getType()` và mapping |
| Field giá trị 0 dù CQL null | Dùng primitive getter mà bỏ `isNull` | Map qua nullable wrapper/Optional khi cần |
| Memory tăng khi đọc nhiều row | `all()`/List giữ toàn bộ, page lớn | Duyệt gia tăng, giới hạn kết quả, backpressure |
| Slow query dù chỉ dùng `one()` | Truy vấn nguồn vẫn đắt hoặc server phải đọc nhiều SSTable/tombstone | Kiểm tra query shape, partition, CL, metrics |
| `getAvailableWithoutFetching()==0` | Page hiện tại hết nhưng còn page sau | Kiểm tra `isFullyFetched()`/iterator |
| Giá trị null không mong muốn sau deploy | SELECT/alias/schema hoặc row lịch sử chưa có cột | Kiểm tra DDL diff, projection, logic migration |
| LWT trả Row lạ | Đang dùng conditional statement | Sử dụng `wasApplied()` và kiểm tra definitions |

### 16.2. Chỉ log metadata cần thiết

Ví dụ log an toàn hơn khi chẩn đoán:

~~~text
operation=read_device_day
query_template=read_readings_v2
outcome=decode_error
column=reading_value
expected_java_type=double
cql_type=double
elapsed_ms=42
~~~

Đây là **schema log ứng dụng đề xuất**, không phải format log mặc định Java Driver. Không ghi nguyên giá trị `device_id`, PII, token, raw row data hoặc secrets vào log chung. Khi phải điều tra một bản ghi cụ thể, dùng correlation ID và quyền truy cập phù hợp.

### 16.3. Phân biệt client mapping với Cassandra timeout

Lỗi Java như “could not decode column” thường xảy ra sau khi driver nhận dữ liệu. Lỗi timeout/unavailable liên quan coordinator/replica và CL lại có phạm vi khác. Cần tách metric:

- **CQL request success/timeout/error** ở driver.
- **Mapping success/error** ở ứng dụng.
- **Rows returned/processed**, page count và bytes.
- **p95/p99 end-to-end** của endpoint.

Nếu request thành công nhưng DTO mapper ném exception, không kết luận Cassandra không trả row. Và nếu SELECT timeout, không tự suy lỗi do `getString` hay `getDouble`.

## 17. Unit test mapper và integration test ResultSet

### 17.1. Test mapping theo tên

Với một hàm map `Row`, unit test có thể dùng mock `Row` (nếu project sử dụng Mockito) để bảo đảm lấy đúng các field. Ví dụ ý tưởng:

~~~java
// Pseudocode unit test: tùy Mockito/JUnit và lớp DTO của project.
when(row.getInstant("event_time")).thenReturn(timestamp);
when(row.isNull("reading_value")).thenReturn(false);
when(row.getDouble("reading_value")).thenReturn(24.6);
when(row.getString("status")).thenReturn("OK");
when(row.isNull("valid")).thenReturn(false);
when(row.getBoolean("valid")).thenReturn(true);

ReadingDto dto = ReadingMapper.map(row);

assertEquals(timestamp, dto.eventTime());
assertEquals(24.6, dto.value());
assertEquals("OK", dto.status());
assertEquals(true, dto.valid());
~~~

Đây là **đoạn minh họa**, chưa có imports/khởi tạo mock; không phải mã test có thể copy chạy độc lập. Nó giúp mô tả hợp đồng mapper.

### 17.2. Test tích hợp với Cassandra lab

Một integration test đáng tin nên:

1. Tạo schema test tương thích với phiên bản Cassandra cần hỗ trợ.
2. Chèn row đủ các kiểu `uuid`, `date`, `timestamp`, `double`, `text`, `decimal`, `list`, `boolean`.
3. SELECT cột theo thứ tự cố định; so getter **tên và index**.
4. SELECT cùng cột theo thứ tự khác; khẳng định name-based mapper vẫn đúng và index mapping cũ không còn đúng.
5. Tạo row thiếu trường optional, xác minh `isNull` và DTO nullable.
6. Query WHERE không khớp, xác minh `one()==null`.
7. Query nhiều page, xác minh vòng lặp xử lý đủ row và `all()` không được dùng trên tập lớn.
8. SELECT alias, kiểm tra tên trong `ColumnDefinitions`.
9. Test LWT riêng, dùng `wasApplied()`.
10. Đo request/consume latency và bảo đảm test chỉ kết nối tới lab, không tới production.

### 17.3. Checklist code review

~~~text
[ ] Session được tái sử dụng; có cơ chế close khi shutdown.
[ ] CQL template dùng bind values, không nối raw input.
[ ] WHERE đầy đủ partition key cho query được thiết kế.
[ ] SELECT liệt kê cột thật sự cần, tránh SELECT * trong API.
[ ] one() được kiểm tra null trước khi gọi getter.
[ ] Row getters đúng CQL type, dùng Instant/LocalDate/BigDecimal đúng chỗ.
[ ] Cột nullable được kiểm tra isNull, nhất là primitive getters.
[ ] Name-based getters đúng alias; index-based mapping có test projection.
[ ] Không dùng ResultSet như List có thể đọc lại từ đầu.
[ ] all() chỉ dùng với tập kết quả nhỏ, có giới hạn.
[ ] Page size và LIMIT được phân biệt rõ.
[ ] LWT dùng wasApplied(), không suy thành công từ one().
[ ] Driver 4.x API đúng phiên bản và JDK tương thích.
[ ] Logs không lộ raw row/PII/bind values.
[ ] Có metrics về timeout, mapping errors, p99 và số row/pages.
~~~

## 18. Tự kiểm tra: câu hỏi và đáp án

### Câu 1 — ResultSet và Row

`session.execute(SELECT...)` trả một `ResultSet` có hai row. `ResultSet` có phải chỉ là `List<Row>` đã tải toàn bộ vào Java heap không?

**Đáp án:** Không. Đây là giao diện tiêu thụ kết quả đồng bộ với paging; driver có thể mới lấy trang đầu và lấy các page khác khi cần.

### Câu 2 — Giá trị rỗng

`Row row = rs.one();` trả `null`. Có nên gọi `row.getString("status")` để kiểm tra status null không?

**Đáp án:** Không. Row không tồn tại; gọi getter sẽ gây `NullPointerException`. Phải kiểm tra `row == null` trước.

### Câu 3 — Index

Query là `SELECT event_time, reading_value, status`. `row.getString(2)` đọc cột nào?

**Đáp án:** `status`, vì index bắt đầu từ 0: 0=event_time, 1=reading_value, 2=status.

### Câu 4 — Đảo thứ tự SELECT

Đổi thành `SELECT status, event_time, reading_value`. Getter `row.getInstant(0)` còn đúng không?

**Đáp án:** Không. Index 0 lúc này là `status`. Nên dùng getter theo tên hoặc cập nhật mapper index có test.

### Câu 5 — Cột không được SELECT

Query chỉ SELECT `event_time`, `reading_value`, nhưng Java gọi `row.getString("status")`. Có phải status đang null trong Cassandra?

**Đáp án:** Không. Cột không nằm trong projection; đó là lỗi mapper. Kiểm tra `ColumnDefinitions`, sửa SELECT hoặc không đọc field này.

### Câu 6 — Primitive và null

CQL `reading_value` không có giá trị, ứng dụng cần phân biệt “chưa đo” với `0.0`. Có nên gọi trực tiếp `getDouble` rồi dùng kết quả không?

**Đáp án:** Không. Kiểm tra `isNull("reading_value")` trước và lưu vào `Double` nullable hoặc đối tượng domain phù hợp.

### Câu 7 — Kiểu timestamp

CQL `timestamp` trong Driver 4.x được đọc bằng getter nào trong bài?

**Đáp án:** `row.getInstant(...)`, trả `java.time.Instant`. CQL `date` dùng `getLocalDate(...)`.

### Câu 8 — Page size

Query không có `LIMIT`, page size = 100. Có nghĩa tổng kết quả không quá 100 row không?

**Đáp án:** Không. Page size là mục tiêu mỗi lần fetch; truy vấn có thể trả nhiều page. Cần giới hạn tổng kết quả/stop condition riêng.

### Câu 9 — all()

Vòng lặp cần xử lý một triệu row nhưng code gọi `rs.all()` để có List rồi xử lý. Rủi ro gì?

**Đáp án:** Có thể fetch và giữ toàn bộ row còn lại trong heap, tăng memory/GC và OOM. Nên tiêu thụ gia tăng có backpressure hoặc pipeline bounded.

### Câu 10 — wasApplied

Sau `INSERT ... IF NOT EXISTS`, nên dùng `rs.one()==null` hay `rs.wasApplied()` để xác định điều kiện có đạt?

**Đáp án:** `rs.wasApplied()`, vì đây là phản hồi conditional query/LWT. Row trả về có cấu trúc riêng.

### Câu 11 — Aggregate

`SELECT COUNT(*) AS total` trả CQL bigint. Getter đúng trong bài là `getInt("total")` hay `getLong("total")`?

**Đáp án:** `getLong("total")`. Không dùng COUNT toàn bảng lớn như cách đo kích thước thông thường vì tốn tài nguyên.

### Câu 12 — Name-based mapping

Query đổi thứ tự SELECT nhưng giữ alias `event_time`, `reading_value`, `status`. Getter theo tên có lợi gì?

**Đáp án:** Mapper theo tên vẫn nhắm đúng cột, ít phụ thuộc thứ tự projection; vẫn cần kiểm tra type/alias và cột có tồn tại.

### Câu 13 — Driver 3.x và 4.x

Một dự án cũ dùng `com.datastax.driver.core.ResultSet`. Có thể dán imports `com.datastax.oss.driver.api.core.*` và giữ nguyên toàn bộ code không?

**Đáp án:** Không. Cần xác minh API, getter kiểu thời gian, cấu hình session/paging và compatibility khi chuyển major driver.

### Câu 14 — Cassandra consistency

Một SELECT với `LOCAL_QUORUM` không thấy row. Có thể kết luận rằng Java `getUuid` làm mất dữ liệu không?

**Đáp án:** Không. Nếu không có Row, getter chưa được gọi. Cần kiểm tra WHERE, thời điểm dữ liệu, CL, replication, TTL/delete và lỗi đường request.

## 19. Những ngộ nhận nên tránh

| Ngộ nhận | Điều đúng |
|---|---|
| “ResultSet luôn là mọi Row đã tải về.” | Có thể chỉ có trang đầu; paging lấy dần |
| “one() trả null nghĩa một cột bị null.” | Nó nghĩa không có row tiếp theo |
| “getString có thể đọc mọi kiểu và tự chuyển thành text.” | Getter cần codec/type tương thích |
| “Cột index 0 là cột đầu tiên trong CREATE TABLE.” | Là cột đầu tiên của **projection kết quả** |
| “Thêm cột vào bảng không ảnh hưởng SELECT * mapper.” | Có thể đổi projection/chi phí dữ liệu; cần test |
| “isNull không cần vì getDouble trả 0 là đủ.” | 0 và null khác ý nghĩa nghiệp vụ |
| “all() vẫn tiết kiệm RAM vì pageSize=50.” | all() có thể thu thập toàn bộ trang còn lại |
| “getAvailableWithoutFetching() là COUNT của truy vấn.” | Chỉ số row đang sẵn mà không fetch thêm |
| “fullyFetched nghĩa đã xử lý toàn bộ Row.” | Chỉ nói trạng thái fetch, không phải xử lý |
| “LWT thành công khi one() == null.” | Dùng wasApplied() cho conditional statement |
| “Getter theo index luôn nhanh hơn nhiều nên nên ưu tiên.” | Lợi ích không mặc định; độ bền mapping quan trọng |
| “Prepared statement ngăn mọi lỗi Row mapping.” | Prepare không tự sửa getter sai type/alias |
| “Một SELECT LIMIT 1 không thấy row là chứng cứ replica mất dữ liệu.” | Phải kiểm tra điều kiện, consistency, TTL và thời điểm |
| “Java Driver 3 và 4 dùng cùng class/API.” | Package/semantics khác; cần migration theo phiên bản |

## 20. Tổng kết

Khi đọc dữ liệu Cassandra bằng Java Driver 4.x:

1. **`CqlSession.execute()` trả về `ResultSet`**, và bạn lấy từng **`Row`** bằng `one()` hoặc iterator.
2. **`one()` tiêu thụ row tiếp theo**; nếu hết kết quả sẽ trả `null`. Không nhầm Row không tồn tại với một cell null.
3. **Getter theo tên** dễ bảo trì và ít phụ thuộc thứ tự SELECT; vẫn phải khớp alias/projection.
4. **Getter theo index** bắt đầu từ 0 và theo **thứ tự cột trả về**, không theo thứ tự định nghĩa bảng; cần test khi query thay đổi.
5. **Kiểu getter phải khớp CQL type**: `timestamp → Instant`, `date → LocalDate`, `decimal → BigDecimal`, v.v.
6. **`isNull` quan trọng với primitive values**, vì thiếu dữ liệu không đồng nghĩa số 0 hoặc boolean false.
7. **`ColumnDefinitions`** giúp kiểm tra tên, index và type, đặc biệt khi schema/alias thay đổi.
8. **`ResultSet` có paging**, nên `all()` có thể kéo toàn bộ kết quả và tăng heap; phân biệt `LIMIT` với page size.
9. **LWT dùng `wasApplied()`** để đọc kết quả áp dụng conditional statement.
10. **Row API không thay data modeling hay consistency**: partition key, replication, compaction và CL vẫn quyết định chất lượng read path.

Câu hỏi khi code review không chỉ là “lấy được giá trị bằng getter nào?”, mà là **“Row này có chắc tồn tại, projection chứa đúng cột/alias, type và null semantics có đúng, và ứng dụng sẽ giữ bao nhiêu Row khi tải các trang tiếp theo?”**. Giải quyết tốt bốn điều đó giúp kết nối Java–Cassandra an toàn, dễ bảo trì và tránh lỗi hiệu năng phổ biến.
