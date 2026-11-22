# Authorization ở controller trong Spring for GraphQL

GraphQL thường cung cấp một endpoint HTTP duy nhất, nhưng endpoint đó có thể thực thi nhiều query, mutation và field lồng nhau với mức độ nhạy cảm khác nhau. Vì vậy, chỉ xác thực request ở `/graphql` chưa đủ để bảo vệ từng thao tác. Spring for GraphQL cho phép kết hợp annotated controller với Spring Security method security để kiểm tra quyền ngay tại method xử lý GraphQL field.

Các annotation như `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` và `@BatchMapping` xác định method nào phân giải field trong schema. Khi bật method security, có thể đặt `@PreAuthorize` trên chính method đó để giới hạn ai được gọi field. Cách này tạo một ranh giới authorization rõ ràng ở lớp GraphQL controller, đồng thời service vẫn cần bảo vệ quy tắc nghiệp vụ nếu use case được gọi từ nhiều adapter khác.

Sau bài này, bạn có thể:

- Phân biệt xác thực endpoint HTTP với authorization tại GraphQL controller.
- Bật Spring Security method security cho annotated controller.
- Dùng `@PreAuthorize` trên query, mutation và nested field mapping.
- Kiểm tra quyền theo authority, role, resource ID và quyền sở hữu.
- Bảo vệ `@BatchMapping` và các field nhạy cảm.
- Hiểu cách authorization exception xuất hiện trong GraphQL response.
- Kiểm thử controller authorization bằng `GraphQlTester` và Spring Security test support.

## 1. Vì sao cần authorization ở controller?

Một HTTP endpoint GraphQL có thể phục vụ nhiều field:

```graphql
type Query {
    books: [Book!]!
    book(id: ID!): Book
    adminReport: AdminReport!
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
    deleteBook(id: ID!): Boolean!
}
```

Người dùng có thể được phép đọc danh sách sách nhưng không được xem báo cáo quản trị hoặc xóa sách. Nếu chỉ bảo vệ `/graphql` bằng một quy tắc `authenticated()`, tất cả người đã đăng nhập đều có thể gửi bất kỳ field nào mà schema công bố.

Authorization ở controller gắn policy với method xử lý từng field:

- `books` yêu cầu quyền đọc sách.
- `adminReport` yêu cầu quyền quản trị.
- `createBook` yêu cầu quyền tạo sách.
- `deleteBook` yêu cầu quyền xóa sách.

Client có thể gửi GraphQL document trực tiếp, tự đặt alias hoặc dùng fragment. Việc ẩn nút trên giao diện không phải là authorization. Server phải kiểm tra quyền mỗi khi field được thực thi.

## 2. Phân biệt HTTP security và GraphQL field authorization

Spring Security có thể bảo vệ endpoint `/graphql` ở tầng HTTP:

```java
@Configuration
public class HttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
```

Quy tắc này yêu cầu người gọi phải đăng nhập trước khi request đến GraphQL handler. Nó không phân biệt field nào được phép chạy trong GraphQL document.

Authorization ở controller dùng method security:

```java
@QueryMapping
@PreAuthorize("hasAuthority('BOOK_READ')")
public List<BookView> books() {
    return bookService.findAll();
}
```

Hai lớp có mục đích khác nhau:

| Lớp bảo vệ | Kiểm tra | Ví dụ |
| --- | --- | --- |
| HTTP Security | Request có được đi vào endpoint không? | Người dùng phải đăng nhập để gọi `/graphql` |
| Controller method security | Caller có quyền gọi field/operation cụ thể không? | Chỉ authority `BOOK_READ` được gọi `books` |
| Service/domain authorization | Caller có được thao tác trên resource cụ thể không? | Chỉ chủ sở hữu hoặc quản trị viên được sửa sách đó |

Một hệ thống có thể dùng cả ba lớp. Endpoint có thể yêu cầu xác thực chung, controller kiểm tra quyền theo field và service kiểm tra quyền theo từng resource.

## 3. Bật method security

Với ứng dụng Spring MVC/Servlet, bật method security bằng `@EnableMethodSecurity`:

```java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

Sau khi bật, Spring Security xử lý các annotation như `@PreAuthorize` và `@PostAuthorize` trên Spring bean thông qua proxy/AOP. Controller annotated của Spring for GraphQL cũng là Spring bean, nên có thể đặt method security annotation trực tiếp trên method mapping.

Với ứng dụng reactive sử dụng WebFlux và reactive method security, cấu hình `@EnableReactiveMethodSecurity` và giữ các method được bảo vệ trong kiểu trả về reactive như `Mono` hoặc `Flux`:

```java
@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Chọn cấu hình phù hợp với web stack và kiểu xử lý của ứng dụng. Không giả định cấu hình method security kiểu imperative tự động thay thế cấu hình reactive.

Method security hoạt động qua proxy. Vì vậy, method được bảo vệ cần được gọi qua Spring bean proxy. Tránh self-invocation: một method trong cùng class gọi trực tiếp method khác trong chính instance đó có thể bỏ qua proxy và không kích hoạt interceptor bảo mật.

## 4. Bảo vệ Query bằng @PreAuthorize

Ví dụ controller có query lấy danh sách và query lấy chi tiết sách:

```java
@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public List<BookView> books() {
        return bookService.findAll();
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public BookView book(@Argument String id) {
        return bookService.findById(id);
    }
}
```

`@QueryMapping` ánh xạ method vào field cùng tên trên root type `Query`. `@PreAuthorize` được đánh giá trước khi method chạy. Nếu caller thiếu authority `BOOK_READ`, Spring Security từ chối lời gọi và method không thực thi phần thân.

Có thể dùng tên mapping tường minh nếu method Java khác tên field GraphQL:

```java
@QueryMapping(name = "book")
@PreAuthorize("hasAuthority('BOOK_READ')")
public BookView findBook(@Argument("id") String bookId) {
    return bookService.findById(bookId);
}
```

Authorization được gắn với method resolver, nên vẫn áp dụng khi client gọi field qua alias hoặc fragment. Alias chỉ thay response key; nó không tạo một đường gọi khác để bỏ qua method security.

## 5. Bảo vệ Mutation

Mutation thay đổi trạng thái nên thường cần authority riêng:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_CREATE')")
public BookView createBook(@Argument("input") CreateBookInput input) {
    return bookService.create(toCommand(input));
}

@MutationMapping
@PreAuthorize("hasAuthority('BOOK_DELETE')")
public boolean deleteBook(@Argument String id) {
    bookService.delete(id);
    return true;
}
```

Người có `BOOK_READ` không mặc nhiên có `BOOK_CREATE` hoặc `BOOK_DELETE`. Tách authority theo hành động giúp policy rõ ràng và dễ kiểm thử.

Method security chạy khi field resolver được gọi. GraphQL thực thi các top-level mutation field theo thứ tự trong operation, nhưng mỗi field vẫn phải tự kiểm tra quyền. Không giả định caller có quyền thực hiện field thứ hai chỉ vì field thứ nhất đã được phép.

## 6. Bảo vệ nested field bằng @SchemaMapping

Authorization không chỉ áp dụng cho root query/mutation. Một object có thể chứa field nhạy cảm chỉ một số nhóm người dùng được xem:

```graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
```

Resolver field `internalNotes` có thể được bảo vệ riêng:

```java
@Controller
public class BookFieldController {

    private final BookAuditService bookAuditService;

    public BookFieldController(BookAuditService bookAuditService) {
        this.bookAuditService = bookAuditService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    @PreAuthorize("hasAuthority('BOOK_AUDIT_READ')")
    public String internalNotes(BookView book) {
        return bookAuditService.internalNotes(book.id());
    }
}
```

Caller có thể đọc `Book.id` và `Book.title` nhưng không có quyền đọc `internalNotes`. Khi field nhạy cảm được chọn, method security kiểm tra authority trước khi gọi service.

Nếu field có thể được đọc qua nhiều đường khác nhau, hãy bảo đảm tất cả resolver/service cung cấp dữ liệu đó đều có policy phù hợp. Không dựa vào việc UI không hiển thị field hoặc client không biết tên field.

## 7. Bảo vệ @BatchMapping

`@BatchMapping` xử lý field cho một nhóm source object. Có thể đặt method security trực tiếp trên batch method:

```java
@BatchMapping(typeName = "Book", field = "author")
@PreAuthorize("hasAuthority('BOOK_READ')")
public Map<BookView, AuthorView> author(List<BookView> books) {
    return authorService.findForBooks(books);
}
```

Ở đây authority được kiểm tra khi batch method được gọi. Vì một lần gọi có thể xử lý nhiều source object, annotation này bảo vệ cả batch invocation. Nó không tự kiểm tra quyền sở hữu của từng sách hoặc từng tác giả.

Nếu quyền phụ thuộc tenant, owner hoặc trạng thái từng resource, service cần lọc/kiểm tra từng source-target trong batch. Ví dụ truy vấn bulk phải giới hạn tenant từ security context đã xác thực; không được lấy tenant ID từ một argument client không đáng tin rồi dùng làm policy.

Nếu một phần tử không được phép xem, quyết định trả null, bỏ field, hay từ chối toàn bộ batch phải phù hợp schema và chính sách bảo mật. Đặc biệt, tránh trả dữ liệu của resource không được phép chỉ vì các ID nằm trong cùng một batch.

## 8. Kiểm tra quyền theo authority và role

Spring Security hỗ trợ kiểm tra authority cụ thể:

```java
@PreAuthorize("hasAuthority('BOOK_READ')")
```

`hasAuthority` so sánh chính xác chuỗi authority. Nó phù hợp với quyền theo hành động như `BOOK_READ`, `BOOK_CREATE`, `BOOK_AUDIT_READ`.

Có thể kiểm tra role:

```java
@PreAuthorize("hasRole('ADMIN')")
```

`hasRole('ADMIN')` mặc định kiểm tra authority `ROLE_ADMIN` do role prefix `ROLE_` được thêm tự động. Nếu dùng `hasAuthority('ADMIN')`, Spring sẽ so sánh đúng chuỗi `ADMIN` và không tự thêm prefix.

Không trộn lẫn hai quy ước. Hãy xác định authority naming convention trong ứng dụng và dùng nhất quán trong cấu hình, JWT converter, test và annotation.

## 9. Kiểm tra quyền theo resource ID

Quyền đọc một loại resource không đồng nghĩa được đọc mọi resource thuộc loại đó. Ví dụ người dùng có `BOOK_READ` nhưng chỉ được đọc sách trong tenant của mình hoặc sách do mình sở hữu.

Có thể gọi một bean policy từ SpEL:

```java
@Component("bookAuthorization")
public class BookAuthorization {

    private final BookPermissionService permissionService;

    public BookAuthorization(BookPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canRead(Authentication authentication, String bookId) {
        return permissionService.canRead(authentication.getName(), bookId);
    }
}
```

Đặt policy trên service method:

```java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('BOOK_READ') "
            + "and @bookAuthorization.canRead(authentication, #p0)")
    public BookView findById(String bookId) {
        return bookRepository.findViewById(bookId)
                .orElseThrow(() -> new BookNotFoundException(bookId));
    }
}
```

`#p0` tham chiếu tham số đầu tiên của method, tránh phụ thuộc vào tên parameter được lưu trong bytecode. Có thể dùng `#bookId` nếu dự án bảo đảm metadata tên parameter được biên dịch và Spring có thể khám phá tên đó.

Policy bean nên kiểm tra quyền dựa trên danh tính đã xác thực và dữ liệu server-side. Không dùng một giá trị `userId` do client gửi như bằng chứng caller là người dùng đó.

## 10. Controller policy và service policy

Đặt `@PreAuthorize` trên controller có lợi thế là policy nhìn thấy ngay tại GraphQL field. Tuy nhiên, service có thể được gọi từ REST controller, scheduled job, message consumer hoặc một use case khác.

Một cách tổ chức thường dùng:

- Controller kiểm tra quyền truy cập field hoặc nhóm operation của GraphQL.
- Service/application layer kiểm tra quy tắc nghiệp vụ và quyền trên resource.
- Repository/query luôn áp dụng tenant/ownership constraints cần thiết.

Ví dụ controller kiểm tra quyền thao tác:

```java
@MutationMapping
@PreAuthorize("hasAuthority('BOOK_UPDATE')")
public BookView updateBook(@Argument("input") UpdateBookInput input) {
    return bookService.update(toCommand(input));
}
```

Service kiểm tra caller có được sửa đúng sách đó không:

```java
@PreAuthorize("@bookAuthorization.canEdit(authentication, #p0.bookId())")
@Transactional
public BookView update(UpdateBookCommand command) {
    // Thực hiện cập nhật sau khi policy resource đã được xác nhận.
    return bookRepository.update(command);
}
```

Không nhất thiết phải lặp lại cùng một biểu thức quyền ở mọi tầng. Hãy đặt policy tại ranh giới phù hợp và bảo đảm use case không thể bị gọi vòng qua một adapter khác mà bỏ qua kiểm tra bắt buộc.

## 11. @PostAuthorize và kiểm tra object trả về

`@PostAuthorize` kiểm tra kết quả sau khi method hoàn tất. Nó có thể hữu ích khi quyết định truy cập phụ thuộc thuộc tính của object vừa tải:

```java
@PostAuthorize("returnObject == null or "
        + "@bookAuthorization.canRead(authentication, returnObject.id())")
public BookView findVisibleBook(String bookId) {
    return bookRepository.findViewById(bookId).orElse(null);
}
```

Với policy cần kiểm tra trước khi đọc hoặc trước khi thực hiện side effect, ưu tiên `@PreAuthorize`. `@PostAuthorize` chạy sau method nên dữ liệu đã được tải và công việc bên trong method đã xảy ra. Không dùng nó để bảo vệ mutation có side effect nếu quyền phải được xác nhận trước khi thay đổi dữ liệu.

Đối với collection, không nên tải toàn bộ dữ liệu rồi dựa vào filter sau cùng nếu có thể giới hạn ngay trong query theo caller/tenant. Lọc ở repository giúp giảm rủi ro rò rỉ qua log, cache, batch hoặc các đường xử lý khác.

## 12. Principal và Authentication trong controller

Method security có thể dùng `authentication` trong biểu thức SpEL mà không cần truyền principal từ client. Khi logic controller cần biết người dùng hiện tại để tạo command hoặc lọc dữ liệu, hãy lấy principal từ Spring Security context hoặc truyền một actor snapshot do server tạo.

Ví dụ với actor được đưa vào `GraphQLContext` bởi interceptor:

```java
@QueryMapping
@PreAuthorize("isAuthenticated()")
public List<BookView> myBooks(
        @ContextValue(name = "currentActor") CurrentActor actor) {
    return bookService.findVisibleTo(actor.subject());
}
```

`CurrentActor` phải được server tạo từ `Authentication` đã xác thực. Không bind một object có cấu trúc giống actor từ GraphQL variables rồi dùng nó làm principal. Nếu dùng cả method security và actor context, bảo đảm hai nguồn cùng đại diện một authentication context và không thể bị client ghi đè.

## 13. Authorization exception trong GraphQL response

Nếu `@PreAuthorize` từ chối method invocation, Spring Security ném exception thuộc nhóm `AccessDeniedException` (chẳng hạn `AuthorizationDeniedException`). Khi lỗi phát sinh trong lúc GraphQL resolve field, Spring for GraphQL có thể ánh xạ nó thành GraphQL error.

Ví dụ handler:

```java
@ControllerAdvice
public class GraphQlAuthorizationExceptionHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("You are not allowed to access this field")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` giữ path và location của field đang thực thi. Client có thể biết field nào bị từ chối qua `errors[].path` và dùng `extensions.code` để xử lý.

Nếu request bị từ chối ở Spring Security filter chain trước khi GraphQL execution bắt đầu, `@GraphQlExceptionHandler` không xử lý được lỗi đó; client có thể nhận HTTP 401/403 ở tầng transport. Hãy phân biệt lỗi endpoint với lỗi authorization của một field.

## 14. Nullability và dữ liệu khi field bị từ chối

Khi field authorization thất bại, GraphQL xử lý lỗi theo nullability của field. Ví dụ:

```graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
```

Nếu `internalNotes` nullable, lỗi có thể làm field đó thành null trong khi `id` và `title` vẫn có dữ liệu. Nếu field được khai báo `String!`, lỗi có thể lan null lên object cha và tiếp tục lên root tùy nullability của các cấp.

Không nên đổi field nhạy cảm thành nullable chỉ để che lỗi authorization. Nullability phải phản ánh hợp đồng dữ liệu; client vẫn cần nhận GraphQL error hoặc một policy response rõ ràng. Nếu muốn không tiết lộ resource có tồn tại hay không, có thể trả cùng một lỗi công khai cho trường hợp không tồn tại và không được phép, nhưng phải giữ semantics nhất quán.

## 15. Nhiều root field và alias không bỏ qua authorization

Một query có thể yêu cầu nhiều root field cùng lúc:

```graphql
query Dashboard {
    visibleBooks: books {
        id
        title
    }
    admin: adminReport {
        totalUsers
    }
}
```

GraphQL có thể phân giải các query field song song. Mỗi controller method phải tự kiểm tra policy của nó. Nếu `books` được phép nhưng `adminReport` bị từ chối, response có thể giữ dữ liệu `visibleBooks` và có lỗi cho nhánh `admin` nếu nullability cho phép.

Alias chỉ đổi response key. Nó không thay đổi method được gọi hoặc policy gắn với resolver. Fragment cũng không tạo đường truy cập thay thế. Authorization phải dựa trên method/resource thực tế, không dựa vào tên alias hoặc cấu trúc query do client chọn.

## 16. Authorization trong ứng dụng reactive

Với WebFlux, security context được truyền qua Reactor Context. Khi dùng reactive method security, method được bảo vệ nên trả `Mono` hoặc `Flux` để interceptor đánh giá quyền trong reactive execution:

```java
@Controller
public class ReactiveBookController {

    private final ReactiveBookService bookService;

    public ReactiveBookController(ReactiveBookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    @PreAuthorize("hasAuthority('BOOK_READ')")
    public Flux<BookView> books() {
        return bookService.findAll();
    }
}
```

Không gọi `.block()` trong controller để lấy kết quả rồi mới kiểm tra quyền. Cũng không chuyển tùy tiện sang executor tự tạo khiến Reactor Context bị mất. Nếu service hoặc batch loader cần actor, hãy truyền context theo cơ chế reactive phù hợp và kiểm thử với request thực tế.

## 17. Kiểm thử authorization ở GraphQL controller

Có thể dùng Spring Security Test với `@WithMockUser` để tạo authentication trong test:

```java
@Test
@WithMockUser(authorities = "BOOK_READ")
void userWithBookReadCanQueryBooks() {
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
        .entityList(BookView.class);
}
```

Kiểm tra người dùng thiếu authority:

```java
@Test
@WithMockUser(authorities = "PROFILE_READ")
void userWithoutBookReadIsDenied() {
    graphQlTester.document("""
            query {
                books {
                    id
                }
            }
            """)
        .execute()
        .errors()
        .satisfy(errors -> {
            assertThat(errors).isNotEmpty();
            assertThat(errors.get(0).getMessage())
                    .contains("not allowed");
        });
}
```

Để test chạy đúng, test slice cần import cấu hình method security và cấu hình GraphQL controller/service liên quan. `@WithMockUser` cung cấp authority giả lập; nó không thay thế integration test cho JWT converter, HTTP filter chain hoặc GraphQL interceptor.

Với test qua HTTP, có thể dùng `WebTestClient`/`MockMvc` cùng Spring Security test support để gửi request có user hoặc JWT giả lập. Cách này xác nhận request đi qua cả security filter chain, transport và GraphQL execution.

## 18. Những trường hợp cần kiểm thử

Một bộ test authorization cho GraphQL nên bao gồm:

1. Người chưa xác thực bị chặn ở endpoint nếu HTTP policy yêu cầu đăng nhập.
2. Người có `BOOK_READ` truy vấn được field đọc sách.
3. Người chỉ có `BOOK_READ` không thể gọi mutation tạo hoặc xóa sách.
4. Người thiếu `BOOK_AUDIT_READ` không thể đọc field `internalNotes`.
5. Người có authority chung nhưng không sở hữu resource không thể sửa resource đó.
6. Alias và fragment không làm thay đổi policy.
7. Một query nhiều root field trả partial data đúng khi một field bị từ chối.
8. `@BatchMapping` kiểm tra quyền cho batch và từng resource theo policy.
9. Async/reactive resolver nhận đúng security context.
10. Authorization error có code, path và message an toàn.
11. Service vẫn bảo vệ use case khi được gọi từ adapter khác ngoài GraphQL.
12. Resource không tồn tại và resource không được phép xem được xử lý theo chính sách chống enumeration.

## 19. Những lỗi thường gặp

- **Chỉ dùng `authenticated()` cho `/graphql`:** người dùng đã đăng nhập có thể vẫn không đủ quyền gọi field cụ thể.
- **Chỉ bảo vệ root query:** field lồng nhau có thể chứa dữ liệu nhạy cảm và cần policy riêng.
- **Tin rằng UI ẩn field là đủ:** client có thể gửi query thủ công.
- **Đặt `@PreAuthorize` nhưng quên `@EnableMethodSecurity`:** annotation không được kích hoạt.
- **Dùng sai role prefix:** `hasRole('ADMIN')` mặc định tìm `ROLE_ADMIN`; `hasAuthority` so sánh chính xác.
- **Dùng `@PostAuthorize` cho side effect:** method đã chạy trước khi quyền được kiểm tra.
- **Chỉ kiểm tra authority chung:** chưa đủ cho quyền theo owner, tenant hoặc resource ID.
- **Dùng `userId` từ variables làm danh tính:** client có thể giả mạo người dùng khác.
- **Bỏ qua authorization trong batch loader:** batch có thể chứa resource thuộc nhiều phạm vi quyền.
- **Self-invocation method được bảo vệ:** lời gọi nội bộ có thể bỏ qua Spring proxy.
- **Nhầm HTTP 403 với GraphQL field error:** lỗi filter chain xảy ra trước execution, còn lỗi method security có thể nằm trong GraphQL `errors`.
- **Không test bằng transport thật:** unit test resolver không xác nhận JWT, filter chain hoặc context propagation.

## 20. Quy trình triển khai authorization ở controller

Khi thêm một query, mutation hoặc field resolver, hãy thực hiện:

1. Xác định caller cần đăng nhập hay field có thể truy cập anonymous.
2. Bảo vệ endpoint `/graphql` ở HTTP layer theo chính sách chung.
3. Bật `@EnableMethodSecurity` hoặc reactive method security phù hợp.
4. Gắn `@PreAuthorize` vào method `@QueryMapping`/`@MutationMapping` cần policy theo operation.
5. Bảo vệ field nhạy cảm trên `@SchemaMapping` và `@BatchMapping`.
6. Dùng authority/role nhất quán; kiểm tra resource ownership và tenant ở service/domain.
7. Không tin principal, user ID hoặc tenant ID do client tự gửi.
8. Ánh xạ access denied thành GraphQL error an toàn khi lỗi phát sinh trong execution.
9. Thiết kế nullability phù hợp với field có thể bị từ chối.
10. Kiểm thử caller được phép, bị từ chối, resource-level policy, batch, alias, fragment và transport.

Authorization ở controller đặt kiểm tra quyền ngay tại method phân giải field GraphQL. `@PreAuthorize` có thể bảo vệ query, mutation, nested field và batch mapping sau khi method security được bật. Kết hợp policy ở controller với kiểm tra quyền theo resource trong service giúp API vừa kiểm soát được field mà client yêu cầu, vừa bảo vệ quy tắc nghiệp vụ khi use case được gọi từ nhiều nơi. Khi phân biệt HTTP security với GraphQL field authorization và kiểm thử cả response lỗi lẫn partial data, Spring for GraphQL có thể cung cấp một bề mặt API rõ ràng và an toàn hơn.

## Tài liệu tham khảo

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Exception Handling](https://docs.spring.io/spring-graphql/reference/controllers.html#controllers.exception-handling)
- [Spring Security Test — Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
