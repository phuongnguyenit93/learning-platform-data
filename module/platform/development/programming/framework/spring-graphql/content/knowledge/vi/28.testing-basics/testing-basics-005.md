# GraphQlTester document

Trong Spring for GraphQL, kiểm thử một GraphQL operation không chỉ là gọi controller rồi kiểm tra object Java. Cần xác nhận GraphQL document được parse và validate, argument được bind đúng, resolver chạy đúng, response có shape phù hợp, errors được trả theo contract và các field được phân giải theo schema.

GraphQlTester là API kiểm thử của Spring for GraphQL cho các thao tác query, mutation và subscription. Điểm bắt đầu của một test thường là tạo GraphQL document, truyền variables nếu cần, gọi execute(), sau đó kiểm tra response bằng path, entity và errors. Bài này tập trung vào cách dùng document() và documentName() để viết test dễ đọc, dễ bảo trì.

## 1. GraphQlTester giải quyết vấn đề gì?

Một resolver unit test có thể chứng minh một method trả đúng giá trị khi được gọi trực tiếp, nhưng không chứng minh GraphQL runtime có thể gọi method đó đúng cách. Một GraphQL operation còn đi qua nhiều thành phần:

1. Parse GraphQL document.
2. Validate field, argument, variable và kiểu dữ liệu theo schema.
3. Bind argument vào tham số controller.
4. Chọn DataFetcher cho từng field.
5. Gọi resolver và các service liên quan.
6. Phân giải field lồng nhau, DataLoader hoặc batch mapping.
7. Áp dụng nullability và error handling.
8. Serialize response theo GraphQL response shape.

GraphQlTester giúp kiểm thử luồng GraphQL ở mức operation. Test có thể gửi document thật và kiểm tra response như client sẽ nhìn thấy. Nhờ đó, test phát hiện được lỗi schema, mapping, argument binding, error path hoặc null propagation mà unit test thuần Java có thể bỏ sót.

## 2. Các loại GraphQlTester

Spring for GraphQL cung cấp những tester phù hợp với các ranh giới khác nhau:

| Tester | Ranh giới được kiểm thử | Khi nên dùng |
| --- | --- | --- |
| ExecutionGraphQlServiceTester | GraphQL service trong ứng dụng, không đi qua HTTP transport | Kiểm tra schema, resolver, argument binding và GraphQL execution |
| HttpGraphQlTester | HTTP endpoint qua WebTestClient | Kiểm tra endpoint, HTTP headers, status, security filter và transport |
| WebSocketGraphQlTester | WebSocket GraphQL endpoint | Kiểm tra subscription, connection lifecycle và event stream |
| RSocketGraphQlTester | RSocket route | Kiểm tra GraphQL qua RSocket nếu ứng dụng bật transport này |

Các tester dùng chung API GraphQlTester để xây dựng document và kiểm tra response. Khác biệt nằm ở cách gửi request đến server.

Nếu chỉ cần kiểm tra resolver/schema, tester ở mức ExecutionGraphQlService thường nhanh và ít phụ thuộc hạ tầng. Nếu muốn xác nhận Spring Security filter, CORS, HTTP status hoặc header, cần test qua HTTP. Một test in-process không thể chứng minh những filter hoặc proxy bên ngoài GraphQL service đã chạy đúng.

## 3. Tạo tester trong test

Với GraphQL service trong ứng dụng, có thể tạo tester trực tiếp từ service:

~~~java
@SpringBootTest
class BookGraphQlTests {

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

Ví dụ này tập trung vào execution và không gửi HTTP request. Cấu hình Spring context vẫn được khởi tạo, vì vậy controller, schema mapping, service và các bean liên quan vẫn tham gia GraphQL execution.

Để kiểm tra HTTP endpoint, tạo tester từ WebTestClient:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHttpGraphQlTests {

    @Autowired
    WebTestClient webTestClient;

    HttpGraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester = HttpGraphQlTester.builder(webTestClient).build();
    }
}
~~~

Với test slice hoặc cấu hình tự tạo, có thể inject hoặc khởi tạo tester theo test context tương ứng. Tránh tự tạo GraphQL schema hoặc controller mới trong mỗi test nếu mục tiêu là xác minh cấu hình ứng dụng thật.

## 4. document() với GraphQL string trực tiếp

document(String) nhận GraphQL document dưới dạng chuỗi. Cách này tiện cho operation ngắn, test tập trung vào một hành vi hoặc test muốn đặt document ngay cạnh assertion:

~~~java
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
    .entityList(BookView.class)
    .hasSize(2);
~~~

Text block của Java giúp viết GraphQL nhiều dòng dễ đọc và không cần nối chuỗi. Document trong test nên chỉ chọn các field cần thiết cho hành vi đang kiểm tra; không cần sao chép một operation rất lớn nếu một selection set nhỏ đã thể hiện đúng mục tiêu.

Document inline phù hợp khi:

- Query chỉ có vài field.
- Test đang kiểm tra một lỗi cụ thể.
- Document không được tái sử dụng ở nhiều test.
- Muốn nhìn thấy operation ngay trong test mà không phải mở thêm file.

Khi document dài hoặc được dùng ở nhiều test, nên cân nhắc documentName().

## 5. documentName() với file GraphQL riêng

documentName(String) tải GraphQL document từ resource trên classpath. Theo cấu hình mặc định của GraphQlTester, document test thường được đặt trong thư mục graphql-test/ với phần mở rộng .graphql.

Ví dụ cấu trúc:

~~~text
src
  test
    resources
      graphql-test
        books.graphql
        book-by-id.graphql
        update-book.graphql
~~~

Nội dung file books.graphql:

~~~graphql
query Books {
    books {
        id
        title
    }
}
~~~

Test:

~~~java
graphQlTester.documentName("books")
    .execute()
    .path("books")
    .entityList(BookView.class)
    .hasSize(2);
~~~

Tách document ra file riêng có một số lợi ích:

- Operation gần với document mà frontend hoặc client thực sự sử dụng.
- Có thể tái sử dụng một document trong nhiều test với variables khác nhau.
- File GraphQL có syntax highlighting và dễ đọc hơn chuỗi Java dài.
- Khi operation thay đổi, diff chỉ tập trung vào document.
- Có thể tổ chức test query, mutation và subscription theo nhóm.

Tên resource được phân giải theo cấu hình document source của GraphQlTester. Nếu ứng dụng tùy chỉnh ResourceLoader hoặc document source, cần đặt file theo cấu hình đó. Khi không tìm thấy document, kiểm tra tên resource, classpath và phần mở rộng trước khi điều tra resolver.

## 6. Chọn documentName hay document?

| Tiêu chí | document() | documentName() |
| --- | --- | --- |
| Nơi lưu document | Trong code test | File resource trên classpath |
| Độ dài phù hợp | Ngắn đến vừa | Vừa đến dài |
| Tái sử dụng | Dễ bị lặp nếu nhiều test | Có thể dùng lại cùng document |
| Syntax highlighting | Phụ thuộc editor Java | Editor GraphQL thường hỗ trợ tốt |
| Thay đổi operation | Sửa chuỗi trong test | Sửa file .graphql |
| Variables | Truyền qua variable() như nhau | Truyền qua variable() như nhau |

Không có quy tắc bắt buộc mọi test phải dùng documentName(). Dùng inline cho operation ngắn và documentName cho operation dài hoặc được dùng lại thường giúp bộ test cân bằng giữa tính trực quan và khả năng bảo trì.

## 7. Truyền variables và operationName

Nên dùng GraphQL variables thay vì ghép giá trị trực tiếp vào document. Điều này giúp test gần với cách client thực tế gửi request, đồng thời tách document khỏi dữ liệu:

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

operationName hữu ích khi một document chứa nhiều operation. GraphQL server cần biết operation nào sẽ được thực thi. Nếu document chỉ có một operation, tên vẫn giúp test mô tả rõ operation đang kiểm tra.

Với nhiều variables:

~~~java
graphQlTester.documentName("search-books")
    .operationName("SearchBooks")
    .variable("keyword", "spring")
    .variable("page", 0)
    .variable("size", 10)
    .execute();
~~~

Không ghép user input trực tiếp vào GraphQL string. Dùng variable() giúp GraphQL xử lý coercion theo schema và giảm nguy cơ tạo document sai cú pháp do ký tự đặc biệt.

## 8. Kiểm tra một field bằng path()

Sau execute(), GraphQlTester trả response. path(String) chọn một vị trí trong data để assertion:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "book-01") {
                id
                title
            }
        }
        """)
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Path dùng response key của GraphQL, không phải tên Java method hoặc tên repository. Nếu query dùng alias, path phải dùng alias.

Ví dụ:

~~~graphql
query {
    featured: bookById(id: "book-01") {
        id
        title
    }
}
~~~

Assertion phải đọc featured.title:

~~~java
response.path("featured.title")
    .entity(String.class)
    .isEqualTo("Spring for GraphQL");
~~~

Path có thể trỏ đến field lồng nhau. Khi test lỗi hoặc list, có thể dùng biểu thức path phù hợp với cấu trúc JSON response và JsonPath support của GraphQlTester.

## 9. Chuyển field thành entity

entity(Class) chuyển giá trị tại path thành kiểu Java:

~~~java
graphQlTester.documentName("book-by-id")
    .variable("id", "book-01")
    .execute()
    .path("bookById")
    .entity(BookView.class)
    .satisfies(book -> {
        assertThat(book.id()).isEqualTo("book-01");
        assertThat(book.title()).isEqualTo("Spring for GraphQL");
    });
~~~

DTO test chỉ cần chứa những field được query và cần kiểm tra:

~~~java
public record BookView(String id, String title) {
}
~~~

Không cần deserialize toàn bộ domain entity nếu response chỉ chứa một phần dữ liệu. DTO riêng giúp test phản ánh GraphQL response contract và tránh vô tình phụ thuộc field nội bộ.

## 10. Kiểm tra danh sách

Với list, dùng entityList(Class) để chuyển các phần tử thành kiểu Java:

~~~java
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
    .entityList(BookView.class)
    .hasSize(2);
~~~

Có thể kiểm tra thêm từng phần tử sau khi chuyển danh sách:

~~~java
List<BookView> books = graphQlTester.documentName("books")
    .execute()
    .path("books")
    .entityList(BookView.class)
    .get();

assertThat(books)
    .extracting(BookView::id)
    .containsExactlyInAnyOrder("book-01", "book-02");
~~~

Khi thứ tự list là một phần của contract, dùng assertion theo thứ tự. Nếu thứ tự không được đảm bảo, kiểm tra tập ID hoặc các thuộc tính ổn định thay vì làm test phụ thuộc thứ tự ngẫu nhiên của database.

## 11. Kiểm tra null và field không có giá trị

GraphQL có thể trả null cho field nullable. Dùng valueIsNull() khi null là kết quả mong đợi:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
                title
            }
        }
        """)
    .execute()
    .path("bookById")
    .valueIsNull();
~~~

Null có thể mang nhiều ý nghĩa:

- Resolver trả null theo nghiệp vụ.
- Field không có dữ liệu.
- Field nullable bị lỗi execution.
- Null propagation từ một nested field non-null.

Vì vậy, nếu null là kết quả của lỗi, cần kiểm tra cả errors và path thay vì chỉ assertion valueIsNull().

Ví dụ:

~~~java
var response = graphQlTester.documentName("book-by-id")
    .variable("id", "missing")
    .execute();

response.path("bookById").valueIsNull();
response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

## 12. Kiểm tra GraphQL errors

GraphQlTester không nên được dùng theo cách chỉ kiểm tra data rồi bỏ qua errors. Một test có thể nhận data một phần cùng lỗi field; nếu lỗi không được kiểm tra, test có thể xanh dù API đang vi phạm contract.

Khi operation kỳ vọng không có lỗi, gọi errors().verify():

~~~java
graphQlTester.documentName("books")
    .execute()
    .errors()
    .verify();
~~~

Khi test đang chủ đích kiểm tra lỗi, dùng expect() để xác nhận lỗi mong đợi:

~~~java
var response = graphQlTester.documentName("book-by-id")
    .variable("id", "missing")
    .execute();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

Predicate trong expect() nên kiểm tra thuộc tính ổn định như extensions.code, path hoặc error classification. Không nên phụ thuộc toàn bộ message nếu message có thể được bản địa hóa.

## 13. Kiểm tra error path và extensions

GraphQL error có path chỉ ra response field bị lỗi. Khi client dùng alias hoặc field lồng nhau, path phản ánh response key:

~~~java
response.errors()
    .expect(error ->
        error.getPath().equals(List.of("featured")))
    .verify();
~~~

Với field lồng nhau, path có thể chứa tên field và chỉ số list. Hãy so sánh đúng cấu trúc path thay vì chỉ kiểm tra message.

Extensions là nơi ứng dụng có thể công bố mã lỗi và metadata:

~~~java
response.errors()
    .expect(error ->
        "VALIDATION_FAILED".equals(error.getExtensions().get("code")))
    .verify();
~~~

Nếu error contract có violations, có thể kiểm tra số lượng và tên field qua extensions. Không nên chỉ kiểm tra rằng errors không rỗng; cần xác nhận code đúng và không lộ rejected value hoặc dữ liệu nhạy cảm.

## 14. Test partial data

GraphQL cho phép một field lỗi trong khi các field khác vẫn thành công. Test nên xác nhận cả hai điều:

~~~java
var response = graphQlTester.document("""
        query {
            bookById(id: "missing") {
                id
            }
            latestBooks {
                id
                title
            }
        }
        """)
    .execute();

response.path("latestBooks")
    .entityList(BookView.class)
    .hasSize(2);

response.path("bookById").valueIsNull();

response.errors()
    .expect(error ->
        "BOOK_NOT_FOUND".equals(error.getExtensions().get("code")))
    .verify();
~~~

Test này xác nhận API không làm mất dữ liệu của field độc lập khi một field khác lỗi. Nếu schema khai báo non-null, null propagation có thể làm parent hoặc root data trở thành null; hãy viết assertion theo schema thực tế.

## 15. Test mutation và input object

Mutation thường nhận input object. Dùng variables để kiểm tra argument binding và validation:

~~~graphql
mutation UpdateBook($input: UpdateBookInput!) {
    updateBook(input: $input) {
        id
        title
    }
}
~~~

Test:

~~~java
Map<String, Object> input = Map.of(
    "bookId", "book-01",
    "title", "New title");

graphQlTester.documentName("update-book")
    .variable("input", input)
    .execute()
    .path("updateBook.title")
    .entity(String.class)
    .isEqualTo("New title");
~~~

Nên có test riêng cho:

- Input hợp lệ và mutation trả dữ liệu mới.
- Required field bị thiếu hoặc sai kiểu.
- Bean/domain validation thất bại.
- Người dùng không có quyền cập nhật resource.
- Mutation không thực hiện side effect khi validation/authorization thất bại.
- Input không thể tự thay đổi owner, tenant hoặc role nếu các field đó không thuộc public contract.

Với mutation, kiểm tra response chưa đủ để chứng minh side effect đúng. Có thể xác minh repository, event publisher hoặc trạng thái aggregate sau khi operation chạy. Khi request bị từ chối, xác nhận dữ liệu không bị thay đổi.

## 16. Test schema validation và argument coercion

GraphQlTester gửi document thật qua GraphQL engine, vì vậy có thể kiểm tra lỗi trước khi resolver chạy:

- Field không tồn tại trong schema.
- Argument thiếu hoặc không đúng kiểu.
- Variable không tương thích scalar.
- Enum value không hợp lệ.
- Field non-null nhận null.

Các lỗi này khác exception trong DataFetcher. Test nên xác nhận chúng không kích hoạt service hoặc repository ngoài ý muốn.

Ví dụ khi truyền ID có kiểu sai, GraphQL có thể trả request/validation error trước khi gọi resolver. Đừng viết test mong DataFetcherExceptionResolver xử lý lỗi coercion vì resolver chưa được thực thi.

## 17. Test authentication và authorization

Tester ở mức GraphQL execution có thể thiết lập GraphQLContext hoặc security context theo test configuration, nhưng không nhất thiết đi qua toàn bộ HTTP security filter chain.

Nếu muốn kiểm tra Spring Security HTTP configuration, dùng HttpGraphQlTester dựa trên WebTestClient và gửi request với principal/token test phù hợp. Kiểm tra cả:

- Request không xác thực bị từ chối.
- Principal có authority được phép truy cập.
- Principal đã xác thực nhưng không có quyền bị từ chối.
- User A không đọc được resource của User B khi đổi argument ID.
- Tenant A không truy cập được dữ liệu tenant B.
- Error response không tiết lộ resource nhạy cảm.

Với method security, cần gọi bean qua Spring proxy trong test context. Một unit test gọi trực tiếp object được new bằng tay sẽ không kích hoạt AOP method security.

## 18. documentName và tổ chức test documents

Khi số lượng test tăng, nên nhóm file GraphQL theo feature hoặc use case:

~~~text
src/test/resources/graphql-test/
  books/
    books.graphql
    book-by-id.graphql
    update-book.graphql
  authors/
    author-by-id.graphql
  orders/
    order-by-id.graphql
    cancel-order.graphql
~~~

Tên truyền vào documentName phụ thuộc resource path và document source được cấu hình. Giữ tên nhất quán và tránh nhiều file cùng tên ở các thư mục khác nhau nếu cấu hình không hỗ trợ phân biệt rõ.

Không lưu token, password hoặc dữ liệu production trong file .graphql. Dùng variables trong test để truyền fixture giả lập. Document nên chứa cấu trúc operation; dữ liệu thay đổi theo test nên nằm trong variable().

## 19. Test subscription

Subscription khác query/mutation vì kết quả là stream event. Với WebSocketGraphQlTester, có thể gọi executeSubscription() rồi kiểm tra publisher bằng Reactor Test StepVerifier:

~~~java
Flux<OrderEventView> events = webSocketGraphQlTester
    .documentName("order-updated")
    .variable("orderId", "order-01")
    .executeSubscription()
    .toFlux("orderUpdated", OrderEventView.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.orderId().equals("order-01"))
    .thenCancel()
    .verify();
~~~

Subscription test cần kiểm tra event đúng, thứ tự nếu contract bảo đảm, lỗi stream, cancellation và cleanup. Nếu kiểm tra authentication, hãy cấu hình credentials ở WebSocket connection hoặc operation theo cách ứng dụng thực tế sử dụng.

Đừng để test subscription chờ vô hạn. Dùng StepVerifier với timeout phù hợp và chủ động cancel sau khi nhận số event cần thiết. Với test quyền, xác nhận principal không hợp lệ không mở được subscription hoặc không nhận event trái quyền.

## 20. Deterministic test data và isolation

GraphQL test thường thất bại không ổn định nếu phụ thuộc dữ liệu dùng chung hoặc thứ tự database không được bảo đảm.

Nên:

- Tạo dữ liệu fixture riêng cho từng test hoặc dùng transaction/test cleanup phù hợp.
- Dùng ID cố định dễ đọc trong test.
- Không phụ thuộc thứ tự list nếu schema không cam kết order.
- Mock service ở test resolver khi muốn kiểm tra mapping cụ thể.
- Dùng repository/database thật trong integration test khi cần xác nhận query, transaction hoặc persistence.
- Không để test song song ghi vào cùng một record dùng chung.
- Kiểm tra cả side effect và GraphQL response với mutation.

Test ở mức GraphQlTester không tự bảo đảm database được rollback. Transaction test phụ thuộc test runner, loại transport và thread/reactive execution. Với HTTP hoặc async execution, hãy xác nhận transaction boundary thực tế thay vì giả định test method transaction sẽ bao phủ mọi công việc.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy documentName | File không nằm trên classpath hoặc tên resource sai | Kiểm tra graphql-test path, tên và extension |
| Test xanh dù response có errors | Không gọi errors().verify() hoặc không assert lỗi mong đợi | Kiểm tra errors trong mọi test |
| Path assertion không tìm thấy field | Dùng tên schema field thay vì alias response key | Dùng đúng response path |
| Entity mapping thất bại | DTO không khớp response shape hoặc scalar mapping | Dùng DTO đúng field và kiểu dữ liệu |
| Null assertion nhưng test vẫn bỏ sót lỗi | Không kiểm tra errors và null propagation | Kiểm tra cả value, error path và schema nullability |
| Security test vẫn cho truy cập | Test gọi object trực tiếp, không qua proxy/filter | Dùng Spring context và tester đúng ranh giới |
| HTTP security không được kiểm tra | Dùng ExecutionGraphQlServiceTester | Dùng HttpGraphQlTester qua WebTestClient |
| Subscription test treo | Không cancel hoặc không có timeout | Dùng StepVerifier và publisher điều khiển được |
| Test phụ thuộc thứ tự database | Không có order contract hoặc fixture ổn định | Sort trong query hoặc assertion không phụ thuộc thứ tự |
| Mutation test chỉ kiểm tra response | Side effect có thể sai dù response đúng | Kiểm tra trạng thái persistence/event sau mutation |

## 22. Nguyên tắc thiết kế GraphQlTester document tests

Dùng document() cho operation ngắn và documentName() cho document dài hoặc tái sử dụng. Truyền input bằng variable() và đặt operationName khi document có nhiều operation hoặc cần làm rõ mục tiêu test. Dùng path() để kiểm tra đúng response key, entity()/entityList() để ánh xạ dữ liệu và errors() để xác nhận error contract.

Chọn tester theo ranh giới cần kiểm chứng: ExecutionGraphQlServiceTester cho GraphQL execution, HttpGraphQlTester cho HTTP/security filters, WebSocketGraphQlTester cho subscription và RSocketGraphQlTester khi dùng RSocket. Không dùng một test in-process để kết luận transport hoặc proxy đã hoạt động đúng.

Với mỗi test, hãy xác định rõ kỳ vọng thành công hay lỗi. Test thành công nên verify không có GraphQL errors; test lỗi nên assert code/path và kiểm tra data/null propagation tương ứng. Với mutation, xác nhận side effect; với subscription, xác nhận event và cancellation. Tổ chức fixture ổn định để test phản ánh contract của GraphQL API thay vì chi tiết ngẫu nhiên của môi trường.

GraphQlTester document giúp kiểm thử GraphQL như một client thực sự tương tác với schema. Khi document, variables, response path và errors được kiểm tra rõ ràng, test trở thành hợp đồng có thể đọc được giữa schema, resolver và consumer của API.
