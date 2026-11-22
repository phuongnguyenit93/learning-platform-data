# Đối chiếu hành vi NULL, chuỗi rỗng và so sánh chuỗi

Ứng dụng **JDBC** có thể dùng cùng `DataSource`, `PreparedStatement` và `ResultSet` để làm việc với nhiều cơ sở dữ liệu quan hệ. Tuy nhiên, cùng một giá trị Java `""`, cùng câu SQL `WHERE name = ?` hoặc cùng ràng buộc `UNIQUE` **không chắc có cùng ý nghĩa trên mọi DBMS**. Khác biệt về `NULL`, chuỗi rỗng, kiểu `CHAR`/`VARCHAR`, collation và Unicode có thể dẫn đến lỗi tìm kiếm, trùng khóa, mất dữ liệu khi migration hoặc kết quả kiểm thử chỉ đúng trên một hệ quản trị.

Trong chương **Đa hệ quản trị** của module **JDBC**, bài này tập trung vào cách **đối chiếu có kiểm soát** hành vi `NULL`, `""`, chuỗi toàn dấu cách và so sánh chuỗi. Bạn sẽ dùng SQL tham số hóa, `setString()`/`setNull()`, `getString()`/`wasNull()`, các phép so sánh và bộ kiểm thử trên nhiều JDBC driver để xác định **hợp đồng dữ liệu thực tế** thay vì dựa vào giả định “chuỗi là chuỗi”.

> **Điểm quan trọng nhất:** `NULL` không phải chuỗi rỗng. Đặc biệt, **Oracle hiện xem chuỗi ký tự độ dài 0 là `NULL` đối với các kiểu chuỗi như `VARCHAR2`**, còn PostgreSQL, MySQL và SQL Server thường giữ `''` tách biệt với `NULL` ở cột chuỗi thông thường. Ngoài ra, **“bằng nhau” trong SQL phụ thuộc kiểu và collation**, không nhất thiết giống `String.equals()` của Java.

## 1. Ba trạng thái cần phân biệt từ đầu

Giả sử một form đăng ký có trường `display_name`. Ba đầu vào sau có thể mang ba ý nghĩa nghiệp vụ khác nhau:

| Giá trị Java | Diễn giải có thể chọn | Trong Java |
| --- | --- | --- |
| `null` | Chưa được cung cấp/không biết/không áp dụng. | `value == null` là `true`. |
| `""` | Người dùng đã gửi một chuỗi độ dài bằng 0. | `value != null` và `value.isEmpty()` là `true`. |
| `" "` | Có đúng một ký tự dấu cách. | Không rỗng; `value.isBlank()` là `true` trên Java 11+. |

**Không có ý nghĩa nghiệp vụ mặc định** cho ba giá trị này. Có ứng dụng muốn giữ nguyên `""`, có ứng dụng muốn coi `""` như `NULL`, có ứng dụng muốn từ chối cả chuỗi trắng. Hãy quyết định và ghi thành quy tắc của API trước khi thiết kế repository, validation, migration hoặc đồng bộ dữ liệu nhiều DBMS.

Ví dụ:

```java
String missing = null;
String empty = "";
String spaces = "  ";

System.out.println(missing == null); // true
System.out.println(empty.isEmpty());  // true
System.out.println(spaces.isEmpty()); // false
System.out.println(spaces.isBlank()); // true (Java 11+)
```

Không gọi `isEmpty()`/`isBlank()` khi biến có thể `null` mà chưa kiểm tra. `String.trim()`, `String.strip()` và `isBlank()` có các quy tắc ký tự trắng khác nhau; việc “trim rồi coi rỗng là NULL” là **chính sách chuẩn hóa của ứng dụng**, không phải hành vi mặc định của JDBC.

## 2. NULL trong SQL: logic ba giá trị

SQL sử dụng logic **TRUE**, **FALSE** và **UNKNOWN** đối với các phép so sánh liên quan đến `NULL`. Chẳng hạn:

```sql
-- Không đúng: phép so sánh với NULL không trả TRUE.
WHERE display_name = NULL

-- Đúng khi muốn tìm giá trị SQL NULL.
WHERE display_name IS NULL

-- Đúng khi muốn loại bỏ giá trị SQL NULL.
WHERE display_name IS NOT NULL
```

Kể cả `NULL = NULL` hoặc `NULL <> NULL` cũng cho kết quả **UNKNOWN**, không phải `TRUE`. Trong mệnh đề `WHERE`, chỉ các hàng có điều kiện **TRUE** mới được giữ; `FALSE` và `UNKNOWN` đều bị loại.

| Giá trị `display_name` | `display_name = 'Mai'` | `display_name <> 'Mai'` | `display_name IS NULL` |
| --- | --- | --- | --- |
| `'Mai'` | TRUE | FALSE | FALSE |
| `'An'` | FALSE | TRUE | FALSE |
| `NULL` | UNKNOWN | UNKNOWN | TRUE |

Hai lỗi phổ biến:

1. `WHERE display_name <> ?` **không** tự chọn cả hàng có `NULL`. Nếu nghiệp vụ muốn “khác giá trị X **hoặc chưa có tên**”, phải thể hiện điều kiện `OR display_name IS NULL` hoặc dùng phép so sánh null-safe được DBMS hỗ trợ.
2. `NOT IN` với danh sách chứa `NULL` có thể loại cả những hàng tưởng như hợp lệ. Ví dụ về mặt logic `1 NOT IN (2, NULL)` là UNKNOWN. Khi dữ liệu con có thể `NULL`, nhiều bài toán nên dùng `NOT EXISTS` với điều kiện nối phù hợp.

### Các hàm NULL cũng không xóa khác biệt DBMS

`COALESCE(expr, fallback)` chọn biểu thức **không NULL đầu tiên**. `COUNT(column)` không tính các hàng mà `column` là `NULL`, trong khi `COUNT(*)` đếm mọi hàng:

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(display_name) AS non_null_names
FROM customer_labels;
```

Ở PostgreSQL/MySQL/SQL Server, `COALESCE(NULL, '')` thường trả chuỗi rỗng. **Trên Oracle, chính literal `''` cũng được xem là `NULL`**, nên `COALESCE(NULL, '')` vẫn là `NULL`. Đó là lý do không thể dùng `COALESCE(column, '')` làm một biểu thức “đảm bảo trả chuỗi không NULL” trên tất cả DBMS.

`NULLIF(a, b)` trả `NULL` khi hai biểu thức so sánh bằng nhau, nhưng phép “bằng nhau” vẫn chịu ảnh hưởng của collation, kiểu chuỗi và chính sách chuỗi rỗng. Không áp dụng `NULLIF(TRIM(name), '')` như một công thức di động tuyệt đối khi migration.

## 3. Bảng đối chiếu: NULL và chuỗi rỗng giữa các hệ quản trị

Bảng sau nói về **cột chuỗi ký tự thông thường** và hành vi phổ biến của DBMS hiện đại; cần kiểm tra phiên bản, kiểu cột, driver và cấu hình cụ thể:

| Câu hỏi | PostgreSQL | MySQL | SQL Server | Oracle |
| --- | --- | --- | --- | --- |
| `VARCHAR`/`TEXT` lưu `''` tách biệt `NULL`? | **Có**, với kiểu chuỗi thông dụng. | **Có**, với kiểu chuỗi thông dụng. | **Có**, với `varchar`/`nvarchar`. | **Không** đối với chuỗi độ dài 0 ở `VARCHAR2`/`NVARCHAR2`: được xử lý như `NULL`. |
| `IS NULL` có khớp hàng đã gán `''` không? | Không, nếu hàng thực sự lưu chuỗi rỗng. | Không, nếu hàng thực sự lưu chuỗi rỗng. | Không, nếu hàng thực sự lưu chuỗi rỗng. | **Có** nếu `''` được chuyển thành `NULL`. |
| `LENGTH('')` hoặc hàm đo độ dài tương đương | `0`. | `CHAR_LENGTH('') = 0`. | `LEN('') = 0`. | `LENGTH('')` là `NULL` vì literal rỗng được hiểu là `NULL`. |
| `getString()` trên hàng lưu `NULL` | Java `null`. | Java `null`. | Java `null`. | Java `null`. |
| So sánh `'abc'` với `'ABC'` | Theo collation/cách so sánh. | Theo collation. | Theo collation. | Theo collation và cấu hình so sánh. |
| So sánh `'abc'` với `'abc '` | Phụ thuộc kiểu, `varchar`/`text` thường phân biệt. | Phụ thuộc collation và thuộc tính padding. | Nhiều phép so sánh bằng của chuỗi ký tự **bỏ qua dấu cách cuối**. | Phụ thuộc kiểu và ngữ nghĩa so sánh blank-padded/nonpadded. |

**Giới hạn quan trọng của bảng:**

- Không suy luận rằng toàn bộ Oracle `CLOB`, `BLOB` hay mọi loại dữ liệu đều có cùng chính sách với `VARCHAR2`. Ví dụ LOB rỗng có thể khác `NULL`; phải kiểm tra theo kiểu dữ liệu thực.
- Kiểu `CHAR(n)` có quy tắc **đệm dấu cách** và so sánh khác `VARCHAR`/`VARCHAR2`. Không dùng kết quả đo trên `CHAR` để suy ra hành vi của mọi cột chuỗi.
- PostgreSQL, MySQL, SQL Server và Oracle đều có tùy chọn collation/case/accent ở những mức khác nhau; **không gắn nhãn “luôn phân biệt hoa thường” hoặc “luôn không phân biệt” cho cả DBMS**.
- Oracle hiện xử lý chuỗi ký tự độ dài 0 như `NULL`; thiết kế ứng dụng nên coi đây là **hành vi triển khai cần xác nhận**, không xây một hợp đồng dữ liệu rằng mọi phiên bản tương lai và mọi kiểu dữ liệu bắt buộc giống nhau.

### Một chuỗi rỗng có thể biến thành NULL mà không có lỗi JDBC

```java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customer_labels (id, label) VALUES (?, ?)")) {
    ps.setLong(1, 101L);
    ps.setString(2, ""); // Truyền đúng Java String độ dài 0.
    ps.executeUpdate();
}
```

JDBC không tự định nghĩa rằng mọi DBMS phải lưu `""` thành một chuỗi rỗng riêng biệt. Trên Oracle `VARCHAR2`, truy vấn đọc lại có thể thấy `NULL` và `ResultSet.getString("label")` trả Java `null`. **Không được kết luận driver đã “làm mất dữ liệu” theo một quy tắc JDBC chung**; cần xét semantics cột và DBMS đang lưu trữ.

Nếu API bắt buộc phân biệt “không được gửi” với “đã gửi rỗng”, ứng dụng sử dụng Oracle `VARCHAR2` cần một mô hình dữ liệu khác: ví dụ **cột trạng thái riêng** (có giá trị đã-cung-cấp hay chưa), hoặc encoding/biểu diễn được thiết kế tường minh. Không sử dụng một ký tự giả như dấu cách tùy tiện: nó có thể hợp lệ với người dùng, bị chuẩn hóa hoặc so sánh bằng chuỗi rỗng dưới một số collation.

## 4. Ví dụ kiểm thử round-trip JDBC trên từng DBMS

Muốn biết DBMS thực sự lưu gì, hãy kiểm thử theo chu trình **Java → PreparedStatement → DBMS → ResultSet → Java**. Dùng bảng dành riêng cho môi trường integration test:

```sql
-- Ví dụ DDL cho PostgreSQL/MySQL/SQL Server;
-- tùy DBMS có thể cần điều chỉnh kiểu và migration.
CREATE TABLE customer_labels (
    id BIGINT PRIMARY KEY,
    label VARCHAR(80) NULL
);
```

Với Oracle, có thể dùng kiểu tương ứng:

```sql
CREATE TABLE customer_labels (
    id NUMBER(19) PRIMARY KEY,
    label VARCHAR2(80)
);
```

Mã dưới đây dùng `DataSource`, gửi ba trạng thái `null`, `""` và `" "`, rồi đọc lại từng hàng. Tất cả hoạt động nằm trong **một transaction thử nghiệm** và được `rollback()` ở cuối để không giữ dữ liệu mẫu. Mỗi DBMS nên dùng một `DataSource` riêng trỏ đến **database/schema test được cấp quyền phù hợp**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class StringRoundTripProbe {
    private final DataSource dataSource;

    public StringRoundTripProbe(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public List<ObservedValue> inspect(long firstId)
            throws SQLException {
        if (firstId < 1 || firstId > Long.MAX_VALUE - 2) {
            throw new IllegalArgumentException("firstId không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ tự sở hữu transaction, không dùng dưới transaction
            // manager/framework đang điều khiển Connection.
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu autoCommit=true ban đầu");
            }
            connection.setAutoCommit(false);

            Throwable originalFailure = null;
            boolean rolledBack = false;
            try {
                insert(connection, firstId, null);
                insert(connection, firstId + 1, "");
                insert(connection, firstId + 2, " ");

                String sql = "SELECT id, label FROM customer_labels "
                           + "WHERE id >= ? AND id <= ? ORDER BY id";
                List<ObservedValue> result = new ArrayList<>();
                try (PreparedStatement ps =
                             connection.prepareStatement(sql)) {
                    ps.setLong(1, firstId);
                    ps.setLong(2, firstId + 2);
                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long id = rs.getLong("id");
                            String label = rs.getString("label");
                            boolean sqlNull = rs.wasNull();
                            result.add(new ObservedValue(
                                    id, label, sqlNull));
                        }
                    }
                }
                return result; // finally vẫn rollback trước khi trả về.
            } catch (SQLException | RuntimeException failure) {
                originalFailure = failure;
                throw failure;
            } finally {
                try {
                    connection.rollback();
                    rolledBack = true;
                } catch (SQLException rollbackFailure) {
                    if (originalFailure != null) {
                        originalFailure.addSuppressed(rollbackFailure);
                    } else {
                        throw rollbackFailure;
                    }
                }
                if (rolledBack) {
                    try {
                        connection.setAutoCommit(true);
                    } catch (SQLException resetFailure) {
                        if (originalFailure != null) {
                            originalFailure.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
                // Nếu rollback thất bại, không ép autoCommit=true:
                // pool phải xử lý connection không còn đáng tin cậy.
            }
        }
    }

    private static void insert(
            Connection connection, long id, String value)
            throws SQLException {
        String sql = "INSERT INTO customer_labels (id, label) "
                   + "VALUES (?, ?)";
        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {
            ps.setLong(1, id);
            if (value == null) {
                ps.setNull(2, Types.VARCHAR);
            } else {
                ps.setString(2, value);
            }
            ps.executeUpdate();
        }
    }

    public static final class ObservedValue {
        public final long id;
        public final String label;
        public final boolean sqlNull;

        ObservedValue(long id, String label, boolean sqlNull) {
            this.id = id;
            this.label = label;
            this.sqlNull = sqlNull;
        }

        public String kind() {
            if (sqlNull) return "NULL";
            if (label.isEmpty()) return "EMPTY";
            if (label.isBlank()) return "BLANK";
            return "TEXT";
        }
    }
}
```

Đoạn sử dụng, khi đã có `dataSource` phù hợp:

```java
StringRoundTripProbe probe = new StringRoundTripProbe(dataSource);
List<StringRoundTripProbe.ObservedValue> values =
        probe.inspect(9001L);

for (StringRoundTripProbe.ObservedValue value : values) {
    System.out.printf(
            "id=%d, kind=%s, sqlNull=%s, value=%s%n",
            value.id, value.kind(), value.sqlNull, value.label);
}
```

**Kỳ vọng định hướng khi dùng `VARCHAR`/`VARCHAR2` như ví dụ:**

| ID | Đầu vào `setString`/`setNull` | PostgreSQL/MySQL/SQL Server | Oracle `VARCHAR2` |
| --- | --- | --- | --- |
| `9001` | `setNull(..., Types.VARCHAR)` | `NULL` | `NULL` |
| `9002` | `setString(..., "")` | `EMPTY` | `NULL` |
| `9003` | `setString(..., " ")` | `BLANK` | `BLANK` |

**Chú ý:** `getString()` trả `null` cho SQL `NULL`. Gọi `wasNull()` **ngay sau getter** muốn kiểm tra (ở ví dụ là sau `getString("label")`), vì nó phản ánh **cột được đọc gần nhất**. Với `String`, kiểm tra `label == null` cũng đủ nhận diện giá trị SQL NULL, nhưng `wasNull()` giúp minh họa quy tắc dùng getter của JDBC và đặc biệt quan trọng khi dùng getter nguyên thủy như `getInt()`/`getLong()`.

Ví dụ dùng `String.isBlank()` nên cần **Java 11 trở lên**. `firstId` phải thuộc khoảng khóa chưa có trong fixture; nếu ID trùng hoặc có worker khác sửa dữ liệu, phép thử sẽ không độc lập. Sau rollback, hãy xác nhận bảng không còn các hàng mẫu đã chèn. Không chạy trên database dùng cho sản xuất và không mặc định driver hỗ trợ mọi quy tắc tương tự nhau đối với kiểu chuỗi đặc thù.

## 5. Lọc bằng NULL và chuỗi rỗng: đừng bind mọi thứ vào dấu bằng

Đây là lỗi thường gặp:

```java
String sql = "SELECT id FROM customer_labels WHERE label = ?";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setNull(1, java.sql.Types.VARCHAR);
    try (ResultSet rs = ps.executeQuery()) {
        System.out.println(rs.next()); // false theo logic NULL chuẩn.
        // Phép label = NULL không tìm các hàng có label IS NULL.
    }
}
```

Vấn đề không phải `setNull()` lỗi mà vì **`label = NULL` có kết quả UNKNOWN**. Muốn tìm các hàng SQL NULL, cần câu SQL `IS NULL`:

```sql
SELECT id FROM customer_labels WHERE label IS NULL;
```

### DAO có hai nhánh SQL tĩnh

Để tránh nối input vào cú pháp, có thể viết:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

static List<Long> findIdsByLabel(
        Connection connection, String expected)
        throws SQLException {
    String sql = expected == null
            ? "SELECT id FROM customer_labels "
              + "WHERE label IS NULL ORDER BY id"
            : "SELECT id FROM customer_labels "
              + "WHERE label = ? ORDER BY id";

    List<Long> ids = new ArrayList<>();
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        if (expected != null) {
            ps.setString(1, expected);
        }
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                ids.add(rs.getLong(1));
            }
        }
    }
    return ids;
}
```

Đây là phương thức tiện ích đặt bên trong một lớp Java; caller quản lý `Connection`/transaction. Nó **cố ý** phân biệt Java `null` với `""` ở phía nhập. Nhưng nếu database là Oracle và `expected=""`, `setString("", ...)` có thể trở thành `NULL`; nhánh `label = ?` **không** có cùng ý nghĩa như nhánh `IS NULL`. Vì vậy repository phải nhận **giá trị đã chuẩn hóa theo hợp đồng lưu trữ** hoặc một đối tượng truy vấn biểu thị rõ “tìm NULL”/“tìm rỗng” trước khi gọi SQL.

Nếu nghiệp vụ muốn coi `null` và `""` như nhau, hãy chuẩn hóa tường minh tại biên API; nếu nghiệp vụ cần phân biệt, phải thiết kế lược đồ có khả năng biểu diễn cả hai trạng thái trên mọi DBMS mục tiêu. Không để sự khác biệt Oracle âm thầm quyết định quy tắc nghiệp vụ.

### Còn so sánh NULL-safe thì sao?

Một số DBMS hỗ trợ `IS [NOT] DISTINCT FROM` theo các phiên bản nhất định; MySQL có toán tử null-safe `<=>`. Những cách này có thể giúp so sánh hai giá trị cùng `NULL` một cách có chủ ý, nhưng **không thể giả định một cú pháp dùng nguyên vẹn trên mọi phiên bản PostgreSQL, SQL Server, MySQL và Oracle**. Nếu cần tính di động, dùng adapter SQL theo DBMS hoặc hai nhánh tĩnh `IS NULL`/`= ?` như ví dụ, rồi kiểm thử hành vi thật.

## 6. So sánh chuỗi: collation quan trọng hơn cú pháp dấu bằng

Câu lệnh:

```sql
SELECT id FROM customer_labels WHERE label = ?;
```

không có nghĩa DBMS sẽ so sánh **từng byte** như Java `String.equals()`. Tùy kiểu chuỗi, collation của cột/biểu thức/database và quy tắc padding, hai giá trị ký tự khác nhau vẫn có thể được xem là bằng nhau, hoặc ngược lại.

| Cặp chuỗi | Câu hỏi cần kiểm tra | Có thể khác vì |
| --- | --- | --- |
| `"An"` và `"an"` | Có phân biệt chữ hoa/chữ thường không? | Collation case-sensitive/case-insensitive. |
| `"cafe"` và `"café"` | Có phân biệt dấu/âm sắc không? | Accent-sensitive hoặc accent-insensitive collation. |
| `"A"` và `"A "` | Dấu cách cuối có ảnh hưởng đến `=` không? | Kiểu `CHAR`/`VARCHAR` và quy tắc padding. |
| `"é"` và `"e\u0301"` | Chuỗi Unicode dựng sẵn và tổ hợp có được xem tương đương không? | Collation và dạng chuẩn hóa Unicode. |
| `""` và `" "` | Có khác rỗng với một dấu cách không? | Oracle empty-as-NULL, padding/collation ở DBMS khác. |
| `"2"` và `"10"` | Thứ tự sắp xếp chữ có giống thứ tự số không? | So sánh chuỗi, numeric collation, kiểu dữ liệu. |

**Không đánh giá “DBMS nào đúng” bằng một câu SQL duy nhất.** Nếu nghiệp vụ quy định mã định danh `"AB12"` khác `"ab12"`, collation không phân biệt hoa/thường có thể **vi phạm hợp đồng** dù câu SQL hợp lệ. Ngược lại, với tên người dùng muốn tìm kiếm không phân biệt hoa thường, collation phân biệt hoa thường có thể làm trải nghiệm không đạt yêu cầu.

### Khác biệt theo DBMS phải được kiểm tra tại nơi triển khai

- **PostgreSQL:** kiểu `text`/`varchar` với nhiều collation deterministic phổ biến phân biệt các chuỗi khác ký tự, nhưng có các lựa chọn kiểu/collation cho so sánh không phân biệt trong những điều kiện nhất định. `char(n)` có quy tắc dấu cách cuối khác `varchar`/`text`.
- **MySQL:** collation của column có thể phân biệt hoặc không phân biệt hoa thường/dấu, và thuộc tính **`PAD SPACE`/`NO PAD`** ảnh hưởng so sánh dấu cách cuối. Không coi mọi `utf8mb4` collation là giống nhau.
- **SQL Server:** tên collation thường thể hiện thuộc tính như `CI`/`CS` và `AI`/`AS`. Nhiều phép so sánh chuỗi bằng có quy tắc **đệm dấu cách cuối**; ngay cả một collation case-sensitive cũng không mặc nhiên tương đương so sánh byte-for-byte của Java.
- **Oracle:** `VARCHAR2` không lưu chuỗi độ dài 0 riêng `NULL`; ngoài ra có khác biệt giữa **blank-padded** và **nonpadded** comparison tùy kiểu toán hạng, và cấu hình/collation ngôn ngữ. Tránh áp quy tắc của literal `CHAR` lên mọi cột `VARCHAR2`.

Khi dùng `ORDER BY`, cùng collation cũng có thể cho thứ tự khác nhau. Một số DBMS mặc định sắp `NULL` trước, một số sau; nếu việc phân trang cần thứ tự ổn định, đừng phụ thuộc mặc định. Ví dụ biểu diễn thứ tự `NULL` cuối bằng SQL phổ biến:

```sql
SELECT id, label
FROM customer_labels
ORDER BY CASE WHEN label IS NULL THEN 1 ELSE 0 END,
         label,
         id;
```

`id` là khóa duy nhất để cố định thứ tự khi `label` có giá trị trùng theo collation. Tuy vậy, **thứ tự giữa các giá trị text khác nhau vẫn chịu ảnh hưởng của collation**, nên không được sử dụng thứ tự đó làm cursor chung cho hai database khác collation mà không thiết kế lại khóa phân trang.

## 7. Dấu cách cuối, CHAR/VARCHAR và độ dài chuỗi

Một tình huống dễ gây sai khi chuyển DBMS:

```sql
SELECT id
FROM customer_labels
WHERE label = 'ABC';
```

Trên một hệ thống, hàng lưu `"ABC "` có thể khớp do quy tắc so sánh đệm dấu cách; trên hệ thống khác với kiểu/collation khác, có thể không. Vì vậy:

- Đừng dùng `WHERE label = ''` làm phép thử **chuỗi có đúng 0 ký tự** trên mọi DBMS. Trên Oracle `VARCHAR2`, literal rỗng là `NULL`; trên SQL Server, nhiều phép so sánh bằng có quy tắc dấu cách cuối.
- `CHAR(n)` thường lưu hoặc so sánh với **padding**, không tương đương `VARCHAR(n)` về trailing spaces.
- Không lấy `LEN()`, `LENGTH()`, `CHAR_LENGTH()` hoặc độ dài của `getString()` làm một tiêu chuẩn duy nhất nếu chưa thống nhất **độ dài theo ký tự, mã Unicode, byte, hay dấu cách cuối**. Ví dụ `LEN` của SQL Server có quy tắc bỏ dấu cách cuối trong nhiều trường hợp.
- `DATALENGTH` (SQL Server) hay `OCTET_LENGTH` trên những DBMS hỗ trợ có thể hữu ích để khảo sát **số byte lưu trữ** nhưng cú pháp và encoding khác nhau. Không kết luận hai chuỗi nghiệp vụ tương đương chỉ vì cùng độ dài byte.

Một quyết định thiết kế quan trọng: **mã kỹ thuật** (SKU, token nghiệp vụ, external key) nên có quy tắc chuẩn hóa và so sánh khác với **tên hiển thị tự do**. Không nên dùng `TRIM`/`LOWER` cho mọi cột một cách tự động.

## 8. Unicode, hoa/thường và chuẩn hóa đầu vào

Hai chuỗi trông giống nhau trên giao diện có thể chứa dãy mã Unicode khác nhau. Ví dụ ký tự `é` có thể biểu diễn bằng một mã dựng sẵn (`U+00E9`) hoặc `e` theo sau là combining acute accent (`U+0065 U+0301`). Với Java `String.equals()`, hai biểu diễn khác nhau có thể **không bằng nhau**, dù được hiển thị tương tự.

Nếu nghiệp vụ cần một khóa tìm kiếm có quy tắc nhất quán, có thể chuẩn hóa ở biên ứng dụng:

```java
import java.text.Normalizer;
import java.util.Locale;

public final class LabelNormalizer {
    public static String normalizeForStorage(String input) {
        if (input == null) {
            return null;
        }
        // Giữ phân biệt NULL và EMPTY; chỉ chuẩn hóa dạng Unicode.
        return Normalizer.normalize(input, Normalizer.Form.NFC);
    }

    public static String simpleCaseFoldForLookup(String input) {
        if (input == null) {
            return null;
        }
        return Normalizer.normalize(input, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);
    }
}
```

Tên `simpleCaseFoldForLookup` ở đây chỉ mô tả **lowercase đơn giản cho ví dụ**, **không phải Unicode full case folding**. Các quy tắc chữ hoa/thường có ngoại lệ theo ngôn ngữ và ký tự; nếu hệ thống quản lý tên người hoặc tên pháp lý, hãy chọn chính sách locale/collation phù hợp. `NFC` giúp thống nhất biểu diễn Unicode ở phía Java, **không tự thay đổi collation hoặc cách đánh chỉ mục ở DBMS**.

Nếu muốn so sánh **không phân biệt hoa thường** trong SQL:

```sql
SELECT id FROM customer_labels
WHERE LOWER(label) = LOWER(?);
```

Đây là cách viết minh họa, **không phải bảo đảm di động tuyệt đối** cho mọi locale, Unicode hay collation. Gọi hàm lên cột cũng có thể khiến chỉ mục thông thường khó được sử dụng, trừ khi DBMS có functional/computed index hoặc chiến lược index phù hợp. Hơn nữa, `LOWER()` không tự biến chuỗi không dấu thành có dấu hoặc xử lý mọi trường hợp Unicode tương đương.

**Chiến lược cho mã định danh nghiệp vụ:** khi cần so sánh nhất quán xuyên DBMS, có thể lưu thêm `normalized_key` được tính theo **một quy tắc Java cố định**, dùng equality/unique constraint theo cấu hình database đã kiểm thử. Không cho rằng chuẩn hóa ở Java **tự khắc** xóa mọi khác biệt của collation SQL; phải kiểm tra cả index, constraint và dữ liệu migration.

## 9. Tìm kiếm LIKE và ký tự đặc biệt

`LIKE` dùng wildcard: `%` khớp nhiều ký tự và `_` khớp một ký tự theo quy tắc DBMS. Nếu nhận chuỗi từ người dùng rồi nối trực tiếp vào pattern, một input có `%` hoặc `_` có thể thay đổi ý nghĩa tìm kiếm dù bạn vẫn bind bằng `PreparedStatement`.

Ví dụ muốn tìm **chuỗi con theo nghĩa literal**:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

static String escapeBasicLike(String raw) {
    return raw.replace("!", "!!")
              .replace("%", "!%")
              .replace("_", "!_");
}

static List<Long> containsLiteral(
        Connection connection, String text) throws SQLException {
    if (text == null) {
        throw new IllegalArgumentException("text không được NULL");
    }
    String sql = "SELECT id FROM customer_labels "
               + "WHERE label LIKE ? ESCAPE '!' ORDER BY id";
    List<Long> ids = new ArrayList<>();
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setString(1, "%" + escapeBasicLike(text) + "%");
        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                ids.add(rs.getLong(1));
            }
        }
    }
    return ids;
}
```

Hai hàm là đoạn mã đặt trong một lớp Java; caller quản lý `Connection`. Cách escape trên chỉ xử lý các ký tự wildcard **cơ bản** `%`, `_` và ký tự escape `!`. Ví dụ SQL Server có cú pháp mẫu với dấu ngoặc vuông `[...]`; cú pháp `LIKE`, ký tự escape, collation và hành vi đối với Unicode cần kiểm thử trên **từng DBMS**. Với văn bản dài, tìm kiếm toàn văn có thể cần full-text index hoặc công cụ tìm kiếm riêng; `LIKE '%...%'` có thể không tận dụng chỉ mục B-tree thông thường.

Nếu `text=""`, pattern trở thành `"%%"`, vốn không diễn đạt một câu hỏi “cột bằng chuỗi rỗng”. Trong trường hợp cần tìm **chính xác chuỗi rỗng**, hãy sử dụng hợp đồng `EMPTY` riêng và xử lý đặc thù Oracle, không trá hình tìm rỗng bằng một câu `LIKE`.

## 10. UNIQUE, chỉ mục và migration dữ liệu

Khác biệt `NULL`/chuỗi rỗng và collation ảnh hưởng trực tiếp đến **ràng buộc duy nhất**. Một vài câu hỏi bắt buộc kiểm tra trước khi chuyển DBMS:

1. **Một cột UNIQUE có cho nhiều hàng `NULL` không?** PostgreSQL/MySQL/Oracle thường cho nhiều `NULL` với thiết lập thông dụng, nhưng **SQL Server với unique constraint/index một cột thường chỉ cho một hàng có `NULL`**; các loại index có filter và tùy chọn DBMS có thể thay đổi thiết kế. PostgreSQL còn có lựa chọn unique xử lý `NULL` như không phân biệt trong những phiên bản hỗ trợ. Không lấy hành vi của một DBMS làm hợp đồng chung.
2. **`''` có va chạm `NULL` không?** Trên Oracle `VARCHAR2`, có thể là **cùng trạng thái NULL**; trên hệ khác chúng thường khác nhau. Nếu migration từ PostgreSQL giữ cả `NULL` và `''` như hai trạng thái có ý nghĩa, sẽ **mất thông tin** khi chuyển trực tiếp vào một cột Oracle `VARCHAR2`.
3. **`'ABC'` và `'abc'` có được xem là trùng không?** Phụ thuộc collation/index và kiểu cột. Dữ liệu vốn hợp lệ trên DBMS phân biệt hoa/thường có thể bị từ chối trên DBMS có unique index không phân biệt hoa/thường.
4. **`'ABC'` và `'ABC '` có thể va chạm không?** Có, tùy chính sách trailing-space; ngay cả khi Java `String.equals()` trả `false`.
5. **Chỉ mục thay đổi ý nghĩa tìm kiếm không?** Unique constraint và index thường dùng quy tắc so sánh của DBMS/collation; việc thêm functional index/normalized key phải được kiểm thử lại toàn bộ tập dữ liệu hiện hữu.

### Checklist migration tối thiểu

```text
Trước migration:
  - Đếm NULL, EMPTY, BLANK riêng theo DBMS nguồn.
  - Tìm các nhóm giá trị va chạm khi chuyển collation/case/space.
  - Thống nhất chính sách API: giữ rỗng, gộp rỗng, hay từ chối.
  - Quyết định schema biểu diễn đủ trạng thái cần giữ.
  - Thử constraint/unique/index với dữ liệu mẫu và dữ liệu thật.

Sau migration thử nghiệm:
  - Đọc lại qua JDBC, kiểm tra NULL/EMPTY/BLANK.
  - Đối soát số hàng và các khóa nghiệp vụ.
  - So kết quả WHERE = ?, IS NULL, LIKE, ORDER BY.
  - Chạy kiểm thử nhiều Connection và transaction nếu có cập nhật.
```

Không dùng một truy vấn `COUNT(label)` để đếm “không rỗng” rồi cho rằng có thể so trực tiếp giữa Oracle và PostgreSQL: trên Oracle chuỗi rỗng `VARCHAR2` chuyển thành `NULL` sẽ **không được `COUNT(label)` tính**, nhưng trên PostgreSQL chuỗi rỗng **được tính**. Phải định nghĩa lại chỉ số thống kê theo hợp đồng chung.

## 11. Kiểm thử hành vi nhiều DBMS bằng bảng ca kiểm thử

Với mỗi DBMS/driver thực tế, tạo một bảng test riêng và seed các giá trị sau, rồi đối chiếu **cả dữ liệu đọc lại và kết quả SQL**:

| Ca | Giá trị gửi từ Java | Kiểm tra |
| --- | --- | --- |
| 1 | `null` | `getString() == null`, `wasNull()`, `IS NULL`. |
| 2 | `""` | Có giữ `EMPTY` hay biến thành `NULL`? `WHERE label = ?` trả gì? |
| 3 | `" "` | `getString()`, `isBlank()`, có khớp `''` khi `=` không? |
| 4 | `"ABC"`, `"abc"` | Equality, unique index và `ORDER BY` theo collation. |
| 5 | `"cafe"`, `"café"` | Accent-sensitive hay accent-insensitive? |
| 6 | `"ABC"`, `"ABC "` | Trailing-space comparison và độ dài. |
| 7 | `"\u00E9"` và `"e\u0301"` | Unicode composition, normalization, equality. |
| 8 | `"100%"`, `"a_b"`, `"a!b"` | `LIKE` literal với escaping. |
| 9 | `NULL` và `''` trong cột unique | Các trạng thái có bị gộp hay va chạm constraint? |
| 10 | `NULL` trong truy vấn `<>` và `NOT IN` | Có bị loại vì logic UNKNOWN không? |

**Cách tổ chức test:**

- Chạy bộ test theo **DataSource riêng** cho PostgreSQL, MySQL, SQL Server, Oracle tương ứng, dùng DBMS thật hoặc container tương thích; **không dựa vào một DB in-memory** để dự đoán engine khác.
- Ghi lại **phiên bản DBMS, phiên bản JDBC driver, kiểu cột, charset, collation, mức isolation** và cấu hình SQL mode/NLS có liên quan.
- Phân tách **hợp đồng chung** (ví dụ `SQL NULL` trả Java `null` khi `getString`) khỏi **quan sát đặc thù** (`""` trên Oracle, case/accent/trailing-space equality). Chỉ áp assertion cố định cho hành vi mà sản phẩm đã cam kết.
- Khi một lệnh `INSERT` bị unique constraint từ chối, kiểm tra trạng thái transaction và rollback đúng; không biến lỗi thành “mặc định hai chuỗi bằng nhau” khi chưa xác nhận collation/index.
- Dùng `PreparedStatement` tham số hóa với cùng giá trị Java ở từng DBMS, không so các literal SQL vô tình khác kiểu/quoting rồi kết luận do JDBC.

### Mẫu assertion JUnit 5 theo hợp đồng

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import org.junit.jupiter.api.Test;
import java.util.List;

class StringRoundTripIT {
    // Được fixture/extension cấp trước từng test.
    private javax.sql.DataSource testDataSource;
    private boolean oracleVarchar2Semantics;

    @Test
    void readBackNullEmptyAndBlank() throws Exception {
        StringRoundTripProbe probe =
                new StringRoundTripProbe(testDataSource);
        List<StringRoundTripProbe.ObservedValue> rows =
                probe.inspect(9001L);

        assertEquals(3, rows.size());
        assertNull(rows.get(0).label);
        assertEquals("NULL", rows.get(0).kind());

        assertEquals(
                oracleVarchar2Semantics ? "NULL" : "EMPTY",
                rows.get(1).kind());
        assertEquals("BLANK", rows.get(2).kind());
    }
}
```

Đây là **thân lớp integration test minh họa**; phải cấp `testDataSource`, `oracleVarchar2Semantics` và fixture cho đúng hệ quản trị, cùng dependency JUnit 5. Với các phép thử so sánh chữ hoa/dấu/cách cuối, **không hard-code kỳ vọng chỉ bằng tên “MySQL” hay “SQL Server”**; cần kỳ vọng theo **collation và loại cột đang cấu hình**. Nếu muốn phép thử chạy song song, dùng schema/ID khác nhau để không tranh chấp bảng fixture.

## 12. Quyết định chính sách dữ liệu ở biên ứng dụng

Có ba chính sách thường gặp cho đầu vào chuỗi tùy yêu cầu nghiệp vụ:

| Chính sách | Với `null` | Với `""` | Với `" "` | Phù hợp khi |
| --- | --- | --- | --- | --- |
| **PRESERVE** | Giữ NULL. | Cố giữ EMPTY. | Giữ BLANK. | Cần phân biệt tuyệt đối từng trạng thái, **nhưng DBMS đích phải hỗ trợ biểu diễn**. |
| **EMPTY_AS_NULL** | Giữ NULL. | Chuyển NULL. | Giữ BLANK hoặc xử lý theo quy tắc riêng. | Một chuỗi không nhập có cùng nghĩa “không có giá trị”. |
| **REJECT_BLANK** | Tùy trường bắt buộc/không. | Từ chối. | Từ chối. | Mã định danh hoặc tên bắt buộc phải có ký tự có nghĩa. |

Ví dụ chính sách **gộp rỗng thành NULL** ở biên Java:

```java
static String emptyAsNull(String value) {
    return value != null && value.isEmpty() ? null : value;
}

static String rejectBlank(String value) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException("Không chấp nhận chuỗi trắng");
    }
    return value;
}
```

Nếu nghiệp vụ chọn `EMPTY_AS_NULL`, hãy **chuẩn hóa trước cả INSERT lẫn SELECT** để kết quả tìm kiếm nhất quán. Nếu chọn `PRESERVE` nhưng dùng Oracle `VARCHAR2`, chỉ đổi `getString`/`setString` là **không đủ**; cần thêm trạng thái/encoding hoặc lược đồ khác để lưu hai khái niệm độc lập.

**Không trộn các chính sách:** tầng API coi `""` như giá trị hợp lệ, DAO tự chuyển nó thành `null`, còn service lại so sánh bằng `String.equals()` sẽ gây ra hành vi không thể giải thích nhất quán. Nên định nghĩa một hợp đồng rõ ràng cho dữ liệu và kiểm thử từ request đến DB rồi đọc lại.

## 13. Những sai lầm cần tránh

| Sai lầm | Hệ quả | Cách làm đúng hơn |
| --- | --- | --- |
| `WHERE name = NULL` | Không tìm được hàng SQL NULL. | `IS NULL` hoặc phép so sánh null-safe phù hợp DBMS. |
| `ps.setNull(...); WHERE name = ?` rồi chờ khớp NULL | Dấu `=` với NULL cho UNKNOWN. | SQL tĩnh `IS NULL` khi cần lọc NULL. |
| Cho rằng `""` luôn lưu thành chuỗi rỗng trên mọi DBMS. | Oracle `VARCHAR2` có thể lưu thành NULL. | Đo round-trip và xác định chính sách dữ liệu. |
| Dùng `COALESCE(name, '')` làm default chuỗi trên Oracle. | `''` cũng là NULL, không tạo default không-null. | Dùng default không rỗng có ý nghĩa hoặc xử lý ở Java. |
| Cho rằng `"A"` khác `"a"` vì Java `equals` khác. | DB có thể dùng case-insensitive collation. | Kiểm tra collation/unique constraint và hợp đồng nghiệp vụ. |
| Nghĩ `VARCHAR` không bao giờ bỏ qua dấu cách cuối. | SQL Server/MySQL collation có thể so sánh theo padding. | Test equality và trailing spaces trên kiểu cột thật. |
| Dùng `LOWER(column)` ở mọi query để “cố định” so sánh. | Thay ngữ nghĩa ngôn ngữ, có thể mất khả năng dùng index. | Chọn collation/normalized key được kiểm thử. |
| Không chuẩn hóa Unicode nhưng dựa vào hình thức hiển thị. | Các dãy mã khác nhau có thể được xem khác nhau khi lookup. | Chọn Unicode normalization và chính sách lookup rõ ràng. |
| Dùng `LIKE '%'+input+'%'` mà không escape wildcard. | `%`/`_` trong input được xem như pattern. | Bind pattern đã escape, test cú pháp từng DBMS. |
| Tạo UNIQUE ở DBMS mới mà không rà dữ liệu. | Dữ liệu cũ có thể va chạm vì case/accent/space/NULL. | Kiểm tra nhóm xung đột trước migration. |
| Chỉ kiểm tra một DBMS và gọi là đa hệ quản trị. | Không phát hiện khác biệt Oracle/SQL Server/collation. | Integration test cùng contract trên driver/DBMS đích. |

## 14. Bài tập thực hành

Một dịch vụ JDBC quản lý mã khách hàng `customer_code`. Hệ thống chạy trên PostgreSQL và Oracle, dự kiến mở rộng SQL Server/MySQL. Các request có thể gửi `null`, `""`, `"ABC"`, `"abc"` và `"ABC "`. Trường này được dùng trong `WHERE customer_code = ?` và có unique constraint.

Hãy trả lời:

1. Nếu `setString(1, "")` được dùng để ghi một cột `VARCHAR2` của Oracle, giá trị đọc lại qua `getString()` thường là gì? Điều này có giống PostgreSQL `varchar` không?
2. Tại sao `WHERE customer_code = ?` với `setNull(1, Types.VARCHAR)` không tìm được các hàng SQL `NULL`? SQL nào đúng cho trường hợp đó?
3. `COUNT(customer_code)` có được dùng để đếm các hàng “có tên khác chuỗi rỗng” một cách chung cho Oracle và PostgreSQL không?
4. Khi di chuyển từ PostgreSQL sang SQL Server, nếu có hai hàng `"ABC"` và `"abc"`, việc tạo unique index có thể gặp vấn đề nào? Điều gì quyết định kết quả?
5. Với `"ABC"` và `"ABC "`, tại sao không thể dùng `String.equals()` của Java để dự đoán kết quả `WHERE customer_code = ?` trên mọi DBMS?
6. Nếu API cần **phân biệt chắc chắn** “không gửi trường” với “đã gửi chuỗi rỗng”, nên sửa getter JDBC hay thiết kế dữ liệu/contract? Vì sao?
7. Input tìm kiếm literal là `"50%"`. Vì sao `LIKE '%50%%'` có thể cho kết quả rộng hơn yêu cầu? Bạn sẽ bind pattern như thế nào?
8. Thiết kế ít nhất năm ca integration test cần chạy trên **mỗi** DBMS, và liệt kê cấu hình DB nào phải ghi lại để giải thích kết quả.

**Đáp án định hướng:**

1. Với Oracle `VARCHAR2`, chuỗi ký tự độ dài 0 thường được xem là SQL `NULL` nên `getString()` trả Java `null`; PostgreSQL `varchar` giữ `""` riêng.
2. Vì logic SQL ba giá trị: `NULL = NULL` là UNKNOWN; dùng `WHERE customer_code IS NULL`.
3. Không. Oracle đã gộp `''` vào `NULL` nên `COUNT(column)` bỏ qua, còn PostgreSQL vẫn tính chuỗi rỗng là non-NULL.
4. Có thể có unique conflict nếu collation SQL Server không phân biệt hoa/thường; phải xem loại cột, collation và cấu hình constraint/index.
5. SQL equality phụ thuộc collation/kiểu và padding; Java `String.equals()` so sánh dãy ký tự theo quy tắc Java, không tự áp dụng quy tắc DBMS.
6. Phải định nghĩa hợp đồng và **mô hình lưu trữ đủ hai trạng thái**; trên Oracle `VARCHAR2`, chỉ dùng `getString()` khác không thể phục hồi thông tin rỗng đã bị gộp thành NULL.
7. `%` là wildcard. Escape dấu `%` và bind vào `PreparedStatement` theo quy tắc `LIKE ... ESCAPE` đã được kiểm thử, không nối raw SQL.
8. Test NULL/EMPTY/BLANK round-trip, case/accent equality, trailing-space equality, LIKE escaping, unique collisions, Unicode normalization và `ORDER BY`; ghi DBMS/driver version, column type, collation, charset và cấu hình liên quan.

**Ghi nhớ:** **`NULL` khác `""` và khác `" "` về ý nghĩa**, nhưng DBMS có thể **không lưu hoặc so sánh chúng giống nhau**. Trong JDBC, dùng `setNull()`/`setString()` đúng kiểu, `getString()`/`wasNull()` để kiểm tra dữ liệu đọc lại và `IS NULL` thay cho `= NULL`. Khi triển khai đa hệ quản trị, kiểm thử **Oracle empty-as-NULL, collation, case/accent, trailing spaces, Unicode, LIKE và UNIQUE** trên từng driver/DBMS; sau đó đưa chính sách chuẩn hóa vào hợp đồng dữ liệu trước khi migration hoặc viết repository dùng chung.
