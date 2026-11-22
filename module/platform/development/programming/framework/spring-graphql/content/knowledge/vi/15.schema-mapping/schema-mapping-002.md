# Parent source object

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích source object là gì trong quá trình GraphQL thực thi một field.
- Theo dõi cách giá trị từ field cha trở thành source cho field con.
- Nhận source object trong phương thức `@SchemaMapping` của Spring for GraphQL.
- Phân biệt source object với argument, GraphQLContext và local context.
- Biết khi nào GraphQL có thể đọc property trực tiếp và khi nào cần resolver riêng.
- Mapping source object khi tên Java class khác GraphQL type.
- Xử lý trường hợp parent source null và tránh phụ thuộc vào state dùng chung.

## 1. Parent source object là gì?

GraphQL query thường có cấu trúc lồng nhau. Một field có thể trả về object, rồi client tiếp tục chọn các field con của object đó.

Ví dụ, client yêu cầu một quyển sách cùng tác giả:

~~~graphql
query {
  book(id: "b-01") {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Server thực thi query theo cây field:

- Field `Query.book` tìm và trả về một đối tượng Book.
- Field `Book.author` dùng đối tượng Book vừa nhận để tìm Author.
- Field `Author.name` đọc tên từ đối tượng Author vừa được trả về.

Trong GraphQL Java, giá trị object được truyền từ field cha sang quá trình phân giải các field con được gọi là *source object* hoặc *parent source*. Nó là dữ liệu đầu vào của resolver hiện tại, thường chính là giá trị mà resolver của field cha trả về.

Có thể hình dung luồng dữ liệu:

~~~mermaid
flowchart TD
    A[Query.book id=b-01] -->|trả về Book| B[Source của Book fields]
    B --> C[Book.id]
    B --> D[Book.title]
    B --> E[Book.author]
    E -->|trả về Author| F[Source của Author fields]
    F --> G[Author.id]
    F --> H[Author.name]
~~~

Điểm cần nhớ: source object của `Book.author` là đối tượng Book, còn source object của `Author.name` là đối tượng Author. Mỗi cấp trong cây query nhận source tương ứng với object cha của cấp đó.

## 2. Source object được tạo ra từ đâu?

Source object thường đến từ giá trị mà DataFetcher của field cha trả về.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Java model:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final String authorId;

    public Book(String id, String title, String authorId) {
        this.id = id;
        this.title = title;
        this.authorId = authorId;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }
}

public class Author {

    private final String id;
    private final String name;

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
}
~~~

Resolver cho Query:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }
}
~~~

Khi `bookService.findById(id)` trả về một đối tượng Book, GraphQL dùng đối tượng đó làm source cho các field được chọn bên trong `book`, chẳng hạn `id`, `title` và `author`.

Nếu client chỉ chọn `id` và `title`, server không cần phân giải field `author`. Nếu client chọn thêm `author.name`, quá trình thực thi tiếp tục đi sâu vào object Book và Author.

Source object là giá trị runtime thực tế, không phải tên type trong SDL và cũng không phải chuỗi ID mà client truyền vào.

## 3. Nhận source object bằng @SchemaMapping

Trong Spring for GraphQL, một phương thức `@SchemaMapping` có thể nhận parent source thông qua tham số Java thông thường.

Ví dụ:

~~~java
@Controller
public class BookFieldController {

    private final AuthorService authorService;

    public BookFieldController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Trong method này:

- `Book book` là source object của field đang được phân giải.
- `book.getAuthorId()` đọc thông tin liên kết từ object cha.
- `authorService.findById(...)` tải Author liên quan.
- Đối tượng Author trả về trở thành source object cho các field con như `Author.id` và `Author.name`.

Với tên mặc định, Spring suy luận mapping từ tên method `author` và kiểu source parameter `Book`, tương ứng với `Book.author`.

Có thể khai báo mapping tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author resolveAuthor(Book source) {
    return authorService.findById(source.getAuthorId());
}
~~~

Ở đây, `typeName` xác định GraphQL type sở hữu field; `field` xác định field được ánh xạ. Tên biến `source` hay `book` không ảnh hưởng mapping, vì kiểu tham số mới là thông tin quan trọng.

## 4. Source object khác với argument

Source object và argument có thể cùng xuất hiện trong một resolver, nhưng chúng có nguồn gốc khác nhau:

- Source object đến từ kết quả của field cha.
- Argument đến từ giá trị client truyền cho field hiện tại.

Ví dụ SDL:

~~~graphql
type Book {
  id: ID!
  reviews(first: Int = 10, minRating: Int): [Review!]!
}
~~~

Client:

~~~graphql
query {
  book(id: "b-01") {
    reviews(first: 5, minRating: 4) {
      id
      rating
    }
  }
}
~~~

Controller:

~~~java
@Controller
public class BookReviewController {

    private final ReviewService reviewService;

    public BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public List<Review> reviews(
            Book book,
            @Argument Integer first,
            @Argument Integer minRating) {

        return reviewService.findByBook(
                book.getId(), first, minRating);
    }
}
~~~

Ở method trên:

| Tham số | Nguồn dữ liệu | Ý nghĩa |
|---|---|---|
| `Book book` | Field cha `Query.book` | Parent source object |
| `@Argument Integer first` | Argument của `Book.reviews` | Số review tối đa |
| `@Argument Integer minRating` | Argument của `Book.reviews` | Điều kiện lọc rating |

`book.getId()` lấy định danh từ source object. `first` và `minRating` lấy từ chính field `reviews` mà client đang gọi.

Không nên nhầm argument `id` của field cha với source object. Khi `Query.book` đã trả về Book, resolver con nhận object Book; nó không tự động nhận lại argument của field cha như một source parameter.

Nếu field con cần một giá trị từ field cha mà object chưa chứa, hãy cân nhắc đưa dữ liệu cần thiết vào source DTO, dùng local context hoặc truy vấn lại từ service theo khóa có sẵn.

## 5. Source object khác với GraphQLContext

GraphQLContext là context dùng chung trong phạm vi một GraphQL request, thường chứa thông tin được đưa vào từ tầng xác thực hoặc interceptor.

Source object là dữ liệu của parent field trong cây query. Hai khái niệm phục vụ hai mục đích khác nhau:

| Thành phần | Phạm vi | Ví dụ |
|---|---|---|
| Source object | Một nhánh field trong cây thực thi | Book đang được phân giải |
| Field argument | Một field cụ thể | `first = 5` |
| GraphQLContext | Toàn bộ GraphQL request | Người dùng hiện tại, correlation ID |
| Local context | Một nhánh cha-con được truyền tiếp có chủ đích | Metadata riêng cho các field con |

Có thể nhận giá trị trong GraphQLContext bằng `@ContextValue`:

~~~java
@SchemaMapping
public List<Review> reviews(
        Book book,
        @ContextValue("currentUserId") String currentUserId) {

    return reviewService.findVisibleReviews(
            book.getId(), currentUserId);
}
~~~

`currentUserId` phải được đưa vào GraphQLContext bởi tầng xác thực hoặc interceptor đáng tin cậy. Không nên lấy danh tính bảo mật từ argument tùy ý do client gửi lên.

Một method có thể nhận đồng thời source object, argument và context. Hãy dùng đúng cơ chế cho đúng loại dữ liệu để chữ ký method thể hiện rõ nguồn gốc của từng tham số.

## 6. Nhận source qua DataFetchingEnvironment

Nếu cần truy cập nhiều thông tin ở mức GraphQL Java, method có thể nhận `DataFetchingEnvironment` và đọc source bằng `getSource()`.

Ví dụ:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(DataFetchingEnvironment environment) {
    Book book = environment.getSource();
    String locale = environment.getArgument("locale");

    return authorService.findById(book.getAuthorId(), locale);
}
~~~

Các API liên quan:

| API | Dữ liệu |
|---|---|
| `getSource()` | Source object của field hiện tại |
| `getArgument(name)` | Argument của field hiện tại |
| `getGraphQlContext()` | Context của GraphQL request |
| `getLocalContext()` | Local context được truyền từ field cha |
| `getField()` | Thông tin field đang thực thi |
| `getSelectionSet()` | Các field con được client yêu cầu |

Khi dùng `DataFetchingEnvironment` thay cho source parameter có kiểu cụ thể, nên khai báo `typeName` tường minh vì Spring không còn source Java type để suy ra GraphQL parent type.

Với controller thông thường, tham số source có kiểu cụ thể thường dễ đọc và an toàn kiểu hơn. Dùng `DataFetchingEnvironment` khi thực sự cần truy cập nhiều metadata của quá trình thực thi.

## 7. PropertyDataFetcher sử dụng source object như thế nào?

Không phải mọi field con đều cần một method `@SchemaMapping`. GraphQL Java có thể dùng `PropertyDataFetcher` mặc định để đọc property tương ứng từ source object.

Ví dụ Java class:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final Author author;

    public Book(String id, String title, Author author) {
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

    public Author getAuthor() {
        return author;
    }
}
~~~

Nếu Query trả về Book và client yêu cầu:

~~~graphql
query {
  book(id: "b-01") {
    title
    author {
      name
    }
  }
}
~~~

GraphQL có thể:

1. Đọc `Book.title` từ getter `getTitle()`.
2. Đọc `Book.author` từ getter `getAuthor()`.
3. Dùng object Author trả về làm source cho field `Author.name`.
4. Đọc `Author.name` từ getter tương ứng.

Trong trường hợp này, không cần viết resolver riêng cho `Book.author` nếu quan hệ Author đã có sẵn trong object Book và property mapping đáp ứng đúng schema.

PropertyDataFetcher thường hữu ích với POJO có getter hoặc property phù hợp. Nếu source là Map, giá trị có thể được lấy theo key tương ứng. Cách truy cập cụ thể phụ thuộc cấu trúc source object và khả năng property access của GraphQL Java.

## 8. Khi nào cần resolver riêng cho field con?

Hãy dùng `@SchemaMapping` khi field không có sẵn trong source object hoặc cần logic truy xuất, tính toán hay kiểm tra riêng.

Ví dụ, Book chỉ lưu `authorId`, không giữ cả object Author:

~~~java
public class Book {

    private final String id;
    private final String title;
    private final String authorId;

    // Constructor và getter
}
~~~

Resolver tải Author từ service:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Một số trường hợp nên có resolver riêng:

- Quan hệ cần tải từ database hoặc service bên ngoài.
- Field là giá trị tính toán từ nhiều property.
- Field phụ thuộc argument của client.
- Field cần áp dụng authorization hoặc quy tắc nghiệp vụ riêng.
- Field cần batch loading để tránh N+1.
- Tên field GraphQL khác property Java và cần mapping rõ ràng.

Không nên tạo resolver cho mọi field chỉ để lặp lại getter. Điều đó làm tăng số method và khiến cấu trúc mapping khó theo dõi.

## 9. Source object có thể là DTO, projection hoặc entity

GraphQL không yêu cầu source object phải là một JPA entity. Nó có thể là bất kỳ Java object nào mà DataFetcher của field cha trả về và resolver con có thể sử dụng.

Ví dụ, GraphQL type công khai là Book nhưng service trả về DTO:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

Resolver:

~~~java
@QueryMapping
public BookView book(@Argument String id) {
    return bookService.findViewById(id);
}

@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView source) {
    return authorService.findById(source.authorId());
}
~~~

Trong ví dụ này:

- GraphQL type là `Book`.
- Java source object là `BookView`.
- `typeName = "Book"` xác định field thuộc GraphQL type Book.
- Tham số `BookView source` nhận object thực tế được trả về từ Query.

Cách tiếp cận này giúp schema API độc lập với mô hình lưu trữ. Entity, DTO và projection có thể thay đổi mà không bắt buộc đổi tên GraphQL type.

Khi source class khác GraphQL type, hãy khai báo `typeName` rõ ràng để tránh phụ thuộc vào quy ước suy luận tên.

## 10. Nhiều field con có thể dùng cùng parent source

Một parent object có thể là source cho nhiều field con trong cùng một query.

Ví dụ:

~~~graphql
query {
  book(id: "b-01") {
    title
    author {
      name
    }
    reviews(first: 5) {
      rating
    }
    relatedBooks {
      id
      title
    }
  }
}
~~~

Các resolver `Book.author`, `Book.reviews` và `Book.relatedBooks` đều nhận cùng một source object Book về mặt dữ liệu đầu vào. Mỗi resolver có thể dùng các property khác nhau để tải dữ liệu tương ứng.

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}

@SchemaMapping
public List<Review> reviews(
        Book book,
        @Argument Integer first) {
    return reviewService.findFirstByBookId(book.getId(), first);
}

@SchemaMapping
public List<Book> relatedBooks(Book book) {
    return bookService.findRelated(book.getId());
}
~~~

Các field con là những nhánh riêng của cây thực thi. Không nên giả định resolver `author` luôn chạy trước `reviews`, hoặc resolver này có thể thay đổi source object để resolver khác đọc kết quả.

Nếu nhiều field cần dùng chung một dữ liệu phụ, hãy cân nhắc DataLoader, batch mapping hoặc một DTO chứa dữ liệu đã được chuẩn bị phù hợp. Tránh dùng field mutable của controller để lưu kết quả tạm giữa các resolver.

## 11. Source object và @BatchMapping

Khi một Query trả về nhiều Book và client yêu cầu Author của từng Book, mỗi field `Book.author` có thể cần tải dữ liệu liên quan. Nếu mỗi resolver truy vấn database riêng, số lần truy vấn có thể tăng theo số lượng Book.

`@BatchMapping` nhận một danh sách source object thay vì một source object đơn:

~~~java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Mono<Map<Book, Author>> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        return authorService.findAllByIds(authorIds)
                .collectMap(
                        Author::getId,
                        Function.identity()
                )
                .map(authorsById -> {
                    Map<Book, Author> result = new HashMap<>();

                    for (Book book : books) {
                        result.put(
                                book,
                                authorsById.get(book.getAuthorId()));
                    }

                    return result;
                });
    }
}
~~~

Spring dùng danh sách Book làm tập source object cho batch field `Book.author`. Map kết quả liên kết từng source Book với Author tương ứng.

Khi dùng Map, key phải có equality và hashCode ổn định để liên kết đúng object. Nếu trả về danh sách hoặc Flux theo thứ tự, kết quả phải tương ứng với thứ tự source đầu vào theo hợp đồng batch mapping.

Source object vẫn là Book; khác biệt là batch resolver nhận nhiều source object cùng lúc để tải dữ liệu theo lô.

## 12. Parent source null và null propagation

Nếu field cha trả về null, GraphQL không có object source để tiếp tục phân giải các field con của object đó.

Ví dụ SDL:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
}
~~~

Nếu Query `book` không tìm thấy dữ liệu và trả null, response có thể là:

~~~json
{
  "data": {
    "book": null
  }
}
~~~

Các resolver con như `Book.id` và `Book.title` không được gọi cho một parent object không tồn tại.

Nếu field cha được khai báo non-null:

~~~graphql
type Query {
  book(id: ID!): Book!
}
~~~

và resolver vẫn trả null hoặc hoàn tất rỗng, GraphQL tạo lỗi thực thi và áp dụng null propagation lên parent gần nhất cho phép null. Nếu root field cũng non-null, giá trị null có thể lan tới data của toàn operation.

Do đó, cần đồng bộ ba yếu tố:

- Kiểu trả về của parent resolver.
- Nullability trong SDL.
- Cách xử lý không tìm thấy dữ liệu ở service.

Đừng dùng một source object rỗng hoặc object giả chỉ để tránh null nếu điều đó làm sai ý nghĩa nghiệp vụ.

## 13. Source object không phải nơi lưu state của request

Controller Spring thường là singleton bean. Nhiều GraphQL request có thể được xử lý đồng thời, vì vậy không nên lưu source object hiện tại vào field mutable của controller.

Ví dụ không an toàn:

~~~java
@Controller
public class BookController {

    private Book currentBook;

    @SchemaMapping
    public Author author(Book book) {
        this.currentBook = book;
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Hai request đồng thời có thể ghi đè `currentBook` của nhau. Resolver khác đọc field này có thể nhận nhầm dữ liệu.

Hãy dùng source parameter của từng method:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Nếu cần truyền metadata từ field cha xuống các field con, hãy dùng local context hoặc cơ chế context được hỗ trợ thay vì state mutable dùng chung. Nếu dữ liệu cần dùng trên toàn request, dùng GraphQLContext theo đúng phạm vi.

## 14. Kiểm thử source mapping

Một integration test nên xác nhận source object do parent resolver trả về được truyền đúng tới resolver con.

Ví dụ schema:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
~~~

Controller:

~~~java
@Controller
public class BookController {

    @QueryMapping
    public Book book(@Argument String id) {
        return new Book("b-01", "GraphQL in Practice", "a-01");
    }

    @SchemaMapping
    public Author author(Book source) {
        return new Author(
                source.getAuthorId(),
                "Nguyen An");
    }
}
~~~

Test bằng `GraphQlTester`:

~~~java
@Test
void shouldPassParentBookAsSourceToAuthorResolver() {
    graphQlTester.document("""
            query {
                book(id: "b-01") {
                    id
                    author {
                        id
                        name
                    }
                }
            }
            """)
            .execute()
            .path("book.author.id")
            .entity(String.class)
            .isEqualTo("a-01");
}
~~~

Các tình huống nên kiểm thử:

1. Parent resolver trả về object và field con nhận đúng source.
2. Field con sử dụng property mapping mặc định khi property có sẵn.
3. Field con tải dữ liệu bằng `@SchemaMapping`.
4. Source Java class khác GraphQL type và được ánh xạ bằng `typeName`.
5. Source kết hợp với argument và GraphQLContext.
6. Parent resolver trả null và field con không được phân giải.
7. Nullability của parent và child tạo response đúng theo schema.
8. Batch mapping liên kết kết quả đúng với từng source object.

## 15. Nguyên tắc thiết kế parent source object

Khi thiết kế resolver và model trả về từ field cha:

- Trả về object có đủ dữ liệu để các field con cần thiết hoạt động.
- Dùng DTO hoặc projection nếu không muốn expose trực tiếp entity persistence.
- Dùng property mapping mặc định cho field đã có sẵn trên source object.
- Dùng `@SchemaMapping` khi field cần truy xuất hoặc tính toán riêng.
- Phân biệt source parameter với `@Argument`, `@ContextValue` và `@LocalContextValue`.
- Khai báo `typeName` khi Java source type khác tên GraphQL type.
- Không lưu source object vào state mutable của singleton controller.
- Dùng `@BatchMapping` hoặc DataLoader khi nhiều parent object cần tải dữ liệu liên quan.
- Thiết kế nullability nhất quán giữa parent resolver, child field và SDL.
- Kiểm thử cả trường hợp parent tồn tại, parent null và dữ liệu liên quan bị thiếu.

## Kết luận

Parent source object là giá trị mà field cha trả về và được truyền vào quá trình phân giải các field con. Trong Spring for GraphQL, source thường được nhận dưới dạng tham số Java trong phương thức `@SchemaMapping`. Kiểu source giúp Spring suy luận GraphQL type sở hữu field; có thể dùng `typeName` khi tên Java khác tên schema.

Hiểu đúng source object giúp phân biệt dữ liệu parent với argument và request context, tận dụng PropertyDataFetcher khi property đã có sẵn, đồng thời dùng resolver riêng hoặc `@BatchMapping` khi cần tải dữ liệu liên quan. Thiết kế source rõ ràng, không lưu state dùng chung và xử lý nullability nhất quán sẽ giúp cây thực thi GraphQL dễ kiểm soát và mở rộng.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Schema Mapping](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java — DataFetchingEnvironment API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/DataFetchingEnvironment.html)
- [GraphQL Java — PropertyDataFetcher API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/schema/PropertyDataFetcher.html)
