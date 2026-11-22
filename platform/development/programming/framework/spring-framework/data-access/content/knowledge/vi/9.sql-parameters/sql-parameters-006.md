# Tham số SQL chỉ thay giá trị, không tự thay tên bảng, tên cột hoặc cú pháp SQL

Trong Spring JDBC, **dấu hỏi ?**, **tham số có tên :param** và các lời gọi **PreparedStatement.setXxx(...)** được dùng để truyền **giá trị dữ liệu** cho một câu SQL đã định hình cấu trúc. Chúng **không** thay thế tên bảng, tên cột, từ khóa, toán tử hoặc nguyên mệnh đề SQL. Đây là ranh giới quan trọng nhất khi làm repository có tham số tìm kiếm, sắp xếp, báo cáo hay lọc động.

Nếu tưởng có thể truyền mọi thứ qua parameter, chương trình có thể lỗi cú pháp, trả kết quả sai hoặc bị cám dỗ nối chuỗi thô vào câu SQL. Nối cấu trúc từ đầu vào không tin cậy lại mở đường cho **SQL injection**, ngay cả khi phần WHERE khác đã dùng PreparedStatement.

Bài học nằm trong **Spring Framework - data-access**, nhóm **Tham số SQL**. Ta sẽ phân biệt SQL structure và value, dùng JdbcTemplate/NamedParameterJdbcTemplate/JdbcClient, dựng ORDER BY và bảng động bằng allow-list, xử lý IN/LIKE/NULL, rồi chạy một ví dụ Java 17+ với H2 để chứng minh.

## 1. Phân tích một truy vấn thành cấu trúc và giá trị

Xét:

~~~sql
SELECT id, display_name, price
FROM products
WHERE product_state = ? AND price >= ?
ORDER BY price DESC, id ASC;
~~~

- **SELECT, FROM, WHERE, AND, ORDER BY, DESC, ASC** là cú pháp.
- **products** là tên bảng; **id, display_name, price, product_state** là tên cột, tức SQL identifier.
- **=, >=** là toán tử.
- Hai ký hiệu **?** là nơi bind **giá trị**: trạng thái sản phẩm và giá tối thiểu.

Trong Java:

~~~java
List<Product> rows = jdbcTemplate.query(
    """
    SELECT id, display_name, product_state, price
    FROM products
    WHERE product_state = ? AND price >= ?
    ORDER BY price DESC, id ASC
    """,
    PRODUCT_ROW_MAPPER,
    "ACTIVE",
    new java.math.BigDecimal("50.00")
);
~~~

Đây là đoạn mã minh họa bên trong repository đã có JdbcTemplate, RowMapper và kiểu Product; chưa phải chương trình chạy độc lập. Spring/driver bind giá trị "ACTIVE" và 50.00 theo thứ tự. Nó không biến đổi bảng products, cột price hay keyword DESC.

~~~text
                 SQL cố định của chương trình
            SELECT ... FROM products
               WHERE price >= ?
                        |
                        v
               Value parameter
                BigDecimal("50")
                        |
                        v
              PreparedStatement
                        |
                Database parser
            đã biết cấu trúc SQL
~~~

Một marker không phải macro, không phải phép chèn văn bản thô, và không phải hàm tạo câu SQL mới.

## 2. Bảng quyết định: thành phần nào bind được?

| Thành phần cần thay đổi | Dùng ? hoặc :param? | Cách đúng |
| --- | --- | --- |
| WHERE id = ? | Có | Bind ID số/UUID |
| WHERE state = :state | Có | Bind chuỗi trạng thái |
| INSERT ... VALUES (?, ?) | Có | Bind các dữ liệu được ghi |
| UPDATE ... SET price = ? | Có | Bind giá mới |
| HAVING COUNT(*) >= ? | Có | Bind ngưỡng |
| LIKE :pattern | Có | Bind toàn bộ pattern |
| LIMIT ? / OFFSET ? | Có nếu dialect/driver hỗ trợ | Bind số đã kiểm tra miền |
| FROM ? | **Không** | Dùng bảng cố định hoặc allow-list |
| SELECT ? với ý định chọn tên cột | **Không** | Chọn projection cố định hoặc allow-list |
| ORDER BY :column | **Không** nếu muốn đổi tên cột | Ánh xạ sort key thành identifier |
| ORDER BY price :direction | **Không** | Chọn ASC/DESC từ enum |
| WHERE price :operator :threshold | **Không** đối với toán tử | Chọn toán tử cho phép, bind threshold |
| WHERE :rawClause | **Không** | Dựng predicate từ code |
| JOIN, GROUP BY, UNION, DISTINCT | **Không** | Dùng SQL/DSL có kiểm soát |
| IN (:ids) với collection | Có nhờ Spring mở rộng list | Bind từng phần tử được mở rộng |
| Tên schema, alias, index hoặc database | **Không** | Chọn từ cấu hình/allow-list |
| Cả câu SELECT trong một giá trị bind | **Không** | Viết SQL thật riêng |

Lưu ý quan trọng: có DBMS cho phép marker trong ORDER BY ở vai trò **biểu thức giá trị**, nhưng điều đó không biến một chuỗi như "price" thành tên cột price. Đặc biệt, không dùng ORDER BY ? để chọn cột dựa trên input.

## 3. Vì sao FROM ? và SELECT ? không phải tên bảng/cột?

Ví dụ sai:

~~~sql
SELECT id, display_name
FROM ?
WHERE id = ?;
~~~

Người viết có thể định bind tham số đầu thành "products". Tuy nhiên FROM yêu cầu một **table reference trong ngữ pháp SQL**. Tham số trong prepared statement không viết lại token loại này. Khi database/driver phân tích câu lệnh, nó không thể tùy ý diễn giải giá trị chuỗi như identifier mới.

Ví dụ khó nhận ra hơn:

~~~sql
SELECT ? FROM products WHERE id = ?;
~~~

Nếu tham số đầu là chuỗi "display_name", ở DBMS cho phép cú pháp này, câu SQL có thể trả **hằng chuỗi "display_name"** trên mỗi hàng, thay vì đọc cột display_name.

~~~sql
-- Đọc tên sản phẩm:
SELECT display_name FROM products WHERE id = ?;

-- Không tương đương: tham số đầu là một GIÁ TRỊ.
SELECT ? FROM products WHERE id = ?;
~~~

Tương tự, WHERE ? = ? so sánh hai giá trị, không tự thay tên cột. Ngay cả khi SQL hợp lệ về cú pháp, kết quả vẫn có thể sai.

### 3.1. JDBC PreparedStatement hoạt động ở ranh giới code/data

Hai bước logic là:

1. Driver nhận một **mẫu SQL có các parameter marker hợp lệ**.
2. Chương trình truyền **giá trị có kiểu** vào các vị trí marker trước khi thực thi.

Driver và DBMS có thể dùng nhiều cơ chế prepare, parse, cache hoặc protocol; không phải mọi PreparedStatement đều được tạo thành một server-side prepared statement tồn tại lâu dài. Dù triển khai khác nhau, **giá trị bind không được đối xử như cấu trúc SQL mới**.

Đây chính là cơ sở an toàn chống SQL injection của tham số hóa: ký tự nháy đơn, dấu chấm phẩy hay đoạn giống SQL trong **giá trị** vẫn là dữ liệu.

## 4. JdbcTemplate: dấu ? theo vị trí

Trong Spring JDBC, JdbcTemplate cung cấp các API query/update dùng PreparedStatement và tự quản lý tài nguyên JDBC theo cơ chế Spring.

~~~java
List<Product> findActiveByPrice(
        java.math.BigDecimal minimumPrice) {

    String sql = """
        SELECT id, display_name, product_state, price
        FROM products
        WHERE product_state = ? AND price >= ?
        ORDER BY price DESC, id ASC
        """;

    return jdbcTemplate.query(
        sql, PRODUCT_ROW_MAPPER, "ACTIVE", minimumPrice
    );
}
~~~

Thứ tự bind là từ trái sang phải. Dấu ? thứ nhất tương ứng product_state; dấu ? thứ hai tương ứng price. Spring không tự ghép tên biến Java với tên cột trong trường hợp positional parameters.

~~~java
// INSERT: thay dữ liệu, không đổi tên bảng/cột.
int inserted = jdbcTemplate.update(
    "INSERT INTO products (id, display_name, product_state, price) " +
    "VALUES (?, ?, ?, ?)",
    id, displayName, state, price
);

// UPDATE: price và id là identifier cố định; giá trị được bind.
int updated = jdbcTemplate.update(
    "UPDATE products SET price = ? WHERE id = ?",
    newPrice, id
);

// DELETE: chỉ id là giá trị thay đổi.
int deleted = jdbcTemplate.update(
    "DELETE FROM products WHERE id = ?",
    id
);
~~~

Các đoạn mã trên là thành phần repository có biến/đối tượng đã được khai báo. Kết quả update(...) là số hàng bị ảnh hưởng theo driver/DBMS; nên kiểm tra khi hợp đồng yêu cầu đúng một hàng.

### 4.1. PreparedStatement thuần: vị trí tham số bắt đầu từ 1

~~~java
String sql = """
    SELECT id, display_name
    FROM products
    WHERE product_state = ? AND price >= ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setString(1, "ACTIVE");
    ps.setBigDecimal(2, new java.math.BigDecimal("50.00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("id"));
        }
    }
}
~~~

Đây là snippet Java JDBC trong ứng dụng đã có DataSource; **index tham số bắt đầu từ 1**. Cần đóng Connection, Statement và ResultSet đúng vòng đời. Nếu Spring đã quản lý transaction, dùng JdbcTemplate hoặc DataSourceUtils thay vì tự đóng một connection đang được transaction quản lý.

### 4.2. Một payload giống SQL vẫn được bind như dữ liệu

Giả sử input là:

~~~text
ACTIVE' OR 1=1 --
~~~

Dùng parameter binding:

~~~java
List<Long> ids = jdbcTemplate.query(
    "SELECT id FROM products WHERE product_state = ?",
    (rs, rowNum) -> rs.getLong("id"),
    input
);
~~~

Toàn bộ chuỗi input là **một giá trị** dùng để so sánh product_state. Phần OR 1=1 và -- không trở thành toán tử hoặc comment SQL. Nếu không có sản phẩm nào có state đúng bằng toàn bộ payload, kết quả là danh sách rỗng.

Ngược lại:

~~~java
// SAI: raw input tham gia cấu trúc SQL được phân tích.
String sql = "SELECT id FROM products WHERE product_state = '" +
             input + "'";
~~~

Đây là cách viết có nguy cơ SQL injection. Không tự thêm dấu nháy hoặc escape chuỗi để thay thế parameter binding.

## 5. NamedParameterJdbcTemplate: :name vẫn là value parameter

NamedParameterJdbcTemplate thay cách đánh số marker bằng tham số có tên. Ví dụ:

~~~java
String sql = """
    SELECT id, display_name, product_state, price
    FROM products
    WHERE product_state = :state AND price >= :minimum
    ORDER BY price DESC
    """;

MapSqlParameterSource args = new MapSqlParameterSource()
    .addValue("state", "ACTIVE")
    .addValue("minimum", new java.math.BigDecimal("50.00"));

List<Product> result = namedJdbc.query(
    sql, args, PRODUCT_ROW_MAPPER
);
~~~

Cần import org.springframework.jdbc.core.namedparam.MapSqlParameterSource và định nghĩa namedJdbc/PRODUCT_ROW_MAPPER trong repository. Tên state/minimum ở đây chỉ nhận **giá trị**. Spring phân tích và chuyển named parameters thành marker JDBC tương ứng.

Ví dụ sai:

~~~sql
SELECT id
FROM :table
WHERE :column = :value
ORDER BY :sortColumn :direction;
~~~

Đưa Map chứa table="products", column="price", direction="DESC" không tạo SQL hợp lệ như ý định. Các vị trí cần identifier/keyword, không phải giá trị. Một vài vị trí biểu thức có thể vẫn hợp lệ nhưng có nghĩa sai, càng cần tránh.

### 5.1. Cùng named parameter xuất hiện nhiều lần

~~~sql
SELECT id, display_name
FROM products
WHERE display_name = :name OR :name = 'ALL';
~~~

Nếu bind name="Chuột", cả hai vị trí được bind bằng **giá trị** "Chuột". Tên biến lặp không thay toán tử OR hoặc cột display_name.

### 5.2. JdbcClient từ Spring Framework 6.1

JdbcClient cung cấp API fluent cho JDBC có tham số theo tên/vị trí:

~~~java
List<Product> products = jdbcClient
    .sql("""
         SELECT id, display_name, product_state, price
         FROM products WHERE product_state = :state
         ORDER BY id
         """)
    .param("state", "ACTIVE")
    .query(PRODUCT_ROW_MAPPER)
    .list();
~~~

Đây là snippet có sẵn JdbcClient/RowMapper trong class repository. Phương thức param(...) vẫn bind **giá trị**, không chuyển tên bảng hoặc cột thành SQL mới. Cần đối chiếu phiên bản Spring và các overload khi áp dụng.

## 6. ORDER BY động: allow-list tên cột và chiều sắp xếp

Nhiều UI cần lựa chọn sort=name, sort=price hoặc direction=desc. Sai lầm:

~~~java
// NGUY HIỂM: userSort / userDirection từ request được nối thẳng.
String sql = "SELECT id, display_name FROM products " +
             "ORDER BY " + userSort + " " + userDirection;
~~~

Dù các giá trị WHERE khác đã bind, cấu trúc ORDER BY vẫn đến từ input không tin cậy, có thể gây injection, chọn cột không được phép hoặc thực thi biểu thức quá nặng.

### 6.1. Chỉ chọn token SQL do chương trình định nghĩa

~~~java
enum SortKey {
    NAME("display_name"),
    PRICE("price"),
    ID("id");

    private final String column;

    SortKey(String column) {
        this.column = column;
    }

    String sqlColumn() {
        return column;
    }
}

enum SortDirection {
    ASC, DESC;

    String sqlToken() {
        return name();
    }
}
~~~

Sau đó dùng enum:

~~~java
List<Product> findSorted(
        String state, SortKey key, SortDirection direction) {

    String sql =
        "SELECT id, display_name, product_state, price " +
        "FROM products WHERE product_state = ? ORDER BY " +
        key.sqlColumn() + " " + direction.sqlToken() +
        ", id ASC";

    return jdbcTemplate.query(
        sql, PRODUCT_ROW_MAPPER, state
    );
}
~~~

Chỉ các token có sẵn trong SortKey/SortDirection mới đi vào **SQL structure**. Giá trị state **vẫn bind bằng ?**. `id ASC` là tie-breaker để tránh thứ tự mơ hồ khi giá hoặc tên giống nhau.

Nếu đầu vào ban đầu là chuỗi HTTP, phải **chuyển sang enum qua allow-list**:

~~~java
static SortKey parseSort(String input) {
    return switch (input) {
        case "name" -> SortKey.NAME;
        case "price" -> SortKey.PRICE;
        case "id" -> SortKey.ID;
        default -> throw new IllegalArgumentException(
            "Unsupported sort field"
        );
    };
}

static SortDirection parseDirection(String input) {
    return switch (input) {
        case "asc" -> SortDirection.ASC;
        case "desc" -> SortDirection.DESC;
        default -> throw new IllegalArgumentException(
            "Unsupported sort direction"
        );
    };
}
~~~

Đoạn mã Java 17; null input cần được xử lý tường minh ở ranh giới controller/service nếu có thể xảy ra. Không chỉ kiểm tra chuỗi hợp regex identifier rồi cho phép sử dụng: một cột hợp lệ về cú pháp vẫn có thể là cột nhạy cảm hoặc chưa được API công bố.

### 6.2. ORDER BY ? không phải đổi tên cột

~~~sql
SELECT id, display_name, price
FROM products
ORDER BY ?;
~~~

Bind chuỗi "price" không tương đương ORDER BY price. DBMS có thể xử lý nó như một biểu thức/hằng số hoặc báo lỗi tùy kiểu và dialect. `ORDER BY price ?` rồi bind "DESC" cũng không hoạt động như thay keyword DESC.

Tương tự:

~~~sql
SELECT id FROM products WHERE price ? ?;
~~~

Không thể bind toán tử `>=` vào vị trí marker thứ nhất. Dấu ? đại diện cho **toán hạng giá trị**, không phải token toán tử hay cấu trúc SQL.

## 7. Dynamic table name và SELECT column: cố định cấu trúc hoặc allow-list

Tên bảng thuộc phần cấu trúc:

~~~sql
-- SAI khi muốn tableName là tên bảng:
SELECT COUNT(*) FROM ?;
~~~

Cách nối input chưa kiểm soát cũng sai:

~~~java
// SAI: requestTable có thể chứa dữ liệu không được phép.
String sql = "SELECT COUNT(*) FROM " + requestTable;
~~~

Nếu API nội bộ cần chọn một số báo cáo đã biết, ánh xạ mã báo cáo sang tên bảng **do ứng dụng sở hữu**:

~~~java
static String allowedReportTable(String reportType) {
    return switch (reportType) {
        case "products" -> "products";
        case "inventory" -> "inventory_snapshot";
        default -> throw new IllegalArgumentException(
            "Unsupported report type"
        );
    };
}

String sql = "SELECT COUNT(*) FROM " +
             allowedReportTable(reportType);
~~~

Đây chỉ là thiết kế minh họa; bảng inventory_snapshot phải tồn tại và DB account cần quyền SELECT hợp lệ. Một lựa chọn còn dễ kiểm tra hơn là viết **hai truy vấn cố định** riêng biệt cho mỗi loại báo cáo.

### 7.1. Dynamic projection không phải giá trị

Nếu UI gửi danh sách fields gồm name và price, không nên String.join trực tiếp dữ liệu đó thành SELECT fields. Hãy ánh xạ mỗi **field key** sang cột được phép, từ chối field khác, bảo đảm người dùng không đọc nhầm cột nhạy cảm.

SQL:

~~~sql
SELECT ? FROM products WHERE id = ?;
~~~

không thể nhận tham số `"display_name"` như tên cột. Nếu DBMS cho phép, nó chọn hằng giá trị `"display_name"` trên mỗi hàng.

### 7.2. UPDATE dynamic column

Không làm:

~~~java
// SAI: fieldName là raw user input.
String sql = "UPDATE products SET " + fieldName +
             " = ? WHERE id = ?";
~~~

Ưu tiên các phương thức nghiệp vụ cụ thể:

~~~java
int changePrice(long id, BigDecimal price) {
    return jdbc.update(
        "UPDATE products SET price = ? WHERE id = ?",
        price, id
    );
}
~~~

Nếu thực sự cần chọn giữa vài cột, map field key sang token cột cố định rồi **vẫn bind giá trị mới**. Không cho người dùng chọn cột tùy ý, đặc biệt cột mật khẩu, owner hoặc tenant ID.

### 7.3. Schema, alias, index và multi-tenant

Tên schema, table alias và index cũng thuộc SQL structure. Không dùng `:schema.tableName` như phép bind tên schema. Với multi-tenant, cân nhắc tenant_id được bind ở WHERE hoặc mapping tenant -> schema/DataSource được server quản lý. Không cho phép raw tenant/schema name từ request trở thành identifier SQL.

### 7.4. Quoting identifier không thay thế allow-list

PostgreSQL dùng dấu nháy kép cho một số identifier đặc biệt; các DBMS khác có quy ước quoting khác nhau. Quoting giúp bảo vệ **cú pháp** của tên đã chọn, không bảo đảm caller được quyền chọn bảng/cột ấy. Chọn identifier từ allow-list trước; nếu cần, quote theo dialect (không tự suy đoán một cú pháp dùng được cho mọi DBMS). Quyền DB và logic authorization là lớp phòng thủ riêng.

## 8. Toán tử, WHERE, JOIN và keyword: phải chọn cấu trúc

Nếu API cho phép các phép so sánh `gt`, `gte`, `lt`, `lte`, đừng bind operator:

~~~sql
-- KHÔNG hợp lệ như cách thay operator:
SELECT id FROM products WHERE price :operator :price;
~~~

Thay vào đó:

~~~java
static String allowedOperator(String key) {
    return switch (key) {
        case "gt" -> ">";
        case "gte" -> ">=";
        case "lt" -> "<";
        case "lte" -> "<=";
        default -> throw new IllegalArgumentException(
            "Unsupported operator"
        );
    };
}

String sql = "SELECT id FROM products WHERE price " +
             allowedOperator(operatorKey) + " ?";

List<Long> ids = jdbc.query(
    sql,
    (rs, index) -> rs.getLong("id"),
    threshold
);
~~~

Operator do code sở hữu; threshold là value bind.

Cũng không thể bind một mệnh đề nguyên văn:

~~~sql
SELECT id FROM products WHERE :whereClause;
~~~

Các chuỗi như `price > 0 AND product_state = 'ACTIVE'` là **SQL code**, không phải một giá trị. Nếu API cần nhiều bộ lọc, phải dựng các predicate định sẵn.

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT id, display_name, product_state, price " +
    "FROM products WHERE tenant_id = :tenantId"
);

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("tenantId", tenantId);

if (state != null) {
    sql.append(" AND product_state = :state");
    params.addValue("state", state);
}

if (minimumPrice != null) {
    sql.append(" AND price >= :minimumPrice");
    params.addValue("minimumPrice", minimumPrice);
}

List<Product> found = namedJdbc.query(
    sql.toString(), params, PRODUCT_ROW_MAPPER
);
~~~

Đây là mẫu trong repository có cột tenant_id và các biến tương ứng; không phải chương trình độc lập. Tất cả **fragment SQL** được nối đều là những đoạn viết sẵn trong code. Điều kiện tenant cố định ở mọi nhánh giúp tránh một bộ lọc động vô tình mở rộng dữ liệu sang tenant khác.

Khi mệnh đề rất phức tạp, có thể dùng DSL/query builder phù hợp nhưng vẫn phải phân biệt API dùng cho identifier với API dùng cho value. Dùng raw SQL string trong builder vẫn có thể không an toàn nếu nội dung đến từ người dùng.

## 9. IN (:ids): Spring có thể mở rộng DANH SÁCH GIÁ TRỊ

SQL chuẩn ở dạng đơn giản:

~~~sql
SELECT id FROM products WHERE id IN (?, ?, ?);
~~~

Mỗi dấu ? là **một giá trị**, không phải văn bản CSV. `NamedParameterJdbcTemplate` hỗ trợ mở rộng collection:

~~~java
List<Long> ids = List.of(1L, 3L, 5L);

List<Long> found = namedJdbc.query(
    "SELECT id FROM products WHERE id IN (:ids) ORDER BY id",
    java.util.Map.of("ids", ids),
    (rs, index) -> rs.getLong("id")
);
~~~

Spring mở rộng :ids thành số placeholder phù hợp rồi bind từng phần tử. Nó **không** biến tên bảng hoặc cú pháp thành tham số. Đừng tự `String.join` các ID người dùng rồi nối chúng vào SQL để thay thế cơ chế này.

### 9.1. Danh sách rỗng

SQL `IN ()` không được mọi DBMS chấp nhận. Không mặc định có thể truyền List rỗng cho IN (:ids) mà nhận tập rỗng đúng cách. Nếu nghiệp vụ định nghĩa “không ID nào được chọn” nghĩa là không có kết quả, trả List rỗng sớm:

~~~java
List<Long> findIds(List<Long> ids) {
    if (ids.isEmpty()) {
        return List.of();
    }
    return namedJdbc.query(
        "SELECT id FROM products " +
        "WHERE id IN (:ids) ORDER BY id",
        java.util.Map.of("ids", ids),
        (rs, index) -> rs.getLong("id")
    );
}
~~~

Có API lại coi collection rỗng là “không áp dụng bộ lọc”; phải nêu rõ hợp đồng riêng, tránh bỏ WHERE ngoài ý muốn khiến query trả cả bảng.

### 9.2. IN-list lớn

Danh sách quá dài có thể vượt giới hạn số marker/IN elements của DBMS hoặc gây tăng chi phí parse/plan. Tùy database, có thể cần chia batch, bảng tạm, array bind, JOIN hoặc table-valued parameter. Không nối CSV không tin cậy vào SQL để “tránh giới hạn”.

## 10. LIKE: bind pattern nhưng wildcard vẫn có ý nghĩa

~~~sql
SELECT id FROM products WHERE display_name LIKE ?;
~~~

Dấu ? nhận **giá trị pattern** như `"Chu%"`. Binding ngăn chuỗi ấy biến thành SQL code, nhưng `%` và `_` vẫn là wildcard do toán tử LIKE diễn giải theo ngữ nghĩa SQL.

Nếu muốn tìm chuỗi literal có `%` hoặc `_`, cần escape wildcard theo dialect:

~~~java
static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

String pattern = escapeLikeLiteral(userText) + "%";

List<Long> ids = jdbc.query(
    """
    SELECT id FROM products
    WHERE display_name LIKE ? ESCAPE '!'
    ORDER BY id
    """,
    (rs, index) -> rs.getLong("id"),
    pattern
);
~~~

Đoạn mã minh họa dùng `!` làm escape character và thêm `%` cuối để chủ ý tìm theo prefix. Cần đối chiếu cú pháp ESCAPE và collation của DBMS đang chạy. `userText` được bind; chuỗi này không bị nối thẳng vào câu SQL.

Phân biệt:
- Bind bảo vệ ranh giới **code vs data**.
- Escape LIKE kiểm soát **wildcard search semantics**.
- Index, collation, full-text search ảnh hưởng **hiệu năng và kết quả tìm kiếm**; bind không tự tối ưu query.

## 11. NULL, kiểu SQL và giới hạn số học

Trong SQL, so sánh với NULL tuân theo **three-valued logic**. Ví dụ:

~~~sql
-- Đúng khi muốn kiểm tra null:
SELECT id FROM products WHERE deleted_at IS NULL;

-- Không tương đương: bind NULL cho ? không khiến = TRUE:
SELECT id FROM products WHERE deleted_at = ?;
~~~

`deleted_at = NULL` thường là UNKNOWN, không phải TRUE. Nếu bộ lọc “chỉ xem bản ghi chưa xóa” yêu cầu IS NULL, đó là **cấu trúc SQL cố định** phải được ứng dụng chọn. Nếu muốn so sánh một thời điểm cụ thể, dùng `deleted_at = :value` và bind thời điểm khác null.

### 11.1. Null parameter cần kiểu trong một số trường hợp

~~~java
MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("nickname", null, java.sql.Types.VARCHAR)
    .addValue("userId", 42L, java.sql.Types.BIGINT);
~~~

Trong JDBC thuần, có thể dùng PreparedStatement.setNull(index, java.sql.Types.VARCHAR). Các driver/DBMS khác nhau về khả năng suy luận kiểu của NULL, UUID, JSON, ARRAY, timestamp. Phải bind đúng kiểu, đôi khi cần cast theo dialect. Bind đúng kiểu không đồng nghĩa cú pháp hoặc SQL type name có thể trở thành parameter.

### 11.2. LIMIT/OFFSET thường là giá trị, nhưng cần validate

PostgreSQL/H2 hỗ trợ:

~~~sql
SELECT id, display_name
FROM products
ORDER BY id
LIMIT ? OFFSET ?;
~~~

Các dấu ? là **số** giới hạn và offset, không thay keyword LIMIT/OFFSET. Một DBMS khác có thể dùng FETCH FIRST, TOP hoặc OFFSET ... FETCH; phải chọn cú pháp riêng theo dialect. Dù bind an toàn trước injection, page size cực lớn hoặc offset lớn vẫn có thể tốn tài nguyên; hãy giới hạn miền giá trị và kiểm tra hiệu năng.

### 11.3. Tiền tệ, ngày giờ và timezone

Ưu tiên BigDecimal cho giá tiền, kiểu date/time phù hợp cho mốc thời gian thay vì ghép literal SQL thủ công. Dùng type mapping của JDBC/driver. Khi xử lý timestamptz/timestamp, phải biết DB lưu instant hay local wall clock; bind parameter không tự giải quyết sai lệch timezone hoặc chính sách so sánh ngày giờ.

## 12. Tạo SQL động có kiểm soát: ba cấp độ ưu tiên

1. **SQL tĩnh** với bind: đơn giản, dễ đọc, dễ review.
2. **Một số query tĩnh được chọn bằng nhánh code**: phù hợp khi có hai hoặc ba dạng báo cáo.
3. **SQL lắp từ fragment/identifier cố định trong allow-list**: dùng cho nhiều bộ lọc hay chọn sắp xếp, nhưng cần test từng tổ hợp.

~~~text
Input từ client
   |
   +--- Giá trị: id, state, minPrice, searchText
   |         |
   |      Validate miền/kiểu
   |         |
   |      Bind qua ? hoặc :param
   |
   +--- Chọn cấu trúc: sort, direction, report type
             |
          Allow-list từ code
             |
         Identifier/keyword/SQL branch cố định

Cấu trúc SQL đáng tin + giá trị bind -> JDBC -> Database
~~~

Đừng coi regex tên cột hoặc escape dấu nháy là đủ thay cho mapping lựa chọn cấu trúc. Một cột hợp lệ về tên vẫn có thể nhạy cảm hoặc gây query quá nặng. Ngược lại, một chuỗi đã validate về ký tự vẫn nên bind như **giá trị**, không nối trực tiếp.

## 13. Lợi ích và giới hạn bảo mật của PreparedStatement

**An toàn value binding không đồng nghĩa toàn bộ câu SQL an toàn.**

~~~java
// NGUY HIỂM: WHERE có bind, ORDER BY lại nối raw user input.
String sql =
    "SELECT id FROM products WHERE product_state = ? " +
    "ORDER BY " + userSort;

List<Long> ids = jdbc.query(
    sql,
    (rs, index) -> rs.getLong("id"),
    state
);
~~~

Value state được bind đúng nhưng sortFromRequest vẫn có thể chèn SQL fragment/identifier ngoài phạm vi cho phép nếu code nối thẳng.

Nguyên tắc phòng thủ:

- Parameter hóa **mọi giá trị dữ liệu**: ID, tên, trạng thái, giá, ngày giờ.
- Allow-list **identifier, operator, direction, report selection** và cấm raw SQL fragments từ người dùng.
- Giữ điều kiện tenant/quyền truy cập trong mọi nhánh SQL.
- Cấp **least privilege** cho DB account: không có quyền DDL hoặc bảng ngoài phạm vi nếu không cần.
- Giới hạn pageSize, LIKE pattern, kích thước IN-list và độ phức tạp query.
- Không ghi secret hoặc dữ liệu nhạy cảm vào log thô.
- Đừng cho rằng stored procedure tự động an toàn: dynamic SQL tạo bằng nối chuỗi bên trong procedure vẫn có thể injection.
- Không dùng escaping thủ công thay parameter binding; cú pháp escape có thể khác theo dialect/configuration.

Sự an toàn đến từ việc **phần có thể thay đổi từ client được xử lý như data**, hoặc nếu là lựa chọn cấu trúc thì được chuyển sang **một tập token đáng tin và hữu hạn** trước khi câu SQL được tạo.

## 14. Demo Java 17+: kiểm chứng thực tế

Demo dùng **Spring JDBC 6.2.7**, **H2 2.3.232**, **Java 17+** và Gradle. Chương trình tạo bảng products trong H2 in-memory rồi minh họa:

- Tên sản phẩm được bind như giá trị.
- Payload giống SQL injection **không** làm thay logic WHERE.
- ORDER BY dùng các token từ enum cho phép, không nhận raw SQL.
- IN (:ids) được Spring mở rộng theo collection.
- Danh sách IN rỗng được xử lý ở Java.
- UPDATE bind giá mới và ID.

Cấu trúc:

~~~text
sql-value-vs-identifier/
  build.gradle
  src/main/java/demo/SqlParameterBoundaryDemo.java
~~~

Tệp **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.7'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'demo.SqlParameterBoundaryDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Tệp **src/main/java/demo/SqlParameterBoundaryDemo.java**:

~~~java
package demo;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class SqlParameterBoundaryDemo {

    record Product(
        long id, String name, String state, BigDecimal price) {}

    enum SortKey {
        NAME("display_name"),
        PRICE("price");

        private final String column;

        SortKey(String column) {
            this.column = column;
        }

        String sqlColumn() {
            return column;
        }
    }

    enum SortDirection {
        ASC, DESC;

        String sqlToken() {
            return name();
        }
    }

    static final class ProductRepository {
        private static final RowMapper<Product> MAPPER =
            (rs, rowNum) -> new Product(
                rs.getLong("id"),
                rs.getString("display_name"),
                rs.getString("product_state"),
                rs.getBigDecimal("price")
            );

        private final JdbcTemplate jdbc;
        private final NamedParameterJdbcTemplate named;

        ProductRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
            this.named = new NamedParameterJdbcTemplate(jdbc);
        }

        int countByName(String name) {
            Integer count = named.queryForObject(
                "SELECT COUNT(*) FROM products " +
                "WHERE display_name = :name",
                Map.of("name", name),
                Integer.class
            );
            return Objects.requireNonNull(count);
        }

        List<Product> findByState(
                String state,
                SortKey sort,
                SortDirection direction) {

            // Chỉ nối token cấu trúc do enum sở hữu.
            String sql =
                "SELECT id, display_name, product_state, price " +
                "FROM products WHERE product_state = ? ORDER BY " +
                sort.sqlColumn() + " " + direction.sqlToken() +
                ", id ASC";

            // state vẫn là giá trị bind qua ?.
            return jdbc.query(sql, MAPPER, state);
        }

        List<Long> findIds(List<Long> ids) {
            if (ids.isEmpty()) {
                return List.of();
            }
            return named.query(
                "SELECT id FROM products " +
                "WHERE id IN (:ids) ORDER BY id",
                Map.of("ids", ids),
                (rs, rowNum) -> rs.getLong("id")
            );
        }

        int updatePrice(long id, BigDecimal price) {
            return jdbc.update(
                "UPDATE products SET price = ? WHERE id = ?",
                price, id
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:param_demo;DB_CLOSE_DELAY=-1",
            "sa",
            ""
        );
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute(
            """
            CREATE TABLE products (
                id BIGINT PRIMARY KEY,
                display_name VARCHAR(100) NOT NULL,
                product_state VARCHAR(20) NOT NULL,
                price DECIMAL(12, 2) NOT NULL
            )
            """
        );

        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            1L, "Bàn phím", "ACTIVE", new BigDecimal("100.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            2L, "Chuột", "ACTIVE", new BigDecimal("40.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            3L, "Màn hình", "INACTIVE", new BigDecimal("250.00")
        );
        jdbc.update(
            "INSERT INTO products VALUES (?, ?, ?, ?)",
            4L, "Tai nghe", "ACTIVE", new BigDecimal("80.00")
        );

        ProductRepository repository = new ProductRepository(jdbc);

        System.out.println(
            "safe name matches: " + repository.countByName("Chuột")
        );

        String payload = "Chuột' OR 1=1 --";
        System.out.println(
            "payload matches: " + repository.countByName(payload)
        );

        List<String> sortedNames = repository.findByState(
                "ACTIVE", SortKey.PRICE, SortDirection.DESC
            ).stream()
            .map(Product::name)
            .toList();
        System.out.println(
            "active by price DESC: " + sortedNames
        );

        System.out.println(
            "ids 1 and 3: " + repository.findIds(List.of(1L, 3L))
        );
        System.out.println(
            "empty id list: " + repository.findIds(List.of())
        );
        System.out.println(
            "updated rows: " +
            repository.updatePrice(2L, new BigDecimal("42.50"))
        );
    }
}
~~~

Chạy với Gradle đã cài:

~~~bash
gradle run
~~~

Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew run
~~~

Trên Windows PowerShell khi có Wrapper:

~~~powershell
.\gradlew.bat run
~~~

Chương trình dùng Java 17 record, text block và Stream.toList(); các thư viện Spring JDBC và H2 được Gradle quản lý. Không chỉ dùng javac đơn lẻ khi chưa cung cấp classpath các dependency này.

**Stdout do chương trình in** (không tính log/build của Gradle):

~~~text
safe name matches: 1
payload matches: 0
active by price DESC: [Bàn phím, Tai nghe, Chuột]
ids 1 and 3: [1, 3]
empty id list: []
updated rows: 1
~~~

Giải thích:

1. Tên Chuột khớp đúng một sản phẩm.
2. Giá trị có dấu nháy và OR 1=1 được bind vào :name như **một chuỗi**, nên không khớp hàng nào; không tạo điều kiện OR.
3. ORDER BY price DESC, id ASC được lắp từ enum **do code định nghĩa**; giá 100, 80, 40 tương ứng Bàn phím, Tai nghe, Chuột.
4. Spring mở rộng hai giá trị ID và trả [1, 3].
5. List rỗng được trả sớm, không sinh IN ().
6. UPDATE chỉ tác động sản phẩm ID 2, nên affected rows là 1.

Demo dùng DriverManagerDataSource cho dễ học, không phải pool kết nối dành cho production. Ứng dụng thực tế thường dùng HikariCP, migration schema, transaction và kiểm soát tenant/authorization riêng.

## 15. Kiểm thử đúng ranh giới giá trị/cấu trúc

| Test | Input | Kỳ vọng |
| --- | --- | --- |
| Tên hợp lệ | Chuột | Một hàng khớp |
| Chuỗi có dấu nháy đơn | Tên chứa ' | Không phá SQL; được so sánh như dữ liệu |
| Chuỗi giống SQL injection | Chuột' OR 1=1 -- | Không làm WHERE mở rộng |
| Sort hợp lệ | price / desc | ORDER BY price DESC |
| Sort field lạ | secret_column | Bị từ chối trước khi tạo SQL |
| Sort chứa cú pháp lạ | price; DROP ... | Bị từ chối, không được nối raw |
| Direction lạ | desc, nulls first; ... | Chỉ token ASC/DESC hợp lệ |
| Report table hợp lệ | products | Chọn bảng cố định được cho phép |
| Report table lạ | users_private | Bị từ chối |
| IN có 2 ID | [1,3] | Hai giá trị được bind |
| IN rỗng | [] | Kết quả rỗng theo hợp đồng |
| LIKE với ký tự % literal | 100% | Wildcard được escape nếu tìm literal |
| SQL NULL | deleted_at null | Nhánh IS NULL có chủ đích |
| Page size quá lớn | 1.000.000 | Bị chặn/giới hạn |
| Bộ lọc tenant | tenant từ ngữ cảnh xác thực | Luôn được giữ trong query |

Không chỉ kiểm thử “query không ném exception”: ORDER BY ? đôi khi vẫn chạy nhưng **sắp xếp không đúng ý định**. Phải kiểm tra thứ tự output trên nhiều hàng; kiểm tra cả đầu vào không được phép, SQL NULL, danh sách rỗng và lỗi DB.

Dùng integration test trên DBMS thật hoặc Testcontainers khi code phụ thuộc cú pháp riêng của PostgreSQL/MySQL/Oracle; H2 không mô phỏng chính xác mọi loại, quy tắc quoting, JSON, array hoặc query planner.

## 16. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| `FROM ?` nhận tên bảng | Marker không thay table identifier |
| `SELECT ?` nhận tên cột | Nó là giá trị, không phải projection của cột |
| `ORDER BY ?` nhận tên cột | Không biến chuỗi "price" thành identifier |
| `ORDER BY price ?` nhận DESC | DESC là SQL keyword |
| `WHERE price ? ?` nhận operator và value | Operator không bind được như dữ liệu |
| Chỉ cần PreparedStatement là toàn câu SQL an toàn | SQL structure nối raw user input vẫn có thể injection |
| Regex tên cột đủ an toàn | Phải allow-list cột được phép cho đúng query |
| Manual escape tương đương binding | Dễ sai theo dialect, không thay binding |
| IN (:ids) nối một chuỗi CSV | Spring mở rộng collection thành các value marker |
| IN rỗng luôn chạy | Có thể tạo SQL không hợp lệ; phải định nghĩa hành vi |
| Bind null vào = ? tìm được SQL NULL | So sánh = NULL không TRUE |
| LIKE parameter không thể match ngoài ý muốn | Wildcard % và _ vẫn hoạt động |
| LIMIT bind an toàn thì page size nào cũng được | Phải giới hạn giá trị để tránh query nặng |
| Identifier quoting thay quyền truy cập | Quoting xử lý cú pháp, không thay authorization |

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao SELECT ... FROM ? không thể dùng tham số "products" như tên bảng?

**Đáp án:** FROM cần table identifier trong SQL structure; marker biểu diễn value, không phân tích lại chuỗi thành tên bảng.

**Câu 2.** Bind "price" vào ORDER BY ? có tương đương ORDER BY price không?

**Đáp án:** Không. Đó là giá trị/biểu thức chứ không phải identifier được thay thế tự động. Dùng allow-list chọn tên cột.

**Câu 3.** Cần direction=desc từ UI, làm thế nào tạo ORDER BY price DESC an toàn?

**Đáp án:** Chuyển đầu vào sang enum hoặc allow-list; thêm literal DESC do chương trình sở hữu vào SQL. Giá trị WHERE vẫn bind riêng.

**Câu 4.** Một repository có WHERE state = ? nhưng nối sortFromRequest vào ORDER BY. SQL injection đã được loại bỏ chưa?

**Đáp án:** Chưa. Chỉ state được bảo vệ; phần ORDER BY nối input trực tiếp vẫn là rủi ro.

**Câu 5.** Trong LIKE ?, người dùng tìm ký tự % thật. Parameter binding có tự escape wildcard không?

**Đáp án:** Không. Bind ngăn injection nhưng % vẫn là wildcard của LIKE. Phải escape wildcard phù hợp dialect nếu muốn tìm literal.

**Câu 6.** Muốn query id IN (1,3,5) với số ID thay đổi, có nên tự nối CSV vào SQL?

**Đáp án:** Không. Dùng collection expansion qua NamedParameterJdbcTemplate/JdbcClient hoặc sinh marker có kiểm soát rồi bind từng ID.

**Câu 7.** Bind NULL cho WHERE deleted_at = ? có tìm mọi hàng deleted_at IS NULL không?

**Đáp án:** Không trong SQL chuẩn. Dùng IS NULL hoặc predicate có ngữ nghĩa NULL đã thiết kế trước.

**Câu 8.** API chọn hai bảng báo cáo products/inventory. Có thể dùng bind parameter cho tên bảng không?

**Đáp án:** Không. Chọn truy vấn tĩnh hoặc allow-list mã báo cáo -> tên bảng do chương trình sở hữu.

**Câu 9.** Vì sao regex chỉ cho chữ cái trong tên cột vẫn không bảo đảm an toàn?

**Đáp án:** Tên hợp lệ về cú pháp có thể trỏ đến cột nhạy cảm/không được API cho phép. Cần allow-list theo nghiệp vụ và kiểm soát quyền.

**Câu 10.** SELECT ? FROM products với chuỗi bind "display_name" có đọc cột display_name không?

**Đáp án:** Không. Nếu DB cho phép câu này, nó coi tham số là giá trị, không phải identifier của cột.

## 18. Checklist khi triển khai repository Spring JDBC

1. Xác định mỗi input là **giá trị** hay **lựa chọn cấu trúc SQL**.
2. Bind tất cả giá trị qua ?/:name, đúng kiểu và đúng thứ tự.
3. Không nối raw user input vào SELECT/FROM/WHERE/ORDER BY/JOIN hoặc DDL.
4. Dùng allow-list/enum cho tên cột, bảng, toán tử và hướng sắp xếp.
5. Bảo đảm mọi nhánh giữ điều kiện tenant/authorization bắt buộc.
6. Xử lý riêng IN-list rỗng/lớn, LIKE wildcard, NULL và giới hạn paging.
7. Không coi identifier quoting, regex hoặc manual escaping là thay thế cho allow-list/binding.
8. Đặt quyền DB tối thiểu; tránh DDL và truy cập dữ liệu không cần thiết.
9. Test đúng thứ tự sort, dữ liệu trả, payload lạ và dialect thực tế.
10. Ưu tiên SQL tĩnh dễ review; chỉ tạo dynamic structure khi nhu cầu nghiệp vụ thực sự đòi hỏi.

**Kết luận:** Parameter binding giúp thay **giá trị có kiểu** trong một câu SQL đã có cấu trúc. Nó không tự thay tên bảng, tên cột hay cú pháp. Khi buộc phải thay cấu trúc, **ứng dụng phải tự chọn từ một tập các token SQL được phép**, rồi tiếp tục bind các giá trị còn lại.

### Tài liệu tham khảo chính thức

- Spring Framework, JDBC Core Classes / NamedParameterJdbcTemplate / JdbcClient: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework, Parameter and Data Value Handling: https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html
- Spring Framework, NamedParameterJdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Java SE 17, PreparedStatement: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html
- OWASP, SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet
- PostgreSQL, PREPARE: https://www.postgresql.org/docs/current/sql-prepare.html
