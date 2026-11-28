# SQL injection

## 1. SQL injection bắt đầu ở ranh giới giữa dữ liệu và câu lệnh

Một API tìm tài liệu nhận tên tài liệu từ người dùng. Lập trình viên muốn thêm giá trị đó vào điều kiện `WHERE`, nhưng lại nối trực tiếp vào chuỗi SQL. Khi giá trị đầu vào chứa ký tự có ý nghĩa trong ngôn ngữ SQL, database có thể hiểu một phần dữ liệu thành điều kiện hoặc cấu trúc truy vấn.

**SQL injection** là lỗi khiến dữ liệu không đáng tin cậy có khả năng thay đổi cú pháp hoặc logic của câu lệnh SQL mà ứng dụng thực thi.

Nguồn dữ liệu không chỉ là ô nhập trên giao diện. Nó có thể đến từ query parameter, JSON, header, file import, message queue, hệ thống đối tác hoặc một bản ghi đã được lưu trong database. Điều quyết định là dữ liệu đó được sử dụng thế nào tại nơi xây dựng câu lệnh.

Trong thiết kế yêu cầu bảo mật, mục tiêu không nên chỉ là “chặn chuỗi có dấu nháy”. Cần thiết lập một bất biến:

> Dữ liệu không đáng tin cậy không được trở thành cú pháp SQL. Cấu trúc truy vấn do ứng dụng kiểm soát; giá trị động được truyền bằng cơ chế binding phù hợp.

Bất biến này cần được giữ ở mọi đường đi tới database, bao gồm API chính, báo cáo, tác vụ nền, chức năng quản trị và stored procedure.

## 2. Ví dụ nhỏ: điều kiện tenant bị vô hiệu hóa

Giả sử mỗi tài liệu thuộc một tenant và người dùng chỉ được tìm tài liệu trong tenant đã xác thực. Đây là cách xây truy vấn không an toàn:

~~~java
String sql =
        "SELECT id, title FROM document "
        + "WHERE tenant_id = " + authenticatedTenantId
        + " AND title = '" + requestedTitle + "'";
~~~

Với tên tài liệu bình thường, chuỗi SQL có vẻ đúng. Nhưng nếu `requestedTitle` là:

~~~text
x' OR '1'='1
~~~

Câu lệnh trở thành:

~~~sql
SELECT id, title
FROM document
WHERE tenant_id = 42
  AND title = 'x' OR '1'='1'
~~~

Với ưu tiên toán tử SQL thông thường, biểu thức trên có nghĩa tương đương:

~~~sql
WHERE (tenant_id = 42 AND title = 'x')
   OR ('1' = '1')
~~~

Nhánh luôn đúng có thể làm truy vấn trả về tài liệu ngoài tenant 42 nếu tài khoản database và các lớp kiểm soát khác cho phép.

Ví dụ này không cần thực thi nhiều câu lệnh, không cần dấu chấm phẩy và không cần mở thêm kết nối. Vì thế, tắt tính năng multiple statements không xử lý tận gốc SQL injection.

Dấu nháy trong dữ liệu cũng có thể hoàn toàn hợp lệ. Một tiêu đề như `O'Reilly guide` phải được xử lý như dữ liệu thông thường khi đáp ứng yêu cầu nghiệp vụ. Cấm dấu nháy để che lỗi nối chuỗi vừa gây mất chức năng vừa không tạo được một ranh giới an toàn có thể chứng minh.

Các chuỗi trong bài chỉ dùng để giải thích và xây tiêu chí kiểm chứng trên môi trường được phép, không phải hướng dẫn chạy truy vấn trên hệ thống ngoài phạm vi kiểm soát.

## 3. Từ lỗi kỹ thuật đến rủi ro nghiệp vụ

Tác động phụ thuộc vào truy vấn, quyền database, kiến trúc và dữ liệu. Không phải lỗ hổng nào cũng có mọi hậu quả, nhưng đặc tả cần xét những khả năng phù hợp với hệ thống.

| Nhóm tác động | Ví dụ trong nền tảng tài liệu | Điều cần bảo vệ |
|---|---|---|
| Mất bí mật | Đọc tài liệu của tenant khác | Phân vùng dữ liệu và quyền đọc |
| Mất toàn vẹn | Thay trạng thái tài liệu hoặc metadata trái phép | Quyền ghi và quy tắc nghiệp vụ |
| Bỏ qua kiểm soát | Làm điều kiện kiểm tra không còn đúng | Luồng xác thực/phân quyền |
| Mất sẵn sàng | Truy vấn tiêu tốn tài nguyên hoặc khóa dữ liệu | Giới hạn tài nguyên và vận hành |
| Lộ cấu trúc | Error response chứa bảng, cột, query hoặc thông tin kết nối | Bề mặt thông tin lỗi |
| Lan rộng sự cố | Tài khoản runtime có quyền quản trị rộng | Phạm vi quyền của tài khoản kết nối |

SQL injection khác với lỗi phân quyền thuần túy. Một truy vấn được bind đúng vẫn có thể trả dữ liệu tenant khác nếu ứng dụng nhận `tenant_id` từ client mà không kiểm tra quyền. Ngược lại, có kiểm tra quyền ở controller không cứu được một repository cho phép input thay đổi câu lệnh.

Vì vậy cần hai điều kiện độc lập:

1. Câu lệnh giữ được ranh giới giữa code và data.
2. Câu lệnh và luồng nghiệp vụ chỉ truy cập tài nguyên mà chủ thể được phép.

## 4. Nhìn theo luồng source–sink

Một cách phân tích hữu ích là lần theo dữ liệu từ nguồn tới điểm thực thi:

~~~mermaid
flowchart LR
    A[HTTP, file, queue, dữ liệu đã lưu] --> B[Parse và kiểm tra nghiệp vụ]
    B --> C[Service xác định tenant và quyền]
    C --> D[Repository hoặc query builder]
    D --> E[SQL template và parameter binding]
    E --> F[Driver và database]
~~~

**Source** là nơi dữ liệu ngoài vùng tin cậy đi vào luồng. **Sink** là API hoặc cơ chế khiến SQL được thực thi.

Các sink cần kiểm soát có thể gồm:

- `Statement.executeQuery` và các hàm execute tương tự.
- `Connection.prepareStatement` khi chuỗi SQL đã được xây bằng dữ liệu không đáng tin.
- Native query của ORM.
- JPQL/HQL được dựng bằng nối chuỗi.
- SQL động bên trong stored procedure.
- Công cụ báo cáo tạo truy vấn từ cấu hình do người dùng hoặc đối tác cung cấp.

Một chuỗi không trở nên đáng tin chỉ vì nó đã đi qua hàm validation, đã được đưa vào một object hoặc đã được đọc từ database. Cần xem nó có còn khả năng đi vào phần cú pháp hay không.

Đường đi ít gặp cũng phải có owner: export ban đêm, tiện ích hỗ trợ khách hàng và một API quản trị nội bộ có thể dùng cùng dữ liệu nhưng xây SQL theo cách khác.

## 5. Biện pháp chính: parameterized query

Câu lệnh có tham số giữ cấu trúc SQL tách khỏi các giá trị động.

~~~sql
SELECT id, title
FROM document
WHERE tenant_id = ?
  AND title = ?
ORDER BY id
~~~

Ứng dụng bind tenant và title vào đúng vị trí. Một giá trị chứa dấu nháy hoặc chữ `OR` vẫn được xử lý như giá trị, không thành mệnh đề SQL mới.

OWASP khuyến nghị dùng parameterized query cho dữ liệu động; các phần cấu trúc không thể bind như tên cột hoặc chiều sắp xếp cần được chọn từ mapping cố định do ứng dụng sở hữu. Tự escape toàn bộ input là cách dễ sai và không nên làm cơ chế bảo vệ chính. [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html#primary-defenses)

Có hai điểm phải kiểm tra đồng thời:

- Chuỗi template được tạo từ những thành phần nào?
- Giá trị không đáng tin được truyền qua bind API hay đã bị ghép vào template trước đó?

Tên class `PreparedStatement` không tự bảo đảm an toàn nếu chuỗi SQL truyền vào đã chứa input nối trực tiếp.

### Một cách dùng PreparedStatement vẫn sai

~~~java
String sql =
        "SELECT id FROM document WHERE title = '" + requestedTitle + "'";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    // SQL đã chứa input trong phần cú pháp trước khi tới đây.
    statement.executeQuery();
}
~~~

Việc gọi `prepareStatement` sau khi nối chuỗi không thể khôi phục ranh giới đã mất.

### Ví dụ JDBC với binding

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class DocumentRepository {
    private final DataSource dataSource;

    public DocumentRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public record DocumentSummary(long id, String title) {
    }

    public List<DocumentSummary> findByTitle(
            long authorizedTenantId,
            String requestedTitle
    ) throws SQLException {
        Objects.requireNonNull(requestedTitle, "requestedTitle");

        String sql = """
                SELECT id, title
                FROM document
                WHERE tenant_id = ?
                  AND title = ?
                ORDER BY id
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, authorizedTenantId);
            statement.setString(2, requestedTitle);

            try (ResultSet resultSet = statement.executeQuery()) {
                List<DocumentSummary> result = new ArrayList<>();
                while (resultSet.next()) {
                    result.add(new DocumentSummary(
                            resultSet.getLong("id"),
                            resultSet.getString("title")
                    ));
                }
                return List.copyOf(result);
            }
        }
    }
}
~~~

Trong ví dụ:

- SQL template không phụ thuộc nội dung của `requestedTitle`.
- `setLong` và `setString` truyền giá trị theo kiểu tương ứng.
- Tenant là phạm vi đã được xác định bởi lớp xác thực/phân quyền; tham số của method không tự chứng minh người gọi có quyền chọn tenant đó.
- Resource JDBC được đóng bằng try-with-resources.
- Pagination, hạn mức kết quả và timeout vẫn cần thiết kế theo yêu cầu vận hành của endpoint.

JDBC mô tả `PreparedStatement` và các setter có kiểu cho tham số. Việc chọn kiểu cần tương thích với kiểu SQL thực tế và cấu hình driver. [Java PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html)

Không cần hứa rằng mọi driver đều gửi cùng một dạng wire protocol hoặc luôn dùng cùng kế hoạch thực thi. Yêu cầu bảo mật là sử dụng đúng cơ chế binding được driver hỗ trợ, với template không bị input chi phối ngoài những nhánh cấu trúc đã kiểm soát.

## 6. Những phần không thể thay bằng dấu hỏi

Parameter binding chủ yếu dành cho **giá trị**. Không dùng placeholder để cho người dùng chọn tùy ý từ khóa, tên bảng hoặc một đoạn biểu thức SQL.

Ví dụ sau không có nghĩa “sắp xếp theo cột mà client gửi”:

~~~sql
SELECT id, title
FROM document
WHERE tenant_id = ?
ORDER BY ?
~~~

Tùy database, nó có thể là lỗi hoặc sắp xếp theo một giá trị/biểu thức hằng; nó không phải cơ chế bind identifier tổng quát.

Những phần cần phân biệt:

| Thành phần động | Cách thiết kế |
|---|---|
| Tên hoặc giá trị tìm kiếm | Bind bằng tham số |
| Tenant ID, resource ID | Bind và kiểm tra phạm vi quyền |
| Tên cột sort | Mapping từ lựa chọn hữu hạn sang tên cột cố định |
| `ASC` / `DESC` | Enum hoặc mapping cố định |
| Tên bảng theo loại báo cáo | Mapping cố định và kiểm tra quyền dùng loại báo cáo |
| Danh sách `IN` | Placeholder cho từng giá trị hoặc cơ chế collection được hỗ trợ |
| Điều kiện filter | Mô hình filter có kiểu và tập toán tử được phép |
| Raw `WHERE` hoặc raw SQL | Không nhận như dữ liệu thông thường của API nghiệp vụ |

### Mapping cho sắp xếp

Giả sử API chỉ cho phép sort theo ID hoặc thời điểm tạo:

~~~java
enum DocumentSort {
    ID_ASC("id ASC"),
    CREATED_DESC("created_at DESC, id DESC");

    private final String sqlFragment;

    DocumentSort(String sqlFragment) {
        this.sqlFragment = sqlFragment;
    }

    String sqlFragment() {
        return sqlFragment;
    }

    static DocumentSort fromApi(String value) {
        return switch (value) {
            case "id_asc" -> ID_ASC;
            case "created_desc" -> CREATED_DESC;
            default -> throw new IllegalArgumentException("Unsupported sort");
        };
    }
}
~~~

Repository có thể ghép fragment từ enum vào template; dữ liệu tìm kiếm vẫn bind:

~~~java
String sql = """
        SELECT id, title
        FROM document
        WHERE tenant_id = ?
          AND title = ?
        ORDER BY
        """ + sort.sqlFragment();
~~~

Chuỗi `sort.sqlFragment()` là hằng do ứng dụng sở hữu, không phải raw giá trị từ request. Luồng parse phải xử lý thiếu/null theo contract trước khi đi vào enum.

Một regex cho phép `[A-Za-z_]+` không thay thế mapping này: nó có thể chặn ký tự cú pháp nhưng vẫn cho client chọn một cột mà endpoint không được phép truy cập. Identifier hợp lệ về cú pháp không đồng nghĩa được phép sử dụng.

Quoting identifier bằng hàm của database cũng không tự giới hạn người dùng chỉ chọn các bảng/cột được nghiệp vụ cho phép. Kiểm soát cấu trúc và kiểm soát quyền phải cùng tồn tại.

## 7. IN, LIKE và filter động

### Danh sách IN

Không nối trực tiếp một chuỗi CSV từ client:

~~~java
// Không an toàn nếu requestedIds là raw string từ request.
String sql = "SELECT id FROM document WHERE id IN (" + requestedIds + ")";
~~~

Một phương án là parse thành danh sách có kiểu, giới hạn số phần tử và sinh số placeholder tương ứng. Nội dung giá trị không được dùng để tạo chuỗi SQL.

~~~text
Danh sách [11, 27, 35]
    -> SQL fragment: IN (?, ?, ?)
    -> bind lần lượt 11, 27, 35
~~~

Cần đặc tả cả danh sách rỗng, giá trị trùng, kiểu số không hợp lệ và số phần tử tối đa. Với API minh họa có thể chọn tối đa 100 ID; con số thực tế phải phù hợp giới hạn driver/database và nhu cầu vận hành.

Placeholder được tạo từ **số lượng phần tử đã giới hạn**, không phải từ việc “lọc ký tự nguy hiểm” trong CSV.

Một số stack hỗ trợ collection binding hoặc SQL array. Chọn cơ chế đúng với thư viện và database triển khai; không giả định mọi API JDBC đều mở rộng một tham số thành nhiều phần tử `IN`.

### LIKE

Binding vẫn cần được dùng khi tìm theo mẫu:

~~~java
String sql = """
        SELECT id, title
        FROM document
        WHERE tenant_id = ?
          AND title LIKE ?
        """;

statement.setLong(1, authorizedTenantId);
statement.setString(2, "%" + searchTerm + "%");
~~~

Nối `"%"` vào một **giá trị tham số** khác với nối input vào chuỗi SQL. Tuy nhiên, `%` và `_` có ý nghĩa wildcard trong `LIKE`. Nếu nghiệp vụ yêu cầu tìm literal, cần escape wildcard theo quy tắc và `ESCAPE` clause phù hợp dialect; đây là xử lý ngữ nghĩa pattern, không phải tự escape dấu nháy để xây SQL.

Không đặt placeholder vào bên trong chuỗi literal:

~~~sql
-- Không phải cách bind term cho tìm kiếm chứa:
WHERE title LIKE '%?%'
~~~

### Filter và biểu thức logic

Nếu API hỗ trợ kết hợp filter, nên parse thành cấu trúc có kiểu:

~~~text
field = status
operator = equals
value = PUBLISHED
~~~

Server ánh xạ field và operator sang một tập hữu hạn; chỉ value được bind. Không nhận raw biểu thức `WHERE` rồi cố kiểm tra bằng danh sách từ khóa cấm.

Cũng cần giữ đúng nhóm điều kiện:

~~~sql
WHERE tenant_id = ?
  AND (status = ? OR status = ?)
~~~

Một query không có injection vẫn có thể rò dữ liệu nếu builder bỏ ngoặc và làm `OR` thoát khỏi phạm vi tenant. Tính đúng logic truy vấn là yêu cầu riêng cần nghiệm thu.

## 8. ORM và query language không tự miễn nhiễm

ORM giúp tổ chức truy cập dữ liệu nhưng vẫn có các điểm nhận chuỗi truy vấn. Nếu nối input vào JPQL/HQL hoặc native SQL, lỗi ranh giới code–data có thể xuất hiện ở tầng đó.

Ví dụ không an toàn:

~~~java
String jpql =
        "SELECT d FROM DocumentEntity d WHERE d.title = '"
        + requestedTitle + "'";

entityManager.createQuery(jpql, DocumentEntity.class).getResultList();
~~~

Cách dùng named parameter:

~~~java
List<DocumentEntity> documents = entityManager
        .createQuery("""
                SELECT d
                FROM DocumentEntity d
                WHERE d.tenantId = :tenantId
                  AND d.title = :title
                ORDER BY d.id
                """, DocumentEntity.class)
        .setParameter("tenantId", authorizedTenantId)
        .setParameter("title", requestedTitle)
        .getResultList();
~~~

Tên entity và property trong ví dụ là giả định của mô hình ứng dụng. `setParameter` truyền giá trị cho tham số truy vấn; nó không biến một chuỗi JPQL đã nối input thành an toàn. Jakarta Persistence cung cấp API tạo query và bind tham số để triển khai cách tách này. [Jakarta EntityManager](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html), [Jakarta Query](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Query.html)

Khi dùng Criteria API hoặc query builder:

- Kiểm tra giá trị đi qua API biểu diễn value/parameter.
- Field động phải được ánh xạ sang property do server cho phép.
- Không truyền raw SQL fragment từ request qua một API có tên như `expression` hoặc `raw`.
- Native query cần cùng tiêu chuẩn như JDBC.
- Nếu framework nhận đối tượng sort từ client, kiểm tra cơ chế chuyển property sang biểu thức thay vì giả định mọi cấu hình đều an toàn.

OWASP có ví dụ parameterization cho JDBC và JPA/Hibernate. Cơ chế cụ thể phụ thuộc stack, nhưng điểm chung là giá trị được truyền riêng khỏi nội dung query. [OWASP Query Parameterization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html)

Một hàm repository được framework tạo tự động có thể an toàn cho value, trong khi một method native query bổ sung bên cạnh lại không an toàn. Đơn vị đánh giá là từng đường xây và thực thi truy vấn, không phải nhãn “dự án dùng ORM”.

## 9. Stored procedure: lời gọi an toàn chưa đủ

Một lời gọi có tham số tới stored procedure bảo vệ ranh giới ở lời gọi đó:

~~~java
try (var statement = connection.prepareCall(
        "{call find_document_by_title(?, ?)}")) {
    statement.setLong(1, authorizedTenantId);
    statement.setString(2, requestedTitle);
    statement.execute();
}
~~~

Tuy nhiên, bên trong procedure vẫn có thể nối giá trị đầu vào vào SQL động. Khi đó, outer call đã bind đúng nhưng sink bên trong vẫn nhận dữ liệu như cú pháp.

Yêu cầu cần bao trùm:

1. Lời gọi procedure dùng binding.
2. Procedure ưu tiên SQL tĩnh với tham số của procedure.
3. Nếu thực sự cần dynamic SQL, giá trị bên trong tiếp tục được bind bằng cơ chế của database.
4. Identifier động được chọn từ mapping cố định, không chỉ quote rồi cho phép truy cập mọi object.
5. Quyền thực thi và quyền hiệu lực của procedure được xác định rõ.

Cần xét cả procedure chạy với quyền người gọi hoặc quyền chủ sở hữu tùy database. Một procedure có quyền cao có thể tăng đáng kể tác động khi xây SQL không an toàn.

Không nên cấp role quản trị rộng cho tài khoản ứng dụng chỉ để “gọi procedure cho tiện”. Đặc tả phải ghi những procedure được phép gọi và những object cần truy cập.

## 10. Second-order SQL injection: dữ liệu đã lưu vẫn là dữ liệu

Một lỗi có thể không xuất hiện ngay lúc nhận input:

~~~text
Bước 1: Người dùng gửi tên hoặc cấu hình báo cáo.
Bước 2: Ứng dụng lưu dữ liệu bằng parameterized INSERT.
Bước 3: Job nền đọc lại dữ liệu.
Bước 4: Job nối dữ liệu vào SQL để tạo báo cáo.
Bước 5: Database diễn giải dữ liệu đó như cú pháp.
~~~

Bước 2 an toàn không làm bước 4 an toàn. Đây là dạng lỗi thường được gọi là **second-order SQL injection**: dữ liệu được lưu trước rồi mới trở thành nguy cơ khi sử dụng ở một truy vấn khác.

Ví dụ một bảng cấu hình có cột `saved_filter_value`. Cột này chứa dữ liệu, không được tự trở thành một đoạn `WHERE` vì nó “đã ở trong database”.

Các nguồn dễ bị bỏ sót:

| Nguồn đã lưu | Sink về sau cần kiểm soát |
|---|---|
| Tên hiển thị hoặc tên tài liệu | Truy vấn báo cáo dựng bằng nối chuỗi |
| File CSV import | Job đối soát đọc lại rồi tạo SQL |
| Cấu hình từ hệ thống đối tác | Query builder cho export |
| Giá trị do quản trị viên nhập | Stored procedure hoặc công cụ hỗ trợ |
| Message queue được lưu để retry | Worker xây lại query khi xử lý lại |

Nếu sản phẩm thực sự có chức năng để người có quyền viết SQL, đó là một capability riêng với mô hình tin cậy và phạm vi thực thi riêng. Không nên ngụy trang nó thành một trường filter thông thường rồi dùng cùng tài khoản database với ứng dụng nghiệp vụ.

Yêu cầu chống injection cần kiểm chứng ở **mỗi lần dùng dữ liệu tại sink**, không chỉ ở lần đầu dữ liệu đi qua API.

## 11. Input validation, escaping và WAF nằm ở đâu?

### Validation là lớp bổ sung

Validation giúp xác định dữ liệu có ý nghĩa cho nghiệp vụ:

- Resource ID có kiểu và phạm vi hợp lệ.
- Page size nằm trong giới hạn.
- Tên tài liệu không vượt độ dài đã chọn.
- Sort key thuộc enum.
- Filter operator nằm trong tập được hỗ trợ.

Nhưng validation không thay thế binding cho text hợp lệ. Một tên hợp lệ có dấu nháy không nên cần một ngoại lệ nối chuỗi đặc biệt.

Parse một ID thành `long` có thể loại bỏ nhiều biểu diễn không hợp lệ ở trường đó, nhưng không cho phép cả hệ thống bỏ parameterization hoặc bỏ kiểm tra quyền trên ID.

### Tự escape dấu nháy

Một hàm như `replace("'", "''")` không phải giải pháp tổng quát cho mọi vị trí SQL. Nó phụ thuộc dialect, encoding và ngữ cảnh; còn identifier, số, biểu thức và SQL động phía sau không được giải quyết bởi một hàm xử lý string literal.

Nếu code đã escape giá trị rồi tiếp tục bind, dữ liệu có thể bị lưu sai vì escape được coi là nội dung literal. Không nên trộn cơ chế theo thói quen mà không xác định điểm xây câu lệnh.

### WAF và bộ lọc từ khóa

WAF có thể góp phần phát hiện hoặc tạm hạn chế một số mẫu tấn công trong khi khắc phục, nhưng không chứng minh rằng query construction đã an toàn.

Danh sách cấm `SELECT`, `UNION`, `OR`, dấu nháy hoặc dấu chấm phẩy có thể:

- Chặn dữ liệu hợp lệ.
- Bỏ sót ngữ cảnh hoặc biểu diễn khác.
- Không áp dụng cho job nền, import hoặc dữ liệu đã lưu.
- Tạo cảm giác đã xử lý lỗi trong khi sink vẫn nối chuỗi.

Yêu cầu chính phải đặt tại nơi thực thi: value bind đúng, cấu trúc từ mapping tin cậy, quyền database phù hợp.

### Tắt multiple statements

Có thể là một lựa chọn hardening theo driver/stack, nhưng một câu `SELECT` bị thay đổi logic vẫn có thể làm lộ dữ liệu. Không dùng cấu hình này như bằng chứng duy nhất cho yêu cầu chống SQL injection.

## 12. Quyền database và giới hạn tác động

Ngăn injection tại sink là mục tiêu chính. Đồng thời, quyền database cần giới hạn tác động nếu một đường đi bị bỏ sót.

Đối với nền tảng tài liệu minh họa:

- Service chỉ tìm tài liệu không cần quyền sửa schema.
- Role chạy migration được tách khỏi role runtime.
- Quyền đọc/ghi giới hạn ở object và thao tác ứng dụng thực sự cần.
- Chức năng báo cáo không tự dùng tài khoản quản trị.
- Khả năng truy cập filesystem, extension, tác vụ hệ điều hành hoặc kết nối ra ngoài của database được kiểm soát theo nhu cầu triển khai.
- Secret kết nối được cấp và quản lý cho đúng workload.

Quyền chỉ đọc vẫn có thể cho phép rò dữ liệu rộng nếu đọc mọi tenant. Vì vậy “read-only” không tương đương với “an toàn với injection”.

Tương tự, một flag read-only trong API kết nối không nên được coi là ranh giới cấp quyền duy nhất. Cần xác minh quyền thực tế được database thực thi.

### Multi-tenancy

Có thể dùng tenant predicate trong ứng dụng, view, chính sách row-level hoặc cơ chế phù hợp khác. Với mỗi cách, cần biết:

- Tenant context đến từ đâu?
- Ai có thể thay đổi context đó?
- Quyền nào có thể bỏ qua chính sách?
- Connection pool có làm context của request trước còn lại không?
- Các tác vụ nền và báo cáo có đi qua cùng cơ chế không?

Không nên tuyên bố có row-level security là không cần parameterization. Nó là một cơ chế giới hạn truy cập cần được cấu hình và nghiệm thu độc lập.

### Giới hạn tài nguyên

Timeout truy vấn, page size tối đa và giới hạn số phần tử filter có thể giảm nguy cơ tiêu tốn tài nguyên. Chúng không thay thế việc giữ cấu trúc câu lệnh.

Một truy vấn bind đúng vẫn có thể quá đắt, còn một truy vấn injection không cần chạy lâu để làm lộ dữ liệu. Hai loại yêu cầu phải được theo dõi riêng.

## 13. Error handling và quan sát

Khi truy vấn thất bại, response cho client không nên chứa raw SQL, tên bảng/cột nội bộ, stack trace, URL kết nối hoặc credential.

Một response minh họa:

~~~json
{
  "code": "DATA_ACCESS_FAILURE",
  "message": "Không thể xử lý yêu cầu.",
  "requestId": "req-7c81"
}
~~~

Lỗi validation có thể dùng mã và thông báo phù hợp riêng. Không nên biến mọi lỗi thành response thành công hoặc trả “không có dữ liệu” để che lỗi vận hành.

Nội bộ có thể ghi nhận:

- Request/trace ID.
- Tên thao tác hoặc query template ID.
- Service và thành phần thực thi.
- Phân loại lỗi đủ phục vụ điều tra.
- Thời gian xử lý và trạng thái thất bại.
- Tenant/principal ID theo quyền truy cập log và chính sách dữ liệu.

Không mặc định ghi mọi parameter hoặc SQL đã nội suy đầy đủ. Tiêu đề, địa chỉ, thông tin nhận dạng và secret có thể nằm trong tham số. Công cụ APM/driver logging cũng cần được cấu hình phù hợp, không chỉ logger của ứng dụng.

Dữ liệu ghi log phải được xử lý theo định dạng log để input chứa newline hay ký tự điều khiển không tạo bản ghi giả.

Cảnh báo số lỗi cú pháp tăng có thể hữu ích, nhưng “không thấy lỗi SQL” không chứng minh không có injection. Một truy vấn bị thay đổi logic có thể hoàn toàn hợp lệ và trả kết quả bình thường.

## 14. Viết yêu cầu có thể nghiệm thu

Câu “hệ thống chống SQL injection” chưa đủ để giao cho đội triển khai. Cần nêu phạm vi và bằng chứng.

| ID | Yêu cầu mẫu | Bằng chứng dự kiến |
|---|---|---|
| SQLI-01 | Mọi giá trị không đáng tin đi vào SQL/JPQL/HQL được bind bằng API được hỗ trợ | Rà soát source–sink và mẫu truy vấn ở từng đường truy cập dữ liệu |
| SQLI-02 | Không có raw input được ghép vào template trước khi prepare | Kiểm tra nơi tạo template, không chỉ nơi gọi execute |
| SQLI-03 | Identifier, sort direction và operator động lấy từ mapping cố định | Đối chiếu mapping và các lựa chọn bị từ chối |
| SQLI-04 | Mỗi truy vấn tài liệu áp dụng tenant/resource scope đã được xác thực | Ca cùng input ở hai tenant và ca ID ngoài quyền |
| SQLI-05 | Native query, stored procedure và tác vụ nền chịu cùng tiêu chuẩn binding | Danh mục sink bao gồm cả đường ít được gọi |
| SQLI-06 | Giá trị đã lưu không được đưa lại vào SQL như cú pháp | Ca lưu rồi sử dụng ở báo cáo/export |
| SQLI-07 | Runtime role không có quyền quản trị hoặc quyền ngoài nhu cầu đã phê duyệt | Kiểm tra grants và các thao tác bị database từ chối |
| SQLI-08 | Response không lộ raw SQL, stack trace hoặc credential | Ca lỗi database trong môi trường kiểm chứng |
| SQLI-09 | Logging/tracing tuân theo chính sách che dữ liệu tham số | Kiểm tra log ở ứng dụng, driver và APM |
| SQLI-10 | Mỗi đường query mới hoặc thay đổi có bằng chứng giữ ranh giới code–data | Review và ca regression gắn với query path |
| SQLI-11 | Danh sách ID/filter có giới hạn kiểu, kích thước và hành vi khi rỗng | Các ca rỗng, vượt giới hạn, sai kiểu và nhiều phần tử |
| SQLI-12 | Test không chỉ kiểm tra status code mà kiểm tra dữ liệu và hiệu ứng | So sánh tập row, tenant, quyền và thay đổi dữ liệu |

Một yêu cầu có thể được viết đầy đủ hơn như sau:

> Với chức năng tìm tài liệu và export tương ứng, title và các giá trị filter phải được truyền bằng binding. Sort key được ánh xạ từ tập lựa chọn đã công bố sang fragment cố định. Kết quả chỉ gồm tài liệu trong tenant và phạm vi quyền của chủ thể đã xác thực, kể cả khi đầu vào chứa ký tự có ý nghĩa SQL hoặc đã được lưu trước đó.

Các bằng chứng trong bảng là kế hoạch nghiệm thu cho thiết kế. Chúng chưa phải kết luận rằng một hệ thống cụ thể hoặc nội dung bài đã trải qua QA.

## 15. Thiết kế ca kiểm chứng an toàn và có ý nghĩa

Không cần dùng dữ liệu production để kiểm chứng một repository. Có thể tạo fixture tổng hợp:

~~~text
Tenant A:
  document 11: "O'Reilly guide"
  document 12: "Quarterly report"

Tenant B:
  document 91: "Internal plan"
~~~

Tất cả nội dung là dữ liệu giả. Dùng môi trường được phép kiểm thử, giới hạn phạm vi và bảo đảm có cách quan sát dữ liệu trước/sau.

### 15.1. Dữ liệu hợp lệ có dấu nháy

**Given:** tenant A có tài liệu tên `O'Reilly guide`.

**When:** người được phép trong tenant A tìm đúng tiêu đề.

**Then:** hệ thống tìm đúng tài liệu, không lỗi cú pháp và không cần client tự escape dấu nháy.

Ca này giúp phát hiện biện pháp “cấm dấu nháy” làm mất chức năng hợp lệ.

### 15.2. Chuỗi trông như biểu thức SQL

**Given:** fixture không có tài liệu mang tên `x' OR '1'='1`.

**When:** client dùng chính chuỗi đó làm giá trị tìm kiếm.

**Then:** nó được xử lý như title literal theo contract; không biến thành điều kiện luôn đúng, không trả dữ liệu tenant B.

Không chỉ kiểm tra HTTP 200. Một implementation có lỗ hổng cũng có thể trả 200 với quá nhiều dữ liệu.

### 15.3. Cấu trúc sort ngoài mapping

**Given:** API chỉ cho `id_asc` và `created_desc`.

**When:** client gửi một giá trị sort khác.

**Then:** API từ chối theo contract trước khi giá trị đó được ghép vào SQL. Không có nhánh fallback sử dụng raw string để “hỗ trợ linh hoạt”.

### 15.4. Đường đi second-order

**Given:** một giá trị chứa dấu nháy và đoạn văn bản giống SQL được lưu hợp lệ như dữ liệu.

**When:** job export đọc lại giá trị đó và thực hiện truy vấn.

**Then:** giá trị vẫn được bind; không thay đổi query structure, không mở rộng phạm vi dữ liệu và không làm biến đổi bản ghi ngoài dự kiến.

### 15.5. Binding nhưng sai phân quyền

**Given:** truy vấn resource ID đã bind đúng.

**When:** người dùng tenant A yêu cầu ID 91 thuộc tenant B.

**Then:** không trả tài liệu tenant B. Ca này xác nhận rằng parameterization và authorization được thực hiện đồng thời.

### 15.6. Stored procedure hoặc native query

**Given:** API gọi một procedure/native query có tham số.

**When:** input đi qua cả outer call và SQL bên trong.

**Then:** kiểm chứng mọi sink giữ được binding; không coi outer call an toàn là đủ bằng chứng cho phần nội bộ.

### 15.7. Quyền database

**Given:** role runtime của chức năng tìm kiếm.

**When:** kiểm tra quyền theo danh mục thao tác được phép và không được phép.

**Then:** quyền vượt nhu cầu bị database từ chối. Việc kiểm tra nên dùng thao tác kiểm chứng không phá hủy trong môi trường đã chuẩn bị, thay vì thử xóa dữ liệu thật.

### 15.8. Danh sách, pattern và điều kiện OR

Cần ca riêng cho:

- `IN` với danh sách rỗng và vượt số phần tử.
- `LIKE` với ký tự wildcard khi contract yêu cầu literal.
- Filter `OR` không thoát khỏi tenant predicate.
- Hai trạng thái hoặc nhiều nhánh filter được kết hợp đúng ngoặc.
- Pagination không làm mất các điều kiện quyền trong một nhánh query khác.

Kết quả mong đợi phải bao gồm tập dữ liệu và hiệu ứng nghiệp vụ, không chỉ việc câu lệnh “chạy được”.

## 16. Đánh giá bằng chứng từ nhiều lớp

Không có một công cụ duy nhất chứng minh mọi đường đi đều an toàn.

| Loại bằng chứng | Giúp xác nhận | Giới hạn |
|---|---|---|
| Rà soát source–sink | Value đi vào đâu, template có bị nối input không | Có thể bỏ sót code sinh động hoặc procedure |
| Unit/regression cho builder | Mapping và grouping logic đúng | Không thay thế kiểm chứng driver/database thật |
| Integration test | Binding và quyền trên stack triển khai hoạt động đúng | Chỉ bao phủ fixture và path đã kiểm tra |
| SAST | Phát hiện một số luồng nối chuỗi hoặc API nguy hiểm | Có false positive/negative |
| Dynamic testing | Phát hiện hành vi bất thường từ API | Khó thấy toàn bộ tác vụ nền và second-order |
| Kiểm tra grants | Giới hạn tác động của database role | Không chứng minh query construction an toàn |
| Quan sát log/trace | Hỗ trợ điều tra và phát hiện sự cố | Không có cảnh báo không đồng nghĩa không có lỗi |

Một kết luận có sức thuyết phục thường nối ba thứ: danh mục đường query, bằng chứng giữ ranh giới code–data và kết quả kiểm tra phạm vi truy cập.

Không nên yêu cầu “không có dấu nháy trong SQL log” để nghiệm thu. Dữ liệu hợp lệ có dấu nháy vẫn có thể xuất hiện trong log đã được render bởi công cụ quan sát; điều cần biết là nó được bind như value hay được ghép thành cú pháp.

## 17. Khi phát hiện một đường truy vấn không an toàn

Một kế hoạch khắc phục có thể gồm:

1. Xác định các source và mọi sink liên quan, bao gồm đường export, batch và dữ liệu đã lưu.
2. Chuyển value sang binding; thay phần cấu trúc bằng mapping hoặc query model có kiểu.
3. Kiểm tra tenant/resource scope và grouping logic trong query mới.
4. Xác minh runtime role và loại bỏ quyền ngoài nhu cầu theo quy trình quản lý quyền.
5. Bổ sung ca regression cho nguyên nhân cụ thể và dữ liệu hợp lệ dễ bị chặn nhầm.
6. Kiểm tra response và logging không làm lộ thêm dữ liệu.
7. Đánh giá phạm vi dữ liệu có thể đã bị truy cập hoặc thay đổi theo bằng chứng vận hành.

Nếu dùng WAF hoặc tạm tắt một chức năng để giảm phơi lộ trong lúc xử lý, cần owner và điều kiện gỡ biện pháp tạm. Không coi một pattern filter vừa thêm là bằng chứng hoàn tất sửa lỗi tại sink.

Thay đổi query cũng cần giữ nguyên hành vi hợp lệ: Unicode, dấu nháy, trường null và filter được hỗ trợ. Một bản vá làm mọi truy vấn lỗi không phải là kết quả an toàn có thể đưa vào vận hành.

## 18. Những nhận định cần tránh

| Nhận định | Vấn đề |
|---|---|
| “Có PreparedStatement nên an toàn” | Template có thể đã nối input trước khi prepare |
| “Chỉ người quản trị nhập nên đáng tin” | Quyền quản trị không biến dữ liệu thành cú pháp được phép |
| “Dữ liệu từ database là dữ liệu sạch” | Có thể gây second-order injection |
| “Dùng ORM là không có SQL injection” | JPQL/HQL/native query vẫn có điểm nối chuỗi |
| “Stored procedure luôn an toàn” | Nội bộ có thể xây dynamic SQL không bind |
| “Cấm dấu nháy là đủ” | Sai ngữ cảnh, dễ bỏ sót và chặn dữ liệu hợp lệ |
| “Tắt nhiều statement là đủ” | Một statement có thể bị đổi logic |
| “Identifier đúng regex thì được dùng” | Đúng cú pháp không đồng nghĩa có quyền chọn object đó |
| “Role read-only không có rủi ro” | Vẫn có thể đọc dữ liệu vượt phạm vi |
| “Không có lỗi SQL nên không bị injection” | Câu lệnh bị thay đổi có thể hợp lệ hoàn toàn |
| “Bind tenant ID thì đã có phân quyền” | Tenant do client tự chọn vẫn có thể không được phép |
| “Chỉ cần test API đồng bộ” | Batch, report, import và retry có thể có sink khác |

## 19. Bài tập áp dụng

Thiết kế chức năng tìm tài liệu có các input:

~~~json
{
  "title": "O'Reilly guide",
  "status": ["DRAFT", "PUBLISHED"],
  "sort": "created_desc",
  "documentIds": [11, 12]
}
~~~

Hãy tạo một đặc tả đáp ứng các câu hỏi:

1. Tenant và principal lấy từ đâu, ai được chọn phạm vi tìm kiếm?
2. Giá trị nào được bind và cấu trúc nào chỉ được lấy từ mapping?
3. `IN` rỗng, nhiều phần tử và filter `OR` được xử lý thế nào?
4. Dấu nháy và Unicode hợp lệ trong title có hoạt động không?
5. Job export dùng lại input đã lưu có giữ cùng ranh giới không?
6. Runtime role cần những quyền database nào?
7. Bằng chứng nào xác nhận không trả dữ liệu tenant khác và không đổi query logic?

Đặc tả tốt cho SQL injection giúp người triển khai xác định được nguồn dữ liệu, điểm thực thi, cấu trúc truy vấn được phép và cách kiểm chứng. Khi dữ liệu luôn ở vị trí dữ liệu, cấu trúc do ứng dụng kiểm soát và quyền truy cập được thực thi độc lập, yêu cầu chống SQL injection mới có thể được triển khai và nghiệm thu rõ ràng.
