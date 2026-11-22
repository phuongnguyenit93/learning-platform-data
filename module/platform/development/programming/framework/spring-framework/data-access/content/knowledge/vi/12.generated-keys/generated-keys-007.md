# Nhiều khóa sinh hoặc nhiều cột khóa và cách đọc phù hợp

Khi chèn dữ liệu bằng JDBC hoặc Spring JDBC, một tình huống đơn giản là bảng có một cột `id` tự sinh, mỗi lệnh `INSERT` tạo đúng một hàng và code chỉ cần lấy một giá trị số. Tuy nhiên, ứng dụng thực tế có thể gặp **nhiều cột tạo nên khóa**, **nhiều giá trị được database sinh ra**, hoặc **nhiều hàng được chèn trong cùng một thao tác**. Nếu luôn gọi `getKey()` hay đọc ô đầu tiên của `ResultSet`, ứng dụng dễ làm mất dữ liệu định danh, hiểu nhầm kết quả hoặc gặp exception.

Bài này hướng dẫn đọc khóa sinh theo đúng *hình dạng* kết quả: **số hàng × số cột**, phân biệt khóa chính ghép với nhiều cột được database trả, và lựa chọn API phù hợp giữa `Statement.getGeneratedKeys()`, `Spring KeyHolder`, `NamedParameterJdbcTemplate` và cú pháp `RETURNING/OUTPUT` đặc thù hệ quản trị.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **một khóa số đơn**, **khóa chính ghép nhiều cột**, **nhiều cột giá trị sinh ra**, và **nhiều hàng khóa sinh**.
2. Hiểu vì sao `getGeneratedKeys()` trả một `ResultSet` và phải đọc **cả hàng lẫn cột** khi không còn ở trường hợp đơn giản.
3. Dùng đúng `Connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` hoặc overload yêu cầu tên cột được trả.
4. Đọc `ResultSetMetaData`, `getColumnLabel(index)` và `getObject(index)` bằng chỉ số cột **bắt đầu từ 1**.
5. Chọn đúng `KeyHolder.getKey()`, `getKeyAs(Class)`, `getKeys()` hoặc `getKeyList()` trong Spring Framework.
6. Viết code Java 17+ an toàn khi một phần khóa ghép đã biết ở ứng dụng và phần còn lại do database sinh ra.
7. Biết giới hạn về JDBC driver, kiểu khóa `Long/BigDecimal/UUID`, thứ tự batch và khả năng lấy nhiều cột.
8. Kiểm thử kết quả từ 0/1/nhiều hàng, 1/nhiều cột và tình huống transaction rollback.

## 2. Trước hết hãy phân biệt bốn khái niệm

Một số cách nói “nhiều khóa sinh” có thể đang chỉ những hiện tượng **khác nhau**:

| Khái niệm | Ví dụ | Đặc điểm cần đọc |
| --- | --- | --- |
| **Một khóa tự sinh** | `shipment_no` do identity/sequence sinh | Một hàng × một cột; thường trả `Number` |
| **Khóa chính ghép (composite primary key)** | `(tenant_id, shipment_no)` | Một định danh gồm **hai thành phần**; có thể chỉ một thành phần tự sinh |
| **Nhiều cột được database trả về** | `shipment_no` và `created_at` | Một hàng × nhiều cột; không phải mọi cột trả về đều là “khóa chính” |
| **Nhiều khóa cho nhiều hàng** | Chèn 3 shipment, nhận 3 shipment numbers | Nhiều hàng × một hoặc nhiều cột; cần đọc hết kết quả |

**Khóa chính ghép không đồng nghĩa nhiều cột tự sinh.** Ví dụ `tenant_id` do tầng xác thực chọn, còn `shipment_no` do sequence sinh; cặp `(tenant_id, shipment_no)` tạo thành khóa chính, nhưng database chỉ cần sinh `shipment_no`. Ngược lại, database có thể sinh thêm `created_at` hoặc `public_id` trong một bảng chỉ có **một** primary key.

Phân loại trước khi chọn API giúp tránh hai kiểu lỗi: làm mất thành phần định danh và ép một bảng kết quả thành một con số duy nhất.

### Mô hình số hàng × số cột

Hãy hình dung kết quả mà driver có thể đưa ra thông qua `getGeneratedKeys()`:

~~~text
1 hàng × 1 cột                 1 hàng × 2 cột
+-------------+                +-----------+-------------+
| shipment_no |                | tenant_id | shipment_no |
+-------------+                +-----------+-------------+
|         301 |                |         7 |         301 |
+-------------+                +-----------+-------------+

2 hàng × 1 cột                 2 hàng × 2 cột
+-------------+                +-----------+-------------+
| shipment_no |                | tenant_id | shipment_no |
+-------------+                +-----------+-------------+
|         301 |                |         7 |         301 |
|         302 |                |         7 |         302 |
+-------------+                +-----------+-------------+
~~~

Các bảng này là **mẫu cấu trúc**, không bảo đảm mọi driver trả được đúng từng dạng từ mọi câu `INSERT`. Việc driver có trả cột nào, có trả nhiều hàng sau batch và tên/type của cột là **khả năng phải kiểm chứng**.

## 3. Ví dụ schema: composite key nhưng chỉ một cột tự sinh

Dùng PostgreSQL để minh họa một schema cụ thể:

~~~sql
CREATE TABLE shipment (
    tenant_id BIGINT NOT NULL,
    shipment_no BIGINT GENERATED ALWAYS AS IDENTITY,
    state VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, shipment_no)
);
~~~

Ở đây:

- `tenant_id` do ứng dụng xác định từ tenant đã được phân quyền.
- `shipment_no` được PostgreSQL cấp bằng identity.
- Primary key là **hai cột** `(tenant_id, shipment_no)`.
- `created_at` cũng có default từ database, nhưng **không thuộc primary key**.
- Identity sequence trong ví dụ là cơ chế database cấp giá trị; không suy ra nó bắt đầu từ 1 riêng cho mỗi tenant.

Một lệnh chèn:

~~~sql
INSERT INTO shipment (tenant_id, state)
VALUES (7, 'NEW');
~~~

Sau chèn, ứng dụng muốn biết `ShipmentKey(tenantId=7, shipmentNo=...)` để tham chiếu hàng vừa tạo. Thông tin `tenantId=7` đã có **trước INSERT**; chỉ cần lấy thêm `shipment_no` do database sinh.

### Không nhầm lẫn “khóa ghép” với yêu cầu driver sinh hai khóa

Nếu code cố lấy đồng thời `tenant_id` và `shipment_no` qua API generated keys, phải hỏi: driver có coi `tenant_id` do ứng dụng bind là *auto-generated column* để trả về không? Điều này không bảo đảm bởi việc nó tham gia primary key. Cách portable hơn là **giữ `tenantId` trong Java và chỉ yêu cầu cột sinh ra**; hoặc dùng cú pháp database-specific `RETURNING` để trả cả hai cột.

Schema và cú pháp `GENERATED ALWAYS AS IDENTITY` ở trên là ví dụ **PostgreSQL**, không đại diện tự động cho DDL MySQL/SQL Server/Oracle/H2. Thực tế có thể khác về datatype, tính năng nhiều identity và trigger.

## 4. JDBC: cách yêu cầu khóa sinh

Một `PreparedStatement` có thể được tạo với chế độ muốn nhận generated keys.

### 4.1. Chế độ tổng quát RETURN_GENERATED_KEYS

~~~java
String sql = "INSERT INTO shipment (tenant_id, state) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setLong(1, 7L);
    ps.setString(2, "NEW");
    int affected = ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        while (keys.next()) {
            // Đọc một hàng generated keys do driver trả.
        }
    }
}
~~~

Đây là đoạn **JDBC tích hợp**, cần imports, một `Connection connection` và database phù hợp. `Statement.RETURN_GENERATED_KEYS` báo driver rằng ứng dụng muốn lấy khóa sinh. Theo API JDBC, nếu không chỉ rõ cột nào, **driver quyết định** những cột được coi là phù hợp để trả.

Điều này rất quan trọng: không được tự động suy ra driver luôn trả **cột id duy nhất**, hoặc trả **tất cả cột default**, hoặc trả **đúng hai cột của composite PK**. Những giả định ấy có thể đúng trên một driver nhưng sai trên driver khác.

### 4.2. Yêu cầu tên cột cụ thể

JDBC có overload:

~~~java
String sql = "INSERT INTO shipment (tenant_id, state) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(
        sql, new String[]{"shipment_no"})) {
    ps.setLong(1, 7L);
    ps.setString(2, "NEW");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            Object shipmentNo = keys.getObject(1);
            // Kiểm tra kiểu, số hàng và lưu định danh.
        }
    }
}
~~~

Tham số `new String[]{"shipment_no"}` **yêu cầu** driver trả giá trị sinh ở cột `shipment_no`. Chỉ định danh sách cột giúp giảm sự mơ hồ so với để driver chọn. Nhưng khả năng xử lý tên cột và trả đúng tập cột vẫn phụ thuộc JDBC driver/database; kiểm tra integration test.

Trong trường hợp muốn nhiều cột, có thể yêu cầu:

~~~java
connection.prepareStatement(
        sql, new String[]{"shipment_no", "created_at"});
~~~

Đây chỉ là **khả năng API**: có driver cho phép trả thêm cột `created_at` mặc dù đó là giá trị default, có driver chỉ trả generated key theo nghĩa hẹp hoặc không hỗ trợ yêu cầu đó. Không coi việc truyền mảng hai tên là cam kết portable rằng kết quả chứa hai cột.

### 4.3. Không phải một con số được trả ngay

Phương thức `getGeneratedKeys()` của `Statement` trả về **`ResultSet`**, ngay cả khi chỉ có một khóa. Nếu không sinh khóa nào, API mô tả một result set rỗng; nếu driver không hỗ trợ, có thể phát sinh `SQLFeatureNotSupportedException` hoặc lỗi tương đương tùy API/driver. Có thể kiểm tra `connection.getMetaData().supportsGetGeneratedKeys()` như một tín hiệu hỗ trợ ở cấp metadata, nhưng test trên câu SQL và driver thật vẫn cần thiết.

`executeUpdate()` trả **số hàng được tác động hoặc mã theo hợp đồng phương thức**, không phải giá trị khóa sinh. Ví dụ một `INSERT` tác động một hàng và sinh `shipment_no=301` thì `affected=1` khác hoàn toàn `shipment_no=301`. Đừng lấy `int affected` để làm ID.

## 5. Đọc hết các hàng và cột từ getGeneratedKeys()

Khi không biết chắc driver trả bao nhiêu cột/hàng, dùng `ResultSetMetaData` để kiểm tra thay vì mặc định `rs.getLong(1)`.

Mẫu phương thức Java 17+ **dùng được trong class JDBC đã có `ResultSet` hợp lệ**:

~~~java
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class GeneratedKeyReader {
    private GeneratedKeyReader() {}

    public static List<Map<String, Object>> readAll(ResultSet rs)
            throws SQLException {
        ResultSetMetaData meta = rs.getMetaData();
        int columnCount = meta.getColumnCount();
        List<Map<String, Object>> rows = new ArrayList<>();

        while (rs.next()) {
            Map<String, Object> row = new LinkedHashMap<>();
            for (int column = 1; column <= columnCount; column++) {
                String label = meta.getColumnLabel(column);
                if (row.containsKey(label)) {
                    throw new SQLException(
                            "Duplicate generated-key column label: " + label);
                }
                row.put(label, rs.getObject(column));
            }
            rows.add(row);
        }
        return rows;
    }
}
~~~

**Tại sao đọc như vậy?**

- `while (rs.next())` đi qua **mọi hàng** kết quả, không giả định chỉ có một hàng.
- `getColumnCount()` xác định số cột của result set thực tế.
- Chỉ số cột JDBC ở `getColumnLabel(column)` và `getObject(column)` **bắt đầu từ 1**.
- `getColumnLabel()` ưu tiên nhãn/alias do result set công bố; có thể khác cách đặt tên trong DDL.
- `getObject()` giữ kiểu Java theo driver và trả Java `null` khi giá trị SQL NULL.
- `LinkedHashMap` giữ thứ tự **đọc** các cột thuận tiện cho phân tích, không có nghĩa thứ tự cột là danh tính logic của composite key.
- Kiểm tra trùng label tránh silently overwrite cột nếu result set có hai tên/alias giống nhau. Trong production có thể chọn các label unique từ query.

Phương thức này **không tạo ra generated keys**; nó chỉ đọc một `ResultSet` được driver cung cấp. Vì thế cần gọi sau lệnh cập nhật đã thực thi với lựa chọn lấy keys phù hợp và đóng result set đúng vòng đời.

### Đừng đọc một cột bằng tên nếu driver trả tên khác

Ví dụ code:

~~~java
long shipmentNo = keys.getLong("shipment_no");
~~~

chỉ đúng khi result set có **column label** tương ứng. Driver có thể trả nhãn khác hoặc biến đổi chữ hoa/thường; xác minh bằng `ResultSetMetaData` hoặc chỉ định tên cột rõ ràng ở nơi driver hỗ trợ. Đọc `getObject(1)` có thể phù hợp khi **đã xác minh chỉ có đúng một cột**; đọc index 1 rồi mặc định nó là `shipment_no` khi có nhiều cột là không an toàn.

### Không suy luận type từ tên cột

Nếu `getObject(...)` trả `BigDecimal`, `BigInteger`, `Long`, `Integer`, `UUID` hoặc một kiểu driver-specific, phải chuyển đổi theo schema và contract. `getLong("shipment_no")` hỗ trợ SQL numeric nhưng có thể mất thông tin SQL NULL nếu không dùng `wasNull()`. Với khóa thực sự `NOT NULL`, null là dấu hiệu cần xử lý như lỗi dữ liệu, không làm ID mặc định 0.

## 6. Java JDBC hoàn chỉnh cho một composite key có một cột sinh

Đây là **class Java 17 có thể biên dịch riêng bằng JDK** nhưng cần `DataSource` đã được cấu hình với JDBC driver, schema `shipment` và một database PostgreSQL tương thích mới có thể chạy thao tác chèn. Không có `main` và không đưa ra stdout giả định.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ShipmentJdbcDao {
    public record ShipmentKey(long tenantId, long shipmentNo) {}

    private final DataSource dataSource;

    public ShipmentJdbcDao(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public ShipmentKey insert(long authorizedTenantId, String state)
            throws SQLException {
        String sql =
                "INSERT INTO shipment (tenant_id, state) VALUES (?, ?)";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(
                     sql, new String[]{"shipment_no"})) {

            ps.setLong(1, authorizedTenantId);
            ps.setString(2, state);

            int affected = ps.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                        "Expected one inserted row, got " + affected);
            }

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("No generated shipment_no returned");
                }

                Object raw = keys.getObject(1);
                if (!(raw instanceof Number number)) {
                    throw new SQLException(
                            "shipment_no is not a numeric generated key");
                }

                long shipmentNo = number.longValue();
                if (keys.next()) {
                    throw new SQLException(
                            "Expected one generated-key row");
                }

                return new ShipmentKey(authorizedTenantId, shipmentNo);
            }
        }
    }
}
~~~

Các chi tiết đúng mục tiêu:

- Chỉ yêu cầu `shipment_no` vì `tenantId` **đã biết trong Java**.
- Chỉ số binding JDBC: `1 = tenant_id`, `2 = state`.
- Kiểm tra `affected==1`, có đúng một row chứa generated key, và value là `Number`.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement`, `Connection` theo thứ tự hợp lý; không để resource leak.
- `ShipmentKey` giữ đủ **hai thành phần khóa chính** để tầng ứng dụng dùng cho truy vấn/quan hệ tiếp theo.

**Lưu ý chuyển đổi số:** `Number.longValue()` có thể làm mất phần lẻ hoặc tràn nếu nguồn không nằm trong phạm vi `long`. Mẫu này giả định cột `shipment_no BIGINT` của schema và driver trả biểu diễn số nguyên phù hợp. Ở hệ thống có yêu cầu kiểm tra chính xác, cần validate kiểu/range hoặc dùng phương thức chuyển đổi exact tương ứng (chẳng hạn `BigDecimal.longValueExact()`), không ép mọi generated value thành `long`.

Nếu method được gọi trong Spring-managed transaction, dùng `JdbcTemplate`/`DataSourceUtils` theo transaction manager để không vô tình lấy một connection nằm ngoài transaction đã mở. Class JDBC thuần ở đây là bài tập ownership độc lập; ví dụ Spring ở phần sau phù hợp hơn với ứng dụng Spring.

## 7. Spring KeyHolder biểu diễn **List<Map<String, Object>>**

Spring `org.springframework.jdbc.support.KeyHolder` (với implementation phổ biến `GeneratedKeyHolder`) lưu generated keys theo cấu trúc tổng quát:

~~~java
List<Map<String, Object>>
~~~

Mỗi **phần tử trong List** tương ứng **một hàng generated keys**, và mỗi **entry trong Map** tương ứng **một cột/label được trả về cho hàng đó**.

Một số mô phỏng:

~~~text
Một hàng, một cột:
[
  {shipment_no=301}
]

Một hàng, hai cột:
[
  {tenant_id=7, shipment_no=301}
]

Hai hàng, mỗi hàng một cột:
[
  {shipment_no=301},
  {shipment_no=302}
]

Hai hàng, mỗi hàng hai cột:
[
  {tenant_id=7, shipment_no=301},
  {tenant_id=7, shipment_no=302}
]
~~~

Đây là **biểu diễn minh họa**, không phải JSON hay cấu trúc log thật; actual maps phụ thuộc cột driver trả về. Chỉ cần nhìn cấu trúc ta đã thấy vì sao API “lấy một `Number`” không thể biểu diễn tất cả các trường hợp.

### 7.1. getKey(): đúng một hàng, đúng một cột, kiểu Number

`KeyHolder.getKey()` phù hợp với tình huống phổ biến nhất: **một** hàng khóa sinh, **một** cột khóa sinh kiểu numeric.

~~~java
Number value = keyHolder.getKey();
if (value == null) {
    throw new IllegalStateException("No generated key");
}
long id = value.longValue();
~~~

Đoạn này giả định biến `keyHolder` đã có từ thao tác INSERT. Nếu có **nhiều hàng** hoặc một hàng chứa **nhiều cột**, `getKey()` **không lấy tùy tiện cột đầu tiên**: theo contract Spring, nó ném `InvalidDataAccessApiUsageException` khi số key không còn là một. Nếu giá trị không phải `Number`, cần API/kiểu đọc phù hợp, không ép kiểu bừa.

### 7.2. getKeyAs(Class<T>): một giá trị đơn nhưng không nhất thiết Number

Trong Spring phiên bản hỗ trợ, `getKeyAs(Class<T>)` giúp lấy một key duy nhất có kiểu tương ứng:

~~~java
UUID id = keyHolder.getKeyAs(UUID.class);
~~~

Chỉ dùng khi result thực tế có **một hàng × một cột** và JDBC driver trả một object có kiểu runtime tương thích `UUID`. Không mặc định driver nào cũng map SQL UUID thành `java.util.UUID`; có driver trả `String` hoặc kiểu riêng. Nếu không tương thích, API có thể gây lỗi kiểu; kiểm tra thực tế hoặc chuyển đổi tường minh từ object phù hợp.

`getKeyAs(...)` không biến multi-column composite key thành một object: nó vẫn yêu cầu **một** giá trị trong **một** hàng.

### 7.3. getKeys(): đúng một hàng, có thể nhiều cột

Khi driver trả một hàng nhưng nhiều cột, dùng:

~~~java
Map<String, Object> columns = keyHolder.getKeys();
if (columns == null || columns.isEmpty()) {
    throw new IllegalStateException("No generated-key columns");
}

for (Map.Entry<String, Object> entry : columns.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

Chỗ này `getKeys()` chỉ thích hợp nếu có **một hàng generated keys**. Nếu KeyHolder chứa nhiều hàng, Spring ném `InvalidDataAccessApiUsageException` để tránh mất thông tin. Còn Map có bao nhiêu cột thì ứng dụng được tự xử lý.

**Đừng làm** `columns.values().iterator().next()` rồi mặc định đó là ID khi Map có nhiều entries: thứ tự Map không phải hợp đồng định danh. Hãy lấy theo **tên cột được xác nhận**:

~~~java
Object tenant = columns.get("tenant_id");
Object shipment = columns.get("shipment_no");
~~~

Ví dụ này **chỉ đúng khi các key label thực tế là `tenant_id`/`shipment_no`**. Driver có thể thay đổi chữ hoa/thường hoặc trả cột khác; kiểm tra tập key qua metadata/integration tests. Nếu `tenant_id` đã biết từ input, không nhất thiết phải yêu cầu DB trả lại.

### 7.4. getKeyList(): nhiều hàng, mỗi hàng có thể nhiều cột

Khi cần toàn bộ generated keys của nhiều hàng:

~~~java
List<Map<String, Object>> keyRows = keyHolder.getKeyList();

for (Map<String, Object> row : keyRows) {
    Object raw = row.get("shipment_no");
    // Kiểm tra kiểu và sự có mặt của cột trong từng row.
}
~~~

Đây là API cho **nhiều hàng**; nếu một hàng chứa nhiều cột, từng Map cũng có nhiều entries. Đừng gọi `getKeys()` hay `getKey()` trong một batch đã trả nhiều key rows. `getKeyList()` có thể rỗng nếu driver không trả keys, cần kiểm tra **số row**, cấu trúc cột và kiểu dữ liệu thay vì giả định thành công chỉ vì INSERT không ném exception.

### Bảng chọn API

| Hình dạng generated keys thực tế | API Spring phù hợp | Cần tránh |
| --- | --- | --- |
| 1 hàng × 1 cột numeric | `getKey()` | Ép type cụ thể mà chưa kiểm tra |
| 1 hàng × 1 cột UUID/String | `getKeyAs(T.class)` nếu driver trả đúng T | `getKey()` giả định Number |
| 1 hàng × N cột | `getKeys()` hoặc `getKeyList()` | `getKey()` |
| N hàng × 1 cột | `getKeyList()` | `getKeys()` và `getKey()` |
| N hàng × M cột | `getKeyList()` | Lấy tùy tiện map/row đầu |
| Không có key row | Kiểm tra rỗng/null và hợp đồng thao tác | Ngầm trả ID 0 |

## 8. Ví dụ Java 17 chạy độc lập: phân biệt hình dạng keys

Đoạn này **không kết nối database hoặc dùng Spring**, mà mô phỏng đúng cấu trúc `List<Map<String,Object>>` để bạn thực hành “một hàng × một cột” và “nhiều hàng/cột” trước khi tích hợp. Dùng thuần JDK 17, không cần dependency ngoài.

Lưu file **`GeneratedKeysShapeDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;

public class GeneratedKeysShapeDemo {
    record ShipmentKey(long tenantId, long shipmentNo) {}

    static long onlyNumericKey(List<Map<String, Object>> keyRows) {
        if (keyRows.size() != 1 || keyRows.get(0).size() != 1) {
            throw new IllegalArgumentException("Expected exactly one row and one column");
        }
        Object value = keyRows.get(0).values().iterator().next();
        if (!(value instanceof Number n)) {
            throw new IllegalArgumentException("Expected numeric key");
        }
        return n.longValue();
    }

    static ShipmentKey compositeKey(Map<String, Object> row) {
        Object tenant = row.get("tenant_id");
        Object shipment = row.get("shipment_no");
        if (!(tenant instanceof Number t) || !(shipment instanceof Number s)) {
            throw new IllegalArgumentException("Missing or nonnumeric composite key");
        }
        return new ShipmentKey(t.longValue(), s.longValue());
    }

    public static void main(String[] args) {
        var single = List.<Map<String, Object>>of(
                Map.of("shipment_no", 301L));
        var twoColumns = List.<Map<String, Object>>of(
                Map.of("tenant_id", 7L, "shipment_no", 301L));
        var twoRows = List.<Map<String, Object>>of(
                Map.of("shipment_no", 301L),
                Map.of("shipment_no", 302L));

        System.out.println("Single key: " + onlyNumericKey(single));
        System.out.println("Composite: " + compositeKey(twoColumns.get(0)));
        System.out.println("Rows of generated keys: " + twoRows.size());
        try {
            onlyNumericKey(twoColumns);
        } catch (IllegalArgumentException expected) {
            System.out.println("Cannot flatten two columns into one key");
        }
        try {
            onlyNumericKey(twoRows);
        } catch (IllegalArgumentException expected) {
            System.out.println("Cannot flatten two rows into one key");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 GeneratedKeysShapeDemo.java
java GeneratedKeysShapeDemo
~~~

Stdout đúng:

~~~text
Single key: 301
Composite: ShipmentKey[tenantId=7, shipmentNo=301]
Rows of generated keys: 2
Cannot flatten two columns into one key
Cannot flatten two rows into one key
~~~

**Ý nghĩa:** Mô phỏng chứng minh rằng hàm chỉ nhận “một row, một column” phải từ chối trường hợp nhiều cột/nhiều hàng, thay vì âm thầm chọn phần tử đầu. Nó **không mô phỏng hành vi driver tự sinh khóa**, nên cần integration tests JDBC/Spring để xác minh loại/result metadata thực tế.

## 9. Spring NamedParameterJdbcTemplate: lấy một cột khóa sinh

Trong một ứng dụng Spring đã có bean `NamedParameterJdbcTemplate jdbc`, có thể yêu cầu key column cụ thể:

~~~java
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

public record ShipmentKey(long tenantId, long shipmentNo) {}

public ShipmentKey createShipment(
        NamedParameterJdbcTemplate jdbc,
        long authorizedTenantId,
        String state) {

    String sql = """
            INSERT INTO shipment (tenant_id, state)
            VALUES (:tenantId, :state)
            """;

    var params = new MapSqlParameterSource()
            .addValue("tenantId", authorizedTenantId)
            .addValue("state", state);

    KeyHolder holder = new GeneratedKeyHolder();
    int affected = jdbc.update(
            sql, params, holder, new String[]{"shipment_no"});

    if (affected != 1) {
        throw new IllegalStateException("Expected one inserted row");
    }

    Map<String, Object> row = holder.getKeys();
    if (row == null || row.size() != 1) {
        throw new IllegalStateException(
                "Expected one generated-key column");
    }
    Object raw = row.values().iterator().next();
    if (!(raw instanceof Number n)) {
        throw new IllegalStateException(
                "Generated shipment_no is not numeric");
    }
    return new ShipmentKey(authorizedTenantId, n.longValue());
}
~~~

Đây là **mã minh họa phương thức và record ở cấp class trong một Spring application**, không thể copy nguyên xi vào một file có top-level method trong Java. Để dùng thực tế, đặt record và method bên trong một class repository/service hợp lệ, truyền/inject `NamedParameterJdbcTemplate`, bảo đảm có bean DataSource, JDBC driver và schema. Tình huống **yêu cầu đúng một key column** và validate Map có đúng một entry trước khi đọc value. Mã không giả định driver tự trả `tenant_id`.

**Vì sao dùng `getKeys()` thay vì `getKey()`?** Cả hai có thể dùng khi driver trả đúng một numeric key; ở đây `getKeys()` giúp kiểm soát **số lượng cột**, phù hợp với bài học về hình dạng kết quả. Nếu driver chỉ trả một key numeric và đã xác minh contract, có thể dùng `Number number = holder.getKey()` rồi kiểm tra null.

**Cẩn trọng với source layout của snippet:** Java không cho phép top-level method không nằm trong class; khi tích hợp, viết hẳn class repository và chọn nơi khai báo record phù hợp. Nội dung SQL text block kết thúc **trước** khi truyền cho `jdbc.update`, nên không mắc lỗi nối text-block mất khoảng trắng.

### Ví dụ class Spring có cấu trúc biên dịch đúng

Mẫu hoàn chỉnh hơn (vẫn cần thư viện Spring và database để chạy):

~~~java
import java.util.Map;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public final class ShipmentRepository {
    public record ShipmentKey(long tenantId, long shipmentNo) {}

    private final NamedParameterJdbcTemplate jdbc;

    public ShipmentRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public ShipmentKey create(long tenantId, String state) {
        String sql = """
                INSERT INTO shipment (tenant_id, state)
                VALUES (:tenantId, :state)
                """;

        var params = new MapSqlParameterSource()
                .addValue("tenantId", tenantId)
                .addValue("state", state);

        KeyHolder holder = new GeneratedKeyHolder();
        int count = jdbc.update(
                sql, params, holder, new String[]{"shipment_no"});
        if (count != 1) {
            throw new IllegalStateException("Expected one inserted row");
        }

        Map<String, Object> columns = holder.getKeys();
        if (columns == null || columns.size() != 1) {
            throw new IllegalStateException(
                    "Expected one generated-key column");
        }
        Object value = columns.values().iterator().next();
        if (!(value instanceof Number number)) {
            throw new IllegalStateException("Generated key is not numeric");
        }
        return new ShipmentKey(tenantId, number.longValue());
    }
}
~~~

Đối với code production, lớp gọi phải cung cấp **tenantId đã kiểm chứng quyền**; tránh nhận trực tiếp ID tenant không được xác thực từ request. Muốn có consistency khi lưu nhiều bảng phụ thuộc khóa mới, gọi repository trong một Spring-managed transaction phù hợp. Việc đọc key sau `INSERT` xảy ra **trước commit**, nên “đã nhận ID” không đồng nghĩa transaction đã được commit thành công.

## 10. Một hàng chứa nhiều cột được trả: đọc theo tên cột

Nếu driver hỗ trợ trả hai cột bằng `keyColumnNames`, Spring có thể nhận kết quả một hàng chứa nhiều entries:

~~~java
KeyHolder holder = new GeneratedKeyHolder();

int count = namedJdbc.update(
        insertSql,
        params,
        holder,
        new String[]{"shipment_no", "created_at"}
);

Map<String, Object> columns = holder.getKeys();
if (count != 1 || columns == null) {
    throw new IllegalStateException("No single-row key result");
}
Object number = columns.get("shipment_no");
Object createdAt = columns.get("created_at");
~~~

Đây là ví dụ **tích hợp với điều kiện driver hỗ trợ**. `created_at` có thể là default database nhưng không phải thành phần khóa; nó chỉ là **giá trị database trả cùng**. Đừng gọi `getKey()` nếu hai cột thực sự đã được trả, vì `getKey()` yêu cầu đúng một cột.

**Quan trọng:** việc truyền tên hai cột **không đảm bảo** cả hai đều được trả. Cần kiểm tra `columns.keySet()`, nullability và JDBC runtime type. Nếu hệ quản trị cần cung cấp tất cả cột một cách xác định, cân nhắc cú pháp `RETURNING/OUTPUT` đặc thù database.

### Đọc composite key từ Map

Một kết quả giả định:

~~~text
columns = {tenant_id=7, shipment_no=301}
~~~

Có thể ánh xạ:

~~~java
Object tenantRaw = columns.get("tenant_id");
Object shipmentRaw = columns.get("shipment_no");

if (!(tenantRaw instanceof Number t)
        || !(shipmentRaw instanceof Number s)) {
    throw new IllegalStateException("Composite key columns missing");
}
ShipmentRepository.ShipmentKey key =
        new ShipmentRepository.ShipmentKey(
                t.longValue(), s.longValue());
~~~

Đoạn minh họa cần class `ShipmentRepository` từ phần trước và Map có đúng labels. Đừng dựa vào thứ tự value của Map để tạo composite key: `(tenant_id, shipment_no)` có ý nghĩa **theo tên trường**. Nếu column labels khác tên dự kiến, phải xử lý theo metadata/alias được xác minh, không âm thầm hoán đổi hai giá trị numeric.

## 11. Khi nào dùng SQL RETURNING hoặc OUTPUT?

Không phải database/driver nào cũng trả nhiều generated columns qua `getGeneratedKeys()` một cách tiện lợi. Một số hệ quản trị cho phép lệnh ghi **trả trực tiếp những cột bạn yêu cầu**.

### PostgreSQL: INSERT ... RETURNING

Với schema `shipment` ở phần 3:

~~~sql
INSERT INTO shipment (tenant_id, state)
VALUES (:tenantId, :state)
RETURNING tenant_id, shipment_no, created_at;
~~~

Trên PostgreSQL, phần `RETURNING` chỉ rõ ba cột muốn lấy. Một record Java đại diện **khóa chính ghép** có thể được tạo từ hai cột đầu; `created_at` là metadata được tạo cùng row chứ không thuộc khóa.

Với `NamedParameterJdbcTemplate` và PostgreSQL JDBC driver có hỗ trợ kết quả từ `RETURNING`, cách xử lý theo dạng query là:

~~~java
String sql = """
        INSERT INTO shipment (tenant_id, state)
        VALUES (:tenantId, :state)
        RETURNING tenant_id, shipment_no
        """;

var params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("state", state);

ShipmentRepository.ShipmentKey key = namedJdbc.queryForObject(
        sql,
        params,
        (rs, rowNum) -> new ShipmentRepository.ShipmentKey(
                rs.getLong("tenant_id"),
                rs.getLong("shipment_no"))
);
~~~

Đoạn này là **ví dụ tích hợp PostgreSQL**, không phải SQL portable. Khi dùng `INSERT ... RETURNING`, bạn đang đọc ResultSet từ câu lệnh ghi, nên chọn API có khả năng đọc kết quả thay vì tưởng `int updateCount` là khóa. Nếu 0/multiple rows vi phạm hợp đồng queryForObject, Spring sẽ áp quy tắc cardinality tương ứng; cần xử lý lỗi theo nghiệp vụ.

Nếu code cần giá trị mặc định mới sinh như `created_at`, thêm cột vào `RETURNING` rồi ánh xạ record/DTO phù hợp. Tính đúng đắn và cấu trúc dữ liệu phụ thuộc PostgreSQL, query và driver đang dùng.

### SQL Server: OUTPUT INSERTED

SQL Server có cấu trúc tương tự về ý nghĩa nhưng **cú pháp khác**:

~~~sql
INSERT INTO shipment (tenant_id, state)
OUTPUT INSERTED.tenant_id, INSERTED.shipment_no
VALUES (@tenantId, @state);
~~~

Đây là **mẫu T-SQL cú pháp**, không dùng trực tiếp `@tenantId` trong `NamedParameterJdbcTemplate` như thể đó là cú pháp Spring. Khi triển khai Java, hãy chọn marker hợp lệ cho driver/framework và điều chỉnh cho SQL Server. Kết quả `OUTPUT` có thể chứa nhiều hàng/cột, vì vậy vẫn phải đọc theo hình dạng thực tế.

Các hệ khác như Oracle có hỗ trợ `RETURNING ... INTO` với cơ chế/binding khác; MySQL có cơ chế lấy auto-increment ID và giới hạn riêng. **Không copy nguyên cú pháp giữa database**. Chọn API theo driver + dialect được xác minh trong test.

## 12. Nhiều hàng được chèn: generated keys có thể nhiều dòng

Ví dụ về mong muốn nghiệp vụ:

~~~text
Input 1 -> INSERT row A -> generated shipment_no 301
Input 2 -> INSERT row B -> generated shipment_no 302
Input 3 -> INSERT row C -> generated shipment_no 303
~~~

Một số driver có thể trả nhiều hàng generated keys khi thực hiện **multi-row INSERT** hoặc **JDBC batch**. Nhưng đây là chỗ dễ sai:

1. Số generated-key rows có thể không khớp số input rows khi driver không hỗ trợ hoặc dùng SQL đặc thù.
2. Thứ tự của generated-key rows **không phải cam kết portable** rằng chúng luôn trùng thứ tự input/batch.
3. Update counts của batch không phải generated IDs.
4. Một bản ghi bị từ chối có thể khiến toàn batch lỗi hoặc trả kết quả một phần theo chính sách driver/transaction.
5. Khi một hàng trả nhiều cột, bạn cần map từng hàng trước khi sử dụng.

### Spring NamedParameterJdbcTemplate.batchUpdate và KeyHolder

Spring có overload nhận cả `KeyHolder`:

~~~java
String sql = """
        INSERT INTO shipment (tenant_id, state)
        VALUES (:tenantId, :state)
        """;

SqlParameterSource[] batch = {
        new MapSqlParameterSource()
                .addValue("tenantId", 7L)
                .addValue("state", "NEW"),
        new MapSqlParameterSource()
                .addValue("tenantId", 7L)
                .addValue("state", "PENDING")
};

KeyHolder keys = new GeneratedKeyHolder();

int[] counts = namedJdbc.batchUpdate(
        sql, batch, keys, new String[]{"shipment_no"});

List<Map<String, Object>> keyRows = keys.getKeyList();
~~~

Đây là **code tích hợp** với imports Spring phù hợp. Overload này yêu cầu **driver hỗ trợ generated keys trong batch**. Không mặc định `keyRows.size()==batch.length` hay phần tử thứ i là ID của phần tử thứ i khi chưa có bằng chứng driver/schema cụ thể. `counts` cũng có thể chứa các giá trị JDBC như `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED`, không thể dùng làm ID.

### Làm thế nào ánh xạ khóa về input an toàn?

Nếu cần một ánh xạ chắc chắn giữa input row và generated row:

- Khi có thể, xử lý **mỗi INSERT riêng** (trong transaction) và lấy key ngay sau lệnh tương ứng. Đây là cách đơn giản, tuy có thể ít hiệu quả hơn batch.
- Hoặc dùng một **correlation token**/business key duy nhất do ứng dụng sinh và đưa nó vào mỗi row; truy vấn kết quả trả **cả token và generated key** qua cơ chế phù hợp dialect, rồi ghép theo token.
- Với PostgreSQL, `RETURNING` trả được các cột do row mang, nhưng vẫn không nên suy ra một thứ tự cố định nếu không có hợp đồng rõ. Correlation theo token sẽ đáng tin hơn dựa vào thứ tự.
- Nếu driver có cam kết documented về thứ tự và số lượng keys trong một thao tác cụ thể, có thể dùng cam kết đó và bảo vệ bằng integration test khi nâng cấp driver.

**Không tự suy** rằng ba ID lần lượt là 301, 302, 303 chỉ từ một lần chèn. Sequence/identity có thể có lỗ, nhảy giá trị, xảy ra cạnh tranh hoặc rollback; tính liên tiếp không phải hợp đồng generated key.

## 13. Một composite primary key có thể không có cột nào tự sinh

Không phải khóa chính ghép nào cũng cần gọi `getGeneratedKeys()`. Ví dụ:

~~~sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

Nếu Java đã có `studentId` và `courseId`, thì toàn bộ khóa đã biết trước INSERT. Chỉ cần bind và thực thi:

~~~java
String sql = """
        INSERT INTO enrollment (student_id, course_id, enrolled_at)
        VALUES (:studentId, :courseId, :enrolledAt)
        """;
var params = new MapSqlParameterSource()
        .addValue("studentId", studentId)
        .addValue("courseId", courseId)
        .addValue("enrolledAt", enrolledAt);
int affected = namedJdbc.update(sql, params);
~~~

**Không dùng generated-key API chỉ vì khóa chính có nhiều cột.** Cần phân biệt “composite” (nhiều trường tham gia identity) với “generated” (database tạo giá trị nào). Một record `EnrollmentKey(studentId, courseId)` có thể được tạo trực tiếp từ hai giá trị đầu vào đã biết.

Nếu doanh nghiệp muốn khóa ghép có thành phần thứ tự **riêng trong một tenant**, không nên tính `MAX(shipment_no)+1` rồi chèn: nhiều transaction chạy song song có thể cùng nhìn thấy MAX cũ. Hãy sử dụng sequence/counter được đồng bộ đúng, constraint unique và transaction isolation/locking phù hợp theo database.

## 14. Các kiểu khóa sinh khác số nguyên

`getKey()` được thiết kế cho **một giá trị numeric**. Trong hệ thống hiện đại, generated identifier có thể là:

- BIGINT/INTEGER identity hoặc sequence → có thể ánh xạ về `Long`, `Integer`, `BigDecimal` hoặc kiểu `Number` khác.
- UUID do database sinh → có thể là `UUID`, `String` hay đối tượng driver-specific.
- String code hoặc token được trigger/procedure sinh → thường cần đọc bằng kiểu/string mapping phù hợp.
- Giá trị composite → cần record/DTO gồm nhiều thành phần, không nhét vào một `Long`.

### Kiểm tra kiểu/range thay vì ép `(Long) getKey()`

Chống ví dụ:

~~~java
Long id = (Long) keyHolder.getKey();
~~~

Nếu driver trả `BigDecimal` dù giá trị là số nguyên, cast sẽ ném `ClassCastException`. Hướng đúng hơn với numeric id:

~~~java
Number raw = keyHolder.getKey();
if (raw == null) {
    throw new IllegalStateException("No generated numeric key");
}
long id = raw.longValue();
~~~

Giải pháp này tránh cast cụ thể, nhưng vẫn cần **kiểm tra range/precision** nếu database có thể cấp số ngoài phạm vi Java long. Với `BigDecimal`:

~~~java
BigDecimal raw = (BigDecimal) value;
long exact = raw.longValueExact();
~~~

Đây là minh họa khi *đã xác minh* runtime type của `value` là `BigDecimal`. `longValueExact()` ném `ArithmeticException` nếu có phần lẻ hoặc vượt phạm vi, tốt hơn âm thầm làm tròn/cắt. Với `BigInteger` có phương thức `longValueExact()` tương ứng.

### UUID sinh tại Java thì không cần hỏi database sinh ID

Nếu ứng dụng có quyền chọn ID trước khi chèn:

~~~java
UUID id = UUID.randomUUID();
String sql = "INSERT INTO document (id, title) VALUES (:id, :title)";
var params = new MapSqlParameterSource()
        .addValue("id", id)
        .addValue("title", title);
namedJdbc.update(sql, params);
~~~

Đây là **app-generated key**, không phải database-generated key. Bạn đã có `id` từ trước INSERT; không cần `getGeneratedKeys()` chỉ để lấy lại nó. Database vẫn phải có constraint để bảo vệ tính duy nhất và kiểm tra kiểu mapping UUID cho dialect/driver thực tế.

## 15. Transactions: lấy được key không đồng nghĩa dữ liệu đã commit

JDBC generated keys thường được đọc sau khi chạy một statement thành công nhưng **trước khi transaction được commit** (nếu transaction đang mở). Ví dụ:

~~~text
BEGIN TRANSACTION
    INSERT shipment -> nhận shipment_no = 301
    INSERT shipment_item trỏ tới (tenant_id=7, shipment_no=301)
    ...
ROLLBACK (do một lỗi nghiệp vụ)
~~~

Ứng dụng có thể từng nhận giá trị `301`, nhưng hàng không còn tồn tại sau rollback. Vì thế:

- Không công bố “đã lưu vĩnh viễn” chỉ vì `getGeneratedKeys()` có dữ liệu.
- Không dùng số identity/sequence để suy ra số hàng đã commit hay khoảng liên tục.
- Không tự làm `SELECT MAX(id)` sau insert để xác định khóa: giao dịch đồng thời và việc nhiều connection có thể tạo kết quả sai.
- Khi tạo parent/child trong cùng nghiệp vụ, dùng khóa vừa nhận **trong cùng transaction** để viết child, rồi commit/rollback toàn bộ bằng transaction manager phù hợp.
- Sự kiện gửi ra ngoài hệ thống trước commit có thể khiến consumer nhìn thấy ID của row bị rollback; sử dụng outbox hoặc cơ chế sự kiện sau commit khi cần tính nhất quán.

Trong Spring, dùng `@Transactional` với transaction manager đúng DataSource. Không tự mở connection khác một cách vô ý rồi nghĩ mọi update cùng một transaction.

## 16. Lỗi thường gặp khi đọc nhiều khóa sinh

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| `getKey()` cho Map có hai cột | API chỉ chấp nhận đúng một key | Dùng `getKeys()` và đọc từng cột theo tên |
| `getKeys()` khi có nhiều rows | API chỉ dành cho một row | Dùng `getKeyList()` |
| Chỉ `rs.next()` một lần khi batch tạo nhiều keys | Bỏ qua các hàng còn lại | Lặp `while(rs.next())` |
| `rs.getLong(1)` với result set nhiều cột và không kiểm tra metadata | Không biết cột 1 là gì | Chỉ định cột, kiểm tra metadata và đọc theo label |
| `(Long) holder.getKey()` | Driver có thể trả kiểu Number khác | Đọc `Number`, validate range/precision |
| Composite key có hai cột nhưng chỉ giữ generated identity | Mất thành phần identity còn lại | Tạo record chứa cả hai, ghép phần đã biết với phần DB sinh |
| Tưởng `RETURN_GENERATED_KEYS` luôn trả mọi default column | Driver quyết định nếu không chỉ rõ | Yêu cầu keyColumnNames hoặc `RETURNING` đặc thù |
| Tưởng `affected == generatedId` | Update count là số hàng, không phải key | Đọc `getGeneratedKeys()`/`KeyHolder` |
| Batch index i ↔ returned key row i không được xác nhận | Không có cam kết portable về thứ tự | Correlation token hoặc insert từng row |
| `MAX(id)+1` để tự sinh ID | Race condition/concurrency | Dùng identity/sequence và unique constraints |
| Key đã đọc nghĩa là row đã commit | Transaction có thể rollback | Quản lý transaction, xác nhận commit |
| Map key name khác chữ hoa/thường | JDBC driver có thể đổi labels | Inspect metadata/keySet, test cùng driver |
| `getGeneratedKeys()` rỗng nhưng bỏ qua | Không có key để tạo domain identity | Fail rõ hoặc dùng phương án trả về khác |
| Không đóng ResultSet/Statement/Connection | Rò rỉ resource/pool | `try-with-resources` hoặc Spring JDBC resource management |

### Phân biệt lỗi không hỗ trợ và lỗi không có khóa

Một `ResultSet` rỗng có thể có nghĩa statement không sinh key, không có hàng thực sự được chèn, hoặc cơ chế driver không trả key trong tình huống đó. Còn `SQLFeatureNotSupportedException`/lỗi JDBC liên quan thường chỉ việc driver không thực hiện khả năng yêu cầu. Đừng trả ID 0 trong cả hai trường hợp; hãy ghi nhận SQL template, update count, driver, schema, cách prepare statement và contract.

## 17. Quy trình chẩn đoán khi KeyHolder bất ngờ có nhiều khóa

Giả sử code cũ:

~~~java
Number id = holder.getKey();
~~~

bắt đầu ném `InvalidDataAccessApiUsageException` sau khi đổi JDBC driver hoặc schema.

Hãy làm theo các bước:

1. Xác nhận câu SQL thực sự chèn **một hay nhiều hàng**, và có dùng batch/trigger/dialect extension hay không.
2. Xác nhận đã yêu cầu `RETURN_GENERATED_KEYS` hay `keyColumnNames` nào.
3. Kiểm tra `holder.getKeyList().size()` (số hàng) và số key columns trong từng Map ở **môi trường test có bảo mật**. Không log raw dữ liệu nhạy cảm.
4. So sánh với hợp đồng: chỉ cần một ID numeric, cần composite key, cần metadata default, hay cần nhiều IDs?
5. Nếu một hàng nhiều cột, chuyển sang `getKeys()` và ánh xạ theo tên; nếu nhiều hàng, dùng `getKeyList()`.
6. Kiểm tra runtime type và label của từng giá trị; đừng ép cast Long hoặc giả định tên cột.
7. Tái kiểm tra transaction và cách gắn kết với input rows; với batch, không tự ghép bằng thứ tự nếu driver không cam kết.
8. Nếu driver không hỗ trợ ổn định, cân nhắc `RETURNING/OUTPUT` theo dialect hoặc phát sinh ID tại ứng dụng.

Một câu hỏi hiệu quả khi review: **Kết quả gồm bao nhiêu hàng? Mỗi hàng có bao nhiêu cột? Cột nào thật sự cấu thành khóa nghiệp vụ?** Trả lời đủ ba câu thường dẫn ngay đến API đúng.

## 18. Kiểm thử các hình dạng kết quả

Thiết lập integration test trên database/driver mà project dùng và xác minh:

| Ca | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| Một hàng × một numeric key | INSERT một shipment, yêu cầu `shipment_no` | Một value numeric có phạm vi đúng |
| Một hàng × nhiều cột | Driver hỗ trợ trả `shipment_no` và `created_at` | Một Map có đủ cột/kiểu theo contract |
| Composite key một phần biết sẵn | Tenant ID từ request context, shipment_no DB sinh | Record có đúng cả tenantId và shipmentNo |
| Composite key hoàn toàn cung cấp trước | Enrollment (student_id, course_id) | Không cần generated keys |
| Nhiều hàng batch | Hai hoặc nhiều INSERT trong batch | Kiểm tra driver trả mấy rows, labels, thứ tự/association |
| Không có generated key | Driver/schema không sinh hoặc không trả | Xử lý rỗng có chủ ý, không giả ID=0 |
| Key UUID/String | DB sinh nonnumeric ID nếu hỗ trợ | Đọc type đúng, không gọi numeric getKey |
| Metadata khác label dự kiến | Driver trả alias/case khác | Code không tráo cột im lặng |
| Rollback sau lấy key | Chèn trong transaction, nhận key rồi rollback | Hàng không tồn tại sau rollback |
| Concurrent inserts | Nhiều transaction insert song song | Không xác định ID bằng MAX/id+1; khóa thực sự unique |
| Nâng driver | So sánh generated-key metadata giữa versions | Thấy nếu shape, labels, types thay đổi |

Trong unit test Java 17, có thể test riêng mapper của `List<Map<...>>` như `GeneratedKeysShapeDemo` ở phần 8. Nhưng **test đó không xác minh driver**: vẫn cần integration test với schema và database thực tế.

### Gợi ý assertions

- Với một key numeric: `assertEquals(1, keyRows.size())` và `assertEquals(1, keyRows.get(0).size())` trước chuyển đổi.
- Với một row nhiều cột: assert Map có các key column labels mong đợi, type/nullability hợp lệ.
- Với nhiều rows: assert số rows **chỉ khi driver đã có contract rõ**; kiểm tra correlation nếu phải ghép về input.
- Với rollback: query theo composite key sau khi transaction rollback phải không thấy row, thay vì tin ID trong biến Java.
- Không assert identity sequence luôn liên tiếp hoặc luôn không có lỗ.

## 19. Checklist lựa chọn chiến lược

Trước khi viết repository lưu một đối tượng:

1. **Khóa định danh có bao nhiêu thành phần?** Nếu composite, xác định từng thành phần.
2. **Thành phần nào do ứng dụng cung cấp, thành phần nào do DB sinh?**
3. **Một lần gọi có thể chèn bao nhiêu rows?** Nếu nhiều, dự kiến hình dạng generated result nào?
4. **Driver/database có hỗ trợ `getGeneratedKeys()` và yêu cầu `keyColumnNames` không?**
5. **Result có cần thêm giá trị default/trigger ngoài PK không?** Nếu có, `RETURNING/OUTPUT` có phù hợp hơn không?
6. **Kết quả là số, UUID hay chuỗi?** Kiểm tra runtime mapping trước khi chuyển kiểu.
7. **Có phải ánh xạ ID về từng input trong batch không?** Nếu có, cần correlation đáng tin.
8. **Có transaction nhiều bước phụ thuộc khóa vừa sinh không?** Đảm bảo cùng transaction/connection context.
9. **API có kiểm tra 0/1/nhiều rows và columns không?** Không âm thầm lấy first.
10. **Có integration test theo JDBC driver và schema đang triển khai không?**

Với trường hợp đơn giản, `getKey()` rất tiện. Với trường hợp phức tạp, **giữ đúng cấu trúc dữ liệu** rồi map thành record domain thường bền vững hơn cố ép mọi thứ về một `Long`.

## 20. Câu hỏi ôn tập

**Câu 1.** Bảng có primary key `(tenant_id, shipment_no)`; chỉ `shipment_no` tự sinh. Có cần DB trả cả hai cột qua `getGeneratedKeys()` không?  
**Đáp án:** Không bắt buộc. Ứng dụng đã biết tenantId, có thể chỉ yêu cầu shipmentNo rồi tạo record chứa cả hai. Hoặc dùng `RETURNING` để trả đầy đủ nếu phù hợp DB.

**Câu 2.** `KeyHolder.getKey()` có dùng được khi result chứa một row và hai cột không?  
**Đáp án:** Không. Contract yêu cầu một row × một key numeric; khi nhiều cột, sử dụng `getKeys()` hoặc `getKeyList()`.

**Câu 3.** Với KeyHolder có ba row, mỗi row một cột, nên gọi gì?  
**Đáp án:** `getKeyList()` và xử lý từng Map theo thứ tự/association đã được driver/test xác minh.

**Câu 4.** `executeUpdate()` trả 1. Giá trị khóa sinh của hàng có bắt buộc bằng 1 không?  
**Đáp án:** Không. Số 1 thường là update count, không phải generated ID.

**Câu 5.** Dùng `Statement.RETURN_GENERATED_KEYS` nhưng không chỉ tên cột; có chắc nhận đủ mọi cột default không?  
**Đáp án:** Không. Driver quyết định cột phù hợp; chỉ định key columns nếu được hỗ trợ hoặc dùng SQL RETURNING theo dialect.

**Câu 6.** Lấy được `shipment_no=301` rồi transaction rollback. Hàng vừa INSERT còn tồn tại không?  
**Đáp án:** Không, nếu transaction thực sự rollback thành công. Có ID trong Java không có nghĩa dữ liệu đã commit.

**Câu 7.** Driver trả `BigDecimal` cho ID trong DB, `(Long)holder.getKey()` có an toàn không?  
**Đáp án:** Không. Dùng `Number` và chuyển đổi có kiểm tra range/precision; cast trực tiếp có thể ném ClassCastException.

**Câu 8.** Một batch chèn 3 rows, getKeyList chứa 3 rows. Có thể luôn ghép theo vị trí 0,1,2 với input không?  
**Đáp án:** Không có cam kết portable. Phải có contract cụ thể của driver hoặc correlation token; nếu không, insert từng row.

**Câu 9.** Một bảng có composite PK do caller biết cả hai thành phần. Có cần `getGeneratedKeys()`?  
**Đáp án:** Không. Các thành phần đã có trước INSERT; chỉ cần ghi đúng khóa và constraint.

**Câu 10.** Vì sao `getColumnLabel(1)` và `getObject(1)` cần đặt trong vòng lặp cột từ 1?  
**Đáp án:** Chỉ số cột JDBC bắt đầu từ 1; đọc theo metadata của result set giúp xác định mọi cột được driver trả.

## 21. Tổng kết

**Generated keys là kết quả dạng bảng, không mặc nhiên là một số đơn.** Một ứng dụng tốt xác định rõ số hàng × số cột được trả, những thành phần khóa đã biết, thành phần cần database sinh và contract của JDBC driver.

- Dùng `Statement.getGeneratedKeys()` với `ResultSet.next()`, `ResultSetMetaData` để đọc đủ nhiều hàng/cột khi cần.
- Dùng `KeyHolder.getKey()` chỉ cho **một numeric key**, `getKeyAs(...)` cho một key có kiểu phù hợp, `getKeys()` cho **một row nhiều columns**, `getKeyList()` cho **nhiều rows**.
- Dùng key column names nếu driver hỗ trợ; chọn `RETURNING/OUTPUT` khi cần một tập cột được trả có chủ đích và hệ quản trị cung cấp.
- Với composite key, ghép đúng các trường theo **tên và ý nghĩa**, không theo thứ tự Map.
- Với batch và transactions, cẩn trọng về correlation, rollback, driver support và sequence gaps.

### Tài liệu tham khảo chính thức

- [Java SE 17 — Statement#getGeneratedKeys](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): kết quả dạng ResultSet và hành vi khi không có generated keys.
- [Java SE 17 — Connection#prepareStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): các overload `RETURN_GENERATED_KEYS` và `columnNames`.
- [Java SE 17 — ResultSet & ResultSetMetaData](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSetMetaData.html): số lượng, nhãn và type cột trong result set.
- [Spring Framework — KeyHolder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/KeyHolder.html): `getKey`, `getKeyAs`, `getKeys`, `getKeyList`.
- [Spring Framework — GeneratedKeyHolder JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/GeneratedKeyHolder.html): implementation thông dụng của KeyHolder.
- [Spring Framework — NamedParameterJdbcTemplate JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): `update(..., KeyHolder, keyColumnNames)` và `batchUpdate(..., KeyHolder, keyColumnNames)`.
- [Spring Framework — SimpleJdbcInsert JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcInsert.html): API hỗ trợ khai báo generated-key columns ở mức insert abstraction.
- [PostgreSQL — Returning Data from Modified Rows](https://www.postgresql.org/docs/current/dml-returning.html): `INSERT ... RETURNING` và biểu thức returned columns.
- [Microsoft SQL Server — OUTPUT Clause](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql): lấy cột từ hàng bị ảnh hưởng trong SQL Server.