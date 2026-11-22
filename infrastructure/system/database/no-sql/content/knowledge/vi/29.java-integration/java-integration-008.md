# API truy vấn an toàn, prepared/bound statement hoặc cơ chế tương ứng

Một ứng dụng Java kết nối NoSQL thường phải nhận dữ liệu từ HTTP request rồi đưa vào truy vấn: `tenantId`, `orderId`, khoảng thời gian, trạng thái, từ khóa tìm kiếm, số bản ghi mỗi trang. Nếu ghép trực tiếp những giá trị này vào **chuỗi ngôn ngữ truy vấn**, một giá trị do người dùng nhập có thể bị hiểu thành **cú pháp**, **toán tử** hoặc **một phần của cấu trúc truy vấn**. Đây là một dạng *injection*, không chỉ xuất hiện trong SQL.

Trong Cassandra, có thể dùng **CQL prepared statement và bound statement**. Trong MongoDB, thường dùng **BSON filter/aggregation builders có kiểu dữ liệu**. Trong DynamoDB, dùng **expression attribute names/values**. Với Redis, chọn **API lệnh có tham số** và xây khóa có phạm vi rõ ràng. Với Neo4j/Cypher hoặc Couchbase SQL++, dùng **parameter binding** của driver. Các API khác nhau, nhưng cùng theo một nguyên tắc:

> **Cấu trúc truy vấn do chương trình quyết định; dữ liệu không đáng tin chỉ được đi vào những vị trí giá trị đã được định nghĩa rõ.**

Tuy nhiên, prepared/bound statement **không tự giải quyết** phân quyền, lộ dữ liệu giữa tenants, truy vấn quá nặng, khóa định tuyến sai, consistency, timeout, retry sau kết quả ghi không rõ hoặc việc cho người dùng chọn tên bảng/toán tử tùy ý.

Bài học thuộc chương **Kết nối Java**, module **Database No SQL**. Ta sẽ đi từ mô hình nguy cơ, cách viết Java an toàn với nhiều NoSQL, đến bài toán tìm kiếm động, phân trang, giới hạn tải, kiểm thử và các lựa chọn thiết kế production.

---

## 1. Một endpoint thực tế cần bảo vệ những gì?

Giả sử dịch vụ đơn hàng có API:

```http
GET /api/orders?customerId=c42&status=PAID&limit=20
Authorization: Bearer ...
```

Tác vụ đúng cần:

1. Xác thực người gọi và suy ra `tenantId` **từ ngữ cảnh đã xác thực**.
2. Kiểm tra `customerId`, `status` và `limit` theo kiểu dữ liệu, độ dài, miền giá trị.
3. Xây truy vấn với các trường và toán tử **đã được chọn sẵn**.
4. Đưa giá trị của request vào vị trí **được bind/encode thành giá trị**.
5. Luôn giới hạn truy vấn trong tenant/owner được phép xem.
6. Dùng index hoặc partition key để tránh scan toàn hệ.
7. Giới hạn số kết quả, deadline và tài nguyên truy vấn.
8. Trả đúng bản ghi và chỉ những trường được phép công bố.
9. Ghi metric và xử lý lỗi nhưng không làm lộ dữ liệu nhạy cảm.

Mục đích bảo mật bao gồm cả **tính bí mật, tính toàn vẹn và khả năng phục vụ**. Chặn injection chỉ bảo vệ một phần bề mặt tấn công.

### 1.1. Đừng trộn “người gửi dữ liệu” với “người có thẩm quyền”

Client có thể gửi:

```json
{
  "tenantId": "tenant-vip",
  "customerId": "c42"
}
```

Nhưng `tenantId` trong body **không chứng minh** người gọi thuộc tenant đó. Một truy vấn được bind hoàn hảo vẫn có thể đọc chéo tenant nếu ứng dụng tin trường client.

---

## 2. “Prepared statement” không có nghĩa giống nhau ở mọi NoSQL

| Hệ hoặc giao diện | Cơ chế điển hình trong Java | Điểm chính |
| --- | --- | --- |
| Cassandra CQL | `CqlSession.prepare(...)` → `PreparedStatement.bind(...)` | Cấu trúc CQL được chuẩn bị; giá trị đi qua bind markers |
| MongoDB | `Filters.eq/and/gte`, `Aggregates.match`, BSON typed API | Xây cấu trúc BSON cố định, đưa input vào vị trí giá trị |
| Spring Data MongoDB | `Query`, `Criteria`, query methods | Framework dựng BSON; vẫn cần kiểm soát field, operator và tenant |
| DynamoDB AWS SDK | `KeyConditionExpression` + `ExpressionAttributeValues/Names` | Placeholders cho giá trị và tên thuộc tính trong expression |
| Neo4j Cypher | `session.run(query, parameters)` | Tham số riêng thay vì ghép literal vào Cypher |
| Couchbase SQL++ | SDK named/positional parameters | Query SQL++ có placeholder cho giá trị |
| Redis | `GET/SET/HGET` qua API tham số; scripts với KEYS/ARGV | Không có SQL query để prepare cho lệnh cơ bản; giữ lệnh và keyspace theo code |
| Elasticsearch/OpenSearch | Typed query DSL/builder của client | Cấu trúc query do code tạo, input là giá trị; DSL nguy hiểm nếu nhận tùy ý |
| JDBC SQL (đối chiếu) | `Connection.prepareStatement()` + setters | Cùng tư tưởng bind giá trị, nhưng **không phải API dùng cho mọi NoSQL** |

**Đừng cố tìm một method tên `prepareStatement()` trên mọi driver.** Hãy hỏi API nào bảo đảm input là giá trị, không bị diễn giải thành một operator hoặc đoạn cú pháp mới.

### 2.1. Cấu trúc khác với giá trị

Một truy vấn có ba phần:

- **Cấu trúc cố định:** nguồn dữ liệu, field, toán tử, thứ tự phép lọc.
- **Các giá trị thay đổi:** `tenantId`, ID, ngày, status.
- **Lựa chọn cấu trúc có kiểm soát:** sort field, loại filter, collection được phép.

Nhóm thứ hai nên bind. Nhóm thứ ba thường **không bind được như giá trị** và cần allowlist/enum hoặc các query templates cố định.

---

## 3. NoSQL injection xảy ra như thế nào?

Injection xảy ra khi input của người gọi bị chuyển thành **cú pháp có quyền điều khiển truy vấn** thay vì chỉ là dữ liệu.

Ví dụ ghép CQL:

```java
String cql =
    "SELECT * FROM commerce.orders WHERE tenant_id = '" +
    tenantId +
    "' AND order_id = " +
    orderId;
```

Nếu `tenantId` chứa dấu nháy hoặc cú pháp đặc biệt, cấu trúc CQL có thể bị thay đổi hoặc gây lỗi. Không nên ghép chuỗi như trên, kể cả khi API đã kiểm tra người dùng đăng nhập.

Với document NoSQL, nguy cơ cũng có thể đến từ **đối tượng JSON do client cung cấp**:

```json
{
  "username": {
    "$ne": null
  }
}
```

Nếu API chủ định yêu cầu `username` là chuỗi, nhưng server lại nhận object trên và đưa thẳng vào một filter như **cấu trúc truy vấn**, `$ne` có thể trở thành toán tử “khác”. Những hậu quả thực tế phụ thuộc cách server biến JSON thành BSON và cách driver được gọi; không phải cứ thấy chuỗi `$ne` trong một giá trị string là tự có injection.

### 3.1. Bốn dạng nguy cơ

1. **Ghép literal vào query text:** CQL, Cypher, SQL++ hoặc một JSON query được ghép chuỗi.
2. **Nhận toàn bộ query object từ client:** client kiểm soát `$or`, `$ne`, `$regex`, pipeline stages, scripts…
3. **Cho client quyết định identifier hoặc operator:** tên collection, tên field, hướng sort, điều kiện join.
4. **Cho phép query hợp lệ nhưng quá đắt:** scan không giới hạn, regex nặng, pipeline tiêu tốn CPU, phân trang sâu.

Một cơ chế binding chỉ trực tiếp chống dạng **giá trị bị diễn giải thành cú pháp**. Ba vấn đề còn lại cần ràng buộc bổ sung.

---

## 4. Bind giá trị khác với escape chuỗi

Một giải pháp dễ mắc lỗi là tự sửa input:

```java
String escaped = userInput.replace("'", "''");
String query = "SELECT ... WHERE name = '" + escaped + "'";
```

Dù escaping đúng trong một ngôn ngữ cụ thể, nó dễ sai khi:

- Cấu trúc quote/cú pháp thay đổi theo dialect.
- Query có nhiều kiểu: string, UUID, timestamp, collection, blob.
- Một path dùng escaping khác.
- Query DSL không dùng cơ chế quote giống SQL.
- Một developer quên escape trong một endpoint khác.

**Binding** tách giá trị khỏi cú pháp và để driver/protocol mã hóa đúng kiểu dữ liệu ở vị trí cho phép.

### 4.1. Hai ví dụ ngược nhau

Không nên:

```java
String statement =
    "SELECT status FROM commerce.orders WHERE tenant_id = '" +
    tenantId + "'";
```

Nên:

```java
PreparedStatement p = session.prepare(
    "SELECT status FROM commerce.orders WHERE tenant_id = ?"
);
BoundStatement b = p.bind(tenantId);
ResultSet result = session.execute(b);
```

Ví dụ là CQL trên Cassandra Java Driver 4.x; bảng/schema và session phải tồn tại sẵn.

### 4.2. Prepared không có nghĩa “được phép input bất kỳ”

Nếu client đưa 10 MB text vào một bound parameter, driver có thể mã hóa thành giá trị hợp lệ nhưng backend vẫn tốn network, RAM và CPU. Cần validate cả **kích thước, miền giá trị, số phần tử và số request**.

---

# Phần I — CQL prepared/bound statements với Java

## 5. Chu trình chuẩn bị và thực thi truy vấn CQL

Trong Java Driver v4 kiểu DataStax/Apache Cassandra, một luồng phổ biến:

```text
Ứng dụng khởi động
       |
       v
Tạo CqlSession
       |
       v
Prepare CQL query shape
       |
       v
Giữ PreparedStatement dùng lại
       |
       +-----------------------------+
       |                             |
       v                             v
Request A                       Request B
bind(valueA)                    bind(valueB)
       |                             |
       v                             v
BoundStatement A                 BoundStatement B
       |                             |
       v                             v
Execute trên session đã quản lý
```

**PreparedStatement** biểu diễn query đã được chuẩn bị theo protocol. **BoundStatement** mang những giá trị của lần thực thi cụ thể.

### 5.1. Prepare một lần cho query shape ổn định

Nếu mọi request đều gọi `session.prepare(...)` cho cùng chuỗi CQL, ứng dụng có thể tăng round-trip/metadata overhead không cần thiết. Thường chuẩn bị query shape trong quá trình khởi tạo repository/DAO rồi bind mỗi lần gọi.

### 5.2. Bind cho từng request

Không giữ chung một đối tượng “giá trị đã bind của request A” để sửa rồi đưa sang request B. Mỗi request nên tạo bound statement mới từ prepared template.

### 5.3. Session lifecycle

`CqlSession` thường được quản lý như tài nguyên ứng dụng dùng lại, đóng khi service shutdown. Không mở/đóng session mới cho mỗi request.

---

## 6. Tạo bảng Cassandra phù hợp cho ví dụ

Schema minh họa trong một môi trường lab:

```sql
CREATE KEYSPACE IF NOT EXISTS commerce
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS commerce.orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id text,
    status text,
    total_minor_units bigint,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
```

`dc1` và replication factor 3 chỉ là **giả định lab**, không phải cấu hình có thể áp dụng nguyên cho mọi cluster. Tên datacenter thực, strategy và keyspace ownership cần khớp deployment.

### 6.1. Khóa truy vấn

`(tenant_id, order_id)` là partition key ghép. Muốn đọc một order bằng point query, ứng dụng cần cả hai thành phần.

### 6.2. Prepared không tự giúp query thiếu partition key

Câu lệnh đã prepare vẫn có thể là một truy vấn sai mô hình hoặc rất tốn kém nếu thiếu điều kiện định tuyến. **An toàn cú pháp** và **hiệu quả phân vùng** là hai mục tiêu khác nhau.

---

## 7. Java: Repository sử dụng PreparedStatement và BoundStatement

Ví dụ dùng các package của Cassandra Java Driver 4.x. Giả định project đã cấu hình driver, datacenter, contact points và bảng ở phần trước.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

public final class CassandraOrderRepository {
    private final CqlSession session;
    private final PreparedStatement findByKey;

    public CassandraOrderRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.findByKey = session.prepare(
            "SELECT tenant_id, order_id, status, total_minor_units " +
            "FROM commerce.orders_by_id " +
            "WHERE tenant_id = ? AND order_id = ?"
        );
    }

    public Optional<String> findStatus(
            String authorizedTenantId,
            UUID orderId
    ) {
        Objects.requireNonNull(authorizedTenantId);
        Objects.requireNonNull(orderId);

        BoundStatement statement = findByKey.bind(
            authorizedTenantId, orderId
        );

        ResultSet results = session.execute(statement);
        Row row = results.one();

        return row == null
            ? Optional.empty()
            : Optional.ofNullable(row.getString("status"));
    }
}
```

### 7.1. Bảo vệ nào nằm ở đâu?

- `findByKey` định nghĩa **CQL cố định**.
- `bind(...)` đưa `authorizedTenantId` và `orderId` vào đúng vị trí giá trị.
- Driver xử lý encoding cho `text` và `uuid`.
- Repository không quyết định tenant từ request tùy ý; nó **nhận tenant đã xác thực từ tầng application/service**.
- Truy vấn có đủ partition key, giúp truy cập đúng logical partition.

### 7.2. Khởi tạo session minh họa

```java
try (CqlSession session = CqlSession.builder().build()) {
    CassandraOrderRepository repo =
        new CassandraOrderRepository(session);

    Optional<String> status = repo.findStatus(
        "tenant-a",
        UUID.fromString(
            "11111111-1111-1111-1111-111111111111"
        )
    );
}
```

Trong môi trường thật, `CqlSession.builder().build()` cần driver configuration hợp lệ; thường session được cấp bởi DI/container thay vì tạo trong controller.

### 7.3. Không bind tên bảng hoặc tên cột như giá trị

Trường hợp này **không** làm điều người viết mong muốn:

```java
String cql = "SELECT * FROM ? WHERE tenant_id = ?";
```

Bind marker ở vị trí tên bảng không biến giá trị `"orders_by_id"` thành identifier hợp lệ theo nghĩa của câu lệnh. **Identifiers không phải dữ liệu thông thường.**

---

## 8. Positional bind và named bind markers

Một số query API cho phép đặt tên marker, thay vì dựa hoàn toàn vào thứ tự tham số.

Ví dụ CQL:

```sql
SELECT status
FROM commerce.orders_by_id
WHERE tenant_id = :tenantId
  AND order_id = :orderId;
```

Khi API/driver hỗ trợ named markers tương ứng, bound statement có thể nhận giá trị theo marker name với phương thức phù hợp.

### 8.1. Thứ tự là rủi ro bảo trì

Nếu hai trường đều là `text`, việc đảo `tenantId` và `customerId` có thể không gây lỗi kiểu dữ liệu nhưng khiến query trả kết quả sai.

Giải pháp:

- Dùng named markers khi phù hợp.
- Đặt query/repository theo một contract nhất quán.
- Kiểm thử với dữ liệu có các ID khác nhau.
- Dùng value objects ở tầng domain để hạn chế nhầm.

### 8.2. Kiểu dữ liệu phải khớp schema

Nếu cột là UUID, không nên chuyển mọi giá trị thành string rồi kỳ vọng query engine tự đoán. Hãy parse/validate UUID trước khi bind.

### 8.3. `null` và `UNSET` không phải lúc nào tương đương

Trong Cassandra Driver/CQL, null và giá trị unset có semantics riêng, đặc biệt khi dùng trong write/update. Đừng coi marker không đặt giá trị, marker null và field bỏ qua là một trong mọi thao tác; tham chiếu đúng protocol/driver version.

---

## 9. Prepared statement và tối ưu hiệu năng

Prepared statements có thể giúp tái sử dụng metadata/tránh parse lặp theo protocol, nhưng **không có nghĩa mỗi query đều nhanh hơn** trong mọi trường hợp.

Một query có partition key sai, truy vấn quá nhiều rows hoặc không có index phù hợp vẫn có thể tốn tài nguyên dù được chuẩn bị.

### 9.1. Mẫu chuẩn bị hợp lý

- Query shapes cố định, số lượng hữu hạn.
- Prepare khi ứng dụng khởi động hoặc lần đầu qua một cache có quản lý.
- Bound values khác nhau cho mỗi request.
- Không đưa giá trị cụ thể vào chuỗi CQL để tạo hàng nghìn query shapes.
- Giám sát cache/prepared metadata theo driver và số nodes.

### 9.2. Schema thay đổi

Khi đổi schema, node restart hoặc cache prepared metadata bị mất, driver/protocol có thể cần **reprepare**. Không viết một retry loop tự chế vô hạn quanh `UNPREPARED`; dùng hành vi driver hỗ trợ và theo dõi sự cố.

### 9.3. Lưu ý hiệu năng tại partition

Tất cả request của một tenant cực nóng dồn vào một partition có thể gây overload dù câu CQL đã prepare. Cần xem chọn khóa, bucketing/salting và workload, không dùng prepared như cách chữa hot partition.

---

## 10. CQL UPDATE có điều kiện và prepared statement

Một bất biến như “chỉ hủy order khi đang `PENDING`” phải được kiểm tra ở **thời điểm ghi**. Chỉ bind giá trị an toàn không bảo vệ business invariant.

Ví dụ CQL minh họa lightweight transaction:

```sql
UPDATE commerce.orders_by_id
SET status = ?
WHERE tenant_id = ?
  AND order_id = ?
IF status = ?;
```

Java:

```java
PreparedStatement changeStatus = session.prepare(
    "UPDATE commerce.orders_by_id SET status = ? " +
    "WHERE tenant_id = ? AND order_id = ? " +
    "IF status = ?"
);

BoundStatement statement = changeStatus.bind(
    "CANCELLED",
    authorizedTenantId,
    orderId,
    "PENDING"
);

ResultSet result = session.execute(statement);
boolean applied = result.wasApplied();
```

### 10.1. Ba loại bảo vệ khác nhau

1. **Bound values:** ngăn giá trị trở thành cú pháp CQL.
2. **Partition key:** xác định đúng logical object.
3. **`IF` condition:** thực thi precondition tại storage authority theo semantics LWT.

Không có cơ chế nào tự thay thế hai cơ chế còn lại.

### 10.2. Timeout khi ghi có thể có kết quả không rõ

Nếu `execute` timeout sau khi server đã áp dụng conditional update, ứng dụng không thể tự suy là chưa ghi. Cần đọc lại state/version theo consistency policy hoặc dùng operation ID/đối soát phù hợp.

### 10.3. Chi phí conditional writes

LWT có protocol/latency và giới hạn scope riêng. Không dùng nó cho mọi write chỉ vì “an toàn hơn”, mà phải quyết định từ invariant.

---

## 11. Truy vấn CQL động: vì sao không nên nối thêm `ALLOW FILTERING`?

Một API tìm kiếm do client điều khiển có thể muốn:

```text
status=PAID
country=VN
createdAfter=...
```

Nếu schema chỉ định tuyến theo `(tenantId, orderId)`, không có nghĩa ta có thể viết một chuỗi CQL tùy biến để tìm mọi order theo status trên toàn cluster.

### 11.1. Prepared không sửa mô hình truy vấn

```sql
SELECT *
FROM commerce.orders_by_id
WHERE status = ? ALLOW FILTERING;
```

Ngay cả khi marker được bind đúng và engine cho chạy trong cấu hình cụ thể, truy vấn có thể phải scan rộng, gây p99 cao và tải nhiều partitions. Không coi `ALLOW FILTERING` là lời giải mặc định cho endpoint production.

### 11.2. Thiết kế bảng theo access pattern

Ví dụ bảng `orders_by_customer` keyed theo tenant/customer/time bucket có thể phục vụ lịch sử khách nhanh hơn. Query có đủ partition key mới tận dụng locality.

### 11.3. Không mở cho client tự chọn CQL predicate

Nếu client được quyền gửi “CQL where clause”, binding vài giá trị không chặn được nguy cơ sử dụng operator, `ALLOW FILTERING`, bảng hoặc schema ngoài phạm vi.

---

# Phần II — MongoDB Java Driver: BSON typed query builders

## 12. MongoDB không yêu cầu “prepare” giống CQL

MongoDB thao tác truy vấn qua BSON documents/commands. Trong Java driver đồng bộ, phương thức phổ biến là:

- `Filters.eq`, `Filters.and`, `Filters.gte`, `Filters.lt`.
- `Sorts.ascending/descending/orderBy`.
- `Projections.include/exclude/fields`.
- `Updates.set/inc/combine`.
- `Aggregates.match/group/project`.
- `MongoCollection.find`, `aggregate`, `updateOne`…

Các builder tạo **BSON query structure**, đưa giá trị như Java `String`, `UUID`, `Date`, `Number`, `ObjectId` đúng kiểu. Không cần `PreparedStatement` phía server cho mẫu này.

### 12.1. Ví dụ an toàn

```java
Bson filter = Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("customerId", customerId),
    Filters.eq("status", "PAID")
);
```

`customerId` được đưa vào vị trí **giá trị của `$eq`**, không phải một đoạn JSON để MongoDB tự parse thành toán tử mới.

### 12.2. Ví dụ dễ gặp rủi ro

Không xây query bằng:

```java
String json =
    "{\"customerId\": \"" + clientInput + "\"}";
Document filter = Document.parse(json);
```

Input có thể phá cấu trúc quote/JSON hoặc tạo dữ liệu không đúng ý. Cũng không nên lấy một JSON filter object tùy ý do client gửi rồi dùng làm truy vấn MongoDB nếu chưa kiểm tra các operator và field được phép.

### 12.3. String chứa `$ne` không tự động là operator

Nếu client gửi chuỗi literal `"$ne"`, `Filters.eq("status", "$ne")` vẫn là tìm status bằng **chuỗi** `$ne`. Nguy cơ xuất hiện khi input được đưa vào **vị trí cấu trúc BSON operator** hoặc được parse thành query language, không phải ở mọi ký tự `$`.

---

## 13. Java MongoDB: truy vấn có tenant, bộ lọc và giới hạn

Đoạn ví dụ dùng MongoDB Java Sync Driver, với những đối tượng đã được khởi tạo bằng dependency injection.

```java
import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;

public final class MongoOrderReader {
    private final MongoCollection<Document> orders;

    public MongoOrderReader(MongoCollection<Document> orders) {
        this.orders = orders;
    }

    public FindIterable<Document> findRecent(
            String authorizedTenantId,
            String customerId,
            Instant fromInclusive,
            Instant toExclusive,
            int requestedLimit
    ) {
        int limit = Math.max(1, Math.min(requestedLimit, 50));

        Bson filter = Filters.and(
            Filters.eq("tenantId", authorizedTenantId),
            Filters.eq("customerId", customerId),
            Filters.gte("createdAt", Date.from(fromInclusive)),
            Filters.lt("createdAt", Date.from(toExclusive))
        );

        return orders.find(filter)
            .sort(Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.ascending("_id")
            ))
            .projection(Projections.fields(
                Projections.include(
                    "_id", "status",
                    "createdAt", "totalMinorUnits"
                )
            ))
            .limit(limit)
            .maxTime(300, TimeUnit.MILLISECONDS);
    }
}
```

### 13.1. Phạm vi bảo vệ

- Các field truy vấn được chọn trong code.
- Mọi giá trị từ request nằm trong `Filters.*` như data.
- Tenant scope được áp thêm cho mọi request.
- Có giới hạn số kết quả và server-side execution time limit.
- Projection không vô tình trả các field như token, địa chỉ riêng tư hoặc dữ liệu card.

### 13.2. Những thứ ví dụ chưa làm

- Chưa xử lý authentication/authorization của caller.
- Chưa kiểm tra định dạng/độ dài `customerId`.
- Chưa cấp cursor/pagination hoặc tái thử có kiểm soát.
- Chưa đo query plan/index.
- Chưa xử lý lỗi network, timeout và consistency/read preference.
- Chưa kiểm tra `fromInclusive < toExclusive` và khoảng thời gian tối đa.

Đây là **DAO minh họa**, không phải endpoint production hoàn chỉnh.

### 13.3. Index phù hợp

Với access pattern trên, một index cần cân nhắc:

```javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: 1
});
```

Kiểm chứng bằng `explain()` và workload đại diện; index có chi phí lưu trữ/ghi và plan còn phụ thuộc selectivity.

---

## 14. MongoDB injection qua object, operator và pipeline

Một ứng dụng nhận:

```json
{
  "filter": {
    "$or": [
      {"status": "PAID"},
      {"tenantId": "another-tenant"}
    ]
  }
}
```

rồi chuyển trực tiếp `filter` thành query có thể khiến client kiểm soát logic bảo mật. Dù input là **JSON hợp lệ**, nó không còn là một giá trị đơn thuần.

### 14.1. Những vùng cần tránh cho client kiểm soát tùy ý

- `$where` hoặc JavaScript-expression features không cần thiết.
- Tên operator như `$ne`, `$or`, `$expr`.
- Aggregation pipeline stages và các nguồn dữ liệu có thể truy cập.
- Field path, update path hoặc projection field bất kỳ.
- Regex pattern không giới hạn.
- Collection/database name, sort key và skip/limit quá lớn.
- Filter được serialize từ một generic `Map<String,Object>` không có schema.

### 14.2. Cách đúng: parse DTO, không parse query do client đưa

Một HTTP DTO chỉ cho:

```json
{
  "status": "PAID",
  "createdAfter": "2026-11-01T00:00:00Z",
  "limit": 20
}
```

Sau validation, server xây:

```java
Bson predicate = Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("status", validatedStatus),
    Filters.gte("createdAt", Date.from(validatedFrom))
);
```

Client chọn **giá trị trong phạm vi nghiệp vụ**, không chọn raw MongoDB query language.

### 14.3. Dynamic filter có thể an toàn nếu dùng AST cho phép

Nếu ứng dụng cần “Advanced Search”, định nghĩa grammar riêng như:

```text
Filter :=
  status EQ allowedStatus
  | createdAt GTE validTimestamp
  | totalMinorUnits BETWEEN validatedNumbers
```

Biến nó thành một **AST đã validate**, rồi biên dịch sang `Filters.eq/gte/lte` bằng field/operator allowlist. Không chấp nhận raw `$where` hoặc pipeline stage tùy ý.

---

## 15. Regex tìm kiếm: bind value vẫn có thể gây DoS

Regex là ví dụ quan trọng: kể cả input được đưa vào **một giá trị regex**, một pattern do người dùng kiểm soát vẫn có thể gây truy vấn nặng hoặc ý nghĩa ngoài dự kiến.

### 15.1. Muốn tìm prefix literal

Nếu người dùng nhập `"a.*"`, nhưng nghiệp vụ muốn tìm các tên **bắt đầu bằng đúng chuỗi `a.*`**, cần escape ký tự regex.

Ví dụ Java:

```java
import java.util.regex.Pattern;
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

String prefix = validatedPrefix;
if (prefix.length() > 64) {
    throw new IllegalArgumentException("Prefix too long");
}

Pattern literalPrefix = Pattern.compile(
    "^" + Pattern.quote(prefix)
);

Bson filter = Filters.and(
    Filters.eq("tenantId", authorizedTenantId),
    Filters.regex("displayName", literalPrefix)
);
```

`Pattern.quote` giữ prefix như literal, không biến `.*` thành wildcard.

### 15.2. Regex vẫn có thể tốn

Ngay cả một regex hợp lệ cũng có thể không dùng index hiệu quả, phụ thuộc regex flags/collation và query plan. Cần giới hạn field, độ dài, time budget và quan sát `keysExamined/docsExamined`.

### 15.3. Full-text search khác regex

Nếu nghiệp vụ cần search văn bản tự do, hãy cân nhắc index tìm kiếm văn bản hay search engine chuyên dụng thay vì gửi regex tùy ý qua mọi document.

---

## 16. Cập nhật MongoDB: field update cũng là một bề mặt injection

Không nên cho client gửi một object lệnh cập nhật tùy ý rồi dùng thẳng:

```java
// Không nên nhận raw request body như một Update BSON operator.
orders.updateOne(filter, Document.parse(clientProvidedUpdateJson));
```

Người gọi có thể cố sửa `tenantId`, `ownerId`, `role`, `priceAtPurchase` hoặc những field hệ thống.

### 16.1. Chỉ cho phép business fields hợp lệ

```java
Bson filter = Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("tenantId", authorizedTenantId),
    Filters.eq("status", "PENDING")
);

Bson update = Updates.combine(
    Updates.set("status", "CANCELLED"),
    Updates.inc("version", 1)
);

orders.updateOne(filter, update);
```

### 16.2. Điều kiện nghiệp vụ khác binding

`status="PENDING"` trong filter là **precondition** để không hủy order đã được giao. `tenantId` bảo vệ scope. `Updates.set` với field cố định không cho client sửa những trường ngoài policy.

Không được tin một bản `status` đọc trước đó rồi update vô điều kiện; một transaction khác có thể đã thay đổi nó giữa read và write.

### 16.3. Không mù quáng dùng replace

Một API nhận toàn bộ document từ client và `replaceOne` có thể làm mất field server-managed hoặc thay ownership. Thường nên map request DTO sang các field update được cho phép.

---

## 17. Spring Data MongoDB: query builder và repository

Spring Data có `Query` và `Criteria` thay cho xây BSON trực tiếp.

Ví dụ khái niệm trong một service:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = new Query()
    .addCriteria(Criteria.where("tenantId").is(authorizedTenantId))
    .addCriteria(Criteria.where("customerId").is(customerId))
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("_id")
    ))
    .limit(25);

var orders = mongoTemplate.find(query, OrderDocument.class);
```

### 17.1. Framework không tự thêm tenant filter

Nếu developer viết `findById(orderId)` và quên tenant scope, query có thể đúng cú pháp nhưng sai quyền. Cần contract repository như `findByTenantIdAndId(...)`, middleware/guard phù hợp và test cross-tenant.

### 17.2. Cẩn trọng với field name động

```java
Criteria.where(clientProvidedField).is(clientValue);
```

`is()` đưa `clientValue` thành giá trị, nhưng **tên field** do client chọn vẫn có thể nhắm những thông tin ngoài quyền.

Chỉ chuyển từ một enum công khai sang field nội bộ đã cho phép.

### 17.3. Spring Data query strings

Một số Spring Data repositories cho phép annotation query dạng chuỗi/JSON. Khi dùng, phải nắm rõ cơ chế binding của framework và tránh tự nối chuỗi input vào annotation/native query.

---

## 18. Aggregation pipeline: chỉ ghép các stage do server lựa chọn

MongoDB aggregation hỗ trợ `$match`, `$group`, `$sort`, `$project`, `$lookup` và nhiều stage khác. Sức mạnh này cũng có thể tiêu thụ tài nguyên lớn nếu client được điều khiển tùy ý.

Một pipeline đọc tổng tiền theo tenant:

```java
var pipeline = java.util.List.of(
    com.mongodb.client.model.Aggregates.match(
        Filters.and(
            Filters.eq("tenantId", authorizedTenantId),
            Filters.eq("status", "PAID")
        )
    ),
    com.mongodb.client.model.Aggregates.group(
        "$currency",
        com.mongodb.client.model.Accumulators.sum(
            "totalMinorUnits", "$totalMinorUnits"
        )
    )
);
```

Field paths và stages được quyết định trong code; tenant là bound value trong BSON filter.

### 18.1. Scope/permission phải ở đầu đường dữ liệu

Bước `$match` theo tenant thường nên được đặt sớm khi query semantics cho phép, nhưng không được suy mọi stage có thể reorder tùy ý. Kiểm tra aggregation optimizer và plan.

### 18.2. Không cho client gửi pipeline JSON như API công khai chung

Một client có thể yêu cầu các stage tiêu tốn tài nguyên lớn hoặc vượt nguồn dữ liệu được phép. Nếu phải hỗ trợ pipeline tùy chỉnh cho admin, dùng **grammar/AST allowlist, RBAC, query budget và audit** riêng.

### 18.3. Tài nguyên aggregation

Thêm giới hạn time, kết quả và concurrency; xem quy tắc memory/disk spilling của phiên bản. Binding không làm một pipeline phức tạp trở nên rẻ.

---

# Phần III — DynamoDB, Redis, Cypher và các cơ chế tương ứng

## 19. DynamoDB: expression placeholders

DynamoDB Query API dùng expression text với placeholders cho **tên thuộc tính** và **giá trị**:

- `#pk`: symbolic alias tới attribute name, ví dụ `PK`.
- `:pk`: placeholder cho attribute value.
- `KeyConditionExpression`: điều kiện trên key của bảng/index theo API.
- `ExpressionAttributeNames`: ánh xạ alias tới field thật.
- `ExpressionAttributeValues`: ánh xạ placeholder tới `AttributeValue` typed.

### 19.1. Java AWS SDK v2: Query theo partition key

```java
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

import java.util.Map;

public final class DynamoOrderReader {
    private final DynamoDbClient dynamo;

    public DynamoOrderReader(DynamoDbClient dynamo) {
        this.dynamo = dynamo;
    }

    public QueryResponse recentOrders(String authorizedTenantId) {
        QueryRequest request = QueryRequest.builder()
            .tableName("OrdersByTenant")
            .keyConditionExpression(
                "#pk = :pk AND begins_with(#sk, :prefix)"
            )
            .expressionAttributeNames(Map.of(
                "#pk", "PK",
                "#sk", "SK"
            ))
            .expressionAttributeValues(Map.of(
                ":pk", AttributeValue.builder()
                    .s("TENANT#" + authorizedTenantId).build(),
                ":prefix", AttributeValue.builder()
                    .s("ORDER#").build()
            ))
            .limit(25)
            .build();

        return dynamo.query(request);
    }
}
```

Giả định `OrdersByTenant` có partition key string `PK` và sort key string `SK`, với dữ liệu `PK="TENANT#..."`, `SK="ORDER#..."`. Phải tạo bảng/index theo schema đó và cấu hình AWS credentials/region qua SDK.

### 19.2. `ExpressionAttributeNames` không thay allowlist

Cho phép client tự gửi `"#field" -> "sensitiveAttribute"` vẫn có thể mở truy cập sai quyền. Alias cho tên thuộc tính giải quyết cú pháp/reserved words, **không cấp quyền nghiệp vụ**.

### 19.3. Giữ Query chứ không vô tình Scan

Một `FilterExpression` chỉ lọc kết quả từ những item đã được đọc theo ngữ nghĩa API; nó không thay `KeyConditionExpression` để giảm mọi truy cập. Nếu thiếu partition key và phải `Scan`, cost có thể lớn.

### 19.4. Query không luôn trả đủ `Limit` kết quả

Kết quả có thể được phân trang bởi giới hạn xử lý của API hoặc filtering. Cần kiểm tra `lastEvaluatedKey` và quy tắc continuation; không suy `limit(25)` bảo đảm trả đúng 25 items.

---

## 20. DynamoDB: điều kiện cập nhật cũng dùng placeholders

Một `UpdateItem` có thể ràng buộc trạng thái:

```text
ConditionExpression:
    #status = :expected

UpdateExpression:
    SET #status = :next
```

Phần names/values được đưa vào maps:

```java
Map<String, String> names = Map.of(
    "#status", "status"
);

Map<String, AttributeValue> values = Map.of(
    ":expected", AttributeValue.builder().s("PENDING").build(),
    ":next", AttributeValue.builder().s("CANCELLED").build()
);
```

### 20.1. Không coi conditional failure là injection hay outage

`ConditionalCheckFailedException` thường biểu thị precondition không đạt; nó có thể là kết quả hợp lệ của cạnh tranh hoặc nghiệp vụ. Không retry vô hạn như lỗi mạng.

### 20.2. Ghi có thể có kết quả không rõ

Nếu response timeout sau khi DynamoDB đã áp dụng update, cần đọc/đối soát state hoặc dùng idempotency/transaction IDs theo API phù hợp. Bind placeholders không sửa vấn đề này.

### 20.3. Key schema quyết định access pattern

Bảng chỉ cho Query theo partition key và sort key tương ứng. Một expression đúng cú pháp không khiến truy vấn theo bất kỳ attribute nào trở thành targeted query hiệu quả.

---

## 21. Redis: không có SQL nhưng vẫn cần API và keyspace an toàn

Lệnh cơ bản Redis như `GET`, `SET`, `HGET` thường nhận **arguments** thay vì một chuỗi SQL cần parse.

Với Jedis:

```java
import redis.clients.jedis.JedisPooled;

try (JedisPooled jedis =
         new JedisPooled("redis://localhost:6379")) {
    String value = jedis.get("tenant:a:profile:u7");
}
```

Trong ứng dụng thật, endpoint, TLS, auth/secret và lifecycle phải được cấu hình an toàn; không hardcode thông tin đăng nhập.

### 21.1. Rủi ro vẫn tồn tại ở key

Không nên:

```java
String key = "tenant:" + clientTenantId + ":profile:" + userId;
```

rồi cho rằng đã an toàn nhờ không có SQL. `clientTenantId` có thể sai quyền, hoặc dấu phân cách có thể gây collision nếu ID không được chuẩn hóa/encode.

### 21.2. Key factory có phạm vi rõ ràng

```java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

static String encodeKeyPart(String input) {
    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(input.getBytes(StandardCharsets.UTF_8));
}

static String profileKey(
        String authorizedTenantId, String userId) {
    return "tenant:" + encodeKeyPart(authorizedTenantId)
        + ":profile:" + encodeKeyPart(userId);
}
```

Base64URL ở đây chỉ giúp tránh trùng dấu phân cách và nhất quán key encoding; **nó không mã hóa bí mật và không xác thực quyền**.

### 21.3. Lua script

Nếu dùng Redis `EVAL`/scripts, code script nên là **một template do server quyết định** và dữ liệu truyền qua `KEYS`/`ARGV` đúng hợp đồng. Không nối input người dùng vào **nguồn Lua code**.

Trong Redis Cluster, phải xem ràng buộc keys/hash slots cho multi-key scripts; không tạo keys tùy ý dựa vào user input rồi giả định một script có quyền đọc toàn cluster.

### 21.4. Không dùng `KEYS *` cho endpoint production

Một lệnh tìm toàn keyspace có thể rất tốn trên dataset lớn. Thiết kế schema/key/index để lookup có phạm vi; nếu phải duyệt, dùng cơ chế scan có batch và giới hạn phù hợp, không coi `SCAN` luôn rẻ trong mọi trường hợp.

---

## 22. Neo4j Cypher: parameter binding

Một graph NoSQL dùng Cypher có cú pháp query riêng. Ví dụ Java Neo4j Driver hiện đại:

```java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

import java.util.Map;

public final class GraphOrderReader {
    private final Driver driver;

    public GraphOrderReader(Driver driver) {
        this.driver = driver;
    }

    public String findStatus(
            String authorizedTenantId, String orderId) {
        try (Session session = driver.session()) {
            return session.executeRead(tx ->
                tx.run(
                    "MATCH (o:Order {tenantId: $tenant, id: $id}) " +
                    "RETURN o.status AS status",
                    Map.of(
                        "tenant", authorizedTenantId,
                        "id", orderId
                    )
                ).single().get("status").asString()
            );
        }
    }
}
```

Mục đích: `$tenant` và `$id` là **parameters**, không ghép literal vào Cypher.

### 22.1. Tên label và relationship type

Nếu client được chọn label, property name hoặc relationship pattern tùy ý, API cần allowlist/typed query branches. Khả năng parameterize một số identifier phụ thuộc version/ngôn ngữ; không tự coi mọi vị trí cú pháp có thể thay bằng `$value`.

### 22.2. Query có thể truy cập quá rộng

Một pattern match không có tenant scope hoặc giới hạn traversal có thể làm lộ graph khác hoặc quét graph rất lớn. Parameterization không thay RBAC và query plan.

### 22.3. Lưu ý `.single()`

Trong code minh họa, `.single()` đòi đúng một kết quả. Production cần xử lý không tìm thấy và dữ liệu trùng theo contract thay vì trả 500 không giải thích.

---

## 23. Couchbase SQL++ và các query language khác

SQL++ (còn gọi là N1QL trong ngữ cảnh Couchbase) có biểu thức gần SQL và hỗ trợ query parameters theo SDK.

Mẫu khái niệm:

```text
SELECT META(o).id, o.status
FROM `orders` AS o
WHERE o.tenantId = $tenantId
  AND o.orderId = $orderId
LIMIT 1
```

Với Couchbase Java SDK hỗ trợ named parameters, ứng dụng truyền `tenantId/orderId` qua API parameters chứ không nối vào query string. Cấu trúc keyspace/index name phải nằm trong **query templates hoặc allowlist**.

### 23.1. Đừng copy một API cụ thể giữa các driver

JDBC `PreparedStatement`, Cassandra CQL `PreparedStatement`, Couchbase query options và Neo4j session parameters có **kiểu, kết nối, caching và semantics riêng**.

### 23.2. Query DSL typed vẫn cần chính sách

Elasticsearch/OpenSearch Java clients có các typed query builders và JSON DSL; nếu client cho gửi raw DSL script/pipeline bất kỳ, một API hợp lệ về cú pháp vẫn có thể vượt scope hoặc tạo truy vấn quá nặng. Dùng whitelist field/query types và request budget.

---

# Phần IV — Bảo vệ những thứ binding không giải quyết

## 24. Multi-tenancy: filter phải tới từ authority

Giả sử database có:

```json
{
  "_id": "o1001",
  "tenantId": "tenant-a",
  "customerId": "c42",
  "status": "PAID"
}
```

Một request từ tenant B gửi `_id=o1001` có thể làm lộ order A nếu repository chỉ:

```java
orders.find(Filters.eq("_id", orderId));
```

Đây là lỗi **IDOR/BOLA hoặc tenant isolation**, dù truy vấn dùng `Filters.eq` hoàn toàn không có injection.

### 24.1. Scope ở mọi point query

```java
Bson filter = Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("tenantId", authorizedTenantId)
);
```

### 24.2. Scope ở update và delete

Không chỉ bảo vệ read. Ví dụ:

```java
orders.deleteOne(Filters.and(
    Filters.eq("_id", orderId),
    Filters.eq("tenantId", authorizedTenantId)
));
```

Cũng phải kiểm tra quyền xóa, trạng thái và các preconditions khác theo business logic.

### 24.3. Scope trong secondary index/read model

Nếu một GSI/search index chứa order của nhiều tenants, mọi query và lookup phải giữ tenant/permission context phù hợp. Không tin một read model stale để cấp quyền mới.

### 24.4. Tầng bảo vệ phòng thủ nhiều lớp

Có thể kết hợp route scopes, repository contracts, database roles/permissions và integration tests. Nhưng không mặc định mọi NoSQL đều cung cấp row-level security tự động.

---

## 25. Validation và parsing trước khi bind

Bind không thay validation. Các loại input nên được kiểm soát:

| Input | Kiểm tra gợi ý | Lý do |
| --- | --- | --- |
| `tenantId` | Lấy từ auth context, định dạng hợp lệ | Tránh vượt tenant và collision |
| UUID/orderId | Parse UUID/ID dạng chuẩn | Tránh dữ liệu kiểu sai, lỗi không rõ |
| `status` | Enum tập giá trị cho phép | Giảm trạng thái bất hợp lệ |
| `createdAfter` | Parse ISO time, timezone rõ | Tránh query thời gian sai |
| `limit` | Min/max cứng | Chặn trả dataset quá lớn |
| `pageToken` | Decode/validate/sign và ràng buộc scope | Không cho sửa cursor tùy ý |
| `sort` | Map allowlist sang field thực | Chặn sort trên field ngoài quyền hoặc không index |
| `searchText` | Độ dài, encoding, kiểu truy vấn | Tránh query nặng và log injection |
| `ids[]` | Kích thước mảng tối đa, dedupe | Chặn `IN` vô hạn/batch bão hòa |
| `regex` | Không nhận raw pattern nếu không cần | Tránh regex abuse |
| `projection` | Cho phép field cụ thể | Tránh trả dữ liệu nhạy cảm |

### 25.1. Chuyển string sang type

```java
UUID id;
try {
    id = UUID.fromString(rawOrderId);
} catch (IllegalArgumentException invalid) {
    throw new BadRequestException("Invalid orderId");
}
```

`BadRequestException` ở đây là kiểu lỗi của application, không phải class có sẵn của Java SE.

### 25.2. Không log raw input tùy ý

Input có thể chứa newline/control characters, tokens hoặc PII. Log nên structured, có giới hạn độ dài và redact theo policy.

---

## 26. Chọn cột sort và operator bằng enum/allowlist

Ngay cả khi các filter values đã bind, một API vẫn có thể dùng:

```java
String query = "SELECT ... ORDER BY " + clientSortField;
```

hoặc:

```java
Sorts.ascending(clientSortField);
```

Trường sort đang là **cấu trúc query**, không phải giá trị. Nếu client được quyền sort theo `adminSecret`, hệ có thể lộ pattern hoặc tạo truy vấn tốn kém.

### 26.1. Mẫu Java an toàn

```java
enum OrderSort {
    NEWEST,
    OLDEST
}

static org.bson.conversions.Bson resolveSort(
        OrderSort requested) {
    return switch (requested) {
        case NEWEST -> com.mongodb.client.model.Sorts.orderBy(
            com.mongodb.client.model.Sorts.descending("createdAt"),
            com.mongodb.client.model.Sorts.ascending("_id")
        );
        case OLDEST -> com.mongodb.client.model.Sorts.orderBy(
            com.mongodb.client.model.Sorts.ascending("createdAt"),
            com.mongodb.client.model.Sorts.ascending("_id")
        );
    };
}
```

Client gửi `sort=newest`; server parse enum rồi ánh xạ đến **field được định nghĩa trong code**.

### 26.2. Trường tùy chọn có whitelist

Nếu UI cho `status`, `createdAt`, `total`, dùng map cố định và chỉ những field đã có index/permission. Unknown sort field → trả lỗi 400, không cố chèn trực tiếp vào BSON/DSL.

### 26.3. Operator cũng phải có policy

Một filter `total > amount` khác `total != amount` hoặc `$or` trên nhiều fields. Nếu client chọn operator, dùng enum hẹp, không cho gửi chuỗi `$where` hay một đoạn CQL tự do.

---

## 27. Phân trang phải bảo vệ dữ liệu và tài nguyên

Một endpoint trả nhiều record cần giới hạn kết quả. Nhưng `limit=20` không tự đủ.

### 27.1. Offset/skip sâu

`skip(1_000_000)` có thể phải duyệt nhiều bản ghi trước khi trả 20 record, phụ thuộc index/engine. Tránh endpoint cho client chọn offset không giới hạn.

### 27.2. Keyset/cursor pagination

Ví dụ MongoDB sort:

```text
createdAt DESC, _id ASC
```

Cursor có thể chứa:

```json
{
  "tenantId": "tenant-a",
  "createdAt": "2026-11-01T10:00:00Z",
  "lastId": "o1001",
  "sort": "newest"
}
```

Tuy nhiên, điều kiện “sau cursor” phải đúng với hướng sort hỗn hợp, chẳng hạn `createdAt < lastCreatedAt` hoặc `createdAt == lastCreatedAt AND _id > lastId`. Cursor cần ràng buộc tenant, filter và version, thường đóng gói thành **opaque token có integrity protection**.

### 27.3. Không tin cursor do client tự sửa

Nếu token chứa `tenantId` mà client đổi được, nó có thể trở thành đường đọc dữ liệu khác. Cần ký/kiểm tra integrity, expiry và so với ngữ cảnh auth hiện tại.

### 27.4. Cursor API của từng hệ

- Cassandra: paging state theo query/driver; không tự phát lại token bất kỳ không kiểm chứng.
- DynamoDB: `LastEvaluatedKey`/`ExclusiveStartKey`, dùng cùng điều kiện Query và tenant scope.
- MongoDB: cursor/keyset filter với sort ổn định.
- Search engine: `search_after`/continuation theo index/consistency policy.

**Không mặc định pagination token giữa hai query shapes có thể dùng lại.**

---

## 28. Giới hạn hiệu năng và chi phí như một lớp an toàn

Một câu query có bind hoàn hảo vẫn có thể gây **denial of service do thuật toán/truy cập dữ liệu**.

### 28.1. Các giới hạn nên có

- Max result count/page size.
- Max input length và số predicate.
- Max range duration (ví dụ không cho search mặc định 10 năm).
- Query deadline/server time limit khi engine hỗ trợ.
- Rate limit và concurrency bulkhead theo endpoint.
- Hạn chế fan-out/scan và số partitions touched.
- Dùng index phù hợp.
- Throttle expensive analytics.
- Cache cho workload đọc nóng phù hợp freshness contract.

### 28.2. “Prepared” không chứng minh query có index

Một query theo `customerId` nhưng partition key là `orderId` có thể cần scatter-gather hoặc secondary index. Trong Cassandra, một query khác partition key có thể không chạy hợp lệ nếu thiếu schema phù hợp.

### 28.3. Read amplification và hot keys

Ngay cả point query có thể chậm nếu hot partition hoặc replication lag lớn. Cần metric key/shard và bảo vệ overload, không chỉ thêm một prepared statement.

### 28.4. Thử nghiệm với dữ liệu skewed

Test với một triệu records phân đều chưa chắc phản ánh tenant lớn với 80% traffic. Dùng tập dữ liệu đại diện để xem p95/p99 và chi phí truy vấn dưới burst.

---

## 29. Read/write consistency và prepared statement

Query API an toàn **không xác định mức nhất quán** của database.

### 29.1. Cassandra

Consistency level và serial consistency của LWT ảnh hưởng số replicas/quorum theo semantics engine. `PreparedStatement` chủ yếu xác định query shape và bound types; không tự chọn mức bảo đảm phù hợp nghiệp vụ.

### 29.2. MongoDB

`readConcern`, `writeConcern`, `readPreference`, sessions/transactions ảnh hưởng visibility, durability và read-your-writes. `Filters.eq` không làm secondary lag biến mất.

### 29.3. DynamoDB

Read consistency options khác nhau theo operation/index. GSI có semantics visibility riêng; query placeholders không bảo đảm đọc thấy mutation vừa ghi.

### 29.4. Redis

Lệnh có thể nguyên tử trong phạm vi key/command, nhưng durability và replica failover phụ thuộc cấu hình/vòng đời; `GET(key)` được gọi bằng API typed không đồng nghĩa read luôn mới theo mọi failover.

### 29.5. Bảo vệ bất biến bằng authority

Nếu quyết định “còn một vé duy nhất” dựa vào read stale rồi ghi, hệ có thể double-booking. Cần conditional writes/transactions hoặc reservation authority phù hợp, dù mọi filter values đều đã bind.

---

## 30. Timeout, retry và unknown outcomes

Java drivers/SDKs có retry policy và timeout riêng. Trước khi tạo retry trong controller, phải hiểu retry đã có ở tầng driver.

### 30.1. Read retry

Một read không gây side effect có thể retry một số lỗi tạm thời nếu còn deadline. Nhưng retry nhiều lần khi backend đang quá tải có thể gây **retry storm**.

### 30.2. Write retry

Một write timeout có thể đã được commit. Không tự phát lại:

```java
// Rủi ro nếu không có operation ID/guard:
// UPDATE balance = balance + amount
```

mà chưa biết effect trước đó có xảy ra. Dùng idempotency key, conditional write, unique operation IDs hoặc đối soát theo contract.

### 30.3. Deadline đầu-cuối

Nếu API chỉ có 300 ms còn lại, không nên thực hiện ba lần query mỗi lần timeout 300 ms. Chia ngân sách thời gian và dừng khi hết deadline.

### 30.4. Circuit breaker và bulkhead

Nếu dependency lỗi kéo dài, breaker giúp fail fast; bulkhead giới hạn số threads/connections bị giữ. Nhưng chúng không thay `tenantId` filter, business invariant hoặc prepared binding.

---

## 31. Connection/session lifecycle và secrets

Một API query tốt vẫn cần quản lý driver đúng.

### 31.1. Dùng lại client/session

- `MongoClient` thường được tái sử dụng để tận dụng connection pool.
- `CqlSession` dùng lại theo application lifetime.
- `DynamoDbClient` và Neo4j `Driver` được quản lý như resources của ứng dụng theo lifecycle phù hợp.
- Redis connection/client pools phải được cấu hình quota/timeout.

Không mở một TCP/TLS connection mới cho mỗi query trừ khi API/lifecycle thực sự yêu cầu.

### 31.2. Cấu hình TLS và credentials

- Không hardcode password/API keys vào code ví dụ production.
- Dùng secret manager/environment injection phù hợp.
- Bật TLS theo security policy.
- Dùng database credentials với **quyền tối thiểu** cho repository.
- Tách read-only/reporting credentials nếu phù hợp.

### 31.3. Đừng log statement kèm secret

CQL query shape có thể an toàn để log theo policy; nhưng bound values có thể chứa PII, token hoặc giá trị nhạy cảm. Log query names/hash và thời gian, hạn chế giá trị cụ thể.

### 31.4. Lifecycle và shutdown

Đóng client/pool khi application shutdown; tránh per-request close khiến pool churn và lỗi cạnh tranh khi concurrent requests vẫn chạy.

---

## 32. Quan sát truy vấn: bảo mật đi kèm khả năng vận hành

| Metric | Câu hỏi |
| --- | --- |
| Query template ID | Endpoint đang dùng query shape nào? |
| Latency p50/p95/p99 | Tải nghiệp vụ có chậm? |
| Timeout/error/throttle rate | Backend có quá tải hoặc lỗi? |
| Result count và bytes | Có endpoint trả dữ liệu quá nhiều? |
| Rows/docs/keys examined | Scan amplification có lớn? |
| Partition/shard fan-out | Query có định tuyến đúng không? |
| Connection pool wait | Có thiếu connections? |
| Retry count | Retry có khuếch đại tải? |
| Query plan/index use | Có dùng access path phù hợp? |
| Tenant authorization rejects | Có truy vấn vượt scope? |
| Invalid field/operator rejects | Có client cố gửi DSL không hợp lệ? |
| Cursor tamper rejects | Có token pagination bị sửa? |
| Unknown write outcomes | Có ghi chưa rõ kết quả? |
| Prepared cache/reprepare events | Driver có overhead bất thường? |

### 32.1. Label metrics vừa đủ

Không gắn `userId`, `orderId`, raw search text vào metric labels vì dễ nổ cardinality hoặc lộ PII. Dùng `queryName`, `operation`, `resultClass`, `tenantTier` và bucket latency phù hợp.

### 32.2. Phân biệt business failure với dependency failure

Một conditional write bị từ chối vì order đã `CANCELLED` không nhất thiết là outage. Đếm thành metric conflict/business result thay vì khiến breaker mở trên những kết quả hợp lệ.

### 32.3. Query plan là bằng chứng, không chỉ cảm giác

Với MongoDB có thể dùng `explain("executionStats")` trong môi trường phân tích. Cassandra có tracing/profiling theo phiên bản và metrics. DynamoDB có consumed capacity. Mỗi hệ cần công cụ quan sát phù hợp; không đoán hiệu năng từ tên API.

---

# Phần V — Một thiết kế endpoint an toàn từ đầu tới cuối

## 33. API tìm kiếm đơn theo customer: contract

Đề xuất endpoint:

```http
GET /v1/orders?customerId=c42&status=PAID&sort=newest&pageSize=25
Authorization: Bearer ...
```

Backend không cho client truyền raw CQL/BSON. Request chỉ có các trường nghiệp vụ đã định nghĩa.

### 33.1. Input contract

```text
customerId: text hợp lệ, tối đa 100 ký tự
status: PENDING | PAID | CANCELLED
sort: newest | oldest
pageSize: integer 1..50
pageToken: opaque, optional
```

Đây là **giới hạn ví dụ**; giá trị production cần phù hợp domain và benchmark.

### 33.2. Context tin cậy

```text
authContext:
  userId = u7
  tenantId = tenant-a
  roles = [ORDER_READER]
```

`tenantId` phải đến từ authorization context đã được kiểm chứng, không lấy lại từ query string.

### 33.3. Trường được trả

```json
{
  "items": [
    {
      "orderId": "o1001",
      "status": "PAID",
      "createdAt": "2026-11-14T08:00:00Z",
      "totalMinorUnits": 125000
    }
  ],
  "nextPageToken": null
}
```

Không trả raw database documents nếu chúng có field nội bộ không thuộc response contract.

---

## 34. Tách controller, service và repository

Một kiến trúc nên rõ trách nhiệm:

```text
HTTP Controller
  |
  +-- Parse DTO và validate
  |
  v
OrderApplicationService
  |
  +-- Authorization, tenant scope, business rules
  |
  v
OrderRepository
  |
  +-- Query template/typed builders
  +-- Bind values
  +-- Limit/sort/projection/index contract
  |
  v
NoSQL Driver
  |
  +-- Encode/protocol/timeout/pool
  |
  v
Database
```

### 34.1. Controller không xây CQL tự do

Controller nhận HTTP request và gọi service qua domain DTO; không tự ghép string query từ parameters.

### 34.2. Repository không tự lấy tenant tùy ý

Repository nên có chữ ký buộc truyền `authorizedTenantId` hoặc một `TenantScope` value object. Một method không tenant scope phải được đánh dấu riêng cho admin/system use và bảo vệ RBAC.

### 34.3. Domain service chịu business rules

`CancelOrder` không chỉ là `Updates.set("status","CANCELLED")`. Nó còn kiểm tra trạng thái thanh toán, giao hàng, quyền người gọi và phát event/outbox khi cần.

### 34.4. Không lẫn input DTO với persistence object

Dữ liệu từ request chỉ được map vào field hợp lệ. Không deserialise nguyên request thành database document rồi `replaceOne` cho mọi field.

---

## 35. Java: một filter compiler có allowlist

Giả sử API hỗ trợ lọc `status` và sắp xếp theo `newest/oldest`, không cho client gửi raw BSON.

```java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.conversions.Bson;

import java.util.Objects;

public final class SafeOrderQuery {

    public enum SortOption {
        NEWEST, OLDEST
    }

    public static Bson buildFilter(
            String authorizedTenantId,
            String customerId,
            String status
    ) {
        Objects.requireNonNull(authorizedTenantId);
        Objects.requireNonNull(customerId);

        Bson scope = Filters.and(
            Filters.eq("tenantId", authorizedTenantId),
            Filters.eq("customerId", customerId)
        );

        if (status == null) {
            return scope;
        }

        if (!status.equals("PENDING")
                && !status.equals("PAID")
                && !status.equals("CANCELLED")) {
            throw new IllegalArgumentException("Invalid status");
        }

        return Filters.and(
            scope,
            Filters.eq("status", status)
        );
    }

    public static Bson buildSort(SortOption option) {
        return switch (option) {
            case NEWEST -> Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.ascending("_id")
            );
            case OLDEST -> Sorts.orderBy(
                Sorts.ascending("createdAt"),
                Sorts.ascending("_id")
            );
        };
    }
}
```

### 35.1. Vì sao an toàn về cấu trúc?

- Filter fields là constants.
- Operator là `eq/and` do code chọn.
- Client chỉ chọn status trong tập hợp cho phép.
- Tenant scope luôn hiện diện.
- Sort dùng enum chứ không nhận field path tùy ý.

### 35.2. Vẫn cần test authorization

Nếu `authorizedTenantId` được lấy sai từ client, filter vẫn sẽ đọc sai tenant. Binding không xác thực nguồn của tham số.

### 35.3. Vẫn cần pagination/index

Build filter đúng không có nghĩa số kết quả hữu hạn. Phần gọi MongoDB phải áp `limit`, sort, cursor và deadline.

---

## 36. Kiểm thử injection theo đúng giao diện

Một test suite nên đưa các input lạ vào **những trường mà API công bố là string/value**, rồi xác nhận truy vấn không đổi cấu trúc.

### 36.1. Bộ giá trị thử

```text
1. ""
2. "normal-user"
3. "' OR '1'='1"
4. "\"}, {\"$or\": [{\"status\": \"PAID\"}]"
5. "$ne"
6. "{\"$ne\": null}"
7. "A\\B"
8. "line1\nline2"
9. " a.* "
10. Chuỗi Unicode có dấu, emoji
11. Chuỗi rất dài vượt max length
12. UUID sai định dạng
```

Trong trường username/customerId string, các chuỗi trên phải được xem như **giá trị literal** hoặc bị từ chối bởi validation, không được biến thành query operators.

### 36.2. Đừng chạy payload tùy tiện trên dữ liệu production

Dùng dataset lab, quyền thấp và resource limits. Test security có thể gây tải nếu tự động phát raw regex/aggregation phức tạp.

### 36.3. Test chính xác điều gì?

- Không đọc bản ghi khác tenant.
- Không thay đổi query operator.
- Không bỏ qua authorization.
- Không trả quá page-size.
- Không trừ tồn kho nếu precondition không đạt.
- Không rò rỉ stack trace hoặc credentials.
- Error được map đúng thành lỗi input hay dependency.
- Không tạo retry storm khi backend chậm.

### 36.4. Chỉ assert lỗi syntax là chưa đủ

Nếu input chứa `"$ne"` và API trả lỗi parser, có thể query đang bị ghép chuỗi sai; không nên xem “không trả dữ liệu” là bằng chứng code đã an toàn. Cần test rằng **input vẫn được mã hóa thành giá trị** hoặc bị reject ở validation layer.

---

## 37. Kiểm thử tích hợp với dữ liệu giả lập nhiều tenant

Tạo tối thiểu:

```text
Tenant A:
  order A1, customer c42, status PAID
  order A2, customer c42, status PENDING

Tenant B:
  order B1, customer c42, status PAID
  order B2, customer c99, status CANCELLED
```

Dùng **cùng customerId `c42` ở hai tenants** để kiểm tra scope. Chỉ dùng dữ liệu giả.

### 37.1. Trường hợp bắt buộc

1. User tenant A tìm `c42` chỉ thấy A1/A2.
2. User tenant B tìm `c42` chỉ thấy B1.
3. User A nhập `_id=B1` vẫn không đọc được B1.
4. Sort field không thuộc allowlist bị từ chối.
5. Page-size quá lớn bị reject/clamp theo contract.
6. Query thiếu partition key không vô tình phát scan toàn hệ.
7. Cancellation có expected state/version; hai lệnh đồng thời không cùng được áp dụng sai.
8. Khi database timeout, API không suy write chắc chắn thất bại.
9. Cùng cursor cũ nhưng đổi tenant/filter phải bị từ chối.
10. Một query hợp lệ nhưng không có index phải được phát hiện trong performance test.

### 37.2. Kiểm tra tầng thực

Unit test query builder không thay integration test với database thực vì BSON serialization, driver errors, query plan và consistency có thể khác kỳ vọng.

### 37.3. Test dưới concurrency

Thử hàng trăm requests đồng thời trên những ID khác nhau để phát hiện reuse mutable query builder, session lifecycle sai hoặc shared state giữa requests.

---

## 38. Mẫu đối chiếu “sai và đúng”

| Mục tiêu | Mẫu có rủi ro | Mẫu nên cân nhắc |
| --- | --- | --- |
| Tìm Cassandra order | Ghép `tenantId` vào chuỗi CQL | `session.prepare` + `bind` |
| Tìm MongoDB order | Ghép JSON rồi `Document.parse` | `Filters.eq/and` với values typed |
| Search nâng cao MongoDB | Forward raw `$or/$where` từ client | Validate DTO/AST và whitelist |
| DynamoDB Query | Ghép value vào expression literal | `ExpressionAttributeValues` |
| DynamoDB field động | Client tự chọn tên mọi attribute | `ExpressionAttributeNames` + field allowlist |
| Cypher | `"WHERE id='" + id + "'"` | `$id` parameter |
| Redis | Ghép source code Lua từ input | Script cố định + `KEYS/ARGV` |
| Tenant access | `findById(id)` không scope | `findByIdAndTenant(id, authTenant)` |
| Sort | `sort(clientField)` tùy ý | Enum → fixed sort definition |
| Pagination | `skip`/limit không giới hạn | Bounded page + opaque scoped cursor |
| Conditional write | Read state rồi update vô điều kiện | CAS/conditional update theo authority |
| Regex | Pattern raw không giới hạn | Escape literal/validate/index/time limit |
| Error handling | Ghi timeout thành chắc chắn fail | Unknown outcome + lookup/idempotency |
| Query performance | Tin rằng prepared luôn nhanh | Index/partition key/measure p99 |

---

## 39. Những sai lầm phổ biến

### 39.1. “NoSQL không có SQL nên không có injection”

Sai. CQL/Cypher/SQL++ có query syntax; MongoDB/Elasticsearch có structured operators; Redis scripts có mã được thực thi.

### 39.2. “Dùng `PreparedStatement` trên mọi NoSQL”

Không. MongoDB thường dùng typed BSON builders; DynamoDB dùng expression placeholders; Redis dùng command APIs.

### 39.3. “Escape dấu nháy là tương đương binding”

Không. Escaping phụ thuộc language/type/path; binding rõ ràng hơn và ít lỗi cấu trúc.

### 39.4. “Dùng `Filters.eq` thì ứng dụng chắc chắn secure”

Không. Có thể quên tenant filter, cấp quyền sai hoặc query quá đắt.

### 39.5. “Bất kỳ JSON nào do client gửi cũng là filter hợp lệ”

Không. JSON object có thể chứa operators/stages ngoài quyền. Cần DTO/AST và allowlist.

### 39.6. “Có thể bind tên bảng như bind tenant ID”

Thông thường không. Identifiers và values là hai vùng cú pháp khác nhau; cần template/allowlist.

### 39.7. “Tên field được gửi từ client cũng an toàn vì dùng builder”

Không tự động. Một builder vẫn có thể tạo query tới field nhạy cảm nếu client chọn field path.

### 39.8. “Prepared CQL luôn nhanh”

Sai. Query thiếu partition key/index hoặc quét quá nhiều rows vẫn chậm.

### 39.9. “DynamoDB FilterExpression tiết kiệm mọi I/O”

Không. Filter có thể được áp sau việc đọc items theo Query semantics; cần key condition và thiết kế bảng.

### 39.10. “Cứ tăng `limit` là tăng hiệu năng”

Trả quá nhiều bản ghi có thể tăng network/CPU và latency. Limit cần được ràng buộc.

### 39.11. “Regex đã escape là luôn rẻ”

Không. Nó có thể scan nếu không dùng index hoặc input làm access path kém.

### 39.12. “Có tenantId trong request nghĩa là được xem tenant đó”

Không. Tenant scope phải dựa trên danh tính/quyền đã xác thực.

### 39.13. “Cùng customerId ở mọi tenant sẽ không xảy ra”

ID phạm vi tenant thường có thể trùng. Cần test dữ liệu đa tenant thực tế.

### 39.14. “Read preference secondary luôn đúng cho mọi endpoint”

Không. Dữ liệu có thể lag; nghiệp vụ cần read-your-writes hoặc authority khác.

### 39.15. “Write timeout nghĩa là chưa commit”

Không chắc. Không retry một non-idempotent operation bằng ID mới.

### 39.16. “Driver đã retry nên không cần nhìn retry ở app”

Hai tầng có thể retry nhân nhau. Cần hiểu driver behavior và retry budget.

### 39.17. “Kiểm tra sort enum chỉ phục vụ UX”

Nó cũng chặn client chỉ định field ngoài quyền và giới hạn chi phí index.

### 39.18. “Pagination token là dữ liệu vô hại”

Nó có thể chứa tenant, filter và vị trí dữ liệu. Cần bảo vệ integrity/scope/expiry.

### 39.19. “Cần log tất cả bound values để debug”

Không. Có thể lộ PII, token hoặc search terms nhạy cảm; log có policy.

### 39.20. “Một unit test query builder đủ chứng minh an toàn”

Không. Cần integration/authorization/concurrency/performance tests trên dữ liệu đại diện.

---

## 40. Bài tập thực hành

### Bài 1 — Tìm lỗi CQL

Vì sao câu Java sau có rủi ro?

```java
String q = "SELECT * FROM t WHERE username='" + username + "'";
```

**Gợi ý:** `username` có thể bị diễn giải thành một phần cú pháp truy vấn.

### Bài 2 — Sửa bằng bound statement

Viết phiên bản an toàn của:

```sql
SELECT status FROM commerce.orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

**Gợi ý:** Prepare một lần, bind string tenant đã xác thực và UUID hợp lệ cho mỗi request.

### Bài 3 — Kiểu dữ liệu

Một route nhận `orderId` là string nhưng Cassandra cột `order_id` là UUID. Nên xử lý thế nào?

**Gợi ý:** Parse UUID tại boundary, trả 400 khi sai, bind kiểu UUID.

### Bài 4 — Bind tên bảng

Có thể viết `SELECT * FROM ?` rồi bind `"orders"` như tên bảng không?

**Gợi ý:** Không theo prepared CQL thông thường; dùng query templates/allowlist identifiers.

### Bài 5 — Chuẩn bị ở đâu?

Một service có 50.000 requests/minute sử dụng 3 query shapes. Có nên gọi `prepare` cho mỗi request?

**Gợi ý:** Thường prepare/cached theo query shape rồi bind nhiều lần.

### Bài 6 — Query thiếu khóa

Prepared query lọc `status` nhưng bảng Cassandra keyed theo `(tenantId, orderId)`. Vì sao có thể không phù hợp?

**Gợi ý:** Prepared không thay partition-key access path; cần bảng/query theo truy cập.

### Bài 7 — MongoDB operator

Client gửi JSON:

```json
{"status": {"$ne": null}}
```

Một API muốn status **chỉ là string** phải xử lý thế nào?

**Gợi ý:** Reject object sai schema; không nhận raw query operator.

### Bài 8 — MongoDB typed filter

Viết `Filters.and` cho `_id=orderId`, `tenantId=authorizedTenantId` và `status="PAID"`.

**Gợi ý:** Các field constants, dữ liệu nhập vào `Filters.eq`.

### Bài 9 — Không đưa tenant trong query

Một repository chỉ `Filters.eq("_id", orderId)`. Có thể lỗi gì dù không có injection?

**Gợi ý:** IDOR/cross-tenant access.

### Bài 10 — Regex literal

User tìm prefix `"a.*"` nhưng muốn đúng các ký tự đó. Vì sao dùng raw regex có thể sai?

**Gợi ý:** `.*` được hiểu như metacharacters; dùng `Pattern.quote` nếu tìm literal.

### Bài 11 — Dynamic sort

API nhận `sortField` là string tùy ý. Hãy thiết kế enum `NEWEST`, `OLDEST`.

**Gợi ý:** Ánh xạ enum sang các `Sorts` cố định.

### Bài 12 — Unsafe pipeline

Một admin API nhận toàn bộ MongoDB aggregation JSON rồi chạy thẳng. Có những rủi ro nào?

**Gợi ý:** Operator/stage ngoài quyền, scan nặng, truy cập dữ liệu nhạy cảm; cần grammar và RBAC.

### Bài 13 — DynamoDB Query

Vì sao expression nên dùng `#pk = :pk` với names/values maps?

**Gợi ý:** Tách tên thuộc tính/value khỏi expression syntax; dùng type-safe `AttributeValue`.

### Bài 14 — DynamoDB Scan

Query theo `tenantId` nhưng table partition key là `orderId`. Cho `FilterExpression tenantId=:t` có làm Query targeted tự động không?

**Gợi ý:** Không; cần key/index phù hợp, filter không tự đổi key schema.

### Bài 15 — Redis key

Hai users có IDs chứa dấu `:`. Làm sao tránh collision khi ghép key?

**Gợi ý:** Key factory với component encoding hoặc length-prefix; tenant từ auth.

### Bài 16 — Lua injection

Vì sao không nối user input vào source Lua script?

**Gợi ý:** Input có thể thay code; script cố định và data qua KEYS/ARGV.

### Bài 17 — Neo4j

Viết Cypher query có `$tenant` và `$id` thay vì nối ID literal.

**Gợi ý:** `MATCH (o:Order {tenantId:$tenant,id:$id}) RETURN ...`.

### Bài 18 — Time range

Client đặt `createdAfter=1900-01-01`, `createdBefore=2100-01-01`. Bind đúng đã đủ chưa?

**Gợi ý:** Chưa; validate max range, index và query budget.

### Bài 19 — Pagination

Tại sao `limit=20` vẫn có thể phải xử lý nhiều items trong DynamoDB khi có filter?

**Gợi ý:** Filter/processed items semantics và `LastEvaluatedKey`.

### Bài 20 — Cursor scope

User đổi tenant nhưng giữ page token cũ. Cần kiểm tra gì?

**Gợi ý:** Cursor integrity, tenant/filter/sort binding và expiry.

### Bài 21 — Unknown write

Java driver báo timeout sau `UPDATE` có condition. Có được kết luận không có update không?

**Gợi ý:** Không. Đọc/đối soát state hoặc retry theo semantics/idempotency.

### Bài 22 — Security vs consistency

`Filters.eq` an toàn cú pháp, nhưng read từ replica lag cho thấy order chưa thanh toán. Có thể dựa vào đó để charge lại không?

**Gợi ý:** Không. Cần payment authority/idempotency và consistency policy phù hợp.

### Bài 23 — Connection pool

Một controller tạo `MongoClient` mới cho mỗi GET. Có vấn đề gì?

**Gợi ý:** Pool churn, TLS/connection overhead, resource exhaustion.

### Bài 24 — Logs

Người dùng nhập search text chứa API token. Có nên ghi raw bound values vào log?

**Gợi ý:** Không; structured logs, redact, query template ID và metric.

### Bài 25 — Test injection

Đưa các chuỗi `"'"`, `"$ne"`, `"{\"$ne\":null}"` vào field `username` dạng string. Kết quả đúng là gì?

**Gợi ý:** Chúng là literal values hoặc bị validation reject; không biến query structure.

### Bài 26 — Test đa tenant

Tạo tenant A/B có cùng `customerId=c42`. Viết ít nhất ba integration tests bắt lỗi lọc thiếu tenant.

**Gợi ý:** List, point read và update/delete đều cần scope.

### Bài 27 — Hiệu năng

Một truy vấn prepared có p99 4 giây và `docsExamined` hàng triệu. Hãy nêu ba nhóm điều tra.

**Gợi ý:** Index/partition key, fan-out/hot keys, query/result limits và resource pressure.

### Bài 28 — Thiết kế API cuối khóa

Thiết kế endpoint `GET /orders` cho ứng dụng Java nhiều tenants dùng MongoDB hoặc Cassandra. Nêu:

1. Request DTO và validation.
2. Nguồn `tenantId` tin cậy.
3. Cấu trúc truy vấn và cách bind values.
4. Field/operator/sort allowlist.
5. Index/partition-key strategy.
6. Pagination và cursor protection.
7. Timeout và giới hạn tài nguyên.
8. Read consistency và lỗi kết quả không rõ.
9. Logging/metrics không lộ secrets.
10. Các unit, integration và load tests bắt buộc.

**Gợi ý:** Viết query an toàn nhưng quên tenant, quên phân vùng hoặc quên giới hạn quét vẫn chưa phải một API truy vấn an toàn.

---

## 41. Checklist triển khai API truy vấn an toàn với Java và NoSQL

### A. Xác thực ranh giới dữ liệu

1. Mỗi endpoint có request DTO/schema rõ ràng.
2. Trường input có kiểu, độ dài, miền giá trị và cardinality limits.
3. `tenantId`/owner scope lấy từ authentication và authorization context.
4. Không chấp nhận raw CQL/Cypher/BSON/DSL trừ khi có policy admin cực kỳ chặt.
5. Không truyền thẳng request object vào database update.

### B. Cấu trúc truy vấn

6. Query shape, field, operator và collection/table do server quyết định.
7. Dùng `prepare/bind` của CQL và query languages tương ứng.
8. Dùng typed BSON `Filters/Updates/Aggregates` với MongoDB.
9. Dùng expression attribute values/names và allowlist với DynamoDB.
10. Dùng command arguments, key factory và script parameters với Redis.
11. Dùng query parameters và allowlist với Cypher/SQL++.
12. Không tự escape rồi nối input vào một chuỗi truy vấn.
13. Không coi identifiers là bindable values trong mọi ngôn ngữ.
14. Dùng typed sort/filter enums và query templates hữu hạn.

### C. Tính đúng và quyền truy cập

15. Scope tenant áp ở read, update, delete, index/read model.
16. Projection/response schema chỉ trả dữ liệu được phép.
17. Conditional update/CAS/transaction bảo vệ invariants.
18. Không coi prepared binding là consistency guarantee.
19. Chọn read/write concerns và retry behavior theo nghiệp vụ.
20. Ghi có kết quả không rõ phải có idempotency/đối soát.

### D. Chi phí và độ bền vận hành

21. Query có đủ partition key hoặc index phù hợp.
22. Giới hạn result count, time range, input list size và scan/fan-out.
23. Phân trang bằng cursor/keyset có scope/integrity/expiry rõ.
24. Thiết lập deadline, timeouts, rate limits và concurrency budgets.
25. Quản lý driver clients/sessions/pools theo lifecycle.
26. Dùng TLS, secrets management và database least privilege.
27. Không log sensitive bound values hay tạo metric cardinality quá cao.
28. Test payload injection, cross-tenant access và dynamic fields.
29. Test under concurrency, hot partitions và replica lag.
30. Theo dõi p99, scan amplification, retry, pool wait và errors.
31. Kiểm tra khả năng đổi schema/index/query shape mà không phá endpoint.
32. Tài liệu hóa ranh giới bảo đảm của từng driver và version.

### Bảng quyết định cuối

| Tình huống | Lựa chọn trọng tâm | Lưu ý |
| --- | --- | --- |
| CQL trong Java | Prepare + bind typed values | Không bind table name |
| MongoDB Java | BSON typed builders | Không nhận raw operator/pipeline |
| Spring Data MongoDB | Query/Criteria và repository scoped | Framework không tự bảo vệ tenant |
| DynamoDB | Expression placeholders + key design | `FilterExpression` không thay partition key |
| Redis | Fixed command APIs + key factory | Keyspace/auth và Lua script injection |
| Neo4j/Cypher | Parameterized query | Label/property/relationship allowlist |
| Couchbase SQL++ | SDK query parameters | Keyspace/index identifiers theo policy |
| Advanced search | Validated DTO/AST → query builder | Tránh arbitrary DSL từ client |
| Multi-tenant data | Auth-derived tenant + scoped query | Binding không ngăn IDOR |
| Conditional write | CAS/condition/transaction | Timeout có thể unknown |
| Paging nhiều records | Bounded page + protected cursor | Không cho scan/offset tùy ý |
| Query chậm dù đã prepared | Index, shard key, resource budgets | Prepared không tạo locality |
| Backend lỗi | Timeout, breaker, retry budget | Giữ idempotency và consistency |
| Audit/tracing | Query template IDs + redacted logs | Không lộ dữ liệu bound |

**Kết luận:** Một **API truy vấn an toàn trong Java với NoSQL** phải tách **cấu trúc truy vấn** khỏi **giá trị đầu vào** bằng cơ chế phù hợp với driver: CQL prepared/bound statements, MongoDB typed BSON builders, DynamoDB expression placeholders, Redis command arguments hoặc Cypher/SQL++ parameters. Nhưng an toàn không kết thúc ở bind markers. Ứng dụng còn phải xác định **ai được truy cập dữ liệu nào**, cho phép **field/operator** nào, giới hạn **kích thước và chi phí truy vấn**, chọn **index/partition key** đúng, xử lý **consistency, retries và unknown write outcomes**, đồng thời bảo vệ **logs, cursors và connection pools**. Binding ngăn dữ liệu bị biến thành cú pháp; thiết kế API và các bất biến nghiệp vụ mới quyết định truy vấn có thực sự **đúng, an toàn và vận hành được dưới tải** hay không.
