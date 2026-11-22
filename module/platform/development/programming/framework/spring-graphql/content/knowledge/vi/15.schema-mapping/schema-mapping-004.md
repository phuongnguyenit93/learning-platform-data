# typeName và field trong @SchemaMapping

Trong Spring for GraphQL, một schema mapping xác định **field nào của GraphQL type nào** sẽ được xử lý bởi một handler method. Hai thông tin cốt lõi là `typeName` và `field`: `typeName` là tên parent type trong SDL, còn `field` là tên field thuộc type đó.

Ví dụ, `Book.author` có nghĩa field `author` thuộc GraphQL object type `Book`. Mapping có thể khai báo rõ cả hai tên bằng `@SchemaMapping(typeName = "Book", field = "author")`. Nếu tên Java phù hợp, Spring for GraphQL còn có thể suy luận `typeName` từ source parameter và suy luận `field` từ tên method.

## 1. Cặp typeName.field trong GraphQL schema

GraphQL schema tổ chức dữ liệu theo type và field. Ví dụ:

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
    comment: String
}
~~~

Các field có thể được xác định bằng cặp `typeName.field`:

| Cặp mapping | Ý nghĩa |
| --- | --- |
| `Query.book` | Field `book` thuộc root type `Query` |
| `Book.author` | Field `author` thuộc type `Book` |
| `Book.reviews` | Field `reviews` thuộc type `Book` |
| `Author.name` | Field `name` thuộc type `Author` |

Trong GraphQL Java, một data fetcher được đăng ký cho một field cụ thể của một type. `@SchemaMapping` giúp Spring for GraphQL tạo đăng ký đó từ controller method.

## 2. Khai báo tường minh typeName và field

Ví dụ ánh xạ `Book.author`:

~~~java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author loadAuthor(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

Annotation nói rõ handler method `loadAuthor` xử lý field `author` của GraphQL type `Book`. Tên method không cần trùng với tên field vì `field` đã được chỉ định.

Trong ví dụ này, `Book source` là source/parent object đang được GraphQL resolve. Spring truyền object `Book` hiện tại vào tham số source. Resolver dùng `authorId` của sách để lấy `Author` tương ứng.

Tên `typeName` và `field` phải khớp chính xác với SDL, bao gồm chữ hoa và chữ thường. `Book.author` khác `Book.Author`, và `Book.author` cũng khác `Author.book`.

## 3. Suy luận field từ tên method

Nếu method name trùng với field name trong SDL, có thể bỏ thuộc tính `field`:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Spring for GraphQL dùng tên method làm field name khi không khai báo `field` hoặc alias `value`. Hai method trên lần lượt ánh xạ đến `Book.author` và `Book.reviews`.

Đây là cách viết ngắn và dễ đọc khi tên method Java có thể giữ giống tên field GraphQL. Nếu tên method cần thể hiện hành động hoặc quy ước đặt tên khác, hãy khai báo field rõ ràng thay vì buộc method phải mang tên GraphQL.

## 4. Dùng field hoặc value để chỉ định tên field

`value` là alias của thuộc tính `field` trong `@SchemaMapping`. Hai cách viết sau có cùng ý nghĩa:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

~~~java
@SchemaMapping(typeName = "Book", value = "author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Cũng có thể dùng dạng rút gọn:

~~~java
@SchemaMapping("author")
public Author loadAuthor(Book book) {
    return authorService.findById(book.authorId());
}
~~~

Trong dạng rút gọn, chuỗi đầu tiên gán cho `value`, tức alias của `field`. Parent type được suy luận từ source parameter `Book` nếu không có `typeName` ở method hoặc class.

Nên thống nhất một cách viết trong cùng codebase. `field = "author"` thường dễ đọc hơn khi người đọc cần phân biệt tên field GraphQL với tên method Java; `@SchemaMapping("author")` ngắn hơn khi mapping đơn giản.

## 5. Suy luận typeName từ source parameter

Nếu không khai báo `typeName`, Spring for GraphQL có thể suy luận parent type từ kiểu Java của source parameter trong handler method.

~~~java
@Controller
public class BookController {

    @SchemaMapping(field = "author")
    public Author resolveAuthor(Book source) {
        return authorService.findById(source.authorId());
    }
}
~~~

Source parameter có kiểu `Book`, nên parent type mặc định được suy luận từ tên class Java là `Book`. Mapping cuối cùng là `Book.author`.

Suy luận này thuận tiện khi tên class Java trùng tên GraphQL object type. Nếu ứng dụng dùng DTO, projection hoặc entity có tên khác SDL, hãy khai báo `typeName` tường minh để tránh mapping sai.

Ví dụ Java class tên `BookView`, nhưng schema vẫn gọi type là `Book`:

~~~java
public record BookView(
        String id,
        String title,
        String authorId
) {}

@Controller
public class BookViewController {

    @SchemaMapping(typeName = "Book", field = "author")
    public Author resolveAuthor(BookView source) {
        return authorService.findById(source.authorId());
    }
}
~~~

Khi tên Java và GraphQL khác nhau, `typeName = "Book"` làm rõ mapping mà không cần đổi tên class Java.

Nếu method không có source parameter để Spring suy luận parent type, hãy chỉ định `typeName` rõ ràng. Với các resolver root, thường nên dùng `@QueryMapping`, `@MutationMapping` hoặc `@SubscriptionMapping` để biểu thị đúng loại operation.

## 6. Kết hợp suy luận và khai báo tường minh

Không bắt buộc phải khai báo cả hai thuộc tính trong mọi handler. Có thể chọn cách viết dựa trên quy ước tên:

| Annotation | Source parameter | Mapping được xác định |
| --- | --- | --- |
| `@SchemaMapping(typeName = "Book", field = "author")` | `Book source` | `Book.author` |
| `@SchemaMapping(typeName = "Book")` | `Book source` | `Book.<tên method>` |
| `@SchemaMapping(field = "author")` | `Book source` | `Book.author` nếu suy luận type thành công |
| `@SchemaMapping("author")` | `Book source` | `Book.author` nếu suy luận type thành công |
| `@SchemaMapping` | `Book source` | `Book.<tên method>` nếu suy luận type thành công |

Khi đọc code, hãy xác định hai giá trị cuối cùng mà Spring sử dụng: parent type và field. Annotation có thể cung cấp một giá trị, còn giá trị kia được suy luận từ method hoặc source parameter.

## 7. Class-level typeName và method-level override

Nếu nhiều handler trong cùng controller cùng thuộc một parent type, có thể đặt `typeName` ở cấp class:

~~~java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "reviews")
    public List<Review> findReviews(Book book) {
        return reviewService.findByBookId(book.id());
    }

    @SchemaMapping(typeName = "Author", field = "featuredBook")
    public Book featuredBook(Author author) {
        return bookService.findFeaturedByAuthor(author.id());
    }
}
~~~

Hai method đầu dùng `typeName = "Book"` từ class. Method `featuredBook` ghi đè type mặc định bằng `typeName = "Author"`. `field` của method thứ hai được đặt tường minh vì tên method `findReviews` khác field `reviews`.

Class-level annotation chỉ cung cấp parent type mặc định cho các handler method; method vẫn cần `@SchemaMapping` hoặc annotation mapping tương ứng. Nếu controller có nhiều method phải override type liên tục, nên cân nhắc tách controller theo parent type để mapping dễ theo dõi.

## 8. Phân biệt field mapping với argument của field

`field` trong `@SchemaMapping` là **tên field GraphQL** mà method xử lý. Nó không phải tên argument của field.

Ví dụ schema có field `Book.localizedTitle(locale: String!)`:

~~~graphql
type Book {
    id: ID!
    title: String!
    localizedTitle(locale: String!): String!
}
~~~

Handler method:

~~~java
@Controller
public class BookController {

    @SchemaMapping(typeName = "Book", field = "localizedTitle")
    public String resolveLocalizedTitle(
            Book source,
            @Argument("locale") String locale
    ) {
        return translationService.translate(source.title(), locale);
    }
}
~~~

Ở đây:

- `typeName = "Book"` là parent type.
- `field = "localizedTitle"` là tên field được ánh xạ.
- `@Argument("locale")` lấy argument `locale` từ lời gọi field.
- `Book source` là parent object hiện tại.

Không viết `field = "locale"` chỉ vì method nhận tham số `locale`; làm vậy sẽ yêu cầu schema có field `Book.locale`, vốn là một mapping khác.

## 9. Mapping root field: Query, Mutation và Subscription

Các field ở root type cũng được xác định theo cặp type và field. Với schema mặc định, root type lần lượt là `Query`, `Mutation` và `Subscription`.

~~~graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    renameBook(id: ID!, title: String!): Book
}

type Subscription {
    bookUpdated(id: ID!): Book!
}
~~~

Có thể dùng `@SchemaMapping` để chỉ định root mapping tường minh:

~~~java
@Controller
public class BookRootController {

    @SchemaMapping(typeName = "Query", field = "book")
    public Book findBook(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Mutation", field = "renameBook")
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title
    ) {
        return bookService.rename(id, title);
    }
}
~~~

Tuy nhiên, Spring for GraphQL cung cấp annotation chuyên biệt để biểu đạt rõ loại root operation:

~~~java
@Controller
public class BookRootController {

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title
    ) {
        return bookService.rename(id, title);
    }
}
~~~

`@QueryMapping`, `@MutationMapping` và `@SubscriptionMapping` là các annotation chuyên biệt cho root field. Với các field con như `Book.author`, dùng `@SchemaMapping` để thể hiện rõ parent type.

## 10. Kết hợp @BatchMapping

`@BatchMapping` cũng đăng ký data fetcher cho một cặp parent type và field. Nó hỗ trợ các thuộc tính `typeName` và `field` tương tự `@SchemaMapping`, đồng thời có thể sử dụng tên method để suy luận field.

Ví dụ SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    reviews: [Review!]!
}
~~~

Batch handler ánh xạ tới `Book.reviews`:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookReviewController {

    @BatchMapping(typeName = "Book", field = "reviews")
    public Mono<Map<Book, List<Review>>> loadReviews(List<Book> books) {
        return reviewService.findByBooks(books);
    }
}
~~~

Trong ví dụ, method name `loadReviews` khác field `reviews`, vì vậy annotation khai báo `field` rõ ràng. Service trả map từ từng `Book` sang danh sách review tương ứng. Spring for GraphQL dùng batch result để cung cấp kết quả cho field của từng parent object.

Nếu method được đặt tên `reviews`, có thể bỏ `field` và để framework suy luận. Dù dùng `@BatchMapping` hay `@SchemaMapping`, cặp `typeName.field` cuối cùng vẫn phải khớp schema.

## 11. Kiểm thử mapping đúng type và field

Kiểm thử nên xác nhận field được đăng ký đúng vị trí trong schema và handler trả dữ liệu mong đợi. Ví dụ:

Các kiểu tối thiểu dùng trong ví dụ kiểm thử:

~~~java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}

public interface BookService {
    Book findById(String id);
    Book rename(String id, String title);
}

public interface AuthorService {
    Author findById(String id);
}
~~~

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.mockito.BDDMockito.given;

@GraphQlTest({BookRootController.class, BookController.class})
class BookFieldMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesAuthorFieldOfBook() {
        given(bookService.findById("book-1"))
                .willReturn(new Book("book-1", "GraphQL thực hành", "author-1"));
        given(authorService.findById("author-1"))
                .willReturn(new Author("author-1", "Nguyen An"));

        graphQlTester.document("""
                query {
                    book(id: "book-1") {
                        id
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

`BookService` và `AuthorService` được mock bằng `@MockitoBean`; test cung cấp một `Book` có `authorId` là `author-1` và một `Author` tương ứng. Các record `Book` và `Author` cần có accessor `id()`, `title()`/`name()` và `authorId()` như các ví dụ trước.

Nên kiểm tra thêm:

1. Method name được dùng làm field khi không khai báo `field`.
2. `field` và alias `value` ánh xạ đến cùng field.
3. `typeName` suy luận từ source parameter khi tên Java và GraphQL trùng nhau.
4. `typeName` tường minh xử lý đúng trường hợp Java DTO khác tên GraphQL type.
5. Class-level default và method-level override tạo đúng cặp type/field.
6. Argument được bind bằng `@Argument` độc lập với tên field mapping.
7. Không có hai handler cùng đăng ký một cặp `typeName.field`.

## 12. Lỗi thường gặp khi cấu hình typeName và field

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field không có data fetcher | `field` không khớp SDL hoặc method chưa có mapping annotation | Kiểm tra cặp `typeName.field` và annotation method |
| Mapping bị đăng ký vào type sai | Suy luận từ source parameter không trùng tên GraphQL type | Khai báo `typeName` tường minh |
| Field name không đúng | Method name khác field SDL nhưng không khai báo `field` | Dùng `field = "..."` hoặc alias `value` |
| Nhầm field với argument | Dùng tên argument làm `field` trong annotation | Giữ `field` là tên field GraphQL; bind argument bằng `@Argument` |
| Method-level override không như mong muốn | `typeName` ở method không khớp hoặc field bị trùng mapping | Kiểm tra giá trị annotation ở class và method |
| Hai method xử lý cùng một field | Trùng cặp `typeName.field` trong nhiều controller | Chỉ để một handler sở hữu mỗi field hoặc thiết kế lại mapping |
| Root query không được gọi | Dùng sai root type hoặc annotation mapping | Dùng `@QueryMapping` hoặc `typeName = "Query"` với schema mặc định |
| Batch field không được resolve | `@BatchMapping` dùng sai field/type hoặc kết quả batch không ghép đúng source | Kiểm tra annotation, danh sách source và map result |

Khi debug, hãy ghi lại chính xác cặp type/field mà SDL công bố, sau đó so sánh với annotation. Đừng chỉ nhìn tên method Java: method name có thể được đổi bằng `field`, và parent type có thể đến từ `typeName`, class-level default hoặc source parameter.

## 13. Quy tắc đặt tên và tổ chức mapping

- Giữ tên method trùng field name nếu không có lý do cần tên khác.
- Dùng `typeName` tường minh khi Java class không trùng GraphQL type hoặc khi mapping không thể suy luận rõ.
- Dùng `field`/`value` khi method name khác field name; chọn một quy ước nhất quán cho toàn project.
- Nhóm các handler theo parent type để dễ tra cứu, ví dụ `BookController`, `AuthorController`.
- Không đăng ký cùng một field bằng cả annotated controller và runtime wiring thủ công.
- Giữ method resolver mỏng; truy cập dữ liệu và quy tắc nghiệp vụ thuộc service.
- Với field liên kết được resolve cho nhiều parent object, cân nhắc `@BatchMapping` hoặc DataLoader để tránh N+1.

`typeName` và `field` xác định chính xác vị trí của một resolver trong GraphQL schema. Khi hiểu cách khai báo tường minh, suy luận từ source/method và cách dùng annotation chuyên biệt cho root operation, việc nối SDL với controller trong Spring for GraphQL sẽ rõ ràng và ít lỗi hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — SchemaMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/SchemaMapping.html)
- [Spring for GraphQL — BatchMapping API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/data/method/annotation/BatchMapping.html)
