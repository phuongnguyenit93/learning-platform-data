# Thiết kế Optional hoặc kết quả rỗng ở hợp đồng repository

Trong tầng **truy vấn JDBC** của Spring Framework, một câu SELECT có thể trả **0 hàng**, **1 hàng** hoặc **nhiều hàng**. Cách repository công bố kết quả đó là một phần của hợp đồng API: caller phải biết khi nào **không tìm thấy** là tình huống hợp lệ, khi nào **thiếu bản ghi** là lỗi nghiệp vụ, và khi nào database hoặc dữ liệu đã vi phạm giả định.

Một hợp đồng tốt cho biết ngay trong kiểu trả về:

- **Optional<T>**: có **0 hoặc 1** đối tượng; vắng mặt là kết quả dự kiến.
- **List<T>**: có **0 đến nhiều** đối tượng; không có phần tử là **danh sách rỗng**.
- **T bắt buộc**: cần **đúng 1** đối tượng; vắng mặt hoặc nhiều hơn một phải có cách xử lý được định nghĩa.
- **boolean**: trả lời câu hỏi có tồn tại hay không.
- **long/int**: biểu diễn số lượng, bao gồm số 0.

Bài tập trung vào JdbcTemplate, NamedParameterJdbcTemplate, JdbcClient và DataAccessUtils của Spring JDBC, với Java 17+; ví dụ SQL dùng H2/PostgreSQL. Đồng thời phân biệt **SQL không có hàng**, **một hàng có cột NULL**, **lỗi nhiều hàng**, **lỗi truy cập database** và cách service sử dụng kết quả.

## 1. Định nghĩa hợp đồng theo cardinality trước khi chọn API

**Cardinality** là số bản ghi truy vấn có thể trả về theo nghiệp vụ. Hợp đồng của phương thức phải mô tả ít nhất bốn điều: đầu vào, số kết quả hợp lệ, giá trị khi không có dữ liệu, và hành vi khi dữ liệu vi phạm ràng buộc.

| Phương thức nghiệp vụ | Cardinality | Chữ ký đề xuất | Khi 0 hàng |
| --- | --- | --- | --- |
| Tìm một user theo khóa chính | 0..1 | Optional<User> findById(long id) | Optional.empty() |
| Tìm user theo email UNIQUE | 0..1 | Optional<User> findByEmail(String email) | Optional.empty() |
| Tìm mọi user theo trạng thái | 0..n | List<User> findByStatus(String status) | List rỗng |
| Đọc user bắt buộc cho một lệnh | Đúng 1 | User getRequiredById(long id) | Lỗi có chủ đích |
| Kiểm tra ID tồn tại | true/false | boolean existsById(long id) | false |
| Đếm user theo trạng thái | Một số đếm | long countByStatus(String status) | 0 |
| Truy vấn phân trang | 0..n + metadata | PageResult<User> | items rỗng với metadata trang |

Ví dụ chữ ký:

~~~java
import java.util.List;
import java.util.Optional;

public interface UserRepository {
    Optional<User> findById(long id);
    Optional<User> findByEmail(String email);
    List<User> findByStatus(String status);
    User getRequiredById(long id);
    boolean existsById(long id);
    long countByStatus(String status);
}
~~~

Đây là **minh họa thiết kế**, kiểu domain User cần được định nghĩa bởi ứng dụng. Không nên để cùng một khái niệm “không tìm thấy” khi thì trả null, khi thì trả Optional.empty(), khi thì trả một List rỗng tùy tiện. Quy ước phải xuất phát từ cardinality của từng phương thức.

**Tên method cũng là hợp đồng:** findById gợi ý cho phép không có; getRequiredById thông báo phải có; findAllByStatus nói rõ một tập hợp. Cách đặt tên không thay thế tài liệu API, nhưng giúp caller đọc đúng nghĩa.

### 1.1. Vì sao Optional<List<T>> thường không phù hợp?

List đã diễn đạt “không có phần tử” bằng danh sách rỗng. Nếu trả Optional<List<User>>, caller phải đoán:

- Optional.empty() có nghĩa chưa truy vấn, database không có dữ liệu, hay không có quyền?
- Optional.of(List.of()) có nghĩa gì khác Optional.empty()?
- Khi nào dùng hai trạng thái rỗng này?

Với truy vấn tập hợp bình thường, chỉ cần **List<User>** và trả **List.of()** hoặc danh sách rỗng do JdbcTemplate tạo. Chỉ dùng mô hình phức tạp hơn khi nghiệp vụ thực sự cần phân biệt “chưa thực hiện” và “đã thực hiện nhưng không có kết quả”; khi đó kiểu kết quả có trạng thái đặt tên rõ ràng thường dễ hiểu hơn Optional<List<T>>.

## 2. Bốn tình huống khác nhau: 0 hàng, 1 hàng, nhiều hàng, SQL NULL

Để thống nhất ví dụ, tạo bảng thực hành:

~~~sql
CREATE TABLE app_users (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    nickname VARCHAR(120),
    status VARCHAR(20) NOT NULL
);

INSERT INTO app_users (id, email, display_name, nickname, status)
VALUES
    (1, 'lan@example.test', 'Lan', NULL, 'ACTIVE'),
    (2, 'minh@example.test', 'Lan', 'M', 'ACTIVE'),
    (3, 'an@example.test', 'An', NULL, 'INACTIVE');
~~~

Bảng có khóa chính id, khóa duy nhất email, còn display_name **không duy nhất** và nickname **cho phép NULL**. Hãy so sánh:

~~~sql
-- Không có hàng nào:
SELECT nickname FROM app_users WHERE id = 999;

-- Có 1 hàng, cột nickname là SQL NULL:
SELECT nickname FROM app_users WHERE id = 1;

-- Có 1 hàng với nickname = 'M':
SELECT nickname FROM app_users WHERE id = 2;

-- Có 2 hàng ACTIVE:
SELECT id, email FROM app_users WHERE status = 'ACTIVE';
~~~

| SQL | Số hàng | Giá trị | Ý nghĩa |
| --- | ---: | --- | --- |
| id = 999 | 0 | Không có bản ghi | User không tồn tại |
| id = 1 | 1 | nickname = NULL | User tồn tại, nhưng nickname chưa được đặt |
| id = 2 | 1 | nickname = M | User tồn tại và nickname có giá trị |
| status = ACTIVE | 2 | Hai user khác nhau | Truy vấn tập hợp hợp lệ |

**Không có hàng không đồng nghĩa một hàng có SQL NULL.** Nếu repository trả Optional<User>, user id=1 phải là **Optional present** khi RowMapper tạo một đối tượng User có trường nickname null. Nếu repository chỉ truy vấn nickname và dùng Optional.ofNullable, hai tình huống trên có thể cùng trở thành empty; chỉ chấp nhận cách đó nếu hợp đồng thực sự hỏi “nickname có giá trị không?” thay vì “user có tồn tại không?”.

**Lỗi database** cũng là trạng thái riêng: sai SQL, mất kết nối, timeout, lỗi quyền hoặc lỗi mapping không cho phép kết luận “không tìm thấy”.

## 3. JdbcTemplate.query(...) cho 0..n: List rỗng là kết quả hợp lệ

Trong Spring JDBC, phương thức query(String, RowMapper, Object...) ánh xạ từng hàng của ResultSet và trả một **List<T>**. Khi SQL trả 0 hàng, danh sách trả về là **rỗng**, không phải null.

~~~java
List<UserRow> users = jdbcTemplate.query(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE status = ?
    ORDER BY id
    """,
    (rs, rowNum) -> new UserRow(
        rs.getLong("id"),
        rs.getString("email"),
        rs.getString("display_name"),
        rs.getString("nickname")
    ),
    "ACTIVE"
);
~~~

Đoạn trên là một phần của ứng dụng đã khai báo jdbcTemplate và record UserRow, không phải chương trình độc lập. Với dữ liệu mẫu, users.size() bằng **2**; status không tồn tại thì users.isEmpty() bằng true.

Ví dụ repository:

~~~java
public List<UserRow> findByStatus(String status) {
    return jdbc.query(
        """
        SELECT id, email, display_name, nickname
        FROM app_users
        WHERE status = ?
        ORDER BY id
        """,
        USER_ROW_MAPPER,
        status
    );
}
~~~

Caller dùng **isEmpty()**, **size()**, **forEach(...)** bình thường. Không nên viết mã repository chuyển danh sách rỗng thành null vì sẽ ép mọi caller thêm một nhánh kiểm tra null vô nghĩa.

### 3.1. NamedParameterJdbcTemplate cũng giữ quy tắc này

~~~java
List<UserRow> found = namedJdbc.query(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE status = :status
    ORDER BY id
    """,
    java.util.Map.of("status", "ACTIVE"),
    USER_ROW_MAPPER
);
~~~

Khác biệt là **:status** được bind theo tên. Hành vi cardinality vẫn như JdbcTemplate: query trả 0..n, queryForObject đòi đúng một. Không hiểu nhầm tham số tên là API tự biến kết quả thành Optional.

## 4. JdbcTemplate.queryForObject(...) cho đúng một hàng

queryForObject là một API nghiêm ngặt về **số hàng**. Với overload dùng RowMapper:

~~~java
UserRow user = jdbc.queryForObject(
    """
    SELECT id, email, display_name, nickname
    FROM app_users
    WHERE id = ?
    """,
    USER_ROW_MAPPER,
    1L
);
~~~

Hành vi theo Javadoc:

| ResultSet | Hành vi queryForObject |
| --- | --- |
| 0 hàng | **EmptyResultDataAccessException** |
| Đúng 1 hàng | Trả đối tượng được RowMapper map; có thể null nếu RowMapper chủ động trả null |
| 2+ hàng | **IncorrectResultSizeDataAccessException** |
| SQL/driver/DB lỗi | Một **DataAccessException** thích hợp sau bước dịch lỗi của Spring |

EmptyResultDataAccessException là subclass của IncorrectResultSizeDataAccessException, vì “0 hàng” cũng là sai số lượng khi yêu cầu chính xác một. Nếu code catch IncorrectResultSizeDataAccessException và trả Optional.empty(), nó sẽ **nuốt luôn cả trường hợp 2+ hàng**, rất nguy hiểm khi query hoặc dữ liệu bị lỗi.

### 4.1. Scalar query và SQL NULL

Overload queryForObject(sql, Integer.class, args...) mong đợi **đúng một hàng, một cột**. Nếu hàng tồn tại nhưng cột là SQL NULL, kết quả có thể là Java null:

~~~java
Integer result = jdbc.queryForObject(
    "SELECT CAST(NULL AS INTEGER)",
    Integer.class
);
// result == null: có một hàng, nhưng giá trị cột SQL NULL.
~~~

Đối chiếu:

~~~java
Integer result = jdbc.queryForObject(
    "SELECT id FROM app_users WHERE id = ?",
    Integer.class,
    999L
);
// 0 hàng -> EmptyResultDataAccessException, KHÔNG trả null.
~~~

Đây là điểm phải nhớ khi đọc tài liệu API: trả null **có thể biểu diễn SQL NULL** với truy vấn scalar, trong khi không có hàng thường gây exception.

### 4.2. Sai lầm: Optional.ofNullable(queryForObject(...))

~~~java
// Cách này KHÔNG chuyển 0 hàng thành Optional.empty().
Optional<UserRow> user = Optional.ofNullable(
    jdbc.queryForObject(
        "SELECT id, email, display_name, nickname " +
        "FROM app_users WHERE id = ?",
        USER_ROW_MAPPER,
        id
    )
);
~~~

Lời gọi queryForObject được đánh giá trước; khi 0 hàng nó ném EmptyResultDataAccessException, nên Optional.ofNullable **không bao giờ được gọi**. Phải thay đổi lựa chọn API hoặc xử lý đúng exception.

## 5. Thiết kế findById bằng Optional<T>

### 5.1. Cách rõ ràng với query và DataAccessUtils.optionalResult

Từ **Spring Framework 6.1**, DataAccessUtils cung cấp optionalResult(Collection), chuyển collection có cardinality 0..1 thành Optional.

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.dao.support.DataAccessUtils;

public Optional<UserRow> findById(long id) {
    List<UserRow> rows = jdbc.query(
        """
        SELECT id, email, display_name, nickname
        FROM app_users
        WHERE id = ?
        """,
        USER_ROW_MAPPER,
        id
    );
    return DataAccessUtils.optionalResult(rows);
}
~~~

Trường hợp cụ thể:

- 0 phần tử: **Optional.empty()**.
- 1 phần tử khác null: **Optional chứa UserRow**.
- Trên 1 phần tử: **IncorrectResultSizeDataAccessException**.
- 1 phần tử null: Optional không thể chứa null nên **Optional.empty()**.

Điểm cuối rất quan trọng: RowMapper của domain nên luôn tạo **một đối tượng không null** cho một hàng hợp lệ. Nếu mapper chọn trả null vì trường dữ liệu sai, optionalResult có thể che mất khác biệt giữa “có hàng không hợp lệ” và “không có hàng”. Hãy bảo vệ constraint ở database, map field nullable đúng cách, và báo lỗi khi hàng không ánh xạ được.

DataAccessUtils còn có **singleResult(Collection)** trả null khi 0 hàng và ném lỗi khi >1; **requiredSingleResult(Collection)** đòi đúng một đối tượng không null; không nhầm chúng với optionalResult. Cần kiểm tra phiên bản Spring trước khi gọi optionalResult vì Spring 6.0 chưa có API này.

### 5.2. Cách dùng queryForObject và bắt riêng EmptyResultDataAccessException

Nếu dự án dùng Spring cũ hoặc repository muốn tiếp tục dùng queryForObject:

~~~java
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;

public Optional<UserRow> findById(long id) {
    try {
        UserRow value = jdbc.queryForObject(
            """
            SELECT id, email, display_name, nickname
            FROM app_users
            WHERE id = ?
            """,
            USER_ROW_MAPPER,
            id
        );
        return Optional.ofNullable(value);
    } catch (EmptyResultDataAccessException missing) {
        return Optional.empty();
    }
}
~~~

**Chỉ bắt EmptyResultDataAccessException** để chuyển “0 hàng” thành một kết quả cho phép vắng mặt. Không bắt toàn bộ DataAccessException; mất kết nối, vi phạm quyền, lỗi SQL hoặc dữ liệu trùng đều là lỗi thực và cần được xử lý/giám sát.

Cũng không dùng **catch (Exception e) { return Optional.empty(); }**. Cách đó che cả lỗi lập trình lẫn lỗi database và khiến hệ thống báo “user không tồn tại” trong khi database đang hỏng.

## 6. Spring JdbcClient: optional() và single() (Spring 6.1+)

**JdbcClient** là API fluent mới từ Spring 6.1, hoạt động trên JdbcTemplate/NamedParameterJdbcTemplate và hỗ trợ tham số theo vị trí hoặc tên. Với một RowMapper:

~~~java
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;

public Optional<UserRow> findById(long id) {
    return jdbcClient
        .sql("""
             SELECT id, email, display_name, nickname
             FROM app_users
             WHERE id = :id
             """)
        .param("id", id)
        .query(USER_ROW_MAPPER)
        .optional();
}
~~~

Đoạn trên thuộc một repository đã có trường jdbcClient và USER_ROW_MAPPER. optional() trên **JdbcClient.MappedQuerySpec** giữ cardinality 0..1: 0 hàng -> Optional.empty(), 1 hàng -> Optional present, hơn một hàng -> lỗi.

Các lựa chọn khác:

~~~java
// Truy vấn tập hợp, 0..n.
List<UserRow> users = jdbcClient
    .sql("SELECT id, email, display_name, nickname " +
         "FROM app_users WHERE status = :status ORDER BY id")
    .param("status", "ACTIVE")
    .query(USER_ROW_MAPPER)
    .list();

// Truy vấn bắt buộc đúng một UserRow.
UserRow required = jdbcClient
    .sql("SELECT id, email, display_name, nickname " +
         "FROM app_users WHERE id = :id")
    .param("id", 1L)
    .query(USER_ROW_MAPPER)
    .single();
~~~

**Phiên bản:** MappedQuerySpec.optional() và JdbcClient xuất hiện từ Spring **6.1**. API **ResultQuerySpec.optionalValue()** cho truy vấn giá trị một cột được bổ sung ở Spring **6.2**; không giả định mọi tiện ích mới đều có trên 6.1. Đọc Javadoc đúng version, nhất là khi dùng Spring Boot quản lý phiên bản Spring Framework.

## 7. Bắt buộc có bản ghi: repository hay service báo lỗi?

Có những truy vấn cho phép “không tồn tại”, nhưng một số thao tác nghiệp vụ đòi hỏi bản ghi phải có. Cách tách hợp đồng:

~~~java
public interface AccountRepository {
    Optional<Account> findById(long id);
    Account getRequiredById(long id);
}
~~~

**Account** là domain class cần có trong ứng dụng. Một cách triển khai phổ biến là repository trả Optional còn service quyết định lỗi nghiệp vụ:

~~~java
public Account requireAccount(long accountId) {
    return accountRepository.findById(accountId)
        .orElseThrow(() -> new AccountNotFoundException(accountId));
}
~~~

**AccountNotFoundException** là exception ứng dụng định nghĩa. Trong trường hợp khác, hợp đồng getRequiredById có thể ném chính loại exception nghiệp vụ khi vắng mặt, nhưng phải nhất quán và có tài liệu rõ.

**Không đưa HTTP vào JDBC repository:** repository không nên ném trực tiếp HTTP 404/ResponseStatusException. Service xử lý “không tìm thấy trong nghiệp vụ”, còn REST controller hoặc @ControllerAdvice ánh xạ sang 404 nếu thích hợp. Một scheduled job hoặc consumer message có thể xử lý cùng trạng thái vắng mặt theo cách khác.

Phân biệt thêm **không tồn tại** với **không có quyền xem**. Một query được lọc bởi tenant/authorization có thể không trả bản ghi mà người dùng không được phép nhìn thấy; cách công bố 403/404 là chính sách bảo mật ở tầng trên. Không vô tình tiết lộ sự tồn tại của tài nguyên qua lỗi, log hoặc thời gian phản hồi.

## 8. Truy vấn theo khóa duy nhất và bảo vệ cardinality bằng schema

Hợp đồng Optional<User> cho ID/email dựa trên giả định SQL có thể tìm thấy tối đa một hàng. **PRIMARY KEY** và **UNIQUE constraint** là cách database bảo đảm giả định đó.

Nếu tên hiển thị không duy nhất:

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE display_name = 'Lan';
~~~

Kết quả mẫu có **2 hàng**. Không được triển khai findByDisplayName trả Optional<User> theo kiểu “lấy phần tử đầu tiên” nếu nghiệp vụ chưa hề quy định chọn ai. Hợp đồng đúng thường là List<User> findByDisplayName(...).

### 8.1. LIMIT 1 có thể che dữ liệu lỗi

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE display_name = 'Lan'
LIMIT 1;
~~~

Lệnh này chỉ trả một hàng nhưng không bảo đảm hàng nào nếu thiếu ORDER BY. Việc tự thêm LIMIT 1 **không sửa** hợp đồng “phải duy nhất”; nó có thể che duplicate gây ra bởi dữ liệu hoặc JOIN sai.

Nếu yêu cầu thực sự là “bản ghi cập nhật mới nhất”, hãy đặt tên phù hợp, dùng ORDER BY updated_at DESC, id DESC và LIMIT 1. Khi đó việc chọn một trong nhiều hàng **là quy tắc nghiệp vụ đã nêu**, có thể trả Optional nếu không có hàng.

### 8.2. LIMIT 2 để phát hiện nhiều hàng

Nếu một truy vấn dự kiến 0..1 nhưng chưa có ràng buộc DB đủ mạnh và muốn kiểm tra hiệu quả:

~~~sql
SELECT id, email, display_name, nickname
FROM app_users
WHERE email = ?
LIMIT 2;
~~~

Kết hợp query(...) trả List và optionalResult(List): 2 hàng -> lỗi cardinality; 0 hoặc 1 xử lý bình thường. Đây chỉ là chiến thuật giảm dữ liệu chuyển về Java khi phát hiện trùng, không thay thế UNIQUE constraint. Cú pháp LIMIT còn tùy DBMS.

## 9. COUNT, EXISTS và trường hợp không nên dùng Optional

Câu hỏi “user có tồn tại không?” thường cần boolean, không phải Optional<User> nếu caller không cần tải dữ liệu user:

~~~java
public boolean existsById(long id) {
    Integer count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM app_users WHERE id = ?",
        Integer.class,
        id
    );
    if (count == null) {
        throw new IllegalStateException("COUNT(*) returned NULL");
    }
    return count > 0;
}
~~~

**SELECT COUNT(*) không GROUP BY** trả một hàng với số đếm; khi không có bản ghi khớp, giá trị là **0**, chứ không phải 0 hàng. Vì vậy long/int là hợp đồng phù hợp hơn Optional<Long>. Tùy DBMS và workload, EXISTS có thể tối ưu hơn COUNT(*) cho bài toán tồn tại.

Tương tự:

~~~sql
SELECT MAX(id) FROM app_users WHERE status = 'UNKNOWN';
~~~

Một truy vấn aggregate không GROUP BY thường **trả một hàng**, nhưng MAX có thể là **SQL NULL** khi không có giá trị để tổng hợp. Với queryForObject(..., Long.class), Java có thể nhận null. Nếu nghiệp vụ muốn “giá trị max có thể không xác định”, Optional<Long> có thể phù hợp, nhưng phải hiểu nó nói về sự vắng mặt của **giá trị aggregate**, không phải JDBC không trả hàng.

## 10. Cách dùng Optional ở service: map, orElseGet và orElseThrow

~~~java
Optional<UserRow> found = repository.findById(userId);

// Biến đổi chỉ khi đối tượng tồn tại.
Optional<String> email = found.map(UserRow::email);

// Lỗi nghiệp vụ rõ ràng khi bắt buộc có.
UserRow required = found.orElseThrow(
    () -> new UserNotFoundException(userId)
);

// Thực hiện một side effect khi có giá trị.
found.ifPresent(user -> audit.recordFound(user.id()));
~~~

Đây là đoạn minh họa; các biến repository, userId, audit và UserNotFoundException phải được khai báo trong ứng dụng.

Các điểm cần nhớ:

- **Optional.get()** khi empty ném NoSuchElementException chung chung; ưu tiên orElseThrow kèm ngữ cảnh nghiệp vụ.
- **orElse(expensiveDefault())** gọi expensiveDefault ngay cả khi Optional đã present, vì đối số Java được đánh giá trước. Khi muốn tính fallback chỉ nếu empty, dùng **orElseGet(() -> expensiveDefault())**.
- **Optional.orElse(null)** có thể cần trong mã tích hợp legacy nhưng trả null qua nhiều lớp sẽ làm mất hợp đồng Optional.
- Một method trả Optional<T> **không được trả null thay cho Optional.empty()**.
- Optional chủ yếu phù hợp ở kiểu **return** của truy vấn 0..1; không mặc định dùng Optional làm field entity, tham số repository hoặc lớp serialize.

**Optional không giúp SQL chạy nhanh hơn.** Nó chỉ diễn đạt trạng thái dữ liệu với caller rõ hơn.

## 11. Khi nghiệp vụ có hơn hai trạng thái

Optional chỉ biểu diễn **present/absent**. Nó không tự diễn đạt:

- Không tìm thấy.
- Có bản ghi nhưng caller bị từ chối quyền.
- Bản ghi đã vô hiệu hóa.
- Truy vấn thất bại do database, network hoặc timeout.

Nếu tất cả đều là trạng thái nghiệp vụ bình thường và caller cần phản ứng khác nhau, có thể thiết kế **kiểu kết quả riêng** thay vì biến mọi thứ thành Optional.empty():

~~~java
public sealed interface AccountLookup
        permits AccountLookup.Found,
                AccountLookup.Missing,
                AccountLookup.Disabled {

    record Found(Account account) implements AccountLookup {}
    record Missing(long accountId) implements AccountLookup {}
    record Disabled(long accountId) implements AccountLookup {}
}
~~~

Đây là ví dụ Java 17 với kiểu Account do ứng dụng định nghĩa. Đừng biến một lỗi database thành trạng thái Missing để trông như truy vấn thành công. Chỉ thêm mô hình này khi thực sự cần; tìm theo ID thông thường với Optional<User> là đủ.

## 12. Ví dụ chạy được: minh họa 0 hàng, 1 hàng, 2 hàng và SQL NULL

Ví dụ dùng **Java 17+**, **Spring JDBC 6.2.7** và **H2 2.3.232**, tạo dữ liệu trong bộ nhớ. Gradle sẽ quản lý các jar Spring JDBC/H2. Mục tiêu là làm rõ output của các hợp đồng, không phụ thuộc Spring Boot web server.

Cấu trúc:

~~~text
jdbc-contract-demo/
  build.gradle
  src/main/java/demo/RepositoryContractDemo.java
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
    mainClass = 'demo.RepositoryContractDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Tệp **src/main/java/demo/RepositoryContractDemo.java**:

~~~java
package demo;

import java.util.List;
import java.util.Optional;
import org.springframework.dao.EmptyResultDataAccessException;
import org.springframework.dao.IncorrectResultSizeDataAccessException;
import org.springframework.dao.support.DataAccessUtils;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public class RepositoryContractDemo {

    record UserRow(long id, String email, String displayName) {}

    interface UserRepository {
        Optional<UserRow> findById(long id);
        List<UserRow> findByDisplayName(String displayName);
        UserRow requireById(long id);
    }

    static final class JdbcUserRepository implements UserRepository {
        private static final RowMapper<UserRow> MAPPER =
                (rs, rowNum) -> new UserRow(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
                );

        private final JdbcTemplate jdbc;

        JdbcUserRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        public Optional<UserRow> findById(long id) {
            List<UserRow> rows = jdbc.query(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE id = ?
                """,
                MAPPER,
                id
            );
            return DataAccessUtils.optionalResult(rows);
        }

        @Override
        public List<UserRow> findByDisplayName(String displayName) {
            return jdbc.query(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE display_name = ?
                ORDER BY id
                """,
                MAPPER,
                displayName
            );
        }

        @Override
        public UserRow requireById(long id) {
            return jdbc.queryForObject(
                """
                SELECT id, email, display_name
                FROM app_users
                WHERE id = ?
                """,
                MAPPER,
                id
            );
        }
    }

    public static void main(String[] args) {
        DriverManagerDataSource source = new DriverManagerDataSource(
            "jdbc:h2:mem:contract_demo;DB_CLOSE_DELAY=-1",
            "sa",
            ""
        );
        JdbcTemplate jdbc = new JdbcTemplate(source);

        jdbc.execute(
            """
            CREATE TABLE app_users (
                id BIGINT PRIMARY KEY,
                email VARCHAR(120) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL
            )
            """
        );
        jdbc.update(
            "INSERT INTO app_users (id, email, display_name) " +
            "VALUES (?, ?, ?)",
            1L, "lan@example.test", "Lan"
        );
        jdbc.update(
            "INSERT INTO app_users (id, email, display_name) " +
            "VALUES (?, ?, ?)",
            2L, "minh@example.test", "Lan"
        );

        UserRepository repo = new JdbcUserRepository(jdbc);
        System.out.println("findById(99): " + repo.findById(99L));
        System.out.println(
            "findById(1).email: " +
            repo.findById(1L).map(UserRow::email).orElse("none")
        );
        System.out.println(
            "findByDisplayName(Nobody).size: " +
            repo.findByDisplayName("Nobody").size()
        );
        System.out.println(
            "findByDisplayName(Lan).size: " +
            repo.findByDisplayName("Lan").size()
        );

        try {
            repo.requireById(99L);
        } catch (EmptyResultDataAccessException ex) {
            System.out.println(
                "requireById(99): " + ex.getClass().getSimpleName()
            );
        }

        try {
            jdbc.queryForObject(
                """
                SELECT id, email, display_name
                FROM app_users WHERE display_name = ?
                """,
                (rs, rowNum) -> new UserRow(
                    rs.getLong("id"),
                    rs.getString("email"),
                    rs.getString("display_name")
                ),
                "Lan"
            );
        } catch (IncorrectResultSizeDataAccessException ex) {
            System.out.println(
                "multiple rows: " + ex.getClass().getSimpleName()
            );
        }

        Integer nullableValue = jdbc.queryForObject(
            "SELECT CAST(NULL AS INTEGER)",
            Integer.class
        );
        System.out.println("one SQL NULL: " + nullableValue);
    }
}
~~~

Chạy trong thư mục chứa build.gradle với Gradle đã cài:

~~~bash
gradle run
~~~

Nếu dự án đã có Gradle Wrapper, dùng:

~~~bash
./gradlew run
~~~

Trên Windows PowerShell, nếu có Wrapper:

~~~powershell
.\gradlew.bat run
~~~

Không chạy riêng lệnh javac RepositoryContractDemo.java nếu chưa cung cấp classpath Spring JDBC/H2, vì Java compiler sẽ thiếu package. Gradle giải quyết các dependency; các lớp dùng cú pháp Java 17 record và text block.

**Stdout của chương trình** (bỏ các dòng log/build của Gradle):

~~~text
findById(99): Optional.empty
findById(1).email: lan@example.test
findByDisplayName(Nobody).size: 0
findByDisplayName(Lan).size: 2
requireById(99): EmptyResultDataAccessException
multiple rows: IncorrectResultSizeDataAccessException
one SQL NULL: null
~~~

Giải thích:

1. ID 99 không tồn tại -> findById trả Optional.empty().
2. ID 1 có user -> Optional chứa UserRow; map lấy email.
3. Không có displayName Nobody -> List rỗng.
4. Có hai user tên Lan -> List chứa hai bản ghi, đây là kết quả hợp lệ của findByDisplayName.
5. requireById cần đúng một bản ghi -> queryForObject ném EmptyResultDataAccessException khi 0 hàng.
6. queryForObject theo displayName không UNIQUE nhận 2 hàng -> IncorrectResultSizeDataAccessException.
7. SELECT CAST(NULL AS INTEGER) trả một hàng có SQL NULL -> giá trị Java null.

Demo dùng **DriverManagerDataSource** để giảm cấu hình, không phải connection pool. Hệ thống production thường dùng HikariCP/DataSource do Spring Boot quản lý, migration schema và transaction boundaries ở service.

## 13. Những test thực sự có giá trị

Bài test repository phải kiểm tra **ngữ nghĩa SQL và cardinality**, không chỉ kiểm tra method được gọi.

| Kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Find theo ID không có | ID chưa tồn tại | Optional.empty() |
| Find theo ID có | Một bản ghi hợp lệ | Optional present với ID/email đúng |
| Query 0..1 bất ngờ có nhiều hàng | Query/JOIN trả 2+ hàng | IncorrectResultSizeDataAccessException |
| Tìm tập hợp trống | Không bản ghi thỏa status | List rỗng, khác null |
| Tìm tập hợp có nhiều | Hai bản ghi | List có đủ 2 và ORDER BY đúng |
| Trường nullable | Một user có nickname SQL NULL | Optional<User> present, nickname null |
| Sai SQL/schema | Tên bảng/cột sai | DataAccessException, không empty |
| DB timeout/mất kết nối | Hạ tầng DB không đáp ứng | Lỗi dữ liệu/kết nối, không empty |
| Service yêu cầu ID bắt buộc | Repo trả Optional.empty() | Exception nghiệp vụ thích hợp |
| Tenant/permission | ID nằm ngoài phạm vi truy vấn | Không rò dữ liệu qua API |

Unit test dùng mock không nên giả định **JdbcTemplate.query(...) trả null khi 0 hàng**; hành vi chuẩn là List rỗng. Với SQL chứa tính năng riêng của PostgreSQL/MySQL, cần kiểm tra trên DBMS thật hoặc integration test thích hợp (ví dụ Testcontainers); H2 không thay thế hoàn toàn ngữ nghĩa của mọi DBMS.

### 13.1. Test ở service khác test ở repository

Repository test chuyển các hàng JDBC thành Optional/List và không nuốt lỗi kỹ thuật. Service test biến Optional.empty() thành lỗi nghiệp vụ khi bắt buộc có, hoặc trả kết quả phù hợp khi vắng mặt được cho phép. REST controller test ánh xạ lỗi nghiệp vụ sang HTTP response nếu cần. Không viết mọi test lặp lại cùng một assertion ở ba lớp.

## 14. Hiệu năng, stream và đồng thời

**Optional chỉ là kiểu dữ liệu Java**, không giảm thời gian truy vấn. Tối ưu thật nằm ở SQL, index, cardinality, kết nối và transaction.

Nếu một query có thể trả tập lớn, JdbcClient/JdbcTemplate còn có cách xử lý stream/RowCallbackHandler. Stream gắn với JDBC resource phải được đóng đúng theo API (thường try-with-resources); không trả một Stream còn giữ ResultSet mở từ repository ra caller mà không quy định vòng đời rõ ràng.

Lưu ý **check-then-act race condition**: một Optional<User> có dữ liệu ở thời điểm tìm kiếm không bảo đảm bản ghi vẫn tồn tại ngay trước UPDATE tiếp theo. Nếu nghiệp vụ cần thay đổi dữ liệu atomically, cân nhắc UPDATE ... WHERE ... và kiểm tra số hàng ảnh hưởng hoặc thiết kế transaction/locking phù hợp. Optional không bảo đảm isolation.

Khi muốn phát hiện dữ liệu trùng mà không tải toàn tập, kỹ thuật LIMIT 2 cùng optionalResult có thể hiệu quả hơn, nhưng vẫn cần unique constraint ở schema để bảo đảm tính đúng đắn.

## 15. Lỗi phổ biến

| Cách làm sai | Vấn đề | Cách sửa |
| --- | --- | --- |
| Optional.ofNullable(queryForObject(...)) để bắt 0 hàng | queryForObject ném lỗi trước khi Optional được gọi | query + optionalResult; JdbcClient.optional; hoặc bắt riêng EmptyResultDataAccessException |
| catch (DataAccessException) rồi trả Optional.empty() | Che lỗi SQL, DB, timeout và duplicate | Chỉ đổi 0 hàng thành empty |
| Dùng catch IncorrectResultSizeDataAccessException cho mọi vắng mặt | Nuốt cả trường hợp >1 hàng | Bắt subclass EmptyResultDataAccessException cụ thể |
| Trả null cho List rỗng | Caller phải kiểm tra null | Trả List rỗng |
| Trả null thay cho Optional.empty() | Phá hợp đồng Optional | Luôn trả Optional hợp lệ |
| Optional<List<User>> cho kết quả 0..n | Hai cách rỗng không rõ nghĩa | Dùng List<User> |
| findByDisplayName dùng queryForObject khi tên không UNIQUE | Lỗi cardinality khi có hai người cùng tên | Dùng List hoặc thay đổi điều kiện |
| Thêm LIMIT 1 để che duplicate | Mất bản ghi hoặc chọn ngẫu nhiên | Unique constraint hoặc quy tắc ORDER BY tường minh |
| Coi một hàng cột NULL là 0 hàng | Mất thông tin tồn tại | Map cả entity với nullable field |
| Dùng Optional.get() bất chấp empty | NoSuchElementException thiếu ngữ cảnh | map, orElseGet, orElseThrow |
| Để repository ném HTTP 404 | Gắn JDBC vào giao thức REST | Service/controller xử lý transport |
| Nghĩ COUNT(*) bằng 0 là ResultSet rỗng | Sai cardinality của aggregate | Xử lý giá trị số đếm 0 |
| Dùng Optional cho mọi method | API phức tạp vô ích | Chọn kiểu trả về theo cardinality |

## 16. Bài tập tự kiểm tra

**Bài 1.** findById(999) được khai báo Optional<User> và SQL trả 0 hàng. Kết quả đúng là gì?

**Đáp án:** Optional.empty(), vì thiếu một bản ghi là tình huống hợp lệ của truy vấn 0..1.

**Bài 2.** findByStatus("ARCHIVED") khai báo List<User> nhưng không có hàng. Trả Optional.empty(), null hay List rỗng?

**Đáp án:** List rỗng; không có phần tử không phải lỗi của truy vấn collection.

**Bài 3.** queryForObject với ID không tồn tại trả null?

**Đáp án:** Không, thông thường ném EmptyResultDataAccessException do query không trả đúng một hàng.

**Bài 4.** Một hàng user tồn tại nhưng nickname là SQL NULL. Optional<UserRow> có thể present không?

**Đáp án:** Có. RowMapper tạo UserRow không null với nickname null. Optional biểu diễn sự tồn tại của **bản ghi**, không phải mọi field đều có dữ liệu.

**Bài 5.** Optional.ofNullable(jdbc.queryForObject(...)) có biến 0 hàng thành Optional.empty() không?

**Đáp án:** Không. Exception phát sinh trước khi ofNullable chạy.

**Bài 6.** DataAccessUtils.optionalResult nhận List chứa 2 User. Có lấy phần tử đầu và bỏ phần còn lại không?

**Đáp án:** Không. Ném IncorrectResultSizeDataAccessException để báo vi phạm hợp đồng 0..1.

**Bài 7.** Dùng LIMIT 1 cho query theo tên không unique có biến tên thành khóa duy nhất không?

**Đáp án:** Không. Cần UNIQUE constraint hoặc quy tắc chọn bản ghi có thứ tự được định nghĩa rõ.

**Bài 8.** COUNT(*) trên tập rỗng thường trả 0 hàng hay một hàng có giá trị 0?

**Đáp án:** Một hàng có giá trị 0 khi không có GROUP BY. Vì vậy repository thường trả số đếm, không phải Optional.

**Bài 9.** JDBC mất kết nối trong findById. Có nên return Optional.empty() để caller khỏi lỗi?

**Đáp án:** Không. “Không truy vấn được” không thể chứng minh “không tồn tại”; phải để lỗi kỹ thuật được xử lý và quan sát.

**Bài 10.** Service có Optional<User> từ repo. Cách diễn đạt “bắt buộc user phải tồn tại” rõ hơn get() là gì?

**Đáp án:** orElseThrow(() -> new UserNotFoundException(id)) với loại lỗi nghiệp vụ do ứng dụng định nghĩa.

## 17. Checklist thiết kế repository JDBC

1. **Xác định cardinality** của truy vấn trước khi code: 0..1, đúng 1, 0..n hay scalar count.
2. **Viết chữ ký đúng nghĩa:** Optional<T> cho 0..1; List<T> cho 0..n; giá trị bắt buộc cho đúng 1.
3. **Phân biệt rõ:** 0 hàng, một hàng có SQL NULL, >1 hàng, lỗi database và không có quyền.
4. **Chọn Spring API đúng:** query(...) cho List, queryForObject(...) cho đúng một, optionalResult/JdbcClient.optional() cho 0..1.
5. **Chỉ chuyển đúng lỗi vắng mặt** thành Optional.empty; không nuốt DataAccessException chung.
6. **Bảo vệ bằng schema:** PRIMARY KEY, UNIQUE và JOIN/WHERE đúng. Không dùng LIMIT 1 để che dữ liệu trùng.
7. **Giữ RowMapper rõ ràng:** mỗi hàng hợp lệ tạo một đối tượng, map nullable field có chủ đích.
8. **Phân lớp quyết định:** repository quản lý dữ liệu, service đặt quy tắc nghiệp vụ, controller đặt HTTP status.
9. **Kiểm thử 0/1/n**, SQL NULL, duplicate, lỗi truy cập dữ liệu, quyền truy cập và transaction.
10. **Đối chiếu phiên bản:** DataAccessUtils.optionalResult và JdbcClient từ Spring 6.1; tiện ích một giá trị optionalValue từ 6.2.

### Nguồn tham khảo chính thức

- Spring Framework JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- JdbcOperations Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/JdbcOperations.html
- DataAccessUtils Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/dao/support/DataAccessUtils.html
- JdbcClient Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- JdbcClient.MappedQuerySpec Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.MappedQuerySpec.html
