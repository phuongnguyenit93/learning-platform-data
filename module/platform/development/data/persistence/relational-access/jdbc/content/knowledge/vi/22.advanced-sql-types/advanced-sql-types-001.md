# Làm việc với SQL Array và mảng giá trị Java trong JDBC

## 1. SQL Array là gì?

Trong chương **Kiểu SQL nâng cao**, `ARRAY` là kiểu dữ liệu dùng để lưu hoặc truyền **một tập hợp phần tử có thứ tự** trong cơ sở dữ liệu quan hệ. JDBC (Java Database Connectivity), API của Java để truy cập cơ sở dữ liệu quan hệ, cung cấp giao diện **`java.sql.Array`** để trao đổi các giá trị kiểu mảng giữa Java và SQL.

Giả sử ứng dụng lưu các thẻ gắn với một bài viết:

~~~text
Java:       String[] tags = {"java", "jdbc", "sql"};
                               │
             Connection.createArrayOf("text", tags)
                               │
JDBC:                     java.sql.Array
                               │
                   PreparedStatement.setArray(...)
                               │
PostgreSQL:               TEXT[] trong cột tags
~~~

Chủ đề này có **ba khái niệm cần phân biệt**:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Mảng Java** | Cấu trúc dữ liệu tồn tại trong bộ nhớ chương trình | `String[]`, `Integer[]`, `BigDecimal[]` |
| **Kiểu ARRAY của SQL** | Kiểu dữ liệu do hệ quản trị CSDL hỗ trợ để biểu diễn các phần tử trong cột/biểu thức/tham số SQL | `TEXT[]` của PostgreSQL |
| **`java.sql.Array`** | Giao diện JDBC biểu diễn một giá trị SQL ARRAY và cung cấp cách truy cập/chuyển đổi phần tử | Kết quả của `createArrayOf(...)` hoặc `ResultSet.getArray(...)` |

**`java.sql.Array` không phải là `String[]`, `Integer[]` hay `java.util.List`.** Nó là đối tượng JDBC gắn với cách driver biểu diễn giá trị SQL, có vòng đời và phương thức giải phóng tài nguyên riêng.

Sau bài này, bạn sẽ biết khi nào dùng SQL ARRAY, cách tạo và truyền nó vào `PreparedStatement`, cách đọc về mảng Java, xử lý `NULL`, kiểm soát tài nguyên và phân biệt phần API JDBC có tính chuẩn với cú pháp riêng của DBMS.

## 2. Khi nào nên dùng SQL Array?

SQL ARRAY hữu ích khi một giá trị có nhiều phần tử **cùng kiểu** và cơ sở dữ liệu hỗ trợ phù hợp: danh sách nhãn của một đối tượng, tập điểm đo, danh sách mã được truyền vào một truy vấn hoặc một số thuộc tính nhiều giá trị tương đối đơn giản.

Ví dụ: một bài viết có các nhãn `["java", "jdbc", "sql"]`. Trong PostgreSQL, ta có thể khai báo:

~~~sql
-- Cú pháp PostgreSQL; không phải cú pháp chung của mọi DBMS.
CREATE TABLE article (
    id   BIGINT PRIMARY KEY,
    tags TEXT[]
);

INSERT INTO article (id, tags)
VALUES (1, ARRAY['java', 'jdbc', 'sql']);
~~~

Không phải mọi CSDL đều triển khai SQL ARRAY theo cùng cách. PostgreSQL có mảng dạng `text[]`, `integer[]`; các DBMS khác có thể dùng kiểu collection riêng, giới hạn khả năng hỗ trợ hoặc không hỗ trợ trực tiếp `Connection.createArrayOf`. **Luôn kiểm tra driver JDBC và cú pháp của DBMS đang sử dụng.**

ARRAY cũng không tự thay thế thiết kế quan hệ nhiều–nhiều. Nếu mỗi nhãn phải có metadata riêng, khóa ngoại, quyền quản trị hoặc được truy vấn/join thường xuyên, bảng liên kết `article_tag(article_id, tag_id)` có thể phù hợp hơn. Quyết định còn phụ thuộc khả năng lập chỉ mục, kiểm tra ràng buộc và khối lượng truy vấn.

## 3. Các API JDBC quan trọng

| API | Công dụng | Điểm cần nhớ |
| --- | --- | --- |
| `Connection.createArrayOf(typeName, elements)` | Tạo một `java.sql.Array` từ mảng đối tượng Java | `typeName` là **tên kiểu SQL của phần tử**, ví dụ `text` trên PostgreSQL, không phải `text[]`. |
| `PreparedStatement.setArray(index, sqlArray)` | Gán SQL ARRAY vào tham số `?` | `index` của placeholder bắt đầu từ **1**. |
| `ResultSet.getArray(column)` | Lấy giá trị SQL ARRAY ở cột kết quả | Có thể trả về `null` khi cột chứa SQL `NULL`. |
| `Array.getArray()` | Chuyển toàn bộ SQL ARRAY thành mảng Java theo mapping của driver | Kiểu mảng Java cụ thể phụ thuộc loại phần tử và driver. |
| `Array.getArray(index, count)` | Lấy một phần mảng | Theo API JDBC, `index` bắt đầu từ **1**. |
| `Array.getResultSet()` | Đọc phần tử như `ResultSet` hai cột | Cột 1 là vị trí phần tử, cột 2 là giá trị phần tử. |
| `Array.getBaseType()` / `getBaseTypeName()` | Xác định kiểu SQL của **phần tử** | `getBaseType()` trả mã loại trong `java.sql.Types`. |
| `Array.free()` | Giải phóng tài nguyên liên quan đến giá trị ARRAY | Không tiếp tục dùng đối tượng ARRAY sau khi đã `free()`. |

### 3.1. Tạo SQL ARRAY từ mảng Java

Ví dụ truyền mảng chuỗi cho cột `TEXT[]` của PostgreSQL:

~~~java
String[] javaTags = {"java", "jdbc", "sql"};
java.sql.Array sqlTags = connection.createArrayOf("text", javaTags);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO article (id, tags) VALUES (?, ?)")) {
    ps.setLong(1, 10L);
    ps.setArray(2, sqlTags);
    ps.executeUpdate();
} finally {
    sqlTags.free();
}
~~~

Trong đó, `"text"` là **kiểu cơ sở của phần tử** theo PostgreSQL; giá trị `"text[]"` không được tự động coi là tên kiểu phần tử đúng trong `createArrayOf`. Với kiểu số nguyên của PostgreSQL, driver thường chấp nhận `"integer"` hoặc `"int4"`; tên kiểu được chấp nhận vẫn cần xác nhận theo driver.

Phương thức `createArrayOf` nhận tham số `Object[]`. Vì thế, các kiểu phần tử tham chiếu như `String[]`, `Integer[]` hay `BigDecimal[]` phù hợp:

~~~java
Integer[] javaIds = {101, 102, 103};
java.sql.Array sqlIds = connection.createArrayOf("integer", javaIds);
try {
    // Gán sqlIds vào PreparedStatement khi cần.
} finally {
    sqlIds.free();
}
~~~

**Mảng nguyên thủy như `int[]` không phải `Object[]`.** Nếu đang có `int[]`, hãy chuyển sang `Integer[]` trước:

~~~java
int[] rawIds = {101, 102, 103};
Integer[] boxedIds = java.util.Arrays.stream(rawIds)
        .boxed()
        .toArray(Integer[]::new);
~~~

Không nên truyền `Arrays.asList(rawIds)` với kỳ vọng nhận `List<Integer>`: đối với `int[]`, lời gọi này tạo một danh sách có **một phần tử là cả mảng `int[]`**.

### 3.2. Đọc SQL ARRAY từ ResultSet

Đọc dữ liệu phải qua **hai bước**: lấy đối tượng `java.sql.Array` từ `ResultSet`, rồi yêu cầu JDBC chuyển nó thành mảng Java hoặc `ResultSet` phần tử.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT tags FROM article WHERE id = ?")) {
    ps.setLong(1, 10L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Array sqlTags = rs.getArray("tags");
            if (sqlTags != null) {
                try {
                    Object values = sqlTags.getArray();
                    if (values instanceof String[]) {
                        String[] tags = (String[]) values;
                        System.out.println(java.util.Arrays.toString(tags));
                    }
                } finally {
                    sqlTags.free();
                }
            }
        }
    }
}
~~~

Với cột `TEXT[]` và driver PostgreSQL phù hợp, kết quả thường là `String[]`. **Không mặc định mọi SQL ARRAY đều cho ra `String[]` hoặc `Object[]`**: một số driver có thể trả kiểu mảng khác tùy phần tử, kiểu được cấu hình, hoặc phiên bản driver. Kiểm tra kiểu trả về hoặc dùng `getResultSet()` để chuyển đổi theo từng phần tử.

## 4. Ví dụ hoàn chỉnh: ghi và đọc danh sách nhãn

Giả sử đã tạo bảng `article` như ở mục 2 và ứng dụng đã có một `Connection` hợp lệ trỏ đến PostgreSQL. Ví dụ dưới đây tách việc ghi/đọc thành hai phương thức DAO, đồng thời quản lý `PreparedStatement`, `ResultSet` và `java.sql.Array`:

~~~java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class ArticleTagsDao {
    private ArticleTagsDao() {}

    public static void insert(Connection connection, long articleId,
                              String[] tags) throws SQLException {
        Objects.requireNonNull(tags, "tags");

        // "text" là tên kiểu SQL của PHẦN TỬ trên PostgreSQL.
        Array sqlTags = connection.createArrayOf("text", tags);
        try {
            String sql = "INSERT INTO article (id, tags) VALUES (?, ?)";
            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setLong(1, articleId);
                ps.setArray(2, sqlTags);
                ps.executeUpdate();
            }
        } finally {
            sqlTags.free();
        }
    }

    public static List<String> readTags(Connection connection, long articleId)
            throws SQLException {
        String sql = "SELECT tags FROM article WHERE id = ?";
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, articleId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không tìm thấy bài viết " + articleId);
                }

                Array sqlTags = rs.getArray("tags");
                if (sqlTags == null) {
                    return null; // Cột tags thực sự chứa SQL NULL.
                }

                try {
                    List<String> result = new ArrayList<>();
                    // ResultSet của Array: cột 1 = chỉ số; cột 2 = giá trị.
                    try (ResultSet elements = sqlTags.getResultSet()) {
                        while (elements.next()) {
                            long oneBasedIndex = elements.getLong(1);
                            String tag = elements.getString(2);
                            result.add(tag); // tag có thể null.
                        }
                    }
                    return result;
                } finally {
                    sqlTags.free();
                }
            }
        }
    }
}
~~~

Cách gọi:

~~~java
try (Connection connection = dataSource.getConnection()) {
    ArticleTagsDao.insert(connection, 20L,
            new String[]{"java", "jdbc", "sql"});

    List<String> tags = ArticleTagsDao.readTags(connection, 20L);
    System.out.println(tags); // [java, jdbc, sql]
}
~~~

Ví dụ giả định `dataSource` đã được cấu hình và `id = 20` chưa tồn tại. Trong ứng dụng thực tế, kết nối và ranh giới giao dịch có thể do service hoặc transaction manager quản lý; các DAO nhận `Connection` để dùng đúng kết nối của nghiệp vụ. **`Array.free()` chỉ giải phóng đối tượng ARRAY của JDBC, không commit hoặc rollback giao dịch.**

### Vì sao đọc qua `Array.getResultSet()`?

`getResultSet()` biểu diễn các phần tử thành một kết quả có **hai cột**, cho phép gọi các getter JDBC như `getString(2)`, `getInt(2)`, `getBigDecimal(2)` tùy kiểu:

| Cột | Nội dung |
| --- | --- |
| 1 | Vị trí phần tử trong SQL ARRAY |
| 2 | Giá trị phần tử, có thể là SQL `NULL` |

Đây là lựa chọn hữu ích khi cần xử lý từng phần tử và muốn tránh ép kiểu toàn bộ mảng Java theo một giả định cụ thể. Tuy nhiên, không nên mặc định driver luôn tải phần tử kiểu streaming; chi phí bộ nhớ, cách truy xuất và hỗ trợ `getResultSet(index, count)` phụ thuộc triển khai.

## 5. Cách ánh xạ kiểu dữ liệu và các trường hợp NULL

### 5.1. Kiểu phần tử SQL và Java

Bảng dưới đây chỉ thể hiện các ánh xạ thường gặp. Kiểu cụ thể vẫn có thể khác theo driver:

| Kiểu phần tử SQL | Kiểu phần tử Java thường dùng | Ghi chú |
| --- | --- | --- |
| `VARCHAR`, `TEXT` | `String` | `TEXT` là tên kiểu thường gặp ở PostgreSQL. |
| `INTEGER` | `Integer` | Sử dụng `Integer[]` khi tạo ARRAY theo API chuẩn nhận `Object[]`. |
| `BIGINT` | `Long` | Phân biệt với `Integer` để tránh mất miền giá trị. |
| `DECIMAL`, `NUMERIC` | `BigDecimal` | Hạn chế sai số khi làm việc với dữ liệu chính xác. |
| `BOOLEAN` | `Boolean` | Có thể chứa phần tử `null` khi DB cho phép. |
| `DATE` | `java.sql.Date` hoặc kiểu được driver hỗ trợ | Khả năng nhận `LocalDate[]` phụ thuộc phiên bản driver. |

Chẳng hạn:

~~~java
java.math.BigDecimal[] prices = {
    new java.math.BigDecimal("12.50"),
    new java.math.BigDecimal("19.99")
};
java.sql.Array sqlPrices = connection.createArrayOf("numeric", prices);
try {
    // Dùng sqlPrices cho tham số SQL có kiểu tương ứng.
} finally {
    sqlPrices.free();
}
~~~

Đoạn trên giả định driver nhận tên kiểu phần tử `numeric` (ví dụ PostgreSQL). Không nên xây dựng SQL ARRAY bằng cách nối các phần tử thành một chuỗi SQL hay một chuỗi giống JSON; `PreparedStatement.setArray` giúp truyền giá trị dưới dạng tham số có kiểu.

### 5.2. SQL NULL, mảng rỗng và phần tử NULL khác nhau

Ba giá trị dưới đây có ý nghĩa riêng:

| Giá trị SQL (PostgreSQL) | Ý nghĩa khi đọc bằng JDBC |
| --- | --- |
| `NULL::text[]` | **Toàn bộ cột là NULL**; `rs.getArray(...)` trả `null`. |
| `ARRAY[]::text[]` | **Mảng rỗng**; `getArray()` trả mảng có 0 phần tử hoặc `getResultSet()` không có dòng. |
| `ARRAY['java', NULL, 'sql']::text[]` | **Mảng có ba phần tử**, phần tử ở giữa là `null`. |

Khi truyền mảng rỗng từ Java:

~~~java
Array emptyTags = connection.createArrayOf("text", new String[0]);
try {
    // setArray(..., emptyTags) để ghi mảng rỗng.
} finally {
    emptyTags.free();
}
~~~

Khi muốn ghi **SQL NULL cho cả cột**, hãy dùng `PreparedStatement.setNull(..., Types.ARRAY)` nếu driver hỗ trợ:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE article SET tags = ? WHERE id = ?")) {
    ps.setNull(1, java.sql.Types.ARRAY);
    ps.setLong(2, 20L);
    ps.executeUpdate();
}
~~~

Một số driver yêu cầu xác định kiểu mảng cụ thể hoặc ép kiểu ngay trong SQL để xử lý tham số `NULL` không có thông tin kiểu. Với PostgreSQL, có thể dùng `tags = CAST(? AS text[])` khi cần; đây là chi tiết phụ thuộc hệ quản trị.

**Không đồng nhất** `new String[0]`, `new String[]{null}`, `null` và chuỗi `"NULL"`. Lựa chọn nào đúng phải xuất phát từ ý nghĩa nghiệp vụ.

### 5.3. Truy cập một phần mảng

Nếu driver hỗ trợ, có thể yêu cầu một đoạn mảng:

~~~java
Array sqlArray = rs.getArray("tags");
if (sqlArray != null) {
    try {
        // Từ phần tử thứ 2, lấy tối đa 3 phần tử.
        Object subArray = sqlArray.getArray(2, 3);
        // Cũng có: sqlArray.getResultSet(2, 3).
    } finally {
        sqlArray.free();
    }
}
~~~

Trong API JDBC, chỉ số truyền vào `getArray(index, count)` và `getResultSet(index, count)` **bắt đầu từ 1**, không phải từ 0 như truy cập `javaArray[0]`. Đoạn yêu cầu phải nằm trong giới hạn mảng; driver có thể ném `SQLException` khi chỉ số hoặc `count` không hợp lệ.

## 6. Dùng SQL ARRAY trong điều kiện truy vấn

Một ứng dụng phổ biến của ARRAY là **truyền nhiều tham số qua một placeholder**. Trên PostgreSQL:

~~~sql
-- Tìm bài viết có nhãn 'jdbc'.
SELECT id, tags
FROM article
WHERE 'jdbc' = ANY(tags);

-- Tìm bài viết có nhãn 'jdbc' theo phép chứa mảng của PostgreSQL.
SELECT id, tags
FROM article
WHERE tags @> ARRAY['jdbc']::text[];
~~~

Sử dụng `PreparedStatement` để truyền một **giá trị** cần đối chiếu:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id FROM article WHERE ? = ANY(tags)")) {
    ps.setString(1, "jdbc");
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong(1));
        }
    }
}
~~~

Hoặc truyền **một danh sách ID** để đối chiếu với mỗi hàng:

~~~java
Long[] ids = {10L, 20L, 30L};
Array sqlIds = connection.createArrayOf("bigint", ids);
try {
    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT id FROM article WHERE id = ANY(?)")) {
        ps.setArray(1, sqlIds);
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("id"));
            }
        }
    }
} finally {
    sqlIds.free();
}
~~~

`ANY`, `@>`, `::text[]` và các cú pháp mảng trên thuộc **PostgreSQL**, không phải các toán tử/cú pháp thống nhất cho mọi DBMS. Với một CSDL không hỗ trợ truyền ARRAY như vậy, cần chọn cách truyền tập giá trị khác, chẳng hạn nhiều placeholder `IN (?, ?, ...)`, bảng tạm hoặc cơ chế tham số dạng bảng mà DBMS cung cấp.

Lưu ý: `WHERE id IN (?)` **không có nghĩa** JDBC sẽ tự mở rộng một `Array` thành danh sách `?, ?, ?`. Một placeholder biểu diễn một tham số SQL; cú pháp SQL phải hỗ trợ kiểu giá trị được gán.

## 7. Vòng đời và lỗi thường gặp

### 7.1. Giải phóng ARRAY đúng lúc

Một quy tắc an toàn là:

1. Tạo `Array` bằng `createArrayOf`, hoặc lấy bằng `ResultSet.getArray`.
2. Hoàn tất `setArray` **và thực thi câu lệnh**, hoặc đọc dữ liệu bằng `getArray/getResultSet`.
3. Gọi `free()` trong `finally` sau khi không còn cần đối tượng.
4. Đóng `ResultSet` thành phần trước khi giải phóng `Array`, đóng `PreparedStatement`, và đóng/trả `Connection` khi tầng sở hữu kết nối kết thúc.

Đừng `free()` ngay sau `ps.setArray(...)` nếu câu lệnh chưa được thực thi: driver có thể còn cần giá trị khi `executeUpdate()` hoặc `executeQuery()` chạy.

### 7.2. Các lỗi phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `SQLFeatureNotSupportedException` khi gọi `createArrayOf` | Driver/DBMS không hỗ trợ chức năng tương ứng | Kiểm tra phiên bản driver và cơ chế collection của DBMS; cân nhắc chiến lược thay thế. |
| Lỗi tên kiểu `typeName` | Truyền tên kiểu mảng thay vì kiểu phần tử, hoặc dùng tên kiểu của DBMS khác | Dùng tên kiểu phần tử phù hợp, ví dụ `text` với `TEXT[]` của PostgreSQL. |
| Lỗi kiểu Java khi đọc | Ép `Object` từ `getArray()` thành loại mảng không tương thích | Kiểm tra kiểu runtime, dùng mapping phù hợp hoặc `getResultSet()`. |
| Không biên dịch được `createArrayOf("integer", ids)` | `ids` là `int[]`, không phải `Object[]` | Chuyển sang `Integer[]`. |
| Đọc ra `null` nhưng mong đợi danh sách rỗng | Cột chứa SQL `NULL` | Xác định chính sách null/rỗng riêng. |
| Lỗi sau khi `free()` | Tiếp tục sử dụng `Array` đã giải phóng | Không tái sử dụng; tạo giá trị `Array` mới khi cần. |
| Truy vấn `IN (?)` không lọc đúng nhiều ID | Cho rằng một placeholder được tự động mở rộng thành nhiều phần tử | Dùng cú pháp mảng của DBMS hoặc tạo đúng số placeholder. |
| Dữ liệu mảng lớn làm tiêu tốn bộ nhớ | Driver phải chuyển đổi hoặc lưu nhiều phần tử cùng lúc | Đánh giá kích thước dữ liệu, chia lô/bảng tạm, kiểm tra hành vi driver. |

### 7.3. Kiểu mảng nhiều chiều và kiểu tự định nghĩa

SQL ARRAY có thể có quy tắc riêng về số chiều, kiểu phần tử phức hợp, chỉ số dưới và cách ánh xạ. Ví dụ PostgreSQL hỗ trợ mảng nhiều chiều, nhưng **không nên giả định** một `Object[][]` sẽ được mọi JDBC driver chuyển đổi giống nhau. Các kiểu cấu trúc hoặc kiểu do người dùng định nghĩa có thể cần mapping riêng. Hãy kiểm tra tài liệu driver, metadata SQL và thử nghiệm với đúng DBMS trước khi triển khai.

## 8. Tự thực hành và câu hỏi kiểm tra

Hãy dùng bảng `article` trong PostgreSQL và thử tuần tự:

1. Chèn `new String[]{"java", "jdbc"}` qua `createArrayOf("text", ...)` và `setArray`. Đọc lại bằng `getArray()` và `getResultSet()`, so sánh thứ tự các phần tử.
2. Chèn mảng rỗng, sau đó cập nhật cột thành SQL `NULL`. Xác nhận một trường hợp trả mảng rỗng, trường hợp còn lại `rs.getArray("tags") == null`.
3. Chèn mảng có một phần tử `null`; kiểm tra `elements.getString(2)` trả giá trị gì ở vị trí đó.
4. Thử `getArray(2, 1)` trên mảng có ít nhất hai phần tử; so sánh vị trí bắt đầu với `tags[1]` trong Java.
5. Truy vấn `SELECT id FROM article WHERE id = ANY(?)` bằng `Long[]`; sau đó thử `WHERE id IN (?)` để hiểu vì sao hai cách gán tham số không tương đương.

Trước khi đưa một lời giải ARRAY vào sản xuất, cần trả lời: **DBMS và driver có hỗ trợ SQL ARRAY không? Kiểu phần tử SQL nào chính xác? Ứng dụng có phân biệt NULL, rỗng và phần tử NULL không? Ai chịu trách nhiệm gọi `free()`? Truy vấn cần cú pháp/đánh chỉ mục riêng nào?**

**Ghi nhớ:** chuyển `String[]` hoặc `Integer[]` thành SQL ARRAY bằng `Connection.createArrayOf`, truyền bằng `PreparedStatement.setArray`, đọc bằng `ResultSet.getArray` rồi `Array.getArray`/`getResultSet`, và gọi `Array.free()` khi xong. Đây là chu trình cơ bản để làm việc với mảng giá trị Java và SQL ARRAY thông qua JDBC; tính tương thích của kiểu mảng và cú pháp SQL vẫn phải kiểm chứng theo từng hệ quản trị cơ sở dữ liệu.
