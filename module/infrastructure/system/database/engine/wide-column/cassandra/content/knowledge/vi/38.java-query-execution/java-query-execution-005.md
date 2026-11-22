# QueryBuilder, identifier và tránh nối đầu vào vào CQL

> **Chương:** Truy vấn từ Java  
> **Mô-đun:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra: kiến trúc phân tán và wide-column, partition key, thiết kế bảng theo truy vấn, mức nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và ứng dụng Java.  
> **Trọng tâm:** Dựng truy vấn động bằng **Apache Cassandra Java Driver 4.x QueryBuilder**; phân biệt **identifier** (tên keyspace/bảng/cột) với **value** (giá trị tham số); sử dụng `CqlIdentifier` và **bind markers** để tránh nối đầu vào không đáng tin trực tiếp vào CQL.

Một ứng dụng cho người dùng tìm đơn hàng theo tenant, ngày và khoảng thời gian rất dễ viết sai:

```java
// KHÔNG DÙNG: lấy đầu vào trực tiếp ghép vào cấu trúc CQL.
String cql = "SELECT * FROM app.orders_by_tenant_day "
    + "WHERE tenant_id = " + tenantFromHttp
    + " AND order_day = '" + dateFromHttp + "'";
session.execute(cql);
```

Ngay cả khi đầu vào “thường là ngày hợp lệ”, cách trên làm trộn **cú pháp CQL** với **dữ liệu từ request**. Nó mở ra lỗi quote, parse/type coercion và nguy cơ *CQL injection*; kiểm thử bằng một giá trị có dấu nháy đơn cũng có thể phát hiện lỗi. Việc dùng `QueryBuilder` giúp xây dựng cấu trúc truy vấn rõ hơn, nhưng **không tự biến mọi chuỗi từ người dùng thành an toàn**. Cách bảo vệ chính là:

1. **Giá trị động** → `bindMarker()` trong CQL đã chuẩn bị và bind đúng kiểu bằng `PreparedStatement/BoundStatement`.
2. **Identifier động** (tên bảng, cột, keyspace) → **allowlist/mapping từ lựa chọn nghiệp vụ** sang `CqlIdentifier`, không dùng bind marker cho identifier.
3. **CQL fragment động** (WHERE tùy chọn, ORDER BY, LIMIT) → dựng bằng **DSL có cấu trúc** và chỉ cho phép *các query shapes đã được thiết kế theo partition key*, thay vì nhận đoạn CQL tự do.
4. **Quyền dữ liệu** → CQL authentication/authorization và tenant scope; escaping/quoting **không phải authorization**.

Bài học này hướng dẫn từ ví dụ sai đến cách triển khai đúng, kèm lab CQL, Java Driver 4.x, kiểm thử, hiệu năng, sự cố và checklist code review.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ranh giới giữa **CQL syntax**, **schema identifier** và **bound data value**.
2. Biết khi nào dùng `SimpleStatement`, `PreparedStatement`, `BoundStatement` và `QueryBuilder`.
3. Thêm dependency của module `java-driver-query-builder` tương thích với Java Driver core.
4. Sử dụng `selectFrom`, `insertInto`, `update`, `deleteFrom` và `bindMarker` theo API 4.x.
5. Phân biệt `CqlIdentifier.fromCql(...)` và `fromInternal(...)`; xử lý case sensitivity, tên có dấu cách/keyword/dấu nháy.
6. Hiểu vì sao **bind marker không thay được tên bảng/cột hoặc ORDER BY direction**.
7. Thiết kế **allowlist** cho projection, table choice, sorting và optional filters, không cho phép CQL tự do từ HTTP.
8. Kiểm tra query shape theo partition/clustering key để tránh `ALLOW FILTERING` và scans tốn tài nguyên.
9. Tái sử dụng prepared query thay vì dựng CQL cho mỗi request, quản lý cache hữu hạn.
10. Kiểm thử đầu vào đặc biệt, tenant isolation, lỗi kiểu dữ liệu và các yêu cầu bảo mật.
11. Phân tích timeout/retry, consistency level, paging và observability khi truy vấn được dựng động.
12. Xây dựng repository Java có `CqlSession` dùng chung, bind parameters và validation rõ ràng.

## 2. Ba tầng trong một câu CQL

Xét truy vấn:

```sql
SELECT event_time, event_type
FROM app.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 50;
```

Phân loại:

| Thành phần | Ví dụ | Vai trò | Có nên lấy trực tiếp từ HTTP? |
|---|---|---|---|
| Keyword/cấu trúc | `SELECT`, `FROM`, `WHERE`, `LIMIT` | Ngữ pháp CQL | Không |
| Keyspace identifier | `app` | Chọn namespace/schema | Không; lựa chọn từ allowlist |
| Table identifier | `events_by_tenant_day` | Chọn layout dữ liệu | Không; lựa chọn từ allowlist |
| Column identifier | `tenant_id`, `event_day` | Đường truy cập và định tuyến | Không; lựa chọn từ schema/allowlist |
| Value | UUID tenant, ngày | Dữ liệu so khớp | **Có, qua bind markers** |
| Numeric policy | Giới hạn trả hàng tối đa | Bảo vệ API/cluster | Giá trị đầu vào phải validate/clamp |
| Query plan shape | Có/không range theo clustering | Xác định lượng dữ liệu đọc | Chọn từ các phương án đã hỗ trợ |
| Authentication context | Service account/tenant identity | Xác định quyền dữ liệu | Không tin chỉ vào query parameter |

**Điểm dễ nhầm:** trong Java một tên bảng và một giá trị `String` đều là chuỗi, nhưng trong CQL chúng là **hai loại ngữ nghĩa khác nhau**. Quoting/escaping chuỗi Java bằng tay không thay được cơ chế bind của driver.

### 2.1. Bind marker là placeholder của *value*

```sql
-- Mẫu dùng để chuẩn bị qua Java Driver; cqlsh thường không chạy
-- trực tiếp dấu ? nếu không có cơ chế bind tương ứng.
SELECT account_id, display_name
FROM app.accounts_by_id
WHERE account_id = ?;
```

Driver/server biết dấu `?` là **giá trị ở vị trí điều kiện**, không phải một đoạn SQL/CQL được parse lại sau khi nhận value. Giá trị `O'Reilly` hoặc `a;b` được mã hóa theo codec của kiểu CQL, không bị coi như ký tự đóng literal hoặc dấu kết thúc lệnh.

### 2.2. Bind marker không biểu diễn tên bảng

```sql
-- Sai về ý nghĩa: CQL không thay table name bằng bind marker.
SELECT account_id FROM ? WHERE account_id = ?;

-- Sai: không dùng marker làm tên cột.
SELECT ? FROM app.accounts_by_id WHERE account_id = ?;
```

CQL phải biết **schema/column names** để phân tích câu lệnh và lập execution plan. Nếu người dùng được chọn một trong hai bảng nghiệp vụ, application phải **ánh xạ lựa chọn đó sang identifier đã cho phép**, rồi prepare statement cho query shape được chọn.

### 2.3. Bind marker không thay thế kiểm soát truy cập

Một câu query có bind marker đầy đủ vẫn có thể đọc dữ liệu tenant khác nếu ứng dụng bind sai `tenant_id`:

```java
// Query đã parameterized nhưng nếu tenantId lấy tự do từ request,
// API vẫn có thể bị lỗi phân quyền ngang (IDOR).
BoundStatement stmt = prepared.bind(tenantIdFromRequest);
```

Với multi-tenant API, tenant scope phải đến từ **identity đã xác thực** và policy của ứng dụng, không chỉ từ query string/body do caller cung cấp. CQL role permissions và audit vẫn cần áp dụng theo mô hình bảo mật.

## 3. Vì sao không nối đầu vào vào CQL?

### 3.1. Dữ liệu có dấu nháy không phải cú pháp

Một account có `display_name = "O'Reilly"` là dữ liệu hợp lệ. Cách nối:

```java
String unsafe = "SELECT account_id FROM app.accounts_by_id "
    + "WHERE display_name = '" + userName + "'";
```

có thể tạo một CQL literal sai khi `userName` chứa `'`. Nếu ứng dụng cũng cho phép các phần query động, rủi ro còn lớn hơn. Không nên tự sửa bằng `replace("'", "''")` rồi tiếp tục nối:

- Dễ bỏ sót khi dữ liệu là collection, UUID, timestamp, blob hoặc text Unicode.
- Mỗi vị trí CQL có quy tắc cú pháp khác nhau.
- Escaping một value không thể bảo vệ một **identifier** hoặc cả **WHERE fragment**.
- Thay đổi driver/CQL syntax có thể tạo chỗ hở mới.
- Logging string sau nối có thể làm lộ dữ liệu cá nhân.

### 3.2. CQL injection không nhất thiết giống SQL injection

Cassandra không phải một RDBMS chạy cùng loại SQL dialect hay hỗ trợ mọi cú pháp SQL. Một payload kiểu SQL chứa `UNION SELECT` hoặc nhiều câu lệnh phân tách bằng `;` có thể bị CQL parser từ chối. Điều đó **không chứng minh nối chuỗi là an toàn**:

- Input có thể làm biến đổi giá trị literal hoặc phá cú pháp.
- Một hệ tự ghép tên bảng/cột/sort có thể bị chuyển sang truy vấn ngoài phạm vi cho phép.
- Một fragment từ cấu hình hoặc UI có thể tạo `ALLOW FILTERING`/scan rộng hoặc lệnh thay đổi dữ liệu nếu được nhét trực tiếp.
- Query lỗi liên tục có thể tạo denial-of-service/log spam.
- Rủi ro bảo mật và đúng đắn tăng theo quyền của service account.

**Không dựa vào giả định “Cassandra chặn nhiều statements” làm biện pháp chống injection.** Thiết kế đúng là câu CQL có cấu trúc ổn định, values đi qua protocol binding và identifiers chỉ chọn từ allowlist.

### 3.3. Chỉ kiểm tra regex “chữ/số” không đủ

Ngay cả tên cột hợp lệ theo regex `[a-z_]+` vẫn có thể chọn một column nhạy cảm như `password_hash` hoặc một query shape cần quét rộng. **Kiểm tra cú pháp** và **cho phép về nghiệp vụ** là hai việc khác nhau.

Ví dụ một API chỉ cho chọn `display_name` và `account_state`. Kể cả `internal_notes` là identifier CQL hợp lệ, caller **không được phép** chọn nó nếu hợp đồng API không hỗ trợ.

## 4. QueryBuilder của Java Driver 4.x là gì?

### 4.1. Mô-đun riêng với driver core

Java Driver 4.x có module QueryBuilder để **tạo CQL theo fluent DSL**. Trong tài liệu Apache Cassandra Java Driver 4.19, ví dụ Maven dependency:

```xml
<dependency>
  <groupId>org.apache.cassandra</groupId>
  <artifactId>java-driver-query-builder</artifactId>
  <version>4.19.0</version>
</dependency>
```

Cần cấu hình **core driver** với phiên bản tương thích trong cùng build; dùng version đồng bộ theo BOM/dependency management của dự án. Ở các bản driver 4.x cũ hơn, Maven groupId có thể là `com.datastax.oss`. **Đọc POM/tài liệu của đúng version**, không dùng đồng thời hai nhóm artifact khác phiên bản một cách tùy ý.

Packages Java vẫn thường dùng namespace:

```java
import com.datastax.oss.driver.api.querybuilder.QueryBuilder;
import com.datastax.oss.driver.api.querybuilder.select.Select;
import com.datastax.oss.driver.api.core.CqlIdentifier;
```

### 4.2. QueryBuilder tạo câu CQL, CqlSession thực thi

```java
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select query = selectFrom("system", "local")
    .column("release_version");

// Lấy CQL text để xem trong test/debug (không có bound values).
String text = query.asCql();

// Chuyển thành statement rồi gửi qua session.
SimpleStatement statement = query.build();
Row row = session.execute(statement).one();
```

QueryBuilder **không tự kết nối** database và không tự chạy query. `CqlSession` vẫn chịu trách nhiệm prepare/execute, pool/metadata/CL/timeout, trong khi Cassandra server xác định replica/read path.

### 4.3. Fluent API là immutable

```java
Select base = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id");

Select withName = base.column("display_name");
Select withState = base.column("account_state");

// base, withName, withState là ba đối tượng query khác nhau.
```

Các bước builder thường **trả object mới**, không sửa object cũ. Do đó:

```java
// SAI: kết quả .whereColumn(...).isEqualTo(...) bị bỏ đi.
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id");
query.whereColumn("account_id").isEqualTo(bindMarker());

// ĐÚNG:
query = query.whereColumn("account_id").isEqualTo(bindMarker());
```

Khi điều kiện động có nhiều nhánh, phải gán lại `query = ...`. Nhờ immutability, có thể chia sẻ base query trong một thành phần khi dùng đúng, nhưng không nên build lại query ở mỗi call chỉ vì DSL trông gọn.

### 4.4. QueryBuilder không thay việc hiểu CQL

QueryBuilder không tự biết tất cả ràng buộc dữ liệu và workload:

- Nó có thể dựng câu query mà server từ chối vì thiếu partition key.
- Nó có thể sinh query cần `ALLOW FILTERING` hoặc scan rộng.
- Nó không chứng minh index/materialized view phục vụ query hiệu quả.
- Nó không tự cấp quyền database.
- Nó không tự chống multi-tenant data leaks khi mapping cho phép chọn bảng sai.
- Nó có API `raw(...)` để chèn đoạn CQL **nguyên văn**, không escaping/validation.

Hãy bắt đầu từ **CQL hợp lệ và mô hình bảng theo truy vấn**, sau đó mới chuyển sang builder DSL.

## 5. Ba lựa chọn: CQL string cố định, SimpleStatement và QueryBuilder

| Nhu cầu | Phương án thường hợp lý | Lý do |
|---|---|---|
| Truy vấn có shape cố định, chạy hàng nghìn lần | CQL text cố định + `session.prepare` | Dễ đọc, ít tạo objects, reusable |
| Query chỉ chạy hiếm, không có dynamic structure | `SimpleStatement` với bound values phù hợp | Ít setup, vẫn phải kiểm kiểu và bảo mật |
| Projection/WHERE/ORDER BY có vài biến thể đã thiết kế | `QueryBuilder` + bind markers + allowlist | Tránh tự nối syntax thủ công |
| Truy vấn động chạy nhiều lần cùng shape | QueryBuilder sinh query lúc init/lần đầu → `PreparedStatement` cache | Giảm chi phí prepare |
| Người dùng muốn chạy CQL bất kỳ | Không đưa thẳng vào service account | Phải dùng môi trường quản trị có ranh giới quyền riêng |
| ORM/DAO đơn giản, schema ổn định | Java Driver Mapper khi phù hợp | Giảm boilerplate, vẫn cần kiểm query semantics |
| Truy vấn analytic không có partition key | Chọn schema/query-first hoặc hệ analytics | Builder không biến scan thành nhẹ |

Một câu CQL chuẩn với markers **không kém an toàn** chỉ vì nó là String constant:

```java
PreparedStatement find = session.prepare(
    "SELECT account_id, display_name " +
    "FROM lab_java_query.accounts_by_id " +
    "WHERE account_id = ?");

Row row = session.execute(find.bind("user-001")).one();
```

Sai lầm cần tránh là **tạo CQL từ dữ liệu đầu vào**, không phải bản thân sự tồn tại của string literal ở source code.

## 6. Lab: schema phù hợp QueryBuilder

### 6.1. Điều kiện môi trường

Bài thực hành giả định Cassandra 4.x/5.x tương thích với Java Driver 4.x, local datacenter tên `dc1`, có CQL access, và **ít nhất ba full replicas ở dc1** nếu dùng RF=3. Với cluster một node trong lab, điều chỉnh RF=1; không giả định luôn có quorum RF=3.

```sql
CREATE KEYSPACE IF NOT EXISTS lab_java_query
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
```

### 6.2. Bảng accounts cho lookup chính xác

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.accounts_by_id (
    account_id text PRIMARY KEY,
    display_name text,
    account_state text,
    contact_email text
);
```

Truy vấn được thiết kế:

```sql
SELECT account_id, display_name, account_state
FROM lab_java_query.accounts_by_id
WHERE account_id = 'user-001';
```

**Không** thiết kế lookup thường xuyên bằng `WHERE display_name = '...'` trên bảng này nếu chưa có bảng phụ/index phù hợp. `display_name` là regular column, không có partition key trong WHERE của query đó.

### 6.3. Bảng events theo tenant/ngày

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
```

Ưu điểm của mô hình:

- `(tenant_id, event_day)` là composite partition key, định vị partition.
- `event_time` là clustering column đầu tiên, phù hợp range query trong một tenant/ngày.
- `event_id` phân biệt events có cùng timestamp.
- `event_type` là regular column: muốn lọc theo loại ở quy mô lớn, cân nhắc bảng `events_by_tenant_type_day` thay vì filter toàn lịch sử.
- Kích thước partition theo tenant/day vẫn phải được định cỡ; tenant quá nóng có thể cần bucket giờ/shard.

### 6.4. Dữ liệu thử với dấu nháy

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_java_query.accounts_by_id (
    account_id, display_name, account_state, contact_email
) VALUES (
    'user-001', 'O''Reilly', 'ACTIVE', 'demo@example.invalid'
);

INSERT INTO lab_java_query.accounts_by_id (
    account_id, display_name, account_state, contact_email
) VALUES (
    'user-002', 'Tên có dấu phẩy, dấu nháy '' và Unicode',
    'INACTIVE', 'demo2@example.invalid'
);

INSERT INTO lab_java_query.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    22222222-2222-4222-8222-222222222222,
    'LOGIN', 'payload-A'
);

INSERT INTO lab_java_query.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    33333333-3333-4333-8333-333333333333,
    'PURCHASE', 'payload-B'
);
```

Hai cột `account_id` và `tenant_id` chỉ dùng các giá trị giả. Các câu CQL với dấu nháy đơn đôi dùng quy tắc **literal text của CQL** khi nhập trực tiếp trong `cqlsh`; Java app nên bind values thay vì tự escape.

## 7. Lookup an toàn bằng QueryBuilder + bind marker

### 7.1. Dựng query một lần

```java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select selectAccount = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .column("display_name")
    .column("account_state")
    .whereColumn("account_id").isEqualTo(bindMarker());

PreparedStatement findAccount = session.prepare(
    selectAccount.build()
);
```

CQL được tạo có cấu trúc tương tự:

```sql
SELECT account_id,display_name,account_state
FROM lab_java_query.accounts_by_id
WHERE account_id = ?;
```

Vị trí của marker **được xác định khi chuẩn bị**, không phụ thuộc độ dài hoặc các ký tự trong `accountId`.

### 7.2. Bind value từ Java

```java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;

String accountId = "user-001";

Row row = session.execute(
    findAccount.bind(accountId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
).one();

if (row != null) {
    System.out.println(row.getString("display_name"));
}
```

Giá trị có dấu nháy/Unicode cũng được truyền qua codec theo kiểu CQL nếu là **giá trị tham số**. Không cần và không nên tự chèn dấu `'` quanh `accountId` khi bind.

### 7.3. Named bind markers

```java
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .column("display_name")
    .whereColumn("account_id").isEqualTo(bindMarker("id"));

PreparedStatement prepared = session.prepare(query.build());

Row row = session.execute(
    prepared.boundStatementBuilder()
        .setString("id", "user-001")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .build()
).one();
```

`bindMarker("id")` sinh placeholder `:id`. **Named marker vẫn chỉ bind value**; tên `id` là tên placeholder do developer xác định, không phải tên cột hoặc table từ user.

## 8. QueryBuilder cho INSERT/UPDATE/DELETE

### 8.1. INSERT dùng markers

```java
import com.datastax.oss.driver.api.querybuilder.insert.Insert;

Insert insert = insertInto("lab_java_query", "accounts_by_id")
    .value("account_id", bindMarker())
    .value("display_name", bindMarker())
    .value("account_state", bindMarker())
    .value("contact_email", bindMarker());

PreparedStatement upsertAccount = session.prepare(insert.build());

session.execute(
    upsertAccount.bind(
        "user-003",
        "Người dùng O'Reilly",
        "ACTIVE",
        "hello@example.invalid"
    ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
);
```

Ưu điểm: không có thao tác tự escape dấu nháy; codecs gắn giá trị đúng kiểu. **Upsert** theo cùng primary key không có nghĩa bản ghi được tạo mới tuyệt đối; có thể cập nhật columns và timestamp.

### 8.2. UPDATE với khóa phân vùng rõ

```java
PreparedStatement changeState = session.prepare(
    update("lab_java_query", "accounts_by_id")
        .setColumn("account_state", bindMarker())
        .whereColumn("account_id").isEqualTo(bindMarker())
        .build()
);

session.execute(
    changeState.bind("SUSPENDED", "user-003")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
);
```

Hành động nghiệp vụ “cho phép chuyển sang SUSPENDED” phải được kiểm soát ở service layer và theo role. Builder không tự chứng minh người gọi có quyền đổi trạng thái tài khoản.

### 8.3. DELETE có thể mất dữ liệu — không để identifier tự do

```java
PreparedStatement deleteAccount = session.prepare(
    deleteFrom("lab_java_query", "accounts_by_id")
        .whereColumn("account_id").isEqualTo(bindMarker())
        .build()
);
```

Đây là **mẫu CQL nguy hiểm nếu gọi sai**, dù có bind marker. Không nhận tùy ý table name, WHERE clause hay delete mode từ HTTP. Cần permission, audit, confirmation theo nghiệp vụ và hiểu tombstones/TTL.

### 8.4. BoundStatement và retry

Nếu write timeout, mutation có thể đã xảy ra ở một số replica dù driver chưa thấy ACK. `QueryBuilder` không giải quyết **idempotence**: counter increments, conditionals và writes có timestamp thay đổi khi retry cần được phân tích riêng. Dùng `setIdempotent(...)` chỉ khi semantics thao tác thực sự cho phép retry.

## 9. CqlIdentifier: tên schema không phải giá trị text

### 9.1. Hai dạng tên trong Cassandra

CQL có hai cách thể hiện identifier:

- **Unquoted identifier:** thường không phân biệt chữ hoa/thường; Cassandra chuẩn hóa sang chữ thường.
- **Double-quoted identifier:** giữ nguyên case/ký tự đặc biệt; phải dùng đúng dấu quote và cách escape.

Ví dụ:

```sql
-- Đây là hai cách tham chiếu CÙNG một tên không nhạy hoa/thường:
CREATE TABLE lab_java_query.demo_unquoted (
    UserId text PRIMARY KEY
);
-- Tên cột lưu theo internal form: userid.

-- Tên quoted giữ đúng chữ hoa/thường.
CREATE TABLE lab_java_query."AuditLog" (
    "EventID" text PRIMARY KEY,
    "SourceName" text
);
```

Trên một schema đã tạo tên phân biệt hoa/thường, không thể tự bỏ dấu `"` khi truy vấn:

```sql
SELECT "EventID", "SourceName"
FROM lab_java_query."AuditLog"
WHERE "EventID" = 'evt-001';
```

### 9.2. `fromCql`: chuỗi đang ở cú pháp CQL

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier a = CqlIdentifier.fromCql("AuditLog");
CqlIdentifier b = CqlIdentifier.fromCql("\"AuditLog\"");

// a diễn giải identifier KHÔNG QUOTE: internal = auditlog
// b diễn giải identifier ĐƯỢC QUOTE: internal = AuditLog
```

`fromCql("AuditLog")` **không** tự suy đoán user muốn table có tên chính xác `"AuditLog"`. Nếu CQL form được quote, phải truyền nguyên cú pháp có dấu quote hoặc dùng `fromInternal` khi bạn **đã có đúng internal name**.

### 9.3. `fromInternal`: tên đã biết ở dạng nội bộ

```java
CqlIdentifier exact = CqlIdentifier.fromInternal("AuditLog");
String forQuery = exact.asCql(true);      // "AuditLog"
String stored = exact.asInternal();       // AuditLog

CqlIdentifier lower = CqlIdentifier.fromCql("accounts_by_id");
String canonical = lower.asInternal();    // accounts_by_id
```

Với identifier chứa dấu nháy kép trong tên, `asCql(...)` sẽ áp quy tắc quote/escape phù hợp cho syntax. **Không nối trực tiếp `asInternal()` vào CQL** vì nó là nội dung tên, không phải cú pháp được escape.

### 9.4. Dùng `asCql(true)` đúng cách

Nếu phải ghi CQL tĩnh/động ngoài QueryBuilder sau khi đã **chọn identifier hợp lệ**:

```java
CqlIdentifier column = CqlIdentifier.fromInternal("AuditLog");
String safeSyntaxForIdentifier = column.asCql(true);
```

`asCql(true)` tạo **cú pháp identifier hợp lệ**, **không** kiểm tra table đó có nằm trong danh sách quyền được phép hay có tồn tại trong cluster. Vì vậy vẫn cần allowlist/authorization.

### 9.5. Identifier là một segment, không phải đường dẫn đầy đủ

```text
lab_java_query.accounts_by_id
^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^
keyspace id    table id
```

Không biến toàn chuỗi `"lab_java_query.accounts_by_id"` thành **một `CqlIdentifier`** nếu API đang đòi keyspace và table riêng. QueryBuilder có overload:

```java
Select query = selectFrom(
    CqlIdentifier.fromCql("lab_java_query"),
    CqlIdentifier.fromCql("accounts_by_id")
).all();
```

Mỗi segment được quote/escape riêng. Nếu client gửi tên chứa dấu chấm, dấu cách hoặc ký tự đặc biệt, không tự tách/ghép theo trực giác mà không có yêu cầu schema rõ ràng.

### 9.6. Bảng so sánh

| Java API | Input | Diễn giải | Tình huống |
|---|---|---|---|
| `fromCql("Foo")` | Không quote | `foo` | Tên chuẩn không nhạy case |
| `fromCql("\"Foo\"")` | Có quote | `Foo` | Tên CQL case-sensitive |
| `fromInternal("Foo")` | Tên nội bộ chính xác | `Foo` | Tên từ metadata/allowlist |
| `asCql(true)` | Một identifier | Cú pháp CQL có quote nếu cần | Render identifier trong query |
| `asInternal()` | Một identifier | Tên nội bộ không quote | Metadata, mapping, display |
| `selectFrom(keyspaceId,tableId)` | Hai identifiers | Tên bảng đủ namespace | Tránh lỗi ghép dotted names |

**Lỗi bảo mật điển hình:** chuyển toàn bộ tên table từ HTTP vào `fromInternal(userInput)` rồi coi đó là “đã an toàn”. Việc quote đúng chỉ giảm nguy cơ thay cú pháp; nó **không cho phép** user chọn tất cả bảng mà service account có quyền.

## 10. Cho phép chọn bảng động bằng allowlist

### 10.1. Nhu cầu thực tế

Một API có tham số `view=active` hoặc `view=archived`. Ứng dụng có hai bảng thiết kế sẵn cho từng view:

```text
view=active   → app.active_orders_by_tenant
view=archived → app.archived_orders_by_tenant
```

Không được làm:

```java
// SAI: client có thể chọn tên bảng bất kỳ.
String table = httpRequest.getParameter("table");
String cql = "SELECT * FROM app." + table + " WHERE tenant_id = ?";
```

Cách tốt hơn là **map giá trị nghiệp vụ** sang identifier do developer định nghĩa:

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.Map;

private static final Map<String, CqlIdentifier> TABLES = Map.of(
    "active", CqlIdentifier.fromCql("active_orders_by_tenant"),
    "archived", CqlIdentifier.fromCql("archived_orders_by_tenant")
);

static CqlIdentifier allowedTable(String view) {
    CqlIdentifier id = TABLES.get(view);
    if (id == null) {
        throw new IllegalArgumentException("Unsupported order view");
    }
    return id;
}
```

Khi đã xác minh bảng hợp lệ:

```java
CqlIdentifier tableId = allowedTable(view);

Select query = selectFrom(
    CqlIdentifier.fromCql("app"), tableId)
    .column("order_id")
    .column("order_state")
    .whereColumn("tenant_id").isEqualTo(bindMarker());
```

### 10.2. Allowlist khác regex

`^[a-z_]+$` có thể giúp chặn tên có ký tự lạ, nhưng **không** chứng minh tên bảng thuộc hợp đồng API. Chỉ cho phép `active`, `archived` giúp ngăn caller:

- Truy vấn bảng chưa được expose.
- Chọn bảng không có tenant-scoping trong primary key.
- Truy vấn bảng quá lớn hoặc có column nhạy cảm.
- Tạo vô số query shapes gây bùng nổ prepared statement cache.
- Chạy nhầm keyspace/schema version.

### 10.3. Đừng mở rộng allowlist bằng metadata tự động

Lỗi thường gặp: “lấy tất cả tên bảng từ `system_schema.tables` rồi cho user chọn”. Metadata cho biết **tồn tại**, không cho biết **được phép public, được bảo vệ tenant hay đáp ứng SLO**. Danh sách được phép phải là sản phẩm của thiết kế API và đánh giá phân quyền.

## 11. Projection động: chỉ cho chọn cột đã công bố

Một endpoint cho người dùng chọn fields:

```text
GET /accounts/user-001?fields=name,state
```

Nếu nhận `fields=contact_email` nhưng API không cho lộ email, câu query có syntax đúng vẫn là **data exposure**.

### 11.1. Định nghĩa map từ tên API sang schema column

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.Map;

static final Map<String,CqlIdentifier> VISIBLE_FIELDS = Map.of(
    "name", CqlIdentifier.fromCql("display_name"),
    "state", CqlIdentifier.fromCql("account_state")
);
```

### 11.2. Dựng projection bằng QueryBuilder

```java
import com.datastax.oss.driver.api.querybuilder.select.Select;
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

static Select buildAccountProjection(
        java.util.List<String> requestedFields) {

    if (requestedFields == null
            || requestedFields.isEmpty()
            || requestedFields.size() > 2) {
        throw new IllegalArgumentException("Invalid projection");
    }

    Select query = selectFrom("lab_java_query", "accounts_by_id")
        .column("account_id");

    java.util.Set<String> used = new java.util.HashSet<>();
    for (String field : requestedFields) {
        if (!used.add(field)) {
            throw new IllegalArgumentException("Duplicate field");
        }
        CqlIdentifier id = VISIBLE_FIELDS.get(field);
        if (id == null) {
            throw new IllegalArgumentException("Forbidden field");
        }
        query = query.column(id);
    }

    return query.whereColumn("account_id")
        .isEqualTo(bindMarker());
}
```

Các identifier do service định nghĩa, không lấy raw field text cho `.column(userInput)`. QueryBuilder có thể quote tên column hợp lệ, nhưng không kiểm tra **được phép trả cho caller không**.

### 11.3. Cẩn trọng với `SELECT *`

`SELECT *` có thể trả cả column mới được thêm sau một lần schema migration, bao gồm dữ liệu riêng tư. Khi tạo API/DTO ổn định, **liệt kê cột tường minh** và giữ response contract. QueryBuilder có `.all()`, nhưng “ngắn hơn” không phải luôn an toàn hơn.

### 11.4. Giới hạn số query shapes

Nếu có 10 cột và người dùng được chọn mọi tập con, lý thuyết có \(2^{10}=1.024\) shapes projection. Nếu cứ `session.prepare(...)` cho mỗi combination ở runtime mà không kiểm soát, cache/metadata có thể phình to. Chọn:

- Vài projection profiles (ví dụ summary/detail) theo API.
- Cache bounded/LRU theo **normalized query shape**, không theo value.
- Giới hạn fields/filters.
- Đo prepare rate, cache hit, memory và latency.

## 12. Optional filters: chỉ sinh query phù hợp data model

### 12.1. Ví dụ lọc theo thời gian trong một partition

Bảng `events_by_tenant_day` có primary key:

```sql
PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
```

Nhờ partition key đầy đủ và clustering `event_time`, một query như sau phù hợp:

```sql
SELECT event_time, event_id, event_type
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

`event_time` là clustering column đầu tiên, do đó range restriction có ý nghĩa. Một optional filter trên `event_type` **không có cùng đặc tính** vì nó là regular column trên bảng này.

### 12.2. Dựng với QueryBuilder

```java
import com.datastax.oss.driver.api.querybuilder.select.Select;
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .column("event_id")
    .column("event_type")
    .whereColumn("tenant_id").isEqualTo(bindMarker("tenant"))
    .whereColumn("event_day").isEqualTo(bindMarker("day"));

if (hasStart) {
    query = query.whereColumn("event_time")
        .isGreaterThanOrEqualTo(bindMarker("from_time"));
}
if (hasEnd) {
    query = query.whereColumn("event_time")
        .isLessThan(bindMarker("to_time"));
}

query = query.limit(100);
```

**Lưu ý thực thi:** có thể cần tách rõ các biến thể query theo giới hạn clustering và hệ Cassandra version, đảm bảo CQL server chấp nhận `WHERE`/`ORDER BY`. Trong code production, các variants nên được thử với **đúng schema, driver và Cassandra version** rồi chuẩn bị/cached có kiểm soát.

### 12.3. Không cho optional filter phá partition key

Sai lầm:

```java
// SAI: nếu tenant/day vắng, sinh SELECT không có partition key.
// QueryBuilder không tự ngăn full-table scan.
if (request.getTenantId() != null) { ... }
```

Một API cho phép “tenantId tùy chọn” có thể vô tình tạo scan toàn cluster khi caller không truyền. Hãy:

- Bắt buộc tenant/day cho endpoint này.
- Hoặc có bảng/index theo truy vấn khác, được thiết kế và định cỡ.
- Hoặc từ chối yêu cầu không được hỗ trợ.
- Không thêm `ALLOW FILTERING` chỉ để query chạy.

### 12.4. Giới hạn tổ hợp filters

Với ba filters optional có thể có \(2^3=8\) query shapes. Càng nhiều filters, số shapes và khả năng query không hợp lệ càng tăng. Một lựa chọn an toàn là **khai báo danh sách shapes rõ ràng**, mỗi shape có một prepared statement và tests.

## 13. ORDER BY động: validate direction và cột

### 13.1. Không bind `ASC/DESC` như value

CQL:

```sql
SELECT event_time, event_id
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 100;
```

`DESC` không phải value để bind bằng `?`; nó là một thành phần syntax. Nếu app cho chọn `sort=oldest` hoặc `sort=newest`:

```java
import com.datastax.oss.driver.api.core.metadata.schema.ClusteringOrder;

ClusteringOrder sortOrder;
switch (sortFromRequest) {
    case "oldest":
        sortOrder = ClusteringOrder.ASC;
        break;
    case "newest":
        sortOrder = ClusteringOrder.DESC;
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort");
}

Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .column("event_id")
    .whereColumn("tenant_id").isEqualTo(bindMarker())
    .whereColumn("event_day").isEqualTo(bindMarker())
    .orderBy("event_time", sortOrder)
    .limit(100);
```

### 13.2. Chỉ sắp xếp theo cột CQL hỗ trợ

Trong Cassandra, `ORDER BY` thông thường bị giới hạn bởi **clustering columns** và phải phù hợp với partition restriction và quy tắc thứ tự clustering của table. Không nhận tên regular column tùy ý như `event_type` rồi mong builder tạo “ORDER BY event_type” hợp lệ/nhanh.

Nếu API yêu cầu sort theo nhiều thuộc tính ngoài PK, cân nhắc:

- Bảng phụ denormalized theo sort/query pattern.
- Index/search engine phù hợp.
- Giới hạn phạm vi và sort ở application khi số rows đã bị chặn nhỏ.
- Phân hệ analytics nếu cần sort dữ liệu toàn cluster.

### 13.3. Không ghép direction nguyên văn

```java
// Không dùng:
String cql = baseQuery + " ORDER BY event_time " + sortFromHttp;
```

Ngay cả khi direction chỉ có `ASC`/`DESC`, chuyển từ enum/allowlist ở Java giúp giữ cấu trúc và tách đầu vào. Khi thêm field sort mới, phải cập nhật data model/performance tests.

## 14. LIMIT, page size và request budget

### 14.1. LIMIT có thể là giá trị động nhưng phải validate

Java Driver QueryBuilder 4.x hỗ trợ `limit(int)` và overload với `BindMarker`. Ví dụ:

```java
int requested = request.getLimit();

if (requested < 1 || requested > 100) {
    throw new IllegalArgumentException(
        "limit must be within 1..100");
}

Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereColumn("account_id").isEqualTo(bindMarker())
    .limit(requested);
```

Nhưng truy vấn theo một account_id đã có tối đa một row; `LIMIT` gần như không mang lợi ích ở ví dụ đó. Nó được đưa ra để minh họa validation. Với nhiều events/partition, `LIMIT` bảo vệ số rows trả cho API.

### 14.2. Cách bind LIMIT

```java
Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .whereColumn("tenant_id").isEqualTo(bindMarker())
    .whereColumn("event_day").isEqualTo(bindMarker())
    .limit(bindMarker());

// PreparedStatement bind(tenantUuid, day, boundedLimit)
```

CQL parser chỉ được dùng marker ở **những vị trí cú pháp cho phép**; `LIMIT` là trường hợp được hỗ trợ theo API này, nhưng không suy ra có thể bind tên bảng, ORDER BY column hay toàn clause. Validate limit **trước bind**.

### 14.3. Paging không phải giới hạn tổng chi phí

```java
BoundStatement page = prepared.bind(tenant, day)
    .setPageSize(100)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);
```

`setPageSize(100)` điều chỉnh cỡ mỗi page; lặp hết `ResultSet` có thể đọc hàng triệu rows. Đặt `LIMIT 100` và partition restrictions có thể hạn chế tổng rows; nhưng **partition lớn, tombstones và SSTable overlap** vẫn có thể tạo I/O đáng kể.

Để bảo vệ hệ thống cần:

- Required partition key.
- Bounded clustering range.
- Bounded `LIMIT`.
- Page size phù hợp row width/latency.
- Server/client timeout, rate limit/backpressure và concurrency budget.
- SLO/read latency, tombstone metrics, retries và alerts.

## 15. `literal(...)` khác `bindMarker()` như thế nào?

QueryBuilder hỗ trợ:

```java
Select literalQuery = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereColumn("account_id")
    .isEqualTo(literal("user-001"));
```

`literal(...)` đưa **giá trị literal đã được format theo codec** vào CQL text. Đây khác `raw(...)` và thường phù hợp các hằng số thực sự cố định, nhưng có những đánh đổi:

- Mỗi value khác nhau có thể tạo query text khác, làm giảm reuse prepared statement.
- Giá trị có thể xuất hiện trong log/trace/query string.
- Định dạng literal phụ thuộc codec/type, không nên dùng thay cho validation.
- Không giải quyết authorization/tenant scope.
- Với payload từ người dùng, **ưu tiên bind marker + prepared**.

Bảng đối chiếu:

| API | Dùng để tạo | Escaping/formating | Nên dùng cho user value? |
|---|---|---|---|
| `bindMarker()` | `?` hoặc `:name` | Value bind qua codec/protocol | **Có — ưu tiên** |
| `literal(value)` | Literal nằm trong CQL text | Codec/formatter có kiểm soát | Thường không; dùng cho hằng đáng tin |
| `raw(text)` | Snippet CQL nguyên văn | **Không escape, không check syntax** | **Không** |
| `CqlIdentifier` | Tên schema có quote phù hợp | Escaping identifier syntax | Chỉ sau allowlist/authorization |

Điểm nhớ: **tính an toàn của một query là tổng của structure, validation, authorization và data model**, không do một method đơn lẻ.

## 16. `raw(...)` là đường thoát nguy hiểm

Tài liệu Java Driver mô tả `QueryBuilder.raw(String)` là một snippet được đưa **nguyên vẹn** vào CQL, không syntax checking hay escaping. Nó hữu ích khi DSL chưa hỗ trợ một tính năng CQL mới, nhưng phải dùng thận trọng.

```java
// KHÔNG DÙNG: untrusted input đi vào raw CQL.
String customFilter = httpRequest.getParameter("filter");
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereRaw(customFilter);
```

Ngay cả nếu API trên được hỗ trợ tại vị trí cụ thể, **nguyên tắc sai** là coi filter string từ người dùng như một CQL fragment. Kết quả có thể là cú pháp sai, truy vấn scan rộng hoặc vượt quyền dữ liệu cho phép.

### 16.1. Khi buộc phải dùng raw

Chỉ dùng khi **không có DSL cho một tính năng đã được đánh giá**:

1. Snippet là **hằng số do developer kiểm soát**, không chứa user input.
2. Mọi value động khác vẫn bind bằng marker nơi được phép.
3. Có review bảo mật và load-test cho query shape.
4. Có integration tests trên Cassandra version đích.
5. Có cách dừng/rollback nếu server từ chối syntax mới.
6. Không dùng raw làm cửa sau cho `ALLOW FILTERING` hay truy vấn tùy ý.

### 16.2. Tránh string interpolation qua mọi lớp

Một lỗi có thể bị giấu sau nhiều tầng:

```text
HTTP request.filter
   └── buildSearchFilter(String)
         └── String.format("event_type='%s'", filter)
               └── QueryBuilder.raw(result)
                     └── CQL
```

Code review phải theo **luồng tainted data**, không chỉ tìm `session.execute("..."+user)`. Nếu tên được đưa qua `CqlIdentifier` nhưng không allowlist, nguy cơ vượt phạm vi dữ liệu vẫn tồn tại.

## 17. Java repository an toàn: một session, một query shape

Ví dụ đầy đủ dùng bảng `lab_java_query.accounts_by_id`. Nó dựng CQL một lần bằng QueryBuilder, prepare một lần và bind từng request.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import java.net.InetSocketAddress;
import java.util.Objects;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

public final class SafeAccountRepository implements AutoCloseable {
    private final CqlSession session;
    private final PreparedStatement find;
    private final PreparedStatement upsert;

    public SafeAccountRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);

        Select lookup = selectFrom("lab_java_query", "accounts_by_id")
            .column("account_id")
            .column("display_name")
            .column("account_state")
            .whereColumn("account_id").isEqualTo(bindMarker());

        this.find = session.prepare(lookup.build());

        this.upsert = session.prepare(
            insertInto("lab_java_query", "accounts_by_id")
                .value("account_id", bindMarker())
                .value("display_name", bindMarker())
                .value("account_state", bindMarker())
                .build()
        );
    }

    public String findDisplayName(String accountId) {
        validateAccountId(accountId);

        BoundStatement request = find.bind(accountId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(request).one();
        return row == null ? null : row.getString("display_name");
    }

    public void save(
            String accountId,
            String displayName,
            String accountState) {
        validateAccountId(accountId);

        if (displayName == null || displayName.length() > 256) {
            throw new IllegalArgumentException("Bad display name");
        }
        if (!"ACTIVE".equals(accountState)
                && !"INACTIVE".equals(accountState)) {
            throw new IllegalArgumentException("Bad state");
        }

        BoundStatement request = upsert.bind(
                accountId, displayName, accountState)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(request);
    }

    private static void validateAccountId(String value) {
        if (value == null || value.isEmpty() || value.length() > 128) {
            throw new IllegalArgumentException("Invalid account id");
        }
    }

    @Override
    public void close() {
        // Repository KHÔNG sở hữu session được inject.
        // Session owner của ứng dụng đóng nó ở shutdown.
    }

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            SafeAccountRepository repo =
                new SafeAccountRepository(session);

            repo.save(
                "user-010",
                "O'Reilly; ký tự dữ liệu, không phải CQL",
                "ACTIVE"
            );

            System.out.println(repo.findDisplayName("user-010"));
        }
    }
}
```

**Giới hạn bài lab:** `validateAccountId` chỉ kiểm tra cơ bản độ dài; hệ thật phải có **authentication, authorization và tenant scoping**. Repository không nên tự đóng session vì session do application bootstrap sở hữu. Khi dùng một node/RF=1 trong lab, CL/RF có thể phải điều chỉnh; **không hạ CL vô điều kiện trên production**.

### 17.1. Vì sao vẫn validate nếu bind đã an toàn?

Bind bảo vệ cú pháp/kiểu, nhưng không kiểm soát:

- Input 20 MiB gây memory/latency.
- Query không nằm trong phạm vi nghiệp vụ.
- Cột nhạy cảm hoặc tenant khác.
- Limit hàng trả, page size, request deadline.
- Giá trị không hợp lệ về domain (trạng thái lạ).
- Spam/abuse hoặc tốc độ requests.

Validation và authorization bổ sung cho parameterization; không thay thế nhau.

### 17.2. Lưu ý về logging

Không log `displayName`, email, token, password hoặc mọi bound values ở chế độ production chỉ để “debug injection”. Nên log:

- Query shape/operation name.
- Table/keyspace logical labels được định nghĩa sẵn.
- Latency, CL, retry/error category, row counts/bytes.
- Correlation ID đã được thiết kế tránh lộ PII.
- Query shape hash thay vì raw values khi phù hợp.

## 18. Ví dụ động an toàn theo thứ tự sort

Một service chỉ cho hai lựa chọn: `newest` hoặc `oldest`. Hãy build **hai prepared statements** từ cùng schema thay vì ghép raw `ORDER BY` theo HTTP.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.metadata.schema.ClusteringOrder;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

public final class EventQueries {
    private final PreparedStatement newest;
    private final PreparedStatement oldest;

    public EventQueries(CqlSession session) {
        this.newest = session.prepare(build(ClusteringOrder.DESC).build());
        this.oldest = session.prepare(build(ClusteringOrder.ASC).build());
    }

    private static Select build(ClusteringOrder order) {
        return selectFrom("lab_java_query", "events_by_tenant_day")
            .column("event_time")
            .column("event_id")
            .column("event_type")
            .whereColumn("tenant_id").isEqualTo(bindMarker())
            .whereColumn("event_day").isEqualTo(bindMarker())
            .orderBy("event_time", order)
            .limit(100);
    }

    public PreparedStatement select(String requestedOrder) {
        if ("newest".equals(requestedOrder)) return newest;
        if ("oldest".equals(requestedOrder)) return oldest;
        throw new IllegalArgumentException("Unsupported order");
    }
}
```

**Điểm cần nhớ:** Cassandra có quy tắc `ORDER BY` theo clustering columns của partition đã cố định; test trên schema thật. Hai prepared statements không phải “session cho mỗi sort”; chúng dùng chung một `CqlSession` và khác ở query shape đã được phê duyệt.

## 19. Identifier có dấu nháy, keyword và case-sensitive

### 19.1. Ví dụ identifier khó

Giả sử một schema cũ (không khuyến nghị tạo mới) có table `"Order History"` và cột `"Event""Name"`. Trong CQL:

```sql
CREATE TABLE lab_java_query."Order History" (
    "EventID" text PRIMARY KEY,
    "Event""Name" text
);
```

Dấu `"` ở giữa internal identifier được biểu diễn bằng **hai dấu nháy kép** khi viết CQL form. Với QueryBuilder:

```java
CqlIdentifier table =
    CqlIdentifier.fromInternal("Order History");

CqlIdentifier eventName =
    CqlIdentifier.fromInternal("Event\"Name");

Select query = selectFrom(
        CqlIdentifier.fromCql("lab_java_query"), table)
    .column(eventName)
    .whereColumn(
        CqlIdentifier.fromInternal("EventID"))
    .isEqualTo(bindMarker());
```

Driver tạo cú pháp identifier phù hợp; **không** cần tự chèn `"` theo chuỗi Java. Đây là giải pháp cho tên kỳ lạ đã được schema định nghĩa, **không phải** cấp quyền cho user tạo/tùy chọn bất kỳ tên.

### 19.2. Khuyến nghị cho schema mới

Ưu tiên:

- Tên lowercase `snake_case`.
- Tránh quoted identifiers nếu có thể.
- Tránh reserved keywords làm tên table/cột.
- Keyspace/table names cố định theo ứng dụng.
- Column names tương ứng với query patterns rõ ràng.
- Test metadata names và serialization khi phải tương thích schema cũ.

Case-sensitive identifiers tăng nguy cơ code ở Java, schema migration và query DSL **đọc nhầm tên**. Dùng `CqlIdentifier` giúp rõ ràng nhưng không xóa sự phức tạp trong vận hành.

## 20. Dynamic queries và tính đúng đắn Cassandra

### 20.1. Không phải mọi filter là truy vấn hợp lệ

Trên `events_by_tenant_day`:

```sql
-- Phù hợp nếu partition key đầy đủ:
SELECT event_time, event_type
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?;

-- Không tự nhiên hiệu quả trên schema đó:
SELECT event_time, event_type
FROM lab_java_query.events_by_tenant_day
WHERE event_type = ?;
```

Câu thứ hai không có partition key; QueryBuilder không biến nó thành point lookup. Nếu API cần tìm events theo loại, phải thiết kế bảng theo query:

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.events_by_tenant_type_day (
    tenant_id uuid,
    event_type text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, event_type, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id DESC
);
```

Ứng dụng cần duy trì bảng phụ khi ghi/delete/TTL; không có JOIN/transaction xuyên hai tables tự động. Nếu dữ liệu rất lớn/hot, cần thêm bucket/shard hoặc search/analytics.

### 20.2. ALLOW FILTERING không phải “fix cho QueryBuilder”

```java
// Có API .allowFiltering(), nhưng không nên bật mặc định.
Select expensive = selectFrom("lab_java_query", "events_by_tenant_day")
    .all()
    .whereColumn("event_type").isEqualTo(bindMarker())
    .allowFiltering();
```

CQL server có thể phải đọc rất nhiều partitions/cells để lọc; client timeout và p99 có thể tăng mạnh. Một câu query syntactically valid vẫn có thể gây load nguy hiểm.

Nếu cần query khác primary key, yêu cầu data modeling/index review và load test, không tự thêm `allowFiltering()` vào nhánh “không tìm thấy dữ liệu”.

### 20.3. LIMIT không cứu mọi scan rộng

`LIMIT 10` chỉ giới hạn số rows trả hoặc được chọn theo semantics câu truy vấn. Nó không tạo secondary index, cũng không đảm bảo server đọc đúng 10 rows vật lý nếu filter/tombstone/SSTables chồng lấn. **Đánh giá phạm vi partition trước tiên.**

### 20.4. Kết quả nhỏ khác công việc nhỏ

`SELECT COUNT(*)` toàn bảng trả một giá trị nhưng có thể đọc rất nhiều rows; query builder chỉ dựng chuỗi. Không dùng query builder như cách vượt qua giới hạn OLTP của Cassandra.

## 21. Giá trị typed: UUID, date, timestamp, collections

### 21.1. Bind bằng codec đúng kiểu

```java
import java.time.LocalDate;
import java.time.Instant;
import java.util.UUID;

UUID tenant = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

LocalDate day = LocalDate.of(2026, 11, 21);

PreparedStatement prepared = session.prepare(
    selectFrom("lab_java_query", "events_by_tenant_day")
        .column("event_time")
        .column("event_id")
        .whereColumn("tenant_id").isEqualTo(bindMarker())
        .whereColumn("event_day").isEqualTo(bindMarker())
        .build()
);

BoundStatement bound = prepared.bind(tenant, day)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);
```

Driver serialize đúng UUID/date theo CQL. Đừng tự dựng text:

```java
// KHÔNG DÙNG:
String where = "WHERE tenant_id = '" + tenant + "' "
    + "AND event_day = '" + day + "'";
```

Ngoài injection/cú pháp, đây còn có nguy cơ sai kiểu (UUID không phải CQL text), format ngày/timezone và mất khả năng tái sử dụng prepared statements.

### 21.2. Timestamp là một loại riêng

Java Driver 4.x thường map:

- CQL `uuid` → Java `UUID`.
- CQL `date` → Java `LocalDate`.
- CQL `timestamp` → Java `Instant`.
- CQL `text` → Java `String`.
- CQL `bigint` → Java `long/Long`.

Nếu người dùng nhập thời gian từ HTTP, parse theo chuẩn đã chọn, kiểm timezone/range, rồi **bind `Instant`**. Không nhận nguyên một mảnh CQL như `toTimestamp(now())` từ query parameter thay cho value. Nếu muốn server-generated function, đó phải là **query shape do developer định nghĩa**, được review về idempotence.

### 21.3. Null và unset không tương đương mọi tình huống

Khi bind null, driver/CQL có semantics cho null/tombstone; một số API hỗ trợ `unset` để giữ cột không được cập nhật. Không dựa vào string literal `"null"` để biểu diễn CQL null. Với UPDATE/INSERT, cần định nghĩa rõ:

- Field absent: không thay đổi.
- Field provided null: xóa/đặt null theo semantics tương ứng.
- Field provided value: upsert.
- Field unset: chỉ khi statement/driver/server hỗ trợ và đúng policy.

Sự khác nhau ảnh hưởng tombstone, TTL, compaction và retry. QueryBuilder chỉ dựng syntax; domain model phải quyết định.

## 22. Prepared statement cache và hiệu năng

### 22.1. Đừng prepare mỗi request

```java
// Kém hiệu quả:
public Row load(String id) {
    Select q = selectFrom("lab_java_query", "accounts_by_id")
        .column("display_name")
        .whereColumn("account_id").isEqualTo(bindMarker());
    PreparedStatement p = session.prepare(q.build());
    return session.execute(p.bind(id)).one();
}
```

Ở workload cao, dựng DSL và prepare lặp lại tạo overhead; driver có caching/reprepare mechanisms, nhưng không nên dựa hoàn toàn vào đó để cứu một hot path.

Hướng đúng:

```java
final class AccountLookup {
    private final CqlSession session;
    private final PreparedStatement prepared;

    AccountLookup(CqlSession session) {
        this.session = session;
        this.prepared = session.prepare(
            selectFrom("lab_java_query", "accounts_by_id")
                .column("display_name")
                .whereColumn("account_id").isEqualTo(bindMarker())
                .build());
    }

    String find(String id) {
        Row r = session.execute(prepared.bind(id)).one();
        return r == null ? null : r.getString("display_name");
    }
}
```

### 22.2. Caching shapes, không caching giá trị đầu vào

Cache key nên phản ánh:

- Keyspace/table identifier đã allowlist.
- Các selected columns/query variants.
- Predicate shape/order direction.
- Schema/version context khi cần.

**Không** tạo prepared statement mới cho từng `tenant_id` hoặc mỗi account value. Prepared statements sinh từ same query shape tái sử dụng qua values.

### 22.3. Bùng nổ biến thể

Giả sử API cho:

- 5 projection profiles.
- 4 bộ optional predicates.
- 2 sort orders.
- 3 table views.

Tối đa:

\[
5 \times 4 \times 2 \times 3 = 120
\]

prepared query shapes nếu mọi tổ hợp thực sự được phép. Cần **giới hạn/định nghĩa trước** các tổ hợp hợp lệ, không cache vô hạn theo mọi chuỗi đầu vào. Một cache theo user-provided CQL fragment không có allowlist là rủi ro memory và security.

### 22.4. QueryBuilder không bắt buộc cho CQL tĩnh

Với câu đơn giản, **CQL String cố định + PreparedStatement** thường đủ và dễ bảo trì. QueryBuilder hữu ích nhất khi cấu trúc truy vấn thực sự động có kiểm soát. Đánh giá readability, caching và testability; không chuyển hết mọi CQL sang DSL chỉ vì có thư viện.

## 23. Consistency level, idempotence và retry trong truy vấn động

### 23.1. CL nằm trên statement

```java
BoundStatement statement = prepared.bind(tenant, day)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(200);
```

`LOCAL_QUORUM` phụ thuộc RF của keyspace và local DC. Với RF=3 trong `dc1`, quorum local cần 2 full replicas. QueryBuilder không tự chọn CL có ý nghĩa nghiệp vụ.

### 23.2. Timeout không chứng minh request không thực hiện

Với UPDATE hoặc DELETE, timeout có thể đến khi một phần replicas đã ghi và client chưa nhận ACK. Khi retry:

- Việc đặt lại timestamp có thể thay conflict resolution.
- Retry counter increment có thể tăng hai lần.
- Retry LWT/conditional mutation có semantics riêng.
- Unbounded retry có thể làm cluster quá tải.

Chỉ gắn `setIdempotent(true)` nếu operation thực sự an toàn khi retry. Không đánh dấu mọi statement do QueryBuilder sinh ra là idempotent một cách tự động.

### 23.3. QueryBuilder có thể suy idempotence một phần

Một số term cố định hoặc bind markers có thể có idempotence semantics rõ hơn `raw(...)` hoặc functions không xác định (ví dụ `now()`). QueryBuilder có logic gợi ý thuộc tính statement trong một số trường hợp, nhưng **không biết logic nghiệp vụ** của event IDs, counters hoặc compensating actions.

Code review phải kiểm tra:
- Key và dữ liệu có cố định khi retry không?
- Có side effects ngoài Cassandra không?
- Source timestamp/TTL có đổi khi retry không?
- Có yêu cầu read-after-write/quorum không?
- Có giới hạn retries và reconciliation không?

## 24. Kiểm thử chống injection và truy vấn sai

### 24.1. Kiểm thử dữ liệu “lạ” nhưng hợp lệ

Chuẩn bị values:

| Dữ liệu thử | Mục tiêu |
|---|---|
| `O'Reilly` | Giá trị chứa nháy đơn không phá CQL |
| `a;b` | Dấu chấm phẩy là dữ liệu khi bind |
| `"name"` | Dấu nháy kép trong **value** không đổi identifier |
| `\n`, Unicode có dấu | Codec text/UTF-8 hoạt động đúng |
| Chuỗi dài sát policy limit | Validation/size guard |
| Chuỗi rỗng/null | Domain policy đúng |
| UUID/date sai format | Validation trước bind, lỗi có kiểm soát |
| Tenant khác caller | Authorization từ chối |
| Table/column lạ | Allowlist từ chối |
| Sort khác `newest/oldest` | Dừng trước khi build CQL |

### 24.2. Kiểm tra CQL generated không chứa values

Unit test có thể kiểm:

```java
Select q = selectFrom("lab_java_query", "accounts_by_id")
    .column("display_name")
    .whereColumn("account_id").isEqualTo(bindMarker());

String cql = q.asCql();

assert cql.contains("?");
assert !cql.contains("O'Reilly");
```

Đây chỉ là kiểm thử đơn giản cho **query shape**. Nó không đủ để chứng minh authorization, query plan hay mọi dữ liệu đều được bind; cần integration tests.

### 24.3. Kiểm thử identifier case sensitivity

```java
CqlIdentifier lower = CqlIdentifier.fromCql("AuditLog");
CqlIdentifier exact = CqlIdentifier.fromCql("\"AuditLog\"");

assert lower.asInternal().equals("auditlog");
assert exact.asInternal().equals("AuditLog");
assert !lower.equals(exact);
```

Kiểm tra cả tên có keyword, dấu cách và dấu nháy kép. Không dùng `equalsIgnoreCase` để so tên quoted identifiers nếu semantic case-sensitive.

### 24.4. Kiểm thử mapping table/field

```java
// Pseudocode cho unit tests.
assert allowedTable("active") != null;
assert allowedTable("archived") != null;
assertThrows(
    IllegalArgumentException.class,
    () -> allowedTable("system_schema")
);
assertThrows(
    IllegalArgumentException.class,
    () -> allowedTable("admin")
);
```

Hãy kiểm tra cả các trường hợp có thêm khoảng trắng hoặc case khác policy. Nếu API muốn normalization (ví dụ trim/lowercase), phải làm có quy tắc, không cho identifier bất ngờ lọt vào.

### 24.5. Integration tests trên Cassandra thật

Một test suite tốt cần:

1. Tạo schema lab giống production (PK, clustering order, NTS/RF).
2. Prepare query và bind `String` có dấu nháy/Unicode.
3. Kiểm query trả đúng row theo account/tenant/day.
4. Đảm bảo query không có partition key bắt buộc bị từ chối **ở validation layer**, trước khi tới Cassandra.
5. Kiểm sort/limit variants bằng truy vấn đúng model.
6. Kiểm unauthorized table/column option bị từ chối, không chờ DB báo unknown table.
7. Kiểm role Cassandra không có quyền các bảng khác.
8. Đo p95/p99, read amplification, tombstones và page counts trên dataset đủ đại diện.

## 25. Observability và logging khi QueryBuilder có nhiều query shapes

### 25.1. Gắn tên cho mỗi operation

Thay vì log raw query với values, đặt logical operation names:

```text
FindAccountById
ListTenantEventsByDayNewest
ListTenantEventsByDayOldest
UpdateAccountState
DeleteAccountById
```

Metrics theo operation và normalized shape sẽ rõ hơn một log chứa CQL mỗi request.

### 25.2. Các chỉ số nên quan sát

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Driver | Request latency p95/p99, in-flight, timeouts, retries | Driver/client đang chịu tải thế nào |
| Query shape | Frequency, prepared cache size/hit/miss, compile/prepare errors | Bùng nổ câu truy vấn động không |
| Cassandra | Read/write latency, range scan latency | Query không có PK hoặc filtering đắt |
| Storage | SSTables-per-read, tombstone scans, compaction backlog | Read amplification |
| Security | Forbidden table/column selections, tenant mismatch | Attempt vượt hợp đồng API |
| Reliability | Unavailable vs timeout, CL/DC, error budget | Replica/cluster health |
| Paging | Page count/bytes per API request | Có fetch quá rộng không |
| Audit | Authenticated principal, operation name, outcome | Truy vết không lộ secrets |

### 25.3. Tracing có chọn lọc

`TRACING ON` trong `cqlsh` hoặc tracing statement ở driver có thể hỗ trợ một số truy vấn lab. Không bật tracing 100% cho service QPS cao; tracing tạo thêm dữ liệu và overhead. Khi điều tra injection, đừng tự log raw data input có thông tin nhạy cảm.

### 25.4. Đừng chữa một query scan bằng tăng timeout

Nếu QueryBuilder sinh `ALLOW FILTERING` và query mất nhiều giây:

- Nguyên nhân có thể là thiếu partition key/index, tombstone và range scan.
- Tăng timeout có thể tăng số requests đang giữ tài nguyên.
- Tăng concurrency làm read latency p99 tệ hơn.
- Đổi CL không biến scan thành point lookup.
- Đổi từ String CQL sang QueryBuilder không giảm lượng dữ liệu cần đọc.

Ưu tiên **sửa schema/query shape**, không chỉ thay driver settings.

## 26. Các lỗi thường gặp và cách phân biệt

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| CQL syntax error khi accountId có dấu `'` | Nối value vào string literal | Dùng bind marker |
| `InvalidQueryException` tên bảng/cột khác kỳ vọng | Case sensitivity, CqlIdentifier form | So schema và `fromCql/fromInternal` |
| QueryBuilder tạo WHERE thiếu điều kiện | Quên gán lại immutable result | `query = query.where...` |
| Marker bound sai thứ tự | Anonymous markers, gọi `bind` sai | Named markers hoặc test thứ tự |
| `CodecNotFoundException`/type mismatch | Bind String cho UUID/date hoặc ngược lại | Parse typed values và bind đúng codec |
| Query cần `ALLOW FILTERING` | Thiếu PK, filter regular column | Thiết kế bảng theo query |
| Query trả dữ liệu tenant khác | Dùng tenantId từ HTTP, thiếu authz | Scope từ principal, policy và audit |
| Query động tạo hàng nghìn prepared entries | Shape không giới hạn theo raw inputs | Allowlist, cache bounded |
| `ORDER BY` bị server từ chối | Cột không phải clustering/ràng buộc sai | Sửa schema/query và test |
| Driver timeout dù LIMIT nhỏ | Partition lớn, tombstone, SSTable overlap | Thu hẹp range, giám sát read I/O |
| Một value đặc biệt xuất hiện trong CQL log | Dùng `literal(...)` hoặc nối string | Bind và hạn chế query logging |
| `raw(...)` chấp nhận đoạn ngoài ý muốn | Untrusted CQL fragment | Loại raw, dùng DSL + allowlist |
| Table tồn tại nhưng không được truy cập | Cassandra role thiếu quyền | Xử lý authz; không nâng quyền vô cớ |
| Contact point chạy được, node khác lỗi | Driver topology/TLS/SAN/CL | Kiểm endpoint, local DC, TLS và health |

**Không mọi lỗi “InvalidQuery” đều do injection.** Nó có thể do schema không tương thích, query restriction hoặc type mismatch; phân loại rõ và không log secret để debug.

## 27. Mẫu code review trước khi merge QueryBuilder

**Data flow**

- [ ] Mọi value từ HTTP/message/job đi qua bind markers, không nối vào CQL.
- [ ] Không có `raw(userInput)`, `whereRaw(userInput)`, `String.format` chèn tainted values.
- [ ] Dữ liệu được parse đúng CQL types trước bind.
- [ ] Không đưa UUID/date/timestamp thành SQL/CQL text bằng interpolation.
- [ ] Có validation cho độ dài/miền giá trị, null và request budget.

**Identifiers và phân quyền**

- [ ] Keyspace/table/column names chọn từ allowlist/mapping do service kiểm soát.
- [ ] `CqlIdentifier.fromCql/fromInternal` dùng đúng ngữ nghĩa.
- [ ] Không dùng `asInternal()` để ghép CQL syntax trực tiếp.
- [ ] Không expose `SELECT *` với fields có thể chứa dữ liệu riêng tư ngoài contract.
- [ ] Tenant scope được lấy từ identity/policy, không tin query parameter.
- [ ] CQL service role chỉ có các quyền tối thiểu cần dùng.

**Cassandra query semantics**

- [ ] `WHERE` có đủ partition key theo data model, có clustering bounds phù hợp.
- [ ] Không thêm `ALLOW FILTERING` nếu chưa có thiết kế/đo tải được phê duyệt.
- [ ] ORDER BY chỉ theo clustering columns và hướng hợp lệ.
- [ ] LIMIT/page size/concurrency có guardrails; không scan lịch sử lớn ngoài ý muốn.
- [ ] RF, CL và local DC phù hợp yêu cầu nhất quán.
- [ ] DELETE/UPDATE/TTL/idempotence/retry được xét theo semantics thực tế.

**Hiệu năng và vận hành**

- [ ] QueryBuilder không dựng lại liên tục trong hot path nếu shape không đổi.
- [ ] PreparedStatement reuse, cache query variants hữu hạn.
- [ ] CqlSession dùng chung theo cluster/security context, không mở theo request.
- [ ] Exceptions/timeouts được xử lý có budget; không retry vô hạn.
- [ ] Metrics theo normalized operation, không log PII/secrets.
- [ ] Unit/integration tests cover quotation, unauthorized identifiers và query shape.

## 28. Bài tập thực hành và tình huống

### Bài 1 — Giá trị có dấu nháy

Có account display name `O'Reilly`. Vì sao `WHERE display_name = '...'+input` có thể tạo cú pháp sai? Tại sao `bindMarker()` giải quyết lớp lỗi đó mà không cần manual escaping?

### Bài 2 — Identifier không phải value

Một API muốn chọn bảng `active_orders_by_tenant` hoặc `archived_orders_by_tenant`. Có thể dùng `FROM ?` rồi bind string table name không? Đề xuất cách chọn an toàn.

### Bài 3 — Identifier case

So `CqlIdentifier.fromCql("AuditLog")`, `fromCql("\"AuditLog\"")` và `fromInternal("AuditLog")`. Những phương thức nào tham chiếu đúng bảng quoted `"AuditLog"`?

### Bài 4 — QueryBuilder immutable

Đoạn code:

```java
Select q = selectFrom("ks", "accounts").column("account_id");
q.whereColumn("account_id").isEqualTo(bindMarker());
```

lỗi gì về tư duy? Cần sửa thế nào?

### Bài 5 — Raw snippet

`QueryBuilder.raw(...)` có escape hoặc kiểm tra cú pháp trước khi nối nội dung không? Nếu app nhận `filterClause` từ HTTP, có nên truyền vào `raw`?

### Bài 6 — Tenant isolation

Một query có bind marker cho `tenant_id` nhưng caller được truyền tenant ID tùy ý. Query đã chống CQL injection, liệu có đủ chống đọc dữ liệu tenant khác?

### Bài 7 — Dynamic sort

Endpoint yêu cầu `sort=event_type_desc`. Trên bảng PK `((tenant_id,event_day),event_time,event_id)`, có thể thêm `orderBy("event_type", DESC)` và xem là hợp lệ/nhanh không? Cần làm gì?

### Bài 8 — Optional filter

QueryBuilder chỉ thêm `WHERE tenant_id=?` nếu user truyền tenant ID. Khi vắng tenant ID, một full-table query được dựng. Thiết kế lại validation và query shapes.

### Bài 9 — LIMIT và paging

Một query có `setPageSize(200)` nhưng kết quả tổng 2 triệu rows. Có phải Cassandra chỉ đọc 200 rows? Làm sao giới hạn **tổng** tải?

### Bài 10 — Prepared cache

Một repository tạo câu query theo 10 boolean filters optional, đồng thời cho tùy chọn projection tự do. Có nguy cơ gì với prepared cache và cách tránh?

### Bài 11 — LWT/DELETE và retry

Một DELETE có bind marker nhưng nhận timeout. Có thể khẳng định DELETE chưa xảy ra không? Nên xử lý thế nào trước khi retry nếu có yêu cầu kiểm toán?

### Bài 12 — Dùng `literal(...)`

`literal(userInput)` và `bindMarker()` có cùng điểm mạnh về reuse query/cache/logging không? Khi nào literal hợp lý?

### Bài 13 — Quoted schema

Bảng `"Order History"` có cột `"Event""Name"`. Viết Java code dùng `CqlIdentifier.fromInternal` để dựng câu SELECT mà không tự nối identifier raw.

### Bài 14 — Query đúng cú pháp nhưng không đúng hiệu năng

QueryBuilder tạo query:

```sql
SELECT COUNT(*) FROM lab_java_query.events_by_tenant_day;
```

Query có thể chạy nhưng vì sao không nên đặt vào mỗi dashboard refresh? QueryBuilder có làm nó O(1) không?

### Bài 15 — Code review

Một PR chứa:

```java
String table = req.getParameter("table");
String id = req.getParameter("id");
String cql = "SELECT * FROM " + table + " WHERE id='" + id + "'";
```

Liệt kê ít nhất năm lỗi về bảo mật, tính đúng đắn hoặc hiệu năng và phác thảo thiết kế thay thế.

### Gợi ý đáp án

1. Dấu nháy phá CQL literal; prepared/bind truyền value qua protocol và codec, không parse thành syntax.
2. Không. Map `active/archived` sang `CqlIdentifier` đã allowlist; prepare query cho mỗi shape.
3. Dùng `fromCql("\"AuditLog\"")` hoặc `fromInternal("AuditLog")`; dạng unquoted bị fold thành `auditlog`.
4. Builder immutable; phải gán `q = q.whereColumn(...).isEqualTo(...)`.
5. Raw chèn nguyên văn, không escaping/syntax checks; không dùng cho input không tin cậy.
6. Chưa. Cần xác thực caller, lấy tenant scope từ principal/policy, RBAC và kiểm quyền CQL.
7. Không, event_type là regular column; ORDER BY Cassandra cần clustering restrictions; thiết kế bảng theo query hoặc sort bounded in-app.
8. Bắt buộc tenant/day hoặc chọn một query pattern khác có table/index phù hợp; từ chối input thiếu trước DB.
9. Không; paging chia kết quả thành pages. Dùng partition/clustering bounds, LIMIT phù hợp, rate/backpressure và data model.
10. Bùng nổ \(2^{10}=1.024\) filter shapes trước khi nhân projections; chỉ cho số variants hữu hạn, cache bounded.
11. Không; có thể đã xóa ở một số/all replicas. Retry theo semantics/idempotence, audit và reconciliation.
12. Không. Literal inline value trong CQL và có thể lộ/log/khó reuse; hợp lý cho hằng cố định do developer kiểm soát.
13. Dùng `selectFrom(CqlIdentifier.fromCql("lab_java_query"), CqlIdentifier.fromInternal("Order History")).column(CqlIdentifier.fromInternal("Event\"Name"))...` và bind WHERE.
14. COUNT toàn bảng duyệt dữ liệu lớn; QueryBuilder chỉ tạo CQL, không tạo count index.
15. Chèn table identifier tự do, id literal tự nối, không bind, không tenant auth, SELECT *, không query plan/limit, logging risk; thay bằng allowlist, explicit columns, prepared markers và auth policy.

## 29. Tài liệu tham khảo

Tài liệu chính thức hữu ích để đối chiếu đúng API/phiên bản:

- [Apache Cassandra Java Driver 4.19 — Query Builder Overview](https://apache.github.io/cassandra-java-driver/4.19.0/query_builder/): DSL, dependency, immutability, caching và giới hạn.
- [Java Driver 4.19 API — QueryBuilder](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/QueryBuilder.html): `selectFrom`, `insertInto`, `bindMarker`, `literal`, `raw`.
- [Java Driver 4.19 API — CqlIdentifier](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/CqlIdentifier.html): CQL/internal form, case sensitivity và escaping.
- [Java Driver 4.19 API — Select](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/select/Select.html): `where`, `limit`, `orderBy`, `allowFiltering`.
- [Java Driver 4.19 API — BuildableQuery](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/BuildableQuery.html): `asCql()`, `build()` và statement builder.
- [Java Driver 4.x — Case Sensitivity](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/): quoted identifiers, `fromCql` và internal names.
- [Java Driver 4.19 — Core Manual](https://apache.github.io/cassandra-java-driver/4.19.0/core/): `CqlSession`, prepared/bound statements và type mapping.
- [Apache Cassandra — CQL SELECT/WHERE/ORDER BY/LIMIT](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/): partition key và query-first.
- [Apache Cassandra — Security](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/security.html): TLS, authentication, authorization.

**Lưu ý phiên bản:** Maven coordinates và một số API/behavior thay đổi giữa các bản Driver 4.x. Bản Apache 4.19 dùng namespace Java `com.datastax.oss.driver.api` dù Maven groupId của module query-builder có thể là `org.apache.cassandra`. Hãy kiểm tra đúng artifact, driver core version và Cassandra release của ứng dụng trước khi dùng những snippet vào production.

## 30. Kết luận: bốn ranh giới phải giữ

1. **Value khác identifier.** Bind markers cho data values; keyspace/table/column names cần `CqlIdentifier` và **allowlist**. Bind marker không thay được một CQL identifier.
2. **Escaping khác authorization.** QueryBuilder giúp tạo syntax; nó không quyết định user có quyền đọc bảng/tenant nào. Tenant scope phải đến từ identity/policy và role permissions.
3. **CQL hợp lệ khác truy vấn rẻ.** WHERE phải phù hợp partition/clustering key; `ALLOW FILTERING`, COUNT toàn bảng và pagination không cứu một data model sai.
4. **Query động khác query tùy ý.** Chỉ hỗ trợ finite query shapes đã định nghĩa, prepare/cache có giới hạn, bind theo codec, giám sát error/latency và kiểm thử các input đặc biệt.

Khi giữ đủ bốn ranh giới, Java application có thể linh hoạt chọn bảng/cột/điều kiện hợp lệ mà **không nối đầu vào không tin cậy vào CQL**, vẫn tận dụng prepared statements, token-aware routing, consistency level và mô hình wide-column của Cassandra.
