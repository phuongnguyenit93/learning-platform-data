# Query trả về list

## 1. Query trả về danh sách trong GraphQL

Một yêu cầu phổ biến của GraphQL API là trả về nhiều bản ghi, chẳng hạn danh sách sách, đơn hàng, người dùng hoặc sản phẩm. Trong GraphQL SDL, một field trả về danh sách được khai báo bằng cặp dấu ngoặc vuông `[]` quanh kiểu phần tử.

Ví dụ:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

`books` trả về một danh sách `Book`. Client chọn các field cần lấy cho từng phần tử:

```graphql
query BookCatalog {
    books {
        id
        title
    }
}
```

Response là một mảng JSON:

```json
{
  "data": {
    "books": [
      { "id": "book-101", "title": "GraphQL Fundamentals" },
      { "id": "book-102", "title": "Spring for GraphQL" }
    ]
  }
}
```

Trong Spring for GraphQL, root field `books` thường được xử lý bằng phương thức có `@QueryMapping`. Phương thức có thể trả về `List<Book>` hoặc một kiểu kết quả tương thích với danh sách đã khai báo trong SDL.

## 2. Hiểu đúng nullability của list

Trong GraphQL, dấu `!` có thể áp dụng cho danh sách và cho từng phần tử bên trong danh sách. Hai vị trí này độc lập với nhau.

| Kiểu SDL | Danh sách có thể null? | Phần tử có thể null? |
| --- | --- | --- |
| `[Book]` | Có | Có |
| `[Book!]` | Có | Không |
| `[Book]!` | Không | Có |
| `[Book!]!` | Không | Không |

Ví dụ:

```graphql
type Query {
    optionalBooks: [Book]
    booksWithRequiredItems: [Book!]!
}
```

Với `[Book!]!`, server phải trả về một danh sách khác `null`, và mọi phần tử trong danh sách cũng phải khác `null`. Danh sách rỗng `[]` vẫn hợp lệ. Không có dữ liệu phù hợp thường nên được biểu diễn bằng danh sách rỗng thay vì `null` nếu hợp đồng API xác định field luôn trả về danh sách.

Nếu resolver trả `null` cho field có kiểu `[Book!]!`, GraphQL phát sinh lỗi thực thi và áp dụng quy tắc null propagation. Nếu một phần tử là `null`, lỗi cũng lan theo nullability của phần tử và danh sách cha. Vì vậy, cần chọn nullability theo ngữ nghĩa nghiệp vụ và bảo đảm dữ liệu Java đáp ứng hợp đồng đó.

Trong Java, `List<Book>` có thể chứa `null` và bản thân biến tham chiếu cũng có thể là `null`. Kiểu Java không tự biểu diễn đầy đủ ràng buộc `!` của GraphQL. Resolver và tầng service phải bảo đảm không trả danh sách null hoặc phần tử null khi schema yêu cầu non-null.

## 3. Ánh xạ `@QueryMapping` sang `List<T>`

Với annotation-based controller, tên phương thức mặc định được dùng làm tên field trong root `Query`. Ví dụ schema khai báo `books`, phương thức `books()` có thể trả về `List<Book>`:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

```java
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books() {
        return bookService.findAll();
    }
}
```

`@QueryMapping` ánh xạ phương thức vào field `Query.books`. Spring for GraphQL gọi phương thức khi client yêu cầu field này, rồi GraphQL engine serialize từng phần tử theo kiểu `Book` trong schema.

Ví dụ trên minh họa mapping cơ bản. Trong ứng dụng thực tế, không nên để một endpoint danh sách gọi `findAll()` không giới hạn khi bảng có thể tăng lớn. Hãy thiết kế phân trang và giới hạn số phần tử như các phần tiếp theo.

### Khi nào cần `@SchemaMapping`?

`@QueryMapping` dành cho field thuộc root type `Query`. Nếu một field danh sách nằm trong một object khác, chẳng hạn `Author.books`, dùng `@SchemaMapping`:

```graphql
type Author {
    id: ID!
    books: [Book!]!
}
```

```java
@SchemaMapping(typeName = "Author", field = "books")
public List<Book> books(Author author) {
    return bookService.findByAuthorId(author.id());
}
```

Phương thức nhận source object `Author` và trả về danh sách sách của tác giả đó. Dù cả hai phương thức đều trả về `List<Book>`, annotation được chọn theo vị trí của field trong schema.

## 4. Trả về danh sách có lọc bằng arguments

Một danh sách hữu ích thường cho phép client truyền điều kiện lọc. Schema có thể khai báo các argument trực tiếp:

```graphql
type Query {
    booksByTitle(keyword: String!, availableOnly: Boolean = false): [Book!]!
}
```

Resolver dùng `@Argument` để nhận giá trị:

```java
@QueryMapping
public List<Book> booksByTitle(
        @Argument String keyword,
        @Argument Boolean availableOnly) {
    return bookService.searchByTitle(keyword, Boolean.TRUE.equals(availableOnly));
}
```

Client gửi operation:

```graphql
query SearchBooks($keyword: String!, $availableOnly: Boolean) {
    booksByTitle(keyword: $keyword, availableOnly: $availableOnly) {
        id
        title
    }
}
```

Variables:

```json
{
  "keyword": "spring",
  "availableOnly": true
}
```

Khi danh sách có nhiều tiêu chí lọc, nên gom chúng vào một input object để schema gọn và dễ mở rộng:

```graphql
input BookFilter {
    keyword: String
    authorId: ID
    available: Boolean
}

type Query {
    books(filter: BookFilter): [Book!]!
}
```

Java có thể dùng DTO hoặc record tương ứng:

```java
public record BookFilterInput(
        String keyword,
        String authorId,
        Boolean available) {
}

@QueryMapping
public List<Book> books(@Argument BookFilterInput filter) {
    return bookService.search(filter);
}
```

Tên field trong input object cần khớp với thuộc tính mà cơ chế binding của Spring sử dụng. Với input phức tạp, có thể dùng DTO có constructor hoặc setter phù hợp. Kiểm tra null cho từng điều kiện vì client có thể bỏ qua input hoặc để một field không được truyền.

Điều kiện lọc phải được áp dụng ở service hoặc repository trước khi trả kết quả. Không nên tải toàn bộ bảng về Java rồi mới lọc nếu database có thể thực hiện điều kiện hiệu quả hơn.

## 5. Phân trang là yêu cầu quan trọng của list query

Trả về toàn bộ danh sách có thể phù hợp với tập dữ liệu nhỏ và cố định. Với dữ liệu tăng theo thời gian, query không phân trang có thể tạo response lớn, chiếm bộ nhớ, tăng thời gian serialize và làm database chịu tải cao.

Một cách đơn giản là dùng offset pagination:

```graphql
type Query {
    books(first: Int = 20, offset: Int = 0): [Book!]!
}
```

`first` là số phần tử muốn lấy, `offset` là số phần tử bỏ qua trước khi lấy trang hiện tại. Resolver cần giới hạn các giá trị:

```java
@QueryMapping
public List<Book> books(
        @Argument Integer first,
        @Argument Integer offset) {

    int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    int start = offset == null ? 0 : Math.max(offset, 0);

    return bookService.findPage(pageSize, start);
}
```

Trong ví dụ, page size được giới hạn tối đa 100 và offset âm được đưa về 0. Quy tắc cụ thể có thể khác tùy API, nhưng server luôn phải tự kiểm tra giới hạn; không tin rằng client chỉ gửi giá trị hợp lệ.

### Ưu và nhược điểm của offset pagination

- Dễ hiểu, dễ tích hợp với `LIMIT`/`OFFSET` và giao diện có số trang.
- Có thể chậm khi offset rất lớn vì database phải đi qua nhiều bản ghi trước khi trả trang.
- Khi dữ liệu được thêm hoặc xóa giữa các lần gọi, bản ghi có thể bị lặp hoặc bị bỏ qua giữa các trang.
- Cần có thứ tự sắp xếp ổn định, tốt nhất bổ sung một khóa duy nhất làm tie-breaker.

Ví dụ truy vấn SQL nên sắp xếp rõ ràng:

```sql
SELECT id, title
FROM books
ORDER BY title ASC, id ASC
LIMIT :limit OFFSET :offset;
```

Nếu không có `ORDER BY`, database không bảo đảm thứ tự bản ghi. Khi phân trang, điều này khiến kết quả giữa các lần gọi khó dự đoán.

## 6. Phân trang với Spring Data `Pageable`

Nếu ứng dụng sử dụng Spring Data, có thể chuyển `first` và `offset` thành `Pageable` để repository thực hiện truy vấn có giới hạn.

Ví dụ service:

```java
public List<Book> findPageContent(int pageSize, int offset) {
    int pageNumber = offset / pageSize;
    Pageable pageable = PageRequest.of(
        pageNumber,
        pageSize,
        Sort.by(Sort.Order.asc("title"), Sort.Order.asc("id"))
    );

    return bookRepository.findAll(pageable)
        .map(bookMapper::toDomain)
        .getContent();
}
```

Đây là cách ánh xạ offset sang page number khi offset là bội số của `pageSize`. Nếu API cho phép offset bất kỳ, cần xử lý chính xác theo chiến lược repository hoặc dùng query hỗ trợ offset trực tiếp; phép chia nguyên sẽ làm tròn offset về đầu trang gần nhất.

Một lựa chọn khác là thiết kế API nhận `page` và `size` ngay từ đầu:

```graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
```

Khi đó `PageRequest.of(page, size, sort)` ánh xạ trực tiếp hơn. Dù chọn `Pageable`, không nên trả thẳng `Page<Book>` cho field khai báo `[Book!]!`; hãy trả `getContent()` hoặc thiết kế một GraphQL object riêng chứa `content`, `totalElements`, `totalPages` và thông tin trang.

## 7. Thiết kế response có metadata phân trang

Nếu client cần biết tổng số bản ghi hoặc còn trang tiếp theo hay không, thay vì chỉ trả về list, có thể khai báo một object chứa danh sách và metadata:

```graphql
type BookPage {
    items: [Book!]!
    page: Int!
    size: Int!
    totalElements: Long!
    totalPages: Int!
    hasNext: Boolean!
}

type Query {
    books(page: Int = 0, size: Int = 20): BookPage!
}
```

`Long` trong ví dụ là custom scalar, cần được khai báo và đăng ký runtime wiring hoặc dùng một scalar tương thích đã có. Nếu không muốn thêm custom scalar, có thể chọn `Int` khi giới hạn tổng số phần tử nằm trong phạm vi 32-bit.

Java record minh họa:

```java
public record BookPage(
        List<Book> items,
        int page,
        int size,
        long totalElements,
        int totalPages,
        boolean hasNext) {
}
```

Resolver:

```java
@QueryMapping
public BookPage books(
        @Argument Integer page,
        @Argument Integer size) {

    int pageNumber = page == null ? 0 : Math.max(page, 0);
    int pageSize = size == null ? 20 : Math.min(Math.max(size, 1), 100);

    Page<Book> result = bookService.findPage(
        PageRequest.of(pageNumber, pageSize)
    );

    return new BookPage(
        result.getContent(),
        result.getNumber(),
        result.getSize(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.hasNext()
    );
}
```

Ở ví dụ này, `Page<Book>` chỉ được dùng nội bộ trong Java; GraphQL response là `BookPage` có cấu trúc được khai báo rõ ràng trong SDL. Cách này giúp client biết dữ liệu trang và metadata mà không phụ thuộc vào cấu trúc cụ thể của Spring Data.

## 8. Cursor pagination cho danh sách thay đổi thường xuyên

Offset pagination phù hợp với nhiều màn hình quản trị và danh sách có số trang. Với feed hoặc danh sách cập nhật liên tục, cursor pagination thường ổn định hơn vì client tiếp tục từ vị trí của bản ghi cuối cùng thay vì yêu cầu bỏ qua một số lượng bản ghi.

Một cấu trúc connection đơn giản:

```graphql
type BookEdge {
    cursor: String!
    node: Book!
}

type PageInfo {
    endCursor: String
    hasNextPage: Boolean!
}

type BookConnection {
    edges: [BookEdge!]!
    pageInfo: PageInfo!
}

type Query {
    books(first: Int = 20, after: String): BookConnection!
}
```

Client gửi `after` bằng cursor nhận được từ trang trước:

```graphql
query NextBooks($first: Int!, $after: String) {
    books(first: $first, after: $after) {
        edges {
            cursor
            node {
                id
                title
            }
        }
        pageInfo {
            endCursor
            hasNextPage
        }
    }
}
```

Cursor thường mã hóa khóa sắp xếp của bản ghi cuối cùng, chẳng hạn `createdAt` và `id`. Server phải xác thực cursor, giữ thứ tự sắp xếp ổn định và áp dụng điều kiện truy vấn tiếp theo tương ứng. Không nên tin cursor do client gửi mà không kiểm tra cấu trúc và phạm vi của nó.

Cursor pagination không tự động bảo đảm snapshot nhất quán nếu dữ liệu bị cập nhật trong lúc client duyệt. Nếu nghiệp vụ yêu cầu tính nhất quán cao, cần thiết kế thêm snapshot/version hoặc điều kiện thời gian phù hợp.

## 9. Sắp xếp danh sách một cách an toàn

Client có thể cần sắp xếp danh sách theo tiêu đề, ngày tạo hoặc giá. Nên công bố các lựa chọn hợp lệ bằng enum thay vì nhận tên cột tùy ý:

```graphql
enum BookSortField {
    TITLE
    CREATED_AT
}

enum SortDirection {
    ASC
    DESC
}

type Query {
    books(
        first: Int = 20
        sortBy: BookSortField = TITLE
        direction: SortDirection = ASC
    ): [Book!]!
}
```

Resolver chuyển enum sang thuộc tính được phép:

```java
@QueryMapping
public List<Book> books(
        @Argument Integer first,
        @Argument BookSortField sortBy,
        @Argument SortDirection direction) {

    int size = first == null ? 20 : Math.min(Math.max(first, 1), 100);
    String property = switch (sortBy == null ? BookSortField.TITLE : sortBy) {
        case TITLE -> "title";
        case CREATED_AT -> "createdAt";
    };
    Sort.Direction order = direction == SortDirection.DESC
        ? Sort.Direction.DESC
        : Sort.Direction.ASC;

    return bookService.findSorted(PageRequest.of(
        0,
        size,
        Sort.by(order, property).and(Sort.by("id"))
    ));
}
```

Enum giới hạn các cột được phép sắp xếp và giúp schema tự mô tả API. Không nối trực tiếp chuỗi do client cung cấp vào SQL `ORDER BY`; nếu cần tên trường động, phải ánh xạ qua allowlist. Hãy bổ sung khóa phụ duy nhất để thứ tự ổn định khi nhiều bản ghi có cùng giá trị sort.

## 10. List query và hiệu năng server-side

Một GraphQL request có thể trả về danh sách ở root field và tiếp tục phân giải nhiều field lồng nhau cho từng phần tử. Ví dụ:

```graphql
query Books {
    books(first: 50) {
        id
        title
        author {
            id
            name
        }
    }
}
```

Nếu `books` tải 50 quyển sách trong một truy vấn, nhưng mỗi `Book.author` lại gọi repository riêng, server có thể thực hiện một truy vấn lấy sách cộng 50 truy vấn lấy tác giả. Đây là vấn đề N+1 ở field lồng nhau.

Các cách giảm chi phí:

- Phân trang và giới hạn số phần tử tối đa ở root list field.
- Đẩy filter, sort và pagination xuống repository/database.
- Dùng `@BatchMapping` hoặc DataLoader để gom các lần tải quan hệ.
- Chỉ truy vấn những cột cần thiết khi điều đó giúp giảm dữ liệu đọc.
- Tránh gọi service từ trong vòng lặp của resolver nếu có thể tải theo lô.
- Đo thời gian query, số lần gọi database và kích thước response.

Phân trang root list không tự giải quyết N+1. Ngược lại, DataLoader không thay thế giới hạn page size. Hai biện pháp giải quyết hai vấn đề khác nhau và thường cần kết hợp.

## 11. Bảo mật và giới hạn truy vấn list

List query có thể trả về lượng dữ liệu lớn hoặc dữ liệu thuộc nhiều người dùng khác nhau. Server phải áp dụng quyền truy cập trước khi trả dữ liệu cho client.

Một số nguyên tắc:

- Lọc theo tenant hoặc phạm vi người dùng ngay trong service/repository.
- Không dựa vào `authorId`, `ownerId` hoặc filter do client gửi để kết luận người dùng có quyền xem dữ liệu.
- Giới hạn `first`, `size`, `offset` và độ phức tạp query.
- Áp dụng rate limit theo người dùng hoặc client nếu endpoint có nguy cơ bị gọi quá mức.
- Tránh trả toàn bộ entity nếu có field nội bộ hoặc dữ liệu nhạy cảm không dành cho client.
- Ghi nhận operation và hiệu năng mà không log variables nhạy cảm không cần thiết.

Nếu mỗi phần tử có quyền truy cập riêng, cần lọc hoặc kiểm tra quyền theo từng bản ghi ở tầng server. Không trả danh sách đầy đủ rồi trông chờ client ẩn các phần tử không được phép xem.

## 12. Kiểm thử Query trả về list bằng GraphQlTester

`GraphQlTester` cho phép kiểm thử operation và cấu trúc response. Ví dụ:

```java
@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookQueryTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void returnsBookList() {
        graphQlTester.document("""
            query {
                books(first: 10) {
                    id
                    title
                }
            }
            """)
            .execute()
            .path("books")
            .entityList(BookView.class)
            .hasSize(2);
    }
}
```

`BookView` là DTO kiểm thử có các thuộc tính `id` và `title`; test context cần cung cấp dữ liệu phù hợp để danh sách có hai phần tử.

Nên kiểm tra thêm các trường hợp:

- Danh sách có nhiều phần tử và mỗi phần tử có đúng field.
- Không có dữ liệu thì trả `[]` theo hợp đồng list non-null.
- Filter không khớp trả danh sách rỗng.
- `first` bằng 0, số âm hoặc vượt giới hạn được xử lý theo chính sách.
- Offset hoặc cursor không hợp lệ bị từ chối hoặc chuẩn hóa theo hợp đồng.
- Thứ tự kết quả ổn định khi nhiều bản ghi có cùng giá trị sort.
- Field lồng nhau được batch đúng khi danh sách có nhiều parent.
- Người dùng không có quyền không nhận được bản ghi ngoài phạm vi.
- Lỗi từ service được ánh xạ thành GraphQL error phù hợp.

## 13. Lỗi thường gặp khi Query trả về list

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Field trả về `null` dù không có bản ghi | Resolver trả `null` thay vì danh sách rỗng | Trả `List.of()` hoặc collection rỗng nếu schema là `[Book!]!` |
| Lỗi non-null khi một phần tử null | List Java chứa phần tử null nhưng SDL dùng `[Book!]` | Loại bỏ hoặc xử lý phần tử không hợp lệ trước khi trả về |
| Query chậm khi dữ liệu tăng | Không phân trang hoặc tải toàn bộ bảng | Thêm giới hạn page size và truy vấn phân trang ở database |
| Các trang có bản ghi lặp hoặc thiếu | Không có thứ tự ổn định hoặc dữ liệu thay đổi giữa lần gọi | Dùng sort ổn định và cân nhắc cursor pagination |
| `Page<T>` không trả đúng list | Java Page object không khớp trực tiếp với SDL list | Trả `getContent()` hoặc tạo GraphQL page wrapper |
| Argument filter luôn null | Tên input field hoặc DTO binding không khớp | Kiểm tra SDL, tên thuộc tính và `@Argument` |
| Sort gây lỗi hoặc rủi ro truy vấn | Dùng tên cột tùy ý do client truyền | Dùng enum và allowlist thuộc tính sort |
| N+1 khi lấy field lồng nhau | Mỗi phần tử kích hoạt một truy vấn quan hệ | Dùng DataLoader hoặc `@BatchMapping` |
| Người dùng xem được dữ liệu tenant khác | Filter bảo mật chỉ dựa vào input client | Áp dụng tenant/authorization từ security context ở server |

## 14. Checklist thiết kế list query

- [ ] Field list được khai báo với nullability phù hợp.
- [ ] Resolver `@QueryMapping` hoặc `@SchemaMapping` trả kiểu Java tương ứng.
- [ ] Danh sách không có dữ liệu trả `[]` nếu schema yêu cầu list non-null.
- [ ] Có page size tối đa và validation cho các tham số phân trang.
- [ ] Filter và sort được xử lý ở service/repository.
- [ ] Thứ tự sort ổn định, có khóa phụ duy nhất khi cần.
- [ ] Không trả trực tiếp `Page<T>` nếu SDL khai báo list đơn giản.
- [ ] Có wrapper riêng nếu client cần metadata phân trang.
- [ ] Dùng cursor pagination khi phù hợp với danh sách thay đổi thường xuyên.
- [ ] Quan hệ lồng nhau đã được xem xét nguy cơ N+1.
- [ ] Authorization và tenant filter được áp dụng ở server.
- [ ] Có kiểm thử danh sách rỗng, nhiều phần tử, phân trang, filter và lỗi.

## Kết luận

Query trả về list trong GraphQL được khai báo bằng kiểu danh sách `[]` và thường ánh xạ sang `List<T>` trong phương thức `@QueryMapping` của Spring for GraphQL. Nullability của danh sách và từng phần tử cần được xác định rõ; với `[Book!]!`, danh sách rỗng hợp lệ nhưng danh sách null hoặc phần tử null đều vi phạm hợp đồng.

Đối với dữ liệu thực tế, list query cần có filter, sort và phân trang với giới hạn do server kiểm soát. Có thể dùng offset pagination cho danh sách đơn giản, cursor pagination cho feed thay đổi thường xuyên, hoặc một GraphQL wrapper khi client cần metadata trang. Kết hợp phân trang với DataLoader hoặc `@BatchMapping` cho field lồng nhau, authorization ở server và kiểm thử bằng `GraphQlTester` để list API hoạt động ổn định khi dữ liệu tăng.
