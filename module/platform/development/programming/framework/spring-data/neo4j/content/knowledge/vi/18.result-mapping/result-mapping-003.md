# Thu thập node và relationship bằng COLLECT

Trong Cypher, `collect()` gom các giá trị từ nhiều dòng kết quả thành một danh sách. Với đồ thị Neo4j, giá trị được gom có thể là property, node, relationship, path hoặc map do truy vấn tạo ra. Đây là cách hữu ích để tạo một kết quả tổng hợp cho một node gốc, ví dụ hồ sơ tác giả kèm danh sách sách đã viết và giải thưởng đã nhận.

Khi dùng Spring Data Neo4j (SDN), cần chú ý rằng `collect()` thay đổi hình dạng kết quả: thay vì một dòng cho mỗi relationship, truy vấn có thể trả một dòng chứa các danh sách. Nếu cần ánh xạ danh sách đó thành DTO hoặc cấu trúc đọc riêng, `Neo4jClient` cho phép chuyển từng phần tử trong record. Nếu cần SDN ánh xạ entity graph, hãy trả về đúng các node và relationship mà mapping cần; đừng giả định mọi cột list do `collect()` tạo ra sẽ tự động trở thành thuộc tính `@Relationship` của entity.

## 1. collect() gom dữ liệu theo nhóm

Giả sử một tác giả viết nhiều sách:

~~~text
(Author)-[:WROTE]->(Book)
~~~

Truy vấn cơ bản:

~~~cypher
MATCH (author:Author)-[:WROTE]->(book:Book)
RETURN author.id AS authorId,
       collect(book.title) AS bookTitles
~~~

Cypher trả về một dòng cho mỗi `authorId`, trong đó `bookTitles` là danh sách tên sách của tác giả đó. Những biểu thức không nằm trong hàm tổng hợp, như `author.id`, trở thành khóa nhóm. Nếu truy vấn chỉ trả `collect(book.title)` mà không có biểu thức thường khác, tất cả dòng phù hợp được gom thành một danh sách.

`collect(expression)` bỏ qua giá trị `null`. Nếu không có giá trị nào để gom trong một nhóm tổng hợp, kết quả danh sách là rỗng. Hành vi này hữu ích khi muốn trả danh sách rỗng thay vì một phần tử null.

## 2. Thu thập node và relationship riêng biệt

Có thể gom node đích và relationship thành hai danh sách riêng:

~~~cypher
MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
RETURN author,
       collect(book) AS books,
       collect(written) AS writingRelationships
~~~

Trong kết quả:

- `author` là node gốc.
- `books` là danh sách các node `Book` ở đầu đích.
- `writingRelationships` là danh sách relationship `WROTE`, bao gồm các property trên relationship nếu có.

Nếu có thể tồn tại nhiều relationship cùng kiểu giữa cùng một cặp node, `collect(book)` có thể chứa cùng một node nhiều lần vì mỗi dòng được tạo bởi một relationship. Khi chỉ cần mỗi node một lần, dùng `collect(DISTINCT book)`. Với relationship, chỉ dùng `DISTINCT` khi muốn loại bỏ các relationship trùng theo định danh graph; hai relationship khác nhau có cùng property vẫn là hai relationship riêng.

Ví dụ:

~~~cypher
MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
RETURN collect(DISTINCT book) AS distinctBooks,
       collect(written) AS allWritingRelationships
~~~

Truy vấn này thể hiện rõ hai khái niệm: số node sách khác nhau và số relationship viết sách thực tế. Chúng không nhất thiết bằng nhau.

## 3. Thu thập path khi cần giữ cấu trúc đường đi

Nếu cần giữ cả chuỗi node và relationship theo đúng thứ tự trên đường đi, có thể gom path:

~~~cypher
MATCH path = (author:Author {id: $authorId})-[:WROTE]->(book:Book)
RETURN collect(path) AS writingPaths
~~~

Mỗi phần tử trong `writingPaths` là một path gồm node và relationship theo thứ tự. Path hữu ích khi kết quả cần giữ cấu trúc của tuyến đi, thay vì chỉ cần danh sách node hoặc relationship tách rời.

Path có thể chứa nhiều dữ liệu hơn DTO tóm tắt. Nếu giao diện chỉ cần mã và tên sách, hãy trả `collect({id: book.id, title: book.title})` hoặc projection tương đương thay vì thu thập toàn bộ path.

## 4. Gom map để tạo DTO cho một use case

Một cách phổ biến là gom các map chứa đúng trường cần thiết. Ví dụ hồ sơ tác giả cần danh sách sách kèm vai trò trên relationship:

~~~cypher
MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
RETURN author.id AS authorId,
       author.name AS authorName,
       collect({
           bookId: book.id,
           title: book.title,
           role: written.role
       }) AS works
~~~

Mỗi phần tử của `works` là một map được tạo trong kết quả truy vấn. Map không tự trở thành property lồng nhau trên node `Author`; nó chỉ là cấu trúc trả về của câu Cypher.

Có thể dùng `Neo4jClient` để ánh xạ danh sách map này thành DTO có kiểu rõ ràng:

~~~java
import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.core.Neo4jClient;

public record WorkView(String bookId, String title, String role) {}

public record AuthorWorksView(
    String authorId,
    String authorName,
    List<WorkView> works
) {}

public class AuthorReadService {
    private final Neo4jClient neo4jClient;

    public AuthorReadService(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public Optional<AuthorWorksView> findWorks(String authorId) {
        return neo4jClient.query("""
                MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
                RETURN author.id AS authorId,
                       author.name AS authorName,
                       collect({
                           bookId: book.id,
                           title: book.title,
                           role: written.role
                       }) AS works
                """)
            .bind(authorId).to("authorId")
            .fetchAs(AuthorWorksView.class)
            .mappedBy((typeSystem, record) -> new AuthorWorksView(
                record.get("authorId").asString(),
                record.get("authorName").asString(),
                record.get("works").asList(value -> new WorkView(
                    value.get("bookId").asString(),
                    value.get("title").asString(),
                    value.get("role").asString()
                ))
            ))
            .one();
    }
}
~~~

`asList(...)` chuyển từng phần tử của list Cypher thành `WorkView`. Alias ở phần `RETURN` phải khớp với những trường mà mapper đọc. Ví dụ giả định `authorId`, `authorName`, `bookId`, `title` và `role` luôn có giá trị; nếu property có thể vắng mặt, hãy kiểm tra null trước khi gọi `asString()` hoặc `asLong()`.

Nếu cần nhiều tác giả, có thể đổi truy vấn để trả nhiều hàng và dùng `.all()` thay cho `.one()`, đồng thời đổi kiểu trả về thành `List<AuthorWorksView>`. Nếu một tác giả không có sách và vẫn cần một hồ sơ với `works` rỗng, cần thiết kế truy vấn để giữ lại node gốc.

## 5. Dùng OPTIONAL MATCH để giữ node gốc không có quan hệ

Với `MATCH` thông thường, tác giả không có relationship `WROTE` sẽ không xuất hiện trong kết quả. Nếu muốn trả hồ sơ tác giả với danh sách sách rỗng, dùng `OPTIONAL MATCH`:

~~~cypher
MATCH (author:Author {id: $authorId})
OPTIONAL MATCH (author)-[written:WROTE]->(book:Book)
RETURN author.id AS authorId,
       author.name AS authorName,
       collect({
           bookId: book.id,
           title: book.title
       }) AS books
~~~

`OPTIONAL MATCH` giữ dòng tác giả và đặt các biến `written`, `book` thành null khi không có quan hệ. `collect()` bỏ qua biểu thức null, nhưng map literal có các trường null vẫn là một map không-null. Do đó, ví dụ trên có thể tạo danh sách chứa một map mà `bookId` và `title` đều null.

Để tránh phần tử giả đó, dùng điều kiện lọc trong biểu thức được gom hoặc lọc danh sách sau khi thu thập. Một cách rõ ràng là:

~~~cypher
MATCH (author:Author {id: $authorId})
OPTIONAL MATCH (author)-[written:WROTE]->(book:Book)
WITH author,
     [item IN collect(CASE
         WHEN book IS NOT NULL THEN {
             bookId: book.id,
             title: book.title,
             role: written.role
         }
     END) WHERE item IS NOT NULL] AS works
RETURN author.id AS authorId,
       author.name AS authorName,
       works
~~~

`CASE` trả về null khi không có sách; `collect()` bỏ qua null, nên `works` là danh sách rỗng. Cách viết này giúp kết quả có hình dạng nhất quán dù node gốc không có relationship.

## 6. Tránh nhân chéo khi thu thập nhiều loại relationship

Một lỗi thường gặp là khớp nhiều nhánh quan hệ trong cùng một `MATCH`. Ví dụ một tác giả có ba sách và hai giải thưởng:

~~~cypher
MATCH (author:Author {id: $authorId})-[:WROTE]->(book:Book)
MATCH (author)-[:WON]->(award:Award)
RETURN collect(book) AS books,
       collect(award) AS awards
~~~

Hai nhánh được khớp đồng thời tạo ra tối đa sáu dòng (3 sách × 2 giải). Vì thế, danh sách `books` có thể lặp mỗi sách hai lần và `awards` có thể lặp mỗi giải ba lần. `collect(DISTINCT ...)` có thể loại bỏ bản ghi lặp nếu chỉ cần các node khác nhau, nhưng nó không giải quyết mọi trường hợp khi relationship song song có ý nghĩa riêng.

Cách tách từng nhánh bằng subquery giúp mỗi danh sách được tổng hợp độc lập:

~~~cypher
MATCH (author:Author {id: $authorId})
CALL {
    WITH author
    MATCH (author)-[written:WROTE]->(book:Book)
    RETURN collect({
        bookId: book.id,
        title: book.title,
        role: written.role
    }) AS works
}
CALL {
    WITH author
    MATCH (author)-[:WON]->(award:Award)
    RETURN collect({
        awardId: award.id,
        name: award.name
    }) AS awards
}
RETURN author.id AS authorId,
       author.name AS authorName,
       works,
       awards
~~~

Mỗi subquery tổng hợp một nhánh và trả về một hàng cho tác giả. Vì thế, `works` và `awards` không nhân chéo với nhau. Các subquery dùng `MATCH` bên trong vẫn trả về danh sách rỗng khi không có kết quả do phép tổng hợp không có grouping key; nếu truy vấn con còn trả thêm biểu thức không tổng hợp, cần xem lại cách nhóm để không làm mất dòng tác giả.

## 7. Sắp xếp phần tử trước khi collect

Thứ tự của danh sách thu thập cần được xác định rõ. Nếu thứ tự có ý nghĩa nghiệp vụ, sắp xếp các dòng trước bước `collect()`:

~~~cypher
MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
WITH author, book, written
ORDER BY written.position, book.title
WITH author,
     collect({
         bookId: book.id,
         title: book.title,
         position: written.position
     }) AS works
RETURN author.id AS authorId, works
~~~

`ORDER BY` trên `WITH` sắp xếp các dòng đầu vào của bước tổng hợp tiếp theo. Nhờ vậy, list được gom theo thứ tự position rồi title. Không dựa vào thứ tự ngẫu nhiên của kết quả Neo4j nếu danh sách cần ổn định giữa các lần chạy.

Nếu `position` có thể trùng, hãy thêm tiêu chí phụ ổn định như `book.id` để thứ tự xác định.

## 8. Thu thập node và relationship qua Neo4jClient

Khi cần giữ các phần tử graph gốc thay vì biến chúng thành map scalar, có thể dùng `Neo4jClient` và đọc từng phần tử list bằng kiểu của Neo4j Driver:

~~~java
import java.util.List;
import java.util.Optional;

import org.neo4j.driver.types.Node;
import org.neo4j.driver.types.Relationship;
import org.springframework.data.neo4j.core.Neo4jClient;

public record AuthorGraphParts(
    List<Node> books,
    List<Relationship> writingRelationships
) {}

public Optional<AuthorGraphParts> loadGraphParts(String authorId) {
    return neo4jClient.query("""
            MATCH (author:Author {id: $authorId})-[written:WROTE]->(book:Book)
            RETURN collect(DISTINCT book) AS books,
                   collect(written) AS writingRelationships
            """)
        .bind(authorId).to("authorId")
        .fetchAs(AuthorGraphParts.class)
        .mappedBy((typeSystem, record) -> new AuthorGraphParts(
            record.get("books").asList(value -> value.asNode()),
            record.get("writingRelationships").asList(value -> value.asRelationship())
        ))
        .one();
}
~~~

Đoạn mã này trả về các kiểu graph của Driver (`Node`, `Relationship`), không phải entity SDN `Book` hay `Author`. Nó phù hợp với lớp adapter hoặc công cụ phân tích cần truy cập trực tiếp dữ liệu graph. Nếu service nghiệp vụ cần domain object, hãy ánh xạ các property cần thiết sang DTO hoặc dùng cơ chế mapping của SDN với hình dạng kết quả tương thích.

## 9. Khi nào không nên dùng collect()?

`collect()` gom tất cả phần tử của mỗi nhóm vào bộ nhớ để tạo một list. Với node có hàng chục nghìn relationship, một danh sách lớn có thể làm tăng bộ nhớ, thời gian truy vấn và kích thước response.

Nên cân nhắc:

- Dùng `count()` nếu chỉ cần số lượng.
- Dùng `collect(DISTINCT ...)` nếu thực sự cần các giá trị duy nhất.
- Lọc node và relationship trước khi gom.
- Giới hạn số dòng trước bước tổng hợp nếu use case chỉ cần top-N, đồng thời đặt `ORDER BY` rõ ràng.
- Phân trang danh sách lớn bằng truy vấn riêng thay vì trả toàn bộ collection trong một hồ sơ.
- Chia các nhánh quan hệ bằng subquery để tránh nhân chéo và dữ liệu lặp.

Ví dụ chỉ lấy năm cuốn sách mới nhất theo năm xuất bản:

~~~cypher
MATCH (author:Author {id: $authorId})-[:WROTE]->(book:Book)
WITH book
ORDER BY book.publishedYear DESC, book.id
LIMIT 5
RETURN collect({
    id: book.id,
    title: book.title,
    publishedYear: book.publishedYear
}) AS latestBooks
~~~

Danh sách này là top năm theo tiêu chí đã sắp xếp, không phải toàn bộ sách của tác giả. Không dùng nó làm trạng thái đầy đủ để đồng bộ collection relationship của entity.

## 10. Bài tập tự kiểm tra

1. `collect(book)` khác `collect(book.title)` ở kiểu dữ liệu và mục đích ra sao?
2. Vì sao `collect(DISTINCT book)` có thể có số phần tử ít hơn `collect(book)`?
3. Khi dùng `OPTIONAL MATCH`, vì sao `collect({id: book.id})` có thể tạo một map chứa null thay vì list rỗng?
4. Hai nhánh relationship trong cùng một `MATCH` có thể làm nhân chéo kết quả như thế nào?
5. Làm thế nào để giữ thứ tự phần tử trong list được gom?
6. Khi nào nên dùng `Neo4jClient` để ánh xạ list node/relationship sang DTO thay vì cố ánh xạ trực tiếp thành entity?

Khi hoàn thành bài học, bạn cần biết cách gom node, relationship, path hoặc map bằng `collect()`, hiểu grouping và xử lý null/duplicate, đồng thời chọn cách ánh xạ kết quả phù hợp với SDN. Điều đó giúp tạo các kết quả đồ thị tổng hợp rõ ràng mà vẫn kiểm soát được kích thước dữ liệu và chi phí truy vấn.
