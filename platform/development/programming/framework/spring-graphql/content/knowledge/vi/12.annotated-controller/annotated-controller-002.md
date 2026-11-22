# @SchemaMapping

Trong Spring for GraphQL, `@SchemaMapping` liên kết một phương thức trong controller với một field của GraphQL schema. Khi GraphQL Java cần phân giải field đó, Spring gọi phương thức tương ứng, truyền source object, argument và các thông tin thực thi phù hợp, rồi dùng giá trị trả về để tiếp tục tạo response.

Annotation này đặc biệt hữu ích với các field lồng nhau, chẳng hạn `Book.author`, `Order.items` hoặc `Customer.address`. Root field của `Query` thường được khai báo bằng `@QueryMapping`; còn `@SchemaMapping` cho phép xử lý field trên bất kỳ object type hoặc interface phù hợp nào trong schema.

## 1. Vai trò của @SchemaMapping

Giả sử schema khai báo:

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

Field `Query.bookById` lấy một quyển sách. Khi client yêu cầu thêm `Book.author`, ứng dụng cần cung cấp cách lấy tác giả tương ứng. Ta có thể viết controller:

```java
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
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }
}
```

`@QueryMapping` xử lý field gốc `Query.bookById`. `@SchemaMapping` xử lý field `author` trên type `Book`. Tham số `Book book` là source object mà field cha trả về. Từ object đó, resolver lấy `authorId` rồi gọi service để tìm tác giả.

Khi client gửi:

```graphql
query {
    bookById(id: "book-01") {
        id
        title
        author {
            name
        }
    }
}
```

GraphQL thực thi `bookById`, sau đó tiếp tục phân giải `id`, `title` và `author` theo selection set. Phương thức `author` chỉ được gọi khi field `author` được chọn trong operation.

## 2. Cách Spring xác định type và field

`@SchemaMapping` có hai thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `typeName` | Tên GraphQL parent type chứa field cần ánh xạ |
| `field` | Tên field GraphQL cần ánh xạ |

Nếu không chỉ định rõ, Spring có thể suy luận tên field từ tên phương thức và parent type từ kiểu source parameter. Quy ước này giúp mapping ngắn gọn:

```java
@Controller
public class BookController {

    @SchemaMapping
    public Author author(Book book) {
        // Spring suy luận parent type là Book và field là author.
        return authorService.findById(book.authorId());
    }
}
```

Ở ví dụ này:

- Tên phương thức `author` được dùng làm tên field.
- Kiểu source parameter `Book` được dùng để suy luận parent type.
- `Book` là object Java cung cấp dữ liệu cho field con.

Khi tên Java class khác tên GraphQL type hoặc muốn mapping tường minh, chỉ định các thuộc tính:

```java
@SchemaMapping(typeName = "CatalogEntry", field = "primaryAuthor")
public Author resolvePrimaryAuthor(Book book) {
    return authorService.findById(book.authorId());
}
```

Phương thức `resolvePrimaryAuthor` được ánh xạ vào field `CatalogEntry.primaryAuthor`; tên method không còn quyết định tên field vì `field` đã được khai báo rõ. Source parameter vẫn là `Book`, còn parent GraphQL type được chỉ định là `CatalogEntry`.

Hãy dùng tên GraphQL type và field đúng như trong SDL. Mapping không tự tạo field mới trong schema. Nếu `CatalogEntry.primaryAuthor` chưa được khai báo, việc viết annotation không làm query có thể chọn field đó.

## 3. Đặt @SchemaMapping ở cấp class

Khi một controller chứa nhiều resolver cho cùng một parent type, có thể đặt `@SchemaMapping(typeName = "Book")` ở cấp class. Các phương thức bên trong có thể chỉ cần khai báo field:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookFieldController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookFieldController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
```

Class-level mapping cung cấp parent type mặc định cho các method mapping trong controller. Method-level `field` có thể ghi đè tên field suy luận từ tên phương thức. Cách tổ chức này giúp gom resolver theo domain type và giảm lặp `typeName`.

Nếu một controller xử lý nhiều parent type, có thể chỉ định `typeName` ở từng phương thức thay vì đặt một giá trị chung ở cấp class. Tránh tạo nhiều method mapping trùng cùng một cặp parent type và field, vì Spring không thể chọn resolver một cách rõ ràng khi mapping bị xung đột.

## 4. Source object là gì?

Trong GraphQL, một field lồng nhau được phân giải dựa trên kết quả của field cha. Giá trị cha đó được gọi là **source object**. Ví dụ, khi `Query.bookById` trả về một `Book`, source object của `Book.author` chính là instance `Book` đó.

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book source) {
    return authorService.findById(source.authorId());
}
```

Tên biến `source` hay `book` không ảnh hưởng đến mapping. Spring nhận diện source parameter dựa trên kiểu tham số và cơ chế phân giải argument của annotated controller. Source object thường là tham số không gắn annotation, có kiểu tương ứng với object mà field cha trả về.

Source object không nhất thiết là entity JPA. Nó có thể là record, DTO, projection, domain object hoặc `Map`, miễn là kiểu dữ liệu phù hợp với resolver và cách GraphQL Java đọc property. Nên trả về DTO hoặc projection có cấu trúc rõ ràng nếu entity persistence chứa nhiều dữ liệu nội bộ hoặc có quan hệ lazy loading khó kiểm soát.

Khi không cần service để lấy field con, GraphQL Java có thể dùng `PropertyDataFetcher` mặc định để đọc property từ source object. Vì vậy, không phải field nào cũng cần `@SchemaMapping`.

## 5. Lấy argument bằng @Argument

Field GraphQL có thể nhận argument. Trong method mapping, dùng `@Argument` để lấy giá trị tương ứng:

```graphql
type Book {
    relatedBooks(limit: Int = 5): [Book!]!
}
```

```java
@SchemaMapping(typeName = "Book", field = "relatedBooks")
public List<Book> relatedBooks(
        Book book,
        @Argument("limit") Integer limit) {
    return bookService.findRelated(book.id(), limit);
}
```

`Book` là source object; `limit` là argument do client truyền. Khi client bỏ qua `limit`, GraphQL áp dụng default value `5` theo schema trước khi Spring chuyển giá trị cho phương thức.

Có thể dùng `@Argument` với DTO để nhận một input object:

```graphql
input ReviewFilter {
    minRating: Int
    language: String
}

type Book {
    reviews(filter: ReviewFilter): [Review!]!
}
```

```java
public record ReviewFilter(Integer minRating, String language) {
}

@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(
        Book book,
        @Argument("filter") ReviewFilter filter) {
    return reviewService.findByBook(book.id(), filter);
}
```

Spring chuyển đổi argument từ GraphQL input thành kiểu Java tương ứng. Kiểu DTO cần phù hợp với cấu trúc input và khả năng binding/conversion của ứng dụng. Với argument đơn giản, có thể bind trực tiếp vào `String`, `Integer`, `Boolean`, `UUID` hoặc kiểu scalar đã cấu hình.

Nên ghi rõ tên trong `@Argument("...")` khi muốn tránh phụ thuộc vào việc giữ metadata tên tham số Java trong quá trình biên dịch. Nếu bỏ tên, Spring dựa trên tên tham số được phát hiện từ bytecode hoặc cấu hình build.

## 6. Các tham số bổ sung trong resolver

Ngoài source object và `@Argument`, annotated controller có thể nhận các tham số phục vụ việc thực thi. Ví dụ `DataFetchingEnvironment` cho phép đọc thông tin field, selection set, context và các DataLoader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book, DataFetchingEnvironment environment) {
    boolean requestsName = environment.getSelectionSet().contains("name");
    return authorService.findById(book.authorId(), requestsName);
}
```

Trong ví dụ, resolver xem selection set để biết client có yêu cầu field `name` hay không. Kỹ thuật này có thể giúp tối ưu projection ở tầng dữ liệu, nhưng cần xử lý cả alias, fragment và field lồng nhau đúng cách; không nên tự phân tích chuỗi query bằng cách đơn giản nếu có thể dùng API selection set.

Resolver cũng có thể nhận thông tin context hoặc principal theo các argument resolver mà Spring for GraphQL hỗ trợ. Ví dụ, khi cần thông tin người dùng hiện tại, có thể nhận `Principal` hoặc dùng annotation context tương ứng. Dù lấy context bằng cách nào, quyền truy cập vẫn phải được kiểm tra ở server cho từng field hoặc service cần bảo vệ.

## 7. @SchemaMapping và các annotation root mapping

Spring for GraphQL cung cấp các annotation chuyên biệt cho root operation type:

| Annotation | Mapping tương đương | Dùng cho |
| --- | --- | --- |
| `@QueryMapping` | `@SchemaMapping(typeName = "Query")` | Field gốc của Query |
| `@MutationMapping` | `@SchemaMapping(typeName = "Mutation")` | Field gốc của Mutation |
| `@SubscriptionMapping` | Mapping field của `Subscription` | Field gốc của Subscription |
| `@SchemaMapping` | Parent type được suy luận hoặc chỉ định | Field trên object/interface type bất kỳ |

Ví dụ:

```java
@Controller
public class BookRootController {

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title) {
        return bookService.rename(id, title);
    }
}
```

Thông thường nên dùng annotation root tương ứng vì nó thể hiện rõ ý định. Dùng `@SchemaMapping(typeName = "Query")` khi muốn cấu hình mapping tổng quát hoặc khi cần thống nhất cách tổ chức resolver.

## 8. Trả về kết quả đồng bộ, bất đồng bộ và reactive

Phương thức `@SchemaMapping` có thể trả về object thông thường:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.authorId());
}
```

Nếu service chạy bất đồng bộ, có thể trả về `CompletableFuture` hoặc `CompletionStage`:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.authorId());
}
```

Với ứng dụng reactive, có thể trả về `Mono` hoặc `Flux`:

```java
@SchemaMapping(typeName = "Book", field = "reviews")
public Flux<Review> reviews(Book book) {
    return reviewService.streamByBookId(book.id());
}
```

Spring for GraphQL tích hợp các kiểu asynchronous và Reactive Streams để GraphQL Java xử lý kết quả phù hợp với operation. Chọn kiểu trả về dựa trên mô hình xử lý của service và stack ứng dụng. Không nên bọc một lời gọi blocking vào `Mono` rồi cho rằng nó tự trở thành non-blocking; cần bảo đảm thao tác bên trong thực sự phù hợp với mô hình reactive hoặc được điều phối trên scheduler phù hợp.

Nếu resolver ném exception hoặc future/reactive publisher phát lỗi, lỗi được chuyển vào cơ chế xử lý lỗi GraphQL của ứng dụng, chẳng hạn `DataFetcherExceptionResolver`. Cần tránh trả thông tin nội bộ hoặc stack trace nhạy cảm trong response.

## 9. Khi nào không cần @SchemaMapping?

Giả sử source object có property tương ứng:

```java
public record Book(String id, String title, String subtitle) {
}
```

Schema:

```graphql
type Book {
    id: ID!
    title: String!
    subtitle: String
}
```

GraphQL Java có thể đọc `id`, `title` và `subtitle` trực tiếp từ source object thông qua `PropertyDataFetcher`. Không cần viết ba phương thức `@SchemaMapping` chỉ để trả lại đúng property đã có.

Nên viết mapping riêng khi field cần gọi service/repository, tính toán giá trị, áp dụng nghiệp vụ, kiểm tra quyền, kết hợp nhiều nguồn dữ liệu hoặc dùng DataLoader. Nếu mapping chỉ trả `book.title()` mà không thêm logic, property fetcher mặc định thường đủ.

## 10. @SchemaMapping và vấn đề N+1

Một resolver field lồng nhau có thể tạo ra nhiều truy vấn dữ liệu. Ví dụ client lấy danh sách 50 quyển sách cùng `author`; nếu `Book.author` gọi database một lần cho mỗi sách, request có thể phát sinh một truy vấn danh sách và 50 truy vấn tác giả.

`@SchemaMapping` không tự batch các lần gọi. Khi cần tối ưu, dùng `@BatchMapping` hoặc DataLoader để gom các source object và tải dữ liệu theo nhóm. `@BatchMapping` phù hợp với trường hợp phổ biến, còn DataLoader cho phép kiểm soát chi tiết cache và batch key.

Ví dụ:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<String> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> byId = authorService.findAllByIds(authorIds);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, byId.get(book.authorId()));
        }
        return result;
    }
}
```

`@BatchMapping` thay thế resolver đơn lẻ cho field tương ứng bằng một resolver nhận danh sách source object. Nếu field cần xử lý đặc biệt cho từng source hoặc có nhiều batch key, có thể đăng ký DataLoader qua `BatchLoaderRegistry` và dùng nó từ resolver. Luôn giữ cache theo request để tránh chia sẻ dữ liệu giữa các request người dùng.

## 11. Kiểm thử @SchemaMapping

`GraphQlTester` cho phép kiểm thử từ góc nhìn GraphQL client: gửi operation, truyền variable và kiểm tra field trong response. Ví dụ:

```java
graphQlTester.document("""
        query($id: ID!) {
            bookById(id: $id) {
                title
                author {
                    name
                }
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("bookById.author.name")
    .entity(String.class)
    .isEqualTo("Ada Lovelace");
```

Kiểm thử này xác nhận toàn bộ luồng: root query lấy `Book`, `@SchemaMapping` phân giải `author`, rồi GraphQL đọc field `name` của `Author`.

Nên có thêm test cho các trường hợp:

- Không tìm thấy source object hoặc field cha trả về `null`.
- Argument có giá trị mặc định, thiếu hoặc không hợp lệ.
- Service ném exception và lỗi được ánh xạ thành GraphQL error phù hợp.
- Field không được chọn thì resolver không cần thực thi.
- Mapping cho nhiều parent type không bị trùng.
- Resolver bất đồng bộ hoặc reactive xử lý lỗi và cancellation đúng cách.

## 12. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Method không được gọi | `typeName` hoặc `field` không khớp SDL | Kiểm tra chính xác tên parent type và field |
| Spring báo mapping trùng | Nhiều method đăng ký cùng một parent type/field | Gộp resolver hoặc đổi mapping để mỗi field có một handler rõ ràng |
| Source parameter không đúng | Kiểu tham số không tương ứng source object | Kiểm tra object do field cha trả về và kiểu Java của tham số |
| `@Argument` nhận null ngoài dự kiến | Sai tên argument hoặc client không truyền giá trị | Ghi rõ `@Argument("name")` và kiểm tra default/nullability trong SDL |
| Query chọn field nhưng response null | Resolver trả null, source thiếu property hoặc mapping sai | Kiểm tra service, source object và default property fetcher |
| Lỗi non-null propagation | Resolver trả null cho field có kiểu `!` | Điều chỉnh dữ liệu/resolver hoặc contract SDL cho đúng nghiệp vụ |
| Nhiều truy vấn cho field con | Resolver đơn lẻ gây N+1 | Dùng `@BatchMapping` hoặc DataLoader |
| Resolver blocking trong reactive flow | Service thực hiện I/O blocking trên luồng không phù hợp | Dùng API reactive thực sự hoặc điều phối blocking work đúng scheduler |

Khi chẩn đoán, đi theo thứ tự: field có tồn tại trong SDL không, mapping có được đăng ký đúng parent type và field không, source object có đúng kiểu không, argument có được bind đúng không, cuối cùng mới kiểm tra service và dữ liệu. Cách này giúp phân biệt lỗi schema mapping với lỗi nghiệp vụ.

## 13. Nguyên tắc tổ chức annotated controller

Nhóm resolver theo domain hoặc parent type để controller dễ đọc. Dùng class-level `@SchemaMapping` khi nhiều method cùng xử lý một GraphQL type; dùng method-level `typeName` và `field` khi cần mapping rõ ràng hoặc parent type khác tên Java class. Giữ resolver mỏng, chuyển nghiệp vụ vào service và chỉ dùng `DataFetchingEnvironment` khi thực sự cần thông tin selection/context.

Không tạo resolver cho mọi property đã có thể đọc trực tiếp từ source object. Khi field con truy cập dữ liệu qua nhiều nguồn hoặc lặp truy vấn, cân nhắc DataLoader. Với field nhạy cảm, kiểm tra quyền ở server và không dựa vào việc client có chọn field hay không.

`@SchemaMapping` là cầu nối giữa field trong GraphQL schema và phương thức Java. Hiểu rõ parent type, field name, source object, argument binding và cơ chế fetch dữ liệu giúp xây dựng annotated controller có cấu trúc rõ ràng, dễ kiểm thử và phù hợp với hiệu năng của Spring for GraphQL.
