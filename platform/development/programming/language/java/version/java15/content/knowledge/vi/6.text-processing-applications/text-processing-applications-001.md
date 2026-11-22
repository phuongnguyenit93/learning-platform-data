# SQL nhiều dòng và tham số hóa bằng PreparedStatement trong Java 15+

## 1. Bài toán và mục tiêu

SQL thực tế thường có nhiều cột, nhiều điều kiện `JOIN`, `WHERE`, `ORDER BY`. Trước Java 15, người viết Java thường phải nối nhiều chuỗi bằng dấu `+` và chèn `\n` thủ công. **Text block** (`"""`), trở thành tính năng chính thức từ Java 15 và vẫn dùng ở Java hiện đại, cho phép viết truy vấn nhiều dòng gần với cách đọc SQL gốc.

Tuy nhiên, **text block chỉ là cú pháp tạo một `String`**; nó không tự ngăn SQL injection. Khi có giá trị đến từ người dùng, request, file hoặc hệ thống khác, Java JDBC cần **`PreparedStatement` với các dấu tham số `?` và lệnh `set...(...)`** để phân tách cấu trúc SQL với dữ liệu.

Sau bài này, bạn sẽ:

- Viết SQL dễ đọc bằng text block và dự đoán chính xác chuỗi cuối cùng.
- Dùng `Connection.prepareStatement(sql)`, đánh số tham số từ **1**, bind đúng kiểu và thực thi truy vấn.
- Đọc kết quả qua `ResultSet`, đóng tài nguyên bằng `try-with-resources`.
- Hiểu vì sao tham số hóa bảo vệ **giá trị** nhưng không áp dụng trực tiếp cho **tên bảng, tên cột, hướng sắp xếp**.
- Xử lý đúng `LIKE`, `NULL`, danh sách `IN (...)`, `SELECT` và `INSERT/UPDATE`.
- Kiểm thử định dạng text block và hành vi truy vấn; tránh những cách làm cũ dựa vào nối chuỗi đầu vào hoặc tự escape dấu nháy.

Phần Java sử dụng API JDBC chuẩn còn hiệu lực. Ví dụ kết nối thực tế bên dưới chọn **PostgreSQL** để có dữ liệu mẫu và kết quả tái lập; JDBC dùng được với nhiều hệ quản trị nhưng cú pháp SQL, driver, kiểu dữ liệu và hành vi `LIKE` có thể khác nhau.

## 2. Text block giúp trình bày SQL, không thay đổi ngữ nghĩa SQL

So sánh cách nối chuỗi và cách dùng text block:

```java
// Dạng chuỗi thường, vẫn hợp lệ nhưng khó đọc khi SQL dài:
String oldStyle = "SELECT id, name, price\n"
        + "FROM demo_products\n"
        + "WHERE active = ?\n"
        + "  AND price >= ?\n"
        + "ORDER BY id\n";

// Java 15+:
String sql = """
        SELECT id, name, price
        FROM demo_products
        WHERE active = ?
          AND price >= ?
        ORDER BY id
        """;
```

Hai giá trị `String` ở ví dụ này **giống hệt nhau**. Với text block:

1. Phải có dấu xuống dòng sau dấu mở `"""`.
2. Java chuẩn hóa line terminator nguồn thành `\n` và bỏ **incidental indentation** (phần lề dùng để căn mã Java); phần thụt vào *tương đối* giữa các dòng SQL còn lại.
3. Nếu closing delimiter `"""` đứng ở dòng riêng, chuỗi ví dụ có `\n` cuối. Nếu closing delimiter đứng ngay sau ký tự cuối, chuỗi có thể không có newline cuối.
4. Các dấu cách thực sự ở cuối dòng nguồn thường bị loại trong bước chuẩn hóa; dùng `\s` nếu chúng là dữ liệu quan trọng. Với SQL thông thường, phần lớn dấu cách căn lề chỉ phục vụ khả năng đọc.
5. Dấu `?` là ký tự bình thường trong Java `String`. Khi truy vấn được đưa cho driver JDBC, nó được hiểu là **parameter marker** theo quy tắc của driver và loại statement.

Điều quan trọng là **SQL cuối cùng vẫn phải hợp lệ trong dialect của database**. Việc viết nhiều dòng không làm JDBC tự thêm khoảng trắng vào chỗ không có, tự đổi cú pháp SQL hay tự bind tham số.

Một cách kiểm tra phần hiển thị là viết `expected` bằng string literal và so sánh `sql.equals(expected)`. Chương trình hoàn chỉnh ở mục 5 có chế độ `--check-sql` để thực hiện điều này **không cần database**.

## 3. Vì sao phải tách dữ liệu khỏi câu lệnh?

Giả sử giao diện cho phép tìm sản phẩm theo tên. Cách ghép dữ liệu trực tiếp vào SQL là không an toàn:

```java
// KHÔNG dùng cho dữ liệu không tin cậy.
String unsafe = """
        SELECT id, name
        FROM demo_products
        WHERE name = '""" + input + "'";
```

Nếu `input` chứa dấu nháy đơn hoặc cấu trúc SQL khác, phần chèn vào có thể thay đổi ngữ pháp câu lệnh. Việc đặt SQL trong text block **không** vô hiệu hóa rủi ro này. Tự thay mọi `'` thành `''` hoặc dựa vào bộ lọc ký tự không phải là biện pháp thay thế cho tham số hóa; cách escape phụ thuộc database và ngữ cảnh.

Thay vào đó:

```java
String safeSql = """
        SELECT id, name
        FROM demo_products
        WHERE name = ?
        """;

try (PreparedStatement ps = connection.prepareStatement(safeSql)) {
    ps.setString(1, input);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("name"));
        }
    }
}
```

Đoạn này nằm **bên trong phương thức đã có `Connection connection` và `String input`**, không phải một chương trình độc lập. Dấu `?` đại diện cho **một giá trị**. `ps.setString(1, input)` truyền giá trị theo API JDBC, nên dữ liệu được xử lý như dữ liệu thay vì một đoạn mã SQL mới.

Ví dụ, giá trị `x' OR '1'='1` được coi là **một giá trị tên cần so khớp**, không thể tự biến thành điều kiện `OR` trong truy vấn đã tham số hóa đúng. Điều đó chỉ giải quyết nguy cơ SQL injection trong phần bind: ứng dụng vẫn cần **ủy quyền truy cập, kiểm tra điều kiện nghiệp vụ và tài khoản database có quyền tối thiểu**.

**Quy tắc quan trọng:** tạo cố định cấu trúc SQL trong ứng dụng, bind từng giá trị bằng `PreparedStatement`. Đừng nối dữ liệu không tin cậy vào text block rồi mới gọi `prepareStatement(...)`: khi đó cấu trúc nguy hiểm đã được hình thành trước bước chuẩn bị.

## 4. JDBC vận hành như thế nào?

Luồng chính với một truy vấn `SELECT`:

```text
Java text block -> String SQL chứa dấu ? (cấu trúc)
                                  |
Connection.prepareStatement(sql) -+
                                  v
                           PreparedStatement
                           setBoolean(1, ...)
                           setBigDecimal(2, ...)
                           setString(3, ...)
                                  |
                             executeQuery()
                                  v
                              ResultSet
                        next() -> getInt/getString...
                                  |
             close ResultSet -> close PreparedStatement -> close Connection
```

- **`Connection`:** phiên làm việc logic với database. Lấy từ `DataSource` (thường kèm connection pool trong ứng dụng thực tế) hoặc `DriverManager` ở ví dụ nhỏ.
- **`PreparedStatement`:** chứa câu lệnh và vị trí các tham số; các phương thức `setXxx(index, value)` gán dữ liệu tương thích với kiểu SQL. **Chỉ số đầu tiên là 1, không phải 0**.
- **`executeQuery()`:** dùng cho truy vấn trả về `ResultSet` (điển hình là `SELECT`); `ResultSet.next()` tiến sang bản ghi tiếp theo và trả `false` ở cuối.
- **`executeUpdate()`:** dùng cho thao tác thay đổi dữ liệu như `INSERT`/`UPDATE`/`DELETE`, trả số bản ghi bị ảnh hưởng (hoặc 0 cho câu lệnh không trả số bản ghi theo hợp đồng API).
- **`try-with-resources`:** tự đóng tài nguyên theo thứ tự ngược với lúc mở, kể cả khi có ngoại lệ; đóng `ResultSet` trước `PreparedStatement` và `Connection`.

Tên `PreparedStatement` không bảo đảm mọi driver/server luôn biên dịch truy vấn trước một lần duy nhất hoặc cache nó theo cùng một cách. Việc chuẩn bị, truyền giá trị và tối ưu thực thi phụ thuộc driver, cấu hình và database. **Lợi ích bắt buộc của ví dụ là tách tham số dữ liệu khỏi cú pháp SQL**, không phải hứa hẹn hiệu năng cố định.

## 5. Ví dụ đầy đủ: Java 15 + PostgreSQL, có chế độ tự kiểm tra không cần DB

Ví dụ tìm các sản phẩm đang hoạt động, có giá từ 5.00 trở lên và tên **chứa một chuỗi tìm kiếm dạng chữ nguyên văn**. Câu SQL có ba dấu `?`; ta sẽ bind lần lượt `boolean`, `BigDecimal` và `String`. Để những ký tự `%`, `_` trong từ khóa không vô tình thành wildcard của `LIKE`, dùng `ESCAPE '!'` và một hàm escape **ý nghĩa của pattern LIKE**; đây là kiểm soát tìm kiếm, không phải biện pháp thay thế cho bind chống SQL injection.

Lưu tệp **`SqlTextBlockPreparedDemo.java`**:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class SqlTextBlockPreparedDemo {
    private static final String SQL = """
            SELECT id, name, price
            FROM demo_products
            WHERE active = ?
              AND price >= ?
              AND name LIKE ? ESCAPE '!'
            ORDER BY id
            """;

    public static void main(String[] args) throws SQLException {
        if (args.length == 1 && "--check-sql".equals(args[0])) {
            checkSqlText();
            return;
        }

        String keyword = args.length == 0 ? "Note" : args[0];

        String url = requireEnv("JDBC_URL");
        String user = requireEnv("JDBC_USER");
        String password = requireEnv("JDBC_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, user, password);
             PreparedStatement statement =
                     connection.prepareStatement(SQL)) {

            statement.setBoolean(1, true);
            statement.setBigDecimal(2, new BigDecimal("5.00"));
            statement.setString(3, "%" + escapeLike(keyword) + "%");

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    int id = rows.getInt("id");
                    String name = rows.getString("name");
                    BigDecimal price = rows.getBigDecimal("price");

                    System.out.println(id + " | " + name
                            + " | " + price.toPlainString());
                }
            }
        }
    }

    private static String escapeLike(String value) {
        return value.replace("!", "!!")
                    .replace("%", "!%")
                    .replace("_", "!_");
    }

    private static String requireEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing environment variable: " + name);
        }
        return value;
    }

    private static void checkSqlText() {
        String expected = "SELECT id, name, price\n"
                + "FROM demo_products\n"
                + "WHERE active = ?\n"
                + "  AND price >= ?\n"
                + "  AND name LIKE ? ESCAPE '!'\n"
                + "ORDER BY id\n";

        if (!SQL.equals(expected)) {
            throw new AssertionError("Text block SQL differs from expected");
        }
        System.out.println("SQL text block: PASS");
    }
}
```

### 5.1. Biên dịch và kiểm tra text block trước khi kết nối

Dùng JDK có hỗ trợ biên dịch đích Java 15:

```bash
javac --release 15 SqlTextBlockPreparedDemo.java
java SqlTextBlockPreparedDemo --check-sql
```

**Kết quả kỳ vọng chính xác:**

```text
SQL text block: PASS
```

Chế độ này chỉ dùng API của JDK; không cần JDBC driver bên ngoài, không kết nối database và không đọc biến môi trường. Nó kiểm tra **toàn bộ dấu cách, line terminator và nội dung SQL** sau khi Java xử lý text block.

### 5.2. Tạo dữ liệu mẫu trên PostgreSQL

Kết nối đến **database thử nghiệm riêng** với quyền tạo bảng để chạy SQL sau. Bảng cần các cột sau; không chạy câu tạo bảng lên môi trường sản xuất:

```sql
CREATE TABLE demo_products (
    id INTEGER PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    active BOOLEAN NOT NULL
);

INSERT INTO demo_products (id, name, price, active)
VALUES
    (1, 'Notebook', 12.50, TRUE),
    (2, 'Marker', 4.25, TRUE),
    (3, 'Discontinued Note', 8.00, FALSE),
    (4, 'Note Clip', 6.40, TRUE);
```

Dùng tài khoản PostgreSQL chỉ có quyền `SELECT` để chạy chương trình sau khi seed, ví dụ `demo_reader` nếu đã tạo và cấp quyền trong database thử nghiệm. Driver PostgreSQL JDBC hiện đại cần có trong **runtime classpath**; không có driver, `DriverManager.getConnection(...)` sẽ không biết xử lý URL `jdbc:postgresql:...`.

Ví dụ cấu hình biến môi trường trong PowerShell (giá trị password do người chạy nhập, không đưa mật khẩu vào source code):

```powershell
$env:JDBC_URL = "jdbc:postgresql://localhost:5432/demo_db"
$env:JDBC_USER = "demo_reader"
$env:JDBC_PASSWORD = Read-Host "Database password"
```

Nếu dùng một tệp driver đã tải từ nguồn chính thức và được đặt tên **`postgresql.jar`** trong thư mục chạy, cách chạy trên Windows là:

```powershell
java -cp ".;postgresql.jar" SqlTextBlockPreparedDemo
```

Với macOS/Linux, classpath dùng dấu `:` thay vì `;`:

```bash
java -cp ".:postgresql.jar" SqlTextBlockPreparedDemo
```

**Stdout với chính xác bốn bản ghi seed phía trên, PostgreSQL mặc định và từ khóa `Note`:**

```text
1 | Notebook | 12.50
4 | Note Clip | 6.40
```

Lý do: `Marker` rẻ hơn 5.00, `Discontinued Note` có `active = FALSE`; hai bản ghi còn lại đáp ứng cả ba điều kiện. `LIKE` của PostgreSQL phân biệt chữ hoa/thường theo hành vi/collation được áp dụng; ví dụ tìm `Note`, không tùy tiện giả định rằng mọi database đều có hành vi như nhau.

Lưu ý phần kết nối cần **database đang chạy, thông tin đăng nhập hợp lệ, bảng đã seed và driver phù hợp**. `javac` chỉ kiểm tra Java; nó không kiểm tra quyền truy cập, database schema hay SQL dialect của server. Nếu môi trường chạy khác với dữ liệu mẫu, kết quả bản ghi cũng khác.

### 5.3. Giải thích ba tham số

| Vị trí `?` | Ý nghĩa trong SQL | Dòng bind trong Java |
| ---: | --- | --- |
| 1 | `active = ?` | `statement.setBoolean(1, true)` |
| 2 | `price >= ?` | `statement.setBigDecimal(2, new BigDecimal("5.00"))` |
| 3 | `name LIKE ? ESCAPE '!'` | `statement.setString(3, "%" + escapeLike(keyword) + "%")` |

Mỗi marker `?` biểu thị một giá trị tương ứng. Không viết `WHERE name = '?'` vì ký tự `?` trong dấu nháy SQL ở đó là một **chuỗi literal SQL**, không phải vị trí tham số. Cũng không dùng `setString(0, ...)`: JDBC đánh số từ 1.

## 6. Tìm kiếm với LIKE: an toàn cú pháp vẫn khác đúng ý nghĩa dữ liệu

`PreparedStatement` giúp dữ liệu của tham số không thay đổi **cấu trúc SQL**, nhưng trong mẫu `LIKE ?`, database vẫn diễn giải các ký tự wildcard **bên trong giá trị pattern**:

- `%` đại diện cho một chuỗi ký tự bất kỳ, kể cả chuỗi rỗng.
- `_` đại diện cho một ký tự.
- `ESCAPE '!'` quy định `!%` và `!_` là dấu phần trăm/gạch dưới **nguyên văn**, còn `!!` là dấu `!` nguyên văn trong ví dụ PostgreSQL.

Nếu người dùng nhập `50%` và muốn tìm đúng ký tự phần trăm, chỉ bind `"%50%%"` sẽ vô tình làm dấu `%` từ input thành wildcard. Bài dùng hàm `escapeLike(...)` để biến từ khóa `50%` thành `50!%`; sau đó thêm wildcard ở đầu/cuối để thực hiện ý định “tên chứa chuỗi nguyên văn”.

Ví dụ Java, trong phạm vi lớp có hàm `escapeLike`:

```java
String input = "50%";
String pattern = "%" + escapeLike(input) + "%";
System.out.println(pattern); // %50!%%
```

Đây là đoạn minh họa thêm vào lớp ví dụ, không phải chương trình độc lập. Nó chỉ dự đoán **pattern truyền cho database**; không phải SQL query được nối từ input. Những hệ quản trị khác có thể dùng ký tự escape/collation hoặc cú pháp so khớp khác nhau; hãy kiểm tra dialect và yêu cầu phân biệt chữ hoa/thường của ứng dụng.

## 7. INSERT, UPDATE và các kiểu dữ liệu khác

`PreparedStatement` không chỉ dùng cho `SELECT`. Với thao tác ghi, tiếp tục viết SQL nhiều dòng và bind giá trị:

```java
String insertSql = """
        INSERT INTO demo_products (id, name, price, active)
        VALUES (?, ?, ?, ?)
        """;

// Ví dụ nằm trong phương thức đã có Connection connection:
try (PreparedStatement ps = connection.prepareStatement(insertSql)) {
    ps.setInt(1, 5);
    ps.setString(2, "Binder");
    ps.setBigDecimal(3, new BigDecimal("7.25"));
    ps.setBoolean(4, true);

    int rowsChanged = ps.executeUpdate();
    System.out.println("Inserted rows: " + rowsChanged);
}
```

Nếu ID `5` chưa tồn tại và database cho phép ghi, thao tác `INSERT` này thường ảnh hưởng một bản ghi; câu lệnh có thể ném `SQLException` nếu có khóa trùng, thiếu quyền, vi phạm ràng buộc hay lỗi database. Đoạn này **không chạy trong chương trình đọc-only mục 5**, mà minh họa một thao tác ghi riêng.

Chọn setter theo kiểu SQL thực tế:

- `setInt`/`setLong` cho số nguyên có kiểu tương ứng.
- `setBigDecimal` cho `NUMERIC`/`DECIMAL` khi cần độ chính xác thập phân; tránh dùng `double` cho số tiền chính xác.
- `setBoolean` cho giá trị boolean được driver hỗ trợ.
- `setString` cho dữ liệu dạng ký tự, theo mapping JDBC của driver.
- `setObject(index, value, SQLType hoặc sqlType)` cho kiểu hỗ trợ phù hợp; với ngày/giờ, chọn kiểu Java và mapping JDBC nhất quán với schema và timezone.

Đối với giá trị `NULL`, nên định nghĩa loại SQL cụ thể khi bind:

```java
// Giả sử cột name cho phép NULL và câu SQL có marker đầu tiên cho name.
ps.setNull(1, java.sql.Types.VARCHAR);
```

Đừng nhầm **giá trị SQL `NULL`** với chuỗi Java `"null"`. Trong SQL, `WHERE name = NULL` không trả TRUE; kiểm tra giá trị null bằng `IS NULL` hoặc xây dựng điều kiện phù hợp dialect. Nếu muốn một điều kiện là “bằng một giá trị có thể null”, cần xác định rõ ngữ nghĩa và viết SQL cho đúng, không tự thay tất cả mọi đối tượng null bằng `setString(..., "null")`.

## 8. Giới hạn của tham số hóa: tên cột, ORDER BY, IN (...)

### 8.1. Không bind tên bảng, tên cột hoặc từ khóa SQL bằng dấu ?

Ví dụ sau sai về ý tưởng:

```java
// Sai: dấu ? này không thể thay thế tên cột được chọn để sắp xếp.
String wrong = "SELECT id, name FROM demo_products ORDER BY ?";
```

Nếu driver/database chấp nhận biểu thức đó, giá trị được bind là **một biểu thức dữ liệu**, không trở thành tên cột `name` hoặc `price`. Hãy chọn token cấu trúc từ **danh sách cố định do ứng dụng quản lý**:

```java
String requestedSort = "price"; // Giá trị đến từ phía yêu cầu.
String safeColumn = switch (requestedSort) {
    case "name" -> "name";
    case "price" -> "price";
    default -> throw new IllegalArgumentException("Unknown sort column");
};

String sortSql = """
        SELECT id, name, price
        FROM demo_products
        WHERE active = ?
        ORDER BY %s
        """.formatted(safeColumn);
```

`String.formatted(...)` là API có từ **Java 15**, thích hợp ở đây vì `safeColumn` chỉ có thể là một trong hai hằng SQL đã được chọn bằng allow-list. **Không bao giờ** đưa trực tiếp `requestedSort` chưa kiểm soát vào `formatted(...)` hoặc nối vào SQL. Tương tự, hướng `ASC`/`DESC` cũng phải được map từ các lựa chọn cố định.

### 8.2. Danh sách IN thay đổi số phần tử

Một dấu `?` thường đại diện **một** giá trị; không mặc định rằng `IN (?)` với một chuỗi `"1,2,3"` sẽ được hiểu thành ba số. Với danh sách ID độ dài thay đổi, tạo **chính xác số marker** ứng với số phần tử, rồi bind từng ID:

```java
import java.util.Collections;
import java.util.List;

// Đoạn minh họa nằm trong phương thức có Connection connection.
List<Integer> ids = List.of(1, 3, 4);
if (ids.isEmpty()) {
    // Quyết định nghiệp vụ: trả danh sách rỗng, không tạo IN ().
    return;
}

String marks = String.join(", ", Collections.nCopies(ids.size(), "?"));
String sql = """
        SELECT id, name
        FROM demo_products
        WHERE id IN (%s)
        """.formatted(marks);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setInt(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        // Xử lý các dòng kết quả tại đây.
    }
}
```

Đây là **đoạn minh họa trong một phương thức có kiểu trả về `void`** (do có `return;`), cần đặt ở đúng lớp và import. `marks` được sinh hoàn toàn từ ký tự `?` do code tạo, không chứa các giá trị ID; việc tạo SQL động này giữ được nguyên tắc **dữ liệu luôn được bind**.

Một số driver/database có hỗ trợ SQL array hoặc cơ chế danh sách riêng; nếu áp dụng, phải tra cứu API driver và SQL dialect tương ứng. Không ép dùng một cách “chuẩn cho mọi database”.

## 9. Quản lý tài nguyên, giao dịch và hiệu năng

**Đối với các truy vấn đơn giản**, đóng tài nguyên bằng `try-with-resources` như chương trình ở mục 5. Trong ứng dụng server:

- Lấy `Connection` từ `DataSource`, thường là connection pool đã cấu hình. Các framework có thể quản lý connection/transaction; tuân theo vòng đời của framework, không tùy tiện đóng connection đang do một transaction bên ngoài quản lý.
- Đóng `PreparedStatement` và `ResultSet` sau khi dùng. Không giữ statement hay result set sống lâu vượt phạm vi kết nối.
- Tái sử dụng một `PreparedStatement` trong phạm vi connection phù hợp khi chạy cùng cấu trúc SQL nhiều lần và bind đủ các tham số cho mỗi lần thực thi. Với thao tác lặp nhiều bản ghi, xem `addBatch()` và `executeBatch()` khi driver/database hỗ trợ.
- Với nhiều thay đổi cần tất cả cùng thành công hoặc cùng rollback, dùng **transaction** (`setAutoCommit(false)`, `commit()`, `rollback()`) hoặc cơ chế transaction của framework; một `PreparedStatement` đơn lẻ không tạo giao dịch nguyên tử cho nhiều thao tác liên tiếp.
- Giới hạn số kết quả, chọn index thích hợp, cấu hình timeout phù hợp và xử lý lỗi `SQLException`; không giả định rằng SQL đẹp trong text block sẽ có kế hoạch thực thi nhanh hơn.
- Hạn chế quyền SQL của tài khoản runtime, tránh ghi dữ liệu nhạy cảm, thông tin đăng nhập hoặc toàn bộ tham số chứa PII vào log.

Tham số hóa là một **biện pháp bảo vệ cấu trúc truy vấn**, không phải thay thế cho phân quyền theo người dùng, xác thực, giới hạn dữ liệu được xem, kiểm soát schema, chống truy vấn tốn tài nguyên hay chính sách transaction.

## 10. Cách kiểm thử đúng và các ca biên

Bài có **hai tầng kiểm thử khác nhau**:

**Tầng A — kiểm thử Java text block, không cần database:** chạy `java SqlTextBlockPreparedDemo --check-sql`. Điều kiện `SQL.equals(expected)` xác nhận chuẩn xác lề, dấu cách giữa các token, số marker và newline cuối chuỗi. Nếu đổi mức lề một dòng hoặc dấu đóng làm chuỗi khác, bài kiểm sẽ báo lỗi. Nó **không** xác nhận SQL syntax với PostgreSQL, vì chưa kết nối database.

**Tầng B — kiểm thử tích hợp JDBC với database mẫu:** chạy chương trình có PostgreSQL JDBC driver, quyền `SELECT` và dữ liệu seed; kiểm tra kết quả hai dòng theo mục 5. Tầng này chứng minh quá trình prepare → bind → execute → đọc bản ghi thực sự hoạt động.

Nên kiểm tra thêm:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Từ khóa `Note`, giá ≥ 5 và active | Trả hai bản ghi mẫu `Notebook` và `Note Clip` |
| Từ khóa không khớp | Không trả dòng nào, không lỗi |
| Từ khóa chứa `%` hoặc `_` | Tìm nguyên văn ký tự đó nhờ `escapeLike` và `ESCAPE '!'`, không biến thành wildcard ngoài ý muốn |
| Từ khóa `x' OR '1'='1` | Được bind thành pattern dữ liệu; không thêm điều kiện `OR` vào SQL |
| Không có driver trong runtime classpath | Kết nối thất bại; cần khai báo JDBC driver tương thích |
| Sai tên cột/bảng hoặc sai cú pháp SQL dialect | `SQLException` khi database phân tích/thực thi |
| Thiếu biến môi trường | `IllegalArgumentException` sớm với tên biến thiếu |
| Đổi thứ tự `set...` | Truy vấn sai ý nghĩa hoặc phát sinh lỗi chuyển kiểu |
| `IN` với danh sách rỗng | Phải xử lý riêng; không sinh `IN ()` |
| Đầu vào sắp xếp không thuộc allow-list | Bị từ chối trước khi dựng SQL |

**Phân biệt rõ:** thử injection qua một ô tìm kiếm chứng minh giá trị không được nhập vào cấu trúc SQL khi đã bind đúng; nó không thay thế kiểm thử ủy quyền và dữ liệu nhạy cảm. Khi viết test thật, tránh việc “làm cho pass” bằng cách xóa whitespace toàn bộ câu SQL rồi bỏ qua những khác biệt có thể làm token dính nhau.

## 11. Những lỗi thường gặp và cách sửa

1. **Nối dữ liệu thẳng vào text block:** `""" ... '""" + input + ...` dễ tạo SQL injection. Dùng dấu `?` tại vị trí **giá trị** và bind với `setString`/`setXxx`.
2. **Đặt marker trong dấu nháy SQL:** `WHERE name = '?'` sẽ so khớp ký tự dấu hỏi, không bind. Viết `WHERE name = ?`.
3. **Dùng chỉ số 0:** `setString(0, ...)` sai, vì JDBC bắt đầu từ 1.
4. **Không bind đủ marker hoặc bind sai kiểu:** kiểm tra số dấu `?` thực sự là parameter markers và mapping setter, kiểu cột; tránh đếm máy móc dấu `?` nằm bên trong SQL literal/comment.
5. **Tưởng `PreparedStatement` cho phép bind tên cột:** tên bảng/cột/hướng sắp xếp là SQL syntax. Dùng danh sách lựa chọn cố định do ứng dụng sở hữu.
6. **Tưởng bind `LIKE` sẽ tự vô hiệu hóa wildcard:** bind bảo vệ **cú pháp SQL**, không đổi quy tắc `%`/`_` của operator. Escape wildcard khi sản phẩm yêu cầu tìm nguyên văn.
7. **Tự chèn ký tự `'` quanh marker hoặc escape thủ công giá trị:** driver đã chịu trách nhiệm truyền kiểu giá trị; đừng can thiệp bằng nối chuỗi SQL.
8. **Dùng `double` cho tiền:** dùng `BigDecimal` với cột `NUMERIC/DECIMAL` tương ứng khi cần chính xác.
9. **Không đóng `ResultSet`/`PreparedStatement`:** có thể làm rò rỉ tài nguyên DB. Dùng `try-with-resources` hoặc lifecycle chuẩn của framework.
10. **Mặc định mọi SQL dialect giống nhau:** text block Java không quyết định PostgreSQL/MySQL/Oracle chấp nhận câu lệnh nào; hãy chạy integration test trên DB mục tiêu.
11. **Hiểu nhầm newline cuối text block:** khi thay đổi closing delimiter hoặc lề, SQL string cũng thay đổi. Tạo assertion nếu cần ổn định SQL nguyên văn.
12. **Đánh đồng PreparedStatement với phân quyền:** vẫn cần kiểm soát người dùng được phép đọc bảng/bản ghi nào; tài khoản DB nên có quyền tối thiểu.

## 12. Tự kiểm tra

**Câu 1.** Khi muốn lọc `WHERE price >= ? AND active = ?`, nên bind theo thứ tự nào?

**Đáp án:** `ps.setBigDecimal(1, minPrice)` rồi `ps.setBoolean(2, true)`. Thứ tự dựa vào vị trí marker trong chính SQL, không dựa vào tên biến hoặc thứ tự khai báo trong Java.

**Câu 2.** Viết `String sql = """ SELECT ... WHERE name = '""" + keyword + "'";` rồi gọi `prepareStatement(sql)` có chống injection không?

**Đáp án:** Không. Trước khi chuẩn bị, giá trị không tin cậy đã trở thành một phần cú pháp SQL. Cần viết `WHERE name = ?` và gọi `ps.setString(1, keyword)`.

**Câu 3.** Có thể viết `ORDER BY ?` rồi bind `"price"` để chọn cột giá không?

**Đáp án:** Không theo cách mong muốn. Marker đại diện giá trị, không thay tên cột. Cần map lựa chọn sắp xếp sang một trong các hằng SQL cho phép, như `name` hoặc `price`.

**Câu 4.** Nếu tên sản phẩm có ký tự `_` và người dùng muốn tìm ký tự này nguyên văn, chỉ dùng `setString(1, "%" + userInput + "%")` đã đủ chưa?

**Đáp án:** Đã ngăn injection vào cú pháp SQL, nhưng **chưa đủ để giữ ngữ nghĩa tìm nguyên văn**; phải escape wildcard theo operator/dialect, như `ESCAPE '!'` và `!_` trong ví dụ.

**Câu 5.** Vì sao `--check-sql` pass vẫn chưa chứng minh JDBC chạy đúng?

**Đáp án:** Vì nó chỉ xác nhận `String` được tạo bởi Java. Muốn xác nhận cú pháp SQL, quyền truy cập, parameter types và kết quả thực tế, phải chạy trên database mục tiêu có JDBC driver và dữ liệu test.

## 13. Tài liệu hiện hành đáng tham khảo

- [Java SE 15 JLS §3.10.6 – Text Blocks](https://docs.oracle.com/javase/specs/jls/se15/html/jls-3.html#jls-3.10.6): nguồn chuẩn về cú pháp text block và cách xử lý lề, newline, escape.
- [Java SE 25 Javadoc – `java.sql.PreparedStatement`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/PreparedStatement.html): hợp đồng `setString`, `setBigDecimal`, `setNull`, `executeQuery`, `executeUpdate` và chỉ số parameter bắt đầu từ 1.
- [Java SE 25 Javadoc – `java.sql.Connection`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Connection.html): chuẩn bị statement, transaction, commit/rollback và vòng đời kết nối.
- [Java SE 25 Javadoc – `java.sql.ResultSet`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/ResultSet.html): đọc dữ liệu và giải phóng tài nguyên kết quả.
- [OWASP – SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet/): tham số hóa dữ liệu, allow-list cho cấu trúc SQL động và nguyên tắc quyền tối thiểu.
- [PostgreSQL JDBC Documentation](https://jdbc.postgresql.org/documentation/): cấu hình driver JDBC, connection URL, cách bind và hành vi riêng của PostgreSQL.

**Ghi nhớ:** Text block giải quyết **cách trình bày chuỗi SQL trong Java**; `PreparedStatement` giải quyết **cách truyền giá trị vào truy vấn**. Khi dùng cùng nhau, bạn có mã dễ đọc và phân tách dữ liệu khỏi cấu trúc SQL theo API Java vẫn còn được hỗ trợ.