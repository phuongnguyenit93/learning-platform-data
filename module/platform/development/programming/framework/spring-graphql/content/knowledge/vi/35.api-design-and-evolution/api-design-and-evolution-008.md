# Input type và output type tách biệt

Khi thiết kế GraphQL schema, dữ liệu client gửi lên và dữ liệu server trả về thường có hình dạng khác nhau. Client có thể gửi authorId để tạo một Book, trong khi response trả về cả object Author với id, name và các field khác. Client có thể cập nhật title và description, nhưng không được tự đặt createdAt, owner, permissions hoặc những field do server quản lý.

GraphQL phản ánh sự khác biệt đó ngay trong type system: input types mô tả những giá trị client được phép cung cấp; output types mô tả những giá trị server có thể trả về. Một số named type như scalar và enum dùng được ở cả hai phía, nhưng Input Object và Object/Interface/Union có vai trò riêng và không thể hoán đổi.

Tách input type khỏi output type giúp schema thể hiện đúng ý định nghiệp vụ, giới hạn dữ liệu client có thể thay đổi, hỗ trợ validation và cho phép API tiến hóa độc lập ở hai chiều.

## Quy tắc input type và output type

GraphQL phân loại type dựa trên vị trí sử dụng:

| Nhóm type | Có thể dùng làm input | Có thể dùng làm output |
| --- | --- | --- |
| Scalar (String, Int, ID, custom scalar...) | Có | Có |
| Enum | Có | Có |
| Input Object (input) | Có | Không |
| Object (type) | Không | Có |
| Interface | Không | Có |
| Union | Không | Có |
| List và Non-Null | Theo type được bọc | Theo type được bọc |

Một field của Object hoặc Interface trả về output type. Các argument của field đó phải dùng input type. Input Object chỉ chứa scalar, enum, input object khác hoặc các dạng list/non-null bao quanh những type đó.

Input Object không thể khai báo argument trên các field con. Các đoạn SDL trong bài là ví dụ độc lập theo từng use case; khi ghép vào một schema hoàn chỉnh, hãy khai báo mỗi type và scalar đúng một lần.

Ví dụ hợp lệ:

~~~graphql
type Query {
  book(id: ID!): Book
  books(filter: BookFilterInput): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}

input BookFilterInput {
  keyword: String
  authorId: ID
}
~~~

Các kiểu DateTime và BookStatus được khai báo ở nơi khác trong schema hoàn chỉnh; ví dụ này tập trung vào cấu trúc output Book.

Trong ví dụ:

- Book và Author là output object types.
- BookFilterInput là input object type.
- ID và String là scalar, có thể dùng ở cả input và output.
- books nhận BookFilterInput nhưng trả về danh sách Book.

## Vì sao không dùng chung một type?

Hãy xét output Book:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Author {
  id: ID!
  name: String!
}

type Book {
  id: ID!
  title: String!
  description: String
  author: Author!
  status: BookStatus!
  createdAt: DateTime!
  updatedAt: DateTime!
  averageRating: Float
  canEdit: Boolean!
}
~~~

Đây là mô hình đọc. Một số field là quan hệ tới object khác (author), một số field do server tính (averageRating, canEdit), và một số field do server quản lý (createdAt, updatedAt).

GraphQL không cho dùng Book trực tiếp làm input. Nhưng nếu thiết kế một input quá rộng và sao chép cả field do server quản lý, client sẽ có thể gửi những giá trị không nên được phép ghi:

~~~graphql
scalar DateTime

type Book {
  id: ID!
  title: String!
}

input UnsafeBookInput {
  id: ID
  title: String
  createdAt: DateTime
  canEdit: Boolean
}

type Mutation {
  updateBook(input: UnsafeBookInput!): Book!
}
~~~

Client request:

~~~graphql
mutation {
  updateBook(input: {
    id: "book-42"
    title: "New title"
    createdAt: "2000-01-01T00:00:00Z"
    canEdit: true
  }) { id title }
}
~~~

Schema đúng sẽ từ chối những field không được khai báo trong input object. Không nên mở rộng input để chấp nhận tất cả field output rồi trông chờ service bỏ qua các field nguy hiểm.

Tách type đem lại các lợi ích:

1. **Giới hạn quyền ghi.** Input chỉ chứa field nghiệp vụ cho phép client thay đổi.
2. **Thể hiện ý định.** Create, update, filter và sort là những thao tác khác nhau, nên có input riêng.
3. **Tránh mass assignment.** Không bind toàn bộ request vào entity rồi vô tình ghi các field nội bộ.
4. **Giữ response giàu thông tin.** Output có thể chứa quan hệ, field tính toán, trạng thái và metadata không cần xuất hiện trong input.
5. **Tiến hóa độc lập.** Có thể thêm field đọc vào output mà không thay đổi contract ghi; có thể mở rộng input mà không làm lộ thêm dữ liệu trả về.
6. **Validation rõ ràng.** Quy tắc cho thao tác tạo mới thường khác quy tắc cho cập nhật hoặc tìm kiếm.

Java DTO và GraphQL type cũng không cần trùng một-một. Có thể dùng một Java command làm đối tượng trung gian cho service, trong khi SDL định nghĩa contract public riêng.

Các đoạn Java phía dưới là những ví dụ độc lập theo từng phần; BookService, BookView và các kiểu domain liên quan được giả định đã có trong ứng dụng.

## Những schema sai thường gặp

Không dùng Object type làm argument:

~~~graphql
type Author {
  id: ID!
  name: String!
}

type Mutation {
  # Sai: Author là output object type.
  createBook(author: Author!): Book!
}
~~~

Không dùng Input Object làm return type:

~~~graphql
input BookInput {
  title: String!
}

type Mutation {
  # Sai: BookInput chỉ được dùng ở vị trí input.
  createBook(input: BookInput!): BookInput!
}
~~~

Không đặt output object hoặc interface bên trong input object:

~~~graphql
input CreateBookInput {
  title: String!
  # Sai: Author là output object type.
  author: Author
}
~~~

Hãy dùng ID hoặc một input object tham chiếu riêng:

~~~graphql
input AuthorReferenceInput {
  id: ID!
}

input CreateBookInput {
  title: String!
  author: AuthorReferenceInput!
}
~~~

Hoặc đơn giản hơn:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Chọn cách biểu diễn phù hợp với nghiệp vụ. Nếu chỉ cần chọn một Author đã tồn tại, authorId thường đủ rõ. Nếu tham chiếu có thêm quy tắc như nguồn định danh hoặc tenant, một input object riêng có thể diễn đạt tốt hơn.

## Thiết kế input cho từng thao tác

Không nên tạo một BookInput tổng quát rồi dùng cho create, update, filter và sort. Mỗi thao tác có yêu cầu khác nhau:

| Input type | Mục đích | Ví dụ field |
| --- | --- | --- |
| CreateBookInput | Tạo Book mới | title!, authorId!, tags |
| UpdateBookInput | Cập nhật một phần Book | title, description, status |
| BookFilterInput | Lọc danh sách Book | keyword, statuses, authorIds |
| BookSortInput | Chọn thứ tự sắp xếp | field, direction |
| BookPageInput | Điều khiển phân trang | first, after |

### Create input

Tạo mới thường yêu cầu các dữ liệu tối thiểu để tạo một thực thể hợp lệ:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  description: String
  tags: [String!]! = []
}
~~~

title và authorId là bắt buộc. description có thể bỏ qua hoặc gửi null. tags có default value là danh sách rỗng nên client không bắt buộc gửi field này; nếu có gửi thì danh sách không được null và từng phần tử không được null.

Không đưa id, createdAt, updatedAt, ownerId, averageRating hoặc canEdit vào input nếu server chịu trách nhiệm tạo hay xác định các giá trị đó.

### Update input

Update thường cho phép thay đổi một phần field:

~~~graphql
input UpdateBookInput {
  title: String
  description: String
  status: BookStatus
}

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}
~~~

Java có thể dùng enum cùng tên để bind giá trị:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Các field nullable và không có default có thể bị bỏ qua. Nếu client gửi một field, server xử lý field đó theo chính sách cập nhật. Không thêm default value vào field update nếu ý nghĩa mong muốn là “không gửi thì giữ nguyên”.

Mutation có thể nhận ID ở argument riêng và input cho phần thay đổi:

~~~graphql
type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}
~~~

Đặt id riêng giúp tách định danh của tài nguyên khỏi nội dung thay đổi. Một API khác có thể đặt ID trong input object nếu đó là convention nhất quán của toàn schema.

### Filter input

Filter diễn đạt tiêu chí tìm kiếm, không phải một phần của Book:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilterInput {
  keyword: String
  statuses: [BookStatus!]
  authorIds: [ID!]
  createdFrom: DateTime
  createdTo: DateTime
}
~~~

Không nhận một object Book đầy đủ chỉ để lọc. Filter nên mô tả điều kiện cần tìm, có thể chứa nhiều lựa chọn và toán tử rõ ràng theo nhu cầu nghiệp vụ.

### Sort và pagination input

Sử dụng enum để giới hạn trường sắp xếp và chiều sắp xếp:

~~~graphql
enum BookSortField {
  TITLE
  CREATED_AT
  UPDATED_AT
}

enum SortDirection {
  ASC
  DESC
}

input BookSortInput {
  field: BookSortField! = CREATED_AT
  direction: SortDirection! = DESC
}

input BookPageInput {
  first: Int! = 20
  after: String
}
~~~

Enum giúp client chỉ chọn các trường được schema công bố. Không nhận chuỗi SQL, tên cột tùy ý hoặc biểu thức sort do client cung cấp rồi nối trực tiếp vào query database.

Schema query:

~~~graphql
type Query {
  books(
    filter: BookFilterInput
    sort: BookSortInput
    page: BookPageInput
  ): BookConnection!
}

type BookConnection {
  edges: [BookEdge!]!
  pageInfo: PageInfo!
  totalCount: Int!
}

type BookEdge {
  cursor: String!
  node: Book!
}

type PageInfo {
  hasNextPage: Boolean!
  endCursor: String
}
~~~

BookFilterInput, BookSortInput và BookPageInput là input types. BookConnection, BookEdge, PageInfo và Book là output types. Output connection có thể chứa object lồng nhau và metadata phân trang mà client chỉ cần đọc.

Server vẫn phải kiểm tra giới hạn nghiệp vụ, ví dụ first nằm trong khoảng 1 đến 100. Int! chỉ bảo đảm giá trị không null và có kiểu Int; nó không tự bảo đảm giá trị dương hoặc nằm trong giới hạn cho phép.

## Output type cho kết quả mutation

Mutation nên trả về một output type thể hiện kết quả nghiệp vụ, thay vì trả lại input object:

~~~graphql
type Mutation {
  createBook(input: CreateBookInput!): CreateBookPayload!
  updateBook(id: ID!, input: UpdateBookInput!): UpdateBookPayload!
}

type CreateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type UpdateBookPayload {
  book: Book
  userErrors: [UserError!]!
}

type UserError {
  field: [String!]!
  code: String!
  message: String!
}
~~~

Payload là output object. Nó có thể trả về Book đã được lưu, lỗi nghiệp vụ có cấu trúc hoặc metadata bổ sung. book nullable vì một mutation có thể thất bại do dữ liệu không hợp lệ và khi đó không có Book được tạo/cập nhật. userErrors luôn trả về danh sách, kể cả danh sách rỗng khi thành công.

Ví dụ response thành công:

~~~json
{
  "data": {
    "createBook": {
      "book": {
        "id": "book-42",
        "title": "Spring GraphQL",
        "status": "DRAFT",
        "createdAt": "2026-11-20T10:00:00Z"
      },
      "userErrors": []
    }
  }
}
~~~

Ví dụ lỗi nghiệp vụ được biểu diễn thành dữ liệu:

~~~json
{
  "data": {
    "createBook": {
      "book": null,
      "userErrors": [
        {
          "field": ["authorId"],
          "code": "AUTHOR_NOT_FOUND",
          "message": "Không tìm thấy tác giả."
        }
      ]
    }
  }
}
~~~

Đây là lựa chọn thiết kế. Với lỗi hệ thống hoặc lỗi không thể xử lý như một kết quả nghiệp vụ bình thường, ứng dụng vẫn có thể trả GraphQL error ở top-level. Hãy thống nhất cách biểu diễn lỗi giữa các mutation.

## Nullability, optional và default value

GraphQL dùng dấu chấm than (!) để khai báo Non-Null. Trong input, Non-Null không chỉ cấm giá trị null mà còn khiến field/argument bắt buộc phải được cung cấp, trừ trường hợp có default value.

Trong output, Non-Null cam kết field không trả null. Nếu resolver trả null hoặc phát sinh lỗi ở vị trí Non-Null, lỗi sẽ lan lên parent cho đến khi gặp vị trí nullable gần nhất.

| Khai báo | Ý nghĩa khi làm input | Ý nghĩa khi làm output |
| --- | --- | --- |
| String | Có thể bỏ qua hoặc gửi null | Có thể trả null |
| String! | Bắt buộc có giá trị, không được null | Nếu được chọn thì không được trả null |
| [ID!] | Có thể bỏ qua hoặc gửi null; nếu có list thì item không null | List có thể null; item không null |
| [ID]! | List bắt buộc không null; item có thể null | List không null; item có thể null |
| [ID!]! | List bắt buộc không null và item không null | List và mọi item đều không null |

Ví dụ:

~~~graphql
type Book {
  tags: [String!]!
  relatedBooks: [Book!]
}

input CreateBookInput {
  title: String!
  tags: [String!]! = []
}
~~~

tags: [String!]! không có nghĩa danh sách phải có ít nhất một phần tử. Danh sách rỗng vẫn hợp lệ. Nếu nghiệp vụ yêu cầu tối thiểu một tag, cần validation bổ sung.

Default value cũng ảnh hưởng đến tính bắt buộc. tags: [String!]! = [] có thể bị bỏ qua vì server tự dùng danh sách rỗng; nếu client gửi tags: null, request vẫn không hợp lệ.

## Phân biệt omitted và explicit null trong update

Input object có một khác biệt quan trọng:

- Field bị bỏ qua: không có entry tương ứng trong input đã coercion.
- Field được gửi với giá trị null: entry tồn tại và có giá trị null.

Với UpdateBookInput, hai request sau có ý nghĩa khác nhau:

~~~graphql
mutation {
  updateBook(
    id: "book-42"
    input: { title: "New title" }
  ) {
    book { id title description }
  }
}
~~~

description bị bỏ qua, nên giữ nguyên mô tả hiện tại.

~~~graphql
mutation {
  updateBook(
    id: "book-42"
    input: {
      title: "New title"
      description: null
    }
  ) {
    book { id title description }
  }
}
~~~

description được gửi rõ ràng là null, nên có thể hiểu là xóa mô tả.

Nếu chỉ bind vào một Java field nullable thông thường, cả hai trường hợp có thể trở thành null, khiến service không biết client có chủ ý xóa hay chỉ không gửi field.

### Dùng ArgumentValue trong Spring for GraphQL

Spring for GraphQL cung cấp ArgumentValue<T> để giữ lại thông tin field bị bỏ qua hay được gửi (kể cả gửi null). Có thể dùng nó bên trong object input được bind bởi @Argument:

~~~java
import org.springframework.graphql.data.ArgumentValue;

public record UpdateBookInput(
        ArgumentValue<String> title,
        ArgumentValue<String> description,
        ArgumentValue<BookStatus> status) {
}
~~~

Resolver:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

record UserError(
        List<String> field,
        String code,
        String message) {
}

record UpdateBookPayload(
        BookView book,
        List<UserError> userErrors) {

    public static UpdateBookPayload invalid(String field, String code) {
        return new UpdateBookPayload(
                null,
                List.of(new UserError(
                        List.of(field),
                        code,
                        "Giá trị đầu vào không hợp lệ.")));
    }
}

@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public UpdateBookPayload updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {

        if (!input.title().isOmitted()) {
            if (input.title().value() == null) {
                return UpdateBookPayload.invalid(
                        "title", "TITLE_REQUIRED");
            }
        }

        return bookService.update(id, input);
    }
}
~~~

Trong service, có thể xử lý từng trạng thái:

~~~java
if (!input.description().isOmitted()) {
    // value() là null thì xóa mô tả;
    // có giá trị thì thay mô tả.
    book.changeDescription(input.description().value());
}

if (!input.status().isOmitted()) {
    if (input.status().value() == null) {
        throw new InvalidBookStatusException();
    }
    book.changeStatus(input.status().value());
}
~~~

ArgumentValue.isOmitted() trả true khi client không gửi field. Nếu client gửi field với null, isOmitted() trả false và value() trả null. Spring cũng hỗ trợ ArgumentValue bên trong các field lồng nhau của object được bind.

Nếu chỉ cần biết một argument ở cấp method có bị bỏ qua hay không, có thể dùng ArgumentValue<T> trực tiếp thay cho @Argument. Không dùng Optional<T> để phân biệt omitted và explicit null vì Optional không giữ được cả hai trạng thái này.

## Tạo Java input DTO và bind trong Spring

Input DTO là kiểu Java dành cho dữ liệu client gửi lên. Nó có thể khác với entity JPA và output DTO:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;

public record CreateBookInput(
        @NotBlank
        @Size(max = 200)
        String title,

        @NotNull
        String authorId,

        List<@NotBlank String> tags) {
}
~~~

Controller:

~~~java
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
    public CreateBookPayload createBook(
            @Argument("input") @Valid CreateBookInput input) {

        return bookService.create(input);
    }
}
~~~

Spring for GraphQL dùng GraphQlArgumentBinder để bind argument thành Java object. Binder có thể dùng constructor chính (bao gồm constructor của record), hoặc constructor mặc định và setter. Với input phức tạp, nested object được bind đệ quy.

Khi có Bean Validation Validator, annotated controller hỗ trợ @Valid và @Validated. Các constraint như @NotBlank, @Size được kiểm tra trước khi gọi method. GraphQL schema vẫn là lớp kiểm tra kiểu, required field và nullability đầu tiên; Bean Validation bổ sung các quy tắc chi tiết của ứng dụng.

Không nên bind request thẳng vào JPA entity. Hãy chuyển input DTO thành command hoặc lời gọi domain service, để chỉ những field được phép mới tham gia thao tác ghi.

## Input validation có nhiều lớp

Không phải mọi quy tắc đều thuộc cùng một tầng:

| Lớp | Ví dụ | Cơ chế |
| --- | --- | --- |
| GraphQL schema validation | Thiếu title: String!, gửi Object vào input, field không tồn tại | GraphQL parser, validator và input coercion |
| Binding | Giá trị không chuyển được sang Java target type | GraphQlArgumentBinder, BindException |
| Bean Validation | Title rỗng, chuỗi quá dài, danh sách vượt giới hạn | @Valid, @Validated, Jakarta Validation |
| Domain/business validation | Author không thuộc tenant, trạng thái không cho phép chuyển | Domain service hoặc application service |
| Authorization | Người dùng không có quyền sửa Book | Spring Security và kiểm tra quyền trong service |

Ví dụ, authorId: ID! chỉ bảo đảm client cung cấp một ID. Nó không bảo đảm Author đó tồn tại, thuộc đúng tenant hay người dùng được phép liên kết Author đó với Book.

Các kiểm tra phụ thuộc dữ liệu và trạng thái nghiệp vụ phải thực hiện trong service/domain layer. Không dựa vào GraphQL input type để thay thế authorization hoặc validation nghiệp vụ.

## Filter input không phải output object

Một filter có thể có nhiều tiêu chí mà không phản ánh cấu trúc đầy đủ của đối tượng được tìm:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  title: String!
}

input BookFilterInput {
  keyword: String
  statuses: [BookStatus!]
  authorIds: [ID!]
  hasDescription: Boolean
}

type Query {
  books(filter: BookFilterInput): [Book!]!
}
~~~

BookFilterInput chỉ công bố những điều kiện được hỗ trợ. Client không thể gửi averageRating, createdAt hoặc canEdit như thể đó là filter nếu schema không khai báo.

Nếu cần biểu diễn toán tử phức tạp, có thể thiết kế các input object riêng:

~~~graphql
scalar DateTime

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input StringFilterInput {
  eq: String
  contains: String
  startsWith: String
}

input DateTimeRangeInput {
  from: DateTime
  to: DateTime
}

input AdvancedBookFilterInput {
  title: StringFilterInput
  createdAt: DateTimeRangeInput
  status: BookStatus
}
~~~

Không tạo một input object tổng quát có thể mô tả mọi biểu thức database nếu API chỉ cần một vài điều kiện. Filter schema càng rộng thì việc validation, tối ưu query và bảo vệ chi phí thực thi càng khó.

## Enum và custom scalar dùng được ở cả hai phía

Scalar và enum có thể dùng trong input lẫn output:

~~~graphql
scalar DateTime
scalar UUID

enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

type Book {
  id: ID!
  status: BookStatus!
  createdAt: DateTime!
}

input BookFilterInput {
  id: UUID
  status: BookStatus
  createdAfter: DateTime
}
~~~

Scalar xác định quy tắc parse input và serialize output. Với custom scalar, hãy định nghĩa rõ format, miền giá trị và quy tắc coercion. Có thể dùng @specifiedBy để liên kết tới đặc tả của scalar:

~~~graphql
scalar UUID @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc9562")
~~~

Không tạo custom scalar chỉ để né type system. Nếu dữ liệu có cấu trúc gồm nhiều field, hãy dùng Input Object cho input hoặc Object type cho output.

## OneOf Input Object cho lựa chọn loại trừ nhau

Một số mutation hoặc query cho phép tìm đối tượng theo đúng một trong nhiều định danh, ví dụ ID hoặc ISBN:

~~~graphql
input BookLookupInput @oneOf {
  id: ID
  isbn: String
}

type Query {
  bookBy(input: BookLookupInput!): Book
}
~~~

Với OneOf Input Object, client phải cung cấp chính xác một field và giá trị của field đó không được null. Các field bên trong phải nullable và không có default value; chính quy tắc @oneOf quyết định phải chọn đúng một nhánh.

@oneOf được định nghĩa trong GraphQL specification hiện hành, nhưng cần xác nhận phiên bản GraphQL Java và tooling của ứng dụng hỗ trợ tính năng này trước khi sử dụng. Nếu implementation chưa hỗ trợ, dùng các argument rõ ràng hoặc một input có discriminator và validation ở service.

Ví dụ phương án tương thích rộng:

~~~graphql
enum BookLookupKind {
  ID
  ISBN
}

input BookLookupInput {
  kind: BookLookupKind!
  id: ID
  isbn: String
}
~~~

Service cần xác nhận chỉ field tương ứng với kind được cung cấp. Nếu không cần tính linh hoạt của một input chung, hai query riêng book(id: ID!) và bookByIsbn(isbn: String!) có thể đơn giản hơn.

## Tiến hóa input và output type

Input và output tiến hóa theo hai hướng khác nhau. Vì vậy, giữ chúng tách biệt giúp thay đổi schema ít gây ảnh hưởng ngoài ý muốn.

### Thay đổi output

GraphQL client chỉ nhận các field đã yêu cầu trong selection set. Thêm field output mới thường là thay đổi tương thích ngược:

~~~graphql
type Book {
  id: ID!
  title: String!
  subtitle: String
}
~~~

Client cũ không yêu cầu subtitle nên response cũ vẫn giữ hình dạng như trước. Client mới có thể chọn thêm field đó.

Để thay field cũ, có thể thêm field mới rồi đánh dấu field cũ deprecated:

~~~graphql
type Book {
  title: String!
  name: String @deprecated(reason: "Use title instead.")
}
~~~

Không xóa field ngay khi client vẫn còn sử dụng. Theo dõi usage, thông báo migration và chỉ loại bỏ sau khi có kế hoạch tương thích phù hợp.

### Thay đổi input

Thêm field input nullable thường cho phép client cũ tiếp tục gửi request:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  subtitle: String
}
~~~

Nhưng thêm field Non-Null không có default sẽ khiến request cũ thiếu field đó trở thành không hợp lệ:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  publisherId: ID!
}
~~~

Trước khi thêm field bắt buộc, cần có chiến lược migration. Có thể thêm field nullable/default trước, cập nhật client, sau đó mới siết required nếu contract và dữ liệu đã sẵn sàng.

Input field và enum value cũng có thể được deprecate. Một input field Non-Null không có default không thể deprecate trực tiếp; trước hết phải chuyển nó thành optional hoặc có default value. Sau đó mới dùng @deprecated và theo dõi client usage.

### Ma trận thay đổi

| Thay đổi | Tác động thường gặp |
| --- | --- |
| Thêm output field nullable | Thường tương thích ngược |
| Thêm output field Non-Null | Client cũ không bị buộc phải query field mới, nhưng cần bảo đảm contract và implementation |
| Xóa output field đang dùng | Breaking change |
| Đổi output field nullable thành Non-Null | Có thể làm thay đổi codegen/client contract và cách lỗi lan truyền |
| Thêm input field nullable không default | Thường tương thích với request cũ |
| Thêm input field Non-Null không default | Breaking change vì request cũ thiếu field |
| Xóa input field client đang gửi | Breaking change |
| Thêm enum value output | Client dùng enum đóng có thể cần cập nhật cách xử lý unknown value |
| Thêm enum value input | Server có thể nhận thêm lựa chọn mới; client cũ không cần gửi |
| Xóa enum value | Có thể làm hỏng client đang gửi hoặc xử lý value đó |

Không thể chỉ nhìn vào tên field để kết luận một thay đổi an toàn. Hãy xét vị trí input/output, nullability, default value và cách client sinh code.

## Kiểm thử contract input/output

Nên kiểm thử cả schema và cách Spring bind dữ liệu:

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Truyền Object output vào argument | Schema validation từ chối |
| Dùng Input Object làm return type | Schema không hợp lệ |
| Bỏ field Non-Null không có default | Request bị từ chối trước khi gọi resolver |
| Gửi null cho field Non-Null | Request bị từ chối |
| Gửi field không được khai báo trong input | Input coercion từ chối |
| Gửi CreateBookInput hợp lệ | Controller nhận đúng DTO |
| Gửi title rỗng | Bean Validation phát hiện |
| Gửi authorId không tồn tại | Domain service trả lỗi nghiệp vụ |
| Update bỏ qua description | Mô tả cũ được giữ nguyên |
| Update gửi description: null | Mô tả được xóa theo chính sách |
| Update gửi description mới | Mô tả được thay đổi |
| Client query output field mới | Response trả field mới |
| Client cũ không query field mới | Response vẫn chỉ có field cũ |

Có thể dùng GraphQlTester hoặc HttpGraphQlTester để gửi mutation/query và kiểm tra response. Khi kiểm thử input validation, xác minh resolver/service không bị gọi nếu request sai cấu trúc hoặc sai kiểu.

Ví dụ kiểm thử create mutation:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                book {
                    id
                    title
                    status
                }
                userErrors {
                    code
                }
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL",
            "authorId", "author-10"))
    .execute()
    .path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
~~~

Test này xác minh contract input được bind và output payload được trả về. Cần seed Author hợp lệ hoặc mock service tương ứng để test độc lập với database.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Schema không khởi tạo | Dùng Object type ở vị trí input | Tạo Input Object riêng |
| Mutation không nhận nested object | Input field tham chiếu output type | Dùng ID hoặc nested input type |
| Không thể trả input object từ resolver | Input Object bị dùng làm output return type | Tạo output Object/Payload type |
| Client có thể sửa field nội bộ | Input tái sử dụng output/entity quá rộng | Chỉ công bố field được phép ghi |
| Update luôn ghi null vào field bị bỏ qua | DTO nullable làm mất khác biệt omitted/null | Dùng ArgumentValue hoặc raw argument map |
| Update không thể xóa nullable field | Input field bị khai báo Non-Null | Cho phép nullable nếu nghiệp vụ hỗ trợ clear |
| Create thiếu dữ liệu | Field input không có required constraint | Dùng Non-Null hoặc Bean Validation tùy quy tắc |
| String! vẫn nhận chuỗi rỗng | Non-Null chỉ cấm null/omission | Dùng @NotBlank hoặc domain validation |
| Sort nhận tên cột tùy ý | Dùng String tự do làm sort field | Dùng enum whitelist |
| Filter quá phức tạp | Reuse output object hoặc input tổng quát quá rộng | Thiết kế filter input theo use case |
| Thêm input field mới làm client cũ lỗi | Field mới là Non-Null không default | Thêm nullable/default trước, migration client rồi siết sau |
| Mutation trả entity có field ngoài ý muốn | Expose trực tiếp persistence entity | Trả output DTO và kiểm soát field công khai |

## Quy trình thiết kế input và output

Khi thiết kế một GraphQL operation:

1. **Xác định dữ liệu client được phép gửi.** Liệt kê field cần cho use case, không sao chép toàn bộ output object.
2. **Xác định dữ liệu server trả về.** Tạo output object có quan hệ, field tính toán và trạng thái cần cho client.
3. **Tách input theo hành động.** Create, update, filter, sort và pagination thường cần type riêng.
4. **Chọn ID hay nested input.** Dùng ID khi tham chiếu tài nguyên đã tồn tại; dùng nested input khi thao tác thực sự cần dữ liệu lồng nhau.
5. **Đặt nullability có chủ đích.** Phân biệt required, optional, nullable và default value.
6. **Thiết kế patch semantics.** Quy định rõ omitted nghĩa là giữ nguyên hay dùng default, còn explicit null nghĩa là xóa hay không hợp lệ.
7. **Bind vào input DTO.** Dùng @Argument, GraphQlArgumentBinder, @Valid và ArgumentValue khi phù hợp.
8. **Kiểm tra domain và authorization.** ID hợp lệ về kiểu không có nghĩa client có quyền truy cập tài nguyên đó.
9. **Trả payload phù hợp.** Dùng output object/payload để thể hiện kết quả và lỗi nghiệp vụ.
10. **Đánh giá tác động schema.** Thêm field nullable/default thường dễ tiến hóa hơn thêm field input bắt buộc.
11. **Kiểm thử cả hai chiều.** Kiểm tra request hợp lệ/không hợp lệ và response theo selection set.

Input type và output type là hai contract khác nhau trong GraphQL. Scalar và enum có thể dùng ở cả hai phía, nhưng Input Object chỉ dùng để nhận dữ liệu; Object, Interface và Union chỉ dùng để trả dữ liệu. Tách CreateBookInput, UpdateBookInput, filter/sort input khỏi output object giúp kiểm soát quyền ghi, validation và tiến hóa API. Khi cập nhật một phần, phải giữ được khác biệt giữa field bị bỏ qua và field được gửi null; trong Spring for GraphQL, ArgumentValue<T> hỗ trợ chính xác trường hợp này. Hãy để schema kiểm tra cấu trúc, Bean Validation kiểm tra dữ liệu đầu vào, domain service kiểm tra nghiệp vụ và authorization, rồi trả output DTO/payload được thiết kế riêng cho client.

## Tài liệu tham khảo

- [GraphQL Specification - Input and Output Types](https://spec.graphql.org/September2026/#sec-Input-and-Output-Types)
- [GraphQL Specification - Input Objects](https://spec.graphql.org/September2026/#sec-Input-Objects)
- [GraphQL Specification - Non-Null and List Types](https://spec.graphql.org/September2026/#sec-Non-Null)
- [GraphQL - Schemas and Types](https://graphql.org/learn/schema/)
- [GraphQL - Schema Design and Evolution](https://graphql.org/learn/schema-design/)
- [Spring for GraphQL - Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - ArgumentValue API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/data/ArgumentValue.html)
