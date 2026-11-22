# Chọn tham số theo tên hoặc vị trí để giữ truy vấn JDBC dễ bảo trì

## 1. Vấn đề: cùng một câu SQL, hai cách biểu diễn tham số

Trong tầng truy cập dữ liệu của Spring Framework, câu SQL thường cần giá trị từ ứng dụng: ID, mã trạng thái, ngày bắt đầu, hạn mức, danh sách khóa... JDBC gốc sử dụng **placeholder theo vị trí** `?`. Spring JDBC bổ sung **placeholder theo tên** `:status`, `:customerId` qua `NamedParameterJdbcTemplate`; từ Spring Framework 6.1 còn có `JdbcClient` hỗ trợ cả hai phong cách trong một API fluent.

Bài học này hướng đến một quyết định thực tế: **nên dùng tham số theo tên hay theo vị trí ở từng câu SQL để code rõ nghĩa, an toàn và dễ bảo trì?** Không có đáp án “named luôn tốt” hoặc “positional luôn nhanh”; điểm quan trọng là số lượng tham số, khả năng đọc, nguy cơ nhầm thứ tự, tần suất thay đổi câu SQL và convention của dự án.

Sau bài này, bạn sẽ biết:
- Viết đúng `JdbcTemplate` với `?` và `NamedParameterJdbcTemplate` với `:name`.
- Hiểu named parameter cuối cùng được Spring chuyển sang JDBC placeholder theo vị trí; cả hai vẫn dùng prepared binding cho **giá trị**.
- Chọn style theo tiêu chí, không theo cảm giác.
- Tránh lỗi **thay đổi thứ tự tham số** mà SQL vẫn chạy nhưng trả/cập nhật sai dữ liệu.
- Tận dụng tham số có tên lặp lại, `MapSqlParameterSource`, `BeanPropertySqlParameterSource`, typed SQL NULL, `IN (:ids)`, batch update.
- Hiểu khi nào named parameters **không** giải quyết vấn đề: dynamic identifier, SQL injection qua SQL fragment, truy vấn sai, logic SQL NULL, transaction và giới hạn driver.
- Chạy một ví dụ Java 17/Spring Boot/H2 có kết quả xác định và xây dựng bộ test kiểm tra cả hai cách binding.

**Bối cảnh kỹ thuật:** Spring JDBC trong Spring Framework 6.x, Spring Boot 3.x, Java 17+, `JdbcTemplate`/`NamedParameterJdbcTemplate` (blocking JDBC). Các ví dụ minh họa SQL quan hệ cơ bản; những cú pháp đặc thù PostgreSQL/Oracle/MySQL cần kiểm thử riêng.

## 2. Hai cách bind cơ bản: nhìn SQL là hiểu ngay

Giả sử cần tìm các khách hàng có trạng thái `ACTIVE` tại Việt Nam. SQL trả về cột `id`, `email`.

### 2.1. Theo vị trí với JdbcTemplate

```java
// Snippet trong class có JdbcTemplate jdbc.
List<CustomerRow> customers = jdbc.query("""
        SELECT id, email
        FROM customers
        WHERE status = ? AND country_code = ?
        ORDER BY id
        """,
    (rs, rowNum) -> new CustomerRow(
        rs.getLong("id"),
        rs.getString("email")
    ),
    "ACTIVE", "VN");
```

Tham số 1 là `status`, tham số 2 là `country_code`. Vị trí phụ thuộc thứ tự dấu `?` từ trái sang phải; đối số Java truyền theo cùng thứ tự.

### 2.2. Theo tên với NamedParameterJdbcTemplate

```java
// Snippet trong class có NamedParameterJdbcTemplate namedJdbc.
Map<String, ?> params = Map.of(
    "status", "ACTIVE",
    "country", "VN"
);

List<CustomerRow> customers = namedJdbc.query("""
        SELECT id, email
        FROM customers
        WHERE status = :status AND country_code = :country
        ORDER BY id
        """,
    params,
    (rs, rowNum) -> new CustomerRow(
        rs.getLong("id"),
        rs.getString("email")
    ));
```

Cặp `"status"` khớp placeholder `:status` và `"country"` khớp `:country`, **không phụ thuộc thứ tự các entry trong Map**. Tên là một phần contract giữa câu SQL và nguồn tham số, không phải tên cột bắt buộc phải trùng hệt: `:country` có thể bind cho cột `country_code` nếu ý nghĩa rõ.

### 2.3. Hai cách trả cùng kết quả khi bind đúng

Với cùng SQL logic, cùng giá trị và cùng cơ sở dữ liệu, hai phương thức **có ý nghĩa truy vấn tương đương**. Tham số named không biến SQL thành ngôn ngữ khác hoặc cung cấp một loại transaction mới. Nó là một lớp tiện ích đặt tên cho placeholder.

Đây là bản chất của quyết định bảo trì:
- `?` giúp SQL gọn khi chỉ có một hoặc hai tham số rõ ràng.
- `:name` tự tài liệu hóa ý nghĩa khi có nhiều tham số, những điều kiện giống kiểu, hoặc khi SQL thường xuyên thay đổi thứ tự.
- Cả hai **phải** dùng binding thay vì nối giá trị người dùng trực tiếp vào SQL.

Record để dùng trong ví dụ:

```java
// CustomerRow.java
package example.jdbc;

public record CustomerRow(long id, String email) {}
```

Các snippet đầu bài giả sử import phù hợp và bean JDBC đã được inject; dự án chạy đầy đủ nằm ở phần 15.

## 3. Bên dưới NamedParameterJdbcTemplate vẫn là JDBC positional binding

Theo cơ chế Spring JDBC, `NamedParameterJdbcTemplate` phân tích SQL chứa `:name` và chuyển các placeholder có tên thành những dấu `?` mà JDBC `PreparedStatement` hiểu, rồi sắp xếp/cung cấp giá trị theo thứ tự tương ứng.

```text
Ứng dụng:
  SELECT id FROM customers
  WHERE status = :status AND country_code = :country

Giá trị:
  status -> "ACTIVE"
  country -> "VN"

Spring named-parameter adapter:
  1. Parse SQL, tìm các named placeholder hợp lệ.
  2. Xây JDBC SQL dùng '?' (hoặc mở rộng list khi cần).
  3. Tạo thứ tự binding: ["ACTIVE", "VN"].

JDBC PreparedStatement:
  SELECT id FROM customers
  WHERE status = ? AND country_code = ?
                  1                    2

Database thực thi câu SQL với giá trị đã bind.
```

Sơ đồ trên là **mô tả logic**, không phải mã nguồn từng bước của Spring. Spring còn xử lý chuỗi SQL, tham số lặp lại, metadata SQL type, các danh sách giá trị và cache parsed SQL khi phù hợp. Cần tránh tự viết regex đơn giản để chuyển `:name` thành `?` trong SQL production; dấu hai chấm có thể xuất hiện trong cú pháp hoặc literal SQL.

**Điểm chính:** dùng named parameters không làm mất tính prepared binding cho giá trị. Đúng như `JdbcTemplate`, `NamedParameterJdbcTemplate` vẫn có JDBC connection/statement/resultset lifecycle, exception translation và transaction participation trong context Spring phù hợp.

### Không nên suy luận named luôn nhanh/chậm hơn positional

Có công việc phân tích placeholder ở phía Java, nhưng Spring có cơ chế cache parsed SQL và vẫn delegate đến JDBC template. Nhiều workload bị chi phối bởi network, index, join, IO hoặc số hàng trả về chứ không bởi chi phí chuyển tên. Khi tối ưu, hãy đo **latency thực**, SQL plan, query count và connection pool thay vì đổi style vì cảm giác hiệu năng.

## 4. Khi nên ưu tiên tham số theo vị trí `?`

Positional binding thường hợp lý khi:
1. Câu SQL chỉ có **một tham số**, ví dụ `WHERE id = ?`.
2. Có **hai tham số khác vai trò rõ ràng**, ví dụ `WHERE created_at >= ? AND created_at < ?` nếu tên biến ở Java nói rõ.
3. Câu SQL ngắn và ổn định, thứ tự hiển nhiên.
4. Bạn đang sử dụng `JdbcTemplate` đã tồn tại và việc đổi sang named không cải thiện đáng kể khả năng đọc.
5. Tương tác JDBC cấp thấp đang nhận parameter index trực tiếp, ví dụ `PreparedStatementSetter` cho vendor-specific binding.

Ví dụ rõ ràng:

```java
// Trong repository có field JdbcTemplate jdbc.
public int deleteExpiredSessions(java.time.Instant cutoff) {
    return jdbc.update("""
            DELETE FROM sessions WHERE expires_at < ?
            """,
        java.sql.Timestamp.from(cutoff));
}
```

Đúng một placeholder, một giá trị. Thay bằng `:cutoff` cũng đúng nhưng không nhất thiết làm code dễ bảo trì hơn.

### Ưu điểm và cái giá của positional

**Ưu điểm:** ít cú pháp, quen thuộc với JDBC/driver, không cần quản lý Map/SqlParameterSource cho những câu query đơn giản.

**Cái giá:** ý nghĩa tham số nằm ở **vị trí**, nên thêm/bớt/hoán đổi điều kiện SQL phải rà lại giá trị tương ứng. Càng nhiều parameter có cùng kiểu Java, lỗi càng dễ lọt qua compiler.

Ví dụ:

```java
// SQL thay đổi vị trí hai điều kiện:
String sql = """
    SELECT id FROM customers
    WHERE country_code = ? AND status = ?
    """;

// SAI: giữ thứ tự argument như khi SQL còn "status = ? AND country_code = ?".
var rows = jdbc.queryForList(sql, Long.class, "ACTIVE", "VN");
```

Ở đây cả hai đều `String`, code có thể chạy nhưng tìm `country_code = 'ACTIVE'` và `status = 'VN'`. Kết quả có thể rỗng mà **không có exception**; trong câu UPDATE, nhầm thứ tự còn có thể sửa nhầm dữ liệu.

Cách sửa positional là đổi args thành `"VN", "ACTIVE"` và thêm test. Nếu SQL thay đổi liên tục hoặc số tham số tăng, named parameters giúp giảm rủi ro này.

## 5. Khi nên ưu tiên tham số theo tên `:name`

Named binding thường đáng giá khi:
1. Query có **nhiều placeholder**, đặc biệt nhiều giá trị cùng kiểu (`String`/`Long`).
2. Tên tham số truyền ý nghĩa tốt hơn thứ tự, ví dụ `:startDate`, `:endDate`, `:status`, `:minAmount`.
3. **Cùng một giá trị xuất hiện nhiều lần** trong SQL: một tên có thể dùng lặp lại.
4. Query có nhiều `WHERE`, `JOIN`, `UPDATE SET` hoặc thay đổi theo requirement.
5. Có thể map giá trị từ một **form/DTO/command object** có field tên rõ, với `BeanPropertySqlParameterSource` khi phù hợp.
6. Muốn biểu diễn `IN (:ids)` với list tham số thay vì tự sinh các dấu `?`.
7. Code review cần dễ đối chiếu SQL với param values/types.
8. Lớp repository có convention named params nhất quán, giúp đọc và debug.

Ví dụ với nhiều tham số:

```java
// Method trong repository có field NamedParameterJdbcTemplate namedJdbc.
public int updateSubscription(
        long subscriptionId,
        String nextStatus,
        String reason,
        java.time.Instant changedAt,
        long expectedVersion) {

    var params = new MapSqlParameterSource()
        .addValue("id", subscriptionId)
        .addValue("status", nextStatus)
        .addValue("reason", reason)
        .addValue("changedAt",
            java.sql.Timestamp.from(changedAt))
        .addValue("expectedVersion", expectedVersion);

    return namedJdbc.update("""
            UPDATE subscriptions
            SET status = :status,
                reason = :reason,
                changed_at = :changedAt,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """, params);
}
```

Số hàng cập nhật là **0 hoặc 1** nếu `id` là PRIMARY KEY. Giá trị 0 có thể nghĩa là không tồn tại hoặc optimistic lock/version mismatch, không được tự diễn giải thành một lỗi cụ thể nếu chưa xét contract. Named parameters giúp đối chiếu từng biến với cột SQL mà không phải đếm `?`.

## 6. Bảng quyết định nhanh: named hay positional?

| Tình huống | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| `SELECT ... WHERE id = ?` | Positional hoặc named | Một tham số, thứ tự quá rõ |
| Hai tham số khác kiểu (`Long` và `Instant`) | Positional thường đủ | Compiler/test dễ phát hiện một số nhầm lẫn |
| 5–10 tham số cùng kiểu String | Named | Tránh lỗi hoán vị có thể chạy im lặng |
| Một giá trị dùng tại ba vị trí SQL | Named | Bind một tên, tránh lặp args thủ công |
| SQL dài có nhiều join/filter | Named | Tên làm query dễ review |
| Danh sách IDs thay đổi độ dài | Named `IN (:ids)` | Spring mở rộng placeholder list |
| Cập nhật từ JavaBean/command object | Named + `BeanPropertySqlParameterSource` khi contract rõ | Giảm mapping thủ công |
| SQL rất ngắn đã chạy ổn định | Giữ style hiện tại | Đổi chỉ vì sở thích tăng churn |
| Cần bind JDBC vendor type rất đặc biệt | Tùy API; `PreparedStatementSetter`/`SqlParameterSource` | Khả năng binding quan trọng hơn cú pháp tên |
| Team đã có convention nhất quán | Theo convention nếu vẫn bảo đảm đúng nghĩa | Giảm chi phí đổi style giữa module |
| Truy vấn tạo từ dynamic clauses | Named thường dễ ghép conditions, nhưng vẫn có quy tắc bảo mật | Tên ổn định khi thứ tự clause thay đổi |

**Đề xuất thực dụng:** dùng positional cho lệnh ngắn với 1–2 tham số, cân nhắc named khi query dài, nhiều tham số cùng loại, lặp lại giá trị hoặc thay đổi thường xuyên. Không tạo quy định cứng “câu nào cũng phải named” khi không có lợi ích bảo trì.

## 7. Lỗi hoán đổi giá trị: demo bảo trì điển hình

Giả sử repository nhận `status="ACTIVE"` và `country="VN"`.

Phiên bản ban đầu:

```java
String sql = """
    SELECT id FROM customers
    WHERE status = ? AND country_code = ?
    """;
List<Long> ids = jdbc.queryForList(
    sql, Long.class, status, country);
```

Một lần sửa query đưa điều kiện country lên trước vì muốn nhóm điều kiện theo index:

```java
String sql = """
    SELECT id FROM customers
    WHERE country_code = ? AND status = ?
    """;

// BUG: quên sửa order của args.
List<Long> ids = jdbc.queryForList(
    sql, Long.class, status, country);
```

Sai nhưng **không sai cú pháp**. Vì cả hai tham số đều String, JDBC không thể biết programmer muốn dùng cái nào làm country.

Với named params:

```java
String sql = """
    SELECT id FROM customers
    WHERE country_code = :country AND status = :status
    """;

List<Long> ids = namedJdbc.queryForList(
    sql,
    Map.of("status", status, "country", country),
    Long.class);
```

Thứ tự của câu `WHERE` đã đổi, nhưng mapping theo tên vẫn đúng. Người review chỉ cần đối chiếu `:country` với `"country"` và `:status` với `"status"`; không đếm placeholder.

**Giới hạn:** nếu đặt tên sai ý nghĩa, ví dụ `Map.of("country", status, "status", country)`, named binding **vẫn sai**. Tên giúp phát hiện lỗi, không thay thế test và code review.

## 8. Tham số lặp lại trong cùng một truy vấn

Một named parameter có thể xuất hiện nhiều lần, chỉ cần định nghĩa một giá trị:

```java
// Method trong class có namedJdbc.
Long count = namedJdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE points >= :threshold
          AND (points - :threshold) <= :maxGap
        """,
    Map.of("threshold", 20, "maxGap", 20),
    Long.class);
```

`:threshold` xuất hiện hai lần. Spring tạo hai vị trí JDBC `?`, cả hai bind cùng giá trị 20 tương ứng tên threshold. Khi sửa threshold ở nơi gọi, không phải tìm và sửa hai đối số theo vị trí.

Tương đương positional:

```java
Long count = jdbc.queryForObject("""
        SELECT COUNT(*)
        FROM customers
        WHERE points >= ?
          AND (points - ?) <= ?
        """,
    Long.class,
    threshold,
    threshold,
    maxGap);
```

Nếu programmer quên vị trí `threshold` thứ hai, kết quả có thể sai âm thầm.

**Một named key có đúng một giá trị trong một lần thực thi**. Nếu SQL có hai vị trí muốn nhận **hai** giá trị khác nhau thì không được dùng chung một tên; đặt `:minPoints` và `:maxPoints` riêng.

## 9. Nguồn cung cấp named parameters: Map, MapSqlParameterSource, BeanPropertySqlParameterSource

### 9.1. Map: tốt khi có vài giá trị không null

```java
Map<String, Object> params = Map.of(
    "status", "ACTIVE",
    "country", "VN",
    "limit", 100
);
```

`Map.of` tiện và immutable, nhưng **không cho phép null key hoặc null value**. Đừng viết `Map.of("note", null)` khi field nullable: Java ném `NullPointerException` trước khi JDBC xử lý.

Một `HashMap` cho phép null nhưng không mang SQL type metadata một cách trực tiếp. Với một vài giá trị thông thường không null, `Map` đủ rõ.

### 9.2. MapSqlParameterSource: mở rộng khi cần type/null

```java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
    .addValue("id", 2L, Types.BIGINT)
    .addValue("note", null, Types.VARCHAR);

int affected = namedJdbc.update("""
        UPDATE customers
        SET note = :note
        WHERE id = :id
        """, params);
```

`MapSqlParameterSource` implements `SqlParameterSource`. Nó cung cấp named values và metadata JDBC type khi cần; `Types.VARCHAR` báo parameter `:note` là SQL VARCHAR dù Java value đang null.

Hãy nhớ: **typed NULL vẫn là SQL NULL**. Với `SET note = :note`, nó làm giá trị note thành NULL; không có nghĩa “giữ nguyên”. Với `WHERE note = :note` và null, quy tắc SQL ba giá trị khiến phép so sánh không TRUE; muốn lọc NULL hãy dùng `IS NULL`/null-safe semantics phù hợp.

### 9.3. BeanPropertySqlParameterSource: khi DTO/JavaBean khớp SQL

```java
public final class PointChange {
    private final String email;
    private final int points;

    public PointChange(String email, int points) {
        this.email = email;
        this.points = points;
    }

    public String getEmail() {
        return email;
    }

    public int getPoints() {
        return points;
    }
}
```

Tại repository:

```java
var input = new PointChange("binh@example.test", 25);

int affected = namedJdbc.update("""
        UPDATE customers
        SET points = :points
        WHERE email = :email
        """,
    new BeanPropertySqlParameterSource(input));
```

`BeanPropertySqlParameterSource` đọc các property của object. Cần tên property đúng (ở ví dụ: `points`, `email`) và accessors hoạt động. Với object quá lớn chứa nhiều field ngoài SQL, cần cẩn thận không vô tình bind sai dữ liệu qua những tên trùng; các placeholder SQL mới là danh sách tham số thực dùng.

Trong nhiều dự án Java 17, record cũng có thể được hỗ trợ theo Spring version/API mapper; một JavaBean có getter công khai như ví dụ giúp diễn giải contract rõ ràng và dễ kiểm thử. Nếu muốn SQL types cho property nullable, `registerSqlType("note", Types.VARCHAR)` trên `SqlParameterSource` tương ứng hoặc chọn `MapSqlParameterSource` minh bạch.

## 10. Collection và mệnh đề IN (:ids)

Đây là một lý do thực tế để chọn named parameters. Giả sử muốn lấy khách hàng theo danh sách ID có độ dài thay đổi:

```java
List<Long> ids = List.of(1L, 4L);

List<CustomerRow> customers = namedJdbc.query("""
        SELECT id, email
        FROM customers
        WHERE id IN (:ids)
        ORDER BY id
        """,
    new MapSqlParameterSource("ids", ids),
    (rs, rowNum) ->
        new CustomerRow(
            rs.getLong("id"), rs.getString("email")));
```

Spring có thể mở rộng `:ids` thành số lượng placeholder JDBC tương ứng, ví dụ `IN (?, ?)` rồi bind hai giá trị. Không cần tự tạo chuỗi `"1,4"` hoặc nối thẳng các ID do người dùng đưa vào SQL.

**Cần xử lý tập rỗng:** nếu `ids = List.of()`, nhiều SQL dialect không chấp nhận `IN ()`, và không có bảo đảm portable về cách driver/template xử lý. Hãy quyết định ý nghĩa nghiệp vụ trước:

```java
// Method minh họa trong repository có namedJdbc và CUSTOMER_MAPPER.
public List<CustomerRow> findByIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return namedJdbc.query("""
            SELECT id, email
            FROM customers
            WHERE id IN (:ids)
            ORDER BY id
            """,
        new MapSqlParameterSource("ids", ids),
        CUSTOMER_MAPPER);
}
```

Đây là lựa chọn nếu **không có ID => không có kết quả**. Một API khác có thể hiểu “không filter” và trả toàn bộ dữ liệu: không được mặc định hai nghĩa giống nhau.

Khi list rất dài:
- SQL có thể vượt giới hạn tham số của driver/database.
- SQL text sau mở rộng có kích thước thay đổi, ảnh hưởng plan/cache tùy DB.
- Có thể cần chia batch có kiểm soát, dùng temp table/table-valued parameter/array theo DB, hoặc join bảng chứa ID.
- Không để caller gửi danh sách tùy ý không giới hạn rồi ghép vào câu SQL lớn.

**Named parameters không thay thế pagination.** Dùng `ORDER BY` nhất quán, `LIMIT/OFFSET` hoặc keyset pagination theo use case.

## 11. Điều kiện tùy chọn và SQL động: tránh cả hai loại lỗi

Filter tìm kiếm có thể chứa `status`, `country`, `createdAfter`, `minPoints`. Named params hỗ trợ cấu trúc dễ đọc khi thêm điều kiện.

Ví dụ chỉ xây các mệnh đề được code xác định trước:

```java
// Snippet trong repository có NamedParameterJdbcTemplate namedJdbc.
public List<CustomerRow> search(
        String status,
        String country) {

    StringBuilder sql = new StringBuilder("""
        SELECT id, email
        FROM customers
        WHERE 1 = 1
        """);

    var params = new MapSqlParameterSource();

    if (status != null) {
        sql.append(" AND status = :status");
        params.addValue("status", status);
    }
    if (country != null) {
        sql.append(" AND country_code = :country");
        params.addValue("country", country);
    }

    sql.append(" ORDER BY id");

    return namedJdbc.query(
        sql.toString(), params, CUSTOMER_MAPPER);
}
```

Điểm bảo mật: đoạn code chỉ nối **SQL fragment cố định đã viết sẵn** trong source; giá trị người dùng tiếp tục đi qua named binding. Không chèn trực tiếp một chuỗi filter/sort từ request.

**Vấn đề bảo trì cần chú ý:**
- Chỉ tạo placeholder khi đã thêm giá trị tương ứng. Nếu thêm `AND status = :status` nhưng quên `params.addValue("status", ...)`, Spring sẽ báo lỗi thiếu parameter.
- Nếu một filter không có giá trị, quyết định rõ là bỏ điều kiện, lọc NULL hay báo validation error. Không để Java null tự “đoán”.
- Không dùng quá nhiều `(:x IS NULL OR col = :x)` như mẹo cho mọi filter: ngoài semantics NULL, dạng SQL này có thể ảnh hưởng plan/index tùy DB. Hãy đo và chọn chiến lược phù hợp.
- Không để số tổ hợp SQL động tăng không kiểm soát. Nếu query quá nhiều biến thể, cân nhắc query builder có kiểm soát hoặc tách các query rõ ràng.

### Lỗi có thể xuất hiện với positional dynamic SQL

Với `JdbcTemplate`, cùng kỹ thuật có thể thực hiện bằng `List<Object>`:

```java
List<Object> args = new ArrayList<>();
StringBuilder sql = new StringBuilder(
    "SELECT id, email FROM customers WHERE 1 = 1");

if (status != null) {
    sql.append(" AND status = ?");
    args.add(status);
}
if (country != null) {
    sql.append(" AND country_code = ?");
    args.add(country);
}

sql.append(" ORDER BY id");
List<CustomerRow> result = jdbc.query(
    sql.toString(),
    CUSTOMER_MAPPER,
    args.toArray());
```

Đúng contract nếu thêm từng `?` **cùng lúc** với thêm argument. Tuy nhiên, thêm/sắp xếp các điều kiện sau đó dễ làm `args` sai thứ tự nếu người viết không kiểm soát. Named parameters giúp loại bớt một nhóm lỗi, nhưng không tự hoàn thành validation/business semantics.

## 12. Named parameter không bind được tên bảng/cột hay cú pháp SQL

Cả `?` lẫn `:name` dùng để bind **giá trị**. Không thể giả định có thể truyền tên cột như một scalar:

```sql
-- SAI ý định: không làm ORDER BY theo cột do user chọn.
SELECT id, email FROM customers ORDER BY :sortColumn;
```

Tùy database, `:sortColumn` được xử lý như một giá trị hằng và **không trở thành SQL identifier**. Tương tự, placeholder không thay thế được table name, `ASC/DESC`, toán tử hoặc cả mệnh đề WHERE.

Khi cần dynamic sort, dùng **allowlist** ánh xạ lựa chọn của người dùng sang tên cột SQL do code kiểm soát:

```java
// Snippet trong repository; sortKey là input đã validate.
String orderBy = switch (sortKey) {
    case "email" -> "email";
    case "points" -> "points";
    default -> "id";
};

String sql = """
    SELECT id, email FROM customers
    WHERE status = :status
    ORDER BY
    """ + " " + orderBy + " ASC, id ASC";

return namedJdbc.query(
    sql,
    Map.of("status", status),
    CUSTOMER_MAPPER);
```

Ở đây `orderBy` chỉ nhận đúng ba literal SQL do lập trình viên định nghĩa; **không** được thay bằng raw `request.getParameter("sort")`. `id ASC` làm thứ tự ổn định khi nhiều hàng có cùng email/points; nếu sort là id, việc nhắc id thêm lần nữa có thể bỏ nhưng không thay đổi mục đích an toàn.

Trường hợp cần nhiều option, xây enum hoặc một map allowlist có giá trị bất biến. Không lấy tên cột từ client rồi bỏ qua kiểm tra.

## 13. Bảo vệ khỏi SQL injection: style nào an toàn?

**Cả hai an toàn khi dùng đúng prepared binding cho giá trị**, và cả hai không an toàn khi raw input được nối vào SQL.

Positional đúng:

```java
jdbc.queryForList(
    "SELECT id FROM customers WHERE email = ?",
    Long.class, userEmail);
```

Named đúng:

```java
namedJdbc.queryForList(
    "SELECT id FROM customers WHERE email = :email",
    Map.of("email", userEmail),
    Long.class);
```

Sai với cả hai:

```java
// SAI: nối raw input làm thay đổi cấu trúc SQL.
String sql = "SELECT id FROM customers WHERE email = '" +
    userEmail + "'";
jdbc.queryForList(sql, Long.class);
```

Không đánh giá an toàn dựa trên dấu `?` hoặc dấu `:` đơn thuần: phải nhìn **đường đi thực tế của dữ liệu không tin cậy**. `NamedParameterJdbcTemplate` không tự kiểm tra whitelist của dynamic table/column names, không tự escape ký tự wildcard `LIKE`, không validation domain input và không ngăn SQL logic bị viết sai.

### LIKE còn có wildcard semantics

`LIKE` với `%` và `_` cho phép matching đặc biệt. Bind tham số loại bỏ SQL injection, **nhưng không tự biến wildcard thành ký tự literal**.

Nếu yêu cầu “tên bắt đầu bằng chuỗi người dùng nhập như text literal”, có thể escape wildcard theo SQL dialect:

```java
// Sử dụng cú pháp ESCAPE '!' nếu database đích hỗ trợ.
String literal = userPrefix
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String pattern = literal + "%";

List<String> emails = namedJdbc.queryForList("""
        SELECT email FROM customers
        WHERE email LIKE :pattern ESCAPE '!'
        ORDER BY email
        """,
    Map.of("pattern", pattern),
    String.class);
```

Ở đây `!` là escape character theo SQL `ESCAPE`. Khi chuyển DB, test lại cách dùng escape, collation/case-sensitivity và semantics của các ký tự đặc biệt. Cần giới hạn độ dài input; một người dùng nhập `%` không nên vô tình yêu cầu scan toàn bảng nếu nghiệp vụ mong literal match.

## 14. SQL NULL và kiểu tham số: tên không thay type

Named binding không tự suy ra mọi SQL type từ `null`. Khi driver cần typed NULL, dùng `MapSqlParameterSource`:

```java
var params = new MapSqlParameterSource()
    .addValue("note", null, java.sql.Types.VARCHAR)
    .addValue("id", 2L, java.sql.Types.BIGINT);

namedJdbc.update("""
        UPDATE customers
        SET note = :note
        WHERE id = :id
        """, params);
```

Cùng ý nghĩa với positional khi dùng `SqlParameterValue`:

```java
jdbc.update("""
        UPDATE customers
        SET note = ?
        WHERE id = ?
        """,
    new SqlParameterValue(java.sql.Types.VARCHAR, null),
    new SqlParameterValue(java.sql.Types.BIGINT, 2L));
```

**Không** gộp “chọn named để dễ đọc” với “dùng typed NULL vì database cần type”: đây là **hai quyết định khác nhau**. Cả named và positional đều có cách cung cấp SQL type.

Một số lưu ý:
- `Map.of` không nhận null values; với typed null dùng `MapSqlParameterSource`.
- SQL `WHERE col = :maybeNull` vẫn không tìm các hàng SQL NULL khi parameter là null; SQL ba giá trị yêu cầu `IS NULL`/null-safe predicate theo dialect.
- `NULL` khác chuỗi `"null"` và số 0.
- `SqlParameterValue`/`java.sql.Types` không thay constraint `NOT NULL` hoặc validate giá trị.
- Nếu API PATCH cần phân biệt “không truyền field” với “truyền null để xóa”, hãy định nghĩa domain contract rõ; named binding không phân biệt hai trạng thái nếu cả hai đã trở thành một Java null.

## 15. Ví dụ Spring Boot + H2 + Java 17 hoàn chỉnh

Đây là demo có thể chạy trong một dự án nhỏ. Nó dùng một tập dữ liệu cố định, thực hiện truy vấn tương đương với **positional** và **named**, tái sử dụng named parameter, mở rộng `IN (:ids)`, bind NULL có kiểu, update theo JavaBean property và batch update.

### 15.1. Cấu trúc

```text
parameter-style-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jdbc/ParameterStyleDemoApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

`settings.gradle`:

```groovy
rootProject.name = 'parameter-style-demo'
```

`build.gradle` (Spring Boot 3.3.5, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:paramstyles;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    country_code VARCHAR(2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    tier VARCHAR(20) NOT NULL,
    note VARCHAR(200),
    points INTEGER NOT NULL
);
```

`src/main/resources/data.sql`:

```sql
INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (1, 'an@example.test', 'VN', 'ACTIVE', 'GOLD', NULL, 10);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (2, 'binh@example.test', 'VN', 'ACTIVE', 'SILVER', 'old', 20);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (3, 'chi@example.test', 'US', 'SUSPENDED', 'GOLD', NULL, 30);

INSERT INTO customers (id, email, country_code, status, tier, note, points)
VALUES (4, 'dung@example.test', 'VN', 'ACTIVE', 'GOLD', NULL, 40);
```

`src/main/java/example/jdbc/ParameterStyleDemoApplication.java`:

```java
package example.jdbc;

import java.sql.Types;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.BeanPropertySqlParameterSource;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;

@SpringBootApplication
public class ParameterStyleDemoApplication {

    public record CustomerRow(long id, String email) {}

    private static final RowMapper<CustomerRow> CUSTOMER_MAPPER =
        (rs, rowNum) -> new CustomerRow(
            rs.getLong("id"), rs.getString("email"));

    public static void main(String[] args) {
        SpringApplication.run(ParameterStyleDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner compare(
            JdbcTemplate jdbc,
            NamedParameterJdbcTemplate namedJdbc) {

        return args -> {
            // 1) Hai phong cách, cùng filter và cùng thứ tự kết quả.
            List<CustomerRow> positional = jdbc.query("""
                    SELECT id, email
                    FROM customers
                    WHERE status = ? AND country_code = ?
                    ORDER BY id
                    """,
                CUSTOMER_MAPPER, "ACTIVE", "VN");

            List<CustomerRow> named = namedJdbc.query("""
                    SELECT id, email
                    FROM customers
                    WHERE status = :status AND country_code = :country
                    ORDER BY id
                    """,
                Map.of("country", "VN", "status", "ACTIVE"),
                CUSTOMER_MAPPER);

            System.out.println(
                "same=" + positional.equals(named));
            System.out.println("ids=" +
                named.stream().map(CustomerRow::id).toList());

            // 2) :threshold xuất hiện hai lần nhưng chỉ bind một lần.
            Long repeated = namedJdbc.queryForObject("""
                    SELECT COUNT(*)
                    FROM customers
                    WHERE points >= :threshold
                      AND (points - :threshold) <= :maxGap
                    """,
                Map.of("threshold", 20, "maxGap", 20),
                Long.class);
            System.out.println("repeatedCount=" + repeated);

            // 3) List được mở rộng thành IN (?, ?).
            List<Long> chosen = namedJdbc.query("""
                    SELECT id
                    FROM customers
                    WHERE id IN (:ids)
                    ORDER BY id
                    """,
                new MapSqlParameterSource(
                    "ids", List.of(1L, 4L)),
                (rs, rowNum) -> rs.getLong("id"));
            System.out.println("chosen=" + chosen);

            // 4) SQL NULL được bind cùng type.
            var nullable = new MapSqlParameterSource()
                .addValue("note", null, Types.VARCHAR)
                .addValue("id", 2L, Types.BIGINT);

            int noteUpdated = namedJdbc.update("""
                    UPDATE customers
                    SET note = :note
                    WHERE id = :id
                    """, nullable);
            System.out.println(
                "noteUpdated=" + noteUpdated);

            String note = jdbc.queryForObject(
                "SELECT note FROM customers WHERE id = ?",
                String.class, 2L);
            System.out.println("noteIsNull=" + (note == null));

            // 5) BeanPropertySqlParameterSource đọc getter.
            var change = new PointChange(
                "binh@example.test", 25);
            int pointUpdated = namedJdbc.update("""
                    UPDATE customers
                    SET points = :points
                    WHERE email = :email
                    """,
                new BeanPropertySqlParameterSource(change));
            System.out.println(
                "pointUpdated=" + pointUpdated);

            Integer points = jdbc.queryForObject(
                "SELECT points FROM customers WHERE id = ?",
                Integer.class, 2L);
            System.out.println("points=" + points);

            // 6) Batch update: một parameter source cho mỗi bản ghi.
            SqlParameterSource[] batch = {
                new MapSqlParameterSource("id", 1L)
                    .addValue("tier", "PLATINUM"),
                new MapSqlParameterSource("id", 4L)
                    .addValue("tier", "PLATINUM")
            };

            int[] updates = namedJdbc.batchUpdate("""
                    UPDATE customers
                    SET tier = :tier
                    WHERE id = :id
                    """, batch);
            System.out.println(
                "batch=" + Arrays.toString(updates));
        };
    }

    public static final class PointChange {
        private final String email;
        private final int points;

        public PointChange(String email, int points) {
            this.email = email;
            this.points = points;
        }

        public String getEmail() {
            return email;
        }

        public int getPoints() {
            return points;
        }
    }
}
```

**Chạy:** ở thư mục `parameter-style-demo`, dùng Java 17 và Gradle 8.x tương thích Spring Boot plugin:

```bash
gradle bootRun
```

Nếu dự án đã có Gradle Wrapper, chạy `./gradlew bootRun` (Unix/macOS) hoặc `gradlew.bat bootRun` (Windows).

Các dòng do `System.out.println` của ứng dụng tạo theo đúng thứ tự dưới đây; console còn có thể có log build và Spring startup:

```text
same=true
ids=[1, 2, 4]
repeatedCount=3
chosen=[1, 4]
noteUpdated=1
noteIsNull=true
pointUpdated=1
points=25
batch=[1, 1]
```

**Giải thích từng dòng:**
- Ba khách hàng VN/ACTIVE là ID 1, 2, 4. Query positional và named cho cùng 3 record bằng `record.equals()` nên `same=true`.
- `:threshold=20` khớp points 20, 30, 40 khi hiệu số so với 20 không vượt 20; có 3 row.
- `IN (:ids)` với 1 và 4 trả `[1,4]` theo `ORDER BY id`.
- Update note của ID 2 tác động một hàng và note sau đó là SQL NULL, query scalar trả Java null.
- JavaBean `PointChange` cung cấp property `email`/`points`, update ID 2 thành points 25.
- Batch update tier của hai ID hợp lệ trả update counts `[1, 1]` trên H2.

Đây là ví dụ **có thể chạy trong project Spring Boot**, không phải file Java có thể biên dịch bằng `javac` độc lập vì cần các Spring libraries. Thí nghiệm trên H2 nhằm kiểm chứng ý nghĩa SQL; trên DB thực tế cần test thêm type/concurrency/optimizer.

### Vì sao demo không chỉ dùng NamedParameterJdbcTemplate?

Mục tiêu là **so sánh**. Nếu chỉ trình bày named parameters, người học khó nhận ra điều gì thực sự thay đổi (mapping tên) và điều gì không thay đổi (prepared binding, transaction, SQL result). Demo kiểm tra cùng dữ liệu, cùng thứ tự và same semantics trước khi thêm tình huống mà named syntax có lợi.

## 16. JdbcClient: chọn named hoặc positional trong cùng API fluent

Với Spring Framework 6.1+, `org.springframework.jdbc.core.simple.JdbcClient` thống nhất cách gọi hai phong cách:

```java
// Method trong class có field JdbcClient client.
Long byPosition = client
    .sql("SELECT COUNT(*) FROM customers WHERE status = ?")
    .param("ACTIVE")
    .query(Long.class)
    .single();

Long byName = client
    .sql("SELECT COUNT(*) FROM customers WHERE status = :status")
    .param("status", "ACTIVE")
    .query(Long.class)
    .single();
```

**Cả hai đếm khách hàng ACTIVE**; `query(Long.class).single()` yêu cầu đúng một hàng (COUNT không GROUP BY cho một hàng). `JdbcClient` là façade phía trên `JdbcTemplate`/`NamedParameterJdbcTemplate`, không tạo thành một JDBC driver mới.

Hãy phân biệt:
- `.param(value)`: bind positional theo thứ tự đăng ký (trừ overload index nếu sử dụng).
- `.param("name", value)`: bind theo tên.
- `.query(...).single()`: xử lý số hàng theo contract riêng.
- `.query(...).optional()`: thể hiện 0..1 khi cần.
- `.query(...).list()`: danh sách 0..N.

Không trộn `?` và `:name` trong cùng một câu SQL/query execution chỉ để “đỡ phải đổi hết”; chọn một style rõ ràng cho **mỗi statement**. Lưu ý `JdbcClient` có thêm API theo phiên bản Spring 7.x; khi dùng Spring 6.x, hãy dựa vào Javadoc đúng phiên bản của dự án.

## 17. Batch updates và số lượng parameter lớn

Khi cập nhật nhiều hàng theo cùng SQL, named parameters phù hợp với từng command object:

```java
SqlParameterSource[] rows = {
    new MapSqlParameterSource()
        .addValue("id", 1L)
        .addValue("tier", "GOLD"),
    new MapSqlParameterSource()
        .addValue("id", 4L)
        .addValue("tier", "GOLD")
};

int[] changed = namedJdbc.batchUpdate("""
        UPDATE customers
        SET tier = :tier
        WHERE id = :id
        """, rows);
```

Một `SqlParameterSource` ứng với một lần bind statement trong batch. Thứ tự mảng nguồn xác định thứ tự `changed[]`, còn tên placeholder xác định cột trong từng lần chạy. Kết quả batch là `int[]` JDBC update counts; tùy driver có thể có giá trị đặc biệt như `Statement.SUCCESS_NO_INFO`, nên đừng mặc định mọi driver luôn trả đúng số hàng.

Với positional batch, `JdbcTemplate.batchUpdate` và `BatchPreparedStatementSetter` cũng hợp lệ. Khi batch có rất ít cột và tài liệu hóa rõ index, positional có thể đơn giản hơn. Khi batch có nhiều field nullable/same type hoặc thay đổi schema, named batch có thể dễ review hơn.

**Không chạy một update 50.000 hàng chỉ vì named params làm code ngắn:** phải cân nhắc batch size, DB limits, locks, transaction duration và kiểm thử throughput/rollback. Cú pháp tham số không thay thế chiến lược xử lý dữ liệu.

## 18. Lỗi thường gặp với named parameters

### 18.1. Sai tên hoặc thiếu giá trị

```java
// SQL yêu cầu :country nhưng map chỉ có "countryCode".
namedJdbc.queryForList("""
        SELECT id FROM customers
        WHERE country_code = :country
        """,
    Map.of("countryCode", "VN"),
    Long.class);
```

Spring không thể tìm tham số tên `country` trong source; sẽ phát sinh lỗi binding trước/ở lúc thực thi. **Sửa bằng tên khớp chính xác**. Đặt tên nhất quán theo camelCase hoặc snake_case trong cùng module và test mọi nhánh SQL động.

### 18.2. SQL có ':' trong cú pháp/literal đặc thù

Một số DB như PostgreSQL dùng `::type` cho cast, ngoài ra SQL có colon trong chuỗi, comment, operator hoặc vendor-specific expression. Spring có parser SQL named parameters; đừng tự thay chuỗi bằng `sql.replace(":id", "?")`, vì có thể làm hỏng `::`, literal hoặc tên có tiền tố giống nhau.

Khi cần portability hoặc gặp xung đột parser/dialect, dùng SQL chuẩn `CAST(:value AS INTEGER)` hay cách tương đương được hỗ trợ và integration test. Không mặc định mọi DB dùng cùng cast syntax.

### 18.3. Tự đặt tên tham số trùng với keyword/điều kiện không rõ nghĩa

`:from`, `:to` có thể hợp lệ trong nhiều ngữ cảnh nhưng khó review; tên như `:startInclusive`, `:endExclusive` rõ hơn. Không đặt named parameter theo tên kiểu dữ liệu nếu nghiệp vụ cần tên có ý nghĩa, ví dụ `:string1`, `:long2`.

### 18.4. Nhầm Map entry order với bind order

Dùng named parameters không yêu cầu `Map` được sắp xếp theo thứ tự placeholder. Nếu code cố ép `LinkedHashMap` để “cho đúng thứ tự SQL”, đó thường là dấu hiệu đang lẫn lộn hai cơ chế.

### 18.5. Truyền map chứa một cấu trúc phức tạp mà SQL không hiểu

Named binding là binding **JDBC values**, không serialize mọi POJO thành JSON/SQL tuple một cách tự động. Với JSON/UUID/array/enum/LOB, driver có thể cần `SqlParameterSource` type metadata, cast hoặc object vendor-specific. `IN (:ids)` dùng collection expansion là trường hợp được Spring hỗ trợ cụ thể; không tự giả định collection bất kỳ cũng hợp lệ với mọi toán tử.

### 18.6. Không xử lý tập IN rỗng hoặc cực lớn

List rỗng phải có business outcome rõ; list quá lớn cần giải pháp DB-specific/batch. Named parameters không bảo đảm không vượt SQL bind limit.

### 18.7. Tin rằng named params ngăn sai kết quả do domain logic

`WHERE created_at > :endDate` và `:startDate` đặt nhầm tên vẫn có thể trả kết quả sai. Test phải kiểm tra input–output và điều kiện biên, không chỉ test câu SQL không ném lỗi.

## 19. Lỗi thường gặp với positional parameters

### 19.1. Quên đổi thứ tự khi refactor WHERE

Cả `status` và `country` đều là String, compiler không biết ý nghĩa. Khi thay SQL order, cập nhật argument order cùng lúc và dùng test nhiều fixture để phát hiện.

### 19.2. Đếm nhầm placeholder

Một query chứa 8 dấu `?` nhưng chỉ 7 args sẽ ném lỗi bind; 8 args nhưng gán nhầm ý nghĩa có thể không báo lỗi. Hãy gom `Object[] args` gần query, tránh xây mảng ở một nơi rất xa SQL.

### 19.3. Nhầm index JDBC và Java

`PreparedStatement.setString(1, value)` bắt đầu từ **1**, còn `args[0]` trong Java bắt đầu từ **0**. Nếu viết setter thủ công, đừng gọi `setString(0, value)`.

### 19.4. Thêm điều kiện SQL động nhưng quên thêm value

Khi xây `StringBuilder` và `List<Object>`, hãy thêm `?` và add arg trong cùng nhánh if, tránh hai khối code tách xa nhau. Dùng named parameters khi phức tạp đủ lớn.

### 19.5. Bỏ placeholder, nối input vào SQL

Đổi từ positional sang named không sửa được lỗi nếu chuỗi đã chứa raw input trước khi template nhận. Hãy làm sạch đường đi dữ liệu: SQL là template cố định/allowlisted, giá trị luôn được bind.

## 20. Quy tắc bảo trì khi sửa một truy vấn đang chạy

Giả sử một repository đang dùng positional và bạn muốn thêm `country`:
1. **Viết contract trước:** chức năng query, các điều kiện có bắt buộc không, null/empty nghĩa gì, thứ tự output có cố định không.
2. **Kiểm tra schema:** index, unique constraints, nullable fields và kiểu JDBC.
3. **Chọn style:** nếu chỉ thêm một parameter và query vẫn ngắn, giữ positional là hợp lý; nếu SQL đã dài/same-type, cân nhắc chuyển cả statement sang named.
4. **Đổi SQL và binding trong cùng diff:** đảm bảo tất cả placeholder đều được cấp giá trị đúng.
5. **Dùng test với dữ liệu phân biệt:** ví dụ status/country có giá trị khiến hoán đổi String trả kết quả khác rõ ràng.
6. **Kiểm thử 0/1/N kết quả:** đặc biệt queryForObject vs query List, SQL NULL, duplicate, constraints.
7. **Kiểm tra transaction & update count:** thay style không đổi transaction semantics; kết quả 0 rows updated cần contract xử lý.
8. **Theo dõi query plan nếu query shape đổi:** đổi placeholder style đơn thuần thường không làm đổi SQL logic, nhưng thêm filter, IN list hay cast có thể đổi plan.
9. **Không đổi tất cả repository cùng lúc không có mục đích:** tránh diff lớn khó review và khó rollback.

**Kiểm tra quan trọng khi code review:** hãy đặt SQL và các binding ngay gần nhau. Với named SQL, so `:name` với key/bean property. Với positional, đánh số `?1`, `?2` trong đầu và so thứ tự args. Các test query dùng fixture đối nghịch để phát hiện giá trị bị swap.

## 21. Kiểm thử query equivalence và sự an toàn của binding

### 21.1. Ma trận test nên có

| Tình huống | Test cần chứng minh |
|---|---|
| 1–2 tham số positional | Lấy đúng hàng từ DB với giá trị biết trước |
| 2 tham số cùng kiểu bị hoán vị | Test phải thất bại khi args đổi order |
| Truy vấn named đổi thứ tự điều kiện | Kết quả không đổi nếu names/values đúng |
| Named parameter lặp | Cả hai vị trí dùng cùng một giá trị |
| Thiếu named value | Báo lỗi; không tự bind null im lặng |
| Typed nullable field | Lưu/đọc lại SQL NULL đúng nghĩa |
| `IN (:ids)` có 2–3 phần tử | Trả đúng IDs và thứ tự |
| `IN (:ids)` rỗng | Trả kết quả theo contract đã chọn, không sinh SQL tùy tiện |
| List chứa input ngoài phạm vi cho phép | Có validation/limit phù hợp |
| LIKE có `%`/`_` literal | Escape đúng semantics nếu yêu cầu tìm literal |
| Dynamic sort | Chỉ chấp nhận các cột từ allowlist |
| Query cập nhật không có row | Update count 0 được xử lý đúng |
| SQL lỗi/DB mất kết nối | `DataAccessException` được truyền, không biến thành list rỗng |
| Batch update nhiều hàng | Mỗi entry nhận đúng mapping values; readback xác nhận dữ liệu |

### 21.2. Test tích hợp Spring Boot/H2

Ví dụ trong project có `spring-boot-starter-test` và `@JdbcTest`, schema/data fixture của phần 15 đã được khởi tạo:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
```

```java
// NamedVsPositionalTest.java (class test đầy đủ trong dự án phù hợp)
package example.jdbc;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@JdbcTest
class NamedVsPositionalTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired NamedParameterJdbcTemplate namedJdbc;

    @Test
    void equivalentBindingsReturnTheSameIds() {
        List<Long> positional = jdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = ? AND country_code = ?
                ORDER BY id
                """, Long.class, "ACTIVE", "VN");

        List<Long> named = namedJdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = :status AND country_code = :country
                ORDER BY id
                """,
            Map.of("status", "ACTIVE", "country", "VN"),
            Long.class);

        assertThat(positional).containsExactly(1L, 2L, 4L);
        assertThat(named).isEqualTo(positional);
    }

    @Test
    void swappedPositionalArgumentsChangeTheMeaning() {
        List<Long> swapped = jdbc.queryForList("""
                SELECT id FROM customers
                WHERE status = ? AND country_code = ?
                ORDER BY id
                """, Long.class, "VN", "ACTIVE");

        assertThat(swapped).isEmpty();
    }
}
```

Test này chỉ chạy khi đã có dependencies, JDBC slice configuration, schema/data và datasource phù hợp. Nó **không** là chương trình `javac` độc lập. `@JdbcTest` thường tạo transaction test và rollback khi kết thúc; để kiểm chứng update/commit xuyên request hãy thiết kế integration test không bị transaction test che hành vi.

Test với H2 đủ cho lỗi hoán đổi args và behavior cơ bản; khi dùng PostgreSQL, MySQL hoặc Oracle trong production, nên thêm Testcontainers/integration suite đúng dialect cho `IN` lớn, JSON, timezone, locks và query planner.

### 21.3. Không chỉ mock NamedParameterJdbcTemplate

Mock kiểm tra SQL string và Map có key đúng nhưng không chứng minh database trả đúng row; ít nhất những query quan trọng nên có test thực thi. Tránh test cứng vào thứ tự lặp của `Map.of`: named binding theo **key**, không theo iteration order.

## 22. Tình huống phức tạp: SQL type, trạng thái không xác định và dữ liệu lớn

Khi ứng dụng có nhiều trạng thái:
- **Missing field vs SQL NULL:** dùng input contract phân biệt absent/present-null/value; named parameter value null không tự thể hiện “field chưa được gửi”.
- **Lỗi không có row:** `queryForObject()` kỳ vọng đúng một row; nếu 0 row sẽ ném `EmptyResultDataAccessException` bất kể placeholder là named hay positional.
- **Nhiều row:** `queryForObject()` cũng có thể ném `IncorrectResultSizeDataAccessException`. Named binding không biến query nhiều hàng thành một hàng.
- **Lỗi driver:** JDBC type mismatch, SQL syntax error, connection outage được dịch sang `DataAccessException` theo Spring translator; không trả `Optional.empty()` chỉ vì đã dùng named parameters.
- **Streaming:** `queryForStream` trả stream có vòng đời riêng, caller phải đóng; lựa chọn named/positional không miễn tài nguyên này.
- **Transaction:** `@Transactional` và transaction manager điều phối connection/commit/rollback. Thay style placeholder không thay đổi transaction boundary.
- **Large IN:** nếu số IDs hàng chục nghìn, cân nhắc staging table, bulk strategy hoặc database-specific array; không vì cú pháp `IN (:ids)` đẹp mà bỏ qua DB bind constraints.

## 23. Các câu hỏi tự kiểm tra

**Câu 1.** Một query có một placeholder `?` trong `WHERE id = ?`, có bắt buộc dùng named parameter để dễ bảo trì không?

Không. Positional thường đủ vì thứ tự và ý nghĩa đã rõ. Tính nhất quán của codebase và test vẫn quan trọng.

**Câu 2.** Với `WHERE country_code = :country AND status = :status`, đổi thứ tự các entry trong `Map.of` có làm đổi kết quả không?

Không, nếu hai key/value khớp đúng tên. Spring lấy theo tên và chuyển sang thứ tự JDBC phù hợp SQL.

**Câu 3.** `:threshold` xuất hiện hai lần thì phải tạo hai key giống nhau trong Map không?

Không. Định nghĩa một key `threshold`; Spring bind cùng value cho mọi vị trí tham số có tên tương ứng.

**Câu 4.** `IN (:ids)` với `List.of()` có luôn được hỗ trợ không?

Không thể coi `IN ()` portable. Xử lý trường hợp rỗng ở application theo contract trước khi gọi query.

**Câu 5.** Named parameters có cho phép `ORDER BY :userColumn` trở thành cột từ request không?

Không. Placeholder bind **giá trị**, không bind identifier. Dùng allowlist SQL fragments cho tên cột.

**Câu 6.** Dùng named parameter có cần `@Transactional` không?

Không bắt buộc cho truy vấn đọc đơn. Transaction được quyết định bởi nghiệp vụ và consistency, độc lập với style binding.

**Câu 7.** `Map.of("note", null)` có phải cách hợp lệ để gửi SQL NULL không?

Không. `Map.of` tự ném NPE vì giá trị null. Dùng `MapSqlParameterSource` với `addValue("note", null, Types.VARCHAR)` nếu cần typed null.

**Câu 8.** Thay SQL từ `status = ? AND country = ?` thành `country = ? AND status = ?` có cần đổi args không?

Có, nếu vẫn dùng positional. Nếu quên, chương trình có thể chạy nhưng truy vấn sai. Với named binding, mapping theo key giảm rủi ro này.

**Câu 9.** Dùng named parameters có luôn tối ưu hơn về hiệu năng không?

Không. Spring xử lý tên rồi delegate vào JDBC binding. Cần đo trên workload/driver/DB thực để kết luận.

**Câu 10.** Khi SQL query sai tên cột, liệu named params biến lỗi thành `Optional.empty()` không?

Không. Lỗi SQL/DB vẫn là lỗi truy cập dữ liệu; kiểu trả về là kết quả của API truy vấn và domain contract, không phải tên placeholder.

## 24. Checklist chọn và duy trì style

- [ ] Mỗi SQL statement dùng **một phong cách binding nhất quán**: `?` hoặc `:name`.
- [ ] Query 1–2 tham số ngắn không bị ép đổi sang named nếu không có lợi ích.
- [ ] Query dài/nhiều tham số cùng kiểu hoặc lặp giá trị đã cân nhắc named.
- [ ] SQL và binding values được đặt gần nhau, dễ review cùng diff.
- [ ] Positional args theo đúng **thứ tự dấu ?**; có test bắt lỗi hoán đổi.
- [ ] Named params khớp tên với `MapSqlParameterSource`/`Map`/JavaBean properties.
- [ ] Tên tham số giàu ý nghĩa (`:country`, `:threshold`), không đặt theo thứ tự (`:p1`, `:p2`).
- [ ] Giá trị người dùng luôn được bind, không nối vào SQL literal.
- [ ] Identifier/sort direction/dynamic SQL fragment chỉ đến từ allowlist.
- [ ] Không dùng `Map.of` cho null, biết typed NULL khi driver cần.
- [ ] `IN (:ids)` có xử lý list rỗng, giới hạn kích thước và test driver.
- [ ] Dynamic filters xác định rõ absent/null/value semantics và thứ tự kết quả.
- [ ] SQL LIKE escape wildcard đúng khi cần literal matching.
- [ ] Một thay đổi SQL bảo đảm không thay đổi contract số hàng/transaction ngầm.
- [ ] Có integration test cả happy path, sai binding, input đặc biệt và lỗi DB.
- [ ] Không đổi hàng loạt style chỉ vì sở thích nếu code hiện tại đã rõ.

## 25. Kết luận

**Cách chọn tham số theo tên hay vị trí là một quyết định thiết kế để giảm lỗi bảo trì, không phải chọn hai hệ JDBC khác nhau.** `JdbcTemplate` với `?` ngắn gọn, phù hợp những query ít tham số và ổn định. `NamedParameterJdbcTemplate` với `:name` rõ nghĩa khi SQL phức tạp, có nhiều giá trị cùng kiểu, tham số lặp hoặc `IN` list; Spring chuyển chúng sang placeholder JDBC trước khi thực thi.

Ưu tiên **đọc được, kiểm thử được và giữ đúng semantics** hơn việc áp đặt một style duy nhất. Dù chọn cách nào, hãy tiếp tục bind values thay vì nối SQL, kiểm soát SQL fragments động, xử lý NULL/empty collection rõ ràng và phân biệt lỗi truy vấn với kết quả không có dữ liệu. Đây là nền tảng cho tầng truy cập dữ liệu Spring dễ mở rộng mà không gây lỗi âm thầm khi query thay đổi.

## Tài liệu chính thức

- Spring Framework — Using JdbcTemplate and NamedParameterJdbcTemplate, ví dụ binding theo tên: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Choosing an Approach for JDBC Database Access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html
- Spring Framework 6.1 — NamedParameterJdbcTemplate API, mở rộng List và delegate sang JdbcTemplate: https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework — SQL type information, SqlParameterSource và typed NULL: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework — JdbcClient unified facade (Spring 6.1+): https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
