# Query và authorization trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao Query GraphQL vẫn cần xác thực và phân quyền dù chỉ đọc dữ liệu.
- Phân biệt bảo vệ endpoint `/graphql` với bảo vệ từng field Query.
- Dùng Spring Security method security để kiểm soát method `@QueryMapping`.
- Phân biệt `hasRole` và `hasAuthority`.
- Kiểm tra quyền truy cập theo từng đối tượng, chủ sở hữu và tenant.
- Bảo vệ dữ liệu ở nested field và service layer.
- Hiểu tác động của alias, fragment, nhiều root field và DataLoader tới authorization.
- Xử lý lỗi truy cập trong GraphQL response và kiểm soát partial data.
- Viết kiểm thử cho người dùng có quyền, không có quyền và truy cập sai phạm vi dữ liệu.

## 1. Vì sao Query cần authorization?

GraphQL Query thường được dùng để đọc dữ liệu. Tuy nhiên, dữ liệu đọc được vẫn có thể nhạy cảm: hồ sơ cá nhân, thông tin đơn hàng, báo cáo nội bộ, ghi chú biên tập hoặc dữ liệu thuộc tenant khác.

Authentication và authorization giải quyết hai câu hỏi khác nhau:

- **Authentication (xác thực):** request đến từ ai?
- **Authorization (phân quyền):** người đó được phép đọc field hoặc tài nguyên nào?

Ví dụ schema:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}

type Report {
    id: ID!
    name: String!
}

type Query {
    book(id: ID!): Book
    publicCatalog: [Book!]!
    adminReports: [Report!]!
}
~~~

Một người dùng có thể được phép xem `publicCatalog`, nhưng không được phép xem `internalNotes` hoặc `adminReports`. Vì vậy, chỉ xác thực request đã đăng nhập là chưa đủ.

Authorization cho Query cần được áp dụng tại server, ở nơi thực thi resolver hoặc truy cập dữ liệu. Không dựa vào giao diện frontend, tên field, custom directive chưa được triển khai hoặc việc ẩn nút trên màn hình để bảo vệ dữ liệu.

## 2. Hai lớp bảo vệ: endpoint và field

Một ứng dụng Spring for GraphQL thường có hai lớp kiểm soát liên quan:

1. **Endpoint/transport security:** Spring Security filter chain xác định ai được gửi request tới endpoint GraphQL, ví dụ `/graphql`.
2. **Field/method authorization:** Spring Security method security kiểm tra người gọi có quyền thực thi một Query cụ thể hoặc truy cập một tài nguyên cụ thể hay không.

Hai lớp này bổ sung cho nhau. Endpoint có thể yêu cầu người dùng đăng nhập, trong khi từng field Query áp dụng quyền chi tiết hơn.

Ví dụ, endpoint `/graphql` chỉ cho người đã xác thực truy cập. Sau đó:

- `publicCatalog` yêu cầu authority `BOOK_READ`.
- `adminReports` yêu cầu role `ADMIN`.
- `book(id)` yêu cầu quyền đọc đúng cuốn sách có ID được truyền.

Một request có thể chứa nhiều root field:

~~~graphql
query Dashboard {
    publicCatalog {
        id
        title
    }
    adminReports {
        id
        name
    }
}
~~~

Mỗi field root được resolve theo mapping riêng. Việc một field được phép chạy không đồng nghĩa field khác trong cùng operation cũng được phép chạy.

Nếu ứng dụng cho phép truy cập ẩn danh vào một số Query, có thể cấu hình endpoint cho phép request tới GraphQL và áp dụng authentication/authorization theo từng field. Nếu toàn bộ API cần đăng nhập, filter chain có thể yêu cầu authentication trước khi request tới GraphQL runtime. Hãy xác định chính sách rõ ràng ở cả hai tầng.

## 3. Bật Spring Security method security

Để sử dụng `@PreAuthorize`, ứng dụng cần bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Sau khi bật, Spring Security có thể kiểm tra biểu thức quyền trước khi gọi method được bảo vệ.

`@PreAuthorize` hoạt động thông qua Spring AOP proxy. Method phải được gọi qua Spring bean được quản lý; gọi nội bộ một method khác trên cùng object (self-invocation) có thể bỏ qua proxy và không kích hoạt kiểm tra như mong đợi.

Trong ví dụ bên dưới, controller là Spring bean được Spring for GraphQL quản lý:

~~~java
@Controller
class BookQueryControllerSimple {

    private final BookService bookService;

    BookQueryControllerSimple(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public Book book(@Argument("id") UUID id) {
        return bookService.findReadableById(id);
    }
}
~~~

Khi GraphQL runtime resolve field `Query.book`, method security kiểm tra authority `BOOK_READ`. Nếu người dùng không có quyền, method không được thực thi và Spring Security từ chối lời gọi.

## 4. Bảo vệ Query bằng @PreAuthorize

`@QueryMapping` ánh xạ một method controller vào field trên root type `Query`. Có thể kết hợp annotation này với `@PreAuthorize` để yêu cầu quyền trước khi resolver chạy.

Schema:

~~~graphql
type Report {
    id: ID!
    title: String!
}

type Query {
    publicReport: Report
    editorReport: Report
    adminReport: Report
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Controller;

@Controller
class ReportQueryController {

    private final ReportService reportService;

    ReportQueryController(ReportService reportService) {
        this.reportService = reportService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('REPORT_READ')")
    public Report publicReport() {
        return reportService.getPublicReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('EDITOR')")
    public Report editorReport() {
        return reportService.getEditorReport();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Report adminReport() {
        return reportService.getAdminReport();
    }
}
~~~

Các quy tắc:

- `hasAuthority('REPORT_READ')` kiểm tra authority có tên chính xác `REPORT_READ`.
- `hasRole('EDITOR')` kiểm tra role với tiền tố mặc định `ROLE_`, tức `ROLE_EDITOR`.
- `hasRole('ADMIN')` tương ứng với authority `ROLE_ADMIN` theo cấu hình mặc định.

Nếu ứng dụng dùng quyền theo hành động như `BOOK_READ`, `BOOK_EXPORT`, `REPORT_READ`, `hasAuthority` thường thể hiện chính sách rõ ràng. Nếu hệ thống tổ chức theo vai trò như `ROLE_EDITOR` và `ROLE_ADMIN`, `hasRole` có thể dễ đọc hơn.

Không nên dùng một quyền `ADMIN` cho mọi thao tác nếu các hành động có mức độ nhạy cảm khác nhau. Phân quyền theo mục đích giúp chính sách dễ kiểm tra và kiểm thử.

## 5. Phân biệt hasRole và hasAuthority

Hai biểu thức thường bị dùng nhầm:

| Biểu thức | Cách kiểm tra | Ví dụ authority |
| --- | --- | --- |
| `hasRole('ADMIN')` | Thêm tiền tố role mặc định `ROLE_` | `ROLE_ADMIN` |
| `hasAuthority('BOOK_READ')` | So sánh authority chính xác | `BOOK_READ` |

Ví dụ:

~~~java
@QueryMapping
@PreAuthorize("hasRole('ADMIN')")
public List<Report> adminReports() {
    return reportService.findAll();
}
~~~

Nếu principal chỉ có authority `ADMIN` mà không có `ROLE_ADMIN`, biểu thức `hasRole('ADMIN')` có thể không khớp. Có thể tùy chỉnh role prefix, nhưng cần thống nhất quy ước ở toàn hệ thống.

Không nên trộn `ROLE_ADMIN`, `ADMIN` và `BOOK_ADMIN` một cách tùy tiện. Hãy định nghĩa rõ role là nhóm người dùng, còn authority là quyền cụ thể mà resolver hoặc service cần kiểm tra.

## 6. Authorization theo từng đối tượng

Có authority đọc sách nói chung chưa chắc đã đủ để đọc mọi cuốn sách. Một người dùng có thể chỉ được xem sách do mình tạo, hoặc chỉ được truy cập dữ liệu thuộc tenant của mình.

Ví dụ, Query nhận một ID:

~~~graphql
type Query {
    book(id: ID!): Book
}
~~~

Controller:

~~~java
import org.springframework.security.core.parameters.P;
import org.springframework.security.core.Authentication;

@Controller
class BookQueryControllerWithObjectPolicy {

    private final BookService bookService;

    BookQueryControllerWithObjectPolicy(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("@bookAuthorization.canRead(authentication, #id)")
    public Book book(@Argument("id") @P("id") UUID id) {
        return bookService.findById(id);
    }
}
~~~

`@bookAuthorization.canRead(authentication, #id)` gọi bean chính sách để kiểm tra người dùng hiện tại có quyền đọc cuốn sách mang ID đó hay không. `@P("id")` cung cấp tên tham số rõ ràng cho biểu thức method security; cũng có thể cấu hình biên dịch để giữ tên tham số nếu dự án dựa vào metadata tên tham số.

Ví dụ policy bean:

~~~java
import org.springframework.security.core.Authentication;

@Component("bookAuthorization")
class BookAuthorization {

    private final BookRepository bookRepository;

    BookAuthorization(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public boolean canRead(Authentication authentication, UUID id) {
        return bookRepository.existsReadableByIdAndUsername(
                id,
                authentication.getName()
        );
    }
}
~~~

Phương thức `existsReadableByIdAndUsername` ở đây đại diện cho truy vấn kiểm tra quyền theo mô hình dữ liệu của ứng dụng. Tên repository method và quy tắc owner cần được điều chỉnh theo domain thực tế.

Với dữ liệu nhạy cảm, có thể an toàn và hiệu quả hơn nếu truy vấn dữ liệu đã giới hạn theo principal ngay từ repository, thay vì tải đối tượng bất kỳ rồi mới kiểm tra quyền. Tránh để client tự quyết định `ownerId` hoặc `tenantId` rồi coi giá trị đó là bằng chứng quyền truy cập.

## 7. Phân quyền theo tenant

Trong hệ thống multi-tenant, cùng một ID có thể chỉ tới dữ liệu thuộc một tenant cụ thể. Người dùng chỉ được truy cập dữ liệu nằm trong phạm vi tenant được xác định từ danh tính đã xác thực.

Ví dụ service lấy tenant từ principal hoặc một thành phần cung cấp thông tin người dùng hiện tại:

~~~java
@Service
class BookQueryService {

    private final BookRepository bookRepository;
    private final CurrentUser currentUser;

    BookQueryService(
            BookRepository bookRepository,
            CurrentUser currentUser) {
        this.bookRepository = bookRepository;
        this.currentUser = currentUser;
    }

    public Book findVisibleById(UUID id) {
        UUID tenantId = currentUser.tenantId();

        return bookRepository.findByIdAndTenantId(id, tenantId)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

Trong ví dụ, `tenantId` đến từ `CurrentUser`, được xây dựng dựa trên security context. Nó không đến từ argument do client tự gửi.

Nếu API có một Query nhận `tenantId` vì lý do nghiệp vụ, server vẫn phải kiểm tra người dùng có quyền truy cập tenant đó. Không dùng giá trị argument làm căn cứ duy nhất để giới hạn dữ liệu.

Giới hạn tenant ngay trong câu truy vấn dữ liệu giúp giảm nguy cơ vô tình trả nhầm record. Với thao tác đọc, có thể trả cùng một kết quả "không tìm thấy" cho record không tồn tại và record ngoài phạm vi nếu chính sách yêu cầu tránh tiết lộ sự tồn tại của tài nguyên.

## 8. Đặt authorization ở controller hay service?

Có thể bảo vệ Query ngay tại controller:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public List<Book> books() {
    return bookService.findAllVisibleToCurrentUser();
}
~~~

Cách này thể hiện rõ field Query nào cần quyền gì. Tuy nhiên, cùng service có thể được gọi từ resolver khác, REST API hoặc một luồng nghiệp vụ khác. Nếu chỉ bảo vệ ở controller, đường gọi khác có thể bỏ qua chính sách.

Với quy tắc nghiệp vụ quan trọng, nên đặt authorization ở service hoặc data access layer dùng chung:

~~~java
@Service
class BookQueryService {

    @PreAuthorize("hasAuthority('BOOK_READ')")
    public List<Book> findAllVisibleToCurrentUser() {
        return repository.findAllVisibleToCurrentUser();
    }
}
~~~

Controller gọi service:

~~~java
@QueryMapping
public List<Book> books() {
    return bookQueryService.findAllVisibleToCurrentUser();
}
~~~

Có thể bảo vệ cả hai tầng khi có lý do rõ ràng: controller thể hiện chính sách của GraphQL field, service bảo vệ nghiệp vụ được dùng chung. Tránh đặt annotation trùng lặp mà không có quy ước, vì điều đó làm khó hiểu nơi nào là nguồn chính sách thực sự.

## 9. Root Query được bảo vệ không tự động bảo vệ mọi nested field

GraphQL cho phép client truy vấn object theo nhiều tầng:

~~~graphql
query {
    book(id: "book-42") {
        title
        internalNotes
        author {
            name
            privateEmail
        }
    }
}
~~~

Giả sử `book(id)` yêu cầu `BOOK_READ`, nhưng `internalNotes` và `privateEmail` là dữ liệu hạn chế. Quyền đọc root object không đồng nghĩa người dùng được đọc mọi field con.

Cần kiểm tra quyền tại nested resolver hoặc service cung cấp dữ liệu nhạy cảm:

~~~java
@Controller
class BookDetailsController {

    private final BookDetailsService detailsService;

    BookDetailsController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_INTERNAL_READ')")
    public String internalNotes(Book book) {
        return detailsService.getInternalNotes(book.id());
    }
}
~~~

Nếu một field có thể được gọi từ nhiều nơi, bảo vệ trong service cũng cần được cân nhắc. Quy tắc quan trọng là mọi đường truy cập đến dữ liệu nhạy cảm đều phải đi qua kiểm tra quyền có hiệu lực.

## 10. Alias, fragment và nhiều root field không bỏ qua authorization

GraphQL operation có thể dùng alias để gọi cùng field nhiều lần:

~~~graphql
query CompareBooks {
    first: book(id: "book-1") {
        title
    }
    second: book(id: "book-2") {
        title
    }
}
~~~

Client cũng có thể dùng fragment:

~~~graphql
fragment BookSummary on Book {
    id
    title
}

query {
    book(id: "book-42") {
        ...BookSummary
    }
}
~~~

Alias và fragment chỉ thay đổi cách client tổ chức selection set. Chúng không thay đổi quy tắc bảo mật của resolver. Nếu method `book` có `@PreAuthorize`, mỗi lần field được thực thi đều đi qua kiểm tra tương ứng.

Tương tự, operation có thể yêu cầu nhiều root field. Mỗi resolver phải áp dụng chính sách của chính field đó; không giả định rằng một field được phép thì toàn bộ operation được phép.

## 11. DataLoader và phạm vi quyền truy cập

DataLoader giúp gom các lần tải dữ liệu liên quan thành batch để giảm N+1. Nhưng batch loading không loại bỏ authorization.

Ví dụ, nhiều sách cùng yêu cầu dữ liệu tác giả. Batch loader phải giới hạn kết quả theo cùng security context và tenant scope như truy vấn đơn lẻ.

Các nguyên tắc:

- Tạo và sử dụng DataLoader trong phạm vi request theo cơ chế Spring GraphQL cung cấp.
- Không chia sẻ cache kết quả giữa các người dùng hoặc tenant nếu dữ liệu phụ thuộc quyền.
- Đưa tenant/user scope vào batch query khi kết quả cần giới hạn theo principal.
- Không giả định root Query đã kiểm tra quyền thì mọi phần tử trong batch đều được phép trả về.
- Kiểm tra quyền trước khi dữ liệu nhạy cảm được đưa vào cache có thể tái sử dụng trong request.

Nếu cùng một ID được yêu cầu bởi hai principal có quyền khác nhau, kết quả cache không được chia sẻ giữa hai security context. Cache sai phạm vi có thể gây rò rỉ dữ liệu dù resolver đơn lẻ đã kiểm tra quyền đúng.

## 12. Xử lý lỗi authorization trong GraphQL

Khi method security từ chối lời gọi, Spring Security có thể phát sinh `AccessDeniedException`. Exception được chuyển qua cơ chế xử lý lỗi GraphQL của ứng dụng, ví dụ `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`.

Một response minh họa khi field bị từ chối:

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
            "message": "Bạn không có quyền truy cập field này",
            "path": ["book", "internalNotes"]
        }
    ]
}
~~~

GraphQL có thể trả partial data: một field bị lỗi trong khi field khác vẫn thành công. HTTP status thực tế phụ thuộc request bị chặn ở filter chain hay lỗi xảy ra trong quá trình thực thi GraphQL. Không nên giả định mọi lỗi authorization đều làm toàn bộ response thành HTTP 403.

Một số điểm cần chú ý:

- Dùng thông điệp phù hợp cho client, không tiết lộ role nội bộ, truy vấn database hoặc dữ liệu nhạy cảm.
- Ghi log có kiểm soát với request ID, principal và field path khi cần điều tra.
- Phân biệt lỗi chưa xác thực với lỗi đã xác thực nhưng không có quyền.
- Nếu field bị từ chối có kiểu non-null, lỗi có thể lan lên field cha theo quy tắc null propagation của GraphQL.
- Không trả thông tin chi tiết cho phép kẻ gọi dò xem một tài nguyên có tồn tại hay không nếu chính sách yêu cầu che giấu điều đó.

Cách ánh xạ exception và error classification phụ thuộc cấu hình Spring GraphQL của ứng dụng. Hãy kiểm tra response thực tế qua integration test thay vì giả định một HTTP status cố định.

## 13. Query bất đồng bộ và SecurityContext

Một resolver có thể trả về kiểu đồng bộ hoặc kiểu bất đồng bộ như `CompletableFuture`, `Mono` hay `Flux`. Khi dùng kiểu reactive, cần bảo đảm security context được truyền đúng qua quá trình thực thi.

Với ứng dụng reactive, bật reactive method security theo cấu hình Spring Security phù hợp, ví dụ `@EnableReactiveMethodSecurity`, và dùng cách truy cập principal dựa trên Reactor Context. Không đọc `SecurityContextHolder` theo kiểu thread-local trong một luồng reactive rồi giả định context luôn tồn tại trên thread hiện tại.

Với ứng dụng servlet và method đồng bộ, `@EnableMethodSecurity` cùng `@PreAuthorize` thường là cấu hình phù hợp. Nếu resolver chuyển công việc sang executor hoặc callback riêng, cần bảo đảm context propagation được cấu hình đúng.

Nguyên tắc chung: authorization phải được đánh giá trong đúng security context của request hiện tại, kể cả khi resolver chạy bất đồng bộ.

## 14. Kiểm thử Query authorization

Authorization nên được kiểm thử qua GraphQL operation thật. Không chỉ xác minh annotation có mặt trên method; cần kiểm tra người dùng có quyền và không có quyền nhận được kết quả khác nhau như mong đợi.

Với method security, có thể dùng `ExecutionGraphQlServiceTester` để kiểm tra GraphQL execution trực tiếp trong test thread. Cách này phù hợp khi muốn dùng `@WithMockUser` để cung cấp security context cho lời gọi resolver đồng bộ:

~~~java
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookQuerySecurityTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = ExecutionGraphQlServiceTester.create(
                executionGraphQlService
        );
    }

    @Test
    @WithMockUser(authorities = "BOOK_READ")
    void readerCanReadBook() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        title
                    }
                }
                """)
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL");
    }

    @Test
    @WithMockUser(authorities = "BOOK_WRITE")
    void writerWithoutReadPermissionIsDenied() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        title
                    }
                }
                """)
                .execute()
                .errors()
                .verify();
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình method security và dữ liệu mẫu tương ứng. Cần thêm dependency Spring Security Test để dùng `@WithMockUser`. `@WithMockUser` thiết lập security context trong test thread; vì vậy ví dụ này tập trung vào execution trực tiếp và resolver đồng bộ.

Nếu cần kiểm tra endpoint authentication và web security filter chain, hãy dùng `HttpGraphQlTester` hoặc `WebGraphQlTester` qua HTTP và cung cấp thông tin xác thực trong chính request (ví dụ Basic hoặc Bearer token theo cấu hình test). `@WithMockUser` trên test method không tự truyền principal sang một request HTTP thật chạy ở server thread khác. Execution service tester cũng không kiểm tra quy tắc bảo vệ endpoint vì nó bỏ qua web filter chain.

### 14.1. Ma trận test nên có

| Principal | Query | Kết quả mong đợi |
| --- | --- | --- |
| Chưa xác thực | Query yêu cầu đăng nhập | Bị filter chain từ chối |
| Người dùng có `BOOK_READ` | Đọc sách trong phạm vi | Thành công |
| Người dùng chỉ có `BOOK_WRITE` | Đọc sách | Bị từ chối |
| Người dùng có quyền đọc nhưng khác owner | Đọc bản ghi riêng tư | Bị từ chối hoặc không tìm thấy theo chính sách |
| Người dùng thuộc tenant A | Đọc record tenant B | Không trả dữ liệu tenant B |
| Editor | Đọc field biên tập | Thành công |
| Người dùng thường | Đọc field biên tập | Bị từ chối |
| Người dùng có quyền với một root field | Gọi thêm root field quản trị | Chỉ field được phép thành công |

Cũng nên kiểm tra alias, fragment, nested field và DataLoader để chắc chắn không có đường truy cập nào bỏ qua chính sách.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Người dùng đã đăng nhập vẫn đọc được field nhạy cảm | Chỉ bảo vệ endpoint, chưa bảo vệ resolver hoặc service | Bổ sung method/object-level authorization |
| `@PreAuthorize` không có tác dụng | Chưa bật method security hoặc lời gọi bỏ qua Spring proxy | Kiểm tra `@EnableMethodSecurity`, bean và self-invocation |
| `hasRole('ADMIN')` không khớp | Principal có `ADMIN` thay vì `ROLE_ADMIN` | Thống nhất role prefix hoặc dùng authority phù hợp |
| Người dùng có `BOOK_READ` nhưng đọc record tenant khác | Chỉ kiểm tra authority, không giới hạn dữ liệu theo tenant | Lấy tenant từ principal và lọc trong repository |
| Root Query được bảo vệ nhưng nested field bị lộ | Chỉ đặt quyền trên root resolver | Bảo vệ nested resolver hoặc service cung cấp dữ liệu |
| Alias/fragment tạo đường truy cập ngoài dự kiến | Chỉ kiểm thử một operation cụ thể | Kiểm thử cùng field qua nhiều selection set |
| DataLoader trả dữ liệu của principal khác | Cache không đúng request/security scope | Giới hạn cache theo request và tenant |
| Test luôn pass dù user không có quyền | Test không thiết lập security context hoặc không đi qua proxy/filter chain | Dùng `@WithMockUser` và đúng loại GraphQlTester |
| Field lỗi làm mất dữ liệu cha | Non-null propagation | Rà soát nullability và cách ánh xạ authorization error |

## 16. Quy trình thiết kế authorization cho Query

Khi thêm một Query mới, có thể thực hiện theo trình tự:

1. **Xác định độ nhạy dữ liệu.** Field công khai, yêu cầu đăng nhập hay chỉ dành cho một nhóm người dùng?
2. **Xác định principal.** Người dùng, tenant và quyền được lấy từ security context nào?
3. **Bảo vệ endpoint phù hợp.** Quyết định `/graphql` cho phép ẩn danh hay yêu cầu authentication.
4. **Bảo vệ resolver.** Dùng `@PreAuthorize` hoặc cơ chế method security tương ứng cho root Query.
5. **Kiểm tra quyền theo đối tượng.** Xác minh owner, tenant và quan hệ truy cập khi field nhận ID.
6. **Giới hạn truy vấn dữ liệu.** Đưa phạm vi quyền vào repository/query khi phù hợp.
7. **Rà soát nested field và batch loader.** Không để field con hoặc cache trả dữ liệu vượt quyền.
8. **Thiết kế lỗi.** Phân biệt chưa xác thực, không được phép và không tìm thấy theo chính sách công bố.
9. **Kiểm thử theo principal.** Bao gồm người dùng thường, editor, admin, owner và người khác tenant.
10. **Theo dõi thay đổi schema.** Mỗi Query mới cần được rà soát quyền trước khi đưa vào sử dụng.

## 17. Tổng kết

Query trong GraphQL chỉ đọc dữ liệu nhưng vẫn có thể làm lộ thông tin nhạy cảm. Spring Security có thể bảo vệ endpoint GraphQL ở tầng transport và bảo vệ từng `@QueryMapping` bằng method security như `@PreAuthorize`. `hasRole` kiểm tra role theo tiền tố mặc định, còn `hasAuthority` kiểm tra quyền cụ thể.

Authorization cần xét cả quyền hành động và quyền trên từng đối tượng. Với dữ liệu multi-tenant, hãy lấy tenant từ security context và giới hạn truy vấn ở server. Bảo vệ root Query không tự động bảo vệ mọi nested field; alias, fragment và DataLoader vẫn phải tuân thủ cùng chính sách. Kiểm thử qua GraphQL operation thực tế với nhiều principal giúp xác nhận dữ liệu chỉ được trả cho đúng người gọi.

