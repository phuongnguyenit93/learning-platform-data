# Field resolver và parent source trong Spring for GraphQL

Trong GraphQL, mỗi field được chọn trong query cần được phân giải thành một giá trị. **Field resolver** là thành phần cung cấp giá trị đó. Khi GraphQL đi từ một object cha xuống field con, object cha được truyền cho resolver của field con dưới tên **source** hoặc **parent source**.

Trong Spring for GraphQL, các phương thức `@QueryMapping`, `@MutationMapping` và `@SchemaMapping` kết nối field trong schema với phương thức Java. Hiểu rõ parent source giúp ta biết dữ liệu của field con đến từ đâu, khi nào cần viết resolver riêng và khi nào GraphQL có thể đọc trực tiếp thuộc tính của object.

## 1. Field resolver là gì?

Xét schema:

```graphql
type Query {
    bookById(id: ID!): Book
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
```

Client gửi query:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            id
            name
        }
    }
}
```

GraphQL không xem toàn bộ query như một lời gọi hàm duy nhất. Nó phân giải từng field được chọn:

1. Field gốc `Query.bookById` tìm một quyển sách theo argument `id`.
2. Từ object `Book` nhận được, GraphQL phân giải `id`, `title` và `author`.
3. Khi phân giải `author`, GraphQL sử dụng object `Book` làm source cho field đó.
4. Sau khi có object `Author`, GraphQL phân giải tiếp `Author.id` và `Author.name`.

Mỗi field có thể dùng data fetcher mặc định hoặc một resolver do ứng dụng cung cấp. Resolver thường cần thiết khi field phải gọi service, tính toán giá trị, kiểm tra ngữ cảnh hoặc tải một quan hệ chưa có sẵn trong object cha.

## 2. Parent source là gì?

**Parent source** là object mà GraphQL đang phân giải field con. Nó chính là kết quả được trả về từ field cha trong cây thực thi query.

Ví dụ, khi resolver `Query.bookById` trả về một object `Book`, object đó trở thành source khi GraphQL phân giải các field `Book.id`, `Book.title` và `Book.author`. Nếu `Book.author` trả về object `Author`, object `Author` tiếp tục trở thành source cho các field `Author.id` và `Author.name`.

Có thể hình dung luồng dữ liệu như sau:

```text
Query.bookById(id)
        |
        | trả về Book
        v
  source = Book
    |       |       |
    id    title   author
                    |
                    | trả về Author
                    v
              source = Author
                  |    |
                  id  name
```

Source không bắt buộc phải là entity của JPA hay object lấy trực tiếp từ database. Nó có thể là Java record, POJO, DTO, projection hoặc `Map`, miễn là object đó được resolver cha trả về và có thể cung cấp dữ liệu cho các field con.

Điểm quan trọng là resolver field con nhận đúng object cha của vị trí đang được phân giải. Nếu query trả về danh sách sách, resolver của field trên `Book` được thực thi cho từng phần tử và mỗi lần nhận source là một `Book` tương ứng.

## 3. Default field resolver và PropertyDataFetcher

Không phải field nào cũng cần viết một phương thức `@SchemaMapping`. GraphQL Java có data fetcher mặc định để đọc thuộc tính từ source object. Cơ chế này thường được gọi là `PropertyDataFetcher`.

Ví dụ Java record:

```java
public record Book(
    String id,
    String title,
    String authorName
) {}
```

Với schema:

```graphql
type Book {
    id: ID!
    title: String!
    authorName: String!
}
```

Nếu resolver cha trả về `Book`, GraphQL có thể lấy `id`, `title` và `authorName` từ các accessor tương ứng của record. Không cần tạo ba phương thức resolver riêng chỉ để trả lại đúng những thuộc tính đã có trong object.

Với JavaBean, các getter như `getTitle()` hoặc `isAvailable()` thường được dùng để đọc property. Với `Map`, data fetcher có thể đọc giá trị theo key. Cần bảo đảm tên field GraphQL khớp với tên property mà data fetcher có thể truy cập.

Ví dụ controller chỉ xử lý field gốc:

```java
@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }
}
```

Khi `BookService` trả về record hoặc POJO có các property tương ứng, GraphQL có thể tự phân giải những field đơn giản. Ta chỉ cần viết resolver riêng cho những field cần logic bổ sung.

## 4. Viết field resolver bằng `@SchemaMapping`

Giả sử object `Book` chỉ lưu `authorId`, còn thông tin tác giả được quản lý bởi `AuthorService`:

```java
public record Book(String id, String title, String authorId) {}

public record Author(String id, String name) {}
```

Schema:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    authorId: ID!
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

`author` không phải property có sẵn trong record `Book`. Ta cần một resolver để tìm tác giả từ `authorId`:

```java
@Controller
class BookController {

    private final BookService bookService;
    private final AuthorService authorService;

    BookController(BookService bookService, AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    Author author(Book source) {
        return authorService.findById(source.authorId());
    }
}
```

Trong phương thức `author(Book source)`, tham số `source` chính là object `Book` mà field cha `bookById` trả về. Resolver đọc `source.authorId()` để tải object `Author`, sau đó GraphQL tiếp tục phân giải các field con của `Author`.

### Quy tắc ánh xạ tên

`@SchemaMapping` cho phép khai báo rõ `typeName` và `field`:

```java
@SchemaMapping(typeName = "Book", field = "author")
Author author(Book source) {
    // ...
}
```

Trong trường hợp thông thường, Spring có thể suy luận type từ kiểu source và field từ tên phương thức. Vì vậy, ví dụ sau cũng có thể ánh xạ đến `Book.author`:

```java
@SchemaMapping
Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Khi tên Java khác tên GraphQL hoặc muốn làm rõ ý định, nên khai báo tường minh `typeName` và `field`. `@SchemaMapping` có thể đặt trên phương thức controller; Spring dùng metadata đó để đăng ký data fetcher cho field tương ứng.

## 5. Phân biệt parent source với `@Argument`

Parent source và argument đều có thể xuất hiện trong chữ ký phương thức resolver, nhưng chúng đại diện cho hai nguồn dữ liệu khác nhau:

| Thành phần | Lấy dữ liệu từ đâu? | Ví dụ |
|---|---|---|
| Parent source | Object cha đã được phân giải | `Book source` trong resolver `Book.author` |
| `@Argument` | Argument của field hiện tại do client truyền | `@Argument String id` trong `Query.bookById` |

Ví dụ query:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    reviews(minRating: Int): [Review!]!
}
```

Resolver gốc nhận argument `id`:

```java
@QueryMapping
Book bookById(@Argument String id) {
    return bookService.findById(id);
}
```

Resolver field con vừa nhận source là `Book`, vừa nhận argument `minRating` của field `reviews`:

```java
@SchemaMapping(typeName = "Book", field = "reviews")
List<Review> reviews(Book source, @Argument Integer minRating) {
    return reviewService.findByBookId(source.id(), minRating);
}
```

Ở đây `source.id()` xác định quyển sách đang được phân giải; `minRating` là điều kiện lọc do client gửi cho field `reviews`. Không nên nhầm `id` của query gốc với argument của field con: mỗi resolver nhận argument thuộc field mà nó xử lý.

## 6. Luồng thực thi qua nhiều cấp object

Với query:

```graphql
query {
    bookById(id: "book-01") {
        title
        author {
            name
        }
    }
}
```

Luồng thực thi được chia thành các bước:

1. Spring gọi resolver `Query.bookById`, truyền `id` từ `@Argument`.
2. Resolver trả về object `Book`.
3. GraphQL dùng `Book` làm source để lấy `title` bằng default property fetcher.
4. GraphQL gọi resolver `Book.author`, truyền cùng object `Book` làm source.
5. Resolver trả về `Author`.
6. GraphQL dùng `Author` làm source để lấy `name`.

Nếu client chỉ yêu cầu `title` mà không yêu cầu `author`, resolver `Book.author` không cần chạy. GraphQL chỉ phân giải những field nằm trong selection set sau khi áp dụng các directive điều khiển lựa chọn như `@skip` và `@include`.

Điều này cho phép API tải dữ liệu theo cấu trúc query. Tuy nhiên, nó cũng có nghĩa một field resolver có thể được gọi nhiều lần khi field xuất hiện trên nhiều parent object trong một danh sách hoặc nhánh lồng nhau.

## 7. Parent source, null và lỗi phân giải

Nếu resolver cha trả về `null` cho một field nullable, GraphQL không có object source để tiếp tục phân giải các field con của object đó. Giá trị của nhánh tương ứng sẽ là `null`.

Nếu field cha được khai báo Non-null nhưng resolver lại trả về `null`, GraphQL phát sinh execution error và áp dụng quy tắc null propagation. Lỗi có thể lan lên field nullable gần nhất, tùy theo cấu trúc Non-null của schema.

Ví dụ:

```graphql
type Query {
    bookById(id: ID!): Book
}

type Book {
    id: ID!
    author: Author
}
```

Nếu không tìm thấy sách, `bookById` có thể trả về `null` và client nhận `bookById: null`. Nếu tìm thấy sách nhưng không có tác giả, resolver `author` có thể trả về `null` vì field này nullable. Cần chọn nullability phù hợp với quy tắc nghiệp vụ và khả năng cung cấp dữ liệu thực tế.

Nếu service ném exception trong resolver, lỗi được xử lý theo cơ chế exception handling của Spring for GraphQL/GraphQL Java. Nên chuyển lỗi nghiệp vụ thành thông tin phù hợp cho client bằng `DataFetcherExceptionResolver` hoặc cơ chế xử lý lỗi đã cấu hình, đồng thời tránh đưa chi tiết nội bộ nhạy cảm vào response.

## 8. Parent source và hiệu năng truy vấn

Một resolver thường hoạt động tốt khi xử lý một parent object. Nhưng khi query trả về danh sách lớn, resolver quan hệ có thể tạo ra vấn đề N+1.

Ví dụ query:

```graphql
query {
    books {
        id
        title
        author {
            name
        }
    }
}
```

Nếu `books` trả về 100 quyển sách và resolver `Book.author` gọi database một lần cho từng quyển, ứng dụng có thể thực hiện 1 truy vấn lấy sách cộng 100 truy vấn lấy tác giả. Đây là vấn đề N+1.

Parent source vẫn cần thiết để biết mỗi field `author` thuộc về sách nào, nhưng việc tải dữ liệu có thể được gom nhóm. Spring for GraphQL hỗ trợ `@BatchMapping` và tích hợp DataLoader để nạp dữ liệu theo batch, giảm số lần gọi database hoặc service. Ví dụ, resolver batch nhận danh sách `Book` và trả về mapping từ từng sách đến tác giả tương ứng.

Không phải field resolver nào cũng cần batch. Với object đã có đủ dữ liệu, default property fetcher thường đơn giản và hiệu quả. Chỉ thêm resolver khi cần logic, và cân nhắc batching khi resolver tải quan hệ lặp lại trên nhiều source object.

## 9. Kiểm thử field resolver và parent source

Có thể dùng `GraphQlTester` để kiểm tra toàn bộ luồng từ query đến field resolver. Những tình huống nên có:

- Query field gốc nhận đúng argument và trả về đúng object cha.
- Field có property sẵn trong source được phân giải đúng bằng default property fetcher.
- Field quan hệ dùng `@SchemaMapping` nhận đúng parent source và trả về object con.
- Field con nhận đúng argument riêng của nó khi kết hợp với source parameter.
- Khi parent object hoặc quan hệ không tồn tại, response tuân theo nullability trong SDL.
- Khi resolver phát sinh lỗi, response có `errors` phù hợp và không lộ thông tin nội bộ.
- Khi query trả về nhiều parent object, kiểm tra số lần truy cập repository hoặc service để phát hiện N+1.

Ví dụ kiểm thử bằng `GraphQlTester`:

```java
@GraphQlTest(BookController.class)
class BookControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    @Test
    void resolvesAuthorFromParentBook() {
        Book book = new Book("book-01", "GraphQL Basics", "author-01");
        Author author = new Author("author-01", "An Nguyen");
        given(bookService.findById("book-01")).willReturn(book);
        given(authorService.findById("author-01")).willReturn(author);

        GraphQlTester.Response response = graphQlTester.document("""
                query {
                    bookById(id: "book-01") {
                        title
                        author {
                            name
                        }
                    }
                }
                """)
            .execute();
        response.path("bookById.title").entity(String.class).isEqualTo("GraphQL Basics");
        response.path("bookById.author.name").entity(String.class).isEqualTo("An Nguyen");
    }
}
```

Đây là ví dụ minh họa cấu trúc kiểm thử; các import và static import `given` được lược bỏ, đồng thời schema SDL tương ứng cần có trong test context. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockitoBean` hoặc `@MockBean`. Có thể bổ sung verify rằng `authorService.findById("author-01")` được gọi với ID lấy từ parent source.

## 10. Lỗi thường gặp

**Nhầm parent source với argument.** `Book source` là object cha; `@Argument` lấy giá trị argument của field hiện tại. Xác định rõ dữ liệu đến từ kết quả field cha hay từ query do client gửi.

**Viết resolver cho mọi field.** Nếu field đã tương ứng với property có thể truy cập trên record, POJO hoặc Map, default property fetcher có thể xử lý. Resolver thủ công chỉ cần thiết khi có logic bổ sung.

**Tên field không khớp property.** GraphQL field `authorName` không tự động đọc property `author_name` hoặc một tên khác nếu không có cấu hình hay resolver chuyển đổi tương ứng.

**Source không có kiểu hoặc dữ liệu như mong đợi.** Kiểm tra object mà resolver cha thực sự trả về. Resolver con nhận object đó làm source, không tự động nhận entity khác chỉ vì schema có tên kiểu tương ứng.

**Truy vấn quan hệ trong từng resolver mà không để ý N+1.** Với danh sách nhiều parent object, đếm số lần gọi service/repository và cân nhắc `@BatchMapping` hoặc DataLoader.

**Không xử lý trường hợp parent hoặc quan hệ bị thiếu.** Chọn nullability phù hợp trong SDL và bảo đảm resolver trả về giá trị hoặc lỗi theo đúng hợp đồng.

## Kết luận

Field resolver cung cấp giá trị cho từng field GraphQL. Parent source là object được field cha trả về và được truyền xuống resolver của field con. Trong Spring for GraphQL, `@QueryMapping` xử lý field gốc, còn `@SchemaMapping` xử lý field trên object; `@Argument` cung cấp dữ liệu client truyền cho field hiện tại. Hãy tận dụng default property fetcher cho thuộc tính có sẵn, viết resolver cho quan hệ hoặc logic cần thiết và dùng batching khi nhiều parent object cần tải dữ liệu liên quan.
