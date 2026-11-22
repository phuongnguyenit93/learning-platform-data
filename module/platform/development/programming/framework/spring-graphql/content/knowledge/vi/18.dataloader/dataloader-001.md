# N+1 select problem

GraphQL cho phép client chọn field lồng nhau theo nhu cầu. Một query có thể lấy danh sách Book rồi chọn Author của từng Book trong cùng một operation. Cách tổ chức này thuận tiện cho API, nhưng nếu mỗi field con tự chạy một truy vấn database cho từng object cha, server sẽ phát sinh vấn đề **N+1 select**.

N+1 select nghĩa là một truy vấn lấy danh sách N object cha, sau đó có thêm N truy vấn để lấy dữ liệu liên quan cho từng object. Với một danh sách nhỏ, chi phí có thể khó nhận thấy. Khi N tăng lên hàng chục hoặc hàng trăm, số lần truy cập database tăng theo và có thể làm request chậm đáng kể.

Trong Spring for GraphQL, hiện tượng này thường xuất hiện khi root resolver trả về một collection, còn field resolver hoặc JPA lazy association tải dữ liệu quan hệ riêng cho từng phần tử. DataLoader và **@BatchMapping** là những cơ chế quan trọng để gom các lần tải đó thành batch. Trước khi chọn cách xử lý, cần hiểu rõ N+1 hình thành ở đâu, cách nhận diện và những tình huống dễ nhầm lẫn.

## 1. N+1 select là gì?

Giả sử hệ thống quản lý sách có hai bảng:

~~~sql
CREATE TABLE author (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE book (
    id BIGINT PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    author_id BIGINT NOT NULL REFERENCES author(id)
);
~~~

Một trang danh mục cần hiển thị danh sách sách cùng tên tác giả. Có N sách trong kết quả.

Truy vấn đầu tiên lấy danh sách sách:

~~~sql
SELECT id, title, author_id
FROM book
ORDER BY id
LIMIT 20;
~~~

Sau đó, ứng dụng lấy tác giả cho từng sách:

~~~sql
SELECT id, name
FROM author
WHERE id = ?;
~~~

Nếu mỗi sách có một tác giả khác nhau và mỗi lần gọi đều phát sinh một truy vấn, tổng số câu SQL là:

\[
Q(N) = 1 + N
\]

Trong đó:

- **1** là truy vấn lấy danh sách sách.
- **N** là số truy vấn lấy tác giả cho từng sách.

Ví dụ:

| Số sách N | Query lấy sách | Query lấy tác giả | Tổng query |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 5 | 1 | 5 | 6 |
| 20 | 1 | 20 | 21 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

Tên gọi N+1 xuất phát từ cấu trúc này. Đây là số lần truy vấn database, không phải số request HTTP từ client. Một GraphQL operation duy nhất vẫn có thể tạo ra hàng trăm câu SQL bên trong server.

### Vì sao đây là vấn đề?

Database có thể thực hiện từng câu SELECT nhanh, nhưng mỗi lần round-trip đều có chi phí:

- Chuẩn bị và thực thi statement.
- Lấy kết nối từ connection pool.
- Gửi request tới database và chờ response.
- Chuyển đổi dữ liệu và ánh xạ kết quả.
- Giữ transaction hoặc connection lâu hơn.

Nếu mỗi query mất vài mili giây, hàng trăm query tuần tự hoặc nhiều lượt database có thể làm latency tăng rõ rệt. Việc query được chạy song song ở một số tầng không loại bỏ chi phí database, connection pool và tải hệ thống.

## 2. N+1 xuất hiện như thế nào trong GraphQL?

GraphQL thực thi operation theo cây field. Một field cha trả về object hoặc list object; mỗi object có thể tiếp tục có các field con cần resolve.

SDL:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}
~~~

Client gửi một operation:

~~~graphql
query {
  books(first: 20) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Operation chỉ có một lần gọi tới GraphQL endpoint, nhưng server cần resolve:

1. Field root Query.books để lấy danh sách Book.
2. Field Book.author cho từng Book.
3. Các field Author.id và Author.name trên object Author tương ứng.

Nếu Book.author truy vấn author bằng một SELECT riêng cho từng Book, N+1 xuất hiện.

### Sơ đồ luồng thực thi

~~~mermaid
flowchart TD
    A[GraphQL query books] --> B[Query.books resolver]
    B --> C[SELECT danh sách N Book]
    C --> D[Danh sách Book]
    D --> E1[Resolve author của Book 1]
    D --> E2[Resolve author của Book 2]
    D --> E3[Resolve author của Book N]
    E1 --> F1[SELECT Author 1]
    E2 --> F2[SELECT Author 2]
    E3 --> F3[SELECT Author N]
    F1 --> G[GraphQL response]
    F2 --> G
    F3 --> G
~~~

GraphQL không tự động gộp những field resolver có cùng kiểu hoặc cùng service call thành một truy vấn database. Mỗi field resolver được thiết kế để trả giá trị cho một source object. Nếu resolver gọi repository riêng, số query có thể tăng theo số source object.

## 3. Ví dụ N+1 với Spring for GraphQL

Một controller có thể được viết như sau:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    public BookController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public List<Book> books(@Argument Integer first) {
        return bookService.findFirst(first);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Hai method có trách nhiệm khác nhau:

- **books** lấy danh sách Book một lần.
- **author** được gọi cho từng Book có field author được chọn.

Nếu query trả về 20 Book, handler author có thể được gọi 20 lần. Nếu mỗi lần gọi authorService.findById phát một SELECT, tổng cộng sẽ có một query lấy sách và 20 query lấy tác giả.

Điểm quan trọng là số lần gọi field resolver và số câu SQL không phải lúc nào cũng giống nhau. Một resolver có thể dùng cache, đọc dữ liệu đã tải sẵn hoặc trả kết quả từ DataLoader. Ngược lại, một getter tưởng như đơn giản cũng có thể kích hoạt truy vấn ORM. Cần đo SQL thực tế để kết luận có N+1 hay không.

## 4. N+1 do JPA lazy loading

Không nhất thiết phải có một repository call rõ ràng trong @SchemaMapping mới xảy ra N+1. ORM có thể tải dữ liệu quan hệ khi getter của association được gọi.

Ví dụ entity:

~~~java
@Entity
public class BookEntity {

    @Id
    private Long id;

    private String title;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "author_id")
    private AuthorEntity author;

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public AuthorEntity getAuthor() {
        return author;
    }
}
~~~

Root resolver:

~~~java
@QueryMapping
public List<BookEntity> books() {
    return bookRepository.findAll();
}
~~~

Nếu schema có field Book.author và không có DataFetcher riêng, property fetcher mặc định có thể gọi getter getAuthor() trên từng BookEntity. Với association LAZY chưa được tải, Hibernate có thể thực hiện SELECT riêng cho từng tác giả khi property được truy cập.

Ví dụ SQL log:

~~~sql
-- Query đầu tiên
select b.id, b.title, b.author_id
from book b;

-- Sau đó, mỗi lần đọc association có thể phát sinh một query
select a.id, a.name
from author a
where a.id = ?;

select a.id, a.name
from author a
where a.id = ?;

select a.id, a.name
from author a
where a.id = ?;
~~~

Kết quả là một query lấy Book cộng thêm các query tải Author. Đây là N+1 do lazy loading.

### Không phải mọi association LAZY đều chắc chắn tạo N+1

Số query thực tế phụ thuộc vào:

- Association đã được tải trước hay chưa.
- Persistence context có entity tương ứng trong first-level cache hay không.
- Có bật second-level cache hay query cache hay không.
- Fetch plan của repository/query.
- Số lượng parent và số lượng child ID khác nhau.
- Cách GraphQL selection set yêu cầu field.

Ví dụ nhiều Book cùng tham chiếu một Author có thể không tạo N query khác nhau trong một persistence context nếu Hibernate đã giữ Author đó trong identity map. Tuy nhiên, không nên dựa vào cache ngẫu nhiên để bảo đảm hiệu năng. Khi số parent tăng và các relation khác nhau, N+1 vẫn có thể xuất hiện.

## 5. N+1 ở nhiều cấp quan hệ

N+1 có thể xuất hiện sâu hơn một cấp.

SDL:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
  reviews: [Review!]!
}

type Review {
  id: ID!
  content: String!
}
~~~

Client:

~~~graphql
query {
  books(first: 20) {
    title
    author {
      name
      reviews {
        content
      }
    }
  }
}
~~~

Giả sử có N Book và mỗi Book thuộc về một Author khác nhau. Mỗi Author có trung bình M Review. Nếu resolver tải từng quan hệ riêng:

- 1 query lấy Book.
- N query lấy Author.
- N query lấy danh sách Review của từng Author.

Tổng số query có thể gần:

\[
Q(N) = 1 + N + N
\]

Nếu mỗi Author có một field con khác cũng tải theo từng record, số query tiếp tục tăng. Với quan hệ một-nhiều và các resolver lồng nhau, số lần truy cập có thể tăng theo tổng số source object ở từng cấp, chứ không chỉ theo số phần tử root.

Không nên mô hình hóa chi phí chỉ bằng một công thức cố định cho mọi schema. Số query phụ thuộc cardinality, selection set, cache và fetch strategy. Điều cần quan sát là mỗi cấp resolver có phát sinh truy vấn riêng theo từng parent hay không.

## 6. N+1 phụ thuộc selection set của client

GraphQL chỉ resolve những field được chọn trong operation. Nếu client chỉ lấy id và title:

~~~graphql
query {
  books(first: 20) {
    id
    title
  }
}
~~~

Field author không được chọn, nên DataFetcher của Book.author không cần chạy. Khi đó các query tải Author có thể không phát sinh.

Nếu client thêm:

~~~graphql
author {
  id
  name
}
~~~

thì resolver hoặc property fetcher cho author mới được thực thi.

Đây là lý do N+1 đôi khi chỉ xuất hiện ở một số operation hoặc khi client mở rộng selection set. Một API có thể chạy nhanh với query danh sách cơ bản nhưng chậm khi client chọn thêm nhiều field quan hệ.

GraphQL trao quyền chọn field cho client, vì vậy server cần thiết kế data fetching sao cho hiệu quả khi các quan hệ được yêu cầu.

## 7. N+1 khác với việc có nhiều field resolver

Không phải cứ một field resolver được gọi N lần thì chắc chắn có N câu SQL.

Ví dụ resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorCache.get(book.getAuthorId());
}
~~~

Method có thể được gọi cho từng Book nhưng đọc dữ liệu từ cache, không truy vấn database mỗi lần.

Ngược lại, một DataFetcher duy nhất cũng có thể gọi nhiều repository method và phát sinh nhiều SQL. Do đó, cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| Resolver invocation count | Số lần handler/DataFetcher được gọi |
| SQL query count | Số câu SQL thực tế được gửi tới database |
| Database round-trip | Số lượt giao tiếp với database |
| GraphQL request count | Số operation/request từ client |

N+1 là vấn đề ở data access pattern. Cách đo quan trọng nhất là theo dõi SQL query count và cách nó thay đổi theo kích thước danh sách.

## 8. Vì sao pagination không tự giải quyết N+1?

Giới hạn số phần tử root giúp giới hạn mức độ nghiêm trọng, nhưng không loại bỏ cấu trúc N+1.

Ví dụ:

- Trang có 10 Book: 1 + 10 = 11 query.
- Trang có 20 Book: 1 + 20 = 21 query.
- Trang có 100 Book: 1 + 100 = 101 query.

Pagination giảm N từ 100 xuống 20, nhưng vẫn còn một query con cho mỗi parent.

Pagination vẫn rất quan trọng để kiểm soát payload size, memory và thời gian xử lý. Tuy nhiên, nên kết hợp pagination với batch loading hoặc fetch strategy phù hợp.

Với GraphQL connection có cursor pagination, server nên áp dụng giới hạn tối đa cho page size. Không nên cho client yêu cầu số lượng tùy ý, vì một operation lớn có thể làm tăng cả số object và chi phí N+1.

## 9. Tác động hiệu năng của N+1

N+1 ảnh hưởng nhiều lớp của hệ thống:

### Latency

Mỗi câu query có chi phí cố định và thời gian chờ database. Nếu các truy vấn được thực thi nối tiếp, tổng thời gian chờ tăng theo N. Nếu một phần thực thi song song, database vẫn phải xử lý nhiều statement và hệ thống vẫn chịu tải lớn hơn.

### Connection pool

Các resolver có thể cần kết nối trong quá trình truy vấn. Khi nhiều request đồng thời cùng phát sinh hàng trăm query, connection pool dễ bị bão hòa và request khác phải chờ.

### Database CPU và I/O

Nhiều query nhỏ vẫn tiêu thụ CPU, buffer cache, parse/plan và I/O. Database có thể xử lý một truy vấn JOIN hoặc một truy vấn IN hiệu quả hơn nhiều truy vấn riêng lẻ, tùy kế hoạch thực thi và dữ liệu.

### Memory và transaction duration

ORM có thể giữ nhiều entity trong persistence context. Nhiều truy vấn quan hệ kéo dài transaction và tăng số object cần quản lý. Điều này làm tăng memory pressure và nguy cơ giữ connection lâu.

### Khả năng mở rộng

Một operation chạy ổn với 5 object có thể suy giảm rõ rệt khi lên 100 hoặc 500 object. Khi số request đồng thời tăng, chi phí query nhân lên và tạo nút thắt ở database.

## 10. Cách nhận diện N+1 trong ứng dụng Spring for GraphQL

Không nên chỉ suy đoán từ code. Hãy đo số truy vấn với một operation đại diện.

### Bật SQL logging khi phát triển

Với Spring Boot và Hibernate, có thể bật log SQL:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
~~~

Để xem bind parameter trong môi trường phát triển:

~~~properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Tên logger có thể khác theo phiên bản Hibernate. Không nên bật log parameter nhạy cảm ở production vì có thể ghi lại dữ liệu cá nhân hoặc bí mật.

### Dùng Hibernate statistics

Có thể bật thống kê Hibernate trong môi trường kiểm thử:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Statistics giúp quan sát số prepared statement, entity load, collection fetch và các chỉ số liên quan. Cần reset hoặc đọc số liệu theo từng test/request để tránh trộn dữ liệu của nhiều operation.

### Dùng datasource proxy hoặc SQL inspector

Các công cụ như datasource proxy, P6Spy hoặc interceptor ở JDBC layer có thể đếm và ghi lại SQL. Đây là cách hữu ích khi cần biết chính xác một GraphQL operation đã phát bao nhiêu câu query.

### So sánh với kích thước danh sách khác nhau

Chạy cùng một operation với số lượng Book khác nhau:

| Kịch bản | Kích thước list | SQL query count kỳ vọng nếu có N+1 |
|---|---:|---:|
| A | 1 | Khoảng 2 |
| B | 10 | Khoảng 11 |
| C | 50 | Khoảng 51 |
| D | 100 | Khoảng 101 |

Nếu số query tăng gần tuyến tính theo số parent, hãy kiểm tra resolver hoặc association đang tải dữ liệu con.

Không nhất thiết số query phải chính xác bằng N+1 trong mọi môi trường. Cache, query batching của ORM, fetch plan và các truy vấn phụ khác có thể làm số liệu thay đổi. Dấu hiệu chính là query count tăng theo số parent ngoài dự kiến.

## 11. Các cách xử lý N+1

Không có một kỹ thuật duy nhất phù hợp với mọi quan hệ. Cần chọn theo cách dữ liệu được truy cập.

| Cách xử lý | Phù hợp khi | Lưu ý |
|---|---|---|
| DataLoader | Nhiều resolver cần tải cùng loại dữ liệu theo key | Gom các key thành một batch và phân phối kết quả |
| **@BatchMapping** | Field quan hệ trong annotated controller cần xử lý nhiều source object | Cú pháp Spring gọn cho batch field resolver |
| SQL JOIN/fetch join | Biết trước quan hệ cần tải trong một use case | Cẩn thận với collection và pagination |
| EntityGraph/fetch plan | Muốn khai báo quan hệ cần tải ở tầng repository | Tránh tải mọi association mặc định |
| DTO/projection query | Chỉ cần một tập field cụ thể cho response | Giảm entity graph và dữ liệu thừa |
| Cache | Dữ liệu lặp lại và có chiến lược invalidation phù hợp | Cache không thay thế batch cho mọi trường hợp |
| Pagination/limit | Giới hạn lượng dữ liệu client yêu cầu | Giảm quy mô, không loại bỏ N+1 |

### DataLoader

DataLoader cho phép nhiều resolver yêu cầu dữ liệu theo key trong cùng một execution được gom lại. Thay vì gọi repository một lần cho mỗi author ID, các resolver nạp key vào loader; khi dispatch, batch loader truy vấn nhiều ID cùng lúc.

Ví dụ về truy vấn batch:

~~~sql
SELECT id, name
FROM author
WHERE id IN (?, ?, ?, ...);
~~~

Khi đó, số query có thể giảm từ một query cho mỗi Book xuống một query cho một batch key, tùy kích thước batch và cách dispatch.

### @BatchMapping

Spring for GraphQL cung cấp **@BatchMapping** để khai báo một handler nhận danh sách source object và trả về kết quả tương ứng. Đây là cách thuận tiện khi field con cần tải dữ liệu theo nhóm.

### Fetch join hoặc EntityGraph

Có thể tải Book và Author trong cùng truy vấn:

~~~sql
SELECT b.id, b.title, a.id, a.name
FROM book b
JOIN author a ON a.id = b.author_id
ORDER BY b.id
LIMIT 20;
~~~

Một truy vấn JOIN có thể phù hợp khi quan hệ cần thiết đã biết và cardinality được kiểm soát. Nhưng không nên fetch join nhiều collection cùng lúc một cách tùy tiện, vì có thể tạo row multiplication, dữ liệu trùng, memory lớn hoặc vấn đề với pagination.

### DTO hoặc projection

Nếu operation chỉ cần Book title và Author name, có thể truy vấn projection trả đúng các cột đó. Điều này tránh phải tải toàn bộ entity và lazy relation.

Hãy cân nhắc projection khi một use case có selection set ổn định hoặc có thể dùng một read model phù hợp. GraphQL selection set có thể thay đổi theo client, vì vậy không phải lúc nào cũng nên tạo một projection riêng cho từng query.

## 12. DataLoader không làm biến mất mọi loại N+1

DataLoader giải quyết tốt việc gom các lần tải theo key, nhưng không tự tối ưu mọi truy vấn:

- Batch loader có thể tự viết SQL kém hiệu quả.
- Một batch lớn có thể vượt giới hạn parameter của database.
- Các field khác nhau có thể cần batch loader khác nhau.
- Dữ liệu không cùng một key space có thể không gom được.
- Resolver vẫn có thể phát sinh query riêng ngoài DataLoader.
- Batch loader có thể trả thiếu key hoặc phân phối sai kết quả nếu mapping không đúng.

DataLoader thường cần một batch function nhận danh sách key và trả về kết quả có thể ánh xạ lại cho từng key. Cần bảo đảm kết quả đúng key, kể cả khi database trả về thứ tự khác với thứ tự input hoặc không tìm thấy một số key.

Ngoài ra, cache của DataLoader thường có phạm vi một GraphQL execution/request. Không nên mặc định cache đó là cache dùng chung toàn ứng dụng. Phạm vi request giúp tránh việc dữ liệu hoặc quyền của người dùng này rò rỉ sang request khác.

## 13. Khi nào không cần xử lý N+1 bằng DataLoader?

Một số trường hợp có cách đơn giản hơn:

- Root resolver đã tải đầy đủ quan hệ cần dùng.
- Field là property scalar có sẵn trong DTO.
- Một query JOIN hoặc projection đáp ứng tốt use case.
- Số lượng phần tử được giới hạn rất nhỏ và đã đo được chi phí chấp nhận được.
- Field hiếm khi được chọn và có cache phù hợp.

Không nên thêm DataLoader cho mọi field chỉ vì module có hỗ trợ. Mỗi loader thêm vào cần batch function, lifecycle, error handling và test. Hãy đo trước, sau đó chọn giải pháp ít phức tạp nhất đáp ứng yêu cầu hiệu năng.

## 14. Kiểm thử để ngăn N+1 quay trở lại

Một integration test chỉ kiểm tra response đúng chưa đủ để phát hiện N+1. Có thể response hoàn toàn chính xác dù server phát hàng trăm câu SQL.

Nên có test hoặc performance check theo dõi số query:

1. Chuẩn bị dữ liệu có nhiều Book và Author khác nhau.
2. Thực thi GraphQL operation chọn field quan hệ gây nghi ngờ.
3. Đếm số SQL được phát trong phạm vi operation.
4. Lặp lại với nhiều kích thước danh sách.
5. Xác nhận query count không tăng tuyến tính ngoài dự kiến sau khi tối ưu.

Ví dụ test ý tưởng:

~~~java
@SpringBootTest
class BookQueryPerformanceTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldResolveAuthorsForBookList() {
        graphQlTester.document("""
                query {
                    books(first: 20) {
                        id
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("books")
            .entityList(BookView.class)
            .hasSize(20);
    }
}
~~~

Đoạn test trên kiểm tra response và số phần tử. Để phát hiện N+1, cần bổ sung SQL counter hoặc Hibernate statistics và assertion về số query theo test setup. Không nên hard-code một con số tuyệt đối nếu test còn có query khởi tạo dữ liệu hoặc framework query phụ; hãy reset counter ngay trước operation và chỉ đo phạm vi cần thiết.

Trong production, tracing hoặc APM có thể liên kết GraphQL operation với database spans. Dữ liệu này giúp xác định field nào tạo nhiều query và operation nào có latency cao.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Một GraphQL request chỉ tạo một query database | Một operation có thể gọi nhiều DataFetcher và phát nhiều SQL |
| Có @SchemaMapping thì chắc chắn bị N+1 | Chỉ bị khi cách resolve dữ liệu tạo nhiều lần tải không cần thiết |
| Không có @SchemaMapping thì không có N+1 | Property fetcher có thể gọi getter JPA lazy và kích hoạt query |
| Pagination giải quyết triệt để N+1 | Pagination chỉ giới hạn N |
| Resolver được gọi N lần đồng nghĩa có N SQL | Resolver có thể dùng cache hoặc dữ liệu đã tải |
| JOIN luôn tốt hơn DataLoader | JOIN có thể tạo row multiplication và khó kết hợp pagination |
| DataLoader tự động batch mọi repository call | Chỉ những lần tải đi qua loader mới được gom |
| Cache làm N+1 biến mất trong mọi trường hợp | Cache miss, scope và key khác nhau vẫn có thể tạo nhiều query |
| Response đúng nghĩa là query hiệu quả | Cần đo query count và latency riêng |

## 16. Quy trình điều tra N+1

Khi một GraphQL operation chậm:

1. Ghi lại operation và selection set thực tế.
2. Xác định root field trả về list hoặc nhiều parent object.
3. Liệt kê các field con có thể tải dữ liệu từ repository hoặc lazy relation.
4. Đếm số lần handler được gọi và số câu SQL thực tế.
5. Chạy cùng operation với N nhỏ và N lớn để xem query count thay đổi ra sao.
6. Xác định truy vấn nào lặp lại theo từng parent.
7. Chọn DataLoader, **@BatchMapping**, fetch join, EntityGraph hoặc projection tùy quan hệ.
8. Kiểm tra kết quả batch được ánh xạ đúng key/source object.
9. Đo lại SQL count, latency và memory sau thay đổi.
10. Thêm kiểm thử hoặc giám sát để phát hiện hồi quy.

N+1 select là hệ quả của việc tải dữ liệu liên quan riêng cho từng object cha. Trong GraphQL, hiện tượng này thường xuất hiện ở field lồng nhau khi một root query trả về list và mỗi field resolver hoặc JPA lazy getter lại truy vấn database. Một operation có thể tạo rất nhiều SQL dù client chỉ gửi một request. Hãy quan sát query count theo kích thước danh sách, xác định đúng field gây tải lặp và chọn cách xử lý phù hợp như DataLoader, **@BatchMapping**, fetch plan hoặc projection. Mục tiêu là giữ response đúng với schema trong khi số lần truy cập database tăng có kiểm soát.
