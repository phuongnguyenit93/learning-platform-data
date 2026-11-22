# Lựa chọn `getXxx` và `getObject` theo kiểu cần nhận trong JDBC

## 1. Đọc dữ liệu từ `ResultSet`: kiểu SQL và kiểu Java

Trong chương **Đọc ResultSet**, một quyết định thường gặp là dùng `getString()`, `getInt()`, `getBigDecimal()`, `getDate()` hay `getObject()` khi lấy giá trị của một cột. **JDBC (Java Database Connectivity)** là API để Java truy cập cơ sở dữ liệu quan hệ; sau khi thực thi truy vấn, `java.sql.ResultSet` cho phép lấy các giá trị SQL và chuyển thành giá trị Java.

Giả sử bảng sản phẩm có các cột `id BIGINT`, `name VARCHAR`, `price DECIMAL`, `discount_percent INTEGER`, `listed_on DATE`. Khi đọc một dòng, bạn thường muốn nhận:

| Cột SQL | Kiểu Java mong muốn | Cách đọc thường phù hợp |
| --- | --- | --- |
| `id BIGINT NOT NULL` | `long` | `rs.getLong("id")` |
| `name VARCHAR NOT NULL` | `String` | `rs.getString("name")` |
| `price DECIMAL(12, 2) NOT NULL` | `BigDecimal` | `rs.getBigDecimal("price")` |
| `discount_percent INTEGER NULL` | `Integer` (nullable) | `rs.getObject("discount_percent", Integer.class)` khi driver hỗ trợ |
| `listed_on DATE NULL` | `LocalDate` (nullable) | `rs.getObject("listed_on", LocalDate.class)` với driver JDBC 4.2 phù hợp |

**Không có một getter tốt nhất cho mọi cột.** Cách chọn phụ thuộc vào kiểu SQL, kiểu Java mà tầng nghiệp vụ cần nhận, cột có thể chứa `NULL` hay không và khả năng chuyển đổi của JDBC driver.

Sau bài này, bạn sẽ biết khi nào chọn getter chuyên biệt `getXxx`, khi nào chọn `getObject` có hoặc không chỉ định lớp đích, cách nhận biết SQL `NULL`, và cách ánh xạ an toàn sang DTO/record mà không giữ `ResultSet` mở.

## 2. Các dạng getter: `getXxx` và `getObject`

Một `ResultSet` có nhiều nhóm getter:

~~~java
// Getter chuyên biệt, trả về kiểu Java được chỉ rõ trong tên phương thức.
String name = rs.getString("name");
long id = rs.getLong("id");
BigDecimal price = rs.getBigDecimal("price");

// Getter tổng quát: kiểu Java cụ thể phụ thuộc ánh xạ SQL/driver.
Object raw = rs.getObject("price");

// Getter có kiểu đích, dùng Class<T> để yêu cầu một kiểu Java.
BigDecimal typed = rs.getObject("price", BigDecimal.class);
~~~

| Cách đọc | Kiểu kết quả khai báo trong Java | Điểm mạnh | Điểm cần lưu ý |
| --- | --- | --- | --- |
| `getInt()`, `getLong()`, `getBoolean()` | Kiểu nguyên thủy như `int`, `long`, `boolean` | Gọn cho cột chắc chắn không `NULL` | SQL `NULL` bị trả thành giá trị mặc định; cần `wasNull()` nếu cột nullable. |
| `getString()`, `getBigDecimal()` | Kiểu đối tượng xác định | Dễ đọc, trả `null` khi cột SQL là `NULL` | Chọn getter tương thích với kiểu SQL để tránh mất ý nghĩa. |
| `getDate()`, `getTimestamp()` | `java.sql.Date`, `java.sql.Timestamp` | Phổ biến với các driver, có thể chuyển sang `java.time` | Cần tự chuyển kiểu và xác định ngữ nghĩa múi giờ. |
| `getObject(column)` | `Object` | Hữu ích cho xử lý động khi chưa biết loại cột | Kiểu runtime do JDBC mapping/driver quyết định; ép kiểu mù dễ lỗi. |
| `getObject(column, Class<T>)` | `T`, ví dụ `Integer`, `LocalDate` | Thể hiện rõ kiểu Java cần nhận; giữ được `null` với kiểu tham chiếu | Chỉ dùng khi driver hỗ trợ chuyển đổi được yêu cầu. |

`getXxx` có thể thực hiện các phép chuyển đổi được JDBC/driver hỗ trợ; chẳng hạn một số driver cho phép `getString()` đối với cột số. Tuy nhiên, **chuyển được không có nghĩa luôn là lựa chọn phù hợp**: lấy giá tiền bằng `double` có thể mất độ chính xác, còn lấy thời gian bằng `String` thường làm code phụ thuộc định dạng driver.

## 3. Đọc đúng dòng và xác định đúng cột

Sau `executeQuery()`, con trỏ `ResultSet` ở **trước dòng đầu tiên**. Mỗi lần `next()` trả `true`, con trỏ mới đứng ở một dòng hợp lệ để gọi getter:

~~~java
String sql = "SELECT id, name, price FROM product ORDER BY id";
try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        BigDecimal price = rs.getBigDecimal("price");
        System.out.println(id + " | " + name + " | " + price);
    }
}
~~~

Các getter cho phép dùng **vị trí cột** hoặc **nhãn cột**:

~~~java
long idByIndex = rs.getLong(1);     // Cột kết quả thứ nhất.
long idByLabel = rs.getLong("id");  // Cột có nhãn "id".
~~~

Chỉ số cột trong `ResultSet` bắt đầu từ **1**, nhưng không liên quan đến chỉ số dấu `?` của `PreparedStatement`. Khi SQL dùng alias, getter theo nhãn cần dùng alias:

~~~sql
SELECT p.price AS unit_price FROM product p
~~~

~~~java
BigDecimal price = rs.getBigDecimal("unit_price");
~~~

Getter theo nhãn giúp mã dễ hiểu khi thay đổi thứ tự cột trong `SELECT`. Nếu truy vấn join nhiều bảng có cột trùng tên, hãy đặt alias riêng thay vì đọc bằng một nhãn mơ hồ.

## 4. `NULL`: khác biệt quan trọng nhất giữa getter nguyên thủy và đối tượng

SQL `NULL` nghĩa là không có giá trị xác định. Với getter trả đối tượng như `getString()` hoặc `getBigDecimal()`, SQL `NULL` thường được trả về thành Java `null`.

Ngược lại, getter nguyên thủy **không thể trả Java `null`**:

| Getter | SQL có giá trị | Khi SQL là `NULL` |
| --- | --- | --- |
| `getInt()` | Giá trị `int` sau chuyển đổi | `0` |
| `getLong()` | Giá trị `long` sau chuyển đổi | `0L` |
| `getBoolean()` | `true` hoặc `false` | `false` |
| `getDouble()` | Giá trị `double` | `0.0` |
| `getString()` | `String` | `null` |
| `getBigDecimal()` | `BigDecimal` | `null` |
| `getObject()` | Đối tượng phù hợp | `null` |

Vì thế, nếu `discount_percent INTEGER` có thể là `NULL`, đoạn sau làm mất thông tin:

~~~java
int discount = rs.getInt("discount_percent");
// discount == 0 có thể là 0 thật hoặc SQL NULL.
~~~

### 4.1. Cách một: `getInt()` kết hợp `wasNull()`

`ResultSet.wasNull()` cho biết **lần gọi getter đọc cột gần nhất** đã gặp SQL `NULL` hay chưa:

~~~java
int value = rs.getInt("discount_percent");
Integer discountPercent = rs.wasNull() ? null : value;
~~~

Hãy gọi `wasNull()` **ngay sau** getter đang kiểm tra. Ví dụ sau không đúng ý định:

~~~java
int discount = rs.getInt("discount_percent");
String name = rs.getString("name");
boolean missingDiscount = rs.wasNull(); // Kiểm tra "name", không còn "discount".
~~~

Nếu `name` không `NULL`, `missingDiscount` sẽ là `false` ngay cả khi `discount_percent` là SQL `NULL`.

### 4.2. Cách hai: `getObject(..., Integer.class)`

Khi driver hỗ trợ, bạn có thể yêu cầu luôn đối tượng `Integer`:

~~~java
Integer discountPercent =
        rs.getObject("discount_percent", Integer.class);
// SQL NULL -> Java null; SQL 0 -> Integer.valueOf(0).
~~~

Cách này tránh việc kiểm tra `wasNull()` và diễn đạt đúng ý nghĩa nullable của thuộc tính. Nếu driver không hỗ trợ chuyển đổi sang `Integer.class`, hãy chọn getter được hỗ trợ và sử dụng `wasNull()`.

Tương tự, cột `BOOLEAN NULL` có thể được đọc bằng `Boolean flag = rs.getObject("flag", Boolean.class)` khi driver hỗ trợ. Chỉ dùng `boolean flag = rs.getBoolean("flag")` nếu cột chắc chắn không `NULL`, hoặc khi bạn đã quyết định rõ cách chuyển `NULL` thành `false`.

## 5. Chọn getter theo từng nhóm kiểu dữ liệu

### 5.1. Số nguyên: `getInt`, `getLong`, hay `getObject`?

Với cột `INTEGER NOT NULL`, `getInt()` phù hợp. Với `BIGINT NOT NULL`, `getLong()` giữ đúng miền giá trị hơn `getInt()`. Với `INTEGER NULL`, dùng `getObject(..., Integer.class)` khi khả dụng hoặc `getInt()` rồi `wasNull()`.

~~~java
long orderId = rs.getLong("id");                  // BIGINT NOT NULL.
Integer rating = rs.getObject("rating", Integer.class); // INTEGER NULL.
~~~

Tránh ép một `BIGINT` thành `int` khi dữ liệu có thể vượt phạm vi. Một số chuyển đổi có thể ném `SQLException` hoặc có hành vi phụ thuộc driver; đừng dựa vào chuyển đổi số ngoài miền hợp lệ.

### 5.2. Tiền và số thập phân chính xác: `getBigDecimal()`

Với `DECIMAL` hoặc `NUMERIC` dùng cho tiền, điểm thưởng hoặc số đo cần giữ độ chính xác thập phân, ưu tiên:

~~~java
BigDecimal total = rs.getBigDecimal("total_amount");
~~~

`BigDecimal` biểu diễn số thập phân chính xác theo giá trị và scale. `getDouble()` trả số dấu phẩy động nhị phân, nên có thể xuất hiện sai số biểu diễn khi tính tiền:

~~~java
// Tránh mặc định dùng double cho tiền:
double total = rs.getDouble("total_amount");

// Nên:
BigDecimal exactTotal = rs.getBigDecimal("total_amount");
~~~

`getObject("total_amount")` thường cũng trả `BigDecimal` đối với `DECIMAL/NUMERIC`, nhưng kiểu cụ thể phải được kiểm tra theo driver. Khi cần rõ kiểu, có thể dùng `getObject("total_amount", BigDecimal.class)` nếu driver hỗ trợ, hoặc dùng `getBigDecimal()` trực tiếp.

### 5.3. Chuỗi, nhị phân và các kiểu lớn

Với `CHAR`, `VARCHAR`, `TEXT`, `getString()` thường là lựa chọn dễ hiểu. Với dữ liệu nhị phân nhỏ, `getBytes()` trả `byte[]`:

~~~java
String title = rs.getString("title");
byte[] thumbnail = rs.getBytes("thumbnail");
~~~

Với `BLOB`, `CLOB` hoặc dữ liệu lớn, cân nhắc `getBinaryStream()`, `getCharacterStream()`, `getBlob()`, `getClob()` theo hỗ trợ driver và nhu cầu đọc. Việc lấy toàn bộ dữ liệu bằng `getBytes()` hoặc `getString()` có thể tốn nhiều bộ nhớ.

Các stream hoặc đối tượng `Blob/Clob` có thể phụ thuộc vòng đời `ResultSet`/`Connection`; cần đọc trong phạm vi tài nguyên còn mở và giải phóng tài nguyên theo hợp đồng API. Không trả stream hoặc LOB handle sang tầng gọi sau khi connection đã đóng, trừ khi tài liệu driver bảo đảm rõ điều đó.

### 5.4. Ngày và thời gian: `java.sql` so với `java.time`

JDBC truyền thống cung cấp `getDate()`, `getTime()`, `getTimestamp()` với các kiểu `java.sql.Date`, `java.sql.Time`, `java.sql.Timestamp`. Với ứng dụng Java hiện đại, thường muốn `LocalDate`, `LocalTime`, `LocalDateTime` hoặc `OffsetDateTime`.

| Kiểu SQL | Kiểu Java thích hợp | Cách đọc |
| --- | --- | --- |
| `DATE` | `LocalDate` | `getObject("day", LocalDate.class)` khi driver hỗ trợ JDBC 4.2 |
| `TIME` không có thông tin múi giờ | `LocalTime` | `getObject("start_time", LocalTime.class)` khi hỗ trợ |
| `TIMESTAMP` không có thông tin múi giờ | `LocalDateTime` | `getObject("created_at", LocalDateTime.class)` khi hỗ trợ |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` | `getObject("event_time", OffsetDateTime.class)` khi driver/DBMS hỗ trợ |

Ví dụ:

~~~java
LocalDate listedOn = rs.getObject("listed_on", LocalDate.class);
LocalDateTime createdAt = rs.getObject("created_at", LocalDateTime.class);
~~~

Nếu driver không hỗ trợ ánh xạ trực tiếp cho `DATE`, có thể chuyển theo cách truyền thống:

~~~java
java.sql.Date date = rs.getDate("listed_on");
LocalDate listedOn = date == null ? null : date.toLocalDate();
~~~

Với `TIMESTAMP` không có múi giờ, một fallback thường gặp là:

~~~java
java.sql.Timestamp timestamp = rs.getTimestamp("created_at");
LocalDateTime createdAt =
        timestamp == null ? null : timestamp.toLocalDateTime();
~~~

**Chú ý ngữ nghĩa thời gian:** `LocalDateTime` không có múi giờ hoặc offset. Nó không tự biểu diễn một thời điểm tuyệt đối. Với dữ liệu cần thời điểm toàn cầu, phải hiểu chính xác kiểu SQL, session time zone và quy tắc chuyển đổi của DBMS/driver; không tự gắn `ZoneId.systemDefault()` tùy tiện rồi cho rằng giá trị đã đúng.

### 5.5. Kiểu đặc thù của DBMS

Một số DBMS hỗ trợ `UUID`, `JSON`, `ARRAY`, kiểu hình học hoặc kiểu do người dùng định nghĩa. `getObject()` có thể trả đối tượng riêng của driver; một số driver hỗ trợ `getObject("id", UUID.class)`, số khác yêu cầu đọc `String` hoặc dùng API chuyên biệt.

Không nên mặc định `getObject("payload")` luôn trả `Map<String, Object>` với cột JSON hoặc `getObject("tags")` luôn trả `String[]` với cột ARRAY. Đối với ARRAY, JDBC có giao diện `java.sql.Array` riêng; đối tượng này còn cần được giải phóng bằng `free()` khi không sử dụng.

## 6. `getObject(column)` khác `getObject(column, Class<T>)` như thế nào?

Hai overload có mục đích khác nhau:

~~~java
Object raw = rs.getObject("value");            // Driver xác định kiểu thực tế.
Integer n = rs.getObject("value", Integer.class); // Ứng dụng yêu cầu Integer.
~~~

### 6.1. `getObject(column)`: hữu ích cho hệ thống đọc dữ liệu động

Khi viết một công cụ báo cáo không biết trước schema, bạn có thể đọc từng cột dưới dạng `Object`:

~~~java
ResultSetMetaData meta = rs.getMetaData();
int columnCount = meta.getColumnCount();

while (rs.next()) {
    for (int column = 1; column <= columnCount; column++) {
        String label = meta.getColumnLabel(column);
        Object value = rs.getObject(column);
        System.out.println(label + " = " + value);
    }
}
~~~

Trong ví dụ, `meta.getColumnLabel(column)` lấy nhãn hiển thị (bao gồm alias khi có), còn `getObject(column)` nhận giá trị với kiểu runtime do ánh xạ JDBC và driver quyết định. Với trường hợp đọc động, có thể dùng `meta.getColumnType(column)`, `meta.getColumnTypeName(column)` hoặc `getColumnClassName(column)` để hiểu hơn về kiểu dữ liệu.

Không ép kiểu theo phỏng đoán:

~~~java
// Dễ phát sinh ClassCastException nếu driver không trả Long.
Long value = (Long) rs.getObject("some_number");
~~~

Nếu schema cố định và bạn biết kiểu mong muốn, nên dùng getter phù hợp hoặc `getObject(..., Class<T>)` để biểu diễn ý định rõ hơn.

### 6.2. `getObject(column, Class<T>)`: rõ hợp đồng đầu ra

Overload `getObject(int/String, Class<T>)` được giới thiệu trong JDBC 4.1. Bạn truyền một **kiểu tham chiếu** cụ thể:

~~~java
Integer quantity = rs.getObject("quantity", Integer.class);
BigDecimal price = rs.getObject("price", BigDecimal.class);
LocalDate listedOn = rs.getObject("listed_on", LocalDate.class);
~~~

Khi cột là SQL `NULL`, kết quả là Java `null`. Nếu driver không hỗ trợ kiểu đích hoặc phép chuyển đổi, lời gọi có thể ném `SQLException` (gồm `SQLFeatureNotSupportedException`). Việc truyền `LocalDate.class` yêu cầu driver hỗ trợ ánh xạ phù hợp; không phải mọi phiên bản driver đều có cùng mức hỗ trợ JDBC 4.2.

**Không dùng `int.class` làm kiểu đích với kỳ vọng nhận `null`**: hãy chọn `Integer.class` hoặc một kiểu tham chiếu tương thích. Kể cả khi dùng setter/getter có kiểu đích, ứng dụng vẫn cần xác minh tính tương thích của dữ liệu SQL và miền giá trị.

## 7. Ví dụ hoàn chỉnh: ánh xạ một hàng thành record Java

Giả sử bảng `product` được định nghĩa:

~~~sql
CREATE TABLE product (
    id               BIGINT PRIMARY KEY,
    name             VARCHAR(200) NOT NULL,
    price            DECIMAL(12, 2) NOT NULL,
    discount_percent INTEGER NULL,
    active           BOOLEAN NOT NULL,
    listed_on        DATE NULL,
    created_at       TIMESTAMP NOT NULL
);

INSERT INTO product
    (id, name, price, discount_percent, active, listed_on, created_at)
VALUES
    (42, 'Bàn phím cơ', 890000.00, NULL, TRUE,
     DATE '2026-11-16', TIMESTAMP '2026-11-16 09:30:00');
~~~

Đoạn SQL sử dụng kiểu `BOOLEAN` và cú pháp literal ngày/giờ phổ biến; khả năng hỗ trợ và cách khai báo có thể khác theo DBMS. Trong Java, định nghĩa record để thể hiện rõ cột nào nullable:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

public record Product(
        long id,
        String name,
        BigDecimal price,
        Integer discountPercent,
        boolean active,
        LocalDate listedOn,
        LocalDateTime createdAt) {}
~~~

Repository chọn getter theo kiểu **muốn nhận trong record**, đồng thời dựa vào ràng buộc SQL và khả năng JDBC driver:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class ProductRepository {
    private final DataSource dataSource;

    public ProductRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<Product> findById(long productId) throws SQLException {
        String sql = """
                SELECT id, name, price, discount_percent,
                       active, listed_on, created_at
                FROM product
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, productId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                Product product = new Product(
                        rs.getLong("id"),
                        rs.getString("name"),
                        rs.getBigDecimal("price"),
                        rs.getObject("discount_percent", Integer.class),
                        rs.getBoolean("active"),
                        rs.getObject("listed_on", LocalDate.class),
                        rs.getObject("created_at", LocalDateTime.class));

                return Optional.of(product);
            }
        }
    }
}
~~~

Ví dụ dùng Java 17 trở lên để khai báo `record` và text block, dùng JDBC driver hỗ trợ ánh xạ `LocalDate`/`LocalDateTime` bằng `getObject(Class<T>)`. `DataSource` cần được cấu hình trước. Phương thức `findById()` đóng `ResultSet`, `PreparedStatement` và `Connection` trước khi trả về `Product`, nên đối tượng không còn phụ thuộc cursor.

Giải thích từng lựa chọn:

1. `id BIGINT PRIMARY KEY` chắc chắn không `NULL`: dùng `getLong()`.
2. `name VARCHAR NOT NULL`: dùng `getString()`.
3. `price DECIMAL NOT NULL`: dùng `getBigDecimal()` để giữ độ chính xác.
4. `discount_percent INTEGER NULL`: dùng `getObject(..., Integer.class)` để phân biệt **0** với **`null`**.
5. `active BOOLEAN NOT NULL`: dùng `getBoolean()` và nhận `boolean`.
6. `listed_on DATE NULL`: dùng `getObject(..., LocalDate.class)`, nhận `null` khi không có ngày.
7. `created_at TIMESTAMP NOT NULL`: dùng `getObject(..., LocalDateTime.class)` nếu driver tương thích.

Nếu gặp driver không hỗ trợ `getObject(..., Integer.class)` hoặc ánh xạ `java.time`, hãy thay các dòng tương ứng bằng `getInt()` + `wasNull()`, `getDate()` + `toLocalDate()`, `getTimestamp()` + `toLocalDateTime()`. Vẫn cần kiểm thử trên DBMS và phiên bản driver thực tế.

## 8. Tránh chuyển kiểu âm thầm và mất thông tin

Một số lựa chọn getter có thể **chạy được** nhưng tạo ra dữ liệu không đúng kỳ vọng:

| Lựa chọn | Rủi ro | Lựa chọn phù hợp hơn |
| --- | --- | --- |
| `getDouble("price")` cho `DECIMAL` tiền tệ | Sai số nhị phân khi biểu diễn thập phân | `getBigDecimal("price")` |
| `getInt("id")` cho `BIGINT` | Giá trị có thể vượt miền `int` | `getLong("id")` |
| `getInt("nullable_count")` rồi coi `0` là số lượng thực | Không phân biệt SQL `NULL` với 0 | `getObject(..., Integer.class)` hoặc `getInt()` + `wasNull()` |
| `getBoolean("optional_flag")` rồi mặc định `false` | Không phân biệt SQL `NULL` với `false` | `getObject(..., Boolean.class)` khi được hỗ trợ |
| `getString("created_at")` để xử lý thời gian | Phải parse chuỗi, phụ thuộc định dạng và múi giờ | Getter kiểu thời gian phù hợp |
| `(Long) getObject("some_number")` | Có thể nhận kiểu runtime khác `Long` | `getLong()` hoặc `getObject(..., Long.class)` |
| `getBytes()` cho cột BLOB rất lớn | Tải toàn bộ dữ liệu vào bộ nhớ | Stream/LOB phù hợp với driver |

**Một phép chuyển đổi không hợp lệ có thể ném `SQLException`.** Không nên tự cho rằng getter sẽ luôn cắt phần thập phân, ép kiểu hoặc làm tròn giống nhau giữa các driver. Với dữ liệu nhạy cảm về độ chính xác, hãy quyết định kiểu SQL và Java ngay từ mô hình dữ liệu.

### Khi cần một kiểu enum trong Java

Với cột `status VARCHAR`, hãy đọc chuỗi rồi chuyển thành enum theo quy tắc của ứng dụng:

~~~java
enum OrderStatus { NEW, PAID, CANCELLED }

String rawStatus = rs.getString("status");
OrderStatus status =
        rawStatus == null ? null : OrderStatus.valueOf(rawStatus);
~~~

Việc chuyển sang enum có thể phát sinh `IllegalArgumentException` khi DB chứa giá trị ngoài tập được phép. Đây là lỗi ánh xạ/quy tắc ứng dụng cần được quyết định rõ, không phải một khả năng tự động của `getObject(..., OrderStatus.class)`.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| `SQLException` khi gọi getter | Tên nhãn cột sai, cột không có trong `SELECT` hoặc chuyển kiểu không được hỗ trợ | Kiểm tra alias, kiểu SQL và loại getter. |
| `ClassCastException` khi ép kết quả `getObject()` | Kiểu Java thực tế khác kiểu suy đoán | Xem metadata hoặc dùng `getObject(column, Class<T>)` phù hợp. |
| Giá trị `0` xuất hiện ở cột nullable | Dùng getter nguyên thủy và không gọi `wasNull()` | Dùng wrapper hoặc gọi `wasNull()` ngay sau getter. |
| `wasNull()` cho kết quả khó hiểu | Đã gọi getter khác trước `wasNull()` | Đặt `wasNull()` ngay sau getter cần kiểm tra. |
| `SQLFeatureNotSupportedException` với `getObject(Class<T>)` | Driver không hỗ trợ chuyển kiểu đích | Dùng getter truyền thống và tự chuyển đổi. |
| Giờ/ngày lệch so với mong đợi | Nhầm kiểu có/không có múi giờ hoặc mapping riêng của DBMS | Kiểm tra kiểu SQL, session time zone và driver. |
| Dữ liệu tiền xuất hiện số lẻ bất ngờ | Đọc qua `double` thay vì số thập phân chính xác | Dùng `BigDecimal`. |
| `ResultSet is closed` hoặc lỗi tài nguyên | Truy cập getter sau khi đóng `ResultSet`/`Statement`/`Connection` | Ánh xạ toàn bộ dữ liệu cần dùng trong khối `try-with-resources`. |
| Thiếu một số dòng khi đọc danh sách | Dùng `if (rs.next())` thay vì `while` | Dùng `while (rs.next())` khi cần đọc nhiều dòng. |

Khi cần kiểm tra ánh xạ trong quá trình phát triển, `ResultSetMetaData` hỗ trợ đọc thông tin cột:

~~~java
ResultSetMetaData meta = rs.getMetaData();
int column = 1;
System.out.println(meta.getColumnLabel(column));
System.out.println(meta.getColumnTypeName(column));
System.out.println(meta.getColumnClassName(column));
~~~

`getColumnClassName()` cho biết tên lớp Java mà metadata của driver gắn với cách đọc mặc định bằng `getObject()`; không phải cam kết rằng mọi `getObject(column, AnyClass.class)` đều thành công. Kết quả metadata và loại chuyển đổi khả dụng cần được xác minh với driver thực tế.

## 10. Thực hành: chọn getter cho từng trường hợp

**Bài 1 — Phân biệt số 0 và SQL NULL.** Bảng `inventory` có `reserved_quantity INTEGER NULL`. Hãy đọc thành `Integer` để biểu diễn cả `0` và `null`. Hai đáp án hợp lệ khi driver hỗ trợ:

~~~java
Integer reserved = rs.getObject("reserved_quantity", Integer.class);

// Hoặc:
int raw = rs.getInt("reserved_quantity");
Integer reservedAlternative = rs.wasNull() ? null : raw;
~~~

**Bài 2 — Giữ độ chính xác.** Cột `unit_price DECIMAL(10,2)` nên đọc thành `BigDecimal` hay `double` nếu tiếp tục tính thành tiền? Lựa chọn phù hợp là **`BigDecimal`**, vì kiểu này giữ chính xác giá trị thập phân theo biểu diễn và scale.

**Bài 3 — Đọc ngày có thể NULL.** Cột `completed_on DATE NULL` phải trở thành `LocalDate`. Dùng `getObject("completed_on", LocalDate.class)` nếu driver hỗ trợ; nếu không, dùng `getDate()`, kiểm tra `null`, rồi `toLocalDate()`.

**Bài 4 — Chỉ ra lỗi.**

~~~java
int quantity = rs.getInt("quantity");
String description = rs.getString("description");
boolean missingQuantity = rs.wasNull();
~~~

Lỗi là `wasNull()` đang kiểm tra **`description`**, vì đó là getter gần nhất. Hãy gọi `wasNull()` ngay sau `getInt("quantity")`.

**Bài 5 — Mô hình dữ liệu động.** Khi viết công cụ hiển thị một bảng bất kỳ mà chưa biết kiểu cột, hãy dùng `ResultSetMetaData` để đọc nhãn/loại cột, rồi `getObject(column)` với lưu ý về kiểu runtime và các giá trị LOB/ARRAY đặc biệt.

## 11. Checklist quyết định getter

- Xác định kiểu SQL của cột và kiểu Java mà phương thức cần trả về, thay vì chỉ chọn getter dễ gõ nhất.
- Với cột **`NOT NULL`** kiểu nguyên thủy tương thích, `getInt()`, `getLong()`, `getBoolean()` thường phù hợp.
- Với cột nullable cần phân biệt giá trị mặc định và SQL `NULL`, chọn `getObject(..., Wrapper.class)` khi có hỗ trợ, hoặc dùng getter nguyên thủy rồi gọi ngay `wasNull()`.
- Với `DECIMAL/NUMERIC` cần độ chính xác, dùng `BigDecimal`; với `VARCHAR` dùng `String`.
- Với `DATE/TIME/TIMESTAMP`, xem xét `java.time` và khả năng hỗ trợ JDBC 4.2, đồng thời xác định rõ ngữ nghĩa múi giờ.
- Với kiểu chưa biết trước, `getObject(column)` và `ResultSetMetaData` hữu ích; không ép kiểu mù.
- Đọc cột theo **label/alias rõ ràng**, gọi getter khi con trỏ đang ở dòng hợp lệ và ánh xạ sang DTO/record trước khi đóng `ResultSet`.
- Kiểm thử với chính DBMS và JDBC driver sử dụng trong dự án, vì các chuyển đổi mở rộng có thể khác nhau.

**Ghi nhớ:** chọn **`getXxx` khi biết rõ kiểu SQL và kiểu Java cần nhận**; chọn **`getObject(column, Class<T>)` khi muốn thể hiện kiểu đích, nhất là kiểu tham chiếu nullable hoặc `java.time`, và driver hỗ trợ chuyển đổi đó**. `getObject(column)` hữu ích khi đọc động nhưng cần kiểm tra kiểu trả về. Bất kể chọn cách nào, hãy xử lý SQL `NULL` chính xác, giữ độ chính xác dữ liệu và đóng các tài nguyên JDBC đúng vòng đời.
