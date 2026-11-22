# Execute mutation trong kiểm thử Spring for GraphQL

Mutation là operation dùng để thay đổi dữ liệu trong GraphQL, ví dụ tạo đơn hàng, cập nhật hồ sơ hoặc hủy một giao dịch. Khi kiểm thử mutation, cần xác minh cả hai phần: GraphQL nhận đúng document và variables, đồng thời resolver gọi đúng nghiệp vụ và trả về response theo schema. Spring for GraphQL cung cấp `GraphQlTester` để thực hiện mutation và kiểm tra kết quả mà không cần tự tạo HTTP request trong từng test.

`GraphQlTester` dùng cùng một workflow cho nhiều cách kiểm thử: trực tiếp với GraphQL execution service, qua `WebGraphQlHandler`, hoặc qua HTTP/WebSocket/RSocket client. Với controller slice test, `@GraphQlTest` tự cấu hình `GraphQlTester`; với kiểm thử HTTP end-to-end, có thể dùng `HttpGraphQlTester`.

## 1. Mutation trong GraphQL hoạt động như thế nào?

GraphQL có ba loại operation chính:

| Operation | Mục đích | Response |
|---|---|---|
| Query | Đọc dữ liệu | Một GraphQL response. |
| Mutation | Thay đổi dữ liệu | Một GraphQL response sau khi xử lý thao tác. |
| Subscription | Nhận event theo thời gian | Một luồng nhiều response. |

Mutation thường nhận input object và trả về một payload mô tả kết quả. Ví dụ:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}

type Mutation {
    createBook(input: CreateBookInput!): CreateBookPayload!
}

type CreateBookPayload {
    book: Book
    userErrors: [UserError!]!
}

type Book {
    id: ID!
    title: String!
}

type UserError {
    code: String!
    message: String!
    field: [String!]
}
```

Client có thể chọn những field cần thiết trong payload:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            code
            message
            field
        }
    }
}
```

Mutation vẫn là một GraphQL request-response operation. Trong test, gọi `execute()` để thực thi mutation và nhận `GraphQlTester.Response`.

## 2. Dependency kiểm thử

Thêm module `spring-graphql-test` vào test scope:

```groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
```

Nếu dự án dùng Spring Boot, dependency quản lý version theo Spring Boot dependency management. Với test controller slice, cần có starter test tương ứng của dự án, ví dụ `spring-boot-starter-test`.

`spring-graphql-test` cung cấp `GraphQlTester` và các biến thể như `ExecutionGraphQlServiceTester`, `WebGraphQlTester`, `HttpGraphQlTester`, `WebSocketGraphQlTester` và `RSocketGraphQlTester`.

## 3. Chuẩn bị controller và service cho mutation

Giả sử ứng dụng có các Java record sau:

```java
public record CreateBookInput(String title, String authorId) {}

public record Book(String id, String title) {}

public record UserError(
    String code,
    String message,
    List<String> field
) {}

public record CreateBookPayload(
    Book book,
    List<UserError> userErrors
) {}
```

Service chịu trách nhiệm xử lý nghiệp vụ:

```java
public interface BookService {
    CreateBookPayload create(CreateBookInput input);
}
```

Controller ánh xạ mutation field:

```java
@Controller
class BookMutationController {

    private final BookService bookService;

    BookMutationController(BookService bookService) {
        this.bookService = bookService;
    }

    @MutationMapping
    CreateBookPayload createBook(@Argument("input") CreateBookInput input) {
        return bookService.create(input);
    }
}
```

`@MutationMapping` mặc định dùng tên method `createBook` làm tên field mutation. `@Argument("input")` bind input object trong GraphQL document vào `CreateBookInput`.

## 4. Dùng `@GraphQlTest` để kiểm thử mutation

`@GraphQlTest` tạo một test slice tập trung vào Spring for GraphQL. Nó cấu hình schema, controller và `GraphQlTester` nhưng không khởi động HTTP server. Những collaborator như service thường được thay bằng mock.

Trong Spring Boot 3.x, annotation thường có package `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest`; ở Spring Boot 4.x, package thuộc `org.springframework.boot.graphql.test.autoconfigure`. Hãy dùng package tương ứng với major version của dự án.

Ví dụ test:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(BookMutationController.class)
class BookMutationTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    BookService bookService;

    @Test
    void createsBook() {
        CreateBookInput input = new CreateBookInput(
            "Spring GraphQL",
            "author-42"
        );

        given(bookService.create(any(CreateBookInput.class)))
            .willReturn(new CreateBookPayload(
                new Book("book-101", "Spring GraphQL"),
                List.of()
            ));

        graphQlTester.document("""
                mutation CreateBook($input: CreateBookInput!) {
                    createBook(input: $input) {
                        book {
                            id
                            title
                        }
                        userErrors {
                            code
                            message
                        }
                    }
                }
                """)
            .variable("input", Map.of(
                "title", "Spring GraphQL",
                "authorId", "author-42"
            ))
            .execute()
            .path("createBook.book.id")
            .entity(String.class)
            .isEqualTo("book-101");

        then(bookService).should().create(input);
    }
}
```

Ví dụ dùng `@MockitoBean` của Spring Framework 6.2 trở lên. Với dự án Spring Boot cũ hơn, có thể dùng `@MockBean` theo phiên bản đang sử dụng. Các static import thường cần:

```java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.verifyNoInteractions;
```

`GraphQlTester` được auto-configure bởi `@GraphQlTest`. Test gửi mutation qua GraphQL execution, đọc `createBook.book.id` trong phần `data`, rồi xác minh service được gọi với input mong đợi.

## 5. Truyền input bằng GraphQL variables

Nên truyền dữ liệu mutation qua variables thay vì nối chuỗi input vào GraphQL document. Cách này giúp document dễ đọc, tránh lỗi escaping và mô phỏng cách client thực tế gửi operation.

Các ví dụ ở những phần tiếp theo dùng document và variables tái sử dụng sau:

```java
private static final String createBookMutation = """
    mutation CreateBook($input: CreateBookInput!) {
        createBook(input: $input) {
            book { id title }
            userErrors { code message field }
        }
    }
    """;

private static final Map<String, Object> inputVariables = Map.of(
    "title", "Spring GraphQL",
    "authorId", "author-42"
);
```

Ví dụ:

```java
graphQlTester.document("""
        mutation CreateBook($input: CreateBookInput!) {
            createBook(input: $input) {
                book { id title }
            }
        }
        """)
    .variable("input", Map.of(
        "title", "GraphQL for Java",
        "authorId", "author-7"
    ))
    .execute();
```

`variable(name, value)` gắn một variable vào request. Nếu cần nhiều variables, có thể dùng `.variables(Map<String, Object>)`:

```java
Map<String, Object> variables = Map.of(
    "input", Map.of(
        "title", "GraphQL for Java",
        "authorId", "author-7"
    )
);

graphQlTester.document(mutationDocument)
    .variables(variables)
    .execute();
```

Tên variable phải khớp với khai báo `$input` trong document. Cấu trúc map phải khớp với input type trong SDL; ví dụ `authorId` là `ID!` nên có thể gửi dưới dạng chuỗi ID.

## 6. Lưu mutation document trong file `.graphql`

Khi mutation dài hoặc được dùng ở nhiều test, có thể lưu document trong `src/test/resources/graphql-test/`:

```text
src
└── test
    └── resources
        └── graphql-test
            └── createBook.graphql
```

Nội dung `createBook.graphql`:

```graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        book {
            id
            title
        }
        userErrors {
            code
            message
            field
        }
    }
}
```

Test tham chiếu bằng `documentName`:

```java
graphQlTester.documentName("createBook")
    .variable("input", Map.of(
        "title", "Spring GraphQL",
        "authorId", "author-42"
    ))
    .execute()
    .path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");
```

`documentName("createBook")` tìm file `createBook.graphql` trong document source mặc định `graphql-test/` trên classpath. Có thể cấu hình `DocumentSource` nếu dự án lưu GraphQL documents ở vị trí khác.

## 7. Kiểm tra nhiều field trong mutation response

`GraphQlTester.Response.path(...)` dùng JsonPath tương đối với phần `data` của GraphQL response. Có thể kiểm tra nhiều field trong cùng response:

```java
GraphQlTester.Response response = graphQlTester
    .document(createBookMutation)
    .variable("input", inputVariables)
    .execute();

response.path("createBook.book.id")
    .entity(String.class)
    .isEqualTo("book-101");

response.path("createBook.book.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL");

response.path("createBook.userErrors")
    .entityList(UserError.class)
    .hasSize(0);
```

Nếu response path có alias, hãy dùng alias trong path. Ví dụ `saved: createBook(...)` thì path bắt đầu bằng `saved`, không phải `createBook`.

Với field scalar hoặc object, dùng `entity(Class)`; với list, dùng `entityList(Class)` rồi kiểm tra kích thước hoặc nội dung. Có thể dùng `.path("...").value()` khi cần lấy giá trị thô để assertion theo cách riêng.

## 8. Kiểm tra business errors trong payload

Business validation thường là kết quả dự kiến của mutation. Ví dụ title trùng hoặc trạng thái hiện tại không cho phép thao tác. API có thể trả `userErrors` trong payload thay vì ném exception.

Test trường hợp title đã tồn tại:

```java
@Test
void returnsUserErrorWhenTitleAlreadyExists() {
    given(bookService.create(any(CreateBookInput.class)))
        .willReturn(new CreateBookPayload(
            null,
            List.of(new UserError(
                "DUPLICATE_TITLE",
                "A book with this title already exists",
                List.of("input", "title")
            ))
        ));

    GraphQlTester.Response response = graphQlTester.document(createBookMutation)
        .variable("input", Map.of(
            "title", "Existing title",
            "authorId", "author-42"
        ))
        .execute();

    // User error nằm trong data payload, không phải top-level GraphQL error.
    response.path("createBook.book").valueIsNull();
    response.path("createBook.userErrors[0].code")
        .entity(String.class)
        .isEqualTo("DUPLICATE_TITLE");
}
```

Không dùng `.errors().verify()` cho business error nằm trong payload vì đây không phải lỗi ở top-level `errors`. Client nên đọc mã `userErrors.code` theo hợp đồng schema.

## 9. Kiểm tra GraphQL errors từ mutation

Execution error xảy ra khi resolver/service ném exception và exception được ánh xạ thành GraphQL error. Khi đó response có thể chứa `data` partial hoặc `null`, cùng danh sách `errors`.

Ví dụ kiểm tra mã lỗi:

```java
GraphQlTester.Response response = graphQlTester
    .document(createBookMutation)
    .variable("input", inputVariables)
    .execute();

response.errors()
    .expect(error -> error.getMessage().contains("Book service unavailable"))
    .verify();
```

`errors().expect(...)` yêu cầu có ít nhất một lỗi thỏa predicate; `verify()` xác nhận lỗi mong đợi. Sau đó có thể tiếp tục kiểm tra `data` nếu GraphQL trả partial data.

Nếu muốn kiểm tra toàn bộ danh sách errors, dùng `satisfy`:

```java
response.errors().satisfy(errors ->
    assertThat(errors).anyMatch(error ->
        "BOOK_SERVICE_UNAVAILABLE".equals(
            error.getExtensions().get("code")
        )
    )
);
```

Khi dùng `satisfy`, các errors được xem là đã xử lý để có thể tiếp tục kiểm tra data. Không nên lọc bỏ lỗi một cách rộng rãi chỉ để test không thất bại; hãy assert chính xác loại lỗi dự kiến.

## 10. Kiểm tra input coercion và validation

GraphQL kiểm tra kiểu input trước khi gọi resolver. Nếu mutation khai báo:

```graphql
input CreateBookInput {
    title: String!
    authorId: ID!
}
```

thì variables thiếu `title`, truyền `null` cho `authorId` hoặc truyền object sai kiểu sẽ bị từ chối trước khi `BookMutationController.createBook` chạy.

Ví dụ kiểm tra thiếu field Non-null:

```java
@Test
void rejectsInputWithoutRequiredTitle() {
    GraphQlTester.Response response = graphQlTester
        .document(createBookMutation)
        .variable("input", Map.of("authorId", "author-42"))
        .execute();

    response.errors().satisfy(errors ->
        assertThat(errors).isNotEmpty()
    );

    verifyNoInteractions(bookService);
}
```

Lỗi coercion/validation xảy ra trước execution nên service không được gọi. Nội dung message chính xác có thể thay đổi theo GraphQL Java/version; nếu cần kiểm tra chi tiết, ưu tiên assertion về vị trí/loại lỗi ổn định thay vì phụ thuộc toàn bộ câu chữ.

GraphQL input coercion khác với validation nghiệp vụ. Ví dụ chuỗi title rỗng vẫn có kiểu `String!` hợp lệ; nếu domain không cho phép title rỗng, service hoặc Bean Validation cần kiểm tra quy tắc đó.

## 11. Kiểm tra mutation không có top-level errors bằng `executeAndVerify`

Nếu test chỉ cần xác nhận mutation thực thi thành công và không cần kiểm tra field trong response, có thể dùng `executeAndVerify()`:

Giả sử schema có mutation trả về scalar:

```graphql
type Mutation {
    archiveBook(id: ID!): Boolean!
}
```

```java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-101")
        }
        """)
    .executeAndVerify();
```

Phương thức này thực thi request và xác minh response không chứa GraphQL errors. Nó phù hợp với mutation mà test chỉ cần xác nhận không có lỗi, ví dụ thao tác trả scalar hoặc test chỉ quan tâm side effect đã được mock/kiểm tra riêng.

Nếu cần xác minh giá trị trả về, dùng `execute()` rồi kiểm tra path:

```java
graphQlTester.document("""
        mutation {
            archiveBook(id: "book-101")
        }
        """)
    .execute()
    .path("archiveBook")
    .entity(Boolean.class)
    .isEqualTo(true);
```

`executeAndVerify()` không thay thế assertion cho dữ liệu trả về. Một mutation có thể không có GraphQL errors nhưng vẫn trả `false`, `null` hoặc business error trong payload.

## 12. Xác minh service được gọi đúng

Kiểm tra response cho biết client nhận gì; kiểm tra mock interaction cho biết resolver đã chuyển input tới service như mong đợi.

Ví dụ xác minh input:

```java
then(bookService).should().create(
    new CreateBookInput("Spring GraphQL", "author-42")
);
```

Có thể dùng `ArgumentCaptor` nếu cần kiểm tra một phần input hoặc giá trị đã được chuẩn hóa:

```java
ArgumentCaptor<CreateBookInput> captor =
    ArgumentCaptor.forClass(CreateBookInput.class);

then(bookService).should().create(captor.capture());

assertThat(captor.getValue().title()).isEqualTo("Spring GraphQL");
assertThat(captor.getValue().authorId()).isEqualTo("author-42");
```

Không nên chỉ verify rằng service được gọi mà bỏ qua response. Một resolver có thể gọi service đúng nhưng ánh xạ sai field hoặc trả sai payload; cần kiểm tra cả response contract.

## 13. Kiểm thử mutation có side effect với database

`@GraphQlTest` thường mock service nên không chứng minh dữ liệu thực sự được ghi vào database. Khi cần xác minh persistence, transaction hoặc constraint, viết integration test với application context và database test.

Ví dụ cấu trúc kiểm thử:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureHttpGraphQlTester
class BookMutationIntegrationTests {

    @Autowired
    HttpGraphQlTester graphQlTester;

    @Autowired
    BookRepository bookRepository;

    @Test
    void createsBookInDatabase() {
        graphQlTester.document(createBookMutation)
            .variable("input", Map.of(
                "title", "Spring GraphQL",
                "authorId", "author-42"
            ))
            .execute()
            .path("createBook.book.title")
            .entity(String.class)
            .isEqualTo("Spring GraphQL");

        assertThat(bookRepository.findByTitle("Spring GraphQL"))
            .isPresent();
    }
}
```

Ví dụ giả định ứng dụng có `GraphQlTester` và `BookRepository` bean, database test đã được cấu hình và mutation ghi dữ liệu thật. Với ứng dụng yêu cầu kiểm thử qua HTTP, dùng `@SpringBootTest` kết hợp `@AutoConfigureHttpGraphQlTester` hoặc tạo `HttpGraphQlTester` từ `WebTestClient`.

Tên package của `@AutoConfigureHttpGraphQlTester` và các annotation test GraphQL phụ thuộc dòng Spring Boot; dùng package tương ứng với phiên bản dự án.

Nếu test cần kiểm tra HTTP status, headers, CORS hoặc security filter chain, `GraphQlTester` trừu tượng hóa transport có thể chưa đủ; hãy dùng `WebTestClient`/MockMvc để assertion phần HTTP và `HttpGraphQlTester` để assertion GraphQL response.

## 14. Kiểm tra quyền khi thực thi mutation

Mutation thường thay đổi dữ liệu nên cần kiểm thử cả trường hợp được phép và bị từ chối. Ví dụ người dùng không có quyền `book:write` không được tạo sách.

Với test slice có Spring Security method security, cần import cấu hình security cần thiết hoặc dùng integration test để bảo đảm đúng filter/method security setup. Các assertion nên kiểm tra:

- Người dùng có authority hợp lệ tạo được dữ liệu.
- Người dùng thiếu authority không gọi service ghi dữ liệu.
- Người dùng không thể sửa resource thuộc tenant hoặc owner khác.
- Response error không làm lộ thông tin nhạy cảm.

Không giả định `@GraphQlTest` tự tải toàn bộ `SecurityFilterChain`, service hoặc cấu hình ứng dụng. Test slice chỉ đưa vào các thành phần GraphQL được hỗ trợ và các bean được import rõ ràng.

## 15. Phân biệt `@GraphQlTest`, `WebGraphQlTester` và `HttpGraphQlTester`

| Công cụ | Phạm vi | Phù hợp khi |
|---|---|---|
| `@GraphQlTest` + `GraphQlTester` | Controller slice, không có HTTP server | Kiểm tra SDL, argument binding, resolver, response và exception mapping. |
| `WebGraphQlTester` | Qua `WebGraphQlHandler` và interceptor chain | Kiểm tra web request metadata, GraphQL context và interceptor. |
| `HttpGraphQlTester` | Qua HTTP với `WebTestClient` | Kiểm tra endpoint HTTP, headers và GraphQL response. |
| `@SpringBootTest` | Toàn bộ application context | Kiểm tra mutation với service, repository, transaction và cấu hình thật. |

Nên bắt đầu bằng test slice để kiểm tra resolver nhanh. Dùng integration test cho những hành vi không thể xác minh bằng mock, như database constraint, transaction rollback, HTTP security và serialization thực tế.

## 16. Lưu ý khi kiểm thử mutation

1. Dùng GraphQL variables thay vì nối chuỗi input trực tiếp vào document.
2. Chọn đúng field trong payload để kiểm tra response contract.
3. Kiểm tra cả service invocation và dữ liệu trả về.
4. Phân biệt GraphQL input coercion, business validation và execution errors.
5. Với business error trong payload, assert `userErrors`; không tìm chúng trong top-level `errors`.
6. Với execution error, dùng `response.errors()` và kiểm tra mã lỗi/path cần thiết.
7. Không dùng mock test để kết luận database đã ghi dữ liệu đúng.
8. Không retry mutation một cách tự động trong test hoặc client nếu chưa có idempotency strategy; retry sau timeout có thể tạo side effect lặp.
9. Dọn dữ liệu test hoặc dùng database cô lập để test không phụ thuộc thứ tự chạy.
10. Dùng document name cho mutation dài và tái sử dụng để giảm trùng lặp.

## 17. Lỗi thường gặp

**Dùng `executeSubscription()` cho mutation.** Mutation là request-response; dùng `execute()` hoặc `executeAndVerify()`.

**Chỉ gọi `executeAndVerify()` rồi cho rằng mutation trả đúng dữ liệu.** Phương thức này xác minh không có GraphQL errors; muốn kiểm tra payload phải dùng `execute()` và `path(...)`.

**Không khai báo variables đúng kiểu.** Variable name và input structure phải khớp SDL. Lỗi coercion xảy ra trước khi resolver chạy.

**Gửi input bằng cách nối chuỗi.** Dễ sai escaping và tạo document khó đọc. Dùng `.variable(...)` hoặc `.variables(...)`.

**Dùng `@GraphQlTest` nhưng quên mock service.** Test slice không tự load `@Service` và `@Repository`; dùng `@MockitoBean` hoặc `@Import` bean cần thiết.

**Nhầm business error với GraphQL error.** `userErrors` là dữ liệu trong payload; top-level `errors` dành cho lỗi GraphQL/execution theo hợp đồng API.

**Chỉ assert service được gọi.** Resolver vẫn có thể trả sai field hoặc sai payload. Hãy kiểm tra cả response.

**Dùng mock để kết luận transaction/persistence hoạt động.** Cần integration test với database thực hoặc Testcontainers cho các hành vi này.

**Bỏ qua side effect khi chạy lại test.** Mutation có thể tạo dữ liệu trùng. Dùng dữ liệu test duy nhất, cleanup hoặc transaction strategy phù hợp.

## Kết luận

Để execute mutation trong kiểm thử Spring for GraphQL, xây dựng request bằng `GraphQlTester.document(...)`, truyền input qua `.variable(...)` hoặc `.variables(...)`, rồi gọi `.execute()` để kiểm tra response. Dùng `@GraphQlTest` và mock service để kiểm thử resolver nhanh; assert các field trong payload và verify input được chuyển đúng. Phân biệt business errors trong payload với top-level GraphQL errors, dùng `executeAndVerify()` khi chỉ cần xác nhận không có lỗi, và bổ sung integration test khi cần chứng minh mutation thực sự ghi database, tuân thủ transaction hoặc security.

## Tài liệu tham khảo

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Testing Spring GraphQL Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Specification — Mutation](https://spec.graphql.org/October2021/#sec-Mutation)
