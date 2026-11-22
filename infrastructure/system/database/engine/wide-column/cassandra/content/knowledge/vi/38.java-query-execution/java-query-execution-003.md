# Bind theo vị trí/tên và kiểm tra đúng kiểu dữ liệu trong Cassandra Java Driver

> **Chương:** Truy vấn từ Java  
> **Trọng tâm:** Dùng `PreparedStatement`/`BoundStatement` của Apache Cassandra Java Driver 4.x để bind giá trị qua vị trí (`?`) hoặc tên (`:name`), xác minh CQL types từ metadata, phân biệt `NULL`/`UNSET`, kiểm Java codec và tránh lỗi thứ tự/kiểu khiến câu truy vấn trả sai dữ liệu. Các ví dụ bám API Driver 4.17 và tương thích về nguyên lý với nhánh Apache 4.18; kiểm phiên bản thực đang dùng trước khi áp dụng vào production.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Mô tả vòng đời **`prepare → bind → execute → decode`** và giá trị của metadata trong Cassandra Java Driver.
2. Viết CQL có marker ẩn danh `?`, bind theo **chỉ số từ 0** với `bind(...)`/`setXxx(index, ...)` và biết khi nào thứ tự dễ sai.
3. Viết marker có tên `:tenant`, `:day`, dùng `setXxx("name", ...)`, xử lý tên cột lặp lại/quoted identifier mà không đánh đồng tên marker với tên cột.
4. Đọc `PreparedStatement.getVariableDefinitions()`, so thứ tự, tên và **CQL DataType** của marker; phân biệt validation của driver với validation nghiệp vụ.
5. Chọn đúng các setter/getter cho `text`, `int`, `bigint`, `decimal`, `date`, `timestamp`, `uuid`/`timeuuid`, `blob` và collection/UDT.
6. Phân biệt `setToNull` với `unset` và tác động lên **primary key, tombstone, TTL** và partial updates.
7. Viết ví dụ Java hoàn chỉnh dùng một `CqlSession` và nhiều prepared statements, gắn consistency level phù hợp RF và kiểm kết quả đọc lại.
8. Thiết kế negative tests có chủ đích để phát hiện **đảo giá trị cùng kiểu**, **sai codec**, **sai tên marker**, **trùng tên** và **khác múi giờ** trước khi dữ liệu production bị ghi sai.
9. Kết nối đúng **partition key → routing key → token → natural replicas**, không hiểu bind đơn thuần là phép thay chuỗi.

**Phạm vi dịch vụ `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Apache Cassandra là hệ quản trị wide-column phân tán. Mô hình bảng thường được thiết kế theo truy vấn; partition key quyết định token/replicas và các lựa chọn consistency đọc/ghi vẫn quan trọng khi gọi từ Java. Bind sai không chỉ gây exception: đôi khi query **vẫn thành công nhưng chạm nhầm partition**, nguy hiểm hơn lỗi type fail-fast.

## 2. Bức tranh tổng thể: chuẩn bị, gắn giá trị, thực thi

~~~text
         Java service / Repository
                   |
         CQL có bind markers
          ?           :name
                   |
            session.prepare()
                   |
           PREPARE tới Cassandra
             schema / types
                   |
        PreparedStatement (dùng lại)
             |              |
        bind(...)        bind() rồi
        theo vị trí      setXxx(name)
             |              |
             +------+-------+
                    |
          BoundStatement bất biến
          giá trị đã encode + metadata
                    |
            session.execute(...)
                    |
           Coordinator và replicas
                    |
                ResultSet
                    |
            Row.getXxx(...) đúng type
~~~

### 2.1. Prepared statement không phải nối chuỗi SQL

Giả sử:

~~~java
String cql =
    "SELECT event_id, status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?";

PreparedStatement prepared = session.prepare(cql);
BoundStatement request =
    prepared.bind("tenant-a", LocalDate.parse("2026-11-21"));
ResultSet result = session.execute(request);
~~~

CQL text được parse khi `prepare`, driver gửi **prepared ID + các giá trị đã serialize theo CQL type** khi `execute`. Nó không tạo câu text mới bằng cách thay `?` bằng `'tenant-a'`. Nhờ metadata của lệnh PREPARE, driver có thể kiểm codec và tính routing key khi đủ partition-key components. Xem [Java Driver — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

### 2.2. Những cấu phần quan trọng

| Thành phần | Vai trò | Không nên hiểu thành |
|---|---|---|
| `CqlSession` | Kết nối, pools, metadata và thực thi CQL; tái sử dụng trong app | Session mới cho từng query |
| `PreparedStatement` | Truy vấn đã chuẩn bị + metadata biến/kiểu/routing | Một kết quả CQL đã chạy |
| `BoundStatement` | Prepared statement với giá trị cụ thể, execute được | String SQL nối thêm literal |
| `BoundStatementBuilder` | Tạo bound object, setter mutable trong builder, sau đó `build()` | Object an toàn dùng chung giữa threads trong khi đang sửa |
| `ColumnDefinitions` | Mô tả tên/kiểu/slot của bind vars hoặc result cols | Toàn bộ schema table/version history |
| `TypeCodec` | Encode/decode một CQL type ↔ Java type | Phép validate nghiệp vụ cho mọi dữ liệu |
| `Row` | Kết quả chứa typed values + column metadata | Bản ghi Java tự ánh xạ hoàn toàn |

**Tách thời điểm lỗi:** CQL sai/schema không tồn tại thường bị phát hiện khi `prepare`; Java/CQL type mismatch thường xảy ra lúc **bind**; timeout/quorum/authorization có thể xảy ra lúc **execute**; đọc `Row` sai getter hoặc cast có thể lỗi ở **decode**.

### 2.3. Quy trình tư duy trước mỗi statement

~~~text
1. CQL nào phục vụ đúng truy vấn?
2. Có bao nhiêu bind markers và thứ tự của chúng?
3. Tên marker nào là duy nhất? Có marker lặp?
4. Metadata báo mỗi marker thuộc CQL type nào?
5. Java DTO field có đúng type/precision/timezone không?
6. Null, unset hay fail validation cho trường này?
7. Bind đủ partition key và set CL/idempotency đúng?
8. Execute và decode kết quả bằng đúng getter?
9. Đối chiếu primary key và giá trị nghiệp vụ?
~~~

## 3. Schema CQL làm nền cho các ví dụ

Bài dùng **lab Cassandra một node** để tập trung vào binding, không phải hiệu năng. Trên cluster nhiều datacenter, dùng `NetworkTopologyStrategy` với RF/DC thật và consistency level được review.

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_bind_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS java_bind_lab.events_by_tenant_day (
  tenant_id text,
  day date,
  event_time timestamp,
  event_id uuid,
  status text,
  amount decimal,
  note text,
  tags set<text>,
  PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
  event_time DESC,
  event_id ASC
);

CREATE TABLE IF NOT EXISTS java_bind_lab.customer_profiles (
  tenant_id text,
  customer_id uuid,
  name text,
  age int,
  active boolean,
  updated_at timestamp,
  PRIMARY KEY ((tenant_id), customer_id)
);
~~~

### 3.1. Hai nhóm khóa cần nhớ

| Bảng | Partition key | Clustering key | Ví dụ truy vấn phù hợp |
|---|---|---|---|
| `events_by_tenant_day` | `(tenant_id, day)` | `(event_time, event_id)` | Event của tenant trong một ngày hoặc event cụ thể |
| `customer_profiles` | `tenant_id` | `customer_id` | Hồ sơ một customer trong tenant |

Trong bảng `events_by_tenant_day`, hai giá trị Java `tenantId:String` và `day:LocalDate` **phải được bind đúng vị trí hoặc đúng tên**. Nếu đảo hai vị trí có type khác nhau, driver thường chặn bằng codec; nếu cả hai đều `text` (ví dụ bảng khác có `region text, tenant_id text`), đảo chúng có thể **không báo lỗi** và query đi tới partition khác.

### 3.2. Không dùng SimpleStrategy làm công thức production

`SimpleStrategy` RF=1 chỉ phù hợp demo một node. Đối với nhiều nodes/DC, cấu hình RF theo topology thực, ví dụ:

~~~sql
-- Chỉ minh họa khi các DC tên dc1/dc2 tồn tại thật.
CREATE KEYSPACE production_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};
~~~

CL là thuộc tính **request**, RF là thuộc tính keyspace. Một getter `getUuid("event_id")` đúng kiểu không chứng minh mọi replica đã có data; đó là hai lớp kiểm tra riêng.

## 4. Bind theo vị trí với dấu `?`

### 4.1. Trật tự là thứ tự xuất hiện trong CQL

~~~java
PreparedStatement insert = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name, age, active, updated_at) " +
    "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.bind(
    "tenant-a",                                    // slot 0: text
    UUID.fromString("11111111-1111-1111-1111-111111111111"), // 1: uuid
    "Linh",                                        // 2: text
    28,                                            // 3: int
    true,                                          // 4: boolean
    Instant.parse("2026-11-21T04:00:00Z")          // 5: timestamp
);

session.execute(bound);
~~~

**Chỉ số bắt đầu bằng 0**, không phải 1. Các vị trí tham chiếu **thứ tự `?` trong statement**, **không phải** thứ tự cột trong `CREATE TABLE`, `PRIMARY KEY` hay thứ tự alphabetical. Nếu người đọc sửa danh sách cột mà không sửa mảng bind, query có thể fail sớm hoặc lưu sai dữ liệu.

### 4.2. Chọn setter theo index

~~~java
BoundStatement bound = insert.bind()
    .setString(0, "tenant-a")
    .setUuid(1, UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setString(2, "Linh")
    .setInt(3, 28)
    .setBoolean(4, true)
    .setInstant(5, Instant.parse("2026-11-21T04:00:00Z"));
~~~

Với driver 4.x, built-in `BoundStatement` **bất biến**, mỗi setter trả **instance mới**. Code chaining trên nhận đúng giá trị. Đoạn dưới sai:

~~~java
BoundStatement bad = insert.bind();
bad.setString(0, "tenant-a");  // trả object mới nhưng bị bỏ
session.execute(bad);          // tenant_id vẫn UNSET
~~~

Ngay cả khi statement được execute, **PK UNSET** không hợp lệ, nên server có thể báo lỗi. Trong các mutation khác, bỏ setter cho regular column có thể khiến cột bị bỏ qua không báo lỗi, nguy hiểm hơn. Xem [Java Driver — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) và [Upgrade guide](https://apache.github.io/cassandra-java-driver/4.18.0/upgrade-README/).

### 4.3. Builder: nhiều setter mà tránh tạo quá nhiều object

~~~java
BoundStatement request = insert.boundStatementBuilder()
    .setString(0, "tenant-a")
    .setUuid(1, UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setString(2, "Linh")
    .setInt(3, 28)
    .setBoolean(4, true)
    .setInstant(5, Instant.parse("2026-11-21T04:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .build();
~~~

`BoundStatementBuilder` là **mutable** và không thread-safe trong lúc build; đừng chia sẻ builder giữa requests/threads. `BoundStatement` đã build thì thread-safe theo triển khai mặc định, nhưng vẫn nên tạo object riêng cho mỗi bộ values. Có thể chia sẻ **`PreparedStatement`** giữa nhiều threads.

### 4.4. Đổi thứ tự query nhưng quên đổi bind

~~~java
// Ban đầu:
String cql1 = "SELECT name FROM java_bind_lab.customer_profiles " +
              "WHERE tenant_id = ? AND customer_id = ?";
// bind: (String tenantId, UUID customerId)

// Sau refactor:
String cql2 = "SELECT name FROM java_bind_lab.customer_profiles " +
              "WHERE customer_id = ? AND tenant_id = ?";
// BẮT BUỘC đổi thứ tự bind thành (UUID customerId, String tenantId).
~~~

Trong trường hợp trên driver sẽ phát hiện mismatch nếu bind cũ vì `uuid` khác `text`. Nhưng với hai columns cùng type `text`, sai thứ tự **vẫn encode được** và có thể tạo ra kết quả rỗng hoặc ghi nhầm tenant. Type safety là **lớp bảo vệ cần nhưng chưa đủ**.

## 5. Bind theo tên với marker `:name`

### 5.1. Khai báo marker rõ nghĩa

~~~java
PreparedStatement insertNamed = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name, age, active, updated_at) " +
    "VALUES (:tenant, :customer, :full_name, :age_years, " +
    ":is_active, :modified_at)");

BoundStatement named = insertNamed.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", UUID.fromString(
        "22222222-2222-2222-2222-222222222222"))
    .setString("full_name", "Minh")
    .setInt("age_years", 31)
    .setBoolean("is_active", true)
    .setInstant("modified_at",
        Instant.parse("2026-11-21T05:00:00Z"));

session.execute(named);
~~~

`:full_name` là **bind marker** do tác giả query đặt; nó **không cần trùng tên cột `name`**. Khi gọi setter, **không thêm dấu `:`**: dùng `setString("full_name", ...)`, không phải `setString(":full_name", ...)`.

### 5.2. Named setter cũng có thể dùng với `?`

Khi chuẩn bị `INSERT ... (tenant_id, name) VALUES (?, ?)`, Cassandra có thể đặt tên metadata cho marker theo cột tương ứng, nên:

~~~java
PreparedStatement p = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name) VALUES (?, ?, ?)");

BoundStatement b = p.bind()
    .setString("tenant_id", "tenant-a")
    .setUuid("customer_id", UUID.fromString(
        "33333333-3333-3333-3333-333333333333"))
    .setString("name", "Thu");
~~~

**Tuy nhiên, không mặc định rằng tên marker luôn đúng với cột khi query phức tạp.** Đọc metadata `getVariableDefinitions()` hoặc khai báo `:name` tường minh khi cần bảo đảm ý nghĩa. Đặc biệt với nhiều điều kiện trên cùng một cột, tên được suy ra có thể **trùng nhau**. Xem [Prepared statements — Parameters and binding](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

### 5.3. Trùng tên marker và range query: bẫy lớn

~~~sql
-- Bản truy vấn dễ gây nhập nhằng:
SELECT event_time, status
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND day = ?
  AND event_time >= ?
  AND event_time < ?;
~~~

Hai marker cuối thường được đặt tên metadata theo cùng column `event_time`. Gọi `setInstant("event_time", x)` có thể áp **x lên tất cả occurrences** của tên đó, biến điều kiện thành khoảng rỗng `event_time >= x AND event_time < x`. API [SettableByName](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/SettableByName.html) mô tả rõ setter theo tên ghi **mọi occurrences** trùng tên, không chỉ một.

**Cách 1 — Sử dụng index cho hai điều kiện khác nhau:**

~~~java
PreparedStatement byRange = session.prepare(
    "SELECT event_time, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? " +
    "AND event_time >= ? AND event_time < ?");

BoundStatement window = byRange.bind()
    .setString(0, "tenant-a")
    .setLocalDate(1, LocalDate.parse("2026-11-21"))
    .setInstant(2, Instant.parse("2026-11-21T00:00:00Z"))
    .setInstant(3, Instant.parse("2026-11-22T00:00:00Z"));
~~~

**Cách 2 — Khai báo tên marker không nhập nhằng:**

~~~java
PreparedStatement rangeNamed = session.prepare(
    "SELECT event_time, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant " +
    "AND day = :target_day " +
    "AND event_time >= :start_time " +
    "AND event_time < :end_time");

BoundStatement windowNamed = rangeNamed.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"))
    .setInstant("start_time", Instant.parse("2026-11-21T00:00:00Z"))
    .setInstant("end_time", Instant.parse("2026-11-22T00:00:00Z"));
~~~

**Ràng buộc thực tế:** Một CQL query phải hợp lệ cho partition/clustering restrictions trước khi được prepare; dùng cùng clustering column cho hai điều kiện range là một dạng truy vấn hợp lý trên bảng minh họa. Việc đổi cách bind **không** tự hợp thức hóa các truy vấn thiếu partition key hoặc `ALLOW FILTERING` thiếu cơ sở.

## 6. Tên CQL, quoted identifiers và sự khác nhau giữa tên marker/tên cột

### 6.1. Ba loại tên trong một statement

~~~sql
SELECT status
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant
  AND day = :report_day;
~~~

| Thành phần | Cụ thể | Ý nghĩa |
|---|---|---|
| Tên keyspace/table | `java_bind_lab.events_by_tenant_day` | Schema identifier |
| Tên column | `tenant_id`, `day`, `status` | Column identifier |
| Tên bind marker | `tenant`, `report_day` | Khóa để ứng dụng gắn giá trị |

Không có hàm `setTableName("...")` để bind tên bảng bằng `?` hay `:table`. **Bind markers biểu diễn giá trị**, không phải tên CQL identifiers, `ORDER BY` clause hoặc toàn bộ cú pháp `WHERE`. Với multi-tenant, không nối tên bảng lấy từ HTTP request; chọn table/column từ **allowlist code-defined** và phân quyền dữ liệu ở tầng ứng dụng/CQL role.

### 6.2. Unquoted identifiers bị canonicalize về lowercase

Trong CQL:

~~~sql
-- Hai cách viết cùng tên không phân biệt hoa thường khi không quote:
SELECT status FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :Tenant AND day = :TargetDay;

SELECT status FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant AND day = :targetday;
~~~

Với **quoted identifiers**, case trở thành một phần của tên. Nếu schema bất khả kháng có column `"DisplayName"`, cách truy cập `getString("displayname")` và `getString("\"DisplayName\"")` có thể mang nghĩa khác. Driver 4.x dùng `CqlIdentifier` để phân biệt **CQL text form** và **internal canonical form**:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier ordinary = CqlIdentifier.fromCql("Tenant_ID");
System.out.println(ordinary.asInternal()); // tenant_id

CqlIdentifier quoted =
    CqlIdentifier.fromCql("\"DisplayName\"");
System.out.println(quoted.asInternal());    // DisplayName
~~~

**Hướng thiết kế:** ưu tiên snake_case **không quote** cho keyspace/table/columns và marker names. Với schema legacy case-sensitive, dùng `CqlIdentifier.fromCql(...)` hoặc overload phù hợp và kiểm metadata trả về, tránh đoán cách driver chuyển đổi `String`. Xem [Case Sensitivity — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/).

### 6.3. Vì sao named bind không phải “chống refactor tuyệt đối”?

Nếu query đổi `:tenant` thành `:tenant_id` nhưng Java vẫn gọi `setString("tenant", ...)`, driver có thể báo **unknown marker**. Điều này tốt hơn ghi nhầm âm thầm, nhưng bạn vẫn cần test statement construction. Nếu đổi **CQL column được gắn với marker** mà không đổi DTO mapping, code vẫn có thể bind một String hợp lệ tới một cột String **sai ngữ nghĩa**.

Không thiết kế code dựa vào khả năng driver “đoán đúng tên cột”: với query phức tạp, hãy **chuẩn hóa tên marker** và có test kiểm declared bind variables sau `prepare()`.

## 7. Kiểm metadata marker trước khi bind

### 7.1. `getVariableDefinitions()` biết những gì?

`PreparedStatement` được trả từ `session.prepare()` chứa `ColumnDefinitions` cho các bind markers. Mỗi definition có:

- **Index** theo thứ tự marker trong CQL.
- **Name** mà server gán: tên marker tường minh hoặc tên được suy ra từ context.
- **CQL type** mà Cassandra mong đợi, ví dụ `text`, `date`, `timestamp`, `uuid`, `decimal`.

Ví dụ Java:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;
import com.datastax.oss.driver.api.core.cql.ColumnDefinition;

PreparedStatement p = session.prepare(
    "SELECT event_time, event_id, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :report_day");

ColumnDefinitions defs = p.getVariableDefinitions();
for (int index = 0; index < defs.size(); index++) {
    ColumnDefinition def = defs.get(index);
    System.out.printf(
        "index=%d name=%s CQL type=%s%n",
        index, def.getName().asInternal(), def.getType());
}
~~~

Kỳ vọng (dạng minh họa):

~~~text
index=0 name=tenant CQL type=text
index=1 name=report_day CQL type=date
~~~

**Đừng hiểu metadata của bind vars là metadata của kết quả trả về.** `getVariableDefinitions()` mô tả **đầu vào**; `Row.getColumnDefinitions()` mô tả **các cột SELECT trả về**. Cùng một tên `status` có thể là bound variable trong UPDATE và một result column ở SELECT, nhưng chúng thuộc những object/bối cảnh khác nhau.

### 7.2. Assert số biến và kiểu, không chỉ in ra

~~~java
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

static void requireVariables(PreparedStatement p) {
    ColumnDefinitions defs = p.getVariableDefinitions();
    if (defs.size() != 2
            || !defs.contains("tenant")
            || !defs.contains("report_day")
            || !DataTypes.TEXT.equals(defs.get("tenant").getType())
            || !DataTypes.DATE.equals(defs.get("report_day").getType())) {
        throw new IllegalStateException(
            "Prepared query markers no longer match repository contract");
    }
}
~~~

Với các query dùng `?`, tên marker có thể được server suy ra; test quan trọng hơn là **số thứ tự và type theo index**:

~~~java
static void requirePositionalTypes(PreparedStatement p) {
    ColumnDefinitions defs = p.getVariableDefinitions();
    if (defs.size() != 2
            || !DataTypes.TEXT.equals(defs.get(0).getType())
            || !DataTypes.DATE.equals(defs.get(1).getType())) {
        throw new IllegalStateException("Unexpected bind layout");
    }
}
~~~

**Lưu ý phạm vi:** Các assert trên chứng minh rằng Java code có **mapping phù hợp type CQL**, nhưng không chứng minh `"tenant-a"` tồn tại, user có quyền truy cập tenant-a, hoặc giá trị `day` mang đúng timezone/bucket nghiệp vụ. Validation business phải bổ sung riêng.

### 7.3. Phát hiện tên marker trùng trước khi ghi

~~~java
ColumnDefinitions defs = rangeQuery.getVariableDefinitions();
for (int i = 0; i < defs.size(); i++) {
    String name = defs.get(i).getName().asInternal();
    if (defs.allIndicesOf(name).size() > 1) {
        System.out.printf(
            "ambiguous named binding: %s at slots %s%n",
            name, defs.allIndicesOf(name));
    }
}
~~~

Với ví dụ `event_time >= ? AND event_time < ?`, cảnh báo sẽ cho thấy `event_time` lặp hai lần. Không tự động kết luận query không hợp lệ: **positional setters** vẫn có thể điền hai slots khác nhau. Đây là cảnh báo để **không dùng cùng một named setter** cho hai giá trị mang ý nghĩa khác nhau. API `ColumnDefinitions.allIndicesOf` cho phép phát hiện trùng thay vì chỉ gọi `firstIndexOf`.

### 7.4. Đổi schema sau khi prepare

Một prepared statement có metadata tại thời điểm prepare. Nếu schema thay đổi tương thích, driver/server có cơ chế cập nhật hoặc reprepare tùy version/protocol; với thay đổi **type hoặc drop/recreate column/table**, không giả định object cũ vẫn đúng mãi.

Runbook khi thay type/schema:

1. Đổi CQL schema theo kế hoạch migration riêng, có schema agreement.
2. Đảm bảo các JVM có query text/DTO/codec tương thích.
3. Chạy integration tests prepare/bind/execute trên cluster đích.
4. Không dùng `SELECT *` trong code cần ổn định metadata qua schema evolution.
5. Xác minh results và failure rate sau deploy; theo dõi errors `UNPREPARED`/codec mismatch.

**Driver không biến `setString` thành `setInstant`** khi DB đổi column từ text sang timestamp. Schema migration phải thay code/codec/chính sách dữ liệu, không chỉ retry query.

## 8. Bảng ánh xạ CQL ↔ Java: lựa chọn setter/getter

| CQL type | Java type thường dùng | Setter trong bound statement | Getter trên `Row` | Cần chú ý |
|---|---|---|---|---|
| `ascii`, `text`, `varchar` | `String` | `setString` | `getString` | Unicode UTF-8, không tự trim/casefold |
| `boolean` | `boolean`/`Boolean` | `setBoolean` | `getBoolean` | Primitive getter trả false khi NULL; dùng `isNull` |
| `tinyint` | `byte`/`Byte` | `setByte` | `getByte` | Range -128..127 |
| `smallint` | `short`/`Short` | `setShort` | `getShort` | Range -32768..32767 |
| `int` | `int`/`Integer` | `setInt` | `getInt` | NULL vs 0; overflow khi parse |
| `bigint`/`counter` | `long`/`Long` | `setLong` | `getLong` | Counter UPDATE có semantics khác upsert |
| `varint` | `BigInteger` | `setBigInteger` | `getBigInteger` | Không tự ép về long |
| `decimal` | `BigDecimal` | `setBigDecimal` | `getBigDecimal` | Không dùng float/double cho tiền |
| `float` | `float` | `setFloat` | `getFloat` | IEEE-754 precision/NaN policy |
| `double` | `double` | `setDouble` | `getDouble` | Không thay `decimal` nghiệp vụ |
| `uuid`/`timeuuid` | `UUID` | `setUuid` | `getUuid` | `timeuuid` cần UUID version 1 hợp lệ |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` | Không chứa timezone hay giờ |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` | Không chứa ngày/timezone |
| `timestamp` | `Instant` | `setInstant` | `getInstant` | Instant tuyệt đối, CQL storage tính ms |
| `duration` | `CqlDuration` | `setCqlDuration` | `getCqlDuration` | Khác `java.time.Duration` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` | Xác nhận IPv4/IPv6 |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` | Position/limit, không assume array |
| `list<text>` | `List<String>` | `setList(..., String.class)` | `getList(..., String.class)` | CQL list ordered, có update semantics |
| `set<text>` | `Set<String>` | `setSet(..., String.class)` | `getSet(..., String.class)` | Uniqueness; order không guaranteed |
| `map<text,int>` | `Map<String,Integer>` | `setMap(..., String.class, Integer.class)` | `getMap(..., String.class, Integer.class)` | Không có null key/value |
| `tuple<...>` | `TupleValue` | `setTupleValue` | `getTupleValue` | Thứ tự field là contract |
| UDT | `UdtValue` | `setUdtValue` | `getUdtValue` | Field names/types phải trùng schema |

Xem [Core Driver — CQL to Java type mapping](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/) để đối chiếu phiên bản. Bộ codec có thể được mở rộng, nhưng phải có mapping **đúng CQL type và Java type**; không giả định driver tự chuyển mọi `String` sang UUID, decimal hay timestamp.

### 8.1. Trường hợp type mismatch có thể fail sớm

~~~java
PreparedStatement p = session.prepare(
    "SELECT status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :target_day");

// ĐÚNG: day là CQL date, tương ứng Java LocalDate.
BoundStatement good = p.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"));

// SAI (trong điều kiện codec mặc định):
// p.bind().setString("target_day", "2026-11-21");
// CQL type date không dùng default String setter.
~~~

Một chuỗi trông giống ngày **không phải** `LocalDate` tự động. Parse và validate ở boundary của ứng dụng; chỉ chuyển object typed đã hợp lệ sang bound statement.

### 8.2. Fail-fast và các lớp kiểm còn thiếu

| Loại kiểm | Ai làm? | Ví dụ |
|---|---|---|
| Số marker/bind values | Driver | Quá nhiều giá trị trong `bind(Object...)` gây lỗi |
| Marker name/index | Driver | `setString("typo", ...)` không có trong metadata |
| Codec type CQL↔Java | Driver/codec registry | `setUuid` cho `date` |
| Hợp lệ của primary key | Cassandra/CQL rules | NULL/UNSET trong partition key |
| Ràng buộc nghiệp vụ | Ứng dụng | tenant authorization, age >= 0 |
| Consistency/availability | Replica/CL/coordinator | RF3 `LOCAL_QUORUM` thiếu replica |
| Đúng kết quả cuối cùng | Tests/reconciliation | Không đảo hai `text` fields cùng type |

**Không suy rằng bind thành công nghĩa là write đúng:** driver kiểm encoding, không tự biết `customer_id` có thuộc `tenant_id`, status chuyển `NEW → PAID` có hợp lệ hay không, hoặc event timestamp có nằm đúng partition-day.

## 9. `bind(Object...)`, named setter và generic `set`: chọn kiểu an toàn

### 9.1. Ưu tiên typed setter khi code cần dễ review

~~~java
BoundStatement b = p.bind()
    .setString("tenant", tenantId)
    .setLocalDate("target_day", day);
~~~

Code cho thấy mapping ngay tại vị trí bind, nên reviewer dễ kiểm soát hơn `bind(tenantId, day)` khi số marker lớn. Ngược lại, `bind(Object...)` ngắn và phù hợp các statement có vài fields, **khi test metadata/ordering đã bảo vệ**.

### 9.2. Generic overload có type hint

~~~java
// Ví dụ với marker CQL decimal:
BoundStatement b = decimalPrepared.bind()
    .set("amount", new BigDecimal("1200.50"), BigDecimal.class);
~~~

Đối với kiểu collection lồng nhau không mô tả đủ bằng `Class`, dùng `GenericType<T>`; với codec tùy biến, dùng overload truyền `TypeCodec<T>` đã đăng ký/được kiểm:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<List<String>> listOfText = new GenericType<List<String>>() {};
BoundStatement b = listPrepared.bind()
    .set("labels", List.of("new", "paid"), listOfText);
~~~

Chỉ dùng đoạn trên khi `labels` có CQL type `list<text>` trên bảng tương ứng. Bảng `events_by_tenant_day` lab dùng `tags set<text>`, nên **không** áp `setList("tags",...)` cho bảng đó; dùng `setSet("tags",...)`.

### 9.3. `bind(Object...)` có thể chấp nhận ít values hơn markers

Driver 4.x cho phép `prepared.bind()` hoặc `bind(v0, v1)` với số values **ít hơn** số marker; những slots còn lại ở trạng thái **UNSET** khi protocol hỗ trợ. Nếu truyền **nhiều values hơn số marker**, driver từ chối. <https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/PreparedStatement.html>

Điều này không có nghĩa “có thể bỏ tùy ý mọi tham số”. Nếu UNSET là partition key hoặc một value cần để tính điều kiện WHERE, query có thể fail server-side. Trong UPDATE, UNSET ở regular column có thể cố ý biểu diễn “đừng thay đổi field đó”; nên validation phải dựa trên **loại statement và business semantics**.

## 10. `NULL`, `UNSET` và giá trị Java `null`: ba khái niệm không được trộn

### 10.1. Trạng thái của một bind variable

| Trạng thái | Cách tạo | Với UPDATE của regular column | Với partition-key marker |
|---|---|---|---|
| Giá trị cụ thể | `setString("name", "Linh")` | Ghi giá trị mới | Dùng để xác định partition |
| **CQL NULL** | `setToNull("name")` hoặc typed setter cho nullable reference | Có thể tạo **tombstone**/xóa giá trị cũ | Không hợp lệ |
| **UNSET** | `bind()` chưa set; `unset(index)` | Cột bị bỏ qua (không tạo tombstone chỉ vì UNSET) | Không hợp lệ cho key required |

**Không equate “field bị thiếu trong JSON PATCH” với “gửi CQL NULL”.** Field thiếu thường biểu diễn **không thay đổi**; field được gửi với null có thể biểu diễn **xóa** theo contract API. Hai hành vi cần mã hóa rõ trong code.

### 10.2. Ví dụ cập nhật chọn lọc hồ sơ

~~~java
PreparedStatement update = session.prepare(
    "UPDATE java_bind_lab.customer_profiles " +
    "SET name = :new_name, age = :new_age, active = :new_active " +
    "WHERE tenant_id = :tenant AND customer_id = :customer");

UUID id = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

// PATCH: chỉ đổi name, không đụng age/active.
BoundStatement patch = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setString("new_name", "Linh Trần");

// new_age và new_active vẫn UNSET.
session.execute(patch);
~~~

Với native protocol V4+ và lệnh UPDATE hỗ trợ UNSET, `age`/`active` không bị xóa và không được ghi lại. Cùng API nếu gọi:

~~~java
BoundStatement eraseAge = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setToNull("new_age");

session.execute(eraseAge);
~~~

Trường `age` được yêu cầu xóa (CQL NULL/tombstone), **khác** với `new_age` UNSET. Việc cho phép xóa tuổi của khách hàng phải được quyết định trong validation nghiệp vụ; driver không biết field nào được phép null.

### 10.3. Tránh `null` của Java bị hiểu sai

`bind(..., null)` và `setString("note", null)` có thể encode **CQL NULL** theo codec, không phải “không truyền marker”. Khi xử lý API `PATCH`, không truyền thẳng tất cả DTO fields qua `bind(Object...)` nếu chúng dùng Java null đồng thời cho **absent** và **clear**.

Mô hình ba trạng thái tường minh:

~~~java
sealed interface PatchField<T>
        permits PatchField.Unspecified,
                PatchField.Clear,
                PatchField.Value {
    record Unspecified<T>() implements PatchField<T> {}
    record Clear<T>() implements PatchField<T> {}
    record Value<T>(T value) implements PatchField<T> {}
}
~~~

Áp vào biến `new_name`:

~~~java
static BoundStatement applyName(
        BoundStatement statement, PatchField<String> field) {
    if (field instanceof PatchField.Unspecified<?>) {
        return statement.unset("new_name");
    }
    if (field instanceof PatchField.Clear<?>) {
        return statement.setToNull("new_name");
    }
    if (field instanceof PatchField.Value<?> value) {
        return statement.setString(
            "new_name", (String) value.value());
    }
    throw new IllegalStateException("Unsupported patch field");
}
~~~

Trong code thật, generic/validation nên bảo đảm `Value` không chứa null, mọi input đã được kiểm quyền và field allowed. Ví dụ chỉ minh họa semantics: **absent → UNSET**, **clear → NULL**, **value → giá trị typed**.

### 10.4. Kiểm `isSet` và `isNull`

~~~java
BoundStatement b = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setToNull("new_age");

System.out.println(b.isSet("new_age")); // true
System.out.println(b.isNull("new_age")); // true
System.out.println(b.isSet("new_name")); // false (UNSET)
~~~

`isSet` trả biến đã được set hay chưa; `isNull` trả trạng thái NULL. Cần kiểm `isSet` **trước khi đọc getter của slot UNSET**. Đặc biệt với marker name trùng nhau, `isSet(name)`/`unset(name)` theo API `Bindable` thao tác/kiểm **first occurrence**, trong khi `setXxx(name)` của `SettableByName` ghi **mọi occurrences**. Vì vậy **không dùng tên trùng để encode nhiều giá trị khác nhau**; kiểm `allIndicesOf(name)` và dùng chỉ số khi cần. Xem [Bindable 4.17 API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/Bindable.html).

### 10.5. Những ngoại lệ quan trọng

- **Primary key:** không được NULL/UNSET nếu lệnh cần khóa để xác định row; reject input tại boundary.
- **LWT `IF ...`:** UNSET không phải wildcard trong condition; kiểm rules theo loại marker.
- **TTL:** NULL có thể sinh tombstone, UNSET thường không update field. Không giả định mọi operation với TTL xử lý giống nhau.
- **Counter:** không thay increment bằng NULL/UNSET tùy tiện; counter có mutation rules riêng.
- **Collections:** NULL, empty collection và UNSET có semantics khác nhau; cần review schema/cú pháp CQL và version.
- **Protocol:** UNSET được hỗ trợ từ native protocol V4 (Cassandra 2.2+). Các protocol cũ hơn không cho bỏ tất cả biến cần thiết.

## 11. Primitive getters và lỗi “NULL biến thành 0/false”

Một vấn đề chỉ xuất hiện ở phía **đọc dữ liệu**:

~~~java
Row row = session.execute(selectCustomer).one();

// Nguy hiểm nếu age là nullable:
int age = row.getInt("age");
// Khi CQL age = NULL, primitive getter mặc định trả 0.
// 0 có thể bị nhầm với một độ tuổi hợp lệ/giá trị ẩn.
~~~

Các getter kiểu primitive `getInt`, `getLong`, `getBoolean` không thể trả Java `null`. Với CQL NULL, chúng trả giá trị mặc định 0/false; phải dùng `row.isNull(...)` hoặc wrapper type:

~~~java
Integer age = row.isNull("age")
    ? null
    : row.getInt("age");

Boolean active = row.isNull("active")
    ? null
    : row.getBoolean("active");

// Hoặc nếu driver có codec tương ứng:
Integer age2 = row.get("age", Integer.class);
~~~

**Lỗi nghiệp vụ:** Nếu bạn dùng `if (age == 0) ...` để biểu diễn “chưa cập nhật tuổi”, đã trộn hai trạng thái `NULL` và `0`. Hợp đồng DTO/REST/GraphQL phải giữ được tính khác nhau nếu nghiệp vụ yêu cầu.

### 11.1. Null primitive khác collection

Một số built-in collection codecs có thể decode CQL NULL thành **empty collection** theo chính sách codec; không dùng `getSet("tags")` trả empty để kết luận dữ liệu là CQL empty set đã được ghi. Nếu phân biệt NULL/empty quan trọng, dùng `row.isNull("tags")` và kiểm semantics của driver version. <https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/>

## 12. Ngày, giờ và độ chính xác: type đúng chưa chắc business đúng

### 12.1. Ba kiểu khác nhau

| CQL | Java | Ý nghĩa |
|---|---|---|
| `date` | `LocalDate` | Một **ngày lịch** không chứa giờ/timezone |
| `time` | `LocalTime` | Giờ trong ngày, không mang ngày/timezone |
| `timestamp` | `Instant` | Một thời điểm tuyệt đối; CQL timestamp lưu độ phân giải milliseconds |

Ví dụ:

~~~java
LocalDate localBusinessDay =
    LocalDate.parse("2026-11-21");

Instant absoluteEventTime =
    Instant.parse("2026-11-21T08:00:00Z");

BoundStatement event = insertEvent.bind()
    .setLocalDate("target_day", localBusinessDay)
    .setInstant("event_time", absoluteEventTime);
~~~

Một `Instant` có thể biểu diễn mốc thời gian chính xác tới nanosecond trong Java, nhưng Cassandra `timestamp` lưu **milliseconds**; khi round-trip, phần micro/nano có thể mất. Nếu nghiệp vụ cần microsecond ordering, cân nhắc dùng `timeuuid`, version sequence hoặc một field hỗ trợ precision được thiết kế riêng.

### 12.2. Quy đổi timezone phải xảy ra tại boundary

Ví dụ một client gửi:

~~~text
2026-11-21T00:30:00+07:00
~~~

Thời điểm tuyệt đối tương ứng:

~~~text
2026-11-20T17:30:00Z
~~~

Code Java:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneId;

OffsetDateTime submitted =
    OffsetDateTime.parse("2026-11-21T00:30:00+07:00");
Instant stored = submitted.toInstant();

LocalDate utcDay = stored.atZone(
    ZoneId.of("UTC")).toLocalDate();
LocalDate vietnamDay = stored.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
~~~

Với ví dụ này, **UTC day là 2026-11-20**, còn **ngày tại Việt Nam là 2026-11-21**: cùng một `Instant` có thể nằm ở hai bucket ngày khác nhau. Hãy định nghĩa rõ `day` là UTC day hay business-local day. Không parse `LocalDateTime` rồi tùy tiện coi là UTC.

### 12.3. Lỗi timezone không phải CodecException

Nếu app bind `day=2026-11-20` thay vì 2026-11-21 vì timezone policy sai, driver vẫn encode `LocalDate` hợp lệ. CQL query có thể trả 0 rows, không có lỗi kiểu. Đây là một ví dụ quan trọng của việc **type checks không thay thế data validation**.

### 12.4. UUID, timeuuid và source of identity

~~~java
UUID eventId =
    UUID.fromString("22222222-2222-2222-2222-222222222222");
~~~

`UUID.fromString` chỉ kiểm cấu trúc UUID chứ không bảo đảm business identity tồn tại; `UUID.randomUUID()` tạo v4, không thể dùng làm `timeuuid` yêu cầu version 1. Nếu retry ghi cùng event, **phải giữ cùng ID** để không sinh hàng trùng logic; tạo một UUID mới ở mỗi retry làm nát idempotency.

### 12.5. Decimal, số nguyên và precision

~~~java
BigDecimal correctMoney = new BigDecimal("1200.50");

// Tránh tạo tiền từ double khi đòi precision exact:
BigDecimal riskyMoney = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` có thể chứa giá trị biểu diễn nhị phân của double, không phải đúng decimal 0.1. Với tiền tệ, parse từ chuỗi kiểm chuẩn/decimal source và đặt scale/rounding policy. `decimal` của Cassandra lưu số thập phân độ chính xác tùy ý; Java nên dùng `BigDecimal`, không chuyển sang float/double cho dễ bind.

Các kiểu `int`, `bigint`, `varint` có ranges khác nhau. Dữ liệu vượt Integer.MAX_VALUE không nên truncate/cast để ép vào `int`; chọn schema và validation đúng từ đầu.

## 13. Collection binding: type của **phần tử** cũng là hợp đồng

### 13.1. `setSet` trên bảng lab

~~~java
PreparedStatement tagsInsert = session.prepare(
    "INSERT INTO java_bind_lab.events_by_tenant_day " +
    "(tenant_id, day, event_time, event_id, tags) " +
    "VALUES (:tenant, :target_day, :event_time, :event_id, :tags)");

BoundStatement withTags = tagsInsert.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"))
    .setInstant("event_time",
        Instant.parse("2026-11-21T08:00:00Z"))
    .setUuid("event_id", UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setSet("tags", Set.of("order", "created"), String.class);
~~~

`tags` có CQL type `set<text>`. Nếu bạn dùng `List<String>` hoặc `Set<Integer>`, không có nghĩa registry tự chuyển nó thành set<text>. Dùng getter:

~~~java
Set<String> tags = row.getSet("tags", String.class);
~~~

Thứ tự iteration của `Set` không phải contract nghiệp vụ. Khi cần thứ tự/duplicates, `list` có semantics khác; không đổi schema collection chỉ để tiện Java.

### 13.2. List và Map

Ví dụ **chỉ khi schema có**:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.collection_demo (
  tenant_id text,
  demo_id uuid,
  labels list<text>,
  metrics map<text,int>,
  PRIMARY KEY ((tenant_id), demo_id)
);
~~~

Java:

~~~java
PreparedStatement p = session.prepare(
    "INSERT INTO java_bind_lab.collection_demo " +
    "(tenant_id, demo_id, labels, metrics) " +
    "VALUES (:tenant, :id, :labels, :metrics)");

BoundStatement request = p.bind()
    .setString("tenant", "tenant-a")
    .setUuid("id", UUID.fromString(
        "55555555-5555-5555-5555-555555555555"))
    .setList("labels", List.of("new", "paid"), String.class)
    .setMap("metrics", Map.of("attempts", 1),
        String.class, Integer.class);
~~~

Các collections trong Cassandra có update/tombstone và read amplification semantics riêng. Nếu cần lưu nhiều events, **không** thay một bảng wide-column với clustering keys bằng một danh sách khổng lồ trong một column chỉ vì `setList` dễ gọi.

### 13.3. Nested types và `GenericType`

Với cấu trúc generic lồng nhau (ví dụ `frozen<list<text>>` trong một collection), Java `List.class`/`Set.class` không mang đủ thông tin phần tử vì type erasure. Sử dụng `GenericType`:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<List<String>> labelsType =
    new GenericType<List<String>>() {};

BoundStatement b = p.bind()
    .set("labels", List.of("a", "b"), labelsType);
~~~

Đừng tạo `new GenericType<...>(){}` trong hot loop hàng triệu lần; giữ constant tĩnh bất biến khi workload cần. Khi ứng dụng cần nested collection phức tạp, xác minh CQL `frozen`/collection compatibility và serializer phiên bản trước khi đưa vào production.

## 14. UDT và Tuple: không bind một `Map` hoặc `List` tùy ý

### 14.1. User-defined type với field names có hợp đồng

Ví dụ lab tạo UDT:

~~~sql
CREATE TYPE IF NOT EXISTS java_bind_lab.postal_address (
  city text,
  postal_code int
);

CREATE TABLE IF NOT EXISTS java_bind_lab.customer_addresses (
  tenant_id text,
  customer_id uuid,
  address frozen<postal_address>,
  PRIMARY KEY ((tenant_id), customer_id)
);
~~~

**Lưu ý:** `frozen<postal_address>` hợp lệ nếu type nằm trong cùng keyspace với bảng; nếu client dùng fully qualified names, phải resolve đúng `java_bind_lab.postal_address`. Type UDT có field order/name/types riêng; không thể chỉ tạo Java `Map.of("city","...")` rồi mong `setUdtValue` hiểu cách encode.

Java lấy định nghĩa **từ schema metadata đích**:

~~~java
import com.datastax.oss.driver.api.core.type.UserDefinedType;
import com.datastax.oss.driver.api.core.data.UdtValue;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace("java_bind_lab")
    .flatMap(keyspace -> keyspace.getUserDefinedType("postal_address"))
    .orElseThrow(() -> new IllegalStateException("Missing address UDT"));

UdtValue address = addressType.newValue()
    .setString("city", "Hồ Chí Minh")
    .setInt("postal_code", 700000);

PreparedStatement insertAddress = session.prepare(
    "INSERT INTO java_bind_lab.customer_addresses " +
    "(tenant_id, customer_id, address) VALUES (:tenant, :customer, :address)");

BoundStatement b = insertAddress.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", UUID.fromString(
        "66666666-6666-6666-6666-666666666666"))
    .setUdtValue("address", address);

session.execute(b);
~~~

**Lỗi thường gặp:** UDT được tạo trên cluster A với fields/order khác cluster B, rồi copy binary/`UdtValue` sang B. Hãy lấy UDT schema từ **session/cluster đích** và chuyển fields riêng khi có version hoặc codec khác. Đừng tự tạo UDT metadata bằng internal APIs để “làm vừa” giá trị. Xem [UDTs — Cassandra Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/).

### 14.2. Tuple: bind theo slot bên trong tuple

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.measurements (
  tenant_id text,
  measurement_id uuid,
  coordinate tuple<text,int>,
  PRIMARY KEY ((tenant_id), measurement_id)
);
~~~

Java:

~~~java
import com.datastax.oss.driver.api.core.type.TupleType;
import com.datastax.oss.driver.api.core.data.TupleValue;

PreparedStatement insertMeasurement = session.prepare(
    "INSERT INTO java_bind_lab.measurements " +
    "(tenant_id, measurement_id, coordinate) " +
    "VALUES (:tenant, :mid, :coordinate)");

TupleType coordType = (TupleType) insertMeasurement
    .getVariableDefinitions()
    .get("coordinate")
    .getType();

TupleValue coord = coordType.newValue()
    .setString(0, "floor")
    .setInt(1, 12);

BoundStatement b = insertMeasurement.bind()
    .setString("tenant", "tenant-a")
    .setUuid("mid", UUID.fromString(
        "77777777-7777-7777-7777-777777777777"))
    .setTupleValue("coordinate", coord);
~~~

Tuple position `0` là `text`, `1` là `int` theo **khai báo tuple**, không theo một map key. Khác với named markers của CQL statement, fields của tuple không có tên để gọi `setString("foo")`. Nếu tuple type đổi order sau migration, payload code phải đổi theo. Xem [Tuples — Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/).

### 14.3. Version 4.x và tính bất biến

`UdtValue`/`TupleValue` của driver 4.x có setters trả object mới theo built-in immutability conventions. Dùng chain `newValue().setXxx(...).setYyy(...)` hoặc reassign; không gọi setter rồi bỏ object trả về. Nếu xử lý nhiều fields, dùng type-safe codecs và test round-trip; đừng dựa vào `toString()` cho dữ liệu nghiệp vụ, có thể lộ PII hoặc không chứa nội dung mong muốn.

## 15. Blob, ByteBuffer và custom TypeCodec

### 15.1. `blob` không tự đồng nghĩa `byte[]`

Mặc định driver dùng `ByteBuffer` cho CQL `blob`:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.binary_objects (
  tenant_id text,
  object_id uuid,
  content blob,
  PRIMARY KEY ((tenant_id), object_id)
);
~~~

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

PreparedStatement upload = session.prepare(
    "INSERT INTO java_bind_lab.binary_objects " +
    "(tenant_id, object_id, content) " +
    "VALUES (:tenant, :id, :content)");

byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
ByteBuffer data = ByteBuffer.wrap(bytes.clone());

BoundStatement b = upload.bind()
    .setString("tenant", "tenant-a")
    .setUuid("id", UUID.fromString(
        "88888888-8888-8888-8888-888888888888"))
    .setByteBuffer("content", data);
~~~

**Không** gọi `ByteBuffer.array()` mù quáng khi decode: buffer có thể là **direct**, read-only, có `position` khác 0 hoặc không backed by array. Để đọc bytes an toàn:

~~~java
ByteBuffer returned = row.getByteBuffer("content");
ByteBuffer view = returned.asReadOnlyBuffer();
byte[] decoded = new byte[view.remaining()];
view.get(decoded);
~~~

`view` là bản đọc có `position/limit` độc lập; không làm thay đổi position của ByteBuffer gốc. Với dữ liệu rất lớn, nên tránh copy toàn bộ vào heap nếu không cần. Cassandra không được tối ưu để lưu blob khổng lồ một cách tùy tiện: cần cân nhắc object storage và chỉ giữ metadata/URI trong Cassandra.

### 15.2. `getBytesUnsafe`/`setBytesUnsafe` là đường nâng cao

Các API *Unsafe* trao đổi dạng binary thô và có cảnh báo rõ về buffer ownership/position. Với ứng dụng thông thường, dùng `setByteBuffer`/`getByteBuffer` hoặc custom codec có kiểm soát. Nếu dùng *Unsafe* sai, bạn có thể encode sai nội dung mà không đi qua kiểm kiểu thông thường; đó **không** phải cách “tăng tốc miễn phí”.

### 15.3. Khi nào dùng custom codec?

Ví dụ domain model có enum Java `OrderStatus` nhưng column Cassandra là `text`. Có ba cách:

1. **Đơn giản nhất:** `setString("status", orderStatus.name())` và parse enum khi đọc, kèm policy về giá trị unknown.
2. **Domain codec:** tạo một `TypeCodec<OrderStatus>` đúng `text ↔ OrderStatus`, thread-safe/fast/immutable, đăng ký tại session hoặc truyền trực tiếp khi bind.
3. **Object mapper:** dùng driver mapper để tạo DAO/entity mapping khi phần lớn ứng dụng là CRUD có schema ổn định, nhưng vẫn phải kiểm column types và null/unset behavior.

Custom codec **không** tự thêm validation nghiệp vụ: enum có thể có `CANCELLED` nhưng status transition `PAID → CANCELLED` có thể bị cấm ở business. Không dùng codec để che việc schema đang dùng sai CQL type, và thử round-trip với các giá trị NULL/empty/Unicode.

### 15.4. Kiểm codec registry khi cần

Nếu ứng dụng thực sự dùng custom domain type, có thể hỏi registry:

~~~java
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.type.codec.TypeCodec;

TypeCodec<String> textCodec = session.getContext()
    .getCodecRegistry()
    .codecFor(DataTypes.TEXT, String.class);
~~~

`CodecRegistry.codecFor` tìm codec cho đúng **CQL type + Java target type**, ném lỗi nếu không có. Kiểm này hữu ích ở startup với contract phức tạp; nhưng **chỉ có codec không chứng minh phép bind cột/marker đúng nghĩa nghiệp vụ**.

## 16. Prepared vs Simple Statement: gắn values và chống injection

### 16.1. Prepared statement khuyến nghị cho query lặp lại

~~~java
PreparedStatement byTenantAndDay = session.prepare(
    "SELECT event_time, event_id, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?");

BoundStatement query = byTenantAndDay.bind(
    "tenant-a", LocalDate.parse("2026-11-21"));
~~~

Prepared query được parse/cached, metadata marker types giúp kiểm sớm và driver có thể tính routing key. `PreparedStatement` thread-safe theo built-in implementation; chuẩn bị một lần trong repository rồi bind theo từng request. Không `prepare` một câu query sinh text ngẫu nhiên cho mỗi request, gây cache churn và tăng round trips.

### 16.2. Simple statement có thể dùng bind values nhưng metadata khác

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement simple = SimpleStatement.builder(
        "SELECT status FROM java_bind_lab.customer_profiles " +
        "WHERE tenant_id = ? AND customer_id = ?")
    .addPositionalValues(
        "tenant-a",
        UUID.fromString("11111111-1111-1111-1111-111111111111"))
    .build();

Row row = session.execute(simple).one();
~~~

Ở `SimpleStatement`, driver có thể phải suy kiểu từ Java object vì chưa có prepared variable metadata. Khi Java type có nhiều ánh xạ CQL (ví dụ String và text/ascii, UUID và uuid/timeuuid), sai type inference có thể gây server-side conversion problem; prepared statement cho typed metadata rõ hơn. Cũng có named simple values, nhưng **không trộn positional và named values trên cùng một built-in SimpleStatement**.

### 16.3. Giá trị bind không cho phép dựng tên bảng/column động

**Sai vì injection và thiếu type safety:**

~~~java
String cql = "SELECT status FROM " + userProvidedTable +
    " WHERE tenant_id = '" + tenantId + "'";
session.execute(cql);
~~~

**Tốt hơn:**

~~~java
// Tên bảng là hằng số được review; tenantId là bind value.
PreparedStatement p = session.prepare(
    "SELECT status FROM java_bind_lab.customer_profiles " +
    "WHERE tenant_id = :tenant AND customer_id = :customer");
~~~

Ngay cả khi `tenantId` được bind và escaped an toàn, vẫn phải kiểm **authorization**: một client có thể gửi `tenant-b` hợp lệ về type nhưng không thuộc user hiện tại. Bind giúp chống literal injection, không thay ACL/tenant isolation.

### 16.4. Prepared statement và schema evolution

Tránh `SELECT *` với prepared statement trên bảng thường `ALTER TABLE`, đặc biệt nếu còn Cassandra 3.x/native protocol cũ. Explicit column selection giúp hạn chế nguy cơ metadata/result decoder lệch khi schema thay đổi. Với Cassandra 4+ native protocol v5 có cơ chế cập nhật result metadata tốt hơn, nhưng vẫn nên có integration tests khi schema migration. [Prepared statements — schema changes](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

## 17. Routing key, consistency và vì sao bind đúng khóa phân vùng quan trọng

~~~text
Java bind: tenant="tenant-a", day=2026-11-21
                     |
          Prepared variable metadata
                     |
       Partition key (tenant_id, day)
                     |
              Murmur3 token
                     |
        Natural replicas theo RF/DC
                     |
          Coordinator + CL responses
                     |
           ResultSet / write ACK
~~~

### 17.1. Token-aware routing cần đủ partition-key components

Với `PRIMARY KEY ((tenant_id, day), event_time, event_id)`, khi driver đã biết metadata và bound statement chứa **đủ `tenant_id` + `day` đúng type**, nó có thể tự tính routing key/token để chọn coordinator thuận lợi. Nếu thiếu một thành phần, routing có thể không tối ưu hoặc query không hợp lệ.

Không phải lúc nào có `WHERE tenant_id = ?` cũng đủ: khóa phân vùng composite còn cần `day`. Nếu bạn đảo `tenant_id` của hai tenant cùng type, driver vẫn tính được routing key — **nhưng route đúng tới partition sai về nghiệp vụ**.

### 17.2. Chọn CL theo thiết kế, không theo lỗi bind

~~~java
BoundStatement request = byTenantAndDay.bind(
        "tenant-a", LocalDate.parse("2026-11-21"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE);
~~~

`ONE` dùng **chỉ vì lab RF1**. Với RF3 nhiều nodes và ứng dụng đòi consistency mạnh hơn, có thể yêu cầu `LOCAL_QUORUM`; điều này phải được thẩm định theo hợp đồng dữ liệu và RF từng DC.

### 17.3. Các vấn đề không thể sửa bằng setter

- Partition quá rộng/hot: `setString` đúng không phân tán một partition ra nhiều token.
- Truy vấn không có partition key: bind đúng type không biến full scan thành point lookup.
- Replica down hoặc repair thiếu: typed bind đúng không làm `LOCAL_QUORUM` có đủ phản hồi.
- Tombstone/TTL: dữ liệu ghi trong SSTables có thể không xuất hiện dù marker đúng.
- Idempotence: retry cùng UUID và cùng timestamp/semantics cần review, không do bind name quyết định.

**Đo lỗi theo từng tầng:** `prepare/bind` (metadata/codec) khác `execute` (network/CL) và khác `result correctness` (logic/routing/TTL/tombstone).

## 18. Lab CQL — chuẩn bị dữ liệu có nhiều kiểu CQL

**Mục tiêu:** Tạo vài dòng trên một node Cassandra lab, kiểm key/type bằng cqlsh, sau đó chạy Java để bind theo vị trí và tên. Lab không đòi benchmark hay tạo cluster nhiều nodes.

**Điều kiện:** Có Cassandra 4.1/5.0 lab, `cqlsh`, Java 17 + driver 4.x, quyền tạo keyspace/table, đủ network/credentials. Không chạy `TRUNCATE` trên bảng production. DDL ở mục 3 được chạy **trước** các bước dưới đây.

### 18.1. Khởi tạo schema

Trong cqlsh, chạy ba câu `CREATE KEYSPACE`/`CREATE TABLE` ở mục 3; sau đó:

~~~sql
DESCRIBE KEYSPACE java_bind_lab;
DESCRIBE TABLE java_bind_lab.events_by_tenant_day;
DESCRIBE TABLE java_bind_lab.customer_profiles;

CONSISTENCY ONE;
~~~

Lab dùng RF1; với nhiều nodes/DC phải chọn `NetworkTopologyStrategy`/RF thích hợp và app CL theo hợp đồng.

### 18.2. Nạp ba events cố định

~~~sql
INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 1200.50, 'created', {'order', 'new'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222,
  'PAID', 1200.50, 'payment received', {'order', 'paid'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333,
  'SHIPPED', 1200.50, 'sent', {'order', 'shipped'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-b', '2026-11-21', '2026-11-21T09:00:00Z',
  44444444-4444-4444-4444-444444444444,
  'NEW', 75.25, 'created', {'new'}
);
~~~

### 18.3. Đối chiếu bằng CQL trước khi chạy Java

~~~sql
SELECT event_time, event_id, status, amount, tags
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status, amount, tags
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Kỳ vọng `tenant-a` có 3 events, `tenant-b` có 1. Event `2222…` là `PAID`, amount `1200.50`. Do `CLUSTERING ORDER BY (event_time DESC,...)`, các rows trong cùng partition thường được trả theo thời điểm mới nhất trước; không nhầm **thứ tự output** với **thứ tự bind markers**.

### 18.4. Bảng biến/kiểu mong đợi cho truy vấn range

~~~sql
SELECT event_time, event_id, status, amount
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant
  AND day = :target_day
  AND event_time >= :from_time
  AND event_time < :to_time;
~~~

| Index marker | Tên | CQL type | Java |
|---:|---|---|---|
| 0 | `tenant` | text | String |
| 1 | `target_day` | date | LocalDate |
| 2 | `from_time` | timestamp | Instant |
| 3 | `to_time` | timestamp | Instant |

Kiểm trong chương trình Java bằng `getVariableDefinitions()` để bảo đảm metadata thực trùng bảng; khi source code query thay, test phải bắt được thay đổi. **Không suy từ tên `from_time` rằng nó là `timestamp`** nếu CQL đã đổi sang type khác — nguồn sự thật về type là prepared metadata.

## 19. Lab Java — một chương trình kết hợp positional, named và typed metadata

### 19.1. Cấu hình session

Mã dưới dùng Java 17 + Java Driver 4.x, ví dụ chạy cùng máy với Cassandra lab tại `127.0.0.1:9042` và local DC `datacenter1`. Nếu node thực thuộc DC tên `dc1`, phải thay đúng local DC đó. Không đưa password/TLS secrets vào source code; nếu lab có authentication/TLS, cấu hình qua config loader/secret manager thích hợp.

Dependency minh họa cho phiên bản 4.17:

~~~xml
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

Đây là đoạn dependency để đưa vào một dự án Java/Maven **đã có**, không yêu cầu tạo `pom.xml` trong module. Với phiên bản ASF từ 4.18, kiểm tọa độ Maven và API theo tài liệu đang dùng.

### 19.2. Chương trình Java 17

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.type.DataTypes;

import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

public final class JavaBindLab {
    private JavaBindLab() {}

    public static void main(String[] args) {
        // Thay datacenter1 đúng với DC thực tế của node lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // 1) Dạng positional cho một partition.
            PreparedStatement byDay = session.prepare(
                "SELECT event_time, event_id, status, amount, tags " +
                "FROM java_bind_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ?");

            // Kiểm contract trước khi bind.
            ColumnDefinitions vars = byDay.getVariableDefinitions();
            require(vars.size() == 2, "Expected two bind markers");
            require(DataTypes.TEXT.equals(vars.get(0).getType()),
                "Marker 0 must be text tenant_id");
            require(DataTypes.DATE.equals(vars.get(1).getType()),
                "Marker 1 must be date");

            BoundStatement dayRequest = byDay.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(2);

            ResultSet byDayResult = session.execute(dayRequest);
            int count = 0;
            for (Row row : byDayResult) {
                count++;
                System.out.printf(
                    "row=%s status=%s amount=%s tags=%s%n",
                    row.getUuid("event_id"),
                    row.getString("status"),
                    row.getBigDecimal("amount"),
                    row.getSet("tags", String.class));
            }
            require(count == 3, "Expected three tenant-a events");

            // 2) Named bind cho một range.
            PreparedStatement range = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM java_bind_lab.events_by_tenant_day " +
                "WHERE tenant_id = :tenant " +
                "AND day = :target_day " +
                "AND event_time >= :from_time " +
                "AND event_time < :to_time");

            ColumnDefinitions rangeVars =
                range.getVariableDefinitions();
            require(rangeVars.size() == 4,
                "Expected four named bind markers");
            require(DataTypes.TIMESTAMP.equals(
                    rangeVars.get("from_time").getType()),
                "from_time must be timestamp");
            require(DataTypes.TIMESTAMP.equals(
                    rangeVars.get("to_time").getType()),
                "to_time must be timestamp");

            BoundStatement rangeRequest = range.bind()
                .setString("tenant", "tenant-a")
                .setLocalDate("target_day",
                    LocalDate.parse("2026-11-21"))
                .setInstant("from_time",
                    Instant.parse("2026-11-21T08:04:00Z"))
                .setInstant("to_time",
                    Instant.parse("2026-11-21T08:11:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            int inRange = 0;
            for (Row row : session.execute(rangeRequest)) {
                inRange++;
                System.out.println("range status=" +
                    row.getString("status"));
            }
            require(inRange == 2,
                "Expected PAID and SHIPPED in the range");

            // 3) Named INSERT có decimal, timestamp, UUID, set<text>.
            PreparedStatement insert = session.prepare(
                "INSERT INTO java_bind_lab.events_by_tenant_day " +
                "(tenant_id, day, event_time, event_id, " +
                "status, amount, note, tags) VALUES " +
                "(:tenant, :target_day, :at, :eid, " +
                ":state, :amount, :note, :tags)");

            BoundStatement inserted = insert.boundStatementBuilder()
                .setString("tenant", "tenant-c")
                .setLocalDate("target_day",
                    LocalDate.parse("2026-11-21"))
                .setInstant("at",
                    Instant.parse("2026-11-21T10:00:00Z"))
                .setUuid("eid", UUID.fromString(
                    "55555555-5555-5555-5555-555555555555"))
                .setString("state", "NEW")
                .setBigDecimal("amount",
                    new BigDecimal("19.95"))
                .setString("note", "created from Java")
                .setSet("tags", Set.of("java", "new"),
                    String.class)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .build();
            session.execute(inserted);

            BoundStatement verify = byDay.bind(
                    "tenant-c", LocalDate.parse("2026-11-21"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);
            Row persisted = session.execute(verify).one();

            require(persisted != null,
                "Inserted event must be visible");
            require("NEW".equals(persisted.getString("status")),
                "Unexpected status");
            require(new BigDecimal("19.95").compareTo(
                    persisted.getBigDecimal("amount")) == 0,
                "Unexpected amount");

            System.out.println("BIND_LAB_PASS");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

### 19.3. Kết quả dự kiến

~~~text
row=33333333-... status=SHIPPED amount=1200.50 tags=[...]
row=22222222-... status=PAID amount=1200.50 tags=[...]
row=11111111-... status=NEW amount=1200.50 tags=[...]
range status=SHIPPED
range status=PAID
BIND_LAB_PASS
~~~

**Output chỉ là minh họa**, thứ tự hiển thị `Set` không phải hợp đồng và driver có thể serialize số decimal khác dạng text. Điều quan trọng là Java đã:

- Dùng **cùng `PreparedStatement`** cho nhiều bộ values.
- Kiểm metadata **trước** khi bind.
- Dùng `bind(Object...)` theo vị trí và `setXxx("name")` theo tên.
- Chọn đúng Java types cho Cassandra date/timestamp/uuid/decimal/set.
- Dùng page-size 2 nhưng đọc đủ **3 rows** qua paging.
- Đọc lại giá trị sau insert và so bằng `BigDecimal.compareTo` để không nhầm khác biệt scale với khác biệt số tiền.

### 19.4. Nếu kết quả không giống kỳ vọng

| Triệu chứng | Kiểm trước |
|---|---|
| Session không tạo được | Contact point, local DC, TLS/auth, node UP |
| Prepare lỗi | Keyspace/table/column names, CQL syntax, schema agreement |
| Metadata assert lỗi | Query markers thay đổi, column type/schema khác dự kiến |
| Codec exception lúc bind | Java type không phù hợp CQL type, custom codec không đăng ký |
| Tenant-a có ít/nhiều hơn 3 rows | Lab đã chạy trước, có UPDATE/DELETE/TTL, không phải môi trường sạch |
| Range trả 0 | Kiểm `from/to` (UTC), bucket `day`, named marker names |
| Insert thành công nhưng SELECT rỗng | Sai tenant/day/PK, CL, tombstone/TTL, query khác |

Lab nên chạy trên **keyspace/table cô lập mới** hoặc reset **môi trường lab có chủ đích**, không dùng `TRUNCATE` trên dữ liệu chưa được phê duyệt.

## 20. Negative tests: cố ý bind sai để biết lỗi được chặn ở đâu

### 20.1. Kiểm sai CQL type tại bind

Với truy vấn:

~~~java
PreparedStatement p = session.prepare(
    "SELECT event_id FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :target_day");
~~~

Trường `target_day` có CQL type `date`, vì thế:

~~~java
// ĐÚNG:
BoundStatement correct = p.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"));

// Dự kiến fail ở bind vì không có codec TEXT -> CQL date:
// p.bind().setString("target_day", "2026-11-21");
~~~

Nếu ứng dụng nhận ngày dưới dạng text, parse bằng `LocalDate.parse` ở validation layer trước khi set; **đừng** tăng retry attempts khi đây là lỗi kiểu cố định.

### 20.2. Sai tên marker

~~~java
// Đã khai báo :tenant, không phải :tenant_id.
// Runtime fail: unknown marker name.
// p.bind().setString("tenant_id", "tenant-a");
~~~

Nên kiểm `p.getVariableDefinitions().contains("tenant")` ngay sau `prepare` trong integration tests, và tránh hardcode cùng một tên marker ở nhiều nơi không đồng bộ.

### 20.3. Quá nhiều hoặc quá ít values

~~~java
// p có 2 markers, đoạn này có 3 values -> driver từ chối.
// p.bind("tenant-a", LocalDate.parse("2026-11-21"), 99);

// p có 2 markers, đoạn dưới bind thiếu 1 value:
BoundStatement incomplete = p.bind("tenant-a");
System.out.println(incomplete.isSet(0));  // true
System.out.println(incomplete.isSet(1));  // false (UNSET)
~~~

Việc `bind("tenant-a")` **có thể tạo statement** không có nghĩa `execute` sẽ thành công: `day` là một phần partition key nên không thể UNSET khi thực thi truy vấn cụ thể này. Chặn ở service boundary bằng schema contract validation để lỗi rõ nghĩa.

### 20.4. Chỉ số âm hoặc vượt range

~~~java
// Driver phải báo IndexOutOfBoundsException:
// p.bind().setString(-1, "tenant-a");
// p.bind().setString(2, "tenant-a");  // chỉ có index 0 và 1
~~~

Không “sửa nhanh” bằng cách cộng/trừ 1 mọi vị trí. In đúng `getVariableDefinitions()` và cập nhật mapping theo thứ tự marker.

### 20.5. Đảo hai marker cùng kiểu là lỗi nguy hiểm nhất

Giả sử bảng nghiệp vụ có:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.tenant_region_notes (
  tenant_id text,
  region_code text,
  note text,
  PRIMARY KEY ((tenant_id), region_code)
);
~~~

Query:

~~~java
PreparedStatement q = session.prepare(
    "SELECT note FROM java_bind_lab.tenant_region_notes " +
    "WHERE tenant_id = ? AND region_code = ?");

// HỢP LỆ VỀ TYPE nhưng SAI NGỮ NGHĨA:
BoundStatement wrong = q.bind("ap-south", "tenant-a");

// ĐÚNG:
BoundStatement right = q.bind("tenant-a", "ap-south");
~~~

Driver thấy cả hai là CQL `text` nên **không thể phân biệt** tenant và region. Ngay cả nếu named markers được dùng, ứng dụng vẫn có thể gọi `setString("tenant", region)` và `setString("region", tenant)` — tên giúp review, không tự ngăn sai ý nghĩa. Giải pháp là **typed domain wrappers/validation**, test với **khóa không đối xứng**, và so kết quả theo primary key.

### 20.6. Trùng tên trong range query

~~~java
PreparedStatement q = session.prepare(
    "SELECT event_id FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? " +
    "AND event_time >= ? AND event_time < ?");

System.out.println(
    q.getVariableDefinitions().allIndicesOf("event_time"));
// Kỳ vọng: [2, 3] theo metadata server.
~~~

Không dùng `setInstant("event_time", from)` rồi `setInstant("event_time", to)` để gắn hai giá trị: mỗi setter theo tên có thể cập nhật **cả hai slots**, khiến cuối cùng chúng cùng bằng `to`. Chuyển sang tên `:from_time`/`:to_time` hoặc indices 2/3. Đây là lỗi gây **kết quả rỗng im lặng**, có thể bị nhầm là mất dữ liệu.

### 20.7. Sai getter trên kết quả

Với `status` có CQL type `text`, gọi `getInt("status")` là sai kiểu. Ngoài ra phải chắc projection của câu SELECT **thực sự có cột `status`**, vì một getter có tên hợp lệ trong schema nhưng không có trong result vẫn thất bại. Chuẩn bị một truy vấn kiểm độc lập:

~~~java
PreparedStatement qStatus = session.prepare(
    "SELECT status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?");

Row statusRow = session.execute(
    qStatus.bind("tenant-a", LocalDate.parse("2026-11-21"))).one();

String goodStatus = statusRow.getString("status");
// statusRow.getInt("status") -> codec/type mismatch.
~~~

### 20.8. Negative tests cần kiểm cả **không xảy ra ghi sai**

Khi thử thao tác INSERT/UPDATE sai type, không dừng ở “có exception”. Kiểm:

- Lệnh fail **trước khi execute** hay sau khi gửi server?
- Có mutation nào đã được áp dụng một phần không? Một write timeout không xác nhận “chưa ghi”.
- Source event ID và primary key có bị sinh mới khi retry không?
- Metadata/schema mới có vừa thay trong một rolling deployment không?
- Log/traces có lộ raw bind values/PII không?

Với các lỗi codec cố định, retry với cùng giá trị không làm chúng tự hết. Với timeout/quorum, cần **idempotency policy và reconciliation** riêng.

## 21. Concurrent requests và tái sử dụng prepared statements

### 21.1. Cái gì được share giữa threads?

| Object | Share? | Quy tắc |
|---|---|---|
| `CqlSession` | **Có** | Tái sử dụng một session cho app/cluster phù hợp |
| `PreparedStatement` | **Có** | Prepare một lần khi khởi tạo repository, cache/reuse |
| `BoundStatement` built-in | Có thể, vì immutable | Nhưng mỗi bộ values khác nhau nên tạo bound mới |
| `BoundStatementBuilder` | **Không** khi đang sửa | Tạo mới per-request; mutable và không thread-safe |
| `Row`, `ResultSet` | Theo API/consumption semantics | Không tự share result iterator giữa threads |
| `ByteBuffer` mutable do app giữ | Chia sẻ có điều kiện | Không mutate position/content sau khi bind |

### 21.2. Repository tạo một prepared và nhiều bound

~~~java
public final class CustomerRepository {
    private final CqlSession session;
    private final PreparedStatement findById;

    public CustomerRepository(CqlSession session) {
        this.session = session;
        this.findById = session.prepare(
            "SELECT name, age, active " +
            "FROM java_bind_lab.customer_profiles " +
            "WHERE tenant_id = :tenant AND customer_id = :customer");
    }

    public Row find(String tenantId, UUID customerId) {
        BoundStatement request = findById.bind()
            .setString("tenant", tenantId)
            .setUuid("customer", customerId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);

        return session.execute(request).one();
    }
}
~~~

Với production, repository nên map `Row` thành DTO sớm, xác minh nullable fields, và giữ consistency level theo RF/hợp đồng ứng dụng thay vì hardcode ONE.

### 21.3. Async không thay nguyên tắc bind

~~~java
BoundStatement request = findById.bind()
    .setString("tenant", tenantId)
    .setUuid("customer", customerId);

CompletionStage<AsyncResultSet> future =
    session.executeAsync(request);
~~~

`BoundStatement` có giá trị cụ thể không bị mutate trong khi gửi bất đồng bộ. Tránh đổi một `BoundStatementBuilder` đang share để gửi nhiều requests; đó là data race.

Một async bulk importer cần **bounded in-flight** và backpressure. Không tạo vô hạn futures rồi chỉ gọi `allOf` một lần trên hàng triệu writes. Khi một request timeout, outcome của write có thể không chắc chắn; chỉ retry nếu semantics thật sự idempotent.

### 21.4. Prepared cache và schema changes

Driver 4.x cache prepared statements theo **CQL text và các execution parameters liên quan**; gọi prepare lại cùng exact query thường được cache client-side, nhưng không nên lặp trong hot path nếu có thể giữ reference. Driver có cơ chế reprepare khi node join/restart/UNPREPARED, nên không cần tự `session.prepare` mọi query sau mỗi lỗi transient. [Prepared statements — caching and reprepare](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

## 22. Quy trình chẩn đoán lỗi binding trong production

~~~text
               Request lỗi hoặc dữ liệu sai
                          |
              Có exception ở prepare?
                /                \
              CÓ                 KHÔNG
               |                   |
       Kiểm CQL/schema         Lỗi lúc bind?
       keyspace/column           /       \
                              CÓ        KHÔNG
                              |           |
                        Metadata +     Lỗi execute?
                        marker/types     /      \
                                        CÓ     KHÔNG
                                        |        |
                               Quorum/network   Result decode?
                               auth/timeout      /      \
                                                CÓ      KHÔNG
                                                |         |
                                         Row metadata   Business audit:
                                         getter/null     wrong PK/timezone
                                                         TTL/tombstone
~~~

### 22.1. Phân loại lỗi theo tầng

| Tầng | Triệu chứng | Bằng chứng nên lấy | Hành động |
|---|---|---|---|
| Prepare | `InvalidQuery`, unknown column/table | CQL text, schema digest, server logs | Sửa query/schema, kiểm schema agreement |
| Bind marker | Unknown name, out of bounds | `getVariableDefinitions()` names/indices | Sửa tên/vị trí, giữ tests |
| Bind codec | Codec not found/invalid value type | CQL type + Java runtime class + codec registry | Parse/validate đúng type hoặc cài codec hợp lệ |
| Execute | Timeout, unavailable, auth | CL, RF, node status, client/server metrics | Incident/backpressure/network, không retry mù |
| Decode | Getter thiếu cột/sai type, NULL primitive | `row.getColumnDefinitions()`, `isNull` | Sửa projection/DTO/getter |
| Logic | Query success nhưng wrong tenant/day/amount | Expected PK, event audit, timezone/decimal policy | Sửa mapping, phục hồi dữ liệu bị ghi sai |

### 22.2. Log an toàn khi debug

Có thể log **non-sensitive metadata**:

~~~text
query_family=events.byTenantDay
statement_kind=prepared
bind_count=2
bind_schema=[0:text,1:date]
profile=point_read
consistency=LOCAL_QUORUM
outcome=codec_error
duration_ms=...
~~~

**Không log** raw bind values, full token/credentials, password, email, địa chỉ, số thẻ hay các trường PII chỉ để debug. Nếu phải lưu sample để tái hiện, dùng môi trường bảo mật và masking/retention theo chính sách. Labels từ `tenantId`/UUID từng bản ghi có thể gây **cardinality cao** trong Prometheus.

### 22.3. “Fail fast” không thay quan sát phía Cassandra

Nếu bind thành công nhưng request chậm:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats java_bind_lab.events_by_tenant_day
~~~

Theo dõi driver `cql-requests`, `cql-messages`, retries, pool in-flight, request timeouts. Kiểm partition size, tombstone scans, read/write latency, disk/GC và consistency quorum. **Đừng tăng timeout chỉ để che một query sai partition key**.

### 22.4. Bảng quyết định sau lỗi

| Kết quả điều tra | Quyết định |
|---|---|
| Sai tên/index CQL marker | Sửa code, thêm contract test; không retry |
| Sai Java type/codec | Fix parser/DTO/custom codec rồi re-test |
| Hai marker cùng tên nhưng cần hai values | Đổi :names hoặc dùng index |
| Sai tenant/partition dù type đúng | STOP rollout và audit dữ liệu nghiệp vụ |
| NULL sinh tombstone ngoài ý muốn | STOP writes, phục hồi logic theo source-of-truth |
| UNSET PK/condition | Validate required fields trước bind |
| Timeout sau execute | Kiểm unknown outcome và retry/idempotency |
| Schema changed trong rolling deploy | Điều phối compatibility, reprepare/DTO migration |

## 23. Checklist code review và chạy production

### 23.1. Trước khi viết câu truy vấn

- [ ] Đã xác định **query pattern** và table/partition key đúng.
- [ ] CQL dùng explicit columns, không dựa vào `SELECT *` khi schema có thể tiến hóa.
- [ ] Nguồn giá trị là user input/DTO đã qua parsing, validation và authorization.
- [ ] Tên keyspace/table/column được **allowlist**, không nối thẳng request text.
- [ ] Nếu là prepared statement lặp lại, được prepare một lần và cache trong repository.
- [ ] Số marker, thứ tự/tên và type dự kiến được ghi trong test contract.
- [ ] Với nhiều điều kiện trên cùng một column, marker names tách biệt hoặc dùng indices.
- [ ] Các identifiers case-sensitive đã được mô hình rõ hoặc tránh quote không cần thiết.
- [ ] Connection/session local DC và authentication đúng cluster đích.

### 23.2. Khi bind values

- [ ] Chỉ số positional bắt đầu từ **0**; thứ tự theo CQL marker không theo DDL.
- [ ] Với named markers, setter dùng tên **không có dấu `:`**.
- [ ] Nếu dùng implicit named binding cho `?`, đã đọc `getVariableDefinitions()`.
- [ ] Đã kiểm `allIndicesOf(name)` khi tên có thể xuất hiện nhiều lần.
- [ ] Typed setter/getter đúng CQL↔Java mapping.
- [ ] Dữ liệu `date` và `timestamp` được parse đúng timezone/precision.
- [ ] Tiền tệ dùng `BigDecimal` từ nguồn decimal tin cậy, không ép qua double.
- [ ] `uuid`/`timeuuid` và retry identity có chính sách rõ.
- [ ] Collection element types/UDT/tuple components được kiểm theo schema đích.
- [ ] Blob ByteBuffer không bị mutate sau khi bind và không giả định có `array()`.
- [ ] Có chính sách **absent vs NULL vs UNSET** cho từng trường optional/PATCH.
- [ ] Primary keys, WHERE restrictions và business-critical fields không UNSET/NULL ngoài ý muốn.
- [ ] Không bỏ instance trả về của `BoundStatement.setXxx`/`unset`.
- [ ] Nếu dùng builder, không chia sẻ builder mutable qua threads.
- [ ] Consistency level, timeout, idempotence và execution profile đúng use case.

### 23.3. Khi execute và đọc lại

- [ ] Kiểm lỗi prepare/bind trước retry; sai kiểu/tên là permanent errors.
- [ ] Với timeout/write failure, phân loại **unknown outcome** theo idempotency.
- [ ] Đã kiểm `Row` không null nếu query mong một record.
- [ ] Không dùng primitive getter khi NULL có nghĩa riêng mà thiếu `isNull`.
- [ ] Không lấy `page size` làm giới hạn tổng records trả về.
- [ ] Kiểm projection/column metadata của result để chọn getter phù hợp.
- [ ] So expected primary keys và values; không chỉ kiểm “SELECT có row”.
- [ ] Kiểm timestamp, status transition, decimal precision và row/collection semantics.
- [ ] Với cluster đa DC, đã xác minh CL/replica data theo phạm vi yêu cầu.
- [ ] Có metric theo query family, bind outcome, retry rate và Cassandra server health.
- [ ] Logs không chứa raw bind values/PII/secrets hoặc high-cardinality IDs.

### 23.4. Khi schema thay đổi

- [ ] Schema/table/keyspace version được review trước khi deploy Java mới.
- [ ] Contract tests kiểm `getVariableDefinitions()` với version đích.
- [ ] Code đang triển khai có backward/forward compatibility nếu rolling deploy.
- [ ] Các custom codecs/UDT types tương thích với schema của từng cluster/session.
- [ ] Không đổi PK type/order mà không có migration dữ liệu riêng.
- [ ] Query mới qua prepare, bind, execute, decode được integration-test trên staging.
- [ ] Nếu phát hiện sai mapping, dừng rollout và kiểm các mutation đã có thể ghi sai.

## 24. Câu hỏi tự đánh giá và gợi ý đáp án

**Câu 1.** Vì sao `PreparedStatement` khác với cách ghép chuỗi CQL chứa literal?  
**Gợi ý:** Cassandra parse query một lần, metadata type được trả về, BoundStatement gửi prepared ID và values đã encode; giảm nguy cơ injection ở phần values.

**Câu 2.** Query có 3 marker `?`. Chỉ số của marker cuối là bao nhiêu?  
**Gợi ý:** 2; positional bind 0-based.

**Câu 3.** Khi đổi thứ tự column/`?` trong CQL, có phải Java `bind(...)` tự cập nhật theo tên thuộc tính DTO?  
**Gợi ý:** Không; phải sửa thứ tự values hoặc dùng named markers/test.

**Câu 4.** Bind `"tenant-a"` vào cả `region_code text` và `tenant_id text` có được driver chặn nếu đảo thứ tự không?  
**Gợi ý:** Không nhất thiết; cả hai là String/text, lỗi ngữ nghĩa phải do validation/integration test bắt.

**Câu 5.** Trong query `event_time >= ? AND event_time < ?`, vì sao `setInstant("event_time", ...)` hai lần là nguy hiểm?  
**Gợi ý:** Metadata names trùng; setter theo name ghi mọi occurrences trùng tên, nên cuối cùng hai bounds có thể bằng nhau.

**Câu 6.** Cách an toàn nhất khi hai marker cùng cột cần hai giá trị khác nhau?  
**Gợi ý:** Dùng vị trí riêng hoặc `:from_time`/`:to_time` tường minh.

**Câu 7.** Với `INSERT ... VALUES (:tenant, :customer)`, Java gọi `setString(":tenant", ...)` đúng không?  
**Gợi ý:** Không; gọi `setString("tenant", ...)`.

**Câu 8.** Named marker `:full_name` có bắt buộc trùng tên cột `name` không?  
**Gợi ý:** Không; tên do query đặt, metadata từ prepared statement.

**Câu 9.** `getVariableDefinitions()` khác `row.getColumnDefinitions()` thế nào?  
**Gợi ý:** Cái đầu mô tả bind variables, cái sau mô tả result columns.

**Câu 10.** Vì sao nên assert `DataTypes.DATE` cho marker `day`?  
**Gợi ý:** Đảm bảo schema/CQL contract chưa thay và code dùng `LocalDate`.

**Câu 11.** CQL `date` nên bind bằng Java `String` hay `LocalDate`?  
**Gợi ý:** `LocalDate` với `setLocalDate`; parse text ở boundary.

**Câu 12.** CQL `timestamp` được decode bằng kiểu Java nào theo driver mặc định?  
**Gợi ý:** `Instant` với `getInstant`; milliseconds precision và timezone policy cần review.

**Câu 13.** `LocalDateTime` và `Instant` có thể thay nhau tùy ý khi bind CQL timestamp không?  
**Gợi ý:** Không; LocalDateTime thiếu timezone/offset, cần chuyển rõ zone trước.

**Câu 14.** CQL `decimal` với tiền nên dùng `BigDecimal` hay `double`?  
**Gợi ý:** BigDecimal; tránh binary floating-point rounding.

**Câu 15.** Java `UUID.randomUUID()` có phù hợp CQL `timeuuid` khi yêu cầu UUID phiên bản 1 không?  
**Gợi ý:** Không; randomUUID thường tạo v4.

**Câu 16.** Nếu một `BoundStatement` gọi `setString(...)` mà bỏ qua giá trị trả về, điều gì xảy ra?  
**Gợi ý:** Built-in object bất biến; bản cũ không được sửa.

**Câu 17.** Có thể dùng `PreparedStatement` cùng lúc từ nhiều threads? Có thể dùng chung `BoundStatementBuilder` không?  
**Gợi ý:** Prepared có thể chia sẻ; builder mutable không thread-safe.

**Câu 18.** `bind(v0)` trên prepared có hai markers luôn ném lỗi ngay không?  
**Gợi ý:** Không; slot còn lại UNSET khi protocol hỗ trợ, nhưng lệnh có thể fail khi execute nếu marker bắt buộc.

**Câu 19.** Sự khác biệt giữa `setToNull("age")` và không set `age` trong UPDATE là gì?  
**Gợi ý:** NULL có thể xóa/tạo tombstone; UNSET bỏ qua update của field.

**Câu 20.** Với `new_age` UNSET và `new_name` đã set, `isSet("new_age")` trả gì?  
**Gợi ý:** false.

**Câu 21.** `isNull("age")` cần thiết trước `getInt("age")` vì sao?  
**Gợi ý:** Primitive getter trả 0 khi CQL NULL; nếu nghiệp vụ phân biệt NULL và 0 phải giữ riêng.

**Câu 22.** `setSet("tags", Set.of(...), String.class)` hợp lệ cho `tags set<text>`. Còn `setList` có tương đương không?  
**Gợi ý:** Không; CQL collection types/list vs set có codec và semantics khác.

**Câu 23.** Khi nested collections dùng Java generics bị erasure, nên chỉ dùng `List.class` không?  
**Gợi ý:** Dùng `GenericType<T>`/codec phù hợp để giữ element types.

**Câu 24.** Cần làm gì khi bind UDT từ cluster khác schema?  
**Gợi ý:** Lấy `UserDefinedType` từ schema/session đích, kiểm fields/version và chuyển values có kiểm soát.

**Câu 25.** Vì sao `ByteBuffer.array()` có thể lỗi khi đọc blob?  
**Gợi ý:** Buffer có thể direct/read-only hoặc position/limit không bao trùm toàn array; dùng view và `remaining()`.

**Câu 26.** `PreparedStatement` giúp chống injection ở values, vậy có bind trực tiếp tên table nhận từ user vào `FROM ?` được không?  
**Gợi ý:** Không; bind values không thay CQL identifiers; tên table/columns chọn từ allowlist.

**Câu 27.** Khi driver bind đủ `tenant_id` và `day` của partition key composite, lợi ích với routing?  
**Gợi ý:** Có thể tính routing key/token và chọn coordinator hợp lý; vẫn cần RF/DC/CL đúng.

**Câu 28.** Nếu bind thành công nhưng result rỗng, có chắc là data chưa tồn tại không?  
**Gợi ý:** Không; có thể sai tenant/day, TTL/tombstone, CL/DC hoặc query shape.

**Câu 29.** Vì sao test chỉ cần “có exception khi sai type” là chưa đủ?  
**Gợi ý:** Sai cùng type có thể im lặng, còn timeout/write outcome không chắc chắn; cần audit primary keys/values.

**Câu 30.** Khi schema change, những tests nào cần chạy trước rollout?  
**Gợi ý:** Prepare/variable metadata, typed binding, execute, result decoding, nullable/UDT/collection, PK routing và business correctness.

## 25. Tổng kết: chọn vị trí hay tên — và kiểm type ở đâu?

~~~text
                       CQL QUERY TEXT
                             |
                    PreparedStatement
                             |
                   getVariableDefinitions
                 /           |             \
           INDEX          MARKER NAME      CQL TYPE
            0,1,2        :tenant,:day      text,date
                 \           |             /
                          VALIDATE
                             |
                 +-----------+------------+
                 |                        |
            Positional bind          Named bind
              ?, ?, ?               :tenant, :day
                 |                        |
           bind(v0,v1,...)           setXxx("name")
           setXxx(index)            distinct marker names
                 +-----------+------------+
                             |
                    CQL NULL / UNSET?
                             |
                  BoundStatement immutable
                             |
              Routing key + CL + execute
                             |
                 Row metadata + getter
                             |
                Business key/value checks
~~~

**Khi nào chọn bind theo vị trí?** Câu CQL ngắn, thứ tự marker cố định, không có nhiều conditions dùng chung column, và có contract tests kiểm type/order. Dùng indices khi muốn gắn **hai giá trị khác nhau cho cùng column** mà tên suy ra bị trùng.

**Khi nào chọn bind theo tên?** Query có nhiều fields, thứ tự dễ thay, muốn code dễ review; dùng **`:name` tường minh, duy nhất** và kiểm metadata. Đừng dựa mù quáng vào tên suy ra từ `?`.

**Khi nào kiểm type?** **Trước bind** kiểm DTO/parse nghiệp vụ; **sau prepare** kiểm `getVariableDefinitions()`; **khi bind** dùng typed setter/codec; **khi đọc** dùng `Row` metadata/getter và `isNull`; **sau execute** đối chiếu đúng primary key, timezone, decimal và dữ liệu nghiệp vụ.

**Thông điệp cốt lõi:** Java Driver 4.x giúp kiểm **định dạng CQL↔Java** và xử lý marker một cách xác định, nhưng nó không thể tự biết tên tenant nào được phép, giá trị nào là đúng trạng thái đơn hàng hoặc query nào là tối ưu cho Cassandra wide-column. Một câu bind **đúng kỹ thuật nhưng sai ngữ nghĩa** có thể gây tổn hại dữ liệu lớn hơn lỗi type bị chặn. Hãy kết hợp **named markers rõ nghĩa, typed metadata assertions, null/unset policy, prepared reuse và integration tests theo partition key**.

## Tài liệu tham khảo

- [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — `?`, `:name`, prepared variable metadata, bound setters, immutable và reprepare.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — API baseline cho phần ví dụ.
- [Apache Cassandra Java Driver 4.18 — Core overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/) — mapping CQL types sang Java, primitive NULL, collection generics và row metadata.
- [Java Driver 4.17 — PreparedStatement Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/PreparedStatement.html) — `bind(Object...)`, `getVariableDefinitions()`, `boundStatementBuilder`.
- [Java Driver 4.17 — ColumnDefinitions Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/ColumnDefinitions.html) — `contains`, `get`, `allIndicesOf` và type metadata.
- [Java Driver 4.17 — SettableByName Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/SettableByName.html) — setters theo tên áp lên mọi occurrence trùng tên.
- [Java Driver 4.17 — Bindable Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/Bindable.html) — `unset`, `isSet` và các giới hạn.
- [Java Driver 4.17 — GettableByIndex Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/GettableByIndex.html) — typed row getters và `isNull`.
- [Apache Cassandra Java Driver — Case sensitivity](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/) — `CqlIdentifier` và named lookup với quoted identifiers.
- [Apache Cassandra Java Driver — UDTs](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/) — lấy type metadata, tạo `UdtValue`, bind vào statement.
- [Apache Cassandra Java Driver — Tuples](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/) — typed tuple fields và `TupleValue`.
- [Apache Cassandra Java Driver — Detachable types](https://apache.github.io/cassandra-java-driver/4.18.0/core/detachable_types/) — UDT/tuple cross-session/protocol codec concerns.
- [DataStax Java Driver — Custom codecs](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/custom_codecs/) — mapping domain types/codec registry.
- [DataStax Java Driver — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) — statements, immutable setters và query attributes.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — partition key, clustering columns và query-first schema.
- [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — INSERT/UPDATE/SELECT, NULL/TTL/conditional mutations.
- [Apache Cassandra — Replication and consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — routing/token ring, natural replicas và CL.

