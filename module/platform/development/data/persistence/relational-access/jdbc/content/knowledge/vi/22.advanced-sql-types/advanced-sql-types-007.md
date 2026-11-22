# Xử lý UUID, JSON và các kiểu riêng qua cơ chế của driver trong JDBC

Trong chương **Kiểu SQL nâng cao**, ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua JDBC có thể gặp những cột không ánh xạ đơn giản thành `String`, `long` hoặc `BigDecimal`: khóa kiểu UUID, tài liệu JSON/JSONB, enum, kiểu địa lý, kiểu do người dùng tự định nghĩa (*user-defined type*) và các kiểu riêng của hệ quản trị. Chúng thường rất tiện trong SQL nhưng cũng dễ làm giảm **tính khả chuyển** giữa các cơ sở dữ liệu.

Ví dụ, PostgreSQL có kiểu `uuid` và `jsonb`; một hệ quản trị khác có thể lưu UUID bằng `CHAR(36)` hoặc `BINARY(16)`, còn JSON được lưu bằng một kiểu JSON riêng hoặc kiểu văn bản có kiểm tra hợp lệ. Cùng một lệnh `PreparedStatement.setObject(...)` không nhất thiết hoạt động giống nhau trên các driver. Nắm được **kiểu SQL thực**, **kiểu Java**, **kiểu mà driver nhận/trả** và **cơ chế ép kiểu** là điều kiện để CRUD hoạt động đúng.

Bài này hướng dẫn làm việc với `java.util.UUID` và JSON, nhận diện `Types.OTHER`, dùng `setObject`/`getObject`, ép kiểu SQL có chủ đích, sử dụng đối tượng riêng của driver khi cần và thiết kế đường tương thích qua `DataSource`, `PreparedStatement`, `ResultSet` và transaction.

## 1. Vì sao UUID, JSON và kiểu riêng cần chú ý?

JDBC chuẩn hóa nhiều kiểu SQL thông qua `java.sql.Types` hoặc `JDBCType`, nhưng không thể áp đặt một biểu diễn Java duy nhất cho mọi kiểu do DB bổ sung.

| Dữ liệu | Biểu diễn Java thường dùng | Biểu diễn SQL có thể gặp | Lưu ý khi dùng JDBC |
| --- | --- | --- | --- |
| UUID | `java.util.UUID`, hoặc chuỗi chuẩn | PostgreSQL `uuid`; SQL Server `uniqueidentifier`; `CHAR(36)`/`BINARY(16)` | Hỗ trợ `setObject(UUID)`/`getObject(UUID.class)` tùy driver |
| Tài liệu JSON | Chuỗi JSON, cây đối tượng đã parse, DTO | PostgreSQL `json`/`jsonb`; MySQL `JSON`; kiểu văn bản hoặc JSON riêng | Có thể cần CAST trong SQL hoặc đối tượng driver để xác định kiểu |
| Enum SQL | `String`/Java enum | Kiểu enum của DB hoặc `VARCHAR` có ràng buộc | Không giả định `setObject(JavaEnum)` hoạt động |
| Mảng SQL | `java.sql.Array` | `ARRAY` hoặc mảng riêng của DB | Có `createArrayOf` nhưng việc hỗ trợ phần tử/kiểu phụ thuộc DB |
| Kiểu tự định nghĩa/địa lý | Class riêng của thư viện hoặc dạng text/binary chuẩn | UDT, geometry, hstore, v.v. | Thường cần API driver, converter hoặc cú pháp SQL đặc thù |

`Types.OTHER` là mã JDBC thường xuất hiện khi driver gặp kiểu SQL không có ánh xạ chuẩn tương ứng. **`Types.OTHER` không cho biết đó là UUID, JSON hay một kiểu nào cụ thể**: phải xem thêm tên kiểu do DB cung cấp và tài liệu driver.

> **Nguyên tắc:** Chọn kiểu Java dựa trên ý nghĩa dữ liệu, đồng thời xác minh hợp đồng chuyển đổi giữa ứng dụng, driver và loại cột SQL thật. Đừng chỉ thử ép `Object` rồi suy ra rằng mọi driver đều xử lý như nhau.

## 2. UUID: phân biệt kiểu UUID gốc với chuỗi và nhị phân

UUID là định danh 128 bit, thường được hiển thị ở dạng 36 ký tự có dấu gạch nối, ví dụ `550e8400-e29b-41d4-a716-446655440000`. Java biểu diễn bằng `java.util.UUID`:

```java
import java.util.UUID;

UUID id = UUID.fromString("550e8400-e29b-41d4-a716-446655440000");
String canonical = id.toString();

System.out.println(canonical);
// 550e8400-e29b-41d4-a716-446655440000
```

Ứng dụng cần **nhất quán kiểu lưu trữ**:

- **Cột UUID gốc:** DB hiểu đây là UUID; có thể kiểm tra giá trị, so sánh và lập chỉ mục bằng chức năng riêng. Cách bind phổ biến là `setObject(index, uuid)` nếu driver có hỗ trợ.
- **`CHAR(36)` hoặc `VARCHAR(36)`:** bind/read dưới dạng chuỗi chuẩn. Dễ chuyển giữa DB nhưng sử dụng nhiều không gian hơn dạng nhị phân và tính đúng đắn cần ràng buộc/kiểm tra.
- **`BINARY(16)`:** gọn hơn kiểu chuỗi, nhưng phải thống nhất quy ước chuyển 128 bit thành 16 byte, thứ tự byte và cách đọc lại. Không giả định các hệ quản trị dùng một thứ tự byte như nhau.

Đoạn mã sau phù hợp với **cột chuỗi** đã được chọn theo thiết kế:

```java
String insertSql = "INSERT INTO external_request (id) VALUES (?)";
try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setString(1, id.toString()); // Cột id là CHAR/VARCHAR thích hợp.
    ps.executeUpdate();
}

String selectSql = "SELECT id FROM external_request WHERE id = ?";
try (PreparedStatement ps = connection.prepareStatement(selectSql)) {
    ps.setString(1, id.toString());
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            UUID loaded = UUID.fromString(rs.getString("id"));
            System.out.println(loaded.equals(id));
        }
    }
}
```

Đây là đoạn minh họa dùng `connection` còn mở và các import JDBC tương ứng. **Không dùng `setString(...)` lên cột UUID gốc với giả định mọi DB/driver đều ngầm chuyển chuỗi thành UUID.** Nếu driver không tự chuyển, cần cách ép kiểu SQL hoặc cơ chế do driver hỗ trợ.

### Bind UUID vào cột UUID gốc

Với PostgreSQL JDBC, cách dùng phổ biến là:

```java
UUID id = UUID.randomUUID();

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO app_event (id, payload) VALUES (?, CAST(? AS jsonb))")) {
    ps.setObject(1, id);  // PostgreSQL JDBC nhận UUID cho cột uuid.
    ps.setString(2, "{\"event\":\"created\"}");
    ps.executeUpdate();
}
```

Với driver hỗ trợ đọc có kiểu đích, có thể dùng `resultSet.getObject("id", UUID.class)`. Trong tình huống driver chỉ trả chuỗi, thử `UUID.fromString(resultSet.getString("id"))` sau khi xác minh định dạng. `getObject(index, Class<T>)` là API JDBC chuẩn, **nhưng khả năng chuyển đổi một kiểu riêng của DB sang `UUID` là do driver triển khai**.

## 3. JSON: một cấu trúc dữ liệu, nhiều kiểu SQL

JSON là định dạng trao đổi dữ liệu gồm object, array, string, number, boolean và `null`. Việc có chuỗi JSON hợp lệ trong Java **không đồng nghĩa** driver biết tham số `?` nên là kiểu JSON của DB.

Một số cách lưu thông dụng:

| Lựa chọn | Ưu điểm | Đổi lại |
| --- | --- | --- |
| Kiểu JSON/JSONB gốc của DB | DB có thể xác thực JSON, hỗ trợ toán tử, index và truy vấn theo đường dẫn | SQL và mapping JDBC khác nhau giữa sản phẩm |
| `VARCHAR`/`TEXT`/`CLOB` | Dễ bind bằng `setString`/`setCharacterStream` | DB có thể không kiểm tra JSON hoặc hỗ trợ truy vấn JSON đầy đủ |
| Bảng quan hệ chuẩn hóa | Ràng buộc dữ liệu và join rõ ràng | Cần schema và phép join cho từng thuộc tính |

Ví dụ PostgreSQL:

```sql
-- Cú pháp và hai kiểu uuid/jsonb thuộc PostgreSQL.
CREATE TABLE app_event (
    id         uuid PRIMARY KEY,
    payload    jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`jsonb` lưu dạng biểu diễn nhị phân đã xử lý của PostgreSQL, không nhất thiết giữ nguyên khoảng trắng hoặc thứ tự khóa của văn bản đầu vào. `json` và `jsonb` có đặc tính khác nhau về lưu trữ, xử lý khóa trùng, toán tử và lập chỉ mục. **Không dùng so sánh nguyên chuỗi JSON sau khi đọc lại như một phép kiểm tra nội dung tương đương.** Nếu ứng dụng yêu cầu giữ nguyên byte của tài liệu gốc, cần lưu byte gốc bằng kiểu nhị phân hoặc tách thêm cột chứa bản gốc.

### Cách A: ép kiểu SQL tại nơi sử dụng tham số

Ví dụ với PostgreSQL, có thể giữ Java không phụ thuộc vào class driver bằng cách ép kiểu trong SQL:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;

public static void insertEvent(Connection connection, UUID id, String json)
        throws SQLException {
    String sql = """
            INSERT INTO app_event (id, payload)
            VALUES (CAST(? AS uuid), CAST(? AS jsonb))
            """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, id.toString());
        ps.setString(2, json);
        if (ps.executeUpdate() != 1) {
            throw new SQLException("Không ghi được đúng một sự kiện");
        }
    }
}
```

`CAST(? AS uuid)` và `CAST(? AS jsonb)` là cú pháp SQL được **PostgreSQL** hiểu; driver bind tham số ở dạng chuỗi rồi máy chủ chuyển sang kiểu đích. Nếu `json` không hợp lệ, DB có thể ném `SQLException`. **PreparedStatement vẫn tham số hóa giá trị**, kể cả khi dùng `CAST`; không ghép nội dung JSON vào chuỗi SQL.

Ưu điểm là giữ dependency Java ở JDBC chuẩn. Điểm đánh đổi là SQL phụ thuộc DB, phải thay cho hệ quản trị khác. Cũng không nên suy ra rằng ép kiểu trên máy chủ không có chi phí.

### Cách B: đối tượng kiểu riêng của PostgreSQL JDBC

Driver PostgreSQL cung cấp `org.postgresql.util.PGobject` để mang **tên kiểu PostgreSQL và giá trị biểu diễn dạng chuỗi**. Ví dụ với kiểu `jsonb`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import org.postgresql.util.PGobject; // Phụ thuộc pgjdbc, không thuộc JDK.

public static void insertWithPgObject(
        Connection connection, UUID id, String json) throws SQLException {
    PGobject payload = new PGobject();
    payload.setType("jsonb");
    payload.setValue(json);

    String sql = "INSERT INTO app_event (id, payload) VALUES (?, ?)";
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setObject(1, id);
        ps.setObject(2, payload);
        ps.executeUpdate();
    }
}
```

`PGobject` là **API riêng của driver PostgreSQL** và yêu cầu dependency `org.postgresql:postgresql` trong dự án. Nó không tồn tại trong JDBC chuẩn và không nên xuất hiện trong phần nghiệp vụ cần hỗ trợ nhiều DB nếu không có lớp adapter. `PGobject.setValue(json)` không thay thế việc kiểm tra schema JSON ở tầng ứng dụng: DB có thể xác thực cú pháp JSON nhưng không tự biết thuộc tính `event` có bắt buộc hay không.

### Tránh nhầm truyền chuỗi là truyền JSON

`ps.setString(index, json)` thường hoạt động với cột `TEXT`; với cột `jsonb`, driver có thể gửi tham số ở kiểu `VARCHAR` khiến PostgreSQL từ chối biểu thức gán không có phép chuyển đổi tương ứng. Đây là lý do cần `CAST(? AS jsonb)` hoặc đối tượng kiểu riêng ở các cấu hình đó.

Ở MySQL và những DB khác, kiểu JSON và quy tắc chuyển đổi chuỗi thành JSON có thể khác. **Không sao chép nguyên `PGobject` hoặc `CAST(? AS jsonb)`** sang DB khác. Hãy kiểm tra phép bind cần thiết qua driver đích, SQL mẫu và kiểu cột thực tế.

## 4. Ví dụ repository hoàn chỉnh với PostgreSQL `uuid` và `jsonb`

Ví dụ sau gom việc ghi và đọc JSON vào một repository. Mọi giá trị do caller đưa vào được bind qua tham số; kết nối lấy từ `DataSource` và đóng bằng `try-with-resources`:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import javax.sql.DataSource;
import org.postgresql.util.PGobject;

public final class PgEventRepository {
    private final DataSource dataSource;

    public PgEventRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record EventData(UUID id, String jsonPayload) {}

    public void insert(UUID id, String jsonPayload) throws SQLException {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(jsonPayload, "jsonPayload");

        PGobject jsonb = new PGobject();
        jsonb.setType("jsonb");
        jsonb.setValue(jsonPayload);

        String sql = "INSERT INTO app_event (id, payload) VALUES (?, ?)";
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, id);
            ps.setObject(2, jsonb);

            int updated = ps.executeUpdate();
            if (updated != 1) {
                throw new SQLException(
                        "INSERT cần ảnh hưởng một dòng, thực tế: " + updated);
            }
        }
    }

    public Optional<EventData> findById(UUID id) throws SQLException {
        Objects.requireNonNull(id, "id");
        String sql = "SELECT id, payload FROM app_event WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setObject(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                UUID actualId = rs.getObject("id", UUID.class);
                String json = rs.getString("payload");
                return Optional.of(new EventData(actualId, json));
            }
        }
    }
}
```

Ví dụ dùng `record` (Java 16+) và driver PostgreSQL có hỗ trợ binding UUID cùng `getObject(..., UUID.class)`; nếu dự án dùng Java cũ hơn có thể thay `record` bằng class thông thường. Để dùng thử:

```java
UUID id = UUID.randomUUID();
String payload = "{\"action\":\"purchase\",\"amount\":12500}";

PgEventRepository repository = new PgEventRepository(dataSource);
repository.insert(id, payload);

PgEventRepository.EventData loaded =
        repository.findById(id).orElseThrow();
System.out.println(loaded.id().equals(id)); // true
System.out.println(loaded.jsonPayload());
```

Trong ví dụ, `payload` bắt buộc không phải SQL `NULL` theo schema và được PostgreSQL xác thực cú pháp khi ghi. Nếu cần ràng buộc thuộc tính `action`, kiểu `amount`, giới hạn kích thước hoặc cấu trúc chi tiết, phải dùng bộ phân tích JSON/JSON Schema ở tầng ứng dụng hoặc ràng buộc DB thích hợp.

**Phạm vi transaction:** Repository minh họa các thao tác CRUD riêng lẻ. Khi một nghiệp vụ phải tạo `app_event` và cập nhật nhiều bảng cùng lúc, tầng sở hữu transaction cần dùng **cùng một `Connection`**, bật quản lý transaction phù hợp, `commit` khi toàn bộ bước thành công và `rollback` khi lỗi. Không thể đạt tính nguyên tử nhiều bước bằng cách gọi nhiều phương thức mỗi phương thức tự mượn một kết nối.

## 5. Đọc JSON và UUID từ `ResultSet` một cách có kiểm chứng

### Các cách đọc JSON

Với PostgreSQL JDBC, có thể đọc văn bản JSON bằng `getString("payload")`. Một cách khác là `getObject("payload")`, kết quả có thể là `PGobject` đối với kiểu riêng, tùy driver và cấu hình.

```java
String jsonText = rs.getString("payload");

Object nativeValue = rs.getObject("payload");
if (nativeValue instanceof PGobject) {
    PGobject pg = (PGobject) nativeValue;
    System.out.println("SQL type: " + pg.getType());
    System.out.println("Value: " + pg.getValue());
} else if (nativeValue != null) {
    System.out.println("Driver Java class: "
            + nativeValue.getClass().getName());
}
```

Đoạn mã giả định `rs` đang ở hàng hiện tại và `PGobject` đã được import. Đây là minh họa về **đọc giá trị native**, không phải bảo đảm mọi driver đều trả đối tượng kiểu đó. Khi cần một cấu trúc Java để kiểm tra nghiệp vụ, hãy parse chuỗi JSON bằng thư viện chuyên dụng đã chọn và kiểm tra schema; **JDK/JDBC không cung cấp một ánh xạ JSON → DTO phổ quát qua `getObject(...)`**.

Không nên so sánh JSON chỉ bằng `String.equals(...)` để xác định tương đương ngữ nghĩa. Cùng một object có thể được viết theo thứ tự khóa hoặc khoảng trắng khác nhau; `jsonb` còn chuẩn hóa biểu diễn. Nếu nghiệp vụ cần so sánh JSON, hãy dùng parser hoặc cơ chế so sánh JSON của DB với quy tắc đã biết.

### Phân biệt SQL `NULL` và JSON literal `null`

Đây là hai trạng thái khác nhau:

| Giá trị cột | `getString(...)` thường trả | Ý nghĩa |
| --- | --- | --- |
| SQL `NULL` | Java `null` | Không có giá trị SQL |
| JSON literal `null` | Chuỗi `"null"` | Có một giá trị JSON, mang kiểu null |
| JSON chuỗi `"null"` | Chuỗi có dấu nháy JSON: `"\"null\""` | Giá trị JSON kiểu string, nội dung là từ `null` |

`getString(...) == null` là cách kiểm tra SQL `NULL`, còn chuỗi `"null"` cần được parse theo JSON nếu nghiệp vụ quan tâm. Với `getObject(...)`, kết quả và class có thể phụ thuộc driver. Với getter nguyên thủy, dùng `ResultSet.wasNull()` ngay sau getter để phân biệt SQL `NULL` với giá trị mặc định.

### Cẩn thận với số trong JSON

Các số trong JSON không nhất thiết ánh xạ an toàn vào `double`. Ví dụ một ID rất lớn hoặc số tiền có nhiều chữ số có thể bị mất chính xác khi thư viện JSON tự chuyển thành số dấu phẩy động nhị phân. Nếu nghiệp vụ yêu cầu chính xác, cấu hình parser dùng `BigDecimal`/`BigInteger` ở những trường phù hợp và làm rõ quy tắc lưu trữ, so sánh cũng như làm tròn.

## 6. `Types.OTHER` và cơ chế kiểu riêng trong JDBC

Khi đối tượng hoặc kiểu cột không có ánh xạ SQL chuẩn, ứng dụng thường gặp các lời gọi:

```java
import java.sql.Types;

// Có thể hỗ trợ trên một số driver cho kiểu riêng.
ps.setObject(1, value, Types.OTHER);

// Với giá trị SQL NULL, kiểu gốc có thể cần được xác định rõ:
ps.setNull(1, Types.OTHER, "jsonb");
```

Đây là **mẫu API**, không phải mã khẳng định hai lời gọi trên chạy với mọi DB. `Types.OTHER` không mang đủ thông tin rằng giá trị là `jsonb` hay một UDT cụ thể; một số driver cần đối tượng riêng, tên kiểu SQL, hoặc `CAST` trong SQL.

Một số API liên quan đến kiểu nâng cao:

- `setObject(index, value)`: để driver suy luận kiểu của đối tượng Java.
- `setObject(index, value, targetSqlType)`: đưa ra mã kiểu JDBC đích, nhưng driver vẫn quyết định cách chuyển đổi.
- `setNull(index, sqlType, typeName)`: truyền kiểu SQL gốc để biểu thị `NULL` cho một số UDT/kiểu riêng khi driver hỗ trợ.
- `Connection.createArrayOf(typeName, elements)`: tạo `java.sql.Array` để bind mảng SQL khi driver/DB hỗ trợ loại phần tử và kiểu mảng.
- `java.sql.SQLData`, `SQLInput`, `SQLOutput` và type map của `Connection`: những cơ chế JDBC dành cho SQL structured type/UDT, **khác** với đối tượng JSON/UUID tùy biến của từng driver.

Không dùng `Object.toString()` như một giải pháp chuyển đổi mặc định. Kiểu địa lý, khoảng thời gian, enum hay mảng có thể có định dạng chuỗi không chuẩn; `toString()` cũng không nhất thiết trả định dạng mà máy chủ SQL chấp nhận.

### Ví dụ enum SQL và kiểu riêng

Giả sử PostgreSQL định nghĩa:

```sql
CREATE TYPE job_status AS ENUM ('PENDING', 'RUNNING', 'DONE');

CREATE TABLE background_job (
    id     uuid PRIMARY KEY,
    status job_status NOT NULL
);
```

Ứng dụng có thể bind `String` rồi ép kiểu **theo SQL PostgreSQL**:

```java
String sql = """
        UPDATE background_job
        SET status = CAST(? AS job_status)
        WHERE id = ?
        """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "RUNNING");
    ps.setObject(2, jobId);
    ps.executeUpdate();
}
```

Tên kiểu `job_status` phải được kiểm soát bởi cấu hình/code ứng dụng, không ghép tên kiểu hoặc tên cột tùy ý lấy trực tiếp từ dữ liệu người dùng. Khi đổi DB, enum SQL này có thể cần chuyển thành `VARCHAR` + `CHECK` hoặc một bảng tham chiếu.

## 7. Chẩn đoán mapping qua `DatabaseMetaData` và `ResultSetMetaData`

Khi `getObject(...)` trả class bất ngờ hoặc `setObject(...)` báo lỗi, hãy kiểm tra **kiểu cột thật** thay vì thử nhiều phép ép kiểu một cách ngẫu nhiên.

`DatabaseMetaData.getColumns(...)` cho biết kiểu của cột trong schema. Với `ResultSetMetaData`, có thể xem kiểu của **cột trong kết quả SELECT**:

```java
import java.sql.ResultSetMetaData;

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, payload FROM app_event WHERE id = ?")) {
    ps.setObject(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        ResultSetMetaData m = rs.getMetaData();
        for (int col = 1; col <= m.getColumnCount(); col++) {
            System.out.printf(
                    "label=%s jdbcType=%d dbType=%s class=%s%n",
                    m.getColumnLabel(col),
                    m.getColumnType(col),
                    m.getColumnTypeName(col),
                    m.getColumnClassName(col));
        }
    }
}
```

Trên một driver, `getColumnType(...)` có thể trả `Types.OTHER` cho `uuid` hoặc `jsonb`; trên driver khác, mã kiểu và class có thể khác. `getColumnTypeName(...)` có thể giúp phân biệt `uuid` với `jsonb`, còn `getColumnClassName(...)` mô tả class Java mà driver dự kiến trả khi gọi `getObject()`. Đây vẫn là **thông tin do driver cung cấp**, không phải bảo đảm có thể ép mọi giá trị thực tế sang class đó mà không xử lý `NULL`.

Ví dụ dùng `DatabaseMetaData` để kiểm tra kiểu cột theo phạm vi biết trước:

```java
var meta = connection.getMetaData();
String escape = meta.getSearchStringEscape();
if (escape == null || escape.isEmpty()) {
    throw new SQLException("Driver không hỗ trợ escape wildcard metadata");
}
String tablePattern = "app" + escape + "_event"; // Match dấu _ theo nghĩa đen.
try (ResultSet columns = meta.getColumns(
        connection.getCatalog(), "public", tablePattern, "%")) {
    while (columns.next()) {
        System.out.printf("%s => JDBC %d / DB %s%n",
                columns.getString("COLUMN_NAME"),
                columns.getInt("DATA_TYPE"),
                columns.getString("TYPE_NAME"));
    }
}
```

`"public"` và `"app_event"` là ví dụ PostgreSQL; các tham số `schemaPattern`, `tableNamePattern` và `columnNamePattern` là mẫu tìm kiếm, ký tự `%` hoặc `_` có ý nghĩa wildcard. Ví dụ lấy ký tự escape do driver cung cấp để khớp dấu `_` trong tên bảng theo nghĩa đen. Với driver không cung cấp ký tự escape, cần áp dụng chiến lược tra cứu và lọc tên chính xác khác đã kiểm chứng. Tên catalog/schema của DB cũng không đồng nhất; hãy kiểm tra phạm vi và quyền của kết nối.

## 8. Thiết kế lớp adapter để hạn chế phụ thuộc driver

Nếu ứng dụng chỉ chạy trên PostgreSQL, việc dùng `PGobject` trong repository có thể đơn giản. Nhưng khi cần hỗ trợ nhiều DB, phần code nghiệp vụ nên làm việc với **`UUID` và cấu trúc JSON ở cấp domain**, còn cách bind tùy driver đặt sau một giao diện riêng:

```java
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public interface AdvancedTypeBinder {
    void bindUuid(PreparedStatement ps, int index, UUID id)
            throws SQLException;

    void bindJson(PreparedStatement ps, int index, String json)
            throws SQLException;

    UUID readUuid(ResultSet rs, String column)
            throws SQLException;

    String readJson(ResultSet rs, String column)
            throws SQLException;
}
```

Hai triển khai có thể khác nhau:

| Triển khai | UUID | JSON |
| --- | --- | --- |
| PostgreSQL adapter | `ps.setObject(index, uuid)`, `getObject(..., UUID.class)` | `PGobject("jsonb")` hoặc SQL `CAST(? AS jsonb)` |
| Adapter cho schema chuỗi | `ps.setString(index, uuid.toString())`, `UUID.fromString(rs.getString(...))` | `setString`/`getString` nếu cột là text được quản lý riêng |

**Lưu ý:** Việc dùng `CAST(? AS jsonb)` thay đổi cả cú pháp câu SQL nên **không thể triển khai đầy đủ chỉ bằng thay đổi `bindJson(...)`**, nếu SQL không có biểu thức CAST tương ứng. Một adapter thực tế có thể cần cung cấp cả cách dựng câu SQL theo DB hoặc đặt phép CAST ở lớp repository dành riêng cho DB. Không nên giấu các khác biệt này bằng lời hứa “chỉ đổi driver là chạy”.

Không cần tạo tầng trừu tượng phức tạp khi hệ thống đã cam kết sử dụng một DB. Ngay cả trong trường hợp đó, cô lập dependency `org.postgresql.util.PGobject` vào một vài class giúp nâng cấp driver và kiểm thử dễ hơn.

## 9. Xử lý lỗi, JSON không hợp lệ và transaction

Những lỗi thường gặp khi ghi/đọc kiểu riêng:

| Tình huống | Biểu hiện có thể | Hướng xử lý |
| --- | --- | --- |
| Gọi `setString` cho cột `jsonb` mà driver bind `VARCHAR` | DB từ chối ép kiểu trong `INSERT`/`UPDATE` | Dùng `CAST(? AS jsonb)` hoặc `PGobject` đã xác minh |
| JSON sai cú pháp | `SQLException` từ DB hoặc lỗi parser ở ứng dụng | Parse/validate trước; trả thông điệp nghiệp vụ phù hợp |
| UUID đầu vào sai định dạng | `IllegalArgumentException` từ `UUID.fromString` | Xác thực đầu vào, dùng dạng chuẩn |
| `getObject(..., UUID.class)` không được hỗ trợ | `SQLException` hoặc `SQLFeatureNotSupportedException` | Đọc dạng chuỗi rồi parse nếu driver trả chuỗi hợp lệ |
| Dùng `Types.OTHER` chung cho mọi kiểu | Không xác định đúng kiểu SQL, driver từ chối | Xác định tên kiểu DB và cơ chế binding |
| Lưu JSON vào text rồi giả định DB kiểm tra schema | Dữ liệu sai cấu trúc vẫn được ghi | Thêm xác thực ứng dụng/ràng buộc DB |
| Dữ liệu JSON quá lớn hoặc sâu | Tốn CPU, bộ nhớ hoặc vượt giới hạn DB/parser | Giới hạn kích thước, độ sâu và thời gian xử lý |
| Gọi lại `INSERT` ngay sau khi mất kết nối lúc commit | Có thể tạo trùng nếu giao dịch đã commit | Dùng mã yêu cầu duy nhất/idempotency và đối chiếu trạng thái |

Trong transaction thủ công, xử lý SQL lỗi theo cùng nguyên tắc JDBC: chỉ `commit` khi toàn bộ bước hợp lệ, `rollback` khi thất bại, lưu ý `rollback` cũng có thể lỗi và kết quả của `commit` có thể không xác định khi kết nối bị mất.

Không dựa hoàn toàn vào thông điệp lỗi của DB để điều khiển nghiệp vụ. `SQLException.getSQLState()` và `getErrorCode()` hỗ trợ chẩn đoán; mã SQLState/vendor code cụ thể vẫn phụ thuộc DB và driver. Không tự động retry tất cả lỗi JSON/UUID vì lỗi cú pháp hoặc dữ liệu không hợp lệ sẽ tiếp tục thất bại.

## 10. Ma trận kiểm tra tính khả chuyển

Khi ứng dụng có thể thay DB hoặc nâng cấp driver, nên thử trực tiếp các trường hợp sau trên môi trường kiểm thử:

| Kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Ghi/đọc UUID native bằng `setObject(UUID)` và `getObject(..., UUID.class)` | Driver có hỗ trợ? Giá trị round-trip có đúng 128 bit? |
| Ghi UUID qua `CHAR(36)` và `BINARY(16)` nếu được dùng | Định dạng, độ dài, quy tắc byte order và truy vấn tìm kiếm có nhất quán? |
| Bind JSON bằng `setString`, `CAST` và đối tượng driver | Cách nào được hỗ trợ với kiểu cột JSON thật? |
| Đọc JSON qua `getString` và `getObject` | Kết quả Java class nào? Có đổi định dạng JSON không? |
| SQL `NULL`, JSON literal `null`, chuỗi JSON `"null"` | Ba trường hợp có được phân biệt đúng không? |
| JSON Unicode và số thập phân lớn | Có mất ký tự hoặc độ chính xác qua parser/DB không? |
| Cột JSON với object/array nhiều cấp, dữ liệu lớn | Kích thước, độ sâu, thời gian bind/read và memory có phù hợp? |
| `ResultSetMetaData.getColumnTypeName`, `getColumnClassName` | Metadata có tương ứng cách `getObject` trả giá trị không? |
| `Types.OTHER` và `setNull(..., typeName)` | Driver có thực sự hỗ trợ từng kiểu riêng? |
| Batch, transaction, rollback và nâng cấp driver | Giá trị có giữ đúng kiểu? Hành vi lỗi và rollback có ổn định? |

Một bài thử nhỏ có thể ghi:

```text
UUID gốc: 550e8400-e29b-41d4-a716-446655440000
JSON vào: {"name":"Đà Nẵng","count":12345678901234567890,"active":true}

1. INSERT bằng PreparedStatement.
2. SELECT lại qua ResultSet.
3. So sánh UUID dưới dạng UUID.
4. Parse JSON và so sánh cấu trúc, kiểu dữ liệu, độ chính xác số.
5. Thử JSON sai cú pháp, SQL NULL và JSON literal null.
6. Ghi tên DB/driver/version và cách bind thực sự được hỗ trợ.
```

Nếu DB chuẩn hóa văn bản JSON, việc byte hoặc thứ tự thuộc tính khác nhau chưa chắc là lỗi; điều phải kiểm chứng là **ngữ nghĩa dữ liệu sau khi parse** cùng những thuộc tính mà nghiệp vụ cần giữ.

## 11. Tình huống thực hành: ứng dụng sự kiện đa cơ sở dữ liệu

Một dịch vụ JDBC nhận HTTP request gồm `eventId` (UUID) và `payload` (JSON). Nhóm phát triển muốn chạy trên PostgreSQL hôm nay và có khả năng đổi hệ quản trị sau này.

Hãy triển khai theo các bước:

1. Quyết định miền dữ liệu: `eventId` là `UUID`; `payload` cần được kiểm tra JSON hợp lệ và những thuộc tính bắt buộc trước khi ghi.
2. Chọn schema cho PostgreSQL: `uuid` và `jsonb`. Viết repository dùng `PreparedStatement`, thử cả `CAST(? AS jsonb)` và `PGobject` trong môi trường test để chọn một cơ chế ổn định.
3. Dùng `getObject("id", UUID.class)` và `getString("payload")` để đọc lại. Nếu driver không hỗ trợ typed getter, ghi nhận và kiểm tra đường chuyển đổi thay thế.
4. Thử các JSON có Unicode, số lớn, array lồng nhau, JSON literal `null` và JSON không hợp lệ. Kiểm tra dữ liệu sau parse thay vì so nguyên chuỗi.
5. Kiểm tra metadata của hai cột và lưu tên DB/driver/version vào hồ sơ kiểm thử.
6. Thiết kế adapter hoặc repository riêng cho DB khác, với test chung về CRUD và tính đúng đắn. Không sao chép nguyên cú pháp PostgreSQL sang DB mới.
7. Nếu ghi thêm outbox/audit cùng event, tổ chức một transaction cho mọi bước; thử lỗi giữa transaction và kiểm tra rollback.

**Tự kiểm tra:**

- Tại sao `Types.OTHER` chưa đủ để biết một cột là `uuid` hay `jsonb`?
- Khi nào `setObject(index, UUID)` phù hợp hơn `setString(index, uuid.toString())`?
- Vì sao `PreparedStatement.setString(index, json)` có thể bị từ chối ở cột `jsonb` dù chuỗi JSON hợp lệ?
- `PGobject` thuộc JDBC chuẩn hay driver PostgreSQL? Việc sử dụng nó ảnh hưởng kiến trúc thế nào?
- SQL `NULL` khác JSON literal `null` ra sao?
- Vì sao JSON đọc lại từ `jsonb` có thể khác chuỗi ban đầu mà vẫn tương đương về ngữ nghĩa?
- Khi thêm một DB mới, cần kiểm thử những kết hợp nào giữa kiểu SQL, lớp Java và driver?

**Ghi nhớ:** Với UUID, JSON và các kiểu SQL riêng, JDBC cung cấp cơ chế chung `setObject`/`getObject` nhưng **kiểu Java và quy tắc chuyển đổi thực tế do driver/DB quyết định**. Hãy phân biệt kiểu SQL gốc với kiểu lưu trữ tương thích, dùng `CAST` hoặc đối tượng driver khi cần, quan sát `Types.OTHER` cùng tên kiểu thực tế, và kiểm chứng round-trip trên đúng driver. Giữ SQL tham số hóa, phân quyền và transaction đúng cách để ứng dụng vừa xử lý dữ liệu chính xác vừa có chiến lược khả chuyển rõ ràng.
