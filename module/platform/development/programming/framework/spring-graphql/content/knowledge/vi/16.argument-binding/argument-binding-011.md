# Direct field access

Trong GraphQL, sau khi một field cha trả về object, GraphQL tiếp tục resolve các field con được client chọn. Nếu giá trị của field con đã có sẵn trong object nguồn, server thường không cần viết thêm resolver. GraphQL Java cung cấp cơ chế **PropertyDataFetcher** mặc định để đọc property từ source object; Spring for GraphQL sử dụng cơ chế này khi không có DataFetcher tường minh cho field.

Đây là cách triển khai phổ biến cho các field đơn giản như **Book.title**, **Book.id** hoặc **Author.name**. Một handler của **@QueryMapping** có thể trả về Java record, DTO, JavaBean hoặc Map; các field con sẽ được đọc trực tiếp theo tên property tương ứng. Khi field cần truy vấn dữ liệu khác, tính toán hoặc áp dụng policy riêng, có thể chuyển sang **@SchemaMapping** hoặc **@BatchMapping**.

Bài này giải thích cách direct field access hoạt động, những kiểu Java có thể làm source object, quy tắc đặt tên, cách xử lý object lồng nhau và list, giới hạn của property fetcher, cùng các lưu ý về nullability, bảo mật, JPA lazy loading và kiểm thử.

## 1. Direct field access là gì?

Giả sử schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Root field **Query.book** cần một DataFetcher để tìm sách. Có thể dùng **@QueryMapping**:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Giả sử method trả về:

~~~java
public record Book(
        String id,
        String title,
        Integer publishedYear) {
}
~~~

Client query:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    publishedYear
  }
}
~~~

Sau khi **Query.book** trả về một instance Book, GraphQL cần lấy ba field con. Nếu ứng dụng không đăng ký DataFetcher riêng cho **Book.id**, **Book.title** và **Book.publishedYear**, GraphQL Java dùng property data fetcher mặc định để đọc các giá trị từ object Book.

Không cần viết ba method **@SchemaMapping** chỉ để trả lại đúng các property đã có sẵn. Đó là ý nghĩa của direct field access trong trường hợp này.

### Luồng xử lý

~~~mermaid
flowchart TD
    A[Client query Query.book] --> B[@QueryMapping book]
    B --> C[Book source object]
    C --> D[Resolve Book.id]
    C --> E[Resolve Book.title]
    C --> F[Resolve Book.publishedYear]
    D --> G[PropertyDataFetcher]
    E --> G
    F --> G
    G --> H[Response]
~~~

Root field **Query.book** vẫn cần một resolver hoặc DataFetcher thích hợp để tạo source object. Direct field access thường phát huy tác dụng ở các field con có giá trị nằm trong source object.

## 2. PropertyDataFetcher hoạt động như thế nào?

GraphQL Java dùng **PropertyDataFetcher** để tìm giá trị theo tên field GraphQL trên source object. Với field có tên **title**, property fetcher tìm cách đọc property tương ứng từ object.

Các kiểu source thường gặp:

- JavaBean có getter như **getTitle()**.
- Boolean property theo quy ước JavaBean như **isAvailable()**.
- Java record có accessor cùng tên component như **title()**.
- Object có method truy cập property theo tên phù hợp.
- Map có key trùng với tên field GraphQL.
- Kiểu dữ liệu khác có property mà cơ chế truy cập của GraphQL Java nhận diện được.

Property fetcher giúp schema field và property của source object được nối với nhau mà không cần viết resolver thủ công cho từng field.

Ví dụ JavaBean:

~~~java
public class Book {

    private String id;
    private String title;

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
~~~

Với SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
}
~~~

Property **id** được đọc qua getter **getId()**, còn **title** được đọc qua **getTitle()**.

Nên ưu tiên getter hoặc accessor rõ ràng. Không nên dựa vào việc GraphQL Java có thể truy cập một private field bằng reflection, vì cách đó làm code khó hiểu và có thể phụ thuộc cấu trúc class, module access hoặc phiên bản thư viện.

## 3. Direct access với Java record

Java record rất phù hợp làm output DTO cho GraphQL vì mỗi component có accessor công khai cùng tên component.

Ví dụ:

~~~java
public record Author(
        String id,
        String name,
        String biography) {
}

public record Book(
        String id,
        String title,
        Integer pageCount,
        Author author) {
}
~~~

SDL:

~~~graphql
type Author {
  id: ID!
  name: String!
  biography: String
}

type Book {
  id: ID!
  title: String!
  pageCount: Int
  author: Author
}
~~~

Resolver root:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

Khi client yêu cầu:

~~~graphql
query {
  book(id: "book-01") {
    title
    author {
      name
      biography
    }
  }
}
~~~

GraphQL Java có thể đọc **title()** và **author()** từ record Book. Sau đó, với object Author được trả về, nó đọc tiếp **name()** và **biography()**.

Không cần viết:

~~~java
@SchemaMapping(typeName = "Book", field = "title")
public String title(Book book) {
    return book.title();
}
~~~

Method trên chỉ trả lại property đã có sẵn, nên thường không mang lại giá trị bổ sung.

### Record lồng nhau

Các record có thể lồng nhau nhiều cấp:

~~~java
public record Address(
        String street,
        String city,
        String postalCode) {
}

public record Author(
        String id,
        String name,
        Address address) {
}

public record Book(
        String id,
        String title,
        Author author) {
}
~~~

GraphQL resolve lần lượt Book, Author và Address theo selection set. Mỗi object trở thành source object cho các field con của nó.

Direct access không giới hạn ở một cấp. Nó có thể được áp dụng xuyên suốt cây object nếu mỗi property đã có trong source và kiểu trả về tương thích với schema.

## 4. Direct access với JavaBean

Ứng dụng có thể dùng DTO hoặc class JavaBean thay cho record:

~~~java
public class BookView {

    private String id;
    private String title;
    private AuthorView author;

    public BookView(String id, String title, AuthorView author) {
        this.id = id;
        this.title = title;
        this.author = author;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public AuthorView getAuthor() {
        return author;
    }
}
~~~

Với schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
}
~~~

Các getter cung cấp property tương ứng. Tên field GraphQL là **author**, nên getter **getAuthor()** phù hợp.

### Boolean property

JavaBean thường biểu diễn boolean primitive bằng accessor **isAvailable()**:

~~~java
public class BookView {

    private boolean available;

    public boolean isAvailable() {
        return available;
    }
}
~~~

Schema:

~~~graphql
type Book {
  available: Boolean!
}
~~~

Với Boolean wrapper, quy ước phổ biến là **getAvailable()**:

~~~java
private Boolean available;

public Boolean getAvailable() {
    return available;
}
~~~

Hãy dùng quy ước JavaBean nhất quán để property được nhận diện rõ ràng. Nếu một class có accessor không theo quy ước hoặc tên không khớp schema, hãy dùng DTO rõ ràng hoặc resolver tường minh.

## 5. Direct access từ Map

PropertyDataFetcher cũng có thể đọc dữ liệu từ Map. Đây là lựa chọn hữu ích khi source được tạo từ projection, dữ liệu tổng hợp hoặc cấu trúc linh hoạt.

Ví dụ:

~~~java
@QueryMapping
public Map<String, Object> book(@Argument String id) {
    return Map.of(
            "id", id,
            "title", "Spring GraphQL",
            "pageCount", 320);
}
~~~

SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  pageCount: Int
}
~~~

Với Map, key cần khớp tên field GraphQL:

- **id** tương ứng field **Book.id**.
- **title** tương ứng field **Book.title**.
- **pageCount** tương ứng field **Book.pageCount**.

Map lồng nhau cũng hoạt động theo cùng cách:

~~~java
@QueryMapping
public Map<String, Object> book(@Argument String id) {
    Map<String, Object> author = Map.of(
            "id", "author-01",
            "name", "An Nguyen");

    return Map.of(
            "id", id,
            "title", "Spring GraphQL",
            "author", author);
}
~~~

GraphQL có thể đọc key **author** để lấy Map con, sau đó đọc **id** và **name** từ Map đó.

Map linh hoạt nhưng không có kiểm tra kiểu ở compile time. Sai tên key có thể khiến property fetcher trả null và dẫn đến lỗi nếu field GraphQL là non-null. Với cấu trúc ổn định, record/DTO thường an toàn hơn.

## 6. Tên property Java và tên field GraphQL

Direct access hoạt động thuận lợi nhất khi tên property Java trùng tên field GraphQL.

| Field GraphQL | Java property/accessor |
|---|---|
| **id** | **getId()** hoặc record accessor **id()** |
| **title** | **getTitle()** hoặc **title()** |
| **publishedYear** | **getPublishedYear()** hoặc **publishedYear()** |
| **available** | **isAvailable()** hoặc **getAvailable()** |
| **author** | **getAuthor()** hoặc **author()** |

Ví dụ SDL:

~~~graphql
type Book {
  displayTitle: String!
}
~~~

Nếu Java class chỉ có **getTitle()**, property mặc định tên **title** không khớp với **displayTitle**. Có hai hướng:

1. Đổi DTO để có property **displayTitle**.
2. Viết **@SchemaMapping** để ánh xạ field GraphQL **displayTitle** sang giá trị Java **title**.

Ví dụ resolver tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "displayTitle")
public String displayTitle(Book book) {
    return book.getTitle();
}
~~~

Nên giữ tên nhất quán nếu không có lý do domain hoặc API cần khác biệt. Khi tên khác nhau có chủ đích, resolver tường minh làm mapping dễ đọc hơn.

## 7. Direct access với object và collection lồng nhau

Một property có thể trả về object khác hoặc collection. GraphQL tiếp tục resolve selection set trên từng giá trị trả về.

Java:

~~~java
public record Review(
        String id,
        String content,
        Integer rating) {
}

public record Book(
        String id,
        String title,
        List<Review> reviews) {
}
~~~

SDL:

~~~graphql
type Review {
  id: ID!
  content: String!
  rating: Int!
}

type Book {
  id: ID!
  title: String!
  reviews: [Review!]!
}
~~~

Query:

~~~graphql
query {
  book(id: "book-01") {
    title
    reviews {
      content
      rating
    }
  }
}
~~~

Property fetcher đọc list **reviews** từ Book. GraphQL sau đó resolve **content** và **rating** cho từng Review.

Direct access phù hợp khi danh sách đã có sẵn trong object trả về. Nếu việc lấy reviews cần truy vấn database theo book ID, property getter có thể kích hoạt tải dữ liệu hoặc field cần một resolver chuyên biệt.

### List chứa Map hoặc DTO

Các phần tử list có thể là record, JavaBean hoặc Map miễn là mỗi phần tử cung cấp các property cần thiết. GraphQL không yêu cầu tất cả source object phải cùng một class nếu schema và runtime type resolution hỗ trợ các kiểu trả về đó.

Với interface hoặc union, server còn phải xác định object type cụ thể tương ứng. Direct property access không thay thế runtime type resolution cho abstract type.

## 8. Direct access không đồng nghĩa với truy vấn database

PropertyDataFetcher đọc một giá trị từ source object đã có. Nó không tự biết cách gọi repository hoặc tạo SQL để tải dữ liệu.

Ví dụ:

~~~java
@QueryMapping
public Book book(@Argument String id) {
    return bookRepository.findById(id).orElse(null);
}
~~~

Nếu Book đã có **title**, **pageCount** và **status**, các field này có thể được đọc trực tiếp. Nếu **author** là một JPA lazy relation, việc gọi getter **getAuthor()** có thể khiến ORM tải thêm dữ liệu.

Điều đó có thể tạo N+1:

1. Query lấy danh sách 100 Book.
2. Client chọn **author** cho mỗi Book.
3. Property fetcher gọi getter author cho từng Book.
4. Mỗi getter kích hoạt một truy vấn riêng nếu association chưa được tải.

Direct access giúp giảm code resolver, nhưng không bảo đảm số lượng truy vấn database tối ưu. Cần xem xét mô hình dữ liệu và cách ORM tải quan hệ.

### Khi cần batch loading

Nếu field cần tải dữ liệu theo nhiều source object, có thể dùng **@BatchMapping**:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(List<Book> books) {
    List<String> authorIds = books.stream()
            .map(Book::getAuthorId)
            .distinct()
            .toList();

    Map<String, Author> authors = authorService.findAllByIds(authorIds);

    Map<Book, Author> result = new HashMap<>();
    for (Book book : books) {
        result.put(book, authors.get(book.getAuthorId()));
    }
    return result;
}
~~~

Ở đây **@BatchMapping** thay thế việc đọc property author đơn giản bằng một lần tải theo nhóm. Hãy dùng batch mapping khi có chi phí tải dữ liệu cần gom; nếu author đã là property được tải sẵn và không phát sinh chi phí đáng kể, direct access có thể đủ.

## 9. Khi nào cần @SchemaMapping thay cho direct access?

Direct access phù hợp với field phản ánh trực tiếp dữ liệu đã có trên source object. Dùng **@SchemaMapping** khi field cần một hành vi riêng.

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Trả **book.title** đã có trong record | Direct property access |
| Trả **author.name** đã có trong object Author | Direct property access |
| Đổi tên field GraphQL so với property Java | **@SchemaMapping** hoặc DTO có tên phù hợp |
| Tính **fullName** từ firstName và lastName | **@SchemaMapping** |
| Tải author từ authorId | **@SchemaMapping** hoặc **@BatchMapping** |
| Kiểm tra quyền trước khi trả field | Resolver có authorization phù hợp hoặc field security |
| Gọi service bên ngoài để tạo giá trị | **@SchemaMapping** |
| Gom tải dữ liệu của nhiều parent | **@BatchMapping** hoặc DataLoader |

Ví dụ field tính toán:

~~~graphql
type Author {
  firstName: String!
  lastName: String!
  fullName: String!
}
~~~

~~~java
@SchemaMapping(typeName = "Author", field = "fullName")
public String fullName(Author author) {
    return author.firstName() + " " + author.lastName();
}
~~~

**fullName** không phải property có sẵn trong source object, nên resolver cung cấp giá trị tính toán.

### Resolver tường minh thay thế default property fetcher

Khi một field có DataFetcher được đăng ký rõ ràng, GraphQL sử dụng DataFetcher đó cho field. Điều này cho phép ứng dụng kiểm soát hành vi thay vì đọc property mặc định.

Không nên viết resolver chỉ để trả lại cùng property nếu không có lý do. Mỗi resolver thêm vào đều là một điểm cần bảo trì và kiểm thử.

## 10. Nullability và property không tồn tại

Schema quyết định field có được phép trả null hay không.

~~~graphql
type Book {
  title: String!
  subtitle: String
}
~~~

Nếu source object có **title = null** trong khi SDL khai báo **String!**, GraphQL không thể trả null hợp lệ cho field đó. Execution phát sinh lỗi và null có thể lan lên field cha theo quy tắc non-null propagation.

Nếu **subtitle** nullable, property có giá trị null là hợp lệ:

~~~json
{
  "data": {
    "book": {
      "title": "Spring GraphQL",
      "subtitle": null
    }
  }
}
~~~

Nếu property không tìm thấy trên source object hoặc Map không có key tương ứng, property fetcher có thể trả null. Với field non-null, điều đó trở thành lỗi execution; với field nullable, response chứa null.

Vì vậy:

- Bảo đảm mọi field non-null có property tương ứng luôn cung cấp giá trị.
- Khai báo nullable nếu dữ liệu thực tế có thể thiếu.
- Kiểm tra tên getter, record component và Map key khi nhận null ngoài dự kiến.
- Không dùng default giả tạo chỉ để che giấu dữ liệu thiếu nếu domain không cho phép.

## 11. Bảo mật khi dùng direct property access

Một object Java có thể chứa nhiều property hơn những gì API nên công khai. Nếu trả trực tiếp entity hoặc domain object, cần chú ý rằng các property có thể được đọc bởi GraphQL nếu chúng được khai báo trong schema và property fetcher truy cập được.

Ví dụ entity:

~~~java
public class Customer {

    private String id;
    private String displayName;
    private String passwordHash;
    private String internalNote;

    public String getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public String getPasswordHash() {
        return passwordHash;
    }

    public String getInternalNote() {
        return internalNote;
    }
}
~~~

Schema công khai chỉ nên định nghĩa những field cần thiết:

~~~graphql
type Customer {
  id: ID!
  displayName: String!
}
~~~

GraphQL không tự thêm field **passwordHash** hoặc **internalNote** vào schema chỉ vì getter tồn tại. Tuy nhiên, nếu schema vô tình công khai field nhạy cảm, direct property access có thể khiến giá trị được trả ra mà không có resolver riêng để kiểm tra quyền.

Các nguyên tắc:

- Dùng output DTO/record chỉ chứa dữ liệu được phép công khai.
- Không trả entity persistence có các getter nhạy cảm nếu không cần.
- Kiểm tra quyền truy cập cho field nhạy cảm trước khi đưa vào response.
- Không xem việc client không chọn field là cơ chế bảo vệ dữ liệu.
- Giữ authorization ở server; client có thể tự thay đổi selection set.

Với field cần policy riêng, hãy dùng resolver có kiểm tra quyền hoặc cơ chế field security phù hợp. Một getter đơn thuần không phải nơi thích hợp để thực thi authorization phức tạp.

## 12. Hạn chế khi trả trực tiếp JPA entity

Direct access có thể thuận tiện khi trả entity, nhưng entity persistence thường mang các đặc điểm không phù hợp để trở thành API contract:

- Lazy association có thể kích hoạt truy vấn khi getter được gọi.
- Quan hệ hai chiều có thể tạo vòng tham chiếu.
- Entity chứa field nội bộ không nên công khai.
- Cấu trúc database thay đổi có thể làm response API thay đổi ngoài ý muốn.
- Getter có thể có side effect hoặc phụ thuộc persistence session.

Ví dụ quan hệ:

~~~java
class BookEntity {
    AuthorEntity author;
}

class AuthorEntity {
    List<BookEntity> books;
}
~~~

Nếu GraphQL query đi từ Book sang Author rồi quay lại Author.books, cần chú ý vòng quan hệ và chi phí tải dữ liệu. GraphQL selection set có giới hạn theo operation, nhưng lazy loading và các truy vấn quan hệ vẫn có thể tạo chi phí lớn.

Một cách tổ chức rõ ràng hơn là chuyển entity thành output DTO:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

DTO chỉ chứa dữ liệu cần thiết cho API. Field author có thể được tải bằng resolver hoặc batch mapping theo authorId. Điều này giúp kiểm soát truy vấn và không phụ thuộc vào toàn bộ entity graph.

## 13. Property fetcher và field mapping có thể cùng tồn tại

Một object type có thể dùng direct access cho phần lớn field và dùng resolver riêng cho một số field.

SDL:

~~~graphql
type Book {
  id: ID!
  title: String!
  author: Author
  reviewCount: Int!
}
~~~

Java:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}
~~~

Resolver:

~~~java
@Controller
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book", field = "reviewCount")
    public int reviewCount(Book book) {
        return reviewService.countByBookId(book.id());
    }
}
~~~

**Book.id** và **Book.title** được đọc trực tiếp từ record. **Book.author** và **Book.reviewCount** có DataFetcher tường minh vì cần truy vấn service.

Đây là cách kết hợp phổ biến: để property fetcher xử lý field đơn giản, chỉ viết resolver cho field cần logic riêng.

## 14. Kiểm thử direct field access

GraphQlTester có thể kiểm tra rằng các property trên source object được đưa vào response đúng như mong đợi.

Ví dụ:

~~~java
@SpringBootTest
class BookDirectAccessTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReadRecordProperties() {
        graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        id
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

Nên kiểm tra:

1. Record component được đọc đúng theo tên field.
2. JavaBean getter được ánh xạ đúng.
3. Boolean property theo quy ước getter hoạt động như mong muốn.
4. Map key khớp tên field GraphQL.
5. Object và list lồng nhau được resolve đầy đủ.
6. Property null phù hợp với nullability trong SDL.
7. Field non-null bị thiếu tạo lỗi GraphQL như dự kiến.
8. Field có **@SchemaMapping** dùng resolver tường minh.
9. Field nhạy cảm không bị lộ qua output type.
10. Lazy association hoặc field có chi phí tải dữ liệu không tạo N+1 ngoài dự kiến.

Khi cần kiểm tra số truy vấn SQL, nên bổ sung test ở service/repository hoặc bật thống kê truy vấn trong môi trường test. Chỉ kiểm tra response GraphQL không đủ để kết luận direct access có hiệu quả về database.

## 15. Những lỗi thường gặp khi dùng direct field access

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Field trả null | Không tìm thấy property/getter hoặc Map key sai | Kiểm tra tên field và accessor |
| Record component không được đọc | Tên component không khớp schema hoặc accessor không tương thích | Kiểm tra record component và GraphQL field |
| Boolean luôn null | Getter không theo quy ước hoặc property sai tên | Dùng **isX()** cho boolean hoặc **getX()** phù hợp |
| Field non-null gây execution error | Property thực tế null hoặc không tồn tại | Kiểm tra dữ liệu và nullability |
| Query phát sinh nhiều SQL | Getter lazy relation tải từng object | Dùng fetch plan hoặc batch loading |
| Field nhạy cảm bị trả ra | Schema công khai property không nên công khai | Thu hẹp output DTO và kiểm tra authorization |
| Getter gây side effect | Logic truy vấn hoặc nghiệp vụ bị đặt trong accessor | Chuyển sang service/resolver tường minh |
| Tên API khác tên Java | Property fetcher không tìm được property | Đổi DTO hoặc viết **@SchemaMapping** |
| Trả entity tạo vòng quan hệ | Entity graph có quan hệ hai chiều | Dùng DTO và giới hạn field mapping |
| Viết resolver chỉ trả lại getter | Tạo code không cần thiết | Để default property fetcher xử lý |

## 16. Quy trình chọn direct access

Khi thêm field vào GraphQL object type:

1. Xác định field có sẵn trong source object hay cần tính toán/tải dữ liệu.
2. Nếu property đã tồn tại, kiểm tra getter, record accessor hoặc Map key tương ứng.
3. Bảo đảm tên property phù hợp với field GraphQL.
4. Kiểm tra kiểu Java tương thích với scalar, enum, object hoặc list trong SDL.
5. Chọn nullability theo khả năng dữ liệu thực tế.
6. Dùng record/DTO làm output model khi cần kiểm soát dữ liệu công khai.
7. Dùng **@SchemaMapping** nếu cần logic riêng, đổi tên hoặc authorization.
8. Dùng **@BatchMapping**/DataLoader nếu field cần tải dữ liệu cho nhiều parent.
9. Kiểm tra lazy loading, query count và quan hệ entity.
10. Viết GraphQlTester cho property access, nullability và field resolver tùy chỉnh.

Direct field access giúp GraphQL trả các property đã có sẵn trên source object mà không cần viết DataFetcher riêng cho từng field. GraphQL Java thực hiện việc này bằng PropertyDataFetcher; Spring for GraphQL cho phép kết hợp mặc định đó với các handler **@QueryMapping** và **@SchemaMapping**. Hãy dùng record/DTO hoặc JavaBean có accessor rõ ràng, giữ tên field nhất quán và chuyển sang resolver tường minh khi cần tải dữ liệu, tính toán hoặc kiểm tra quyền. Như vậy schema vừa gọn, vừa giữ được quyền kiểm soát đối với dữ liệu và hiệu năng.
