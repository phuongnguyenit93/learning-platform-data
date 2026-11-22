# typeName mặc định từ source type trong Annotated Controller

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích source object trong một field mapping của Spring for GraphQL.
- Hiểu cách Spring suy luận `typeName` từ kiểu Java của source parameter.
- Phân biệt `typeName` được suy luận với tên field được suy luận từ tên method.
- Viết `@SchemaMapping` mà không cần khai báo `typeName` khi tên Java type và GraphQL type khớp nhau.
- Dùng `@Source` để thể hiện rõ tham số source trong method signature.
- Đặt `@SchemaMapping` ở cấp class để cung cấp `typeName` mặc định cho các method.
- Ghi đè `typeName` tại method khi một controller xử lý nhiều GraphQL type.
- Nhận biết trường hợp DTO, interface hoặc base class khiến typeName suy luận không đúng mong muốn.
- Hiểu cách suy luận source type trong `@BatchMapping`.
- Kiểm thử và chẩn đoán lỗi mapping giữa Java source type và GraphQL object type.

## 1. Source type trong Annotated Controller là gì?

Khi GraphQL thực thi một field lồng nhau, field đó thường được resolve dựa trên object cha đang được xử lý. Object cha này được gọi là **source object**.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    displayLabel: String!
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Client gửi operation:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

Quá trình xử lý có thể diễn ra như sau:

1. Field `Query.book` được resolve và trả về một đối tượng Java đại diện cho sách.
2. GraphQL runtime dùng đối tượng đó làm source khi resolve field con `Book.author`.
3. Method controller ánh xạ tới field `Book.author` nhận source object của sách.
4. Method trả về tác giả để GraphQL tiếp tục resolve `Author.name`.

Trong Spring for GraphQL, tham số source của method `@SchemaMapping` thường là object cha:

~~~java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return bookService.findAuthor(book.id());
    }
}
~~~

Method nhận `Book` làm source object và trả về `Author`. Spring cần xác định method này xử lý field nào trên GraphQL type nào. Nếu không khai báo tường minh, framework có thể suy luận hai thông tin đó từ method signature và tên method.

## 2. Spring suy luận typeName mặc định từ source parameter

`@SchemaMapping` có hai thuộc tính quan trọng:

- `typeName`: tên GraphQL object type chứa field cần resolve.
- `field`: tên field GraphQL cần ánh xạ tới method.

Khi không khai báo `typeName`, Spring for GraphQL suy luận tên type từ kiểu Java của source parameter trong method. Ví dụ:

~~~java
@SchemaMapping
public Author author(Book book) {
    return bookService.findAuthor(book.id());
}
~~~

Với source parameter có kiểu Java `Book`, Spring suy luận:

| Thành phần | Giá trị suy luận |
| --- | --- |
| Source parameter type | `Book` |
| GraphQL `typeName` | `Book` |
| Tên method | `author` |
| GraphQL `field` | `author` |

Method được hiểu tương đương với mapping tường minh:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return bookService.findAuthor(book.id());
}
~~~

Vì vậy, nếu tên simple class của source type trùng với tên GraphQL object type, có thể bỏ `typeName` để code gọn hơn.

Điều cần nhớ là `typeName` được suy luận từ **kiểu Java khai báo cho source parameter**, không phải từ tên service, tên repository hoặc tên method trả về.

## 3. Phân biệt suy luận typeName và field

Spring có thể suy luận cả `typeName` và `field`, nhưng chúng đến từ hai thông tin khác nhau:

- `typeName` mặc định đến từ source parameter type.
- `field` mặc định đến từ tên method.

Ví dụ:

~~~java
@SchemaMapping
public Author primaryAuthor(Book book) {
    return bookService.findPrimaryAuthor(book.id());
}
~~~

Spring suy luận mapping là `Book.primaryAuthor`, vì source parameter là `Book` và tên method là `primaryAuthor`.

Nếu SDL khai báo field là `Book.author`, method cần chỉ rõ field:

~~~java
@SchemaMapping(field = "author")
public Author primaryAuthor(Book book) {
    return bookService.findPrimaryAuthor(book.id());
}
~~~

Ở đây, `typeName` vẫn được suy luận là `Book`, còn `field` được ghi đè thành `author`.

Ngược lại, nếu tên method là `author` nhưng source parameter là `BookView`, framework sẽ suy luận `BookView.author`. Việc tên method trùng với field trong SDL không đủ để xác định đúng parent type.

## 4. Ví dụ đầy đủ khi tên Java type trùng GraphQL type

Giả sử ứng dụng dùng Java record `Book` và `Author`:

~~~java
public record Book(
        String id,
        String title,
        String authorId) {
}

public record Author(
        String id,
        String name) {
}
~~~

SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
    displayLabel: String!
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Root resolver trả về `Book`:

~~~java
@Controller
class CatalogQueryController {

    private final BookService bookService;

    CatalogQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

Resolver cho nested field:

~~~java
@Controller
class BookController {

    private final AuthorService authorService;

    BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
~~~

Với method `author(Book book)`, Spring suy luận:

- Source type `Book` tương ứng GraphQL type `Book`.
- Tên method `author` tương ứng GraphQL field `author`.

Do đó không cần ghi `@SchemaMapping(typeName = "Book", field = "author")`.

Đây là trường hợp phù hợp nhất để dùng suy luận mặc định: kiểu Java được đặt tên gần với mô hình GraphQL và source parameter có kiểu cụ thể, rõ ràng.

## 5. Dùng @Source để chỉ rõ source parameter

Trong method có nhiều tham số, có thể dùng `@Source` để đánh dấu rõ tham số nào là source object.

~~~java
@Controller
class BookController {

    private final ReviewService reviewService;

    BookController(ReviewService reviewService) {
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public List<Review> reviews(
            @Source Book book,
            @Argument("first") Integer first) {

        return reviewService.findByBookId(book.id(), first);
    }
}
~~~

Trong ví dụ:

- `@Source Book book` là source object của field `Book.reviews`.
- `@Argument("first")` nhận argument `first` được khai báo trên field `reviews`.
- Tên method `reviews` được dùng để suy luận tên field.
- Kiểu `Book` của source parameter được dùng để suy luận `typeName`.

`@Source` giúp method signature thể hiện rõ vai trò tham số. Khi chỉ có một source parameter đơn giản, nhiều trường hợp Spring có thể nhận diện source mà không cần annotation này. Dùng annotation tường minh có thể làm code dễ đọc hơn, nhất là khi method còn nhận arguments, context hoặc các tham số được resolve bằng annotation khác.

Ví dụ schema tương ứng:

~~~graphql
type Review {
    id: ID!
    rating: Int!
    comment: String
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

## 6. Đặt typeName mặc định ở cấp controller class

Nếu nhiều method trong cùng controller cùng xử lý field của một GraphQL object type, có thể đặt `@SchemaMapping(typeName = "...")` trên class.

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class BookFieldsController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    BookFieldsController(AuthorService authorService, ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }

    @SchemaMapping
    public String displayLabel(Book book) {
        return book.title() + " (" + book.id() + ")";
    }
}
~~~

Trong ví dụ, class-level `typeName = "Book"` cung cấp type mặc định cho các method mapping trong controller. Tên method được dùng làm field nếu method không khai báo `field`.

Có thể hiểu các mapping là:

| Method | GraphQL mapping |
| --- | --- |
| `author(Book book)` | `Book.author` |
| `reviews(Book book)` | `Book.reviews` |
| `displayLabel(Book book)` | `Book.displayLabel` |

Cách đặt ở class hữu ích khi controller tập trung vào một GraphQL type và có nhiều nested field resolver. Nó giảm lặp `typeName = "Book"` trên từng method.

Không nên đặt class-level typeName quá rộng nếu controller xử lý nhiều loại object không liên quan. Khi đó, khai báo riêng ở method thường dễ đọc và ít gây nhầm lẫn hơn.

## 7. Ghi đè typeName ở cấp method

Một controller có thể xử lý field của nhiều GraphQL type. Trong trường hợp đó, khai báo `typeName` ở method giúp mapping chính xác.

~~~java
@Controller
class CatalogFieldController {

    private final AuthorService authorService;
    private final BookService bookService;

    CatalogFieldController(AuthorService authorService, BookService bookService) {
        this.authorService = authorService;
        this.bookService = bookService;
    }

    @SchemaMapping(typeName = "Book")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Author")
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

Mapping tương ứng:

- `author(Book book)` xử lý `Book.author`.
- `books(Author author)` xử lý `Author.books`.

Nếu class-level annotation đã đặt một `typeName` mặc định, method-level `typeName` có thể chỉ rõ type khác cho method tương ứng.

Ví dụ:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
class CatalogFieldControllerWithDefault {

    private final AuthorService authorService;
    private final BookService bookService;

    CatalogFieldControllerWithDefault(
            AuthorService authorService, BookService bookService) {
        this.authorService = authorService;
        this.bookService = bookService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Author")
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

Ở method `author`, class-level `typeName` là `Book`. Ở method `books`, `typeName` được khai báo trực tiếp là `Author`.

Khi đọc code, hãy kiểm tra cả annotation trên class và annotation trên method để hiểu mapping cuối cùng. Nếu mapping quan trọng hoặc dễ gây nhầm, khai báo tường minh ở method là một lựa chọn rõ ràng.

## 8. Khi source Java type khác tên GraphQL type

Trong ứng dụng thực tế, Java source object thường là DTO, projection hoặc view model thay vì class có tên giống GraphQL type.

Ví dụ Java:

~~~java
public record BookView(
        String id,
        String title,
        String authorId) {
}
~~~

SDL vẫn công bố type `Book`:

~~~graphql
type Book {
    id: ID!
    title: String!
    author: Author!
}
~~~

Nếu viết:

~~~java
@SchemaMapping
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Spring suy luận `typeName` từ `BookView`, dẫn đến mapping `BookView.author`. Schema lại chỉ có `Book.author`, nên mapping không khớp.

Cách sửa là chỉ rõ GraphQL type:

~~~java
@SchemaMapping(typeName = "Book")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Hoặc chỉ rõ cả type và field:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(BookView book) {
    return authorService.findById(book.authorId());
}
~~~

Quy tắc thực tế:

- Nếu Java class và GraphQL type có cùng tên, có thể dùng suy luận mặc định.
- Nếu Java class có hậu tố như `View`, `Dto`, `Projection` hoặc `Entity`, kiểm tra tên GraphQL type mà framework sẽ suy luận.
- Nếu tên khác nhau, dùng `typeName` tường minh hoặc class-level mapping phù hợp.
- Không đổi tên GraphQL schema chỉ để khớp với tên class persistence nếu điều đó làm API kém rõ nghĩa.

## 9. Source parameter khai báo bằng interface hoặc base class

Một trường hợp dễ gây nhầm là source parameter có kiểu tổng quát:

~~~java
public interface CatalogItem {
    String id();
}
~~~

~~~java
public record BookView(
        String id,
        String title,
        String authorId) implements CatalogItem {
}
~~~

Method:

~~~java
@SchemaMapping
public Author author(CatalogItem item) {
    return authorService.findByBookId(item.id());
}
~~~

Kiểu source parameter được khai báo là `CatalogItem`, vì vậy không nên mặc định rằng Spring sẽ suy luận `typeName` thành `Book` chỉ vì object runtime hiện tại là `BookView`.

Nếu field thuộc GraphQL type `Book`, hãy chỉ rõ:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(CatalogItem item) {
    return authorService.findByBookId(item.id());
}
~~~

Điều này đặc biệt quan trọng khi một interface Java được dùng làm source cho nhiều GraphQL object type. Một source interface có thể đại diện cho nhiều kiểu runtime; chỉ một tên interface không đủ để xác định mapping field của từng GraphQL type.

Nếu mỗi GraphQL object type có field mapping khác nhau, nên khai báo resolver riêng hoặc thiết kế source parameter cụ thể cho từng mapping. Chỉ dùng một base class khi hợp đồng field thực sự áp dụng cho mọi type liên quan.

## 10. Suy luận source type trong @BatchMapping

`@BatchMapping` cũng ánh xạ một field trên source type, nhưng method thường nhận một danh sách source object để xử lý theo batch.

Ví dụ:

~~~java
@Controller
class BookBatchController {

    private final AuthorService authorService;

    BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping
    public Map<Book, Author> author(List<Book> books) {
        return authorService.findAuthorsByBooks(books);
    }
}
~~~

Method có tên `author` và source parameter là `List<Book>`. Spring có thể suy luận:

- `typeName` là `Book`, dựa trên kiểu phần tử source.
- `field` là `author`, dựa trên tên method.

Nếu source là `List<BookView>` nhưng GraphQL type vẫn là `Book`, hãy khai báo rõ:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, Author> author(List<BookView> books) {
    return authorService.findAuthorsByBooks(books);
}
~~~

`@BatchMapping` dùng chung ý tưởng xác định source type với `@SchemaMapping`, nhưng cần chú ý kiểu phần tử bên trong collection. Hãy kiểm tra generic type của source parameter khi method nhận `List<T>` hoặc một collection tương tự.

Không nên nhầm `typeName` với kiểu giá trị trả về của batch method. Trong ví dụ, `Map<Book, Author>` trả về quan hệ giữa source `Book` và kết quả `Author`; `typeName` vẫn là GraphQL type của source, tức `Book`.

## 11. QueryMapping và các root mapping không suy luận typeName từ source

`@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping` là các annotation chuyên biệt cho root operation type.

Ví dụ:

~~~java
@Controller
class BookQueryController {

    private final BookService bookService;

    BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
~~~

`@QueryMapping` ánh xạ method tới field trên root type `Query`. `typeName` của root mapping không cần suy luận từ source parameter như nested `@SchemaMapping`, vì method đang xử lý root operation chứ không phải field của một object cha.

Tương tự:

- `@MutationMapping` ánh xạ vào root type `Mutation`.
- `@SubscriptionMapping` ánh xạ vào root type `Subscription`.

Sau khi Query trả về một object `Book`, các nested field của object đó mới có thể dùng `@SchemaMapping` và suy luận source type từ tham số `Book`.

Không dùng quy tắc suy luận source type của `@SchemaMapping` để giải thích root mapping. Hai nhóm annotation có mục đích khác nhau.

## 12. Lỗi thường gặp khi suy luận typeName

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Method không được gọi cho field mong đợi | Source class là `BookView` nhưng SDL dùng `Book` | Khai báo `@SchemaMapping(typeName = "Book")` |
| Mapping trỏ tới type không tồn tại | Kiểu source Java được suy luận thành tên không có trong schema | Kiểm tra source parameter và tên GraphQL type |
| Đúng type nhưng sai field | Tên method khác tên field trong SDL | Dùng `@SchemaMapping(field = "...")` |
| Controller có nhiều method cùng source type nhưng mapping khó đọc | Thiếu quy ước class-level hoặc method-level | Gom controller theo type hoặc khai báo tường minh |
| Field mapping trên interface không khớp object type | Source parameter khai báo base interface | Chỉ rõ `typeName` hoặc dùng source type cụ thể |
| Batch mapping không suy luận được type mong muốn | Generic element type khác GraphQL type | Kiểm tra `List<T>` và đặt `typeName` tường minh |
| Query mapping bị hiểu nhầm là nested mapping | Nhầm root operation với field trên object | Dùng `@QueryMapping` cho root Query và `@SchemaMapping` cho nested field |
| Field tồn tại trong SDL nhưng resolver không chạy | Annotation mapping không khớp hoặc controller không được Spring quản lý | Kiểm tra tên type/field và component registration |

Một nguyên tắc chẩn đoán hữu ích là viết ra mapping cuối cùng theo dạng:

~~~text
GraphQL type + field = Java handler method
Book + author = BookController.author(BookView)
~~~

Sau đó kiểm tra lần lượt source parameter, `typeName`, `field` và schema. Cách này thường giúp phát hiện lỗi suy luận nhanh hơn việc chỉ nhìn vào tên method.

## 13. Kiểm thử typeName mặc định và mapping tường minh

Nên kiểm thử operation thực tế để xác minh mapping đã được đăng ký đúng. Ví dụ, với schema `Book.author`, client truy vấn:

~~~graphql
query {
    book(id: "book-42") {
        title
        author {
            name
        }
    }
}
~~~

Test có thể dùng `GraphQlTester`:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                author {
                    name
                }
            }
        }
        """)
        .execute()
        .path("book.author.name")
        .entity(String.class)
        .isEqualTo("An Nguyen");
~~~

Nên có các trường hợp:

- Source class `Book` trùng GraphQL type `Book`, mapping mặc định hoạt động.
- Source class `BookView` khác GraphQL type `Book`, mapping tường minh hoạt động.
- Tên method trùng field mặc định.
- Tên method khác field nhưng `field` được khai báo rõ.
- Class-level `typeName` được áp dụng cho method.
- Method-level `typeName` ghi đè mặc định của class.
- `@BatchMapping` suy luận từ generic source element type.
- Source parameter là interface hoặc base class và mapping được khai báo tường minh.

Khi mapping không hoạt động, kiểm tra lỗi khởi tạo schema hoặc log đăng ký handler trước. Sau đó chạy operation tối thiểu chỉ yêu cầu field đang cần xác minh, tránh để lỗi ở nested field khác làm khó xác định nguyên nhân.

## 14. Quy tắc thiết kế để mapping dễ hiểu

Một số quy tắc giúp code annotated controller rõ ràng:

1. Dùng source parameter có kiểu cụ thể khi có thể.
2. Đặt tên Java source class gần với GraphQL object type nếu kiến trúc cho phép.
3. Nếu dùng DTO hoặc projection có tên khác, khai báo `typeName` tường minh.
4. Đặt controller theo nhóm GraphQL type khi có nhiều nested field mapping.
5. Dùng class-level `@SchemaMapping(typeName = "...")` khi phần lớn method trong controller cùng xử lý một type.
6. Dùng method-level `typeName` khi method xử lý type khác hoặc cần làm rõ mapping.
7. Chỉ định `field` khi tên method không trùng field trong SDL.
8. Dùng `@Source` khi muốn thể hiện rõ tham số source trong method có nhiều tham số.
9. Với `@BatchMapping`, kiểm tra generic element type của collection source.
10. Kiểm thử operation qua `GraphQlTester` để xác nhận mapping thực tế.

Không nên lạm dụng suy luận mặc định nếu tên type không rõ ràng. Mapping tường minh là lựa chọn tốt khi nó giúp người đọc xác định ngay GraphQL field đang được xử lý.

## 15. Tổng kết

Trong Spring for GraphQL, `@SchemaMapping` có thể suy luận `typeName` mặc định từ kiểu Java của source parameter. Tên field mặc định được suy luận từ tên method. Vì vậy, `author(Book book)` thường ánh xạ tới `Book.author` mà không cần khai báo hai thuộc tính trong annotation.

Quy tắc này hoạt động rõ nhất khi tên Java source type trùng tên GraphQL object type. Nếu source là DTO, projection, interface hoặc base class có tên khác, hãy khai báo `typeName` tường minh. Class-level `@SchemaMapping` có thể cung cấp type mặc định cho nhiều method, còn method-level annotation có thể ghi đè khi cần. Với `@BatchMapping`, chú ý generic element type của collection source. Hiểu đúng nguồn suy luận giúp controller ngắn gọn mà mapping vẫn chính xác và dễ bảo trì.

