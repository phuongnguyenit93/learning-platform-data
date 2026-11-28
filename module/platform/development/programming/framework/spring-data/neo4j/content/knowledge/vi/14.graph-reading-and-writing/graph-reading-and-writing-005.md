# Nguy cơ mất liên kết khi save entity chỉ được tải một phần

Trong Spring Data Neo4j (SDN), entity thường biểu diễn một node cùng các relationship được khai báo bằng annotation @Relationship. Khi gọi save(entity), SDN đồng bộ trạng thái của entity với graph theo mapping đã khai báo. Vì vậy, một entity chỉ được tải một phần có thể không chứa đầy đủ các liên kết đang tồn tại trong Neo4j. Nếu ứng dụng sửa một thuộc tính rồi lưu chính object đó, những relationship bị bỏ sót trong object có nguy cơ bị xem như không còn thuộc trạng thái cần giữ và bị loại bỏ khỏi graph.

Đây là một lỗi khó nhận ra vì thao tác save có thể chạy thành công, node vẫn tồn tại và thuộc tính vừa sửa vẫn đúng. Chỉ khi truy vấn các node liên quan, ứng dụng mới phát hiện những cạnh cũ đã biến mất. Bài học này giải thích vì sao hiện tượng xảy ra, cách nhận biết entity được tải đủ hay chưa và cách cập nhật an toàn khi chỉ muốn thay đổi một phần graph.

## Entity là mô hình trạng thái, không phải bản vá từng trường

Giả sử một tác giả có thể viết nhiều cuốn sách. Graph đang lưu:

~~~cypher
CREATE (a:Author {id: "A-01", name: "Lan Nguyen"})
CREATE (b1:Book {id: "B-01", title: "Graph Basics"})
CREATE (b2:Book {id: "B-02", title: "Cypher in Practice"})
CREATE (a)-[:WROTE]->(b1)
CREATE (a)-[:WROTE]->(b2);
~~~

Mô hình Java có thể khai báo quan hệ như sau:

~~~java
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Author")
public class Author {

    @Id
    private String id;

    private String name;

    @Relationship(type = "WROTE")
    private Set<Book> books = new LinkedHashSet<>();

    protected Author() {
    }

    public Author(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Set<Book> getBooks() {
        return books;
    }
}
~~~

Entity **Book** được tham chiếu trong collection có thể khai báo tối thiểu như sau:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Book")
public class Book {

    @Id
    private String id;

    private String title;

    protected Book() {
    }
}
~~~

Giả sử một truy vấn chỉ lấy node Author, không lấy các relationship WROTE. Object Java được tạo ra có thể có tên tác giả nhưng collection books rỗng vì trường được khởi tạo bằng LinkedHashSet. Trạng thái này chỉ phản ánh phạm vi dữ liệu đã đọc; nó không chứng minh tác giả không có sách.

Nếu ứng dụng đổi tên rồi gọi save(author), SDN có thể đồng bộ collection books rỗng thành trạng thái quan hệ mong muốn. Tùy mapping và phiên bản SDN, các relationship WROTE hiện có nhưng không xuất hiện trong collection có thể bị xóa. Kết quả có thể giống như sau:

**Trước khi save**

~~~text
(Author A-01)
   ├──[:WROTE]──> (Book B-01)
   └──[:WROTE]──> (Book B-02)
~~~

**Object tải một phần trong Java**

~~~text
Author {
  id = "A-01",
  name = "Lan Nguyen",
  books = []
}
~~~

**Sau khi save và đồng bộ relationship rỗng**

~~~text
(Author A-01)
  name = "Lan N."
  // Không còn cạnh WROTE trong phạm vi relationship đã đồng bộ
~~~

Điểm quan trọng là save(entity) không nên được hiểu như câu lệnh PATCH chỉ cập nhật đúng field đã thay đổi. Với các relationship được SDN quản lý qua entity, object graph được đưa vào save có thể được dùng làm trạng thái cần đồng bộ. Khi object graph thiếu dữ liệu, trạng thái lưu có thể không còn phản ánh toàn bộ graph ban đầu.

## Vì sao entity có thể chỉ được tải một phần?

Một entity có thể thiếu relationship vì nhiều nguyên nhân:

- Repository method hoặc cấu hình độ sâu chỉ tải một số cấp quan hệ.
- Custom Cypher query chỉ trả về node gốc mà không trả các relationship hoặc node liên quan.
- Projection hoặc truy vấn đọc chỉ lấy các trường cần hiển thị.
- Ứng dụng tự tạo entity từ request DTO, chỉ điền ID và một vài thuộc tính.
- Một tiến trình đọc graph bằng Neo4jClient rồi chuyển thành entity thủ công nhưng không nạp các relationship.
- Graph có cấu trúc sâu hoặc rộng, nên ứng dụng chủ động giới hạn dữ liệu để giảm chi phí truy vấn.

Ví dụ custom query sau chỉ trả node Author:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface AuthorRepository extends Neo4jRepository<Author, String> {

    @Query("MATCH (a:Author {id: $id}) RETURN a")
    Optional<Author> findNodeOnly(@Param("id") String id);
}
~~~

Query trả về node a, không trả các cạnh WROTE hoặc các node Book đi cùng. Không nên giả định SDN sẽ tự tải mọi relationship ngoài kết quả mà custom query cung cấp. Hãy xem query trả về node, path và relationship nào, cũng như cách phiên bản SDN của dự án ánh xạ kết quả đó.

Một nguồn khác là giới hạn độ sâu đọc. SDN hỗ trợ kiểm soát độ sâu quan hệ trong các phương thức repository phù hợp thông qua **@Depth**. Thêm derived query sau vào interface **AuthorRepository** ở trên để yêu cầu độ sâu rõ ràng:

~~~java
import org.springframework.data.neo4j.repository.query.Depth;

Optional<Author> findOneById(String id, @Depth int depth);
~~~

Hãy chọn độ sâu theo thao tác nghiệp vụ. Nếu thao tác sắp lưu cần thay đổi quan hệ WROTE, phải nạp đủ các quan hệ thuộc phạm vi sẽ được đồng bộ. Việc tải sâu hơn cũng có chi phí: graph lớn có thể tạo nhiều node và relationship trong bộ nhớ. Không nên dùng một độ sâu lớn cho mọi màn hình hoặc mọi thao tác.

## Phân biệt ba trạng thái: đầy đủ, rỗng và chưa tải

Với một thuộc tính relationship dạng collection, cần hiểu ý nghĩa của trạng thái Java:

| Trạng thái trong object | Có thể mang ý nghĩa | Rủi ro khi save |
|---|---|---|
| Collection có các phần tử đã tải | Những relationship đã được đọc và ánh xạ | Phù hợp hơn cho thao tác đồng bộ nếu phạm vi tải đầy đủ |
| Collection rỗng | Không có liên kết trong phạm vi đã tải hoặc ứng dụng muốn xóa hết liên kết | Có thể khiến các liên kết cũ thuộc field được quản lý bị xóa |
| Field null hoặc không được gán | Chưa có dữ liệu, không được khởi tạo hoặc mang ý nghĩa tùy mapping | Không nên dựa vào null như một hợp đồng partial update |

Một collection rỗng không thể tự cho biết nó rỗng vì database không có quan hệ hay vì query đã không tải quan hệ. Java entity thông thường cũng không tự lưu metadata đáng tin cậy cho biết field nào đã được đọc đầy đủ.

Đặc biệt, khởi tạo collection bằng Set rỗng giúp tránh NullPointerException nhưng không giải quyết được vấn đề dữ liệu chưa tải. Nếu dùng một object được tạo từ request rồi gán ID và name, collection mặc định rỗng vẫn có thể bị hiểu là trạng thái quan hệ cần đồng bộ khi save.

Không dùng mẹo đặt field thành null để né cập nhật quan hệ trừ khi semantics đó được tài liệu phiên bản SDN xác nhận và đã có test. Null, collection rỗng và field không được load có thể được xử lý khác nhau tùy cơ chế mapping; chúng không phải một giao thức patch ổn định.

## Cách an toàn khi cần cập nhật một phần dữ liệu

Trước khi chọn cách ghi, hãy xác định thao tác đang thực hiện thuộc loại nào:

1. Chỉ cập nhật một property của node, ví dụ đổi tên tác giả.
2. Thêm hoặc xóa một relationship cụ thể.
3. Thay thế toàn bộ tập relationship do entity quản lý.
4. Thay đổi một aggregate gồm node gốc và các node liên quan đã được tải đầy đủ.

Mỗi loại nên dùng cơ chế ghi phù hợp.

### Cách 1: Tải đủ aggregate rồi mới gọi save

Nếu nghiệp vụ yêu cầu cập nhật object graph, hãy đọc entity cùng các relationship cần quản lý trước khi sửa. Sau đó mới thay đổi object và save trong cùng một transaction.

Với derived query đã bổ sung **findOneById(String id, @Depth int depth)** trong **AuthorRepository**, service có thể đọc với độ sâu phù hợp rồi đổi tên:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthorService {

    private final AuthorRepository authors;

    public AuthorService(AuthorRepository authors) {
        this.authors = authors;
    }

    @Transactional
    public Author rename(String id, String newName) {
        Author author = authors.findOneById(id, 1)
            .orElseThrow(() -> new IllegalArgumentException("Author not found"));

        author.setName(newName);
        return authors.save(author);
    }
}
~~~

Ví dụ giả định relationship WROTE được ánh xạ ở độ sâu đã chọn và toàn bộ các liên kết cần giữ nằm trong phạm vi tải. Hãy kiểm tra query thực tế và kết quả mapping bằng integration test trước khi sử dụng cách này trong nghiệp vụ quan trọng. Nếu graph có nhiều nhánh hoặc độ sâu không giới hạn, không nên tải toàn bộ chỉ để đổi một thuộc tính đơn giản.

### Cách 2: Cập nhật property bằng Cypher có mục tiêu

Nếu chỉ cần đổi một thuộc tính, hãy cập nhật đúng property bằng Cypher. Cách này không cần tạo entity Author có collection books rỗng rồi gọi save.

Có thể dùng Neo4jClient:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;

@Repository
public class AuthorWriter {

    private final Neo4jClient neo4jClient;

    public AuthorWriter(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    public void rename(String id, String newName) {
        neo4jClient.query("""
            MATCH (a:Author {id: $id})
            SET a.name = $newName
            """)
            .bind(id).to("id")
            .bind(newName).to("newName")
            .run();
    }
}
~~~

Truy vấn chỉ thay đổi property name trên node Author có ID tương ứng. Các cạnh WROTE không nằm trong câu lệnh cập nhật nên được giữ nguyên. Tham số được bind riêng giúp tránh nối chuỗi Cypher và giảm nguy cơ injection.

Nếu cần xác nhận node có tồn tại, hãy trả về một giá trị đếm hoặc dùng kết quả summary phù hợp để service phân biệt trường hợp không tìm thấy node. Đặt thao tác trong transaction cùng các cập nhật nghiệp vụ liên quan nếu cần tính nguyên tử.

### Cách 3: Thêm hoặc xóa một relationship cụ thể bằng Cypher

Khi chỉ muốn thêm một liên kết WROTE, dùng MATCH hai đầu mối rồi MERGE relationship:

~~~cypher
MATCH (a:Author {id: $authorId})
MATCH (b:Book {id: $bookId})
MERGE (a)-[:WROTE]->(b);
~~~

MERGE giúp thao tác thêm liên kết có tính lặp an toàn theo mẫu relationship này: nếu cạnh phù hợp đã tồn tại thì không tạo thêm một cạnh tương tự.

Để xóa đúng một liên kết giữa tác giả và sách:

~~~cypher
MATCH (a:Author {id: $authorId})-[r:WROTE]->(b:Book {id: $bookId})
DELETE r;
~~~

Câu lệnh chỉ xóa relationship được MATCH giữa hai node đã chỉ định; node Author, Book và các relationship khác không bị xóa. Nếu mô hình cho phép nhiều relationship WROTE có ý nghĩa khác nhau giữa cùng hai node, hãy thêm điều kiện theo property hoặc khóa của relationship để chỉ xóa đúng cạnh nghiệp vụ cần chọn.

Nếu relationship có property như vai trò, ngày bắt đầu hoặc nguồn tạo, hãy xác định rõ mẫu MERGE và điều kiện nhận diện cạnh. Không gộp các quan hệ khác nhau thành cùng một cạnh chỉ vì hai node có cùng đầu mối.

### Cách 4: Dùng DTO hoặc projection cho luồng chỉ đọc

Nếu một màn hình chỉ cần ID và tên tác giả, không cần tải entity đầy đủ. Hãy trả DTO hoặc projection để thể hiện rõ đây là dữ liệu đọc:

~~~java
public record AuthorSummary(String id, String name) {
}
~~~

Một repository query có thể trả các trường cần thiết:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface AuthorReadRepository extends Neo4jRepository<Author, String> {

    @Query("""
        MATCH (a:Author)
        WHERE a.name CONTAINS $keyword
        RETURN a.id AS id, a.name AS name
        ORDER BY a.name
        """)
    List<AuthorSummary> searchSummary(@Param("keyword") String keyword);
}
~~~

Projection giúp giới hạn dữ liệu đọc và giảm nguy cơ vô tình dùng một entity thiếu relationship làm đầu vào cho save. DTO đọc không nên được chuyển ngược thành entity chỉ bằng cách chép ID và các field đã nhận. Nếu người dùng gửi yêu cầu cập nhật, service cần đọc lại trạng thái phù hợp hoặc dùng lệnh cập nhật có mục tiêu.

## Quy trình làm việc an toàn với entity graph

Một quy trình đơn giản giúp tránh mất liên kết:

1. **Xác định phạm vi thay đổi.** Chỉ đổi property, thay một cạnh hay cập nhật toàn bộ aggregate?
2. **Kiểm tra nguồn dữ liệu.** Entity được đọc từ repository nào, query nào, độ sâu bao nhiêu? Có relationship field nào chưa được tải?
3. **Chọn cơ chế ghi.** Dùng save khi object graph đại diện đầy đủ cho phần trạng thái được quản lý; dùng Cypher có mục tiêu khi chỉ cập nhật một phần.
4. **Đặt ranh giới transaction.** Gom các thay đổi cần thành công hoặc rollback cùng nhau vào một transaction.
5. **Xác minh quan hệ sau ghi.** Truy vấn lại số cạnh hoặc danh sách node liên quan cần được giữ.
6. **Kiểm thử trường hợp thiếu dữ liệu.** Cố tình đọc entity với độ sâu thấp, cập nhật property rồi xác nhận các relationship ngoài phạm vi tải vẫn còn.

Một truy vấn xác minh các sách của tác giả:

~~~cypher
MATCH (a:Author {id: $authorId})-[:WROTE]->(b:Book)
RETURN b.id AS bookId, b.title AS title
ORDER BY b.title;
~~~

Nếu thao tác chỉ đổi tên tác giả, tập bookId trước và sau phải giống nhau. Nếu thao tác thêm hoặc xóa một sách, chỉ thay đổi đúng liên kết tương ứng.

## Transaction không tự khôi phục relationship đã bị bỏ sót

@Transactional bảo đảm các câu lệnh thuộc transaction cùng commit hoặc rollback theo kết quả xử lý. Nó không biết ứng dụng muốn giữ một relationship mà object Java không chứa. Nếu save đồng bộ một collection rỗng và transaction commit thành công, việc xóa relationship có thể là kết quả hợp lệ theo trạng thái object được gửi xuống.

Do đó, transaction giải quyết tính nguyên tử, còn tính đầy đủ của dữ liệu đọc là trách nhiệm của luồng ứng dụng. Với nhiều request cùng sửa một graph, cần cân nhắc cả xung đột cập nhật. Một request tải danh sách relationship, request khác thêm cạnh mới, rồi request đầu save lại collection cũ có thể ghi đè thay đổi vừa được thêm. Dùng transaction không tự giải quyết mọi lost update.

Các biện pháp có thể cân nhắc:

- Thực hiện thay đổi relationship qua Cypher có mục tiêu để không ghi đè những cạnh không liên quan.
- Giới hạn nơi được phép thay đổi một loại relationship và gom quy tắc vào service.
- Dùng optimistic locking hoặc cơ chế đồng bộ phù hợp với mô hình và phiên bản SDN/Neo4j khi cần phát hiện cập nhật cạnh tranh.
- Thiết kế thao tác idempotent và kiểm tra trạng thái sau ghi.
- Tránh giữ entity graph trong bộ nhớ quá lâu rồi save sau khi dữ liệu có thể đã thay đổi.

## Kiểm thử nguy cơ mất liên kết

Một integration test nên mô phỏng chính xác lỗi: database có hai relationship, ứng dụng chỉ tải node gốc, sửa một property rồi save. Sau đó kiểm tra số relationship còn lại. Cần chạy test với đúng phiên bản SDN, Neo4j và mapping của dự án, vì chi tiết đồng bộ phụ thuộc cách query và relationship field được ánh xạ.

Một test cho thao tác cập nhật property bằng Cypher có thể kiểm tra rằng các liên kết vẫn còn:

~~~java
@Test
void renamingAuthorKeepsExistingBooks() {
    // Arrange: lưu Author A-01 và hai Book, tạo hai cạnh WROTE.
    // Act: gọi authorWriter.rename("A-01", "Lan N.").
    // Assert: name đã đổi và vẫn có đúng hai Book nối với Author.
}
~~~

Đây là khung mô tả test; phần setup và assertion cần dùng repository, fixture hoặc Testcontainers của dự án. Không chỉ kiểm tra tên đã đổi, vì điều đó bỏ sót lỗi quan trọng nhất. Hãy kiểm tra cả số lượng và ID của các node liên quan.

Có thể kiểm tra bằng Cypher trong test:

~~~cypher
MATCH (a:Author {id: "A-01"})
OPTIONAL MATCH (a)-[:WROTE]->(b:Book)
RETURN a.name AS authorName,
       collect(b.id) AS bookIds;
~~~

Kết quả mong đợi là tên mới và cả hai ID sách ban đầu. Với trường hợp xóa một relationship cụ thể, test cần xác nhận cạnh đó đã mất trong khi các cạnh khác vẫn còn.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng entity chỉ tải node gốc rồi gọi save | Relationship không có trong object có thể bị xóa khi đồng bộ | Tải đủ phạm vi quan hệ hoặc dùng cập nhật Cypher có mục tiêu |
| Tạo entity mới chỉ có ID và một vài property rồi save | Collection mặc định rỗng có thể được hiểu là không còn liên kết | Không dùng entity partial như request patch |
| Cho rằng collection rỗng có nghĩa database không có relationship | Có thể xóa các cạnh chưa từng được đọc | Phân biệt empty với not loaded |
| Chỉ trả node trong custom query nhưng vẫn kỳ vọng có đủ relationship | Entity nhận về thiếu dữ liệu liên quan | Trả graph cần thiết hoặc dùng DTO cho read-only |
| Tải toàn bộ graph chỉ để đổi một property | Tốn truy vấn, bộ nhớ và tăng nguy cơ ghi đè trạng thái khác | Cập nhật property bằng Cypher có mục tiêu |
| Dùng save để thêm một cạnh duy nhất | Có thể đồng bộ cả collection và ảnh hưởng cạnh khác | Dùng MERGE cho cạnh cần thêm |
| Dùng transaction như cơ chế chống lost update | Thay đổi đồng thời vẫn có thể bị ghi đè theo trạng thái cũ | Dùng cập nhật có mục tiêu và chiến lược đồng bộ |
| Không xác minh relationship sau ghi | Lỗi mất liên kết khó phát hiện | Kiểm tra ID và số lượng cạnh trong integration test |

## Bài tập thực hành

Xây dựng mô hình Author và Book với relationship WROTE:

1. Tạo một tác giả có ID A-01 và hai sách B-01, B-02.
2. Tạo hai relationship WROTE từ tác giả tới hai sách.
3. Viết một custom query chỉ trả node Author và quan sát trạng thái collection books trong entity được ánh xạ.
4. Thử đổi name rồi save entity chỉ tải một phần trên database kiểm thử; quan sát các relationship có bị thay đổi theo mapping của phiên bản SDN đang dùng hay không.
5. Viết một thao tác rename bằng Neo4jClient chỉ cập nhật property name.
6. Viết thao tác thêm một sách bằng MERGE và xóa một cạnh bằng DELETE relationship cụ thể.
7. Viết integration test xác nhận rename không làm mất B-01 và B-02.
8. Viết thêm test cho trường hợp entity được tải đủ relationship trước khi save và giải thích vì sao phạm vi tải cần phù hợp với phạm vi đồng bộ.

Khi dùng Spring Data Neo4j, hãy xem entity được save là trạng thái graph mà ứng dụng muốn đồng bộ trong phạm vi mapping. Trước khi save, xác nhận relationship cần giữ đã được tải đầy đủ. Nếu chỉ muốn sửa một phần dữ liệu, dùng DTO cho đọc và Cypher có mục tiêu cho ghi để tránh làm mất những liên kết mà object Java chưa từng nhận được.

