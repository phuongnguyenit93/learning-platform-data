# Mapping field của nested type

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích cách GraphQL thực thi field lồng nhau trên object cha.
- Phân biệt cơ chế đọc property mặc định với resolver được khai báo bằng `@SchemaMapping`.
- Ánh xạ nested field bằng `@SchemaMapping` và xác định đúng `typeName`, `field`.
- Nhận source object bằng tham số Java thông thường hoặc `@Source`.
- Bind arguments của nested field bằng `@Argument`.
- Resolve field trả về object, list hoặc giá trị được tính toán.
- Xử lý khác biệt giữa Java DTO và GraphQL object type.
- Nhận biết khi nào cần `@BatchMapping` hoặc DataLoader để tránh N+1.
- Kiểm thử nested mapping bằng `GraphQlTester` và chẩn đoán lỗi phổ biến.

## 1. Nested field trong GraphQL là gì?

GraphQL cho phép một field trả về object hoặc danh sách object. Client có thể tiếp tục chọn các field con trên object được trả về. Những field con đó được gọi là nested field.

Ví dụ schema:

~~~graphql
type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Query {
    book(id: ID!): Book
}
~~~

Client có thể lấy sách, tác giả và các review trong cùng một operation:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
        author {
            id
            name
        }
        reviews {
            id
            rating
            comment
        }
    }
}
~~~

Operation có một field root là `Query.book`. Kết quả của field này là object `Book`. GraphQL tiếp tục resolve các field được chọn bên trong object đó:

- `Book.id` và `Book.title` lấy dữ liệu từ object sách.
- `Book.author` trả về object `Author`.
- `Author.id` và `Author.name` được resolve trên object tác giả.
- `Book.reviews` trả về danh sách `Review`.
- `Review.id`, `Review.rating` và `Review.comment` được resolve trên từng review.

GraphQL không yêu cầu client gọi một endpoint riêng cho mỗi nested field. Runtime đi theo selection set của operation và resolve từng field trên object cha tương ứng.

## 2. Source object và quá trình resolve nested field

Khi GraphQL resolve một field trên object, runtime có một giá trị nguồn gọi là **source object**. Với nested field, source object thường là object cha mà field đang được chọn.

Ví dụ, sau khi `Query.book` trả về một đối tượng Java `Book`, runtime dùng đối tượng đó làm source khi resolve `Book.author`.

Có thể hình dung luồng xử lý:

~~~mermaid
flowchart TD
    A["Query.book(id)"] --> B["Book source object"]
    B --> C["Resolve Book.title"]
    B --> D["Resolve Book.author"]
    B --> E["Resolve Book.reviews"]
    D --> F["Author source object"]
    F --> G["Resolve Author.name"]
    E --> H["Review source objects"]
    H --> I["Resolve Review.rating / comment"]
~~~

Một method `@SchemaMapping` cho nested field nhận source object tương ứng. Ví dụ, method xử lý `Book.author` nhận một `Book`, sau đó trả về `Author`.

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Ở đây:

- `Book` là source object.
- `author` là field đang được resolve.
- `Author` là giá trị trả về cho field đó.

Source object không nhất thiết là entity database. Nó có thể là DTO, projection, record, Map hoặc một kiểu Java khác mà resolver trước đó trả về.

## 3. Property mapping mặc định và khi nào cần @SchemaMapping

Không phải nested field nào cũng cần viết controller method. GraphQL Java có thể đọc giá trị từ source object thông qua cơ chế property data fetching mặc định.

Ví dụ Java bean:

~~~java
public class Book {

    private String id;
    private String title;
    private Author author;

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

Với schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author
}
~~~

Nếu resolver `Query.book` trả về một `Book` có property `author`, GraphQL có thể lấy giá trị đó qua property accessor mà không cần method `@SchemaMapping` riêng.

Property mapping phù hợp khi:

- Giá trị field đã có sẵn trên source object.
- Cách đọc dữ liệu chỉ là truy cập property đơn giản.
- Không cần gọi service hoặc repository riêng.
- Không cần xử lý logic bổ sung cho field.

Dùng `@SchemaMapping` khi field cần hành vi riêng, ví dụ:

- Tải quan hệ từ service hoặc repository.
- Tính toán giá trị dựa trên nhiều thuộc tính.
- Áp dụng quy tắc nghiệp vụ.
- Nhận arguments do client truyền.
- Gọi một nguồn dữ liệu khác hoặc trả về kết quả bất đồng bộ.

Method mapping đã đăng ký cho field sẽ cung cấp DataFetcher xử lý field đó. Hãy tránh tạo cả property logic và resolver riêng với hai nguồn dữ liệu khác nhau mà không có chủ đích rõ ràng.

## 4. Ánh xạ nested field bằng @SchemaMapping

`@SchemaMapping` là annotation của Spring for GraphQL dùng để kết nối method trong controller với một field của GraphQL object type.

Có thể chỉ rõ cả type và field:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Hai thuộc tính chính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `typeName` | Tên GraphQL object type chứa field |
| `field` | Tên field trong object type đó |

Với ví dụ trên, mapping cuối cùng là `Book.author`.

Tên trong annotation phải khớp với SDL. `Book` ở đây là GraphQL type name, còn `Book` trong tham số Java là source class. Hai tên có thể giống nhau nhưng chúng thuộc hai hệ thống tên khác nhau.

### 4.1. Suy luận field từ tên method

Nếu tên method trùng tên field, có thể bỏ `field`:

~~~java
@SchemaMapping(typeName = "Book")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Spring suy luận field là `author` từ tên method. Nếu tên method khác tên field trong SDL, hãy chỉ rõ:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author loadBookAuthor(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

### 4.2. Suy luận typeName từ source parameter

Khi không khai báo `typeName`, Spring for GraphQL có thể suy luận tên GraphQL type từ kiểu Java của source parameter.

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Nếu source parameter là Java `Book`, Spring mặc định suy luận `typeName` là `Book`. Tên method `author` được dùng làm tên field.

Cách viết này gọn khi Java source class và GraphQL object type có cùng tên. Nếu dùng DTO như `BookView` nhưng GraphQL type vẫn tên `Book`, cần khai báo `typeName` tường minh. Chủ đề suy luận typeName từ source type được phân tích riêng trong bài tương ứng của chương Annotated Controller.

## 5. Nhận source object bằng @Source

Trong annotated controller, tham số source thường được nhận trực tiếp bằng kiểu Java:

~~~java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

Có thể dùng `@Source` để đánh dấu tường minh tham số source:

~~~java
import org.springframework.graphql.data.method.annotation.Source;

@SchemaMapping(typeName = "Book", field = "author")
public Author author(@Source Book book) {
    return authorService.findById(book.getAuthorId());
}
~~~

`@Source` hữu ích khi method có nhiều tham số và muốn làm rõ tham số nào đại diện cho object cha. Các tham số khác có thể được bind từ argument hoặc lấy từ GraphQL context.

Ví dụ, nested field nhận thêm argument `locale`:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book")
public String localizedTitle(
        @Source Book book,
        @Argument("locale") String locale) {

    return translationService.translate(book.getTitle(), locale);
}
~~~

Trong ví dụ, `book` là source object còn `locale` là argument của field `localizedTitle`. Không nhầm argument với property của object cha: `locale` do client truyền trong operation, còn `book` được GraphQL runtime cung cấp làm source.

## 6. Mapping field trả về một object liên quan

Một nested field phổ biến là quan hệ giữa hai object, ví dụ sách có tác giả.

SDL:

~~~graphql
type Author {
    id: ID!
    name: String!
}

type Book {
    id: ID!
    title: String!
    author: Author!
}

type Query {
    book(id: ID!): Book
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
~~~

Controller:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }
}
~~~

Khi client chọn `author`, GraphQL truyền `Book` tương ứng vào method. Method lấy `authorId`, gọi service và trả về `Author`. Sau đó GraphQL tiếp tục resolve các field con của `Author`, chẳng hạn `id` và `name`.

Không cần tự tạo response JSON cho nested object. Chỉ trả về object Java; GraphQL runtime sẽ tiếp tục xử lý selection set của object đó.

## 7. Mapping field trả về danh sách object

Một field nested có thể trả về danh sách, ví dụ các review của sách:

~~~graphql
type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}
~~~

Resolver:

~~~java
@Controller
class BookReviewController {

    private final ReviewService reviewService;

    BookReviewController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
~~~

GraphQL gọi resolver cho từng source `Book` xuất hiện trong selection set. Mỗi lần gọi trả về danh sách `Review` của cuốn sách tương ứng.

Client có thể chọn các field của từng review:

~~~graphql
query {
    book(id: "book-42") {
        title
        reviews {
            rating
            comment
        }
    }
}
~~~

Kiểu trả về Java cần tương thích với GraphQL field type. Nếu SDL khai báo `[Review!]!`, resolver nên trả một danh sách không null và không chứa phần tử null. Khi không có review, trả danh sách rỗng thường phù hợp hơn trả null.

## 8. Mapping field được tính toán

Nested field không nhất thiết phải ánh xạ trực tiếp tới một cột hoặc property trong database. Có thể dùng resolver để tính giá trị từ source object.

Ví dụ SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    displayLabel: String!
    isLongTitle: Boolean!
}
~~~

Resolver:

~~~java
@Controller
class BookComputedFieldController {

    @SchemaMapping(typeName = "Book")
    public String displayLabel(Book book) {
        return book.getTitle() + " (" + book.getId() + ")";
    }

    @SchemaMapping(typeName = "Book")
    public boolean isLongTitle(Book book) {
        return book.getTitle().length() > 40;
    }
}
~~~

Tên method quyết định tên field mặc định. Nếu muốn làm rõ mapping, có thể khai báo `field`:

~~~java
@SchemaMapping(typeName = "Book", field = "isLongTitle")
public boolean calculateLongTitle(Book book) {
    return book.getTitle().length() > 40;
}
~~~

+## 9. Arguments của nested field

Nested field có thể nhận arguments giống root field. Ví dụ một sách có thể yêu cầu một số lượng review giới hạn:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

Client:

~~~graphql
query {
    book(id: "book-42") {
        reviews(first: 5) {
            id
            rating
        }
    }
}
~~~

Resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        @Source Book book,
        @Argument("first") Integer first) {

    int limit = first != null ? first : 10;
    return reviewService.findByBookId(book.getId(), limit);
}
~~~

`@Argument("first")` bind giá trị argument `first` của field `Book.reviews`. `@Source` cung cấp object `Book` đang được resolve.

Nếu SDL đã khai báo default value, GraphQL áp dụng default khi client bỏ qua argument. Trong ví dụ Java, giá trị dự phòng chỉ minh họa cách bảo vệ service ở tầng ứng dụng; nên thống nhất default giữa schema và service để tránh hai nơi có quy tắc khác nhau.

Với argument nullable, hãy xác định rõ ý nghĩa của việc bỏ qua argument và truyền `null`. Nếu cần phân biệt hai trạng thái đó trong mutation hoặc filter, sử dụng kiểu binding phù hợp với phiên bản Spring for GraphQL đang dùng.

## 10. Dùng DTO hoặc projection cho nested source

Java class đại diện source object không bắt buộc phải trùng tên GraphQL type hoặc entity database.

Ví dụ DTO:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

Nếu resolver dùng `BookView` làm source, hãy chỉ rõ GraphQL type:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Nếu bỏ `typeName`, Spring có thể suy luận theo tên Java source class `BookView`, trong khi schema dùng `Book`. Kết quả là mapping không khớp.

Dùng DTO giúp tách GraphQL contract khỏi entity persistence. Tuy nhiên, cần nhất quán mapping type và field, đặc biệt khi một DTO được dùng trong nhiều GraphQL type hoặc nhiều nested field.

## 11. Nhiều nested field trong cùng controller

Một controller có thể chứa nhiều resolver cho cùng một GraphQL type. Có thể đặt `@SchemaMapping(typeName = "...")` ở cấp class để dùng type mặc định:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class BookFieldsController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    BookFieldsController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }

    @SchemaMapping
    public String displayLabel(Book book) {
        return book.getTitle() + " (" + book.getId() + ")";
    }
}
~~~

Các method lần lượt ánh xạ tới:

- `Book.author`
- `Book.reviews`
- `Book.displayLabel`

Nếu một method xử lý type khác, có thể ghi đè ở method:

~~~java
@SchemaMapping(typeName = "Author", field = "books")
public List<Book> books(Author author) {
    return bookService.findByAuthorId(author.getId());
}
~~~

Nên tổ chức controller theo nhóm GraphQL type để người đọc dễ xác định source và field. Khi controller xử lý nhiều type khác nhau, khai báo `typeName` tường minh tại method giúp tránh nhầm lẫn.

## 12. Nested field và nguy cơ N+1

Một nested resolver có thể được gọi nhiều lần trong cùng operation. Nếu mỗi lần resolver đều gọi repository riêng, ứng dụng có thể phát sinh N+1 query.

Ví dụ client yêu cầu danh sách sách và tác giả của từng sách:

~~~graphql
query {
    books {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

Nếu `Query.books` trả về 50 sách, resolver `Book.author` có thể được gọi 50 lần. Nếu mỗi lần gọi `authorService.findById` thực hiện một truy vấn database, ứng dụng có thể chạy một truy vấn lấy danh sách sách cộng thêm 50 truy vấn tác giả.

Có thể bắt đầu bằng resolver đơn giản khi dữ liệu ít hoặc quan hệ đã được tải sẵn. Khi số lượng source tăng, hãy dùng batch loading.

### 12.1. Dùng @BatchMapping cho quan hệ cùng loại

Ví dụ:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

Thay vì tải tác giả riêng cho từng sách, Spring gom các source `Book` thành một batch. Service có thể truy vấn tác giả theo danh sách `authorId` rồi trả về map từ source book tới author.

`@BatchMapping` là một cách khai báo batch resolver cho nested field. Với field đã được xử lý bằng `@BatchMapping`, không đăng ký thêm một `@SchemaMapping` khác cho cùng field nếu không có chủ đích rõ ràng.

### 12.2. Khi nào dùng DataLoader?

DataLoader phù hợp khi cần kiểm soát rõ quá trình batch và cache theo request, hoặc khi nhiều field cần tải cùng một loại dữ liệu.

Dù dùng `@SchemaMapping`, `@BatchMapping` hay DataLoader, cần giữ các nguyên tắc:

- Batch query theo tập ID thay vì lặp truy vấn từng source.
- Giữ thứ tự hoặc ánh xạ kết quả đúng với key tương ứng.
- Xử lý key không có dữ liệu.
- Giới hạn cache trong phạm vi phù hợp, thường là request.
- Đo số lượng query và thời gian thực thi để xác định bottleneck thực tế.

Không nên dùng batch loading chỉ vì một field là nested. Hãy xác định có truy vấn lặp hay không, sau đó chọn cách tối ưu phù hợp.

## 13. Nullability và lỗi khi resolve nested field

Kiểu trả về trong SDL quyết định cách GraphQL xử lý null.

Ví dụ:

~~~graphql
type Book {
    author: Author
    reviews: [Review!]!
}
~~~

- `author: Author` có thể trả null nếu sách không có tác giả hoặc resolver không tìm thấy quan hệ theo nghiệp vụ.
- `reviews: [Review!]!` yêu cầu danh sách không null và không chứa phần tử null. Khi không có review, trả `[]`.
- Nếu một field non-null trả null hoặc phát sinh lỗi thực thi, GraphQL áp dụng null propagation lên parent field gần nhất có thể nhận null.

Resolver nên có quy tắc rõ ràng:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findOptionalById(book.getAuthorId())
            .orElse(null);
}
~~~

Ví dụ này chỉ phù hợp nếu schema cho phép `author` nullable. Nếu schema khai báo `author: Author!`, trả null sẽ tạo execution error và có thể làm mất dữ liệu ở cấp cha.

Khi service ném exception, có thể dùng `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler` để ánh xạ lỗi thành GraphQL error phù hợp. Không nên che giấu lỗi hạ tầng bằng cách trả null nếu điều đó làm client hiểu nhầm rằng dữ liệu đơn giản là không tồn tại.

## 14. Kiểm thử nested field mapping

Nên kiểm thử qua GraphQL operation thật để xác minh schema, root resolver và nested resolver hoạt động cùng nhau.

Ví dụ operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
        reviews {
            rating
        }
    }
}
~~~

Với `GraphQlTester`:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
                reviews {
                    rating
                }
            }
        }
        """)
        .execute();

response.path("book.author.name")
        .entity(String.class)
        .isEqualTo("An Nguyen");

response.path("book.reviews[0].rating")
        .entity(Integer.class)
        .isEqualTo(5);
~~~

Các test nên bao gồm:

- Nested field được lấy trực tiếp từ property mặc định.
- Nested field được resolve qua `@SchemaMapping`.
- Source object được truyền đúng vào method.
- Argument của nested field được bind đúng.
- Field trả về object hoặc list đúng với SDL.
- Source object là DTO có tên khác GraphQL type.
- Quan hệ không tồn tại được xử lý đúng nullability.
- Batch resolver trả kết quả đúng cho nhiều source object.
- Lỗi từ service được chuyển thành GraphQL error theo chính sách ứng dụng.

Nếu chỉ kiểm tra method Java bằng unit test, có thể bỏ sót lỗi tên `typeName`, tên field hoặc runtime wiring. Ít nhất một integration test qua `GraphQlTester` nên xác minh mapping ở cấp GraphQL.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nested field trả null dù service có dữ liệu | Mapping sai type hoặc field, hoặc property không được đọc đúng | Kiểm tra SDL, `typeName`, `field` và source object |
| Method `@SchemaMapping` không được gọi | Tên type/field không khớp hoặc controller không được Spring quản lý | Kiểm tra annotation và `@Controller` |
| Field được đọc từ property cũ thay vì service | Chưa đăng ký đúng method mapping hoặc đang kiểm tra nhầm field | Xác nhận DataFetcher thực tế của field |
| Source parameter nhận sai object | Chữ ký method hoặc source mapping không phù hợp | Kiểm tra kiểu Java và dùng `@Source` tường minh |
| Argument nested field luôn null | Argument không khai báo trong SDL hoặc tên `@Argument` sai | Đối chiếu schema và operation |
| DTO không map được với GraphQL type | Tên DTO khác tên object type | Khai báo `typeName` rõ ràng |
| Danh sách nested field phát sinh nhiều query | Resolver gọi service riêng cho từng source | Dùng `@BatchMapping` hoặc DataLoader |
| Resolver trả null gây mất cả object cha | Field được khai báo non-null | Điều chỉnh nullability hoặc xử lý lỗi phù hợp |
| Field có trong schema nhưng không có dữ liệu | Chưa có property hoặc DataFetcher phù hợp | Bổ sung property resolver hoặc `@SchemaMapping` |

## 16. Quy trình triển khai nested field mapping

Khi thêm một nested field, có thể thực hiện theo trình tự:

1. **Xác định GraphQL parent type.** Field thuộc object type nào?
2. **Xác định field và kiểu trả về.** Field trả scalar, object hay list?
3. **Kiểm tra source object.** Root resolver trả về Java type nào?
4. **Kiểm tra property mặc định.** Nếu dữ liệu đã có sẵn, property fetcher có đáp ứng được không?
5. **Viết `@SchemaMapping` khi cần logic riêng.** Chỉ rõ `typeName` và `field` nếu tên Java khác SDL.
6. **Nhận source và arguments.** Dùng source parameter hoặc `@Source`, bind argument bằng `@Argument`.
7. **Xử lý nullability.** Đảm bảo giá trị trả về phù hợp với dấu `!` trong SDL.
8. **Đánh giá số lượng truy vấn.** Nếu resolver bị gọi lặp theo từng source, cân nhắc `@BatchMapping` hoặc DataLoader.
9. **Kiểm thử operation.** Dùng `GraphQlTester` kiểm tra field, argument, object và list.
10. **Theo dõi hiệu năng và lỗi.** Đo truy vấn database, thời gian resolver và GraphQL error path.

## 17. Tổng kết

Nested field là field được chọn bên trong một object mà field cha trả về. GraphQL runtime dùng object cha làm source để resolve field con. Khi giá trị đã có trên Java bean hoặc Map, cơ chế property mapping mặc định có thể đáp ứng mà không cần controller method riêng.

Khi cần gọi service, tính toán dữ liệu hoặc nhận arguments, dùng `@SchemaMapping` để ánh xạ method tới field của GraphQL object type. Source parameter đại diện object cha; `@Source` có thể làm vai trò đó rõ ràng hơn, còn `@Argument` bind dữ liệu client truyền cho nested field. Với DTO có tên khác GraphQL type, khai báo `typeName` tường minh. Nếu nested resolver tạo nhiều truy vấn lặp, dùng `@BatchMapping` hoặc DataLoader. Kiểm thử bằng operation GraphQL thực tế giúp xác nhận toàn bộ mapping hoạt động đúng với schema và dữ liệu.


