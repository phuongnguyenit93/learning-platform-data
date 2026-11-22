# Mutation tạo resource trong Spring for GraphQL

Mutation là operation dùng để thay đổi trạng thái của hệ thống. Trong một API quản lý tài nguyên, mutation thường tạo mới một resource như sách, khách hàng, đơn hàng hoặc sản phẩm. Với Spring for GraphQL, ta khai báo field tạo resource trong root type `Mutation`, sau đó triển khai bằng method có annotation `@MutationMapping`.

Một mutation tạo resource cần xác định rõ dữ liệu client được phép gửi, cách xác thực input, nơi sinh ID, quy tắc nghiệp vụ, transaction và dữ liệu trả về. Controller GraphQL tiếp nhận input và gọi application service; service thực hiện use case tạo mới và phối hợp repository; GraphQL serialize kết quả theo selection set mà client yêu cầu.

Sau bài này, bạn có thể:

- Thiết kế SDL cho mutation tạo resource với input type và output type phù hợp.
- Triển khai `@MutationMapping` và bind input bằng `@Argument`.
- Tổ chức luồng tạo resource qua controller, service và repository.
- Sinh ID ở server, kiểm tra quan hệ và trả resource vừa tạo.
- Xử lý validation, authorization, transaction và lỗi nghiệp vụ.
- Thiết kế response payload và hiểu nullability khi tạo mới thất bại.
- Kiểm thử mutation bằng `GraphQlTester`.
- Cân nhắc duplicate request, idempotency và concurrency khi API được gọi nhiều lần.

## 1. Mutation tạo resource là gì?

GraphQL có ba root operation type: `Query` để đọc dữ liệu, `Mutation` để thay đổi trạng thái và `Subscription` để nhận luồng sự kiện. Khi client muốn tạo một resource mới, nó gọi field thuộc root type `Mutation`.

Ví dụ, một API thư viện cho phép tạo sách mới. Client gửi tiêu đề, mã tác giả và năm xuất bản; server kiểm tra dữ liệu, sinh ID, lưu sách rồi trả về resource vừa tạo.

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}

input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
}

type Book {
    id: ID!
    title: String!
    publishedYear: Int
    author: Author
}

type Author {
    id: ID!
    name: String!
}
```

Field `createBook` nhận một input object bắt buộc và trả về `Book`. Client có thể chọn những field cần dùng sau khi tạo thành công:

```graphql
mutation {
    createBook(input: {
        title: "Spring GraphQL in Practice"
        authorId: "author-42"
        publishedYear: 2026
    }) {
        id
        title
        publishedYear
    }
}
```

Mutation tạo resource thường trả lại dữ liệu vừa được tạo để client không cần gửi thêm một query chỉ nhằm lấy ID hoặc các thuộc tính ban đầu. Server vẫn chỉ trả những field mà client chọn trong selection set.

Theo quy tắc thực thi GraphQL, các field cấp cao nhất của một mutation operation được thực thi tuần tự theo thứ tự xuất hiện trong document. Điều này giúp client thực hiện nhiều thay đổi có thứ tự trong cùng operation. Tuy nhiên, GraphQL không tự mở một database transaction bao quanh toàn bộ các field đó; nếu nhiều thay đổi cần tính nguyên tử, hãy tạo một mutation/use case duy nhất và quản lý transaction ở service. Các request mutation độc lập vẫn có thể chạy đồng thời.

## 2. Thiết kế input type cho thao tác tạo mới

Nên gom các trường đầu vào liên quan vào một input object:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    publishedYear: Int
    tags: [String!]
}
```

Input type giúp phân biệt dữ liệu client được phép gửi với dữ liệu do server quản lý. Ví dụ, `id`, `createdAt`, `createdBy` và trạng thái kiểm duyệt ban đầu thường do server sinh hoặc áp dụng theo quy tắc nghiệp vụ, nên không nhất thiết xuất hiện trong `CreateBookInput`.

Không nên tái sử dụng một output object type làm input. GraphQL phân biệt input type và output type: input object chỉ chứa scalar, enum hoặc input object khác; output object có thể chứa field object lồng nhau và resolver riêng.

### Vì sao nên dùng input object?

- Các trường đầu vào được nhóm thành một cấu trúc có tên và có thể mở rộng.
- Có thể dùng lại input trong nhiều mutation nếu ngữ nghĩa thực sự giống nhau.
- Có thể áp dụng validation trên DTO/record tương ứng.
- Không vô tình cho client gửi các trường nội bộ như ID, audit metadata hoặc trạng thái hệ thống.
- Dễ phân biệt một thao tác tạo mới với thao tác cập nhật từng phần.

Nếu mutation chỉ nhận một giá trị đơn giản, có thể dùng argument trực tiếp. Khi thao tác có nhiều trường hoặc có khả năng mở rộng, input object thường dễ duy trì hơn.

## 3. Chọn kiểu trả về: resource hay payload?

Mutation có thể trả trực tiếp resource vừa tạo:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

Đây là thiết kế gọn, phù hợp khi client chỉ cần resource. Nếu kết quả cần thêm metadata như thông báo, trạng thái xử lý, cảnh báo hoặc danh sách lỗi theo từng trường, có thể dùng payload type:

```graphql
type CreateBookPayload {
    book: Book
    message: String!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Payload giúp hợp đồng diễn đạt rõ hơn khi thao tác có nhiều thông tin kết quả. Không cần tạo payload chỉ để bọc một object nếu nó không mang thêm ý nghĩa.

Với thao tác bulk hoặc có thể thành công một phần, payload có thể chứa kết quả theo từng item:

```graphql
type CreateBookItemResult {
    index: Int!
    book: Book
    errorCode: String
    message: String
}

type CreateBooksPayload {
    results: [CreateBookItemResult!]!
}

type Mutation {
    createBooks(inputs: [CreateBookInput!]!): CreateBooksPayload!
}
```

Chọn payload dựa trên ngữ nghĩa use case, không chỉ vì một quy ước hình thức. Với một resource đơn giản, trả trực tiếp `Book!` là đủ.

## 4. Triển khai bằng @MutationMapping

Spring for GraphQL cung cấp `@MutationMapping` để liên kết method controller với field cùng tên trên root type `Mutation`:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public BookView createBook(@Argument("input") CreateBookInput input) {
        CreateBookCommand command = new CreateBookCommand(
                input.title(),
                input.authorId(),
                input.publishedYear());

        return bookService.create(command);
    }
}
```

`@Argument("input")` bind argument `input` từ GraphQL document vào record `CreateBookInput`. `@MutationMapping` mặc định lấy tên method làm tên field; vì vậy method `createBook` được nối với `Mutation.createBook`.

Nếu tên method không trùng tên field, có thể chỉ rõ tên mapping:

```java
@MutationMapping(name = "createBook")
public BookView create(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

Method controller nên tập trung vào việc nhận input, chuyển thành command và gọi service. Việc sinh ID, kiểm tra tác giả có tồn tại hay không, đặt trạng thái ban đầu và lưu dữ liệu thuộc use case tạo sách.

## 5. Luồng tạo resource qua service và repository

Một luồng tạo mới điển hình:

```mermaid
flowchart TD
    A[Client gửi mutation] --> B[GraphQL validate operation]
    B --> C[@MutationMapping nhận input]
    C --> D[Bind và validate DTO]
    D --> E[BookService.create command]
    E --> F[Kiểm tra tác giả và quy tắc nghiệp vụ]
    F --> G[Sinh ID và tạo entity]
    G --> H[Repository lưu resource]
    H --> I[Map thành BookView]
    I --> J[GraphQL resolve selection set]
    J --> K[Trả response]
```

Service có thể được triển khai như sau:

```java
public record CreateBookCommand(
        String title,
        String authorId,
        Integer publishedYear) {
}

@Service
public class BookService {

    private final BookRepository bookRepository;
    private final AuthorRepository authorRepository;
    private final BookMapper bookMapper;

    public BookService(
            BookRepository bookRepository,
            AuthorRepository authorRepository,
            BookMapper bookMapper) {
        this.bookRepository = bookRepository;
        this.authorRepository = authorRepository;
        this.bookMapper = bookMapper;
    }

    @Transactional
    public BookView create(CreateBookCommand command) {
        AuthorEntity author = authorRepository.findById(command.authorId())
                .orElseThrow(() -> new AuthorNotFoundException(command.authorId()));

        BookEntity book = new BookEntity();
        book.setId(UUID.randomUUID().toString());
        book.setTitle(command.title().trim());
        book.setPublishedYear(command.publishedYear());
        book.setAuthor(author);

        BookEntity saved = bookRepository.save(book);
        return bookMapper.toView(saved);
    }
}
```

Đây là ví dụ minh họa theo kiểu JPA. Với hệ thống dùng ID do database sinh, service có thể để repository/database tạo ID rồi đọc ID từ entity đã lưu. Với hệ thống dùng UUID, ULID hoặc ID từ một dịch vụ khác, việc sinh ID nên được đặt ở application/domain layer phù hợp.

## 6. ID và các trường do server quản lý

Khi tạo resource, cần xác định trường nào thuộc quyền quyết định của client và trường nào do server kiểm soát.

| Trường | Nguồn thường dùng | Lý do |
| --- | --- | --- |
| `title` | Client | Dữ liệu nghiệp vụ người dùng nhập |
| `authorId` | Client | Tham chiếu đến resource đã tồn tại |
| `id` | Server/database | Định danh duy nhất do hệ thống quản lý |
| `createdAt` | Server | Thời điểm tạo đáng tin cậy |
| `createdBy` | Security context | Danh tính người dùng đã xác thực |
| `status` | Quy tắc nghiệp vụ | Trạng thái khởi tạo phải theo policy của ứng dụng |

Không nên tin `createdBy` hoặc `createdAt` do client gửi nếu các trường này có ý nghĩa kiểm toán. Nếu cho client truyền ID tùy ý, service cần kiểm tra quyền và xung đột ID; với đa số thao tác tạo resource, để server sinh ID giúp tránh giả mạo hoặc collision ngoài ý muốn.

ID cần được trả về trong response để client có thể tham chiếu resource mới. Nếu database sinh ID khi insert, bảo đảm mapper dùng giá trị sau khi lưu, không dùng giá trị trước insert có thể vẫn null.

## 7. Validation input trước khi tạo

GraphQL schema kiểm tra kiểu và nullability. Ví dụ `title: String!` buộc client cung cấp giá trị khác null, nhưng không đảm bảo chuỗi không rỗng hoặc không vượt quá giới hạn nghiệp vụ.

Có thể dùng Bean Validation trên record:

```java
public record CreateBookInput(
        @NotBlank(message = "Title must not be blank")
        @Size(max = 200, message = "Title must be at most 200 characters")
        String title,

        @NotBlank(message = "Author ID is required")
        String authorId,

        @Min(1450)
        @Max(2100)
        Integer publishedYear) {
}
```

Controller yêu cầu validation cho argument:

```java
@MutationMapping
public BookView createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

Ứng dụng cần có Bean Validation provider và cấu hình phù hợp. Validation của DTO phù hợp với định dạng, độ dài và ràng buộc cục bộ của input. Các quy tắc phụ thuộc dữ liệu hiện có như tác giả phải tồn tại, tiêu đề không được trùng trong cùng catalog hoặc người dùng có quyền tạo sách cần được kiểm tra trong service/domain.

Không dựa hoàn toàn vào validation ở controller. Service có thể được gọi từ REST, job hoặc message consumer, nên các invariant quan trọng phải được bảo vệ tại application/domain boundary.

## 8. Kiểm tra quan hệ và quyền tạo resource

Input có thể chứa ID của resource liên quan, ví dụ `authorId`. Việc GraphQL xác nhận argument có kiểu `ID` chỉ kiểm tra scalar; nó không bảo đảm tác giả tồn tại hoặc người dùng được phép gắn sách vào tác giả đó.

Service cần kiểm tra:

- Resource được tham chiếu có tồn tại hay không.
- Resource đó có đang ở trạng thái cho phép liên kết hay không.
- Người gọi có quyền tạo resource trong tenant hoặc phạm vi dữ liệu tương ứng hay không.
- Các quan hệ có tạo thành vòng tham chiếu hoặc vi phạm constraint nghiệp vụ hay không.

Có thể dùng Spring Method Security để giới hạn use case:

```java
@PreAuthorize("hasAuthority('BOOK_CREATE')")
@Transactional
public BookView create(CreateBookCommand command) {
    // Kiểm tra tác giả, tenant và các invariant trước khi lưu.
    // ...
}
```

Ứng dụng cần bật method security. Nếu quyền phụ thuộc người dùng hiện tại, actor hoặc tenant phải được lấy từ security context đáng tin cậy và truyền vào use case dưới dạng dữ liệu ứng dụng; không nhận danh tính từ input client rồi coi đó là đã xác thực.

## 9. Transaction và thời điểm trả kết quả

Tạo resource thường cần một transaction để bảo đảm các thao tác ghi liên quan thành công cùng nhau. Ví dụ, tạo sách và ghi audit event trong cùng database có thể được thực hiện trong một service method `@Transactional`.

```java
@Transactional
public BookView create(CreateBookCommand command) {
    AuthorEntity author = authorRepository.findById(command.authorId())
            .orElseThrow(() -> new AuthorNotFoundException(command.authorId()));

    BookEntity book = bookRepository.save(BookEntity.create(command, author));
    auditRepository.save(AuditEntry.bookCreated(book.getId()));

    return bookMapper.toView(book);
}
```

Nếu ghi audit thất bại và cả hai repository cùng tham gia một transaction manager, transaction có thể rollback việc tạo sách. Nếu cần phát sự kiện ra broker hoặc gọi hệ thống ngoài, transaction database không tự tạo atomicity trên các hệ thống đó; cân nhắc transactional outbox hoặc một quy trình phối hợp phù hợp.

Controller không nên giữ transaction mở trong lúc chờ client. Transaction nên nằm quanh use case đồng bộ hoặc reactive transaction boundary tương ứng với công nghệ truy cập dữ liệu.

## 10. Trả resource vừa tạo và xử lý selection set

Sau khi service lưu resource, controller trả `BookView`. GraphQL tiếp tục phân giải các field client yêu cầu:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        author {
            id
            name
        }
    }
}
```

Service không cần trả toàn bộ quan hệ lồng nhau nếu `BookView` chỉ chứa `authorId`. Field `author` có thể được phân giải bởi `@SchemaMapping` hoặc `@BatchMapping` theo source object. Điều này giữ cho mutation service tập trung vào việc tạo sách, còn GraphQL xử lý selection set.

Nếu response cần field tính toán như `displayLabel`, có thể cung cấp resolver field tương ứng. Không nên tự dựng một response JSON trong mutation method; hãy trả object có kiểu để GraphQL thực hiện serialization và nullability theo schema.

## 11. Chọn nullability và biểu diễn lỗi

Schema sau:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

cam kết rằng khi mutation hoàn tất thành công, field trả về một `Book` khác null. Nếu service ném exception, GraphQL có thể trả lỗi trong `errors`; do field là non-null, null có thể lan lên parent gần nhất cho phép null. Root response có thể có `data: null` tùy vị trí lỗi và nullability của các field cha.

Nếu muốn biểu diễn lỗi nghiệp vụ trong payload, có thể thiết kế kết quả có trạng thái:

```graphql
type UserError {
    field: String
    code: String!
    message: String!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Khi đó, lỗi validation có thể được trả trong `userErrors` và response vẫn là payload hợp lệ. Đây là một lựa chọn thiết kế API; không cần dùng payload error nếu ứng dụng muốn biểu diễn lỗi bằng GraphQL error chuẩn.

Không trả `Book!` với một object giả hoặc dữ liệu mặc định khi tạo thất bại. Chọn một chiến lược nhất quán: lỗi GraphQL, payload có lỗi nghiệp vụ, hoặc kết quả kiểu union nếu API có lý do rõ ràng.

## 12. Ánh xạ exception thành GraphQL error

Service nên dùng exception có ý nghĩa nghiệp vụ như `AuthorNotFoundException`, `DuplicateBookException` hoặc `BookCreationNotAllowedException`. Lớp GraphQL có thể chuyển chúng thành error phù hợp bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`.

Ví dụ handler trong controller advice:

```java
@ControllerAdvice
public class GraphQlExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAuthorNotFound(AuthorNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Author not found")
                .build();
    }

    @GraphQlExceptionHandler
    public GraphQLError handleDuplicateBook(DuplicateBookException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.BAD_REQUEST)
                .message("A book with the same title already exists")
                .build();
    }
}
```

Thông điệp gửi client nên đủ để xử lý tình huống nhưng không tiết lộ SQL, stack trace hoặc dữ liệu nội bộ. Log phía server có thể giữ nguyên exception và thông tin chẩn đoán.

## 13. Xử lý duplicate request và idempotency

Nếu client gửi mutation tạo resource hai lần, server có thể tạo hai resource khác nhau. Đây không nhất thiết là lỗi: một mutation `create` thông thường tạo một resource cho mỗi lần thực thi. Tuy nhiên, retry do timeout hoặc mất kết nối có thể khiến client không biết lần đầu đã commit hay chưa.

Nếu use case cần tránh tạo trùng khi client retry, có thể thiết kế idempotency key:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
    idempotencyKey: String!
}
```

Service lưu key cùng kết quả hoặc resource đã tạo. Khi nhận lại cùng key trong phạm vi người dùng/operation được xác định, service trả lại kết quả trước đó thay vì tạo resource mới. Cần có unique constraint ở database hoặc cơ chế lưu key có tính nguyên tử để xử lý hai request đồng thời.

Không dùng riêng tiêu đề hoặc các field nghiệp vụ làm idempotency key nếu chúng không định danh duy nhất một lần yêu cầu. Hai lần tạo hai cuốn sách cùng tiêu đề có thể là hai hành động hợp lệ tùy domain.

## 14. Concurrency và ràng buộc dữ liệu

Hai client có thể đồng thời tạo resource với cùng dữ liệu. Kiểm tra duplicate trước khi insert có thể gặp race condition:

1. Request A kiểm tra chưa có sách với tiêu đề X.
2. Request B cũng kiểm tra chưa có sách với tiêu đề X.
3. Cả hai cùng insert.

Nếu nghiệp vụ yêu cầu duy nhất, hãy đặt unique constraint ở database và chuyển lỗi constraint thành lỗi nghiệp vụ phù hợp. Kiểm tra ở service giúp thông báo sớm, còn constraint ở persistence bảo vệ tính đúng đắn khi có cạnh tranh.

Với quan hệ như `authorId`, cần xử lý trường hợp tác giả bị xóa hoặc thay đổi trạng thái trong lúc tạo sách. Foreign key, transaction isolation và quy tắc domain cần phối hợp để bảo vệ dữ liệu. Không dựa vào một lần kiểm tra tồn tại ở controller làm bảo đảm cuối cùng.

## 15. Mutation tạo resource với kiểu trả về reactive

Trong ứng dụng Spring WebFlux dùng repository reactive, resolver có thể trả `Mono<BookView>`:

```java
@MutationMapping
public Mono<BookView> createBook(
        @Argument("input") CreateBookInput input) {

    CreateBookCommand command = toCommand(input);
    return reactiveBookService.create(command);
}
```

Service thực hiện thao tác qua repository non-blocking và trả publisher. Nếu dùng R2DBC, transaction cần dùng reactive transaction manager và giữ các thao tác trong cùng pipeline. Không gọi `.block()` trong resolver.

Với Spring MVC và JPA/JDBC, method đồng bộ thường phù hợp:

```java
@MutationMapping
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}
```

Không bọc lời gọi blocking bằng `Mono.just(bookService.create(...))` rồi cho rằng nó trở thành non-blocking; lời gọi service vẫn chạy trước khi publisher được tạo. Nếu phải dùng thư viện blocking trong WebFlux, cần cô lập lời gọi ở scheduler/executor có giới hạn hoặc thay bằng API non-blocking.

## 16. Kiểm thử mutation bằng GraphQlTester

`GraphQlTester` kiểm thử mutation từ góc nhìn client, bao gồm schema, argument binding, resolver và response selection:

```java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
                publishedYear
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL in Practice",
            "authorId", "author-42",
            "publishedYear", 2026))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL in Practice");
```

Nên kiểm thử thêm:

1. Mutation hợp lệ tạo resource và trả ID khác null.
2. Resource vừa tạo có thể được query lại bằng ID trả về.
3. Thiếu field non-null hoặc sai kiểu bị GraphQL từ chối trước khi gọi service.
4. Input vi phạm Bean Validation được ánh xạ thành lỗi theo cấu hình.
5. Resource tham chiếu không tồn tại tạo đúng lỗi nghiệp vụ.
6. Người dùng không có quyền không thể tạo resource.
7. Duplicate request hoặc idempotency key được xử lý đúng.
8. Unique constraint xử lý được hai request cạnh tranh.
9. Lỗi khi ghi audit hoặc quan hệ phụ làm transaction rollback theo yêu cầu.
10. Payload hoặc GraphQL error có response shape đúng với schema.

Với `@GraphQlTest`, có thể mock `BookService` để kiểm tra mapping và argument binding. Service test riêng kiểm tra transaction, repository và quy tắc domain. Integration test với database kiểm thử xác nhận ID sinh, constraint và rollback thực tế.

## 17. Những lỗi thường gặp

- **Đặt field tạo mới trong `Query`:** thao tác thay đổi trạng thái phải thuộc `Mutation`.
- **Nhận toàn bộ entity từ client:** có thể cho phép client điều khiển ID, audit field hoặc trạng thái nội bộ. Dùng input model có chủ đích.
- **Dùng output type làm input:** GraphQL phân biệt input object và object type.
- **Sinh ID trước khi lưu nhưng không đồng bộ với database:** response có thể trả ID sai hoặc null. Dùng ID từ resource đã persist.
- **Chỉ kiểm tra quan hệ ở controller:** service/use case vẫn phải bảo vệ invariant và quyền truy cập.
- **Không đặt transaction cho nhiều thao tác ghi liên quan:** có thể tạo resource dở dang hoặc audit không nhất quán.
- **Trả null cho mutation non-null khi thất bại:** gây null propagation và response khó hiểu. Chọn error hoặc payload semantics rõ ràng.
- **Không xử lý retry:** client có thể tạo trùng resource sau timeout. Dùng idempotency nếu use case yêu cầu.
- **Chỉ kiểm tra duplicate bằng truy vấn trước insert:** vẫn có race condition. Dùng unique constraint làm bảo vệ cuối cùng.
- **Gọi service blocking trong WebFlux:** làm chặn luồng xử lý reactive.
- **Mutation controller tự truy cập nhiều repository:** logic nghiệp vụ và transaction bị phân tán. Đưa use case vào service.

## 18. Quy trình triển khai mutation tạo resource

Khi thêm mutation tạo mới, hãy thực hiện theo trình tự:

1. Xác định resource và các trường client được phép cung cấp.
2. Khai báo input type; để server quản lý ID, audit metadata và trạng thái hệ thống khi phù hợp.
3. Chọn output resource trực tiếp hay payload có metadata/lỗi theo nhu cầu API.
4. Viết method `@MutationMapping` và bind input bằng `@Argument`.
5. Chuyển input thành command và gọi application service.
6. Trong service, kiểm tra quan hệ, quyền, invariant và duplicate; sinh ID hoặc nhận ID từ persistence.
7. Lưu resource và các thay đổi liên quan trong transaction phù hợp.
8. Trả DTO/resource đã lưu để GraphQL resolve selection set.
9. Ánh xạ lỗi nghiệp vụ thành GraphQL error hoặc payload theo hợp đồng.
10. Kiểm thử thành công, validation, authorization, rollback, retry và concurrency.

Mutation tạo resource là điểm vào của một use case thay đổi trạng thái. Spring for GraphQL cung cấp `@MutationMapping` để nối field SDL với controller; service chịu trách nhiệm tạo resource đúng quy tắc và repository lưu dữ liệu. Khi input được giới hạn rõ, ID và metadata do server quản lý, transaction và lỗi được thiết kế có chủ đích, client sẽ nhận được resource mới cùng một hợp đồng GraphQL ổn định.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Argument Binding and Validation](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.arguments)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [GraphQL Specification — Mutation](https://spec.graphql.org/October2021/#sec-Mutation)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
