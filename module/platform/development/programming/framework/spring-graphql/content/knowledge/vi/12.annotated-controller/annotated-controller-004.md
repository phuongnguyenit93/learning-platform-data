# `@MutationMapping` trong Spring for GraphQL

Mutation là operation dùng để thay đổi trạng thái của hệ thống, chẳng hạn tạo sách, cập nhật hồ sơ hoặc hủy đơn hàng. Trong Spring for GraphQL, annotation `@MutationMapping` liên kết một method trong controller với field tương ứng trên root type `Mutation` của GraphQL schema.

`@MutationMapping` giúp viết mutation resolver theo cách tự nhiên của Spring: nhận input qua `@Argument`, gọi service xử lý nghiệp vụ và trả kết quả để GraphQL tạo response. Để triển khai an toàn, cần thiết kế input/output rõ ràng, kiểm tra dữ liệu, áp dụng authorization và quản lý transaction ở đúng tầng.

## 1. Mutation dùng để làm gì?

GraphQL có ba nhóm operation chính:

- `Query`: đọc dữ liệu, không nên tạo side effect.
- `Mutation`: thay đổi trạng thái hoặc thực hiện hành động có side effect.
- `Subscription`: nhận các sự kiện được server phát ra theo thời gian.

Ví dụ trong ứng dụng quản lý sách:

| Nhu cầu | Operation phù hợp |
| --- | --- |
| Xem thông tin một cuốn sách | Query |
| Tạo sách mới | Mutation |
| Đổi tiêu đề sách | Mutation |
| Xóa sách | Mutation |
| Nhận thông báo khi có sách mới | Subscription |

Mutation được khai báo trên root object type có tên `Mutation`. Nếu schema có nhiều field mutation, client có thể chọn field cần thực thi trong một operation. Theo quy tắc GraphQL, các field cấp cao nhất của một mutation operation được thực thi tuần tự trong cùng operation; điều này không có nghĩa các HTTP request độc lập được server xử lý tuần tự toàn cục.

## 2. Khai báo Mutation trong GraphQL SDL

Trước tiên, khai báo các object type, input type và root `Mutation` trong file schema, ví dụ `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
    renameBook(id: ID!, title: String!): Book!
    deleteBook(id: ID!): Boolean!
}

input CreateBookInput {
    title: String!
    isbn: String!
}

type Book {
    id: ID!
    title: String!
    isbn: String!
}
```

Schema định nghĩa ba mutation:

- `createBook` nhận một input object và trả về sách vừa tạo.
- `renameBook` nhận ID và tiêu đề mới, sau đó trả về sách đã cập nhật.
- `deleteBook` nhận ID và trả về kết quả xóa dưới dạng Boolean.

`CreateBookInput` là input object vì client gửi dữ liệu vào server. `Book` là object type dùng cho output. GraphQL phân biệt input type và output type; không thể dùng trực tiếp một object type thông thường làm argument input.

## 3. Viết resolver với `@MutationMapping`

Tạo controller Spring và đánh dấu method xử lý mutation bằng `@MutationMapping`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

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

    @MutationMapping
    public Book renameBook(
            @Argument("id") String id,
            @Argument("title") String title) {
        return bookService.rename(id, title);
    }

    @MutationMapping
    public Boolean deleteBook(@Argument("id") String id) {
        return bookService.delete(id);
    }
}
```

Spring for GraphQL phát hiện controller và đăng ký các method này làm data fetcher cho root type `Mutation`. Tên method mặc định được dùng để xác định tên field. Vì vậy `createBook` ánh xạ tới `Mutation.createBook`, `renameBook` ánh xạ tới `Mutation.renameBook`, và `deleteBook` ánh xạ tới `Mutation.deleteBook`.

`@Argument("input")` lấy giá trị argument có tên `input` từ GraphQL request. Có thể chỉ rõ tên argument như ví dụ để mapping không phụ thuộc vào việc Java compiler có giữ metadata tên tham số hay không.

`@MutationMapping` là cách viết chuyên biệt cho field thuộc root `Mutation`, tương tự cách `@QueryMapping` dùng cho root `Query`. Về bản chất, nó là dạng rút gọn của `@SchemaMapping(typeName = "Mutation")`.

## 4. Ánh xạ input object sang Java record

Input object trong SDL có thể được bind vào Java record hoặc class có thuộc tính tương ứng:

```java
public record CreateBookInput(String title, String isbn) {
}
```

Khi client gửi:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
    }
}
```

Variables JSON:

```json
{
  "input": {
    "title": "Spring for GraphQL",
    "isbn": "9780000000001"
  }
}
```

Spring for GraphQL chuyển input thành `CreateBookInput` rồi truyền vào method controller. Tên field và kiểu dữ liệu trong input object cần tương thích với thuộc tính Java. Với input lồng nhau, có thể dùng record lồng nhau hoặc class tương ứng để giữ cấu trúc dữ liệu rõ ràng.

Nên dùng input object khi mutation có nhiều tham số liên quan. Cách này làm schema dễ đọc, dễ mở rộng và tránh một field mutation có quá nhiều argument rời rạc. Khi bổ sung field mới, cần cân nhắc nullability và default để không vô tình phá vỡ client hiện tại.

## 5. Thiết kế kiểu trả về cho Mutation

Mutation có thể trả trực tiếp object đã tạo hoặc cập nhật:

```graphql
type Mutation {
    createBook(input: CreateBookInput!): Book!
}
```

Đây là cách đơn giản khi thao tác thành công sẽ luôn trả về một `Book`. Với API lớn hơn, có thể dùng payload type để chứa object cùng metadata hoặc lỗi nghiệp vụ có thể dự đoán:

```graphql
type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type UserError {
    field: String
    message: String!
    code: String
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}
```

Payload cho phép API biểu diễn kết quả nghiệp vụ theo cấu trúc ổn định, ví dụ trả về danh sách lỗi validation mà client có thể hiển thị cạnh form. Khi dùng kiểu này, controller cần trả `CreateBookPayload` thay vì `Book` trực tiếp.

Hãy phân biệt lỗi nghiệp vụ dự kiến với lỗi hệ thống. Ví dụ tiêu đề trùng có thể là lỗi nghiệp vụ mà payload trả về `userErrors`; database không khả dụng hoặc lỗi lập trình thường cần được xử lý thành GraphQL execution error theo chính sách của server.

## 6. Gửi mutation qua HTTP

Client thường gửi mutation bằng HTTP POST đến GraphQL endpoint. Ví dụ endpoint mặc định là `/graphql`:

```bash
curl http://localhost:8080/graphql \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{
    "query": "mutation CreateBook($input: CreateBookInput!) { createBook(input: $input) { id title isbn } }",
    "variables": {
      "input": {
        "title": "Spring for GraphQL",
        "isbn": "9780000000001"
      }
    },
    "operationName": "CreateBook"
  }'
```

Response mẫu khi tạo thành công:

```json
{
  "data": {
    "createBook": {
      "id": "book-101",
      "title": "Spring for GraphQL",
      "isbn": "9780000000001"
    }
  }
}
```

Dùng GraphQL variables giúp client tái sử dụng document và truyền dữ liệu riêng qua JSON. Không nên ghép input từ chuỗi người dùng vào query document vì dễ tạo lỗi escape và khó kiểm soát kiểu dữ liệu.

GraphQL over HTTP không cho phép thực thi mutation bằng HTTP GET. Hãy dùng POST cho mutation và cấu hình client đúng với endpoint của ứng dụng.

## 7. Validation cho dữ liệu mutation

SDL kiểm tra kiểu GraphQL, nhưng không tự kiểm tra toàn bộ quy tắc nghiệp vụ. Ví dụ `title: String!` không chấp nhận null nhưng vẫn có thể nhận chuỗi rỗng. Có thể dùng Jakarta Bean Validation để kiểm tra input trước khi gọi service.

Khai báo input record:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CreateBookInput(
        @NotBlank String title,
        @NotBlank
        @Pattern(regexp = "[0-9Xx-]{10,17}") String isbn) {
}
```

Áp dụng `@Valid` ở tham số resolver:

```java
import jakarta.validation.Valid;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(@Valid @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

Để Bean Validation hoạt động, ứng dụng cần có implementation tương ứng, thường là `spring-boot-starter-validation`. Quy tắc regex trong ví dụ chỉ là kiểm tra hình dạng sơ bộ, không thay thế thuật toán kiểm tra checksum ISBN hoặc quy tắc domain đầy đủ.

Validation nên được thực hiện ở tầng phù hợp. Kiểm tra định dạng input có thể dùng Bean Validation; kiểm tra tính duy nhất của ISBN hoặc quyền sở hữu dữ liệu cần được bảo đảm ở service/domain và database. Không dựa vào client để tự kiểm tra các điều kiện này.

## 8. Xử lý lỗi trong Mutation

Khi mutation thất bại, GraphQL response có thể chứa `data` và `errors`. Nếu lỗi xảy ra trong một field mutation, GraphQL có thể trả null cho field đó và đưa thông tin lỗi vào mảng `errors`; kết quả cuối cùng còn phụ thuộc nullability trong SDL và vị trí lỗi.

Ví dụ response minh họa:

```json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "ISBN đã tồn tại",
      "path": ["createBook"]
    }
  ]
}
```

Đây là ví dụ về cấu trúc, không phải message cố định của Spring. Nếu `createBook` được khai báo `Book!`, lỗi khiến field không thể hoàn tất có thể lan truyền null lên cấp cha theo quy tắc Non-Null. Nếu muốn trả lỗi nghiệp vụ mà không làm mất toàn bộ field, cân nhắc payload type với `userErrors`.

Spring for GraphQL hỗ trợ xử lý exception bằng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice`, cũng như `DataFetcherExceptionResolver` ở tầng GraphQL execution. Ví dụ khái quát:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GraphQlErrorAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleBookNotFound(BookNotFoundException exception) {
        return GraphqlErrorBuilder.newError()
                .errorType(ErrorType.NOT_FOUND)
                .message("Không tìm thấy sách")
                .build();
    }
}
```

Trong ứng dụng thực tế, hãy tạo `GraphQLError` có message và classification phù hợp với API; ví dụ trên dùng `@ControllerAdvice` để xử lý exception cho các controller liên quan. Có thể bổ sung extension code nếu client cần phân loại lỗi. Không đưa stack trace, SQL, token hoặc dữ liệu nội bộ vào response cho client.

## 9. Transaction và tính nhất quán dữ liệu

Mutation thường ghi dữ liệu, vì vậy transaction nên được quản lý ở service hoặc tầng domain phù hợp. Ví dụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {

    private final BookRepository bookRepository;

    public BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @Transactional
    public Book create(CreateBookInput input) {
        if (bookRepository.existsByIsbn(input.isbn())) {
            throw new DuplicateIsbnException(input.isbn());
        }

        BookEntity entity = new BookEntity(input.title(), input.isbn());
        BookEntity saved = bookRepository.save(entity);
        return new Book(saved.getId().toString(), saved.getTitle(), saved.getIsbn());
    }
}
```

Ví dụ giả định `BookRepository`, `BookEntity`, `Book` và `DuplicateIsbnException` là các kiểu của ứng dụng. Kiểm tra trùng trước khi ghi giúp đưa ra lỗi dễ hiểu, nhưng vẫn cần unique constraint ở database để xử lý trường hợp hai request đồng thời cùng tạo một ISBN. Transaction không tự thay thế ràng buộc toàn vẹn dữ liệu.

Đặt `@Transactional` ở service giúp transaction bao trọn thao tác nghiệp vụ và có thể tái sử dụng từ các entry point khác. Không nên phụ thuộc vào transaction chỉ ở controller nếu service còn được gọi từ nơi khác.

## 10. Bảo mật mutation

Mutation có thể tạo, sửa hoặc xóa dữ liệu nên cần authorization rõ ràng:

- Xác thực danh tính người gọi bằng cơ chế bảo mật của ứng dụng.
- Kiểm tra người dùng có quyền thực hiện hành động hay không.
- Kiểm tra quyền trên tài nguyên cụ thể, ví dụ người dùng chỉ được sửa sách thuộc phạm vi quản lý.
- Không tin `userId`, `ownerId` hoặc vai trò do client tự gửi trong input; lấy danh tính từ security context đã xác thực.
- Ghi audit log cho các hành động quan trọng theo yêu cầu nghiệp vụ.
- Với mutation nhạy cảm, cân nhắc idempotency key để tránh tạo tác dụng phụ lặp lại khi client retry request.

Có thể dùng Spring Security method security như `@PreAuthorize` ở controller hoặc service. Ví dụ:

```java
@PreAuthorize("hasAuthority('BOOK_WRITE')")
@Transactional
public Book create(CreateBookInput input) {
    // Kiểm tra domain và lưu dữ liệu.
}
```

Đoạn ví dụ giả định method security đã được bật và authority được cấp qua cấu hình bảo mật. Kiểm tra quyền sở hữu tài nguyên vẫn cần được thực hiện trong service/domain vì quyền `BOOK_WRITE` chung có thể chưa đủ để cho phép sửa mọi bản ghi.

## 11. Mutation và tính idempotent

Một mutation tạo mới thường không idempotent: gửi cùng request hai lần có thể tạo hai bản ghi. Client có thể retry khi timeout mà không biết server đã commit thao tác trước đó hay chưa.

Với thao tác có nguy cơ gây tác dụng phụ lặp lại, như tạo đơn hàng hoặc thanh toán, có thể thiết kế `idempotencyKey` trong input:

```graphql
input CreateOrderInput {
    idempotencyKey: String!
    productId: ID!
    quantity: Int!
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
}
```

Service cần lưu key cùng kết quả thao tác và bảo đảm key có unique constraint trong phạm vi phù hợp. Nếu nhận lại cùng key, service trả kết quả đã ghi nhận thay vì tạo side effect mới. Chỉ thêm cơ chế này khi nghiệp vụ cần bảo vệ trước retry hoặc request trùng; GraphQL không tự cung cấp idempotency cho mutation.

## 12. Kiểm thử `@MutationMapping` bằng GraphQlTester

`GraphQlTester` cho phép gửi GraphQL document trong test và kiểm tra response. Ví dụ kiểm thử tạo sách:

```java
@Test
void createBookReturnsSavedBook() {
    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    id
                    title
                    isbn
                }
            }
            """)
        .variable("input", java.util.Map.of(
                "title", "Spring for GraphQL",
                "isbn", "9780000000001"))
        .execute()
        .path("createBook.title")
        .entity(String.class)
        .isEqualTo("Spring for GraphQL");
}
```

Test này giả định `graphQlTester` đã được cấu hình trong test context và service/repository trả về dữ liệu có thể dự đoán. Nên cô lập database hoặc dùng fixture để test có thể chạy lặp lại.

Ngoài trường hợp thành công, cần kiểm thử:

1. Input thiếu field Non-Null hoặc truyền null bị GraphQL từ chối trước khi gọi resolver.
2. Input sai định dạng hoặc vi phạm Bean Validation tạo lỗi phù hợp.
3. ISBN trùng được xử lý theo quy tắc nghiệp vụ.
4. Người dùng không có quyền không thể tạo, sửa hoặc xóa sách.
5. Không tìm thấy ID khi rename/delete được trả về theo contract đã chọn.
6. Lỗi trong transaction không để lại dữ liệu ghi dở.
7. Mutation trả đúng payload, `data` và `errors` theo schema.
8. Nếu có idempotency key, request retry không tạo side effect lần thứ hai.

Nếu cần xác minh cả HTTP transport, dùng `HttpGraphQlTester` hoặc `WebTestClient` để gửi request qua endpoint thực tế. `GraphQlTester` ở tầng execution phù hợp để kiểm tra schema và resolver nhưng không nhất thiết kiểm tra toàn bộ HTTP stack.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Mutation không được gọi | Tên method không khớp field trong root `Mutation` hoặc annotation đặt sai | Kiểm tra tên field SDL và `@MutationMapping`. |
| Argument nhận null | Tên trong `@Argument` không khớp tên argument hoặc input field | Chỉ rõ `@Argument("...")` và kiểm tra SDL. |
| Không bind được input object | Java record/class không tương thích field hoặc kiểu | Đồng bộ tên và kiểu giữa SDL với Java input. |
| Mutation trả lỗi Non-Null | Resolver trả null trong khi field khai báo `!` | Điều chỉnh service hoặc thiết kế nullability/payload phù hợp. |
| Validation không chạy | Thiếu Bean Validation implementation hoặc chưa đặt `@Valid` | Thêm starter validation và kiểm tra method argument. |
| Dữ liệu ghi một phần | Transaction không bao trọn nghiệp vụ hoặc có side effect ngoài transaction | Đặt transaction ở service và thiết kế xử lý side effect phù hợp. |
| Tạo bản ghi trùng khi retry | Mutation không có cơ chế idempotency | Dùng idempotency key cho thao tác cần chống lặp. |
| Người dùng sửa được dữ liệu của người khác | Chỉ kiểm tra đăng nhập mà thiếu authorization trên tài nguyên | Kiểm tra quyền và ownership ở service/domain. |

## 14. Checklist triển khai Mutation

1. Khai báo field trên root `Mutation` và dùng input object cho dữ liệu có cấu trúc.
2. Tạo method controller với `@MutationMapping` và ánh xạ argument bằng `@Argument`.
3. Giữ controller mỏng; đưa nghiệp vụ vào service.
4. Chọn kiểu trả về trực tiếp hoặc payload theo cách client cần xử lý lỗi nghiệp vụ.
5. Dùng Bean Validation và kiểm tra quy tắc domain trước khi ghi dữ liệu.
6. Quản lý transaction ở service và dùng constraint database cho tính toàn vẹn.
7. Áp dụng authentication, authorization và kiểm tra quyền trên tài nguyên.
8. Cân nhắc idempotency cho thao tác có side effect quan trọng.
9. Kiểm thử trường hợp thành công, lỗi input, lỗi nghiệp vụ, quyền truy cập và retry.
10. Dùng HTTP POST cho mutation và để client đọc cả `data` lẫn `errors`.

`@MutationMapping` giúp kết nối một method Spring controller với hành động thay đổi dữ liệu trong GraphQL schema. Khi input, output, validation, transaction và authorization được thiết kế rõ ràng, mutation sẽ tạo ra một API dễ dùng cho client và giữ được tính nhất quán của hệ thống.
