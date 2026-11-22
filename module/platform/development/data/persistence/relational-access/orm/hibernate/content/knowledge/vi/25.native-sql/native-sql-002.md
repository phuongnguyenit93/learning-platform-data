# Tạo native query và binding tham số trong Hibernate

**Native query** cho phép ứng dụng dùng **SQL gốc của cơ sở dữ liệu** thông qua Jakarta Persistence hoặc Hibernate. Khác với HQL/JPQL (truy vấn theo tên entity và thuộc tính Java), native SQL truy vấn trực tiếp tên **bảng, cột, view và cú pháp SQL** mà database hiểu.

Ví dụ:

~~~java
List<?> rows = entityManager.createNativeQuery(
    """
    SELECT id, title, price
    FROM book
    WHERE status = :status
      AND price >= :minPrice
    ORDER BY price ASC, id ASC
    """
)
.setParameter("status", "PUBLISHED")
.setParameter("minPrice", new BigDecimal("100000"))
.getResultList();
~~~

Trong ví dụ này, `book`, `title` và `price` là **tên bảng/cột thật** trong database, còn `:status` và `:minPrice` là **tham số do Hibernate bind**. Lưu ý: named parameters trong native SQL được Hibernate hỗ trợ, nhưng **không được bảo đảm portable giữa mọi JPA provider**. Nếu hệ thống cần portability cao, hãy kiểm tra cách sử dụng positional parameters của provider mục tiêu.

Các kỹ năng cốt lõi của bài:

- Tạo native SELECT và native INSERT/UPDATE/DELETE.
- Bind tham số đúng kiểu, không ghép raw input vào SQL.
- Đọc scalar result, entity result và DTO/projection result.
- Xử lý danh sách `IN`, giá trị NULL và các loại dữ liệu đặc biệt.
- Hiểu sự khác biệt giữa native SQL và entity lifecycle/persistence context.
- Sắp xếp, phân trang và kiểm soát SQL injection.
- Kiểm thử query trên database thực tế.

> **Phạm vi phiên bản:** Các ví dụ sử dụng Hibernate ORM 6.x, Jakarta Persistence (`jakarta.persistence`), Java 17+ khi dùng text block/record. Hibernate 5 thường dùng `javax.persistence`. Những API thuộc `org.hibernate.query.NativeQuery` được ghi rõ là Hibernate-specific. SQL minh họa thiên về PostgreSQL; chi tiết `RETURNING`, boolean, UUID, JSON, casts và pagination thay đổi theo DBMS/dialect.

## 1. Native SQL khác HQL/JPQL thế nào?

Giả sử Java entity:

~~~java
@Entity
@Table(name = "book")
public class Book {
    @Id
    private Long id;

    @Column(name = "book_title")
    private String title;

    @Column(name = "unit_price")
    private BigDecimal price;
}
~~~

**HQL/JPQL** tham chiếu entity và property:

~~~sql
select b
from Book b
where b.price >= :minimum
order by b.title
~~~

**Native SQL** tham chiếu bảng và cột vật lý:

~~~sql
SELECT b.id, b.book_title, b.unit_price
FROM book b
WHERE b.unit_price >= :minimum
ORDER BY b.book_title
~~~

| Tiêu chí | HQL/JPQL | Native SQL |
|---|---|---|
| Đối tượng được truy vấn | Entity, thuộc tính Java, association. | Bảng, cột, view, expression SQL. |
| Query được dịch | Hibernate chuyển HQL/JPQL sang SQL. | Hibernate gửi SQL gốc tới DB, có thể xử lý parameter/pagination. |
| Tính portable | Tương đối cao nếu dùng JPQL chuẩn. | Phụ thuộc cú pháp và kiểu dữ liệu của DBMS. |
| Mapping kết quả | Gần với mô hình entity. | Có thể trả scalar, object array, entity hoặc DTO khi cấu hình. |
| Tính năng DB riêng | Có thể bị giới hạn hoặc cần HQL extension. | Có thể dùng CTE, window function, hint, JSON operators, DB functions... theo DB. |
| An toàn | Cần bind parameters. | Cũng cần bind parameters; SQL gốc không tự an toàn. |
| Lifecycle | SELECT có thể trả managed entity; bulk JPQL DML không đi qua entity callbacks. | Native DML không đi qua entity lifecycle/cascade callbacks. |

**Không phải cứ dùng native SQL là nhanh hơn HQL.** Một câu HQL đơn giản thường được Hibernate chuyển thành SQL tương đương. Native SQL hữu ích khi cần kiểm soát SQL cụ thể hoặc dùng tính năng DBMS mà HQL không biểu diễn thuận tiện.

## 2. Mô hình ví dụ xuyên suốt

Giả sử có bảng:

~~~sql
CREATE TABLE author (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE book (
    id BIGINT PRIMARY KEY,
    isbn VARCHAR(20) NOT NULL UNIQUE,
    book_title VARCHAR(300) NOT NULL,
    unit_price NUMERIC(15, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    author_id BIGINT REFERENCES author(id),
    published_at TIMESTAMP NULL
);

CREATE INDEX ix_book_status_price ON book(status, unit_price);
CREATE INDEX ix_book_author ON book(author_id);
~~~

Và entity:

~~~java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

@Entity
@Table(name = "book")
public class Book {
    @Id
    private Long id;

    @Column(name = "isbn", nullable = false, unique = true)
    private String isbn;

    @Column(name = "book_title", nullable = false)
    private String title;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    private BookStatus status;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private Author author;

    @Column(name = "published_at")
    private LocalDateTime publishedAt;

    // Constructors, getters/setters lược bớt.
}

public enum BookStatus {
    DRAFT, REVIEW, PUBLISHED, ARCHIVED
}
~~~

Bài sẽ phân biệt rõ:

- `Book.title` trong HQL tương ứng `book.book_title` trong native SQL.
- `Book.price` tương ứng `book.unit_price`.
- `Book.author` là association Java; native SQL truy cập `author_id` và tự quyết định JOIN.
- `BookStatus.PUBLISHED` là enum Java, còn cột `status` đang lưu chuỗi vì `EnumType.STRING`.

Khi database schema khác ví dụ, phải đổi **tên cột/bảng trong SQL** chứ không tự động dùng tên field Java.

## 3. API JPA cơ bản: EntityManager.createNativeQuery()

Jakarta Persistence định nghĩa các overload thường gặp:

~~~java
Query createNativeQuery(String sqlString);

Query createNativeQuery(
    String sqlString,
    Class resultClass
);

Query createNativeQuery(
    String sqlString,
    String resultSetMapping
);
~~~

Ví dụ SELECT:

~~~java
Query query = entityManager.createNativeQuery(
    """
    SELECT b.id, b.book_title
    FROM book b
    WHERE b.status = :status
    ORDER BY b.id
    """
);

query.setParameter("status", "PUBLISHED");

List<?> rows = query.getResultList();
~~~

Phương thức `getResultList()` trả kết quả của truy vấn SELECT. Với native query không cấu hình mapping, JPA provider/JDBC driver quyết định kiểu Java của các cột scalar.

### Luồng thực thi khái niệm

~~~mermaid
flowchart TD
    A["Application tạo SQL string"] --> B["EntityManager.createNativeQuery"]
    B --> C["setParameter: bind values"]
    C --> D["getResultList / getSingleResult / executeUpdate"]
    D --> E["Hibernate/JDBC chuẩn bị statement"]
    E --> F["Database thực thi SQL"]
    F --> G["JDBC ResultSet / row count"]
    G --> H["Hibernate map scalar / entity / DTO"]
    H --> I["Application dùng kết quả"]
~~~

Khi `createNativeQuery()` được gọi, không nên giả định SQL đã được thực thi ngay. Thao tác thực thi thường xảy ra khi gọi `getResultList()`, `getSingleResult()` hoặc `executeUpdate()`.

## 4. Native SELECT trả một cột

Ví dụ truy vấn danh sách ISBN:

~~~java
List<?> rawIsbns = entityManager.createNativeQuery(
    """
    SELECT isbn
    FROM book
    WHERE status = :status
    ORDER BY isbn
    """
)
.setParameter("status", "PUBLISHED")
.getResultList();

for (Object raw : rawIsbns) {
    String isbn = (String) raw;
    System.out.println(isbn);
}
~~~

Khi SELECT **một cột scalar**, mỗi phần tử thông thường là một giá trị Java tương ứng với cột, **không phải** một `Object[]` có một phần tử. Kiểu có thể là `String`, `Integer`, `Long`, `BigDecimal`, `Timestamp`... phụ thuộc kiểu SQL, JDBC driver, Hibernate và mapping.

Không áp dụng một kiểu cast dựa trên giả định không được kiểm tra. Đặc biệt, cột số nguyên và kết quả aggregate có thể khác kiểu Java giữa dialect/driver.

## 5. Native SELECT trả nhiều cột

~~~java
List<?> rows = entityManager.createNativeQuery(
    """
    SELECT id, book_title, unit_price
    FROM book
    WHERE status = :status
    ORDER BY id
    """
)
.setParameter("status", "PUBLISHED")
.getResultList();

for (Object row : rows) {
    Object[] columns = (Object[]) row;

    Number idNumber = (Number) columns[0];
    Long id = idNumber.longValue();

    String title = (String) columns[1];
    BigDecimal price = (BigDecimal) columns[2];

    System.out.printf("%d | %s | %s%n", id, title, price);
}
~~~

Cần nhớ:

1. Thứ tự phần tử của `Object[]` tương ứng thứ tự cột trong SELECT.
2. Alias SQL không tự tạo DTO.
3. Kiểu scalar có thể bị driver/dialect ảnh hưởng.
4. Nếu đổi thứ tự cột trong SQL mà không cập nhật code đọc mảng, giá trị có thể bị map sai.

Với nhiều cột và logic ứng dụng nghiêm túc, nên dùng result mapping hoặc DTO thay vì lan truyền `Object[]` khắp service.

## 6. Binding tham số tên (named parameters)

Hibernate hỗ trợ dạng `:parameterName` trong native SQL:

~~~java
Query query = entityManager.createNativeQuery(
    """
    SELECT id, book_title
    FROM book
    WHERE status = :status
      AND unit_price >= :minPrice
    ORDER BY id
    """
);

query.setParameter("status", "PUBLISHED");
query.setParameter("minPrice", new BigDecimal("150000"));

List<?> rows = query.getResultList();
~~~

Giải thích:

- `:status` và `:minPrice` là placeholders do Hibernate quản lý.
- `setParameter("status", ...)` truyền **giá trị**, không phải một đoạn cú pháp SQL.
- JDBC bind values theo kiểu phù hợp thay vì nối literal trực tiếp vào SQL string.
- Có thể lặp một named parameter trong SQL nếu Hibernate parser/version hỗ trợ và query được thiết kế phù hợp.

**Portability:** JPA không bảo đảm named parameters được hỗ trợ trong mọi native query implementation. Ví dụ trên dựa vào Hibernate. Nếu chuyển provider, cần kiểm tra tài liệu của provider đó, thường dùng positional parameter chuẩn được provider hỗ trợ.

## 7. Binding tham số vị trí (positional parameters)

Đối với native SQL, dạng marker vị trí kiểu JDBC thường là dấu `?`:

~~~java
Query query = entityManager.createNativeQuery(
    """
    SELECT id, book_title
    FROM book
    WHERE status = ?
      AND unit_price >= ?
    ORDER BY id
    """
);

query.setParameter(1, "PUBLISHED");
query.setParameter(2, new BigDecimal("150000"));

List<?> rows = query.getResultList();
~~~

Với JPA parameter binding, **vị trí thường bắt đầu từ 1**, không phải 0. Đừng nhầm với chỉ số mảng `Object[]` khi đọc kết quả, vì mảng Java bắt đầu từ 0.

Một số provider/phiên bản hỗ trợ dạng `?1`, `?2` trong native SQL; hỗ trợ cụ thể có khác nhau, vì vậy hãy dùng cú pháp mà Hibernate/JPA provider và JDBC dialect đang sử dụng xác nhận. Không trộn lẫn `?`, `?1` và `:name` tùy tiện trong cùng query.

### Named hay positional?

| Tiêu chí | Named parameter | Positional parameter |
|---|---|---|
| Ví dụ | `:status` | `?` |
| Dễ đọc khi query dài | Cao | Thấp hơn. |
| Bảo trì khi đổi thứ tự điều kiện | Thường dễ hơn. | Dễ sai nếu quên đổi chỉ số. |
| Hỗ trợ Hibernate native query | Có. | Có, theo cú pháp hỗ trợ. |
| Portability giữa JPA providers | Không được bảo đảm. | Thường là lựa chọn portable hơn, theo API/provider. |

## 8. Tham số nào được bind?

Binding phù hợp cho **dữ liệu/value expressions**:

~~~sql
WHERE status = :status
  AND unit_price >= :minPrice
  AND published_at < :cutoff
~~~

Binding **không** dùng để thay tên bảng, tên cột, keyword SQL hoặc hướng ORDER BY:

~~~sql
SELECT * FROM :tableName          -- Sai ý tưởng: tên bảng không là value
ORDER BY :sortColumn              -- Không sort theo tên cột được bind
ORDER BY unit_price :direction    -- ASC/DESC không bind như value
~~~

Nếu thực sự cần dynamic table/column/sort, hãy chọn từ **allowlist cố định** do application định nghĩa, không nối raw input của người dùng.

## 9. Tránh SQL injection: giá trị phải được bind

Không an toàn:

~~~java
String sql =
    "SELECT * FROM book WHERE isbn = '" + userInput + "'";

List<?> rows = entityManager.createNativeQuery(sql).getResultList();
~~~

Nếu input chứa dấu nháy hoặc các ký tự SQL đặc biệt, nó có thể làm thay đổi logic query, gây lỗi hoặc SQL injection.

An toàn hơn:

~~~java
List<?> rows = entityManager.createNativeQuery(
    "SELECT * FROM book WHERE isbn = :isbn"
)
.setParameter("isbn", userInput)
.getResultList();
~~~

Parameter binding giúp tách dữ liệu khỏi cú pháp SQL. Tuy nhiên, binding **không** tự xử lý mọi vấn đề nghiệp vụ: cần validate giá trị, quyền truy cập, số lượng trả về, giới hạn thời gian truy vấn và khả năng dữ liệu chứa wildcard.

### LIKE cần escape wildcard nếu tìm literal

~~~sql
SELECT id, book_title
FROM book
WHERE book_title LIKE :pattern ESCAPE '!'
~~~

Helper:

~~~java
static String containsLiteralPattern(String input) {
    String value = input
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");

    return "%" + value + "%";
}
~~~

Sau đó:

~~~java
query.setParameter(
    "pattern",
    containsLiteralPattern(keyword)
);
~~~

Như vậy, ký tự `%` và `_` do người dùng nhập sẽ được xem như dữ liệu literal, không phải wildcard. Điều kiện chữ hoa/chữ thường và collation vẫn phụ thuộc database.

## 10. Dynamic ORDER BY bằng allowlist

Khi API cho phép client chọn sort field:

~~~java
String orderColumn = switch (sortField) {
    case "title" -> "b.book_title";
    case "price" -> "b.unit_price";
    case "date" -> "b.published_at";
    default -> "b.id";
};

String orderDirection = descending ? "DESC" : "ASC";

String sql = """
    SELECT b.id, b.book_title, b.unit_price
    FROM book b
    WHERE b.status = :status
    ORDER BY %s %s, b.id ASC
    """.formatted(orderColumn, orderDirection);

Query query = entityManager.createNativeQuery(sql);
query.setParameter("status", "PUBLISHED");
~~~

Đoạn trên chỉ an toàn vì `orderColumn` được lấy từ allowlist và `orderDirection` được tạo từ boolean của application. Không thay `switch` bằng cách gắn trực tiếp `sortField` vào SQL.

Thêm `b.id` làm tie-breaker để ổn định thứ tự khi nhiều bản ghi có cùng giá trị sort. Nếu sortField mặc định là `id`, ORDER BY có thể chứa ID hai lần; điều đó không cần thiết nhưng không làm thay đổi ý nghĩa.

## 11. Bind danh sách cho IN với Hibernate NativeQuery

Một nhu cầu phổ biến là tìm theo nhiều ID:

~~~sql
SELECT b.*
FROM book b
WHERE b.id IN (:ids)
~~~

Hibernate NativeQuery hỗ trợ binding collection bằng `setParameterList()`:

~~~java
import org.hibernate.Session;
import org.hibernate.query.NativeQuery;

Session session = entityManager.unwrap(Session.class);

NativeQuery<Book> query = session.createNativeQuery(
    """
    SELECT b.*
    FROM book b
    WHERE b.id IN (:ids)
    ORDER BY b.id
    """,
    Book.class
);

query.setParameterList("ids", List.of(10L, 20L, 30L));

List<Book> books = query.getResultList();
~~~

Hibernate triển khai expansion/binding phù hợp thành các JDBC placeholders. Không nối danh sách raw thành một chuỗi `"10,20,30"` rồi chèn vào SQL.

### Collection rỗng

Đừng mặc định `IN (:ids)` với collection rỗng có cùng behavior trên mọi Hibernate version và dialect. Nên quyết định trước:

~~~java
if (ids.isEmpty()) {
    return List.of();
}
~~~

Đây là lựa chọn đúng khi nghiệp vụ là “chỉ trả những ID được cung cấp”. Nếu empty collection có nghĩa “không lọc theo ID”, cần bỏ predicate `IN` khi dựng query. Hai semantics khác nhau.

### NULL trong IN/NOT IN

`NOT IN` có bẫy SQL three-valued logic khi danh sách chứa `NULL`. Các rows không khớp vẫn có thể bị loại vì điều kiện thành UNKNOWN. Không cho giá trị null lọt vào danh sách exclusion nếu không có semantics rõ; trong nhiều tình huống kiểm tra không tồn tại, `NOT EXISTS` tốt hơn.

### Danh sách rất lớn

Mỗi DBMS có giới hạn và chi phí khác nhau cho số bind parameters hoặc kích thước SQL statement. Nếu danh sách hàng chục/hàng trăm nghìn ID, cân nhắc temp table, table-valued parameters, bulk-loading và JOIN, hoặc chiến lược batch có kiểm soát. Không tự giả định một `IN` cực dài luôn tối ưu.

## 12. Kiểu số: Integer, Long, BigDecimal và aggregate

Native SQL có thể trả kiểu số khác nhau tùy JDBC driver:

~~~java
Object raw = entityManager.createNativeQuery(
    "SELECT COUNT(*) FROM book"
).getSingleResult();

long count = ((Number) raw).longValue();
~~~

Cast qua `Number` thường linh hoạt hơn ép cứng một kiểu `Long` khi chưa khai báo scalar mapping. Cần lưu ý conversion và range: `longValue()` có thể mất phần thập phân hoặc overflow nếu dữ liệu không phù hợp; với COUNT thông thường cần giá trị nguyên.

Với tiền tệ:

~~~java
query.setParameter(
    "minPrice",
    new BigDecimal("125000.00")
);
~~~

Đừng bind giá bằng `double` khi domain cần độ chính xác thập phân. Schema `NUMERIC(15,2)` kết hợp `BigDecimal` thường hợp lý hơn cho tiền.

### COUNT với GROUP BY

~~~sql
SELECT status, COUNT(*) AS total
FROM book
GROUP BY status
ORDER BY status
~~~

Kết quả nhiều cột thường là `Object[]`, trong đó `total` có thể mang kiểu số khác nhau theo mapping/driver. Hãy chuyển đổi có kiểm soát hoặc khai báo scalar type rõ bằng Hibernate API.

## 13. Hibernate-specific: addScalar() để khai báo kiểu kết quả

Hibernate cung cấp `NativeQuery.addScalar()` để mô tả scalar column:

~~~java
Session session = entityManager.unwrap(Session.class);

NativeQuery<Long> query = session.createNativeQuery(
    "SELECT COUNT(*) AS total FROM book",
    Long.class
);

query.addScalar("total", Long.class);

Long total = query.getSingleResult();
~~~

Tùy Hibernate version/API overload, có thể không cần `resultClass` khi dùng `addScalar`. Ví dụ minh họa một query trả một cột có alias `total` và mong kiểu `Long`. Nếu đang dùng Hibernate 5 hoặc phiên bản API khác, cần dùng overload của `NativeQuery` tương ứng.

Một số lợi ích:

- Kiểm soát Java type của cột scalar.
- Tránh suy luận kiểu từ JDBC metadata khi không cần thiết.
- Làm rõ alias/cấu trúc kết quả của query.

Với nhiều scalar columns:

~~~java
NativeQuery<?> query = session.createNativeQuery(
    """
    SELECT b.id AS book_id, b.book_title AS title
    FROM book b
    WHERE b.status = :status
    """
);

query.addScalar("book_id", Long.class);
query.addScalar("title", String.class);
query.setParameter("status", "PUBLISHED");

List<?> rows = query.getResultList();
~~~

Thứ tự scalars và shape của kết quả cần được xử lý theo mapping/phiên bản đang dùng. Nếu cần kiểu DTO rõ ràng, dùng result set mapping hoặc transformer.

## 14. Bind boolean và enum: phải hiểu cột vật lý

Native SQL làm việc với representation của database, không phải lúc nào cũng tự biết mapping field của entity.

Với cột `status VARCHAR` lưu tên enum:

~~~java
query.setParameter("status", BookStatus.PUBLISHED.name());
~~~

Nếu bind `BookStatus.PUBLISHED` trực tiếp, Hibernate có thể suy luận Java type/enum binding theo ngữ cảnh, nhưng native SQL không luôn có metadata thuộc tính entity để xác định SQL representation như HQL. Vì vậy, với native query, bind biểu diễn tương ứng schema (ví dụ tên enum) hoặc cung cấp kiểu Hibernate/JDBC tường minh nếu cần.

Với boolean, DB có thể lưu `BOOLEAN` thật, số 0/1, ký tự hoặc representation khác theo DBMS/mapping. Không giả định `true` trong Java luôn là `1` trong database.

Nếu SQL query phụ thuộc mapping converter như `AttributeConverter`, cần kiểm tra xem native scalar parameter có sử dụng converter hay không; không mặc định Hibernate sẽ áp dụng converter khi SQL không tham chiếu attribute path có type metadata.

## 15. Bind ngày giờ, timezone và kiểu JDBC

Ví dụ native SQL:

~~~sql
SELECT b.*
FROM book b
WHERE b.published_at >= :fromTime
  AND b.published_at < :toTime
ORDER BY b.published_at
~~~

Với Hibernate 6 và Java time types, có thể bind:

~~~java
query.setParameter(
    "fromTime",
    LocalDateTime.of(2026, 1, 1, 0, 0)
);
query.setParameter(
    "toTime",
    LocalDateTime.of(2026, 2, 1, 0, 0)
);
~~~

Cần phân biệt:

- `LocalDate` biểu diễn ngày không có giờ.
- `LocalDateTime` không chứa timezone/offset.
- `Instant` biểu diễn thời điểm trên timeline.
- `OffsetDateTime` có offset.
- Kiểu cột `TIMESTAMP` và `TIMESTAMP WITH TIME ZONE` có semantics khác nhau giữa DBMS.

Native query không tự sửa sai nếu application dùng một timezone nhưng DB lưu dữ liệu theo timezone khác. Quy ước lưu UTC/zone và bind type nên nhất quán.

Nếu driver/provider không suy luận được kiểu của một parameter, dùng overload binding có type hoặc chuyển sang JDBC type tương ứng theo API đang dùng. Tránh gửi datetime như chuỗi text rồi dựa vào implicit SQL cast.

## 16. Binding NULL: vì sao đôi khi phải khai báo kiểu?

Một cách lọc optional hay thấy:

~~~sql
WHERE (:isbn IS NULL OR b.isbn = :isbn)
~~~

Cách này tiện nhưng **không luôn portable trong native SQL**: một số DB/driver khó suy luận type cho một placeholder NULL không có thông tin kiểu. PostgreSQL chẳng hạn có thể báo không xác định được data type của parameter trong một số biểu thức.

Giải pháp thực tế:

1. Nếu có filter, thêm predicate `b.isbn = :isbn` và bind string.
2. Nếu không có filter, bỏ predicate khỏi SQL.
3. Nếu bắt buộc bind NULL, dùng type binding phù hợp với API/dialect hoặc SQL CAST thích hợp.

Ví dụ dynamic predicate:

~~~java
StringBuilder sql = new StringBuilder(
    "SELECT b.* FROM book b WHERE 1 = 1"
);

if (isbn != null) {
    sql.append(" AND b.isbn = :isbn");
}

sql.append(" ORDER BY b.id");

Query query = entityManager.createNativeQuery(sql.toString(), Book.class);

if (isbn != null) {
    query.setParameter("isbn", isbn);
}
~~~

Việc chọn thêm/bỏ predicate trong source code an toàn khi chỉ nối các chuỗi SQL **cố định** do application định nghĩa, không chèn raw user input.

## 17. Tạo native query trả entity managed

Có thể yêu cầu Hibernate/JPA map hàng từ SQL thành entity `Book`:

~~~java
Query query = entityManager.createNativeQuery(
    """
    SELECT b.*
    FROM book b
    WHERE b.status = :status
    ORDER BY b.id
    """,
    Book.class
);

query.setParameter("status", "PUBLISHED");

List<?> raw = query.getResultList();

for (Object item : raw) {
    Book book = (Book) item;
    // book là entity kết quả được Hibernate map.
}
~~~

Nếu cần Hibernate typed API:

~~~java
Session session = entityManager.unwrap(Session.class);

NativeQuery<Book> query = session.createNativeQuery(
    """
    SELECT b.*
    FROM book b
    WHERE b.status = :status
    ORDER BY b.id
    """,
    Book.class
);

query.setParameter("status", "PUBLISHED");

List<Book> books = query.getResultList();
~~~

**Quan trọng:** Entity mapping cần các cột mà Hibernate yêu cầu để hydrate entity, đặc biệt **primary key**, discriminator (nếu inheritance) và những cột cần cho entity/subclass mapping. `SELECT b.*` thường là lựa chọn khởi đầu khi một bảng chứa các cột entity cần thiết. Với entity phức tạp, secondary tables, formula, inheritance hoặc multi-table mapping, cần kiểm tra đủ cột/alias theo Hibernate.

### Managed hay detached?

Trong persistence context đang hoạt động, native query trả entity qua ORM mapping thường trả **managed entities** (trừ trường hợp query/EM được cấu hình riêng). Hibernate vẫn áp dụng identity map: cùng entity key trong một persistence context tham chiếu cùng managed instance.

Điều này **không** có nghĩa mọi association sẽ tự động fetch; lazy-loading và fetch plan vẫn phụ thuộc mapping/những gì query cấu hình.

## 18. Không SELECT thiếu cột khi muốn map entity

Ví dụ dễ sai:

~~~java
entityManager.createNativeQuery(
    "SELECT id, book_title FROM book",
    Book.class
);
~~~

Nếu `Book` có các thuộc tính persistent như `price`, `status` hoặc các FK mà Hibernate cần hydrate, việc SELECT thiếu cột có thể dẫn tới lỗi column not found, kết quả thiếu state hoặc behavior phụ thuộc mapping/provider.

Nếu chỉ cần ID và title, hãy lấy **scalar/DTO projection**:

~~~java
List<?> rows = entityManager.createNativeQuery(
    "SELECT id, book_title FROM book"
).getResultList();
~~~

Không nên ép một row chứa vài cột thành entity đầy đủ khi entity mapping yêu cầu nhiều cột.

## 19. JOIN và native entity result mapping

Native SQL có thể JOIN để lọc:

~~~java
NativeQuery<Book> query = session.createNativeQuery(
    """
    SELECT b.*
    FROM book b
    JOIN author a ON a.id = b.author_id
    WHERE a.full_name LIKE :pattern
    ORDER BY b.id
    """,
    Book.class
);

query.setParameter("pattern", "Nguyen%");
List<Book> books = query.getResultList();
~~~

`SELECT b.*` giúp tránh alias collision khi hai bảng đều có `id`, `created_at` hoặc tên cột giống nhau. Truy vấn này **không tự đồng nghĩa fetch join association Author** như `JOIN FETCH` trong HQL. Nó JOIN để lọc SQL rows và map phần `b.*` thành Book.

Với quan hệ một-nhiều, JOIN có thể nhân số SQL rows và dẫn tới kết quả trùng theo root entity. Nếu mục tiêu chỉ kiểm tra tồn tại child, `EXISTS` thường rõ hơn. Nếu cần map nhiều entity trong một row, dùng `@SqlResultSetMapping` hoặc Hibernate-specific API phù hợp.

## 20. Mapping kết quả thành DTO với @SqlResultSetMapping

Khi query tổng hợp nhiều cột và muốn DTO có kiểu rõ:

~~~java
public record BookSummary(
    Long id,
    String title,
    Long reviewCount
) {}
~~~

Khai báo result set mapping trên một managed entity (ví dụ Book):

~~~java
@SqlResultSetMapping(
    name = "BookSummaryMapping",
    classes = @ConstructorResult(
        targetClass = BookSummary.class,
        columns = {
            @ColumnResult(name = "book_id", type = Long.class),
            @ColumnResult(name = "title", type = String.class),
            @ColumnResult(name = "review_count", type = Long.class)
        }
    )
)
@Entity
@Table(name = "book")
public class Book {
    @Id
    private Long id;
    // Các thuộc tính khác...
}
~~~

SQL cần alias khớp mapping:

~~~sql
SELECT
    b.id AS book_id,
    b.book_title AS title,
    COUNT(r.id) AS review_count
FROM book b
LEFT JOIN review r ON r.book_id = b.id
GROUP BY b.id, b.book_title
ORDER BY b.id
~~~

Thực thi:

~~~java
Query query = entityManager.createNativeQuery(
    """
    SELECT
        b.id AS book_id,
        b.book_title AS title,
        COUNT(r.id) AS review_count
    FROM book b
    LEFT JOIN review r ON r.book_id = b.id
    GROUP BY b.id, b.book_title
    ORDER BY b.id
    """,
    "BookSummaryMapping"
);

List<?> rows = query.getResultList();

for (Object row : rows) {
    BookSummary summary = (BookSummary) row;
}
~~~

Lưu ý:

- Thứ tự và kiểu `@ColumnResult` phải tương thích constructor/record canonical constructor.
- `@SqlResultSetMapping` là JPA API, nhưng việc xử lý conversion của `COUNT` sang `Long` cần kiểm tra provider/dialect.
- SQL alias phải khớp với `@ColumnResult(name=...)`.
- DTO result **không phải managed entity** và không được dirty checking như entity.

## 21. Named native query để tái sử dụng SQL

JPA cho phép khai báo `@NamedNativeQuery`:

~~~java
@NamedNativeQuery(
    name = "Book.findPublishedNative",
    query = """
        SELECT b.*
        FROM book b
        WHERE b.status = :status
        ORDER BY b.id
        """,
    resultClass = Book.class
)
@Entity
@Table(name = "book")
public class Book {
    @Id
    private Long id;
    // ...
}
~~~

Thực thi với Hibernate:

~~~java
List<?> books = entityManager.createNamedQuery(
    "Book.findPublishedNative"
)
.setParameter("status", "PUBLISHED")
.getResultList();
~~~

**Cảnh báo portability:** Named native SQL có `:status` là dạng Hibernate hỗ trợ; một provider khác có thể chỉ hỗ trợ positional markers. Nếu ứng dụng phải chuyển JPA provider, xác minh parameter syntax và kết quả mapping.

Named native query giúp tổ chức truy vấn cố định, tránh lặp SQL string và có thể được provider kiểm tra metadata ở giai đoạn khởi tạo. Nó không tự thay thế việc kiểm thử SQL theo dialect/schema thực tế.

## 22. Native query qua Hibernate Session API

Nếu cần tính năng riêng của Hibernate:

~~~java
Session session = entityManager.unwrap(Session.class);

NativeQuery<Book> query = session.createNativeQuery(
    "SELECT b.* FROM book b WHERE b.status = :status",
    Book.class
);

query.setParameter("status", "PUBLISHED");

List<Book> books = query.getResultList();
~~~

Những khả năng Hibernate-specific thường dùng:

| API/cơ chế | Công dụng |
|---|---|
| `Session.createNativeQuery(sql, Book.class)` | Tạo native query có entity result class. |
| `NativeQuery.addScalar(...)` | Mô tả cột scalar/Java type rõ ràng. |
| `NativeQuery.setParameterList(...)` | Bind một collection cho IN predicate. |
| `NativeQuery.addSynchronizedEntityClass(...)` | Khai báo entity query spaces nhằm hỗ trợ auto-flush và cache synchronization. |
| `NativeQuery.addSynchronizedQuerySpace(...)` | Khai báo bảng/query space SQL ảnh hưởng đến query. |
| `Query.setTupleTransformer(...)` | Chuyển tuple thành đối tượng khác theo API Hibernate phù hợp. |

Tên method/overload có thể khác giữa Hibernate 5 và 6, nhất là API type mapping, transformer và result mapping. Nếu ứng dụng muốn chỉ phụ thuộc JPA, ưu tiên `EntityManager` và `@SqlResultSetMapping` khi chúng đáp ứng được nhu cầu.

## 23. Native INSERT, UPDATE, DELETE

Native DML thường dùng `executeUpdate()`:

~~~java
int changed = entityManager.createNativeQuery(
    """
    UPDATE book
    SET unit_price = :newPrice
    WHERE id = :bookId
    """
)
.setParameter("newPrice", new BigDecimal("180000"))
.setParameter("bookId", 42L)
.executeUpdate();
~~~

Lệnh phải chạy trong transaction khi là thao tác ghi:

~~~java
@Transactional
public int updateBookPrice(Long id, BigDecimal price) {
    return entityManager.createNativeQuery(
        """
        UPDATE book
        SET unit_price = :price
        WHERE id = :id
        """
    )
    .setParameter("price", price)
    .setParameter("id", id)
    .executeUpdate();
}
~~~

`@Transactional` ở đây là ví dụ Spring transaction management. Trong môi trường application-managed `EntityManager`, dùng `EntityTransaction.begin()/commit()` tương ứng; trong JTA, dùng transaction container.

### INSERT

~~~java
int inserted = entityManager.createNativeQuery(
    """
    INSERT INTO book (
        id, isbn, book_title, unit_price, status
    )
    VALUES (
        :id, :isbn, :title, :price, :status
    )
    """
)
.setParameter("id", 99L)
.setParameter("isbn", "978-1-0000-0000-1")
.setParameter("title", "Hibernate Native SQL")
.setParameter("price", new BigDecimal("150000"))
.setParameter("status", "DRAFT")
.executeUpdate();
~~~

Ví dụ dùng ID tường minh để tập trung vào binding. Trong ứng dụng thật, phải tuân theo ID generation, constraints và schema DB. Không tự chèn ID vào cột identity nếu schema không cho phép.

### DELETE

~~~java
int deleted = entityManager.createNativeQuery(
    "DELETE FROM book WHERE id = :id"
)
.setParameter("id", 42L)
.executeUpdate();
~~~

Đừng giả định `executeUpdate()` luôn trả đúng số entity objects bị ảnh hưởng. JDBC row count phụ thuộc statement/driver; cascade deletes qua FK/triggers thường không được tính như những row root do câu DML trực tiếp ảnh hưởng.

## 24. SQL RETURNING, UPSERT, CTE: các tính năng DB riêng

PostgreSQL hỗ trợ:

~~~sql
UPDATE book
SET unit_price = :price
WHERE id = :id
RETURNING id, unit_price
~~~

Vì `RETURNING` trả result set, cách gọi `getResultList()` hay provider-specific mutation API cần tương thích Hibernate version/dialect. Đừng mặc định mọi database hỗ trợ `RETURNING` hoặc mọi JPA method xử lý giống SELECT bình thường.

Ví dụ PostgreSQL UPSERT:

~~~sql
INSERT INTO book (id, isbn, book_title, unit_price, status)
VALUES (:id, :isbn, :title, :price, :status)
ON CONFLICT (isbn)
DO UPDATE SET
    book_title = EXCLUDED.book_title,
    unit_price = EXCLUDED.unit_price
~~~

Ví dụ trên minh họa tính năng database riêng; nếu code hỗ trợ cả MySQL/SQL Server/Oracle, cần chiến lược SQL khác. Dùng native query khi lợi ích kiểm soát DB feature lớn hơn chi phí giảm portability.

## 25. Native DML không chạy entity lifecycle callbacks

Lệnh:

~~~sql
UPDATE book SET unit_price = 180000 WHERE id = 42
~~~

không tương đương với:

~~~java
Book book = entityManager.find(Book.class, 42L);
book.setPrice(new BigDecimal("180000"));
~~~

Khi thay đổi managed entity, Hibernate dirty checking và entity lifecycle có thể chạy theo mapping. Native UPDATE đi **thẳng qua SQL**, không gọi setter/domain methods, không tự chạy `@PreUpdate` hay entity listeners cho từng row. Native DELETE cũng không truyền `CascadeType.REMOVE` của JPA đến từng entity.

Nếu DB có `ON DELETE CASCADE`, database vẫn có thể xóa child rows theo FK action, nhưng Java callbacks trên child không chạy do DB cascade.

Nếu entity dùng optimistic locking (`@Version`), native UPDATE không tự động thực thi version check/increment giống entity update của Hibernate. Muốn bảo vệ chống lost updates, phải tự thêm điều kiện `WHERE version = :expectedVersion` và cập nhật version một cách nhất quán, hoặc dùng ORM lifecycle. Đừng bỏ qua version column chỉ vì dùng native SQL.

## 26. Persistence context có thể stale sau native DML

Giả sử:

~~~java
Book book = entityManager.find(Book.class, 42L);

entityManager.createNativeQuery(
    "UPDATE book SET unit_price = :price WHERE id = :id"
)
.setParameter("price", new BigDecimal("250000"))
.setParameter("id", 42L)
.executeUpdate();

System.out.println(book.getPrice());
~~~

`book` vẫn có thể giữ giá **trước** native UPDATE, vì SQL đã thay đổi DB row nhưng Hibernate không tự đồng bộ từng managed entity đã nằm trong first-level cache.

Các lựa chọn:

- `entityManager.refresh(book)` để tải lại state của entity còn tồn tại.
- `entityManager.detach(book)` nếu không cần quản lý instance đó.
- `entityManager.clear()` để bỏ toàn bộ managed entities (cẩn trọng với pending changes).
- Kết thúc transaction/`EntityManager` và mở unit of work mới.

### Cẩn thận với pending changes

Nếu trước native SQL còn thay đổi managed entities chưa flush, thứ tự thực thi có thể gây kết quả khó đoán. Có thể gọi `entityManager.flush()` ở thời điểm phù hợp trước native DML, khi transaction đang hoạt động, để đưa pending SQL vào DB; sau đó mới chạy native DML và quyết định refresh/clear.

`clear()` không tự flush; nó có thể bỏ những thay đổi chưa được gửi. Đừng dùng `clear()` vô điều kiện trong service khi có nhiều entity đang được sửa.

## 27. Auto-flush và synchronized query spaces

Native SQL là chuỗi văn bản; Hibernate không luôn suy luận chính xác các table/query spaces liên quan, nhất là với SQL phức tạp. Cơ chế auto-flush khi chạy native query còn phụ thuộc bootstrap qua `EntityManager` hay `Session`, flush mode, Hibernate version và khai báo query synchronization.

Với Hibernate API có thể khai báo entity/table liên quan:

~~~java
NativeQuery<Book> query = session.createNativeQuery(
    "SELECT b.* FROM book b WHERE b.id = :id",
    Book.class
);

query.addSynchronizedEntityClass(Book.class);
query.setParameter("id", 42L);

Book result = query.getSingleResult();
~~~

Hoặc query space:

~~~java
query.addSynchronizedQuerySpace("book");
~~~

Tác dụng khái niệm:

- Cung cấp thông tin bảng/entity được query truy cập.
- Giúp Hibernate xác định lúc nào pending changes cần auto-flush trước query.
- Hỗ trợ cơ chế query cache invalidation/synchronization khi cấu hình phù hợp.

Không coi việc khai báo query spaces là lời hứa rằng Hibernate sẽ tự cập nhật mọi managed object sau native UPDATE. Auto-flush **trước** query và làm mới first-level cache **sau** native DML là hai việc khác nhau.

## 28. Second-level cache và query cache

Native UPDATE/DELETE không đi qua vòng đời từng entity. Nếu có Hibernate second-level cache, entity/collection cache entries có thể cần được invalidate/evict theo cơ chế Hibernate hoặc thủ công, nhất là khi SQL do service khác/JDBC ngoài Hibernate thực hiện.

- Với native SQL chạy qua Hibernate, Hibernate có thể invalidates cache regions dựa vào synchronized query spaces/cấu hình.
- Nếu query không khai báo rõ affected tables, invalidation có thể rộng hoặc không theo kỳ vọng của ứng dụng, tùy version.
- Với SQL chạy **ngoài Hibernate**, database không biết cache region của Hibernate và không tự thông báo các ứng dụng.
- First-level cache của `EntityManager` khác second-level cache; invalidating L2 không tự sửa state của object đã load trong một persistence context khác.

Khi correctness phụ thuộc cache, test native DML với L1/L2/query cache bật trong cấu hình giống production. Không dựa vào một ví dụ nhỏ để kết luận cache đã luôn được đồng bộ.

## 29. Phân trang native query

Có thể dùng API thay vì tự nối `LIMIT`/`OFFSET`:

~~~java
List<?> rows = entityManager.createNativeQuery(
    """
    SELECT id, book_title, unit_price
    FROM book
    WHERE status = :status
    ORDER BY unit_price ASC, id ASC
    """
)
.setParameter("status", "PUBLISHED")
.setFirstResult(20)
.setMaxResults(10)
.getResultList();
~~~

Hibernate chuyển pagination sang cú pháp DB dialect khi được hỗ trợ. Một số native SQL phức tạp hoặc statement đặc biệt có thể không hỗ trợ cách rewrite pagination; kiểm tra SQL thật.

**Luôn có ORDER BY ổn định** khi phân trang. `ORDER BY unit_price ASC` riêng lẻ chưa đủ nếu nhiều sách cùng giá. Thêm `id` làm khóa phân định duy nhất để thứ tự không mơ hồ.

### Offset và keyset

Với danh sách lớn, OFFSET sâu có thể tốn chi phí bỏ qua rows. Keyset pagination có thể dùng predicate:

~~~sql
SELECT id, book_title, unit_price
FROM book
WHERE status = :status
  AND (
      unit_price > :lastPrice
      OR (unit_price = :lastPrice AND id > :lastId)
  )
ORDER BY unit_price ASC, id ASC
~~~

Trường hợp này giả định `unit_price` không NULL, và cursor chứa giá/ID của row cuối trang trước. Nếu các sort keys có NULL hoặc người dùng đổi thứ tự trong khi phân trang, cần thiết kế cursor/predicate phù hợp.

## 30. Native SQL với JOIN, aggregate và subquery

Một truy vấn report thường cần SQL mạnh hơn entity query đơn giản:

~~~sql
SELECT
    a.id AS author_id,
    a.full_name AS author_name,
    COUNT(b.id) AS book_count,
    COALESCE(SUM(b.unit_price), 0) AS total_price
FROM author a
LEFT JOIN book b
    ON b.author_id = a.id
   AND b.status = :status
GROUP BY a.id, a.full_name
HAVING COUNT(b.id) >= :minimumBooks
ORDER BY book_count DESC, a.id ASC
~~~

Điều kiện `b.status = :status` đặt trong `ON` để vẫn giữ author không có book khớp trước khi áp dụng HAVING. Nếu đưa điều kiện đó vào `WHERE`, LEFT JOIN có thể biến thành lọc loại tác giả không có book tương ứng.

Với report, DTO/scalar result mapping thường phù hợp hơn map toàn bộ hàng tổng hợp về một entity. Đặc biệt, `COUNT`/`SUM` có kiểu JDBC và null semantics cần được xử lý rõ.

## 31. PostgreSQL casts và dấu hai chấm trong SQL

Một số database có cú pháp đặc biệt như PostgreSQL cast:

~~~sql
SELECT :value::date
~~~

Hibernate native named-parameter parser cũng dùng dấu `:`; tùy version/parser, cú pháp `::` sát parameter có thể gây nhầm lẫn. Cách rõ hơn:

~~~sql
SELECT CAST(:value AS DATE)
~~~

Tương tự, một số toán tử JSON/array của PostgreSQL dùng dấu `?`, `?|` hoặc `?&` có thể xung đột với cách parser nhận positional placeholder. Nếu truy vấn có DB-specific operators, kiểm tra Hibernate dialect/parser và cân nhắc cú pháp hàm SQL tương đương được hỗ trợ.

Không tự escape dấu hai chấm hoặc dấu hỏi theo một quy tắc chung chưa được xác nhận; kỹ thuật escape/parser thay đổi theo Hibernate version và dialect.

## 32. Native SQL và converter, UUID, JSON, LOB

Trong HQL, Hibernate có metadata thuộc tính entity để suy luận JDBC mapping. Với native SQL:

- UUID có thể được lưu bằng kiểu `uuid`, `binary(16)`, `char(36)` hoặc loại khác.
- JSON có thể là `jsonb`, `json`, CLOB/VARCHAR hoặc custom type.
- Enum có thể là string, integer hoặc native enum DB.
- LOB có thể yêu cầu stream/driver-specific binding.
- AttributeConverter có thể không tự được áp dụng cho parameter của một scalar native SQL không gắn với attribute mapping.

Nếu `setParameter("value", object)` gây lỗi suy luận type, cần chọn đúng Hibernate type/JDBC type hoặc chuyển sang representation được schema mong đợi. Không nên sửa bằng cách `toString()` mọi thứ, vì có thể mất format, timezone hoặc gây lỗi với byte arrays.

Native result mapping cho JSON/custom columns cũng cần kiểm tra các API Hibernate tương ứng; đôi khi nên trả scalar `String`/`PGobject` hoặc dùng entity attribute mapping có custom type phù hợp.

## 33. Native query trong Spring Data JPA

Spring Data JPA cho phép:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {

    @Query(
        value = """
            SELECT b.*
            FROM book b
            WHERE b.status = :status
            ORDER BY b.id
            """,
        nativeQuery = true
    )
    List<Book> findByStatusNative(@Param("status") String status);
}
~~~

Ở đây `nativeQuery = true` yêu cầu SQL gốc; câu query dùng bảng/cột vật lý. Named parameter trong Spring Data repository được bind qua Spring Data/Hibernate integration; tính portable vẫn phụ thuộc provider.

Native DML:

~~~java
@Modifying
@Query(
    value = """
        UPDATE book
        SET unit_price = :price
        WHERE id = :id
        """,
    nativeQuery = true
)
int updatePriceNative(
    @Param("id") Long id,
    @Param("price") BigDecimal price
);
~~~

Gọi repository mutation method trong transaction thích hợp. `@Modifying` báo đây là modifying query, nhưng không tự khiến entity callbacks hoặc dirty checking chạy cho từng row. Với persistence context đang chứa Book tương ứng, vẫn có stale state; Spring Data có tùy chọn flush/clear context cho modifying queries, nhưng phải hiểu pending changes trước khi bật.

## 34. Transaction, isolation và khóa

Native query không tự tạo transaction boundary. SELECT có thể được thực thi trong bối cảnh transaction hoặc ngoài transaction tùy framework; UPDATE/DELETE/INSERT thường cần transaction đang hoạt động.

Ví dụ:

~~~java
@Transactional
public void increasePrice(Long id, BigDecimal increment) {
    entityManager.createNativeQuery(
        """
        UPDATE book
        SET unit_price = unit_price + :increment
        WHERE id = :id
        """
    )
    .setParameter("increment", increment)
    .setParameter("id", id)
    .executeUpdate();
}
~~~

Thao tác cộng giá trực tiếp ở DB tránh read-modify-write trong Java cho một cột, nhưng không tự giải quyết mọi quy tắc nghiệp vụ và concurrency. Nếu cần giới hạn giá hay version check, thêm WHERE phù hợp hoặc dùng cơ chế optimistic locking.

`SELECT ... FOR UPDATE` là cú pháp SQL khóa hàng ở nhiều DB, nhưng chi tiết, quyền, isolation và hành vi khi kết hợp JOIN/subquery khác nhau. Chỉ dùng khi có chiến lược transaction rõ ràng; đừng giữ transaction dài để chờ remote HTTP call.

## 35. Mẫu thực hành: filter động an toàn

Giả sử API có `status`, `minPrice`, `maxPrice` và keyword. Thay vì tạo một SQL với nhiều parameter nullable:

~~~sql
WHERE (:status IS NULL OR status = :status)
~~~

có thể chỉ thêm điều kiện khi có giá trị:

~~~java
public List<?> searchNative(
        String status,
        BigDecimal minPrice,
        BigDecimal maxPrice,
        String keyword,
        int limit) {

    StringBuilder sql = new StringBuilder("""
        SELECT b.id, b.book_title, b.unit_price
        FROM book b
        WHERE 1 = 1
        """);

    if (status != null) {
        sql.append(" AND b.status = :status");
    }
    if (minPrice != null) {
        sql.append(" AND b.unit_price >= :minPrice");
    }
    if (maxPrice != null) {
        sql.append(" AND b.unit_price <= :maxPrice");
    }
    if (keyword != null && !keyword.isBlank()) {
        sql.append(" AND LOWER(b.book_title) LIKE :pattern ESCAPE '!'");
    }

    sql.append(" ORDER BY b.unit_price ASC, b.id ASC");

    Query q = entityManager.createNativeQuery(sql.toString());

    if (status != null) {
        q.setParameter("status", status);
    }
    if (minPrice != null) {
        q.setParameter("minPrice", minPrice);
    }
    if (maxPrice != null) {
        q.setParameter("maxPrice", maxPrice);
    }
    if (keyword != null && !keyword.isBlank()) {
        q.setParameter(
            "pattern",
            containsLiteralPattern(keyword.toLowerCase(Locale.ROOT))
        );
    }

    return q
        .setMaxResults(Math.max(1, Math.min(limit, 100)))
        .getResultList();
}
~~~

Hàm `containsLiteralPattern` đã được định nghĩa ở phần LIKE/ESCAPE. Ở đây SQL fragment được nối vào query đều là **hằng số do lập trình viên kiểm soát**, còn user values luôn được bind. Query có ORDER BY với tie-breaker, giới hạn số kết quả và không sinh predicate khi filter null.

Trong ứng dụng thật, chuẩn hóa keyword cần cân nhắc locale/collation của database. `Locale.ROOT` chỉ là quy ước normalize phía Java; logic so khớp case/accents của DB có thể không hoàn toàn tương đương.

## 36. Mapping theo JPA và Hibernate: chọn cách nào?

| Kết quả mong muốn | API thường chọn |
|---|---|
| Một giá trị scalar như COUNT | `EntityManager.createNativeQuery(sql)` + `Number`, hoặc Hibernate `addScalar`. |
| Vài cột không có lifecycle entity | `Object[]` cho demo ngắn; `@SqlResultSetMapping`/DTO cho code lớn. |
| Một entity đầy đủ | `createNativeQuery(sql, Book.class)`; bảo đảm đủ cột. |
| Typed entity result với Hibernate | `Session.createNativeQuery(sql, Book.class)`. |
| Bind collection cho IN | Hibernate `NativeQuery.setParameterList`. |
| Reusable SQL được đặt tên | `@NamedNativeQuery` và named query APIs. |
| Native UPDATE/DELETE | `executeUpdate` trong transaction; xử lý cache/context. |
| Tính năng SQL rất riêng của DB | Native SQL, với integration test theo DBMS mục tiêu. |

Nên ưu tiên HQL/JPQL nếu truy vấn hoàn toàn diễn tả được theo entity model, vì giảm coupling với schema vật lý. Native SQL phù hợp khi tính năng SQL DBMS mang lại lợi ích rõ ràng hoặc yêu cầu tối ưu đã được đo đạc.

## 37. Các lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `SQLGrammarException` / syntax error | Dùng tên field Java trong native SQL, hoặc cú pháp DB khác dialect. | Kiểm tra tên bảng/cột vật lý và SQL chạy được trên DB thật. |
| Named parameter not bound | Quên gọi `setParameter` hoặc sai tên. | Đối chiếu placeholder và binding. |
| Could not determine parameter type | NULL/custom type thiếu type metadata. | Bind kiểu tường minh hoặc chỉ tạo predicate khi có giá trị. |
| Column not found khi map entity | SELECT thiếu cột/alias Hibernate cần. | SELECT đủ cột hoặc chuyển sang scalar/DTO. |
| `ClassCastException` | Giả định kiểu scalar sai. | Xem JDBC type, dùng `Number`/`addScalar`/result mapping. |
| IN list rỗng lỗi | Hibernate/DB xử lý empty collection khác nhau. | Xác định semantics trước khi query; bỏ/đổi predicate. |
| Query chậm | Hàm trên cột, thiếu index, IN lớn, sort/offset sâu. | EXPLAIN/ANALYZE và điều chỉnh schema/query. |
| Giá entity cũ sau native UPDATE | Persistence context chưa được đồng bộ. | `refresh`/`clear` theo phạm vi sau khi xử lý pending changes. |
| Native DELETE không gọi `@PreRemove` | Native DML bỏ qua entity lifecycle. | ORM remove nếu cần callback hoặc thiết kế audit ở DB/outbox. |
| SQL injection khi dynamic sort | Nối tên cột/hướng sort từ raw user input. | Allowlist identifiers và bind values. |
| Sai encoding/Unicode/collation | Driver, schema hoặc collation khác yêu cầu. | Kiểm tra DB encoding, parameter binding và test dữ liệu thực tế. |
| Query chạy PostgreSQL nhưng lỗi MySQL | SQL chứa `::`, `RETURNING`, `ON CONFLICT` hoặc JSON syntax riêng. | Tách dialect-specific SQL hoặc dùng tính năng portable. |

## 38. Debug SQL và parameter binding

Khi truy vấn native có kết quả sai, nên kiểm tra:

1. SQL string thực tế sau khi application ghép các fragment **cố định**.
2. Tên bảng/cột/alias đúng với schema deploy.
3. Named/positional placeholders và tất cả `setParameter`.
4. Java type/SQL JDBC type và null handling.
5. Transaction, flush order và isolation.
6. Entity result mapping, số cột/alias/constructor DTO.
7. ORDER BY, LIMIT/OFFSET và số rows trả về.
8. Các bảng/query spaces được query tác động và cache invalidation.
9. SQL execution plan với dữ liệu đại diện.

Với Hibernate 6 trong Spring Boot, có thể dùng logging:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger name có thể khác theo Hibernate version. Bind logging có thể chứa dữ liệu nhạy cảm; không bật tùy tiện trên production. Thông số thực thi thực tế nên đo bằng database EXPLAIN/ANALYZE hoặc công cụ giám sát phù hợp thay vì chỉ đếm số dòng log.

## 39. Kiểm thử native query trên database mục tiêu

Native SQL phụ thuộc schema và dialect nên integration test đặc biệt quan trọng. Với PostgreSQL production, nên dùng PostgreSQL test database (có thể qua Testcontainers), không chỉ dựa vào H2 giả lập.

Tối thiểu nên kiểm thử:

- SELECT scalar một cột và nhiều cột.
- Entity mapping có đủ cột primary key và attribute fields.
- DTO constructor mapping, đặc biệt `COUNT`, `SUM` và alias.
- Named/positional binding, NULL và collection IN.
- LIKE với dấu `%` và `_` literal.
- Cột enum, decimal, timestamp và timezone.
- ORDER BY ổn định, giới hạn số row và pagination.
- Native UPDATE/DELETE cùng transaction rollback và persistence context.
- DB-specific SQL features, casts, JSON/UUID nếu có.
- Hành vi cache khi bật L2 cache và khi có nhiều persistence contexts.

### Ví dụ test kết quả SELECT

~~~java
@Test
void nativeQueryFiltersByStatus() {
    List<?> rows = entityManager.createNativeQuery(
        """
        SELECT id
        FROM book
        WHERE status = :status
        ORDER BY id ASC
        """
    )
    .setParameter("status", "PUBLISHED")
    .getResultList();

    // Dữ liệu fixture kiểm soát expected IDs.
    // assertEquals(...) tùy framework test.
}
~~~

Kiểm thử bằng dữ liệu fixture có những giá trị đối nghịch nhau: trạng thái khác nhau, ID không liên tiếp, NULL, tiêu đề chứa wildcard và nhiều rows có cùng sort key. Điều này giúp phát hiện các query cho kết quả đúng tình cờ trên dữ liệu quá đơn giản.

## 40. Bài tập thực hành

1. Tạo native query trả toàn bộ sách đã xuất bản có giá trên 100.000 và sort theo giá, ID.
2. Viết một query dùng named parameters và một query tương đương dùng positional parameters.
3. Trả một cột `isbn`, sau đó trả ba cột `id`/`title`/`price` và đọc kết quả.
4. Dùng `createNativeQuery(sql, Book.class)` để lấy danh sách managed Book.
5. Viết DTO cho thống kê số lượng sách theo tác giả dùng `@SqlResultSetMapping`.
6. Lấy sách theo danh sách IDs bằng `NativeQuery.setParameterList`; xác định xử lý list rỗng.
7. Tìm title chứa literal `%` hoặc `_` mà không xem đó là wildcard.
8. Viết dynamic ORDER BY chỉ cho phép `title`, `price`, `date`.
9. Viết một native UPDATE giá rồi quan sát Book entity đã load trong cùng persistence context.
10. Viết một UPDATE có version check để bảo vệ optimistic concurrency.
11. Thực hiện native DELETE trong transaction rồi rollback, xác nhận row vẫn tồn tại.
12. So sánh SQL plan của điều kiện `LOWER(book_title)` với predicate trực tiếp và index tương ứng.
13. Thử native query chứa PostgreSQL `CAST`, `RETURNING` hoặc `ON CONFLICT` trên chính PostgreSQL test database.
14. Bật logging bind parameters trong môi trường test và kiểm tra giá trị bind có đúng type.

### Gợi ý bài version check

~~~sql
UPDATE book
SET unit_price = :newPrice,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
~~~

Giả sử schema thật có cột `version` và mapping optimistic locking phù hợp. Nếu `executeUpdate()` trả 0, có thể row không tồn tại hoặc version đã đổi; application phải xử lý như một optimistic concurrency conflict thay vì giả định update đã thành công.

## 41. Checklist trước khi dùng native query trong production

**SQL và schema**

- SQL dùng đúng tên bảng, cột, alias thực tế.
- Chỉ dùng DB-specific syntax khi hệ thống chấp nhận phụ thuộc dialect.
- Query không SELECT dư dữ liệu nhạy cảm hoặc cột lớn khi không cần.
- Index, JOIN cardinality và execution plan được cân nhắc theo workload.

**Parameters và bảo mật**

- Tất cả user values được bind; không nối raw values vào SQL.
- Dynamic table/column/sort được chọn từ allowlist.
- LIKE literal input được escape nếu có wildcard.
- Null/empty collection và type binding có semantics rõ ràng.
- Có giới hạn số rows, truy vấn và phân trang phù hợp.

**Kết quả và lifecycle**

- Scalar/DTO/entity mapping được xác định rõ.
- Entity result có đủ columns và primary key.
- Native DML chạy trong transaction đúng.
- Persistence context được refresh/clear/detach khi cần.
- Optimistic locking, callbacks và cache invalidation không bị bỏ quên.
- Các đường xóa ngoài ORM và foreign key constraints được tính đến.

**Kiểm thử**

- Kiểm thử bằng database dialect giống production.
- Kiểm thử NULL, unicode, enum, decimal, date/time, list rỗng.
- Kiểm thử thứ tự ổn định và pagination.
- Kiểm thử rollback, stale entity và concurrency khi quan trọng.
- Logging bind parameters không làm lộ dữ liệu nhạy cảm.

## 42. Tổng kết

~~~mermaid
flowchart TD
    A["Cần truy vấn dữ liệu"] --> B{"HQL/JPQL biểu diễn đủ?"}
    B -- "Có" --> C["Ưu tiên HQL/JPQL"]
    B -- "Không / cần SQL DBMS" --> D["Tạo native query"]
    D --> E["Chọn EntityManager hoặc Session"]
    E --> F["Định nghĩa SQL với tên bảng/cột"]
    F --> G["Bind parameter an toàn"]
    G --> H{"Kết quả là gì?"}
    H -- "Scalar" --> I["Object / Number / addScalar"]
    H -- "Entity" --> J["Result class đủ cột"]
    H -- "DTO" --> K["SqlResultSetMapping"]
    H -- "DML" --> L["executeUpdate trong transaction"]
    I --> M["Kiểm thử trên DB mục tiêu"]
    J --> M
    K --> M
    L --> N["Đồng bộ context/cache nếu cần"]
    N --> M
~~~

**Native query** là công cụ để dùng SQL thật khi cần kiểm soát cú pháp hoặc khai thác tính năng riêng của database. Trình tự đúng là **viết SQL theo schema vật lý → tạo query → bind dữ liệu bằng parameter → chọn result mapping phù hợp → thực thi trong transaction cần thiết → xử lý persistence context/cache → kiểm thử trên DB thực tế**.

Điểm quan trọng nhất không phải thuộc lòng `createNativeQuery()`, mà là phân biệt được **value binding** với dynamic SQL identifiers, **scalar result** với **managed entity**, và **native DML** với **entity lifecycle operations**. Khi nắm các ranh giới đó, bạn có thể sử dụng SQL gốc linh hoạt mà vẫn giữ được an toàn, tính nhất quán và khả năng bảo trì trong ứng dụng Hibernate.
