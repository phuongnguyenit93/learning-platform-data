# Query với nhiều field

Một GraphQL query có thể yêu cầu nhiều field cấp cao nhất trong cùng một operation. Thay vì gửi nhiều HTTP request riêng cho từng loại dữ liệu, client có thể lấy thông tin sách, tác giả và danh sách mới nhất trong một request, miễn là các field đó được khai báo trên root type `Query`.

GraphQL Java thực thi từng field theo schema và selection set. Kết quả được ghép thành một object `data` với key tương ứng tên field hoặc alias. Các field cấp cao nhất của query có thể được thực thi độc lập và song song; vì vậy ứng dụng không được dựa vào thứ tự gọi resolver. Nếu cần thay đổi dữ liệu theo thứ tự, hãy dùng mutation với các root field được thực thi tuần tự.

## 1. Khai báo nhiều field trên root Query

Giả sử API quản lý sách và tác giả có schema:

```graphql
type Query {
    bookById(id: ID!): Book
    authorById(id: ID!): Author
    latestBooks(limit: Int = 10): [Book!]!
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

Root type `Query` có ba field độc lập: `bookById`, `authorById` và `latestBooks`. Client có thể gọi cả ba trong cùng một operation:

```graphql
query Dashboard {
    bookById(id: "book-01") {
        id
        title
    }
    authorById(id: "author-01") {
        id
        name
    }
    latestBooks(limit: 5) {
        id
        title
    }
}
```

Server trả về một response có cấu trúc tương ứng:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "authorById": {
      "id": "author-01",
      "name": "Craig Walls"
    },
    "latestBooks": [
      {
        "id": "book-01",
        "title": "Spring in Action"
      }
    ]
  }
}
```

Các field được yêu cầu trong một operation và được trả về trong cùng một response. Client không cần gửi một request để lấy sách, một request khác để lấy tác giả và một request nữa để lấy danh sách mới nhất.

## 2. Kết nối từng root field với Spring controller

Trong Spring for GraphQL, mỗi root field có thể được xử lý bởi một phương thức `@QueryMapping`. Có thể đặt các phương thức trong cùng controller hoặc tách theo domain:

```java
@Controller
public class CatalogQueryController {

    private final BookService bookService;
    private final AuthorService authorService;

    public CatalogQueryController(
            BookService bookService,
            AuthorService authorService) {
        this.bookService = bookService;
        this.authorService = authorService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @QueryMapping
    public Author authorById(@Argument("id") String id) {
        return authorService.findById(id);
    }

    @QueryMapping
    public List<Book> latestBooks(@Argument("limit") Integer limit) {
        return bookService.findLatest(limit);
    }
}
```

Spring liên kết tên phương thức với field tương ứng trên `Query`. `@Argument` lấy giá trị argument từ operation. Nếu client không truyền `limit`, giá trị mặc định `10` trong SDL được áp dụng theo quy tắc GraphQL trước khi resolver nhận argument.

Các field này là những resolver độc lập. GraphQL Java thu thập chúng từ selection set và gọi từng resolver khi thực thi operation. Field con như `Book.author` có thể được xử lý bằng `@SchemaMapping` hoặc `@BatchMapping` theo nhu cầu lấy dữ liệu.

## 3. Dùng alias khi cần gọi cùng một field nhiều lần

Một query có thể cần lấy nhiều sách theo các ID khác nhau. Nếu viết hai lần cùng field `bookById` nhưng không có alias, cả hai lần xuất hiện sẽ có cùng response key. GraphQL yêu cầu các field cùng response key phải tương thích và có thể được gộp; nếu argument khác nhau, operation sẽ gặp lỗi field conflict.

Hãy dùng alias để tạo response key khác nhau:

```graphql
query CompareBooks($firstId: ID!, $secondId: ID!) {
    firstBook: bookById(id: $firstId) {
        id
        title
    }
    secondBook: bookById(id: $secondId) {
        id
        title
    }
}
```

Response sử dụng alias làm key:

```json
{
  "data": {
    "firstBook": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "secondBook": {
      "id": "book-02",
      "title": "GraphQL in Action"
    }
  }
}
```

Alias chỉ đổi tên key trong response của operation hiện tại. Nó không đổi tên field trong schema và không tạo thêm resolver. Cả `firstBook` và `secondBook` vẫn được ánh xạ đến cùng field `Query.bookById`, nhưng có argument riêng.

Alias cũng hữu ích khi gọi một field lồng nhau nhiều lần với các argument khác nhau:

```graphql
query BookReviews($bookId: ID!) {
    bookById(id: $bookId) {
        positive: reviews(ratingAtLeast: 4) {
            content
        }
        critical: reviews(ratingAtMost: 2) {
            content
        }
    }
}
```

Trong ví dụ, `positive` và `critical` là hai response key riêng cho cùng field `reviews`. Resolver phải hỗ trợ các argument tương ứng.

## 4. Dùng variables để truyền dữ liệu cho nhiều field

Variables giúp operation tái sử dụng và tách dữ liệu đầu vào khỏi GraphQL document. Một operation có thể khai báo nhiều variables rồi truyền chúng vào các root field khác nhau:

```graphql
query Dashboard(
    $bookId: ID!
    $authorId: ID!
    $latestLimit: Int = 5
) {
    selectedBook: bookById(id: $bookId) {
        id
        title
    }
    selectedAuthor: authorById(id: $authorId) {
        id
        name
    }
    latestBooks(limit: $latestLimit) {
        id
        title
    }
}
```

Khi gửi request, client cung cấp variables trong phần payload riêng:

```json
{
  "operationName": "Dashboard",
  "variables": {
    "bookId": "book-01",
    "authorId": "author-01",
    "latestLimit": 8
  }
}
```

GraphQL kiểm tra kiểu của variables so với argument trong schema trước khi thực thi. Nếu thiếu variable non-null hoặc truyền giá trị không tương thích, operation không vượt qua validation/coercion và các resolver không được thực thi như một query hợp lệ.

Một GraphQL document có thể chứa nhiều operation có tên, nhưng một request thông thường chỉ thực thi operation được chỉ định bằng `operationName`. Nhiều root field trong một operation là cách lấy nhiều phần dữ liệu cùng lúc; viết nhiều operation trong một document không có nghĩa server tự chạy tất cả operation đó.

## 5. Tái sử dụng selection set bằng fragment

Khi nhiều root field trả về cùng một type và cần cùng nhóm field, fragment giúp tránh lặp selection set:

```graphql
fragment BookSummary on Book {
    id
    title
    author {
        id
        name
    }
}

query CatalogOverview($firstId: ID!, $secondId: ID!) {
    featured: bookById(id: $firstId) {
        ...BookSummary
    }
    recommended: bookById(id: $secondId) {
        ...BookSummary
    }
}
```

Fragment `BookSummary` được áp dụng ở hai vị trí. GraphQL mở rộng selection set và thực thi các field cần thiết cho từng source object. Fragment chỉ tái sử dụng cấu trúc yêu cầu dữ liệu; nó không tạo một request mới hoặc một resolver độc lập.

Có thể kết hợp fragment với inline fragment khi một field trả về interface hoặc union. Client chọn field chung trực tiếp, rồi dùng `... on Book` hoặc `... on Article` để lấy field riêng của từng object type.

## 6. GraphQL thu thập và hợp nhất field như thế nào?

Trước khi thực thi, GraphQL parse document, kiểm tra operation với schema và thu thập các field được chọn theo selection set. Field có thể đến từ selection trực tiếp, named fragment hoặc inline fragment.

GraphQL sử dụng **response key** để xác định field trong kết quả. Response key là alias nếu có, nếu không thì là tên field. Các lần xuất hiện có cùng response key phải thỏa quy tắc field merging: chúng phải tương thích về field name, argument và selection set. Nếu xung đột, operation bị từ chối trong giai đoạn validation.

Ví dụ hai lần chọn cùng field với cùng argument và response key có thể được gộp thành một nhóm field:

```graphql
query {
    bookById(id: "book-01") {
        title
    }
    bookById(id: "book-01") {
        author {
            name
        }
    }
}
```

Các selection set tương thích được kết hợp để kết quả `bookById` có cả `title` và `author.name`. Tuy nhiên, để code dễ đọc, thông thường nên viết một lần field với selection set đầy đủ:

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

Nếu muốn cùng field được gọi với argument khác nhau, hãy đặt alias khác nhau như ví dụ `firstBook` và `secondBook`.

## 7. Nhiều root field được thực thi như thế nào?

Theo quy tắc GraphQL, các field cấp cao nhất của một query có thể được thực thi song song. Điều này cho phép server xử lý những phần dữ liệu độc lập mà không phải đợi field trước hoàn tất. GraphQL Java sử dụng execution strategy cho query để điều phối các field; các kết quả bất đồng bộ như `CompletableFuture` có thể được xử lý đồng thời.

Tuy nhiên, không nên hiểu rằng mọi lời gọi Java đồng bộ chắc chắn chạy trên các thread riêng. Khả năng thực sự chồng lấp thời gian phụ thuộc vào loại `DataFetcher`, cách trả kết quả và executor/runtime được cấu hình. Một resolver đồng bộ có thao tác blocking vẫn có thể làm chậm tiến trình thực thi. Nếu service hỗ trợ async hoặc reactive, hãy dùng kiểu trả về phù hợp thay vì tự tạo thread tùy tiện trong controller.

Điều quan trọng về mặt contract là **không dựa vào thứ tự thực thi giữa các root field của query**. Ví dụ, không nên viết field `reserveInventory` trong `Query` rồi kỳ vọng field `bookById` chạy sau nó để thấy dữ liệu mới. Query nên biểu diễn thao tác đọc không gây side effect. Các root field của mutation được GraphQL thực thi tuần tự và phù hợp với thao tác thay đổi dữ liệu.

## 8. Phân biệt Query và Mutation khi có nhiều field

Một mutation có thể chứa nhiều root field:

```graphql
type Mutation {
    updateBookTitle(id: ID!, title: String!): Book!
    publishBook(id: ID!): Book!
}
```

```graphql
mutation UpdateAndPublish($id: ID!, $title: String!) {
    update: updateBookTitle(id: $id, title: $title) {
        id
        title
    }
    publish: publishBook(id: $id) {
        id
        title
    }
}
```

Các root field của mutation được thực thi tuần tự theo thứ tự xuất hiện trong operation. Vì vậy, `publishBook` được thực thi sau `updateBookTitle`. Quy tắc tuần tự này áp dụng cho root fields của mutation; các field con trong selection set vẫn tuân theo quy tắc thực thi field thông thường.

Query thì khác: root fields không có cam kết thứ tự. Nếu hai thao tác có phụ thuộc dữ liệu hoặc side effect, hãy mô hình hóa thành mutation và đặt chúng trong cùng operation khi phù hợp.

## 9. Xử lý lỗi khi một trong nhiều field thất bại

GraphQL có thể trả về dữ liệu thành công của một số field cùng danh sách lỗi của field khác. Ví dụ `bookById` trả dữ liệu hợp lệ, `authorById` gặp lỗi từ service, còn `latestBooks` vẫn có thể trả kết quả.

Response có thể có dạng:

```json
{
  "data": {
    "bookById": {
      "id": "book-01",
      "title": "Spring in Action"
    },
    "authorById": null,
    "latestBooks": []
  },
  "errors": [
    {
      "message": "Author service is unavailable",
      "path": ["authorById"]
    }
  ]
}
```

Đây là ví dụ minh họa cho field nullable. Nếu một field có kiểu non-null và resolver trả `null` do lỗi, GraphQL áp dụng quy tắc null propagation lên parent nullable gần nhất. Vì thế, lỗi ở một field có thể làm một phần lớn hơn của response trở thành `null`, tùy vị trí non-null trong schema.

Spring for GraphQL cho phép chuyển exception thành lỗi GraphQL bằng `DataFetcherExceptionResolver`. Nên trả thông điệp phù hợp với client và giữ chi tiết kỹ thuật nhạy cảm trong log server. Client cần kiểm tra cả `data` và `errors`; không nên giả định HTTP response thành công đồng nghĩa mọi field đều thành công.

## 10. Tối ưu nhiều field bằng DataLoader

Nhiều root field và field lồng nhau trong cùng operation có thể yêu cầu dữ liệu liên quan. Ví dụ query lấy 20 quyển sách và mỗi quyển sách yêu cầu `author`. Nếu resolver `Book.author` thực hiện một truy vấn riêng cho từng sách, request có thể tạo ra vấn đề N+1.

DataLoader của GraphQL Java giúp gom các lần tải dữ liệu thành batch và cache kết quả trong phạm vi request. Spring for GraphQL tích hợp `BatchLoaderRegistry`, đồng thời cung cấp `@BatchMapping` cho trường hợp phổ biến:

```java
@Controller
public class BookAuthorController {

    private final AuthorService authorService;

    public BookAuthorController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> authors(List<Book> books) {
        Set<String> ids = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        Map<String, Author> authorsById = authorService.findAllByIds(ids);
        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, authorsById.get(book.authorId()));
        }
        return result;
    }
}
```

Các lần phân giải `Book.author` có thể được gom để service tải tác giả theo nhóm. Nếu nhiều root field trong cùng request cũng dùng chung một DataLoader với cùng key, chúng có thể hưởng lợi từ cache request và batch dispatch. Loader phải được quản lý theo request để không chia sẻ dữ liệu giữa các người dùng.

DataLoader không thay thế việc thiết kế query tốt. Client vẫn có thể yêu cầu một danh sách rất lớn hoặc selection set quá sâu. Cần giới hạn kích thước trang, đặt default/max limit và cân nhắc giới hạn query depth hoặc complexity.

## 11. Nhiều field và hiệu năng server-side

Một request duy nhất không có nghĩa chi phí thực thi luôn nhỏ. Một operation có thể chứa nhiều root field, nhiều alias của cùng field, nhiều fragment và selection set sâu. Mỗi nhánh có thể tạo thêm lời gọi service, truy vấn database hoặc tải dữ liệu bên ngoài.

Một số biện pháp cần cân nhắc:

- Dùng pagination cho danh sách và đặt giới hạn tối đa cho `first`, `limit` hoặc `pageSize`.
- Dùng DataLoader hoặc `@BatchMapping` cho quan hệ lặp để giảm N+1.
- Dùng async/reactive khi I/O có thể thực hiện bất đồng bộ và stack hỗ trợ phù hợp.
- Đo thời gian theo từng field bằng instrumentation/observation để tìm resolver chậm.
- Giới hạn depth và complexity, đặc biệt với query có nhiều alias hoặc quan hệ lồng nhau.
- Kiểm tra authorization cho từng field nhạy cảm, kể cả khi nhiều field nằm trong cùng operation.

Alias có thể tạo nhiều response key cho cùng một resolver. Ví dụ client có thể gọi `bookById` hàng chục lần với các ID khác nhau trong một operation. Điều này tiện cho client nhưng cũng có thể tạo tải lớn. Server cần giới hạn complexity hoặc số lần gọi phù hợp với yêu cầu hệ thống.

## 12. Kiểm thử query có nhiều field bằng GraphQlTester

`GraphQlTester` cho phép gửi một operation chứa nhiều root field và kiểm tra từng nhánh trong response:

```java
graphQlTester.document("""
        query Dashboard($bookId: ID!, $authorId: ID!) {
            bookById(id: $bookId) {
                title
            }
            authorById(id: $authorId) {
                name
            }
            latestBooks(limit: 3) {
                id
            }
        }
        """)
    .variable("bookId", "book-01")
    .variable("authorId", "author-01")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring in Action");
```

Có thể kiểm tra thêm các path `authorById.name` và `latestBooks[*].id` theo API assertion phù hợp. Nên kiểm thử:

- Tất cả root field cùng trả dữ liệu trong một operation.
- Alias cho phép gọi cùng field với các argument khác nhau.
- Variables được bind đúng và default value hoạt động.
- Field conflict bị phát hiện trước khi resolver chạy.
- Một field lỗi vẫn giữ dữ liệu field khác khi nullability cho phép.
- Root mutation được thực thi tuần tự.
- DataLoader gom các lần tải dữ liệu và không rò cache giữa request.

Đặc biệt, khi test lỗi một field, hãy kiểm tra cả `errors` và phần `data` còn lại để bảo đảm client nhận được partial response như thiết kế.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Hai lần gọi cùng field gây field conflict | Cùng response key nhưng argument hoặc selection không tương thích | Dùng alias khác nhau hoặc hợp nhất selection set |
| Response chỉ có một key cho field | GraphQL dùng tên field làm response key khi không có alias | Thêm alias nếu cần phân biệt nhiều kết quả |
| Resolver không chạy | Field chưa khai báo trên `Query` hoặc mapping sai tên | Kiểm tra SDL và `@QueryMapping` |
| Resolver phụ thuộc thứ tự field | Query root fields không có cam kết thực thi tuần tự | Thiết kế field độc lập hoặc chuyển thao tác ghi sang mutation |
| Một field lỗi làm dữ liệu khác thành null | Non-null propagation đi qua parent | Xem lại nullability và xử lý lỗi theo contract |
| Một request chứa nhiều alias gây tải cao | Mỗi response key có thể kích hoạt một lần resolve riêng | Giới hạn complexity, alias count và pagination |
| Nhiều field lồng nhau tạo N+1 | Resolver tải quan hệ theo từng source object | Dùng DataLoader hoặc `@BatchMapping` |
| Viết nhiều operation nhưng server chỉ chạy một | Request chọn operation qua `operationName` | Gửi từng operation hoặc gộp các root field vào một operation |

Khi debug, trước tiên kiểm tra query đã qua parse và validation chưa. Nếu validation thất bại, xem alias, argument, fragment và response key. Nếu operation hợp lệ nhưng dữ liệu thiếu, kiểm tra resolver, nullability và errors. Nếu dữ liệu đúng nhưng chậm, đo field-level latency, số truy vấn và kích thước selection set.

## 14. Nguyên tắc thiết kế Query với nhiều field

Hãy đưa các field độc lập mà màn hình hoặc use case cần vào cùng một query để giảm round trip. Dùng alias khi cùng một field cần được gọi với argument khác nhau. Dùng variables để tách input khỏi document và fragment để tái sử dụng selection set.

Giữ các query field có tính chất đọc và không phụ thuộc thứ tự thực thi. Dùng mutation cho thao tác thay đổi dữ liệu cần thứ tự xác định. Thiết kế nullability có chủ đích để một field lỗi không làm mất quá nhiều dữ liệu không liên quan. Dùng DataLoader cho quan hệ lặp, pagination và giới hạn complexity để kiểm soát chi phí server-side.

Trong Spring for GraphQL, mỗi root field được nối với resolver bằng `@QueryMapping`, còn field lồng nhau dùng `@SchemaMapping` hoặc `@BatchMapping`. GraphQL Java chịu trách nhiệm thu thập, kiểm tra và thực thi các field trong operation; Spring cung cấp cơ chế kết nối chúng với controller, service, context và DataLoader. Hiểu rõ các quy tắc này giúp xây dựng query nhiều field dễ dùng, hiệu quả và có hành vi ổn định.
