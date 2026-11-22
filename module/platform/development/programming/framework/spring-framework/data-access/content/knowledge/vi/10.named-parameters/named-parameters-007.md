# Không ghép trực tiếp dữ liệu người dùng vào câu SQL

Khi xây dựng ứng dụng Java/Spring truy cập database, nguyên tắc nền tảng là **không đưa giá trị do người dùng hoặc hệ thống bên ngoài cung cấp trực tiếp vào văn bản SQL bằng phép nối chuỗi, nội suy chuỗi hay định dạng chuỗi**. Thay vào đó, hãy giữ **cấu trúc câu SQL** do ứng dụng kiểm soát và truyền các **giá trị dữ liệu** qua bind parameters.

Trong phần **Tham số có tên** của Spring Framework – data-access, giải pháp rất phù hợp là `NamedParameterJdbcTemplate` với cú pháp `:email`, `:tenantId` hoặc `:status`. Framework sẽ phân tích các tham số có tên và dùng cơ chế parameter binding JDBC tương ứng. Quy tắc này cũng áp dụng cho `JdbcTemplate` với dấu `?` và `PreparedStatement` thuần.

Bài học tập trung vào cách xác định ranh giới **SQL code / SQL data**, ngăn SQL injection bằng tham số hóa, xử lý phần cấu trúc không bind được như `ORDER BY`, và tránh các lỗi dễ bị bỏ sót với `LIKE`, `IN`, `NULL`, truy vấn động và phân quyền.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết việc ghép user input vào SQL tạo rủi ro **SQL injection** và đôi khi chỉ gây lỗi cú pháp, lỗi dữ liệu.
2. Giải thích vì sao bind parameter bảo vệ ranh giới giữa **giá trị** và **cú pháp SQL**.
3. Viết truy vấn có `:namedParameter` và `MapSqlParameterSource`/`Map` bằng Spring `NamedParameterJdbcTemplate`.
4. Dùng `PreparedStatement` với `?` đúng cách nếu không dùng named parameters.
5. Xử lý đúng các trường hợp cần thay đổi **identifier/cấu trúc** như tên cột `ORDER BY`: chỉ chọn từ **allowlist** các fragment cố định.
6. Phân biệt SQL injection với thao túng wildcard khi tìm kiếm `LIKE`; áp dụng `ESCAPE` nếu cần tìm literal.
7. Bind danh sách `IN (:ids)` một cách có kiểm soát; xử lý danh sách rỗng, kiểu dữ liệu và giới hạn database.
8. Thiết kế test chứng minh dữ liệu đầu vào không bị đưa vào câu SQL, đồng thời không để lỗi database bị che giấu.
9. Kết hợp parameterization với authorization, input validation, tài khoản database ít quyền và logging an toàn.

## 2. SQL injection hình thành tại đâu?

Giả sử giao diện cho nhập email để tìm tài khoản:

~~~text
HTTP request: /accounts?email=an@example.test
                         |
                         v
Controller nhận email: String
                         |
                         v
Repository tạo câu SQL
                         |
                         v
Database thực thi SQL
~~~

Một cách viết **sai** là nối email trực tiếp vào SQL:

~~~java
// CHỐNG VÍ DỤ — tuyệt đối không dùng cho input không đáng tin.
String sql =
        "SELECT id, email FROM account WHERE email = '" + email + "'";
List<Account> accounts = jdbcTemplate.query(sql, accountRowMapper);
~~~

Nếu email là `an@example.test`, SQL tạo ra có thể trông như:

~~~sql
SELECT id, email
FROM account
WHERE email = 'an@example.test';
~~~

Nhưng `email` là dữ liệu không đáng tin. Người dùng có thể nhập chuỗi chứa dấu nháy đơn, biểu thức SQL, ký hiệu chú thích hoặc cú pháp khác. Khi ghép chuỗi, những ký tự này trở thành một phần của **văn bản câu lệnh**, thay vì chỉ là nội dung của một giá trị. Ví dụ đầu vào kiểm thử:

~~~text
x' OR '1'='1
~~~

Nếu ghép theo mẫu trên, điều kiện có thể bị thay đổi thành dạng:

~~~sql
WHERE email = 'x' OR '1'='1'
~~~

Điều kiện mới có ý nghĩa khác hẳn điều kiện tìm đúng một email. Đây là ví dụ nhỏ để nhận ra **lỗi ranh giới dữ liệu–câu lệnh**, không phải mô tả mọi kỹ thuật tấn công. Các chi tiết cú pháp, cách xử lý dấu nháy và mức tác động khác nhau theo database/driver và câu truy vấn.

**Điểm quan trọng:** không phải vì chuỗi có dấu nháy đơn nên bản thân nó nguy hiểm. Tên người dùng, địa chỉ hoặc thông báo hoàn toàn có thể chứa dấu nháy hợp lệ. Rủi ro xuất hiện khi **ứng dụng coi dữ liệu là SQL code** thông qua việc tự lắp câu SQL từ giá trị ấy.

### SQL injection không chỉ đến từ ô tìm kiếm

Dữ liệu không đáng tin có thể đến từ:

- Query string, form, JSON body, HTTP header, cookie, đường dẫn URL.
- Giá trị lọc, sort field, sort direction, danh sách ID, ngưỡng giá và mã trạng thái.
- Tên file, nội dung upload, message từ queue, thông tin của bên thứ ba.
- Dữ liệu đã được lưu trong database rồi được sử dụng để dựng câu SQL về sau (*second-order SQL injection*).
- Cấu hình do tenant/người dùng chỉnh sửa hoặc chuỗi lấy từ cache và hệ thống tích hợp.

Một giá trị đi qua nhiều lớp Java hay đã nằm trong database **không tự trở thành đáng tin**. Điều quyết định là nó có được phép ảnh hưởng tới cấu trúc SQL hay chỉ được dùng như **giá trị tham số**.

## 3. Ranh giới đúng: SQL template + bind values

Thay vì nối nội dung trực tiếp:

~~~java
String sql = "SELECT id, email FROM account WHERE email = '" + email + "'";
~~~

hãy giữ SQL template cố định và truyền giá trị riêng:

~~~java
String sql =
        "SELECT id, email FROM account WHERE email = :email";
MapSqlParameterSource parameters =
        new MapSqlParameterSource("email", email);

List<Account> accounts =
        namedJdbc.query(sql, parameters, accountRowMapper);
~~~

Đây là đoạn **minh họa bên trong repository đã có các biến `namedJdbc` và `accountRowMapper`**, không phải chương trình Java độc lập. Về cơ chế:

1. Ứng dụng kiểm soát SQL template chứa marker `:email`.
2. `MapSqlParameterSource` mang giá trị của tham số `email` tách khỏi văn bản SQL.
3. `NamedParameterJdbcTemplate` chuyển marker tên sang cơ chế binding JDBC do driver xử lý.
4. Database được yêu cầu thực thi câu lệnh với **một giá trị dữ liệu**; dấu nháy và nội dung của email không tự trở thành toán tử hoặc mệnh đề SQL.

Hãy hình dung:

~~~text
SQL TEMPLATE:   SELECT id, email FROM account WHERE email = :email

BIND DATA:      email -> "x' OR '1'='1"

DATABASE:       Điều kiện email = [một giá trị chuỗi đã bind]
                Không phải điều kiện email = 'x' OR ...
~~~

Việc bind không chỉ dành cho chuỗi: số nguyên, ngày tháng, boolean, UUID và nhiều kiểu dữ liệu khác cũng cần đi qua cơ chế parameter binding. Đưa numeric input vào SQL bằng nối chuỗi chỉ vì “nó là số” vẫn là thói quen dễ gây lỗi; dữ liệu số phải được parse/validate và bind đúng kiểu.

**Phạm vi bảo vệ:** prepared/named parameters ngăn **giá trị bind** thay đổi cú pháp SQL ở vị trí được phép bind. Chúng không tự bảo vệ những fragment SQL vẫn được ghép trực tiếp như tên bảng, tên cột, điều kiện sort hoặc câu SQL do người dùng nhập toàn bộ. Những vị trí đó cần thiết kế riêng.

## 4. Ví dụ dữ liệu và hợp đồng truy vấn

Giả sử ứng dụng nhiều tenant có bảng `account`:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(200) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

Một repository cần:

- Tìm tài khoản theo email trong tenant đã được xác thực.
- Lọc theo trạng thái, tìm kiếm tên và sắp xếp.
- Cập nhật display name hoặc trạng thái mà không để dữ liệu người dùng thay đổi câu SQL.
- Không thể tự đổi sang tenant khác chỉ nhờ thay một tham số từ request.

SQL an toàn cho thao tác đầu tiên:

~~~sql
SELECT id, email, display_name, status, created_at
FROM account
WHERE tenant_id = :tenantId
  AND email = :email;
~~~

Tại Java:

~~~java
var parameters = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("email", requestedEmail);
~~~

Với ví dụ trên, `authorizedTenantId` nên được xác định từ context phân quyền đã được kiểm chứng của ứng dụng, **không lấy nguyên xi từ trường `tenantId` do người dùng tự gửi mà không xác thực quyền**. Parameterization ngăn SQL injection nhưng không thay thế **authorization**.

## 5. Spring NamedParameterJdbcTemplate: cách dùng cơ bản

Spring Framework cung cấp `org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate`. Các tham số có tên dùng cú pháp `:parameterName` bên trong SQL template, ví dụ `:email`, `:id`, `:status`. Nguồn giá trị có thể là `Map<String, ?>` hoặc implementation của `SqlParameterSource` như `MapSqlParameterSource`.

### 5.1. Cấu hình bean

Trong Spring application context đã có bean `DataSource`:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

@Configuration
public class DataAccessConfig {
    @Bean
    public NamedParameterJdbcTemplate namedJdbc(DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }
}
~~~

Đây là **class cấu hình tích hợp Spring**, cần module `spring-context`, `spring-jdbc`, một `DataSource` hoạt động và JDBC driver. Nó không tự tạo database hay tự chạy bằng lệnh `java DataAccessConfig`.

`NamedParameterJdbcTemplate` bọc cơ chế `JdbcTemplate` thông thường; nó phân tích SQL có tên tham số rồi thực hiện binding theo các vị trí tương ứng. Vì thế an toàn đến từ **không chèn untrusted value vào SQL text**, chứ không đến từ bản thân dấu hai chấm `:` nếu chuỗi SQL vẫn bị ghép tùy ý ở nơi khác.

### 5.2. SELECT với MapSqlParameterSource

Một method trong repository đã được inject `NamedParameterJdbcTemplate namedJdbc`:

~~~java
public List<Account> findByEmail(long tenantId, String email) {
    String sql = """
            SELECT id, email, display_name, status, created_at
            FROM account
            WHERE tenant_id = :tenantId
              AND email = :email
            """;

    var parameters = new MapSqlParameterSource()
            .addValue("tenantId", tenantId)
            .addValue("email", email);

    return namedJdbc.query(
            sql,
            parameters,
            (rs, rowNum) -> new Account(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
            )
    );
}
~~~

Ví dụ giả định record `Account(long id, String email, String displayName)` đã khai báo; method là **đoạn tích hợp**, cần database. Quan trọng: các biến `tenantId`, `email` chỉ đi vào `parameters`, không đi vào SQL text. `RowMapper` xử lý kết quả, không thay đổi cách tham số được bind.

Nếu cần một hàng theo khóa duy nhất, có thể dùng API tra cứu tương ứng và xử lý 0/many rows theo hợp đồng. Tránh bắt mọi `DataAccessException` rồi trả danh sách rỗng, vì làm vậy có thể che lỗi kết nối hay câu SQL.

### 5.3. Dùng Map đơn giản

Nếu các giá trị đều không NULL, có thể dùng `Map.of`:

~~~java
String sql = """
        SELECT id FROM account
        WHERE tenant_id = :tenantId AND status = :status
        """;

Map<String, Object> params =
        Map.of("tenantId", tenantId, "status", status);

List<Long> ids = namedJdbc.query(
        sql,
        params,
        (rs, rowNum) -> rs.getLong("id")
);
~~~

**Lưu ý:** `Map.of(...)` trong Java không cho phép key hoặc value null. Khi nghiệp vụ có giá trị nullable, hãy dùng `MapSqlParameterSource` để bind NULL một cách tường minh, có thể đăng ký kiểu SQL nếu cần.

## 6. INSERT/UPDATE/DELETE an toàn với tham số có tên

Không chỉ `SELECT` mới cần parameterization. Câu lệnh thay đổi dữ liệu cần tuân thủ cùng nguyên tắc.

### INSERT

~~~java
String sql = """
        INSERT INTO account
            (id, tenant_id, email, display_name, status, created_at)
        VALUES
            (:id, :tenantId, :email, :displayName, :status, :createdAt)
        """;

var params = new MapSqlParameterSource()
        .addValue("id", accountId)
        .addValue("tenantId", authorizedTenantId)
        .addValue("email", requestedEmail)
        .addValue("displayName", requestedDisplayName)
        .addValue("status", "ACTIVE")
        .addValue("createdAt", createdAtTimestamp);

int inserted = namedJdbc.update(sql, params);
~~~

Đây là đoạn tích hợp có biến nghiệp vụ đã tồn tại, không phải class độc lập. Nó tránh tự đặt dấu nháy quanh tên hoặc email; JDBC driver nhận các giá trị theo kiểu tương ứng. `inserted` là số hàng bị ảnh hưởng theo hợp đồng driver cho câu lệnh update này; ràng buộc khóa, uniqueness và quyền database vẫn phải được thiết lập riêng.

### UPDATE

~~~java
String sql = """
        UPDATE account
        SET display_name = :displayName,
            status = :status
        WHERE id = :id
          AND tenant_id = :tenantId
        """;

var params = new MapSqlParameterSource()
        .addValue("displayName", requestedDisplayName)
        .addValue("status", newStatus)
        .addValue("id", accountId)
        .addValue("tenantId", authorizedTenantId);

int affected = namedJdbc.update(sql, params);
~~~

Tên tham số thể hiện vai trò của từng giá trị. Nếu SQL đổi thứ tự `SET` và `WHERE`, mapping theo tên giúp giảm lỗi bind nhầm vị trí so với đếm dấu `?` thủ công.

**Tuy nhiên**, việc bind `newStatus` không có nghĩa mọi chuỗi status đều hợp lệ. Service/domain vẫn nên kiểm tra status thuộc tập trạng thái cho phép, ví dụ `ACTIVE`, `SUSPENDED`, và caller có quyền thay đổi trạng thái.

### DELETE

~~~java
String sql =
        "DELETE FROM account WHERE id = :id AND tenant_id = :tenantId";

int affected = namedJdbc.update(
        sql,
        Map.of("id", accountId, "tenantId", authorizedTenantId)
);
~~~

Đừng cho phép request tự chỉ định tenant tùy ý chỉ vì tham số đã được bind an toàn. Nếu quên điều kiện authorization hoặc thiếu kiểm tra role, đó là **lỗi phân quyền** khác SQL injection.

## 7. JdbcTemplate với dấu hỏi cũng an toàn nếu không ghép dữ liệu

Khi không cần named parameters, dùng `JdbcTemplate` và positional marker `?`:

~~~java
String sql =
        "SELECT id FROM account WHERE tenant_id = ? AND email = ?";

List<Long> ids = jdbcTemplate.query(
        sql,
        (rs, rowNum) -> rs.getLong("id"),
        authorizedTenantId,
        requestedEmail
);
~~~

Các giá trị được truyền riêng theo đúng **thứ tự marker**, không nối vào SQL text. Tương tự với JDBC thuần:

~~~java
String sql =
        "SELECT id FROM account WHERE tenant_id = ? AND email = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setString(2, requestedEmail);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long accountId = rs.getLong("id");
            // Xử lý accountId.
        }
    }
}
~~~

Đoạn JDBC này cần imports và `DataSource` có sẵn, không phải CLI hoàn chỉnh. JDBC parameter indexes **bắt đầu từ 1**. Spring `NamedParameterJdbcTemplate` giúp không phải đếm bằng tay, nhưng không có “an toàn hơn tuyệt đối” so với `PreparedStatement` được dùng đúng: cả hai phụ thuộc việc code **tách giá trị khỏi SQL**.

### Không thay prepared statement bằng Statement cho dữ liệu động

Chống ví dụ:

~~~java
String sql =
        "SELECT id FROM account WHERE email = '" + requestedEmail + "'";

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(sql)) {
    // Câu SQL đã bị ảnh hưởng bởi requestedEmail.
}
~~~

Ngay cả khi trước đó áp dụng một số kiểm tra ký tự, cách nối vẫn dễ sai khi yêu cầu thay đổi, có Unicode, quotes hoặc dialect khác. Đừng dùng `Statement` để tự nội suy dữ liệu nếu có thể bind.

## 8. Ví dụ Java 17 chạy độc lập: SQL template tách khỏi dữ liệu

Chương trình bên dưới không yêu cầu Spring hoặc database. Nó minh họa hai điều:

1. **Email luôn nằm trong map dữ liệu bind**, không xuất hiện trong SQL template.
2. **Tên cột để ORDER BY phải là fragment cố định đã được allowlist**; chuỗi không hợp lệ bị từ chối.

Lưu file **`SafeSqlPlanDemo.java`**:

~~~java
import java.util.Map;

public class SafeSqlPlanDemo {
    record SqlPlan(String sql, Map<String, Object> parameters) {}

    static String sortColumn(String requested) {
        return switch (requested) {
            case "created" -> "created_at";
            case "email" -> "email";
            default -> throw new IllegalArgumentException("Unsupported sort field");
        };
    }

    static SqlPlan build(String userEmail, String sort, boolean ascending) {
        String sql = "SELECT id, email FROM account WHERE email = :email ORDER BY "
                + sortColumn(sort)
                + (ascending ? " ASC" : " DESC");
        return new SqlPlan(sql, Map.of("email", userEmail));
    }

    public static void main(String[] args) {
        String supplied = "x' OR '1'='1";
        SqlPlan plan = build(supplied, "created", false);
        System.out.println("SQL: " + plan.sql());
        System.out.println("Bound email: " + plan.parameters().get("email"));
        System.out.println("Input inside SQL: " + plan.sql().contains(supplied));
        try {
            build("a@example.test", "email; DROP TABLE account", true);
        } catch (IllegalArgumentException expected) {
            System.out.println("Invalid sort rejected");
        }
    }
}
~~~

Biên dịch và thực thi với Java 17+:

~~~bash
javac --release 17 SafeSqlPlanDemo.java
java SafeSqlPlanDemo
~~~

Stdout chính xác của ví dụ:

~~~text
SQL: SELECT id, email FROM account WHERE email = :email ORDER BY created_at DESC
Bound email: x' OR '1'='1
Input inside SQL: false
Invalid sort rejected
~~~

**Giới hạn minh bạch:** `SqlPlan` ở đây chỉ là record Java để biểu diễn **ý định** ghép một template đáng tin với tập giá trị bind; chương trình **chưa gọi JDBC hoặc Spring**, chưa mở kết nối và chưa chứng minh SQL có thể chạy với một database cụ thể. Khi đưa vào ứng dụng thật, phải truyền `plan.sql()` và `plan.parameters()` cho API parameterized như `NamedParameterJdbcTemplate.query(...)`. Chương trình kiểm chứng thành công việc **không đưa input vào SQL text** và **không tin tên cột tuỳ ý** ngay tại tầng dựng câu lệnh.

Không coi việc kiểm tra `plan.sql().contains(input) == false` là phép chứng minh an toàn tổng quát cho một hệ thống: dữ liệu có thể được ghép từ nguồn khác, các query khác vẫn có lỗi và authorization vẫn độc lập.

## 9. Identifier và cấu trúc SQL: parameter không thay tên bảng/cột

Đây là điểm dễ hiểu nhầm nhất khi học named parameters. Dấu `:value` đại diện cho **giá trị dữ liệu**, không phải chỗ để chèn tùy ý một đoạn SQL.

**Câu đúng:**

~~~sql
SELECT id, email FROM account WHERE email = :email;
~~~

**Câu sai ý định:**

~~~sql
SELECT id, email FROM account ORDER BY :sortColumn;
~~~

Ở câu thứ hai, `:sortColumn` là **giá trị bind**, không được database hiểu như identifier tên cột. Trên một số dialect, câu lệnh có thể hợp lệ về cú pháp nhưng thực chất sắp xếp theo một biểu thức hằng, dẫn tới kết quả không như mong muốn; trên dialect khác có thể bị từ chối. Nó không phải cách portable để chọn cột động.

Tương tự, không bind trực tiếp tên bảng trong `FROM :tableName`, tên cột trong `SELECT :columnName` với kỳ vọng biến thành identifier, hoặc nguyên mệnh đề `WHERE :filterSql`. Binding được thiết kế cho **data values**, không cho SQL code.

### Cách làm đúng: mapping từ khóa nghiệp vụ sang fragment cố định

Giả sử request có `sort=created` hoặc `sort=email`. Chỉ chấp nhận hai tên này:

~~~java
private static String sortColumn(String requested) {
    return switch (requested) {
        case "created" -> "created_at";
        case "email" -> "email";
        default -> throw new IllegalArgumentException("Invalid sort field");
    };
}
~~~

Sau đó:

~~~java
String orderColumn = sortColumn(requestedSort);
String direction = ascending ? "ASC" : "DESC";

String sql =
        "SELECT id, email FROM account WHERE tenant_id = :tenantId "
      + "ORDER BY " + orderColumn + " " + direction + ", id ASC";
~~~

Tại đây có **nối chuỗi SQL**, nhưng hai fragment được nối là **giá trị cố định do ứng dụng lựa chọn** từ allowlist, không phải untrusted raw text. Đây là tình huống cấu trúc SQL buộc phải được xây linh hoạt mà vẫn kiểm soát được nguồn và phạm vi của mọi fragment. Tiêu chí không phải “cấm mọi phép nối chuỗi” mà là **không nối dữ liệu không đáng tin vào vị trí có thể thay đổi cú pháp SQL**.

Nếu có nhiều tùy chọn, có thể dùng enum với mapping cố định. Không coi việc chỉ kiểm tra `sort.matches("[a-zA-Z_]+")` là đủ: chuỗi gồm toàn chữ cái vẫn có thể là tên cột không được phép lộ/đọc, hoặc thay đổi behavior query. **Allowlist lựa chọn nghiệp vụ** giúp kiểm soát cả bảo mật lẫn hợp đồng API.

### Sort direction, LIMIT và OFFSET

- Direction cũng là **SQL keyword**, nên phải chọn từ các giá trị cố định `ASC` hoặc `DESC` theo boolean/enum đã parse, không đưa raw `direction` từ request vào SQL.
- `LIMIT`/`OFFSET` có cú pháp và khả năng parameter binding khác nhau theo database/driver; ở dialect có hỗ trợ `LIMIT :limit OFFSET :offset`, giá trị numeric nên được parse thành số, giới hạn phạm vi hợp lý và bind.
- Bất kể SQL có hỗ trợ bind paging hay không, vẫn cần giới hạn `pageSize` để tránh request tiêu thụ quá nhiều tài nguyên. SQL injection prevention không thay kiểm soát tải.

## 10. Ví dụ Spring repository an toàn với filter + sort

Mẫu dưới đây kết hợp giá trị bind và allowlist identifier. Giả định schema `account` đã nêu, môi trường hỗ trợ `LIKE ... ESCAPE '!'` và bean `NamedParameterJdbcTemplate` đã được cấu hình.

~~~java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountSearchRepository {
    public record AccountView(long id, String email, Instant createdAt) {}

    private final NamedParameterJdbcTemplate jdbc;

    public AccountSearchRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private static String sortColumn(String requested) {
        return switch (requested) {
            case "created" -> "created_at";
            case "email" -> "email";
            default -> throw new IllegalArgumentException("Unknown sort field");
        };
    }

    private static String escapeLikeLiteral(String raw) {
        Objects.requireNonNull(raw);
        return raw.replace("!", "!!")
                  .replace("%", "!%")
                  .replace("_", "!_");
    }

    public List<AccountView> search(
            long authorizedTenantId,
            String requestedEmailPart,
            String requestedSort,
            boolean ascending) {

        String column = sortColumn(requestedSort);
        String direction = ascending ? "ASC" : "DESC";

        String sql = """
                SELECT id, email, created_at
                FROM account
                WHERE tenant_id = :tenantId
                  AND LOWER(email) LIKE LOWER(:pattern) ESCAPE '!'
                ORDER BY """ + column + " " + direction + ", id ASC";

        var params = new MapSqlParameterSource()
                .addValue("tenantId", authorizedTenantId)
                .addValue("pattern", "%" +
                        escapeLikeLiteral(requestedEmailPart) + "%");

        return jdbc.query(sql, params, (rs, rowNum) ->
                new AccountView(
                        rs.getLong("id"),
                        rs.getString("email"),
                        rs.getTimestamp("created_at").toInstant()
                )
        );
    }
}
~~~

Đây là **class tích hợp Spring**, không phải chương trình chạy độc lập. Để chạy cần Spring JDBC, schema/database tương ứng và bean `NamedParameterJdbcTemplate`. `Timestamp.toInstant()` ở đây giả định `created_at NOT NULL`. SQL `ESCAPE '!'` sử dụng cú pháp SQL phổ biến nhưng cần kiểm thử theo dialect thực tế.

Vì sao đoạn này tránh việc ghép user data vào SQL?

- `authorizedTenantId` đi vào `:tenantId` như data value.
- Nội dung tìm kiếm đi vào `:pattern`; trước đó chỉ được biến đổi thành literal search pattern.
- `requestedSort` chỉ được sử dụng **sau khi ánh xạ** sang hai identifier cố định `created_at` hoặc `email`.
- `ascending` chỉ chọn giữa hai keyword cố định.
- Không có đường nào đưa trực tiếp email, chuỗi tìm kiếm hoặc tên sort nguyên xi vào cấu trúc SQL.

Dù vậy, repository không tự xác thực quyền tenant: lớp gọi phải truyền `authorizedTenantId` được lấy từ authentication/authorization context thực. Thêm nữa, `requestedEmailPart` có thể rất dài; tầng API nên giới hạn độ dài, chuẩn hóa hành vi tìm kiếm và bảo vệ database khỏi truy vấn chi phí lớn.

## 11. LIKE: bind parameter chống injection nhưng không tự vô hiệu wildcard

Một lỗi dễ bỏ qua là:

~~~sql
SELECT id FROM account WHERE display_name LIKE :pattern;
~~~

Nếu code bind:

~~~java
params.addValue("pattern", "%" + userSearch + "%");
~~~

thì SQL injection vẫn được phòng tránh **ở vị trí bind**, nhưng bản thân `%` và `_` trong `userSearch` vẫn có nghĩa **wildcard của LIKE**:

- `%` thường khớp chuỗi ký tự bất kỳ, kể cả chuỗi rỗng.
- `_` thường khớp một ký tự.
- Dấu escape phụ thuộc cú pháp/dialect được dùng.

Nếu giao diện **cố ý hỗ trợ wildcard** thì hành vi này có thể đúng. Nếu muốn người dùng tìm **nguyên văn** chuỗi `a_b` hoặc `50%`, phải escape LIKE metacharacters theo cú pháp database.

Ví dụ chọn ký tự `!` làm escape:

~~~sql
SELECT id FROM account
WHERE display_name LIKE :pattern ESCAPE '!';
~~~

Java:

~~~java
private static String escapeLikeLiteral(String input) {
    return input.replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
}

String pattern = "%" + escapeLikeLiteral(userSearch) + "%";
var params = new MapSqlParameterSource("pattern", pattern);
~~~

Với `userSearch = "50%"`, biến `pattern` có dạng `%50!%%`: hai dấu `%` ngoài là wildcard dùng để tìm đoạn con, `!%` bên trong biểu diễn **một dấu phần trăm literal**. Dấu `!` tự nó cũng được escape thành `!!` trước. Lời gọi `replace` chỉ xử lý **ngữ nghĩa LIKE pattern**, không thay cho parameter binding. Pattern cuối cùng vẫn phải bind qua `:pattern`.

**Không “lọc bỏ mọi ký tự đặc biệt” để chống injection.** Ví dụ họ tên có dấu nháy, phần trăm trong nội dung hoặc ký tự Unicode là dữ liệu hợp lệ. Chính parameterization bảo vệ ranh giới code/data, còn validation và LIKE escaping thể hiện yêu cầu nghiệp vụ riêng.

## 12. IN (:ids): danh sách giá trị không phải một chuỗi SQL

Với Spring `NamedParameterJdbcTemplate`, có thể bind collection để tạo các positional placeholders phù hợp với danh sách `IN`:

~~~java
String sql = """
        SELECT id, email
        FROM account
        WHERE tenant_id = :tenantId
          AND id IN (:ids)
        """;

List<Long> ids = List.of(10L, 20L, 30L);

var params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId)
        .addValue("ids", ids);

List<Long> selected = namedJdbc.query(
        sql, params, (rs, rowNum) -> rs.getLong("id")
);
~~~

Spring sẽ mở rộng collection thành các bind markers tương ứng rồi bind **mỗi phần tử như dữ liệu**. Không tạo chuỗi `"10,20,30"` và nối vào `IN (...)`. Không tin trực tiếp một CSV do người dùng nhập làm SQL fragment. Nếu nhận `ids` từ HTTP, hãy parse thành `List<Long>` có kiểm tra số lượng, khoảng giá trị và quyền truy cập từng bản ghi.

### Danh sách rỗng

Một danh sách rỗng không được xử lý giống danh sách có một phần tử. SQL `IN ()` có thể không hợp lệ hoặc có behavior theo dialect. Hãy xác định nghiệp vụ trước:

~~~java
if (ids.isEmpty()) {
    return List.of();  // Nếu "không ID" có nghĩa "không hàng".
}
~~~

Đoạn này thuộc method trả `List<?>`, là nhánh xử lý nghiệp vụ minh họa. Với hệ thống thực, cũng cần giới hạn kích thước danh sách: database/driver có thể có giới hạn số bind parameters hoặc kích thước câu SQL; tập hàng chục nghìn ID có thể đòi batching, temporary table hay một giải pháp khác tùy hệ quản trị.

### Không chèn danh sách SQL do người dùng cung cấp

Chống ví dụ:

~~~java
String sql = "SELECT id FROM account WHERE id IN (" + rawIdsCsv + ")";
~~~

Ngay cả khi chuỗi đầu vào thường chỉ có số, nó vẫn bị chèn vào SQL text. Cách đúng là parse thành giá trị có kiểu và bind từng phần tử hoặc dùng hỗ trợ collection binding của Spring.

## 13. SQL NULL và kiểu tham số

Khi giá trị đầu vào là Java `null`, không thể dùng `Map.of("note", null)` vì Java `Map.of` không chấp nhận null. `MapSqlParameterSource` có thể biểu diễn NULL và đăng ký SQL type:

~~~java
import java.sql.Types;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

var params = new MapSqlParameterSource()
        .addValue("id", accountId)
        .addValue("note", optionalNote, Types.VARCHAR);

String sql =
        "UPDATE account_note SET note = :note WHERE account_id = :id";

int affected = namedJdbc.update(sql, params);
~~~

Giả định bảng `account_note` và các biến đã tồn tại. `Types.VARCHAR` biểu diễn kiểu SQL của `note`; cung cấp kiểu có thể quan trọng với một số JDBC driver hoặc câu SQL có tham số NULL.

**NULL cũng là một giá trị bind** trong contract của câu SQL. Không bỏ hẳn dấu marker rồi nối `"NULL"` bằng chuỗi để xử lý một trường hợp, trừ khi cố ý thay cấu trúc SQL bằng template đáng tin. Với điều kiện lọc, `column = NULL` không chọn các hàng SQL NULL theo logic SQL chuẩn; cần dùng `IS NULL` hoặc thiết kế điều kiện phù hợp:

~~~sql
-- Tìm hàng mà note thật sự là SQL NULL:
SELECT account_id FROM account_note WHERE note IS NULL;
~~~

Không phải mọi trường nullable đều được biểu diễn bằng `column = :value` với `value = null`. Đây là **vấn đề semantics SQL**, không phải việc bind thiếu an toàn.

## 14. Truy vấn động: kết hợp fragment đáng tin thay vì raw input

Ứng dụng đôi khi cần thêm/bớt điều kiện tìm kiếm. Cách làm sai là cho phép client truyền cả đoạn SQL:

~~~java
// CHỐNG VÍ DỤ:
String sql = "SELECT id FROM account WHERE " + userSuppliedWhereClause;
~~~

Với thiết kế này, user input điều khiển trực tiếp cú pháp SQL. Thay vào đó, hãy bật/tắt **những fragment do ứng dụng đã định nghĩa** và bind giá trị:

~~~java
StringBuilder sql = new StringBuilder(
        "SELECT id FROM account WHERE tenant_id = :tenantId");

var params = new MapSqlParameterSource()
        .addValue("tenantId", authorizedTenantId);

if (requestedStatus != null) {
    sql.append(" AND status = :status");
    params.addValue("status", requestedStatus);
}

if (minimumId != null) {
    sql.append(" AND id >= :minimumId");
    params.addValue("minimumId", minimumId);
}

List<Long> ids = namedJdbc.query(
        sql.toString(), params,
        (rs, rowNum) -> rs.getLong("id")
);
~~~

Đây là đoạn tích hợp, cần khai báo trước `requestedStatus`, `minimumId` và các bean/dữ liệu liên quan. Chỉ có **literal SQL do developer kiểm soát** được append. Dữ liệu vẫn nằm trong `params`. Nếu thêm điều kiện, hãy đảm bảo marker có giá trị tương ứng và không để filter cố định quan trọng như `tenant_id` bị bỏ qua.

### Không dùng “chỉ cho phép chữ/số” thay thế binding

Một input validation rule như `[a-zA-Z0-9]+` có thể phù hợp cho một mã định danh nghiệp vụ bị giới hạn định dạng. Nhưng nó **không phải** lớp bảo vệ thay cho SQL parameters vì:

- Nhiều dữ liệu hợp lệ chứa ký tự ngoài biểu thức này.
- Một thay đổi về schema/dialect hoặc cách ghép SQL có thể làm rule không còn đúng.
- Nó không giải quyết quyền người dùng đối với tài nguyên, giới hạn cardinality hoặc column identifiers.

Dùng validation để xác định **dữ liệu hợp lệ theo domain** (độ dài, định dạng, tập trạng thái cho phép, giới hạn số lượng). Dùng parameterization để xác định **cách dữ liệu tham gia SQL**.

## 15. Query builders, JPA và ORM: vẫn phải giữ nguyên tắc

Bài tập trung vào Spring JDBC, nhưng nguyên tắc lan sang những abstraction khác:

- Với JPQL/HQL hoặc native query trong JPA, dùng **parameter binding** của query API, không tự nối chuỗi từ input.
- Với Spring Data repositories có câu query chứa `:email` hoặc method query được framework sinh ra, kiểm tra vẫn có bind, không có đoạn raw SQL/JPQL được nối từ user input.
- Với query DSL hoặc ORM hỗ trợ expression tree, sử dụng API truyền **giá trị tham số**, tránh các chức năng “raw SQL”/“literal fragment” nhận untrusted input.
- Dynamic identifier vẫn phải được chọn từ cấu hình có kiểm soát; ORM không mặc nhiên bảo vệ mọi hàm cho phép chèn nguyên SQL fragment.

Ví dụ với JPA (đoạn tích hợp; `entityManager` và entity `AccountEntity` đã được cấu hình):

~~~java
var query = entityManager.createQuery(
        "SELECT a FROM AccountEntity a WHERE a.email = :email",
        AccountEntity.class
);
query.setParameter("email", requestedEmail);
List<AccountEntity> result = query.getResultList();
~~~

Không đổi thành:

~~~java
// CHỐNG VÍ DỤ:
String jpql = "SELECT a FROM AccountEntity a WHERE a.email = '"
              + requestedEmail + "'";
~~~

Một ORM không thể sửa lỗi nếu lập trình viên đưa untrusted input vào cấu trúc query trước khi nó được parse.

## 16. JdbcClient với named parameters (Spring Framework 6.1+)

Spring Framework 6.1 giới thiệu `JdbcClient` như một giao diện fluent có khả năng làm việc với cả positional và named parameters. Đoạn minh họa trong ứng dụng có bean `JdbcClient jdbcClient`:

~~~java
List<Long> ids = jdbcClient.sql("""
        SELECT id
        FROM account
        WHERE tenant_id = :tenantId
          AND email = :email
        """)
        .param("tenantId", authorizedTenantId)
        .param("email", requestedEmail)
        .query((rs, rowNum) -> rs.getLong("id"))
        .list();
~~~

Đây là một **phương án API khác** để bind giá trị, không phải cách thay đổi SQL injection threat model. SQL vẫn cần là template đáng tin; `param("email", requestedEmail)` giữ email ở vị trí dữ liệu. Khi đọc code theo nhiều phiên bản Spring, bạn có thể thấy `NamedParameterJdbcTemplate` hoặc `JdbcClient`; hãy kiểm tra phiên bản dependency của project trước khi áp dụng ví dụ.

## 17. Tránh các phương pháp “tự escape mọi thứ”

### Ghép giá trị sau khi thay dấu nháy là giải pháp mong manh

Chống ví dụ:

~~~java
// CHỐNG VÍ DỤ: không xem việc tự thay dấu nháy là biện pháp bảo vệ chung.
String escaped = requestedEmail.replace("'", "''");
String sql = "SELECT id FROM account WHERE email = '" + escaped + "'";
~~~

Ngay cả khi quy tắc thay dấu nháy hợp với một tình huống SQL cụ thể, cách này buộc ứng dụng phải tự hiểu đầy đủ escaping, encoding, dialect, type conversion, cú pháp literal và các ngữ cảnh SQL khác nhau. Quy tắc của một **string literal** không dùng được cho **identifier**, **number**, **JSON path**, **ORDER BY** hoặc các loại SQL fragment khác.

**Giải pháp bền vững:** giữ SQL template cố định và bind giá trị bằng driver/framework. Không tự tạo “hàm chống SQL injection” bằng cách nối sau khi thay vài ký tự. Cũng đừng dùng HTML escaping, URL encoding hoặc JSON escaping rồi coi đó là SQL escaping: mỗi lớp có ngữ pháp khác nhau.

### Cẩn trọng khi diễn giải “đã dùng PreparedStatement”

Một chương trình có thể dùng `PreparedStatement` nhưng **vẫn tạo SQL bằng nối chuỗi trước khi prepare**:

~~~java
// CHỐNG VÍ DỤ: PreparedStatement không sửa được SQL đã bị ghép nguy hiểm.
String sql =
        "SELECT id FROM account WHERE email = '" + requestedEmail + "'";
PreparedStatement ps = connection.prepareStatement(sql);
~~~

Dùng đúng class Java không đủ; câu hỏi phải là: **input có nằm trong SQL text hay chỉ đi vào setter/bind map?** Nếu input đã chen vào SQL string, việc gọi `prepareStatement(sql)` không tự biến nó thành parameter.

### Cẩn trọng khi diễn giải “đã dùng named parameter”

Ví dụ vẫn sai:

~~~java
// CHỐNG VÍ DỤ: status được bind, nhưng email vẫn bị ghép.
String sql = "SELECT id FROM account WHERE email = '"
           + requestedEmail + "' AND status = :status";
namedJdbc.query(sql, Map.of("status", requestedStatus), rowMapper);
~~~

Bảo vệ **một tham số** không bảo vệ tự động **toàn bộ câu SQL**. Mọi input có thể ảnh hưởng query phải được kiểm tra theo đường dữ liệu riêng.

## 18. Vì sao parameterization không giải quyết mọi vấn đề bảo mật?

**SQL injection prevention** là một ranh giới quan trọng, nhưng không nên đồng nhất với việc một endpoint “an toàn toàn diện”:

| Rủi ro | Parameterization hỗ trợ gì? | Cần thêm gì? |
| --- | --- | --- |
| Input thay đổi cú pháp SQL ở value position | Ngăn biến value thành SQL code | Không nối raw input ở nơi khác |
| User đọc dữ liệu của tenant khác | Không tự xác định quyền đọc | Authorization và ràng buộc tenant đáng tin |
| User yêu cầu sort bằng cột nhạy cảm | Không bind identifier được | Allowlist field/column ở application |
| Query tải quá nhiều hàng | Không giới hạn cardinality | Pagination, quota, query/timeouts, indexes |
| LIKE wildcard gây truy vấn rộng | Wildcard vẫn có semantics LIKE | Escape literal, limit pattern, design search |
| User chọn tên bảng động | Bind không biến text thành identifier | Mapping cố định hoặc query templates |
| Tài khoản DB có quyền quá lớn | Không giảm quyền DB | Least-privilege roles và secret management |
| Thông tin nhạy cảm trong log | Không tự che log | Redaction/masking, quyền log, retention |
| Business logic update sai hàng | Không sửa điều kiện nghiệp vụ | Test, authorization, đúng WHERE/transaction |

Ví dụ: `SELECT * FROM account WHERE tenant_id = :tenantId` là SQL injection-safe ở value position. Nhưng nếu `tenantId` được lấy trực tiếp từ body của một user không có quyền truy cập tenant ấy, endpoint vẫn có thể **lộ dữ liệu do thiếu kiểm tra quyền**. Đây là lỗi authorization, không phải SQL injection; cần xử lý riêng.

## 19. Logging và xử lý lỗi không làm lộ dữ liệu

Khi chẩn đoán query, nên ghi lại **SQL template** và ngữ cảnh kỹ thuật cần thiết (service, trace ID, loại câu lệnh, thời gian, số hàng, tên statement) nếu chính sách cho phép. Hạn chế log giá trị bind thô, nhất là password, token, email, số điện thoại hoặc dữ liệu khách hàng.

Thay vì log toàn bộ SQL với user input đã được ghép, điều tra theo hướng:

~~~text
statement=account.findByEmail
sql_template=SELECT id FROM account WHERE tenant_id = :tenantId AND email = :email
parameters={tenantId:[authorized], email:[redacted]}
duration_ms=14
rows=1
~~~

Đây là **log mô phỏng**, không phải format bắt buộc của Spring. Không log một giá trị đã được masking rồi vô tình thêm bản rõ trong exception message hoặc tracing tags.

Nếu database trả lỗi cú pháp hoặc lỗi binding, đừng “khắc phục” bằng cách tạm nối input trực tiếp vào SQL để chạy thử ở production. Hãy kiểm tra tên parameter, map key, SQL dialect, loại dữ liệu và câu query trong môi trường test. Lỗi database nên được phân loại theo tầng; không nên bắt mọi exception và trả “không tìm thấy” để che lỗi.

## 20. Phương pháp review code có thể áp dụng ngay

Khi review một repository Spring JDBC, tìm các dấu hiệu sau:

1. **SQL text có được ghép từ biến request không?** Đặc biệt `"... WHERE " + userFilter`, `"... ORDER BY " + sort`, `String.format("... %s ...", input)`.
2. **Input của mọi điều kiện giá trị có đi qua `:name` hoặc `?` không?**
3. **Tên identifier/keyword động có được mapping bằng allowlist cố định không?**
4. **Danh sách `IN` có dùng collection binding hay nối chuỗi CSV?** Có xử lý danh sách rỗng và giới hạn kích thước không?
5. **Truy vấn LIKE có phân biệt wildcard chủ ý và tìm nguyên văn không?**
6. **Giá trị nullable có được bind đúng type không?** Không âm thầm thay bằng chuỗi SQL dựng tay.
7. **Mọi filter quyền truy cập (tenant, owner, role) có lấy từ nguồn đáng tin và được áp vào query không?**
8. **Logging có ghi bind values nhạy cảm không?**
9. **Test có xác minh kết quả với input chứa quotes, wildcard, Unicode và chuỗi dài không?**
10. **Có raw SQL escape hatch trong ORM, stored procedure hoặc query builder nhận input không?**

Nếu phát hiện code ghép trực tiếp dữ liệu, hãy phân tích **vị trí** ghép. Đối với value position, đổi sang bind parameter. Đối với cấu trúc SQL buộc phải động, thiết kế allowlist/query variants rồi bind tất cả giá trị còn lại. Không chỉ thay một hàm escape chung.

## 21. Kiểm thử chống lỗi ghép SQL

Một bộ test hữu ích nên kiểm tra cả **tách biệt SQL/data** và **hành vi chức năng đúng**.

| Trường hợp | Điều cần khẳng định |
| --- | --- |
| Email bình thường | Đúng hàng theo email và tenant |
| Email chứa dấu nháy đơn | Không làm hỏng cú pháp; được tìm như giá trị literal |
| Email giống một điều kiện SQL | Không làm query trả thêm bản ghi ngoài điều kiện |
| Email Unicode | Bind và so sánh đúng theo encoding/collation của DB |
| Ký tự `%` và `_` trong tìm kiếm literal | Không bị hiểu thành wildcard nếu nghiệp vụ yêu cầu literal |
| Sort field hợp lệ | Chọn đúng cột từ allowlist và hướng sort cố định |
| Sort field không hợp lệ | Bị từ chối trước khi tạo SQL dùng identifier |
| Danh sách ID rỗng | Trả kết quả rỗng hoặc xử lý theo hợp đồng, không phát sinh SQL `IN ()` sai |
| Danh sách ID lớn | Có giới hạn số lượng hoặc xử lý phù hợp với DB |
| Giá trị nullable | Dùng `MapSqlParameterSource`/SQL type nếu cần |
| Tenant ID giả từ request | Không thể chuyển sang tenant không có quyền |
| UPDATE/DELETE với ID không thuộc tenant | Không tác động dữ liệu khác tenant |
| SQL exception | Không bị nuốt và biến thành kết quả nghiệp vụ giả |

### Integration test với database

Test cần chạy repository với một database/driver phù hợp (ví dụ Testcontainers hoặc database test do dự án quản lý), tạo ít nhất hai record có dữ liệu phân biệt rõ. Thử truyền chuỗi giống SQL code vào `:email`, rồi assert query **không trả hàng ngoài giá trị literal đó**; không chỉ kiểm tra “không có exception”. Đồng thời xác nhận schema vẫn nguyên vẹn, dữ liệu không bị cập nhật ngoài kỳ vọng và không bị lỗi phân quyền.

Một test có thể dùng dữ liệu email chứa dấu nháy đơn thật để chứng minh binding không làm hỏng cú pháp. Với các cột bị ràng buộc định dạng email, dùng trường `display_name` hoặc `search_term` phù hợp cho những chuỗi kiểm thử đặc biệt, tránh viết test vô tình vi phạm constraint vốn không liên quan SQL injection.

### Unit test cho query planner

Đối với mã như `SafeSqlPlanDemo`, kiểm tra:

- Với cùng `sort=created`, SQL text giống nhau dù email thay đổi.
- `parameters.get("email")` đúng nguyên văn input.
- Tham số sort không hợp lệ bị từ chối.
- Direction chỉ cho `ASC` hoặc `DESC` cố định.
- Không có đoạn raw user input nào bị nối vào SQL text ở các đường khác.

Unit test không thay thế integration test: nó có thể chứng minh query **được dựng đúng ý đồ**, nhưng không chứng minh runtime Spring/driver/database bind thành công hoặc quyền truy cập đã đúng.

## 22. Bài tập tự kiểm tra và đáp án

**Câu 1.** Vì sao nối `requestedEmail` vào `WHERE email = '...'` nguy hiểm hơn bind `:email`?  
**Đáp án:** Vì nối chuỗi đưa dữ liệu thành một phần của cú pháp SQL. Bind giữ email ở vị trí giá trị, không tự biến nội dung của email thành mệnh đề hoặc toán tử SQL.

**Câu 2.** Có thể truyền `sortColumn = "created_at"` vào `ORDER BY :sortColumn` để chọn cột không?  
**Đáp án:** Không nên. Bind parameter đại diện value, không phải identifier. Chọn tên cột SQL bằng allowlist fixed fragment, rồi chỉ ghép fragment đáng tin.

**Câu 3.** Tham số `:email` xuất hiện hai lần trong một SQL template, có cần ghép chuỗi hai lần không?  
**Đáp án:** Không. Dùng cùng giá trị trong parameter source; `NamedParameterJdbcTemplate` có thể ánh xạ giá trị đó tới từng vị trí JDBC tương ứng khi thực thi.

**Câu 4.** `LIKE :pattern` đã dùng bind thì người dùng gõ `%` có tự được xem là ký tự literal không?  
**Đáp án:** Không. Bind chống SQL injection ở value position nhưng `%`/`_` vẫn là wildcard của LIKE. Nếu UI yêu cầu tìm literal, dùng quy tắc escape phù hợp dialect và bind pattern đã xử lý.

**Câu 5.** Danh sách ID nhận từ API nên xử lý thế nào với `IN (...)`?  
**Đáp án:** Parse thành danh sách số có validation/authorization/size limit; dùng `IN (:ids)` với collection binding của Spring, xử lý danh sách rỗng theo hợp đồng. Không nối raw CSV vào SQL.

**Câu 6.** Chỉ gọi `connection.prepareStatement(sql)` có đủ an toàn nếu `sql` được dựng trước bằng `"..." + userInput`?  
**Đáp án:** Không. PreparedStatement không khôi phục ranh giới giá trị nếu input đã bị ghép vào SQL text. Phải dùng marker và setter hoặc parameter source.

**Câu 7.** Nếu user điền `tenantId=999` và `tenantId` được bind an toàn, ứng dụng có thể bỏ qua kiểm tra quyền không?  
**Đáp án:** Không. Bind chống SQL injection nhưng không kiểm tra user có quyền đọc tenant 999. Tenant ID dùng trong query nên dựa trên context phân quyền đã xác thực.

**Câu 8.** Vì sao `Map.of("note", null)` không phù hợp khi cột SQL nullable?  
**Đáp án:** Vì Java `Map.of` không cho phép null. Dùng `MapSqlParameterSource` và, khi cần, đăng ký kiểu SQL như `Types.VARCHAR`.

**Câu 9.** Một query có `:status` được bind nhưng `requestedEmail` vẫn được nối vào SQL. Query đã chống injection toàn diện chưa?  
**Đáp án:** Chưa. Từng đường user input có thể ảnh hưởng SQL phải được xử lý đúng; binding một tham số không bảo vệ phần query được ghép trực tiếp.

**Câu 10.** Có cần xóa mọi dấu nháy, dấu phần trăm hoặc ký tự Unicode trong dữ liệu để phòng SQL injection không?  
**Đáp án:** Không. Dùng parameter binding cho giá trị, validation theo nghiệp vụ và escaping riêng cho các ngữ nghĩa như LIKE literal search. Không biến validation thành một cách tự dựng SQL.

## 23. Tổng kết nguyên tắc

**Không ghép trực tiếp dữ liệu người dùng vào câu SQL.** Với Spring JDBC, dùng `NamedParameterJdbcTemplate` và `:namedParameter` cùng `MapSqlParameterSource` hoặc `Map` cho các giá trị; hoặc dùng `JdbcTemplate`/`PreparedStatement` với `?`. Câu SQL template thuộc quyền kiểm soát của ứng dụng; giá trị đầu vào đi qua binding.

Khi phần cấu trúc thực sự phải thay đổi, như `ORDER BY`, chỉ chọn fragment SQL cố định từ **allowlist**; không gửi raw tên cột, tên bảng hoặc nguyên mệnh đề `WHERE` từ client. Với `LIKE`, `IN`, `NULL` và paging, vừa bind đúng cách vừa xử lý đúng ngữ nghĩa và giới hạn của database. Cuối cùng, đừng quên authorization, database least privilege, giới hạn tài nguyên, logging an toàn và kiểm thử trên database thật.

### Tài liệu tham khảo chính thức

- [Spring Framework — JDBC Core: NamedParameterJdbcTemplate](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): sử dụng SQL có tham số tên, `MapSqlParameterSource`, `Map` và `JdbcClient`.
- [Spring Framework — Common Problems with Parameter and Data Value Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/parameter-handling.html): khai báo kiểu SQL, xử lý tham số NULL và data binding.
- [Spring Framework — NamedParameterJdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html): contract query/update theo named parameters.
- [Spring Framework — MapSqlParameterSource API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/MapSqlParameterSource.html): gắn giá trị và kiểu SQL cho từng tham số.
- [Java SE 17 — PreparedStatement API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): các setter dạng positional của JDBC.
- [OWASP — SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html): parameterized queries, allowlist identifiers, least privilege và các cách cần tránh.