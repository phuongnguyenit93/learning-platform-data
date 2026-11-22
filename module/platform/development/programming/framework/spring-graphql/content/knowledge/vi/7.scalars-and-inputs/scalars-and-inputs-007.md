# Input object binding

## Mục tiêu

Sau bài học này, bạn có thể:

- Thiết kế input object trong GraphQL SDL cho query và mutation.
- Giải thích cách Spring for GraphQL bind dữ liệu GraphQL vào Java class, record và collection.
- Dùng @Argument để nhận input object trong annotated controller.
- Bind input lồng nhau, list, enum và các kiểu dữ liệu miền nghiệp vụ.
- Kết hợp Bean Validation để kiểm tra dữ liệu và xử lý lỗi binding.
- Phân biệt dữ liệu bị bỏ qua với null khi thiết kế mutation cập nhật từng phần.

## Input object binding là gì?

GraphQL input object là một cấu trúc dữ liệu mà client gửi vào một field, thường dùng khi query có nhiều tiêu chí hoặc mutation cần nhiều dữ liệu liên quan. Input object được khai báo bằng từ khóa input trong SDL.

Spring for GraphQL cung cấp cơ chế argument binding để chuyển dữ liệu đã được GraphQL xử lý thành các tham số Java. Với annotated controller, bạn có thể nhận input object bằng @Argument và một DTO, class hoặc record tương ứng. Nhờ đó, controller không cần tự đọc từng key trong Map rồi chuyển đổi thủ công.

Ví dụ, API tạo sách có thể nhận tiêu đề, mã tác giả và số trang:

~~~graphql
input CreateBookInput {
  title: String!
  authorId: ID!
  pageCount: Int
}

type Mutation {
  createBook(input: CreateBookInput!): Book!
}
~~~

Client gửi một mutation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

Variables:

~~~json
{
  "input": {
    "title": "Spring GraphQL Guide",
    "authorId": "author-12",
    "pageCount": 320
  }
}
~~~

GraphQL kiểm tra cấu trúc input theo schema trước khi thực thi resolver. Sau đó Spring for GraphQL bind object đầu vào thành kiểu Java mà method controller khai báo.

## Input object và object type có mục đích khác nhau

GraphQL phân biệt kiểu dùng để nhận dữ liệu với kiểu dùng để trả dữ liệu:

| Loại | Khai báo | Mục đích |
| --- | --- | --- |
| Object type | type Book { ... } | Mô tả dữ liệu có thể được truy vấn trong response |
| Input object | input CreateBookInput { ... } | Mô tả dữ liệu client có thể gửi vào field |

Input object không thể dùng object type làm field con. Nó chỉ chứa các kiểu hợp lệ cho input như scalar, enum, input object khác và các list/non-null modifier của chúng. Ví dụ sau không hợp lệ:

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

Author là object type, vì vậy không thể dùng làm field của input object. Hãy khai báo một input type riêng:

~~~graphql
input AuthorReferenceInput {
  authorId: ID!
}

input CreateBookInput {
  title: String!
  author: AuthorReferenceInput!
}
~~~

Tách input và output giúp API kiểm soát rõ dữ liệu client được phép gửi. Một object Book có thể chứa createdAt, internalStatus hoặc các field chỉ đọc; CreateBookInput chỉ nên chứa những thuộc tính mà use case tạo sách thực sự cần.

## Bind input object vào Java record

Java record phù hợp với DTO đầu vào vì nó biểu diễn dữ liệu bất biến, có constructor rõ ràng và accessor theo tên component.

~~~java
public record CreateBookInput(
        String title,
        String authorId,
        Integer pageCount) {
}
~~~

Controller nhận toàn bộ argument input:

~~~java
@Controller
public class BookMutationController {

    private final BookService bookService;

    public BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    public Book createBook(
            @Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
~~~

Tên component trong record cần tương ứng với tên field trong input object. Với schema có title, authorId và pageCount, binder ánh xạ các giá trị đó vào CreateBookInput. Kiểu Java cần tương thích với kiểu GraphQL: String thường được bind vào String, Int vào Integer hoặc int khi chắc chắn không null, và list vào collection phù hợp.

Ưu tiên kiểu tham chiếu như Integer cho field nullable. Nếu dùng int, Java không thể biểu diễn null. Với field có thể bị bỏ qua hoặc gửi null, kiểu tham chiếu giúp DTO phản ánh được dữ liệu đầu vào.

## Bind vào class Java thông thường

Bạn cũng có thể dùng class DTO thay vì record. Spring for GraphQL hỗ trợ binding thông qua constructor hoặc cơ chế property binding phù hợp với cấu trúc class.

~~~java
public class CreateBookInput {

    private String title;
    private String authorId;
    private Integer pageCount;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getAuthorId() {
        return authorId;
    }

    public void setAuthorId(String authorId) {
        this.authorId = authorId;
    }

    public Integer getPageCount() {
        return pageCount;
    }

    public void setPageCount(Integer pageCount) {
        this.pageCount = pageCount;
    }
}
~~~

Class có constructor và setter phù hợp thường thuận tiện khi DTO cần tương thích với JavaBean conventions hoặc framework validation. Với class bất biến, hãy khai báo constructor rõ ràng và bảo đảm binder có thể khớp tên tham số với input field.

Tránh tạo nhiều constructor không cần thiết khiến việc chọn constructor binding trở nên khó hiểu. DTO đầu vào nên đơn giản, có cấu trúc gần với input object và không mang logic persistence.

## Cách Spring for GraphQL thực hiện binding

Quá trình xử lý có thể hình dung qua các bước:

~~~mermaid
flowchart TD
    A[Client gửi variables hoặc literal] --> B[GraphQL parse và coerce input]
    B --> C[Kiểm tra kiểu và cấu trúc theo SDL]
    C --> D[GraphQL tạo dữ liệu argument]
    D --> E[Spring GraphQlArgumentBinder]
    E --> F[Chuyển đổi và bind vào DTO Java]
    F --> G[Annotated controller]
    G --> H[Application service]
    H --> I[Response GraphQL]
~~~

GraphQL chịu trách nhiệm kiểm tra contract của schema, chẳng hạn field bắt buộc, kiểu scalar, enum và cấu trúc input. Spring for GraphQL tiếp tục bind dữ liệu argument vào kiểu Java được khai báo trong method. Việc bind có thể cần chuyển đổi kiểu, gọi constructor hoặc gán property, tùy DTO.

Hai tầng này có thể tạo ra hai nhóm lỗi khác nhau:

- GraphQL input coercion/validation: field không tồn tại trong input type, thiếu field non-null, sai scalar hoặc enum không hợp lệ.
- Java argument binding: không thể chuyển dữ liệu sang kiểu Java đích, constructor không phù hợp hoặc lỗi khi gán property.

Khi chẩn đoán, hãy xem cả GraphQL errors và log server. Một lỗi binding có thể xảy ra trước khi method controller được gọi.

## Bind input object lồng nhau

Input object có thể chứa input object khác. Điều này hữu ích khi một mutation nhận dữ liệu có cấu trúc theo miền nghiệp vụ.

Ví dụ tạo đơn hàng gồm thông tin giao hàng và danh sách sản phẩm:

~~~graphql
input AddressInput {
  recipient: String!
  street: String!
  city: String!
  postalCode: String
}

input OrderItemInput {
  productId: ID!
  quantity: Int!
}

input CreateOrderInput {
  customerId: ID!
  shippingAddress: AddressInput!
  items: [OrderItemInput!]!
}

type Mutation {
  createOrder(input: CreateOrderInput!): Order!
}
~~~

Các record Java tương ứng:

~~~java
public record AddressInput(
        String recipient,
        String street,
        String city,
        String postalCode) {
}

public record OrderItemInput(
        String productId,
        Integer quantity) {
}

public record CreateOrderInput(
        String customerId,
        AddressInput shippingAddress,
        List<OrderItemInput> items) {
}
~~~

Controller có thể nhận DTO cấp cao nhất:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Spring for GraphQL bind các object con theo cấu trúc tương ứng. List OrderItemInput được bind thành List<OrderItemInput>; shippingAddress được bind thành AddressInput. Service có thể nhận DTO đã có cấu trúc rõ ràng và thực hiện kiểm tra nghiệp vụ như sản phẩm có tồn tại, số lượng còn hàng và địa chỉ có được hỗ trợ hay không.

Schema chỉ kiểm tra kiểu và tính hiện diện. Ví dụ quantity: Int! không đảm bảo số lượng lớn hơn 0. Điều kiện đó thuộc validation hoặc nghiệp vụ ứng dụng.

## Bind list, enum và scalar chuyên biệt

### List

Input object có thể chứa list scalar hoặc list input object:

~~~graphql
input BulkArchiveInput {
  bookIds: [ID!]!
}
~~~

Java DTO có thể dùng List<String>:

~~~java
public record BulkArchiveInput(List<String> bookIds) {
}
~~~

Với [ID!]!, list không được null và từng phần tử không được null. List rỗng vẫn có thể hợp lệ theo kiểu GraphQL; nếu nghiệp vụ yêu cầu ít nhất một phần tử, hãy thêm validation như @NotEmpty.

### Enum

Enum GraphQL là kiểu input/output hữu ích cho tập giá trị hữu hạn:

~~~graphql
enum BookStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

input BookFilterInput {
  status: BookStatus
}
~~~

Java có thể khai báo enum tương ứng:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}

public record BookFilterInput(BookStatus status) {
}
~~~

Tên enum constant cần tương thích với giá trị GraphQL. Nếu cần quy tắc chuyển đổi tên khác nhau, hãy cấu hình mapping rõ ràng và kiểm thử.

### Custom scalar

Nếu schema dùng custom scalar, Java DTO cần có kiểu đích tương thích với scalar implementation. Ví dụ scalar DateTime có thể parse thành Instant hoặc OffsetDateTime tùy thư viện scalar được chọn. Không giả định mọi custom scalar đều tự động bind vào mọi kiểu Java có vẻ tương tự; hãy kiểm tra Coercing và conversion service của ứng dụng.

## Đổi tên field khi bind với @BindParam

Đôi khi schema dùng camelCase hoặc snake_case theo quy ước API, trong khi tên thuộc tính Java theo một quy ước khác. Spring for GraphQL cung cấp @BindParam để chỉ định tên input field dùng khi bind constructor parameter hoặc property.

Ví dụ schema:

~~~graphql
input CreateCustomerInput {
  first_name: String!
  last_name: String!
}
~~~

Java record có thể giữ tên component theo camelCase:

~~~java
import org.springframework.graphql.data.BindParam;

public record CreateCustomerInput(
        @BindParam("first_name") String firstName,
        @BindParam("last_name") String lastName) {
}
~~~

Khi dùng @BindParam, hãy đặt annotation tại vị trí binder hỗ trợ trong DTO và xác minh bằng test. Đừng đổi tên field schema chỉ để khớp một class Java nếu điều đó làm API không nhất quán với các client hiện có.

## Dùng Map khi cấu trúc input thực sự linh hoạt

Trong một số trường hợp, ứng dụng cần nhận một input object có cấu trúc động. Có thể nhận argument thành Map:

~~~java
@MutationMapping
public Result configure(
        @Argument("settings") Map<String, Object> settings) {
    return configurationService.apply(settings);
}
~~~

Map linh hoạt nhưng làm mất lợi ích của DTO có kiểu tĩnh: compiler không kiểm tra key, kiểu giá trị và cấu trúc lồng nhau. Nếu schema đã xác định cấu trúc input, ưu tiên DTO hoặc record. Chỉ dùng Map khi dữ liệu thực sự mở rộng động và service có cơ chế kiểm tra allowlist, kiểu và giới hạn rõ ràng.

## Validation cho input object

Schema kiểm tra kiểu và nullability, nhưng không thay thế validation nghiệp vụ. Ví dụ:

- title không được để trống hoặc chỉ chứa khoảng trắng.
- pageCount phải lớn hơn 0.
- items phải có ít nhất một phần tử.
- quantity phải lớn hơn 0.
- địa chỉ phải có city hợp lệ theo quy tắc hệ thống.

Có thể dùng Jakarta Bean Validation trên DTO. Thêm dependency validation phù hợp với Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Định nghĩa ràng buộc trên record:

~~~java
public record CreateOrderInput(
        @NotBlank String customerId,
        @NotNull @Valid AddressInput shippingAddress,
        @NotEmpty List<@Valid OrderItemInput> items) {
}

public record AddressInput(
        @NotBlank String recipient,
        @NotBlank String street,
        @NotBlank String city,
        String postalCode) {
}

public record OrderItemInput(
        @NotBlank String productId,
        @NotNull @Positive Integer quantity) {
}
~~~

Đặt @Valid ở các field lồng nhau để validation cascade vào object con và phần tử list. Controller kích hoạt validation:

~~~java
@MutationMapping
public Order createOrder(
        @Argument("input") @Valid CreateOrderInput input) {
    return orderService.create(input);
}
~~~

Khi validation thất bại, method không nên tiếp tục thực hiện nghiệp vụ. Spring for GraphQL có thể chuyển lỗi binding/validation thành GraphQL error; ứng dụng có thể dùng exception resolver để chuẩn hóa thông điệp và mã lỗi cho client. Không trả stack trace, câu SQL hoặc dữ liệu nội bộ trong error message.

Phân biệt ba lớp kiểm tra:

| Lớp | Ví dụ | Nơi xử lý |
| --- | --- | --- |
| GraphQL schema | Field bắt buộc, kiểu Int, enum hợp lệ | GraphQL engine |
| DTO validation | Chuỗi không rỗng, số lượng dương, list không rỗng | Bean Validation |
| Business validation | Khách hàng tồn tại, sản phẩm còn hàng, người dùng có quyền đặt hàng | Application service/domain |

Không nên nhồi mọi quy tắc vào SDL hoặc DTO. Quy tắc phụ thuộc database, trạng thái hiện tại hay quyền người dùng cần được kiểm tra trong tầng nghiệp vụ.

## Nullability, default và input object

Các modifier trong SDL quyết định dữ liệu nào được phép thiếu hoặc null:

~~~graphql
input SearchBooksInput {
  keyword: String
  authorId: ID
  page: Int = 0
  size: Int! = 20
}
~~~

keyword và authorId có thể bị bỏ qua hoặc nhận null. page có default 0; nếu bị bỏ qua, GraphQL áp dụng giá trị mặc định. size là non-null nhưng có default 20, vì vậy client có thể bỏ qua nhưng không được truyền null.

Trong Java, dùng kiểu tham chiếu cho field nullable:

~~~java
public record SearchBooksInput(
        String keyword,
        String authorId,
        Integer page,
        Integer size) {
}
~~~

Nếu cần phân biệt field bị bỏ qua với explicit null, Spring for GraphQL hỗ trợ ArgumentValue<T> cho argument và các vị trí binding phù hợp. Ví dụ DTO cập nhật có thể khai báo ArgumentValue<String> subtitle để biết client muốn giữ nguyên hay xóa phụ đề. Hãy kiểm thử binding của input lồng nhau trên phiên bản Spring for GraphQL đang sử dụng; không cần wrapper cho mọi field nếu nghiệp vụ không cần phân biệt.

## Thiết kế DTO an toàn

Input object là ranh giới dữ liệu đi từ client vào hệ thống. Hãy thiết kế DTO theo use case thay vì bind thẳng vào JPA entity hoặc document lưu trữ.

Ví dụ, entity User có thể có các thuộc tính id, email, role, enabled và createdAt. Mutation cập nhật hồ sơ người dùng chỉ nên nhận những field mà người dùng được phép thay đổi:

~~~graphql
input UpdateProfileInput {
  displayName: String
  phoneNumber: String
}
~~~

DTO tương ứng:

~~~java
public record UpdateProfileInput(
        String displayName,
        String phoneNumber) {
}
~~~

Nếu bind trực tiếp vào entity, những thuộc tính nội bộ có thể vô tình trở thành một phần của contract hoặc bị cập nhật qua đường binding khác. DTO chuyên biệt giúp giới hạn dữ liệu đầu vào, làm rõ quyền sở hữu field và tránh mass assignment.

Ngoài ra:

- Không tin giá trị userId hoặc tenantId do client gửi nếu danh tính có thể lấy từ security context.
- Kiểm tra quyền trên từng object và hành động trong service.
- Giới hạn kích thước list và chuỗi để tránh request quá lớn.
- Không lưu nguyên input thô vào log nếu có thông tin nhạy cảm.
- Giữ DTO input độc lập với entity persistence để schema có thể tiến hóa theo nhu cầu API.

## Kiểm thử input object binding

Spring for GraphQL cung cấp GraphQlTester để kiểm thử operation, variables và kết quả. Ví dụ:

~~~java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                id
                title
            }
        }
        """)
    .variable("input", Map.of(
            "title", "Spring GraphQL Guide",
            "authorId", "author-12",
            "pageCount", 320))
    .execute()
    .path("createBook.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Guide");
~~~

Nên kiểm thử các trường hợp:

1. Input hợp lệ được bind vào DTO với đúng giá trị.
2. Input lồng nhau và list được bind đúng thứ tự, đúng kiểu.
3. Field optional bị bỏ qua và field explicit null được xử lý theo contract.
4. Thiếu field non-null hoặc truyền sai kiểu bị GraphQL từ chối.
5. Enum hoặc custom scalar không hợp lệ bị từ chối.
6. Bean Validation phát hiện dữ liệu không thỏa ràng buộc.
7. Business validation từ chối trạng thái không hợp lệ, ví dụ sản phẩm không tồn tại.
8. User không có quyền không thể gửi input để thay đổi dữ liệu ngoài phạm vi của họ.

Khi test lỗi, kiểm tra cả GraphQL errors và trạng thái dữ liệu sau mutation để chắc chắn thao tác thất bại không tạo side effect ngoài ý muốn.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Argument không bind được vào DTO | Tên field không khớp component/property hoặc constructor không phù hợp | So sánh SDL với DTO; dùng @BindParam khi cần |
| Field input object bị báo sai kiểu | Dùng object type thay cho input type | Khai báo input object riêng |
| Giá trị nullable gây lỗi Java | Dùng kiểu nguyên thủy cho field có thể null | Dùng kiểu tham chiếu như Integer hoặc Boolean |
| Field lồng nhau không được bind | DTO con không có constructor/property phù hợp | Kiểm tra cấu trúc DTO và kiểu collection |
| Enum không chuyển đổi được | Tên constant Java khác giá trị enum GraphQL | Đồng bộ tên hoặc cấu hình mapping rõ ràng |
| Validation không chạy | Thiếu validation dependency, thiếu @Valid hoặc thiếu cascade validation | Kiểm tra starter, annotation và @Valid trên field lồng nhau |
| Input có thể cập nhật field nội bộ | Bind trực tiếp entity hoặc DTO quá rộng | Tạo input DTO theo use case và kiểm tra quyền |

## Thực hành tổng hợp

Xây dựng mutation tạo đơn hàng theo schema CreateOrderInput ở phần input lồng nhau:

1. Tạo record AddressInput, OrderItemInput và CreateOrderInput.
2. Viết controller nhận @Argument("input") và gọi OrderService.
3. Thêm Bean Validation cho recipient, street, city, productId và quantity.
4. Kiểm tra business rule: customer phải tồn tại, sản phẩm phải còn bán và quantity phải lớn hơn 0.
5. Viết GraphQlTester test cho input hợp lệ, thiếu field bắt buộc, list rỗng, quantity âm và productId không tồn tại.
6. Kiểm tra response lỗi không làm lộ dữ liệu nội bộ và không tạo đơn hàng khi validation thất bại.

Sau khi hoàn thành, thử thay đổi tên một field SDL và cập nhật DTO bằng @BindParam. Quan sát test để hiểu rõ mối liên hệ giữa contract GraphQL và Java binding.

## Ghi nhớ

Input object mô tả cấu trúc dữ liệu client gửi vào GraphQL field. Spring for GraphQL dùng argument binder để chuyển dữ liệu đã được GraphQL kiểm tra thành Java record, class, list hoặc kiểu đích phù hợp. @Argument liên kết input với method controller; @BindParam hỗ trợ ánh xạ tên field tùy chỉnh; @Valid và Bean Validation kiểm tra ràng buộc dữ liệu. Hãy dùng DTO riêng theo use case, hỗ trợ input lồng nhau có chủ đích, phân biệt null với omitted khi cần và để service chịu trách nhiệm validation nghiệp vụ cùng phân quyền.
