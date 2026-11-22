# @PreAuthorize trên resolver

GraphQL cho phép client tự chọn field trong một operation. Vì vậy, bảo vệ endpoint HTTP ở mức request là chưa đủ: một người dùng có thể được phép gọi endpoint nhưng không được phép đọc một field cụ thể, xem một quyển sách riêng tư hoặc thực hiện một mutation nhạy cảm. Spring Security cung cấp **method security** để kiểm tra quyền ngay khi resolver được gọi. Với **@PreAuthorize**, ứng dụng có thể đặt điều kiện truy cập trước khi method xử lý GraphQL field bắt đầu chạy.

Spring for GraphQL dùng annotated controller để ánh xạ method Java thành Query, Mutation, Subscription hoặc field resolver. Khi bật method security, các annotation như **@PreAuthorize** có thể bảo vệ những method này giống các Spring bean method khác. Điều đó giúp viết chính sách theo role, authority, principal và argument của field.

Bài này trình bày cách bật method security, áp dụng @PreAuthorize trên @QueryMapping, @MutationMapping và @SchemaMapping, dùng role/authority và SpEL, bảo vệ nested field, phối hợp với service layer, xử lý batch/subscription, ánh xạ AccessDeniedException thành GraphQL error và kiểm thử quyền truy cập.

## 1. Vì sao cần bảo vệ resolver?

Giả sử API có schema:

~~~graphql
type Query {
  books: [Book!]!
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  internalNotes: String
}

type Mutation {
  deleteBook(id: ID!): Boolean!
}
~~~

Một người dùng thông thường có thể đọc danh sách sách công khai, nhưng chỉ nhân viên nội bộ mới được xem internalNotes và chỉ quản trị viên mới được xóa sách.

GraphQL client có thể gửi bất kỳ selection set hợp lệ nào trong schema. Ẩn nút trên giao diện hoặc bỏ field khỏi một màn hình không ngăn client tự gửi operation khác. Server phải kiểm tra quyền tại nơi dữ liệu được truy cập.

Ví dụ operation:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    internalNotes
  }
}
~~~

Nếu chỉ bảo vệ Query.book nhưng không bảo vệ Book.internalNotes, một người dùng có quyền đọc sách có thể lấy thêm field nhạy cảm. Vì vậy cần xác định rõ quyền cho từng root resolver và từng nested field.

## 2. Bật method security

Để sử dụng @PreAuthorize, thêm Spring Security và bật method security trong cấu hình:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-security")
~~~

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Với Spring Security hiện đại, **@EnableMethodSecurity** bật pre/post annotations như @PreAuthorize và @PostAuthorize theo mặc định. Cấu hình cũ dùng @EnableGlobalMethodSecurity đã được thay thế trong các phiên bản mới.

Method security được triển khai bằng Spring AOP. Khi một method được gọi qua Spring proxy, interceptor bảo mật đánh giá expression trước khi cho phép method chạy.

Các điều kiện quan trọng:

- Controller phải là Spring bean được quản lý bởi application context.
- Method cần được gọi qua proxy để security interceptor có thể thực thi.
- Tránh đặt method được bảo vệ là private hoặc final.
- Không dựa vào self-invocation trong cùng bean để kích hoạt method security.
- Phải bật @EnableMethodSecurity; chỉ thêm annotation @PreAuthorize không tự kích hoạt cơ chế này.

## 3. Phân biệt request security và method security

Spring Security có thể kiểm soát request HTTP ở filter chain và kiểm soát lời gọi method ở application layer.

| Cơ chế | Phạm vi | Ví dụ |
|---|---|---|
| HTTP request authorization | Toàn request tới endpoint | Chỉ người dùng đã đăng nhập được gửi request tới /graphql |
| Method security | Một method cụ thể | Chỉ người có authority book:read được gọi resolver đọc sách |
| Field-level authorization | Một field trong GraphQL type | Chỉ người có authority book:notes được đọc internalNotes |
| Domain/service authorization | Một use case hoặc resource | Người dùng chỉ sửa sách thuộc tenant của họ |

Một GraphQL request có thể chọn nhiều field. Filter chain thường quyết định có cho request đi vào GraphQL endpoint hay không; method security có thể cho phép một field nhưng từ chối field khác trong cùng operation.

Không nên bỏ qua HTTP security chỉ vì đã có @PreAuthorize. Authentication, CORS, CSRF, session/token validation và request-level policy vẫn thuộc trách nhiệm của security filter chain.

## 4. Dùng hasRole và hasAuthority

@PreAuthorize nhận một Spring Expression Language (SpEL) expression.

Ví dụ chỉ quản trị viên được gọi resolver:

~~~java
@QueryMapping
@PreAuthorize("hasRole('ADMIN')")
public List<Book> allBooks() {
    return bookService.findAll();
}
~~~

**hasRole('ADMIN')** kiểm tra authority theo quy ước role prefix mặc định, thường là ROLE_ADMIN.

Nếu ứng dụng dùng authority cụ thể, có thể kiểm tra chính xác:

~~~java
@QueryMapping
@PreAuthorize("hasAuthority('book:read')")
public List<Book> books() {
    return bookService.findPublicBooks();
}
~~~

**hasAuthority('book:read')** so khớp chính xác chuỗi authority được cấp cho Authentication.

Ví dụ:

| Expression | Authority được kiểm tra |
|---|---|
| hasRole('ADMIN') | ROLE_ADMIN theo role prefix mặc định |
| hasAuthority('ROLE_ADMIN') | ROLE_ADMIN |
| hasAuthority('book:read') | book:read |
| hasAnyAuthority('book:read', 'book:admin') | Có ít nhất một authority được liệt kê |
| isAuthenticated() | Có principal đã xác thực |
| isAnonymous() | Request đang được xử lý như anonymous |

Nên chọn một quy ước role và permission thống nhất. Role thường biểu diễn nhóm trách nhiệm rộng; authority có thể biểu diễn hành động cụ thể trên tài nguyên.

## 5. Bảo vệ @QueryMapping

Ví dụ chỉ người dùng có quyền đọc sách mới gọi được query:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('book:read')")
    public List<Book> books() {
        return bookService.findVisibleBooks();
    }

    @QueryMapping
    @PreAuthorize("hasRole('ADMIN')")
    public List<Book> allBooks() {
        return bookService.findAll();
    }
}
~~~

Khi người dùng thiếu authority book:read, Spring Security từ chối method trước khi gọi bookService.findVisibleBooks().

Việc bảo vệ method giúp tránh phải viết lại kiểm tra quyền trong từng nhánh của resolver. Tuy nhiên, nếu quyền phụ thuộc vào từng book hoặc tenant, chỉ kiểm tra authority chung có thể chưa đủ; cần kiểm tra resource-specific policy ở service hoặc authorization component.

## 6. Bảo vệ @MutationMapping

Mutation thường thay đổi dữ liệu nên cần chính sách quyền rõ ràng.

~~~java
@MutationMapping
@PreAuthorize("hasAuthority('book:delete')")
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
~~~

Chỉ người có authority book:delete mới được gọi method.

Nếu quyền phụ thuộc vào sách cụ thể, có thể gọi bean kiểm tra quyền trong SpEL:

~~~java
@MutationMapping
@PreAuthorize("@bookAuthorization.canDelete(#id, authentication)")
public boolean deleteBook(@Argument("id") String id) {
    bookService.delete(id);
    return true;
}
~~~

Bean bookAuthorization có thể kiểm tra ownership, tenant hoặc policy nghiệp vụ. Điều kiện được đánh giá trước khi method deleteBook thực thi.

Ví dụ component:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookRepository bookRepository;

    public BookAuthorization(BookRepository bookRepository) {
        this.bookRepository = bookRepository;
    }

    public boolean canDelete(String bookId, Authentication authentication) {
        return bookRepository.findById(bookId)
                .filter(book -> book.getOwnerUsername()
                        .equals(authentication.getName()))
                .isPresent();
    }
}
~~~

Trong ứng dụng multi-tenant, policy cần kiểm tra cả tenant và actor. Không tin tenant ID do client tự gửi nếu nó chưa được xác minh với principal.

## 7. Dùng method arguments trong SpEL

@PreAuthorize có thể tham chiếu tham số method. Ví dụ:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(#id, authentication)")
public Book book(@Argument("id") String id) {
    return bookService.findById(id);
}
~~~

Ở đây #id là giá trị tham số Java được bind từ GraphQL argument. Spring Security cần xác định tên tham số để phân giải biến SpEL.

Để biểu thức #id hoạt động ổn định:

- Biên dịch Java với tùy chọn -parameters để giữ tên tham số, hoặc
- Dùng annotation đặt tên tham số được Spring Security hỗ trợ, chẳng hạn @P("id"), hoặc
- Dùng vị trí tham số như #p0 nếu phù hợp với convention của dự án.

Ví dụ dùng @P:

~~~java
@QueryMapping
@PreAuthorize("@bookAuthorization.canRead(#bookId, authentication)")
public Book book(
        @Argument("id") @P("bookId") String id) {
    return bookService.findById(id);
}
~~~

Tên argument GraphQL và tên tham số SpEL là hai khái niệm riêng. @Argument("id") nói Spring GraphQL lấy giá trị từ input field id; @P("bookId") đặt tên biến method parameter để SpEL tham chiếu.

Không nối chuỗi input vào SpEL expression. Expression nên được khai báo cố định trong source code; dữ liệu GraphQL chỉ được truyền qua tham số method.

## 8. Dùng principal và authentication trong SpEL

SpEL cung cấp các biến và hàm liên quan đến người dùng hiện tại:

~~~java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<Book> myBooks(Authentication authentication) {
    return bookService.findOwnedBy(authentication.getName());
}
~~~

Có thể dùng principal trong expression:

~~~java
@QueryMapping
@PreAuthorize("authentication.name == #username")
public List<Book> booksForUser(@Argument String username) {
    return bookService.findOwnedBy(username);
}
~~~

Tuy nhiên, cho phép client truyền username rồi chỉ so sánh với principal thường không cần thiết. Với query kiểu myBooks, tốt hơn là lấy actor từ Authentication trong resolver/service và không cho client chọn username.

Ví dụ:

~~~java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<Book> myBooks(Authentication authentication) {
    return bookService.findOwnedBy(authentication.getName());
}
~~~

Đối với thông tin tenant hoặc organization, hãy lấy từ principal hoặc một tenant resolver đáng tin cậy và kiểm tra quyền trước khi truy vấn.

## 9. Bảo vệ field lồng nhau bằng @SchemaMapping

Một root query có thể trả về Book, sau đó GraphQL resolve các field con. Để bảo vệ field nhạy cảm, tạo resolver tường minh và đặt @PreAuthorize trên method đó.

~~~java
@Controller
public class BookFieldController {

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('book:notes:read')")
    public String internalNotes(Book book) {
        return book.getInternalNotes();
    }
}
~~~

Schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

Client có thể đọc title nhưng không được đọc internalNotes nếu thiếu authority book:notes:read.

### Vì sao cần resolver tường minh?

GraphQL có thể dùng default property fetcher để lấy giá trị từ property hoặc getter của source object. Nếu field được resolve trực tiếp từ property mà không gọi method controller/service có proxy bảo mật, annotation @PreAuthorize không có cơ hội chạy.

Với field nhạy cảm:

1. Khai báo resolver tường minh bằng @SchemaMapping hoặc DataFetcher phù hợp.
2. Đặt method security trên method được gọi qua Spring proxy.
3. Kiểm tra quyền trước khi trả dữ liệu.
4. Không dựa vào việc client không chọn field trên UI.

Đây là lý do field-level authorization cần được thiết kế cùng schema và resolver.

## 10. Phân biệt quyền ở root field và nested field

Ví dụ:

~~~graphql
query {
  book(id: "book-01") {
    id
    title
    internalNotes
  }
}
~~~

Resolver Query.book có thể yêu cầu book:read, trong khi Book.internalNotes yêu cầu book:notes:read.

| Field | Policy ví dụ | Ý nghĩa |
|---|---|---|
| Query.book | book:read | Được đọc thông tin sách |
| Book.title | book:read hoặc public | Được xem tiêu đề |
| Book.internalNotes | book:notes:read | Được xem ghi chú nội bộ |
| Mutation.deleteBook | book:delete | Được xóa sách |

Một operation có thể thành công một phần. Ví dụ Query.book được phép nhưng nested field internalNotes bị từ chối. GraphQL response có thể giữ các field được phép trong data và thêm lỗi ở path của internalNotes.

Nếu schema khai báo field nhạy cảm là non-null, lỗi authorization có thể làm null lan lên parent object. Hãy thiết kế nullability dựa trên semantics và hành vi khi field bị từ chối.

## 11. Bảo vệ dữ liệu theo resource bằng authorization bean

Role hoặc authority chung không đủ cho mọi trường hợp. Ví dụ người dùng có quyền book:update nhưng chỉ được cập nhật sách do họ sở hữu.

Có thể đưa policy vào một bean:

~~~java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookRepository repository;

    public BookAuthorization(BookRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(String bookId, Authentication authentication) {
        return repository.findById(bookId)
                .filter(book -> book.isPublic()
                        || book.getOwnerUsername()
                                .equals(authentication.getName()))
                .isPresent();
    }

    public boolean canUpdate(String bookId, Authentication authentication) {
        return repository.findById(bookId)
                .filter(book -> book.getOwnerUsername()
                        .equals(authentication.getName()))
                .isPresent();
    }
}
~~~

Dùng trong resolver:

~~~java
@MutationMapping
@PreAuthorize("@bookAuthorization.canUpdate(#id, authentication)")
public Book updateBook(
        @Argument String id,
        @Argument UpdateBookInput input) {
    return bookService.update(id, input);
}
~~~

Authorization bean nên chứa policy rõ ràng, dễ kiểm thử. Tránh viết expression quá dài hoặc nhúng truy vấn database phức tạp trực tiếp trong annotation.

Nếu policy cần nhiều dữ liệu hoặc thao tác có side effect, hãy thực hiện ở service/domain layer thay vì gọi method phức tạp từ SpEL.

## 12. Kết hợp @PreAuthorize với service-layer security

Bảo vệ resolver giúp biểu đạt quyền ở GraphQL field. Tuy nhiên, service có thể được gọi từ REST API, scheduled job, message listener hoặc use case khác. Vì vậy, các quy tắc nghiệp vụ quan trọng nên được bảo vệ ở service/application layer nữa.

Ví dụ:

~~~java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:delete')")
    public void delete(String bookId) {
        bookRepository.deleteById(bookId);
    }
}
~~~

Resolver:

~~~java
@MutationMapping
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
~~~

Method security ở service bảo vệ use case bất kể nó được gọi từ GraphQL hay một adapter khác.

Có thể giữ @PreAuthorize ở resolver nếu cần policy riêng cho GraphQL, chẳng hạn giới hạn một field hoặc operation. Tránh lặp lại hàng loạt expression giống nhau mà không có lý do; hãy xác định policy có thẩm quyền ở service layer và dùng resolver để kiểm soát field-specific behavior.

### Lưu ý self-invocation

Method security dựa trên proxy. Nếu một method trong cùng bean gọi trực tiếp method khác bằng this.method(), lời gọi nội bộ đó có thể bỏ qua proxy và không chạy @PreAuthorize của method đích.

Tách use case được bảo vệ sang một Spring bean riêng hoặc gọi qua proxy được quản lý đúng cách. Không xem annotation là một kiểm tra tự động cho mọi lời gọi nội bộ.

## 13. @PostAuthorize và quyền dựa trên kết quả

@PreAuthorize kiểm tra trước khi method chạy. Khi policy phụ thuộc vào object được trả về, có thể dùng **@PostAuthorize**:

~~~java
@QueryMapping
@PostAuthorize(
        "returnObject == null || " +
        "returnObject.ownerUsername == authentication.name")
public Book book(@Argument String id) {
    return bookService.findById(id);
}
~~~

@PostAuthorize đánh giá sau khi method trả về. Cách này hữu ích khi cần kiểm tra owner của object vừa được tải.

Tuy nhiên, cần cân nhắc:

- Dữ liệu đã được tải trước khi policy được đánh giá.
- Không dùng @PostAuthorize để thay thế query filter tenant ở database.
- Tránh trả object nhạy cảm từ service rồi mới kiểm tra nếu có nguy cơ side effect hoặc rò rỉ qua log/cache.
- Với collection, @PostAuthorize không tự động lọc từng phần tử như một chính sách query.

Nếu có thể, lọc dữ liệu theo actor/tenant ngay trong repository/service và dùng @PreAuthorize để kiểm tra quyền gọi use case.

## 14. @PreAuthorize trên @BatchMapping

Một @BatchMapping nhận nhiều source object cùng lúc. @PreAuthorize trên method batch có thể kiểm tra quyền chung để gọi batch handler:

~~~java
@BatchMapping(typeName = "Book", field = "internalNotes")
@PreAuthorize("hasAuthority('book:notes:read')")
public Map<Book, String> internalNotes(List<Book> books) {
    return bookService.loadInternalNotes(books);
}
~~~

Nhưng một authority chung không tự kiểm tra quyền trên từng Book. Nếu người dùng chỉ được xem ghi chú của một số sách, batch handler hoặc service cần áp dụng policy theo từng source object.

Ví dụ:

~~~java
@BatchMapping(typeName = "Book", field = "internalNotes")
@PreAuthorize("isAuthenticated()")
public Map<Book, String> internalNotes(
        List<Book> books,
        Authentication authentication) {

    return bookService.loadReadableNotes(books, authentication);
}
~~~

Service cần xác định sách nào được phép đọc cho principal hiện tại và tạo kết quả đúng với từng source. Không giả định @PreAuthorize trên batch method được chạy một lần cho từng Book; method được gọi theo batch.

## 15. @PreAuthorize trên Subscription resolver

Subscription resolver được gọi khi client thiết lập stream. Có thể dùng @PreAuthorize để kiểm tra quyền mở subscription:

~~~java
@SubscriptionMapping
@PreAuthorize("hasAuthority('order:events:read')")
public Flux<OrderEvent> orderEvents(@Argument String orderId) {
    return orderEventService.eventsFor(orderId);
}
~~~

Method security kiểm tra lời gọi tạo Publisher. Với stream dài hạn, không nên mặc định quyền được kiểm tra lại mỗi khi event phát ra. Nếu quyền có thể bị thu hồi trong lúc stream mở, event source hoặc pipeline cần có cơ chế kiểm tra lại hoặc kết thúc stream.

Với dữ liệu nhạy cảm, cần kiểm tra cả:

- Người dùng có quyền đăng ký theo dõi resource hay không.
- Mỗi event có còn thuộc phạm vi người dùng được phép xem hay không.
- Tenant và principal có còn hợp lệ trong suốt vòng đời stream hay không.
- Cancellation có giải phóng listener khi client rời đi hay không.

## 16. Authentication context trong MVC và WebFlux

Spring Security cung cấp Authentication cho method security. Trong ứng dụng Servlet/MVC, security context thường được truy cập qua SecurityContextHolder theo cơ chế context của Servlet stack.

Trong WebFlux, Spring Security sử dụng Reactor Context để truyền SecurityContext theo reactive pipeline. Không nên dựa vào ThreadLocal hoặc giả định một request luôn chạy trên cùng thread.

Khi resolver trả Mono/Flux hoặc thực hiện công việc bất đồng bộ:

- Giữ reactive chain do framework quản lý.
- Không tự chuyển sang thread tùy ý rồi đọc SecurityContextHolder như thể đang ở cùng context.
- Dùng cơ chế reactive security context phù hợp khi cần lấy Authentication trong pipeline.
- Kiểm thử với đúng web stack mà ứng dụng triển khai.

Method security reactive cần cấu hình phù hợp với ứng dụng reactive; Spring Security cung cấp @EnableReactiveMethodSecurity cho reactive method security. Không nên trộn cấu hình reactive và Servlet tùy tiện trong cùng một ứng dụng.

## 17. Xử lý AccessDeniedException trong GraphQL

Khi @PreAuthorize từ chối một resolver, Spring Security có thể ném **AccessDeniedException**. Vì exception phát sinh trong lúc GraphQL đang resolve field, nó được xử lý trong GraphQL execution và có thể trở thành GraphQL error.

Có thể dùng @GraphQlExceptionHandler để chuẩn hóa response:

~~~java
@ControllerAdvice
public class GraphQlSecurityExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Bạn không có quyền truy cập trường dữ liệu này")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

Handler chỉ nên trả thông tin an toàn. Không đưa tên role, authority, expression SpEL hoặc chi tiết policy nội bộ vào message cho client.

Phân biệt hai trường hợp:

- Request bị security filter từ chối trước khi GraphQL execution bắt đầu: thường được xử lý thành HTTP 401/403 ở transport/security layer.
- Resolver bị method security từ chối trong GraphQL execution: thường được biểu diễn trong GraphQL response errors, có path tới field liên quan.

Nếu operation chọn nhiều field, một field bị từ chối không nhất thiết làm mất toàn bộ data. Kết quả còn phụ thuộc nullability của field và các parent field trong schema.

## 18. Field authorization và nullability

Schema:

~~~graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

internalNotes nullable. Nếu người dùng không được phép xem field này, GraphQL có thể trả null cho field và thêm error.

Nếu schema khai báo:

~~~graphql
type Book {
  id: ID!
  internalNotes: String!
}
~~~

Khi resolver field non-null bị từ chối và trả lỗi, GraphQL không thể giữ null ở field đó. Null có thể lan lên Book object và tiếp tục lan theo các parent field non-null.

Do đó, khi thiết kế field nhạy cảm:

- Chọn nullability phù hợp với semantics và khả năng authorization failure.
- Kiểm tra partial data trong response.
- Không biến quyền truy cập bị từ chối thành giá trị mặc định giả.
- Cân nhắc ẩn field hoặc trả cùng một response cho not found/forbidden nếu cần tránh tiết lộ resource tồn tại.

## 19. Kiểm thử @PreAuthorize trên resolver

Có thể dùng **@WithMockUser** để kiểm thử với Authentication giả lập và **GraphQlTester** để gửi operation.

Ví dụ người dùng có quyền:

~~~java
@SpringBootTest
class BookResolverSecurityTest {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    @WithMockUser(authorities = "book:read")
    void shouldAllowBookQuery() {
        graphQlTester.document("""
                query {
                    books {
                        id
                        title
                    }
                }
                """)
            .execute()
            .path("books")
            .entityList(Book.class)
            .hasSize(1);
    }
}
~~~

Ví dụ giả định test fixture có sẵn một quyển sách.

Ví dụ người dùng thiếu quyền:

~~~java
@Test
@WithMockUser(authorities = "book:write")
void shouldRejectBookQuery() {
    graphQlTester.document("""
            query {
                books {
                    id
                    title
                }
            }
            """)
        .execute()
        .errors()
        .expect()
        .message("Bạn không có quyền truy cập trường dữ liệu này")
        .verify();
}
~~~

Test trên giả định ứng dụng có @GraphQlExceptionHandler ánh xạ AccessDeniedException thành message như ví dụ trước.

Nên kiểm thử:

1. Người dùng có authority được phép gọi resolver.
2. Người dùng thiếu authority bị từ chối trước khi service được gọi.
3. hasRole và hasAuthority khớp đúng convention.
4. SpEL tham chiếu đúng argument name.
5. Resource owner được phép, người khác bị từ chối.
6. Nested field nhạy cảm bị chặn dù root query được phép.
7. Alias và nested selection vẫn tạo error path đúng.
8. Mutation không thực hiện side effect khi bị từ chối.
9. Batch mapping kiểm tra quyền theo từng source khi cần.
10. Subscription kiểm tra quyền lúc mở stream và theo event nếu policy yêu cầu.
11. Reactive resolver giữ Authentication context.
12. Request bị chặn ở filter chain được phân biệt với field error trong GraphQL response.

Đối với integration test qua HTTP, dùng tester tương ứng với transport để xác minh filter chain, CSRF, authentication header/cookie và response status. GraphQlTester ở execution layer tập trung vào GraphQL execution và không tự chứng minh mọi cấu hình HTTP security.

## 20. Những lỗi thường gặp khi bảo vệ resolver

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @PreAuthorize không chạy | Chưa bật @EnableMethodSecurity | Bật method security trong configuration |
| Role hợp lệ vẫn bị từ chối | Nhầm ROLE_ prefix hoặc dùng hasAuthority sai chuỗi | Kiểm tra authority thực tế và chọn hasRole/hasAuthority |
| SpEL không tìm thấy #id | Tên tham số không được giữ hoặc không khai báo | Bật -parameters, dùng @P hoặc #p0 |
| Root query được bảo vệ nhưng nested field vẫn lộ | Field dùng default property fetcher | Tạo resolver tường minh và đặt method security |
| Service method có annotation nhưng không chạy | Self-invocation bỏ qua proxy | Tách method sang bean khác hoặc gọi qua proxy |
| Người dùng có quyền chung đọc được mọi resource | Chỉ kiểm tra authority, thiếu ownership/tenant policy | Kiểm tra resource trong authorization bean/service |
| Batch mapping chỉ kiểm tra một lần | Hiểu nhầm @PreAuthorize chạy cho từng source | Kiểm tra policy theo từng object trong batch service |
| Subscription tiếp tục gửi dữ liệu sau revoke | Quyền chỉ được kiểm tra khi tạo Publisher | Recheck theo event hoặc kết thúc stream |
| AccessDenied lộ chi tiết nội bộ | Trả exception message hoặc expression | Map sang message/code công khai |
| Field bị null lan lên parent | Non-null propagation | Xem lại nullability và error handling |
| Reactive resolver mất security context | Dựa vào ThreadLocal hoặc mất Reactor Context | Dùng reactive security context propagation |
| Test báo denied dù method đúng | Mock user thiếu authority hoặc test không thiết lập context | Kiểm tra @WithMockUser và test stack |

## 21. Quy trình triển khai @PreAuthorize trên resolver

Khi bảo vệ GraphQL field:

1. Liệt kê field và mutation cần bảo vệ trong schema.
2. Xác định policy: role, authority, ownership, tenant hoặc trạng thái domain.
3. Thêm Spring Security và bật @EnableMethodSecurity.
4. Đặt @PreAuthorize trên @QueryMapping, @MutationMapping hoặc @SchemaMapping phù hợp.
5. Dùng hasRole cho role và hasAuthority cho permission cụ thể.
6. Chỉ tham chiếu method argument trong SpEL khi tên tham số được Spring Security phân giải ổn định.
7. Dùng authorization bean cho policy theo resource; tránh expression quá phức tạp.
8. Tạo resolver tường minh cho field nhạy cảm thay vì dựa vào default property fetcher.
9. Đặt quy tắc nghiệp vụ quan trọng ở service layer để bảo vệ các entry point khác.
10. Với batch và subscription, kiểm tra quyền theo từng resource hoặc từng event khi cần.
11. Chuẩn hóa AccessDeniedException thành GraphQL error an toàn.
12. Kiểm thử cả quyền được phép, quyền bị từ chối, nested fields, mutation side effects và transport security.

@PreAuthorize trên resolver cho phép kiểm tra quyền ngay trước khi Spring for GraphQL thực thi một field hoặc operation. Method security cần được bật bằng @EnableMethodSecurity và method phải được gọi qua Spring proxy. Hãy kết hợp role/authority với policy theo resource, bảo vệ cả nested field bằng resolver tường minh và giữ quy tắc domain ở service layer. Với batch hoặc subscription, một lần kiểm tra method không thay thế authorization theo từng object/event. Cuối cùng, chuẩn hóa AccessDeniedException thành GraphQL error an toàn và kiểm thử cả partial data lẫn side effect để bảo đảm client chỉ nhận dữ liệu được phép.
