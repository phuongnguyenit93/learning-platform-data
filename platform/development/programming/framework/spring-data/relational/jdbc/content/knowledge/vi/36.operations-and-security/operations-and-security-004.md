# Bind tham số để phòng SQL injection và kiểm soát SQL động

Spring Data JDBC và Spring JDBC cho phép truyền giá trị vào câu SQL bằng bind parameter. Khi dùng đúng cách, driver gửi câu lệnh và dữ liệu theo hai phần riêng, giúp database hiểu đầu vào là **value** thay vì một phần cú pháp SQL. Đây là biện pháp cơ bản để ngăn SQL injection.

Tuy nhiên, bind parameter chỉ dùng cho giá trị như ID, email, trạng thái, ngày tháng hoặc số tiền. Nó không thể thay thế tên bảng, tên cột, toán tử, từ khóa ORDER BY hay hướng ASC/DESC. Những phần SQL động đó phải được tạo từ danh sách lựa chọn cố định và được kiểm tra trước khi đưa vào câu lệnh.

Bài này trình bày cách bind tham số với repository query, JdbcTemplate và NamedParameterJdbcTemplate; cách xây dựng bộ lọc, sort và phân trang động; cùng các lỗi cần tránh khi xử lý LIKE, NULL và danh sách IN.

## 1. SQL injection xảy ra như thế nào?

SQL injection xảy ra khi dữ liệu đầu vào không tin cậy được ghép trực tiếp vào chuỗi SQL và database diễn giải một phần dữ liệu đó thành cú pháp.

Ví dụ tìm khách hàng bằng email:

~~~java
String sql =
        "SELECT id, email FROM customers WHERE email = '"
        + email
        + "'";

Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Nếu email là giá trị bình thường, câu SQL có thể chạy đúng. Nhưng nếu đầu vào chứa một đoạn như:

~~~text
' OR '1'='1' --
~~~

chuỗi SQL sau khi ghép có thể thay đổi điều kiện WHERE. Kẻ tấn công có thể làm truy vấn trả nhiều hàng hơn dự kiến hoặc thay đổi ý nghĩa câu lệnh.

Vấn đề nằm ở việc ứng dụng đã trộn dữ liệu với cú pháp SQL trước khi database phân tích câu lệnh.

## 2. Dùng PreparedStatement và bind parameter

Với JDBC, hãy viết câu SQL có placeholder rồi bind dữ liệu qua PreparedStatement:

~~~java
String sql =
        "SELECT id, email FROM customers WHERE email = ?";

try (PreparedStatement statement =
             connection.prepareStatement(sql)) {

    statement.setString(1, email);

    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

Database nhận cấu trúc câu lệnh với một placeholder. Giá trị email được gửi riêng qua JDBC parameter API. Nếu email chứa dấu nháy hoặc chuỗi giống cú pháp SQL, nó vẫn được xử lý như dữ liệu của parameter.

Các lợi ích:

- Không phải tự escape dấu nháy trong value.
- Không ghép dữ liệu người dùng vào câu SQL.
- Driver có thể bind đúng JDBC type.
- Câu SQL và giá trị được tách rõ ràng.
- Có thể tái sử dụng cùng statement shape với nhiều giá trị khác nhau.

Không tự thêm dấu nháy quanh placeholder. Viết WHERE email = ? thay vì WHERE email = '?'. Driver sẽ chịu trách nhiệm biểu diễn giá trị theo giao thức JDBC.

## 3. Spring Data JDBC repository query tự bind value

Với derived query, Spring Data JDBC tạo câu SQL từ tên method và bind các tham số:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndActive(
            String status,
            boolean active
    );
}
~~~

Các giá trị email, status và active được truyền qua cơ chế parameter binding của repository infrastructure. Không cần nối chuỗi SQL.

Với @Query, viết SQL cố định và dùng named parameter:

~~~java
import org.springframework.data.jdbc.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Query("""
        SELECT id, display_name, email, status
        FROM customers
        WHERE email = :email
        """)
    Optional<Customer> findCustomerByEmail(
            @Param("email") String email
    );
}
~~~

Tên parameter :email được ánh xạ với method argument có @Param("email"). Giá trị được bind, không được nối vào SQL.

Có thể dùng @Query cho DML theo nhu cầu:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

@Modifying cho biết query thực hiện thao tác thay đổi dữ liệu. Nó không phải cơ chế chống injection riêng; việc bảo vệ value đến từ parameter binding.

Không viết SQL bằng cách ghép argument vào annotation hoặc tạo query string từ dữ liệu request.

## 4. Bind tham số với JdbcTemplate

JdbcTemplate dùng PreparedStatement ở phía dưới. Truyền value qua placeholder:

~~~java
String sql = """
    SELECT id, display_name, email
    FROM customers
    WHERE email = ?
    """;

List<CustomerSummary> customers = jdbcTemplate.query(
        sql,
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        ),
        email
);
~~~

Nếu cần kiểm soát cách bind, có thể dùng PreparedStatementSetter:

~~~java
List<CustomerSummary> customers = jdbcTemplate.query(
        sql,
        ps -> ps.setString(1, email),
        (rs, rowNum) -> new CustomerSummary(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("email")
        )
);
~~~

Với update:

~~~java
int affected = jdbcTemplate.update(
        "UPDATE customers SET status = ? WHERE id = ?",
        status,
        customerId
);
~~~

Không ghép customerId hoặc status vào SQL string. Kể cả ID là số nguyên, vẫn nên bind bằng parameter để giữ một quy tắc nhất quán và tránh lỗi khi kiểu dữ liệu thay đổi.

## 5. Dùng NamedParameterJdbcTemplate cho query nhiều tham số

Khi có nhiều điều kiện, positional placeholder có thể khó đọc vì phải nhớ thứ tự. NamedParameterJdbcTemplate cho phép đặt tên parameter:

~~~java
String sql = """
    SELECT id, display_name, status
    FROM customers
    WHERE status = :status
      AND created_at >= :fromTime
      AND created_at < :toTime
    """;

var parameters = new MapSqlParameterSource()
        .addValue("status", status)
        .addValue("fromTime", fromTime)
        .addValue("toTime", toTime);

List<CustomerSummary> result =
        namedParameterJdbcTemplate.query(
                sql,
                parameters,
                customerSummaryRowMapper
        );
~~~

Named parameter giúp:

- Nhìn thấy rõ mỗi value gắn với điều kiện nào.
- Thêm hoặc sắp xếp lại điều kiện mà không phải đếm vị trí dấu hỏi.
- Bind kiểu dữ liệu qua API Spring JDBC.
- Truyền collection cho một số dạng IN clause.

Tên parameter vẫn là một phần của SQL template do lập trình viên viết. Giá trị truyền vào được bind riêng.

## 6. Bind value không thể thay tên bảng hoặc tên cột

Một hiểu nhầm phổ biến là dùng placeholder cho identifier:

~~~sql
SELECT * FROM ? WHERE id = ?
~~~

Placeholder đầu tiên không thể đại diện tên bảng. PreparedStatement bind value, không thay thế cấu trúc SQL như table name, column name, operator hoặc keyword.

Tương tự, câu lệnh:

~~~sql
SELECT id, name
FROM customers
ORDER BY ?
~~~

không có nghĩa là database sẽ sort theo tên cột được truyền. Parameter ở vị trí đó là một giá trị biểu thức, không phải identifier SQL.

Nếu người dùng được chọn cột sort, hãy ánh xạ lựa chọn sang một trong các identifier đã được định nghĩa trong code. Không nối trực tiếp chuỗi gửi từ client.

## 7. Whitelist cho dynamic ORDER BY

Ví dụ API cho phép sort theo ngày tạo, tên khách hàng hoặc tổng tiền.

Tạo enum biểu diễn các lựa chọn hợp lệ:

~~~java
public enum CustomerSortField {
    CREATED_AT,
    NAME,
    TOTAL
}
~~~

Chuyển enum thành identifier SQL bằng switch cố định:

~~~java
private String columnFor(CustomerSortField field) {
    return switch (field) {
        case CREATED_AT -> "created_at";
        case NAME -> "display_name";
        case TOTAL -> "total";
    };
}
~~~

Validate direction:

~~~java
private String directionFor(String direction) {
    if ("asc".equalsIgnoreCase(direction)) {
        return "ASC";
    }
    if ("desc".equalsIgnoreCase(direction)) {
        return "DESC";
    }
    throw new IllegalArgumentException("Unsupported sort direction");
}
~~~

Sau khi validate, có thể tạo phần ORDER BY từ các hằng số nội bộ:

~~~java
String sql = """
    SELECT id, display_name, total, created_at
    FROM customers
    ORDER BY
    """ + columnFor(sortField) + " " + directionFor(direction)
    + " LIMIT :limit OFFSET :offset";
~~~

Trong ví dụ, chỉ các chuỗi do switch và hàm validation trả về mới được ghép vào SQL. Không có giá trị identifier tùy ý từ request đi thẳng vào câu lệnh.

Tốt hơn nữa, API có thể nhận enum trực tiếp thay vì String. Khi parse request, từ chối giá trị ngoài tập cho phép trước khi gọi persistence layer.

## 8. Sort bằng Spring Data Sort

Khi dùng repository hoặc JdbcAggregateTemplate, có thể sử dụng Sort để biểu diễn thứ tự:

~~~java
Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Iterable<Customer> customers = repository.findAll(sort);
~~~

Nếu sort field đến từ query parameter, không truyền thẳng một chuỗi tùy ý. Ánh xạ lựa chọn client sang domain property được phép:

~~~java
private String allowedProperty(String requested) {
    return switch (requested) {
        case "name" -> "name";
        case "created" -> "createdAt";
        case "total" -> "total";
        default -> throw new IllegalArgumentException(
                "Unsupported sort field");
    };
}
~~~

Sau đó:

~~~java
Sort sort = Sort.by(
        Sort.Direction.DESC,
        allowedProperty(requestedSort)
);
~~~

Spring Data xử lý mapping property sang cột theo metadata. Whitelist vẫn cần thiết để giới hạn khả năng truy vấn và tránh sort theo property không được công bố.

## 9. Dynamic WHERE an toàn

Có thể tạo bộ lọc tùy chọn bằng các đoạn SQL cố định và parameter riêng. Ví dụ:

~~~java
StringBuilder sql = new StringBuilder("""
    SELECT id, display_name, status
    FROM customers
    WHERE 1 = 1
    """);

MapSqlParameterSource params = new MapSqlParameterSource();

if (status != null) {
    sql.append(" AND status = :status");
    params.addValue("status", status);
}

if (createdFrom != null) {
    sql.append(" AND created_at >= :createdFrom");
    params.addValue("createdFrom", createdFrom);
}

if (createdTo != null) {
    sql.append(" AND created_at < :createdTo");
    params.addValue("createdTo", createdTo);
}

List<CustomerSummary> result =
        namedParameterJdbcTemplate.query(
                sql.toString(),
                params,
                customerSummaryRowMapper
        );
~~~

Các fragment được append đều là literal do code kiểm soát. Các giá trị từ request chỉ được thêm vào MapSqlParameterSource.

Quy tắc:

- SQL fragment phải đến từ code hoặc whitelist.
- Value phải được bind bằng parameter.
- Không append trực tiếp chuỗi người dùng vào WHERE.
- Không để client gửi một đoạn SQL như filter expression.
- Giới hạn số bộ lọc và xác định rõ cách kết hợp AND/OR.

Với truy vấn phức tạp, hãy tạo một query object hoặc specification để validate đầu vào trước khi build SQL.

## 10. Dynamic filter trong MyBatis

Nếu ứng dụng đồng thời dùng MyBatis, các phần tử dynamic SQL như if, choose, where, set và foreach giúp tạo điều kiện theo tham số.

Ví dụ XML:

~~~xml
<select id="search" resultType="CustomerSummary">
  SELECT id, display_name, status
  FROM customers
  <where>
    <if test="status != null and status != ''">
      AND status = #{status}
    </if>
    <if test="createdFrom != null">
      AND created_at >= #{createdFrom}
    </if>
    <if test="createdTo != null">
      AND created_at < #{createdTo}
    </if>
  </where>
  ORDER BY created_at DESC, id ASC
</select>
~~~

Cú pháp #{status} tạo parameter binding. Không dùng cơ chế thay chuỗi trực tiếp trong mapper với dữ liệu không tin cậy. Nếu cần dynamic identifier, dùng whitelist và các nhánh cố định trong mapper.

Dù MyBatis không phải chủ đề chính của repository JDBC, nguyên tắc bảo mật vẫn giống nhau: value được bind; SQL structure chỉ được chọn từ những phần đã được ứng dụng kiểm soát.

## 11. Tìm kiếm LIKE và wildcard

Bind parameter ngăn chuỗi tìm kiếm thay đổi cấu trúc SQL, nhưng ký tự % và _ vẫn là wildcard theo semantics của LIKE.

Ví dụ:

~~~sql
WHERE display_name LIKE :pattern
~~~

Nếu pattern là %an%, truy vấn có thể khớp nhiều tên chứa chuỗi an. Đây không phải SQL injection, nhưng có thể rộng hơn ý định tìm kiếm của người dùng.

Nếu muốn tìm literal text, escape wildcard trước khi bind. Có thể chọn ! làm escape character:

~~~java
private String literalContainsPattern(String input) {
    String escaped = input
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");

    return "%" + escaped + "%";
}
~~~

SQL:

~~~sql
SELECT id, display_name
FROM customers
WHERE display_name LIKE :pattern ESCAPE '!'
~~~

Bind pattern:

~~~java
params.addValue("pattern", literalContainsPattern(searchText));
~~~

Thứ tự escape quan trọng: escape chính ký tự ! trước, sau đó mới escape % và _. Nếu không, ký tự escape vừa thêm có thể bị escape lần nữa.

Nếu ứng dụng chủ ý hỗ trợ wildcard search, hãy công bố semantics đó trong API thay vì vô tình để người dùng điều khiển pattern.

## 12. NULL cần xử lý bằng nhánh SQL riêng

Trong SQL, so sánh bằng NULL bằng toán tử = không trả TRUE. Ví dụ:

~~~sql
WHERE deleted_at = :deletedAt
~~~

nếu deletedAt được bind là NULL thì điều kiện không khớp các hàng có deleted_at NULL.

Nếu cần lọc hàng có giá trị null, dùng:

~~~sql
WHERE deleted_at IS NULL
~~~

Nếu muốn bộ lọc optional:

~~~java
if (deletedAtIsNull) {
    sql.append(" AND deleted_at IS NULL");
} else if (deletedAt != null) {
    sql.append(" AND deleted_at = :deletedAt");
    params.addValue("deletedAt", deletedAt);
}
~~~

Không tạo cú pháp SQL bằng cách ghép từ khóa NULL do client gửi. Dùng boolean/enum biểu diễn lựa chọn nghiệp vụ rồi ánh xạ sang nhánh SQL cố định.

## 13. IN clause và danh sách rỗng

NamedParameterJdbcTemplate hỗ trợ mở rộng collection cho named parameter trong IN clause:

~~~java
String sql = """
    SELECT id, display_name
    FROM customers
    WHERE id IN (:ids)
    """;

var params = new MapSqlParameterSource()
        .addValue("ids", customerIds);

List<CustomerSummary> customers =
        namedParameterJdbcTemplate.query(
                sql,
                params,
                customerSummaryRowMapper
        );
~~~

Spring JDBC tạo số placeholder phù hợp với collection. Không nối từng ID vào SQL string.

Phải xử lý danh sách rỗng trước khi thực thi. Một số database không chấp nhận IN () và semantics nghiệp vụ có thể khác nhau:

- Nếu danh sách rỗng nghĩa là không chọn khách hàng nào, trả danh sách rỗng ngay.
- Nếu danh sách rỗng nghĩa là không áp dụng bộ lọc, bỏ hẳn điều kiện IN.
- Nếu danh sách rỗng không hợp lệ, từ chối request.

Ví dụ:

~~~java
if (customerIds == null || customerIds.isEmpty()) {
    return List.of();
}
~~~

Không mặc định rằng bỏ điều kiện IN khi danh sách rỗng là an toàn. Nó có thể biến truy vấn tìm theo các ID đã chọn thành tìm tất cả khách hàng.

Với JdbcTemplate positional parameter, nếu cần IN list động, hãy tạo đúng số dấu hỏi từ số phần tử đã validate và bind từng ID; không ghép giá trị ID vào câu SQL.

## 14. Phân trang động: bind limit và offset

LIMIT, OFFSET hoặc cú pháp pagination tương đương thường nhận giá trị số. Có thể bind chúng:

~~~sql
SELECT id, display_name
FROM customers
ORDER BY id
LIMIT :limit OFFSET :offset
~~~

Trước khi query, validate:

- limit lớn hơn 0.
- limit không vượt mức tối đa API cho phép.
- offset không âm.
- Tính offset bằng kiểu số đủ lớn để tránh overflow.
- Sort field nằm trong allowlist.
- Có ORDER BY ổn định, thường thêm khóa duy nhất làm tie-breaker.

Ví dụ:

~~~java
int pageSize = Math.min(requestedSize, 100);

if (pageSize < 1 || pageNumber < 0) {
    throw new IllegalArgumentException("Invalid page request");
}

long offset = Math.multiplyExact((long) pageNumber, pageSize);
~~~

Cú pháp LIMIT/OFFSET khác nhau giữa database. Với Spring Data repository hoặc Query API, ưu tiên Pageable để dialect xử lý phần pagination. Với SQL tùy chỉnh, dùng cú pháp phù hợp DBMS và bind các giá trị số.

## 15. Không cho client gửi một đoạn SQL hoàn chỉnh

Một API không nên nhận tham số filter hoặc sort chứa một đoạn SQL rồi chèn nguyên văn vào query. Việc lọc bỏ dấu chấm phẩy hoặc chỉ cấm một số keyword không tạo thành parser SQL an toàn.

Thiết kế API theo cấu trúc dữ liệu:

~~~json
{
  "status": "ACTIVE",
  "createdFrom": "2026-01-01T00:00:00Z",
  "sortBy": "created",
  "direction": "desc",
  "page": 0,
  "size": 20
}
~~~

Ứng dụng validate từng field theo kiểu và contract:

- status chỉ thuộc tập trạng thái hợp lệ.
- createdFrom phải parse thành thời gian hợp lệ.
- sortBy thuộc enum/allowlist.
- direction chỉ ASC hoặc DESC.
- page và size nằm trong giới hạn.
- Các filter có quyền truy cập phù hợp với người dùng hiện tại.

Sau validation, code mới tạo query từ fragment cố định và bind các value.

## 16. Phân biệt SQL injection với authorization

Một câu query được parameterize vẫn có thể trả dữ liệu mà người dùng không được phép xem nếu thiếu điều kiện phân quyền.

Ví dụ:

~~~sql
SELECT id, total
FROM purchase_orders
WHERE id = :orderId
~~~

Parameter orderId đã được bind an toàn, nhưng user có thể thử ID của đơn hàng thuộc người khác.

Nếu quyền xem phụ thuộc chủ sở hữu hoặc tenant, query phải giới hạn thêm bằng identity lấy từ security context:

~~~sql
SELECT id, total
FROM purchase_orders
WHERE id = :orderId
  AND tenant_id = :tenantId
~~~

tenantId phải đến từ context đã được xác thực/ủy quyền, không tin giá trị client gửi chỉ vì nó cũng được bind an toàn.

Parameter binding bảo vệ cấu trúc SQL; authorization bảo vệ quyền truy cập dữ liệu. Hai yêu cầu cần được kiểm tra riêng.

## 17. Bind đúng kiểu dữ liệu

Bind parameter không chỉ là chống injection. Nó còn giúp driver biết kiểu dữ liệu.

Ví dụ với NamedParameterJdbcTemplate:

~~~java
var params = new MapSqlParameterSource()
        .addValue("customerId", customerId, Types.BIGINT)
        .addValue("createdAt", createdAt, Types.TIMESTAMP)
        .addValue("total", total, Types.DECIMAL);
~~~

Khi giá trị null hoặc kiểu đặc thù, có thể cần chỉ định JDBC type để driver/database xử lý chính xác.

Không chuyển mọi value thành String rồi bind. Giữ kiểu Java tương ứng với cột như Long, BigDecimal, LocalDate, Instant hoặc UUID theo mapping và khả năng driver.

Với custom type, converter hoặc JDBC type handler phải được kiểm tra trên database mục tiêu.

## 18. Batch update vẫn phải bind tham số

Khi thực hiện batch, mỗi hàng vẫn phải dùng PreparedStatement parameter:

~~~java
String sql = """
    UPDATE customers
    SET status = ?
    WHERE id = ?
    """;

jdbcTemplate.batchUpdate(
        sql,
        customersToUpdate,
        100,
        (ps, customer) -> {
            ps.setString(1, customer.status());
            ps.setLong(2, customer.id());
        }
);
~~~

Không xây một câu UPDATE khác nhau bằng cách nối ID và status của từng phần tử. Batch parameter binding vừa giữ an toàn vừa cho driver cơ hội tối ưu thực thi.

Nếu batch chứa dữ liệu đến từ file import hoặc message broker, vẫn coi toàn bộ value là không tin cậy. Nguồn nội bộ không đồng nghĩa dữ liệu đã được xác thực.

## 19. Những cách viết cần tránh

| Cách viết | Vấn đề | Cách thay thế |
|---|---|---|
| Nối email vào SQL string | SQL injection | Placeholder và bind parameter |
| Nối ID vào WHERE | Trộn value với cú pháp | Bind ID theo JDBC type |
| Dùng request string làm ORDER BY | Identifier không thể bind; có thể injection | Whitelist cột và direction |
| Dùng parameter để thay table name | Placeholder không đại diện identifier | Chọn table từ map/enum cố định |
| Dùng cú pháp thay chuỗi trực tiếp trong mapper | Chèn SQL fragment không kiểm soát | Bind value; whitelist structure |
| Dùng IN với list rỗng | Có thể sinh SQL không hợp lệ hoặc đổi semantics | Xử lý empty list trước |
| Dùng = NULL | Không khớp SQL NULL | IS NULL/IS NOT NULL |
| Ghép wildcard không chủ đích | Kết quả LIKE quá rộng | Escape %/_ hoặc công bố wildcard semantics |
| Tin tenantId do client gửi | Có thể đọc chéo tenant | Lấy tenant từ security context đã xác thực |
| Chỉ lọc keyword nguy hiểm | Blacklist không thể nhận diện đầy đủ SQL grammar | Parameterize và whitelist |

## 20. Kiểm thử chống SQL injection

Một integration test nên xác nhận payload giống SQL được lưu/tìm như một giá trị bình thường.

Ví dụ:

~~~java
@Test
void treatsSqlLikeInputAsPlainValue() {
    String payload = "' OR '1'='1' --";

    jdbcTemplate.update(
            "INSERT INTO customers(email, display_name) VALUES (?, ?)",
            "safe@example.com",
            payload
    );

    List<CustomerSummary> result = customerRepository
            .findByDisplayName(payload);

    assertEquals(1, result.size());
    assertEquals(payload, result.get(0).displayName());
}
~~~

Tùy repository method và schema thực tế, điều chỉnh tên property/DTO cho phù hợp. Mục tiêu là chứng minh chuỗi payload được bind như value, không thay đổi điều kiện query.

Nên có test cho:

- Dấu nháy đơn và dấu nháy kép.
- Comment marker và ký tự dấu chấm phẩy.
- Chuỗi dài hoặc ký tự Unicode.
- Giá trị null.
- Danh sách IN rỗng.
- Sort field không được phép.
- Direction không hợp lệ.
- Wildcard % và _ trong LIKE.
- Tenant/user không có quyền truy cập bản ghi.
- Dynamic filter kết hợp nhiều điều kiện.

Không chỉ kiểm tra một payload cụ thể. Cần review mọi nơi tạo SQL động và xác nhận value được bind, identifier được whitelist.

## 21. Log và quan sát query an toàn

Khi debug, SQL log có thể giúp xác nhận query structure và parameter binding. Tuy nhiên, parameter có thể chứa email, số điện thoại, token, địa chỉ hoặc dữ liệu thanh toán.

Thực hành an toàn:

- Không log toàn bộ parameter nhạy cảm trong production.
- Mask hoặc redact dữ liệu định danh khi cần.
- Hạn chế thời gian bật log SQL chi tiết.
- Bảo vệ quyền truy cập log và thời hạn lưu.
- Không ghi token/session secret vào exception message.
- Dùng metrics/tracing để theo dõi latency và số hàng mà không cần lộ toàn bộ value.

Logging không thay thế parameter binding. Một câu query an toàn vẫn có thể làm lộ dữ liệu nếu log ghi toàn bộ tham số.

## 22. Defense in depth

Parameter binding là lớp bảo vệ chính cho SQL value, nhưng nên kết hợp thêm:

1. Dùng database account có quyền tối thiểu cần thiết.
2. Không chạy ứng dụng bằng tài khoản quản trị database.
3. Validate kiểu, độ dài và miền giá trị ở application boundary.
4. Whitelist identifier, sort field và SQL structure động.
5. Áp dụng authorization và tenant isolation.
6. Dùng constraint để bảo vệ dữ liệu ở database.
7. Giữ JDBC driver và framework ở phiên bản được hỗ trợ.
8. Kiểm thử repository query và custom SQL.
9. Không để exception trả chi tiết schema/SQL nhạy cảm ra client.
10. Theo dõi hành vi truy vấn bất thường.

Stored procedure cũng có thể mắc SQL injection nếu bên trong procedure ghép chuỗi thành dynamic SQL. Chuyển query vào stored procedure không tự động làm nó an toàn.

## 23. Quy trình xây dựng query động an toàn

Khi một use case cần bộ lọc, sort và pagination tùy chọn:

1. Định nghĩa request DTO với kiểu rõ ràng.
2. Validate giá trị và giới hạn kích thước đầu vào.
3. Chuyển sort field/direction sang enum hoặc allowlist.
4. Chọn SQL template hoặc các fragment cố định.
5. Bind mọi value bằng repository parameter, PreparedStatement hoặc NamedParameterJdbcTemplate.
6. Xử lý null và empty collection theo semantics nghiệp vụ.
7. Escape LIKE wildcard nếu cần tìm literal text.
8. Thêm điều kiện authorization/tenant từ context tin cậy.
9. Kiểm tra update count hoặc kết quả trả về.
10. Viết integration test cho payload, filter combinations và database mục tiêu.

~~~mermaid
flowchart TD
    A[Request filter / sort / page] --> B[Parse và validate kiểu]
    B --> C{Sort có trong allowlist?}
    C -->|Không| D[Từ chối request]
    C -->|Có| E[Chọn SQL fragment cố định]
    E --> F[Bind toàn bộ value]
    F --> G[Thực thi query]
    G --> H[Kiểm tra quyền và kết quả]
    H --> I[Trả response]
~~~

## 24. Nguyên tắc ghi nhớ

- SQL injection xuất hiện khi dữ liệu không tin cậy bị ghép vào cấu trúc SQL.
- Dùng PreparedStatement, repository parameter binding, JdbcTemplate hoặc NamedParameterJdbcTemplate để bind mọi value.
- Trong Spring Data JDBC, derived query và @Query bind method argument; không nối argument vào SQL string.
- Bind parameter thay value, không thay table name, column name, operator hoặc ORDER BY direction.
- Dynamic identifier phải được chọn từ whitelist/enum/map cố định.
- Dynamic WHERE chỉ append fragment do code kiểm soát; value luôn bind.
- Với LIKE, % và _ vẫn là wildcard; escape nếu muốn tìm literal text.
- Xử lý NULL bằng IS NULL/IS NOT NULL và xác định semantics của filter optional.
- Với IN list, xử lý collection rỗng trước khi chạy query.
- Giới hạn page size, offset và sort field; dùng Pageable khi framework có thể tạo pagination theo dialect.
- Bind đúng JDBC type, đặc biệt với null và kiểu đặc thù.
- Parameter binding không thay thế authorization, tenant isolation hoặc database least privilege.
- SQL trong stored procedure và batch job vẫn cần được kiểm soát.
- Test payload SQL-like, dynamic sort, LIKE, NULL, empty list và quyền truy cập dữ liệu.

Bind tham số tạo ranh giới rõ giữa SQL structure và dữ liệu đầu vào. Trong Spring Data JDBC, hãy ưu tiên derived query, Criteria hoặc @Query có parameter binding; khi cần SQL động, chỉ xây cấu trúc từ fragment cố định và whitelist. Kết hợp cách làm đó với authorization, quyền database tối thiểu và integration test để truy vấn vừa linh hoạt vừa an toàn.

## Tài liệu tham khảo

- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)

