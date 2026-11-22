# Mutation trả về payload object

Một mutation thường cần trả về nhiều thông tin sau khi server xử lý một thao tác: tài nguyên vừa tạo hoặc cập nhật, lỗi nghiệp vụ có thể sửa, trạng thái của thao tác và thông tin liên quan để client tiếp tục làm việc. Nếu mutation chỉ trả về một object domain, hợp đồng đầu ra có thể trở nên hạn chế khi use case phát triển.

GraphQL cho phép mutation trả về một **payload object** do ứng dụng thiết kế. Payload là object type mô tả kết quả của một thao tác cụ thể. Nó có thể chứa tài nguyên đã thay đổi, danh sách lỗi nghiệp vụ, metadata hoặc thông tin tương quan. Trong Spring for GraphQL, handler được ánh xạ bằng **@MutationMapping**, nhận input qua **@Argument** và trả về DTO/record tương ứng với payload type trong SDL.

Bài này tập trung vào cách thiết kế payload cho mutation, cách chọn nullability, cách biểu diễn lỗi nghiệp vụ và phân biệt chúng với GraphQL execution errors, cách triển khai trong Spring for GraphQL, cùng cách kiểm thử response thành công và thất bại.

## 1. Payload object giải quyết vấn đề gì?

Một mutation có thể trả trực tiếp object vừa tạo:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Client nhận được Book và chọn các field cần thiết:

~~~graphql
mutation {
  createBook(input: {
    title: "Spring GraphQL"
    authorId: "author-01"
  }) {
    id
    title
  }
}
~~~

Thiết kế này đơn giản và phù hợp nếu thao tác luôn thành công hoặc lỗi được biểu diễn hoàn toàn qua GraphQL errors. Nhưng khi client cần nhận cả object lẫn lỗi nghiệp vụ có thể xử lý, trả về riêng **Book** không đủ chỗ để biểu diễn cả hai.

Có thể tạo payload riêng:

~~~graphql
type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Payload cho phép response có cấu trúc rõ ràng:

- Thành công: **book** có giá trị, **userErrors** rỗng.
- Thất bại do dữ liệu hoặc quy tắc nghiệp vụ: **book** là null, **userErrors** chứa thông tin lỗi có thể hiển thị hoặc xử lý.

Đây là một pattern thiết kế API, không phải yêu cầu bắt buộc của GraphQL. Với thao tác đơn giản, trả trực tiếp object vẫn hợp lý. Hãy dùng payload khi mutation thực sự cần nhiều phần kết quả có liên quan.

## 2. Định nghĩa payload trong SDL

Ví dụ một mutation tạo sách:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}

input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Các thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| **CreateBookInput** | Dữ liệu client gửi để tạo sách |
| **CreateBookPayload** | Kết quả của thao tác tạo sách |
| **Book** | Tài nguyên được tạo |
| **UserError** | Lỗi nghiệp vụ có thể trả về như một phần kết quả |
| **clientMutationId** | Giá trị tương quan do client gửi và server echo lại nếu API chọn hỗ trợ |

Tên payload thường gắn với mutation, ví dụ **CreateBookPayload**, **UpdateBookPayload** hoặc **ArchiveBookPayload**. Cách đặt tên này giúp client hiểu object biểu diễn kết quả của hành động nào.

### Vì sao payload có thể chứa Book nullable?

Field **book** được khai báo là **Book**, có thể null. Nếu **book** là **Book!**, server không thể trả null khi thao tác thất bại do validation. Khi payload pattern dùng **userErrors** để mô tả thất bại nghiệp vụ, field tài nguyên thường cần nullable.

Ngược lại, **userErrors: [UserError!]!** cam kết server luôn trả về một danh sách lỗi khác null và từng phần tử trong danh sách cũng khác null. Khi thành công, danh sách là **[]**.

Quy tắc này giúp client xử lý response nhất quán:

- Payload luôn tồn tại vì mutation trả **CreateBookPayload!**.
- Danh sách lỗi luôn đọc được.
- Tài nguyên chỉ tồn tại khi thao tác tạo thành công.

## 3. Response khi thành công và khi có lỗi nghiệp vụ

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    book {
      id
      title
      status
    }
    userErrors {
      code
      message
      field
    }
    clientMutationId
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "Spring GraphQL",
    "authorId": "author-01",
    "clientMutationId": "create-book-form-7"
  }
}
~~~

Response thành công:

~~~json
{
  "data": {
    "createBook": {
      "book": {
        "id": "book-101",
        "title": "Spring GraphQL",
        "status": "DRAFT"
      },
      "userErrors": [],
      "clientMutationId": "create-book-form-7"
    }
  }
}
~~~

Response khi tác giả không tồn tại:

~~~json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "code": "AUTHOR_NOT_FOUND",
          "message": "Không tìm thấy tác giả được chọn",
          "field": ["authorId"]
        }
      ],
      "clientMutationId": "create-book-form-7"
    }
  }
}
~~~

Trong trường hợp thứ hai, operation vẫn được thực thi thành công ở cấp GraphQL. Nghiệp vụ không tạo được sách, nhưng client nhận payload hợp lệ và có thể hiển thị lỗi cạnh field tương ứng.

## 4. Phân biệt userErrors với GraphQL errors

Đây là một quyết định quan trọng khi thiết kế mutation.

**Payload userErrors** phù hợp với lỗi nghiệp vụ dự kiến mà client có thể xử lý như một phần kết quả, ví dụ:

- Tên sách đã được sử dụng.
- Tác giả không tồn tại hoặc không thể chọn.
- Trạng thái hiện tại không cho phép cập nhật.
- Dữ liệu không thỏa mãn quy tắc nghiệp vụ.

**GraphQL top-level errors** phù hợp với lỗi của operation hoặc lỗi thực thi, ví dụ:

- Query/mutation sai cú pháp hoặc không qua schema validation.
- Thiếu argument non-null hoặc truyền sai kiểu.
- Scalar/enum variable không thể coercion.
- Người dùng không được phép thực hiện operation theo chính sách bảo mật.
- Hạ tầng hoặc dependency gặp lỗi ngoài dự kiến.
- Resolver phát sinh exception không được chuyển thành lỗi nghiệp vụ trong payload.

Ví dụ, nếu client truyền enum không tồn tại, GraphQL có thể từ chối variables trước khi gọi handler. Khi đó không có payload do mutation resolver chưa chạy.

Không nên bắt mọi exception rồi nhét vào **userErrors**. Làm vậy sẽ biến lỗi lập trình, lỗi database hoặc lỗi hệ thống thành lỗi nghiệp vụ giả, khiến monitoring và client khó phân biệt tình trạng thực tế.

Một response có thể có **data** và top-level **errors** cùng lúc tùy vị trí lỗi và nullability. Payload pattern không thay thế quy tắc error propagation của GraphQL.

## 5. Thiết kế UserError hữu ích cho client

Một kiểu lỗi nên có mã ổn định, thông điệp dễ hiểu và đường dẫn tới field liên quan:

~~~graphql
type UserError {
  code: String!
  message: String!
  field: [String!]!
}
~~~

Ý nghĩa:

- **code**: mã máy đọc được để client quyết định hành vi.
- **message**: nội dung có thể hiển thị hoặc dùng làm thông tin giải thích.
- **field**: đường dẫn tới field input có liên quan; danh sách cho phép chỉ ra field lồng nhau.

Ví dụ lỗi cho input lồng:

~~~json
{
  "code": "INVALID_QUANTITY",
  "message": "Số lượng phải lớn hơn 0",
  "field": ["lines", "1", "quantity"]
}
~~~

Client có thể dùng **field** để đưa thông báo cạnh input tương ứng. Nếu lỗi không gắn với một field cụ thể, có thể trả danh sách rỗng.

### Dùng enum cho error code khi tập lỗi ổn định

Nếu API có tập mã lỗi hữu hạn và được quản lý trong schema, có thể dùng enum:

~~~graphql
enum CreateBookErrorCode {
  TITLE_ALREADY_EXISTS
  AUTHOR_NOT_FOUND
  INVALID_STATUS
}

type CreateBookUserError {
  code: CreateBookErrorCode!
  message: String!
  field: [String!]!
}
~~~

Enum giúp client sinh code an toàn kiểu hơn, nhưng mỗi lần thêm mã lỗi là một thay đổi schema. Nếu mã lỗi có thể mở rộng độc lập hoặc đến từ nhiều domain, **String!** linh hoạt hơn. Hãy chọn theo mức độ ổn định của contract.

Thông điệp lỗi không nên chứa SQL, stack trace, token, thông tin nội bộ hoặc dữ liệu của người dùng khác. Nếu cần chi tiết điều tra, ghi log phía server với correlation ID.

## 6. Khi nào trả trực tiếp object, khi nào dùng payload?

Không cần tạo payload cho mọi mutation. Có thể so sánh:

| Tiêu chí | Trả object trực tiếp | Trả payload object |
|---|---|---|
| Cấu trúc | Gọn, chỉ có tài nguyên | Có thể chứa tài nguyên, lỗi và metadata |
| Use case đơn giản | Phù hợp | Có thể dư thừa |
| Validation error có cấu trúc | Thường dùng top-level GraphQL error | Có thể trả trong **userErrors** |
| Metadata của thao tác | Không có vị trí riêng | Có field riêng |
| Mở rộng contract | Thay đổi kiểu trả về có thể ảnh hưởng client | Có thể thêm field payload theo chiến lược tương thích |
| Tên type | Dùng object domain | Thường có payload type riêng cho mutation |

Trả object trực tiếp phù hợp khi:

- Mutation có kết quả đơn giản.
- Client chỉ cần tài nguyên được tạo/cập nhật.
- Không có nhu cầu biểu diễn lỗi nghiệp vụ trong response data.
- Top-level GraphQL errors đã đáp ứng tốt contract.

Payload phù hợp khi:

- Client cần nhận nhiều loại kết quả sau thao tác.
- Có lỗi nghiệp vụ dự kiến cần gắn với field input.
- Cần trả metadata như trạng thái xử lý, cảnh báo hoặc thông tin tương quan.
- Nhiều client cần một response contract rõ ràng và ổn định.

Không nên thêm các field như **success**, **message** và **data** một cách máy móc vào mọi payload. Hãy để cấu trúc phản ánh kết quả nghiệp vụ cụ thể.

## 7. Triển khai payload bằng Spring for GraphQL

Giả sử schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  status: String!
}

type UserError {
  code: String!
  message: String!
  field: [String!]!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}

type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
}
~~~

Java record cho input và payload:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        String clientMutationId) {
}

public record UserError(
        String code,
        String message,
        List<String> field) {
}

public record CreateBookPayload(
        Book book,
        List<UserError> userErrors,
        String clientMutationId) {
}
~~~

Handler:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public CreateBookPayload createBook(
            @Argument("input") CreateBookInput input) {

        CreateBookResult result = bookService.create(input);

        return new CreateBookPayload(
                result.book(),
                result.userErrors(),
                input.clientMutationId());
    }
}
~~~

**@MutationMapping** ánh xạ method vào field **Mutation.createBook**. **@Argument("input")** bind input object thành **CreateBookInput**. Kết quả Java được GraphQL Java đọc theo field của **CreateBookPayload**.

Với Java record, tên component nên khớp với field trong SDL để property data fetcher có thể đọc giá trị tương ứng. Nếu dùng DTO thông thường, có thể dùng getter theo quy ước JavaBean.

## 8. Đặt validation và transaction ở đúng lớp

Payload thường biểu diễn lỗi nghiệp vụ dự kiến. Service nên kiểm tra các điều kiện trước khi ghi dữ liệu:

~~~java
public record CreateBookResult(
        Book book,
        List<UserError> userErrors) {
}
~~~

~~~java
@Service
public class BookService {

    private final BookRepository bookRepository;
    private final AuthorRepository authorRepository;

    public BookService(
            BookRepository bookRepository,
            AuthorRepository authorRepository) {
        this.bookRepository = bookRepository;
        this.authorRepository = authorRepository;
    }

    @Transactional
    public CreateBookResult create(CreateBookInput input) {
        List<UserError> errors = new ArrayList<>();

        if (bookRepository.existsByTitleIgnoreCase(input.title())) {
            errors.add(new UserError(
                    "TITLE_ALREADY_EXISTS",
                    "Tên sách đã được sử dụng",
                    List.of("title")));
        }

        if (!authorRepository.existsById(input.authorId())) {
            errors.add(new UserError(
                    "AUTHOR_NOT_FOUND",
                    "Không tìm thấy tác giả được chọn",
                    List.of("authorId")));
        }

        if (!errors.isEmpty()) {
            return new CreateBookResult(null, errors);
        }

        Author author = authorRepository.findById(input.authorId())
                .orElseThrow();

        Book book = Book.create(input.title(), author);
        Book saved = bookRepository.save(book);

        return new CreateBookResult(saved, List.of());
    }
}
~~~

Trong ví dụ, tất cả kiểm tra nghiệp vụ được thực hiện trước khi ghi sách. Nếu có lỗi, service trả kết quả thất bại và không tạo dữ liệu. Nếu hợp lệ, thao tác lưu diễn ra trong transaction.

### Không nuốt lỗi persistence để trả payload thành công giả

Kiểm tra trước khi ghi không loại bỏ mọi race condition. Ví dụ, hai request đồng thời có thể cùng vượt qua kiểm tra tên chưa tồn tại; unique constraint trong database chỉ cho một request thành công.

Nếu database ném exception trong lúc ghi, không nên bắt exception tùy tiện bên trong transaction rồi trả **userErrors** như thể transaction đã hoàn tất bình thường. Transaction có thể đã bị đánh dấu rollback-only hoặc đang ở trạng thái không an toàn.

Với lỗi cạnh tranh dữ liệu đã biết, hãy thiết kế một ranh giới xử lý transaction rõ ràng: để transaction rollback, sau đó chuyển lỗi đã nhận diện thành kết quả nghiệp vụ ở một lớp phù hợp nếu API yêu cầu. Với lỗi hạ tầng không dự kiến, để exception đi qua GraphQL error handling và ghi log.

### Bean Validation và payload errors

Schema kiểm tra kiểu, field bắt buộc và input coercion. Bean Validation có thể kiểm tra các constraint như **@NotBlank**, **@Size** hoặc **@Min**. Tuy nhiên, lỗi validation từ **@Valid** có thể được xử lý thành GraphQL error tùy cấu hình và cơ chế exception handling.

Nếu API muốn tất cả lỗi validation có thể sửa được xuất hiện trong **userErrors**, cần chủ động chuyển các constraint violations thành danh sách **UserError** theo contract. Không nên cho rằng chỉ thêm **@Valid** là Spring tự điền field **userErrors**.

Có thể dùng một validator ở application layer để trả danh sách lỗi có cấu trúc, sau đó handler đóng gói thành payload. Các quy tắc cần truy vấn database hoặc kiểm tra quyền vẫn nên nằm trong service.

## 9. Payload cho update và delete mutation

Payload không chỉ dùng cho thao tác tạo mới. Update có thể trả object đã cập nhật và lỗi nghiệp vụ:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
}

type UpdateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type Mutation {
  updateBook(input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Delete có thể trả tài nguyên đã xóa hoặc định danh cùng trạng thái:

~~~graphql
type DeleteBookPayload {
  deletedBookId: ID
  userErrors: [UserError!]!
}

type Mutation {
  deleteBook(id: ID!): DeleteBookPayload!
}
~~~

Với delete, không nhất thiết trả toàn bộ Book nếu client chỉ cần biết ID đã xóa. Hãy trả dữ liệu đủ để client cập nhật cache hoặc giao diện.

Một payload khác nhau cho từng mutation giúp contract thể hiện đúng use case. Không nên dùng chung một **MutationPayload** chứa hàng chục field nullable cho mọi thao tác nếu phần lớn field không có ý nghĩa với từng mutation.

## 10. Payload có thể chứa nhiều object liên quan

Một thao tác nghiệp vụ có thể thay đổi nhiều tài nguyên. Ví dụ đặt đơn hàng có thể trả về đơn hàng và thông tin thanh toán được tạo:

~~~graphql
type OrderPayload {
  order: Order
  payment: Payment
  userErrors: [UserError!]!
}

type Mutation {
  placeOrder(input: PlaceOrderInput!): OrderPayload!
}
~~~

Client có thể chọn đúng phần dữ liệu cần:

~~~graphql
mutation PlaceOrder($input: PlaceOrderInput!) {
  placeOrder(input: $input) {
    order {
      id
      status
      total
    }
    payment {
      id
      status
    }
    userErrors {
      code
      message
      field
    }
  }
}
~~~

Payload chỉ mô tả response shape. Nó không bảo đảm các thao tác tạo Order và Payment đã được commit nguyên tử. Tính nhất quán phải được thiết kế trong application/service layer bằng transaction hoặc cơ chế phân tán phù hợp.

Nếu payment được xử lý bất đồng bộ, payload nên thể hiện trạng thái thật, ví dụ **PENDING**, thay vì giả định thanh toán đã hoàn tất chỉ vì đã tạo order.

## 11. clientMutationId, correlation và idempotency

Một số API thêm **clientMutationId** vào input và payload:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  clientMutationId: String
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}
~~~

Giá trị này cho phép client ghép response với thao tác đã gửi, hữu ích khi có nhiều mutation đang chờ hoặc UI cần tương quan request.

Tuy nhiên, **clientMutationId không tự bảo đảm idempotency**. Nếu client gửi lại cùng mutation sau timeout, server có thể tạo hai tài nguyên nếu không có cơ chế chống trùng.

Nếu cần retry an toàn, hãy thiết kế idempotency key riêng:

- Client gửi key ổn định cho một ý định nghiệp vụ.
- Server lưu key cùng kết quả hoặc trạng thái xử lý.
- Request lặp lại với cùng key được nhận diện và không thực hiện side effect lần nữa.
- Key phải được ràng buộc với người dùng/tenant và phạm vi thao tác phù hợp.

Correlation ID giúp theo dõi request; idempotency key kiểm soát tác động lặp. Hai khái niệm có thể cùng tồn tại nhưng không nên dùng thay thế nhau.

## 12. Nullability của payload và khả năng tiến hóa schema

Nullability cần phản ánh các trạng thái hợp lệ:

~~~graphql
type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
  clientMutationId: String
}
~~~

Lựa chọn này có ý nghĩa:

- Payload non-null vì mutation luôn trả về cấu trúc kết quả nếu resolver hoàn thành bình thường.
- Book nullable vì thao tác có thể thất bại do lỗi nghiệp vụ.
- **userErrors** non-null list để client luôn nhận danh sách, kể cả danh sách rỗng.
- **clientMutationId** nullable vì client có thể không gửi.

Nếu đổi **book** thành **Book!**, payload không còn biểu diễn được thất bại nghiệp vụ theo cách **book: null**. Nếu đổi **userErrors** thành nullable, client phải xử lý thêm trạng thái danh sách lỗi không tồn tại.

Khi tiến hóa payload:

- Thêm field nullable thường dễ tương thích hơn với client cũ.
- Thêm field non-null đòi hỏi server luôn cung cấp giá trị và có thể thay đổi contract đáng kể.
- Đổi tên hoặc xóa field có thể làm operation cũ không hợp lệ.
- Thay đổi cấu trúc **UserError** ảnh hưởng mọi client đang đọc lỗi.

Nên thêm field mới có chủ đích, giữ field cũ trong giai đoạn chuyển đổi nếu cần và dùng **@deprecated** để thông báo thay thế.

## 13. Bảo mật khi trả payload

Payload là dữ liệu gửi ra client. Không nên đưa toàn bộ exception, entity nội bộ hoặc thông tin nhạy cảm vào payload chỉ vì muốn response giàu thông tin.

Một số nguyên tắc:

- Chỉ trả field mà client được phép đọc.
- Kiểm tra quyền trên tài nguyên được tạo/cập nhật trước khi đưa vào payload.
- Không trả SQL, stack trace, đường dẫn nội bộ hoặc thông tin xác thực trong **userErrors**.
- Không tin **ownerId**, **tenantId** hoặc role do client gửi nếu server phải quyết định.
- Dùng error code ổn định thay vì buộc client phân tích chuỗi message.
- Không đưa dữ liệu nhạy cảm vào **clientMutationId** hoặc log request.
- Giữ authorization trong service để các adapter khác cũng được bảo vệ.

Nếu user không được phép thực hiện mutation, có thể trả top-level authorization error theo chính sách bảo mật của API. Chỉ trả lỗi đó trong payload nếu việc tiết lộ thông tin không làm lộ sự tồn tại của tài nguyên hoặc quyền của người dùng khác.

## 14. Kiểm thử mutation trả về payload bằng GraphQlTester

GraphQlTester có thể kiểm tra cả nhánh thành công và nhánh lỗi nghiệp vụ.

Test thành công:

~~~java
@SpringBootTest
class CreateBookMutationTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    void shouldReturnCreatedBookAndNoUserErrors() {
        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            title
                        }
                        userErrors {
                            code
                        }
                    }
                }
                """)
            .variable("input", Map.of(
                    "title", "Spring GraphQL",
                    "authorId", "author-01"))
            .execute()
            .path("createBook.book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");
    }
}
~~~

Test lỗi nghiệp vụ có thể kiểm tra **book** là null và **userErrors** có mã tương ứng:

~~~java
graphQlTester.document("""
        mutation {
            createBook(input: {
                title: "Spring GraphQL"
                authorId: "missing-author"
            }) {
                book {
                    id
                }
                userErrors {
                    code
                    field
                }
            }
        }
        """)
    .execute()
    .path("createBook.book")
    .valueIsNull()
    .path("createBook.userErrors[0].code")
    .entity(String.class)
    .isEqualTo("AUTHOR_NOT_FOUND");
~~~

Các trường hợp nên kiểm thử:

1. Mutation thành công trả payload, tài nguyên và danh sách lỗi rỗng.
2. Validation nghiệp vụ trả **book: null** và **userErrors** phù hợp.
3. Lỗi có field path đúng, kể cả input lồng nhau.
4. **clientMutationId** được echo đúng nếu client gửi.
5. Không gửi **clientMutationId** vẫn nhận payload hợp lệ.
6. Input sai kiểu hoặc thiếu field non-null bị GraphQL từ chối trước resolver.
7. Exception hệ thống trở thành top-level GraphQL error theo chính sách.
8. Không có dữ liệu được lưu khi validation thất bại.
9. Constraint database và race condition không tạo payload thành công giả.
10. Authorization ngăn người dùng không đủ quyền thực hiện thao tác.

Ngoài response, hãy kiểm tra trạng thái database sau mutation thất bại để xác nhận không có side effect ngoài ý muốn.

## 15. Những lỗi thiết kế payload thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Payload chứa mọi field đều nullable | Client khó hiểu trạng thái nào hợp lệ | Chọn nullability theo contract |
| Field tài nguyên để non-null dù mutation có thể thất bại | Không thể trả lỗi nghiệp vụ cùng payload | Cho phép field tài nguyên null |
| **userErrors** nullable | Client phải kiểm tra thêm null | Dùng list non-null và trả **[]** khi thành công |
| Bắt mọi exception thành user error | Che giấu lỗi hệ thống | Chỉ chuyển lỗi nghiệp vụ dự kiến thành payload |
| Dùng message làm error code | Client phụ thuộc văn bản có thể đổi | Cung cấp code ổn định |
| Một payload khổng lồ dùng cho mọi mutation | Contract khó hiểu và nhiều field không liên quan | Tạo payload theo use case |
| Nhầm clientMutationId với idempotency | Request retry vẫn có thể tạo side effect lặp | Dùng idempotency key có lưu trạng thái server |
| Trả entity nội bộ trực tiếp | Có thể lộ field không dành cho client | Dùng output type/DTO công khai |
| Trả payload trước khi transaction rõ ràng | Có thể báo thành công dù dữ liệu chưa commit | Xác định transaction boundary |
| Chỉ test response thành công | Bỏ sót lỗi nghiệp vụ và rollback | Test cả success, failure và side effect |

## 16. Quy trình thiết kế mutation payload

Khi thiết kế mutation trả về payload:

1. Xác định dữ liệu client cần sau khi thao tác hoàn tất.
2. Tạo payload type gắn với tên use case.
3. Chọn field tài nguyên và nullability phù hợp với cả success lẫn domain failure.
4. Thiết kế **userErrors** với code ổn định, message an toàn và field path nếu cần.
5. Phân biệt lỗi nghiệp vụ với GraphQL validation/execution errors.
6. Khai báo input type riêng cho thao tác.
7. Bind input và trả payload từ handler bằng **@MutationMapping**.
8. Thực hiện validation trước side effect và đặt transaction trong service.
9. Thiết kế correlation hoặc idempotency riêng khi có nhu cầu retry.
10. Kiểm tra authorization, thông tin nhạy cảm và schema evolution.
11. Viết GraphQlTester cho thành công, lỗi nghiệp vụ, lỗi GraphQL và trạng thái dữ liệu.

Payload object giúp mutation trả về một hợp đồng kết quả rõ ràng gồm tài nguyên, lỗi nghiệp vụ và metadata liên quan. Trong Spring for GraphQL, SDL định nghĩa payload type, **@MutationMapping** nối field với handler method, **@Argument** bind input và service quyết định kết quả nghiệp vụ. Phân biệt **userErrors** với top-level GraphQL errors, chọn nullability đúng và kiểm soát transaction sẽ giúp client xử lý mutation nhất quán mà server vẫn giữ được ranh giới nghiệp vụ và lỗi hệ thống.
