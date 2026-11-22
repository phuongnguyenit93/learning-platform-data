# Field mapping bằng `@SchemaMapping`

Trong Spring for GraphQL, `@SchemaMapping` dùng để ánh xạ một phương thức trong annotated controller tới một field của GraphQL object type. Phương thức nhận object cha làm source, có thể đọc thêm argument của field và trả về giá trị mà GraphQL cần đưa vào response.

Ví dụ một `Book` có field `author`. Nếu object Java `Book` chỉ chứa `authorId`, việc lấy thông tin tác giả cần gọi service hoặc repository. `@SchemaMapping` cho phép viết resolver riêng cho field `Book.author`, trong khi schema vẫn mô tả field đó như một phần tự nhiên của object `Book`.

## Field mapping giải quyết vấn đề gì?

GraphQL cho phép client chọn field lồng nhau trong một operation. Với schema:

```graphql
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
```

Client có thể lấy sách cùng tác giả trong một request:

```graphql
query BookDetail($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
```

Resolver của `Query.book` tìm sách theo ID. Sau khi nhận được object `Book`, GraphQL tiếp tục resolve field `id`, `title` và `author`. Nếu `author` không phải property có sẵn trong object Java hoặc cần gọi nghiệp vụ để lấy dữ liệu, ta cần một field resolver.

`@SchemaMapping` chính là cách Spring for GraphQL đăng ký field resolver đó từ một phương thức Java.

## Ví dụ cơ bản với `@SchemaMapping`

Giả sử model Java có `authorId` nhưng không có object `Author` được nạp sẵn:

```java
public class Book {
    private String id;
    private String title;
    private String authorId;

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getAuthorId() { return authorId; }
}

public class Author {
    private String id;
    private String name;

    public String getId() { return id; }
    public String getName() { return name; }
}
```

Controller có thể ánh xạ field `Book.author` như sau:

```java
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId()).orElse(null);
    }
}
```

Trong ví dụ này, `typeName = "Book"` chỉ object type trong SDL, còn `field = "author"` chỉ field cần resolve. Tham số `Book book` là source object do GraphQL truyền từ resolver cha xuống. Phương thức lấy `authorId` từ source, gọi `AuthorService` và trả về `Author`.

Khi client chọn `author`, GraphQL thực thi phương thức này. Sau đó engine tiếp tục resolve `Author.id` và `Author.name` theo selection set.

## Cách Spring suy luận type và field

Không phải lúc nào cũng cần khai báo cả `typeName` và `field`. Spring for GraphQL hỗ trợ suy luận theo quy ước:

- Tên field mặc định được suy ra từ tên phương thức.
- Tên object type mặc định được suy ra từ kiểu source parameter.

Ví dụ nếu phương thức có source là `Book` và tên phương thức là `author`, có thể viết ngắn:

```java
@SchemaMapping
public Author author(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

Spring hiểu đây là mapping cho field `Book.author`. Cách viết ngắn phù hợp khi tên class Java và GraphQL type thống nhất. Khi GraphQL type có tên khác, source là một lớp cơ sở hoặc cần làm rõ ý định, nên khai báo `typeName` và `field` tường minh.

Có thể đổi tên field mapping bằng thuộc tính `field` mà không cần đổi tên phương thức Java:

```java
@SchemaMapping(typeName = "Book", field = "primaryAuthor")
public Author loadAuthor(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

Phương thức `loadAuthor` lúc này xử lý field `Book.primaryAuthor` trong schema.

## Source object và `@Source`

Source là object cha mà GraphQL đã resolve ở cấp field trước đó. Với `Book.author`, source chính là một instance `Book`. Source khác với argument: source đến từ kết quả của field cha, còn argument là dữ liệu client gửi cho field hiện tại.

Có thể đánh dấu source parameter tường minh bằng `@Source` khi cần làm rõ vai trò của tham số:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.graphql.data.method.annotation.Source;

@SchemaMapping(typeName = "Book", field = "authorByLocale")
public Author authorByLocale(
        @Source Book book,
        @Argument String locale) {
    return authorService.findByBookAndLocale(book.getAuthorId(), locale);
}
```

Trong ví dụ, `@Source` chỉ object `Book` hiện tại; `@Argument` lấy giá trị `locale` từ field argument trong SDL:

```graphql
type Book {
  id: ID!
  title: String!
  authorByLocale(locale: String!): Author
}
```

Khi method chỉ có một source parameter rõ ràng, Spring thường có thể suy luận vai trò source theo quy ước. Annotation `@Source` hữu ích khi method có nhiều tham số hoặc cần làm code dễ đọc hơn.

## Đọc argument bằng `@Argument`

Field lồng nhau có thể nhận argument giống field cấp cao nhất. Ví dụ client muốn chọn một phiên bản ngôn ngữ cụ thể của mô tả sách:

```graphql
type Book {
  id: ID!
  title: String!
  description(locale: String!): String
}
```

Controller đọc argument bằng `@Argument`:

```java
@SchemaMapping(typeName = "Book", field = "description")
public String description(Book book, @Argument String locale) {
    return descriptionService.findText(book.getId(), locale);
}
```

`book` là source object; `locale` là argument do client truyền. Nếu tên biến Java khác tên argument SDL, có thể chỉ rõ tên argument trong annotation theo cú pháp được Spring for GraphQL hỗ trợ.

Với input object, có thể nhận một DTO hoặc record tương ứng:

```graphql
input ReviewFilter {
  minimumRating: Int
  language: String
}

type Book {
  reviews(filter: ReviewFilter): [Review!]!
}
```

```java
@SchemaMapping(typeName = "Book", field = "reviews")
public List<Review> reviews(Book book, @Argument ReviewFilter filter) {
    return reviewService.findByBook(book.getId(), filter);
}
```

Kiểu Java đầu vào phải tương thích với cách Spring chuyển đổi argument. Với input phức tạp, nên dùng DTO/record có cấu trúc rõ ràng và kiểm tra validation tại ranh giới API.

## Ánh xạ nhiều field trong cùng controller

Có thể đặt `@SchemaMapping(typeName = "Book")` ở cấp class để dùng chung GraphQL type cho các phương thức mapping bên trong. Khi đó, từng phương thức chỉ cần `@SchemaMapping` và field name có thể được suy ra từ tên phương thức:

```java
@Controller
@SchemaMapping(typeName = "Book")
public class BookController {

    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            AuthorService authorService,
            ReviewService reviewService) {
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @SchemaMapping
    public Author author(Book book) {
        return authorService.findById(book.getAuthorId()).orElse(null);
    }

    @SchemaMapping
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.getId());
    }
}
```

Ở đây cả hai phương thức được ánh xạ vào object type `Book`; tên phương thức lần lượt là field `author` và `reviews`. Cách gom nhóm này hữu ích khi một controller chịu trách nhiệm cho nhiều field của cùng GraphQL type.

Không nên gom mọi resolver của toàn bộ schema vào một controller lớn. Có thể chia controller theo domain hoặc GraphQL type để dependency và trách nhiệm rõ ràng.

## `@SchemaMapping` và default PropertyDataFetcher

GraphQL Java có cơ chế mặc định `PropertyDataFetcher` để lấy giá trị từ object nguồn. Nếu Java object đã có getter hoặc property tương ứng với field SDL, Spring for GraphQL thường không cần một phương thức `@SchemaMapping` riêng.

Ví dụ:

```java
public class Book {
    private String id;
    private String title;

    public String getId() { return id; }
    public String getTitle() { return title; }
}
```

Với SDL:

```graphql
type Book {
  id: ID!
  title: String!
}
```

Khi resolver `Query.book` trả về `Book`, GraphQL có thể đọc `id` và `title` trực tiếp từ object. Không cần tạo mapping chỉ để trả lại đúng giá trị getter.

Nên dùng `@SchemaMapping` khi field cần:

- Gọi service hoặc repository để lấy dữ liệu liên quan.
- Tính toán giá trị từ nhiều thuộc tính của source.
- Chuyển đổi dữ liệu sang kiểu GraphQL phù hợp.
- Áp dụng quy tắc nghiệp vụ hoặc kiểm tra quyền truy cập.
- Trả về kết quả bất đồng bộ từ một dịch vụ khác.

Không tạo resolver thừa cho field chỉ phản ánh property có sẵn. Ít mapping hơn giúp schema và model Java dễ bảo trì hơn.

## Phân biệt `@SchemaMapping` với `@QueryMapping` và `@MutationMapping`

Cả ba annotation đều đăng ký DataFetcher từ annotated controller, nhưng chúng nhắm tới các vị trí khác nhau:

| Annotation | Vị trí mapping | Ví dụ |
| --- | --- | --- |
| `@QueryMapping` | Field trên Query root type. | `Query.book` |
| `@MutationMapping` | Field trên Mutation root type. | `Mutation.createBook` |
| `@SchemaMapping` | Field của một GraphQL object type, thường là field lồng nhau. | `Book.author` |

Ví dụ Query root:

```java
@QueryMapping
public Book book(@Argument String id) {
    return bookService.findById(id).orElse(null);
}
```

Ví dụ field lồng nhau:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findById(book.getAuthorId()).orElse(null);
}
```

`@QueryMapping` là shortcut cho field của Query root. Không cần viết `@SchemaMapping(typeName = "Query", field = "book")` nếu đang triển khai một Query field thông thường. Dùng annotation thể hiện đúng loại operation giúp code dễ đọc hơn.

## Mapping bất đồng bộ

Field resolver có thể gọi dịch vụ bất đồng bộ và trả về kiểu mà GraphQL Java hỗ trợ, chẳng hạn `CompletableFuture` hoặc Reactor `Mono` trong ứng dụng Spring for GraphQL.

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(Book book) {
    return authorService.findByIdAsync(book.getAuthorId());
}
```

Hoặc với reactive service:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Mono<Author> author(Book book) {
    return authorService.findByIdReactive(book.getAuthorId());
}
```

Các ví dụ giả định service thực sự cung cấp API bất đồng bộ/non-blocking. Nếu service gọi JDBC/JPA đồng bộ rồi mới bọc kết quả bằng `Mono.just`, lời gọi vẫn blocking. Với blocking I/O trong WebFlux, cần offload sang scheduler/executor phù hợp hoặc dùng driver non-blocking.

## Bảo mật ở cấp field

`@SchemaMapping` là nơi thuận tiện để kiểm tra quyền truy cập vào dữ liệu của field lồng nhau. Ví dụ người dùng có thể xem sách nhưng chỉ biên tập viên mới được đọc ghi chú kiểm duyệt:

```graphql
type Book {
  id: ID!
  title: String!
  moderationNote: String
}
```

```java
@SchemaMapping(typeName = "Book", field = "moderationNote")
public String moderationNote(Book book, Principal principal) {
    authorizationService.checkCanViewModerationNote(principal, book.getId());
    return bookService.getModerationNote(book.getId());
}
```

Không dựa vào việc client không biết tên field. Nếu field tồn tại trong schema, client có thể thử truy vấn trực tiếp. Resolver hoặc service phải xác thực người dùng và kiểm tra quyền cho tài nguyên cụ thể.

Với ứng dụng đa tenant, việc kiểm tra phải bao gồm phạm vi tenant. Không lấy tenant từ argument do client tự khai báo làm bằng chứng quyền truy cập.

## N+1 khi resolve field quan hệ

`@SchemaMapping` có thể tạo ra N+1 nếu mỗi object cha gọi repository riêng để tải dữ liệu liên quan.

Ví dụ query:

```graphql
query Books {
  books {
    id
    title
    author {
      id
      name
    }
  }
}
```

Nếu Query `books` trả về 100 sách và resolver `Book.author` thực hiện một truy vấn database cho mỗi sách, hệ thống có thể chạy 1 truy vấn lấy sách và 100 truy vấn lấy tác giả.

Có hai hướng thường dùng trong Spring for GraphQL:

- **DataLoader:** resolver gọi `load(authorId)` để gom các key trong cùng request; batch loader truy vấn nhiều tác giả một lần rồi trả kết quả theo key.
- **`@BatchMapping`:** khai báo phương thức nhận danh sách source objects và trả về dữ liệu liên quan theo batch. Spring for GraphQL đăng ký cơ chế batch DataLoader cho field đó.

Ví dụ `@BatchMapping` cho field author:

```java
@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<String, Author> authorsById = authorService.findAllByIds(authorIds);

        return books.stream().collect(Collectors.toMap(
                book -> book,
                book -> authorsById.get(book.getAuthorId())));
    }
}
```

Ví dụ giả định service trả map theo author ID và mỗi Book có một Author. Với quan hệ một-nhiều hoặc nhiều-nhiều, kiểu trả về và cách ghép kết quả sẽ khác. `@BatchMapping` là một cách đăng ký resolver theo batch cho field; không nên đồng thời viết `@SchemaMapping` riêng cho chính field đó nếu không có chủ đích rõ ràng.

Batching giảm số lần gọi dữ liệu, nhưng vẫn cần phân trang và giới hạn kích thước danh sách. Không tải hàng nghìn object cùng lúc chỉ vì đã có DataLoader.

## Kiểm thử `@SchemaMapping`

Có thể dùng `GraphQlTester` để kiểm tra operation đi qua Query root rồi resolve field lồng nhau:

```java
@Test
void bookQueryResolvesAuthor() {
    graphQlTester.document("""
        query {
          book(id: "book-10") {
            id
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
```

Ngoài kết quả thành công, nên kiểm tra:

- Field và type trong annotation khớp với SDL.
- Source object được truyền đúng từ field cha.
- Argument được bind đúng, kể cả input object và trường hợp null.
- Khi dữ liệu liên quan không tồn tại, kết quả tuân theo nullability.
- Exception được ánh xạ thành GraphQL error phù hợp.
- Người dùng thiếu quyền không đọc được field nhạy cảm.
- Danh sách nhiều object không tạo N+1 ngoài dự kiến.
- Mapping bất đồng bộ xử lý cả thành công, lỗi và timeout.

Khi test batching, có thể xác minh số lần gọi service/repository để bảo đảm nhiều source object được xử lý trong một batch. Unit test chỉ gọi trực tiếp phương thức controller chưa đủ để xác nhận mapping đã được đăng ký vào GraphQL schema.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field trả null dù source có dữ liệu liên quan | `typeName`, `field` hoặc tên phương thức không khớp SDL. | Đối chiếu annotation với schema. |
| Spring không suy luận đúng GraphQL type | Tên class Java không trùng tên object type hoặc source parameter không rõ. | Khai báo `typeName` tường minh. |
| `@Argument` luôn null | Tên argument sai hoặc client không gửi variables đúng. | Kiểm tra SDL, operation và tên argument. |
| Resolver không nhận được object cha | Method signature không có source parameter phù hợp. | Khai báo source parameter hoặc `@Source` tường minh. |
| Resolver chạy nhưng query chậm | Mỗi source object gọi repository riêng, gây N+1. | Dùng DataLoader hoặc `@BatchMapping`. |
| Handler không mong muốn được gọi | Cùng field được đăng ký bằng nhiều cơ chế mapping. | Chọn một handler cho mỗi field và kiểm tra runtime wiring. |
| Người dùng đọc được field nội bộ | Resolver thiếu authorization theo tài nguyên. | Kiểm tra principal, quyền và tenant trong resolver/service. |

## Ghi nhớ

`@SchemaMapping` đăng ký field resolver cho một GraphQL object type. Spring có thể suy luận field từ tên phương thức và type từ source parameter; khi cần rõ ràng, dùng `typeName` và `field`. Source object là giá trị do field cha trả về, còn `@Argument` lấy dữ liệu client gửi vào field hiện tại.

GraphQL Java có `PropertyDataFetcher` mặc định nên không cần tạo mapping cho field chỉ đọc property có sẵn. Dùng `@SchemaMapping` khi cần gọi service, tính toán, kiểm tra quyền hoặc xử lý dữ liệu liên quan. Với danh sách object, hãy để ý N+1 và cân nhắc DataLoader hoặc `@BatchMapping` để gom truy vấn.
