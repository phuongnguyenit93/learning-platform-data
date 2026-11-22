# An toàn truy vấn và vai trò của lớp truy cập dữ liệu

Trong ứng dụng MVC, Controller tiếp nhận request, dịch vụ ứng dụng điều phối use case, Model bảo vệ quy tắc nghiệp vụ và lớp truy cập dữ liệu làm việc với cơ sở dữ liệu. Khi request chứa từ khóa tìm kiếm, bộ lọc, mã định danh hoặc trường sắp xếp, dữ liệu đó có thể ảnh hưởng trực tiếp đến câu truy vấn được thực thi. Nếu ghép dữ liệu người dùng vào chuỗi SQL hoặc JPQL, ứng dụng có nguy cơ bị SQL injection, truy cập sai phạm vi dữ liệu hoặc làm lộ thông tin.

Truy vấn an toàn cần nhiều lớp bảo vệ: **tham số hóa giá trị**, kiểm soát những phần cấu trúc truy vấn có thể thay đổi, giới hạn quyền của tài khoản database, ràng buộc dữ liệu theo người dùng hoặc tenant và chỉ trả về những trường cần thiết. Lớp truy cập dữ liệu (Data Access Layer, DAL) là nơi tập trung cách đọc/ghi dữ liệu và che giấu chi tiết persistence; nó hỗ trợ bảo mật nhưng không thay thế việc xác thực, phân quyền và kiểm tra quy tắc nghiệp vụ ở các tầng ứng dụng.

Trong MVC, Controller không nên tự nối chuỗi SQL từ request. Controller chuyển yêu cầu thành tham số hoặc query object có kiểu; application service xác định phạm vi và chính sách; repository/DAO thực thi truy vấn bằng cơ chế binding an toàn. Cách tổ chức này giúp truy vấn dễ kiểm thử, dễ thay đổi và giảm nguy cơ dữ liệu đầu vào biến thành câu lệnh.

## 1. Luồng dữ liệu từ request đến database

Một chức năng tìm kiếm công việc có thể nhận từ trình duyệt các tham số như từ khóa, trạng thái, trang hiện tại và trường sắp xếp. Các giá trị đó đi qua nhiều tầng:

~~~mermaid
flowchart TD
    A["View: form tìm kiếm"] --> B["HTTP request"]
    B --> C["Controller: binding và kiểm tra đầu vào"]
    C --> D["Query DTO / Application Service"]
    D --> E["Repository / Data Access Layer"]
    E --> F["Parameterized query"]
    F --> G["Database"]
    G --> H["Kết quả có giới hạn"]
    H --> I["DTO / ViewModel"]
    I --> J["View hoặc API response"]
~~~

Mỗi tầng có trách nhiệm riêng:

- **View** thu nhận dữ liệu tìm kiếm và hiển thị kết quả. Giá trị ở trình duyệt luôn có thể bị sửa.
- **Controller** binding query parameter, kiểm tra định dạng và chuyển chúng thành kiểu dữ liệu phù hợp.
- **Application service** áp dụng ngữ cảnh đã xác thực, chính sách truy cập và quy tắc của use case.
- **Repository/DAO** tạo truy vấn, bind giá trị, giới hạn dữ liệu và chuyển kết quả persistence thành dạng mà tầng ứng dụng sử dụng.
- **Database** thực thi truy vấn theo quyền của tài khoản kết nối và các ràng buộc đã cấu hình.

Không nên truyền một đoạn SQL thô do client gửi lên qua Controller rồi giao cho repository thực thi. Hợp đồng đầu vào nên mô tả ý định ở mức nghiệp vụ, ví dụ trạng thái cần lọc hoặc thứ tự sắp xếp được hỗ trợ.

## 2. SQL injection xảy ra như thế nào?

SQL injection xảy ra khi dữ liệu không đáng tin cậy bị ghép vào cấu trúc câu lệnh SQL, khiến database diễn giải một phần dữ liệu đó như cú pháp truy vấn.

Ví dụ tìm công việc theo tên:

~~~java
String sql =
    "SELECT id, title FROM task WHERE title = '" +
    request.title() + "'";
Statement statement = connection.createStatement();
ResultSet result = statement.executeQuery(sql);
~~~

Nếu người dùng nhập một chuỗi chứa dấu nháy và biểu thức SQL, chuỗi được nối có thể làm thay đổi ý nghĩa câu lệnh. Một payload thường được dùng để minh họa là:

~~~text
' OR '1'='1
~~~

Khi ghép trực tiếp, phần nhập có thể làm điều kiện WHERE luôn đúng hoặc thay đổi cấu trúc truy vấn. Trong tình huống nghiêm trọng, kẻ tấn công có thể đọc dữ liệu ngoài phạm vi, sửa hoặc xóa dữ liệu nếu tài khoản database có quyền tương ứng và câu truy vấn cho phép.

SQL injection không chỉ xuất hiện trong câu lệnh SELECT. Nó có thể ảnh hưởng đến UPDATE, DELETE, INSERT, truy vấn báo cáo, bộ lọc quản trị hoặc câu truy vấn native trong ORM.

### 2.1. Vì sao kiểm tra chuỗi đầu vào chưa đủ?

Các cách như loại bỏ dấu nháy, thay thế một vài ký tự hoặc kiểm tra từ khóa SQL thường không đáng tin cậy:

- SQL có nhiều cú pháp, cách escape và biểu diễn khác nhau theo hệ quản trị.
- Encoding hoặc cách chuẩn hóa dữ liệu có thể làm bộ lọc hiểu khác database.
- Một giá trị hợp lệ có thể chứa dấu nháy, dấu gạch hoặc ký tự đặc biệt.
- Kẻ tấn công có thể dùng cú pháp chưa được bộ lọc dự kiến.
- Quy tắc lọc tự viết thường bỏ sót một đường truy vấn khác.

Hãy dùng parameterized query hoặc prepared statement để tách dữ liệu khỏi cú pháp SQL. Validation vẫn cần thiết cho quy tắc đầu vào, nhưng không thay thế parameter binding.

## 3. Parameterized query và prepared statement

Prepared statement cho phép định nghĩa cấu trúc SQL với placeholder, sau đó truyền giá trị riêng qua API binding. Database hoặc driver xử lý giá trị như dữ liệu, không coi nó là một phần cú pháp truy vấn.

~~~java
String sql = "SELECT id, title FROM task WHERE title = ?";
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, request.title());

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            // Đọc kết quả
        }
    }
}
~~~

Dù người dùng nhập chuỗi có ký tự giống cú pháp SQL, nó vẫn được bind như một giá trị của điều kiện title. Câu truy vấn giữ nguyên cấu trúc.

Parameterized query giúp ngăn SQL injection qua **giá trị dữ liệu**. Nó không tự giải quyết mọi vấn đề truy cập dữ liệu: vẫn cần kiểm soát quyền, tenant, giới hạn kết quả, truy vấn động và các thao tác không được phép.

### 3.1. Named parameter giúp truy vấn dễ đọc

Thay vì dùng vị trí ? theo thứ tự, có thể dùng named parameter:

~~~java
String sql = """
    SELECT id, title, status
    FROM task
    WHERE tenant_id = :tenantId
      AND status = :status
      AND title LIKE :pattern
    ORDER BY created_at DESC
    """;

MapSqlParameterSource parameters = new MapSqlParameterSource()
    .addValue("tenantId", tenantId)
    .addValue("status", status.name())
    .addValue("pattern", pattern);

List<TaskRow> rows = namedParameterJdbcTemplate.query(
    sql,
    parameters,
    (result, rowNumber) -> new TaskRow(
        result.getObject("id", UUID.class),
        result.getString("title"),
        result.getString("status")
    )
);
~~~

NamedParameterJdbcTemplate của Spring JDBC chuyển named parameter thành placeholder mà JDBC driver hỗ trợ và bind giá trị tương ứng. Tên tham số làm câu truy vấn dễ đọc hơn, đặc biệt khi có nhiều điều kiện.

Các biến tenantId, status và pattern trong ví dụ phải được tạo từ dữ liệu đã binding và ngữ cảnh tin cậy. tenantId nên lấy từ principal hoặc ngữ cảnh tenant đã xác thực, không nhận nguyên giá trị do client tự khai báo rồi coi đó là quyền truy cập.

### 3.2. Giá trị được bind, cấu trúc SQL thì không

Placeholder đại diện cho một giá trị, chẳng hạn chuỗi, số, ngày hoặc UUID. Nó không thể đại diện cho tên bảng, tên cột, từ khóa ASC/DESC hay một đoạn điều kiện SQL.

Ví dụ sau không hoạt động như mong muốn:

~~~java
String sql = "SELECT * FROM task ORDER BY ?";
~~~

Tham số ? được hiểu là một giá trị, không phải tên cột. Database có thể sắp xếp theo một hằng số giống nhau cho mọi hàng, hoặc từ chối tùy driver và dialect. Không được nghĩ rằng bind tên cột sẽ biến nó thành cú pháp identifier.

Với cấu trúc truy vấn thay đổi, hãy dùng danh sách cho phép (allowlist) hoặc API query builder an toàn. Không nối trực tiếp chuỗi do client cung cấp vào SQL.

## 4. Kiểm soát sắp xếp và lọc động

Chức năng danh sách thường cho phép chọn cột sắp xếp và chiều tăng/giảm. Vì identifier không thể bind như giá trị, cần ánh xạ lựa chọn của người dùng sang một tập cột đã được định nghĩa.

~~~java
private static final Map<String, String> SORT_COLUMNS = Map.of(
    "created", "created_at",
    "title", "title",
    "status", "status"
);

String requestedSort = request.sort();
String column = SORT_COLUMNS.get(requestedSort);

if (column == null) {
    throw new InvalidQueryParameterException("Trường sắp xếp không hợp lệ");
}

String direction = request.descending() ? "DESC" : "ASC";

String sql = """
    SELECT id, title, status
    FROM task
    WHERE tenant_id = ?
    ORDER BY %s %s
    LIMIT ? OFFSET ?
    """.formatted(column, direction);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, tenantId);
    statement.setInt(2, limit);
    statement.setLong(3, offset);

    try (ResultSet result = statement.executeQuery()) {
        // Ánh xạ các hàng kết quả
    }
}
~~~

Trong ví dụ, column chỉ có thể nhận giá trị từ map hằng do ứng dụng kiểm soát; direction chỉ nhận hai hằng ASC hoặc DESC do boolean quyết định. Các giá trị tenant, limit và offset được bind bằng PreparedStatement. Không đưa request.sort() hoặc một chuỗi direction tùy ý vào formatted().

Một lựa chọn khác là dùng enum:

~~~java
enum TaskSort {
    CREATED,
    TITLE,
    STATUS
}
~~~

Controller chuyển query parameter thành enum đã được kiểm tra. Repository ánh xạ từng enum sang identifier cố định. Cách này giúp hợp đồng API rõ và giảm việc xử lý chuỗi tự do.

### 4.1. Giới hạn phân trang

Page number và page size cũng là dữ liệu không đáng tin cậy. Cần kiểm tra:
- page không âm.
- size lớn hơn 0.
- size không vượt giới hạn hợp lý.
- phép tính offset không bị tràn số.
- truy vấn có thứ tự ổn định khi phân trang, thường cần thêm khóa phụ duy nhất.

Giới hạn phân trang giúp giảm tải và tránh client yêu cầu một lượng dữ liệu quá lớn. Nó không thay thế quyền truy cập; một truy vấn phân trang vẫn phải giới hạn theo người dùng hoặc tenant.

## 5. Tìm kiếm LIKE và ký tự đại diện

Dùng parameter binding cho LIKE ngăn chuỗi tìm kiếm thoát ra khỏi giá trị tham số. Tuy nhiên, ký tự % và _ vẫn có ý nghĩa wildcard của LIKE. Đây không phải SQL injection, nhưng có thể khiến tìm kiếm rộng hơn ý định của người dùng.

Ví dụ:

~~~sql
WHERE title LIKE :pattern
~~~

Nếu pattern là %report%, database tìm các tiêu đề chứa report. Nếu người dùng nhập % đơn lẻ, nó có thể khớp rất nhiều bản ghi.

Nếu yêu cầu là tìm chuỗi literal, hãy escape ký tự wildcard theo quy tắc của database và chỉ định ký tự escape. Ví dụ dùng dấu ! làm ký tự escape:

~~~java
String escaped = input
    .replace("!", "!!")
    .replace("%", "!%")
    .replace("_", "!_");

String pattern = "%" + escaped + "%";
~~~

~~~sql
WHERE title LIKE :pattern ESCAPE '!'
~~~

Thứ tự thay thế quan trọng: escape ký tự escape trước, sau đó mới escape % và _. Hành vi collation, phân biệt hoa thường và Unicode còn phụ thuộc database. Nếu ứng dụng muốn wildcard do người dùng chủ động sử dụng, hãy mô tả rõ cú pháp tìm kiếm thay vì vô tình cho phép mọi ký tự điều khiển.

## 6. An toàn truy vấn với JPA và Hibernate

ORM giúp làm việc với entity và query object, nhưng không có nghĩa mọi cách viết truy vấn đều tự động an toàn. JPQL, Criteria API và Spring Data repository hỗ trợ binding tham số; native query hoặc đoạn truy vấn được ghép chuỗi vẫn có thể mắc SQL injection.

### 6.1. Derived query của Spring Data

Spring Data JPA có thể tạo truy vấn từ tên phương thức:

~~~java
public interface TaskRepository extends JpaRepository<Task, UUID> {
    List<Task> findByTenantIdAndStatus(
        UUID tenantId,
        TaskStatus status
    );
}
~~~

Spring Data tạo truy vấn dựa trên thuộc tính entity và bind tham số. Cách này phù hợp với truy vấn đơn giản, dễ đọc và có hợp đồng rõ.

### 6.2. JPQL với named parameter

Với truy vấn phức tạp hơn, có thể khai báo JPQL:

~~~java
@Query("""
    select t
    from Task t
    where t.tenantId = :tenantId
      and t.status = :status
      and lower(t.title) like lower(:pattern)
    """)
List<Task> search(
    @Param("tenantId") UUID tenantId,
    @Param("status") TaskStatus status,
    @Param("pattern") String pattern
);
~~~

JPQL tham chiếu entity và thuộc tính Java thay vì tên bảng/cột vật lý. Named parameter giúp bind giá trị an toàn. Dữ liệu tenantId vẫn phải lấy từ ngữ cảnh được xác thực; parameter binding chỉ bảo vệ cú pháp, không tự quyết định người dùng được xem tenant nào.

### 6.3. Native query cần được kiểm tra kỹ

Native query hữu ích khi cần tính năng đặc thù của database hoặc tối ưu truy vấn. Hãy dùng placeholder và bind tham số như khi viết JDBC. Tránh tạo query bằng cách nối chuỗi từ request.

~~~java
@Query(
    value = """
        SELECT *
        FROM task
        WHERE tenant_id = :tenantId
          AND status = :status
        """,
    nativeQuery = true
)
List<Task> findForTenant(
    @Param("tenantId") UUID tenantId,
    @Param("status") String status
);
~~~

Tên bảng, cột và đoạn SQL trong annotation là mã nguồn do ứng dụng kiểm soát. Giá trị tenantId và status được bind. Nếu native query có phần động, phần đó phải đến từ allowlist hoặc query builder an toàn.

### 6.4. EntityManager và setParameter

Nếu dùng EntityManager:

~~~java
TypedQuery<Task> query = entityManager.createQuery(
    "select t from Task t where t.tenantId = :tenantId and t.status = :status",
    Task.class
);

query.setParameter("tenantId", tenantId);
query.setParameter("status", status);

List<Task> tasks = query.getResultList();
~~~

Dùng setParameter cho giá trị thay vì nối chuỗi. Với truy vấn động, có thể dùng Criteria API để xây predicate có kiểu và ghép điều kiện theo cấu trúc. Criteria API giảm nguy cơ nối chuỗi nhưng không tự áp dụng phân quyền hay tenant scope nếu người viết quên thêm điều kiện.

### 6.5. Không ghép JPQL/SQL từ đầu vào

Ví dụ không an toàn:

~~~java
String jpql =
    "select t from Task t where t.title like '%" +
    request.keyword() + "%'";

entityManager.createQuery(jpql, Task.class).getResultList();
~~~

Việc sử dụng ORM không làm cách ghép chuỗi này an toàn. Hãy thay bằng named parameter và giá trị pattern đã được chuẩn hóa theo ngữ nghĩa tìm kiếm.

## 7. Vai trò của lớp truy cập dữ liệu

Data Access Layer là ranh giới giữa phần ứng dụng với cơ chế lưu trữ. Nó thường được tổ chức qua repository, DAO hoặc adapter persistence.

Một DAL được thiết kế tốt có thể đảm nhận:

- Đóng gói SQL, JPQL, Criteria hoặc chi tiết truy vấn.
- Bind giá trị theo cơ chế an toàn.
- Giới hạn kết quả, sắp xếp và phân trang theo hợp đồng.
- Ánh xạ hàng dữ liệu hoặc entity thành đối tượng mà ứng dụng cần.
- Che giấu chi tiết database và giúp thay đổi persistence ít ảnh hưởng tầng trên.
- Chuyển lỗi persistence thành lỗi có ý nghĩa với ứng dụng.
- Thực thi điều kiện tenant hoặc quyền sở hữu ở truy vấn khi phù hợp.
- Tạo điểm kiểm thử truy vấn và hiệu năng.

DAL không nên trở thành nơi chứa toàn bộ quy tắc nghiệp vụ. Ví dụ, quyết định một công việc có thể chuyển từ OPEN sang DONE thuộc Model hoặc use case; repository chỉ lưu trạng thái sau khi quy tắc được kiểm tra.

Cũng không nên coi repository là lớp duy nhất chịu trách nhiệm phân quyền. Một truy vấn an toàn về cú pháp vẫn có thể trả dữ liệu mà người dùng không được xem nếu thiếu điều kiện tenant hoặc quyền truy cập.

### 7.1. Repository diễn đạt ý định, không nhận SQL tùy ý

Một interface rõ:

~~~java
public interface TaskRepository {
    Optional<Task> findVisibleTask(
        UUID taskId,
        UUID tenantId
    );

    Page<TaskSummary> search(
        UUID tenantId,
        TaskSearchCriteria criteria,
        Pageable pageable
    );
}
~~~

Interface cho biết truy vấn có phạm vi tenant và trả về summary cần thiết. Application service có thể gọi phương thức có ý nghĩa thay vì truyền một chuỗi SQL tùy ý.

Không nên thiết kế API kiểu:

~~~java
List<Map<String, Object>> execute(String sql);
~~~

rồi cho phép Controller truyền trực tiếp query string. Cách đó phá vỡ ranh giới, làm khó kiểm soát tham số, quyền truy cập và hợp đồng dữ liệu.

### 7.2. Trả đúng lượng dữ liệu cần thiết

Không phải lúc nào repository cũng nên trả toàn bộ entity. Với màn hình danh sách, có thể dùng projection hoặc DTO chỉ chứa ID, tiêu đề, trạng thái và thời điểm cần hiển thị. Điều này giảm dữ liệu truyền qua tầng, hạn chế truy cập quan hệ ngoài ý muốn và giảm nguy cơ lộ trường nhạy cảm.

Ví dụ projection:

~~~java
public record TaskSummary(
    UUID id,
    String title,
    TaskStatus status
) {}
~~~

Truy vấn chỉ chọn các cột cần thiết. Response DTO sau đó có thể ánh xạ từ TaskSummary mà không làm lộ các trường nội bộ của entity.

## 8. Parameter binding không thay thế phân quyền

Một truy vấn có thể hoàn toàn không có SQL injection nhưng vẫn vi phạm quyền truy cập.

Ví dụ:

~~~sql
SELECT id, title
FROM task
WHERE id = ?
~~~

Truy vấn này bind ID an toàn, nhưng nếu người dùng thay ID trong request sang công việc của người khác và server không kiểm tra quyền, ứng dụng vẫn mắc lỗi truy cập đối tượng trực tiếp (IDOR/BOLA).

Cần phân biệt:

- **Authentication:** request thuộc về ai?
- **Authorization:** người đó được phép thực hiện hành động nào trên tài nguyên nào?
- **Parameter binding:** dữ liệu request có bị diễn giải thành cú pháp truy vấn hay không?
- **Data scoping:** tập dữ liệu truy vấn có bị giới hạn đúng người dùng, tổ chức hoặc tenant không?

Đây là các kiểm soát khác nhau. Một ứng dụng cần tất cả những lớp phù hợp với mô hình dữ liệu.

### 8.1. Kiểm tra quyền trên tài nguyên

Một cách là tải tài nguyên rồi gọi authorization policy:

~~~java
public TaskDetails getTask(UUID taskId, AppPrincipal principal) {
    Task task = taskRepository.findById(taskId)
        .orElseThrow(TaskNotFoundException::new);

    taskAuthorization.requireCanView(principal, task);

    return taskMapper.toDetails(task);
}
~~~

Cách này rõ ràng khi chính sách quyền phức tạp và cần đối tượng nghiệp vụ. Tuy nhiên, nếu truy vấn theo ID toàn cục trước khi kiểm tra, cần bảo đảm response không làm lộ sự tồn tại của tài nguyên ngoài phạm vi theo chính sách bảo mật.

### 8.2. Giới hạn truy vấn theo tenant hoặc người dùng

Một cách khác là đưa tenant hoặc owner vào điều kiện truy vấn:

~~~java
Optional<Task> findByIdAndTenantId(
    UUID taskId,
    UUID tenantId
);
~~~

Application service lấy tenantId từ principal hoặc context đã được xác thực, sau đó truyền vào repository. Không lấy tenantId từ query parameter rồi tin đó là phạm vi được phép.

Điều kiện tenant trong truy vấn giúp giảm nguy cơ quên lọc ở một endpoint. Tuy vậy, quyền truy cập có thể phức tạp hơn tenant membership, ví dụ chia sẻ tài nguyên hoặc vai trò theo dự án. Khi đó cần authorization policy phù hợp, và truy vấn phải phản ánh chính sách đó một cách nhất quán.

### 8.3. Defense in depth

Có thể kết hợp:
- Method security hoặc kiểm tra quyền ở application service.
- Truy vấn có tenant/owner scope.
- Database constraint hoặc row-level security khi phù hợp.
- Tài khoản database có quyền tối thiểu.
- Kiểm thử truy cập chéo tenant và truy cập theo vai trò.

Row-level security của database có thể là lớp bảo vệ bổ sung, nhưng cần quản lý session variable/tenant context và connection pool cẩn thận. Nếu connection được tái sử dụng mà tenant context không được đặt hoặc xóa đúng, nguy cơ rò rỉ dữ liệu giữa tenant vẫn tồn tại.

## 9. Quyền tối thiểu của tài khoản database

Ứng dụng nên kết nối database bằng tài khoản chỉ có quyền cần thiết. Ví dụ, một dịch vụ chỉ đọc báo cáo có thể dùng tài khoản chỉ SELECT trên các view hoặc bảng cần thiết. Tài khoản runtime thông thường không nên có quyền tạo user, thay đổi schema hoặc quản trị database nếu không cần.

Nguyên tắc least privilege giảm tác động nếu một truy vấn bị khai thác:
- Tách tài khoản runtime khỏi tài khoản migration/schema owner.
- Chỉ cấp SELECT/INSERT/UPDATE/DELETE trên bảng cần thiết.
- Hạn chế quyền truy cập schema và stored procedure.
- Không dùng tài khoản admin trong ứng dụng.
- Quản lý credential qua secret manager hoặc cơ chế cấu hình an toàn.
- Luân chuyển credential theo chính sách vận hành.

Parameter binding vẫn là biện pháp chính chống injection ở truy vấn; quyền tối thiểu giới hạn hậu quả nếu có lỗ hổng khác. Hai kiểm soát bổ sung cho nhau.

## 10. Stored procedure và query builder có an toàn tuyệt đối không?

Stored procedure không tự động ngăn SQL injection. Nếu bên trong procedure tạo dynamic SQL bằng cách nối chuỗi đầu vào, rủi ro vẫn tồn tại. Hãy dùng tham số procedure và cơ chế bind an toàn cho dynamic statement theo khả năng của hệ quản trị.

Query builder hoặc Criteria API cũng không tự bảo đảm mọi truy vấn an toàn. Nếu thư viện cho phép chèn raw SQL fragment, hoặc ứng dụng nối identifier tùy ý, vẫn có thể tạo truy vấn nguy hiểm.

Hãy đánh giá cách dữ liệu được đưa vào câu truy vấn cuối cùng, thay vì chỉ dựa vào tên công nghệ.

## 11. Các loại injection ngoài SQL

Nếu ứng dụng dùng NoSQL hoặc search engine, nguyên tắc vẫn tương tự: không để dữ liệu người dùng trở thành cấu trúc truy vấn ngoài ý muốn.

Ví dụ, với MongoDB, không nhận nguyên một object filter tùy ý từ client rồi truyền thẳng vào database. Một payload có thể đưa toán tử như $ne hoặc $where nếu API cho phép. Hãy binding các trường đầu vào đã định nghĩa vào query builder, kiểm tra kiểu dữ liệu và chỉ cho phép những toán tử ứng dụng hỗ trợ.

Với LDAP, shell hoặc search query language, cũng cần dùng API tham số hóa hoặc escape đúng theo ngữ cảnh. Mỗi ngôn ngữ truy vấn có quy tắc riêng; escape SQL không thể dùng thay cho escape LDAP hay shell.

## 12. Logging và thông báo lỗi của truy vấn

Khi truy vấn thất bại, không trả nguyên SQL, tên bảng, cấu trúc schema hoặc message database cho client. Thông tin đó có thể giúp người tấn công suy luận kiến trúc và tìm điểm yếu.

Log nội bộ nên:
- Có correlation ID để liên kết request và lỗi persistence.
- Ghi loại thao tác hoặc tên repository method, không nhất thiết ghi toàn bộ dữ liệu.
- Không log mật khẩu, token, session cookie hoặc dữ liệu cá nhân không cần thiết.
- Cẩn trọng với bind parameter có thể chứa thông tin nhạy cảm.
- Phân biệt lỗi constraint dự kiến với lỗi kết nối hoặc lỗi không dự kiến.
- Giới hạn quyền truy cập và thời gian lưu log.

Không nên hiển thị thông báo “SQL syntax error near...” trên trang. Người dùng chỉ cần biết thao tác chưa thực hiện được và cách tiếp tục nếu có thể. Đội vận hành cần chi tiết kỹ thuật trong log có kiểm soát.

## 13. Kiểm thử truy vấn an toàn

Unit test cho service có thể xác minh tenantId được lấy từ principal và truyền vào repository. Tuy nhiên, để xác minh truy vấn thật được bind đúng và hành vi phù hợp với dialect, cần integration test với database tương thích môi trường triển khai.

Các trường hợp nên kiểm thử:

- Chuỗi có dấu nháy, dấu gạch và payload giống SQL được xử lý như dữ liệu.
- Ký tự % và _ trong tìm kiếm được xử lý đúng ngữ nghĩa wildcard.
- sort field chỉ nhận các giá trị allowlist.
- sort direction chỉ là ASC hoặc DESC được ứng dụng định nghĩa.
- page và size bị giới hạn; không thể yêu cầu truy vấn không giới hạn.
- Request không có quyền không thể đọc tài nguyên bằng cách thay ID.
- Người dùng tenant A không nhận bản ghi của tenant B.
- Projection không trả password hash, token hoặc trường nội bộ.
- Lỗi constraint được chuyển thành phản hồi phù hợp mà không lộ SQL.
- Các truy vấn có chỉ mục và kế hoạch thực thi phù hợp với dữ liệu thực tế.

Ví dụ test tích hợp tìm kiếm:

~~~java
@Test
void searchTreatsSqlLikeInputAsData() {
    String input = "' OR '1'='1";
    String expectedTitle = "Task title: " + input;
    taskRepository.save(Task.create(expectedTitle, tenantAId));

    List<TaskRow> results = taskRepository.searchByTitle(
        tenantAId,
        input
    );

    assertThat(results)
        .extracting(TaskRow::title)
        .containsExactly(expectedTitle);
}
~~~

Test này giả định fixture của tenantAId được cô lập cho ca kiểm thử. Nó xác minh chuỗi giống payload được xem là giá trị tìm kiếm và chỉ hàng khớp literal được trả về, thay vì làm điều kiện WHERE rộng ra.

Kiểm thử tenant isolation:

~~~java
@Test
void repositoryDoesNotReturnAnotherTenantsTask() {
    Task task = taskRepository.save(
        Task.create("Nội bộ tenant B", tenantBId)
    );

    Optional<Task> result =
        taskRepository.findByIdAndTenantId(task.getId(), tenantAId);

    assertThat(result).isEmpty();
}
~~~

Kiểm thử này nên chạy với database thực tế hoặc Testcontainers khi cần xác minh SQL, constraint và hành vi dialect. Mock repository không thể chứng minh truy vấn SQL được tham số hóa đúng.

## 14. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Nối chuỗi request vào SQL/JPQL | SQL injection | Dùng prepared statement và parameter binding |
| Nghĩ placeholder dùng được cho tên cột | Truy vấn sai hoặc tìm cách nối identifier không an toàn | Dùng allowlist cho identifier |
| Chỉ lọc dấu nháy hoặc từ khóa SQL | Có thể bị vượt qua và làm hỏng dữ liệu hợp lệ | Tách dữ liệu khỏi cú pháp bằng binding |
| Dùng ORM nên bỏ qua kiểm tra native query | Native SQL ghép chuỗi vẫn có injection | Parameterize mọi truy vấn, kể cả native |
| Nhận nguyên filter object từ client | Client có thể chèn toán tử hoặc cấu trúc truy vấn | Map request sang query criteria được kiểm soát |
| Bind ID an toàn nhưng không kiểm tra quyền | IDOR/BOLA và truy cập chéo tenant | Kiểm tra authorization và data scope |
| Lấy tenantId từ client làm nguồn tin cậy | Có thể truy vấn dữ liệu tenant khác | Lấy tenant context từ danh tính đã xác thực |
| Trả entity đầy đủ cho mọi màn hình | Lộ trường nhạy cảm và tải dữ liệu thừa | Dùng projection/DTO tối thiểu |
| Dùng tài khoản database quyền admin | Tăng hậu quả khi bị khai thác | Least privilege |
| Log toàn bộ SQL và tham số nhạy cảm | Rò rỉ dữ liệu qua log | Log có chọn lọc và che dữ liệu |

## 15. Quy trình thiết kế một truy vấn an toàn

Khi thêm chức năng đọc hoặc ghi dữ liệu, hãy đi theo các bước:

1. Xác định use case và dữ liệu người dùng được phép truy cập.
2. Thiết kế request DTO hoặc query criteria với kiểu dữ liệu rõ ràng.
3. Lấy user/tenant context từ nguồn xác thực ở server.
4. Đưa điều kiện quyền sở hữu hoặc tenant vào truy vấn khi phù hợp.
5. Viết SQL/JPQL cố định và bind mọi giá trị bằng parameter.
6. Nếu cấu trúc truy vấn thay đổi, dùng enum, allowlist hoặc query builder có kiểu.
7. Giới hạn page size, số lượng kết quả và các bộ lọc được hỗ trợ.
8. Chỉ chọn các cột cần thiết cho use case.
9. Dùng tài khoản database có quyền tối thiểu.
10. Kiểm thử injection, truy cập chéo tenant, quyền theo vai trò và hiệu năng với database phù hợp.

Nếu một truy vấn cần nhiều điều kiện động, hãy tạo query criteria có cấu trúc thay vì truyền chuỗi SQL. Nếu logic truy vấn chứa quy tắc phân quyền phức tạp, hãy phối hợp với application service hoặc authorization policy để đảm bảo mọi luồng gọi đều áp dụng cùng chính sách.

## 16. Những điểm cần ghi nhớ

Truy vấn an toàn bắt đầu bằng việc tách giá trị dữ liệu khỏi cấu trúc truy vấn. JDBC PreparedStatement, named parameter trong Spring JDBC, JPQL parameter binding và Criteria API giúp tránh việc dữ liệu đầu vào bị diễn giải thành cú pháp. Identifier và hướng sắp xếp không thể bind như giá trị; hãy ánh xạ chúng qua allowlist.

Lớp truy cập dữ liệu đóng gói truy vấn, parameter binding, mapping và giới hạn dữ liệu. Nó không thay thế authentication hoặc authorization. Một truy vấn không có SQL injection vẫn có thể trả dữ liệu của người khác nếu thiếu tenant scope hoặc kiểm tra quyền trên tài nguyên.

Hãy lấy danh tính và tenant từ ngữ cảnh đã xác thực, chỉ trả dữ liệu cần thiết, dùng tài khoản database quyền tối thiểu, không để raw query từ client đi vào DAL và không tiết lộ SQL trong response. Kết hợp unit test với integration test trên database phù hợp để xác minh cả cú pháp, quyền truy cập và hành vi thực tế.

Một lớp truy cập dữ liệu có ranh giới rõ giúp ứng dụng MVC kiểm soát truy vấn nhất quán, giảm nguy cơ injection và ngăn các tầng giao diện vô tình quyết định cách database được truy cập.
