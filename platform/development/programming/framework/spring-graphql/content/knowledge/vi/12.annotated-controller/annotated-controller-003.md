# `@QueryMapping` trong Spring for GraphQL

`@QueryMapping` là annotation của Spring for GraphQL dùng để ánh xạ một phương thức trong controller Java với một field thuộc root `Query` của GraphQL schema. Khi client gửi query có chọn field đó, Spring gọi phương thức tương ứng, lấy giá trị trả về và để GraphQL hoàn thiện response theo selection set của client.

Trong một API Spring for GraphQL, SDL định nghĩa hợp đồng mà client được phép truy vấn; `@QueryMapping` kết nối một field query với logic Java thực thi nó. Annotation này giúp viết resolver theo kiểu controller, dễ kết hợp với service, dependency injection, xử lý argument và kiểm thử.

## 1. `@QueryMapping` giải quyết việc gì?

Xét schema SDL:

```graphql
type Query {
    greeting: String!
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Schema khai báo hai field ở query root:

- `greeting` không nhận argument và trả về chuỗi khác `null`.
- `bookById` nhận argument `id` bắt buộc và trả về một `Book` hoặc `null`.

Trong Spring, có thể viết controller:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    String greeting() {
        return "Hello from Spring for GraphQL";
    }

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

`@QueryMapping` đánh dấu phương thức là data fetcher cho một field trên query root. Phương thức `greeting` được ánh xạ tới `Query.greeting`, còn `bookById` được ánh xạ tới `Query.bookById`.

Khi client gửi:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
    }
}
```

Spring gọi `bookById`, truyền giá trị argument `id`, rồi GraphQL sử dụng object `Book` trả về để phân giải `id` và `title`. Những field đơn giản đã có property trên object có thể được xử lý bằng default property fetcher mà không cần viết thêm resolver.

## 2. Quan hệ giữa `@QueryMapping` và SDL

`@QueryMapping` không tự tạo field trong schema. Field phải được khai báo trong SDL và tên ánh xạ phải khớp với tên field đó.

Ví dụ, nếu SDL khai báo:

```graphql
type Query {
    findBook(id: ID!): Book
}
```

thì phương thức Java cần ánh xạ tới `Query.findBook`. Nếu chỉ viết:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Spring sẽ tìm field theo tên phương thức `bookById`. Vì schema chỉ có `findBook`, mapping không khớp. Có thể đổi tên phương thức hoặc chỉ định tên field rõ ràng:

```java
@QueryMapping(name = "findBook")
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Khi không chỉ định tên, Spring sử dụng tên phương thức làm tên field. Dùng thuộc tính `name` khi muốn tên phương thức Java khác tên GraphQL hoặc muốn khai báo mapping tường minh.

`@QueryMapping` là dạng rút gọn của `@SchemaMapping(typeName = "Query")`. Hai cách dưới đây có cùng mục đích:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

```java
@SchemaMapping(typeName = "Query", field = "bookById")
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Thông thường nên dùng `@QueryMapping` cho field query root để thể hiện rõ ý định. `@SchemaMapping` linh hoạt hơn khi cần ánh xạ field thuộc object type khác, ví dụ `Book.author`.

## 3. Nhận argument bằng `@Argument`

Một query field có thể khai báo argument trong SDL. Spring dùng `@Argument` để lấy giá trị tương ứng từ request và chuyển đổi sang kiểu Java phù hợp.

SDL:

```graphql
type Query {
    booksByAuthor(authorId: ID!, limit: Int): [Book!]!
}
```

Controller:

```java
@QueryMapping
List<Book> booksByAuthor(
        @Argument("authorId") String authorId,
        @Argument("limit") Integer limit) {

    return bookService.findByAuthor(authorId, limit);
}
```

`authorId` là argument bắt buộc trong SDL, còn `limit` có thể không được gửi. Dùng `Integer` cho argument có thể vắng mặt giúp biểu diễn giá trị `null`; nếu schema khai báo `Int!`, có thể dùng kiểu Java nguyên thủy hoặc wrapper tùy cách xử lý giá trị mặc định của ứng dụng.

### Dùng tên argument tường minh

Tên argument trong SDL không nhất thiết trùng tên tham số Java. Hãy truyền tên GraphQL vào `@Argument` để tránh phụ thuộc vào tên tham số được giữ trong bytecode:

```java
@QueryMapping
Book book(@Argument("bookId") String id) {
    return bookService.findById(id);
}
```

Với schema:

```graphql
type Query {
    book(bookId: ID!): Book
}
```

Spring lấy argument `bookId` và gán vào tham số Java `id`.

### Nhận input object

Khi query có nhiều điều kiện lọc, có thể gom chúng vào input object:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
    publishedAfter: String
}

type Query {
    searchBooks(filter: BookFilter!): [Book!]!
}
```

Java có thể dùng record làm kiểu input:

```java
public record BookFilter(
    String keyword,
    String authorId,
    String publishedAfter
) {}
```

```java
@QueryMapping
List<Book> searchBooks(@Argument("filter") BookFilter filter) {
    return bookService.search(filter);
}
```

Spring for GraphQL sử dụng cơ chế binding để chuyển input map thành object Java. Các field trong input object cần có kiểu tương thích với SDL. Với dữ liệu đầu vào phức tạp, nên bổ sung validation cho những quy tắc nghiệp vụ như giới hạn độ dài keyword hoặc khoảng ngày hợp lệ.

## 4. Kiểu trả về của phương thức query

Kiểu trả về Java cần tương thích với kiểu mà SDL khai báo. Một số ví dụ thường gặp:

| SDL | Kiểu Java thường dùng | Ý nghĩa |
|---|---|---|
| `greeting: String!` | `String` | Trả về chuỗi, không được là `null` khi thực thi thành công. |
| `book: Book` | `Book` | Trả về object hoặc `null`. |
| `books: [Book!]!` | `List<Book>` | Trả về danh sách, các phần tử không được `null`. |
| `count: Int!` | `Integer` hoặc `int` | Trả về số nguyên. |

Ví dụ trả về danh sách:

```java
@QueryMapping
List<Book> books() {
    return bookService.findAll();
}
```

Nếu SDL khai báo `[Book!]!`, service nên trả về list rỗng khi không có sách, thay vì `null`. Nếu trả về `null` cho field Non-null, GraphQL phát sinh execution error và áp dụng quy tắc null propagation.

### Trả về kết quả bất đồng bộ

Spring for GraphQL hỗ trợ kiểu trả về bất đồng bộ như `CompletableFuture` và Reactor `Mono`. Điều này hữu ích khi service gọi hệ thống khác hoặc dùng API non-blocking:

```java
@QueryMapping
CompletableFuture<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdAsync(id);
}
```

Hoặc với Reactor:

```java
@QueryMapping
Mono<Book> bookById(@Argument("id") String id) {
    return bookService.findByIdReactive(id);
}
```

Kiểu bất đồng bộ cho phép GraphQL chờ kết quả mà không cần chặn thread request trong lúc I/O đang diễn ra. Cần chọn kiểu trả về nhất quán với mô hình lập trình của service và tránh gọi thao tác blocking trên scheduler dành cho tác vụ non-blocking.

## 5. Tách controller và service

Controller nên tập trung vào việc nhận request GraphQL, lấy argument và điều phối tới service. Quy tắc nghiệp vụ, truy cập repository và transaction nên được đặt ở tầng phù hợp.

Ví dụ:

```java
@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    Book findById(String id) {
        return bookRepository.findById(id).orElse(null);
    }
}
```

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Trong ví dụ này, trường `bookById` được khai báo nullable (`Book` không có `!`), nên trường hợp không tìm thấy sách có thể trả về `null`. Nếu đổi SDL thành `Book!`, cần thay đổi hợp đồng xử lý khi không tìm thấy dữ liệu, chẳng hạn ném exception nghiệp vụ và ánh xạ thành GraphQL error phù hợp.

## 6. Xử lý lỗi trong `@QueryMapping`

Khi resolver ném exception, GraphQL trả response có phần `errors`. Cách chuyển exception thành thông tin phù hợp cho client nên được quản lý tập trung, ví dụ bằng `DataFetcherExceptionResolver` hoặc cơ chế xử lý lỗi đã cấu hình trong Spring for GraphQL.

Không nên trả stack trace, câu SQL, thông tin kết nối hoặc chi tiết nội bộ trong message lỗi. Hãy phân biệt lỗi nghiệp vụ như không tìm thấy dữ liệu với lỗi hệ thống như database không sẵn sàng, sau đó ánh xạ thành mã và thông điệp phù hợp.

Ví dụ minh họa resolver có thể ném exception nghiệp vụ:

```java
@QueryMapping
Book requiredBook(@Argument("id") String id) {
    Book book = bookService.findById(id);
    if (book == null) {
        throw new BookNotFoundException(id);
    }
    return book;
}
```

Trong trường hợp này, `BookNotFoundException` nên được xử lý bởi exception resolver để tạo `GraphQLError` phù hợp. Nếu schema khai báo field là Non-null, lỗi còn có thể làm `null` lan truyền lên field cha theo cấu trúc schema.

## 7. Bảo mật cho query field

Query có thể trả về dữ liệu riêng tư hoặc dữ liệu chỉ một nhóm người dùng được xem. Có thể kết hợp Spring Security method security với controller method:

```java
@Controller
class AccountController {

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    List<Account> allAccounts() {
        return accountService.findAll();
    }
}
```

Để `@PreAuthorize` hoạt động, ứng dụng cần bật method security bằng cấu hình phù hợp, ví dụ `@EnableMethodSecurity`, và bảo đảm dependency Spring Security được cấu hình. Kiểm tra quyền ở tầng service cũng có thể phù hợp nếu cùng một nghiệp vụ được gọi từ nhiều entry point.

Không nên coi việc ẩn field khỏi tài liệu hoặc tắt introspection là biện pháp bảo mật. Server phải kiểm tra quyền trên request thực tế và tránh trả dữ liệu nhạy cảm cho người dùng không đủ quyền.

## 8. Phân biệt `@QueryMapping` với các annotation mapping khác

Spring for GraphQL cung cấp một số annotation có mục đích khác nhau:

| Annotation | Field được ánh xạ | Trường hợp dùng |
|---|---|---|
| `@QueryMapping` | Field thuộc query root | Đọc dữ liệu hoặc thực hiện truy vấn. |
| `@MutationMapping` | Field thuộc mutation root | Tạo, cập nhật hoặc xóa dữ liệu. |
| `@SubscriptionMapping` | Field thuộc subscription root | Cung cấp luồng sự kiện cho client. |
| `@SchemaMapping` | Field của một object type bất kỳ | Phân giải field lồng nhau, ví dụ `Book.author`. |

Ví dụ query root:

```java
@QueryMapping
Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Ví dụ mutation root:

```java
@MutationMapping
Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

Ví dụ field lồng nhau:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Chọn annotation theo vị trí field trong schema. `@QueryMapping` không dùng để ánh xạ field `Book.author`, vì field đó thuộc object type `Book`, không thuộc query root.

## 9. Kiểm thử `@QueryMapping` bằng `GraphQlTester`

`@GraphQlTest` tạo test slice cho thành phần Spring for GraphQL, còn `GraphQlTester` gửi GraphQL document và kiểm tra response. Service có thể được mock để tập trung kiểm thử mapping và dữ liệu trả về.

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void returnsBookById() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("bookById.id").entity(String.class).isEqualTo("book-01");
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

Đây là ví dụ minh họa; các import, static import `given`, lớp `Book`, `BookService` và SDL khai báo `Query.bookById` cùng `Book` cần có trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Ví dụ đã kiểm tra cả `id` và `title`; có thể bổ sung verify để xác nhận service được gọi với đúng ID.

### Các trường hợp nên kiểm thử

- Query field hợp lệ với argument đúng và trả về dữ liệu mong đợi.
- Argument bắt buộc bị thiếu hoặc sai kiểu; GraphQL từ chối request trước khi gọi resolver.
- Field nullable không tìm thấy dữ liệu và trả về `null` đúng hợp đồng.
- Field Non-null gặp `null` hoặc exception; response có `errors` và null propagation phù hợp.
- Tên field trong `@QueryMapping` không khớp SDL; kiểm tra lỗi khi xây dựng schema hoặc đăng ký mapping.
- Người dùng không đủ quyền truy cập; xác minh dữ liệu không bị trả về.

## 10. Lỗi thường gặp

**Quên khai báo field trong SDL.** `@QueryMapping` chỉ đăng ký resolver cho field; nó không tự thêm field vào schema. Hãy khai báo field trong query root.

**Tên phương thức không khớp tên field.** Mặc định Spring dùng tên phương thức. Nếu tên khác, đổi tên phương thức hoặc chỉ định `@QueryMapping(name = "...")`.

**Lấy sai argument.** Tên argument trong SDL khác tên biến Java. Dùng `@Argument("graphqlName")` để chỉ rõ tên cần bind.

**Dùng `@QueryMapping` cho field lồng nhau.** Chỉ dùng annotation này cho query root. Với field thuộc object type như `Book.author`, dùng `@SchemaMapping` hoặc `@BatchMapping`.

**Không đồng bộ nullability.** Nếu SDL khai báo `Book!` nhưng service có thể trả `null`, response sẽ có execution error. Chọn nullable hoặc xử lý trường hợp thiếu dữ liệu theo đúng hợp đồng.

**Đặt truy cập dữ liệu và nghiệp vụ phức tạp trực tiếp trong controller.** Tách logic vào service giúp dễ kiểm thử, tái sử dụng và quản lý transaction.

**Không kiểm tra quyền truy cập.** Query là điểm truy cập dữ liệu; cần áp dụng authorization theo người dùng và theo nghiệp vụ.

## Kết luận

`@QueryMapping` kết nối phương thức controller Java với field trên root `Query` của GraphQL schema. Spring mặc định dùng tên phương thức làm tên field, cho phép chỉ định tên khác bằng `name`, và dùng `@Argument` để bind dữ liệu client gửi lên. Hãy giữ SDL và mapping nhất quán, trả về kiểu phù hợp với nullability, tách nghiệp vụ vào service, bảo vệ query bằng authorization và kiểm thử operation bằng `GraphQlTester`.
