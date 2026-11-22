# @MutationMapping cho Mutation field

Trong GraphQL, **mutation** là operation dùng để thay đổi trạng thái dữ liệu, ví dụ tạo sách, cập nhật thông tin tác giả hoặc xóa một bản ghi. Schema khai báo các thao tác này trong root type `Mutation`; Spring for GraphQL dùng annotation `@MutationMapping` để kết nối một method Java với từng field của root type đó.

`@MutationMapping` giúp controller diễn đạt rõ mục đích của method và tận dụng cơ chế argument binding, dependency injection cùng exception handling của Spring. Khi thiết kế mutation, ngoài việc ánh xạ đúng field, cần quan tâm đến input object, kết quả trả về, transaction, validation, authorization và cách kiểm thử.

Bài học này trình bày cách khai báo mutation trong SDL, triển khai `@MutationMapping`, nhận arguments bằng `@Argument`, xây dựng create/update/delete operation và xử lý các tình huống thường gặp trong Spring for GraphQL.

## 1. Mutation trong GraphQL là gì?

GraphQL định nghĩa ba operation type thường dùng:

| Operation | Mục đích | Root type mặc định |
| --- | --- | --- |
| Query | Đọc dữ liệu | `Query` |
| Mutation | Thay đổi dữ liệu | `Mutation` |
| Subscription | Nhận sự kiện hoặc dữ liệu theo thời gian | `Subscription` |

Mutation thường được dùng cho các hành động có side effect:

- Tạo một cuốn sách mới.
- Đổi tên hoặc cập nhật mô tả một tác giả.
- Đặt hàng hoặc hủy đơn hàng.
- Đánh dấu một thông báo đã đọc.
- Xóa một tài nguyên.

Ví dụ operation phía client:

```graphql
mutation {
  createBook(title: "Spring for GraphQL") {
    id
    title
  }
}
```

Từ khóa `mutation` xác định operation type. Field `createBook` là thao tác cụ thể được gọi trên root mutation type. Client có thể chọn các field của object được trả về, giống như khi truy vấn dữ liệu bằng Query.

Mutation không phải HTTP route riêng. Với Spring for GraphQL, Query và Mutation thường đi qua cùng GraphQL endpoint; GraphQL engine phân biệt loại operation dựa trên document mà client gửi.

## 2. Khai báo Mutation field trong SDL

Root mutation type thường được khai báo bằng `type Mutation`:

```graphql
type Mutation {
  createBook(title: String!): Book!
}

type Book {
  id: ID!
  title: String!
}
```

Field `createBook` nhận argument `title` và trả về một `Book` khác null. Dấu `!` trong `String!` có nghĩa client phải truyền giá trị khác null. Dấu `!` ở `Book!` có nghĩa field phải trả về một object khác null nếu thực thi thành công.

Khi schema có nhiều thao tác, mỗi thao tác là một field của root type `Mutation`:

```graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
  updateBook(id: ID!, input: UpdateBookInput!): Book
  deleteBook(id: ID!): Boolean!
}
```

Trong ứng dụng thực tế, input object thường dễ mở rộng và dễ quản lý hơn việc thêm nhiều argument trực tiếp vào field. Các phần tiếp theo sử dụng input object để minh họa.

## 3. @MutationMapping kết nối method Java với Mutation field

`@MutationMapping` nằm trong package:

```java
org.springframework.graphql.data.method.annotation.MutationMapping
```

Annotation này đánh dấu một method trong class `@Controller` là handler cho một field trên root type `Mutation`.

SDL:

```graphql
type Mutation {
  createBook(title: String!): Book!
}
```

Controller:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument String title) {
        return bookService.create(title);
    }
}
```

Spring for GraphQL phát hiện controller bean, đọc annotation mapping và đăng ký data fetcher cho field tương ứng. Khi client gọi `Mutation.createBook`, method `createBook` được thực thi.

`@MutationMapping` là dạng rút gọn của `@SchemaMapping` trên type `Mutation`. Hai cách sau cùng ánh xạ đến field `Mutation.createBook`:

```java
@MutationMapping
public Book createBook(@Argument String title) {
    return bookService.create(title);
}
```

```java
@SchemaMapping(typeName = "Mutation", field = "createBook")
public Book createBook(@Argument String title) {
    return bookService.create(title);
}
```

Thông thường nên dùng `@MutationMapping` vì thể hiện rõ ý nghĩa của method. `@SchemaMapping` hữu ích khi cần ánh xạ một field thuộc type khác hoặc cần chỉ định parent type tường minh.

## 4. Quy tắc đặt tên field

Nếu không chỉ định tên, Spring suy ra field name từ tên method. Ví dụ:

```java
@MutationMapping
public Book createBook(@Argument String title) {
    // ...
}
```

Method trên mặc định ánh xạ tới field `Mutation.createBook`.

Nếu tên method Java khác tên field trong SDL, chỉ định `name`:

```java
@MutationMapping(name = "createBook")
public Book save(@Argument String title) {
    return bookService.create(title);
}
```

Tên field phải khớp chính xác với SDL, kể cả chữ hoa/chữ thường. Nếu schema khai báo `createBook` nhưng method vô tình ánh xạ sang `save`, client sẽ không gọi được handler mong muốn.

Tránh đăng ký hai method cùng xử lý một mutation field trong cùng application context. Mỗi field nên có một handler rõ ràng; nếu cần phối hợp nhiều nghiệp vụ, method controller có thể gọi một service điều phối.

## 5. Nhận dữ liệu bằng @Argument

`@Argument` lấy giá trị từ argument của GraphQL field và chuyển đổi sang kiểu Java tương ứng.

### Nhận argument đơn giản

SDL:

```graphql
type Mutation {
  renameBook(id: ID!, title: String!): Book!
}
```

Controller:

```java
@MutationMapping
public Book renameBook(
        @Argument("id") String id,
        @Argument("title") String title) {
    return bookService.rename(id, title);
}
```

Client:

```graphql
mutation RenameBook {
  renameBook(id: "book-1", title: "Spring GraphQL in Practice") {
    id
    title
  }
}
```

Có thể chỉ định tên argument trong `@Argument("id")` để tránh phụ thuộc vào tên parameter Java hoặc cấu hình compiler giữ parameter names.

### Nhận input object

Khi mutation cần nhiều dữ liệu, nên gom chúng vào một input type:

```graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
```

Java input model:

```java
public record CreateBookInput(
        String title,
        String authorId,
        Integer publishedYear) {
}
```

Controller:

```java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(input);
}
```

Client gửi input bằng variables:

```graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    publishedYear
  }
}
```

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "authorId": "author-1",
    "publishedYear": 2026
  }
}
```

GraphQL kiểm tra kiểu và nullability trước khi gọi resolver. Spring for GraphQL sau đó bind input map sang Java input object. Dùng DTO hoặc record riêng cho input giúp API không phụ thuộc trực tiếp vào entity persistence.

## 6. Xây dựng Create mutation

Một mutation tạo mới thường nhận input object và trả về object vừa được tạo:

```graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publishedYear: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author
  publishedYear: Int
}
```

Controller:

```java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Service thực hiện nghiệp vụ và persistence:

```java
@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book create(CreateBookInput input) {
        Book book = new Book(
                UUID.randomUUID().toString(),
                input.title().trim(),
                input.authorId(),
                input.publishedYear());

        return bookRepository.save(book);
    }
}
```

Đoạn code minh họa luồng xử lý; model và repository cần được điều chỉnh theo persistence technology của ứng dụng. Điểm quan trọng là controller nhận input rồi ủy quyền nghiệp vụ cho service. Transaction thường đặt ở service method để ranh giới commit/rollback gắn với use case.

## 7. Xây dựng Update mutation

Update mutation cần xác định rõ ý nghĩa của từng field: thay thế toàn bộ resource, hay chỉ cập nhật một phần.

Ví dụ cập nhật title:

```graphql
input UpdateBookInput {
  title: String!
  publishedYear: Int
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book
}
```

Controller:

```java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("input") UpdateBookInput input) {
    return bookService.update(id, input);
}
```

Nếu book không tồn tại, schema cho phép trả `null` vì kết quả là `Book` nullable. Ứng dụng cũng có thể chọn ném domain exception và chuyển nó thành GraphQL error hoặc dùng payload có trường lỗi nghiệp vụ.

### Phân biệt omitted và null trong cập nhật một phần

Với partial update, ba trạng thái thường mang ý nghĩa khác nhau:

| Giá trị client gửi | Ý nghĩa thường gặp |
| --- | --- |
| Không gửi field | Giữ nguyên giá trị cũ |
| Gửi field với `null` | Xóa giá trị nếu nghiệp vụ cho phép |
| Gửi giá trị cụ thể | Cập nhật thành giá trị đó |

Ví dụ schema:

```graphql
type Mutation {
  updateBookSummary(id: ID!, summary: String): Book
}
```

Trong Spring for GraphQL, có thể dùng `ArgumentValue<T>` để phân biệt argument bị bỏ qua với argument được gửi tường minh là null:

```java
import org.springframework.graphql.data.ArgumentValue;

@MutationMapping
public Book updateBookSummary(
        @Argument("id") String id,
        @Argument("summary") ArgumentValue<String> summary) {

    if (summary.isOmitted()) {
        return bookService.keepSummary(id);
    }
    if (summary.value() == null) {
        return bookService.clearSummary(id);
    }
    return bookService.updateSummary(id, summary.value());
}
```

Không đặt default value cho argument nếu cần giữ được trạng thái omitted. Khi GraphQL áp dụng default, resolver sẽ nhận giá trị mặc định thay vì trạng thái client không gửi argument.

## 8. Xây dựng Delete mutation

Delete mutation có thể trả về boolean:

```graphql
type Mutation {
  deleteBook(id: ID!): Boolean!
}
```

```java
@MutationMapping
public boolean deleteBook(@Argument("id") String id) {
    return bookService.delete(id);
}
```

Tuy nhiên, boolean không cho biết bản ghi nào đã bị xóa hoặc có thể cung cấp metadata nào cho client. Với API lớn hơn, có thể trả về payload:

```graphql
type DeleteBookPayload {
  deletedBookId: ID!
  deleted: Boolean!
}

type Mutation {
  deleteBook(id: ID!): DeleteBookPayload!
}
```

Payload cho phép bổ sung thông tin trong tương lai mà không phải đổi kiểu trả về thành một scalar khác. Chọn kiểu trả về dựa trên nhu cầu client và hợp đồng API.

## 9. Thiết kế mutation payload

Trả trực tiếp object domain phù hợp với thao tác đơn giản. Khi client cần metadata, warning hoặc lỗi validation có cấu trúc, payload thường linh hoạt hơn.

```graphql
type UserError {
  code: String!
  field: String
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

Controller có thể trả payload:

```java
@MutationMapping
public CreateBookPayload createBook(
        @Argument("input") CreateBookInput input) {
    return bookService.createWithPayload(input);
}
```

Nên phân biệt hai nhóm tình huống:

- **Lỗi nghiệp vụ có thể dự đoán:** ví dụ title đã được sử dụng, trạng thái hiện tại không cho phép cập nhật. Có thể trả `userErrors` hoặc một result type rõ ràng để client hiển thị và xử lý.
- **Lỗi thực thi hoặc hạ tầng:** ví dụ database unavailable, lỗi lập trình hoặc dependency timeout. Những lỗi này thường đi qua GraphQL error handling và được trả trong mảng `errors`.

Không nên trả HTTP/GraphQL success với payload rỗng cho mọi lỗi. Client cần biết thao tác thành công, thất bại do validation hay thất bại do lỗi hệ thống.

## 10. Mutation và transaction

GraphQL quy định các top-level field trong một mutation operation được thực thi tuần tự theo thứ tự xuất hiện. Điều này giúp các mutation field trong cùng operation không chạy song song như các field thông thường của Query.

Ví dụ:

```graphql
mutation {
  createDraft(title: "GraphQL") {
    id
  }
  publishDraft(id: "draft-1") {
    id
    status
  }
}
```

Field `publishDraft` được thực thi sau `createDraft` trong cùng mutation operation. Tuy nhiên, việc thực thi tuần tự **không tự động tạo một transaction database bao trùm toàn bộ operation**. Nếu field đầu thành công và field sau thất bại, GraphQL không tự rollback side effect của field trước.

Đặt transaction tại service method:

```java
@Service
public class BookService {

    @Transactional
    public Book create(CreateBookInput input) {
        // Validate và ghi dữ liệu trong một transaction.
    }
}
```

Nếu một use case gồm nhiều thay đổi cần atomicity, hãy triển khai chúng trong cùng service method và cùng transaction thay vì dựa vào nhiều top-level mutation field. Transaction boundary nên phản ánh nghiệp vụ mà hệ thống cần bảo đảm.

## 11. Validation cho mutation input

GraphQL kiểm tra cấu trúc và kiểu dữ liệu của input. Ví dụ `title: String!` ngăn client bỏ qua hoặc gửi null, nhưng không tự ngăn chuỗi rỗng, chuỗi toàn khoảng trắng hoặc tiêu đề vượt quá giới hạn nghiệp vụ.

Validation nghiệp vụ nên được thực hiện ở server. Có thể dùng Bean Validation trên input DTO:

```java
public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotBlank
        String authorId,

        @Min(1)
        Integer publishedYear) {
}
```

Controller có thể kích hoạt validation cho argument bằng `@Valid` nếu ứng dụng đã cấu hình Jakarta Bean Validation:

```java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
```

Validation ở service vẫn cần thiết cho các quy tắc phụ thuộc trạng thái database, ví dụ author phải tồn tại, sách chưa được tạo trùng hoặc người dùng có quyền tạo sách trong thư viện đó. Không dựa vào validation ở client vì client có thể gửi request trực tiếp.

## 12. Xử lý lỗi từ mutation

Mutation có thể thất bại vì nhiều lý do:

- Input không hợp lệ.
- Tài nguyên không tồn tại.
- Vi phạm quy tắc nghiệp vụ.
- Người dùng không có quyền thực hiện.
- Lỗi database hoặc dịch vụ phụ thuộc.

Spring for GraphQL hỗ trợ cơ chế xử lý exception cho GraphQL, bao gồm `DataFetcherExceptionResolver` và `@GraphQlExceptionHandler` trong controller/advice. Có thể chuyển domain exception thành GraphQL error có message, classification hoặc extension phù hợp.

Ví dụ phân loại:

| Tình huống | Cách biểu diễn phù hợp |
| --- | --- |
| Thiếu title bắt buộc | GraphQL input coercion error hoặc validation error |
| Book không tồn tại | Nullable result, typed user error hoặc domain error theo contract |
| Người dùng không đủ quyền | Authorization error với thông tin không làm lộ dữ liệu |
| Database ngừng hoạt động | Execution error được log và ánh xạ an toàn |
| Xung đột phiên bản khi cập nhật | Conflict result/error có mã để client xử lý |

Không trả stack trace, SQL, connection string hoặc dữ liệu nội bộ trong error message gửi cho client. Log chi tiết ở server và trả thông báo an toàn, có correlation ID nếu cần.

## 13. Bảo mật mutation

Mutation thay đổi dữ liệu nên cần authorization rõ ràng. Việc client biết ID của resource không có nghĩa họ có quyền sửa hoặc xóa resource đó.

Có thể bảo vệ method bằng Spring Security:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_WRITE')")
public Book archiveBook(@Argument("id") String id) {
    return bookService.archive(id);
}
```

Tùy thiết kế ứng dụng, authorization cũng có thể đặt trong service để bảo đảm các luồng gọi khác ngoài GraphQL được bảo vệ. Với quyền phụ thuộc resource, cần kiểm tra quyền sở hữu hoặc tenant trong service/domain logic, không chỉ kiểm tra role chung.

Một số nguyên tắc:

- Xác thực người gọi trước khi xử lý thao tác nhạy cảm.
- Kiểm tra quyền trên chính resource được cập nhật hoặc xóa.
- Không tin `ownerId`, `tenantId` hoặc role do client gửi trong input.
- Không trả dữ liệu nhạy cảm trong payload hoặc error.
- Ghi audit event cho thao tác quan trọng.
- Xem xét rate limit và idempotency cho thao tác có thể được retry.

## 14. Idempotency và cập nhật đồng thời

Client có thể gửi lại mutation khi timeout hoặc mất kết nối, trong khi server đã thực hiện side effect. Nếu thao tác không idempotent, retry có thể tạo dữ liệu trùng hoặc thực hiện giao dịch nhiều lần.

Với thao tác tạo đơn hàng, thanh toán hoặc tạo resource quan trọng, cân nhắc một idempotency key:

```graphql
input CreateOrderInput {
  idempotencyKey: ID!
  productId: ID!
  quantity: Int!
}
```

Server lưu key cùng kết quả thao tác và trả lại kết quả cũ khi nhận request trùng key theo quy tắc nghiệp vụ. Idempotency cần được bảo đảm ở server/database; chỉ thêm field vào SDL là chưa đủ.

Với cập nhật đồng thời, có thể dùng version number hoặc optimistic locking:

```graphql
input UpdateBookInput {
  title: String
  expectedVersion: Int!
}
```

Service kiểm tra version hiện tại trước khi ghi. Nếu dữ liệu đã được người khác cập nhật, trả conflict để client tải lại trạng thái mới và quyết định cách tiếp tục.

## 15. Mutation và DataLoader cache

Trong cùng một GraphQL request, DataLoader có thể cache kết quả đã tải. Nếu mutation cập nhật một entity rồi response tiếp tục đọc entity hoặc quan hệ qua DataLoader, cache có thể còn giữ giá trị cũ.

Sau khi ghi dữ liệu, cân nhắc clear hoặc prime các key bị ảnh hưởng:

```java
Book updated = bookService.update(id, input);

dataLoader.clear(id).prime(id, updated);
return updated;
```

Đoạn code chỉ minh họa ý tưởng; cách inject DataLoader và kiểu key/value phải khớp với loader thực tế của ứng dụng. Chỉ invalidate những key liên quan và giữ cache trong phạm vi request. DataLoader không thay thế cache dùng chung hoặc cơ chế đồng bộ dữ liệu của hệ thống.

## 16. Kiểm thử MutationMapping bằng GraphQlTester

`GraphQlTester` cho phép kiểm thử mutation mà không cần gửi HTTP request thật. Với controller test slice, có thể dùng `@GraphQlTest` và mock service:

```java
@GraphQlTest(BookMutationController.class)
class BookMutationControllerTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockBean
    BookService bookService;

    @Test
    void createsBookFromInput() {
        Book created = new Book(
                "book-1",
                "Spring for GraphQL");

        given(bookService.create(any(CreateBookInput.class)))
                .willReturn(created);

        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        id
                        title
                    }
                }
                """)
                .variable("input", Map.of(
                        "title", "Spring for GraphQL",
                        "authorId", "author-1"))
                .execute()
                .path("createBook.id")
                .entity(String.class)
                .isEqualTo("book-1");

        then(bookService).should()
                .create(any(CreateBookInput.class));
    }
}
```

Đây là ví dụ minh họa; bổ sung constructor, field và kiểu dữ liệu đúng với model của dự án. Tùy phiên bản Spring Boot, annotation mock bean có thể là `@MockBean` hoặc `@MockitoBean`.

Nên có test cho các tình huống:

- Input hợp lệ và mutation trả kết quả mong đợi.
- Thiếu argument non-null hoặc sai kiểu input.
- Input vi phạm validation nghiệp vụ.
- Resource không tồn tại.
- Người dùng không đủ quyền.
- Xung đột version hoặc idempotency key trùng.
- Lỗi service được chuyển thành GraphQL error hoặc typed payload đúng contract.
- DataLoader cache được cập nhật nếu mutation thay đổi dữ liệu đã cache trong cùng request.

`@GraphQlTest` phù hợp để kiểm tra mapping và response của controller. Dùng integration test với database thật hoặc Testcontainers khi cần xác nhận transaction, constraint, optimistic locking và tính toàn vẹn dữ liệu.

## 17. Lỗi thường gặp khi dùng @MutationMapping

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Mutation field không gọi vào method | Controller không được scan hoặc method thiếu annotation | Kiểm tra `@Controller`, component scan và `@MutationMapping` |
| Field không tồn tại | SDL chưa khai báo field trong root `Mutation` | Bổ sung field vào SDL |
| Method không nhận đúng input | Tên argument hoặc kiểu Java không khớp | Dùng `@Argument("input")` và DTO tương thích |
| Resolver không được ánh xạ đúng tên | Method name khác SDL field name | Chỉ định `@MutationMapping(name = "...")` |
| Argument null dù nghĩ là có default | Client truyền null tường minh | Phân biệt omitted với null và kiểm tra operation variables |
| Partial update xóa dữ liệu ngoài ý muốn | Không phân biệt field bị bỏ qua và null | Dùng `ArgumentValue<T>` hoặc input model biểu diễn rõ trạng thái |
| Mutation thành công một phần | Dựa vào serial execution nhưng không có transaction bao trùm | Đưa use case atomic vào một service transaction |
| Retry tạo dữ liệu trùng | Mutation không có idempotency strategy | Dùng idempotency key và unique constraint phù hợp |
| Response trả dữ liệu cũ | DataLoader cache chưa được invalidate | Clear hoặc prime key liên quan sau mutation |
| Test không tìm thấy controller/configuration | Test slice thiếu controller hoặc bean phụ thuộc | Chỉ định controller, import configurer và mock service |

## 18. Nguyên tắc thiết kế mutation

- Đặt thao tác thay đổi dữ liệu trong root type `Mutation`.
- Dùng `@MutationMapping` cho mutation field và `@Argument` để bind input.
- Dùng input object cho mutation có nhiều dữ liệu hoặc có khả năng mở rộng.
- Dùng input DTO riêng, tránh bind trực tiếp persistence entity từ client.
- Trả object hoặc payload có cấu trúc phù hợp với nhu cầu client.
- Phân biệt lỗi nghiệp vụ có thể dự đoán với execution error.
- Đặt transaction boundary ở service/use case.
- Không giả định serial execution đồng nghĩa với database transaction.
- Phân biệt omitted, null và giá trị cụ thể trong partial update.
- Kiểm tra authorization trên resource và tenant thực tế.
- Thiết kế idempotency cho mutation có thể được retry.
- Xử lý optimistic locking khi nhiều client có thể cập nhật cùng dữ liệu.
- Cập nhật DataLoader cache trong cùng request nếu mutation làm thay đổi dữ liệu đã tải.
- Kiểm thử cả success path, validation, authorization và lỗi persistence.

## 19. Bài tập thực hành

Xây dựng mutation API cho ứng dụng thư viện:

1. Khai báo `CreateBookInput`, `UpdateBookInput` và root type `Mutation`.
2. Viết `BookMutationController` với `@MutationMapping` cho `createBook`, `updateBook` và `deleteBook`.
3. Dùng `@Argument` để bind input object sang Java record.
4. Chuyển logic persistence vào `BookService` và đặt transaction cho từng use case.
5. Thiết kế `CreateBookPayload` có `book` và `userErrors`.
6. Bổ sung validation cho title và author ID.
7. Thêm authorization cho thao tác archive hoặc delete.
8. Viết test `GraphQlTester` cho create, update, delete và validation failure.
9. Thử gửi hai mutation field trong cùng một operation và quan sát thứ tự thực thi.
10. Giải thích vì sao thứ tự mutation không tự bảo đảm rollback toàn bộ operation.

Khi hoàn thành, bạn cần biết cách ánh xạ một Mutation field vào method Java, bind input, lựa chọn payload, xử lý transaction và bảo vệ thao tác thay đổi dữ liệu trong Spring for GraphQL.

## 20. Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Specification — Execution](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)

Chữ ký method argument, validation integration và annotation hỗ trợ có thể thay đổi theo phiên bản Spring for GraphQL/Spring Boot. Khi nâng cấp dependency, hãy kiểm tra reference documentation và Javadoc đúng phiên bản đang được dự án sử dụng.
