# Đối chiếu collection Java với các relationship thực tế

Trong Spring Data Neo4j (SDN), một thuộc tính collection như `Set<Book>` hoặc `List<Enrollment>` là cách Java biểu diễn các relationship được ánh xạ từ graph. Collection không phải một property dạng danh sách được lưu nguyên khối trên node. Neo4j lưu từng relationship riêng, có hướng, kiểu quan hệ và có thể có các property riêng.

Vì vậy, số phần tử trong collection Java và số relationship thực tế chỉ tương ứng khi phạm vi dữ liệu được tải đầy đủ, kiểu collection có thể biểu diễn đúng các relationship và cách ánh xạ không loại bỏ phần tử trùng theo quy tắc `equals`/`hashCode`. Bài học này trình bày cách đối chiếu hai phía, chọn `Set` hay `List`, xử lý relationship properties và tránh cập nhật graph từ một collection chưa đầy đủ.

## 1. Collection Java biểu diễn relationship như thế nào?

Giả sử một tác giả viết nhiều cuốn sách. Graph có dạng:

~~~text
(Author)-[:WROTE]->(Book)
~~~

Một entity SDN có thể khai báo collection các node đích:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

import java.util.LinkedHashSet;
import java.util.Set;

@Node("Author")
public class Author {
    @Id
    private String id;

    private String name;

    @Relationship(type = "WROTE", direction = Relationship.Direction.OUTGOING)
    private Set<Book> books = new LinkedHashSet<>();

    // Constructor, getter và setter được lược bỏ.
}
~~~

`books` là collection những node `Book` được nối từ tác giả hiện tại bằng relationship `WROTE`. SDN dùng metadata của `@Relationship` để xác định loại và hướng quan hệ khi đọc hoặc ghi entity.

Ví dụ, nếu graph có ba relationship `WROTE` đi từ tác giả đến ba sách khác nhau, collection `books` có thể chứa ba entity `Book`. Nhưng collection chỉ phản ánh những relationship mà thao tác đọc đã đưa vào object graph. Nếu truy vấn giới hạn kết quả, chỉ tải một phần quan hệ hoặc trả về projection, collection không phải bản kiểm kê đầy đủ mọi relationship trong database.

## 2. Đối chiếu số phần tử với số relationship trong Neo4j

Không nên suy luận số relationship trong database chỉ bằng cách nhìn `books.size()` trên một entity bất kỳ. Hãy kiểm tra graph trực tiếp bằng Cypher:

~~~cypher
MATCH (author:Author {id: $authorId})-[r:WROTE]->(book:Book)
RETURN count(r) AS relationshipCount,
       count(DISTINCT book) AS distinctBookCount
~~~

Hai số liệu có ý nghĩa khác nhau:

- `relationshipCount` đếm các relationship `WROTE` thực tế khớp với mẫu truy vấn.
- `distinctBookCount` đếm số node sách khác nhau ở đầu đích.

Nếu mỗi tác giả chỉ được phép có một relationship `WROTE` đến mỗi cuốn sách, hai con số thường bằng nhau. Nếu graph cho phép nhiều relationship cùng loại giữa cùng một cặp node, `relationshipCount` có thể lớn hơn `distinctBookCount`.

Có thể kiểm tra từng relationship cùng node đích:

~~~cypher
MATCH (author:Author {id: $authorId})-[r:WROTE]->(book:Book)
RETURN type(r) AS relationshipType,
       properties(r) AS relationshipProperties,
       book.id AS bookId,
       book.title AS title
ORDER BY title
~~~

Truy vấn này giúp phát hiện các relationship trùng đầu đích nhưng khác thuộc tính. Nó cũng cho thấy relationship là một thực thể riêng trong graph, không chỉ là một phần tử node trong collection Java.

## 3. Chọn Set hay List

`Set<TargetNode>` và `List<TargetNode>` có ngữ nghĩa Java khác nhau. Chọn collection theo quy tắc nghiệp vụ và khả năng biểu diễn relationship, không chỉ theo thói quen lập trình.

| Kiểu collection | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| `Set<Book>` | Không giữ phần tử trùng theo `equals`/`hashCode`; không cam kết thứ tự | Quan hệ logic duy nhất đến mỗi sách và domain có equality phù hợp |
| `List<Book>` | Cho phép nhiều phần tử bằng nhau và giữ thứ tự trong bộ nhớ | Cần biểu diễn các mục lặp trong collection Java hoặc xử lý tuần tự trong ứng dụng |
| `Set<RelationshipProperties>` | Mỗi phần tử là một object mang dữ liệu của một relationship; vẫn chịu quy tắc equality của Set | Quan hệ có thuộc tính và mỗi object relationship có định danh/equality rõ |
| `List<RelationshipProperties>` | Mỗi phần tử mô tả một relationship, cho phép nhiều object cùng trỏ đến một node đích | Có thể có nhiều relationship giữa cùng hai node hoặc cần xử lý từng relationship riêng |

### 3.1. Set có thể làm mất biểu diễn của nhiều relationship

Neo4j có thể lưu nhiều relationship cùng kiểu giữa cùng một cặp node. Tuy nhiên, `Set<Book>` chỉ lưu các phần tử Java theo equality của `Book`. Nếu `equals` và `hashCode` của `Book` dựa trên ID, hai relationship `WROTE` khác nhau cùng trỏ đến một `Book` sẽ không thể được biểu diễn thành hai phần tử riêng trong `Set<Book>`.

Nếu nghiệp vụ cho phép nhiều lần đóng góp của cùng tác giả vào cùng một sách, chẳng hạn một người vừa viết vừa biên tập, hãy mô hình hóa mỗi relationship bằng một lớp relationship properties có trường mô tả vai trò. Khi đó collection chứa các object quan hệ thay vì chỉ chứa node đích.

### 3.2. List không tạo ra thứ tự lưu trữ trong graph

`List` giữ thứ tự trong object Java, nhưng Neo4j không tự gán thứ tự cho các relationship. Kết quả truy vấn cũng không có thứ tự được bảo đảm nếu không có `ORDER BY`. Nếu thứ tự là một phần của nghiệp vụ, hãy lưu thuộc tính như `position` trên relationship hoặc node liên quan và truy vấn theo thuộc tính đó.

Ví dụ:

~~~cypher
MATCH (author:Author {id: $authorId})-[r:WROTE]->(book:Book)
RETURN book, r.position AS position
ORDER BY position
~~~

Không nên dựa vào thứ tự phần tử trả về tình cờ từ database để biểu diễn thứ tự chương sách, thứ tự thành viên hay trình tự xử lý.

## 4. Ánh xạ relationship có thuộc tính riêng

Khi mỗi relationship có dữ liệu như vai trò, thời điểm hoặc trạng thái, hãy dùng `@RelationshipProperties`. Collection lúc này chứa object mô tả từng relationship:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Contribution {
    @RelationshipId
    private Long id;

    private String role;

    private Integer position;

    @TargetNode
    private Book book;

    // Constructor, getter và setter được lược bỏ.
}
~~~

Phía `Author` có thể khai báo:

~~~java
import java.util.ArrayList;
import java.util.List;

@Relationship(type = "CONTRIBUTED_TO", direction = Relationship.Direction.OUTGOING)
private List<Contribution> contributions = new ArrayList<>();
~~~

Trong mô hình này, `contributions` thay cho trường `Set<Book> books` ở ví dụ trước vì mỗi phần tử cần đại diện cho một relationship có thuộc tính riêng.

Mỗi `Contribution` biểu diễn một relationship `CONTRIBUTED_TO`, có node đích là `book` và property riêng như `role` hoặc `position`. Hai phần tử trong list có thể cùng trỏ đến một `Book` nhưng mô tả hai relationship riêng biệt.

`@RelationshipId` là định danh nội bộ do SDN dùng để nhận diện relationship khi ánh xạ và lưu. Không nên xem giá trị này là mã nghiệp vụ ổn định để công khai cho hệ thống khác hoặc tự đặt tùy ý. Nếu nghiệp vụ cần mã relationship ổn định, hãy thêm một property riêng như `contributionKey` và xác định quy tắc duy nhất phù hợp.

Nếu dùng `Set<Contribution>`, hãy thiết kế `equals`/`hashCode` sao cho hai relationship khác nhau không bị gộp nhầm. Với nhiều relationship cùng node đích, `List<Contribution>` thường thể hiện ý nghĩa từng relationship rõ hơn, nhưng thứ tự vẫn cần thuộc tính và truy vấn rõ ràng nếu có ý nghĩa lưu trữ.

## 5. Thêm và xóa phần tử trong collection

Với entity đã được tải đầy đủ theo phạm vi quan hệ cần cập nhật, có thể thay đổi collection trong domain rồi lưu entity qua repository. Ví dụ:

~~~java
public void addBook(Book book) {
    books.add(book);
}

public void removeBook(Book book) {
    books.remove(book);
}
~~~

~~~java
Author author = authorRepository.findById(authorId)
    .orElseThrow();
Book book = bookRepository.findById(bookId)
    .orElseThrow();

author.addBook(book);
authorRepository.save(author);
~~~

Khi thao tác lưu entity, SDN sử dụng object graph và các quan hệ được ánh xạ để đồng bộ dữ liệu tương ứng. Vì vậy, việc loại một phần tử khỏi collection có thể mang ý nghĩa xóa relationship tương ứng khi lưu. Hãy bảo đảm collection phản ánh đúng phạm vi quan hệ mà use case muốn duy trì.

Nếu entity được đọc với collection rỗng do quan hệ chưa được tải, collection đó không chứng minh rằng database không có relationship. Không dùng một object graph thiếu dữ liệu làm nguồn để thay thế toàn bộ quan hệ đã có. Với thao tác thêm hoặc xóa một relationship đơn lẻ trên graph lớn, một câu Cypher nhắm đúng cặp node thường dễ kiểm soát hơn việc lưu lại collection rộng.

Ví dụ thêm hoặc xóa một relationship cụ thể bằng repository query:

~~~java
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

@Query("""
    MATCH (author:Author {id: $authorId})
    MATCH (book:Book {id: $bookId})
    MERGE (author)-[:WROTE]->(book)
    """)
void linkBook(@Param("authorId") String authorId,
              @Param("bookId") String bookId);

@Query("""
    MATCH (author:Author {id: $authorId})
          -[r:WROTE]->
          (book:Book {id: $bookId})
    DELETE r
    """)
void unlinkBook(@Param("authorId") String authorId,
                @Param("bookId") String bookId);
~~~

Truy vấn xóa trên xóa mọi relationship `WROTE` khớp với cặp tác giả và sách đó. Nếu có nhiều relationship cùng kiểu giữa cùng hai node và chỉ muốn xóa một relationship cụ thể, cần thêm điều kiện nhận diện relationship, chẳng hạn `contributionKey` hoặc một thuộc tính nghiệp vụ khác.

## 6. Collection được tải có thể không phải toàn bộ graph

SDN ánh xạ dữ liệu dựa trên entity metadata, truy vấn và độ sâu quan hệ được yêu cầu. Một thao tác đọc có thể tải node gốc cùng một số tầng quan hệ; truy vấn tùy chỉnh có thể chỉ trả về một phần graph. Vì vậy, collection trong entity cần được hiểu trong ngữ cảnh thao tác đọc đã tạo ra nó.

Các trường hợp dễ tạo ra collection không đầy đủ:

- Truy vấn có `LIMIT` hoặc điều kiện lọc làm giảm số relationship được trả về.
- Truy vấn chỉ trả về node gốc hoặc một phần cấu trúc graph cần thiết.
- Độ sâu mapping không bao gồm những tầng quan hệ xa hơn.
- Ứng dụng dùng projection hoặc DTO chỉ chứa một phần thông tin quan hệ.
- Object được giữ lâu trong bộ nhớ sau khi transaction khác đã thêm hoặc xóa relationship.

Khi cần biết tổng số relationship thực tế, hãy dùng truy vấn đếm. Khi cần hiển thị danh sách có phân trang, hãy truy vấn danh sách relationship hoặc node đích riêng với `ORDER BY`, `SKIP` và `LIMIT` phù hợp, thay vì tải toàn bộ collection vào entity.

## 7. Kiểm tra sự khác nhau giữa collection và graph

Có thể dùng một quy trình kiểm tra ngắn khi phát hiện số phần tử trong Java không khớp với số relationship trong Neo4j:

1. Xác nhận đúng node gốc bằng ID nghiệp vụ và nhãn node.
2. Kiểm tra đúng loại relationship và hướng truy vấn.
3. Đếm relationship bằng `count(r)` và node đích khác nhau bằng `count(DISTINCT target)`.
4. Kiểm tra collection Java là `Set`, `List` hay collection relationship properties.
5. Kiểm tra `equals`/`hashCode` của entity và wrapper relationship nếu dùng `Set`.
6. Xác nhận truy vấn và độ sâu mapping đã tải đủ quan hệ cần so sánh.
7. Kiểm tra các thay đổi chưa lưu, transaction khác và trạng thái object đã cũ.

Ví dụ Cypher liệt kê số relationship theo từng loại và hướng từ một tác giả:

~~~cypher
MATCH (author:Author {id: $authorId})-[r]->(target)
RETURN type(r) AS relationshipType,
       count(r) AS relationshipCount,
       count(DISTINCT target) AS targetCount
ORDER BY relationshipType
~~~

Truy vấn này chỉ thống kê các relationship đi ra từ tác giả. Nếu cần quan hệ đi vào, đổi pattern sang `(author)<-[r]-(source)`. Hãy giữ cùng điều kiện nhãn và hướng khi so sánh với dữ liệu Java.

## 8. Transaction và cập nhật cạnh tranh

Thay đổi collection trong bộ nhớ chưa làm thay đổi graph cho đến khi thao tác ghi được thực hiện. Hãy đặt các bước đọc, kiểm tra điều kiện và lưu trong transaction phù hợp khi chúng cần tính nhất quán:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorService {
    private final AuthorRepository authorRepository;
    private final BookRepository bookRepository;

    public AuthorService(AuthorRepository authorRepository,
                         BookRepository bookRepository) {
        this.authorRepository = authorRepository;
        this.bookRepository = bookRepository;
    }

    @Transactional
    public void addBook(String authorId, String bookId) {
        Author author = authorRepository.findById(authorId)
            .orElseThrow();
        Book book = bookRepository.findById(bookId)
            .orElseThrow();

        author.addBook(book);
        authorRepository.save(author);
    }
}
~~~

Transaction giúp các thao tác persistence tham gia cùng một đơn vị công việc. Nếu nhiều request đồng thời cập nhật collection lớn, cần xem xét optimistic locking bằng `@Version` hoặc dùng Cypher có điều kiện phù hợp để xử lý cạnh tranh. Transaction không tự giải quyết mọi xung đột logic giữa hai bản collection đã được tải ở các thời điểm khác nhau.

## 9. Chọn biểu diễn theo nghiệp vụ

| Nhu cầu miền | Biểu diễn nên cân nhắc |
| --- | --- |
| Một node đích chỉ có một quan hệ logic với node nguồn | `Set<TargetNode>` với equality phù hợp |
| Có thể có nhiều relationship giữa cùng hai node | Collection `@RelationshipProperties` |
| Relationship có vai trò, trạng thái, ngày hoặc thứ tự | `@RelationshipProperties` với các property riêng |
| Cần thứ tự nghiệp vụ | Lưu `position` hoặc timestamp và truy vấn với `ORDER BY` |
| Cần phân trang hoặc thống kê trên graph lớn | Cypher riêng trả projection hoặc kết quả tổng hợp |
| Chỉ cập nhật một relationship trong collection lớn | Cypher nhắm đúng cặp node và relationship |

## 10. Bài tập tự kiểm tra

1. Vì sao `books.size()` không phải lúc nào cũng bằng số relationship `WROTE` trong Neo4j?
2. Một tác giả có hai relationship `WROTE` đến cùng một sách. Điều gì xảy ra nếu entity dùng `Set<Book>` và `equals`/`hashCode` dựa trên ID?
3. Khi nào nên dùng `List<RelationshipProperties>` thay cho `Set<TargetNode>`?
4. Neo4j có bảo đảm thứ tự relationship khi trả kết quả không? Cần làm gì nếu nghiệp vụ cần thứ tự?
5. Vì sao không nên lưu một entity có collection chưa tải đầy đủ để thay thế toàn bộ quan hệ?
6. Viết Cypher đếm số relationship thực tế và số node đích khác nhau cho một tác giả.

Khi hoàn thành bài học, bạn cần hiểu collection Java là cách SDN biểu diễn phần relationship được ánh xạ vào entity, biết cách đối chiếu nó với graph thực tế và chọn collection phù hợp với số lượng, thuộc tính và thứ tự của relationship. Nhờ đó, thao tác lưu không vô tình làm mất hoặc tạo sai các quan hệ trong Neo4j.
