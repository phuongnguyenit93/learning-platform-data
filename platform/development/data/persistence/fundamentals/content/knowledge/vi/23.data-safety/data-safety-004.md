# Ngăn SQL injection bằng tham số hóa truy vấn

Một API Java tìm khách hàng theo email có thể bị lộ dữ liệu nếu ứng dụng ghép trực tiếp chuỗi do người dùng gửi vào câu SQL. Ngay cả khi nhà phát triển chỉ định thực hiện một câu SELECT, nội dung đầu vào có thể làm thay đổi điều kiện WHERE, khiến database xử lý **cấu trúc lệnh khác với cấu trúc mà ứng dụng định viết**. Lỗi này gọi là **SQL injection**.

Cách phòng vệ nền tảng là **tham số hóa truy vấn**: định nghĩa phần SQL mang ý nghĩa cú pháp **tách biệt** với các giá trị dữ liệu, rồi truyền giá trị thông qua API binding của JDBC, ORM hoặc thư viện truy cập dữ liệu. Thay vì cố tự đoán và loại bỏ mọi ký tự “nguy hiểm”, ứng dụng yêu cầu driver xử lý dữ liệu theo đúng kiểu dữ liệu của nó.

Bài thuộc chương **An toàn dữ liệu** trong module **DATA_PERSISTENCE_FUNDAMENTALS**. Module giúp người học hiểu persistence bền vững trong ứng dụng Java, từ mô hình dữ liệu, lược đồ, truy vấn và chỉ mục đến giao dịch, cô lập, kiểm soát đồng thời, kết nối, tiến hóa schema, bảo mật, sao lưu và hiệu năng. Nội dung dùng **JDBC PreparedStatement, Spring JdbcTemplate, JPA/Hibernate và PostgreSQL** để minh họa; nguyên tắc phòng chống injection áp dụng rộng hơn, nhưng cú pháp placeholder và khả năng binding từng thành phần có thể khác nhau giữa driver/DBMS.

## 1. Mục tiêu học tập

Sau khi học, người học có thể:

- Giải thích **SQL injection** xuất hiện khi dữ liệu không đáng tin cậy bị diễn giải thành **cú pháp SQL**.
- Viết lại câu SQL ghép chuỗi thành **PreparedStatement** với placeholder và binding đúng kiểu.
- Phân biệt phần có thể binding như **giá trị trong WHERE/INSERT/UPDATE/LIMIT** với các thành phần cấu trúc như **tên bảng, tên cột, ORDER BY và hướng ASC/DESC**.
- Thiết kế truy vấn động dùng **allowlist**, xây dựng số placeholder hữu hạn cho **IN**, và dùng escaping đúng cho ký tự đại diện của **LIKE**.
- Sử dụng tham số trong **JPA JPQL/native query, Spring JdbcTemplate và NamedParameterJdbcTemplate** mà không giả định ORM tự làm mọi đoạn SQL động trở nên an toàn.
- Hiểu rằng tham số hóa **không thay thế** kiểm tra quyền tenant, ràng buộc dữ liệu, transaction, giới hạn tài nguyên, quyền DB tối thiểu và quản lý secret.
- Thiết kế kiểm thử phòng chống injection cho cả trường hợp bình thường, input đặc biệt và những vị trí dễ bỏ sót.

## 2. SQL injection là sự nhầm lẫn giữa lệnh và dữ liệu

Trong một ứng dụng persistence, lệnh SQL thường có hai phần:

1. **Cấu trúc được chương trình quyết định:** SELECT, FROM, JOIN, WHERE, ORDER BY, các toán tử, tên bảng/cột và số điều kiện.
2. **Giá trị do người dùng hoặc hệ thống khác cung cấp:** email, tên, mã đơn, từ khóa tìm kiếm, khoảng thời gian và ID.

Ví dụ, câu lệnh mong muốn là:

~~~sql
SELECT id, email
FROM customers
WHERE tenant_id = 10
  AND email = 'user@example.com';
~~~

Nếu ứng dụng dựng câu SQL bằng cách nối một giá trị email vào dấu nháy đơn, một email có chứa dấu nháy hoặc chuỗi có ý nghĩa cú pháp có thể khiến database hiểu phần nối thêm là **một mảnh lệnh**, không còn là một giá trị.

~~~text
Nguy cơ khi ghép chuỗi:
  SQL prefix + untrusted input + SQL suffix
               |
               v
        DB parser đọc cả chuỗi như SQL

Khi tham số hóa:
  SQL template cố định --parse/prepare--> câu lệnh có cấu trúc xác định
  Giá trị đầu vào ------bind-----------> một giá trị dữ liệu tương ứng
~~~

Nguồn dữ liệu **không đáng tin cậy** không chỉ là biểu mẫu trên web. Nó có thể là:

- Header, query parameter, path parameter và JSON body của HTTP request.
- Nội dung CSV, Excel, JSON, XML hoặc file nhập.
- Event/message đến từ hệ thống khác.
- Tên file, định danh trong URL hoặc giá trị được nạp từ cache.
- Dữ liệu đã được lưu ở DB nhưng ban đầu do người ngoài cung cấp (**second-order injection**).
- Giá trị đến từ cấu hình hoặc dashboard vận hành mà người sử dụng có thể chỉnh sửa.

**Kiểu String hợp lệ trong Java không chứng minh chuỗi đó là cú pháp SQL an toàn.** Ranh giới bảo mật phải nằm tại nơi dữ liệu được đưa vào lệnh.

## 3. Ví dụ lỗi: nối chuỗi để tìm khách hàng

Đoạn code sau **không an toàn**, chỉ dùng để nhận diện anti-pattern:

~~~java
String sql = "SELECT id, email FROM customers " +
        "WHERE tenant_id = " + tenantId +
        " AND email = '" + emailFromRequest + "'";

try (Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(sql)) {
    // Xử lý kết quả.
}
~~~

Nguy hiểm nằm ở đoạn **emailFromRequest** được ghép trực tiếp giữa các dấu nháy trong chuỗi SQL. Ví dụ một giá trị có dấu nháy đơn **O'Brien@example.com** có thể làm câu lệnh bị lỗi cú pháp. Giá trị được chế tạo có chủ ý còn có thể thay đổi logic điều kiện.

Đừng nghĩ rằng chỉ cần kiểm tra **tenantId** đã là số thì toàn bộ câu SQL an toàn: nếu một tham số khác được nối chuỗi, lệnh vẫn có thể bị injection. Hơn nữa, giới hạn truy cập tenant còn phụ thuộc **tenantId lấy từ danh tính đã xác thực**, không thể chỉ dựa trên việc nó là số.

Các biến thể cùng rủi ro:

~~~java
// Không an toàn: input chen vào mệnh đề SQL.
String query = "SELECT * FROM orders WHERE status = '" + status + "'";

// Không an toàn: tên cột do client gửi được đưa thẳng vào cú pháp.
String sorted = "SELECT * FROM orders ORDER BY " + sortBy;

// Không an toàn: nối một chuỗi ID do client gửi vào IN.
String queryIds = "SELECT * FROM orders WHERE id IN (" + idsCsv + ")";
~~~

**PreparedStatement chỉ bảo vệ phần thực sự được binding.** Nếu code nối input vào SQL trước khi truyền chuỗi đó cho prepareStatement, thì việc gọi prepareStatement sau đó **không xóa được lỗ hổng đã tạo**.

## 4. Cách đúng: SQL tĩnh và PreparedStatement

Với JDBC, sử dụng dấu hỏi **?** làm placeholder cho giá trị, rồi gọi các phương thức **setXxx**:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class CustomerLookup {
    private final DataSource dataSource;

    public CustomerLookup(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Customer(long id, String email) {}

    public Customer findByEmail(long tenantId, String email)
            throws SQLException {
        String sql = """
            SELECT id, email
            FROM customers
            WHERE tenant_id = ?
              AND email = ?
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement st = connection.prepareStatement(sql)) {
            st.setLong(1, tenantId);
            st.setString(2, email);

            try (ResultSet rs = st.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }
                return new Customer(
                        rs.getLong("id"),
                        rs.getString("email"));
            }
        }
    }
}
~~~

Điều cần nhận ra:

1. **SQL template không thay đổi theo nội dung email.** Placeholder thứ nhất tương ứng tenantId, thứ hai tương ứng email.
2. **st.setString(2, email)** truyền email như một giá trị kiểu chuỗi, kể cả nếu nó chứa dấu nháy, dấu chấm phẩy hoặc những từ trông giống SQL.
3. **Chỉ số tham số của PreparedStatement bắt đầu từ 1**, không phải 0.
4. **try-with-resources** đóng ResultSet, PreparedStatement và logical Connection; nếu có pool, close thường trả connection về pool theo cơ chế được quản lý.
5. Ví dụ chỉ tìm dữ liệu. Trong ứng dụng thật, tenantId phải được lấy từ **identity/authorization context**, và email cần được kiểm tra quy tắc nghiệp vụ phù hợp.

### 4.1. Vì sao một giá trị đặc biệt không trở thành SQL?

Giả sử client gửi email có nội dung giống:

~~~text
' OR '1'='1
~~~

Nếu được **setString** vào placeholder, đây vẫn là **một giá trị chuỗi** để so sánh với cột email. Driver/DBMS không xem các dấu nháy và toán tử trong giá trị đó như một điều kiện OR mới của câu SQL.

Tham số hóa phân tách **cấu trúc cú pháp** với **giá trị**; đó mới là cơ chế chính để chống SQL injection, không phải chỉ chặn riêng dấu nháy đơn.

## 5. Binding phải đúng vị trí và đúng kiểu

PreparedStatement hỗ trợ các kiểu tham số khác nhau:

~~~java
String sql = """
    INSERT INTO orders
        (tenant_id, customer_id, total_amount, created_at, note)
    VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement st = connection.prepareStatement(sql)) {
    st.setLong(1, tenantId);
    st.setLong(2, customerId);
    st.setBigDecimal(3, totalAmount);
    st.setObject(4, createdAt);

    if (note == null) {
        st.setNull(5, java.sql.Types.VARCHAR);
    } else {
        st.setString(5, note);
    }
    st.executeUpdate();
}
~~~

Ví dụ giả định **createdAt** là một kiểu thời gian Java được driver hỗ trợ, chẳng hạn **LocalDateTime** với kiểu SQL phù hợp; cần xác định semantics múi giờ và loại cột như **timestamp/timestamptz** trong ứng dụng thật.

Lợi ích của binding đúng kiểu:

- Không phải ghép dấu nháy đơn cho chuỗi hoặc tự định dạng ngày giờ vào SQL.
- Hạn chế lỗi do locale, dấu phân cách thập phân, Unicode và ký tự escape.
- **BigDecimal** giúp biểu diễn giá trị thập phân phù hợp hơn dùng float/double trong nghiệp vụ tiền tệ (vẫn phải kiểm soát scale và currency).
- **setNull(index, sqlType)** diễn đạt NULL có kiểu rõ ràng khi cần; lưu ý **WHERE col = NULL** không có nghĩa so sánh bằng NULL, cần **IS NULL** hoặc điều kiện riêng.
- Có cơ hội tái sử dụng cấu trúc prepared statement/plan theo driver và DBMS, dù tối ưu hiệu năng không phải lý do chính về bảo mật.

**Parameter binding không thay cho kiểm tra dữ liệu.** Giá trị số lượng âm, số tiền vượt giới hạn, ngày không hợp lệ hoặc tenant khác vẫn có thể được binding an toàn về mặt injection nhưng **sai nghiệp vụ**.

## 6. PreparedStatement bảo vệ giá trị, không thay thế cả cú pháp SQL

Một placeholder **?** thường đại diện một **biểu thức giá trị** tại vị trí SQL/driver cho phép. Không thể dùng nó để tùy ý thay thế từ khóa hoặc định danh SQL.

| Vị trí | Có thể dùng bind value? | Ghi chú |
| --- | --- | --- |
| **WHERE email = ?** | Có | Cách phổ biến và đúng |
| **WHERE created_at >= ?** | Có | Bind kiểu ngày giờ tương ứng |
| **INSERT ... VALUES (?, ?)** | Có | Mỗi placeholder cho một giá trị |
| **UPDATE ... SET status = ?** | Có | Giá trị trạng thái được binding |
| **LIMIT ? OFFSET ?** | Có trên PostgreSQL/JDBC thông thường | Vẫn cần giới hạn số hàng và offset |
| **ORDER BY ?** để chọn tên cột | **Không phải cách đúng** | ? là giá trị, không phải identifier |
| **FROM ?** để chọn bảng | Không | Tên bảng là cấu trúc SQL |
| **SELECT ?** để chọn tên cột | Không | Trả một giá trị literal, không biến thành cột mong muốn |
| **ASC/DESC bằng ?** | Không | Đây là từ khóa cú pháp |
| **Tên schema, toán tử, hướng JOIN** | Không tùy ý | Phải được chương trình chọn từ danh sách hợp lệ |
| **IN (?)** để truyền chuỗi **1,2,3** | Không theo ý nghĩa nhiều ID | Một placeholder là một giá trị, không phải một danh sách SQL |

Một anti-pattern tưởng như đã tham số hóa:

~~~java
// Không làm sort theo cột do người dùng chọn:
String sql = "SELECT id, created_at FROM orders ORDER BY ?";
st.setString(1, "created_at");
~~~

Database sẽ diễn giải placeholder thành **giá trị**, không thành tên cột **created_at**. Tùy hệ quản trị, câu lệnh có thể không hợp lệ hoặc sắp theo một biểu thức hằng, nhưng không phải chức năng sort động như mong đợi.

**Nguyên tắc tổng quát:** binding cho **giá trị**; còn **cấu trúc SQL** phải do chương trình lựa chọn có kiểm soát.

## 7. ORDER BY động: chọn từ allowlist

Giả sử API cho phép sort đơn hàng theo **created_at** hoặc **total_amount**, tăng hoặc giảm dần. Đừng dùng:

~~~java
// Không an toàn khi sortField/sortDirection đến từ request:
String sql = "SELECT id, total_amount FROM orders ORDER BY "
        + sortField + " " + sortDirection;
~~~

Thay vào đó, ánh xạ các lựa chọn đã xác thực tới **các mảnh SQL cố định do code sở hữu**:

~~~java
public enum OrderSortField {
    CREATED_AT, TOTAL_AMOUNT
}

public enum SortDirection {
    ASC, DESC
}

public static String orderQuery(
        OrderSortField field, SortDirection direction) {
    String column = switch (field) {
        case CREATED_AT -> "created_at";
        case TOTAL_AMOUNT -> "total_amount";
    };
    String order = switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };

    return """
        SELECT id, created_at, total_amount
        FROM orders
        WHERE tenant_id = ?
        ORDER BY %s %s, id ASC
        LIMIT ?
        """.formatted(column, order);
}
~~~

Phần **formatted(column, order)** ở đây chỉ dùng những chuỗi **hard-code** đi ra từ enum/switch, **không chứa chuỗi tự do của client**. Những giá trị như **tenant_id** và **LIMIT** vẫn là placeholder để binding.

Ngoài ra:

- Parse request thành enum và **từ chối giá trị lạ**; không đưa nguyên chuỗi request vào nhánh default.
- Thêm khóa phụ **id** để có thứ tự toàn phần khi nhiều đơn cùng giá trị sort.
- Kiểm tra index/plan nếu cho phép nhiều kiểu sắp xếp.
- Giới hạn page size để tránh lạm dụng tài nguyên.
- Nếu API hỗ trợ đường dẫn sort qua nhiều bảng, từng lựa chọn JOIN/column cũng phải nằm trong tập định nghĩa sẵn.

**Allowlist tốt hơn blacklist.** Thay vì cố liệt kê mọi chuỗi nguy hiểm như dấu nháy, dấu chấm phẩy, comment hoặc từ khóa SQL, hãy chấp nhận đúng một số lựa chọn nghiệp vụ đã được thiết kế.

## 8. Tên bảng, tên schema và tên cột động

Một hệ multi-tenant có thể có schema theo tenant hoặc bảng phân vùng được chọn ở tầng ứng dụng. Đây là vị trí nhạy cảm vì **không thể binding tên bảng/schema như một giá trị SQL thông thường**:

~~~java
// Không an toàn nếu tableName lấy trực tiếp từ input:
String sql = "SELECT count(*) FROM " + tableName;
~~~

Cách an toàn hơn là dùng **một mapping được ứng dụng kiểm soát**:

~~~java
enum ReportSource {
    ORDERS, REFUNDS
}

static String tableFor(ReportSource source) {
    return switch (source) {
        case ORDERS -> "orders";
        case REFUNDS -> "refunds";
    };
}

String sql = "SELECT count(*) FROM " + tableFor(source)
        + " WHERE tenant_id = ?";
~~~

Lưu ý:

1. **source** phải là enum đã được parse/validate từ lựa chọn của người dùng.
2. Tên bảng phải nằm trong code/config đáng tin cậy, không được đơn thuần nối với tenant name tự do.
3. **Quoting identifiers** đúng chuẩn DBMS là một vấn đề riêng; ngay cả khi có hàm quote identifier, ứng dụng vẫn cần kiểm tra quyền chọn nguồn dữ liệu. Quoting không tự biến một bảng bất kỳ thành bảng mà người dùng được phép đọc.
4. Khi cần schema-per-tenant, sử dụng mapping tenant → schema có xác thực, quyền DB, và reset session state an toàn nếu sử dụng **search_path** với connection pool.
5. Lựa chọn bảng sai vẫn có thể là **broken access control** ngay cả khi chuỗi SQL không bị injection.

## 9. Truy vấn IN với số phần tử thay đổi

Giả sử client được phép truy vấn tối đa 100 ID đơn hàng:

~~~text
ids = [101, 205, 309]
~~~

Cách sai là nối các chuỗi input thành:

~~~sql
SELECT id FROM orders WHERE id IN (101,205,309);
~~~

với nội dung nằm nguyên từ dữ liệu yêu cầu chưa tin cậy. Cách đúng với JDBC là tạo **số dấu ?** dựa trên **số lượng phần tử đã kiểm tra**, rồi binding từng giá trị:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public static List<Long> findIds(
        Connection connection, long tenantId, List<Long> ids)
        throws SQLException {

    if (ids == null || ids.isEmpty()) {
        return List.of();
    }
    if (ids.size() > 100 || ids.stream().anyMatch(
            id -> id == null || id <= 0)) {
        throw new IllegalArgumentException("Danh sách ID không hợp lệ");
    }

    String placeholders = String.join(
            ", ", Collections.nCopies(ids.size(), "?"));
    String sql = """
        SELECT id
        FROM orders
        WHERE tenant_id = ?
          AND id IN (%s)
        """.formatted(placeholders);

    try (PreparedStatement st = connection.prepareStatement(sql)) {
        st.setLong(1, tenantId);
        for (int i = 0; i < ids.size(); i++) {
            st.setLong(i + 2, ids.get(i));
        }
        try (ResultSet rs = st.executeQuery()) {
            List<Long> found = new java.util.ArrayList<>();
            while (rs.next()) {
                found.add(rs.getLong(1));
            }
            return found;
        }
    }
}
~~~

Đoạn code chỉ tạo mảnh cấu trúc gồm dấu **?** và dấu phẩy từ **kích thước danh sách đã giới hạn**. Không có ID nào được nối trực tiếp vào SQL. Ví dụ chưa đảm bảo thứ tự kết quả khớp thứ tự input hoặc xử lý duplicate IDs theo chính sách nghiệp vụ.

**Danh sách rỗng** cần xử lý riêng vì cú pháp **IN ()** không hợp lệ ở nhiều DBMS; ở ví dụ, danh sách rỗng có nghĩa trả kết quả rỗng mà không query.

### 9.1. PostgreSQL array binding

Trong PostgreSQL, có thể dùng array parameter cho nhiều phần tử:

~~~sql
SELECT id
FROM orders
WHERE tenant_id = ?
  AND id = ANY (?);
~~~

Ví dụ JDBC:

~~~java
java.sql.Array array = connection.createArrayOf(
        "int8", ids.toArray(new Long[0]));
try {
    try (PreparedStatement st = connection.prepareStatement(
            "SELECT id FROM orders WHERE tenant_id = ? AND id = ANY (?)")) {
        st.setLong(1, tenantId);
        st.setArray(2, array);
        try (ResultSet rs = st.executeQuery()) {
            while (rs.next()) {
                // Đọc các ID được trả về.
            }
        }
    }
} finally {
    array.free();
}
~~~

Tên kiểu phần tử, giới hạn số lượng và chiến lược query plan cần kiểm tra cho driver/DBMS thực tế. **Array parameter vẫn là dữ liệu**; không chuyển sang ghép một chuỗi CSV thô để “đơn giản hóa”.

## 10. LIKE: tham số hóa ngăn injection nhưng không ngăn wildcard

Với tìm kiếm theo tên:

~~~sql
SELECT id, display_name
FROM customers
WHERE tenant_id = ?
  AND display_name ILIKE ?;
~~~

Một chuỗi binding là an toàn về **cú pháp SQL**, nhưng ký tự **%** và **_** trong LIKE/ILIKE vẫn có ý nghĩa **mẫu khớp**, không phải ký tự literal. Nếu sản phẩm muốn tìm chính xác phần văn bản mà người dùng nhập, cần escape wildcard theo quy tắc của DBMS.

Ví dụ PostgreSQL dùng ký tự escape **!**:

~~~java
static String escapeLikeLiteral(String input) {
    return input
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}

String sql = """
    SELECT id, display_name
    FROM customers
    WHERE tenant_id = ?
      AND display_name ILIKE ? ESCAPE '!'
    """;

try (PreparedStatement st = connection.prepareStatement(sql)) {
    st.setLong(1, tenantId);
    st.setString(2, "%" + escapeLikeLiteral(term) + "%");
    try (ResultSet rs = st.executeQuery()) {
        // Xử lý từng kết quả.
    }
}
~~~

Phân biệt rõ:

- **Binding term** bảo vệ **SQL injection**.
- **Escaping %/_/!** bảo vệ **ý nghĩa tìm kiếm literal** khỏi wildcard không mong muốn.
- **Giới hạn độ dài term, quota, page size và index** bảo vệ **tài nguyên/hiệu năng**; một truy vấn LIKE có dấu % đầu có thể quét lượng dữ liệu lớn nếu không có chiến lược index phù hợp.

Không nên dùng “lọc bỏ toàn bộ ký tự đặc biệt” vì tên người, địa chỉ, Unicode và email hợp lệ có thể chứa những ký tự đó. Mục tiêu là xử lý theo **ngữ cảnh chính xác**, không bóp méo dữ liệu.

## 11. Điều kiện tùy chọn và bộ lọc động

Một API tìm đơn có thể nhận các bộ lọc **status**, **fromTime**, **toTime**. Có thể tạo SQL bằng cách thêm **mảnh điều kiện tĩnh** do code sở hữu, rồi binding giá trị:

~~~java
StringBuilder sql = new StringBuilder("""
    SELECT id, status, created_at
    FROM orders
    WHERE tenant_id = ?
    """);

List<Object> params = new java.util.ArrayList<>();
params.add(tenantId);

if (status != null) {
    sql.append(" AND status = ?");
    params.add(status);
}
if (fromTime != null) {
    sql.append(" AND created_at >= ?");
    params.add(fromTime);
}
if (toTime != null) {
    sql.append(" AND created_at < ?");
    params.add(toTime);
}
sql.append(" ORDER BY created_at DESC, id DESC LIMIT ?");
params.add(pageSize);

try (PreparedStatement st = connection.prepareStatement(sql.toString())) {
    for (int i = 0; i < params.size(); i++) {
        st.setObject(i + 1, params.get(i));
    }
    try (ResultSet rs = st.executeQuery()) {
        // Xử lý kết quả.
    }
}
~~~

**Vì sao ví dụ này khác nối chuỗi không an toàn?** Tất cả chuỗi được append đều là **cú pháp cố định** do chương trình quyết định; không có giá trị status/fromTime/toTime nào được nối vào SQL. Chúng chỉ đi qua **setObject**.

Trong production, nên:

- Ràng buộc **pageSize** vào khoảng hữu hạn, ví dụ 1..100, trước khi binding.
- Xác định kiểu SQL/Java cho từng tham số, có thể dùng **setString**, **setObject** với kiểu, hoặc mapper rõ ràng để tránh suy kiểu không mong muốn.
- Kiểm tra logic thời gian **fromTime <= toTime** và múi giờ.
- Xem **EXPLAIN** và index: nhiều tổ hợp filter có thể tạo kế hoạch truy vấn khác nhau.
- Luôn đưa điều kiện tenant/authorization bắt buộc vào **cấu trúc cố định**, không để client bật/tắt điều kiện bảo mật.

Một câu SQL có mọi nhánh optional dùng biểu thức **(? IS NULL OR col = ?)** cũng có thể an toàn nếu binding đúng, nhưng ảnh hưởng query plan và index cần được đo; đừng chỉ chọn cách viết vì ít dòng code.

## 12. UPDATE, DELETE và câu lệnh ghi cũng phải tham số hóa

SQL injection không chỉ xảy ra ở SELECT. Các thao tác ghi có thể nguy hiểm hơn vì thay đổi trạng thái dữ liệu.

~~~java
String sql = """
    UPDATE orders
    SET status = ?
    WHERE tenant_id = ?
      AND id = ?
      AND status = ?
    """;

try (PreparedStatement st = connection.prepareStatement(sql)) {
    st.setString(1, "CANCELED");
    st.setLong(2, tenantId);
    st.setLong(3, orderId);
    st.setString(4, "NEW");
    int changed = st.executeUpdate();
    if (changed != 1) {
        throw new IllegalStateException(
                "Đơn không tồn tại hoặc trạng thái không hợp lệ");
    }
}
~~~

Điều kiện **tenant_id** và **status = NEW** giúp bảo vệ phạm vi và quy tắc chuyển trạng thái; chúng khác với cơ chế chống injection. Dù mọi tham số đều được binding an toàn, một câu UPDATE **thiếu WHERE** vẫn có thể sửa tất cả hàng do **lỗi logic của lập trình viên**.

Với DELETE, chỉ cho phép xóa theo định danh có ủy quyền, cân nhắc soft-delete hoặc audit nếu nghiệp vụ yêu cầu:

~~~sql
DELETE FROM draft_orders
WHERE tenant_id = ?
  AND id = ?
  AND status = 'DRAFT';
~~~

**Không chọn giữa bảo mật cú pháp và tính đúng nghiệp vụ**: cần cả hai. Mọi thao tác thay đổi nhiều hàng nên kiểm tra số hàng thực tế, transaction boundary và cách rollback khi kết quả không như dự kiến.

## 13. Spring JdbcTemplate: truyền tham số tách khỏi SQL

**JdbcTemplate** giúp giảm mã quản lý PreparedStatement và ResultSet. Ví dụ DAO:

~~~java
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderSearchDao {
    private final JdbcTemplate jdbc;

    public OrderSearchDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Summary(long id, String status) {}

    public List<Summary> byStatus(long tenantId, String status) {
        return jdbc.query(
            """
            SELECT id, status
            FROM orders
            WHERE tenant_id = ? AND status = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (rs, rowNum) -> new Summary(
                rs.getLong("id"), rs.getString("status")),
            tenantId, status);
    }
}
~~~

Ở đây, các biến **tenantId** và **status** được truyền qua cơ chế binding của JdbcTemplate. Nhưng thư viện **không làm sạch** một câu SQL động mà ứng dụng đã tạo sai:

~~~java
// Vẫn không an toàn nếu sortField lấy thẳng từ input:
String sql = "SELECT id FROM orders ORDER BY " + sortField;
jdbc.query(sql, rowMapper);
~~~

Tham số phải được binding, không phải chỉ sử dụng một thư viện có tên “Jdbc”.

## 14. NamedParameterJdbcTemplate và danh sách tham số

Khi câu SQL có nhiều tham số, tên có thể dễ đọc hơn vị trí số:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

public List<Long> findOrders(
        NamedParameterJdbcTemplate jdbc,
        long tenantId,
        List<Long> ids) {
    if (ids == null || ids.isEmpty()) {
        return List.of();
    }
    if (ids.size() > 100) {
        throw new IllegalArgumentException("Quá nhiều ID");
    }
    return jdbc.query(
        """
        SELECT id
        FROM orders
        WHERE tenant_id = :tenantId
          AND id IN (:ids)
        """,
        Map.of("tenantId", tenantId, "ids", ids),
        (rs, rowNum) -> rs.getLong(1));
}
~~~

**NamedParameterJdbcTemplate** có thể mở rộng collection thành những placeholder JDBC tương ứng cho IN. Nhưng vẫn cần xác thực phần tử (kiểu, null, phạm vi), giới hạn danh sách và xử lý danh sách rỗng có chủ đích.

Chú ý **:tenantId** và **:ids** là tham số **giá trị**; chúng không phải cú pháp để truyền tên bảng hoặc một đoạn ORDER BY chưa được kiểm tra.

Khi ứng dụng dùng nhiều DataSource và transaction manager, phải chắc chắn JdbcTemplate tham gia **đúng transaction**, nhưng việc này là vấn đề **atomicity/lifecycle**, tách biệt với nguyên tắc injection.

## 15. JPA/Hibernate: JPQL cũng có thể bị injection

Sử dụng ORM không tự động loại bỏ SQL injection. Một câu **JPQL/HQL** ghép trực tiếp input vào cấu trúc truy vấn vẫn nguy hiểm:

~~~java
// KHÔNG an toàn:
String jpql = "SELECT o FROM PurchaseOrder o WHERE o.status = '"
        + statusFromRequest + "'";

entityManager.createQuery(jpql, PurchaseOrder.class)
        .getResultList();
~~~

Cách đúng:

~~~java
String jpql = """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
      AND o.status = :status
    ORDER BY o.id DESC
    """;

List<PurchaseOrder> orders = entityManager
        .createQuery(jpql, PurchaseOrder.class)
        .setParameter("tenantId", tenantId)
        .setParameter("status", status)
        .setMaxResults(50)
        .getResultList();
~~~

Ví dụ giả định **PurchaseOrder** là entity đã mapping và **status** có kiểu tương thích với thuộc tính của entity. Nếu status là enum, nên parse input thành một **enum cho phép** theo quy tắc nghiệp vụ thay vì gửi tùy ý một chuỗi.

JPA còn hỗ trợ **Criteria API**, cho phép xây dựng các predicate và order expression bằng API có kiểu. Nó có ích với truy vấn động, nhưng vẫn có thể xuất hiện lỗ hổng nếu lập trình viên chuyển một chuỗi request trực tiếp thành một biểu thức raw/named path không được kiểm soát hoặc chạy native SQL ghép chuỗi.

### 15.1. Native query của ORM cũng phải bind

~~~java
Object result = entityManager.createNativeQuery(
        """
        SELECT count(*)
        FROM orders
        WHERE tenant_id = ?1
          AND status = ?2
        """)
    .setParameter(1, tenantId)
    .setParameter(2, status)
    .getSingleResult();
~~~

**?1** và **?2** là positional parameters của JPA trong ví dụ; cần kiểm tra cú pháp với provider khi dùng các cấu trúc native SQL đặc biệt. Tránh chuyển nguyên input thành SQL string trước lời gọi **createNativeQuery**.

### 15.2. Không gán bảo đảm tuyệt đối cho ORM

ORM giải quyết mapping và giúp binding, nhưng:

- Native SQL được ghép chuỗi vẫn có thể bị injection.
- Các hàm mở rộng để chạy SQL fragment, tên cột động hoặc HQL động phải được kiểm soát.
- Annotation mapping, filter tenant hoặc interceptor sai có thể làm lộ dữ liệu mà **không liên quan injection**.
- Lazy loading, N+1 và truy vấn không có giới hạn có thể gây vấn đề hiệu năng dù không có injection.
- ORM không thay thế optimistic locking, constraint và transaction trong nghiệp vụ.

## 16. Đăng nhập, tra cứu tài khoản và kiểm tra quyền

Một lỗi nghiêm trọng là ghép email và mật khẩu thành điều kiện SQL. Ngoài rủi ro injection, thiết kế lưu mật khẩu ở dạng rõ còn gây nguy cơ lớn khác.

Thay vào đó, ứng dụng thường **tra cứu tài khoản bằng giá trị đã binding**, lấy **password hash** và dùng thư viện xác thực mật khẩu phù hợp để kiểm tra ngoài SQL:

~~~java
String sql = """
    SELECT id, password_hash, enabled
    FROM app_users
    WHERE email = ?
    """;

try (PreparedStatement st = connection.prepareStatement(sql)) {
    st.setString(1, emailFromLogin);
    try (ResultSet rs = st.executeQuery()) {
        if (!rs.next()) {
            // Xử lý xác thực không thành công theo chính sách.
        } else {
            String storedHash = rs.getString("password_hash");
            // Gọi password verifier đã cấu hình để kiểm tra mật khẩu.
        }
    }
}
~~~

Đoạn code minh họa **truy vấn an toàn**, chưa phải một luồng xác thực hoàn chỉnh: cần chính sách password hashing chuyên dụng, chống brute force, xử lý thời gian và thông báo lỗi, phiên đăng nhập, MFA nếu cần và bảo vệ secret.

**Tham số hóa chỉ ngăn input bị diễn giải thành cú pháp SQL.** Nó không xác thực rằng user đang được phép đăng nhập hoặc xem dữ liệu.

## 17. Tenant isolation: binding đúng vẫn có thể lộ dữ liệu

Giả sử hệ thống đa tenant. Câu SQL này đã binding an toàn:

~~~sql
SELECT id, total_amount
FROM orders
WHERE tenant_id = ?
  AND id = ?;
~~~

Nhưng nếu **tenant_id** được lấy trực tiếp từ query parameter do người dùng tùy ý gửi, người dùng có thể yêu cầu ID tenant khác. Lỗi này là **broken access control / IDOR**, không phải SQL injection.

Thiết kế an toàn phải kết hợp:

1. **Lấy tenantId từ danh tính/phiên được xác thực** và kiểm tra người dùng có quyền thao tác trên tenant đó.
2. Luôn thêm điều kiện tenant vào các SELECT/UPDATE/DELETE phù hợp.
3. Kiểm tra quyền theo **resource**, không chỉ tin mỗi tenantId.
4. Dùng quyền DB tối thiểu và cân nhắc **Row Level Security (RLS)** nếu phù hợp kiến trúc.
5. Nếu dùng session variable cho RLS với connection pool, phải bảo đảm **thiết lập/reset đúng phạm vi transaction** và không rò trạng thái tenant giữa request.
6. Kiểm thử request dùng resource ID hợp lệ của tenant khác vẫn bị từ chối, kể cả khi truy vấn hoàn toàn có placeholder.

Ví dụ: một SQL đã tham số hóa nhưng **thiếu WHERE tenant_id** có thể làm lộ hàng của tenant khác do **lỗi thiết kế truy vấn**. SQL injection defense và authorization defense là **hai lớp cần có đồng thời**.

## 18. Second-order injection: dữ liệu đã lưu cũng có thể nguy hiểm

Một lỗi phổ biến là nghĩ rằng “dữ liệu đã nằm trong database” thì có thể ghép thẳng vào SQL. Thử tưởng tượng:

1. Người dùng đăng ký tài khoản với một chuỗi hiển thị đặc biệt.
2. Ứng dụng lưu chuỗi đó bằng PreparedStatement, nên thao tác INSERT ban đầu an toàn.
3. Một batch job đêm đọc chuỗi từ DB rồi dùng nó để xây dựng mảnh SQL động bằng nối chuỗi.
4. Database ở lượt xử lý sau diễn giải dữ liệu đó thành cú pháp.

~~~java
// Lần ghi đầu tiên có thể an toàn.
saveDisplayNameUsingPreparedStatement(input);

// Lần xử lý khác vẫn có thể sai nếu nối giá trị đã đọc vào SQL.
String sql = "SELECT id FROM customers WHERE display_name = '"
        + storedDisplayName + "'";
~~~

Đây là **second-order SQL injection**. Nguồn dữ liệu không đáng tin không trở nên đáng tin chỉ vì nó đã qua một lần lưu trữ.

Tất cả đường truy cập dữ liệu — **HTTP request, event consumer, import/export job, migration, báo cáo, script nội bộ** — đều cần tuân thủ cùng ranh giới **cú pháp tĩnh/giá trị binding**.

## 19. Stored procedure, query builder và escaping không phải phép màu

Có nhiều công cụ được sử dụng để tổ chức SQL, nhưng mức an toàn phụ thuộc **cách truyền giá trị**:

| Kỹ thuật | Khi nào có thể an toàn? | Khi nào vẫn nguy hiểm? |
| --- | --- | --- |
| **JDBC PreparedStatement** | SQL cấu trúc do code kiểm soát, input chỉ bind làm giá trị | Nối input vào SQL trước prepare |
| **Spring JdbcTemplate** | Dùng tham số JDBC trong query/update | Nối sort field/table vào SQL tùy ý |
| **JPA/Hibernate JPQL** | Dùng setParameter hoặc Criteria parameters | Ghép input vào JPQL/HQL/raw SQL |
| **Stored procedure** | Procedure dùng tham số kiểu và không sinh SQL động không kiểm soát | Procedure tự nối input rồi EXECUTE |
| **Query builder/DSL** | Sử dụng API typed values và allowlist cấu trúc | Dùng raw fragment hoặc unsafe literal interpolation |
| **Escaping thủ công** | Có thể là biện pháp tình thế trong trường hợp đặc biệt được kiểm chứng | Bỏ sót ngữ cảnh, encoding, DBMS mode hoặc loại dữ liệu |

Không khuyến nghị lấy **manual escaping** làm phòng tuyến chính cho mọi giá trị. Quy tắc escape thay đổi giữa chuỗi, LIKE pattern, identifier, JSON path, regex, binary và các hệ quản trị. Một hàm **sanitizeSql(String)** tự viết khó có thể thay thế việc binding đúng ngữ cảnh.

**PreparedStatement không nhất thiết có nghĩa server tạo và giữ một compiled plan cố định từ lần đầu.** Driver/DBMS có thể dùng protocol hoặc cache kế hoạch khác nhau. Bảo đảm quan trọng ở đây là **giá trị không được ghép làm cú pháp SQL**, không phải lời hứa về hiệu năng của server-side prepared statements.

## 20. SQL động có kiểm soát: thiết kế API thay vì nhận SQL fragment

Một yêu cầu như **“cho phép người dùng gửi WHERE condition bất kỳ”** là tín hiệu thiết kế nguy hiểm. Không nên cung cấp API:

~~~text
GET /reports?where=...
GET /orders?sortExpression=...
~~~

rồi chèn nguyên chuỗi đó vào câu SQL. Thay bằng **hợp đồng dữ liệu hữu hạn**:

~~~text
GET /orders?status=PAID&sort=createdAt&direction=desc&pageSize=50
~~~

Ứng dụng xử lý:

1. Parse **status** thành tập enum hợp lệ.
2. Parse **sort** thành lựa chọn cột đã định nghĩa trong code.
3. Parse **direction** thành ASC/DESC hợp lệ.
4. Kiểm tra **pageSize** trong phạm vi giới hạn.
5. Xây dựng query từ **các mảnh SQL cố định**.
6. Bind **status, tenantId và pageSize** như các giá trị.
7. Áp kiểm tra **authorization** ở service và ràng buộc tenant trong truy vấn.

Nếu sản phẩm thật sự cần ngôn ngữ lọc linh hoạt, hãy thiết kế **AST/DSL riêng có parser và allowlist về field, toán tử, depth, cost, số điều kiện**, rồi dịch nó sang SQL đã được binding. Không coi một chuỗi “đã được kiểm tra bằng regex” là một ngôn ngữ SQL an toàn.

## 21. Transaction, constraint và parameter binding là ba lớp khác nhau

Một ví dụ chuyển điểm thưởng gồm hai thao tác ghi:

~~~text
BEGIN
  UPDATE rewards trừ điểm ở tài khoản A
  UPDATE rewards cộng điểm ở tài khoản B
COMMIT
~~~

Nếu mỗi UPDATE dùng placeholder, ứng dụng đã chống injection cho **giá trị** nhưng vẫn có thể sai nếu:

- UPDATE thứ nhất commit riêng, UPDATE thứ hai lỗi.
- Số điểm âm hoặc vượt số dư mà không có điều kiện bảo vệ.
- Hai transaction cạnh tranh tạo lost update.
- Client retry sau timeout và thực hiện chuyển điểm hai lần.

Vì vậy cần phối hợp:

| Lớp | Trách nhiệm |
| --- | --- |
| **Parameter binding** | Không cho input trở thành cú pháp SQL |
| **Validation** | Đầu vào phù hợp quy tắc nghiệp vụ |
| **Authorization/tenant scope** | Caller được phép truy cập và sửa đúng resource |
| **Database constraints** | UNIQUE, CHECK, NOT NULL, FOREIGN KEY bảo vệ bất biến tại DB |
| **Transaction** | Nhiều câu SQL commit hoặc rollback cùng nhau |
| **Concurrency control** | Cập nhật có điều kiện, version, locking hoặc isolation phù hợp |
| **Idempotency** | Retry không tạo tác động nghiệp vụ lặp |
| **Least privilege** | Giới hạn phạm vi thiệt hại nếu một lớp khác có lỗi |

Không nên diễn giải “dùng PreparedStatement” thành “toàn bộ tầng persistence đã an toàn”.

## 22. Quyền database tối thiểu và bảo vệ kết nối

Ngay cả khi mọi query đã tham số hóa, tầng persistence vẫn cần **defense in depth**:

- **Tài khoản DB riêng** cho ứng dụng và các job theo nhu cầu; không dùng superuser để phục vụ HTTP request.
- Chỉ cấp **SELECT/INSERT/UPDATE/DELETE** trên những bảng và schema cần thiết; quyền DDL/migration nên được tách ra.
- Dùng **TLS/xác thực server** theo chính sách bảo mật, không chỉ bật mã hóa mà bỏ qua kiểm tra chứng chỉ/hostname.
- Bảo vệ credential bằng secret manager hoặc hạ tầng phù hợp; tránh hard-code và không log JDBC URL có chứa mật khẩu.
- Giới hạn kết nối đến DB bằng network controls, quyền truy cập hạ tầng và audit.
- Đặt **statement timeout, lock timeout, pool acquisition timeout và resource limits** theo workload để hạn chế truy vấn tốn tài nguyên; timeout không thay thế injection prevention.
- Không cung cấp cho tài khoản ứng dụng quyền đọc tất cả dữ liệu “để tiện debug”.
- Tách tài khoản truy cập **read replica** hoặc reporting khi có mục tiêu và ranh giới quyền riêng.

Quyền tối thiểu không thể sửa logic injection, nhưng giúp giảm ảnh hưởng nếu một chỗ nào đó vẫn ghép SQL không an toàn hoặc có lỗi ủy quyền.

## 23. Log SQL và quan sát lỗi một cách an toàn

Khi cần debug, nhóm phát triển có thể muốn log toàn bộ SQL kèm giá trị tham số. Tuy nhiên, email, token, thông tin thẻ, địa chỉ hoặc dữ liệu cá nhân có thể bị ghi ra log.

Tốt hơn nên lưu:

- **Tên thao tác/query template ID**, không cần mọi giá trị bind.
- **Độ trễ, số hàng, SQLSTATE, loại exception, thời gian chờ pool**.
- **Correlation ID**, tenant ID đã xác thực theo chính sách phân quyền log.
- **Tỷ lệ query timeout, unique violation, syntax error và authorization denial**.
- **Cảnh báo** nếu một đường code còn dùng API Statement với nối chuỗi hoặc native SQL không được kiểm soát.

Với PostgreSQL, lỗi **syntax error** có thể giúp phát hiện những đoạn query động sai, nhưng **không chứng minh hệ thống đã bị SQL injection**. Ngược lại, ứng dụng có thể bị injection qua mệnh đề SQL hợp lệ mà không sinh lỗi syntax. Cần kết hợp code review, test bảo mật và telemetry.

Khi cần ghi giá trị để điều tra, áp **masking, sampling, retention và kiểm soát truy cập**. Không dùng log SQL đầy đủ làm mặc định trên production.

## 24. Kiểm thử phòng chống SQL injection

Mục tiêu của kiểm thử không phải chỉ là chứng minh một chuỗi đặc biệt làm câu SQL thất bại. **Điều cần chứng minh là nội dung đầu vào không thể thay đổi cấu trúc lệnh hoặc mở rộng phạm vi truy cập**.

Một ma trận kiểm thử:

| Đầu vào | Kỳ vọng với truy vấn tham số hóa |
| --- | --- |
| Email bình thường | Tìm đúng bản ghi |
| **O'Brien@example.com** | Không lỗi cú pháp; tìm theo đúng chuỗi literal |
| Chuỗi **' OR '1'='1** | Là một giá trị so sánh; không trả toàn bộ bảng |
| Chuỗi có **;** hoặc dấu mở comment | Không được tạo thêm SQL statement |
| Chuỗi Unicode, dấu tiếng Việt | Được xử lý theo kiểu, collation và validation đúng |
| LIKE term chứa **%/_** | Escape pattern nếu nghiệp vụ muốn tìm literal |
| Danh sách **IN** rỗng | Trả kết quả rỗng hoặc lỗi validation rõ ràng, không dựng IN () sai |
| Danh sách **IN** quá lớn | Bị giới hạn bởi API để tránh lạm dụng tài nguyên |
| Sort field không thuộc allowlist | Bị từ chối, không nối vào ORDER BY |
| Tenant ID của người khác | Không được trả tài nguyên dù các tham số đều binding đúng |
| String lưu trong DB rồi chạy job | Không được ghép thẳng thành cú pháp SQL ở lần xử lý sau |

### 24.1. Ví dụ kiểm thử JDBC trên database thật

Mã giả JUnit dưới đây mô tả ý tưởng, không phụ thuộc vào một bộ khởi tạo fixture cụ thể:

~~~java
@Test
void specialEmailMustRemainAValue() throws Exception {
    String unusual = "O'Brien@example.com";
    long tenantId = 10L;

    // Arrange: insert fixture bằng PreparedStatement.
    seedCustomerUsingBoundParameters(tenantId, unusual);

    // Act: repository cũng dùng PreparedStatement.
    CustomerLookup.Customer customer =
            repository.findByEmail(tenantId, unusual);

    // Assert: truy vấn không hỏng cú pháp và trả đúng bản ghi.
    assertNotNull(customer);
    assertEquals(unusual, customer.email());
}
~~~

Với test có input trông giống một biểu thức SQL, hãy xác minh repository **không trả thêm hàng**, không bỏ qua tenant scope và không phát sinh tác dụng ngoài ý muốn. Mã giả **seedCustomerUsingBoundParameters**, **repository** và assertions cần được cung cấp bởi test fixture thực tế.

Các test quan trọng khác:

1. Test **JDBC PreparedStatement** thực hiện binding đúng thứ tự/kiểu.
2. Test **JdbcTemplate/NamedParameterJdbcTemplate** với filter optional và IN list.
3. Test **JPA JPQL và native query**, không chỉ test repository method đơn giản.
4. Test **dynamic ORDER BY** từ allowlist với input lạ.
5. Test **batch import/consumer**, vì nguồn nguy hiểm có thể đến từ file hoặc message.
6. Test **second-order injection** khi dữ liệu được lưu rồi tham gia query/report sau này.
7. Test **tenant isolation** riêng biệt: người dùng tenant A không thấy/sửa được dữ liệu của B.
8. Test **phân quyền DB** bằng tài khoản ứng dụng production-like, không chạy mọi test dưới superuser.

## 25. Code review và static analysis: nhận diện đường nguy hiểm

Khi review code Java, hãy xem mọi nơi tạo SQL:

~~~text
DriverManager / Connection.createStatement
Connection.prepareStatement
JdbcTemplate.query/update
NamedParameterJdbcTemplate
EntityManager.createQuery/createNativeQuery
Hibernate createQuery/createNativeQuery
Query DSL / raw SQL fragment helpers
Migration / admin scripts / report builders
~~~

Tập trung vào luồng:

~~~text
Nguồn dữ liệu không tin cậy
           |
           v
Chuỗi được biến đổi / lưu / đọc lại
           |
           v
String concatenation / String.format / text block interpolation
           |
           v
API chạy SQL/JPQL
~~~

**Không phải mọi phép nối chuỗi đều là lỗ hổng.** Nối **" AND status = ?"** là thêm một mảnh SQL cố định; nối **statusFromRequest** như cú pháp mới là điều nguy hiểm. Công cụ static analysis nên giúp xác định nguồn input và điểm thực thi SQL, nhưng cần review ngữ cảnh để phân biệt cấu trúc cố định và dữ liệu.

Một checklist code review ngắn:

- Mọi **value** đến từ HTTP, file, event hoặc dữ liệu lưu được truyền qua binding chưa?
- Mọi **identifier/keyword/operator** động có map allowlist do code sở hữu không?
- Có đường dùng **Statement.execute(sql)** với SQL ghép dữ liệu không?
- Có helper “escapeSql” tùy ý thay cho PreparedStatement không?
- Có **LIKE, IN, ORDER BY, JSON/path, LIMIT** hoặc truy vấn báo cáo động bị bỏ sót không?
- Có **native SQL** trong ORM hoặc stored procedure tự dựng SQL không?
- Có xác thực tenant/resource, quyền DB tối thiểu và timeout hợp lý không?
- Có test trên database đúng loại và phiên bản được dùng không?

## 26. Những sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Ghép email/status vào WHERE trong dấu nháy | Input có thể đổi cú pháp SQL | **WHERE col = ?** và **setString** |
| Gọi prepareStatement sau khi đã ghép input vào SQL | Placeholder không còn bảo vệ phần ghép | Chỉ ghép fragment tĩnh, bind mọi giá trị |
| Dùng **ORDER BY ?** để chọn cột | Placeholder không phải identifier | Enum/allowlist ánh xạ sang tên cột cố định |
| Nối chuỗi ID vào **IN (...)** | Có thể injection, lỗi kiểu và giới hạn | Tạo placeholder theo số phần tử hoặc bind SQL array |
| Tưởng LIKE binding biến **%/_** thành literal | Kết quả tìm kiếm rộng hơn mong muốn | Escape wildcard theo ngữ cảnh bên cạnh binding |
| Chỉ sanitize dấu nháy đơn | Bỏ sót encoding và các ngữ cảnh khác | PreparedStatement và allowlist |
| Dùng ORM nên bỏ qua review native SQL | JPQL/HQL/native SQL vẫn có thể injection | setParameter/typed Criteria và audit fragment |
| Tin dữ liệu đọc từ DB luôn an toàn | Second-order injection | Bind lại ở mọi truy vấn mới |
| Cho client gửi tenantId tùy ý | Lộ dữ liệu dù không injection | Authorization context và tenant scope |
| Bind đúng nhưng UPDATE thiếu WHERE | Sửa nhiều hàng do lỗi logic | Điều kiện nghiệp vụ, row count và transaction |
| Dùng tài khoản DB superuser cho ứng dụng | Mở rộng thiệt hại khi có lỗi | Quyền tối thiểu, tài khoản migration riêng |
| Log SQL cùng token/password | Lộ dữ liệu qua log | Redaction, query template ID, phân quyền log |
| Để client tự gửi SQL filter hoàn chỉnh | Biến API thành giao diện thực thi cú pháp | DSL hữu hạn, parser/allowlist và cost limits |
| Không kiểm thử ký tự Unicode/dấu nháy | Sai dữ liệu hợp lệ hoặc cú pháp lỗi | Test đầu vào đặc biệt với DB thật |

## 27. Bài tập thực hành

### Bài 1. Phát hiện đoạn code không an toàn

~~~java
String sql = "SELECT id FROM accounts WHERE username = '"
        + username + "'";
~~~

Điểm sai là gì? Viết lại bằng JDBC.

**Gợi ý:** SQL chứa dữ liệu username được nối trực tiếp. Dùng **SELECT id FROM accounts WHERE username = ?** và **PreparedStatement.setString(1, username)**.

### Bài 2. Chuỗi có dấu nháy

Một khách hàng có họ **O'Brien**. Nếu form tra cứu dùng binding, giá trị này có làm câu SQL bị lỗi vì dấu nháy không?

**Gợi ý:** Không, khi gửi qua **setString**, dấu nháy thuộc giá trị chuỗi. Không cần tự thêm dấu escape SQL vào tên khách hàng.

### Bài 3. Dynamic sort

API nhận **sort=createdAt** hoặc **sort=amount**, cùng **direction=asc/desc**. Vì sao không dùng **ORDER BY ? ?**?

**Gợi ý:** Placeholder không thay thế được tên cột/hướng sắp xếp. Parse enum, ánh xạ tới các SQL fragments hard-code, rồi bind các giá trị lọc riêng.

### Bài 4. Danh sách ID

API nhận **ids=[1,2,3]**, cần truy vấn PostgreSQL bằng JDBC. Có thể dùng một **setString(1, "1,2,3")** cho **IN (?)** để tìm ba ID không?

**Gợi ý:** Không. Một placeholder đại diện một giá trị. Tạo ba placeholder **IN (?, ?, ?)** và bind từng ID, hoặc dùng **PostgreSQL array** với **ANY (?)**.

### Bài 5. LIKE và wildcard

Người dùng nhập phần tên **100%** với mong muốn tìm đúng ký tự phần trăm. Truy vấn **ILIKE ?** đã binding term thì có cần xử lý gì nữa không?

**Gợi ý:** Có, nếu sản phẩm yêu cầu literal matching. **%** vẫn là wildcard trong LIKE; cần escape ký tự mẫu và escape character. Đây là vấn đề semantics tìm kiếm, tách biệt với injection.

### Bài 6. JPA không miễn nhiễm

Một method **EntityManager.createQuery(...)** xây JPQL bằng cách nối **statusFromRequest**. Liệu Hibernate tự bảo vệ câu lệnh không?

**Gợi ý:** Không. Phải dùng **:status** và **setParameter** hoặc Criteria API. ORM không vô hiệu hóa input đã chèn vào cú pháp truy vấn.

### Bài 7. SQL có tham số nhưng vẫn lộ dữ liệu

Một query dùng **WHERE tenant_id = ?** nhưng service bind tenantId lấy từ header do client tự gửi mà không kiểm tra quyền. Có an toàn không?

**Gợi ý:** An toàn hơn về SQL injection nhưng **không an toàn về authorization**. Tenant phải được lấy/kiểm chứng từ danh tính và quyền của người gọi, cùng kiểm tra resource tương ứng.

### Bài 8. Second-order injection

Một chuỗi đã được lưu bằng PreparedStatement từ tuần trước. Batch job hôm nay đọc chuỗi đó rồi ghép vào SQL báo cáo. Vì sao vẫn có rủi ro?

**Gợi ý:** Dữ liệu lưu trữ không trở nên đáng tin. Batch job đã biến giá trị thành cú pháp trong lượt truy vấn mới; phải binding lại.

### Bài 9. Quyền database tối thiểu

Tất cả API đọc và ghi đều dùng PreparedStatement. Có thể cho tài khoản kết nối DB quyền tạo/xóa toàn bộ schema để đơn giản hóa vận hành không?

**Gợi ý:** Không nên. SQL injection prevention không giải quyết mọi lỗi code hoặc lộ credential. Dùng tài khoản chỉ có quyền cần thiết và tài khoản migration riêng.

### Bài 10. Kiểm thử đúng mục tiêu

Bạn gửi một chuỗi thử nghiệm chứa dấu nháy qua API. Query không báo lỗi. Điều đó có đủ chứng minh API không có injection không?

**Gợi ý:** Chưa đủ. Cần xác minh phạm vi hàng trả về, quyền tenant, cấu trúc SQL, các nhánh sort/IN/LIKE/native query, trường hợp second-order và các điểm thực thi khác. Thử nhiều input nhưng quan trọng hơn là review đường dữ liệu và binding.

### Bài 11. Transaction

Hai câu UPDATE có placeholder đều an toàn về injection, nhưng câu thứ nhất đã commit còn câu thứ hai lỗi. Loại rủi ro nào đang xảy ra?

**Gợi ý:** Sai **transaction boundary/atomicity**, không phải SQL injection. Cần gộp các bước nghiệp vụ vào transaction và xử lý rollback phù hợp.

### Bài 12. Query builder tùy ý

Đội sản phẩm muốn hỗ trợ các điều kiện tìm kiếm phức tạp. Có nên nhận một chuỗi SQL WHERE đầy đủ từ trình duyệt rồi “xóa dấu nháy đơn” trước khi chạy không?

**Gợi ý:** Không. Thiết kế bộ lọc cấu trúc có field/operator allowlist, giới hạn depth/độ phức tạp và ánh xạ thành predicate có binding; không nhận SQL tự do từ client.

## 28. Checklist áp dụng trong dự án Java

1. **Nguồn input:** đánh dấu các giá trị đến từ HTTP, file, message, cache và database mà người dùng có thể ảnh hưởng.
2. **Truy vấn tĩnh:** SELECT/UPDATE/DELETE/INSERT dùng placeholder cho mọi giá trị chưa tin cậy.
3. **Kiểu binding:** setLong, setString, setBigDecimal, setObject/setNull đúng kiểu, không tự ghép định dạng ngày/tiền.
4. **SQL động:** mọi identifier, ORDER BY, direction, toán tử được chọn từ allowlist.
5. **LIKE:** binding và escape ký tự mẫu nếu cần semantics literal.
6. **IN:** mảng/list tạo placeholder theo số phần tử đã giới hạn hoặc dùng array parameter được driver hỗ trợ.
7. **ORM:** kiểm tra JPQL/HQL/native SQL và những extension nhận raw fragments.
8. **Quyền:** tenant ID từ ngữ cảnh xác thực, resource authorization, least-privilege DB user.
9. **Transaction:** câu ghi cần atomicity, concurrency control và idempotency độc lập với injection prevention.
10. **Tài nguyên:** page size, timeout, số điều kiện, tổng số ID và tốc độ request có giới hạn.
11. **Log:** không in credential/token/payload nhạy cảm, dùng correlation ID và mã lỗi phù hợp.
12. **Kiểm thử:** chuỗi có dấu nháy, input giống SQL, Unicode, LIKE wildcards, unknown sort, empty/huge IN, tenant khác và second-order.
13. **Review:** tìm String concatenation, format/interpolation gần điểm chạy SQL trong mọi thư viện truy cập dữ liệu.
14. **Triển khai:** dùng database/driver tương thích khi test; không coi mock JDBC là đủ chứng minh hành vi parser và kiểu dữ liệu.

## 29. Tổng kết

**SQL injection xảy ra khi một giá trị không đáng tin bị đưa vào vị trí mà database diễn giải như cú pháp lệnh.** Phòng tuyến mạnh nhất cho giá trị là **tham số hóa truy vấn**: giữ cấu trúc SQL do code quyết định và sử dụng **PreparedStatement/JdbcTemplate/JPA parameters** để truyền các giá trị. Với những phần **không thể binding** như tên bảng, tên cột, hướng sort hoặc toán tử, hãy dùng **allowlist** thay vì nối chuỗi tùy ý hay tự viết bộ lọc ký tự.

Tuy nhiên, ứng dụng persistence an toàn cần nhiều lớp phối hợp: **validation, authorization/tenant isolation, transaction, constraint, concurrency control, idempotency, quyền DB tối thiểu và log an toàn**. Khi tất cả các luồng nhập liệu, truy vấn ứng dụng, batch job và ORM đều tuân thủ ranh giới giữa **cú pháp và dữ liệu**, hệ thống Java có thể xử lý những chuỗi đầu vào phức tạp mà không biến chúng thành mệnh lệnh vượt ngoài ý định nghiệp vụ.
