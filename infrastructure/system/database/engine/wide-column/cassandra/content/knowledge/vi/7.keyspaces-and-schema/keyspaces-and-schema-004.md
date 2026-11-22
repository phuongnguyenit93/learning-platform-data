# Tên đối tượng, quoted identifier và phân biệt hoa/thường trong Cassandra CQL

## 1. Vì sao quy tắc đặt tên quan trọng?

Trong Apache Cassandra, câu lệnh CQL sử dụng **identifier** (định danh) để tham chiếu đến keyspace, table, column, user-defined type (UDT) và một số đối tượng schema khác. Identifier trông giống những chuỗi ký tự thông thường, nhưng **cách viết dấu nháy kép quyết định Cassandra hiểu tên nào**.

Đây là một phần của chương **Keyspace và schema** trong module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Khi thiết kế bảng wide-column theo truy vấn, partition key, clustering column và tên bảng phải được ứng dụng gọi đúng. Một sai lệch hoa/thường có thể khiến lệnh CQL báo không tìm thấy bảng/cột, hoặc trỏ sang đối tượng khác nếu đã tồn tại tên gần giống.

Sau bài này, bạn có thể:

1. Phân biệt identifier không có nháy kép (*unquoted identifier*) và identifier có nháy kép (*quoted identifier*).
2. Dự đoán Cassandra chuẩn hóa tên như thế nào khi gặp chữ hoa và chữ thường.
3. Dùng đúng cú pháp khi tên chứa từ khóa CQL, chữ hoa hoặc ký tự đặc biệt được phép.
4. Xem tên thực tế đã lưu trong schema và sử dụng tên đó đúng cách từ `cqlsh` và ứng dụng Java.
5. Chọn quy ước đặt tên ít rủi ro cho keyspace, table và các cột trong môi trường phân tán.

## 2. Hai cách viết identifier trong CQL

### 2.1. Unquoted identifier: không có dấu nháy kép

**Identifier không đặt trong nháy kép không phân biệt hoa/thường.** Cassandra chuẩn hóa chúng thành chữ thường khi phân giải và lưu tên schema.

Ví dụ, những cách viết sau trỏ tới **cùng một tên logic**:

```sql
SELECT customer_id FROM orders_by_customer;
SELECT CUSTOMER_ID FROM ORDERS_BY_CUSTOMER;
SELECT Customer_Id FROM Orders_By_Customer;
```

Cả ba đều được hiểu tương đương với tên chữ thường `customer_id` và `orders_by_customer`, **nếu** các bảng/cột đó tồn tại và ngữ cảnh keyspace đúng. Cassandra **không** tự thêm dấu gạch dưới: `CustomerID` được chuẩn hóa thành `customerid`, khác với `customer_id`.

Với tên tự đặt, lựa chọn đơn giản là chữ cái ASCII thường, chữ số và dấu gạch dưới, bắt đầu bằng chữ cái: `commerce`, `orders_by_customer`, `customer_id`, `created_at`. Các nhóm đối tượng có thể có giới hạn ký tự/độ dài khác nhau theo phiên bản Cassandra; dùng tên đơn giản giúp tương thích hơn.

### 2.2. Quoted identifier: đặt trong dấu nháy kép

**Identifier trong dấu nháy kép đôi giữ nguyên chữ hoa/thường và được so khớp đúng như đã khai báo.**

```sql
-- Hai cột có thể mang hai tên logic khác nhau:
"customerid"
"CustomerID"
```

Tên `"CustomerID"` **không tương đương** `customerid` hoặc `CUSTOMERID` không có nháy kép. Ngược lại, `"customerid"` viết hoàn toàn chữ thường trùng với tên logic `customerid` không nháy kép.

Quy tắc này áp dụng khi tham chiếu bảng, cột, keyspace và các đối tượng schema hỗ trợ quoted identifier. Tuy nhiên, **dùng nháy kép không có nghĩa mọi tên tùy ý đều hợp lệ cho mọi loại đối tượng**: ví dụ keyspace và table có thể chịu thêm ràng buộc đặt tên riêng trong phiên bản đang sử dụng.

| CQL viết ra | Tên Cassandra dùng để tra cứu | Có trùng với tên `customerid` không? |
| --- | --- | --- |
| `customerid` | `customerid` | Có |
| `CustomerID` | `customerid` | Có |
| `CUSTOMERID` | `customerid` | Có |
| `"customerid"` | `customerid` | Có |
| `"CustomerID"` | `CustomerID` | Không |
| `"CUSTOMERID"` | `CUSTOMERID` | Không |
| `customer_id` | `customer_id` | Không; dấu gạch dưới có ý nghĩa |

> Mẹo nhớ: **Không nháy kép → chữ thường. Có nháy kép → giữ nguyên từng chữ.**

### 2.3. Identifier khác với string literal

Trong CQL, dấu nháy kép và dấu nháy đơn có vai trò khác nhau:

| Ký hiệu | Vai trò | Ví dụ |
| --- | --- | --- |
| `customer_id` | Identifier không nháy kép | Tên cột |
| `"CustomerID"` | Quoted identifier | Tên cột có phân biệt hoa/thường |
| `'CustomerID'` | String literal | **Giá trị chuỗi** gồm các ký tự `CustomerID` |
| `'class'`, `'datacenter1'` | String literal bên trong replication map | Khóa/value của tùy chọn `replication` |

Ví dụ sau minh họa cả hai loại dấu nháy trong cùng một câu lệnh:

```sql
SELECT "DisplayName"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- "DisplayName" là tên cột.
-- Khi INSERT, 'Nguyễn An' là dữ liệu text được ghi vào cột đó.
```

Không thay `"DisplayName"` bằng `'DisplayName'` để tham chiếu cột: chuỗi literal không có chức năng định danh cột.

## 3. Tên keyspace, table và column nằm trong những phạm vi nào?

Các đối tượng Cassandra có quan hệ tên theo nhiều cấp. Ví dụ:

```text
Cluster Cassandra
└── keyspace: naming_lab
    ├── table: people_by_id
    │   ├── column: person_id
    │   ├── column: display_name
    │   └── column: "DisplayName"
    └── table: "PeopleById"  (minh họa một tên bảng khác)
```

**Tên đầy đủ của bảng** có dạng `keyspace_name.table_name`. Dấu chấm phân tách namespace và tên đối tượng; dấu chấm không phải phần mặc định của unquoted identifier.

```sql
SELECT person_id FROM naming_lab.people_by_id;

USE naming_lab;
SELECT person_id FROM people_by_id;
```

`USE naming_lab` đặt keyspace mặc định cho phiên làm việc CQL; nó **không** đổi vị trí replica, không thay đổi partition key và không đổi replication factor. Nếu bảng cần quoted identifier, chỉ đặt dấu nháy kép quanh **thành phần tên cần bảo toàn chữ hoa/thường**:

```sql
-- Cú pháp khi bảng đã được tạo với đúng tên "PeopleById":
SELECT person_id FROM naming_lab."PeopleById";
```

| Đối tượng | Ví dụ thông thường | Khi cần nháy kép |
| --- | --- | --- |
| Keyspace | `naming_lab` | Tên có chữ hoa được khai báo có chủ đích, nếu hợp lệ với phiên bản |
| Table | `people_by_id` | `"PeopleById"` khác `peoplebyid` |
| Column | `person_id` | `"DisplayName"` phải gọi đúng chữ hoa |
| UDT và field | `shipping_address`, `city` | Dùng đúng tên đã khai báo khi tên có chữ hoa |
| Materialized view, index và đối tượng schema khác | `orders_by_customer` | Quy tắc nhận diện tên và ràng buộc đối tượng cần được kiểm tra theo phiên bản |

**Lưu ý:** Cassandra phân phối dữ liệu dựa vào partition key và replication strategy, **không** dựa vào việc tên đối tượng có chữ hoa hay nháy kép. Đặt tên đúng đảm bảo CQL truy cập đúng schema; cấu hình RF/consistency và thiết kế khóa là các quyết định khác.

## 4. Ví dụ thực hành: một tên bình thường và một tên có chữ hoa

Các lệnh phần này dùng trong **keyspace lab riêng**. Giả sử `nodetool status` cho biết DC thật là `datacenter1` và lab chỉ có một node; hãy sửa tên DC trong CQL nếu môi trường của bạn khác.

### Bước 1 — Tạo keyspace

```sql
CREATE KEYSPACE IF NOT EXISTS naming_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': '1'
}
AND durable_writes = true;
```

Ở đây, `naming_lab` là **unquoted identifier**. Hai chuỗi `'class'` và `'datacenter1'` là literal trong map replication; chúng không tuân theo quy tắc chuẩn hóa identifier. Tên DC phải khớp topology thực tế, còn RF = 1 chỉ nhằm phù hợp lab một node.

### Bước 2 — Tạo bảng với một số cột quoted

```sql
CREATE TABLE naming_lab.people_by_id (
    person_id uuid PRIMARY KEY,
    name text,
    "DisplayName" text,
    "SELECT" text
);
```

Bảng có bốn cột nhưng hai quy tắc phân giải tên:

- `person_id` và `name` là unquoted identifier, được lưu chữ thường; `PERSON_ID` và `Name` không nháy kép vẫn tham chiếu đúng chúng.
- `"DisplayName"` giữ chữ `D` và `N` viết hoa. Truy vấn dùng `DisplayName` không có nháy kép sẽ tìm `displayname`, **khác** cột đã khai báo.
- `"SELECT"` là một quoted identifier dùng từ khóa CQL làm tên cột. Nếu viết `SELECT` không có nháy kép tại vị trí tên cột, parser có thể hiểu là từ khóa của cú pháp thay vì identifier.

### Bước 3 — Ghi và đọc bằng đúng tên cột

```sql
INSERT INTO naming_lab.people_by_id (
    person_id, name, "DisplayName", "SELECT"
) VALUES (
    11111111-1111-4111-8111-111111111111,
    'An',
    'Nguyễn An',
    'active'
);

SELECT person_id, NAME, "DisplayName", "SELECT"
FROM NAMING_LAB.PEOPLE_BY_ID
WHERE person_id = 11111111-1111-4111-8111-111111111111;
```

Câu `SELECT` trên hợp lệ về cách phân giải tên vì `NAMING_LAB`, `PEOPLE_BY_ID` và `NAME` không có nháy kép, nên chúng được chuẩn hóa thành chữ thường. Hai cột `"DisplayName"` và `"SELECT"` vẫn phải được đặt nháy kép đúng như lúc tạo.

Thử dự đoán câu lệnh nào **không** truy cập được cùng cột:

```sql
-- Sai: DisplayName không nháy kép thành displayname.
SELECT DisplayName
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- Sai: đây là "DISPLAYNAME", không phải "DisplayName".
SELECT "DISPLAYNAME"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;

-- Đúng: viết chính xác cột được khai báo.
SELECT "DisplayName"
FROM naming_lab.people_by_id
WHERE person_id = 11111111-1111-4111-8111-111111111111;
```

Hai câu đầu thường bị Cassandra từ chối vì cột tương ứng không tồn tại trong bảng này. Đây là lỗi **phân giải identifier**; không phải lỗi replication, RF hay consistency level.

### Bước 4 — Hiểu quoted identifier ở tên bảng

Trong lab, bạn có thể tạo thêm một bảng có chữ hoa theo cú pháp:

```sql
CREATE TABLE naming_lab."PeopleById" (
    person_id uuid PRIMARY KEY,
    city text
);

-- Đúng: tên bảng được lưu chính xác là PeopleById.
SELECT * FROM naming_lab."PeopleById";

-- Tên không có nháy kép được hiểu là peoplebyid.
-- Không tự động tham chiếu tới "PeopleById".
SELECT * FROM naming_lab.PeopleById;
```

Ở cuối ví dụ, `naming_lab.PeopleById` trỏ tới tên logic `naming_lab.peoplebyid`. Nếu không có bảng `peoplebyid` thì truy vấn thất bại; nếu tồn tại một bảng riêng mang tên ấy, truy vấn có thể đi tới **bảng khác**. Đây là lý do tránh tạo nhiều tên chỉ khác nhau về viết hoa/thường.

Việc Cassandra hỗ trợ quoted identifier không có nghĩa các hệ thống hỗ trợ schema migration, ORM hoặc các công cụ backup đều xử lý thuận tiện tên chữ hoa. Với ứng dụng mới, ưu tiên tên chữ thường để giảm chi phí bảo trì.

## 5. Dấu nháy kép, từ khóa CQL và ký tự đặc biệt

### Dùng tên trùng từ khóa của ngôn ngữ

CQL có các từ khóa dành cho câu lệnh, chẳng hạn `SELECT`, `FROM`, `WHERE`. Nếu buộc phải lấy từ khóa làm tên cột, **quoted identifier** giúp parser phân biệt:

```sql
-- Hợp lệ khi bảng có cột đúng tên "SELECT".
SELECT "SELECT" FROM naming_lab.people_by_id;
```

Dù vậy, **nên tránh từ khóa làm tên schema** nếu bạn kiểm soát được thiết kế mới. Tên như `selection_status` hoặc `query_type` rõ nghĩa và ít đòi hỏi dấu nháy kép hơn.

### Nháy kép nằm bên trong chính identifier

Khi một quoted identifier cần chứa dấu nháy kép như một phần của tên, quy tắc CQL là **viết hai dấu nháy kép liên tiếp** để biểu diễn một dấu nháy kép trong tên.

```sql
-- Minh họa cú pháp identifier:
"a""b"
```

Biểu thức trên đại diện cho tên gồm các ký tự `a"b`. Đây là quy tắc cú pháp; **đừng mặc định mọi loại đối tượng Cassandra đều cho phép mọi ký tự đặc biệt**. Keyspace và table có thể chịu quy tắc đặt tên chặt hơn cột hoặc một số đối tượng khác. Đối với schema thực tế, nên tránh kiểu tên này.

Nếu một **giá trị chuỗi** chứa dấu nháy đơn, cách escape lại khác: nhân đôi dấu nháy đơn bên trong chuỗi.

```sql
-- Giá trị text O'Brien:
INSERT INTO naming_lab.people_by_id (person_id, name)
VALUES (
    22222222-2222-4222-8222-222222222222,
    'O''Brien'
);
```

Không trộn lẫn cơ chế escape của **identifier** (dấu `"`) và **string literal** (dấu `'`).

### Dấu cách, Unicode và giới hạn tên

Quoted identifier có thể nới rộng cách biểu diễn tên ở **một số** vị trí CQL, nhưng việc cho phép dấu cách, Unicode, dấu chấm hoặc ký tự đặc biệt còn tùy loại đối tượng và phiên bản Cassandra. Các tên keyspace/table có ràng buộc lưu trữ riêng; đừng giả định chỉ cần thêm `"..."` là có thể đặt mọi tên tùy ý.

Một quy ước an toàn cho các thành phần schema là dùng:

```text
customer_profiles
orders_by_customer
created_at
shipping_address
```

Thay cho những tên buộc phải quote:

```text
"Customer Profiles"
"OrdersByCustomer"
"CREATED AT"
"SELECT"
```

Ngay cả khi một tên đặc biệt được CQL chấp nhận, nó vẫn có thể gây khó khăn cho migration, driver mapping, code generator, script shell hoặc truy vấn metadata.

## 6. Kiểm tra tên thật đã được lưu trong schema

Đọc metadata là cách đáng tin cậy để xác nhận Cassandra đã lưu identifier dưới dạng nào. Trong `cqlsh`, có thể kiểm tra:

```sql
DESCRIBE KEYSPACE naming_lab;
DESCRIBE TABLE naming_lab.people_by_id;
DESCRIBE TABLE naming_lab."PeopleById";
```

Lệnh `DESCRIBE` là tiện ích của **`cqlsh`**, không phải một CQL query phổ quát có thể gửi nguyên vẹn qua Cassandra Java Driver.

Các bảng metadata hệ thống cho phép truy vấn trực tiếp:

```sql
-- Danh sách tên keyspace đã được lưu.
SELECT keyspace_name
FROM system_schema.keyspaces
WHERE keyspace_name = 'naming_lab';

-- Tên bảng được lưu nguyên như đã khai báo.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'naming_lab';

-- Tên các cột của bảng people_by_id.
SELECT column_name, kind, position
FROM system_schema.columns
WHERE keyspace_name = 'naming_lab'
  AND table_name = 'people_by_id';
```

Nếu đã tạo bảng từ bài thực hành, kết quả metadata ở trên sẽ có các tên `person_id`, `name`, `DisplayName` và `SELECT`; Cassandra lưu tên cột quoted theo đúng chữ hoa/thường.

**Bẫy quan trọng:** trong `WHERE keyspace_name = 'naming_lab'`, dấu nháy đơn biểu thị **giá trị chuỗi để so sánh**. Truy vấn sau không tự động biến giá trị thành chữ thường:

```sql
-- Điều kiện này lọc chuỗi 'PeopleById' trong metadata.
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'naming_lab'
  AND table_name = 'PeopleById';
```

Khi so sánh giá trị ở cột `table_name`, chữ hoa/thường có ý nghĩa như dữ liệu bình thường. Quy tắc chuẩn hóa identifier áp dụng cho **tên cột trong câu CQL**, không áp dụng tự động cho literal `'PeopleById'`.

### Bảng phân biệt ba tình huống thường bị lẫn

| Ví dụ | Phần nào được phân giải như identifier? | Phần nào được coi là dữ liệu? |
| --- | --- | --- |
| `SELECT "DisplayName" FROM naming_lab.people_by_id` | `"DisplayName"`, `naming_lab`, `people_by_id` | Không có literal |
| `WHERE person_id = 11111111-...` | `person_id` | Giá trị UUID |
| `WHERE table_name = 'PeopleById'` trong metadata | `table_name` | Chuỗi `'PeopleById'`; không tự lowercase |

## 7. Tác động khi viết truy vấn từ ứng dụng Java

Trong ứng dụng Java dùng Cassandra Java Driver, **CQL vẫn tuân theo đúng quy tắc identifier kể trên**, bất kể truy vấn đi qua `cqlsh` hay driver. Ví dụ với bảng `naming_lab.people_by_id`:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

// session đã được cấu hình kết nối và đóng theo vòng đời ứng dụng.
String cql = """
    SELECT "DisplayName"
    FROM naming_lab.people_by_id
    WHERE person_id = ?
    """;

PreparedStatement ps = session.prepare(cql);
UUID id = UUID.fromString("11111111-1111-4111-8111-111111111111");
Row row = session.execute(ps.bind(id)).one();
String displayName = row == null ? null : row.getString(0);
```

Đoạn minh họa sử dụng **Java text block** (Java 15 trở lên), DataStax/Apache Cassandra Java Driver 4.x và một `CqlSession session` đã kết nối. Nó dùng `?` để bind **giá trị** `person_id`, còn identifier `"DisplayName"` phải được viết đúng trong văn bản câu truy vấn.

Nếu ứng dụng dùng Java phiên bản cũ hơn, có thể viết:

```java
String cql =
    "SELECT \"DisplayName\" FROM naming_lab.people_by_id WHERE person_id = ?";
```

Trong Java string literal, `\"` biểu diễn một dấu nháy kép của CQL; dấu nháy kép này vẫn là bắt buộc ở tầng CQL. Đừng xóa nó chỉ vì mã Java khó đọc hơn.

### Identifier không phải bind variable

Prepared statement parameter `?` dùng để ràng buộc **giá trị dữ liệu**, không dùng thay keyspace, table hoặc column. Ví dụ ý tưởng sau là sai:

```sql
-- Sai: không thể bind identifier cho tên bảng theo cách này.
SELECT * FROM ? WHERE person_id = ?;
```

Nếu ứng dụng buộc phải chọn bảng động, hãy giới hạn tên trong **allowlist cố định** và tạo CQL từ những tên đã kiểm soát, thay vì ghép trực tiếp chuỗi do người dùng nhập. Đồng thời giữ thống nhất cách trích dẫn tên trên cả lệnh tạo schema và lệnh truy vấn.

Java Driver 4 còn có kiểu `CqlIdentifier` để biểu diễn tên CQL trong metadata/configuration. Khi dùng API này, phải phân biệt tên được phân tích như cú pháp CQL với tên đã chuẩn hóa, đặc biệt nếu schema có chữ hoa. Đừng tự áp dụng `toLowerCase()` cho mọi tên lấy từ metadata: điều đó làm hỏng các quoted identifier phân biệt hoa/thường.

## 8. Lỗi thường gặp, nguyên nhân và cách sửa

| Dấu hiệu | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Truy vấn cột `DisplayName` báo `Undefined column name` | Cột thật là `"DisplayName"`, còn `DisplayName` bị chuẩn hóa thành `displayname` | Đọc metadata, dùng `"DisplayName"` đúng cách viết |
| Bảng tạo với `"PeopleById"` nhưng `SELECT ... FROM PeopleById` thất bại | Tên không có quote thành `peoplebyid` | Dùng `"PeopleById"` hoặc đổi quy ước schema trong một migration được kiểm soát |
| Muốn tạo cột tên `SELECT` mà parser báo lỗi | Tên trùng từ khóa CQL | Đổi sang tên không phải từ khóa, hoặc dùng quoted identifier nếu phải giữ tên đó |
| `SELECT ... WHERE table_name = 'peoplebyid'` không tìm thấy bảng `"PeopleById"` trong metadata | Giá trị chuỗi trong metadata có phân biệt hoa/thường | So sánh với `'PeopleById'` |
| Đặt `'column_name'` tại vị trí tên cột | Nhầm string literal với identifier | Dùng `column_name` hoặc `"ColumnName"` |
| Một script migration tạo tên khác với ứng dụng Java | Hai bên quote tên không thống nhất | Chuẩn hóa tên ở schema và truy vấn; kiểm tra metadata sau migration |
| Cố đặt keyspace/table với dấu cách và tưởng chỉ cần quote | Hạn chế đặt tên riêng của loại đối tượng/phiên bản | Dùng tên chữ thường ASCII với dấu `_` |
| Hai bảng tên gần giống nhau nhưng trả dữ liệu khác | Có hai đối tượng khác nhau vì tên quoted có chữ hoa | Liệt kê `system_schema.tables`, kiểm tra đầy đủ tên trước khi chọn bảng |

### Tình huống migration

Một hệ thống cũ khai báo cột `"CustomerID"`, còn ứng dụng mới giả định cột `customer_id`. Chỉ sửa tên trong mã Java **không thay đổi schema**. Đây là hai tên khác nhau về cả chữ hoa và dấu gạch dưới; cần quyết định một trong các phương án có kiểm soát:

1. Tiếp tục truy vấn chính xác `"CustomerID"` để tương thích schema cũ.
2. Thiết kế schema/bảng mới theo quy ước `customer_id` và chuyển dữ liệu, truy vấn, mapper một cách có kế hoạch.

Đừng mặc định có thể đổi tên mọi cột tùy ý bằng một lệnh `ALTER TABLE ... RENAME`: việc hỗ trợ đổi tên phụ thuộc loại cột và phiên bản Cassandra. Với bảng được thiết kế theo truy vấn, tạo bảng mới rồi chuyển dữ liệu thường cần được đánh giá khi thay đổi khóa hoặc mô hình truy vấn.

## 9. Bài tập tự kiểm tra

Giả sử đã có:

```sql
CREATE TABLE naming_lab.naming_quiz (
    id uuid PRIMARY KEY,
    product_code text,
    "ProductCode" text,
    "SELECT" text
);
```

Hãy dự đoán mỗi tham chiếu sau trỏ đến cột nào:

| Tham chiếu | Kết quả |
| --- | --- |
| `PRODUCT_CODE` | Cột `product_code` |
| `Product_Code` | Cột `product_code` |
| `"product_code"` | Cột `product_code` |
| `ProductCode` | Tên logic `productcode`, **không** phải `"ProductCode"`; không có cột này trong ví dụ |
| `"ProductCode"` | Cột `"ProductCode"` |
| `"PRODUCTCODE"` | Tên khác; không có cột tương ứng |
| `"SELECT"` | Cột `"SELECT"` |
| `'SELECT'` | Literal chuỗi; không phải tên cột |

Thực hành thêm:

1. Chạy `DESCRIBE TABLE naming_lab.naming_quiz` và truy vấn `system_schema.columns` để xác nhận cách lưu tên.
2. Viết một `SELECT` hợp lệ lấy `product_code` và `"ProductCode"` trong cùng câu lệnh, lọc theo `id`.
3. Thử bỏ nháy kép quanh `"ProductCode"` và quan sát lỗi. Giải thích vì sao vấn đề không liên quan đến partition key, replication hay consistency level.
4. Trong Java, viết prepared statement với bảng cố định và dùng bind marker cho `id`. Đảm bảo phần tên cột có quote được escape đúng trong Java string nếu không dùng text block.

Sau thực hành, nếu chỉ cần dọn dữ liệu thử nghiệm:

```sql
-- Chỉ chạy khi chắc chắn naming_lab là keyspace lab có thể xóa.
DROP KEYSPACE IF EXISTS naming_lab;
```

Lệnh trên xóa **toàn bộ** bảng và dữ liệu trong keyspace `naming_lab`; hãy xác minh không có đối tượng cần giữ trước khi thực hiện.

## 10. Quy ước khuyến nghị cho dự án Cassandra

Một nhóm phát triển dùng CQL từ Java có thể giảm lỗi identifier bằng quy tắc đơn giản:

1. **Keyspace/table/column/UDT dùng chữ thường `snake_case`**, tránh tên chỉ khác nhau về hoa/thường.
2. **Không dùng từ khóa CQL** làm tên; chọn tên có nghĩa nghiệp vụ, như `order_status` thay cho `"SELECT"`.
3. **Dùng tên bảng bộc lộ truy vấn** như `orders_by_customer`, nhưng nhớ partition key và clustering columns mới quyết định cách lưu và đọc dữ liệu.
4. **Duy trì cùng một quy ước** trong migration, CQL, mapping Java, kiểm thử và tài liệu vận hành.
5. **Đọc metadata thực tế** khi xử lý schema cũ có quoted identifier; không đoán tên đã được chuẩn hóa.
6. **Tránh nối identifier từ đầu vào tự do**, dùng allowlist và bind dữ liệu bằng prepared statement.

Một bảng có tên `orders_by_customer` và cột `customer_id` dễ truy vấn, ghi log và kiểm tra hơn các tên `"OrdersByCustomer"` hoặc `"CustomerID"`. Sự đơn giản này đặc biệt có ích khi cluster có nhiều keyspace, nhiều bảng phi chuẩn hóa theo truy vấn, nhiều bản sao và nhiều thành phần Java truy cập đồng thời.

**Ghi nhớ:** unquoted identifier được chuẩn hóa thành chữ thường; quoted identifier giữ nguyên chữ hoa/thường; dấu nháy đơn biểu diễn literal. Hiểu đúng ba quy tắc này là nền tảng để tạo schema, kiểm tra keyspace/table/column và viết CQL tin cậy cho Apache Cassandra.
