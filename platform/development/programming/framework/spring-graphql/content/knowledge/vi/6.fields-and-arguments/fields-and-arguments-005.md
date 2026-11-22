# Input object cho mutation

Mutation thường cần nhiều dữ liệu đầu vào để tạo mới hoặc cập nhật một tài nguyên. Nếu khai báo tất cả giá trị thành các argument riêng lẻ, chữ ký field sẽ dài, khó mở rộng và khó tái sử dụng. GraphQL giải quyết vấn đề này bằng **input object**: một kiểu dữ liệu chuyên dùng để gom các giá trị đầu vào thành một cấu trúc có tên và có kiểu rõ ràng.

Trong Spring for GraphQL, input object được khai báo bằng SDL, sau đó Spring bind argument thành Java record, DTO hoặc cấu trúc dữ liệu phù hợp thông qua **@Argument**. Việc tách input object khỏi object type đầu ra giúp server kiểm soát chính xác dữ liệu client được phép gửi, áp dụng validation và bảo vệ mô hình nội bộ.

Bài này tập trung vào cách thiết kế input object cho mutation, truyền dữ liệu bằng variables, hiểu quy tắc null/default, bind vào Java, xác thực dữ liệu và xử lý các tình huống tạo mới hoặc cập nhật.

## 1. Vì sao mutation cần input object?

Một mutation đơn giản có thể khai báo từng argument trực tiếp:

~~~graphql
type Mutation {
  createBook(
    title: String!
    authorId: ID!
    status: String
    description: String
  ): Book!
}
~~~

Khi số trường tăng lên, field có quá nhiều argument. Mỗi lần thêm một thuộc tính, chữ ký mutation lại thay đổi. Client cũng phải truyền một nhóm giá trị rời rạc, dù về mặt nghiệp vụ chúng cùng mô tả một yêu cầu tạo sách.

Có thể gom các giá trị đó vào một input object:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  description: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Lúc này mutation chỉ nhận một argument **input**. Các trường thuộc yêu cầu tạo sách được mô tả tập trung trong **CreateBookInput**.

Input object mang lại một số lợi ích:

- Nhóm các giá trị cùng thuộc một lệnh nghiệp vụ.
- Thể hiện rõ kiểu và tính bắt buộc của từng trường.
- Dễ mở rộng khi thêm trường đầu vào.
- Có thể lồng các input object để mô tả cấu trúc phức tạp.
- Tách dữ liệu client được phép gửi khỏi dữ liệu server trả về hoặc dữ liệu persistence nội bộ.
- Thuận tiện bind vào Java record/DTO và áp dụng validation.

## 2. Khai báo input object trong SDL

Input object được khai báo bằng từ khóa **input**:

~~~graphql
input InputTypeName {
  fieldName: InputFieldType
}
~~~

Ví dụ:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  description: String
}
~~~

Một input object phải có ít nhất một input field. Mỗi field có tên, kiểu đầu vào và có thể có giá trị mặc định.

### Những kiểu được phép dùng trong input object

Input field chỉ được dùng các input type hợp lệ:

- Scalar như **String**, **Int**, **Float**, **Boolean**, **ID** và custom scalar.
- Enum như **BookStatus**.
- Input object khác.
- List và non-null bọc một input type hợp lệ.

Ví dụ:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookMetadataInput {
  language: String
  pageCount: Int
  keywords: [String!]
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus
  metadata: BookMetadataInput
}
~~~

Không thể dùng object type thông thường, interface hoặc union làm kiểu field của input object. Các kiểu đó mô tả dữ liệu đầu ra. Nếu client cần tham chiếu một object đã tồn tại, thường chỉ cần gửi định danh như **authorId** thay vì gửi toàn bộ object **Author**.

Schema sau không hợp lệ:

~~~graphql
type Author {
  id: ID!
  name: String!
}

input CreateBookInput {
  title: String!
  author: Author
}
~~~

Hãy thay bằng input type hoặc ID:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Server dùng **authorId** để tải Author, kiểm tra quyền và tạo quan hệ. Client không được tự gửi những thuộc tính của Author mà thao tác tạo sách không có quyền thay đổi.

## 3. Kết nối input object với mutation

Một mutation field nhận input object như argument và trả về một output type:

~~~graphql
type Book {
  id: ID!
  title: String!
  status: BookStatus!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Có ba phần cần phân biệt:

1. **CreateBookInput** định nghĩa cấu trúc dữ liệu client gửi.
2. **input: CreateBookInput!** khai báo argument bắt buộc của mutation.
3. **Book!** là output type server trả về sau khi xử lý.

Input object không phải kết quả của mutation. Client vẫn cần selection set trên output object để chỉ định những trường muốn nhận:

~~~graphql
mutation {
  createBook(input: {
    title: "GraphQL with Spring"
    authorId: "author-01"
  }) {
    id
    title
    status
  }
}
~~~

Ở ví dụ này, **input** là argument đầu vào; phần trong cặp ngoặc nhọn sau **createBook** là selection set của kết quả **Book**.

### Nên dùng một input object cho mỗi hành động nghiệp vụ

Tạo mới và cập nhật thường có quy tắc bắt buộc khác nhau. Vì vậy nên thiết kế input riêng:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}

input UpdateBookInput {
  id: ID!
  title: String
  description: String
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
  updateBook(input: UpdateBookInput!): Book
}
~~~

Khi tạo mới, **title** và **authorId** là bắt buộc. Khi cập nhật, client chỉ có thể gửi các trường cần thay đổi; những trường khác có thể được giữ nguyên theo quy tắc của API.

Không nên tạo một input tổng quát chứa mọi thuộc tính của Book rồi dùng chung cho tất cả mutation. Input riêng cho từng use case giúp hợp đồng API rõ ràng, hạn chế mass assignment và tránh trường hợp client gửi nhầm trường không liên quan.

## 4. Truyền input object bằng variables

Có thể viết input object trực tiếp trong operation, nhưng với ứng dụng thực tế nên ưu tiên variables. Cách này tách GraphQL document khỏi dữ liệu cụ thể:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
    status
  }
}
~~~

Variables được gửi dưới dạng JSON:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

Tên biến **input** được khai báo với kiểu **CreateBookInput!**, sau đó được truyền vào argument cùng tên của mutation. Server kiểm tra variables theo schema trước khi gọi resolver.

### Literal và JSON variables có cú pháp khác nhau

Trong GraphQL document, enum được viết dưới dạng enum literal không có dấu nháy:

~~~graphql
mutation {
  createBook(input: {
    title: "GraphQL with Spring"
    authorId: "author-01"
    status: DRAFT
  }) {
    id
  }
}
~~~

Trong JSON variables, enum được truyền bằng chuỗi:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "status": "DRAFT"
  }
}
~~~

Đây là khác biệt giữa cú pháp GraphQL và JSON. Nếu viết **"DRAFT"** như một string literal trong GraphQL document, kiểu của giá trị sẽ không còn là enum literal và operation có thể không hợp lệ.

Variables còn giúp client tái sử dụng cùng một document với nhiều bộ dữ liệu, tránh nối chuỗi để tạo query và giảm nguy cơ lỗi escaping.

## 5. Required, nullable và default value

Khi thiết kế input object, cần hiểu chính xác ba trạng thái: field bắt buộc, field tùy chọn và field có giá trị mặc định.

~~~graphql
input CreateBookInput {
  title: String!
  subtitle: String
  status: BookStatus = DRAFT
  tags: [String!] = []
}
~~~

Ý nghĩa:

| Field | Quy tắc |
|---|---|
| **title: String!** | Phải được cung cấp và không được null |
| **subtitle: String** | Có thể bỏ qua hoặc truyền null |
| **status: BookStatus = DRAFT** | Nếu bỏ qua, dùng DRAFT; nếu truyền null thì giá trị vẫn là null vì field nullable |
| **tags: [String!] = []** | Nếu bỏ qua, dùng danh sách rỗng; phần tử trong danh sách không được null |

Giá trị mặc định của input field được khai báo sau dấu **=**. Default value giúp client không cần gửi những giá trị có quy tắc mặc định ổn định.

### Phân biệt bỏ qua field và truyền null

GraphQL phân biệt việc một field không xuất hiện trong input object với việc field được gửi tường minh là **null**.

Với input object:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
  description: String
}
~~~

Nếu client gửi:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "Tên mới"
  }
}
~~~

Field **description** không được cung cấp. Sau khi coercion, field nullable không có default bị bỏ khỏi map giá trị đầu vào.

Nếu client gửi:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "Tên mới",
    "description": null
  }
}
~~~

Field **description** đã được cung cấp với giá trị null. Nếu nghiệp vụ cập nhật phân biệt hai trường hợp, server có thể hiểu:

- Không gửi **description**: giữ nguyên mô tả hiện tại.
- Gửi **description: null**: xóa mô tả hiện tại.

Điểm này rất quan trọng với mutation dạng patch. Không nên mặc định mọi giá trị Java null đều có nghĩa giống nhau, vì khi bind vào một DTO thông thường, field bị bỏ qua và field được truyền null có thể cùng trở thành Java null.

### Giá trị mặc định ở input field và argument

Có thể khai báo default cho từng field:

~~~graphql
input CreateBookInput {
  status: BookStatus = DRAFT
}
~~~

Hoặc default cho argument của mutation:

~~~graphql
type Mutation {
  createDraftBook(status: BookStatus = DRAFT): Book!
}
~~~

Default ở input field được áp dụng khi field đó không xuất hiện trong input object. Default ở argument được áp dụng khi argument không được cung cấp. Hãy tránh đặt các default mâu thuẫn ở nhiều cấp vì client khó hiểu giá trị cuối cùng được dùng.

Nếu field non-null có default hợp lệ, client có thể bỏ qua field đó và server dùng default. Nếu client truyền null tường minh cho field non-null, operation bị từ chối trong giai đoạn coercion.

## 6. Input object lồng nhau và danh sách

Input object có thể chứa một input object khác. Điều này phù hợp khi một mutation nhận nhiều nhóm dữ liệu có cấu trúc riêng:

~~~graphql
input AddressInput {
  street: String!
  city: String!
  postalCode: String
}

input BookMetadataInput {
  language: String
  pageCount: Int
  keywords: [String!]
}

input CreateBookInput {
  title: String!
  authorId: ID!
  shippingAddress: AddressInput
  metadata: BookMetadataInput
}
~~~

Client có thể gửi cấu trúc lồng nhau bằng JSON:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "shippingAddress": {
      "street": "12 Nguyen Hue",
      "city": "Ho Chi Minh City",
      "postalCode": "700000"
    },
    "metadata": {
      "language": "vi",
      "pageCount": 320,
      "keywords": ["graphql", "spring", "api"]
    }
  }
}
~~~

### Input object trong list

Một input object cũng có thể là phần tử của list:

~~~graphql
input ChapterInput {
  title: String!
  position: Int!
}

input CreateBookInput {
  title: String!
  authorId: ID!
  chapters: [ChapterInput!]!
}
~~~

Client gửi nhiều chapter:

~~~json
{
  "input": {
    "title": "GraphQL with Spring",
    "authorId": "author-01",
    "chapters": [
      {
        "title": "GraphQL fundamentals",
        "position": 1
      },
      {
        "title": "Spring integration",
        "position": 2
      }
    ]
  }
}
~~~

Với **[ChapterInput!]!**, danh sách không được null và từng phần tử không được null. Danh sách rỗng vẫn là giá trị hợp lệ nếu không có quy tắc nghiệp vụ nào khác. Nếu phải có ít nhất một chapter, server cần validation nghiệp vụ bổ sung.

### Input object đệ quy

Input object có thể tham chiếu một input object khác, kể cả chính nó, nếu cấu trúc không tạo ra chuỗi field non-null đơn lẻ bắt buộc phải có giá trị vô hạn:

~~~graphql
input CategoryInput {
  name: String!
  parent: CategoryInput
  children: [CategoryInput!]
}
~~~

Ví dụ này biểu diễn một cây danh mục. Field **parent** nullable nên client có thể kết thúc nhánh đệ quy. Một chuỗi tham chiếu trực tiếp chỉ gồm các field non-null như **next: NodeInput!** sẽ không thể tạo giá trị đầu vào hữu hạn và không hợp lệ theo quy tắc schema của GraphQL.

Chỉ nên dùng input lồng sâu khi nó phản ánh một cấu trúc nghiệp vụ rõ ràng. Với dữ liệu tham chiếu đến resource đã tồn tại, gửi ID thường đơn giản và an toàn hơn việc lặp lại toàn bộ object.

## 7. Spring for GraphQL bind input object vào Java

Sau khi GraphQL kiểm tra và coercion variables, Spring for GraphQL bind argument vào tham số Java của controller. Với **@Argument**, tên argument trong SDL được ánh xạ vào tham số method.

Ví dụ input schema:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input CreateBookInput {
  title: String!
  authorId: ID!
  status: BookStatus = DRAFT
  tags: [String!] = []
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Java record:

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        BookStatus status,
        List<String> tags) {
}
~~~

Controller:

~~~java
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
~~~

**@MutationMapping** ánh xạ method vào field **Mutation.createBook**. **@Argument("input")** yêu cầu Spring bind argument **input** thành **CreateBookInput**. Spring GraphQL hỗ trợ bind vào constructor hoặc property của kiểu Java phù hợp; record là lựa chọn gọn vì có constructor canonical và dữ liệu đầu vào có thể được biểu diễn bất biến.

Tên trường của Java DTO cần tương thích với tên input field hoặc được cấu hình binding tương ứng. Kiểu Java cũng cần phù hợp với kiểu GraphQL: **ID** thường bind vào **String**, enum bind vào Java enum tương ứng, list bind vào collection/array và input object lồng nhau bind vào DTO lồng nhau.

### Bind input lồng nhau

Với schema có **AddressInput**, có thể tạo record Java tương ứng:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateBookInput(
        String title,
        String authorId,
        AddressInput shippingAddress) {
}
~~~

Spring bind cấu trúc lồng nhau vào tham số tương ứng. Controller có thể chuyển input sang command hoặc gọi service:

~~~java
@MutationMapping
public Book createBook(@Argument("input") CreateBookInput input) {
    CreateBookCommand command = new CreateBookCommand(
            input.title(),
            input.authorId(),
            input.shippingAddress());

    return bookService.create(command);
}
~~~

Trong ứng dụng lớn, nên cân nhắc chuyển GraphQL input DTO sang command của application/service layer. Như vậy service không phải phụ thuộc trực tiếp vào cấu trúc API và có thể được dùng từ những adapter khác.

## 8. Validation cho input object

GraphQL có nhiều lớp kiểm tra dữ liệu đầu vào. Cần phân biệt validation theo schema với validation của ứng dụng.

### Schema validation và input coercion

GraphQL tự kiểm tra:

- Field có tồn tại trong input object hay không.
- Field bắt buộc có được cung cấp hay không.
- Giá trị có đúng scalar, enum, list hoặc input object đã khai báo không.
- Field non-null có bị truyền null không.
- Literal hoặc variables có thể coercion thành kiểu yêu cầu không.

Ví dụ, schema:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
}
~~~

Variables thiếu **title** hoặc truyền **authorId: null** sẽ bị từ chối trước khi resolver thực thi. Client cũng không thể gửi một field tùy ý như **internalCost** nếu field đó không được khai báo trong input type.

### Bean Validation

Schema chỉ kiểm tra cấu trúc và kiểu dữ liệu. Nó không thể diễn đạt đầy đủ các quy tắc như chuỗi không được chỉ chứa khoảng trắng, mã tác giả phải tồn tại hoặc số chương phải nằm trong một giới hạn nghiệp vụ.

Có thể dùng Jakarta Bean Validation cho Java input:

~~~java
public record CreateBookInput(
        @NotBlank String title,
        @NotBlank String authorId,
        BookStatus status,
        List<@NotBlank String> tags) {
}
~~~

Controller đánh dấu argument cần validate:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") @Valid CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Ứng dụng cần có Jakarta Bean Validation provider, thường được thêm qua **spring-boot-starter-validation**. Với Spring Boot 3, các annotation thuộc namespace **jakarta.validation**.

Các constraint thường dùng:

| Constraint | Công dụng |
|---|---|
| **@NotNull** | Giá trị không được null |
| **@NotBlank** | Chuỗi phải có ít nhất một ký tự không phải whitespace |
| **@NotEmpty** | Chuỗi, collection hoặc map không được rỗng |
| **@Size** | Giới hạn độ dài hoặc số phần tử |
| **@Min / @Max** | Giới hạn số nguyên |
| **@Email** | Kiểm tra định dạng email cơ bản |
| **@Pattern** | Kiểm tra theo regular expression |

Đối với input lồng nhau, dùng **@Valid** ở thuộc tính cần cascade validation và constraint phù hợp trên các field con. Hãy kiểm tra cấu hình validation của ứng dụng để chắc chắn các constraint được thực thi ở đúng cấp.

### Validation nghiệp vụ ở service

Một số quy tắc chỉ có thể kiểm tra khi truy cập dữ liệu hoặc thực hiện nghiệp vụ:

- **authorId** có tồn tại không?
- Người dùng hiện tại có quyền tạo sách cho tác giả đó không?
- Tên sách có trùng theo quy tắc của catalog không?
- Tập chapter có vị trí trùng nhau không?
- Trạng thái được phép tạo trực tiếp là **DRAFT** hay **PUBLISHED**?

Các kiểm tra này nên nằm trong application/service layer và được thực hiện trong cùng quy trình nghiệp vụ cần thiết. Không nên coi việc GraphQL đã chấp nhận input là bằng chứng dữ liệu hợp lệ về mặt nghiệp vụ.

## 9. Phân biệt lỗi schema, binding và nghiệp vụ

Một request mutation có thể thất bại ở nhiều giai đoạn:

| Giai đoạn | Ví dụ lỗi | Resolver đã chạy chưa? |
|---|---|---:|
| Parse/validation operation | Sai cú pháp, field input không tồn tại | Chưa |
| Variable/input coercion | Thiếu field non-null, enum không hợp lệ | Chưa |
| Binding/Bean Validation | DTO không bind được hoặc constraint thất bại | Có thể chưa vào thân method |
| Business validation | Tác giả không tồn tại hoặc người dùng không có quyền | Có |
| Persistence/external call | Database constraint hoặc service bên ngoài lỗi | Có |

GraphQL trả lỗi qua mảng **errors**. Với mutation trả về non-null **Book!**, nếu resolver phát sinh lỗi và không có giá trị thay thế, null propagation có thể khiến field mutation và phần **data** bị null theo quy tắc GraphQL.

Ví dụ response:

~~~json
{
  "data": {
    "createBook": null
  },
  "errors": [
    {
      "message": "Tác giả không tồn tại",
      "path": ["createBook"],
      "extensions": {
        "code": "AUTHOR_NOT_FOUND"
      }
    }
  ]
}
~~~

Trong Spring for GraphQL, có thể chuẩn hóa exception thành GraphQL error bằng **@GraphQlExceptionHandler** hoặc **DataFetcherExceptionResolver** tùy phạm vi xử lý. Tránh trả stack trace, SQL hoặc thông tin nội bộ cho client. Chi tiết kỹ thuật nên được ghi log có kiểm soát ở server, còn response chỉ chứa thông tin đủ để client xử lý.

## 10. Input object cho mutation cập nhật

Tạo mới thường yêu cầu đầy đủ các trường bắt buộc; cập nhật thường chỉ thay đổi một phần. Vì vậy **UpdateBookInput** thường có cấu trúc khác:

~~~graphql
input UpdateBookInput {
  id: ID!
  title: String
  description: String
  status: BookStatus
}

type Mutation {
  updateBook(input: UpdateBookInput!): Book
}
~~~

Ví dụ chỉ đổi tiêu đề:

~~~json
{
  "input": {
    "id": "book-01",
    "title": "Tên sách mới"
  }
}
~~~

Ví dụ xóa mô tả nếu API quy định null có nghĩa là xóa:

~~~json
{
  "input": {
    "id": "book-01",
    "description": null
  }
}
~~~

### Bảo toàn ý nghĩa omitted và null khi bind vào Java

Với một Java record thông thường:

~~~java
public record UpdateBookInput(
        String id,
        String title,
        String description,
        BookStatus status) {
}
~~~

Field **title** không được gửi và field **title** được gửi với null có thể cùng được biểu diễn bằng Java null sau khi bind. Nếu nghiệp vụ cần phân biệt hai trạng thái, hãy dùng representation giữ được thông tin field có xuất hiện hay không, chẳng hạn một map có kiểm tra key, hoặc cơ chế presence-aware như **ArgumentValue** ở vị trí argument mà Spring GraphQL hỗ trợ.

**ArgumentValue<T>** được dùng để phân biệt một argument không được cung cấp với argument được cung cấp nhưng có giá trị null. Với input object lồng nhau, cần kiểm tra khả năng binding và biểu diễn presence ở đúng cấp của phiên bản Spring GraphQL đang dùng; không nên giả định một Java field nullable tự giữ được thông tin này.

Một cách thiết kế khác là tránh patch mơ hồ. Ví dụ, tách thao tác xóa mô tả thành mutation rõ nghĩa hoặc dùng một input có hành động cụ thể. Cách này làm API tường minh hơn khi client cần điều khiển nhiều trạng thái cập nhật.

## 11. Bảo mật và kiểm soát dữ liệu đầu vào

Input object là ranh giới dữ liệu mà client được phép gửi. Thiết kế input cần tuân thủ nguyên tắc chỉ nhận những trường cần thiết cho use case.

Ví dụ, không nên khai báo:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  ownerId: ID
  createdAt: String
  approved: Boolean
  internalCost: Float
}
~~~

Nếu **ownerId**, **createdAt**, **approved** hoặc **internalCost** do server quản lý, client không nên được tự chỉ định chúng trong thao tác tạo sách. Server cần lấy owner từ principal đã xác thực, tạo timestamp và áp dụng quy trình phê duyệt ở backend.

Các nguyên tắc nên áp dụng:

- Chỉ khai báo field mà client thực sự cần cung cấp.
- Không bind input trực tiếp vào persistence entity có nhiều thuộc tính nhạy cảm.
- Kiểm tra quyền trên từng resource ID được truyền vào.
- Không tin các trường role, tenant hoặc owner do client tự gửi nếu chưa được xác minh.
- Giới hạn kích thước list, độ dài chuỗi và độ sâu input lồng nhau.
- Không để input object làm đường vòng thay đổi field mà người dùng không được phép sửa.
- Áp dụng transaction và kiểm tra tính nhất quán ở service layer khi mutation cập nhật nhiều bảng hoặc tài nguyên.

Schema validation giúp giới hạn hình dạng dữ liệu; authorization và business validation vẫn phải được thực hiện ở server.

## 12. Kiểm thử mutation nhận input object

Spring for GraphQL cung cấp **GraphQlTester** để thực thi operation và kiểm tra kết quả. Ví dụ:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
                status
            }
        }
        """)
    .variable("input", Map.of(
            "title", "GraphQL with Spring",
            "authorId", "author-01",
            "status", "DRAFT"))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

Có thể kiểm tra trường mặc định bằng cách bỏ **status** khỏi variables:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                status
            }
        }
        """)
    .variable("input", Map.of(
            "title", "GraphQL with Spring",
            "authorId", "author-01"))
    .execute()
    .path("createBook.status")
    .entity(String.class)
    .isEqualTo("DRAFT");
~~~

Trong test thực tế, service và repository cần được cấu hình hoặc mock theo loại test đang viết. Có thể kiểm thử thêm:

1. Input hợp lệ tạo đúng dữ liệu và trả về output object.
2. Thiếu **title** hoặc **authorId** bị schema từ chối.
3. Truyền enum không hợp lệ bị input coercion từ chối.
4. Field không tồn tại trong input object bị validation từ chối.
5. Giá trị vi phạm Bean Validation được chuyển thành lỗi phù hợp.
6. ID tham chiếu không tồn tại tạo business error có mã rõ ràng.
7. Người dùng không có quyền không thể tạo hoặc cập nhật tài nguyên của người khác.
8. Field bị bỏ qua và field truyền null có hành vi đúng với hợp đồng update.
9. Input lồng nhau và list được bind đúng, kể cả danh sách rỗng.
10. Mutation nhiều bước tuân thủ transaction và tính nhất quán dữ liệu.

## 13. Những lỗi thiết kế input object thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng object type làm field của input | Schema không hợp lệ | Dùng scalar, enum, input object hoặc ID |
| Dùng một input cho mọi mutation | Trường bắt buộc và quyền thay đổi không rõ | Tạo input riêng theo use case |
| Đưa toàn bộ entity vào input | Tăng nguy cơ mass assignment | Chỉ nhận field client được phép thay đổi |
| Đánh dấu mọi field là non-null | Client phải gửi dữ liệu không cần thiết | Phân biệt create và update |
| Không khai báo default cho giá trị ổn định | Client phải lặp lại giá trị mặc định | Dùng default ở input field hoặc argument |
| Nhầm omitted với null | Patch có thể xóa dữ liệu ngoài ý muốn | Dùng representation giữ presence khi cần |
| Chỉ dựa vào GraphQL type validation | Bỏ sót quy tắc nghiệp vụ | Kết hợp Bean Validation và service validation |
| Không giới hạn list hoặc chuỗi | Có thể nhận payload quá lớn | Giới hạn kích thước và số phần tử |
| Tin ID do client gửi | Có nguy cơ truy cập chéo tenant hoặc resource | Xác minh quyền trên resource ở server |
| Trả exception nội bộ cho client | Làm lộ thông tin triển khai | Chuẩn hóa GraphQL errors và log an toàn |

## 14. Quy trình thiết kế input object cho mutation

Khi tạo một mutation mới, có thể thực hiện theo trình tự:

1. Xác định hành động nghiệp vụ và dữ liệu tối thiểu client phải cung cấp.
2. Tạo input object riêng cho hành động, ví dụ **CreateBookInput** hoặc **UpdateBookInput**.
3. Chọn scalar, enum, input object lồng nhau, list và nullability cho từng field.
4. Xác định default value và ý nghĩa của việc bỏ qua field.
5. Dùng ID cho resource đã tồn tại thay vì nhận cả object output.
6. Khai báo mutation nhận input object và trả về output type phù hợp.
7. Bind input vào record/DTO bằng **@Argument**.
8. Áp dụng schema coercion, Bean Validation và business validation ở đúng lớp.
9. Kiểm tra authorization, mass assignment, payload size và transaction.
10. Viết GraphQlTester cho trường hợp hợp lệ, không hợp lệ, null và omitted.

Input object giúp mutation có một hợp đồng đầu vào gọn, có kiểu và dễ phát triển. Trong Spring for GraphQL, SDL xác định dữ liệu nào được phép gửi; **@Argument** bind dữ liệu thành Java object; validation và service layer quyết định dữ liệu đó có hợp lệ về nghiệp vụ hay không. Khi tách rõ ba trách nhiệm này, mutation dễ đọc, dễ kiểm thử và an toàn hơn khi API tiếp tục mở rộng.
