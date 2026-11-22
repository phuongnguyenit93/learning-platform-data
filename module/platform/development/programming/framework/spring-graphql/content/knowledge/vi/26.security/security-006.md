# Authorization theo field

## Mục tiêu

Sau bài học này, bạn có thể:

- Phân biệt xác thực, authorization ở HTTP endpoint và authorization ở từng GraphQL field.
- Giải thích vì sao một URL GraphQL dùng chung cần kiểm soát quyền ở cấp method hoặc service.
- Bật method security bằng @EnableMethodSecurity.
- Dùng @PreAuthorize để bảo vệ root resolver và nested field thông qua service.
- Viết quy tắc authorization dựa trên authority, owner, tenant và object đang truy cập.
- Bảo vệ batch resolver khi mỗi parent object có quyền truy cập khác nhau.
- Hiểu cách AccessDeniedException trở thành GraphQL error và ảnh hưởng của nullability.
- Kiểm thử quyền truy cập bằng Spring Security Test và GraphQlTester.

## Vì sao cần authorization theo field?

Một endpoint GraphQL thường dùng chung một URL, chẳng hạn POST /graphql. Nhiều operation khác nhau đi qua cùng endpoint:

- Query sách công khai.
- Query thông tin nội bộ của sách.
- Mutation cập nhật sách.
- Query thông tin của người dùng hiện tại.

Nếu chỉ cấu hình HTTP security cho URL /graphql, server có thể xác định người gửi đã đăng nhập hay chưa, nhưng không thể từ URL đó biết operation đang đọc field nào hoặc mutation nào đang được thực thi.

GraphQL cho phép client chọn field tùy ý trong selection set. Một query có thể lấy title công khai cùng internalNotes nhạy cảm:

~~~graphql
query {
  bookById(id: "book-101") {
    title
    internalNotes
  }
}
~~~

Người dùng có quyền đọc sách chưa chắc có quyền đọc ghi chú nội bộ. Vì vậy, authorization cần được áp dụng tại phần dữ liệu hoặc thao tác cụ thể.

Spring for GraphQL khuyến nghị dùng các annotation Spring Security như @PreAuthorize hoặc @Secured trên service method cung cấp dữ liệu cho từng phần của response. Security context được truyền tới tầng data fetching để các method đó có thể sử dụng danh tính hiện tại. Cách này cũng bảo vệ service nếu nó được gọi từ một entry point khác ngoài GraphQL.

## Phân biệt authentication và authorization

Hai khái niệm này giải quyết hai câu hỏi khác nhau:

- Authentication xác định người gọi là ai.
- Authorization xác định người đó được phép làm gì với dữ liệu hoặc thao tác cụ thể.

Ví dụ:

| Người dùng | Authentication | Quyền có thể được cấp |
| --- | --- | --- |
| Người chưa đăng nhập | Anonymous | Đọc thông tin sách công khai |
| Thành viên | Đã đăng nhập | Đọc sách và hồ sơ của chính mình |
| Biên tập viên | Đã đăng nhập | Tạo và cập nhật sách |
| Nhân viên nội bộ | Đã đăng nhập | Đọc ghi chú nội bộ |
| Quản trị viên | Đã đăng nhập | Quản lý người dùng và cấu hình |

Không dùng việc đã đăng nhập làm bằng chứng rằng người dùng được phép đọc mọi field. Một principal có thể có nhiều authority khác nhau; policy phải kiểm tra đúng quyền cho từng use case.

## Kết hợp HTTP security và method security

HTTP security kiểm soát việc truy cập transport endpoint. Ví dụ, ứng dụng có thể yêu cầu mọi request tới /graphql phải được xác thực:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/graphql").authenticated()
                    .anyRequest().permitAll())
            .build();
}
~~~

Đây là kiểm soát ở cấp endpoint. Nếu API có cả operation công khai và riêng tư, chính sách HTTP có thể cho phép request tới endpoint, sau đó dùng method security để bảo vệ dữ liệu riêng tư. Quyết định này tùy cách ứng dụng muốn xử lý anonymous operation.

Bật method security bằng @EnableMethodSecurity:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Chỉ thêm spring-boot-starter-security không tự bật method authorization. Cần @EnableMethodSecurity để Spring tạo các interceptor cho @PreAuthorize, @PostAuthorize và các annotation method security mặc định.

Khi bật method security, annotation được áp dụng trên Spring-managed bean và được thực thi qua proxy AOP. Vì vậy, method cần được gọi qua Spring bean proxy. Lời gọi nội bộ kiểu this.securedMethod() trong cùng bean có thể bỏ qua proxy và không kích hoạt @PreAuthorize.

## Bảo vệ root field và nested field

Ví dụ schema có một field công khai và một field nội bộ:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  internalNotes: String
}
~~~

Field internalNotes được khai báo nullable. Điều này cho phép GraphQL giữ lại các field công khai của Book nếu việc đọc ghi chú bị từ chối và lỗi được xử lý tại field đó.

### Bảo vệ thao tác đọc ở service

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class BookService {

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(String id) {
        return bookRepository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @PreAuthorize("hasAuthority('book:internal:read')")
    public String findInternalNotes(String bookId) {
        return bookRepository.findInternalNotes(bookId);
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(String id, UpdateBookInput input) {
        return bookRepository.update(id, input);
    }
}
~~~

Mỗi method có một quyền rõ ràng:

- book:read cho phép đọc sách.
- book:internal:read cho phép đọc ghi chú nội bộ.
- book:write cho phép cập nhật sách.

Không gộp mọi quyền vào một authority chung như authenticated. Authority nên phản ánh hành động hoặc dữ liệu mà API đang bảo vệ.

### Nested resolver gọi service đã được bảo vệ

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "internalNotes")
    public String internalNotes(Book book) {
        return bookService.findInternalNotes(book.id());
    }
}
~~~

Khi client chọn Book.internalNotes, GraphQL gọi resolver của field đó. Resolver gọi BookService.findInternalNotes; Spring Security kiểm tra authority trước khi method service thực thi.

Nếu người dùng có book:read nhưng không có book:internal:read, họ vẫn có thể đọc title trong khi internalNotes bị từ chối. Quyền được kiểm tra đúng ở nơi lấy dữ liệu nhạy cảm.

Không để một property nhạy cảm tự động được đọc qua default property data fetcher mà không có kiểm soát. Nếu Book có getter internalNotes và không có resolver được bảo vệ, GraphQL có thể lấy trực tiếp property đó. Với field nhạy cảm, hãy cung cấp resolver/service có authorization rõ ràng hoặc không đưa dữ liệu nhạy cảm vào source object.

## Authorization theo object và ownership

Authority chung không đủ khi quyền phụ thuộc vào object cụ thể. Ví dụ, người dùng có thể sửa sách do mình sở hữu nhưng không được sửa sách của người khác.

Có thể đưa policy vào một bean chuyên trách:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("bookAuthorization")
public class BookAuthorization {

    private final BookPermissionService permissionService;

    public BookAuthorization(BookPermissionService permissionService) {
        this.permissionService = permissionService;
    }

    public boolean canReadInternalNotes(
            String bookId,
            Authentication authentication) {

        return permissionService.canReadInternalNotes(
                authentication.getName(), bookId);
    }

    public boolean canUpdate(
            String bookId,
            Authentication authentication) {

        return permissionService.canUpdate(
                authentication.getName(), bookId);
    }
}
~~~

Service có thể gọi policy bằng SpEL:

~~~java
@PreAuthorize(
        "hasAuthority('book:internal:read') and " +
        "@bookAuthorization.canReadInternalNotes(#p0, authentication)")
public String findInternalNotes(String bookId) {
    return bookRepository.findInternalNotes(bookId);
}

@PreAuthorize(
        "@bookAuthorization.canUpdate(#p0, authentication)")
public Book update(String bookId, UpdateBookInput input) {
    return bookRepository.update(bookId, input);
}
~~~

Trong ví dụ, #p0 là tham số đầu tiên của method. Có thể dùng tên tham số trong SpEL nếu build có metadata tên tham số hoặc dùng annotation Spring Security @P để đặt tên tường minh. Không nên dựa vào tên tham số không được giữ lại sau compile.

Policy nên kiểm tra ownership hoặc tenant ở server. Không tin ownerId, tenantId hoặc role do client gửi trong GraphQL arguments. Client chỉ gửi ID tài nguyên cần thao tác; server tra cứu và so sánh với principal đã xác thực.

Đối với mutation, ưu tiên kiểm tra quyền trước khi ghi dữ liệu bằng @PreAuthorize. Không dùng @PostAuthorize để kiểm tra quyền sau khi method đã thay đổi database, vì khi đó side effect có thể đã xảy ra trước khi từ chối kết quả.

## Đọc principal trong annotated controller

Spring for GraphQL hỗ trợ bind Principal hoặc @AuthenticationPrincipal vào tham số controller nếu có Spring Security context:

~~~java
import java.security.Principal;
import java.util.List;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class CurrentUserController {

    private final BookService bookService;

    public CurrentUserController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> myBooks(Principal principal) {
        return bookService.findOwnedBy(principal.getName());
    }
}
~~~

Hoặc lấy principal cụ thể:

~~~java
@QueryMapping
public UserProfile me(
        @AuthenticationPrincipal AppPrincipal principal) {
    return userService.profile(principal.userId());
}
~~~

Principal và @AuthenticationPrincipal giúp controller đọc danh tính hiện tại. Chúng không thay thế authorization ở service. Service vẫn cần bảo vệ các thao tác nhạy cảm vì cùng method có thể được gọi từ nhiều đường đi khác nhau.

Không lấy username hoặc userId từ GraphQL argument để thay thế principal. Nếu query có argument userId, server phải xác minh người gọi được phép truy cập user đó.

## Bảo vệ @BatchMapping

Batch mapping gom việc tải nested field cho nhiều parent object. Điều đó giúp giảm N+1 nhưng cũng làm authorization phức tạp hơn: một lần gọi batch có thể chứa nhiều Book thuộc các owner hoặc tenant khác nhau.

Một quyền chung có thể được kiểm tra ở method batch:

~~~java
@Service
public class AuthorService {

    @PreAuthorize("hasAuthority('author:read')")
    public Map<Book, Author> findAuthorsForBooks(List<Book> books) {
        // Bulk load authors for the requested books.
        return loadAuthors(books);
    }
}
~~~

Quyền author:read chỉ chứng minh người gọi được phép sử dụng chức năng đọc tác giả. Nó không tự chứng minh người đó được phép đọc tác giả liên kết với từng Book trong danh sách.

Nếu policy thay đổi theo parent object, hãy lọc hoặc kiểm tra từng key ở service/repository:

~~~java
@BatchMapping(typeName = "Book", field = "author")
public Map<Book, Author> author(
        List<Book> books,
        Principal principal) {

    return authorService.findAuthorsVisibleTo(
            books, principal.getName());
}
~~~

findAuthorsVisibleTo cần áp dụng policy cho từng Book trước khi tải hoặc trả Author. Với quan hệ không được phép hiển thị, API có thể chọn che giấu bằng giá trị null hoặc báo lỗi theo từng field, tùy contract và yêu cầu bảo mật. Không trả kết quả của tenant khác chỉ vì các key được gom chung trong một batch.

Khi dùng Map<Book, Author>, key phải tương ứng đúng source object và equality/hashCode phải ổn định. Nếu dùng List kết quả, phải giữ đúng thứ tự source. Authorization không được làm sai alignment giữa Book và Author.

Với dữ liệu nhiều tenant, cách an toàn và hiệu quả thường là đưa tenant/owner condition trực tiếp vào bulk repository query để database chỉ trả các bản ghi trong phạm vi được phép. Không tải toàn bộ dữ liệu rồi chỉ lọc ở controller.

## Authorization theo field khác với ẩn field ở client

Ẩn một field trong giao diện không bảo vệ dữ liệu. Client có thể tự gửi GraphQL document khác, dùng alias, fragment hoặc gọi endpoint trực tiếp.

Các chỉ thị @skip và @include chỉ điều khiển field có được thực thi trong một operation hay không; chúng không phải cơ chế phân quyền.

Tương tự, việc không hiển thị field trong UI hoặc bỏ field khỏi query mẫu không ngăn người dùng có quyền gửi một query khác để yêu cầu field đó.

Authorization phải chạy ở server cho mọi đường truy cập:

- Root query.
- Nested field.
- Mutation.
- Batch resolver và DataLoader.
- Resolver được gọi qua service hoặc entry point khác.

Hãy trả về DTO có đúng dữ liệu cần thiết và giữ các thuộc tính nhạy cảm sau một service method được bảo vệ. Không dựa vào quy ước tên field hoặc khả năng client không biết schema.

## AccessDeniedException và GraphQL error

Khi @PreAuthorize từ chối, Spring Security ném AccessDeniedException. Trong GraphQL, lỗi này xảy ra trong quá trình phân giải field, vì vậy response có thể chứa partial data cùng một error có path chỉ tới field bị từ chối.

Ví dụ:

~~~json
{
  "data": {
    "bookById": {
      "id": "book-101",
      "title": "Spring GraphQL",
      "internalNotes": null
    }
  },
  "errors": [
    {
      "message": "Access is denied",
      "path": ["bookById", "internalNotes"]
    }
  ]
}
~~~

Spring GraphQL cung cấp ErrorType.FORBIDDEN và ErrorType.UNAUTHORIZED để phân loại lỗi authorization. SecurityDataFetcherExceptionResolver là resolver có sẵn để xử lý Spring Security exception trong ứng dụng dùng transport không reactive, ví dụ Spring MVC. Với WebFlux hoặc policy lỗi riêng, hãy đăng ký resolver phù hợp và kiểm thử classification thực tế của phiên bản đang dùng.

Nếu exception không được resolver nào xử lý, Spring for GraphQL mặc định phân loại thành INTERNAL_ERROR với message tổng quát. Vì vậy, đừng mặc định mọi AccessDeniedException đều tự động trở thành FORBIDDEN trong mọi stack hoặc mọi cấu hình.

Nullability trong SDL quyết định phạm vi lỗi lan truyền:

| Khai báo field | Khi resolver bị từ chối |
| --- | --- |
| internalNotes: String | Field có thể trở thành null; các field anh em vẫn có thể trả về |
| internalNotes: String! | Null lan truyền lên object Book gần nhất có thể null |
| bookById: Book! và field con non-null lỗi | Lỗi có thể lan truyền tới root data |

Không thay đổi field thành nullable chỉ để che lỗi authorization. Hãy chọn nullability theo contract dữ liệu và quyết định rõ API muốn báo lỗi hay che giấu sự tồn tại của tài nguyên.

Nếu không muốn tiết lộ tài nguyên có tồn tại hay không, policy có thể trả kết quả NOT_FOUND cho cả trường hợp không tồn tại và không được phép xem. Cần áp dụng nhất quán để tránh tạo kênh dò tìm ID.

## Kiểm thử authorization

Kiểm thử ở hai cấp:

1. Service test xác minh method security thực sự chặn thao tác.
2. GraphQL integration test xác minh quyền được áp dụng qua resolver và response có path/error phù hợp.

Ví dụ service test:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class BookServiceSecurityTests {

    @Autowired
    private BookService bookService;

    @Test
    @WithMockUser(authorities = "book:internal:read")
    void internalReaderCanReadNotes() {
        String notes = bookService.findInternalNotes("book-101");
        assertThat(notes).isNotNull();
    }

    @Test
    @WithMockUser(authorities = "book:read")
    void regularReaderCannotReadInternalNotes() {
        assertThatThrownBy(
                () -> bookService.findInternalNotes("book-101"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Để chạy test, thêm spring-security-test vào test dependencies. Với policy object-level, tạo test cho owner đúng, owner khác, tenant khác và principal anonymous.

GraphQL integration test nên gửi query có cả field công khai và field được bảo vệ. Dùng security test support phù hợp với transport:

- Spring MVC: MockMvc với Spring Security test support hoặc WebGraphQlTester qua cấu hình security tương ứng.
- Spring WebFlux: WebTestClient và SecurityMockServerConfigurers.

Xác minh field công khai vẫn có dữ liệu, field nhạy cảm bị từ chối, error path chỉ đúng nested field và error classification là FORBIDDEN hoặc UNAUTHORIZED theo principal. Nếu field non-null, xác minh thêm null propagation lên parent.

Nên kiểm thử:

- Anonymous không thể gọi operation yêu cầu authentication.
- Người có book:read không thể đọc internalNotes.
- Người có book:internal:read có thể đọc internalNotes.
- Người dùng chỉ sửa được sách thuộc phạm vi được phép.
- Alias và fragment không bỏ qua authorization.
- Batch mapping không trả dữ liệu chéo tenant.
- Mutation bị từ chối trước khi có side effect.
- Các resolver khác vẫn trả partial data khi field độc lập bị từ chối.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @PreAuthorize không có tác dụng | Chưa bật @EnableMethodSecurity | Bật method security trong configuration |
| Chỉ bảo vệ /graphql nhưng field nhạy cảm vẫn lộ | HTTP URL security chỉ kiểm soát endpoint | Bảo vệ service method cung cấp field |
| Field nhạy cảm vẫn được trả về | Default property fetcher đọc trực tiếp getter | Tạo resolver gọi service đã bảo vệ hoặc bỏ dữ liệu nhạy cảm khỏi source object |
| Quyền bị bỏ qua khi service gọi method cùng bean | Self-invocation đi qua this thay vì proxy | Chuyển method được bảo vệ sang bean khác hoặc gọi qua proxy |
| Người dùng đọc được object của tenant khác | Chỉ kiểm tra role, không kiểm tra ownership/tenant | Dùng object-level policy và tenant condition ở repository |
| Batch mapping làm lộ dữ liệu chéo tenant | Chỉ kiểm tra quyền chung cho cả batch | Áp dụng policy theo từng source/key hoặc truy vấn bulk có tenant scope |
| AccessDeniedException thành INTERNAL_ERROR | Không có resolver phù hợp hoặc resolver không được đăng ký | Cấu hình security exception resolver và kiểm tra stack MVC/WebFlux |
| Cả object cha thành null | Field bị từ chối được khai báo non-null | Xem lại nullability và contract response |
| Mutation đã ghi dữ liệu rồi mới bị từ chối | Dùng kiểm tra hậu điều kiện cho thao tác ghi | Kiểm tra quyền trước khi thực hiện side effect |
| Client tự truyền userId để đọc dữ liệu người khác | Tin input client thay cho principal | Lấy danh tính từ SecurityContext và xác minh object ownership |

## Thực hành tổng hợp

Xây dựng authorization theo field cho API thư viện:

1. Khai báo Book.internalNotes là field nhạy cảm trong SDL.
2. Tạo authority book:read, book:internal:read và book:write.
3. Bật method security bằng @EnableMethodSecurity.
4. Bảo vệ BookService.findById, findInternalNotes và update bằng @PreAuthorize.
5. Tạo BookAuthorization để kiểm tra ownership hoặc tenant khi cần.
6. Viết @SchemaMapping cho internalNotes và gọi service đã bảo vệ.
7. Tạo @BatchMapping cho Book.author và kiểm tra quyền theo từng Book nếu policy phụ thuộc parent object.
8. Cấu hình GraphQL error resolver để AccessDeniedException được phân loại đúng.
9. Kiểm thử anonymous, reader, internal reader, editor và owner bằng @WithMockUser.
10. Viết GraphQL integration test để xác minh partial data, error path và null propagation.

Sau khi hoàn thành, hãy giải thích vì sao URL security không đủ cho GraphQL, vì sao service-level authorization bảo vệ được nhiều entry point và cách tránh lộ dữ liệu khi batch resolver tải nhiều object cùng lúc.

## Ghi nhớ

GraphQL dùng một endpoint chung nên HTTP URL security chỉ cung cấp lớp kiểm soát coarse-grained. Để phân quyền theo field, bật @EnableMethodSecurity và đặt @PreAuthorize trên service method cung cấp dữ liệu hoặc thực hiện thao tác. Dùng authority cho quyền chung, policy bean cho ownership và tenant scope. Bảo vệ cả nested field, batch mapping và mọi đường truy cập service; không dựa vào UI hoặc GraphQL selection set để giấu dữ liệu. AccessDeniedException cần được ánh xạ thành GraphQL error phù hợp; nullability quyết định partial response hay null propagation. Kiểm thử bằng Spring Security Test và GraphQlTester để xác nhận cả quyền truy cập lẫn dữ liệu thực sự được trả về.

## Tài liệu tham khảo

- [Spring for GraphQL – Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring GraphQL – SecurityDataFetcherExceptionResolver API](https://docs.spring.io/spring-graphql/docs/2.0.x/api/org/springframework/graphql/execution/SecurityDataFetcherExceptionResolver.html)
