# Directive và authorization trong GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích directive là gì và cách directive bổ sung hành vi hoặc metadata cho GraphQL schema và operation.
- Phân biệt directive dùng trong operation với directive gắn vào schema.
- Sử dụng các directive dựng sẵn như `@include`, `@skip`, `@deprecated` và `@specifiedBy`.
- Khai báo custom directive để mô tả chính sách truy cập.
- Hiểu vì sao khai báo directive authorization trong SDL chưa tự bảo vệ dữ liệu.
- Bảo vệ Query, Mutation và nested field bằng Spring Security trong Spring for GraphQL.
- Kết hợp phân quyền theo authority, role và quyền truy cập từng đối tượng.
- Nhận biết các đường truy cập dễ bị bỏ sót qua alias, fragment, nested field và DataLoader.
- Kiểm thử hành vi authorization và xử lý lỗi mà không làm lộ dữ liệu nhạy cảm.

## 1. Directive là gì?

Directive là một thành phần của GraphQL dùng để bổ sung chỉ dẫn hoặc metadata cho schema và operation. Tên directive bắt đầu bằng ký tự `@`, theo sau là tên directive và có thể có arguments.

Directive có thể xuất hiện ở hai phạm vi chính:

- **Executable directive** được viết trong operation mà client gửi. Nó tác động đến cách một phần operation được thực thi.
- **Schema directive** được gắn vào định nghĩa type, field, argument, scalar hoặc thành phần schema khác. Nó mô tả metadata hoặc chính sách liên quan đến schema.

Ví dụ operation dùng directive:

~~~graphql
query GetBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        title
        author @include(if: $showAuthor) {
            name
        }
    }
}
~~~

Khi `showAuthor` là `true`, field `author` được đưa vào quá trình thực thi. Khi là `false`, field đó bị bỏ qua.

Ví dụ directive trên schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    oldTitle: String @deprecated(reason: "Use title instead")
}
~~~

`@deprecated` đánh dấu field `oldTitle` là không còn được khuyến nghị sử dụng. Công cụ introspection có thể hiển thị thông tin này cho client và IDE.

Directive không thay thế field hoặc type. Nó gắn thêm thông tin hoặc quy tắc vào một vị trí hợp lệ trong GraphQL document hay schema.

## 2. Cú pháp khai báo và vị trí áp dụng directive

Một directive được khai báo bằng từ khóa `directive`:

~~~graphql
directive @audit(action: String!) on FIELD_DEFINITION
~~~

Trong khai báo này:

- `@audit` là tên directive.
- `action: String!` là argument bắt buộc của directive.
- `FIELD_DEFINITION` là vị trí directive được phép gắn vào.

Một directive có thể áp dụng ở nhiều vị trí bằng cách liệt kê các location và phân tách bằng `|`:

~~~graphql
directive @example on FIELD | FRAGMENT_SPREAD | INLINE_FRAGMENT
~~~

Một số location thường gặp:

| Location | Ý nghĩa |
| --- | --- |
| `FIELD` | Field trong executable operation |
| `FRAGMENT_SPREAD` | Vị trí gọi fragment |
| `INLINE_FRAGMENT` | Inline fragment trong operation |
| `OBJECT` | Object type trong schema |
| `FIELD_DEFINITION` | Field được định nghĩa trong schema |
| `ARGUMENT_DEFINITION` | Argument của một field hoặc directive |
| `INPUT_FIELD_DEFINITION` | Field bên trong input object |
| `ENUM_VALUE` | Giá trị enum |
| `SCALAR` | Custom scalar |
| `INTERFACE` | Interface type |
| `UNION` | Union type |

Một directive chỉ được sử dụng tại các location đã khai báo. Nếu gắn directive vào vị trí không hợp lệ, schema hoặc operation sẽ không vượt qua validation.

### 2.1. Directive có arguments

Directive có thể nhận arguments giống field:

~~~graphql
directive @cacheControl(
    maxAge: Int!
    scope: CacheScope = PUBLIC
) on FIELD_DEFINITION

enum CacheScope {
    PUBLIC
    PRIVATE
}

type Query {
    publicCatalog: [Book!]! @cacheControl(maxAge: 300)
    myBooks: [Book!]! @cacheControl(maxAge: 30, scope: PRIVATE)
}
~~~

Các arguments của directive có thể có kiểu scalar, enum, list hoặc input object hợp lệ. Chúng cho phép directive biểu diễn metadata có cấu trúc.

Việc khai báo directive chỉ tạo ra hợp đồng trong schema. Runtime phải có thành phần hiểu và áp dụng ý nghĩa của directive nếu directive cần thay đổi hành vi thực thi.

## 3. Các directive dựng sẵn thường gặp

GraphQL định nghĩa một số directive chuẩn. Chúng có ý nghĩa đã được GraphQL runtime và công cụ hỗ trợ hiểu.

### 3.1. @include — chỉ đưa field vào khi điều kiện đúng

`@include(if: Boolean!)` cho phép field hoặc fragment được thực thi khi biểu thức điều kiện là `true`.

~~~graphql
query GetBook($id: ID!, $showAuthor: Boolean!) {
    book(id: $id) {
        id
        title
        author @include(if: $showAuthor) {
            id
            name
        }
    }
}
~~~

Variables:

~~~json
{
    "id": "book-42",
    "showAuthor": true
}
~~~

Khi `showAuthor` là `true`, response có thể chứa field `author`. Khi `false`, GraphQL bỏ qua field đó trong lần thực thi này.

Directive này hữu ích khi giao diện có các phần dữ liệu tùy chọn hoặc khi client muốn dùng cùng một operation cho nhiều trạng thái hiển thị.

### 3.2. @skip — bỏ qua field khi điều kiện đúng

`@skip(if: Boolean!)` có ý nghĩa ngược với `@include`: field hoặc fragment bị bỏ qua khi điều kiện là `true`.

~~~graphql
query GetBook($id: ID!, $hideReviews: Boolean!) {
    book(id: $id) {
        title
        reviews(first: 5) @skip(if: $hideReviews) {
            rating
            comment
        }
    }
}
~~~

Khi `hideReviews` là `true`, field `reviews` không được thực thi. Khi `false`, field được xử lý như bình thường.

Có thể dùng cả hai directive trong cùng operation, nhưng nên thiết kế điều kiện đơn giản để client dễ hiểu và dễ kiểm thử.

### 3.3. @deprecated — đánh dấu thành phần schema cũ

`@deprecated` đánh dấu field, argument, input field hoặc enum value không còn được khuyến nghị sử dụng.

~~~graphql
type Book {
    id: ID!
    title: String!
    name: String @deprecated(reason: "Use title instead")
}
~~~

Trong ví dụ, client nên chuyển từ `name` sang `title`. Lý do deprecation có thể được IDE hoặc công cụ introspection hiển thị.

Directive này hỗ trợ tiến hóa schema an toàn:

1. Bổ sung field hoặc argument mới.
2. Đánh dấu thành phần cũ bằng `@deprecated` và cung cấp lý do cụ thể.
3. Cập nhật client để dùng thành phần mới.
4. Theo dõi việc sử dụng thành phần cũ.
5. Chỉ xóa thành phần cũ khi đã kiểm tra tác động đến client.

`@deprecated` không tự xóa field và cũng không ngăn client tiếp tục truy vấn nó. Nó là metadata thông báo trạng thái API.

### 3.4. @specifiedBy — mô tả định dạng custom scalar

`@specifiedBy(url: String!)` gắn một URL mô tả quy tắc biểu diễn của custom scalar:

~~~graphql
scalar UUID @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc9562")

scalar DateTime @specifiedBy(url: "https://www.rfc-editor.org/rfc/rfc3339")
~~~

URL nên trỏ tới một tài liệu đặc tả có thẩm quyền và mô tả đúng định dạng mà scalar thực sự chấp nhận.

Directive này giúp công cụ và người dùng schema hiểu quy ước của scalar. Nó không tự triển khai parser, validator hoặc serializer. Ứng dụng vẫn cần đăng ký coercing implementation tương ứng.

### 3.5. Directive chuẩn và directive tùy chỉnh

Các directive như `@include`, `@skip` và `@deprecated` có ý nghĩa chuẩn. GraphQL runtime và công cụ hiểu cách xử lý chúng.

Một directive do ứng dụng định nghĩa như `@requiresRole` không tự có hành vi chỉ vì xuất hiện trong SDL. Ứng dụng phải triển khai cơ chế đọc metadata và thực thi chính sách tương ứng.

Đây là điểm đặc biệt quan trọng với authorization: tên directive nghe có vẻ bảo vệ field không đồng nghĩa field đã được bảo vệ.

## 4. Custom directive cho authorization

Một schema có thể công bố chính sách truy cập bằng custom directive. Ví dụ:

~~~graphql
enum Role {
    USER
    EDITOR
    ADMIN
}

directive @requiresRole(role: Role!) on FIELD_DEFINITION

type Report {
    id: ID!
    title: String!
}

type Query {
    publicReport: Report
    editorReport: Report @requiresRole(role: EDITOR)
    adminReport: Report @requiresRole(role: ADMIN)
}
~~~

`@requiresRole` gắn metadata về role cần có để gọi field. Nhờ vậy, người đọc schema có thể nhận biết chính sách truy cập ở ngay nơi field được khai báo.

Tuy nhiên, GraphQL không tự hiểu `@requiresRole` là quy tắc bảo mật. Nếu ứng dụng chỉ khai báo directive trong SDL mà không có runtime implementation, một client vẫn có thể gọi `adminReport` nếu field được công bố và resolver không kiểm tra quyền.

Có hai cách tiếp cận phổ biến:

- Dùng directive làm metadata rồi tích hợp với cơ chế authorization của ứng dụng, ví dụ qua GraphQL Java schema wiring hoặc DataFetcher wrapper.
- Dùng Spring Security method security trên controller hoặc service để thực thi quyền ở nơi xử lý dữ liệu; directive có thể được giữ làm tài liệu schema nếu cần.

Trong ứng dụng Spring for GraphQL, Spring Security method security thường là cách trực tiếp để bảo vệ resolver và service. Custom directive có thể bổ sung một lớp mô tả chính sách tập trung, nhưng phải bảo đảm metadata và cơ chế thực thi luôn đồng bộ.

### 4.1. Directive không thay thế authorization thực thi

Không nên xem các cách sau là biện pháp bảo mật:

- Đặt tên field là `adminOnlyData` nhưng không kiểm tra quyền.
- Đánh dấu field bằng custom directive nhưng không triển khai xử lý directive.
- Ẩn field khỏi giao diện GraphiQL nhưng vẫn để resolver truy cập được.
- Dùng `@skip` hoặc `@include` để quyết định ai được phép xem dữ liệu.
- Chỉ kiểm tra quyền ở client hoặc giao diện frontend.

Client có thể gửi operation GraphQL trực tiếp, bỏ qua giao diện. Vì vậy, server phải kiểm tra danh tính và quyền mỗi khi dữ liệu được truy cập.

## 5. Xác thực và phân quyền trong Spring for GraphQL

Hai khái niệm cần phân biệt:

- **Authentication (xác thực):** xác định người gửi request là ai.
- **Authorization (phân quyền):** quyết định người đó được phép thực hiện hành động nào hoặc truy cập dữ liệu nào.

Spring Security thường đảm nhiệm xác thực ở tầng web hoặc security filter chain. Sau khi request được xác thực, thông tin người dùng và quyền có thể được sử dụng trong quá trình gọi GraphQL controller và service.

Một ứng dụng GraphQL có thể bảo vệ nhiều cấp:

- Endpoint và transport.
- Root field trong Query hoặc Mutation.
- Nested field trên object.
- Hành động nghiệp vụ trong service.
- Từng bản ghi hoặc tài nguyên cụ thể.

Không nên chỉ bảo vệ endpoint GraphQL bằng authentication rồi giả định mọi field đều an toàn. Một người dùng đã đăng nhập vẫn có thể không được xem một field hoặc một đối tượng cụ thể.

## 6. Bật method security trong Spring

Spring Security hỗ trợ method security thông qua annotation như `@PreAuthorize`. Ứng dụng cần bật method security trong cấu hình.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Khi method security được bật, Spring có thể kiểm tra biểu thức quyền trước khi gọi method được bảo vệ.

Ví dụ bảo vệ một Query:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class ReportController {

    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public Report publicReport() {
        return reportService.getPublicReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Report adminReport() {
        return reportService.getAdminReport();
    }
}
~~~

Trong ví dụ:

- `hasAuthority('REPORT_READ')` yêu cầu người dùng có authority chính xác là `REPORT_READ`.
- `hasRole('ADMIN')` thường kiểm tra authority có tiền tố `ROLE_`, tức `ROLE_ADMIN` theo mặc định.
- Nếu điều kiện không thỏa mãn, Spring Security từ chối lời gọi method.

Các annotation phải nằm trên Spring bean được quản lý. Controller được Spring for GraphQL phát hiện và quản lý như bean, nên method security có thể áp dụng khi GraphQL runtime gọi method qua proxy Spring.

### 6.1. Phân biệt hasRole và hasAuthority

Hai biểu thức này không hoàn toàn giống nhau:

| Biểu thức | Quy tắc |
| --- | --- |
| `hasRole('ADMIN')` | Kiểm tra role với tiền tố mặc định `ROLE_` |
| `hasAuthority('REPORT_READ')` | Kiểm tra authority chính xác `REPORT_READ` |

Nếu hệ thống dùng quyền theo hành động như `BOOK_READ`, `BOOK_UPDATE`, `REPORT_EXPORT`, `hasAuthority` thường thể hiện rõ hơn.

Nếu hệ thống tổ chức theo vai trò như `ROLE_ADMIN` hoặc `ROLE_EDITOR`, `hasRole` có thể dễ đọc hơn. Cần thống nhất cách đặt tên và mapping quyền từ identity provider hoặc authentication provider.

### 6.2. Bảo vệ Mutation

Mutation thường làm thay đổi trạng thái nên cần kiểm tra quyền phù hợp:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('BOOK_CREATE')")
    public Book createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }

    @MutationMapping
    @PreAuthorize("hasAuthority('BOOK_ARCHIVE')")
    public Book archiveBook(@Argument("id") UUID id) {
        return bookService.archive(id);
    }
}
~~~

Không nên dùng chung một quyền quá rộng cho mọi mutation nếu các hành động có mức độ rủi ro khác nhau. Tách quyền theo hành động giúp chính sách dễ kiểm tra và kiểm thử.

## 7. Authorization ở cấp đối tượng

Kiểm tra role hoặc authority chỉ trả lời người dùng có quyền thực hiện một loại hành động hay không. Nhiều nghiệp vụ còn cần kiểm tra quyền trên từng đối tượng.

Ví dụ, người dùng có quyền đọc sách nói chung nhưng chỉ được xem bản nháp do chính họ tạo. Khi đó cần kiểm tra cả danh tính người dùng và chủ sở hữu của sách.

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;

@Service
class BookService {

    private final BookRepository bookRepository;

    BookService(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    @PreAuthorize("@bookAuthorization.canRead(authentication, #id)")
    public Book findReadableById(@P("id") UUID id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Trong ví dụ:

- `@bookAuthorization.canRead(...)` gọi bean kiểm tra quyền truy cập theo đối tượng.
- `authentication` là thông tin xác thực hiện tại.
- `@P("id")` đặt tên tham số rõ ràng để biểu thức method security tham chiếu được `#id`.
- Service chỉ trả dữ liệu nếu chính sách cho phép.

Controller gọi service:

~~~java
@QueryMapping
    public Book book(@Argument("id") UUID id) {
    return bookService.findReadableById(id);
}
~~~

Đưa kiểm tra vào service giúp quy tắc được áp dụng cả khi cùng service được gọi từ REST endpoint, scheduled job hoặc một luồng nghiệp vụ khác. Tuy vậy, cần xác định rõ principal và ngữ cảnh bảo mật trong từng kiểu gọi.

### 7.1. Không chỉ dựa vào ID khó đoán

UUID hoặc ID dài không thay thế authorization. Nếu client biết hoặc đoán được định danh của đối tượng, server vẫn phải kiểm tra người dùng có quyền truy cập đối tượng đó.

Đây là nguyên tắc quan trọng để tránh lỗi truy cập trực tiếp đối tượng không được phép (IDOR/BOLA). Mọi thao tác đọc, cập nhật, xóa hoặc chia sẻ tài nguyên đều cần kiểm tra quyền theo đối tượng khi nghiệp vụ yêu cầu.

## 8. Bảo vệ nested field

GraphQL cho phép client truy cập dữ liệu qua nhiều tầng field. Một root Query đã được bảo vệ không có nghĩa mọi nested field đều tự động an toàn.

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
    author: Author
}

type Author {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
}
~~~

Người dùng có thể truy vấn:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
        }
    }
}
~~~

Nếu `internalNotes` là dữ liệu chỉ dành cho biên tập viên, cần bảo vệ field đó:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Controller
class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String internalNotes(Book book) {
        return book.getInternalNotes();
    }
}
~~~

Khi GraphQL runtime resolve field `internalNotes`, Spring Security kiểm tra authority trước khi method trả dữ liệu.

Field-level authorization đặc biệt hữu ích khi một object chứa cả dữ liệu công khai và dữ liệu hạn chế. Nó cho phép client truy vấn cùng object nhưng chỉ nhận được các field mà người dùng có quyền xem.

### 8.1. Kiểm tra quyền ở service/data layer

Nếu field có thể được truy cập qua nhiều resolver hoặc nhiều API, không nên chỉ đặt kiểm tra ở một controller method. Hãy đặt quy tắc quan trọng trong service hoặc policy dùng chung để tránh một đường gọi khác bỏ qua kiểm tra.

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;

@Service
class BookDetailsService {

    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String getInternalNotes(UUID bookId) {
        return repository.findInternalNotes(bookId);
    }
}
~~~

Resolver gọi service:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookDetailsService.getInternalNotes(book.id());
}
~~~

## 9. Kết hợp custom directive và Spring Security

Nếu muốn chính sách truy cập hiển thị trực tiếp trong schema, có thể giữ custom directive như metadata:

~~~graphql
enum Permission {
    BOOK_READ
    BOOK_INTERNAL_READ
    BOOK_UPDATE
    REPORT_ADMIN
}

directive @requiresPermission(permission: Permission!)
    on FIELD_DEFINITION

type Book {
    id: ID!
    title: String!
    internalNotes: String
        @requiresPermission(permission: BOOK_INTERNAL_READ)
}

type Query {
    book(id: ID!): Book
        @requiresPermission(permission: BOOK_READ)
}
~~~

Schema cho biết field nào yêu cầu permission nào. Tuy nhiên, ứng dụng vẫn phải kết nối metadata này với cơ chế kiểm tra quyền.

Một cách triển khai ở cấp GraphQL Java là dùng schema directive wiring để đọc argument của directive và bọc DataFetcher tương ứng bằng logic authorization. Một cách khác là dùng công cụ tạo DataFetcher hoặc instrumentation để áp dụng chính sách tập trung. Với Spring for GraphQL, có thể kết nối runtime wiring thông qua các extension point như `RuntimeWiringConfigurer`.

Nếu ứng dụng đã dùng Spring Security method security, cần bảo đảm custom directive và annotation không mô tả hai chính sách khác nhau. Có thể chọn một nguồn chính sách có thẩm quyền rồi dùng cơ chế khác để kiểm tra hoặc tạo tài liệu, tránh duy trì hai bộ role độc lập.

### 9.1. Directive metadata không tự gọi Spring Security

Định nghĩa:

~~~graphql
type Query {
    adminReport: Report @requiresPermission(permission: REPORT_ADMIN)
}
~~~

không tương đương với:

~~~java
@PreAuthorize("hasAuthority('REPORT_ADMIN')")
~~~

Dòng SDL chỉ lưu thông tin directive trong schema. Annotation Spring Security mới thực sự kích hoạt method authorization khi method được gọi, với điều kiện method security đã được bật và bean đi qua proxy phù hợp.

Nếu muốn directive tự thực thi, phải viết và đăng ký phần xử lý runtime. Hãy kiểm thử rằng một người dùng không có quyền thực sự bị từ chối, thay vì chỉ kiểm tra directive có xuất hiện trong schema.

## 10. Authorization với DataLoader và batch field

Trong GraphQL, DataLoader hoặc `@BatchMapping` có thể tải nhiều đối tượng liên quan trong một batch. Điều này giúp giảm N+1 nhưng không làm mất yêu cầu authorization.

Ví dụ, một field `books` trả về nhiều sách và mỗi sách có nested field `internalNotes`. Nếu dữ liệu được tải qua batch loader, cần bảo đảm batch loader áp dụng cùng chính sách quyền như resolver đơn lẻ.

Các nguyên tắc cần giữ:

- Không dùng cache DataLoader dùng chung giữa người dùng hoặc tenant nếu kết quả phụ thuộc quyền của người gọi.
- Đảm bảo DataLoader được tạo hoặc quản lý theo request context phù hợp.
- Áp dụng tenant và user scope trong batch query.
- Không giả định root field đã kiểm tra quyền thì mọi record trong batch đều được phép trả về.
- Kiểm tra quyền trước khi đưa dữ liệu nhạy cảm vào cache có thể được dùng bởi nhiều field trong cùng request.

Nếu cùng một UUID được yêu cầu bởi hai người dùng có quyền khác nhau, cache kết quả không được chia sẻ giữa hai security context. Một cache sai phạm vi có thể làm lộ dữ liệu dù resolver ban đầu đã kiểm tra quyền đúng.

## 11. Introspection và authorization

GraphQL introspection cho phép client khám phá schema thông qua các field đặc biệt như `__schema` và `__type`. Nó giúp IDE biết các type, field, argument, directive và description mà API công bố.

Ví dụ truy vấn tên type:

~~~graphql
query InspectBookType {
    __type(name: "Book") {
        name
        fields {
            name
            type {
                name
                kind
            }
        }
    }
}
~~~

Introspection hữu ích trong phát triển và tích hợp client. Tuy nhiên, việc ẩn schema không thay thế authorization:

- Client có thể đã biết tên field từ tài liệu hoặc request cũ.
- Một field bị ẩn khỏi công cụ khám phá vẫn có thể được gọi nếu server không chặn thực thi.
- Custom directive authorization chỉ có tác dụng bảo mật nếu runtime thực sự áp dụng nó.

Một số hệ thống hạn chế introspection ở môi trường production để giảm thông tin schema công khai. Đây là quyết định về bề mặt khám phá API, không phải cơ chế kiểm tra quyền truy cập dữ liệu. Mọi resolver nhạy cảm vẫn cần authorization độc lập.

## 12. Xử lý lỗi authorization trong GraphQL

Khi Spring Security từ chối một lời gọi method, exception bảo mật có thể được chuyển thành lỗi GraphQL trong response. GraphQL có thể trả partial data nếu một field thất bại nhưng những field khác vẫn thực thi được.

Ví dụ response minh họa:

~~~json
{
    "data": {
        "book": {
            "title": "Spring GraphQL",
            "internalNotes": null
        }
    },
    "errors": [
        {
            "message": "Access is denied",
            "path": ["book", "internalNotes"]
        }
    ]
}
~~~

Thông điệp và HTTP status thực tế phụ thuộc cấu hình transport và error handling của ứng dụng. Không nên giả định mọi lỗi authorization đều làm toàn bộ GraphQL response thành HTTP 403 hoặc 500.

Một số nguyên tắc:

- Trả thông điệp đủ rõ cho client nhưng không tiết lộ quyền nội bộ hoặc cấu trúc dữ liệu nhạy cảm.
- Không phân biệt quá chi tiết giữa "đối tượng không tồn tại" và "người dùng không có quyền" nếu điều đó giúp dò tìm tài nguyên.
- Ghi log có kiểm soát với request ID, principal phù hợp và field path.
- Giữ partial data semantics của GraphQL khi phù hợp.
- Kiểm thử null propagation nếu field bị từ chối có kiểu non-null.

Nếu field nhạy cảm được khai báo non-null, việc resolver ném lỗi có thể khiến null lan lên field cha theo quy tắc GraphQL. Vì vậy, nullability cần phản ánh cả khả năng dữ liệu vắng mặt lẫn hành vi lỗi dự kiến.

## 13. Kiểm thử authorization

Authorization cần được kiểm thử qua GraphQL operation thực tế, không chỉ kiểm tra annotation có mặt trên method.

Với Spring GraphQL, có thể dùng `GraphQlTester` hoặc tester theo transport để gửi operation. Test nên xác minh ít nhất các tình huống:

| Người gọi | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Chưa xác thực | Query yêu cầu đăng nhập | Bị từ chối |
| Người dùng thường | Đọc field công khai | Thành công |
| Người dùng thường | Đọc field nội bộ | Bị từ chối |
| Editor | Đọc field biên tập | Thành công |
| Người dùng không sở hữu bản ghi | Đọc bản ghi riêng tư | Bị từ chối |
| Admin | Thực hiện thao tác quản trị | Thành công |
| Người dùng thường | Thực hiện mutation quản trị | Bị từ chối |

Ví dụ test một field bị từ chối:

~~~java
graphQlTester.document("""
        query {
            book(id: "book-42") {
                title
                internalNotes
            }
        }
        """)
        .execute()
        .errors()
        .verify();
~~~

Test này cần chạy với security context của người dùng không có authority `BOOK_INTERNAL_READ`. Nếu không thiết lập principal hoặc authentication phù hợp, test có thể đang xác minh một trường hợp khác với mục tiêu.

### 13.1. Kiểm thử cả đường truy cập gián tiếp

Một field có thể xuất hiện trong nhiều operation, fragment hoặc nested path. Nên kiểm tra:

- Truy cập field qua Query gốc.
- Truy cập field qua nested object.
- Truy cập cùng field bằng alias.
- Truy cập field thông qua fragment.
- Truy cập dữ liệu qua batch loader.
- Gọi cùng service từ một resolver khác.
- Người dùng có role nhưng không có quyền trên đối tượng cụ thể.

Alias và fragment không tạo ra một cơ chế authorization mới. Chúng chỉ thay đổi cách operation chọn field; server vẫn phải bảo vệ field và dữ liệu ở mọi đường thực thi.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Custom directive xuất hiện nhưng field vẫn truy cập được | Directive mới chỉ được khai báo, chưa có runtime enforcement | Bọc DataFetcher hoặc dùng method/service security |
| `@PreAuthorize` không có tác dụng | Chưa bật method security hoặc method không đi qua Spring proxy | Kiểm tra `@EnableMethodSecurity` và cách bean được gọi |
| Người dùng có role vẫn không đọc được | Dùng nhầm `hasAuthority`/`hasRole` hoặc authority không khớp | Kiểm tra mapping quyền và tiền tố `ROLE_` |
| Root Query được bảo vệ nhưng nested field bị lộ | Chỉ kiểm tra quyền ở root resolver | Bảo vệ nested field hoặc service trả dữ liệu nhạy cảm |
| Người dùng đọc được bản ghi của người khác | Chỉ kiểm tra role, không kiểm tra quyền theo đối tượng | Áp dụng object-level authorization |
| Dữ liệu lộ qua DataLoader cache | Cache dùng chung giữa các security context hoặc thiếu tenant scope | Giới hạn cache theo request và áp dụng permission trong batch |
| Ẩn introspection nhưng field vẫn gọi được | Nhầm khả năng khám phá schema với authorization | Bảo vệ resolver độc lập |
| Authorization error làm mất nhiều dữ liệu | Field non-null gây null propagation | Xem lại nullability và thiết kế lỗi |
| Directive và annotation mô tả chính sách khác nhau | Duy trì hai nguồn chính sách không đồng bộ | Chọn nguồn chính sách chính và kiểm thử consistency |

## 15. Quy trình thiết kế directive và authorization

Khi bổ sung directive hoặc bảo vệ một field GraphQL, hãy đi theo trình tự:

1. **Xác định ý nghĩa directive.** Directive điều khiển operation, mô tả metadata hay biểu diễn một chính sách?
2. **Chọn location hợp lệ.** Khai báo directive đúng vị trí mà nó cần áp dụng.
3. **Phân biệt metadata với enforcement.** Xác định thành phần runtime nào thực sự thực thi quy tắc.
4. **Xác định principal và permission.** Quyền đến từ Spring Security, identity provider hay policy service nào?
5. **Bảo vệ đúng tầng.** Dùng method security cho resolver/service và kiểm tra quyền theo đối tượng khi cần.
6. **Rà soát nested field và batch loading.** Đảm bảo không có đường truy cập gián tiếp bỏ qua chính sách.
7. **Xử lý lỗi có kiểm soát.** Không tiết lộ dữ liệu hoặc chi tiết nội bộ trong GraphQL errors.
8. **Kiểm thử theo từng principal.** Thử người chưa xác thực, người dùng thường, editor và admin.
9. **Kiểm tra introspection.** Quyết định mức khám phá schema phù hợp với môi trường, nhưng không dùng nó thay authorization.
10. **Theo dõi và rà soát chính sách.** Khi thêm field hoặc mutation mới, kiểm tra quyền tương ứng trước khi công bố.

## 16. Tổng kết

Directive bổ sung chỉ dẫn hoặc metadata cho GraphQL operation và schema. Các directive dựng sẵn như `@include`, `@skip`, `@deprecated` và `@specifiedBy` có ý nghĩa chuẩn. Custom directive như `@requiresRole` hoặc `@requiresPermission` có thể mô tả chính sách truy cập ngay trong SDL, nhưng chỉ có hiệu lực bảo mật khi ứng dụng triển khai runtime enforcement.

Trong Spring for GraphQL, Spring Security method security với `@PreAuthorize` có thể bảo vệ Query, Mutation, nested field và service. Authorization cần xét cả authority, role và quyền trên từng đối tượng; các đường truy cập qua fragment, alias hoặc DataLoader vẫn phải tuân thủ cùng chính sách. Introspection giúp khám phá schema nhưng không thay thế kiểm tra quyền. Kết hợp directive có ý nghĩa rõ ràng, enforcement ở server và test theo từng principal giúp API GraphQL an toàn và dễ tiến hóa.



