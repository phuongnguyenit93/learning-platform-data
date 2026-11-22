# Test argument binding

GraphQL resolver nhận dữ liệu đầu vào qua arguments. Spring for GraphQL chuyển các giá trị đã được GraphQL kiểm tra và coercion thành tham số Java bằng `@Argument`, `@Arguments` và cơ chế argument binding. Một test tốt cần xác nhận cả hai phía: GraphQL document tuân thủ schema, và resolver nhận đúng giá trị Java mà ứng dụng mong đợi.

Argument binding có thể lỗi ở nhiều tầng. GraphQL có thể từ chối document vì thiếu argument bắt buộc hoặc truyền sai scalar; Spring có thể không bind được input object vào DTO; Bean Validation có thể phát hiện dữ liệu không hợp lệ; còn resolver có thể chạy thành công nhưng nhận sai field do tên mapping không khớp. Dùng `GraphQlTester` với document và variables thực tế giúp kiểm tra những trường hợp này qua GraphQL execution.

## 1. Argument đi từ GraphQL đến Java như thế nào?

Ví dụ schema:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

Resolver:

~~~java
@QueryMapping
public Book bookById(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Khi client gửi:

~~~graphql
query BookById($id: ID!) {
    bookById(id: $id) {
        id
        title
    }
}
~~~

GraphQL engine parse và validate document, kiểm tra variable `id`, rồi thực hiện coercion theo scalar `ID`. Spring for GraphQL bind argument `id` vào tham số Java được đánh dấu `@Argument("id")`. Sau đó resolver mới được gọi.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[GraphQL document + variables] --> B[Parse và validate]
    B --> C[Coerce arguments theo schema]
    C --> D[Spring GraphQlArgumentBinder]
    D --> E[Bind vào tham số Java / DTO]
    E --> F{Binding thành công?}
    F -->|Có| G[Invoke controller method]
    F -->|Không| H[Binding error]
    G --> I[Resolver và service]
    H --> J[GraphQL error response]
~~~

Việc kiểm tra schema và coercion diễn ra trước khi resolver chạy. Vì vậy, lỗi như thiếu argument `ID!` hoặc truyền một object vào argument `Int` thường không phải lỗi do service ném ra.

## 2. Tạo GraphQlTester cho test argument binding

Để kiểm tra binding cùng schema và controller, có thể dùng `ExecutionGraphQlServiceTester`:

~~~java
@SpringBootTest
class BookArgumentBindingTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }
}
~~~

Tester này thực thi GraphQL service trực tiếp, không đi qua HTTP transport. Nó phù hợp để kiểm tra document, schema, argument binding và resolver.

Nếu cần xác minh HTTP security filter, header hoặc request transport, dùng `HttpGraphQlTester` qua `WebTestClient`. Test ở mức GraphQL service không chứng minh HTTP layer đã xử lý request đúng.

## 3. Test một scalar argument bằng document và variable

Nên dùng GraphQL variable để truyền dữ liệu đầu vào thay vì ghép chuỗi vào document:

~~~java
graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """)
    .operationName("BookById")
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");
~~~

Test này kiểm tra được document, variable declaration, argument mapping và response. Nếu resolver nhận sai tên argument, test sẽ thất bại dù gọi service trực tiếp vẫn có thể hoạt động.

Khi muốn kiểm tra nhiều giá trị cho cùng operation, có thể tái sử dụng document và thay variable:

~~~java
graphQlTester.documentName("book-by-id")
    .variable("id", "book-01")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-01");

graphQlTester.documentName("book-by-id")
    .variable("id", "book-02")
    .execute()
    .path("bookById.id")
    .entity(String.class)
    .isEqualTo("book-02");
~~~

Document resource được đặt theo document source của tester, thường dưới `src/test/resources/graphql-test/` với phần mở rộng `.graphql`. `documentName()` hữu ích khi operation được dùng lại trong nhiều test; `document()` tiện cho operation ngắn đặt ngay trong test.

## 4. Kiểm tra kiểu scalar và coercion

GraphQL schema định nghĩa scalar cho arguments. Những scalar cơ bản thường gặp:

| GraphQL scalar | Ý nghĩa | Kiểu Java thường dùng |
| --- | --- | --- |
| `String` | Chuỗi ký tự | `String` |
| `Int` | Số nguyên 32-bit có dấu | `Integer` |
| `Float` | Số dấu phẩy động | `Double` |
| `Boolean` | Giá trị đúng/sai | `Boolean` hoặc `boolean` |
| `ID` | Định danh | Thường là `String`; có thể chuyển đổi sang kiểu khác nếu cấu hình hỗ trợ |

Ví dụ schema:

~~~graphql
type Query {
    booksByPage(page: Int!, pageSize: Int = 20): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> booksByPage(
        @Argument("page") Integer page,
        @Argument("pageSize") Integer pageSize) {
    return bookService.findPage(page, pageSize);
}
~~~

Test truyền variable:

~~~java
graphQlTester.document("""
        query BooksByPage($page: Int!, $pageSize: Int) {
            booksByPage(page: $page, pageSize: $pageSize) {
                id
            }
        }
        """)
    .variable("page", 0)
    .variable("pageSize", 10)
    .execute()
    .path("booksByPage")
    .entityList(BookView.class)
    .hasSize(10);
~~~

`Int` trong GraphQL có giới hạn 32-bit. Nếu ứng dụng cần số nguyên lớn hơn, không nên giả định GraphQL `Int` tự ánh xạ sang `Long`; hãy thiết kế custom scalar hoặc biểu diễn theo contract phù hợp.

GraphQL `ID` có semantics định danh và thường được serialize thành string. Nếu Java resolver dùng `UUID`, hãy xác nhận conversion được hỗ trợ bởi cấu hình ứng dụng và có test cho cả giá trị hợp lệ lẫn không hợp lệ.

## 5. Test enum argument

GraphQL enum là một tập giá trị được schema định nghĩa. Literal enum trong document không đặt trong dấu nháy:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

type Query {
    booksByStatus(status: BookStatus!): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> booksByStatus(@Argument("status") BookStatus status) {
    return bookService.findByStatus(status);
}
~~~

Java enum có thể dùng cùng tên constant:

~~~java
public enum BookStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

Test dùng variable:

~~~java
graphQlTester.document("""
        query BooksByStatus($status: BookStatus!) {
            booksByStatus(status: $status) {
                id
                status
            }
        }
        """)
    .variable("status", "PUBLISHED")
    .execute()
    .errors()
    .verify();
~~~

Nếu enum value không tồn tại trong schema, GraphQL từ chối input trước khi gọi resolver. Đây là lỗi coercion/validation, không phải exception nghiệp vụ từ service.

## 6. Test input object binding sang DTO

Input object giúp gom các argument liên quan thành một cấu trúc:

~~~graphql
input BookFilterInput {
    keyword: String
    status: BookStatus
    minRating: Int
}

type Query {
    searchBooks(filter: BookFilterInput): [Book!]!
}
~~~

DTO Java:

~~~java
public record BookFilterInput(
        String keyword,
        BookStatus status,
        Integer minRating) {
}
~~~

Controller:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("filter") BookFilterInput filter) {
    return bookService.search(filter);
}
~~~

Test:

~~~java
Map<String, Object> filter = Map.of(
    "keyword", "spring",
    "status", "PUBLISHED",
    "minRating", 4);

graphQlTester.document("""
        query SearchBooks($filter: BookFilterInput) {
            searchBooks(filter: $filter) {
                id
                title
            }
        }
        """)
    .variable("filter", filter)
    .execute()
    .path("searchBooks")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Test có thể được mở rộng để xác nhận từng thuộc tính được bind đúng. Khi muốn xác nhận chính xác object truyền vào service, dùng mock hoặc spy và `ArgumentCaptor` để kiểm tra `BookFilterInput`.

## 7. Constructor binding và property binding

Spring for GraphQL sử dụng cơ chế argument binder để chuyển Map dữ liệu từ GraphQL thành object Java. Việc binding có thể dựa trên constructor hoặc property access tùy kiểu object.

Các kiểu dữ liệu thường phù hợp:

- Java record với canonical constructor.
- DTO có constructor phù hợp.
- DTO mutable với setter hoặc property có thể ghi.
- Kotlin data class nếu ứng dụng dùng Kotlin và cấu hình tương ứng.

Ví dụ record:

~~~java
public record CreateBookInput(
        String title,
        String description,
        BookStatus status) {
}
~~~

Ví dụ DTO mutable:

~~~java
public class CreateBookInput {

    private String title;
    private String description;

    public CreateBookInput() {
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

Khi binding thất bại, hãy kiểm tra tên field GraphQL, tên component/constructor parameter, setter, kiểu dữ liệu và conversion service. Không đổi tên schema field chỉ để che một lỗi Java binding; trước tiên xác định contract input nào là public API và mapping nào cần điều chỉnh.

## 8. Test input object lồng nhau và list

GraphQL input object có thể chứa object khác hoặc list:

~~~graphql
input AddressInput {
    street: String!
    city: String!
    postalCode: String
}

input CreateAuthorInput {
    name: String!
    address: AddressInput!
    tags: [String!]!
}

type Mutation {
    createAuthor(input: CreateAuthorInput!): Author
}
~~~

Java DTO:

~~~java
public record AddressInput(
        String street,
        String city,
        String postalCode) {
}

public record CreateAuthorInput(
        String name,
        AddressInput address,
        List<String> tags) {
}
~~~

Test:

~~~java
Map<String, Object> input = Map.of(
    "name", "Mai",
    "address", Map.of(
        "street", "12 Nguyen Hue",
        "city", "Ho Chi Minh City",
        "postalCode", "700000"),
    "tags", List.of("java", "graphql"));

graphQlTester.document("""
        mutation CreateAuthor($input: CreateAuthorInput!) {
            createAuthor(input: $input) {
                id
                name
                address {
                    city
                }
            }
        }
        """)
    .variable("input", input)
    .execute()
    .path("createAuthor.address.city")
    .entity(String.class)
    .isEqualTo("Ho Chi Minh City");
~~~

Test này xác nhận nested map được bind thành DTO lồng nhau và list được chuyển đúng. Với input phức tạp, nên có assertion cho các field quan trọng thay vì chỉ kiểm tra response ID.

## 9. @Argument và @Arguments

`@Argument` bind một GraphQL argument cụ thể vào tham số method:

~~~java
@QueryMapping
public List<Book> books(
        @Argument("keyword") String keyword,
        @Argument("status") BookStatus status) {
    return bookService.search(keyword, status);
}
~~~

`@Arguments` bind toàn bộ arguments của field vào một object hoặc Map:

~~~java
public record BookSearchArguments(
        String keyword,
        BookStatus status,
        Integer page) {
}

@QueryMapping
public List<Book> books(@Arguments BookSearchArguments arguments) {
    return bookService.search(arguments);
}
~~~

Khi dùng `@Arguments`, tên property của DTO cần khớp tên argument trong schema. Test nên truyền nhiều argument cùng lúc để xác nhận toàn bộ object được bind, và có test khi một argument tùy chọn bị bỏ qua.

Map linh hoạt nhưng mất kiểm tra kiểu ở compile time. DTO/record giúp phát hiện mapping sai sớm hơn và làm rõ contract mà resolver nhận.

## 10. Phân biệt argument bị bỏ qua và explicit null

Với argument nullable, GraphQL phân biệt hai tình huống:

- Client không gửi argument.
- Client gửi argument với giá trị `null`.

Trong một số mutation update, hai tình huống có ý nghĩa khác nhau. Ví dụ, bỏ qua `description` nghĩa là giữ giá trị cũ; gửi `description: null` nghĩa là xóa mô tả.

Nếu method nhận trực tiếp `String`, cả hai trường hợp có thể trở thành `null` và ứng dụng không còn phân biệt được. Spring for GraphQL cung cấp `ArgumentValue<T>` để giữ trạng thái omitted:

~~~java
@MutationMapping
public Book updateBook(
        @Argument("id") String id,
        @Argument("description") ArgumentValue<String> description) {

    if (description.isOmitted()) {
        return bookService.keepDescription(id);
    }

    if (description.value() == null) {
        return bookService.clearDescription(id);
    }

    return bookService.changeDescription(id, description.value());
}
~~~

Test phải kiểm tra riêng cả ba trạng thái:

~~~java
// 1. Argument omitted: không gọi variable("description", ...).
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .execute();

// 2. Explicit null: variable có mặt và giá trị null.
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .variable("description", null)
    .execute();

// 3. Có giá trị.
graphQlTester.document(UPDATE_BOOK)
    .variable("id", "book-01")
    .variable("description", "Updated description")
    .execute();
~~~

Đây là ba request riêng biệt. Trong test thực tế, nên assert kết quả hoặc verify service nhận đúng trạng thái `ArgumentValue` tương ứng.

Nếu schema khai báo default value cho argument, GraphQL có thể áp dụng default trước khi binder nhận giá trị. Khi nghiệp vụ cần phân biệt omitted và explicit null, không nên đặt default làm mất khác biệt đó; hãy xác định default ở application layer hoặc test rõ semantics mong muốn.

## 11. Test default values

Schema có thể định nghĩa default cho argument hoặc input field:

~~~graphql
type Query {
    books(page: Int = 0, size: Int = 20): [Book!]!
}
~~~

Khi client bỏ qua `page` và `size`, GraphQL áp dụng default theo schema. Test nên kiểm tra cả trường hợp bỏ qua và trường hợp truyền giá trị khác:

~~~java
graphQlTester.document("""
        query {
            books {
                id
            }
        }
        """)
    .execute()
    .errors()
    .verify();

graphQlTester.document("""
        query Books($page: Int, $size: Int) {
            books(page: $page, size: $size) {
                id
            }
        }
        """)
    .variable("page", 2)
    .variable("size", 5)
    .execute()
    .errors()
    .verify();
~~~

Để xác nhận resolver thực sự nhận page 0 và size 20 ở trường hợp đầu, có thể verify lời gọi service hoặc kiểm tra số lượng và nội dung kết quả. Không chỉ xác nhận response không có errors vì điều đó chưa chứng minh default được bind đúng.

## 12. Test required argument và nullability

GraphQL schema dùng `!` để đánh dấu argument hoặc input field non-null:

~~~graphql
type Query {
    bookById(id: ID!): Book
}
~~~

Các trường hợp cần test:

| Input | Kết quả mong đợi |
| --- | --- |
| Không truyền id | GraphQL request/validation error |
| Truyền id = null | GraphQL coercion/validation error |
| Truyền id đúng kiểu | Resolver được gọi |
| Truyền object thay cho ID | GraphQL coercion error |

Ví dụ kiểm tra thiếu variable:

~~~java
var response = graphQlTester.document("""
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors ->
    assertThat(errors).isNotEmpty());
~~~

Test này không truyền variable `id`, vì vậy GraphQL không thể thực thi operation có required variable. Nên verify service không được gọi nếu test có mock/spy cho service.

Lỗi thiếu required argument xảy ra trước resolver. Không kỳ vọng `DataFetcherExceptionResolver` xử lý lỗi này vì DataFetcher chưa chạy.

## 13. Test input binding failure và Bean Validation

Có hai nhóm lỗi dễ bị nhầm:

- **GraphQL coercion/validation:** sai scalar, thiếu field non-null, enum không tồn tại hoặc input object có field không được schema khai báo.
- **Java binding/Bean Validation:** dữ liệu đã hợp lệ theo GraphQL schema nhưng không bind được vào kiểu Java hoặc vi phạm constraint ở application layer.

Ví dụ schema cho phép chuỗi:

~~~graphql
input CreateBookInput {
    title: String!
}
~~~

Nhưng DTO hoặc domain yêu cầu title không được để trống. GraphQL chấp nhận chuỗi rỗng vì đó vẫn là String; Bean Validation/domain validation mới quyết định giá trị này không hợp lệ.

DTO:

~~~java
public record CreateBookInput(
        @NotBlank String title) {
}
~~~

Resolver:

~~~java
@MutationMapping
public Book createBook(@Argument("input") @Valid CreateBookInput input) {
    return bookService.create(input);
}
~~~

Test cần xác nhận:

- Chuỗi hợp lệ được bind và service nhận đúng DTO.
- Chuỗi rỗng đi qua GraphQL coercion nhưng bị validation từ chối.
- Input sai kiểu bị GraphQL từ chối trước resolver.
- Error code/message được trả theo contract của ứng dụng.

Tùy cấu hình Spring và phiên bản, binding/validation exception có thể được xử lý qua `BindingResult`, `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`. Test nên xác nhận response thực tế thay vì giả định mọi lỗi đều có cùng dạng.

## 14. BindingResult và xử lý binding error

Khi cần xử lý lỗi bind trong controller, Spring for GraphQL hỗ trợ tham số `Errors` hoặc `BindingResult` đặt ngay sau tham số được bind tương ứng trong những trường hợp được hỗ trợ:

~~~java
@MutationMapping
public Book createBook(
        @Argument("input") @Valid CreateBookInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        throw new BindException(errors);
    }
    return bookService.create(input);
}
~~~

Đoạn code minh họa cách controller chuyển binding errors sang lỗi ứng dụng. Cần kiểm tra API binding và kiểu exception của phiên bản Spring for GraphQL đang dùng; không nên vừa nhận BindingResult vừa bỏ qua errors rồi tiếp tục side effect.

Trong test, gửi input có field sai để xác nhận resolver không ghi dữ liệu và response chứa lỗi validation đã được chuẩn hóa. Nếu lỗi xảy ra trước khi controller method được gọi, BindingResult không thể xử lý lỗi GraphQL parse/coercion.

## 15. Test custom scalar

Ứng dụng có thể định nghĩa custom scalar như `Date`, `DateTime`, `UUID` hoặc `Money`. Khi đó, test cần xác nhận cả literal và variable được coercion đúng theo scalar implementation.

Ví dụ schema dùng scalar Date:

~~~graphql
scalar Date

input PublicationFilter {
    publishedAfter: Date
}

type Query {
    books(filter: PublicationFilter): [Book!]!
}
~~~

Nếu scalar được cấu hình để nhận chuỗi ISO date, test truyền variable:

~~~java
Map<String, Object> filter = Map.of(
    "publishedAfter", "2026-01-01");

graphQlTester.document("""
        query Books($filter: PublicationFilter) {
            books(filter: $filter) {
                id
            }
        }
        """)
    .variable("filter", filter)
    .execute()
    .errors()
    .verify();
~~~

Thử thêm giá trị sai định dạng để xác nhận scalar từ chối input ở bước coercion và resolver không chạy. Chuỗi format cụ thể phải theo contract của custom scalar; không mặc định mọi scalar Date đều dùng cùng định dạng.

## 16. Test unknown input field

GraphQL input object chỉ chấp nhận field được schema khai báo. Ví dụ nếu `CreateBookInput` không có field `ownerId`, client gửi thêm field này phải bị từ chối:

~~~graphql
mutation {
    createBook(input: {
        title: "Spring GraphQL"
        ownerId: "user-02"
    }) {
        id
    }
}
~~~

Đây là lỗi validation/coercion của GraphQL trước khi resolver chạy. Test nên xác nhận:

- Response có errors.
- Service create không được gọi.
- Không có dữ liệu mới được lưu.

Kiểm tra này giúp phát hiện schema vô tình mở rộng input contract hoặc client gửi field không được hỗ trợ. Tuy nhiên, không nên xem việc schema loại bỏ `ownerId` là lớp authorization duy nhất; service vẫn phải gán owner từ principal đã xác thực.

## 17. Kiểm tra service nhận đúng argument

Kiểm tra response giúp xác nhận kết quả cuối cùng, nhưng đôi khi cần biết resolver truyền đúng dữ liệu vào service. Có thể dùng mock và argument captor:

~~~java
@Captor
ArgumentCaptor<BookFilterInput> filterCaptor;

// Sau khi thực thi GraphQL operation:
verify(bookService).search(filterCaptor.capture());

assertThat(filterCaptor.getValue().keyword()).isEqualTo("spring");
assertThat(filterCaptor.getValue().status()).isEqualTo(BookStatus.PUBLISHED);
assertThat(filterCaptor.getValue().minRating()).isEqualTo(4);
~~~

Ví dụ này giả định test đã cấu hình mock `bookService` và inject captor bằng Mockito. Với integration test dùng repository thật, có thể kiểm tra kết quả truy vấn và trạng thái persistence thay vì capture lời gọi.

Không nên mock mọi thứ trong tất cả test. Mock hữu ích để kiểm tra resolver mapping và input được chuyển đúng; integration test với service/repository thật cần thiết để kiểm tra conversion, query và transaction.

## 18. Test nhiều argument và alias

Một field có thể nhận nhiều argument:

~~~graphql
type Query {
    searchBooks(keyword: String, status: BookStatus, page: Int): [Book!]!
}
~~~

Resolver:

~~~java
@QueryMapping
public List<Book> searchBooks(
        @Argument("keyword") String keyword,
        @Argument("status") BookStatus status,
        @Argument("page") Integer page) {
    return bookService.search(keyword, status, page);
}
~~~

Test nên truyền đủ, thiếu các argument nullable và explicit null để xác nhận từng tham số được bind như dự kiến.

GraphQL cũng cho phép gọi cùng field nhiều lần bằng alias:

~~~graphql
query {
    published: searchBooks(status: PUBLISHED) {
        id
    }
    drafts: searchBooks(status: DRAFT) {
        id
    }
}
~~~

Hai alias tạo hai lần resolve với argument khác nhau. Test nên xác nhận mỗi nhánh nhận đúng enum và response được đặt dưới đúng alias. Điều này cũng giúp phát hiện resolver vô tình dùng state mutable dùng chung giữa các lần gọi.

## 19. Các assertion quan trọng cho argument binding

Một bộ test thực tế nên bao phủ các nhóm sau:

| Nhóm | Trường hợp |
| --- | --- |
| Scalar | String, Int, Float, Boolean, ID hợp lệ và sai kiểu |
| Enum | Enum hợp lệ, enum không tồn tại |
| Input object | DTO/record đơn giản và nested object |
| List | List scalar, list input object, phần tử null nếu schema cho phép |
| Required | Thiếu argument hoặc truyền null cho non-null |
| Optional | Bỏ qua argument, explicit null và giá trị cụ thể |
| Default | Không truyền argument có default và truyền giá trị override |
| Binding | Tên field, constructor/property, conversion |
| Validation | Bean Validation và domain constraints |
| Custom scalar | Literal/variable hợp lệ và sai định dạng |
| Security | Argument ID/tenant không thuộc principal |
| Side effect | Mutation không chạy khi input/binding/authorization lỗi |

Không cần tạo một test khổng lồ cho mọi trường hợp. Chia theo contract và hành vi giúp lỗi dễ định vị hơn.

## 20. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Tham số Java luôn null | Tên @Argument không khớp tên argument trong schema | Ghi rõ @Argument("...") và test document thật |
| DTO input không bind được | Constructor/property hoặc tên field không khớp | Kiểm tra record component, constructor và setter |
| Enum không chuyển thành Java enum | Giá trị không khớp enum schema/Java | Dùng đúng enum token và mapping |
| ID không chuyển thành UUID | Chưa có conversion phù hợp | Dùng String hoặc đăng ký conversion/scalar rõ ràng |
| Không phân biệt omitted và null | Dùng tham số nullable thông thường | Dùng ArgumentValue<T> |
| Default value không như mong đợi | Nhầm default schema với default Java | Kiểm tra schema default và test trường hợp omitted |
| Resolver không chạy khi input sai | GraphQL coercion/validation từ chối trước execution | Assert request errors và verify service không được gọi |
| Bean Validation không chạy | Thiếu @Valid/cấu hình validation phù hợp | Kiểm tra annotation và validation provider |
| Binding error bị trả như internal error | Chưa chuẩn hóa exception | Dùng BindingResult hoặc error resolver phù hợp |
| Test xanh nhưng service nhận sai object | Chỉ kiểm tra response gián tiếp | Capture argument hoặc kiểm tra service result |
| Field input lạ vẫn được lưu | Input DTO/entity cho phép mass assignment | Dùng input type allowlist và mapping tường minh |

## 21. Nguyên tắc thiết kế test argument binding

Dùng GraphQL document thật để đi qua parse, validation và coercion; truyền dữ liệu bằng variables để test gần với request của client. Dùng `@Argument` cho từng argument và `@Arguments` khi cần bind toàn bộ arguments; với input object, ưu tiên DTO/record có tên field rõ ràng và kiểm tra nested binding.

Test riêng scalar, enum, list, required/nullability, default, custom scalar và các trường hợp binding/validation thất bại. Dùng `ArgumentValue<T>` khi nghiệp vụ cần phân biệt argument bị bỏ qua với explicit null. Xác nhận resolver nhận đúng object qua response assertion hoặc argument capture, đồng thời kiểm tra service không chạy khi GraphQL từ chối input trước execution.

Với mutation, kiểm tra side effect và không cho input tự gán field nhạy cảm như owner hoặc tenant. Với authorization, dùng principal đã xác thực và thử ID/tenant không thuộc quyền. Với lỗi, phân biệt coercion/validation trước resolver với exception trong DataFetcher để assertion đúng tầng.

Test argument binding tốt chứng minh contract giữa schema và Java method: dữ liệu client gửi được kiểm tra, chuyển đổi và gắn vào đúng tham số, còn những input không hợp lệ bị từ chối trước khi gây tác động lên hệ thống.
