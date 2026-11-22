# Sử dụng `ParameterMetaData` và giới hạn hỗ trợ của JDBC driver

Trong JDBC, `PreparedStatement` cho phép truyền giá trị vào các dấu `?` của câu SQL bằng `setLong`, `setString`, `setBigDecimal` và những phương thức `setXxx` khác. Khi cần tìm hiểu **câu lệnh có bao nhiêu tham số, driver suy ra kiểu SQL nào cho mỗi tham số, tham số có thể nhận `NULL` hay không**, Java cung cấp giao diện `java.sql.ParameterMetaData`.

`ParameterMetaData` hữu ích khi xây công cụ chẩn đoán, kiểm tra tương thích driver, phát triển lớp truy cập dữ liệu hoặc phân tích câu SQL động. Tuy nhiên, metadata của tham số **không phải hợp đồng nghiệp vụ đáng tin cậy tuyệt đối**: nhiều thuộc tính có thể không xác định được trước khi thực thi câu lệnh, một số driver không hiện thực đầy đủ API, và một lời gọi metadata có thể phát sinh truy vấn bổ sung tới cơ sở dữ liệu.

Bài thuộc chương **Siêu dữ liệu** của module **JDBC**. Ta sẽ dùng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và `SQLException` để phân biệt thông tin tham số với dữ liệu truy vấn, xem ví dụ ghi dữ liệu thực tế và thiết kế cách xử lý khi driver không trả được metadata. Mục tiêu là biết **dùng metadata đúng chỗ mà vẫn giữ việc tham số hóa SQL và CRUD hoạt động an toàn**.

Sau bài học, bạn có thể:

- Lấy `ParameterMetaData` từ `PreparedStatement` và duyệt vị trí tham số bắt đầu từ **1**.
- Hiểu `getParameterCount`, `getParameterType`, `getParameterTypeName`, `getParameterClassName`, `getPrecision`, `getScale`, `isNullable`, `isSigned` và `getParameterMode`.
- Phân biệt `ParameterMetaData`, `ResultSetMetaData` và `DatabaseMetaData`.
- Xử lý `SQLFeatureNotSupportedException`, `SQLException` và những thuộc tính không được driver suy luận chính xác.
- Quyết định khi nào nên dựa vào schema/DDL và quy tắc ứng dụng thay vì tự suy đoán kiểu tham số từ metadata.

## 1. `ParameterMetaData` mô tả cái gì?

Xét câu SQL:

```sql
UPDATE product_catalog
SET product_name = ?, list_price = ?
WHERE product_id = ?;
```

Ba dấu `?` là ba **parameter marker** được sử dụng theo thứ tự xuất hiện trong câu lệnh:

| Vị trí JDBC | Vai trò | Kiểu ứng dụng kỳ vọng theo schema minh họa |
| ---: | --- | --- |
| `1` | Giá trị mới của `product_name` | `VARCHAR` → `String` |
| `2` | Giá trị mới của `list_price` | `DECIMAL(12,2)` → `BigDecimal` |
| `3` | `product_id` dùng trong điều kiện `WHERE` | `BIGINT` → `long` hoặc `Long` |

Ứng dụng gán giá trị qua `PreparedStatement`:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "Bàn phím cơ");
    statement.setBigDecimal(2, new BigDecimal("149.90"));
    statement.setLong(3, 501L);

    int affected = statement.executeUpdate();
}
```

Ở đoạn này, `ParameterMetaData` không cần thiết để thực thi `UPDATE`: ứng dụng đã biết hợp đồng kiểu từ **cấu trúc bảng** và **ý nghĩa tham số**. Nếu muốn quan sát driver mô tả ba dấu `?` như thế nào, có thể gọi:

```java
ParameterMetaData metadata = statement.getParameterMetaData();
int count = metadata.getParameterCount();
```

Với driver hỗ trợ đầy đủ và câu SQL trên, `count` được kỳ vọng là `3`. Nhưng thông tin kiểu/độ dài/khả năng `NULL` của từng tham số **có thể kém chính xác hơn thông tin số lượng dấu `?`**. Driver cần phân tích câu SQL hoặc hỏi DB để suy luận loại giá trị thích hợp; không phải biểu thức SQL nào cũng cung cấp đủ thông tin ấy.

Đặc biệt, `ParameterMetaData` mô tả **các marker của câu SQL đã chuẩn bị**, không mô tả những giá trị Java hiện tại do `setXxx` gán vào statement. Việc thay `setString(1, "A")` bằng `setString(1, "B")` không tạo thêm tham số hay thay đổi thứ tự các marker.

### Ba nhóm metadata cần phân biệt

| Loại JDBC metadata | Đối tượng sở hữu | Câu hỏi chính |
| --- | --- | --- |
| `ParameterMetaData` | `PreparedStatement` / `CallableStatement` | **Đầu vào** của câu SQL có bao nhiêu marker và driver biết gì về chúng? |
| `ResultSetMetaData` | `ResultSet` | **Đầu ra** của truy vấn có bao nhiêu cột, tên/kiểu/precision/scale nào? |
| `DatabaseMetaData` | `Connection` | DB/driver hỗ trợ tính năng nào; bảng, cột, khóa, procedure, phiên bản ra sao? |

Ví dụ `SELECT product_id, product_name FROM product_catalog WHERE product_id = ?` có **một** parameter marker nhưng **hai** cột trả về. Khi đó `ParameterMetaData.getParameterCount()` dự kiến là `1`, còn `ResultSetMetaData.getColumnCount()` dự kiến là `2`.

## 2. Các phương thức chính và cách diễn giải

`java.sql.ParameterMetaData` định nghĩa các phương thức sau:

| Phương thức | Trả về | Ý nghĩa / giới hạn cần nhớ |
| --- | --- | --- |
| `getParameterCount()` | `int` | Số marker mà driver báo cho câu lệnh đã chuẩn bị |
| `getParameterType(index)` | `int` | Mã kiểu SQL theo `java.sql.Types` của tham số ở vị trí `index` |
| `getParameterTypeName(index)` | `String` | Tên kiểu SQL theo cách driver/DB công bố; có thể mang tính riêng của sản phẩm |
| `getParameterClassName(index)` | `String` | Tên lớp Java mà metadata cho biết phù hợp khi truyền qua `setObject` |
| `getPrecision(index)` | `int` | Precision của tham số theo metadata; `0` có thể là không áp dụng |
| `getScale(index)` | `int` | Scale của tham số theo metadata; không nên coi là quy tắc làm tròn nghiệp vụ |
| `isNullable(index)` | `int` | Một trong ba hằng `parameterNoNulls`, `parameterNullable`, `parameterNullableUnknown` |
| `isSigned(index)` | `boolean` | Kiểu số theo metadata có dấu hay không |
| `getParameterMode(index)` | `int` | Vai trò `IN`, `OUT`, `INOUT` hoặc `UNKNOWN` mà driver báo |

Các phương thức truy cập tham số (trừ `getParameterCount`) dùng chỉ số từ **`1` đến `getParameterCount()`**, không phải từ `0`. Gọi `getParameterType(0)` hoặc chỉ số ngoài phạm vi có thể ném `SQLException`.

### Kiểu SQL và lớp Java không phải cùng một khái niệm

Ví dụ minh họa:

```java
int sqlType = metadata.getParameterType(2);
if (sqlType == java.sql.Types.DECIMAL
        || sqlType == java.sql.Types.NUMERIC) {
    // Theo metadata, tham số 2 dùng kiểu số thập phân SQL.
}

String databaseType = metadata.getParameterTypeName(2);
String javaClass = metadata.getParameterClassName(2);
```

`getParameterType` trả **mã SQL**; `getParameterClassName` trả tên **lớp Java** mà metadata gợi ý cho `setObject`. Chẳng hạn, tham số `DECIMAL` có thể đi cùng `java.math.BigDecimal`, nhưng không được giả định driver nào cũng trả chính xác giá trị này trong mọi câu SQL.

Khi biết rõ kiểu từ schema, lựa chọn `setBigDecimal(2, price)` thường minh bạch hơn việc đọc class name rồi dựng bộ chuyển đổi Java động. Mã `Types.DECIMAL` là một hằng JDBC; tên như `DECIMAL`, `NUMERIC`, `NUMBER` hoặc các kiểu do vendor đặt có thể được driver biểu diễn khác nhau.

### Nullable: ba trạng thái, không phải boolean

`isNullable(index)` dùng các hằng của `ParameterMetaData`:

```java
int nullable = metadata.isNullable(2);

if (nullable == ParameterMetaData.parameterNoNulls) {
    System.out.println("Driver reports NOT NULL");
} else if (nullable == ParameterMetaData.parameterNullable) {
    System.out.println("Driver reports nullable");
} else if (nullable == ParameterMetaData.parameterNullableUnknown) {
    System.out.println("Driver cannot determine nullability");
}
```

`parameterNullableUnknown` là **không biết**; không được diễn giải thành “cho phép NULL”. Ngay cả khi driver trả `parameterNullable`, điều đó cũng không thay thế schema và ràng buộc của bảng. Ví dụ một marker nằm trong biểu thức `COALESCE(?, column_name)` có thể được xử lý khác marker được gán trực tiếp cho cột `NOT NULL`.

Khi một giá trị thực sự phải ghi SQL `NULL`, hãy chọn kiểu từ hợp đồng cột rồi gọi `setNull(index, Types.VARCHAR)` hoặc `setObject(index, null, Types.VARCHAR)` theo API và driver được hỗ trợ. Không cần lấy kiểu bằng `getParameterType` trước mỗi câu lệnh ghi.

### Precision, scale và dấu

Giả sử schema chứa `list_price DECIMAL(12, 2)`. Metadata của tham số gán trực tiếp vào cột này **có thể** báo precision `12`, scale `2`. Hai giá trị ấy không đảm bảo luôn được báo như vậy, đặc biệt với biểu thức toán học, `CAST`, toán tử, procedure và driver suy luận kiểu không đầy đủ.

```java
int precision = metadata.getPrecision(2);
int scale = metadata.getScale(2);
boolean signed = metadata.isSigned(2);
```

Nếu `precision == 0` hoặc `scale == 0`, đừng vội kết luận “driver lỗi” hoặc “kiểu số không có phần thập phân”: theo API, `0` có thể biểu thị thông số **không áp dụng**; ở một số môi trường nó cũng xuất hiện khi metadata không đủ chi tiết. Để kiểm tra dữ liệu có thể lưu vừa `DECIMAL(12,2)`, hãy dùng **định nghĩa cột** và `BigDecimal`, với chính sách làm tròn của nghiệp vụ; đừng dùng một giá trị `scale` không rõ từ metadata làm quy tắc tính tiền.

`isSigned` chỉ phản ánh khả năng biểu diễn số có dấu theo metadata, **không** cho biết cột nghiệp vụ có cho phép giá trị âm hay không. Một cột `DECIMAL(12,2)` có thể có `CHECK (list_price >= 0)` dù kiểu số bản thân nó hỗ trợ số âm.

### Mode của tham số

`getParameterMode(index)` có thể trả:

```java
ParameterMetaData.parameterModeIn
ParameterMetaData.parameterModeOut
ParameterMetaData.parameterModeInOut
ParameterMetaData.parameterModeUnknown
```

Các dấu `?` của một `PreparedStatement` dùng cho `INSERT`, `UPDATE` hay điều kiện `WHERE` thông thường là **tham số đầu vào**. Mode hữu ích hơn khi nghiên cứu `CallableStatement` gọi stored procedure với tham số `IN`, `OUT`, `INOUT`. Tuy vậy, `getParameterMode` cũng có thể trả `UNKNOWN` hoặc không được hỗ trợ. Khi gọi procedure thật, hãy dùng chữ ký procedure đã biết và `registerOutParameter(...)` đúng kiểu, thay vì mong chờ metadata luôn tự khám phá mọi OUT parameter.

## 3. Đọc metadata một cách an toàn

Để quan sát các marker của SQL, một chương trình thử nghiệm có thể tạo `PreparedStatement`, lấy `ParameterMetaData` và in thông tin theo chỉ số:

```java
import java.sql.Connection;
import java.sql.ParameterMetaData;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ParameterMetadataDemo {
    private ParameterMetadataDemo() {}

    public static void inspect(DataSource dataSource) throws SQLException {
        String sql = """
                UPDATE product_catalog
                SET product_name = ?, list_price = ?
                WHERE product_id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            ParameterMetaData metadata = statement.getParameterMetaData();
            int count = metadata.getParameterCount();
            System.out.println("Parameter count = " + count);

            for (int index = 1; index <= count; index++) {
                System.out.println("Parameter #" + index);
                System.out.println("  SQL type code: "
                        + metadata.getParameterType(index));
                System.out.println("  SQL type name: "
                        + metadata.getParameterTypeName(index));
                System.out.println("  Java class: "
                        + metadata.getParameterClassName(index));
                System.out.println("  Precision: "
                        + metadata.getPrecision(index));
                System.out.println("  Scale: "
                        + metadata.getScale(index));
                System.out.println("  Nullable code: "
                        + metadata.isNullable(index));
                System.out.println("  Parameter mode code: "
                        + metadata.getParameterMode(index));
            }
        }
    }
}
```

Đây là **ví dụ khảo sát**, không phải mã bắt buộc trong luồng ghi dữ liệu sản xuất. Trên driver hỗ trợ đầy đủ, nó có thể in ba tham số. Trên driver không hỗ trợ một phương thức metadata, lời gọi có thể phát sinh `SQLFeatureNotSupportedException` hoặc `SQLException` khác. Đặc biệt, việc gọi `getParameterMetaData()` thành công **không bảo đảm** mọi getter của đối tượng metadata đều được hỗ trợ.

Trong chương trình khảo sát, ta nên ghi rõ **tên DB, phiên bản DB, tên driver và phiên bản driver** (có thể đọc từ `Connection.getMetaData()`) để so sánh kết quả giữa các môi trường. Không nên sao chép các giá trị in từ một máy vào tài liệu như một chuẩn bắt buộc cho mọi DBMS.

## 4. Ví dụ thực hành: câu `INSERT` vẫn chạy khi metadata không có

Mục đích chính của `PreparedStatement` là **truyền dữ liệu tham số hóa an toàn**, còn việc introspection là tùy chọn. Một repository nên có hợp đồng kiểu dữ liệu dựa trên schema và vẫn sử dụng được nếu driver không trả `ParameterMetaData`.

Giả sử bảng có cấu trúc:

```sql
CREATE TABLE product_catalog (
    product_id   BIGINT PRIMARY KEY,
    product_name VARCHAR(120) NOT NULL,
    list_price   DECIMAL(12, 2) NOT NULL,
    description  VARCHAR(500) NULL,
    CHECK (list_price >= 0)
);
```

`product_id`, `product_name` và `list_price` là các giá trị bắt buộc. `description` có thể `NULL`. Những quy tắc này đến từ **schema**, không cần đợi `ParameterMetaData.isNullable()` mới được quyết định.

Tệp minh họa `CatalogWriter.java` (Java 17 trở lên để dùng SQL text block):

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.ParameterMetaData;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Objects;
import javax.sql.DataSource;

public final class CatalogWriter {
    private static final String INSERT = """
            INSERT INTO product_catalog
                (product_id, product_name, list_price, description)
            VALUES (?, ?, ?, ?)
            """;

    private final DataSource dataSource;

    public CatalogWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public void insert(
            long id, String name, BigDecimal rawPrice, String description)
            throws SQLException {

        Objects.requireNonNull(name, "name");
        Objects.requireNonNull(rawPrice, "rawPrice");

        if (id <= 0 || name.isBlank() || name.length() > 120) {
            throw new IllegalArgumentException("Invalid product ID or name");
        }

        // Không tự làm tròn giá: chỉ cho phép bỏ số 0 dư.
        final BigDecimal price;
        try {
            price = rawPrice.setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Price cannot be represented exactly with scale 2", ex);
        }

        if (price.signum() < 0 || price.precision() > 12) {
            throw new IllegalArgumentException("Price exceeds DECIMAL(12,2)");
        }
        if (description != null && description.length() > 500) {
            throw new IllegalArgumentException("Description is too long");
        }

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(INSERT)) {

            // Bước tùy chọn: chỉ để quan sát, không quyết định việc gán giá trị.
            inspectParameterCountIfAvailable(statement);

            // Bước chính: dựa trên schema và thứ tự placeholder đã biết.
            statement.setLong(1, id);
            statement.setString(2, name);
            statement.setBigDecimal(3, price);

            if (description == null) {
                statement.setNull(4, Types.VARCHAR);
            } else {
                statement.setString(4, description);
            }

            int affected = statement.executeUpdate();
            if (affected != 1) {
                throw new SQLException(
                        "Expected one inserted product, got " + affected);
            }
        }
    }

    private static void inspectParameterCountIfAvailable(
            PreparedStatement statement) {
        try {
            ParameterMetaData metadata = statement.getParameterMetaData();
            System.out.println("Driver reports parameter count: "
                    + metadata.getParameterCount());
        } catch (SQLException inspectionError) {
            // Metadata chỉ phục vụ quan sát. Không che giấu lỗi executeUpdate.
            // Ứng dụng thật nên dùng logger thay vì System.err.
            System.err.println("Parameter metadata unavailable: "
                    + inspectionError.getClass().getSimpleName());
        }
    }
}
```

Cách gọi:

```java
CatalogWriter writer = new CatalogWriter(dataSource);
writer.insert(
        501L,
        "Bàn phím cơ",
        new BigDecimal("149.90"),
        null);
```

Ví dụ gọi `inspectParameterCountIfAvailable` **để minh họa khả năng fallback**. Trong mã sản xuất thông thường, có thể bỏ hẳn bước introspection vì đã biết đúng bốn placeholder. Nếu metadata không hỗ trợ, phương thức ghi vẫn gán đủ tham số và thực thi. Nhưng nếu `setLong`, `setNull` hoặc `executeUpdate` ném `SQLException`, lỗi **vẫn được truyền lên caller**; đừng nhầm việc bỏ qua lỗi metadata tùy chọn với việc bỏ qua lỗi ghi dữ liệu.

Ngoài ra, việc in tên lớp lỗi thay vì toàn bộ SQL hoặc giá trị người dùng giúp hạn chế lộ dữ liệu trong log. Khi cần chẩn đoán sâu, dùng công cụ log có kiểm soát và không ghi mật khẩu, khóa truy cập, dữ liệu cá nhân hoặc các giá trị bí mật vào thông báo.

### Vì sao không tự động chọn setter dựa vào metadata?

Giả sử `getParameterType(3)` báo `Types.OTHER` hoặc ném ngoại lệ. Điều đó **không có nghĩa** cột `list_price` chuyển thành kiểu Java khác hay cần gọi `setObject(3, price.toString())`. Ứng dụng biết `list_price` là `DECIMAL(12,2)` nên vẫn dùng `setBigDecimal(3, price)`. Nếu dữ liệu `description` là `NULL`, ứng dụng biết cột là `VARCHAR` nên dùng `setNull(4, Types.VARCHAR)`.

`ParameterMetaData` có thể dùng để **so sánh, cảnh báo, ghi log, kiểm tra thiết bị**. Nó không nên là cơ sở duy nhất cho một cơ chế chuyển đổi kiểu dữ liệu trong ứng dụng đang có schema rõ ràng. Với nền tảng truy vấn động thực sự, cần định nghĩa quy tắc fallback, kiểm thử driver và xử lý hợp đồng schema cẩn thận.

## 5. Khi nào driver khó xác định kiểu tham số?

Không phải mọi dấu `?` đều xuất hiện ở vị trí có thể suy ra kiểu SQL rõ ràng. Xem những trường hợp sau:

| Câu SQL minh họa | Khó khăn có thể gặp |
| --- | --- |
| `INSERT INTO t(amount) VALUES (?)` | Thường có ngữ cảnh từ kiểu cột `amount`; mức độ hỗ trợ vẫn phụ thuộc DB/driver |
| `SELECT * FROM t WHERE id = ?` | Có thể suy ra kiểu từ `id`, nhưng driver có thể không phân tích hoặc hỏi DB |
| `SELECT ?` | Marker đứng độc lập, không có cột đích để suy ra kiểu |
| `SELECT * FROM t WHERE ? IS NULL` | Biểu thức không cung cấp rõ kiểu của marker; một số DB còn từ chối chuẩn bị câu lệnh nếu không có khai báo kiểu |
| `SELECT COALESCE(?, name) FROM t` | Quy tắc ép kiểu hàm, biểu thức và DB có thể khiến kiểu tham số mơ hồ |
| `SELECT ? + ?` | Kiểu số và kết quả phụ thuộc quy tắc suy luận kiểu của DB |
| `CALL do_work(?, ?)` | Chữ ký procedure, mode IN/OUT, cú pháp gọi và khả năng metadata không đồng nhất |

Một số hệ quản trị cho phép thêm `CAST` rõ kiểu để giải quyết tính mơ hồ, chẳng hạn `CAST(? AS DECIMAL(12,2))`. Cú pháp và cách suy luận kiểu trong biểu thức cần được kiểm tra trên hệ quản trị thực tế. Đây là giải pháp cho **hợp đồng SQL**, không phải một mẹo để buộc mọi driver trả đủ `ParameterMetaData`.

Đặc biệt, không phải dấu hỏi trong văn bản SQL nào cũng là parameter marker. Dấu `?` nằm trong **literal chuỗi** không trở thành tham số:

```sql
SELECT product_name
FROM product_catalog
WHERE product_name = '?' OR product_id = ?;
```

Với cú pháp SQL thông thường, marker chỉ là dấu `?` thứ hai. Tuy nhiên, một số DB có toán tử sử dụng ký tự `?` hoặc cú pháp riêng khiến việc phân tích cần theo đúng quy tắc của driver. Đừng tự đếm ký tự `?` bằng thao tác chuỗi Java để thay `getParameterCount()`; cách đó không phân biệt literal, comment, toán tử hoặc cú pháp vendor.

## 6. Thiếu hỗ trợ là tình huống cần dự liệu

`PreparedStatement.getParameterMetaData()` và các phương thức trên đối tượng trả về có thể ném `SQLFeatureNotSupportedException` hoặc `SQLException` khi driver không hỗ trợ, không suy luận được metadata hoặc phát sinh lỗi khi trao đổi với DB. Một số driver chỉ hỗ trợ đếm marker nhưng không cung cấp chi tiết type/precision/nullable.

| Tình huống | Cách hiểu | Hướng xử lý |
| --- | --- | --- |
| `getParameterMetaData()` ném `SQLFeatureNotSupportedException` | Driver không hiện thực tính năng được yêu cầu | Bỏ bước metadata tùy chọn; gán tham số theo hợp đồng SQL |
| `getParameterCount()` hoạt động, getter kiểu ném ngoại lệ | Có hỗ trợ một phần | Chỉ dùng những thuộc tính đã kiểm chứng, không coi phần còn lại là bắt buộc |
| `getParameterType` trả kiểu chung hoặc vendor-specific | Thông tin chưa đủ để suy luận setter | Lấy kiểu từ schema/DDL hoặc hợp đồng câu SQL |
| `isNullable` trả `parameterNullableUnknown` | Driver không xác định được khả năng NULL | Dựa vào schema và quy tắc ứng dụng |
| `getPrecision` hoặc `getScale` báo `0` | Có thể không áp dụng hoặc không đủ chi tiết trong ngữ cảnh | Không tự suy ra độ chính xác nghiệp vụ |
| Metadata lấy chậm dù SQL đơn giản | Có thể tốn lượt trao đổi để driver hỏi server | Đo đạc; tránh gọi mỗi lần xử lý hàng khi không cần |
| DB/driver nâng cấp làm metadata thay đổi | Quy tắc phân tích và mô tả kiểu có thể đã đổi | Chạy lại integration test và ghi nhận phiên bản |

**JDBC không cung cấp một cờ `DatabaseMetaData.supportsParameterMetaData()` chuẩn để khẳng định mọi phương thức đều khả dụng.** Không tự gọi tên phương thức giả định đó. Hãy kiểm thử những lời gọi cụ thể dự kiến dùng và xử lý `SQLException` tương ứng. Các khả năng metadata khác như `supportsBatchUpdates()` hoặc `supportsStoredProcedures()` giải quyết câu hỏi khác, không thay thế phép kiểm tra cho `ParameterMetaData`.

Một cách kiểm tra **từng thuộc tính** trong công cụ chẩn đoán là tách các lời gọi, vì getter thứ nhất thành công không bảo đảm getter kế tiếp sẽ chạy được:

```java
ParameterMetaData pm = statement.getParameterMetaData();
int count = pm.getParameterCount();

for (int index = 1; index <= count; index++) {
    try {
        System.out.println("#" + index + " type="
                + pm.getParameterType(index));
    } catch (SQLException typeError) {
        System.out.println("#" + index + " type unavailable");
    }

    try {
        System.out.println("#" + index + " nullability="
                + pm.isNullable(index));
    } catch (SQLException nullableError) {
        System.out.println("#" + index + " nullability unavailable");
    }
}
```

Đây là logic **điều tra đặc tính driver**. Nếu `getParameterMetaData()` hoặc `getParameterCount()` ném ngoại lệ, khối bao bên ngoài cũng phải xử lý; ví dụ này giả định hai lời gọi đầu đã thành công. Không nên cài vòng lặp introspection trong mọi lần gọi CRUD chỉ để tạo log metadata giống nhau.

### Ngoại lệ phải được phân biệt theo mục đích

- **Lỗi metadata tùy chọn:** nếu không ảnh hưởng tính đúng đắn của câu SQL, có thể ghi nhận và tiếp tục thực thi bằng setter đã xác định từ schema.
- **Lỗi chuẩn bị hoặc thực thi câu SQL:** cần được báo lên tầng gọi; không được che giấu dưới nhãn “driver không hỗ trợ metadata”.
- **Lỗi thiết kế hợp đồng tham số:** ví dụ quên `setXxx` cho một marker, dùng sai thứ tự, gán số tiền không vừa cột; phải sửa ứng dụng hoặc dữ liệu, không được bỏ qua chỉ vì metadata có vẻ thiếu chính xác.

## 7. Số tham số, kiểu `NULL` và `CallableStatement`

### Đếm marker có ích nhưng không thay thế kiểm tra hợp đồng

Giả sử một câu `INSERT` có bốn dấu `?`. Khi driver trả số đếm đúng, có thể dùng để phát hiện sự khác biệt giữa SQL và cấu hình tham số:

```java
ParameterMetaData pm = statement.getParameterMetaData();
int actualCount = pm.getParameterCount();

if (actualCount != 4) {
    throw new IllegalStateException(
            "Expected 4 SQL parameters, driver reported " + actualCount);
}
```

Đoạn kiểm tra này chỉ thích hợp **khi chương trình yêu cầu và đã xác minh driver hỗ trợ chính xác**. Nếu metadata là tùy chọn như `CatalogWriter`, nên ghi cảnh báo thay vì tự từ chối một thao tác ghi hợp lệ do driver báo giá trị bất thường. Dù có đếm đúng bốn marker, phương thức vẫn có thể gán **sai kiểu hoặc sai vị trí**; đó không phải điều `getParameterCount()` có thể tự kiểm tra toàn bộ.

Trong những truy vấn động được tạo bởi builder, một giải pháp thường ổn định hơn là **builder đồng thời tạo SQL và danh sách giá trị/kiểu tham số tương ứng**, sau đó gán theo danh sách đó. Như vậy ứng dụng biết số lượng tham số từ chính cấu trúc mình tạo, còn metadata là phép kiểm tra chéo nếu môi trường hỗ trợ.

### Gán `NULL` rõ kiểu

Giả sử `description` ở SQL là `VARCHAR(500) NULL`:

```java
if (description == null) {
    statement.setNull(4, java.sql.Types.VARCHAR);
} else {
    statement.setString(4, description);
}
```

Đừng suy đoán `Types.NULL` là kiểu cột vì ứng dụng đang truyền `null`. `Types.NULL` chỉ là mã kiểu SQL dành cho giá trị `NULL` trong ngữ cảnh JDBC; nhiều DB cần **kiểu đích cụ thể** để xử lý marker. Với `setObject(index, null)` không có khai báo kiểu, hành vi suy luận có thể không đồng nhất, đặc biệt trong biểu thức SQL mơ hồ. Dựa vào schema để truyền kiểu phù hợp giúp tăng tính tương thích.

### Stored procedure với `IN`, `OUT`, `INOUT`

Với một `CallableStatement`, driver có thể công bố `getParameterMode(index)`. Tuy vậy, logic gọi thủ tục vẫn nên xuất phát từ chữ ký đã biết:

```java
// Giả sử stored procedure có IN BIGINT và OUT INTEGER.
try (CallableStatement call = connection.prepareCall(
        "{call get_product_status(?, ?)}")) {
    call.setLong(1, productId);
    call.registerOutParameter(2, java.sql.Types.INTEGER);
    call.execute();

    int status = call.getInt(2);
    if (call.wasNull()) {
        // Xử lý SQL NULL theo hợp đồng OUT parameter.
    }
}
```

`get_product_status` là procedure giả định dùng để minh họa API, không phải một phần của DDL `product_catalog` phía trên. Đừng sử dụng `ParameterMetaData.getParameterMode()` làm cơ chế duy nhất để quyết định `registerOutParameter`: metadata có thể trả `parameterModeUnknown`, và hành vi trả OUT parameter khác nhau giữa DBMS. Nếu procedure đồng thời trả nhiều `ResultSet` hoặc update count, cần xử lý các kết quả đó theo hợp đồng `CallableStatement` trước khi trông chờ OUT parameter sẵn sàng trên mọi driver.

## 8. So sánh kiểm tra `ParameterMetaData` với schema thực tế

Một công cụ kiểm tra có thể dùng ba nguồn thông tin khác nhau:

```text
Hợp đồng ứng dụng / migration
          |  Kiểu cột, nullable, precision, scale
          v
    PreparedStatement
          |  getParameterMetaData()
          v
    Metadata driver  ------>  Báo cáo so sánh
          ^                         |
          |                         v
 Connection.getMetaData()    Xác minh bằng integration test
          |
    DatabaseMetaData
          |  getColumns(...)
          v
    Thông tin cột của DB
```

`DatabaseMetaData.getColumns(catalog, schemaPattern, tableNamePattern, columnNamePattern)` trả một `ResultSet` chứa thông tin cột như `DATA_TYPE`, `TYPE_NAME`, `COLUMN_SIZE`, `DECIMAL_DIGITS` và `NULLABLE`. Đây là thông tin về **cột bảng**; không đồng nhất với cách driver diễn giải marker trong một biểu thức SQL cụ thể. Ví dụ, hai dấu `?` cùng được so sánh với cột `DECIMAL` có thể nằm trong các phép toán khiến kiểu trung gian khác kiểu lưu trữ.

Để so sánh, cần biết tên schema/catalog và quy tắc chữ hoa/chữ thường của DB; chúng không được chuẩn hóa hoàn toàn giữa các sản phẩm. Cần dùng `try-with-resources` cho `ResultSet` metadata như với kết quả truy vấn thông thường.

Ví dụ lấy thông tin cột (chỉ minh họa cách dùng API):

```java
var dbMeta = connection.getMetaData();

try (ResultSet columns = dbMeta.getColumns(
        connection.getCatalog(),
        null,
        "product_catalog",
        "list_price")) {

    while (columns.next()) {
        System.out.println("SQL type: " + columns.getInt("DATA_TYPE"));
        System.out.println("Type name: " + columns.getString("TYPE_NAME"));
        System.out.println("Column size: " + columns.getInt("COLUMN_SIZE"));
        System.out.println("Decimal digits: "
                + columns.getInt("DECIMAL_DIGITS"));
    }
}
```

Trong DB thật, `getColumns` có thể không trả hàng nếu catalog, schema pattern hoặc tên bảng không phù hợp; cần điều chỉnh tham số theo cách DB lưu tên định danh. Ví dụ không phải “lấy dữ liệu mặc định bất kể DB”; nó minh họa **đường kiểm chứng schema** khi muốn đối chiếu metadata tham số.

### `ResultSetMetaData` chỉ phản ánh đầu ra

```java
String query = "SELECT product_id, list_price FROM product_catalog "
        + "WHERE product_id = ?";

try (PreparedStatement statement = connection.prepareStatement(query)) {
    statement.setLong(1, 501L);

    try (ResultSet rs = statement.executeQuery()) {
        ResultSetMetaData resultMeta = rs.getMetaData();
        System.out.println(resultMeta.getColumnCount()); // Kỳ vọng: 2.
    }

    ParameterMetaData parameterMeta = statement.getParameterMetaData();
    System.out.println(parameterMeta.getParameterCount()); // Kỳ vọng: 1, nếu hỗ trợ.
}
```

`ResultSetMetaData` không cho biết cách gán giá trị vào `?`, còn `ParameterMetaData` không cho biết dữ liệu mỗi hàng của `SELECT`. Hai API giải quyết hai hướng khác nhau của truy vấn. Đoạn mã trên là ví dụ dùng metadata trong môi trường hỗ trợ; nếu mục đích duy nhất là đọc dữ liệu, việc gọi `getParameterMetaData()` sau khi thực thi là không cần thiết.

## 9. Tính tương thích, hiệu năng và bảo mật

### Không giả định metadata miễn phí

Để trả thông tin kiểu của các marker, driver có thể cần phân tích SQL hoặc gửi yêu cầu metadata tới server. Điều này có thể phát sinh thêm thời gian chờ, nhất là khi ứng dụng chuẩn bị nhiều câu SQL khác nhau hoặc tạo nhiều statement trên mỗi request. Khi tối ưu đường xử lý CRUD, **đo thời gian thật** trước khi gọi `getParameterMetaData()` trong hot path.

Nếu schema và câu SQL là cố định, mã truy cập dữ liệu thường đã biết số placeholder và kiểu tham số. Khi ấy, `getParameterMetaData()` phù hợp hơn với **chẩn đoán, kiểm tra tương thích và công cụ phát triển**. Nếu xây một công cụ truy vấn động, có thể cache metadata theo câu SQL/phiên bản schema khi được chứng minh an toàn, nhưng cần xử lý thay đổi schema, driver và cấu hình kết nối.

### Metadata không thay thế SQL tham số hóa

Giả sử mã muốn đổi tên cột từ `product_name` sang `description`. Placeholder `?` chỉ đại diện cho **giá trị**, không đại diện cho tên bảng/cột hay toàn bộ cú pháp SQL:

```java
// ĐÚNG: SQL cố định, giá trị từ người dùng được gán qua setter.
String sql = "SELECT product_id FROM product_catalog WHERE product_name = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, userInput);
    try (ResultSet rs = statement.executeQuery()) {
        // Đọc hàng kết quả.
    }
}
```

`ParameterMetaData` không kiểm tra SQL injection, không thực hiện escape và không biến việc ghép giá trị vào SQL thành an toàn. Phải tiếp tục dùng `PreparedStatement` và `setXxx`. Nếu ứng dụng chọn tên cột động, dùng **danh sách tên đã cho phép** từ mã ứng dụng; không truyền một chuỗi tên cột bất kỳ của người dùng vào cấu trúc SQL.

### Không coi metadata là công cụ kiểm tra hợp lệ dữ liệu đầu vào

Ngay cả khi driver báo tham số thứ hai thuộc kiểu `DECIMAL(12,2)`, điều đó không giải thích quy tắc **làm tròn tiền**, miền giá trị hợp lệ hay yêu cầu không âm của sản phẩm. Ví dụ, `DECIMAL(12,2)` có thể nhận số âm về mặt kiểu SQL trong khi ràng buộc `CHECK (list_price >= 0)` từ chối giá âm. Các quy tắc nghiệp vụ cần kiểm tra trong Java và bằng constraint ở DB.

Tương tự, `isNullable` của marker không thay thế `NOT NULL` trên cột. `getParameterClassName` không đảm bảo một lớp Java cụ thể luôn được chuyển đổi đúng trong mọi môi trường. Với các kiểu ngày giờ, JSON, array, UUID hoặc kiểu riêng của DB, đặc biệt cần thử nghiệm cặp **getter/setter JDBC + driver** thực tế, không chỉ nhìn tên kiểu trong metadata.

## 10. Kiểm thử khả năng hỗ trợ với driver đích

Một bảng kiểm thử thực tế nên bao gồm cả câu SQL dễ suy luận kiểu và câu SQL khó suy luận, đồng thời so sánh kết quả trên đúng DB/driver triển khai:

| Trường hợp | Cách thử | Điều cần xác minh |
| --- | --- | --- |
| Câu `INSERT` bốn tham số | `getParameterCount()` trên SQL ví dụ | Driver có trả `4` hay không |
| SQL `UPDATE` với `DECIMAL(12,2)` | Đọc `getParameterType/Precision/Scale` | Báo đúng, báo chung chung hay không hỗ trợ? |
| Marker gán vào cột `NOT NULL` | Gọi `isNullable(index)` | Trả `parameterNoNulls` hay `parameterNullableUnknown`? |
| Marker trong `WHERE ? IS NULL` | Chuẩn bị statement và lấy metadata | DB có chấp nhận SQL và suy ra kiểu không? |
| Câu `SELECT ?` | Lấy kiểu marker | Có cần `CAST` để xác định kiểu không? |
| Chỉ hỗ trợ một phần metadata | Thử từng getter của `ParameterMetaData` | Getter nào ném `SQLException` hoặc `SQLFeatureNotSupportedException`? |
| Không dùng metadata | Bind giá trị với `setXxx`, `executeUpdate` | CRUD vẫn thành công theo schema đã biết |
| `description = null` | `setNull(4, Types.VARCHAR)` | Có thể chèn hàng và đọc lại `NULL` đúng không? |
| Giá tiền quá scale hoặc precision | Kiểm tra Java/DB trước và khi ghi | Có từ chối đúng hợp đồng nghiệp vụ không? |
| Nâng cấp phiên bản driver | Chạy lại cùng bộ câu SQL | Metadata hay hành vi chuẩn bị/thực thi thay đổi thế nào? |

Khi chạy test, ghi nhận tên và phiên bản DBMS, tên và phiên bản JDBC driver cùng trạng thái của từng getter. Đừng chỉ kiểm tra **không ném ngoại lệ**: một driver có thể trả giá trị `UNKNOWN`, `0` hoặc kiểu chung chung mà vẫn hoàn toàn hợp lệ trong ngữ cảnh giới hạn hỗ trợ.

Một số lỗi cần phân biệt trong báo cáo test:

- **`SQLFeatureNotSupportedException`**: tính năng hoặc lời gọi chưa được driver hỗ trợ.
- **`SQLException` khác khi lấy metadata**: có thể do SQL không hợp lệ, kết nối, quyền, server hoặc giới hạn riêng của driver; cần giữ SQLState/mã lỗi để chẩn đoán.
- **`SQLException` khi `setXxx` hoặc `executeUpdate()`**: lỗi thực thi dữ liệu, không thể kết luận chỉ từ metadata thiếu hỗ trợ.
- **Chênh lệch so với schema**: có thể vì biểu thức SQL, suy luận của DB hoặc cách driver thể hiện kiểu; cần điều tra trước khi áp dụng logic tự sửa.

Để giữ bài kiểm thử có ý nghĩa, dùng cả **integration test trên DB thật** và những phép kiểm tra đơn giản cho lớp xác thực dữ liệu Java. Mock `ParameterMetaData` có thể kiểm tra nhánh xử lý ngoại lệ, nhưng không thể chứng minh driver thật suy ra kiểu tham số như thế nào.

## 11. Những lỗi thiết kế thường gặp

| Cách làm | Vì sao có vấn đề? | Cách xử lý |
| --- | --- | --- |
| Đánh chỉ số `getParameterType(0)` | Tham số JDBC bắt đầu từ 1 | Duyệt từ `1` đến `getParameterCount()` |
| Dùng số dấu `?` trong chuỗi để đếm marker | Có literal, comment hoặc toán tử vendor | Dựa vào SQL builder hoặc `getParameterCount` đã kiểm chứng |
| Giả định mọi getter chạy vì `getParameterMetaData` chạy | Driver có thể hỗ trợ metadata từng phần | Kiểm tra từng thuộc tính cần dùng và xử lý lỗi |
| Dựa vào `getParameterTypeName` để luôn chọn setter | Kiểu vendor-specific hoặc không xác định | Dựa vào schema, DDL và `setXxx` đúng hợp đồng |
| Coi `parameterNullableUnknown` là nullable | “Không biết” khác “cho phép NULL” | Kiểm tra ràng buộc cột và quy tắc đầu vào |
| Coi `scale = 0` luôn nghĩa cột là số nguyên | `0` có thể không áp dụng hoặc metadata không đủ chi tiết | Kiểm tra schema và kiểu dữ liệu thực tế |
| Dùng `setObject(index, null)` cho mọi kiểu | Một số DB cần kiểu SQL đích để suy luận `NULL` | Dùng `setNull(index, Types.X)` theo schema |
| Chạy introspection cho mỗi request CRUD | Tăng overhead, đôi khi thêm round trip | Chỉ dùng ở nơi cần chẩn đoán hoặc đã đo hiệu năng |
| Nuốt mọi `SQLException` vì cho rằng đều là lỗi metadata | Có thể che giấu lỗi thực thi SQL thực sự | Chỉ fallback cho bước metadata tùy chọn; giữ lỗi ghi dữ liệu |
| Tin rằng `getParameterMode` tự khám phá mọi OUT parameter | Procedure/driver có thể không công bố mode | Dùng chữ ký thủ tục và `registerOutParameter` rõ ràng |
| Dùng metadata để kiểm tra an toàn SQL injection | Metadata không tham số hóa dữ liệu | Tiếp tục dùng placeholder và setter |

## 12. Bài tập tự kiểm tra

**Bài 1 — Đếm tham số.** Với truy vấn:

```sql
SELECT product_id, product_name
FROM product_catalog
WHERE list_price >= ? AND product_name = ?;
```

`ParameterMetaData.getParameterCount()` được kỳ vọng trả bao nhiêu? `ResultSetMetaData.getColumnCount()` của kết quả truy vấn được kỳ vọng là bao nhiêu?

**Đáp án:** Có hai parameter marker và hai cột kết quả. Hai con số bằng nhau trong trường hợp này **chỉ là trùng hợp**; chúng mô tả hai hướng dữ liệu khác nhau.

**Bài 2 — Không suy ra từ metadata.** Driver trả `parameterNullableUnknown` cho marker của `product_name`, trong khi schema khai báo `product_name VARCHAR(120) NOT NULL`. Ứng dụng có được tự chèn `NULL` vì metadata không cấm không?

**Đáp án:** Không. `UNKNOWN` không cho phép bỏ qua ràng buộc `NOT NULL`; phải dùng schema và kiểm tra đầu vào.

**Bài 3 — Giới hạn hỗ trợ.** `getParameterMetaData()` thành công, `getParameterCount()` trả `4`, nhưng `getParameterType(3)` ném `SQLFeatureNotSupportedException`. Có bắt buộc hủy lệnh `INSERT` nếu giá tiền đã biết là `DECIMAL(12,2)` không?

**Đáp án:** Không, nếu metadata chỉ phục vụ quan sát và ứng dụng đã có hợp đồng kiểu đúng. Có thể dùng `setBigDecimal(3, price)` rồi thực thi; nhưng lỗi tại bước ghi vẫn phải được xử lý bình thường.

**Bài 4 — Precision và scale.** Vì sao `getScale(3) == 0` không đủ để khẳng định cột giá tiền không có hai chữ số thập phân?

**Đáp án:** Đó là giá trị metadata của **tham số**, có thể không áp dụng hoặc thiếu thông tin. Cần đối chiếu schema `DECIMAL(12,2)` và kiểm chứng DB/driver.

**Bài 5 — `NULL` có kiểu.** `description` là `VARCHAR(500) NULL`. Khi giá trị Java là `null`, nên dùng `setNull(4, Types.VARCHAR)` hay đọc `getParameterClassName(4)` rồi tự chọn kiểu khác?

**Đáp án:** Dùng `setNull(4, Types.VARCHAR)` theo schema. Metadata không phải nguồn quyết định kiểu khi hợp đồng SQL đã rõ.

**Bài 6 — Thử driver.** Một framework tự động xây `INSERT` và muốn dùng metadata để kiểm tra mọi tham số. Hãy mô tả cách nó nên hoạt động nếu driver A trả đầy đủ kiểu, driver B chỉ trả số lượng, driver C ném ngoại lệ ngay khi `getParameterMetaData()`.

**Gợi ý:** Để SQL builder giữ danh sách kiểu/giá trị đã biết, dùng metadata như kiểm tra tùy chọn và báo mức hỗ trợ. Không làm mất khả năng gán tham số theo schema trên driver B/C; kiểm thử cụ thể và không che giấu lỗi thực thi.

**Bài 7 — `CallableStatement`.** Vì sao `getParameterMode(2) == parameterModeUnknown` không đủ để kết luận tham số thứ hai không thể là `OUT`?

**Đáp án:** `UNKNOWN` chỉ cho biết metadata không xác định mode. Phải dựa vào chữ ký procedure và đăng ký `registerOutParameter` khi tham số thực sự là OUT.

## Tổng kết

`ParameterMetaData` trong JDBC giúp quan sát **số lượng, kiểu, precision, scale, nullability và mode** của các marker `?` trên một `PreparedStatement` hoặc `CallableStatement`. Hãy dùng chỉ số tham số từ **1**, hiểu các giá trị chưa xác định và nhớ rằng `getParameterMetaData()` có thể chỉ được driver hỗ trợ một phần. Với CRUD thông thường, nguồn sự thật cho kiểu dữ liệu và ràng buộc vẫn là **schema, câu SQL và quy tắc ứng dụng**; tiếp tục gán giá trị bằng `setXxx` và quản lý `Connection`/`SQLException` đúng cách. Dùng metadata cho khảo sát, kiểm tra chéo và công cụ động khi có nhu cầu thực sự, rồi xác minh các getter cần dùng trên đúng DBMS và JDBC driver triển khai.
