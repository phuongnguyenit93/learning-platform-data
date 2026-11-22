# Phân biệt kiểu chuẩn JDBC và lớp đối tượng do driver trả về

Khi dùng JDBC, tên cột `JSONB`, `UUID`, `DECIMAL` hay `TIMESTAMP` thường khiến người học nghĩ rằng mỗi kiểu SQL sẽ luôn tương ứng với **một lớp Java duy nhất**. Trong thực tế, điều này không đúng. Chuẩn JDBC định nghĩa các **mã kiểu SQL** (`java.sql.Types`, `java.sql.JDBCType`), đồng thời định nghĩa nhiều phương thức đọc giá trị, nhưng một số kiểu database không nằm trong tập kiểu chuẩn hoặc được driver ánh xạ theo quy tắc riêng.

Do đó, `ResultSet.getObject(...)` có thể trả về một lớp thuộc Java SE, một interface JDBC như `java.sql.Array` hoặc một lớp riêng của nhà cung cấp driver. Việc thấy một đối tượng có tên lớp lạ **không có nghĩa dữ liệu bị sai**, và ngược lại, tên lớp có vẻ quen thuộc không chứng minh rằng phép chuyển đổi giữ được toàn bộ ý nghĩa dữ liệu.

Bài học thuộc chương **Kiểu SQL nâng cao** của module **JDBC**. Nội dung vận dụng `DataSource`, `PreparedStatement`, `ResultSet`, metadata và các API chuẩn để xây dựng code truy cập dữ liệu ít phụ thuộc driver nhưng vẫn xử lý được nhu cầu riêng của hệ quản trị.

Sau bài học, bạn có thể:

- Phân biệt **mã SQL type**, **tên kiểu do DBMS khai báo**, **lớp Java do driver trả về** và **kiểu Java mà ứng dụng mong muốn**.
- Sử dụng `ResultSetMetaData` để kiểm tra thông tin kiểu mà không nhầm metadata với runtime value.
- Chọn giữa `getXxx`, `getObject(column)` và `getObject(column, Class<T>)` theo khả năng hỗ trợ.
- Nhận diện những trường hợp `Types.OTHER`, `ARRAY`, `STRUCT`, `SQLXML`, `BLOB`, `CLOB` và kiểu mở rộng của DBMS.
- Thiết kế ranh giới ánh xạ dữ liệu: không cast mù, không viết phụ thuộc vào tên lớp của driver khi không cần, có đường fallback khi phù hợp.
- Kiểm thử khả năng tương thích và quản lý bộ nhớ, lỗi và dữ liệu nhạy cảm.

## 1. Bốn lớp thông tin về cùng một cột

Giả sử database có một cột lưu JSON bằng kiểu `jsonb` (đặc trưng của PostgreSQL). Cần phân biệt:

| Tầng | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Kiểu khai báo trong DBMS** | `jsonb` | Tên kiểu do SQL dialect của PostgreSQL cung cấp |
| **Mã kiểu JDBC** | `Types.OTHER` | Mã chuẩn mà driver có thể dùng để phân loại một kiểu không có ánh xạ JDBC trực tiếp |
| **Lớp runtime của giá trị** | `org.postgresql.util.PGobject` | Lớp cụ thể mà một phiên bản pgJDBC có thể trả về khi gọi `getObject` không chỉ định kiểu |
| **Kiểu đích trong ứng dụng** | DTO như `OrderPayload`, hoặc `String` JSON để parse | Cách ứng dụng lựa chọn biểu diễn dữ liệu của mình |

Bốn tầng này **không đồng nhất**. Ví dụ một driver có thể đọc giá trị `UUID` trực tiếp thành `java.util.UUID`, trong khi driver khác trả dạng chuỗi hoặc lớp riêng. Một cột SQL `DECIMAL` thường ánh xạ sang `BigDecimal`, nhưng code lại có thể chủ động gọi `getDouble` và đánh đổi độ chính xác.

~~~mermaid
flowchart LR
    A["Cột SQL: tên kiểu của DBMS"] --> B["JDBC metadata: type code + type name"]
    A --> C["Driver giải mã dữ liệu"]
    C --> D["getObject(): lớp runtime"]
    C --> E["getXxx() / getObject(Class): kiểu được yêu cầu"]
    D --> F["Adapter / Mapper ứng dụng"]
    E --> F
    F --> G["DTO / Domain model"]
~~~

**Nguyên tắc:** Dùng metadata để hiểu cột và dùng **hợp đồng nghiệp vụ** để chọn kiểu Java phù hợp. Không để lớp nội bộ của JDBC driver tự động trở thành API công khai của tầng domain.

## 2. `java.sql.Types` và `JDBCType` có phải lớp dữ liệu không?

Không. `java.sql.Types` gồm các **hằng số nguyên**, ví dụ `Types.INTEGER`, `Types.DECIMAL`, `Types.TIMESTAMP`, `Types.ARRAY`, `Types.STRUCT` và `Types.OTHER`. Chúng mô tả **phân loại kiểu SQL** được sử dụng trong JDBC metadata, bind tham số hoặc đăng ký tham số OUT.

`java.sql.JDBCType` (từ JDBC 4.2) là enum triển khai interface `SQLType` cho các mã chuẩn tương ứng:

~~~java
import java.sql.JDBCType;
import java.sql.Types;

int typeCode = Types.DECIMAL;
JDBCType standardType = JDBCType.DECIMAL;

System.out.println(typeCode == standardType.getVendorTypeNumber());
// true
~~~

Hai cơ chế có những ứng dụng điển hình:

| API | Vai trò | Ví dụ |
| --- | --- | --- |
| `Types.DECIMAL` | Mã `int` cho kiểu SQL chuẩn | `ps.setNull(1, Types.DECIMAL)` |
| `JDBCType.DECIMAL` | Enum `SQLType` mô tả mã chuẩn | `ps.setObject(1, value, JDBCType.DECIMAL)` |
| `ResultSetMetaData.getColumnType(i)` | Trả mã kiểu dạng `int` do driver báo cáo | `Types.OTHER` |
| `ResultSetMetaData.getColumnTypeName(i)` | Trả tên kiểu do driver/DBMS báo cáo | `jsonb`, `DECIMAL` |
| `ResultSetMetaData.getColumnClassName(i)` | Tên lớp Java **dự kiến** của `getObject` theo metadata | `java.math.BigDecimal` hoặc lớp driver |
| `ResultSet.getObject(i)` | Đọc giá trị thực dưới dạng `Object` | Có thể là `BigDecimal`, `UUID`, `PGobject`... |
| `ResultSet.getObject(i, Target.class)` | Yêu cầu driver chuyển giá trị sang kiểu Java đích | `LocalDateTime.class` hoặc kiểu tương thích |

`JDBCType.valueOf(int)` có thể chuyển mã chuẩn được nhận biết thành enum, nhưng **không có nghĩa mọi mã riêng do vendor trả về đều chuyển được**. Nếu mã không được nhận biết, lời gọi có thể ném `IllegalArgumentException`. Khi xây dựng công cụ kiểm tra metadata, luôn có fallback.

### `Types.OTHER` không phải câu trả lời cho “giá trị Java là gì?”

`Types.OTHER` có nghĩa loại dữ liệu SQL không được mô tả cụ thể bằng một mã chuẩn thông thường, hoặc driver chọn phân loại tổng quát. Nó **không** có nghĩa:

- Giá trị luôn là `String`.
- Giá trị luôn là `byte[]`.
- Giá trị luôn là một `java.sql.Struct`.
- Driver luôn trả một lớp Java cố định trên mọi phiên bản.
- Có thể dùng `setObject(index, value, Types.OTHER)` một cách giống nhau trên mọi DBMS.

Với `OTHER`, cần xem **tên kiểu DBMS**, tài liệu driver và kết quả kiểm thử tích hợp trước khi thiết kế converter.

## 3. Những ánh xạ JDBC phổ biến

Bảng sau mô tả các ánh xạ **thường gặp**, không phải cam kết rằng lời gọi `getObject()` luôn trả đúng lớp được ghi ở mọi driver.

| Kiểu SQL/JDBC | Mã `Types` | Giá trị Java thường gặp | Cách đọc nên cân nhắc |
| --- | --- | --- | --- |
| `INTEGER` | `Types.INTEGER` | `Integer` | `getInt` + `wasNull` hoặc `getObject(..., Integer.class)` khi hỗ trợ |
| `BIGINT` | `Types.BIGINT` | `Long` | `getLong` + `wasNull` |
| `DECIMAL`/`NUMERIC` | `Types.DECIMAL`/`NUMERIC` | `BigDecimal` | `getBigDecimal` để bảo toàn số thập phân |
| `VARCHAR` | `Types.VARCHAR` | `String` | `getString` |
| `BOOLEAN` | `Types.BOOLEAN`/`BIT` | `Boolean` | `getBoolean` + `wasNull` |
| `DATE` | `Types.DATE` | `java.sql.Date`; driver hỗ trợ Java Time có thể chuyển thành `LocalDate` | `getObject(..., LocalDate.class)` khi hỗ trợ hoặc `getDate` |
| `TIME` | `Types.TIME` | `java.sql.Time`; có thể chuyển `LocalTime` | `getObject(..., LocalTime.class)` khi hỗ trợ hoặc `getTime` |
| `TIMESTAMP` không có múi giờ | `Types.TIMESTAMP` | `java.sql.Timestamp`; có thể chuyển `LocalDateTime` | `getObject(..., LocalDateTime.class)` khi tương thích |
| `TIMESTAMP WITH TIME ZONE` | `Types.TIMESTAMP_WITH_TIMEZONE` khi driver báo đúng | `OffsetDateTime` trong ánh xạ JDBC 4.2 | `getObject(..., OffsetDateTime.class)` khi hỗ trợ |
| `ARRAY` | `Types.ARRAY` | `java.sql.Array` hoặc biểu diễn riêng driver | `getArray`, rồi đọc phần tử |
| `STRUCT` | `Types.STRUCT` | `java.sql.Struct` hoặc lớp đã ánh xạ theo type map | `getObject` và xử lý qua `Struct` nếu có |
| `BLOB` | `Types.BLOB` | `java.sql.Blob` | `getBlob`/`getBinaryStream` |
| `CLOB`/`NCLOB` | `Types.CLOB`/`NCLOB` | `Clob`/`NClob` | `getClob`/`getNClob` hoặc character stream |
| `SQLXML` | `Types.SQLXML` | `java.sql.SQLXML` | `getSQLXML` |
| `ROWID` | `Types.ROWID` | `java.sql.RowId` | `getRowId` nếu DBMS hỗ trợ |
| Loại riêng DBMS | Có thể `Types.OTHER` hay mã vendor | `Object`/`String`/`UUID`/lớp driver | Dựa vào tài liệu driver và hợp đồng cột |

**Hai lưu ý đặc biệt:**

1. `java.sql.Timestamp` và `LocalDateTime` không tự nói rằng giá trị là UTC. Cần xem cột SQL và cấu hình múi giờ. `OffsetDateTime` không đồng nghĩa với `ZonedDateTime` có `ZoneId` đầy đủ.
2. Các kiểu LOB/array/struct có thể giữ tài nguyên driver hoặc tham chiếu dữ liệu lớn; đừng materialize tất cả chỉ để biết lớp runtime của chúng.

## 4. Quan sát metadata và lớp runtime một cách an toàn

`ResultSetMetaData` giúp trả lời ba câu hỏi khác nhau về một cột:

- `getColumnType(i)` — driver gán **mã kiểu JDBC nào**?
- `getColumnTypeName(i)` — driver mô tả **tên kiểu SQL nào**?
- `getColumnClassName(i)` — driver **dự kiến** trả về tên lớp Java nào từ `getObject`?

Thử nghiệm sau không cần thư viện JSON hay lớp riêng của driver:

~~~java
import java.sql.Connection;
import java.sql.JDBCType;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class SqlTypeInspector {
    private final DataSource dataSource;

    public SqlTypeInspector(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void inspectOne(long id) throws SQLException {
        String sql = "SELECT amount, attributes, created_at "
                   + "FROM orders WHERE id = ?";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {

            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                ResultSetMetaData md = rs.getMetaData();

                for (int i = 1; i <= md.getColumnCount(); i++) {
                    int code = md.getColumnType(i);
                    String typeLabel;

                    try {
                        typeLabel = JDBCType.valueOf(code).getName();
                    } catch (IllegalArgumentException unknownCode) {
                        typeLabel = "VENDOR_TYPE_" + code;
                    }

                    System.out.println(
                            "column=" + md.getColumnLabel(i)
                          + " jdbcCode=" + code
                          + " jdbcType=" + typeLabel
                          + " dbTypeName=" + md.getColumnTypeName(i)
                          + " expectedClass=" + md.getColumnClassName(i));
                }

                if (rs.next()) {
                    for (int i = 1; i <= md.getColumnCount(); i++) {
                        Object value = rs.getObject(i);

                        // Chỉ in tên lớp, KHÔNG in nội dung value.
                        String runtimeClass = value == null
                                ? "<SQL NULL>"
                                : value.getClass().getName();

                        System.out.println(
                                "columnIndex=" + i
                              + " runtimeClass=" + runtimeClass);
                    }
                }
            }
        }
    }
}
~~~

Giả sử bảng `orders` có cột `amount`, `attributes` và `created_at`; kiểu của `attributes` có thể là JSON/JSONB do DBMS định nghĩa. Ví dụ trên là công cụ **khảo sát trên môi trường test**; không nên chạy đại trà trong production rồi log toàn bộ schema hoặc giá trị. Với LOB/SQLXML hoặc dữ liệu rất lớn, `getObject` có thể khởi tạo việc tải dữ liệu hoặc đối tượng giữ tài nguyên; nếu chỉ cần metadata, **không gọi `getObject` cho giá trị lớn**.

### Metadata không phải lời hứa về lớp runtime

`getColumnClassName(i)` mô tả lớp Java mà driver cho rằng `getObject` sẽ tạo ra. Kết quả thực tế có thể khác tùy:

- Giá trị là SQL `NULL`: `rs.getObject(i)` trả `null`, không phải instance của bất kỳ lớp nào.
- Driver/version/configuration thay đổi cách mapping hoặc dùng class riêng.
- DBMS có UDT hoặc kiểu `OTHER` được xử lý khác nhau tùy trường hợp.
- Ứng dụng dùng `getObject(i, Target.class)` thay vì `getObject(i)`: kiểu **đích được yêu cầu** có thể khác class mặc định của `getObject`.

Không xây logic nghiệp vụ chỉ dựa trên chuỗi `getColumnClassName`. Metadata phù hợp để **kiểm tra hợp đồng** và chẩn đoán, còn tầng mapping phải có quy tắc chuyển đổi được định nghĩa rõ.

## 5. `getObject` không kiểu và `getObject` có kiểu

### 5.1. Đọc `Object` mặc định

~~~java
Object raw = rs.getObject("amount");

if (raw == null) {
    // SQL NULL
} else if (raw instanceof java.math.BigDecimal) {
    java.math.BigDecimal amount = (java.math.BigDecimal) raw;
    // ...
} else {
    throw new SQLException(
            "Không thể ánh xạ cột amount từ kiểu runtime hiện tại");
}
~~~

Cách này cần thiết khi khám phá kiểu động hoặc xử lý một nhóm kiểu khác nhau. Nhưng nếu code nghiệp vụ **đã biết cột `amount` là `DECIMAL`**, gọi `getBigDecimal` thường đơn giản và ổn định hơn. `getObject` không kiểu rồi ép về `BigDecimal` là hai bước mà một getter chuẩn có thể thay thế.

### 5.2. Yêu cầu kiểu Java với `getObject(column, Class<T>)`

JDBC 4.1/4.2 có các overload đọc đối tượng về class cụ thể, nếu driver hỗ trợ:

~~~java
import java.time.LocalDate;
import java.time.LocalDateTime;

LocalDate deliveryDate =
        rs.getObject("delivery_date", LocalDate.class);

LocalDateTime createdLocal =
        rs.getObject("created_local", LocalDateTime.class);
~~~

Phương thức này yêu cầu **driver chuyển dữ liệu** sang kiểu đích. Nó **không đơn giản là một phép cast**. Nếu kiểu cột/driver không hỗ trợ chuyển đổi, JDBC có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException`; không nên mặc định mọi class Java tùy ý đều có thể truyền vào.

Ví dụ, cách viết sau không phải API chuẩn để JSON tự biến thành domain object:

~~~java
// Không có cam kết JDBC rằng driver hiểu lớp ứng dụng này.
OrderPayload payload =
        rs.getObject("attributes", OrderPayload.class);
~~~

Để chuyển JSON thành `OrderPayload`, ứng dụng cần một bước parse/validate bằng thư viện phù hợp hoặc converter riêng, sau khi đã lấy dữ liệu SQL qua cơ chế driver hỗ trợ.

### 5.3. Chọn getter theo ý nghĩa dữ liệu

| Tình huống | Cách ưu tiên |
| --- | --- |
| `DECIMAL(19,2)` dùng cho giá tiền | `getBigDecimal`, tránh `getDouble` |
| `BIGINT` bắt buộc | `getLong` và `wasNull()` khi cần phân biệt SQL NULL |
| `VARCHAR` | `getString` |
| `DATE` | `getObject(..., LocalDate.class)` nếu hỗ trợ; fallback `getDate` |
| `TIMESTAMP` không múi giờ | `getObject(..., LocalDateTime.class)` nếu hỗ trợ |
| `ARRAY` SQL | `getArray` thay vì cast trực tiếp sang `List<?>` |
| `BLOB` lớn | `getBinaryStream` thay vì `getBytes` tải cả giá trị |
| JSON/UUID/INTERVAL riêng DBMS | Kiểu được driver tài liệu hóa, sau đó chuyển thành domain object |

Đừng dựa vào tên kiểu SQL để gọi getter không phù hợp. Với `NUMERIC` cỡ lớn, `getLong` có thể overflow hoặc mất phần thập phân; với kiểu thời điểm, chuyển qua `java.util.Date` có thể khiến ngữ nghĩa múi giờ không rõ ràng.

## 6. Ví dụ repository: ánh xạ theo hợp đồng thay vì runtime class

Giả sử bảng SQL có cấu trúc logic sau, với các kiểu chuẩn:

~~~sql
CREATE TABLE order_summary (
    id BIGINT PRIMARY KEY,
    total DECIMAL(19, 2) NOT NULL,
    posted_at_local TIMESTAMP NOT NULL,
    approved BOOLEAN
);
~~~

Cú pháp và khả năng hỗ trợ `BOOLEAN`/`TIMESTAMP` có khác biệt giữa DBMS. Ví dụ giả định `posted_at_local` là ngày giờ **không kèm múi giờ**, còn `approved` có thể `NULL`.

### 6.1. Domain object không phụ thuộc driver

~~~java
import java.math.BigDecimal;
import java.time.LocalDateTime;

public final class OrderSummary {
    private final long id;
    private final BigDecimal total;
    private final LocalDateTime postedAtLocal;
    private final Boolean approved;

    public OrderSummary(
            long id, BigDecimal total,
            LocalDateTime postedAtLocal, Boolean approved) {
        this.id = id;
        this.total = total;
        this.postedAtLocal = postedAtLocal;
        this.approved = approved;
    }

    public long id() { return id; }
    public BigDecimal total() { return total; }
    public LocalDateTime postedAtLocal() { return postedAtLocal; }
    public Boolean approved() { return approved; }
}
~~~

### 6.2. Mapper và truy vấn JDBC

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class OrderSummaryRepository {
    private final DataSource dataSource;

    public OrderSummaryRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public Optional<OrderSummary> findById(long id)
            throws SQLException {

        String sql = "SELECT id, total, posted_at_local, approved "
                   + "FROM order_summary WHERE id = ?";

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {

            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                long orderId = rs.getLong("id");
                if (rs.wasNull()) {
                    throw new SQLException("id bắt buộc không được NULL");
                }

                BigDecimal total = rs.getBigDecimal("total");
                if (total == null) {
                    throw new SQLException("total bắt buộc không được NULL");
                }

                LocalDateTime postedAt =
                        rs.getObject("posted_at_local",
                                     LocalDateTime.class);
                if (postedAt == null) {
                    throw new SQLException(
                            "posted_at_local bắt buộc không được NULL");
                }

                boolean approvedValue = rs.getBoolean("approved");
                Boolean approved = rs.wasNull()
                        ? null
                        : Boolean.valueOf(approvedValue);

                return Optional.of(new OrderSummary(
                        orderId, total, postedAt, approved));
            }
        }
    }
}
~~~

Ở đây, code **không hỏi `getObject` trả về lớp runtime gì**, vì schema và miền nghiệp vụ đã quy định kiểu Java phù hợp. Mỗi trường được lấy bằng getter có ý nghĩa rõ. Nếu driver không hỗ trợ `getObject(..., LocalDateTime.class)`, ứng dụng có thể viết adapter fallback có kiểm soát, sau khi kiểm thử.

### 6.3. Fallback cho JDBC driver chưa hỗ trợ `LocalDateTime`

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;

static LocalDateTime readLocalTimestamp(
        ResultSet rs, String column) throws SQLException {

    // Dùng khi driver và kiểu cột đã được kiểm thử với
    // TIMESTAMP không có múi giờ.
    Timestamp value = rs.getTimestamp(column);
    return value == null ? null : value.toLocalDateTime();
}
~~~

Đây là **đường tương thích có chủ đích**, không phải bằng chứng rằng mọi kiểu `TIMESTAMP` và múi giờ đều chuyển đổi chính xác. Nếu cột mang thời điểm tuyệt đối hoặc kiểu `TIMESTAMP WITH TIME ZONE`, cần dùng hợp đồng thời gian riêng và kiểm thử cấu hình driver.

**Không dùng `catch (SQLException)` rồi âm thầm thử nhiều converter khác nhau cho bất kỳ cột nào.** Một lỗi SQL cũng có thể là mất connection hoặc sai tên cột; bắt chung rồi biến lỗi đó thành “kiểu không hỗ trợ” sẽ che giấu nguyên nhân. Fallback chỉ nên được chọn theo cấu hình/driver capability đã kiểm chứng hoặc bắt lỗi tính năng không hỗ trợ một cách cụ thể.

## 7. Những kiểu riêng của DBMS: JSON, UUID và INTERVAL

### 7.1. PostgreSQL `json`/`jsonb`

PostgreSQL có các kiểu `json` và `jsonb`. Một số phiên bản pgJDBC trả `org.postgresql.util.PGobject` cho `getObject("attributes")`; đây là **lớp riêng của driver**, không thuộc Java SE hay API JDBC tiêu chuẩn.

~~~java
Object value = rs.getObject("attributes");

// Không nên mặc định:
// String json = (String) value;

// Cũng không nên rải cast sang PGobject
// trong mọi service/domain object.
~~~

Có các chiến lược:

1. **Adapter PostgreSQL chuyên biệt:** trong lớp hạ tầng, nhận diện/cấu hình kiểu `PGobject` do phiên bản driver đang dùng, lấy nội dung theo API của driver rồi parse JSON; giữ dependency ở một vị trí rõ ràng.
2. **Lấy biểu diễn văn bản qua SQL dialect:** ví dụ khi PostgreSQL cho phép, chọn `attributes::text AS attributes_json` rồi dùng `getString("attributes_json")` và parse JSON.
3. **Getter text tương thích driver:** một số driver hỗ trợ `getString` cho JSON/JSONB; phải xác minh trên driver thực tế, không xem đó là quy tắc áp dụng cho mọi SQL `OTHER`.

Ví dụ PostgreSQL-specific:

~~~sql
SELECT id, attributes::text AS attributes_json
FROM orders
WHERE id = ?;
~~~

~~~java
String jsonText = rs.getString("attributes_json");
if (jsonText != null) {
    // Parse/validate bằng thư viện JSON của ứng dụng.
    // Đừng coi JSON là domain object đã được kiểm chứng.
}
~~~

Cách cast trong SQL có thể phù hợp với payload nhỏ/vừa. Với JSON có dung lượng rất lớn, gọi `getString` vẫn tải toàn bộ một giá trị vào `String`; cần giới hạn kích thước hoặc thiết kế cách xử lý khác.

Khi **ghi** JSONB, việc bind `String` vào tham số có thể cần cast SQL riêng cho PostgreSQL:

~~~sql
INSERT INTO orders (id, attributes)
VALUES (?, CAST(? AS jsonb));
~~~

~~~java
ps.setLong(1, orderId);
ps.setString(2, jsonText); // Nội dung JSON là tham số, không ghép chuỗi.
ps.executeUpdate();
~~~

Dữ liệu JSON vẫn phải được validate theo schema nghiệp vụ; SQL cast không thay thế việc kiểm tra các trường cần thiết, kích thước, quyền truy cập và giới hạn dữ liệu.

### 7.2. UUID

Nhiều hệ quản trị hỗ trợ UUID hoặc GUID theo các kiểu khác nhau. PostgreSQL có kiểu `uuid`, SQL Server có `uniqueidentifier`, còn hệ thống khác có thể lưu UUID dưới dạng `CHAR(36)` hoặc `BINARY(16)`.

Một driver có thể trả `java.util.UUID` trực tiếp, driver khác trả chuỗi hoặc byte array. Vì vậy:

~~~java
Object rawId = rs.getObject("external_id");

// Nếu ứng dụng yêu cầu UUID, đừng cast mù:
if (rawId instanceof java.util.UUID) {
    java.util.UUID id = (java.util.UUID) rawId;
} else {
    // Sử dụng converter theo driver/kiểu SQL đã kiểm thử,
    // thay vì đoán rằng mọi rawId đều là String.
}
~~~

Một số driver cho phép `rs.getObject("external_id", UUID.class)` hoặc `ps.setObject(index, uuid)`, nhưng **không nên mặc định** hỗ trợ này tồn tại ở mọi DBMS. Nếu cột là `CHAR(36)`, có thể parse một chuỗi đã kiểm tra định dạng bằng `UUID.fromString` và xử lý `IllegalArgumentException` ở tầng mapper, không đưa giá trị nhạy cảm vào thông báo lỗi công khai.

### 7.3. INTERVAL, ENUM, địa lý và kiểu khác

Các kiểu như PostgreSQL `interval`, `inet`, `jsonb`, ENUM do DBMS định nghĩa, PostGIS geometry hoặc Oracle object type thường không có đối tượng Java tiêu chuẩn chung cho mọi driver. Một vài driver trả `String`, một vài trả lớp riêng, và một số cần gọi extension API của vendor.

Không sử dụng một converter tổng quát `String.valueOf(rs.getObject(i))` cho tất cả kiểu đặc biệt: `toString()` của đối tượng vendor có thể không phải biểu diễn dữ liệu ổn định, có thể chứa thông tin không mong muốn, và không thay thế parser/validator.

## 8. Kiểu `ARRAY` và `java.sql.Array`

Đối với một cột SQL array, JDBC có interface `java.sql.Array`. Nó **không phải** `java.util.List` và cũng **không nhất thiết** là `String[]`.

~~~java
import java.sql.Array;
import java.sql.ResultSet;
import java.sql.SQLException;

static long countArrayElements(ResultSet rs, String column)
        throws SQLException {

    Array array = rs.getArray(column);
    if (array == null) {
        return 0L; // Ở đây nghiệp vụ chủ động coi NULL là 0.
    }

    try {
        long count = 0L;

        try (ResultSet elements = array.getResultSet()) {
            // JDBC SQL ARRAY thường trình bày các phần tử qua
            // hai cột: INDEX ở vị trí 1 và VALUE ở vị trí 2.
            while (elements.next()) {
                long position = elements.getLong(1);
                Object element = elements.getObject(2);

                // Xử lý phần tử; không lưu tất cả vào List.
                count++;
            }
        }

        return count;
    } finally {
        array.free();
    }
}
~~~

`Array.getArray()` có thể trả một Java array được materialize trong bộ nhớ; với mảng lớn, `Array.getResultSet()` có thể phù hợp hơn nếu driver hỗ trợ, nhưng **không có cam kết mọi driver đều stream** phần tử. Đối với `NULL`, `getArray` trả `null`; còn một mảng rỗng là giá trị **khác** SQL `NULL`.

Dù biến `element` được khai báo `Object`, lớp thực tế của từng phần tử phụ thuộc vào **SQL base type**, driver và ánh xạ JDBC. Ví dụ array số có thể là đối tượng số, nhưng không được cast thành `Integer[]` chỉ vì tên cột là `integers`. Dùng `Array.getBaseType()` và `getBaseTypeName()` để kiểm tra metadata của kiểu phần tử.

Khi ghi array, một hướng đi thường dùng là `Connection.createArrayOf(typeName, Object[])` rồi `PreparedStatement.setArray(index, array)`. Nhưng không phải DBMS nào cũng hỗ trợ SQL array và `typeName` thường phải khớp định nghĩa kiểu/driver. Ví dụ:

~~~java
java.sql.Array tags = connection.createArrayOf(
        "varchar", new String[] {"new", "priority"});

try {
    ps.setArray(2, tags);
    ps.executeUpdate();
} finally {
    tags.free();
}
~~~

Ở đây `"varchar"` là tên kiểu phần tử minh họa; kiểm tra tên mà driver cụ thể chấp nhận. Không biến tên type hoặc schema do người dùng truyền vào thành SQL động không kiểm soát.

## 9. `STRUCT`, UDT và các type map

Một SQL `STRUCT` có thể đại diện cho kiểu cấu trúc do DBMS định nghĩa. JDBC cung cấp interface `java.sql.Struct`, ví dụ:

~~~java
import java.sql.Struct;

Object raw = rs.getObject("shipping_address");

if (raw instanceof Struct) {
    Struct structure = (Struct) raw;

    String sqlTypeName = structure.getSQLTypeName();
    Object[] attributes = structure.getAttributes();

    // Ánh xạ từng thuộc tính theo đúng định nghĩa UDT.
}
~~~

`Struct.getAttributes()` materialize mảng các thuộc tính trong Java. Với cấu trúc lớn hoặc lồng nhau, cần cân nhắc bộ nhớ và kiểm tra nullability, kiểu con, thứ tự thuộc tính và version của UDT.

JDBC cũng có cơ chế `SQLData` và type map liên kết tên UDT với lớp Java do ứng dụng tự định nghĩa (ví dụ qua `Connection.getTypeMap()` và `setTypeMap()`). Tuy nhiên, khả năng hỗ trợ và cách dùng UDT **không đồng nhất giữa DBMS/driver**. Một số driver trả object riêng thay vì `Struct` thông thường.

**Không đồng nhất `STRUCT` với Java `record`.** `record` là tính năng ngôn ngữ Java, còn `java.sql.Struct` là một giao diện biểu diễn SQL structured type; cần bước mapper minh bạch để chuyển đổi.

## 10. `BLOB`, `CLOB`, `SQLXML` và tài nguyên dữ liệu lớn

Có những kiểu SQL mà giá trị Java trả về có thể **nắm giữ tài nguyên của driver** hoặc yêu cầu truy cập khi `ResultSet`/`Connection` còn mở. Điểm khác nhau không chỉ là class, mà còn là **vòng đời sử dụng**.

| Kiểu SQL | API đọc tiêu biểu | Lưu ý |
| --- | --- | --- |
| `BLOB` | `getBlob`, `getBinaryStream` | `getBytes` có thể tạo mảng byte rất lớn |
| `CLOB` | `getClob`, `getCharacterStream` | `getString` có thể materialize cả nội dung |
| `NCLOB` | `getNClob`, `getNCharacterStream` | Khả năng hỗ trợ tùy DBMS/driver |
| `SQLXML` | `getSQLXML`, sau đó đọc stream hoặc `getString` | Phải kiểm soát XML parser và vòng đời của `SQLXML` |
| `ARRAY` | `getArray`, `Array.getResultSet` | Có thể materialize toàn array hoặc dùng tài nguyên DB |
| `STRUCT` | `getObject`/`Struct` | Có thể có thuộc tính nested và lớp vendor |

Ví dụ xử lý BLOB theo khối mà không nạp toàn bộ vào RAM:

~~~java
import java.io.InputStream;
import java.io.OutputStream;
import java.sql.Blob;
import java.sql.ResultSet;
import java.sql.SQLException;

static long copyBlob(ResultSet rs, String column,
        OutputStream destination) throws Exception {

    Blob blob = rs.getBlob(column);
    if (blob == null) {
        return 0L; // Chính sách NULL cần được xác định bởi nghiệp vụ.
    }

    try {
        long totalBytes = 0L;

        try (InputStream input = blob.getBinaryStream()) {
            byte[] buffer = new byte[64 * 1024];
            int count;

            while ((count = input.read(buffer)) != -1) {
                destination.write(buffer, 0, count);
                totalBytes += count;
            }
        }

        return totalBytes;
    } finally {
        blob.free();
    }
}
~~~

Đọc stream **trước khi đóng `ResultSet`, statement hoặc connection**. Khi driver cho trả locator LOB, đóng tài nguyên sớm có thể làm mất khả năng đọc tiếp. `free()` giải phóng tài nguyên LOB ở mức API JDBC; nơi nhận `OutputStream` do caller sở hữu nên method không tự đóng nó.

Đối với `SQLXML`, có thể dùng:

~~~java
import java.sql.SQLXML;
import java.sql.ResultSet;

SQLXML xml = rs.getSQLXML("xml_payload");

if (xml != null) {
    try {
        // Ví dụ dữ liệu nhỏ: materialize XML thành String.
        String value = xml.getString();

        // Parse XML bằng parser được cấu hình chống XXE/DTD
        // nếu payload đến từ nguồn chưa tin cậy.
    } finally {
        xml.free();
    }
}
~~~

Với XML lớn, ưu tiên stream khi driver hỗ trợ thay vì `getString`. Khi parse XML không tin cậy, phải tắt cơ chế xử lý external entities và các tính năng có nguy cơ XXE ở parser tương ứng; **đây là yêu cầu bảo mật riêng**, không được tự giải quyết chỉ bằng `SQLXML`.

## 11. Ghi dữ liệu: `setObject` có tự hiểu mọi kiểu không?

Không. `PreparedStatement.setObject(index, value)` dựa vào các ánh xạ JDBC được driver hỗ trợ. Với kiểu vendor, thông tin class Java chưa chắc đủ để xác định kiểu SQL mà DBMS mong muốn.

Các phương án:

| Dữ liệu | API ưu tiên | Lưu ý |
| --- | --- | --- |
| `BigDecimal` → `DECIMAL` | `setBigDecimal` | Bảo toàn biểu diễn số, kiểm tra precision/scale |
| `LocalDate` → `DATE` | `setObject` với driver JDBC 4.2 | Test khả năng hỗ trợ |
| `NULL` có kiểu | `setNull(index, Types.XXX)` | Tránh ambiguity của parameter |
| `ARRAY` SQL | `createArrayOf` + `setArray` | Hỗ trợ phụ thuộc DBMS |
| `SQLXML` | `createSQLXML` + `setSQLXML` | Quản lý `free()` và quyền sở hữu |
| LOB lớn | `setBinaryStream`/`setCharacterStream` | Tránh giữ toàn bộ dữ liệu trong `byte[]`/`String` |
| JSONB PostgreSQL | Bind chuỗi với cast `CAST(? AS jsonb)` hoặc adapter pgJDBC | Là SQL dialect riêng, không thay thế validation |
| UDT/vendor | `setObject` với kiểu đúng hoặc API driver | Không giả định `Types.OTHER` giải quyết mọi trường hợp |

Overload `setObject(index, value, JDBCType.OTHER)` chỉ là **yêu cầu driver chuyển giá trị** theo kiểu đích đó; nó không quy định cách mọi cơ sở dữ liệu diễn giải object Java tự tạo. Nếu driver không có mapping, nó có thể ném `SQLException` hoặc `SQLFeatureNotSupportedException`.

Ví dụ một JSON string **không tự trở thành cột JSONB** chỉ vì ứng dụng gửi một `String`. Khi dùng PostgreSQL có thể dùng SQL cast tham số để định kiểu rõ ràng, nhưng vẫn phải xử lý lỗi JSON sai cú pháp và giới hạn kích thước.

## 12. Lỗi và tính di động: không cast mù

Những đoạn mã sau dễ tạo rủi ro:

~~~java
// Sai: SQL OTHER không bảo đảm trả String.
String rawJson = (String) rs.getObject("attributes");

// Sai: một SQL ARRAY không bảo đảm là List.
java.util.List<?> tags =
        (java.util.List<?>) rs.getObject("tags");

// Sai: DECIMAL không nên ép số qua double nếu cần chính xác.
double money = rs.getDouble("total");

// Sai: in mọi giá trị vào log có thể lộ thông tin khách hàng.
System.out.println(rs.getObject("private_payload"));
~~~

Tầng mapper nên áp dụng các nguyên tắc:

1. **Mô tả hợp đồng cột.** Ví dụ `total: DECIMAL(19,2) → BigDecimal`, `attributes: jsonb → validated JSON/DTO`.
2. **Ưu tiên getter có kiểu khi biết schema.** `getBigDecimal`, `getString`, `getBlob`, `getArray`, `getObject(..., Class)` được kiểm thử.
3. **Cô lập vendor adapter.** Các class như `PGobject` không xuất hiện khắp domain/service, chỉ nằm ở một lớp hạ tầng có kiểm thử.
4. **Kiểm tra `NULL` rõ ràng.** Getter primitive như `getLong` trả giá trị mặc định khi SQL NULL; gọi `wasNull()` ngay sau getter.
5. **Không tự động gọi `toString()` của vendor object để parse dữ liệu.** Không phải mọi driver cam kết đây là định dạng round-trip.
6. **Không bắt `SQLException` rồi lặng lẽ dùng converter khác.** Lỗi SQL có thể do connection/permission/schema, không chỉ vì driver không hỗ trợ mapping.
7. **Giữ thông báo lỗi an toàn.** Log mã truy vấn cố định, tên field đã cho phép, SQLState được kiểm soát và loại lỗi; không log toàn bộ hàng, tham số SQL hay JSON payload.
8. **Kiểm soát bộ nhớ.** Với LOB/ARRAY/STRUCT, tránh materialize các đối tượng rất lớn nếu không cần.

### Lỗi ánh xạ khác lỗi truy cập database

Ví dụ, `ClassCastException` thường cho thấy ứng dụng đã giả định sai về class runtime. `SQLException` trong `getObject(index, SomeClass.class)` có thể cho thấy driver không hỗ trợ chuyển đổi, nhưng cũng có thể là lỗi từ kết nối hoặc dữ liệu. Không gộp mọi trường hợp thành thông báo “driver lỗi” rồi bỏ qua ngữ cảnh.

Nếu dùng `SQLException.getSQLState()` và `getErrorCode()` để điều tra, nên ghi trong kênh nội bộ theo chính sách, không đưa nguyên văn SQL hoặc message driver chưa kiểm soát ra phản hồi HTTP.

## 13. Quy trình khảo sát một kiểu SQL mới

Khi dự án thêm cột `jsonb`, kiểu vector, kiểu không gian hoặc UDT, làm theo trình tự:

~~~mermaid
flowchart TD
    A["1. Đọc định nghĩa cột/routine"] --> B["2. Ghi nhận driver + DBMS + version"]
    B --> C["3. Kiểm tra getColumnType/TypeName/ClassName"]
    C --> D["4. Đọc thử giá trị đại diện có và không NULL"]
    D --> E["5. Kiểm thử getXxx/getObject(Class) được hỗ trợ"]
    E --> F["6. Viết adapter chuyển sang domain type"]
    F --> G["7. Kiểm thử round-trip và trường hợp lỗi"]
    G --> H["8. Đo bộ nhớ/tài nguyên khi dữ liệu lớn"]
~~~

Không cần ngay lập tức thêm phụ thuộc riêng của driver nếu có cách truy cập qua API JDBC chuẩn hoặc truy vấn SQL được tham số hóa với kiểu đầu ra rõ ràng. Ngược lại, nếu cần khai thác dữ liệu chuyên biệt hiệu quả, phụ thuộc vendor adapter **được cô lập và kiểm thử** thường tốt hơn một chuỗi ép kiểu không có hợp đồng.

## 14. Kiểm thử tích hợp cho mapping chuẩn và vendor-specific

Một test chỉ dùng mock `ResultSet` sẽ xác nhận mapper gọi getter đúng nhưng **không chứng minh** driver thực tế trả class nào. Kiểm thử cần sử dụng database và driver thực sự.

| Trường hợp | Mục tiêu |
| --- | --- |
| `DECIMAL(19,2)` có `123.45` | Đọc `BigDecimal` chính xác, không qua `double` |
| `BIGINT` chứa `NULL` ở cột nullable | `getLong` + `wasNull` phân biệt SQL NULL với 0 |
| `DATE`, `TIMESTAMP` | Đọc bằng Java Time đúng nghĩa ngày giờ, kiểm tra timezone |
| `JSONB` có object/array/null | Metadata và runtime class phù hợp driver; adapter parse đúng |
| JSON sai cấu trúc nghiệp vụ | Converter báo lỗi hợp đồng, không log nguyên payload |
| UUID trong kiểu native hoặc `CHAR(36)` | Converter cho ra `UUID`; thử cả dữ liệu sai format |
| SQL `ARRAY` rỗng/NULL/có phần tử | Đọc đúng phần tử; `free()`; không nhầm NULL với array rỗng |
| `STRUCT` nhiều cấp | Xử lý thứ tự và null của thuộc tính; theo DBMS |
| `BLOB` lớn | Stream theo khối, không nạp toàn bộ vào RAM |
| `SQLXML` | Đọc và parse an toàn, dọn `free()` |
| Đổi phiên bản driver | Phát hiện thay đổi `getColumnClassName`/`getObject` nếu có |
| `getObject(..., Target.class)` không hỗ trợ | Adapter fallback đúng, không che giấu lỗi khác |
| Ghi lại giá trị đã đọc (round-trip) | Kiểm tra precision, timezone, schema và cách bind tham số |

Những test quan trọng nên ghi rõ **version driver, version DBMS, schema, kiểu cột và giá trị mong đợi**. Kết quả từ một JDBC driver không tự chứng minh tính di động sang driver khác.

### Checklist rà soát code

- [ ] Tôi phân biệt mã `Types`, tên SQL type và Java runtime class.
- [ ] Tôi có hợp đồng cột trước khi chọn getter và DTO.
- [ ] Tôi không xem `Types.OTHER` là một kiểu Java cụ thể.
- [ ] Tôi không cast kết quả `getObject` sang lớp không được driver bảo đảm.
- [ ] Tôi ưu tiên `getBigDecimal` cho số thập phân, không đánh mất precision.
- [ ] Tôi kiểm tra SQL NULL đúng cách, kể cả `wasNull()` với primitive.
- [ ] Tôi tách adapter vendor khỏi domain/API công khai.
- [ ] Tôi xử lý vòng đời `Blob`/`Clob`/`SQLXML`/`Array` nếu có.
- [ ] Tôi đã kiểm thử metadata, kiểu runtime, null và round-trip trên DBMS thật.
- [ ] Tôi không log giá trị nhạy cảm hoặc thông điệp driver chưa kiểm soát.

## 15. Bài tập tự luyện

**Bài 1 — Phân biệt ba kết quả.** Một cột PostgreSQL khai báo kiểu `jsonb`, `getColumnType` trả `Types.OTHER`, `getColumnTypeName` trả `jsonb` và `getObject` trả `PGobject`. Hãy giải thích vì sao ba kết quả này không mâu thuẫn.

**Bài 2 — Sửa phép cast.** Đoạn code sau hỏng ở một số driver:

~~~java
String payload = (String) rs.getObject("attributes");
~~~

Hãy đề xuất một cách đọc dựa trên adapter riêng cho pgJDBC hoặc một câu SQL PostgreSQL trả biểu diễn text đã được xác định kiểu, sau đó parse/validate JSON.

**Bài 3 — Kiểm tra `NULL`.** Cột `approved BOOLEAN` cho phép null. Làm sao trả `Boolean` gồm ba trạng thái `true`, `false` và `null` khi driver hỗ trợ `getBoolean`?

**Bài 4 — Mảng SQL.** Tại sao `(List<?>) rs.getObject("tags")` không phải giả định an toàn? API nào giúp làm việc với SQL ARRAY và cách giải phóng tài nguyên ra sao?

**Bài 5 — UUID/JSON/INTERVAL.** Một phiên bản driver mới đổi lớp runtime của `getObject("vendor_value")`. Cần sửa bao nhiêu lớp domain nếu ứng dụng thiết kế tốt? Nêu cách cô lập thay đổi trong adapter.

**Bài 6 — Kiểu thời gian.** Cột `TIMESTAMP WITHOUT TIME ZONE` có nên luôn được ánh xạ thành `Instant`? Điều gì còn thiếu khi chỉ có `LocalDateTime`?

**Gợi ý đáp án:** (1) Mỗi kết quả mô tả một tầng khác nhau: mã JDBC, tên kiểu DBMS và lớp runtime; (2) đọc qua adapter hoặc `attributes::text` có tham số truy vấn phù hợp; (3) `boolean value = rs.getBoolean(...)` rồi `rs.wasNull()` ngay sau đó; (4) dùng `getArray`/`Array.getResultSet` hoặc `getArray()`, gọi `free()`; (5) tốt nhất chỉ sửa adapter + test; (6) không, `LocalDateTime` không có `ZoneId`/offset, cần chính sách múi giờ và loại cột.

---

**Ghi nhớ:** `Types` và `JDBCType` định nghĩa **mã kiểu SQL trong giao thức JDBC**, còn `ResultSet.getObject` trả **giá trị Java do driver ánh xạ**. Hai khái niệm có liên quan nhưng không đồng nhất. Muốn hệ thống bền vững, hãy chọn getter theo hợp đồng schema, kiểm tra metadata khi cần, cô lập phụ thuộc vendor và kiểm thử kiểu runtime trên **DBMS/driver thực tế**.
