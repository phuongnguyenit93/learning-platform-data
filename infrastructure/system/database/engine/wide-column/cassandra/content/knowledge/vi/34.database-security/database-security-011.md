# Ngăn chèn CQL bằng bind parameter và kiểm tra định danh động trong Apache Cassandra

## 1. Vấn đề bảo mật trong một hệ thống CQL phân tán

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Dữ liệu được phân vùng dựa trên **partition key**, các bảng được thiết kế theo những truy vấn quan trọng, và các thao tác CQL đi qua coordinator tới replica theo **consistency level**. Ứng dụng Java thường nhận tham số từ HTTP API, gRPC, message queue hoặc tác vụ nội bộ để tạo câu `SELECT`, `INSERT`, `UPDATE` và `DELETE`.

Rủi ro xuất hiện khi mã nguồn trộn lẫn hai loại thông tin:

1. **Cấu trúc truy vấn do ứng dụng kiểm soát**: tên keyspace, tên bảng, cột, điều kiện `WHERE`, `ORDER BY`, phép toán, loại statement.
2. **Giá trị dữ liệu từ bên ngoài**: UUID, ngày, timestamp, chuỗi, số, danh sách, giá trị cập nhật.

Nếu ghép chuỗi trực tiếp từ input vào CQL, người gọi có thể ảnh hưởng đến cú pháp của statement thay vì chỉ cung cấp giá trị. Đó là bản chất của **CQL injection**.

Biện pháp nền tảng:

- Dùng **prepared statement và bind parameter** (`?`) cho **giá trị dữ liệu**.
- Dùng **allowlist ánh xạ tới các câu CQL đã định nghĩa** cho **identifier hoặc phần cấu trúc cần chọn động**.
- Kiểm tra kiểu, kích thước, phạm vi, quyền truy cập và ranh giới tenant ở tầng ứng dụng.
- Cấu hình authentication, authorization, TLS và quyền tối thiểu ở tầng Cassandra.

Bài thuộc chương **Bảo mật** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, với phạm vi học CQL, replication, dữ liệu theo partition key, xử lý lỗi và Java Driver. Trọng tâm là ngăn input không đáng tin được hiểu thành **mã truy vấn**.

> Prepared statement bảo vệ **vị trí có thể bind giá trị**. Nó **không tự kiểm tra quyền người dùng**, không giới hạn chi phí của query và không tự động làm an toàn các đoạn CQL động đã được nối sẵn vào template trước khi prepare.

## 2. Một ví dụ sai: nối trực tiếp giá trị vào CQL

Giả sử API cung cấp các sự kiện gần đây của thiết bị, theo ngày. Bảng được thiết kế theo partition key:

~~~cql
-- Tên datacenter dc1 chỉ mang tính ví dụ.
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Một cách viết Java **không an toàn**:

~~~java
// KHÔNG DÙNG: chuỗi do client gửi đi thẳng vào cú pháp CQL.
String rawDevice = request.getParameter("deviceId");
String rawDay = request.getParameter("day");

String cql = "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = " + rawDevice +
    " AND event_day = '" + rawDay + "'" +
    " LIMIT 50";

session.execute(cql);
~~~

Vấn đề không phải chỉ là thiếu dấu nháy. Nếu caller điều khiển phần văn bản ở vị trí một giá trị CQL, câu lệnh được tạo ra có thể bị **thay đổi cấu trúc, thất bại khi parse, thực hiện sai phạm vi truy vấn hoặc bị lạm dụng**. CQL không có toàn bộ cú pháp SQL truyền thống; vì vậy **không mặc định một payload SQL injection phổ biến sẽ chạy được trên Cassandra**. Mức độ khai thác thực tế còn phụ thuộc vị trí nối chuỗi, parser, loại statement và phiên bản.

Việc “escape dấu nháy đơn thủ công” cũng không giải quyết đầy đủ:

- Mỗi kiểu CQL có cú pháp và quy tắc encode riêng.
- Có thể quên một chỗ nối ở code path khác.
- Dùng UUID, timestamp, collection hoặc blob làm chuỗi tăng lỗi format.
- Nối tên bảng hoặc tên cột không được bảo vệ bằng cách escape **giá trị**.
- Sửa dữ liệu đầu vào bằng regex thay vì bind có thể gây mất dữ liệu hợp lệ.

**Hướng đúng:** viết sẵn query shape, đưa giá trị qua **bind marker** và để driver encode theo kiểu CQL.

## 3. Prepared statement và bind parameter hoạt động như thế nào?

### 3.1. Phân tách cấu trúc và dữ liệu

CQL template:

~~~cql
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Ba dấu `?` đại diện cho **giá trị**: UUID, date và số nguyên giới hạn kết quả. Ứng dụng có thể gửi các giá trị khác nhau mà không tự xây dựng lại cú pháp query.

~~~mermaid
flowchart LR
    A["Template CQL cố định"] --> B["Prepare trên cluster"]
    C["Input từ HTTP / message"] --> D["Parse và validate kiểu dữ liệu"]
    D --> E["Bind values theo đúng vị trí và kiểu"]
    B --> F["BoundStatement"]
    E --> F
    F --> G["Driver gửi request CQL"]
    G --> H["Coordinator thực thi statement đã định hình"]
    I["Input muốn thay tên table, WHERE hoặc ORDER BY"] --> J["Allowlist / template selection"]
    J --> A
~~~

Ở mức khái niệm, **cú pháp câu truy vấn không được xây dựng bằng cách nối dữ liệu ngoài**. Prepared statement còn thường giúp tái sử dụng quá trình prepare và query metadata; nhưng mục tiêu bảo mật là **ranh giới giữa dữ liệu và cú pháp**.

### 3.2. Ví dụ Java Driver 4.x đầy đủ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class SafeEventRepository {
    private final CqlSession session;
    private final PreparedStatement readLatest;

    public SafeEventRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.readLatest = session.prepare(
            "SELECT event_time, metric_value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public List<Row> latest(UUID deviceId,
                            LocalDate day,
                            int requestedLimit) {
        Objects.requireNonNull(deviceId, "deviceId");
        Objects.requireNonNull(day, "day");

        // Đây là chính sách của API, không phải mặc định Cassandra.
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100");
        }

        BoundStatement statement = readLatest
            .bind(deviceId, day, requestedLimit)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(requestedLimit, 50));

        List<Row> rows = new ArrayList<>();
        ResultSet result = session.execute(statement);
        for (Row row : result) {
            rows.add(row);
        }
        return rows;
    }
}
~~~

Ví dụ giả định keyspace/table tồn tại và cluster có đủ replica trong datacenter cục bộ để đáp ứng `LOCAL_QUORUM`. `CqlSession` được khởi tạo với local DC/auth/TLS phù hợp ở nơi khác. Mã giới hạn kết quả ở **100 row** nên việc tạo danh sách ở đây có phạm vi rõ; với kết quả lớn, hãy xử lý theo trang để không gom toàn bộ vào RAM.

**Điểm bảo mật:**

- `UUID` và `LocalDate` được parse thành kiểu dữ liệu trước khi bind.
- `requestedLimit` được kiểm tra phạm vi, rồi bind như số nguyên.
- Query shape là hằng số, không có văn bản CQL do người dùng chọn.
- `PreparedStatement` được prepare **một lần trong vòng đời repository**, thay vì prepare một câu string mới trên mỗi request.
- `setPageSize` là tham số fetch/paging, **không thay thế `LIMIT`** hay chặn truy vấn không có partition key.
- `LOCAL_QUORUM` là quyết định về consistency; nó không bảo vệ khỏi injection thay cho bind.

### 3.3. Dùng bind parameter cho ghi

~~~java
PreparedStatement upsert = session.prepare(
    "INSERT INTO telemetry.events_by_device_day " +
    "(device_id, event_day, event_time, metric_value) " +
    "VALUES (?, ?, ?, ?)"
);

BoundStatement write = upsert.bind(
    deviceId,
    LocalDate.of(2026, 11, 21),
    java.time.Instant.parse("2026-11-21T08:30:00Z"),
    24.7
);
session.execute(write);
~~~

Các cột được xác định bởi code; bốn giá trị được encode bằng driver. Không cần tự chèn dấu nháy cho timestamp hoặc build một chuỗi JSON để biểu diễn mutation.

Với lệnh `UPDATE` và `DELETE`, nguyên tắc tương tự: **giữ `SET` và `WHERE` có cấu trúc được phê duyệt**, bind những giá trị có thể thay đổi. Nếu hệ thống cho phép cập nhật những **cột khác nhau**, dùng template được allowlist hoặc map field tới statement đã định nghĩa, không ghép raw tên cột.

## 4. Bind parameter áp dụng cho dữ liệu, không thay thế identifier

### 4.1. Phân loại phần nào có thể bind

| Thành phần CQL | Có nên dùng `?`? | Cách xử lý an toàn |
|---|---|---|
| UUID, số, chuỗi, timestamp trong `WHERE` | **Có** | Parse kiểu, validate và bind |
| Giá trị trong `INSERT ... VALUES` | **Có** | Prepared/bound statement |
| Giá trị trong `UPDATE ... SET` | **Có** | Bind theo kiểu cột |
| Giá trị số của `LIMIT` (nếu statement hỗ trợ) | **Có** | Kiểm tra giới hạn hợp lý, rồi bind |
| Giá trị của điều kiện `IF` được hỗ trợ | **Có** | Bind; xét riêng semantics LWT |
| **Tên keyspace** | **Không** | Allowlist/dữ liệu cấu hình tin cậy |
| **Tên table** | **Không** | Allowlist ánh xạ tới query template |
| **Tên column** | **Không** | Allowlist hoặc template tương ứng |
| **Tên clustering column trong `ORDER BY`** | **Không** | Cố định theo schema và query shape |
| **`ASC` hoặc `DESC`** | **Không** | Enum/allowlist chọn một statement |
| **Toán tử, `WHERE` fragment, `ALLOW FILTERING`** | **Không** | Chọn trong các query shape được phê duyệt |
| **`CREATE/ALTER/DROP/TRUNCATE` hoặc loại lệnh** | **Không** | Không nhận từ request thông thường; RBAC và luồng admin riêng |

Dấu `?` không phải phép biến bất cứ vị trí nào trong câu CQL thành tham số. Một marker cho **term/value** không thể thay cho token tên bảng, cột, từ khóa hay cả đoạn `WHERE`.

### 4.2. Định danh động (dynamic identifier) là gì?

Một số nhu cầu có thể hợp lệ:

- Chọn bảng active hoặc bảng archive đã được cấp phép.
- Chọn một tập báo cáo đã được thiết kế sẵn.
- Chọn thứ tự mới nhất/cũ nhất trên clustering column được hỗ trợ.
- Chọn keyspace tương ứng với tenant có mapping được kiểm soát.
- Chọn một trong vài loại mutation do API cho phép.

**Không đồng nghĩa** client có thể gửi raw table name hoặc CQL fragment tùy ý. Giới hạn đúng là **tập lựa chọn do server định nghĩa**.

~~~text
Dữ liệu bên ngoài:
    dataset = "archive"
    sort = "newest"

Server mapping:
    archive -> template A (table đã biết)
    newest  -> ORDER BY event_time DESC (được hỗ trợ)

Không bao giờ:
    "FROM " + request.tableName
    "ORDER BY " + request.sortExpression
~~~

### 4.3. Escape tên không thay thế authorization

Cassandra có quy tắc cho **unquoted identifiers** và **quoted identifiers**, gồm phân biệt chữ hoa/thường khi quoted. Thư viện có thể hỗ trợ biểu diễn/quote identifier đúng cách, nhưng **quote đúng không có nghĩa người gọi được quyền truy cập bảng đó**.

Ví dụ: ngay cả một tên table chỉ gồm `a-z0-9_` cũng có thể trỏ tới bảng chứa dữ liệu bí mật. Regex chặn ký tự đặc biệt **không chứng minh identifier đã được cho phép**.

Thứ tự tư duy đúng:

1. Xác minh người gọi có quyền chọn loại dữ liệu đó.
2. Ánh xạ **mã nghiệp vụ** tới một identifier/template đã được phê duyệt.
3. Nếu thật sự cần dựng identifier, sử dụng API xây dựng CQL hoặc quote có kiểm soát và xác minh cú pháp.
4. Dùng prepared/bound values cho mọi giá trị còn lại.
5. Dựa vào Cassandra RBAC như **lớp phòng thủ bổ sung**, không chỉ kiểm tra phía ứng dụng.

## 5. Cách tốt nhất: chọn một trong các truy vấn có cấu trúc cố định

### 5.1. Ánh xạ dữ liệu động sang enum

Giả sử lab hoặc production có hai keyspace đã được tạo, với **schema cùng kiểu** cho bảng `events_by_device_day`:

- `telemetry.events_by_device_day`.
- `telemetry_archive.events_by_device_day`.

Cả hai truy vấn đều phải có WHERE đầy đủ partition key. Java chỉ chấp nhận lựa chọn `live` hoặc `archive`.

~~~java
public enum Dataset {
    LIVE("telemetry.events_by_device_day"),
    ARCHIVE("telemetry_archive.events_by_device_day");

    private final String qualifiedTable;

    Dataset(String qualifiedTable) {
        this.qualifiedTable = qualifiedTable;
    }

    public String qualifiedTable() {
        return qualifiedTable;
    }

    public static Dataset fromApi(String input) {
        if ("live".equals(input)) {
            return LIVE;
        }
        if ("archive".equals(input)) {
            return ARCHIVE;
        }
        throw new IllegalArgumentException("Unsupported dataset");
    }
}
~~~

Ở đây **`qualifiedTable` là giá trị hard-coded trong code được review**, không phải chuỗi nhận từ HTTP request. Nếu caller gửi tên khác, hệ thống **từ chối**, không tìm cách sửa/escape đầu vào thành tên bảng hợp lệ.

### 5.2. Prepare một template cho từng lựa chọn hợp lệ

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.LocalDate;
import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;

public final class DatasetReader {
    private final CqlSession session;
    private final Map<Dataset, PreparedStatement> queries =
        new EnumMap<>(Dataset.class);

    public DatasetReader(CqlSession session) {
        this.session = session;

        for (Dataset dataset : Dataset.values()) {
            // An toàn: identifier được chọn từ enum nội bộ,
            // không lấy trực tiếp từ input người dùng.
            String cql =
                "SELECT event_time, metric_value FROM " +
                dataset.qualifiedTable() +
                " WHERE device_id = ? AND event_day = ? LIMIT ?";
            queries.put(dataset, session.prepare(cql));
        }
    }

    public ResultSet read(String datasetFromRequest,
                          UUID deviceId,
                          LocalDate day,
                          int limit) {
        Dataset dataset = Dataset.fromApi(datasetFromRequest);
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }
        BoundStatement bs = queries.get(dataset)
            .bind(deviceId, day, limit);
        return session.execute(bs);
    }
}
~~~

Cách này không tạo vô hạn prepared statement. **Số query shape bị chặn bởi enum**, có thể kiểm tra bằng code review và test.

Lưu ý: đặt `dataset` vào enum không tự kiểm tra người dùng có quyền xem archive. Nếu chỉ một số role được phép, phải xác thực/ủy quyền **trước khi chọn enum hoặc thực hiện query**.

### 5.3. Trường hợp bảng có schema khác nhau

Nếu `orders_by_customer` và `orders_by_id` có partition key khác nhau, đừng gộp chúng vào một template `WHERE id = ?` rồi tự đổi tên bảng. Mỗi access pattern cần **statement riêng phù hợp với primary key**.

Ví dụ hướng đúng:

~~~text
Operation GET_BY_ORDER_ID
    -> SELECT ... FROM commerce.orders_by_id WHERE order_id = ?

Operation GET_BY_CUSTOMER
    -> SELECT ... FROM commerce.orders_by_customer
       WHERE customer_id = ? ...

Caller chỉ chọn operation đã được server cho phép.
Mỗi operation có validation, quyền và giới hạn riêng.
~~~

Một allowlist giúp bảo mật **và** ngăn nhiều truy vấn sai schema làm cluster bị quét rộng.

## 6. Sắp xếp động: ORDER BY phải gắn với clustering key

### 6.1. Không nối nguyên chuỗi sort từ client

Đoạn mã **không an toàn**:

~~~java
String rawOrder = request.getParameter("orderBy");
String cql = "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY " + rawOrder;
~~~

Dù các giá trị trong `WHERE` được bind, phần `ORDER BY` vẫn có thể bị người gọi thay đổi. **Prepare một statement chứa raw fragment không làm fragment đó an toàn**.

### 6.2. Dùng hai template cố định

Trong bảng có clustering column `event_time`, nếu truy vấn theo đủ partition key, có thể hỗ trợ cả chiều sắp xếp phù hợp:

~~~cql
-- Lựa chọn mới nhất trước:
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT ?;

-- Lựa chọn cũ nhất trước:
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time ASC
LIMIT ?;
~~~

Java:

~~~java
String latestCql =
    "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY event_time DESC LIMIT ?";

String oldestCql =
    "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY event_time ASC LIMIT ?";

PreparedStatement newest = session.prepare(latestCql);
PreparedStatement oldest = session.prepare(oldestCql);

PreparedStatement selected;
switch (sortInput) {
    case "newest":
        selected = newest;
        break;
    case "oldest":
        selected = oldest;
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort");
}

BoundStatement bs = selected.bind(deviceId, day, 50);
~~~

Đây là ví dụ code trong một phương thức có `session`, `sortInput`, `deviceId`, `day` tương ứng. Production nên prepare một lần khi khởi tạo service và tái sử dụng.

**Đặc thù Cassandra:** `ORDER BY` không phải công cụ sắp xếp tùy ý trên mọi cột như ở nhiều RDBMS. Thứ tự được ràng buộc bởi clustering columns, partition restrictions và schema. Allowlist chỉ là một lớp; từng query shape vẫn phải hợp lệ và được benchmark.

## 7. Lọc động: danh sách trường không đồng nghĩa truy vấn tùy ý

Người dùng có thể muốn lọc theo `device_id`, ngày hoặc ngưỡng đo. Trong Cassandra, điều quan trọng hơn injection là **mô hình truy vấn có phục vụ access pattern đó không**.

### 7.1. Không tạo WHERE fragment từ API

~~~java
// KHÔNG DÙNG:
String rawFilter = request.getParameter("filter");
String cql = "SELECT * FROM telemetry.events_by_device_day " +
    "WHERE " + rawFilter;
~~~

Đoạn này trao quyền kiểm soát toàn bộ phần `WHERE` cho client; ngay cả nếu chỉ có các ký tự ASCII “an toàn”, caller vẫn có thể yêu cầu một query rất rộng, sai partition key hoặc tiêu tốn quá nhiều tài nguyên.

### 7.2. Định nghĩa API ở mức nghiệp vụ

| Operation được cho phép | Dạng WHERE được định nghĩa | Vì sao |
|---|---|---|
| `GET_LATEST_BY_DEVICE_DAY` | `device_id = ? AND event_day = ?` | Đầy đủ partition key |
| `GET_RANGE_BY_DEVICE_DAY` | `device_id = ? AND event_day = ? AND event_time >= ? AND event_time < ?` | Giới hạn clustering range |
| `GET_BY_METRIC_RANGE` | Không dùng template trên bảng này nếu thiếu access path | Có thể cần bảng khác/index/search được thiết kế |
| `SCAN_EVERYTHING` | Không mở dưới HTTP API công khai | Tránh scan toàn cluster |

Dấu `?` cho biết giá trị có thể bind, còn **dạng truy vấn được kiểm soát bởi code và schema**.

### 7.3. Đừng để “ALLOW FILTERING” trở thành lựa chọn tùy ý

Kể cả query không bị injection ở mức ký tự, một API cho phép chọn `ALLOW FILTERING` vẫn có thể đẩy Cassandra quét nhiều partition. Cần đặt tiêu chuẩn hiệu năng, kiểm soát access pattern, hạn chế số row và concurrency ở tầng application.

`LIMIT 50` chỉ giới hạn số row được trả về; nếu filter phải đi qua nhiều SSTable/tombstone/partition mới tìm đủ 50 row, workload vẫn có thể tốn tài nguyên. **An toàn truy vấn** gồm cả tránh lạm dụng tài nguyên, không chỉ tránh parser bị điều khiển.

## 8. Multi-tenant: bind tenant_id từ danh tính đã xác thực

### 8.1. Nguy cơ đọc chéo tenant

Giả sử ứng dụng cung cấp dữ liệu cho nhiều tổ chức. Nếu client gửi `tenantId` trên query string và backend dùng giá trị đó một cách vô điều kiện, một người dùng có thể yêu cầu dữ liệu của tenant khác **dù query đã dùng prepared statement**.

Đây là **lỗi authorization**, không phải lỗi injection. Bind ngăn văn bản làm biến đổi cú pháp CQL, nhưng không xác minh caller có quyền với partition đang truy vấn.

### 8.2. Mô hình khóa phân vùng có tenant

~~~cql
CREATE TABLE telemetry.events_by_tenant_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Truy vấn:

~~~cql
SELECT event_time, metric_value
FROM telemetry.events_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Quan trọng: `tenant_id` phải được lấy từ **authenticated principal/authorization context** mà server đã xác minh; nếu request có trường tenant thì phải kiểm tra quyền tương ứng, không tự tin rằng client sẽ truyền đúng.

Một quy trình hợp lý:

~~~mermaid
flowchart TD
    A["HTTP request + access token"] --> B["Xác thực token"]
    B --> C["Xác định tenant/role hợp lệ"]
    C --> D["Kiểm tra quyền với device/data"]
    D --> E["Chọn template cố định"]
    E --> F["Bind tenant_id được xác thực + device_id + day + limit"]
    F --> G["Cassandra RBAC và truy vấn"]
    H["tenantId tự nhận từ request"] -. "Không tin vô điều kiện" .-> D
~~~

**Cassandra GRANT ở mức keyspace/table không thay cho kiểm tra quyền từng row của ứng dụng.** Nếu nhiều tenant cùng nằm trong một bảng, ứng dụng phải thực hiện kiểm soát truy cập phù hợp tại ranh giới API và truy vấn.

### 8.3. Khi mỗi tenant dùng keyspace riêng

Nếu kiến trúc chọn một keyspace cho mỗi tenant:

- Dùng **mapping do backend quản lý**, ví dụ tenant UUID đã xác thực → keyspace đã đăng ký.
- Không sinh keyspace name trực tiếp từ slug do client gửi.
- Xem xét số lượng schema/keyspace, prepared statements và chi phí vận hành khi số tenant rất lớn.
- Tạo role và GRANT tối thiểu theo phạm vi cần thiết; lưu ý connection pool/role là thiết kế riêng cho ứng dụng.
- Thận trọng với automation cấp quyền và cleanup khi tenant bị xóa.

Regex chặn dấu chấm/nháy không thay mapping quyền. **Một tên hợp cú pháp vẫn có thể là tài nguyên không được phép**.

## 9. Xác thực giá trị và giới hạn tài nguyên trước khi bind

Prepared statement xử lý **encode dữ liệu**, không thay business validation. Các ràng buộc quan trọng:

| Dữ liệu đầu vào | Cần xác thực | Hậu quả nếu bỏ qua |
|---|---|---|
| UUID của device | Parse UUID hợp lệ; quyền xem device | Exception, đọc nhầm dữ liệu |
| Ngày | Định dạng rõ và phạm vi ngày được phép | Scan nhiều partition qua các request |
| Time range | `start <= end` và giới hạn số ngày/giờ | Query quá rộng hoặc nhiều request fan-out |
| `LIMIT` | Số nguyên dương, cận trên theo API | Trả nhiều row, tốn RAM/network |
| Page size | Giới hạn bytes/row count theo workload | Nhiều allocations hoặc round-trip quá nhiều |
| String/collection/blob | Độ dài, số phần tử, kiểu và quota | Mutation quá lớn, disk/GC/compaction pressure |
| Timestamp/TTL | Phạm vi hợp lệ và chính sách nghiệp vụ | Dữ liệu hết hạn bất ngờ hoặc độ lệch timestamp |
| Dynamic operation | Enum/allowlist và role cho phép | Truy cập bảng/loại thao tác ngoài mục đích |
| Request rate | Quota/rate limit theo caller/tenant | Lạm dụng query dù đã bind đúng |

Chẳng hạn query có đầy đủ partition key vẫn có thể chậm nếu một partition rất rộng hoặc nhiều tombstone. **Bind đúng là điều kiện cần của security; thiết kế bảng, giới hạn concurrency và giám sát p99 giúp giảm nguy cơ denial of service ở lớp dữ liệu.**

### 9.1. Validation khác encoding

- **Validation** trả lời: “giá trị có hợp lệ theo nghiệp vụ không?”.
- **Authorization** trả lời: “người gọi có quyền thao tác với dữ liệu/tài nguyên không?”.
- **Binding** trả lời: “giá trị sẽ được gửi như dữ liệu, không bị hiểu thành cú pháp CQL chứ?”.
- **Query planning/data modeling** trả lời: “truy vấn có thể được Cassandra phục vụ hiệu quả và an toàn tài nguyên không?”.

Cả bốn lớp đều cần; không lớp nào thay được tất cả lớp khác.

## 10. Quyền tối thiểu trong Cassandra: lớp phòng thủ bổ sung

Giả sử role `telemetry_reader` đã được đội vận hành tạo theo chính sách nội bộ. Chỉ cấp quyền đọc bảng được phép:

~~~cql
-- Chạy bởi người quản trị có quyền cấp quyền, không phải API công khai.
GRANT SELECT ON TABLE telemetry.events_by_device_day
TO telemetry_reader;
~~~

Cần kiểm tra chính xác cú pháp/quyền và cài đặt authentication/authorizer của phiên bản Cassandra. Trong hệ thống thật, không tạo role với mật khẩu hard-code trong bài học hoặc commit secrets vào Git.

Các nguyên tắc:

1. **Tách application role** của read API với migration/admin account.
2. **Không cấp `ALL PERMISSIONS` trên tất cả keyspaces** cho web service.
3. Chỉ cấp `SELECT`, `MODIFY` hay quyền quản trị theo đúng nhiệm vụ.
4. Theo dõi schema migration và việc role có được mở rộng ngoài ý muốn không.
5. Dùng TLS cho client-to-node, mạng riêng cho internode và bảo vệ secrets.
6. Phân biệt **lỗi authorization** với syntax error, timeout và unavailable.
7. Audit các thao tác nhạy cảm theo khả năng của phiên bản; không log thông tin bind nhạy cảm vô hạn.

Nếu một lỗi nối raw CQL làm ứng dụng cố thực hiện thao tác ngoài chức năng, **role quyền tối thiểu** có thể giới hạn tác hại. Nhưng một role SELECT rộng vẫn có thể đọc dữ liệu trái phép; authorization ở API không thể bỏ qua.

## 11. Logging an toàn: ghi query ID, không ghi raw bind values

### 11.1. Slow request log không nên tự tạo rủi ro mới

Log là nguồn phổ biến khiến dữ liệu nhạy cảm bị sao chép ra ngoài database. Một slow-query event nên ghi các trường có cardinality thấp:

~~~text
event=cassandra_request
query_id=read_events_by_device_day
duration_ms=184
outcome=success
consistency=LOCAL_QUORUM
page_size=50
dc=dc1
rows_returned=50
~~~

Đây là **schema log minh họa do ứng dụng phát ra**, không phải định dạng log mặc định của Cassandra. Những thông tin nên tránh trong log thông thường:

- `tenant_id`, `device_id`, email, access token hoặc full raw CQL có bind values.
- Mật khẩu, secret, key material và payload dữ liệu.
- Request URI nguyên vẹn nếu chứa ID nhạy cảm.
- Exception message thiếu kiểm soát có thể chứa tham số truy vấn.

Nếu cần điều tra một partition cụ thể, dùng trace/log được kiểm soát truy cập và có chính sách retention/sampling. **Không gắn user ID hoặc partition key vào nhãn Prometheus** vì vừa làm nổ cardinality vừa tăng phạm vi rò rỉ.

### 11.2. Không prepare mỗi request với literal values

Mã kiểu này vừa phá ý nghĩa bind vừa có thể tăng số lượng query shape:

~~~java
// Sai: literal được nội suy vào statement trước khi prepare.
String cql = "SELECT ... WHERE device_id = " + rawValue;
PreparedStatement ps = session.prepare(cql);
~~~

`prepare()` **không làm sạch câu CQL đã bị nội suy**. Prepared statement chỉ phát huy tác dụng khi query text chứa markers và mọi giá trị động được chuyển qua `bind()`.

Ngoài bảo mật, prepare hàng nghìn statement khác nhau có thể gây tốn cache/memory và tăng traffic prepare. Nên giữ một tập hữu hạn query template.

## 12. Kiểm thử để chứng minh input không điều khiển query shape

### 12.1. Kiểm thử lựa chọn dataset

Đoạn JUnit 5 minh họa test enum allowlist (không cần mở kết nối Cassandra):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class DatasetTest {
    @Test
    void acceptsOnlyKnownPublicValues() {
        assertEquals(Dataset.LIVE, Dataset.fromApi("live"));
        assertEquals(Dataset.ARCHIVE, Dataset.fromApi("archive"));
    }

    @Test
    void rejectsUnknownOrCqlLikeInputs() {
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("system"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("archive; DROP TABLE something"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("ARCHIVE"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi(""));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi(null));
    }
}
~~~

Test cho thấy **input không thể chọn tài nguyên ngoài tập mapping**. Không cần thử xem một chuỗi mang dấu chấm phẩy có khiến Cassandra thực thi nhiều lệnh hay không; chỉ cần chứng minh nó bị từ chối trước khi ghép statement.

### 12.2. Test bind và giới hạn

Với repository và API, cần các kiểm thử:

- UUID không hợp lệ bị từ chối khi parse, **trước** khi thực hiện CQL.
- `limit = 0`, `limit = 101` (theo cận ví dụ) bị từ chối.
- Các chuỗi có dấu nháy, dấu chấm phẩy, comment marker hoặc Unicode trong **trường dữ liệu kiểu text** vẫn được lưu/truy vấn như **giá trị nguyên vẹn** khi bind; không biến thành cú pháp.
- Tên table/keyspace/column ngoài allowlist không được đưa vào query.
- Quyền tenant kiểm tra trên **principal đã xác thực**, không chỉ trường `tenantId` trong body.
- Request bất thường không làm logger lộ raw value.
- Query lớn/scan rộng bị chặn bởi API policy và query shape.

### 12.3. Kiểm thử tích hợp trên môi trường cô lập

Một bài test với Cassandra lab có thể:

1. Tạo keyspace/bảng theo schema test.
2. Chèn một row với giá trị text chứa ký tự đặc biệt qua `bind`.
3. Đọc lại bằng prepared SELECT, xác minh byte/string bằng nhau.
4. Gửi request với lựa chọn dataset ngoài allowlist và xác minh **không có CQL gửi đi**.
5. Gửi request từ principal tenant A nhưng đòi đọc tenant B, xác minh `403 Forbidden` hoặc kết quả từ chối tương đương do API.
6. Xác minh telemetry/log không chứa dữ liệu nhạy cảm.
7. Theo dõi p95/p99 và timeout để phát hiện query shape gây quá tải.

Không chạy test phá hoại hoặc tạo lệnh `DROP` vào production. Tách database integration test khỏi cluster có dữ liệu thật và dùng role ít quyền.

## 13. CQL injection có giống SQL injection trong RDBMS không?

**Nguyên lý gốc giống nhau:** dữ liệu không đáng tin không được biến thành cú pháp câu truy vấn. Tuy nhiên Apache Cassandra có **ngữ pháp và mô hình truy cập khác**:

- Không mặc định hỗ trợ các cú pháp SQL như `JOIN`, `UNION SELECT`, `OFFSET` hoặc một số dạng `OR` phổ biến; khả năng khác theo CQL/phiên bản.
- `WHERE` chủ yếu được thiết kế để xác định partition/clustering hoặc sử dụng các tính năng truy vấn phù hợp, không phải bộ lọc tùy ý trên mọi cột.
- Một payload muốn thêm nhiều statement có thể bị driver/server từ chối thay vì được thực thi. **Không nên khẳng định mọi chuỗi có dấu chấm phẩy đều chạy được như nhiều lệnh.**
- Dù parser từ chối một payload, **việc ghép input vào query text vẫn là anti-pattern** và có thể trở thành lỗ hổng khi code thay đổi.
- Truy vấn có cú pháp hợp lệ vẫn có thể gây **resource exhaustion** nếu ứng dụng cho phép scan rộng hoặc request rate không được hạn chế.

Vì vậy không chép máy móc “payload mẫu SQL” để đánh giá bảo mật Cassandra. Hãy kiểm tra **ranh giới dữ liệu/cú pháp, tập query template, quyền hạn và giới hạn tài nguyên**.

## 14. Các mẫu anti-pattern cần phát hiện khi review

| Anti-pattern | Nguy cơ | Giải pháp |
|---|---|---|
| `"WHERE name = '" + userInput + "'"` | Giá trị điều khiển query text | Prepared/bind text |
| `"WHERE id = " + rawUuid` | Raw UUID chưa parse/encode | Parse UUID và bind |
| `"FROM " + request.table` | Caller điều khiển identifier | Ánh xạ enum → table/template |
| `"SELECT " + request.columns` | Caller điều khiển projection | Allowlist các dạng projection |
| `"ORDER BY " + request.order` | Caller điều khiển clause | Enum sort → query cố định |
| `"WHERE " + filterExpression` | Caller điều khiển toàn bộ WHERE | Chọn operation/template theo access pattern |
| `"LIMIT " + rawLimit` | Câu query chứa dữ liệu chưa validate | Kiểm tra số và bind |
| `session.prepare("..." + rawInput)` | Prepare query đã nối input | Template cố định rồi bind |
| Chỉ regex `[a-z0-9_]+` cho table | Tên có cú pháp hợp lệ vẫn có thể trái quyền | Allowlist theo tài nguyên và principal |
| Request body cung cấp `tenant_id` và server tin luôn | Cross-tenant access dù đã bind | Tenant từ authenticated context |
| Dùng role có quyền schema admin trong API | Rủi ro thao tác ngoài ý muốn rất lớn | Least-privilege roles |
| Ghi raw bound values vào log | Rò rỉ PII/secrets | Query ID, redaction, TTL log |
| Không giới hạn `LIMIT` và concurrency | RAM, I/O, query DoS | Validation, rate limit, backpressure |

### 14.1. Regex hợp lệ là lớp phụ, không phải hợp đồng bảo mật

Nếu thật sự có nhiều identifier được tạo theo tên vật lý do hệ thống cấp phát, có thể thêm validation cú pháp như `^[a-z][a-z0-9_]{0,47}$`. Nhưng giới hạn này chỉ là **quy ước riêng của ứng dụng**, không phản ánh toàn bộ ngữ pháp tên Cassandra và không thay:

- Mapping tenant → keyspace được phê duyệt.
- Danh sách bảng/cột có quyền truy cập.
- Schema compatibility của truy vấn.
- Authorization theo role hoặc principal.

Với ít lựa chọn, **enum/template cố định dễ kiểm toán hơn regex + string concatenation**.

## 15. Runbook: nghi ngờ client điều khiển identifier hoặc query fragment

**Tình huống:** Log cho thấy một số request dùng `dataset` lạ, truy vấn lỗi syntax tăng và query throughput bất thường. Đội vận hành nghi ngờ API đang nối raw table name hoặc WHERE fragment.

### Bước 1 — Xác định phạm vi

Thu thập đường API, commit/deploy liên quan, query ID, role dùng kết nối Cassandra, thời điểm UTC, tỷ lệ syntax/error/timeout, keyspace/table bị ảnh hưởng. **Không đưa raw token hoặc thông tin nhạy cảm vào ticket/log công khai**.

### Bước 2 — Kiểm tra code path

Tìm các đoạn xây dựng query text bằng input không đáng tin:

~~~text
"FROM " + ...
"WHERE " + ...
"ORDER BY " + ...
"LIMIT " + ...
session.prepare(dynamicCql)
session.execute(dynamicCql)
~~~

Đây là **mẫu review** chứ không phải quy tắc tất cả phép nối đều sai. Nối các **hằng số được allowlist** có thể hợp lệ; nối input từ request thì không.

### Bước 3 — Hạn chế tác động ngay

Tùy mức độ sự cố, có thể tạm vô hiệu hóa endpoint, chỉ cho phép known operation, giảm rate limit, thu hẹp role permissions hoặc rollback deployment theo quy trình incident. Không thử payload lạ trực tiếp trên dữ liệu thật để “xem có DROP được không”.

### Bước 4 — Chuyển sang template cố định + bind

- Thiết kế query shape dựa trên schema/partition key.
- Chuyển giá trị sang prepared/bound statement.
- Chuyển lựa chọn table/column/sort sang enum/allowlist.
- Ràng buộc tenant theo authenticated principal.
- Thêm validation limit/range và backpressure.

### Bước 5 — Kiểm thử và quan sát

Chạy unit/integration tests trên môi trường cô lập; thử input có ký tự đặc biệt, lựa chọn không được phép và các giới hạn cực trị. Xác minh lỗi syntax giảm, log không lộ dữ liệu, các query hợp lệ vẫn đúng, p99 và timeout không xấu đi.

### Bước 6 — Điều tra hậu sự cố

Kiểm tra audit/driver/server logs theo khả năng phiên bản, xác minh quyền của tài khoản Cassandra, rà soát thao tác schema/data bất thường và rotation credentials nếu có chỉ dấu lộ bí mật. **Không suy luận có khai thác thành công chỉ từ một chuỗi mang hình thức injection**; cần bằng chứng có thể kiểm tra.

## 16. Bài tập tự kiểm tra

### Câu 1 — Bind parameter có thay được tên bảng?

Ứng dụng muốn dùng `FROM ?` và bind tên bảng do caller gửi. Cách này có đúng không?

**Đáp án:** Không. Bind marker dành cho vị trí giá trị được hỗ trợ; tên bảng là identifier/cấu trúc. Dùng allowlist ánh xạ tới table/query template đã được phê duyệt.

### Câu 2 — Prepare có làm sạch raw string?

Code nối `rawName` vào `WHERE name = '...'` rồi gọi `session.prepare(cql)`. Có được bảo vệ khỏi injection không?

**Đáp án:** Không. Câu CQL đã bị xây dựng bằng input không đáng tin trước khi prepare. Cần để marker `?` trong template và bind giá trị riêng.

### Câu 3 — Regex kiểm tra tên table

Tên `financial_reports` khớp regex `[a-z_]+`. Có đủ để caller được quyền SELECT bảng đó không?

**Đáp án:** Không. Regex chỉ xác thực định dạng, không xác thực quyền hay tính hợp lệ của access pattern. Cần allowlist và authorization.

### Câu 4 — Multi-tenant

Request từ tenant A đặt `tenantId=B`, nhưng cả hai đều là UUID hợp lệ và đã bind. Có an toàn không?

**Đáp án:** Không. Bind chống injection, không ngăn truy cập chéo tenant. Backend phải lấy tenant từ principal đã xác thực hoặc kiểm tra quyền phù hợp.

### Câu 5 — Sort động

Client chọn “oldest” hoặc “newest”. Có nên ghép raw `orderBy` vào CQL không?

**Đáp án:** Không. Dùng enum để chọn giữa hai prepared statement chứa `ORDER BY event_time ASC` hoặc `DESC` hợp lệ; cột phải phù hợp với clustering schema.

### Câu 6 — LIMIT

Input limit được bind nhưng có giá trị 10.000.000. Query có chắc an toàn hiệu năng không?

**Đáp án:** Không. Bind ngăn thay đổi cú pháp nhưng không giới hạn tải. Cần đặt upper bound theo API, page size, query shape và rate limit.

### Câu 7 — SQL payload điển hình

Một chuỗi tấn công SQL có `UNION SELECT` bị Cassandra báo syntax error. Có thể kết luận code ghép raw CQL an toàn không?

**Đáp án:** Không. CQL khác SQL về ngữ pháp; một payload bị từ chối không chứng minh mọi dạng input an toàn. Phải kiểm tra cấu trúc query, binding và allowlist.

### Câu 8 — Role có quyền quá rộng

API chỉ đọc sự kiện nhưng kết nối Cassandra bằng role có quyền thay schema trên toàn cluster. Bind parameter có đủ để giảm rủi ro không?

**Đáp án:** Không. Phải dùng least-privilege authorization, tách account read API khỏi migration/admin.

### Câu 9 — Lưu dữ liệu text có dấu nháy

Một giá trị text hợp lệ chứa ký tự `'`, dấu chấm phẩy và xuống dòng. Có cần xóa hết những ký tự đó trước khi lưu không?

**Đáp án:** Không, nếu dữ liệu được phép theo nghiệp vụ. Dùng bind parameter để driver encode nguyên vẹn giá trị; validation chỉ giới hạn định dạng/kích thước thực sự cần thiết.

### Câu 10 — Truy vấn thiếu partition key

API dùng prepared statement an toàn nhưng có `ALLOW FILTERING`, query chạy rộng và nhiều người gọi cùng lúc. Đây có phải vấn đề cần xử lý không?

**Đáp án:** Có. Không phải injection theo nghĩa truyền thống nhưng có rủi ro tài nguyên/DoS. Cần thiết kế access pattern phù hợp, giới hạn concurrency và kiểm tra schema/index.

### Câu 11 — Dynamic column updates

Một API nhận JSON map có thể cập nhật mọi column của table. Dùng bind cho các giá trị có đủ an toàn không?

**Đáp án:** Không. Tên cột và những trường được phép chỉnh phải được allowlist theo role, mapping vào template `UPDATE` cụ thể; đồng thời validate kiểu dữ liệu, TTL và các quy tắc nghiệp vụ.

### Câu 12 — Log có đầy đủ query text

Đội phát triển log mọi CQL sau khi nội suy kèm giá trị customer ID và token. Đây có phải lựa chọn tốt cho tracing lỗi không?

**Đáp án:** Không. Có rủi ro lộ thông tin nhạy cảm. Nên log query ID, outcome, latency, DC/CL và thông tin đã làm sạch; chỉ dùng trace có kiểm soát khi cần.

## 17. Checklist review trước khi đưa một API Cassandra vào production

~~~text
[ ] Không có raw request data được nối trực tiếp vào CQL syntax.
[ ] SELECT/INSERT/UPDATE/DELETE dùng prepared/bound values hợp lệ.
[ ] Keyspace, table, column, ORDER BY, operator và WHERE shape là cố định
    hoặc được ánh xạ từ allowlist/enum server-side.
[ ] Không có client-defined ALLOW FILTERING hoặc arbitrary CQL fragment.
[ ] Các query shape phù hợp partition key/clustering schema và đã benchmark.
[ ] UUID, date, numeric range, LIMIT/page size và payload size được validate.
[ ] Tenant ID được suy ra từ principal đã xác thực hoặc kiểm quyền rõ ràng.
[ ] Cassandra role chỉ có quyền tối thiểu cần cho API.
[ ] Authentication, TLS, secrets và access controls được cấu hình theo policy.
[ ] Không log raw bind values/PII; metrics tags có cardinality hữu hạn.
[ ] Prepared statements tái sử dụng từ tập template hữu hạn.
[ ] Negative tests từ chối identifier/operation ngoài allowlist.
[ ] Integration tests chạy trên môi trường cô lập, không dùng production.
[ ] Rate limits, concurrency và timeouts phù hợp tránh resource exhaustion.
[ ] Timeout/retry có chính sách riêng và không gây side effect trùng.
[ ] Audit và incident runbook đủ để phát hiện truy vấn trái quyền.
~~~

Checklist này không chứng minh toàn bộ ứng dụng an toàn; nó là bộ tiêu chí cụ thể cho **ranh giới tạo CQL** và quyền truy cập dữ liệu. Các yêu cầu bảo mật khác như secret rotation, network segmentation, encryption at rest, backup protection và software patching cần được quản lý theo tiêu chuẩn hệ thống.

## 18. Tổng kết

**CQL injection được ngăn trước tiên bằng cách không biến input không đáng tin thành cú pháp truy vấn.** Trong Cassandra và Java Driver:

1. **Giữ query structure cố định; bind mọi giá trị có thể thay đổi** qua prepared/bound statement.
2. **Bind marker không thay được identifier** như keyspace/table/column, `ORDER BY`, toán tử hoặc fragment `WHERE`.
3. **Dynamic identifiers phải được allowlist**, tốt nhất ánh xạ mã nghiệp vụ hoặc enum tới một tập template hữu hạn.
4. **Regex/quoting không phải authorization**: tên hợp cú pháp vẫn có thể trỏ tới dữ liệu ngoài phạm vi cho phép.
5. **Tenant isolation phải kiểm tra danh tính người gọi**, không tin tenant ID nhận trực tiếp từ request dù đã bind.
6. **Prepared statement không thay validation**: giới hạn `LIMIT`, row size, range, concurrency, TTL và truy vấn đúng partition key.
7. **Least-privilege RBAC, TLS và logging an toàn** giảm tác hại khi có lỗi ở ứng dụng.
8. **Kiểm thử negative cases** trước khi deploy và chỉ điều tra input nghi vấn trên môi trường được cấp phép, cô lập.

Khi review code, hãy hỏi: **“Phần nào của câu CQL do chính ứng dụng định nghĩa, phần nào là dữ liệu được bind, và ai có quyền chọn giữa các query shape đã cho phép?”**. Nếu ba ranh giới ấy được thể hiện rõ trong code, khả năng chèn CQL và đọc nhầm dữ liệu giữa các tenant sẽ giảm đáng kể, đồng thời hệ thống Cassandra dễ tối ưu và kiểm toán hơn.
