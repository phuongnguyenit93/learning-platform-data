# Schema mapping ở cấp class trong Spring for GraphQL

`@SchemaMapping` ánh xạ một handler method trong controller thành data fetcher cho một field của GraphQL schema. Khi nhiều method cùng xử lý field thuộc một parent type, có thể đặt `@SchemaMapping(typeName = "...")` ở cấp class để khai báo parent type mặc định cho các handler method trong class đó.

Cách tổ chức này giúp controller tập trung vào một GraphQL object type. Các method chỉ cần khai báo field cần xử lý; tên field mặc định lấy từ tên method, còn `typeName` được kế thừa từ class. Nếu một method xử lý parent type khác, có thể ghi đè `typeName` ở cấp method.

## 1. Schema mapping là gì?

Trong GraphQL, một object type có thể chứa các field cần được tải hoặc tính toán từ dữ liệu khác. Ví dụ schema thư viện:

~~~graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews: [Review!]!
}

type Author {
    id: ID!
    name: String!
}

type Review {
    id: ID!
    rating: Int!
    comment: String!
}
~~~

Field `book` nằm dưới root type `Query`. Các field `author` và `reviews` nằm dưới object type `Book`. Spring for GraphQL có thể ánh xạ từng field này vào method Java bằng `@QueryMapping`, `@SchemaMapping` hoặc `@BatchMapping`.

Ví dụ method xử lý field `Book.author`:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author getAuthor(Book book) {
        // Load the author for this book.
    }
}
~~~

Ở đây:

- `typeName = "Book"` xác định parent type của field.
- `field = "author"` xác định tên field trong SDL.
- Tham số `Book book` là source/parent object hiện tại mà GraphQL đang resolve.
- Giá trị trả về `Author` trở thành kết quả của field `Book.author`.

`AnnotatedControllerConfigurer` phát hiện các controller bean và đăng ký handler method được annotate thành `DataFetcher` trong GraphQL runtime wiring. Với Spring Boot starter, phần cấu hình này thường được auto-configuration thiết lập sẵn.

## 2. Đặt @SchemaMapping ở cấp class

Khi nhiều handler method cùng ánh xạ field của `Book`, có thể chuyển `typeName` lên class:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Load the author for this book.
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        // Load reviews for this book.
    }
}
~~~

Class-level annotation đặt parent type mặc định là `Book` cho các handler method trong class. Vì vậy hai method trên được hiểu tương đương với:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) { ... }

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book) { ... }
~~~

Class-level `@SchemaMapping` chỉ cung cấp giá trị `typeName` mặc định. Mỗi method vẫn cần được khai báo là handler, ví dụ bằng `@SchemaMapping` hoặc `@BatchMapping`. Chỉ đặt annotation trên class không biến mọi method Java trong class thành data fetcher.

## 3. Quy tắc xác định typeName và field name

Spring for GraphQL xác định mapping từ annotation, tên method và source parameter. Khi dùng class-level annotation, quy tắc có thể đọc theo thứ tự sau:

| Thành phần | Cách xác định |
| --- | --- |
| Parent type (`typeName`) | Method-level `typeName` nếu được khai báo; nếu không, dùng class-level `typeName`; nếu cả hai đều không có, suy ra từ simple class name của source/parent parameter |
| Field name | Method-level `field` hoặc alias `value` nếu được khai báo; nếu không, dùng tên method |
| Source object | Tham số handler có kiểu parent object, ví dụ `Book book` |

Ví dụ method name khác tên field:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping(field = "primaryAuthor")
    public Author resolveMainAuthor(Book source) {
        // Maps to Book.primaryAuthor.
    }
}
~~~

Method `resolveMainAuthor` được ánh xạ đến field `primaryAuthor` nhờ `field`. Parent type vẫn là `Book` do class-level annotation cung cấp.

`value` là alias của thuộc tính `field`, vì vậy có thể viết `@SchemaMapping("primaryAuthor")`. Trong codebase, nên thống nhất một cách viết để người đọc dễ nhận ra đây là tên field GraphQL.

## 4. Method-level typeName ghi đè class-level default

Một controller có thể xử lý phần lớn field của `Book`, nhưng có một method xử lý field thuộc parent type khác. Khi đó method-level `typeName` được ưu tiên:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class CatalogMappingController {

    @SchemaMapping
    public Author author(Book book) {
        // Maps to Book.author.
    }

    @SchemaMapping(typeName = "Author", field = "featuredBook")
    public Book featuredBook(Author author) {
        // Maps to Author.featuredBook.
    }
}
~~~

Trong ví dụ:

- `author` kế thừa `typeName = "Book"` từ class.
- `featuredBook` khai báo `typeName = "Author"` nên ghi đè giá trị mặc định của class.
- Field name của `featuredBook` được chỉ định rõ bằng `field`.

Nếu một controller có quá nhiều method phải ghi đè type mặc định, đó có thể là dấu hiệu các handler thuộc nhiều domain khác nhau. Tách controller theo parent type thường giúp mapping dễ đọc và tránh annotation override rải rác.

## 5. Khi nào class-level mapping hữu ích?

Class-level `@SchemaMapping` đặc biệt phù hợp trong các trường hợp:

**Nhiều field thuộc cùng một parent type.** Một `BookController` có thể xử lý `author`, `reviews`, `publisher`, `categories` và các field khác của `Book`. Khai báo type name một lần giúp các method ngắn và đồng nhất.

**Tên Java source khác tên GraphQL type.** Ví dụ ứng dụng dùng `BookEntity`, `BookView` hoặc `BookDto`, nhưng schema công bố type `Book`. Class-level `@SchemaMapping(typeName = "Book")` tránh việc phải suy luận `typeName` từ tên Java class.

**Nhóm resolver theo domain.** Controller có thể đóng vai trò nơi tập hợp data fetcher cho một object type, trong khi service riêng đảm nhiệm nghiệp vụ và truy cập dữ liệu.

Ví dụ source Java có tên `BookView`:

~~~java
public record BookView(
        String id,
        String title,
        String authorId
) {}

@Controller
@SchemaMapping(typeName = "Book")
public class BookViewController {

    @SchemaMapping
    public Author author(BookView source) {
        // The GraphQL parent type is Book, although the Java type is BookView.
    }
}
~~~

Không có yêu cầu tên class Java phải trùng tên GraphQL type khi đã chỉ định rõ `typeName`. Điều quan trọng là method nhận đúng source object mà field đang resolve.

## 6. Ví dụ hoàn chỉnh: ánh xạ field của Book

Giả sử ứng dụng có model và service:

~~~java
public record Book(
        String id,
        String title,
        String authorId
) {}

public record Author(
        String id,
        String name
) {}

public record Review(
        String id,
        int rating,
        String comment
) {}
~~~

Các service chịu trách nhiệm lấy dữ liệu:

~~~java
public interface AuthorService {
    Author findById(String id);
}

public interface ReviewService {
    List<Review> findByBookId(String bookId);
}
~~~

Controller có class-level mapping:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService
    ) {
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
}
~~~

Trong phiên bản dùng batch mapping, service cần có thêm method tương ứng:

~~~java
import java.util.List;
import java.util.Map;
import reactor.core.publisher.Mono;

public interface ReviewService {
    Mono<Map<Book, List<Review>>> findByBooks(List<Book> books);
}
~~~

Vì class khai báo `@SchemaMapping(typeName = "Book")`, hai method được ánh xạ đến `Book.author` và `Book.reviews`. Method name mặc định trùng với field name trong SDL nên không cần chỉ định `field`.

Query:

~~~graphql
query BookDetails($id: ID!) {
    book(id: $id) {
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

GraphQL thực thi resolver `book` ở root type `Query` để lấy `Book`. Sau đó các field được chọn trên object đó gọi data fetcher tương ứng: `author` gọi `BookController.author`, `reviews` gọi `BookController.reviews`. Mỗi method nhận chính object `Book` vừa được resolve làm source parameter.

## 7. Class-level @SchemaMapping kết hợp @BatchMapping

`@BatchMapping` là cách khai báo batch data fetcher cho field liên kết. Nó có thể kế thừa `typeName` mặc định từ class-level `@SchemaMapping`, vì vậy controller xử lý field của cùng parent type có thể đặt cả schema mapping thông thường và batch mapping trong một class.

Ví dụ thay resolver `reviews` tải riêng cho từng quyển sách bằng batch mapping:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService
    ) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @BatchMapping
    public Mono<Map<Book, List<Review>>> reviews(List<Book> books) {
        return reviewService.findByBooks(books);
    }
}
~~~

Trong ví dụ, `ReviewService.findByBooks(...)` trả về map với key là từng source `Book` và value là danh sách review tương ứng. Spring for GraphQL dùng kết quả batch để cung cấp field `Book.reviews` cho từng parent object. `@BatchMapping` mặc định lấy field name từ tên method, còn type name có thể kế thừa từ class-level `@SchemaMapping`.

Một batch mapping cũng có thể trả `Flux<V>` theo đúng thứ tự source objects, hoặc các dạng đồng bộ phù hợp. Khi dùng map, các key phải xác định được đúng parent object; nếu dùng object làm key, hãy bảo đảm `equals` và `hashCode` phản ánh identity mong muốn.

Batch mapping có thể giảm N+1 khi một query lấy nhiều `Book` và mỗi quyển cần tải `reviews`. Class-level mapping chỉ giúp chia sẻ parent type; nó không tự batching dữ liệu. Việc gom truy vấn được thực hiện bởi cơ chế batch loader mà `@BatchMapping` đăng ký.

## 8. Phân biệt class-level mapping với các root mapping

`@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping` là các annotation chuyên biệt được meta-annotate từ `@SchemaMapping`, với parent type cố định lần lượt là `Query`, `Mutation` và `Subscription`.

Ví dụ root controller:

~~~java
@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        // Load the root Book object.
    }
}
~~~

Controller này xử lý field `Query.book`. Các field con của object `Book` có thể được đặt trong controller khác dùng class-level `@SchemaMapping(typeName = "Book")`.

Nên tách root operation và field mapping theo parent type khi cách tổ chức đó giúp code dễ đọc. Không đặt class-level `@SchemaMapping(typeName = "Book")` lên một controller chứa lẫn nhiều handler root và handler field con nếu điều đó làm người đọc khó xác định mapping thực tế. Các annotation chuyên biệt có type name cố định cho root operation; class-level default chủ yếu dành cho các handler field của object type.

## 9. Method arguments và source parameter

Handler method có thể nhận source object cùng các đối số hỗ trợ khác. Với schema mapping ở cấp class, việc kế thừa `typeName` không làm thay đổi quy tắc bind tham số method.

| Tham số | Mục đích |
| --- | --- |
| `Book book` | Source/parent object mà field đang được resolve |
| `@Argument("locale") String locale` | Lấy argument `locale` của field GraphQL |
| `@ContextValue("tenantId") String tenantId` | Lấy giá trị từ `GraphQLContext` |
| `GraphQLContext context` | Truy cập GraphQL context hiện tại |
| `DataFetchingEnvironment environment` | Truy cập execution metadata và source/arguments ở mức GraphQL Java |
| `Principal principal` | Lấy principal nếu Spring Security tích hợp cung cấp |

Ví dụ field `Book.localizedTitle(locale: String!)`:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String!
}
~~~

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public String localizedTitle(
            Book book,
            @Argument("locale") String locale
    ) {
        return translationService.translate(book.title(), locale);
    }
}
~~~

Tham số `Book book` là source object; `@Argument` lấy giá trị từ argument của field. Class-level mapping chỉ cung cấp parent type mặc định là `Book`.

## 10. Tổ chức controller theo parent type

Một cách tổ chức thường dùng là mỗi controller tập trung vào một GraphQL object type hoặc một nhóm field có liên quan:

~~~text
graphql/
├── BookQueryController.java       # Query.book, Query.books
├── BookController.java            # Book.author, Book.reviews, Book.publisher
├── AuthorController.java          # Author.books, Author.featuredBook
└── ReviewController.java          # Review.reviewer, Review.reactions
~~~

Ví dụ `AuthorController`:

~~~java
@Controller
@SchemaMapping(typeName = "Author")
public class AuthorController {

    private final BookService bookService;

    public AuthorController(BookService bookService) {
        this.bookService = bookService;
    }

    @SchemaMapping
    public List<Book> books(Author author) {
        return bookService.findByAuthorId(author.id());
    }
}
~~~

Class-level `typeName = "Author"` làm rõ controller này sở hữu các field của GraphQL type `Author`. Khi schema có nhiều domain, cách nhóm này giúp tìm resolver theo type nhanh hơn và giảm việc lặp `typeName` trên mỗi method.

Không cần tạo một controller riêng cho từng type nếu schema nhỏ. Hãy chọn ranh giới theo độ liên quan của nghiệp vụ và số lượng handler, tránh chia quá nhỏ khiến dependency injection và điều hướng code trở nên rườm rà.

## 11. Kiểm thử class-level schema mapping

Kiểm thử nên xác nhận class-level default thực sự ánh xạ method vào đúng field và method-level override được áp dụng đúng. Có thể dùng `@GraphQlTest` kết hợp `GraphQlTester`.

Ví dụ schema:

~~~graphql
type Query {
    book(id: ID!): Book
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

Root controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return new Book("book-1", "GraphQL thực hành", "author-1");
    }
}
~~~

Controller field mapping:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return new Author(book.authorId(), "Nguyen An");
    }
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest({BookQueryController.class, BookController.class})
class BookSchemaMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void mapsAuthorUsingClassLevelTypeName() {
        graphQlTester.document("""
                query {
                    book(id: "book-1") {
                        title
                        author {
                            id
                            name
                        }
                    }
                }
                """)
            .execute()
            .path("book.author.name")
            .entity(String.class)
            .isEqualTo("Nguyen An");
    }
}
~~~

Test này giả định `Book` có accessor `authorId()` và `Author` có các accessor tương ứng. Nó xác nhận method `author(Book)` được ánh xạ thành field `Book.author` nhờ class-level `typeName`, dù method không lặp lại `typeName`.

Nên bổ sung test cho:

1. Field name suy ra từ tên method.
2. Field name tùy chỉnh bằng `@SchemaMapping(field = "...")`.
3. Method-level `typeName` ghi đè class-level default.
4. Source Java type khác tên GraphQL type nhưng class-level mapping vẫn chính xác.
5. `@BatchMapping` kế thừa parent type và trả kết quả đúng cho từng source object.
6. Không có hai handler method cùng đăng ký một cặp parent type/field.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field không có data fetcher | Method chưa được annotate bằng `@SchemaMapping` hoặc `@BatchMapping` | Class-level annotation chỉ đặt default type name; annotate method cần xử lý |
| Mapping trỏ sai parent type | `typeName` không khớp tên object type trong SDL | Kiểm tra tên GraphQL type và method-level override |
| Field name không khớp | Tên method khác tên field nhưng không khai báo `field` | Đặt `@SchemaMapping(field = "fieldName")` |
| Method không nhận được source object | Tham số source có kiểu không phù hợp với object parent thực tế | Kiểm tra source parameter và kiểu object resolver cha trả về |
| Method-level override không có tác dụng | Annotation method không khai báo đúng `typeName` hoặc mapping bị trùng | Kiểm tra annotation ở cả hai cấp và cặp type/field cuối cùng |
| Batch mapping không được gọi | Method không có `@BatchMapping`, hoặc type/field mapping không khớp | Kiểm tra annotation, source list và field name |
| Hai handler cùng đăng ký một field | Trùng mapping giữa controller hoặc giữa annotation và wiring thủ công | Chỉ giữ một data fetcher cho mỗi cặp parent type/field |
| Resolver chạy nhưng trả null | Service không tìm thấy dữ liệu hoặc source object thiếu thông tin liên kết | Kiểm tra service, source object và nullability trong SDL |

Khi debug, hãy xác định trước cặp `typeName.fieldName` mà method cần xử lý. Sau đó kiểm tra class-level default, method-level override, field name suy ra và source parameter. Cách này giúp tìm nhanh lỗi do annotation thay vì nhầm với lỗi truy cập dữ liệu.

## 13. Lưu ý về bảo mật và hiệu năng

Class-level `@SchemaMapping` chỉ là cách khai báo mapping. Nó không tự thêm xác thực hoặc phân quyền cho các field. Nếu `Book.internalNotes` chỉ dành cho người có quyền, resolver hoặc service cần kiểm tra principal và quyền truy cập trước khi trả dữ liệu.

Tương tự, gom các resolver của một parent type vào một controller không làm giảm số lần truy cập database. Nếu query lấy danh sách nhiều `Book` rồi resolve `author` hoặc `reviews` cho từng phần tử, có thể phát sinh N+1. Dùng `@BatchMapping`, DataLoader hoặc service batch để gom truy vấn; đo lường và kiểm thử với dữ liệu có nhiều parent object.

Giữ handler method mỏng: nhận source và argument, gọi service, trả kết quả. Không đưa toàn bộ logic nghiệp vụ, transaction hoặc truy cập hạ tầng vào annotation/controller chỉ vì các field cùng nằm dưới một GraphQL type.

## 14. Quy trình áp dụng class-level schema mapping

Khi tạo controller cho một GraphQL object type:

1. Xác định parent type trong SDL mà controller sẽ xử lý.
2. Đặt `@Controller` và `@SchemaMapping(typeName = "ParentType")` ở cấp class.
3. Annotate từng handler method bằng `@SchemaMapping` hoặc `@BatchMapping`.
4. Để tên method trùng field name nếu có thể; nếu khác, khai báo `field` rõ ràng.
5. Dùng method-level `typeName` khi một method cần ánh xạ sang parent type khác.
6. Nhận source object bằng tham số có kiểu phù hợp; nhận argument qua `@Argument` khi cần.
7. Giữ logic nghiệp vụ trong service và dùng batching cho các field liên kết có nguy cơ N+1.
8. Kiểm thử cặp parent type/field bằng `GraphQlTester` và kiểm tra các mapping bị trùng.

Class-level `@SchemaMapping` giúp controller thể hiện rõ parent type mà nó phục vụ, giảm lặp annotation và hỗ trợ tổ chức resolver theo domain. Khi hiểu đúng quy tắc kế thừa `typeName`, cách suy ra field name và quyền override ở cấp method, các annotated controller trong Spring for GraphQL sẽ dễ đọc và dễ bảo trì hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL 1.4 — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.batch-loading)
