# Query mapping theo tên tùy chỉnh trong Spring for GraphQL

Trong Spring for GraphQL, `@QueryMapping` kết nối một phương thức controller Java với một field thuộc root `Query` của GraphQL schema. Mặc định, tên field được suy ra từ tên phương thức. Khi tên trong Java cần khác tên công khai của API, ta có thể chỉ định tên field ngay trên annotation bằng `name` hoặc `value`.

Khả năng đặt tên riêng giúp giữ tên phương thức Java rõ nghĩa theo quy ước mã nguồn, đồng thời duy trì tên GraphQL ổn định theo hợp đồng API. Điều quan trọng là phải phân biệt tên field với tên argument: `@QueryMapping` đổi tên field được ánh xạ, còn `@Argument` xác định argument nào được bind vào tham số Java.

## 1. Cách ánh xạ tên mặc định

Xét schema SDL:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
}
```

Với controller:

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

Spring suy ra field GraphQL từ tên phương thức `bookById`, nên phương thức được ánh xạ tới `Query.bookById`. Tên type cha `Query` được đặt sẵn bởi `@QueryMapping`; ta không cần khai báo lại.

Nếu tên phương thức Java trùng với tên field SDL, không cần truyền thuộc tính tên. Đây là cách ngắn gọn và dễ đọc khi hai bên có cùng quy ước đặt tên.

## 2. Đổi tên field bằng `name`

Giả sử schema muốn công khai field `book`, nhưng trong Java ta muốn dùng tên phương thức mô tả rõ hành động `findBookById`:

```graphql
type Query {
    book(id: ID!): Book
}
```

Khai báo tên field rõ ràng trong annotation:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping(name = "book")
    Book findBookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Trong trường hợp này:

- Tên phương thức Java là `findBookById`.
- Tên field trong GraphQL schema là `book`.
- `@QueryMapping` vẫn ánh xạ vào root type `Query`.
- `@Argument("id")` bind argument `id` của field `book` vào tham số Java `id`.

Client gọi field theo tên trong schema:

```graphql
query {
    book(id: "book-01") {
        id
        title
    }
}
```

Client không biết và cũng không cần biết phương thức Java có tên `findBookById`. Tên phương thức là chi tiết triển khai phía server; tên field GraphQL là một phần hợp đồng API công khai.

## 3. Dùng `value` thay cho `name`

`@QueryMapping` cung cấp cả hai thuộc tính `name` và `value`. Chúng là hai alias cùng chỉ định tên field của `@SchemaMapping`.

Hai cách viết sau có cùng ý nghĩa:

```java
@QueryMapping(name = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

```java
@QueryMapping(value = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Java cũng cho phép truyền giá trị trực tiếp khi annotation chỉ có một giá trị được gán theo thuộc tính `value`:

```java
@QueryMapping("book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Trong một codebase, nên chọn một cách viết nhất quán. Dùng `name = "..."` thường dễ đọc khi người xem cần nhận ra ngay đây là tên field GraphQL. Không cần đồng thời đặt cả `name` và `value` cho cùng một mapping.

## 4. Đổi tên field không làm đổi tên argument

Tên field và tên argument là hai cấp tên riêng biệt trong GraphQL.

Schema:

```graphql
type Query {
    lookupBook(bookId: ID!, includeReviews: Boolean): Book
}
```

Controller có thể dùng tên phương thức và tên tham số Java khác:

```java
@QueryMapping(name = "lookupBook")
Book findBook(
        @Argument("bookId") String id,
        @Argument("includeReviews") Boolean withReviews) {

    return bookService.findById(id, withReviews);
}
```

Ở đây:

- `name = "lookupBook"` ánh xạ phương thức vào field `Query.lookupBook`.
- `@Argument("bookId")` lấy argument GraphQL `bookId` và gán vào tham số Java `id`.
- `@Argument("includeReviews")` lấy argument `includeReviews` và gán vào tham số Java `withReviews`.

Query tương ứng:

```graphql
query {
    lookupBook(bookId: "book-01", includeReviews: true) {
        id
        title
    }
}
```

Nếu chỉ đổi tên field bằng `@QueryMapping(name = "lookupBook")` nhưng schema vẫn khai báo argument `bookId`, thì tham số Java cần bind đúng tên `bookId`. `@QueryMapping` không tự đổi tên argument, không đặt giá trị mặc định và cũng không thay thế quy tắc nullability của SDL.

## 5. Khi nào nên dùng tên tùy chỉnh?

Tên tùy chỉnh hữu ích trong một số tình huống:

| Tình huống | Tên phương thức Java | Tên field GraphQL |
|---|---|---|
| Muốn tên Java diễn tả rõ thao tác | `findBookById` | `book` |
| Giữ API cũ trong khi đổi tên code | `loadLegacyBook` | `bookById` |
| Tên GraphQL theo quy ước miền nghiệp vụ | `searchCatalogEntries` | `catalogSearch` |
| Dùng tên Java tránh từ viết tắt nội bộ | `findCustomerAccount` | `account` |

Không nên đổi tên field chỉ để làm code Java trông ngắn hơn nếu việc đó khiến API thiếu nhất quán. Tên field GraphQL nên được chọn theo ngôn ngữ miền nghiệp vụ, dễ hiểu với client và ổn định giữa các lần phát hành.

Nếu API đã được client sử dụng, đổi tên field GraphQL là thay đổi hợp đồng. Dùng tên tùy chỉnh có thể giúp đổi tên phương thức Java mà không làm thay đổi API, nhưng nếu đổi `name` thì client cũng phải chuyển sang field mới. Trong quá trình migration, có thể giữ field cũ trong schema, đánh dấu deprecated và chuyển cả hai resolver về cùng service cho tới khi client hoàn tất nâng cấp.

Ví dụ giữ API cũ và công bố field mới:

```graphql
type Query {
    bookById(id: ID!): Book @deprecated(reason: "Use book instead")
    book(id: ID!): Book
}
```

```java
@QueryMapping(name = "book")
Book findBook(@Argument("id") String id) {
    return bookService.findById(id);
}

@QueryMapping(name = "bookById")
Book findBookLegacy(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Hai field công khai có thể cùng gọi một service method. Sau khi client ngừng sử dụng field cũ, nhóm phát triển có thể loại bỏ field deprecated theo quy trình versioning của API.

## 6. `@QueryMapping` là shortcut cho `@SchemaMapping`

`@QueryMapping` là composed annotation của `@SchemaMapping` với `typeName = "Query"`. Thuộc tính `name` và `value` của nó là alias cho thuộc tính `field` của `@SchemaMapping`.

Vì vậy, ví dụ:

```java
@QueryMapping(name = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

có cùng mục đích ánh xạ với:

```java
@SchemaMapping(typeName = "Query", field = "book")
Book findBookById(@Argument("id") String id) {
    return bookService.findById(id);
}
```

Nên dùng `@QueryMapping` khi xử lý field của query root để biểu đạt rõ loại operation. Dùng `@SchemaMapping` khi cần ánh xạ field thuộc object type khác, chẳng hạn `Book.author`. `@QueryMapping` không phải công cụ để chuyển phương thức sang `Mutation` hoặc `Subscription`; các root đó có annotation tương ứng.

## 7. Kết hợp tên tùy chỉnh với input object

Tên field tùy chỉnh không giới hạn kiểu argument. Nếu query nhận một input object, vẫn dùng `@Argument` để bind input như bình thường.

SDL:

```graphql
input BookSearchInput {
    keyword: String
    authorId: ID
    page: Int
}

type Query {
    searchBooks(criteria: BookSearchInput!): [Book!]!
}
```

Java:

```java
public record BookSearchInput(
    String keyword,
    String authorId,
    Integer page
) {}
```

```java
@QueryMapping(name = "searchBooks")
List<Book> findBooks(@Argument("criteria") BookSearchInput input) {
    return bookService.search(input);
}
```

`searchBooks` là tên field GraphQL, `findBooks` là tên phương thức Java, còn `criteria` là tên argument trong SDL. Ba tên này có thể khác nhau vì chúng phục vụ ba vai trò riêng.

## 8. Kiểm thử mapping theo tên tùy chỉnh

Khi đặt tên tùy chỉnh, cần kiểm tra client gọi được field theo đúng tên trong SDL và mapping không vô tình dựa vào tên phương thức Java.

Ví dụ controller:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping(name = "book")
    Book findBookById(@Argument("id") String id) {
        return bookService.findById(id);
    }
}
```

Test bằng `GraphQlTester`:

```java
@GraphQlTest(BookController.class)
class BookQueryMappingTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void mapsCustomGraphQlFieldName() {
        given(bookService.findById("book-01"))
            .willReturn(new Book("book-01", "GraphQL Basics"));

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    book(id: "book-01") {
                        id
                        title
                    }
                }
                """)
            .execute();

        response.path("book.id").entity(String.class).isEqualTo("book-01");
        response.path("book.title").entity(String.class).isEqualTo("GraphQL Basics");
    }
}
```

Đây là ví dụ minh họa; các import, static import `given`, lớp `Book`, `BookService` và SDL có field `Query.book` cần được cung cấp trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Điểm quan trọng của test là document gọi `book`, dù phương thức Java có tên `findBookById`.

### Các tình huống nên kiểm thử

- Field được gọi bằng tên tùy chỉnh trong SDL và trả về dữ liệu đúng.
- Argument được bind theo tên GraphQL dù tên tham số Java khác.
- Field cũ và field mới cùng hoạt động khi đang migration API.
- Query gọi tên phương thức Java thay vì tên field GraphQL phải bị GraphQL từ chối nếu schema không khai báo field đó.
- Field nullable, Non-null và lỗi resolver vẫn tuân theo hợp đồng SDL.

## 9. Lỗi thường gặp

**Dùng tên phương thức thay vì tên field đã cấu hình.** Khi annotation có `name = "book"`, client phải gọi `book`, không gọi `findBookById` trừ khi schema có field đó riêng.

**Nhầm tên field với tên argument.** `@QueryMapping(name = "lookupBook")` đổi field; `@Argument("bookId")` chọn argument. Cần kiểm tra cả hai với SDL.

**Không khai báo field tương ứng trong SDL.** Annotation chỉ đăng ký handler cho field; nó không tự thêm field mới vào schema. Bảo đảm SDL có field cần ánh xạ.

**Đặt nhiều handler cho cùng một field.** Một field không nên có nhiều handler cạnh tranh trong runtime wiring. Kiểm tra các controller và cấu hình mapping để tránh đăng ký trùng.

**Dùng `@QueryMapping` cho field không thuộc Query root.** Annotation này luôn ánh xạ vào `Query`. Với field của object type, dùng `@SchemaMapping`; với mutation hoặc subscription root, dùng annotation tương ứng.

**Đổi tên API mà không đánh giá client.** Tên field là hợp đồng công khai. Nếu cần đổi, cân nhắc giữ field cũ, đánh dấu deprecated và có kế hoạch loại bỏ rõ ràng.

## Kết luận

`@QueryMapping(name = "...")` hoặc `@QueryMapping(value = "...")` cho phép ánh xạ một phương thức Java vào tên field tùy chỉnh trên root `Query`. Nếu không đặt tên, Spring dùng tên phương thức. Tên field, tên argument và tên phương thức là ba khái niệm riêng: dùng `@QueryMapping` để chọn field, `@Argument` để bind argument, và chọn tên phương thức theo quy ước Java. Hãy kiểm thử bằng query sử dụng đúng tên công khai trong SDL để bảo đảm mapping hoạt động như mong đợi.
