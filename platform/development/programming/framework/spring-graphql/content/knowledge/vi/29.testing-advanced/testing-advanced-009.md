# Test authorization

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao cần kiểm thử authorization ở cả HTTP endpoint và từng GraphQL field.
- Phân biệt authentication với authorization.
- Bật method security bằng `@EnableMethodSecurity`.
- Bảo vệ service method bằng `@PreAuthorize` và `@PostAuthorize`.
- Tạo test user với role và authority cụ thể.
- Dùng `@WithMockUser`, `@WithAnonymousUser` và `spring-security-test`.
- Kiểm thử field-level authorization thông qua `GraphQlTester`.
- Gửi credential qua `HttpGraphQlTester` khi kiểm thử HTTP integration.
- Phân biệt HTTP 401/403 với GraphQL execution errors.
- Kiểm tra partial data, error path và việc dữ liệu nhạy cảm không bị trả về.
- Nhận biết các lỗi thường gặp khi test security trong Spring for GraphQL.

## 1. Authentication và authorization trong GraphQL

Authentication trả lời câu hỏi: người gửi request là ai? Authorization trả lời câu hỏi: người đó được phép thực hiện hành động hoặc đọc dữ liệu nào?

Với một REST API, mỗi endpoint thường có URL riêng. Với GraphQL, nhiều operation dùng chung một endpoint, thường là `/graphql`. Vì vậy, chỉ bảo vệ URL giúp chặn người chưa đăng nhập, nhưng không đủ để phân biệt quyền truy cập giữa các Query, Mutation hoặc field.

Ví dụ, hai người dùng cùng gửi request tới `POST /graphql`:

- Người dùng có quyền đọc thông tin sách công khai.
- Người dùng có quyền đọc thêm ghi chú nội bộ của sách.

Cả hai có thể được phép gọi endpoint và thực hiện Query `bookById`, nhưng chỉ người có authority phù hợp mới được đọc field `privateNotes`.

Spring for GraphQL khuyến nghị kết hợp hai lớp:

1. Request-level security bảo vệ endpoint và xác thực request.
2. Method-level security bảo vệ các service method thực hiện công việc cụ thể cho từng phần dữ liệu.

Nhờ context propagation, Spring Security context có thể được truyền từ HTTP transport qua GraphQL engine tới DataFetcher. Do đó, các annotation như `@PreAuthorize` trên service method có thể áp dụng khi GraphQL resolve field.

## 2. Bảo vệ endpoint không thay thế field authorization

Có thể cấu hình Spring Security yêu cầu người dùng đăng nhập trước khi truy cập GraphQL endpoint:

~~~java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

Ví dụ trên dùng HTTP Basic để minh họa authentication. Ứng dụng thực tế có thể dùng session, OAuth2 Resource Server, JWT hoặc cơ chế xác thực khác.

Nếu request không có credential hợp lệ, Spring Security có thể chặn request trước khi GraphQL engine thực thi operation. Tùy cơ chế authentication và authorization, HTTP response có thể là:

- `401 Unauthorized`: request chưa được xác thực hợp lệ.
- `403 Forbidden`: người dùng đã xác thực nhưng không được phép truy cập endpoint.

Khi endpoint chỉ cho phép người dùng đã đăng nhập, mọi GraphQL operation cùng chia sẻ một URL đều đi qua điều kiện đó. Điều kiện này không thể thay thế quyền riêng cho `bookById`, `privateNotes` hoặc một mutation cụ thể.

Với GraphQL API dùng session cookie cho trình duyệt, cần giữ và kiểm thử CSRF protection. Ví dụ cấu hình HTTP Basic ở trên không vô hiệu hóa CSRF. Chỉ cân nhắc tắt CSRF cho API stateless khi kiến trúc xác thực và cách client gửi credential đã được đánh giá phù hợp.

## 3. Bật method security

Spring Boot Starter Security không tự bật method-level authorization. Cần thêm `@EnableMethodSecurity` vào một configuration class:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau khi bật, Spring Security có thể áp dụng các annotation như:

- `@PreAuthorize`: kiểm tra quyền trước khi gọi method.
- `@PostAuthorize`: kiểm tra kết quả trước khi trả về caller.
- `@PreFilter` và `@PostFilter`: lọc tham số hoặc kết quả theo expression.
- `@Secured`: cơ chế cũ hơn, cần bật riêng bằng `securedEnabled = true`.

Trong đa số trường hợp mới, ưu tiên `@PreAuthorize` vì có thể kiểm tra role, authority, method argument và bean authorization.

## 4. Bảo vệ service method bằng @PreAuthorize

Giả sử GraphQL API cho phép người dùng đọc thông tin cơ bản của một cuốn sách, nhưng chỉ một số người được xem ghi chú nội bộ.

Schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  privateNotes: String
}
~~~

Service chịu trách nhiệm đọc ghi chú nội bộ:

~~~java
@Service
public class BookAccessService {

    @PreAuthorize("hasAuthority('book:private:read')")
    public String findPrivateNotes(String bookId) {
        return "Internal review: verify publisher contract";
    }
}
~~~

`@PreAuthorize` được kiểm tra trước khi method chạy. Người dùng cần có authority chính xác là `book:private:read`.

Controller ánh xạ field GraphQL:

~~~java
@Controller
public class BookController {

    private final BookService bookService;
    private final BookAccessService bookAccessService;

    public BookController(
            BookService bookService,
            BookAccessService bookAccessService) {
        this.bookService = bookService;
        this.bookAccessService = bookAccessService;
    }

    @QueryMapping
    public Book bookById(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "privateNotes")
    public String privateNotes(Book book) {
        return bookAccessService.findPrivateNotes(book.id());
    }
}
~~~

Khi client query:

~~~graphql
query {
  bookById(id: "b-01") {
    id
    title
    privateNotes
  }
}
~~~

GraphQL thực thi root field `bookById`, sau đó resolve `privateNotes`. Khi DataFetcher gọi `BookAccessService.findPrivateNotes(...)`, Spring Security kiểm tra authority của người dùng hiện tại.

Nếu người dùng không có quyền, method bị từ chối và GraphQL ghi nhận lỗi ở field tương ứng. Vì `privateNotes` được khai báo nullable, phần dữ liệu cơ bản của Book vẫn có thể được trả về.

Cách đặt authorization ở service giúp bảo vệ dữ liệu kể cả khi service được gọi từ một GraphQL field khác, REST endpoint hoặc một luồng xử lý nội bộ khác. Không nên chỉ ẩn field trên giao diện client rồi xem đó là cơ chế bảo mật.

## 5. Phân biệt role và authority

Spring Security phân biệt role và authority:

- `hasRole('ADMIN')` kiểm tra authority có tiền tố mặc định `ROLE_`, tức `ROLE_ADMIN`.
- `hasAuthority('book:private:read')` kiểm tra chính xác authority được chỉ định.

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteBook(String bookId) {
    // ...
}

@PreAuthorize("hasAuthority('book:private:read')")
public String findPrivateNotes(String bookId) {
    // ...
}
~~~

Trong test, `@WithMockUser(roles = "ADMIN")` tạo người dùng có `ROLE_ADMIN`. Nếu cần authority không có tiền tố role, dùng thuộc tính `authorities`:

~~~java
@WithMockUser(authorities = "book:private:read")
~~~

Không dùng `roles = "book:private:read"` vì Spring sẽ tự thêm tiền tố `ROLE_` và authority tạo ra sẽ không khớp expression.

## 6. Kiểm tra quyền sở hữu dữ liệu

Có quyền đọc một loại dữ liệu không đồng nghĩa có quyền đọc mọi bản ghi thuộc loại đó. Với dữ liệu theo người sở hữu hoặc tenant, cần kiểm tra cả quyền và đối tượng cụ thể.

Có thể dùng method argument trong expression:

~~~java
@Service
public class DocumentService {

    @PreAuthorize("@documentAuthorization.canRead(#documentId, authentication)")
    public Document findById(String documentId) {
        return documentRepository.findById(documentId)
                .orElseThrow(DocumentNotFoundException::new);
    }
}
~~~

Bean authorization có thể kiểm tra người dùng hiện tại có quyền trên đúng document hay không:

~~~java
@Component("documentAuthorization")
public class DocumentAuthorization {

    private final DocumentRepository repository;

    public DocumentAuthorization(DocumentRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(
            String documentId,
            Authentication authentication) {

        return repository.existsByIdAndOwnerUsername(
                documentId,
                authentication.getName());
    }
}
~~~

Nếu dùng tên tham số trong SpEL như `#documentId`, cần bảo đảm tên tham số được Spring Security phát hiện. Có thể biên dịch với tùy chọn `-parameters` hoặc dùng annotation tham số phù hợp như `@P`.

Với trường hợp cần kiểm tra object trả về, `@PostAuthorize` cũng có thể dùng:

~~~java
@PostAuthorize("returnObject.ownerUsername == authentication.name")
public Document findById(String documentId) {
    return documentRepository.findById(documentId)
            .orElseThrow(DocumentNotFoundException::new);
}
~~~

`@PostAuthorize` phù hợp với một số thao tác đọc cần xác nhận quyền sở hữu sau khi đã lấy object. Không nên dùng nó để bảo vệ method ghi dữ liệu vì side effect có thể đã xảy ra trước khi kết quả bị từ chối. Với mutation, ưu tiên kiểm tra quyền trước khi thực hiện thay đổi.

## 7. Thêm Spring Security Test

Để sử dụng `@WithMockUser`, `@WithAnonymousUser` và các tiện ích kiểm thử security, thêm `spring-security-test` trong test scope.

Gradle:

~~~groovy
testImplementation("org.springframework.security:spring-security-test")
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Hãy dùng dependency management của Spring Boot để chọn phiên bản tương thích với Spring Security đang chạy. Không cần khai báo phiên bản riêng nếu project đã dùng Spring Boot dependency management.

## 8. Test service authorization với @WithMockUser

`@WithMockUser` thiết lập một `SecurityContext` giả cho test hiện tại. Đây là cách thuận tiện để kiểm tra trực tiếp method có `@PreAuthorize`.

Ví dụ test:

~~~java
@SpringBootTest
class BookAccessServiceTests {

    @Autowired
    BookAccessService bookAccessService;

    @Test
    @WithMockUser(authorities = "book:private:read")
    void userWithPermissionCanReadPrivateNotes() {
        String notes = bookAccessService.findPrivateNotes("b-01");

        assertThat(notes)
                .contains("Internal review");
    }

    @Test
    @WithMockUser(authorities = "book:summary:read")
    void userWithoutPermissionCannotReadPrivateNotes() {
        assertThatThrownBy(() ->
                bookAccessService.findPrivateNotes("b-01"))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Test đầu tiên chạy với user có authority cần thiết nên method được thực thi. Test thứ hai dùng authority khác, vì vậy Spring Security ném `AccessDeniedException` trước khi method thực thi.

Cần inject bean thật đã được Spring quản lý để method security proxy có hiệu lực. Nếu thay chính `BookAccessService` bằng Mockito mock, test sẽ gọi mock trực tiếp và không kiểm tra được proxy authorization.

Có thể dùng `@WithMockUser(username = "alice", roles = "ADMIN")` để kiểm tra rule theo role. Với user ẩn danh, dùng `@WithAnonymousUser`.

## 9. Test với principal tùy chỉnh

`@WithMockUser` tạo principal mặc định của Spring Security. Nếu ứng dụng cần principal có kiểu riêng, ví dụ `CustomUserPrincipal` chứa tenant ID hoặc user ID, hãy dùng `@WithUserDetails` hoặc `@WithSecurityContext`.

Ví dụ:

~~~java
@Test
@WithUserDetails("alice")
void userDetailsPrincipalCanAccessOwnedDocument() {
    Document document = documentService.findById("doc-01");

    assertThat(document.ownerUsername()).isEqualTo("alice");
}
~~~

`@WithUserDetails` sử dụng `UserDetailsService` trong application context để nạp user thật cho test. User phải tồn tại trong test fixture.

Nếu principal của ứng dụng không phải UserDetails hoặc cần thêm claims, có thể tạo annotation test riêng dựa trên `@WithSecurityContext` và `WithSecurityContextFactory`.

## 10. Phân biệt @WithMockUser với HTTP integration test

Một điểm rất quan trọng: `@WithMockUser` đặt SecurityContext vào `SecurityContextHolder` của thread đang chạy test.

Khi test gửi HTTP request tới server đang chạy ở một cổng riêng, request được xử lý trên server thread khác. SecurityContext do `@WithMockUser` tạo trên test thread không tự động trở thành credential của HTTP request đó.

Vì vậy:

- Dùng `@WithMockUser` cho test gọi trực tiếp service method hoặc các test in-process phù hợp.
- Với HTTP integration test, gửi authentication credential qua HTTP request, ví dụ Basic Authentication hoặc bearer token.
- Không dùng `@WithMockUser` làm bằng chứng rằng một request HTTP từ client thật đã được xác thực.

Spring Security Test cũng cung cấp cơ chế test cho WebFlux và các request mock. Tuy nhiên, cần phân biệt rõ mock security context của test với credential được gửi qua một HTTP request thật.

Nếu kiểm thử reactive method security trực tiếp, Spring Security Test còn cần `ReactorContextTestExecutionListener` để đưa security context vào Reactor Context. Với test dùng đầy đủ Spring Test integration, kiểm tra test execution listeners đã được đăng ký theo cấu hình của project.

## 11. Cấu hình test user cho HTTP GraphQL

Giả sử test application dùng HTTP Basic và có hai user:

- `owner` có authority `book:private:read`.
- `viewer` chỉ có authority `book:summary:read`.

Một test configuration đơn giản:

~~~java
@TestConfiguration
@EnableMethodSecurity
public class GraphQlAuthorizationTestConfiguration {

    @Bean
    UserDetailsService testUsers() {
        UserDetails owner = User.withUsername("owner")
                .password("{noop}test-password")
                .authorities("book:private:read")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}test-password")
                .authorities("book:summary:read")
                .build();

        return new InMemoryUserDetailsManager(owner, viewer);
    }

    @Bean
    SecurityFilterChain testSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/graphql").authenticated()
                        .anyRequest().permitAll())
                .httpBasic(Customizer.withDefaults())
                .csrf(csrf -> csrf.disable())
                .build();
    }
}
~~~

`{noop}` chỉ được dùng để minh họa password trong test. Không dùng password encoder này cho tài khoản production. Ví dụ cũng tắt CSRF để tập trung vào API test dùng Basic Authentication; nếu ứng dụng dùng session cookie hoặc browser authentication, hãy giữ CSRF protection và gửi CSRF token trong test.

Cấu hình trên giả định test context chỉ có một security filter chain phù hợp với endpoint. Nếu ứng dụng có nhiều `SecurityFilterChain`, cần kiểm tra matcher và thứ tự để test thực sự chạy qua chain dự kiến.

Trong ứng dụng, `@EnableMethodSecurity` cần được bật trong cấu hình method security. Có thể đặt nó trong application configuration thay vì chỉ đặt trong test configuration nếu ứng dụng cần bảo vệ service ở production.

## 12. Test field authorization bằng HttpGraphQlTester

Spring Boot có thể cấu hình `HttpGraphQlTester` để gọi GraphQL endpoint. Dùng `mutate()` để tạo tester có header authentication riêng cho từng user.

Ví dụ test người có quyền:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
@Import(GraphQlAuthorizationTestConfiguration.class)
class GraphQlAuthorizationIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Test
    void ownerCanReadPrivateNotes() {
        HttpGraphQlTester ownerTester = graphQlTester.mutate()
                .headers(headers ->
                        headers.setBasicAuth("owner", "test-password"))
                .build();

        ownerTester.document("""
                query {
                    bookById(id: "b-01") {
                        id
                        title
                        privateNotes
                    }
                }
                """)
                .execute()
                .path("bookById.privateNotes")
                .entity(String.class)
                .isEqualTo("Internal review: verify publisher contract");
    }
}
~~~

Request được gửi qua HTTP tới server đang chạy. Header Basic Authentication xác định user là `owner`; service method kiểm tra authority `book:private:read` và cho phép truy cập.

Kiểm thử user không có quyền:

~~~java
@Test
void viewerCannotReadPrivateNotesButCanReadBook() {
    HttpGraphQlTester viewerTester = graphQlTester.mutate()
            .headers(headers ->
                    headers.setBasicAuth("viewer", "test-password"))
            .build();

    GraphQlTester.Response response = viewerTester.document("""
            query {
                bookById(id: "b-01") {
                    id
                    title
                    privateNotes
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors)
                    .anyMatch(error ->
                            error.getPath().contains("privateNotes")));

    response.path("bookById.id")
            .entity(String.class)
            .isEqualTo("b-01");

    response.path("bookById.privateNotes")
            .valueIsNull();
}
~~~

Test xác nhận ba điều:

1. Người dùng vẫn đọc được field công khai `bookById.id`.
2. Field `privateNotes` bị từ chối và tạo GraphQL error có path tương ứng.
3. Giá trị nhạy cảm không xuất hiện trong phần data.

Không nên chỉ kiểm tra response có errors. Hãy kiểm tra cả data và path để chứng minh field được bảo vệ đúng vị trí trong GraphQL response.

## 13. Kiểm tra HTTP 401 và 403 riêng với GraphQL errors

Có hai tình huống authorization khác nhau:

**Endpoint bị chặn trước GraphQL execution**

Nếu user chưa đăng nhập và endpoint yêu cầu authentication, Spring Security chặn request ở HTTP layer. Response có thể là HTTP 401. Nếu user đã đăng nhập nhưng không có quyền gọi endpoint, response có thể là HTTP 403.

Dùng `WebTestClient` để kiểm tra status code HTTP trực tiếp:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of(
                "query",
                "{ bookById(id: \"b-01\") { id } }"))
        .exchange()
        .expectStatus()
        .isUnauthorized();
~~~

Ví dụ giả định test client không gửi authentication và endpoint yêu cầu đăng nhập. Trong test cần inject hoặc tạo `WebTestClient` được bind tới đúng application context/server.

**Một field bị từ chối trong lúc GraphQL execution**

Nếu endpoint cho phép user đăng nhập, nhưng một field yêu cầu authority cao hơn, GraphQL engine vẫn có thể thực thi các field khác và trả response có cả `data` lẫn `errors`. Đây là trường hợp dùng `HttpGraphQlTester.execute()` để kiểm tra field path và partial data.

Không nên nhầm hai loại kết quả:

| Tình huống | Tầng xử lý | Cách kiểm thử |
|---|---|---|
| Chưa xác thực, endpoint yêu cầu đăng nhập | HTTP Security | WebTestClient kiểm tra 401 |
| Đã xác thực, không được gọi endpoint | HTTP Security | WebTestClient kiểm tra 403 |
| Được gọi endpoint nhưng thiếu quyền một field | Method Security trong DataFetcher | GraphQlTester kiểm tra errors và partial data |
| Có quyền field nhưng không sở hữu object | Object-level authorization | GraphQlTester kiểm tra field error và dữ liệu không bị lộ |

Với HTTP-based tester, nếu endpoint trả 401 hoặc 403 trước khi GraphQL response được tạo, `execute()` có thể báo lỗi do status HTTP không phù hợp với GraphQL response mong đợi. Khi cần xác nhận status transport, hãy dùng WebTestClient trực tiếp.

## 14. Test authorization cho Mutation

Mutation thường thay đổi trạng thái dữ liệu, vì vậy cần kiểm tra quyền trước khi thực hiện side effect.

Ví dụ service:

~~~java
@Service
public class BookAdminService {

    @PreAuthorize("hasAuthority('book:delete')")
    public void deleteBook(String bookId) {
        bookRepository.deleteById(bookId);
    }
}
~~~

Test người có quyền:

~~~java
@Test
@WithMockUser(authorities = "book:delete")
void userWithDeleteAuthorityCanDeleteBook() {
    bookAdminService.deleteBook("b-01");

    verify(bookRepository).deleteById("b-01");
}
~~~

Test người không có quyền:

~~~java
@Test
@WithMockUser(authorities = "book:read")
void userWithoutDeleteAuthorityCannotDeleteBook() {
    assertThatThrownBy(() ->
            bookAdminService.deleteBook("b-01"))
            .isInstanceOf(AccessDeniedException.class);

    verifyNoInteractions(bookRepository);
}
~~~

Test thứ hai xác nhận repository không bị gọi. Đây là bằng chứng quan trọng rằng authorization được kiểm tra trước side effect.

Với mutation, nên kiểm tra cả hai khía cạnh:

- Người không đủ quyền không thể thay đổi dữ liệu.
- Người có quyền thực hiện được mutation và nhận response đúng.

## 15. Test authorization với GraphQlTest

`@GraphQlTest` phù hợp để kiểm thử GraphQL controller mà không cần HTTP server. Tuy nhiên, đây là test slice nên không tự động nạp mọi service và security configuration của ứng dụng.

Nếu cần test method security trong slice test:

- Import cấu hình method security cần thiết.
- Cung cấp service thật đã được Spring proxy nếu muốn kiểm tra annotation.
- Mock repository hoặc dependency sâu hơn thay vì mock chính service đang được bảo vệ.
- Xác nhận security context được cung cấp cho cách thực thi test đang dùng.

Ví dụ khung test:

~~~java
@GraphQlTest(BookController.class)
@Import({
        MethodSecurityConfiguration.class,
        BookAccessService.class
})
class BookFieldSecuritySliceTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    @WithMockUser(authorities = "book:private:read")
    void authorizedUserCanResolvePrivateField() {
        // Arrange test fixtures, then execute the GraphQL document.
    }
}
~~~

Đây là khung minh họa cấu trúc test slice; cấu hình import cụ thể phụ thuộc constructor và dependency thật của ứng dụng. Nếu test cần security filter ở HTTP transport, `@GraphQlTest` không đủ vì annotation này không khởi động transport/server. Khi đó hãy dùng full integration test với `@SpringBootTest` và `HttpGraphQlTester`.

Một lỗi phổ biến là dùng `@MockitoBean BookAccessService` rồi kết luận `@PreAuthorize` hoạt động. Mock thay thế bean proxy nên test đó chỉ xác nhận GraphQL controller gọi mock, không xác nhận method security. Hãy test service security bằng bean thật hoặc test toàn bộ ứng dụng.

## 16. Context propagation và SecurityContext

GraphQL Java có thể thực thi DataFetcher trên thread khác với thread nhận HTTP request. Nếu code bảo mật phụ thuộc vào `SecurityContextHolder`, việc truyền context là rất quan trọng.

Spring for GraphQL hỗ trợ context propagation từ transport tới GraphQL engine và DataFetcher:

- Với Spring MVC, ThreadLocal context từ request handling thread có thể được truyền tới thread thực thi DataFetcher.
- Với Spring WebFlux, Reactor Context từ pipeline request có thể được sử dụng trong quá trình thực thi reactive.
- Spring Security có thể tận dụng cơ chế này để cung cấp Authentication cho method security.

Khi test thấy `@PreAuthorize` hoạt động khi gọi service trực tiếp nhưng thất bại trong GraphQL request, hãy kiểm tra:

1. Method security đã được bật chưa.
2. Service được gọi có phải Spring-managed proxy không.
3. HTTP request có credential hợp lệ không.
4. Test đang dùng server-side tester, mock transport hay live HTTP server.
5. Reactive pipeline hoặc executor tùy chỉnh có làm mất context không.
6. Các custom thread switch có giữ context propagation đúng không.

Không nên tự truyền username qua GraphQL variables để thay thế Authentication. Client không được tự khai báo danh tính của mình trong query; danh tính phải đến từ cơ chế authentication đáng tin cậy.

## 17. Không để lộ thông tin nội bộ qua GraphQL errors

Khi authorization thất bại, GraphQL response thường có một error gắn với field bị từ chối. Error này phục vụ client và logging, nhưng không nên tiết lộ thông tin nội bộ.

Tránh trả các thông tin như:

- Stack trace.
- Tên bảng hoặc câu SQL.
- Đường dẫn file nội bộ.
- Quy tắc phân quyền chi tiết có thể giúp dò quyền.
- Nội dung private field mà user không được phép đọc.

Có thể chuẩn hóa lỗi bằng `DataFetcherExceptionResolver` hoặc `@GraphQlExceptionHandler`, tùy phạm vi exception handling. Client chỉ cần một message an toàn và error code ổn định nếu ứng dụng định nghĩa.

Trong test, không nên phụ thuộc quá chặt vào message mặc định của `AccessDeniedException`. Thay vào đó, kiểm tra:

- Có error ở đúng field path.
- Field nhạy cảm là null hoặc không có trong data theo schema.
- Field công khai vẫn trả dữ liệu nếu được phép.
- Không có thông tin nhạy cảm trong error message hoặc extensions.

## 18. Kiểm thử danh sách quyền cần có

Một bộ test authorization nên có ma trận quyền thay vì chỉ kiểm tra một trường hợp admin thành công.

Ví dụ:

| User | Authority | Query field công khai | Field privateNotes | Mutation delete |
|---|---|---|---|---|
| Anonymous | Không có | Bị chặn nếu endpoint yêu cầu đăng nhập | Bị chặn | Bị chặn |
| Viewer | book:summary:read | Cho phép | Từ chối | Từ chối |
| Owner | book:private:read | Cho phép | Cho phép | Từ chối |
| Admin | book:private:read, book:delete | Cho phép | Cho phép | Cho phép |

Bảng trên là chính sách minh họa. Quyền thực tế cần được xác định theo nghiệp vụ và role/authority của ứng dụng.

Ngoài quyền theo role, cần có test cho quyền sở hữu:

- User A đọc document của chính mình.
- User A không đọc được document của User B.
- Tenant A không truy cập dữ liệu Tenant B.
- Không thể đổi ID trong GraphQL arguments để vượt qua quyền sở hữu.

## 19. Các lỗi thường gặp khi test authorization

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@PreAuthorize` không có tác dụng | Chưa bật `@EnableMethodSecurity` | Bổ sung cấu hình method security |
| Test luôn được phép truy cập | Đang gọi Mockito mock thay cho bean proxy | Inject service thật |
| `@WithMockUser` không hoạt động qua live HTTP | SecurityContext chỉ nằm trên test thread | Gửi Basic/Bearer credential trong HTTP header |
| Authority không khớp | Nhầm `roles` với `authorities` | Kiểm tra tiền tố `ROLE_` |
| `@GraphQlTest` thiếu security config | Test slice không scan configuration thông thường | Dùng `@Import` hoặc full integration test |
| GraphQL response có data null nhưng test không báo lỗi | Field nullable và error chưa được assertion | Kiểm tra errors và field path |
| Field private vẫn xuất hiện | Resolver không gọi service có security hoặc rule nằm sai tầng | Đặt authorization ở service method được gọi thực tế |
| Test HTTP nhận 401 thay vì GraphQL errors | Endpoint bị chặn trước execution | Kiểm tra credential hoặc test HTTP status riêng |
| Test Mutation bị thay đổi dữ liệu dù bị từ chối | Authorization chạy sau side effect hoặc test gọi method khác | Dùng `@PreAuthorize` và verify repository không được gọi |
| Error message làm lộ chi tiết | Exception được trả nguyên văn | Chuẩn hóa GraphQL error response |

## 20. Checklist kiểm thử authorization

Trước khi hoàn thành test security cho GraphQL API:

- [ ] Request-level security bảo vệ đúng endpoint.
- [ ] Method security đã bật bằng `@EnableMethodSecurity`.
- [ ] Service method quan trọng có `@PreAuthorize` hoặc rule tương ứng.
- [ ] Có test user với authority hợp lệ.
- [ ] Có test user đã đăng nhập nhưng thiếu authority.
- [ ] Có test anonymous nếu endpoint hoặc field cho phép anonymous.
- [ ] Có test quyền sở hữu object hoặc tenant khi cần.
- [ ] Test method security dùng Spring-managed bean thật.
- [ ] HTTP integration test gửi credential qua request.
- [ ] Test phân biệt HTTP 401/403 với GraphQL field errors.
- [ ] Field bị từ chối có error path chính xác.
- [ ] Partial data vẫn đúng theo nullability của schema.
- [ ] Field nhạy cảm không xuất hiện trong response.
- [ ] Mutation bị từ chối không tạo side effect.
- [ ] Error message và extensions không làm lộ dữ liệu nội bộ.
- [ ] Context propagation hoạt động với execution model của ứng dụng.

## Kết luận

Kiểm thử authorization trong Spring for GraphQL cần xác nhận quyền ở cả HTTP endpoint và từng phần dữ liệu GraphQL. Request-level security kiểm soát ai được gọi endpoint; method-level security với `@PreAuthorize` kiểm soát ai được gọi service method trong quá trình resolve field hoặc thực hiện mutation.

Dùng `@WithMockUser` để kiểm tra service method với SecurityContext của test thread. Khi kiểm thử HTTP integration bằng `HttpGraphQlTester`, hãy gửi credential qua header vì request được xử lý trên server thread riêng. Dùng `WebTestClient` để kiểm tra HTTP 401/403 và dùng GraphQlTester để kiểm tra field errors, partial data và việc dữ liệu nhạy cảm không bị trả về.

Một bộ test tốt cần chứng minh cả người được phép truy cập thành công lẫn người không có quyền bị từ chối trước khi dữ liệu hoặc side effect bị lộ.

## Tài liệu tham khảo

- [Spring for GraphQL — Security](https://docs.spring.io/spring-graphql/reference/security.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Request Execution and Context Propagation](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
