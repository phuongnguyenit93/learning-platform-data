# Tìm theo property trực tiếp và đường dẫn qua relationship

Spring Data Neo4j cho phép khai báo truy vấn trong repository bằng tên phương thức. Thay vì tự viết Cypher cho mọi bộ lọc, ta đặt tên phương thức theo property của entity và các điều kiện cần áp dụng. Spring Data phân tích tên đó, kiểm tra đường dẫn property trong mô hình Java rồi tạo truy vấn Cypher phù hợp.

Một truy vấn có thể lọc trực tiếp property của node, chẳng hạn tìm sách theo tiêu đề. Nó cũng có thể đi qua relationship đã ánh xạ để lọc theo property của node liên quan, chẳng hạn tìm sách theo tên tác giả. Khả năng này giúp repository gọn và dễ đọc khi điều kiện truy vấn bám sát mô hình entity. Khi cần đường đi đồ thị tùy ý, lọc thuộc tính relationship phức tạp hoặc phép tổng hợp đặc biệt, nên dùng `@Query` với Cypher tường minh.

## 1. Derived query hoạt động như thế nào?

Một derived query là truy vấn được suy ra từ tên phương thức repository. Phần tên phương thức có hai phần chính:

- **Subject:** cho biết loại thao tác và kết quả, thường bắt đầu bằng `find`, `read`, `get`, `query`, `exists`, `count`, `delete` hoặc `remove`.
- **Predicate:** bắt đầu sau từ `By`, mô tả property cần lọc và các toán tử nối điều kiện.

Ví dụ:

```java
List<Book> findByTitle(String title);
```

`find` là subject; `ByTitle` cho biết lọc theo property `title`. Giá trị truyền vào tham số được gắn vào điều kiện truy vấn. Về mặt ý nghĩa, truy vấn tìm các node `Book` có `title` bằng giá trị được cung cấp.

Một số dạng subject thường gặp:

| Subject | Ý nghĩa | Kiểu kết quả thường dùng |
|---|---|---|
| `find…By` | Tìm bản ghi phù hợp | `Optional<T>`, `T`, `List<T>` |
| `exists…By` | Kiểm tra có bản ghi phù hợp | `boolean` |
| `count…By` | Đếm số bản ghi phù hợp | `long` hoặc kiểu số phù hợp |
| `delete…By` / `remove…By` | Xóa bản ghi phù hợp | `void` hoặc số lượng bị xóa, tùy khai báo và hỗ trợ của store |

Từ `By` đầu tiên là ranh giới giữa subject và predicate. Các từ như `Distinct`, `Top` hoặc `First` có thể bổ sung cách giới hạn kết quả trong subject. Khả năng cụ thể phụ thuộc vào phiên bản Spring Data Neo4j và kiểu truy vấn được hỗ trợ.

## 2. Khai báo mô hình ví dụ

Ta dùng hai node `Book` và `Author`. Một cuốn sách có một tác giả chính trong ví dụ này. Relationship đi từ `Book` tới `Author` theo kiểu `WRITTEN_BY`.

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Author")
public class Author {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public Long getId() { return id; }
    public String getName() { return name; }
}
```

```java
import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Book")
public class Book {
    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private Integer publishedYear;

    @Relationship(
        type = "WRITTEN_BY",
        direction = Relationship.Direction.OUTGOING
    )
    private Author author;

    protected Book() {
    }

    public Book(String title, Integer publishedYear, Author author) {
        this.title = title;
        this.publishedYear = publishedYear;
        this.author = author;
    }

    public Long getId() { return id; }
    public String getTitle() { return title; }
    public Integer getPublishedYear() { return publishedYear; }
    public Author getAuthor() { return author; }
}
```

Các lớp minh họa có thể được đặt trong hai file Java riêng. `Book.author` là property trong mô hình Java được đánh dấu `@Relationship`; `Author.name` là property của node đích. Khi phân tích derived query, Spring Data dựa vào tên property Java này. Tên relationship trong Neo4j (`WRITTEN_BY`) không phải thành phần cần viết trong tên phương thức repository.

Mô hình tương ứng trong Neo4j:

```text
(:Book {title, publishedYear})-[:WRITTEN_BY]->(:Author {name})
```

## 3. Tìm theo property trực tiếp của node

Repository khai báo các phương thức tìm sách theo thuộc tính trực tiếp của `Book`:

```java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface BookRepository extends Neo4jRepository<Book, Long> {

    Optional<Book> findByTitle(String title);

    List<Book> findByPublishedYear(Integer publishedYear);

    List<Book> findByPublishedYearGreaterThanEqual(Integer year);

    List<Book> findByTitleContaining(String text);
}
```

Ý nghĩa từng phương thức:

- `findByTitle`: so sánh bằng với property `title`.
- `findByPublishedYear`: so sánh bằng với `publishedYear`.
- `findByPublishedYearGreaterThanEqual`: lấy sách có năm xuất bản lớn hơn hoặc bằng tham số.
- `findByTitleContaining`: tìm tiêu đề có chứa chuỗi được truyền vào, nếu toán tử này được hỗ trợ bởi phiên bản/store đang sử dụng.

Các tham số được gắn theo thứ tự xuất hiện của điều kiện trong tên phương thức. Kiểu tham số nên tương thích với kiểu property trong entity. Nếu phương thức trả về `Optional<Book>`, hãy chỉ dùng khi nghiệp vụ bảo đảm kết quả tối đa một bản ghi; nếu có thể có nhiều sách cùng tiêu đề, dùng `List<Book>` hoặc một kiểu collection thích hợp.

Lưu ý về tên dành riêng: `findById`, `existsById` và `deleteById` là các phương thức được kế thừa từ repository cơ sở. Chúng luôn thao tác trên property được đánh dấu `@Id`, kể cả khi entity có một property khác cũng tên `id`. Nếu cần truy vấn property `id` không phải định danh, hãy dùng tên mô tả khác để tránh trùng chữ ký, chẳng hạn `findBookById`.

## 4. Đi qua relationship để lọc property của node liên quan

Giả sử cần tìm tất cả sách do một tác giả có tên xác định viết. `Book` không có property `authorName`; nó có property `author`, mà `author` lại có property `name`.

Repository có thể khai báo:

```java
List<Book> findByAuthorName(String authorName);
```

Spring Data phân tích `AuthorName` thành đường dẫn property:

```text
Book.author.name
```

Đây là property traversal qua relationship đã ánh xạ. Về mặt ý nghĩa, truy vấn tương đương mẫu Cypher sau:

```cypher
MATCH (b:Book)-[:WRITTEN_BY]->(a:Author)
WHERE a.name = $authorName
RETURN b;
```

Cypher thực tế do SDN tạo có thể bao gồm map projection và thông tin phục vụ ánh xạ entity; đoạn trên chỉ minh họa điều kiện và đường đi trong đồ thị.

Ví dụ kết hợp điều kiện trên node gốc và node liên quan:

```java
List<Book> findByAuthorNameAndPublishedYearGreaterThanEqual(
    String authorName,
    Integer year
);
```

Phương thức này lọc `Author.name` và `Book.publishedYear`. Tham số thứ nhất gắn với `author.name`, tham số thứ hai gắn với `publishedYear`.

Có thể biểu diễn đường đi nhiều cấp nếu mô hình Java có các property tương ứng. Ví dụ, nếu `Author` có relationship `address` tới `Address`, có thể khai báo một property path như `authorAddressCity` để đi qua `Book.author.address.city`. Chỉ dùng cách này khi từng đoạn đã được mô hình hóa và ánh xạ trong domain model.

## 5. Dùng dấu gạch dưới để xác định ranh giới đường dẫn

Spring Data phân tích tên property theo camel case. Trình phân tích thường tìm một property khớp toàn bộ tên trước, sau đó mới thử tách thành các đoạn nhỏ hơn. Điều này có thể gây nhầm lẫn nếu entity có cả property trực tiếp và property lồng nhau với tên gần giống nhau.

Ví dụ, nếu `Book` có cả hai property:

```java
private String authorName;
private Author author;
```

Thì `findByAuthorName(...)` có thể được hiểu là property trực tiếp `Book.authorName`, thay vì đường dẫn `Book.author.name`. Để chỉ rõ điểm tách, dùng dấu gạch dưới:

```java
List<Book> findByAuthor_Name(String authorName);
```

Tên này buộc parser đi theo `author` rồi tới `name`. Dấu gạch dưới là ký tự dành riêng để phân tách property path; nên đặt tên field Java theo camel case và tránh dùng dấu gạch dưới trong tên property thông thường.

| Tên phương thức | Đường dẫn được nhắm tới |
|---|---|
| `findByTitle` | `Book.title` |
| `findByAuthorName` | Thường được phân tích thành `Book.author.name` nếu không có property trực tiếp gây xung đột |
| `findByAuthor_Name` | Tường minh: `Book.author.name` |
| `findByAuthorAddressCity` | Có thể thành `Book.author.address.city` nếu các property đó tồn tại |

Khi tên phương thức khó đọc hoặc có khả năng mơ hồ, hãy dùng `_` để làm rõ ranh giới thay vì dựa vào cách parser suy đoán.

## 6. Kết hợp nhiều điều kiện

Các điều kiện có thể nối bằng `And` và `Or`. Ví dụ:

```java
List<Book> findByAuthorNameAndPublishedYearGreaterThanEqual(
    String authorName,
    Integer year
);

List<Book> findByTitleOrPublishedYear(
    String title,
    Integer year
);
```

`And` yêu cầu cả hai điều kiện thỏa mãn; `Or` cho phép một trong các điều kiện thỏa mãn. Hãy đặt tên phương thức theo thứ tự tham số để người đọc dễ kiểm tra điều kiện nào nhận giá trị nào.

Khi biểu thức Boolean có nhiều nhánh và cần nhóm điều kiện rõ ràng, tên phương thức có thể trở nên khó hiểu. Đừng cố mã hóa một biểu thức logic dài vào một tên hàm. Dùng `@Query` và viết Cypher với `WHERE`, dấu ngoặc và tham số đặt tên sẽ dễ kiểm soát hơn.

## 7. Một số toán tử thường dùng

Spring Data cung cấp nhiều keyword cho predicate. Các keyword phổ biến gồm so sánh bằng, lớn hơn/nhỏ hơn, khoảng giá trị, chuỗi bắt đầu/kết thúc/chứa, `In`, `IsNull`, `IsNotNull`, `True`, `False`, `And`, `Or` và sắp xếp `OrderBy`. Tuy nhiên, danh sách chính xác được hỗ trợ phụ thuộc vào datastore và phiên bản Spring Data Neo4j; hãy kiểm tra tài liệu của phiên bản đang dùng trước khi thiết kế API repository.

Ví dụ về cách đặt tên:

| Keyword | Ví dụ phương thức | Ý nghĩa |
|---|---|---|
| So sánh bằng | `findByTitle(String title)` | `title` bằng giá trị tham số |
| Lớn hơn | `findByPublishedYearGreaterThan(Integer year)` | Năm lớn hơn tham số |
| Lớn hơn hoặc bằng | `findByPublishedYearGreaterThanEqual(Integer year)` | Năm lớn hơn hoặc bằng tham số |
| Nhỏ hơn | `findByPublishedYearLessThan(Integer year)` | Năm nhỏ hơn tham số |
| Trong tập | `findByPublishedYearIn(Collection<Integer> years)` | Năm thuộc tập giá trị |
| Bắt đầu bằng | `findByTitleStartingWith(String prefix)` | Tiêu đề bắt đầu bằng chuỗi |
| Chứa chuỗi | `findByTitleContaining(String text)` | Tiêu đề chứa chuỗi |
| Không null | `findByTitleIsNotNull()` | Property có giá trị |
| Sắp xếp tĩnh | `findByAuthorNameOrderByPublishedYearDesc(String name)` | Lọc theo tác giả, sắp xếp năm giảm dần |

Không suy ra rằng mọi keyword của Spring Data Commons đều được SDN hỗ trợ ở mọi phiên bản. Nếu một keyword không được hỗ trợ, repository có thể lỗi khi khởi tạo hoặc truy vấn không có semantics như mong muốn. Hãy kiểm tra tài liệu tham chiếu và tích hợp thử trong phiên bản dependency thực tế.

## 8. Sắp xếp, giới hạn và kiểu trả về

Có thể yêu cầu thứ tự cố định trong tên phương thức:

```java
List<Book> findByAuthorNameOrderByPublishedYearDesc(String authorName);
```

Hoặc nhận `Sort` để chọn thứ tự lúc gọi:

```java
import org.springframework.data.domain.Sort;

List<Book> findByAuthorName(String authorName, Sort sort);
```

Ví dụ gọi:

```java
List<Book> books = bookRepository.findByAuthorName(
    "Nguyen Van An",
    Sort.by(Sort.Direction.DESC, "publishedYear")
);
```

Nếu cần giới hạn số kết quả, có thể dùng subject như `findTop5By...` hoặc `findFirstBy...` khi được hỗ trợ:

```java
List<Book> findTop5ByAuthorNameOrderByPublishedYearDesc(String authorName);
```

Chọn kiểu trả về theo cardinality:

- `Optional<Book>`: kỳ vọng không có hoặc tối đa một kết quả.
- `Book`: kỳ vọng một kết quả; cần xác định cách xử lý khi không có kết quả.
- `List<Book>` hoặc `Set<Book>`: có thể có nhiều kết quả.
- `boolean` cho `exists…By` và kiểu số cho `count…By`.

Nếu kết quả có thể lớn, hãy dùng phân trang hoặc giới hạn phù hợp thay vì luôn tải toàn bộ. Hỗ trợ kiểu trả về và tham số phân trang cần được xác nhận theo phiên bản SDN đang sử dụng.

Với truy vấn lọc theo property của node liên quan, hãy cân nhắc index cho property được dùng thường xuyên. Ví dụ, nếu thường xuyên tìm sách theo tên tác giả:

```cypher
CREATE INDEX author_name_index IF NOT EXISTS
FOR (a:Author) ON (a.name);
```

Index không bảo đảm mọi truy vấn sẽ dùng index; quyết định phụ thuộc vào kế hoạch thực thi và độ chọn lọc của điều kiện. Dùng `EXPLAIN` để xem kế hoạch, hoặc `PROFILE` để chạy truy vấn và đo các operator/DB hits. Kiểm tra truy vấn được SDN sinh trong log hoặc bằng công cụ quan sát phù hợp trước khi tối ưu.

## 9. Lưu ý với relationship tùy chọn và property path

Derived query đi qua property path đã được khai báo trong domain model. Với `Book.author`, nếu node sách không có relationship tới tác giả thì đường dẫn `author.name` không có node đích để thỏa điều kiện tên tác giả; bản ghi đó không được trả về bởi truy vấn lọc theo `author.name`.

Tên property trong phương thức phải khớp tên thuộc tính Java của entity, không phải tên label hoặc tên relationship trong Neo4j. Ví dụ:

```java
@Relationship(type = "WRITTEN_BY", direction = Relationship.Direction.OUTGOING)
private Author author;
```

thì property path dùng `author`, dù relationship trong database có tên `WRITTEN_BY`. Nếu đổi tên field Java từ `author` thành `primaryAuthor`, tên phương thức derived query cũng cần đổi theo property mới.

Property path thích hợp cho quan hệ đã ánh xạ và các đoạn đường đi có cấu trúc rõ ràng. Nó không phải cú pháp để diễn tả mọi traversal của Cypher. Không thể chỉ đặt tên phương thức để yêu cầu một đường đi độ dài tùy ý, tìm đường ngắn nhất hoặc lọc theo nhiều nhánh graph tùy biến.

## 10. Khi nào nên chuyển sang @Query?

Derived query hữu ích khi điều kiện truy vấn đơn giản, ổn định và có thể diễn đạt rõ bằng property path. Dùng Cypher tường minh khi cần:

- Duyệt đường đi có độ dài thay đổi hoặc nhiều loại relationship.
- Lọc theo thuộc tính của relationship hoặc theo tổ hợp node/relationship khó biểu diễn bằng property path.
- Dùng `collect`, `count(DISTINCT ...)`, aggregation, subquery hoặc biểu thức Cypher đặc thù.
- Điều khiển rõ `MATCH`, hướng relationship, `OPTIONAL MATCH`, `WITH` và `RETURN`.
- Trả về projection hoặc cấu trúc kết quả không tương ứng trực tiếp với entity root.

Ví dụ, tìm sách và trả về tên tác giả cùng số lượng sách của tác giả bằng Cypher:

```java
public interface AuthorBookSummary {
    String getAuthorName();
    Long getBookCount();
}
```

```java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (a:Author)<-[:WRITTEN_BY]-(b:Book)
    WHERE a.name = $authorName
    RETURN a.name AS authorName,
           count(b) AS bookCount
    """)
List<AuthorBookSummary> summarizeBooksByAuthor(
    @Param("authorName") String authorName
);
```

Đây là truy vấn tổng hợp trả về projection, phù hợp hơn một derived query trả về toàn bộ `Book`. Tham số được bind qua `$authorName`; không ghép chuỗi đầu vào trực tiếp vào Cypher.

## 11. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository lỗi khi khởi động | Tên phương thức trỏ tới property không tồn tại hoặc đường dẫn không hợp lệ | Đối chiếu từng đoạn với field trong entity và target entity |
| Truy vấn không đi qua relationship như mong muốn | Dùng nhầm tên relationship type thay cho tên property Java | Dùng field được đánh dấu `@Relationship`, ví dụ `author` |
| `findByAuthorName` chọn property sai | Có property trực tiếp `authorName` gây mơ hồ | Dùng `findByAuthor_Name` để chỉ rõ đường dẫn |
| Kết quả trống dù node gốc tồn tại | Node thiếu relationship hoặc node đích thiếu property cần lọc | Kiểm tra relationship và property bằng Cypher |
| Tên phương thức quá dài và khó đọc | Có quá nhiều điều kiện hoặc đường dẫn lồng nhau | Chuyển truy vấn sang `@Query` và đặt tên theo nghiệp vụ |
| Kết quả bị tải quá nhiều | Dùng `List` không giới hạn trên dữ liệu lớn | Dùng `Top`/`First`, `Sort`, phân trang hoặc projection khi phù hợp |
| Không truy vấn được property trên relationship | Đang nhầm property của target node với property của relationship model | Xác minh mapping; dùng `@Query` nếu cần điều kiện Cypher tường minh |

## 12. Quy trình thiết kế derived query

Khi thêm một phương thức repository, thực hiện theo thứ tự:

1. Xác định entity gốc mà repository quản lý.
2. Xác định property trực tiếp hoặc từng đoạn relationship cần đi qua.
3. Đối chiếu đường dẫn với field Java và annotation mapping.
4. Chọn keyword phù hợp với điều kiện và xác nhận keyword được SDN hỗ trợ.
5. Chọn kiểu trả về theo số lượng kết quả có thể có.
6. Nếu đường dẫn có thể mơ hồ, dùng `_` để chỉ rõ ranh giới property.
7. Kiểm tra query bằng integration test và dữ liệu có/không có relationship.
8. Chuyển sang `@Query` nếu tên phương thức trở nên quá phức tạp hoặc không diễn đạt được graph traversal mong muốn.

## 13. Tự kiểm tra

1. Trong `findByTitle`, phần nào là subject và phần nào là predicate?
2. Nếu `Book` có property `author` trỏ tới `Author`, `findByAuthorName` biểu diễn đường dẫn property nào?
3. Vì sao `findByAuthor_Name` hữu ích khi entity có cả `authorName` và `author.name`?
4. Tên phương thức derived query dùng tên Java field hay tên relationship type trong Neo4j?
5. Khi nào nên dùng `Optional<Book>` và khi nào nên dùng `List<Book>`?
6. Vì sao derived query không phù hợp với đường đi Cypher có độ dài tùy ý hoặc phép tổng hợp nhiều nhánh?
7. Nếu repository không trả về sách không có tác giả, bạn sẽ kiểm tra những node và relationship nào trong Neo4j?

## Tài liệu tham khảo

- [Spring Data Neo4j — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Data Neo4j — Repository Query Keywords](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-keywords-reference.html)
- [Spring Data Neo4j — Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html)
