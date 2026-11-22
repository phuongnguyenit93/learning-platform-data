# Spring Security với GraphQL

Spring Security bảo vệ ứng dụng GraphQL ở hai mức chính: **xác thực request tới endpoint** và **phân quyền cho từng thao tác hoặc dữ liệu được resolve**. HTTP URL security giúp xác định ai được gọi endpoint `/graphql`, nhưng tất cả Query, Mutation và field lồng nhau thường dùng chung một URL. Vì vậy, muốn giới hạn quyền theo nghiệp vụ, cần kết hợp method security ở service hoặc resolver với kiểm tra quyền trên tài nguyên cụ thể.

Spring for GraphQL hỗ trợ tích hợp Spring Security thông qua context propagation. Security context có thể được sử dụng ở tầng data fetching, kể cả khi GraphQL thực thi field bất đồng bộ. Spring for GraphQL cũng hỗ trợ lấy `Principal` hoặc `@AuthenticationPrincipal` làm tham số trong annotated controller.

## Xác thực và phân quyền trong GraphQL

Hãy phân biệt hai câu hỏi:

- **Authentication (xác thực):** người gọi là ai? Ví dụ user đăng nhập bằng session cookie, HTTP Basic hoặc bearer JWT.
- **Authorization (phân quyền):** người đó được phép làm gì? Ví dụ được đọc sách công khai, sửa sách thuộc nhóm biên tập hoặc xem ghi chú nội bộ.

Một request có thể xác thực thành công nhưng vẫn không có quyền đọc một field cụ thể. Ngược lại, người dùng có thể được phép đọc danh sách sách nhưng không được phép chạy Mutation xóa sách.

GraphQL thường có một endpoint chung:

```text
POST /graphql
```

Do đó, rule chỉ dựa vào URL không phân biệt được `Query.books`, `Mutation.deleteBook` hay `Book.internalNotes`. Cần áp dụng authorization ở các method thực hiện nghiệp vụ hoặc field resolver có dữ liệu nhạy cảm.

## Các lớp bảo vệ trong một ứng dụng GraphQL

| Lớp | Trách nhiệm | Cơ chế thường dùng |
| --- | --- | --- |
| HTTP endpoint | Ai được gửi request tới GraphQL transport? | `SecurityFilterChain`, `authorizeHttpRequests`. |
| Authentication | Xác minh danh tính và tạo `Authentication`. | Session, HTTP Basic, OAuth2 Resource Server/JWT. |
| Operation/service | Ai được chạy nghiệp vụ đọc hoặc ghi? | `@EnableMethodSecurity`, `@PreAuthorize`. |
| Resource/field | Người dùng có quyền trên bản ghi, tenant hoặc field cụ thể không? | Authorization service, `PermissionEvaluator`, method security. |
| Subscription | Ai được đăng ký và tiếp tục nhận event nào? | Security ở handshake/operation, kiểm tra quyền và lọc event source. |
| GraphQL workload | Request có tiêu tốn tài nguyên bất thường không? | Rate limit, pagination, giới hạn depth/complexity và timeout. |

Không có một annotation duy nhất thay thế tất cả các lớp này. Nên bảo vệ endpoint ở ranh giới HTTP, bảo vệ nghiệp vụ ở service và kiểm tra quyền tài nguyên tại nơi có đủ thông tin để đưa ra quyết định.

## Thêm Spring Security dependency

Với Spring Boot và Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

Spring Security cung cấp servlet filter chain, authentication và authorization. Nếu ứng dụng dùng Spring WebFlux, cấu hình security tương ứng sẽ là reactive security (`SecurityWebFilterChain`); không dùng `SecurityFilterChain` servlet trong ứng dụng WebFlux.

## Bảo vệ endpoint GraphQL bằng SecurityFilterChain

Ví dụ yêu cầu mọi request tới `/graphql` phải được xác thực:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

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

Với cấu hình này, request chưa xác thực bị chặn ở servlet security filter trước khi GraphQL engine thực thi. Client cần gửi session cookie hoặc thông tin xác thực theo cơ chế authentication mà ứng dụng đã cấu hình.

Nếu thay endpoint path bằng `spring.graphql.http.path`, hãy cập nhật matcher tương ứng. Nếu endpoint nằm sau context path hoặc reverse proxy prefix, kiểm tra path mà servlet filter thực sự nhận được.

Rule URL chỉ bảo vệ endpoint chung. Nó không tự kiểm tra quyền cho từng field. Nếu một số Query công khai và Query khác yêu cầu đăng nhập, có thể cho phép endpoint đi qua filter rồi đặt method security cho các service cần bảo vệ; tuy nhiên phải bảo đảm mọi đường gọi nghiệp vụ đều được bảo vệ.

## Bật method security

Để dùng `@PreAuthorize`, cần bật method security trong cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` bật các annotation pre/post authorization như `@PreAuthorize` và `@PostAuthorize`. Đây là cấu hình riêng với URL authorization trong `SecurityFilterChain`; bật một cơ chế không tự bật cơ chế còn lại.

Method security hoạt động qua Spring AOP proxy. Vì vậy, lời gọi cần đi qua Spring bean proxy. Một method gọi method được bảo vệ khác trong cùng object bằng `this.someMethod()` có thể bỏ qua proxy và không kích hoạt interceptor bảo mật. Đặt ranh giới bảo vệ ở service bean được inject và gọi từ controller hoặc service khác.

## Phân quyền theo authority và role

Spring Security có thể kiểm tra authority chính xác hoặc role:

```java
@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(String id) {
        // Load book
        return repository.findById(id).orElse(null);
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(String id, UpdateBookCommand command) {
        // Update book
        return repository.update(id, command);
    }

    @PreAuthorize("hasRole('ADMIN')")
    public void delete(String id) {
        repository.deleteById(id);
    }
}
```

`hasAuthority("book:read")` so sánh với authority có tên chính xác `book:read`. `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`; Spring Security tự thêm prefix `ROLE_` khi dùng `hasRole`.

Đặt annotation trên service giúp quy tắc được áp dụng dù service được gọi từ GraphQL, REST endpoint, scheduled job hoặc thành phần khác thông qua Spring proxy. Controller chỉ điều phối request và không cần tự viết lại cùng một kiểm tra quyền.

## Ánh xạ GraphQL field tới service đã bảo vệ

Schema có Query đọc sách và Mutation cập nhật sách:

```graphql
type Book {
  id: ID!
  title: String!
  internalNotes: String
}

input UpdateBookInput {
  title: String!
}

type Query {
  book(id: ID!): Book
}

type Mutation {
  updateBook(id: ID!, input: UpdateBookInput!): Book!
}
```

Controller gọi service. Việc cho phép hay từ chối được quyết định tại method security:

```java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("id") String id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input.toCommand());
    }
}
```

Khi người dùng thiếu `book:read`, lời gọi `findById` bị từ chối. Khi thiếu `book:write`, Mutation không thể thực hiện cập nhật. GraphQL runtime nhận exception từ quá trình resolve và đưa nó vào `errors`; response có thể vẫn chứa dữ liệu của các field khác đã resolve thành công.

## Phân quyền theo từng tài nguyên

Kiểm tra authority chung chưa đủ nếu người dùng chỉ được đọc sách thuộc tenant hoặc nhóm của họ. Có thể gọi một authorization bean từ biểu thức SpEL trong `@PreAuthorize`:

```java
@Component("bookAuthorization")
public class BookAuthorization {

    public boolean canRead(Authentication authentication, String bookId) {
        String userId = authentication.getName();
        return permissionRepository.canReadBook(userId, bookId);
    }
}
```

Service kiểm tra quyền theo ID trước khi trả dữ liệu:

```java
@Service
public class BookService {

    @PreAuthorize("@bookAuthorization.canRead(authentication, #p0)")
    public Book findReadableById(String id) {
        return repository.findById(id).orElse(null);
    }
}
```

`#p0` tham chiếu tham số đầu tiên của method, nên không phụ thuộc vào tên tham số Java được giữ lại khi compile. Có thể dùng `#id` khi dự án bảo đảm metadata tên tham số có sẵn, chẳng hạn biên dịch với `-parameters`.

Authorization service cần kiểm tra quyền dựa trên danh tính đã xác thực và dữ liệu server-side. Không dùng `userId`, `ownerId` hoặc `tenantId` do client gửi làm bằng chứng người gọi sở hữu tài nguyên.

### Bảo vệ field lồng nhau

Giả sử người dùng được xem thông tin cơ bản của sách nhưng chỉ biên tập viên được đọc `internalNotes`. Có thể bảo vệ service chuyên cung cấp field này:

```java
@Service
public class BookDetailsService {

    @PreAuthorize("hasAuthority('book:moderation:read')")
    public String getInternalNotes(String bookId) {
        return repository.findInternalNotes(bookId);
    }
}
```

Resolver chỉ gọi service đã bảo vệ:

```java
@Controller
public class BookFieldController {

    private final BookDetailsService detailsService;

    public BookFieldController(BookDetailsService detailsService) {
        this.detailsService = detailsService;
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(Book book) {
        return detailsService.getInternalNotes(book.getId());
    }
}
```

Khi client không có authority phù hợp, chỉ field `internalNotes` bị lỗi theo quy tắc GraphQL nullability. Các field khác như `id` và `title` vẫn có thể trả về. Đây là cách bảo vệ chi tiết hơn so với chặn toàn bộ endpoint.

Nếu field nhạy cảm phụ thuộc quyền trên từng Book, dùng authorization theo resource thay vì chỉ kiểm tra role chung. Cũng cần cân nhắc schema nullability: nếu field được khai báo Non-Null, lỗi ở field đó có thể lan lên object cha và làm mất nhiều phần `data` hơn.

## Lấy Principal trong annotated controller

Spring for GraphQL hỗ trợ `java.security.Principal` và `@AuthenticationPrincipal` trong tham số của annotated controller. Có thể dùng thông tin người dùng cho logic điều phối hoặc truyền định danh tới service:

```java
import java.security.Principal;

@QueryMapping
public List<Book> myBooks(Principal principal) {
    return bookService.findByOwner(principal.getName());
}
```

Hoặc lấy trực tiếp principal object của Spring Security:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@QueryMapping
public Profile myProfile(@AuthenticationPrincipal AppUser user) {
    return profileService.findByUserId(user.getId());
}
```

`Principal` cho phép code ít phụ thuộc Spring Security hơn; `@AuthenticationPrincipal` hữu ích khi ứng dụng có kiểu principal riêng chứa user ID hoặc thông tin định danh. Cần xử lý trường hợp chưa xác thực nếu endpoint cho phép anonymous request; không dereference principal khi nó có thể null.

Không dùng việc nhận được Principal làm bằng chứng rằng mọi thao tác đều được phép. Danh tính chỉ trả lời ai đang gọi; service vẫn cần kiểm tra authority và quyền trên tài nguyên.

## Context propagation khi GraphQL thực thi bất đồng bộ

GraphQL có thể resolve nhiều field, dùng `CompletableFuture`, Reactor hoặc DataLoader. Việc thực thi có thể tiếp tục trên thread khác với thread nhận HTTP request. Spring for GraphQL có hỗ trợ context propagation để Security context và các context khác khả dụng ở tầng data fetching.

Điều này cho phép method security trên service hoạt động trong quá trình GraphQL resolve field. Tuy nhiên, nếu ứng dụng tự tạo executor hoặc khởi chạy công việc detached bên ngoài cơ chế thực thi GraphQL, cần xem xét việc truyền context tương ứng. Không giả định mọi `ThreadLocal` tự động xuất hiện trên mọi thread.

Các nguyên tắc thực hành:

- Ưu tiên gọi service bean đã bảo vệ từ resolver và để Spring quản lý context propagation.
- Với executor tự tạo, cấu hình cơ chế truyền `SecurityContext` phù hợp nếu task cần thông tin xác thực.
- Không dùng `CompletableFuture.supplyAsync` với common pool rồi kỳ vọng `SecurityContextHolder` luôn có giá trị.
- Truyền tenant/user ID đã xác thực một cách tường minh khi công việc được đưa vào queue hoặc chạy nền.
- Không lưu `Authentication` trong singleton mutable field hoặc cache dùng chung giữa request.

Với Reactor, giữ pipeline reactive xuyên suốt và tránh tự chuyển sang thread không có context khi không cần thiết. Khi tích hợp thư viện blocking, vừa phải quản lý dispatcher/executor, vừa phải bảo đảm context cần thiết được truyền an toàn.

## Xử lý AccessDeniedException trong GraphQL response

Khi HTTP security filter từ chối request trước khi GraphQL engine chạy, client thường nhận HTTP 401 hoặc 403. Khi method security từ chối một service trong lúc GraphQL đang resolve field, đó là lỗi thực thi GraphQL. Response thường chứa `errors` và có thể có partial `data`; HTTP status thường vẫn là 200 vì operation đã được chấp nhận và bắt đầu thực thi.

Có thể dùng `@GraphQlExceptionHandler` trong controller hoặc `@ControllerAdvice`, hay `DataFetcherExceptionResolver` cho DataFetcher tương ứng, để ánh xạ `AccessDeniedException` thành message công khai và error classification phù hợp.

Ví dụ response đã được chuẩn hóa:

```json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring in Practice",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "Bạn không có quyền xem ghi chú nội bộ",
      "path": ["book", "internalNotes"],
      "extensions": {
        "code": "FORBIDDEN"
      }
    }
  ]
}
```

Đây là response minh họa cho field nullable. Không trả stack trace, câu SQL, tên lớp nội bộ hoặc chi tiết policy nhạy cảm cho client. Log nội bộ có thể lưu correlation ID và loại lỗi theo chính sách bảo mật.

Không nên biến mọi lỗi thành `null` mà không có error. Client cần phân biệt field thực sự không có dữ liệu với field bị từ chối truy cập.

## Bảo vệ Mutation và tránh kiểm tra quyền sau khi ghi

Mutation thay đổi trạng thái nên cần authorization trước khi thực hiện side effect. Đặt `@PreAuthorize` trên service method ghi dữ liệu:

```java
@Service
public class BookCommandService {

    @PreAuthorize("@bookAuthorization.canEdit(authentication, #p0)")
    @Transactional
    public Book update(String bookId, UpdateBookCommand command) {
        Book book = repository.findById(bookId).orElseThrow();
        book.rename(command.title());
        return repository.save(book);
    }
}
```

Không dùng `@PostAuthorize` như lớp bảo vệ chính cho thao tác ghi. Annotation này kiểm tra kết quả sau khi method đã chạy; nếu method đã commit thay đổi rồi mới phát hiện người gọi không có quyền, side effect có thể đã xảy ra. Với thao tác ghi, kiểm tra quyền trước khi thay đổi dữ liệu và bảo vệ invariant trong service/domain.

Nếu quyền phụ thuộc trạng thái bản ghi, có thể tải bản ghi trong service rồi kiểm tra authorization trước khi cập nhật trong cùng transaction. Cần cân nhắc race condition và dùng optimistic/pessimistic locking hoặc điều kiện cập nhật ở database khi phù hợp.

## Bảo mật DataLoader và `@BatchMapping`

DataLoader gom nhiều lần tải field quan hệ thành một batch. Batch loader vẫn là một đường truy cập dữ liệu và phải tuân thủ cùng chính sách authorization như resolver thông thường.

Ví dụ không nên để batch loader tải toàn bộ tác giả chỉ dựa trên ID do source object cung cấp mà bỏ qua tenant. Service batch nên nhận tenant hoặc user scope đã xác thực và lọc dữ liệu ở server:

```java
public Map<Long, Author> findVisibleAuthors(
        String tenantId, Set<Long> authorIds) {
    return authorRepository.findVisibleByTenantAndIdIn(tenantId, authorIds);
}
```

Trong một request GraphQL, DataLoader thường được tạo theo request và cache theo key. Không chia sẻ DataLoader hoặc cache kết quả nhạy cảm như singleton giữa người dùng. Nếu batch key không đủ để phân biệt phạm vi dữ liệu trong cùng một registry, thiết kế key hoặc loader context để bao gồm phạm vi cần thiết.

Với `@BatchMapping`, kiểm tra quyền trong service được gọi bởi batch method hoặc lọc nguồn dữ liệu trước khi trả map/list. Đừng giả định việc một resolver cha đã kiểm tra quyền thì mọi field con và mọi batch loader đều tự động an toàn.

## Bảo mật Subscription

Subscription có vòng đời dài hơn một HTTP request thông thường. Cần kiểm tra quyền khi client bắt đầu đăng ký và xác định chính sách khi quyền thay đổi trong lúc stream vẫn hoạt động.

Các điểm cần xử lý:

- Xác thực ở WebSocket handshake hoặc cơ chế transport tương ứng.
- Kiểm tra quyền đăng ký Subscription operation và tài nguyên được yêu cầu.
- Lọc event source theo user, tenant và resource đã xác thực.
- Không phát broadcast event nhạy cảm cho mọi subscriber rồi trông chờ selection set che dữ liệu.
- Xác định hành vi khi token hết hạn, người dùng đăng xuất hoặc quyền bị thu hồi.
- Hủy subscription và giải phóng listener khi không còn được phép hoặc client gửi complete.

Method security ở `@SubscriptionMapping` có thể bảo vệ bước bắt đầu đăng ký. Nhưng event producer có thể chạy trên thread khác và phát event lâu sau đó; không nên giả định `SecurityContextHolder` của request luôn có sẵn trên thread producer. Hãy ràng buộc subscription với scope đã xác thực, lọc ở event source và có cơ chế hủy/revalidate nếu nghiệp vụ yêu cầu.

## CSRF và CORS với GraphQL HTTP

GraphQL thường dùng một endpoint POST cho cả Query và Mutation. Nếu ứng dụng xác thực bằng session cookie, trình duyệt tự gửi cookie theo quy tắc của nó; vì vậy CSRF protection của Spring Security vẫn quan trọng đối với mutation.

Không tắt CSRF cho toàn bộ ứng dụng chỉ để request GraphQL hoạt động. Nếu dùng cookie session, cấu hình cách frontend lấy và gửi CSRF token. Nếu API dùng bearer token trong Authorization header và không dựa vào cookie tự động gửi, đánh giá CSRF dựa trên mô hình xác thực thực tế.

CORS kiểm soát frontend từ origin khác có được phép gọi endpoint và gửi các header cần thiết hay không. CORS không xác thực user và không thay thế authorization. Khi bật credentials, khai báo origin cụ thể; không kết hợp credentials với wildcard origin.

## Kiểm soát truy vấn và lạm dụng tài nguyên

Một người dùng hợp lệ vẫn có thể gửi operation quá sâu hoặc yêu cầu lượng dữ liệu lớn. Bảo mật GraphQL cần xem cả quyền truy cập lẫn giới hạn tài nguyên:

- Bắt buộc pagination và giới hạn `first`/`last` tối đa.
- Giới hạn query depth hoặc complexity theo cấu hình phù hợp.
- Rate limit theo user, API key hoặc client identity.
- Đặt timeout cho GraphQL operation và các dịch vụ phụ thuộc.
- Giới hạn số lượng alias, batch request hoặc subscription đồng thời nếu transport cho phép.
- Tắt hoặc giới hạn introspection ở môi trường cần chính sách đó, nhưng không xem việc ẩn schema là authorization.
- Theo dõi các operation tốn tài nguyên và tỷ lệ lỗi/timeout.

Introspection chỉ cung cấp thông tin về schema; tắt introspection không ngăn người dùng đã biết field name truy cập dữ liệu. Authorization phải được thực thi ở resolver/service cho từng field và tài nguyên.

## Kiểm thử security cho GraphQL

Kiểm thử cần bao gồm cả endpoint security và method security. Với method security, có thể dùng `@WithMockUser` để tạo Authentication trong test:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookServiceSecurityTests {

    private final BookService bookService;

    BookServiceSecurityTests(BookService bookService) {
        this.bookService = bookService;
    }

    @Test
    @WithMockUser(authorities = "book:read")
    void readerCanReadBook() {
        assertThat(bookService.findById("book-10")).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "book:write")
    void writerCannotUseReadOnlyAuthority() {
        assertThatThrownBy(() -> bookService.findById("book-10"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
```

Ví dụ giả định service bean được inject từ Spring application context đã bật `@EnableMethodSecurity`; không tự tạo `new BookService(...)` vì cách đó bỏ qua AOP proxy và không kiểm tra annotation.

Test cần các dependency `spring-boot-starter-test` và `spring-security-test` ở scope test. Dữ liệu `book-10` cần được chuẩn bị trong fixture hoặc test database để assertion thành công có ý nghĩa.

Để test GraphQL end-to-end, dùng `GraphQlTester` hoặc HTTP tester với security filter chain thật. Cần xác nhận:

- Anonymous request bị chặn ở endpoint nếu endpoint yêu cầu authentication.
- User có authority phù hợp chạy được Query/Mutation tương ứng.
- User thiếu authority nhận GraphQL error phù hợp ở field được bảo vệ.
- User không thể truy cập tài nguyên thuộc user hoặc tenant khác dù biết ID.
- Field nhạy cảm bị từ chối trong khi field công khai vẫn trả được nếu nullability cho phép.
- Batch loader không bỏ qua tenant/resource authorization.
- Subscription chỉ nhận event thuộc phạm vi được phép và cancellation hoạt động.
- CSRF token và CORS được kiểm tra đúng với kiểu authentication.
- Không lộ stack trace, token hoặc dữ liệu nhạy cảm trong errors/extensions/logs.

Với test HTTP dùng MockMvc, có thể dùng Spring Security Test để thêm user và CSRF token vào request. Với WebSocket Subscription, cần test cả xác thực kết nối và quyền ở operation; một test gọi trực tiếp service không chứng minh handshake được bảo vệ.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Endpoint `/graphql` cho anonymous truy cập | SecurityFilterChain chưa bảo vệ đúng path hoặc filter chain khác được áp dụng trước. | Kiểm tra matcher, thứ tự filter chain và path thực tế. |
| Đã đăng nhập nhưng service vẫn báo AccessDenied | Thiếu authority hoặc dùng nhầm role/authority prefix. | Kiểm tra `GrantedAuthority`, `hasRole` và `hasAuthority`. |
| `@PreAuthorize` không chạy | Chưa bật `@EnableMethodSecurity` hoặc lời gọi bỏ qua proxy qua self-invocation. | Bật method security và gọi qua Spring bean proxy. |
| GraphQL field lồng nhau lộ dữ liệu | Chỉ bảo vệ Query gốc, field/service con chưa được bảo vệ. | Bảo vệ service cung cấp field nhạy cảm và kiểm tra quyền tài nguyên. |
| Async DataFetcher mất Authentication | Tự tạo executor không truyền SecurityContext. | Dùng context propagation hoặc executor truyền SecurityContext phù hợp. |
| DataLoader trả dữ liệu khác tenant | Batch loader không áp dụng tenant scope hoặc cache dùng chung. | Lọc trong service batch và giữ loader/cache theo request. |
| Method security trả GraphQL error nhưng HTTP status vẫn 200 | Lỗi xảy ra sau khi GraphQL operation bắt đầu thực thi. | Client đọc `errors` và xử lý partial `data`; không mặc định coi đây là lỗi transport. |
| Mutation thay đổi dữ liệu rồi mới bị từ chối | Dùng `@PostAuthorize` để bảo vệ thao tác ghi. | Kiểm tra quyền trước side effect bằng `@PreAuthorize` và service/domain invariant. |
| Subscription tiếp tục phát sau khi quyền bị thu hồi | Chỉ kiểm tra quyền lúc đăng ký. | Revalidate, hủy stream hoặc giới hạn thời gian subscription theo policy. |

## Ghi nhớ

Bảo vệ GraphQL bằng Spring Security cần kết hợp URL security và method security. `SecurityFilterChain` xác thực request tới endpoint chung; `@EnableMethodSecurity` bật `@PreAuthorize` để bảo vệ service method thực hiện từng nghiệp vụ. Dùng authority hoặc role cho quyền tổng quát, và authorization service để kiểm tra quyền trên từng resource/tenant.

Spring for GraphQL hỗ trợ lấy `Principal` hoặc `@AuthenticationPrincipal` trong annotated controller và context propagation để security context khả dụng ở tầng data fetching. Với async executor tự tạo, DataLoader, batch mapping và Subscription, cần bảo đảm context hoặc scope đã xác thực được truyền và lọc đúng. Xử lý `AccessDeniedException` thành GraphQL error an toàn, giữ nguyên phân biệt giữa lỗi HTTP filter và lỗi trong quá trình resolve field. Cuối cùng, kiểm thử anonymous, từng authority, resource ownership, tenant isolation, CSRF/CORS và subscription lifecycle.

## Tài liệu tham khảo

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
