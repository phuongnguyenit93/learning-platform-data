# Callback cung cấp SQL, tham số hoặc cách đọc kết quả trong JdbcTemplate

## 1. Vì sao JdbcTemplate có callback?

Khi dùng JDBC thuần, mỗi lần truy vấn chúng ta thường lặp lại chuỗi công việc:

1. Lấy `Connection` từ `DataSource`.
2. Tạo `PreparedStatement` với câu SQL.
3. Gán giá trị cho các dấu `?` nếu có.
4. Thực thi câu SQL.
5. Đọc từng hàng từ `ResultSet` hoặc xử lý số dòng bị thay đổi.
6. Đóng `ResultSet`, `Statement`, trả `Connection` và xử lý `SQLException`.

Phần lớn các bước ấy giống nhau giữa các truy vấn. Khác biệt chủ yếu nằm ở **câu SQL nào được chạy**, **các tham số nào được gán** và **kết quả được đọc thành gì**. `JdbcTemplate` của Spring tách phần công việc lặp lại ra khỏi phần thay đổi bằng **callback**: mã ứng dụng truyền một đối tượng hoặc lambda mô tả cách làm tại một điểm cụ thể, còn template điều phối quy trình JDBC.

```text
Mã ứng dụng
    |
    +-- SQL hoặc PreparedStatementCreator   -> tạo PreparedStatement
    +-- PreparedStatementSetter              -> đặt tham số và tùy chỉnh statement
    +-- RowMapper / ResultSetExtractor /
    |   RowCallbackHandler                   -> xử lý kết quả SELECT
    +-- PreparedStatementCallback            -> tự thực hiện thao tác chuyên biệt
    |
    v
JdbcTemplate
    -> lấy Connection phù hợp giao dịch
    -> chuẩn bị Statement
    -> gọi callback đúng thời điểm
    -> thực thi / duyệt kết quả
    -> giải phóng tài nguyên
    -> chuyển SQLException thành DataAccessException
```

**Callback không đồng nghĩa với “tự đóng kết nối” hoặc “tự gọi SQL ở bất kỳ lúc nào”.** Mỗi giao diện có hợp đồng riêng về đối tượng nhận vào, thao tác được làm và quyền điều khiển con trỏ `ResultSet`.

Sau bài này, bạn có thể:

- Chọn đúng callback cung cấp SQL/statement, gán tham số hoặc ánh xạ dữ liệu.
- Phân biệt `PreparedStatementCreator` với `PreparedStatementSetter`, cũng như `RowMapper` với `ResultSetExtractor` và `RowCallbackHandler`.
- Biết callback nào được gọi **một lần cho truy vấn** và callback nào được gọi **mỗi hàng kết quả**.
- Viết truy vấn Spring JDBC với lambda đúng kiểu; xử lý `NULL`, tham số có thứ tự, ngoại lệ và tài nguyên.
- Nhận diện trường hợp nên dùng API đơn giản hoặc `NamedParameterJdbcTemplate` thay vì triển khai callback ở mức quá thấp.

## 2. Bản đồ các callback quan trọng

| Callback | Phương thức chức năng | Đối tượng nhận | Trách nhiệm chính | Được gọi khi nào? |
| --- | --- | --- | --- | --- |
| `PreparedStatementCreator` | `createPreparedStatement(Connection)` | `Connection` do template cung cấp | Tạo `PreparedStatement`, chọn SQL và tùy chọn tạo statement; có thể gán tham số | Khi template chuẩn bị statement |
| `PreparedStatementSetter` | `setValues(PreparedStatement)` | `PreparedStatement` đã tạo | Gán tham số `?`, thiết lập vài tùy chọn statement | Trước khi statement thực thi |
| `RowMapper<T>` | `mapRow(ResultSet, int)` | Con trỏ đang ở hàng hiện tại và chỉ số hàng | Biến **một hàng** thành một đối tượng `T` | Mỗi hàng được ánh xạ |
| `ResultSetExtractor<T>` | `extractData(ResultSet)` | Toàn bộ `ResultSet` | Điều khiển việc duyệt và xây **một kết quả tổng thể** `T` | Thường một lần cho một tập kết quả |
| `RowCallbackHandler` | `processRow(ResultSet)` | Con trỏ đang ở hàng hiện tại | Thực hiện tác vụ cho từng hàng, không cần tạo `List<T>` | Mỗi hàng được xử lý |
| `PreparedStatementCallback<T>` | `doInPreparedStatement(PreparedStatement)` | `PreparedStatement` đang hoạt động | Tự chạy thao tác JDBC chuyên biệt và trả `T` | Khi dùng biến thể `execute(...)` tương ứng |

Bốn giao diện đầu và `RowCallbackHandler` thường phối hợp trong các lời gọi `query(...)`. `PreparedStatementCallback` dùng khi muốn trực tiếp điều khiển thao tác của một statement, ví dụ xử lý một lô lệnh trên cùng `PreparedStatement`.

Một số callback liên quan khác có phạm vi riêng: `ConnectionCallback<T>` làm việc ở cấp `Connection`; `StatementCallback<T>` làm việc với `Statement` thông thường; `CallableStatementCreator` và `CallableStatementCallback<T>` phục vụ stored procedure hoặc lời gọi `CallableStatement`. Không cần dùng các giao diện cấp thấp ấy cho một truy vấn thông thường chỉ có vài tham số.

## 3. Callback là hợp đồng, lambda chỉ là cách viết ngắn

Các giao diện callback thường là **functional interface**: chỉ có một phương thức trừu tượng cần triển khai, nên có thể được biểu diễn bằng lambda. Chẳng hạn:

```java
PreparedStatementSetter setter = ps -> ps.setString(1, "ACTIVE");
```

Đây là mã minh họa cần import `org.springframework.jdbc.core.PreparedStatementSetter`. Lambda trên tương đương với một lớp cài đặt `setValues(PreparedStatement ps)`. Nó **không chạy ngay tại thời điểm khai báo**: `JdbcTemplate` sẽ gọi lambda khi đã tạo được statement và đến bước gán tham số.

Tương tự:

```java
RowMapper<String> ownerMapper = (rs, rowNum) -> rs.getString("owner");
```

Template gọi `mapRow` với `ResultSet` đã đặt ở hàng hiện tại. Lambda trả một tên trên mỗi hàng; `JdbcTemplate.query(..., ownerMapper)` thu chúng thành danh sách. `rowNum` là chỉ số hàng được tính từ 0 bởi phần ánh xạ của Spring, **không phải khóa chính** và không phải thứ tự ổn định nếu SQL thiếu `ORDER BY`.

Khai báo biến với kiểu callback cụ thể cũng giúp tránh nhầm các overload của `query(...)`. Một lambda một tham số có thể nhìn giống nhau dù thực chất là `ResultSetExtractor`, `RowCallbackHandler` hoặc `PreparedStatementSetter`, nên hãy đọc **kiểu tham số và kiểu kết quả** của phương thức đang gọi.

## 4. Ví dụ dữ liệu để thống nhất ý nghĩa

Giả sử ứng dụng có bảng `account` trong PostgreSQL hoặc H2 thử nghiệm:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    owner VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    balance DECIMAL(12, 2) NOT NULL
);

INSERT INTO account (id, owner, status, balance) VALUES
    (1, 'Lan',  'ACTIVE',   120.00),
    (2, 'Minh', 'INACTIVE',  70.00),
    (3, 'Vy',   'ACTIVE',    90.00);
```

Truy vấn:

```sql
SELECT id, owner, balance
FROM account
WHERE status = ?
ORDER BY id;
```

Khi gán tham số thứ nhất thành `"ACTIVE"`, truy vấn trả hai hàng:

| id | owner | balance |
| ---: | --- | ---: |
| 1 | Lan | 120.00 |
| 3 | Vy | 90.00 |

Ta sẽ dùng dữ liệu ấy để xem cùng một SQL nhưng những cách đọc kết quả khác nhau có thể cho `List<Account>`, một con số tổng hợp hoặc hành động theo từng hàng.

## 5. Phần cung cấp SQL: khi nào cần PreparedStatementCreator?

### 5.1. Trường hợp thông thường: truyền chuỗi SQL

Với các yêu cầu đơn giản, không cần tự xây statement:

```java
List<String> owners = jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("owner"),
    "ACTIVE"
);
```

Ví dụ này giả định `jdbcTemplate` đã được khởi tạo trong ứng dụng Spring. API `query(String, RowMapper<T>, Object...)` tự tạo prepared statement và gán các đối số theo vị trí. Danh sách trả về gồm `["Lan", "Vy"]` với dữ liệu mẫu. Lambda `RowMapper` chỉ định cách đọc từng hàng.

**Khi đã có sẵn SQL dạng `String`, ưu tiên overload nhận `String` và tham số**: nó ngắn gọn hơn việc tự tạo `PreparedStatementCreator`.

### 5.2. PreparedStatementCreator tạo statement từ Connection

`PreparedStatementCreator` hữu ích khi cần kiểm soát cách tạo statement: chọn loại `ResultSet`, chế độ đồng thời, khóa phát sinh hoặc tùy chọn tạo `PreparedStatement` mà API đơn giản không đáp ứng trực tiếp.

```java
import java.sql.PreparedStatement;
import org.springframework.jdbc.core.PreparedStatementCreator;

String sql = """
    SELECT id, owner, balance
    FROM account
    WHERE status = ?
    ORDER BY id
    """;

PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(sql);
    ps.setString(1, "ACTIVE");
    return ps;
};
```

`JdbcTemplate` cung cấp `connection` cho callback và **đóng statement được callback tạo ra** khi hoàn tất. Callback chọn SQL, tạo `PreparedStatement` và có thể tự gán giá trị. Không gọi `connection.close()` trong creator vì kết nối do template và bộ quản lý giao dịch kiểm soát.

Có thể đưa creator vào câu truy vấn:

```java
RowMapper<String> mapper = (rs, rowNum) -> rs.getString("owner");

List<String> owners = jdbcTemplate.query(creator, mapper);
```

Nếu chỉ cần gán vài tham số thì sử dụng `PreparedStatementSetter` hoặc overload với `Object... args` thường rõ hơn. Không tạo lớp creator phức tạp chỉ vì muốn dùng lambda.

### 5.3. Trường hợp đặc biệt: nhận khóa tự sinh

Khi chạy `INSERT` và muốn truy xuất khóa được DB tạo, callback tạo statement có thể yêu cầu `RETURN_GENERATED_KEYS`:

```java
import java.sql.PreparedStatement;
import java.sql.Statement;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

int affected = jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO account(owner, status, balance) VALUES (?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, "Hoa");
    ps.setString(2, "ACTIVE");
    ps.setBigDecimal(3, new java.math.BigDecimal("50.00"));
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
```

**Điều kiện cho ví dụ:** bảng thực tế phải dùng cột `id` tự sinh hoặc có cơ chế sinh khóa tương ứng; bảng `account` ở mục 4 khai báo `id BIGINT PRIMARY KEY` **không tự sinh**, nên phải đổi DDL phù hợp DB trước khi dùng ví dụ này. Trình điều khiển JDBC cũng phải hỗ trợ truy xuất khóa phát sinh. `getKey()` chỉ phù hợp khi có đúng một khóa số; nó có thể không cung cấp giá trị nếu DB/driver không trả khóa như mong đợi. `affected` là số hàng bị ảnh hưởng, không phải ID tự sinh.

Ví dụ này minh họa **vì sao cần điều khiển cách tạo PreparedStatement**, không có ý nói mọi `INSERT` nên tự viết `PreparedStatementCreator`.

## 6. Phần cung cấp tham số: PreparedStatementSetter

`PreparedStatementSetter` nhận một `PreparedStatement` đã được tạo sẵn và gán giá trị cho các dấu `?` trước khi statement được thực thi. Chỉ số tham số JDBC bắt đầu từ **1**, khác với chỉ số mảng Java bắt đầu từ 0.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.PreparedStatementSetter;

String sql = """
    SELECT id, owner, balance
    FROM account
    WHERE status = ? AND balance >= ?
    ORDER BY id
    """;

PreparedStatementSetter setter = ps -> {
    ps.setString(1, "ACTIVE");
    ps.setBigDecimal(2, new BigDecimal("100.00"));
};
```

Ở đây, callback cung cấp **hai giá trị** theo đúng thứ tự của dấu `?`: trạng thái trước, số dư tối thiểu sau. Nếu đảo vị trí, DB có thể phát sinh lỗi kiểu dữ liệu hoặc trả kết quả sai.

Gắn setter với mapper:

```java
RowMapper<String> mapper = (rs, rowNum) -> rs.getString("owner");
List<String> owners = jdbcTemplate.query(sql, setter, mapper);
```

Với dữ liệu mẫu, danh sách là `["Lan"]` vì Vy có số dư 90.00.

### 6.1. Tại sao vẫn dùng PreparedStatement với callback?

`PreparedStatement` tách cấu trúc SQL khỏi giá trị đầu vào. Thay vì ghép chuỗi:

```java
// KHÔNG NÊN: giá trị người dùng được nối trực tiếp vào SQL.
String unsafe = "SELECT * FROM account WHERE owner = '" + userInput + "'";
```

hãy sử dụng:

```java
String sql = "SELECT id, owner, balance FROM account WHERE owner = ?";
List<Account> found = jdbcTemplate.query(sql, ACCOUNT_MAPPER, userInput);
```

`ACCOUNT_MAPPER` ở đây là một `RowMapper<Account>` được định nghĩa trong lớp repository ở mục 9. Ký hiệu `?` dành cho **giá trị**, không dùng thay tên bảng, tên cột hoặc từ khóa `ORDER BY`. Nếu nghiệp vụ cho chọn cột sắp xếp, phải ánh xạ lựa chọn vào **danh sách tên cột cho phép** thay vì chèn chuỗi tùy ý.

### 6.2. NULL và kiểu SQL

Đối với giá trị `null`, một số driver cần biết rõ kiểu SQL:

```java
import java.sql.Types;

PreparedStatementSetter setter = ps -> {
    if (optionalOwner == null) {
        ps.setNull(1, Types.VARCHAR);
    } else {
        ps.setString(1, optionalOwner);
    }
};
```

Đây là fragment minh họa với biến `optionalOwner` đã có. `setNull(1, Types.VARCHAR)` nói rõ kiểu của tham số. Lưu ý ngữ nghĩa SQL: `WHERE owner = NULL` không khớp các hàng có `owner IS NULL`; nếu cần lọc dữ liệu `NULL`, phải chủ động thiết kế điều kiện `IS NULL` hoặc cú pháp tương đương phù hợp DB.

Với các kiểu số tiền, dùng `BigDecimal` thay vì `double` để tránh sai số nhị phân trong phép tính thập phân.

### 6.3. Nếu không cần callback setter riêng

`JdbcTemplate` có các overload nhận trực tiếp các đối số:

```java
List<String> names = jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    (rs, rowNum) -> rs.getString("owner"),
    "ACTIVE"
);
```

Về mặt trách nhiệm, template vẫn phải gán tham số. Nhưng lớp ứng dụng không cần tự định nghĩa một `PreparedStatementSetter` khi việc gán giá trị đơn giản đã được API xử lý. Nếu tên/kiểu tham số khó đọc vì có quá nhiều `?`, `NamedParameterJdbcTemplate` ở mục 12 có thể phù hợp hơn.

## 7. Phần đọc kết quả 1: RowMapper<T> cho mỗi hàng một đối tượng

`RowMapper<T>` có phương thức:

```java
T mapRow(ResultSet rs, int rowNum) throws SQLException;
```

Ý nghĩa: nhận **hàng hiện tại** và trả về **một giá trị T**. Spring đảm nhiệm lặp qua kết quả, gọi mapper một lần cho mỗi hàng rồi tập hợp các giá trị thành `List<T>`.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.RowMapper;

public record Account(long id, String owner, BigDecimal balance) {}

RowMapper<Account> mapper = (rs, rowNum) ->
    new Account(
        rs.getLong("id"),
        rs.getString("owner"),
        rs.getBigDecimal("balance")
    );
```

Các đoạn trên là ví dụ rời trong mã nguồn Java/Spring; một tệp biên dịch thực tế cần đặt record và biến trong phạm vi lớp/phương thức thích hợp (xem lớp hoàn chỉnh ở mục 9). Trong `mapRow` **không gọi `rs.next()`**: Spring đã đưa con trỏ đến đúng hàng trước khi callback chạy. Nếu tự gọi `next()` sẽ bỏ qua hàng hoặc đọc lệch dữ liệu.

`JdbcTemplate.query(sql, mapper)` trả danh sách rỗng nếu SQL không có hàng; `queryForObject(sql, mapper, ...)` lại yêu cầu đúng một hàng và có thể ném `EmptyResultDataAccessException` hoặc `IncorrectResultSizeDataAccessException` khi kích thước không như kỳ vọng.

Một record `Account` giúp mô hình kết quả dễ đọc. Đối với SQL `JOIN` 1–N, mỗi hàng kết quả có thể lặp dữ liệu cha, nên `RowMapper<Account>` đơn giản có thể trả nhiều đối tượng mang cùng khóa cha. Muốn gom một cấu trúc cha với nhiều con, hãy dùng truy vấn khác hoặc `ResultSetExtractor` có logic nhóm theo khóa.

## 8. Phần đọc kết quả 2: ResultSetExtractor<T> cho cả tập kết quả

`ResultSetExtractor<T>` có phương thức:

```java
T extractData(ResultSet rs) throws SQLException, DataAccessException;
```

Khác với `RowMapper`, callback này nhận **toàn bộ ResultSet** và tự điều khiển vòng lặp `while (rs.next())`, có thể trả bất kỳ cấu trúc nào: một đối tượng, danh sách, `Map`, cây dữ liệu, thống kê hoặc `null` khi nghiệp vụ yêu cầu.

Ví dụ đếm số hàng người dùng đang hoạt động:

```java
import org.springframework.jdbc.core.ResultSetExtractor;

ResultSetExtractor<Integer> extractor = rs -> {
    int count = 0;
    while (rs.next()) {
        count++;
    }
    return count;
};

int count = jdbcTemplate.query(
    "SELECT id FROM account WHERE status = ?",
    ps -> ps.setString(1, "ACTIVE"),
    extractor
);
```

Kết quả mẫu là `2`. Tuy nhiên nếu mục tiêu thật chỉ cần đếm hàng trong DB thì **`SELECT COUNT(*)` hiệu quả hơn** vì không phải truyền mọi hàng về Java. Ví dụ trên chỉ minh họa người điều khiển vòng lặp là extractor.

Có thể dùng extractor cho cấu trúc nhiều cấp. Ví dụ, một khách hàng có nhiều đơn:

```java
ResultSetExtractor<Map<Long, List<Long>>> extractor = rs -> {
    Map<Long, List<Long>> orderIdsByCustomer = new LinkedHashMap<>();
    while (rs.next()) {
        long customerId = rs.getLong("customer_id");
        List<Long> ids = orderIdsByCustomer.computeIfAbsent(
            customerId, ignored -> new ArrayList<>()
        );
        Long orderId = rs.getObject("order_id", Long.class);
        if (orderId != null) {
            ids.add(orderId);
        }
    }
    return orderIdsByCustomer;
};
```

Đoạn này cần import `java.util.Map`, `List`, `LinkedHashMap`, `ArrayList`, và một câu SQL cung cấp hai cột `customer_id`, `order_id` (ví dụ `LEFT JOIN` giữa khách hàng và đơn). Khi không có con, `getObject(..., Long.class)` trả `null`; khác với `getLong()` vốn trả 0 cho SQL NULL và cần kiểm tra `wasNull()`. Nếu SQL nối thêm nhiều bảng con, một đơn có thể xuất hiện nhiều lần; phải xác định rõ việc loại trùng theo **khóa con** hoặc thay thiết kế truy vấn.

**Không tự đóng `ResultSet` do `JdbcTemplate.query(...)` cung cấp trong `ResultSetExtractor`**. Template sở hữu vòng đời của nó. Nếu cần mở tài nguyên phụ *bên trong callback*, chính callback phải quản lý tài nguyên phụ ấy.

Một extractor thường có thể viết không lưu trạng thái và tái sử dụng. Nếu callback giữ biến mutable bên ngoài, phải cân nhắc khả năng dùng đồng thời giữa nhiều request.

## 9. Phần đọc kết quả 3: RowCallbackHandler cho mỗi hàng một hành động

`RowCallbackHandler` khác `RowMapper` ở kiểu trả về:

```java
void processRow(ResultSet rs) throws SQLException;
```

Template gọi `processRow` cho từng hàng, nhưng callback **không trả một đối tượng riêng để Spring tự xây `List<T>`**. Nó thích hợp để cập nhật bộ đếm, gửi dữ liệu đến bộ xử lý, tổng hợp cục bộ hoặc ghi vào một cấu trúc do caller quản lý.

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.jdbc.core.RowCallbackHandler;

List<String> owners = new ArrayList<>();
RowCallbackHandler collectOwner = rs ->
    owners.add(rs.getString("owner"));

jdbcTemplate.query(
    "SELECT owner FROM account WHERE status = ? ORDER BY id",
    ps -> ps.setString(1, "ACTIVE"),
    collectOwner
);
// owners chứa ["Lan", "Vy"] với dữ liệu mẫu.
```

Trong `RowCallbackHandler` **không gọi `rs.next()`**; Spring đã làm việc đó. Nếu mục tiêu chỉ là dựng một `List<Account>`, `RowMapper` thường ngắn gọn và dễ đọc hơn.

`RowCallbackHandler` không đương nhiên “stream” dữ liệu theo nghĩa tốn bộ nhớ hằng số: driver JDBC có thể đệm nhiều hoặc toàn bộ hàng theo cấu hình, và callback vẫn có thể giữ mọi hàng trong danh sách bên ngoài. Nếu làm xử lý tập lớn, cần xét fetch size, transaction, cách driver hỗ trợ con trỏ, giới hạn lượng dữ liệu và thời gian giữ connection.

Tránh giữ một `RowCallbackHandler` có trạng thái mutable dùng chung giữa nhiều request, vì các lời gọi có thể ghi đè hoặc trộn dữ liệu. Hãy tạo trạng thái riêng cho mỗi lần query, hoặc dùng thành phần đồng bộ phù hợp khi thật sự cần chia sẻ.

## 10. Một lớp Spring JDBC hoàn chỉnh ghép các callback

Ví dụ dưới đây là mã nguồn dành cho **ứng dụng Spring Boot đã có `DataSource`, `JdbcTemplate` và bảng `account` ở mục 4**. Nó biên dịch trong dự án Java 17+ có Spring JDBC/Spring context trên classpath; **không thể chạy riêng chỉ bằng JDK**.

Tạo tệp `AccountReadRepository.java`:

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.util.List;
import java.util.function.Consumer;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.ResultSetExtractor;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public final class AccountReadRepository {
    private static final String BY_STATUS = """
        SELECT id, owner, balance
        FROM account
        WHERE status = ?
        ORDER BY id
        """;

    private static final RowMapper<Account> ACCOUNT_ROW_MAPPER =
        (rs, rowNum) -> new Account(
            rs.getLong("id"),
            rs.getString("owner"),
            rs.getBigDecimal("balance")
        );

    private final JdbcTemplate jdbc;

    public AccountReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // SQL + tham số do PreparedStatementSetter cung cấp,
    // mỗi hàng do RowMapper biến thành một Account.
    public List<Account> findByStatus(String status) {
        PreparedStatementSetter setter = ps ->
            ps.setString(1, status);
        return jdbc.query(BY_STATUS, setter, ACCOUNT_ROW_MAPPER);
    }

    // PreparedStatementCreator tự tạo statement và gán tham số.
    public List<Account> findWithCreator(String status) {
        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(BY_STATUS);
            ps.setString(1, status);
            return ps;
        };
        return jdbc.query(creator, ACCOUNT_ROW_MAPPER);
    }

    // ResultSetExtractor đọc cả ResultSet và trả một tổng.
    public BigDecimal totalByStatus(String status) {
        String sql = """
            SELECT COALESCE(SUM(balance), 0) AS total_balance
            FROM account
            WHERE status = ?
            """;
        ResultSetExtractor<BigDecimal> extractor = rs ->
            rs.next() ? rs.getBigDecimal("total_balance")
                      : BigDecimal.ZERO;

        return jdbc.query(
            sql,
            (PreparedStatementSetter) ps -> ps.setString(1, status),
            extractor
        );
    }

    // RowCallbackHandler xử lý từng hàng mà không tạo List tự động.
    public void forEachByStatus(
        String status, Consumer<Account> receiver
    ) {
        RowCallbackHandler handler = rs -> receiver.accept(
            new Account(
                rs.getLong("id"),
                rs.getString("owner"),
                rs.getBigDecimal("balance")
            )
        );
        jdbc.query(
            BY_STATUS,
            (PreparedStatementSetter) ps -> ps.setString(1, status),
            handler
        );
    }

    public record Account(long id, String owner, BigDecimal balance) {}
}
```

Với dữ liệu mẫu ở mục 4:

- `findByStatus("ACTIVE")` trả danh sách hai `Account` có ID 1 và 3 theo thứ tự `ORDER BY id`.
- `findWithCreator("ACTIVE")` trả cùng danh sách, nhưng creator tự tạo statement.
- `totalByStatus("ACTIVE")` trả số tiền **210.00** theo tổng ở DB (kiểu `BigDecimal`, có thể khác cách biểu diễn scale giữa các DB).
- `forEachByStatus("ACTIVE", consumer)` gọi consumer hai lần. Nếu consumer ném ngoại lệ runtime, nó được lan truyền và việc truy vấn dừng; Spring vẫn thực hiện dọn tài nguyên theo hợp đồng.

Đây là **bốn hình thức cài đặt callback**, không phải bốn bước bắt buộc cho cùng một query. Trong thực tế chọn API ngắn nhất đáp ứng nhu cầu; không nhất thiết dùng `PreparedStatementCreator`, `Setter` và extractor cùng lúc.

## 11. PreparedStatementCallback<T>: tự chạy thao tác trên statement

Đôi khi ứng dụng cần chủ động gọi nhiều thao tác JDBC trên cùng một `PreparedStatement`. Khi ấy `PreparedStatementCallback<T>` kết hợp với `JdbcTemplate.execute(...)` hữu ích.

```java
import java.util.List;
import org.springframework.jdbc.core.PreparedStatementCallback;

int[] counts = jdbcTemplate.execute(
    "UPDATE account SET status = ? WHERE id = ?",
    (PreparedStatementCallback<int[]>) ps -> {
        for (long id : List.of(1L, 3L)) {
            ps.setString(1, "INACTIVE");
            ps.setLong(2, id);
            ps.addBatch();
        }
        return ps.executeBatch();
    }
);
```

Đây là ví dụ tích hợp, không độc lập. Template tạo statement, gọi callback, xử lý `SQLException` và đóng statement. Callback **tự gán tham số và tự gọi `executeBatch()`** trong ví dụ này. Kết quả `int[]` chứa thông tin số hàng bị thay đổi theo JDBC; một phần tử có thể là `Statement.SUCCESS_NO_INFO` thay vì số đếm cụ thể, tùy driver.

**Batch không đồng nghĩa giao dịch nguyên tử.** Nếu cần tất cả cập nhật thành công hoặc không có cập nhật nào, đặt thao tác trong giao dịch Spring phù hợp và xét khả năng DB/driver. Callback không được tự đóng statement mà template đang sở hữu. Nếu callback tự tạo thêm `ResultSet` hoặc stream phụ trong quá trình xử lý, phải đóng các tài nguyên phụ theo đúng hợp đồng trước khi trả về.

Trong công việc thường nhật, `jdbcTemplate.update(...)` hoặc `batchUpdate(...)` cung cấp API cấp cao hơn và ít lỗi hơn so với tự dùng `PreparedStatementCallback`.

## 12. Callback ở lớp khác: NamedParameterJdbcTemplate và JdbcClient

### 12.1. Khi có quá nhiều dấu hỏi `?`

Với `JdbcTemplate`, tham số là **theo vị trí**, ví dụ:

```sql
WHERE status = ? AND balance >= ? AND owner = ?
```

Với nhiều tham số hoặc điều kiện được xây có kiểm soát, `NamedParameterJdbcTemplate` giúp đặt tên:

```java
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

NamedParameterJdbcTemplate named = new NamedParameterJdbcTemplate(jdbcTemplate);

List<AccountReadRepository.Account> result = named.query(
    """
    SELECT id, owner, balance
    FROM account
    WHERE status = :status AND balance >= :minBalance
    ORDER BY id
    """,
    Map.of(
        "status", "ACTIVE",
        "minBalance", new BigDecimal("100.00")
    ),
    (rs, rowNum) -> new AccountReadRepository.Account(
        rs.getLong("id"),
        rs.getString("owner"),
        rs.getBigDecimal("balance")
    )
);
```

Trên dữ liệu mẫu, truy vấn trả đúng một khách hàng Lan. `NamedParameterJdbcTemplate` xử lý tham số đặt tên rồi sử dụng cơ chế JDBC phía dưới; nó vẫn có overload nhận `RowMapper`, `ResultSetExtractor`, `RowCallbackHandler`. Khi bản đồ dữ liệu chứa null hoặc cần chỉ định SQL type rõ ràng, cân nhắc `MapSqlParameterSource` thay vì `Map.of` (vốn không cho phép giá trị null).

### 12.2. JdbcClient trong Spring Framework 6.1+

Spring Framework 6.1 có `JdbcClient`: một facade dạng fluent để viết SQL, bind tham số và chỉ định mapper dễ đọc hơn. Nó phối hợp với `JdbcTemplate`/`NamedParameterJdbcTemplate` phía dưới, chứ không làm thay đổi hợp đồng của `RowMapper` hoặc cách JDBC quản lý kết nối. Với Spring cũ hơn 6.1, không giả định API này có sẵn.

```java
import org.springframework.jdbc.core.simple.JdbcClient;

JdbcClient client = JdbcClient.create(jdbcTemplate);
List<String> owners = client.sql(
        "SELECT owner FROM account WHERE status = :status ORDER BY id"
    )
    .param("status", "ACTIVE")
    .query((rs, rowNum) -> rs.getString("owner"))
    .list();
```

Ở đây ví dụ minh họa API cho dự án Spring Framework 6.1+ đã có `jdbcTemplate` và bảng thử nghiệm. Mục tiêu của bài vẫn là **hiểu callback và ranh giới trách nhiệm**, bởi cú pháp mới cũng cần chỉ rõ cách biến hàng dữ liệu thành đối tượng.

## 13. Quy tắc điều khiển ResultSet và tài nguyên

Đây là nguồn lỗi phổ biến nhất khi mới dùng callback:

| Điều cần làm | Người chịu trách nhiệm | Điều không nên làm |
| --- | --- | --- |
| Lấy `Connection` và gắn vào transaction | `JdbcTemplate`/Spring transaction infrastructure | Creator/mapper không tự gọi `close()` trên connection của template |
| Tạo `PreparedStatement` | Template hoặc `PreparedStatementCreator` do template gọi | Không tạo statement từ một connection khác ngoài template |
| Gán tham số | Template từ `Object...`, `PreparedStatementSetter` hoặc creator theo overload | Không nối trực tiếp chuỗi đầu vào vào SQL |
| Duyệt từng hàng cho mapper | `JdbcTemplate` | `RowMapper` không gọi `rs.next()` |
| Duyệt từng hàng cho handler | `JdbcTemplate` | `RowCallbackHandler` không gọi `rs.next()` |
| Duyệt cả tập cho extractor | `ResultSetExtractor` | Không chờ template tự lặp bên trong extractor |
| Đóng `ResultSet` và statement của query thông thường | `JdbcTemplate` | Không đóng `ResultSet` được template đưa vào extractor |
| Dọn tài nguyên phụ tự mở bên trong callback | Callback mở tài nguyên đó | Không để hở `ResultSet` phụ/stream do callback tạo |
| Dịch `SQLException` từ thao tác JDBC | `JdbcTemplate` qua `SQLExceptionTranslator` | Không bắt và nuốt mọi `SQLException` trong callback |
| Quản lý commit/rollback trong transaction Spring | Transaction manager phù hợp `DataSource` | Không `commit` hoặc `rollback` thủ công trên connection gắn với giao dịch |

Khi callback ném `SQLException` từ JDBC, Spring thường dịch thành `DataAccessException` (không kiểm tra checked exception) để tầng ứng dụng xử lý nhất quán. Lỗi nghiệp vụ runtime do callback chủ động ném không mặc định biến thành lỗi JDBC. Không bao tất cả lỗi bằng `catch (Exception)` rồi trả danh sách rỗng: như thế làm mất khả năng phân biệt “không có bản ghi” với “DB gặp sự cố”.

Nếu cần stream kết quả theo API `JdbcTemplate.queryForStream(...)`, **đóng `Stream`** sau khi đọc, thường bằng `try-with-resources`. Việc có stream không bảo đảm driver thực sự lấy từng hàng qua mạng với kích thước bộ nhớ hằng số; hành vi phụ thuộc DB, driver, fetch size và transaction.

## 14. Một ví dụ Java 17 chạy độc lập để hình dung callback

Ví dụ sau dùng **chỉ JDK 17**, không dùng Spring và không truy cập DB. Nó mô phỏng ba điểm mở rộng: một callback đưa SQL, một callback cung cấp danh sách tham số và một callback đọc hàng đã truy vấn. Các giao diện `SqlCallback`, `ParameterCallback`, `ResultCallback` là **giao diện mô phỏng trong bài**, không phải API của Spring; chúng giúp nhìn rõ cách template gọi logic được truyền từ bên ngoài.

Tạo tệp `CallbackFlowDemo.java`:

```java
import java.util.Arrays;
import java.util.List;

public final class CallbackFlowDemo {
    record Account(long id, String owner, int points) {}

    @FunctionalInterface
    interface SqlCallback {
        String sql();
    }

    @FunctionalInterface
    interface ParameterCallback {
        Object[] values();
    }

    @FunctionalInterface
    interface ResultCallback<T> {
        T read(List<Account> rows);
    }

    static <T> T execute(
            SqlCallback sqlCallback,
            ParameterCallback parameterCallback,
            ResultCallback<T> resultCallback) {
        String sql = sqlCallback.sql();
        Object[] parameters = parameterCallback.values();
        System.out.println("SQL: " + sql);
        System.out.println("params: " + Arrays.toString(parameters));

        // Mô phỏng DB đã thực thi WHERE points >= ? ORDER BY id.
        int minimum = (Integer) parameters[0];
        List<Account> resultRows = List.of(
            new Account(1, "Lan", 120),
            new Account(2, "Minh", 70),
            new Account(3, "Vy", 90)
        ).stream().filter(a -> a.points() >= minimum).toList();
        return resultCallback.read(resultRows);
    }

    public static void main(String[] args) {
        List<String> names = execute(
            () -> "SELECT owner FROM account WHERE points >= ? ORDER BY id",
            () -> new Object[] { 80 },
            rows -> rows.stream().map(Account::owner).toList()
        );
        System.out.println("owners: " + names);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CallbackFlowDemo.java
java CallbackFlowDemo
```

Đầu ra chính xác (đã có thứ tự ổn định trong dữ liệu mô phỏng):

```text
SQL: SELECT owner FROM account WHERE points >= ? ORDER BY id
params: [80]
owners: [Lan, Vy]
```

Mã mô phỏng không phân tích chuỗi SQL; nó cố ý lọc danh sách trong bộ nhớ. Khi thay bằng `JdbcTemplate` thật, SQL phải được thực thi bởi DB qua `PreparedStatement` và callback kết quả sẽ nhận `ResultSet` thay vì `List<Account>` giả lập. Điểm tương đồng là **quy trình chung gọi các hàm được truyền vào ở đúng giai đoạn**.

## 15. Chọn callback qua tình huống cụ thể

### Tình huống A: Tìm một danh sách khách hàng từ nhiều hàng

Đề bài: “Trả về một `List<Account>` cho các tài khoản có `status = ACTIVE`.”

Chọn `jdbcTemplate.query(sql, mapper, args...)` hoặc `query(sql, setter, mapper)`. `RowMapper` làm một việc rõ ràng: biến một hàng thành một `Account`. Không phải tự duyệt `ResultSet`.

### Tình huống B: Gom khách hàng và danh sách đơn theo khóa cha

Đề bài: “Một khách hàng được trả một lần cùng danh sách ID đơn.”

Nếu SQL trả nhiều hàng trên mỗi khách hàng do quan hệ 1–N, cân nhắc `ResultSetExtractor<Map<Id, ...>>` gom theo khóa chính và kiểm tra `NULL` của bên con. Cũng có thể tách truy vấn/DTO projection để tránh nhân hàng quá mức. `RowMapper<Customer>` đơn giản không tự gom các hàng SQL lặp khóa cha.

### Tình huống C: Tính thống kê chỉ cần một giá trị

Đề bài: “Đếm số tài khoản đang hoạt động.”

Ưu tiên:

```java
Integer count = jdbcTemplate.queryForObject(
    "SELECT COUNT(*) FROM account WHERE status = ?",
    Integer.class,
    "ACTIVE"
);
```

Kết quả là `2` với dữ liệu mẫu. SQL tổng hợp thực hiện ở DB nên thường tốt hơn việc kéo mọi hàng về Java cho `RowCallbackHandler` tăng bộ đếm. Trong nghiệp vụ cần số lớn, cân nhắc `Long.class`/`COUNT` và giới hạn kiểu số phù hợp.

### Tình huống D: Gửi hàng kết quả đến bộ xử lý mà không cần danh sách trả về

Dùng `RowCallbackHandler` nếu cần hành động cho mỗi hàng. Đừng cho rằng callback tự động loại bỏ hoàn toàn nhu cầu bộ nhớ; hành vi fetch phụ thuộc driver và trạng thái ứng dụng.

### Tình huống E: Cần tạo statement với `RETURN_GENERATED_KEYS`

Dùng overload `update(PreparedStatementCreator, KeyHolder)` như mục 5.3. Chú ý schema cột phải tự sinh khóa và driver phải hỗ trợ.

### Tình huống F: Cần tự gọi `executeBatch()` trên cùng statement

`PreparedStatementCallback<int[]>` có thể xử lý. Nếu chỉ đơn giản cập nhật nhiều bản ghi bằng cùng SQL, kiểm tra `batchUpdate(...)` trước vì API cấp cao thường đủ nhu cầu.

### Tình huống G: Có 8 tham số khó hiểu vì thứ tự

`PreparedStatementSetter` tách phần binding ra khỏi SQL nhưng vẫn là theo vị trí. Nếu tên trường có ý nghĩa hơn số thứ tự, chuyển sang `NamedParameterJdbcTemplate` hoặc `JdbcClient` khi phiên bản Spring hỗ trợ.

## 16. Các lỗi phổ biến và cách sửa

**Lỗi 1 – Gọi `rs.next()` trong `RowMapper`:** bỏ qua hàng vì Spring đã di chuyển con trỏ. Chỉ đọc cột của hàng hiện tại.

**Lỗi 2 – Không gọi `rs.next()` trong `ResultSetExtractor` mà truy cập cột ngay:** con trỏ thường chưa ở một hàng hợp lệ. Extractor phải tự duyệt, ví dụ `if (rs.next())` hoặc `while (rs.next())`.

**Lỗi 3 – Gọi `rs.next()` trong `RowCallbackHandler`:** cũng làm nhảy con trỏ và mất dữ liệu. Spring tự duyệt từng hàng cho handler.

**Lỗi 4 – Truyền nhầm thứ tự hai tham số:** thứ tự `ps.setString(1, ...)`, `ps.setBigDecimal(2, ...)` phải đúng vị trí dấu `?` trong SQL. Biến có tên rõ và kiểm thử với dữ liệu phân biệt từng cột sẽ giúp phát hiện.

**Lỗi 5 – Cố dùng `?` cho tên bảng hoặc cột:** placeholder JDBC thay giá trị, không thay cấu trúc cú pháp SQL. Với tên cột động, dùng allowlist; với giá trị người dùng, luôn bind.

**Lỗi 6 – Biến mọi lỗi thành danh sách rỗng:** một truy vấn không trả hàng khác với lỗi kết nối, lỗi SQL, lỗi quyền hay timeout. Giữ ngoại lệ phù hợp để tầng gọi quyết định xử lý.

**Lỗi 7 – Dùng `RowMapper` để kết luận tập SQL đã độc nhất theo đối tượng cha:** truy vấn `JOIN` 1–N vẫn có thể trả nhiều hàng cho cùng khóa cha. Xác định đơn vị hàng kết quả và gom theo khóa khi cần.

**Lỗi 8 – Dùng lại callback chứa trạng thái mutable toàn cục:** handler ghi vào cùng một `ArrayList` cho nhiều request có thể trộn dữ liệu hoặc gây vấn đề đồng thời. Tạo collection bên trong phạm vi truy vấn.

**Lỗi 9 – Giữ connection quá lâu trong callback:** đọc mạng, gọi API khác hoặc ngủ trong callback có thể giữ `Connection`, làm pool thiếu kết nối và kéo dài transaction. Tách công việc nặng khỏi giai đoạn giữ kết nối khi nghiệp vụ cho phép.

**Lỗi 10 – Tự đóng tài nguyên thuộc Spring:** không đóng `Connection` trong `PreparedStatementCreator`, không đóng `ResultSet` do template cấp cho extractor. Chỉ đóng tài nguyên phụ do callback tự mở.

**Lỗi 11 – Nhầm `queryForObject` với `query`:** `query` dùng mapper trả `List<T>`, có thể rỗng; `queryForObject` yêu cầu đúng một hàng. Nếu nhiều hàng thì có lỗi kích thước; không nên gọi nó rồi hy vọng tự chọn hàng đầu.

**Lỗi 12 – Hiểu rằng `RowCallbackHandler` bảo đảm streaming:** driver có thể đã tải nhiều dữ liệu trước khi callback được gọi. Với tập lớn, quan sát fetch size, thời lượng giao dịch, bộ nhớ và cách driver quản lý cursor; bảo đảm đóng stream nếu dùng API stream.

## 17. Bài tập kiểm tra hiểu biết

**Bài 1.** Cần biến mỗi hàng SQL thành một `Account` và trả `List<Account>`. Dùng callback nào?

**Đáp án:** `RowMapper<Account>` trong `JdbcTemplate.query(...)`. Spring lặp result set và gom danh sách.

**Bài 2.** Cần đặt hai tham số cho `WHERE status = ? AND balance >= ?`. Callback nào chỉ chịu trách nhiệm binding?

**Đáp án:** `PreparedStatementSetter`, dùng `ps.setString(1, status)` và `ps.setBigDecimal(2, minBalance)`. Nếu đơn giản, cũng có thể truyền trực tiếp `Object... args`.

**Bài 3.** Cần tự duyệt toàn bộ `ResultSet` để trả `Map<Long, List<Long>>` nhóm theo khóa cha. Dùng gì?

**Đáp án:** `ResultSetExtractor<Map<Long, List<Long>>>` vì extractor điều khiển vòng `rs.next()` và tạo một cấu trúc kết quả tổng thể.

**Bài 4.** Vì sao `processRow(ResultSet rs)` không được gọi `rs.next()`?

**Đáp án:** `JdbcTemplate` đã đặt cursor ở hàng hiện tại trước khi gọi `RowCallbackHandler`. Tự tiến con trỏ sẽ bỏ hàng hoặc phá hỏng thứ tự xử lý.

**Bài 5.** Muốn lấy khóa được sinh từ `INSERT` thì callback nào giúp chuẩn bị statement có `RETURN_GENERATED_KEYS`?

**Đáp án:** `PreparedStatementCreator`, dùng với overload `jdbcTemplate.update(creator, keyHolder)` và DB/driver hỗ trợ.

**Bài 6.** Callback ném `SQLException`. Có cần tự đóng connection đang thuộc `JdbcTemplate` không?

**Đáp án:** Không. `JdbcTemplate` bắt và dịch ngoại lệ JDBC, đồng thời quản lý statement, result set và connection theo transaction. Chỉ dọn tài nguyên phụ do callback tự tạo.

**Bài 7.** Truy vấn trả 0 hàng. `query(sql, mapper)` và `queryForObject(sql, mapper)` khác nhau ra sao?

**Đáp án:** `query` trả danh sách rỗng, còn `queryForObject` yêu cầu đúng một hàng, nên có thể ném `EmptyResultDataAccessException`.

**Bài 8.** Với SQL mẫu ở mục 4, `RowMapper` truy vấn `status = ACTIVE` tạo bao nhiêu đối tượng?

**Đáp án:** Hai: tài khoản Lan và Vy. `ResultSetExtractor` có thể trả một số 2, một danh sách hoặc một `Map` tùy cách triển khai; kiểu callback không thay đổi số hàng SQL do DB trả.

## 18. Ghi nhớ

- `JdbcTemplate` giữ **quy trình chung**; callback mô tả những phần thay đổi: **SQL**, **tham số**, **cách đọc kết quả**.
- `PreparedStatementCreator` tạo statement từ connection; `PreparedStatementSetter` gán tham số cho statement đã có.
- `RowMapper` trả một đối tượng cho **mỗi hàng**; `RowCallbackHandler` thực hiện một hành động cho mỗi hàng; `ResultSetExtractor` duyệt **toàn bộ tập** và trả một kết quả tổng thể.
- `RowMapper` và `RowCallbackHandler` **không gọi `rs.next()`**; `ResultSetExtractor` phải tự di chuyển con trỏ nếu muốn đọc hàng.
- `PreparedStatementCallback` cho phép chủ động thao tác trên một `PreparedStatement` khi API cấp cao chưa đủ; template vẫn quản lý tài nguyên và dịch lỗi JDBC.
- Ưu tiên `query(sql, mapper, args...)`, `update(...)` hoặc `batchUpdate(...)` khi chúng đã diễn tả yêu cầu. Chỉ tạo callback cấp thấp khi cần kiểm soát thật sự.
- Dùng tham số bind thay vì nối chuỗi đầu vào vào SQL; quản lý `NULL` và thứ tự `?`; không chia sẻ callback chứa trạng thái không an toàn giữa nhiều request.
- Với Spring 6.1+, `JdbcClient` giúp diễn đạt cùng công việc bằng fluent API; hiểu các hợp đồng callback vẫn cần thiết để tránh lỗi ánh xạ và tài nguyên.

### Tài liệu đối chiếu

- [Spring Framework 6.1: `JdbcTemplate` API](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [Spring Framework 6.1: `PreparedStatementCreator`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreator.html)
- [Spring Framework 6.1: `RowCallbackHandler`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/RowCallbackHandler.html)
- [Spring Framework 6.1: `ResultSetExtractor`](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/jdbc/core/ResultSetExtractor.html)
- [Spring Framework: Data Access with JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
