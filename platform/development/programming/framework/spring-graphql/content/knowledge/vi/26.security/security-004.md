# Method security trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích method security và vai trò của nó bên cạnh HTTP request security.
- Bật method security bằng `@EnableMethodSecurity`.
- Dùng `@PreAuthorize` để kiểm tra quyền trước khi method chạy.
- Dùng `@PostAuthorize` để kiểm tra kết quả trả về khi phù hợp.
- Phân biệt role và authority trong biểu thức bảo mật.
- Bảo vệ Query, Mutation và nested field bằng service method.
- Kiểm tra quyền truy cập object theo owner hoặc tenant để tránh IDOR.
- Hiểu giới hạn của Spring AOP proxy và lỗi self-invocation.
- Phân biệt method security imperative với reactive method security.
- Ánh xạ lỗi từ chối truy cập thành GraphQL error an toàn.
- Kiểm thử quyền truy cập bằng `@WithMockUser` và `GraphQlTester`.

## 1. Method security là gì?

Method security là cơ chế kiểm tra quyền ngay tại ranh giới gọi method của một Spring bean. Thay vì chỉ xác thực hoặc phân quyền một HTTP request, ứng dụng có thể đặt quy tắc trên method nghiệp vụ để kiểm soát ai được phép gọi thao tác đó.

Trong Spring for GraphQL, một operation có thể gọi nhiều resolver:

- Root resolver như `@QueryMapping` hoặc `@MutationMapping`.
- Nested resolver như `@SchemaMapping`.
- Service và repository được gọi từ resolver.

Một GraphQL request có thể chọn nhiều field trong cùng operation. Vì vậy, kiểm tra quyền ở tầng service giúp bảo vệ nghiệp vụ bất kể method được gọi từ Query, Mutation, nested field, REST endpoint hay một luồng xử lý khác.

Ví dụ, người dùng có quyền đọc sách nhưng không có quyền sửa sách. Server cần kiểm tra quyền trước khi thực thi thao tác cập nhật, ngay cả khi client tự gửi Mutation mà giao diện người dùng không hiển thị.

Method security không thay thế authentication ở HTTP/WebSocket transport. Nó bổ sung lớp authorization tại nơi nghiệp vụ được thực hiện.

## 2. Bật method security

Với ứng dụng dùng Spring Security imperative, bật method security bằng `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Khi bật `@EnableMethodSecurity`:

- `@PreAuthorize` và `@PostAuthorize` được hỗ trợ mặc định.
- `@PreFilter` và `@PostFilter` cũng thuộc nhóm pre/post annotations.
- `@Secured` không được bật mặc định.
- JSR-250 annotations như `@RolesAllowed` không được bật mặc định.

Nếu ứng dụng cần `@Secured` hoặc `@RolesAllowed`, có thể bật rõ ràng:

~~~java
@Configuration
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
class MethodSecurityConfiguration {
}
~~~

Chỉ bật các annotation mà ứng dụng thực sự sử dụng. Một cấu hình method security cần được nạp trong Spring application context; chỉ thêm annotation vào method mà không bật cơ chế tương ứng sẽ không tạo ra kiểm tra quyền như mong đợi.

## 3. Authentication và authorization

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication:** người đang gọi là ai?
- **Authorization:** người đó có được phép thực hiện hành động này không?

Ví dụ, Spring Security có thể xác thực token và tạo một `Authentication` đại diện cho người dùng `alice`. Đối tượng này có thể chứa:

- Principal hoặc username.
- Các authority được cấp.
- Trạng thái authenticated.
- Thông tin xác thực hoặc metadata theo cơ chế security đang dùng.

Method security dùng `Authentication` hiện tại để đánh giá biểu thức quyền. Không lấy username hoặc role từ GraphQL argument rồi coi đó là danh tính đã xác thực.

Ví dụ request có thể gửi:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

`book-42` là ID tài nguyên client muốn truy cập. ID đó không chứng minh client sở hữu cuốn sách. Server phải dùng principal đã xác thực và dữ liệu quyền ở backend để quyết định.

## 4. Phân biệt role và authority

Spring Security biểu diễn quyền dưới dạng authority. Một authority có thể mô tả vai trò rộng hoặc một quyền cụ thể.

| Biểu thức | Ý nghĩa |
| --- | --- |
| `hasAuthority('book:read')` | Kiểm tra authority chính xác là `book:read` |
| `hasAuthority('book:write')` | Kiểm tra authority chính xác là `book:write` |
| `hasRole('ADMIN')` | Kiểm tra role với tiền tố mặc định `ROLE_`, tương đương authority `ROLE_ADMIN` |
| `hasAnyRole('ADMIN', 'EDITOR')` | Người gọi có một trong các role được chỉ định |
| `isAuthenticated()` | Người gọi đã được xác thực |
| `permitAll()` | Cho phép mọi người gọi method |
| `denyAll()` | Từ chối mọi lời gọi |

Với `hasRole('ADMIN')`, không truyền cả tiền tố `ROLE_` vào tham số. Nếu muốn kiểm tra chính xác một authority như `book:read`, dùng `hasAuthority`.

Trong ứng dụng GraphQL, authority theo hành động thường dễ biểu đạt hơn một role tổng quát:

- `book:read`
- `book:write`
- `book:notes:read`
- `book:publish`

Một người dùng có role `EDITOR` có thể được cấp một số authority đọc và sửa, trong khi người dùng `AUDITOR` chỉ có quyền đọc. Quy tắc ánh xạ role thành authority được quản lý ở authentication/authorization configuration.

## 5. Dùng @PreAuthorize để bảo vệ service method

`@PreAuthorize` kiểm tra biểu thức trước khi method đích được thực thi. Nếu biểu thức không thỏa mãn, Spring Security từ chối lời gọi và method body không chạy.

Ví dụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class BookService {

    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Book findById(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    @PreAuthorize("hasAuthority('book:write')")
    public Book update(UUID id, UpdateBookInput input) {
        Book book = repository.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));

        book.setTitle(input.title());
        return repository.save(book);
    }
}
~~~

Trong ví dụ:

- Người gọi phải có `book:read` để tìm sách.
- Người gọi phải có `book:write` để cập nhật sách.
- Nếu thiếu authority, method body không được thực thi.
- Quyền được kiểm tra tại service boundary, không phụ thuộc resolver nào gọi service.

Đặt kiểm tra ở service đặc biệt hữu ích khi cùng nghiệp vụ được gọi từ nhiều GraphQL field hoặc từ các transport khác nhau.

## 6. Kết nối method security với GraphQL resolver

Resolver có thể giữ nhiệm vụ nhận argument và chuyển tiếp tới service đã được bảo vệ:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class BookController {

    private final BookService bookService;

    BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") UUID id) {
        return bookService.findById(id);
    }

    @MutationMapping
    public Book updateBook(
            @Argument("id") UUID id,
            @Argument("input") UpdateBookInput input) {
        return bookService.update(id, input);
    }
}
~~~

SDL tương ứng:

~~~graphql
input UpdateBookInput {
    title: String!
}

type Book {
    id: ID!
    title: String!
}

type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBook(id: ID!, input: UpdateBookInput!): Book
}
~~~

Khi client gọi `Query.book`, service kiểm tra `book:read`. Khi client gọi `Mutation.updateBook`, service kiểm tra `book:write`.

Có thể đặt method security trực tiếp trên method controller trong một số thiết kế, nhưng bảo vệ service method giúp áp dụng quy tắc cho mọi caller của nghiệp vụ. Không nên chỉ dựa vào việc giao diện client ẩn nút hoặc field.

## 7. Bảo vệ nested field trong GraphQL

GraphQL cho phép client chọn field theo từng object. Một số field có thể chứa dữ liệu nhạy cảm hơn những field khác.

Ví dụ SDL:

~~~graphql
type Book {
    id: ID!
    title: String!
    internalNotes: String
}
~~~

Resolver của field nhạy cảm gọi một service method có authorization riêng:

~~~java
@SchemaMapping(typeName = "Book", field = "internalNotes")
public String internalNotes(Book book) {
    return bookService.readInternalNotes(book.getId());
}
~~~

Service:

~~~java
@PreAuthorize("hasAuthority('book:notes:read')")
public String readInternalNotes(UUID bookId) {
    return repository.findInternalNotesByBookId(bookId);
}
~~~

Người dùng có thể đọc `id` và `title` nhưng không được đọc `internalNotes` nếu thiếu authority `book:notes:read`.

Method security kiểm tra lời gọi service khi resolver cần field đó. GraphQL có thể trả partial data cùng error cho field bị từ chối, tùy nullability của schema và error handling đã cấu hình.

Một lưu ý quan trọng: field security phải được áp dụng cho mọi đường truy cập dữ liệu nhạy cảm. Nếu `internalNotes` cũng được trả về qua một service method khác không có bảo vệ, quy tắc trên một resolver không đủ để bảo vệ dữ liệu.

## 8. Kiểm tra quyền sở hữu object và chống IDOR

Chỉ kiểm tra quyền tổng quát như `book:read` có thể chưa đủ. Người dùng có quyền đọc sách nhưng chỉ được đọc sách thuộc tenant hoặc phạm vi của mình.

Đây là vấn đề object-level authorization. Nếu API chỉ kiểm tra người dùng có authority đọc rồi truy vấn theo ID client gửi, một người dùng có thể thử ID của tài nguyên thuộc người khác. Kiểu lỗi này thường được gọi là IDOR hoặc broken object-level authorization.

Có thể kiểm tra bằng authorization bean trong biểu thức:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;

@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book findVisibleBook(@P("bookId") UUID bookId) {
    return repository.findById(bookId)
            .orElseThrow(() -> new BookNotFoundException(bookId));
}
~~~

Authorization bean:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("bookAuthorization")
class BookAuthorization {

    private final BookAccessRepository accessRepository;

    BookAuthorization(BookAccessRepository accessRepository) {
        this.accessRepository = accessRepository;
    }

    public boolean canRead(Authentication authentication, UUID bookId) {
        String username = authentication.getName();

        return accessRepository.existsReadableBook(
                bookId,
                username
        );
    }
}
~~~

Trong ví dụ, `bookId` đến từ client nhưng `username` lấy từ `Authentication` đáng tin cậy. Backend kiểm tra quan hệ quyền giữa principal và tài nguyên.

Với multi-tenant system, tenant cần được xác định từ security context hoặc dữ liệu membership phía server. Không tin `tenantId` client gửi trong GraphQL variables như bằng chứng người dùng thuộc tenant đó.

Đối với truy vấn dữ liệu lớn, nên kết hợp authorization với query ở repository, ví dụ chỉ tải record thỏa `id` và `tenant_id` đã xác thực. Cách này giảm nguy cơ kiểm tra quyền sau khi đã lấy dữ liệu ngoài phạm vi.

## 9. Dùng tham số method trong biểu thức bảo mật

Biểu thức `@PreAuthorize` đôi khi cần tham chiếu tham số của method:

~~~java
@PreAuthorize("@bookAuthorization.canRead(authentication, #bookId)")
public Book findVisibleBook(@P("bookId") UUID bookId) {
    // ...
}
~~~

`@P("bookId")` từ Spring Security đặt tên tham số để biểu thức có thể tham chiếu bằng `#bookId` một cách rõ ràng.

Có thể dùng các alias vị trí như `#p0` hoặc `#a0` khi phù hợp, nhưng tên tham số có ý nghĩa thường dễ đọc và ít gây nhầm lẫn hơn.

Không đưa toàn bộ object input vào biểu thức nếu chỉ cần một vài giá trị. Giữ authorization expression ngắn, dễ kiểm thử; logic quyền phức tạp nên chuyển vào một authorization bean có tên rõ ràng.

## 10. Dùng @PostAuthorize để kiểm tra kết quả

`@PostAuthorize` đánh giá biểu thức sau khi method hoàn tất và có thể truy cập giá trị trả về thông qua `returnObject`.

Ví dụ:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PostAuthorize;

@PostAuthorize(
        "returnObject == null || returnObject.ownerUsername == authentication.name"
)
public Book findPrivateBook(UUID id) {
    return repository.findById(id).orElse(null);
}
~~~

Trong ví dụ, kết quả chỉ được trả về nếu sách không có hoặc chủ sở hữu của sách trùng với principal hiện tại. Nếu biểu thức không thỏa mãn, Spring Security từ chối lời gọi.

`@PostAuthorize` hữu ích khi cần kiểm tra một thuộc tính chỉ có sau khi method trả kết quả. Tuy nhiên, method đã chạy và dữ liệu có thể đã được tải trước khi kiểm tra.

Vì vậy:

- Dùng `@PreAuthorize` khi có thể kiểm tra quyền trước thao tác.
- Dùng `@PostAuthorize` cho các thao tác đọc mà quyền phụ thuộc vào object vừa tải.
- Không dùng `@PostAuthorize` như cơ chế bảo vệ mutation có side effect; việc ghi dữ liệu có thể đã xảy ra trước khi quyền hậu kiểm bị từ chối.
- Với truy vấn nhạy cảm, ưu tiên lọc ngay trong repository hoặc service để không tải dữ liệu ngoài phạm vi nếu có thể.

## 11. @PreFilter và @PostFilter

Spring Security còn hỗ trợ lọc phần tử collection bằng biểu thức bảo mật.

- `@PreFilter` lọc các phần tử đầu vào trước khi method chạy.
- `@PostFilter` lọc các phần tử kết quả sau khi method chạy.

Ví dụ:

~~~java
@PostFilter("filterObject.ownerUsername == authentication.name")
public List<Book> findBooksForCurrentUser() {
    return repository.findAll();
}
~~~

Ví dụ này loại bỏ các sách không thuộc người dùng hiện tại sau khi repository đã tải danh sách.

Với GraphQL, không nên mặc định dùng `@PostFilter` cho mọi field trả danh sách. Một số hệ quả:

- Repository có thể tải nhiều dữ liệu không cần thiết.
- Kết quả pagination và total count có thể không còn phản ánh đúng tập dữ liệu được phép xem.
- Client có thể nhận trang ít phần tử hơn dự kiến.
- Việc lọc sau khi tải có thể tăng chi phí bộ nhớ và thời gian.

Khi có thể, hãy áp dụng tenant/owner predicate ngay trong truy vấn database và tính pagination trên tập dữ liệu đã được phân quyền.

## 12. @Secured và @RolesAllowed

Ngoài pre/post annotations, có thể dùng các annotation đơn giản hơn nếu ứng dụng đã bật chúng.

Ví dụ với `@Secured`:

~~~java
@Secured("ROLE_ADMIN")
public void publishBook(UUID bookId) {
    // Publish book.
}
~~~

Ví dụ với JSR-250 `@RolesAllowed`:

~~~java
@RolesAllowed("ADMIN")
public void archiveBook(UUID bookId) {
    // Archive book.
}
~~~

Cấu hình bật cả hai:

~~~java
@Configuration
@EnableMethodSecurity(
        securedEnabled = true,
        jsr250Enabled = true
)
class MethodSecurityConfiguration {
}
~~~

`@Secured` thường nhận authority/role name chính xác, ví dụ `ROLE_ADMIN`. `@RolesAllowed` sử dụng role name và Spring áp dụng role prefix mặc định trong quá trình kiểm tra.

Các annotation này phù hợp với quy tắc role đơn giản. Khi cần kết hợp quyền, tham số method, trạng thái object hoặc policy bean, `@PreAuthorize` linh hoạt hơn.

## 13. Proxy và self-invocation

Method security của Spring dựa trên AOP interceptor. Lời gọi cần đi qua Spring proxy để security interceptor có cơ hội kiểm tra quyền.

Một số tình huống dễ làm kiểm tra không chạy:

- Tạo service bằng `new` thay vì inject bean từ Spring.
- Gọi method được bảo vệ từ một method khác trong cùng instance bằng `this`.
- Đặt annotation lên method private rồi kỳ vọng proxy chặn lời gọi nội bộ.
- Gọi implementation trực tiếp thay vì đi qua Spring-managed proxy.

Ví dụ self-invocation:

~~~java
@Service
class BookService {

    public Book loadAndReadNotes(UUID id) {
        // Lời gọi nội bộ này không đi qua proxy.
        return readPrivateBook(id);
    }

    @PreAuthorize("hasAuthority('book:notes:read')")
    public Book readPrivateBook(UUID id) {
        return repository.findById(id).orElseThrow();
    }
}
~~~

Nếu `loadAndReadNotes` gọi `readPrivateBook` trên cùng object, method security có thể bị bỏ qua vì lời gọi không đi qua proxy.

Cách tổ chức tốt hơn là chuyển method được bảo vệ sang một Spring service khác và inject service đó:

~~~java
@Service
class PrivateBookReader {

    @PreAuthorize("hasAuthority('book:notes:read')")
    public Book readPrivateBook(UUID id) {
        // Load private book.
        return repository.findById(id).orElseThrow();
    }
}
~~~

Giữ method security trên public service boundary, inject bean qua constructor và tránh self-invocation. Khi kiểm thử, lấy bean từ Spring context thay vì tự khởi tạo class.

## 14. Method security với reactive service

Nếu ứng dụng Spring GraphQL dùng WebFlux và service trả về `Mono` hoặc `Flux`, cần cấu hình reactive method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Ví dụ reactive service:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
class ReactiveBookService {

    private final ReactiveBookRepository repository;

    ReactiveBookService(ReactiveBookRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Mono<Book> findById(@P("bookId") UUID bookId) {
        return repository.findById(bookId);
    }

    @PreAuthorize("hasAuthority('book:read')")
    public Flux<Book> findAll() {
        return repository.findAll();
    }
}
~~~

Reactive method security sử dụng security context gắn với Reactor Context. Không giả định `ThreadLocal` của imperative security context luôn có mặt khi publisher chuyển scheduler.

Các nguyên tắc:

- Dùng `@EnableReactiveMethodSecurity` cho reactive method security.
- Giữ publisher reactive và không gọi `block()` trong resolver hoặc service.
- Truyền context qua Reactor pipeline theo cơ chế Spring Security hỗ trợ.
- Không chuyển tùy tiện sang executor khác rồi giả định principal tự động được truyền.
- Kiểm thử authorization với reactive pipeline thực tế.

`@EnableMethodSecurity` và `@EnableReactiveMethodSecurity` phục vụ các mô hình thực thi khác nhau. Chọn cấu hình theo loại service và stack đang dùng; không bật cả hai một cách máy móc mà không hiểu các interceptor tương ứng.

## 15. Method security không thay thế field và object authorization design

GraphQL cho phép client tự chọn field, alias và nested relation. Điều đó không có nghĩa server được phép chỉ kiểm tra quyền ở root resolver.

Ví dụ operation:

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

Có thể cần ba quy tắc khác nhau:

- Quyền đọc sách.
- Quyền đọc ghi chú nội bộ.
- Quyền xem thông tin tác giả.

Hãy xác định security boundary cho từng nghiệp vụ:

| Boundary | Ví dụ kiểm tra |
| --- | --- |
| Root Query | Người gọi có `book:read` không? |
| Nested field nhạy cảm | Người gọi có `book:notes:read` không? |
| Object-level | Sách có thuộc tenant hoặc phạm vi người gọi không? |
| Mutation | Người gọi có `book:write` và quyền sửa object cụ thể không? |
| Service | Mọi caller đều phải tuân thủ cùng quy tắc nghiệp vụ |

Không dựa vào schema ẩn field hoặc UI ẩn nút để bảo vệ dữ liệu. Client có thể gửi GraphQL document tùy ý; server phải kiểm tra quyền tại mỗi boundary cần thiết.

## 16. Xử lý AccessDeniedException trong GraphQL response

Khi method security từ chối lời gọi, Spring Security có thể ném `AccessDeniedException`. Trong GraphQL execution, exception cần được chuyển thành GraphQL error theo contract của API.

Có thể dùng `@GraphQlExceptionHandler` trong global `@ControllerAdvice` để trả thông báo an toàn:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import java.util.Map;

import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.security.access.AccessDeniedException;

@ControllerAdvice
class GraphQlSecurityExceptionAdvice {

    @GraphQlExceptionHandler
    public GraphQLError handleAccessDenied(
            AccessDeniedException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.FORBIDDEN)
                .message("Bạn không có quyền thực hiện thao tác này.")
                .extensions(Map.of("code", "FORBIDDEN"))
                .build();
    }
}
~~~

Không trả exception message hoặc stack trace cho client. Nếu chính sách bảo mật cần tránh tiết lộ tài nguyên có tồn tại hay không, có thể dùng cùng thông báo cho trường hợp không tìm thấy và không được phép truy cập.

GraphQL response có thể chứa partial data cùng error ở field bị từ chối. Nếu field được khai báo non-null, null propagation có thể làm parent field trở thành null. Hãy thiết kế nullability và error contract nhất quán.

## 17. Kiểm thử method security trong GraphQL

Nên kiểm thử qua GraphQL operation để xác minh resolver, service proxy và error mapping hoạt động cùng nhau.

Spring Security Test cung cấp `@WithMockUser` để tạo Authentication cho test. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureHttpGraphQlTester
class BookMethodSecurityTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Test
    @WithMockUser(authorities = "book:read")
    void readerCanQueryBook() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .path("book.id")
                .entity(String.class)
                .isEqualTo("book-42");
    }

    @Test
    @WithMockUser
    void userWithoutBookAuthorityIsDenied() {
        graphQlTester.document("""
                query {
                    book(id: "book-42") {
                        id
                        title
                    }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors ->
                        assertThat(errors).anySatisfy(error ->
                                assertThat(error.getExtensions())
                                        .containsEntry("code", "FORBIDDEN")
                        )
                );
    }
}
~~~

Test này giả định ứng dụng đã cấu hình GraphQL HTTP tester, method security và error advice. Dependency `spring-security-test` cần có trong test scope.

Nên có các nhóm test:

- Người có authority đọc được Query tương ứng.
- Người thiếu authority bị từ chối trước khi service method thực thi.
- Người có `book:read` nhưng thiếu `book:write` không thể gọi Mutation cập nhật.
- Field `internalNotes` bị từ chối khi thiếu `book:notes:read`, trong khi field công khai vẫn trả dữ liệu nếu schema cho phép.
- Người dùng không thể truy cập object thuộc tenant khác bằng cách đoán ID.
- `@PostAuthorize` từ chối kết quả không thuộc người gọi.
- Reactive method security hoạt động trong Reactor Context.
- Self-invocation không tạo ra một đường gọi bỏ qua security boundary.

Kiểm thử service method trực tiếp cũng hữu ích, nhưng hãy lấy bean từ Spring context để lời gọi đi qua proxy. Test GraphQL bổ sung bằng chứng rằng security được áp dụng ở đúng đường thực thi của API.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@PreAuthorize` không có tác dụng | Chưa bật `@EnableMethodSecurity` hoặc method không đi qua proxy | Bật cấu hình và kiểm tra bean invocation |
| `@Secured` không chạy | `securedEnabled` vẫn là false | Bật `securedEnabled = true` |
| `@RolesAllowed` không chạy | `jsr250Enabled` chưa bật | Bật `jsr250Enabled = true` |
| `hasRole('ADMIN')` luôn false | Authority không có `ROLE_ADMIN` hoặc role mapping sai | Kiểm tra role prefix và Authentication |
| Người dùng đọc được object tenant khác | Chỉ kiểm tra authority chung, không kiểm tra ownership | Thêm object-level authorization và tenant predicate |
| Mutation đã ghi dữ liệu rồi mới bị từ chối | Dùng `@PostAuthorize` cho method có side effect | Dùng `@PreAuthorize` trước thao tác |
| Self-invocation bỏ qua kiểm tra | Lời gọi nội bộ không qua proxy | Tách method được bảo vệ sang bean khác |
| `@PostFilter` làm pagination sai | Lọc sau khi repository đã phân trang | Lọc ở query database trước pagination |
| Reactive authorization không thấy principal | Security context không được truyền trong Reactor Context | Dùng reactive method security và context propagation phù hợp |
| Client thấy exception message nội bộ | Không ánh xạ `AccessDeniedException` an toàn | Chuẩn hóa GraphQL error message và code |
| UI ẩn field nhưng API vẫn trả dữ liệu | Chỉ bảo vệ ở frontend | Kiểm tra quyền tại resolver/service boundary |

## 19. Quy trình triển khai method security

Khi thêm method security cho GraphQL API, hãy thực hiện theo trình tự:

1. **Xác định nghiệp vụ cần bảo vệ.** Liệt kê Query, Mutation và nested field có dữ liệu hoặc hành động nhạy cảm.
2. **Xác định danh tính.** Dùng Authentication do Spring Security xác thực; không tin username hoặc tenant từ client.
3. **Định nghĩa authority.** Chọn quyền cụ thể như `book:read`, `book:write` và `book:notes:read`.
4. **Bật method security.** Dùng `@EnableMethodSecurity` cho imperative hoặc `@EnableReactiveMethodSecurity` cho reactive.
5. **Đặt policy tại service boundary.** Dùng `@PreAuthorize` trước các thao tác cần bảo vệ.
6. **Kiểm tra object ownership.** Kết hợp principal với owner/tenant trong backend query.
7. **Dùng hậu kiểm có chủ đích.** Chỉ dùng `@PostAuthorize` khi quyền phụ thuộc kết quả và method không gây side effect nguy hiểm.
8. **Kiểm tra proxy.** Tránh self-invocation và gọi service ngoài Spring container.
9. **Ánh xạ lỗi an toàn.** Chuyển `AccessDeniedException` thành GraphQL error không tiết lộ thông tin nội bộ.
10. **Kiểm thử quyền.** Bao gồm user được phép, user bị từ chối, field nhạy cảm, object tenant khác và reactive execution.

## 20. Tổng kết

Method security cho phép kiểm tra quyền ngay tại lời gọi method nghiệp vụ. Trong Spring for GraphQL, `@EnableMethodSecurity` kích hoạt các annotation như `@PreAuthorize` và `@PostAuthorize`; service method có thể bảo vệ Query, Mutation và nested field bất kể caller đến từ resolver nào.

Dùng `@PreAuthorize` để chặn trước khi thao tác chạy, phân biệt role với authority, và bổ sung object-level authorization để kiểm tra owner hoặc tenant. `@PostAuthorize` phù hợp với một số thao tác đọc nhưng không nên dùng để bảo vệ mutation đã có side effect. Method security dựa trên Spring AOP proxy nên cần tránh self-invocation. Với WebFlux, dùng reactive method security và bảo đảm security context đi qua Reactor Context. Cuối cùng, ánh xạ lỗi từ chối truy cập thành GraphQL error an toàn và kiểm thử cả trường hợp được phép lẫn bị từ chối bằng `GraphQlTester`.

