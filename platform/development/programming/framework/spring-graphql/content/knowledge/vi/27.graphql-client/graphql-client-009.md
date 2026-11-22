# Client variables

Trong GraphQL, **variable** cho phép client truyền dữ liệu vào operation mà không phải ghép giá trị trực tiếp vào chuỗi query. Client khai báo tên và kiểu của variable trong phần đầu operation, sau đó dùng variable đó ở argument của field hoặc input object. Giá trị thực tế được gửi riêng trong payload của request.

Spring for GraphQL cung cấp abstraction **GraphQlClient** để gửi query, mutation và subscription qua các transport khác nhau. API request của client cho phép truyền từng variable bằng `variable(name, value)` hoặc truyền cả map bằng `variables(map)`. Bài học này tập trung vào cách khai báo, truyền và quản lý variables, cách biểu diễn input phức tạp, xử lý default/null/omitted và kiểm tra response.

## 1. Vì sao cần GraphQL variables?

Giả sử client cần tìm một quyển sách theo ID. Có thể viết giá trị trực tiếp vào document:

~~~graphql
query {
    book(id: "book-42") {
        id
        title
    }
}
~~~

Cách này làm query phụ thuộc vào một giá trị cụ thể. Khi ID thay đổi, client phải tạo một document khác. Nếu ghép chuỗi từ dữ liệu người dùng, code còn dễ mắc lỗi escaping và có nguy cơ đưa dữ liệu không đáng tin cậy vào cấu trúc GraphQL.

Dùng variable sẽ tách document khỏi dữ liệu:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

Giá trị được gửi riêng:

~~~json
{
    "query": "query BookById($id: ID!) { book(id: $id) { id title } }",
    "operationName": "BookById",
    "variables": {
        "id": "book-42"
    }
}
~~~

Cùng một document có thể chạy với nhiều ID khác nhau. Lợi ích chính:

- Document ổn định và dễ đọc.
- Dữ liệu đầu vào được serialize riêng theo JSON.
- Tránh nối chuỗi giá trị người dùng vào GraphQL syntax.
- Dễ kiểm thử với nhiều bộ dữ liệu.
- Có thể tái sử dụng operation và hỗ trợ caching dựa trên document ở các lớp phù hợp.

Variables không thay thế authentication, authorization hoặc validation. Server vẫn phải kiểm tra người dùng có quyền truy cập resource được truyền vào hay không.

## 2. Khai báo variable trong GraphQL operation

Cú pháp khai báo variable đặt trong dấu ngoặc sau operation type và operation name:

~~~graphql
query OperationName($variableName: GraphQLType) {
    field(argument: $variableName) {
        id
    }
}
~~~

Ví dụ:

~~~graphql
query SearchBooks($keyword: String!, $limit: Int) {
    searchBooks(keyword: $keyword, limit: $limit) {
        id
        title
    }
}
~~~

Trong đó:

- `$keyword` là tên variable.
- `String!` là kiểu GraphQL và dấu `!` có nghĩa non-null.
- `$limit` là variable nullable kiểu `Int`.
- `keyword: $keyword` truyền variable vào argument cùng tên của field.

Tên variable bắt đầu bằng ký tự `$`, sau đó là tên hợp lệ theo GraphQL Name. Variable chỉ có hiệu lực trong operation nơi nó được khai báo.

Một document có thể chứa nhiều operation:

~~~graphql
query FindBook($id: ID!) {
    book(id: $id) {
        id
        title
    }
}

query FindAuthor($id: ID!) {
    author(id: $id) {
        id
        name
    }
}
~~~

Khi document có nhiều operation, client cần chỉ định operation name để server biết operation nào cần thực thi. Việc khai báo variable trong một operation không làm variable đó dùng được trong operation khác.

## 3. Kiểu variable và nullability

Variable phải tương thích với kiểu argument được khai báo trong schema.

Các scalar GraphQL phổ biến:

| Kiểu | Dữ liệu thường truyền trong JSON | Lưu ý |
| --- | --- | --- |
| `String` | Chuỗi JSON | Dùng cho văn bản |
| `Int` | Số nguyên | GraphQL Int là số nguyên có dấu 32-bit |
| `Float` | Số JSON | Dùng cho số thực |
| `Boolean` | `true` hoặc `false` | Không gửi chuỗi `"true"` |
| `ID` | Thường gửi chuỗi | Dùng định danh; tránh phụ thuộc cách biểu diễn số |

Ví dụ variable bắt buộc:

~~~graphql
query BookById($id: ID!) {
    book(id: $id) {
        id
        title
    }
}
~~~

`ID!` yêu cầu variable phải được cung cấp và không được null, trừ trường hợp có default value hợp lệ trong khai báo. Nếu client thiếu variable hoặc gửi null, GraphQL từ chối request ở giai đoạn input coercion; resolver không được gọi.

Variable nullable:

~~~graphql
query Books($category: String) {
    books(category: $category) {
        id
        title
    }
}
~~~

Nếu `category` không được cung cấp và không có default, nó được xem là không có giá trị. Nếu client gửi explicit null, variable có giá trị null. Sự khác biệt này có thể ảnh hưởng đến việc argument có được xem là đã truyền hay không và đến semantics của input object.

List và non-null có thể kết hợp:

~~~graphql
query BooksByIds($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
~~~

`[ID!]!` có nghĩa list bắt buộc phải có giá trị, và mỗi phần tử bên trong list cũng không được null. List có thể rỗng nếu schema hoặc business rule không cấm điều đó.

## 4. Truyền variable bằng GraphQlClient

`GraphQlClient` là API chung của Spring for GraphQL để gửi GraphQL request. Các implementation theo transport như `HttpGraphQlClient`, `WebSocketGraphQlClient` và `RSocketGraphQlClient` cung cấp cách kết nối tương ứng, còn API truyền variable về cơ bản được dùng thống nhất.

Ví dụ tạo HTTP client từ `WebClient`:

~~~java
import org.springframework.graphql.client.GraphQlClient;
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

GraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Gửi query và truyền variable:

~~~java
Mono<Book> bookMono = graphQlClient
        .document("""
                query BookById($id: ID!) {
                    book(id: $id) {
                        id
                        title
                    }
                }
                """)
        .operationName("BookById")
        .variable("id", "book-42")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Các bước chính:

1. `document(...)` cung cấp GraphQL document.
2. `operationName(...)` đặt tên operation cần thực thi.
3. `variable("id", value)` gắn giá trị cho variable `$id`.
4. `retrieve("book")` chọn field trong response cần đọc.
5. `toEntity(Book.class)` chuyển dữ liệu field thành Java object.

Ví dụ trên trả về `Mono<Book>` vì GraphQlClient là API reactive. Ứng dụng có thể tiếp tục compose với Reactor hoặc subscribe ở tầng phù hợp. Tránh gọi `block()` trên event-loop của WebFlux.

## 5. Truyền nhiều variables

Có thể khai báo nhiều variable trong operation rồi gọi `variable(...)` nhiều lần:

~~~graphql
query SearchBooks(
    $keyword: String!
    $page: Int!
    $size: Int!
) {
    searchBooks(keyword: $keyword, page: $page, size: $size) {
        content {
            id
            title
        }
        totalElements
    }
}
~~~

Java:

~~~java
Mono<BookPage> result = graphQlClient
        .document("""
                query SearchBooks(
                    $keyword: String!
                    $page: Int!
                    $size: Int!
                ) {
                    searchBooks(keyword: $keyword, page: $page, size: $size) {
                        content {
                            id
                            title
                        }
                        totalElements
                    }
                }
                """)
        .operationName("SearchBooks")
        .variable("keyword", keyword)
        .variable("page", page)
        .variable("size", size)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Khi có nhiều variable, có thể truyền một map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", keyword,
        "page", 0,
        "size", 20
);

Mono<BookPage> result = graphQlClient
        .document(searchBooksDocument)
        .operationName("SearchBooks")
        .variables(variables)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Tên key trong map phải trùng với tên variable đã khai báo trong operation, không có ký tự `$` ở đầu key. Ví dụ key là `id` chứ không phải `$id`.

Dùng `variable(...)` khi chỉ có một vài giá trị cần gắn riêng lẻ. Dùng `variables(...)` khi dữ liệu đã được tổ chức thành map, ví dụ lấy từ một DTO hoặc lớp mapping. Không nên gửi cả map lẫn các biến trùng key theo nhiều cách khác nhau trong cùng một request vì dễ làm code khó hiểu.

## 6. Truyền input object

Mutation thường nhận một input object thay vì nhiều scalar argument.

SDL:

~~~graphql
input CreateBookInput {
    title: String!
    isbn: String!
    pageCount: Int
    description: String
}

type Mutation {
    createBook(input: CreateBookInput!): Book!
}
~~~

Operation:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
    createBook(input: $input) {
        id
        title
        isbn
    }
}
~~~

Client truyền object trong variable:

~~~java
Map<String, Object> input = Map.of(
        "title", "Spring for GraphQL",
        "isbn", "9780132350884",
        "pageCount", 420,
        "description", "Practical GraphQL API"
);

Mono<Book> created = graphQlClient
        .document(createBookDocument)
        .operationName("CreateBook")
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

Cấu trúc object gửi trong variable phải khớp với input type của schema. Field không tồn tại trong input type sẽ gây lỗi coercion; field bắt buộc bị thiếu hoặc null cũng bị từ chối trước khi resolver chạy.

Khi input có nhiều cấp, map có thể lồng nhau:

~~~java
Map<String, Object> input = Map.of(
        "title", "Spring for GraphQL",
        "author", Map.of(
                "name", "Lan Nguyen",
                "email", "lan@example.test"
        )
);
~~~

Giải pháp khác là dùng Java record/class làm DTO, miễn là JSON codec của client serialize object thành cấu trúc JSON phù hợp với GraphQL input type.

## 7. Dùng DTO để biểu diễn variables

Với input có cấu trúc ổn định, DTO giúp kiểm soát kiểu dữ liệu tốt hơn map:

~~~java
public record AuthorInput(
        String name,
        String email
) {
}

public record CreateBookInput(
        String title,
        String isbn,
        Integer pageCount,
        AuthorInput author
) {
}
~~~

Truyền DTO:

~~~java
CreateBookInput input = new CreateBookInput(
        "Spring for GraphQL",
        "9780132350884",
        420,
        new AuthorInput("Lan Nguyen", "lan@example.test")
);

Mono<Book> created = graphQlClient
        .document(createBookDocument)
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

DTO cần có tên property và kiểu tương thích với input type trong schema. JSON codec chịu trách nhiệm serialize DTO. Với `HttpGraphQlClient`, codec đến từ `WebClient`; có thể cấu hình Jackson hoặc codec khác qua `WebClient.Builder`.

DTO không tự bảo đảm dữ liệu hợp lệ theo schema. Client nên kiểm tra dữ liệu ở tầng UI/domain nếu cần trải nghiệm tốt, nhưng server vẫn là nơi thực thi validation có thẩm quyền.


## 8. List, enum và custom scalar variables

Variable có thể mang giá trị list:

~~~graphql
query BooksByIds($ids: [ID!]!) {
    booksByIds(ids: $ids) {
        id
        title
    }
}
~~~

Java:

~~~java
List<String> ids = List.of("book-1", "book-2", "book-3");

Mono<List<Book>> books = graphQlClient
        .document(booksByIdsDocument)
        .variable("ids", ids)
        .retrieve("booksByIds")
        .toEntityList(Book.class);
~~~

Với enum, JSON payload gửi tên enum dưới dạng chuỗi:

~~~graphql
enum BookStatus {
    DRAFT
    PUBLISHED
    ARCHIVED
}

query BooksByStatus($status: BookStatus!) {
    booksByStatus(status: $status) {
        id
        title
    }
}
~~~

~~~java
.variable("status", "PUBLISHED")
~~~

Nếu Java có enum tương ứng, JSON codec thường serialize enum theo tên. Hãy bảo đảm tên symbol trùng với GraphQL enum value; tên enum Java không tự động được chuyển sang một symbol khác nếu không có custom serializer.

Custom scalar như `Date`, `DateTime`, `UUID` hoặc `Money` có định dạng do schema và scalar implementation quy định. Ví dụ nếu server định nghĩa `Date` nhận chuỗi ISO-8601, client có thể truyền:

~~~java
.variable("publishedAfter", "2026-01-01")
~~~

Không giả định GraphQL server và client dùng chung cách serialize Java object. Client chỉ gửi JSON; custom scalar trên server quyết định JSON value nào được chấp nhận. Nếu muốn truyền `LocalDate` trực tiếp, hãy cấu hình JSON codec để serialize theo đúng định dạng mà scalar server mong đợi.

## 9. Default value, omitted và explicit null

GraphQL hỗ trợ default value ngay trong khai báo variable:

~~~graphql
query SearchBooks(
    $keyword: String!
    $page: Int = 0
    $size: Int = 20
) {
    searchBooks(keyword: $keyword, page: $page, size: $size) {
        id
        title
    }
}
~~~

Nếu client không gửi `page` hoặc `size`, GraphQL dùng default tương ứng. Nếu client gửi một giá trị cụ thể, giá trị đó được dùng thay thế default.

Với variable nullable không có default, có ba trường hợp cần phân biệt:

| Client gửi | Ý nghĩa |
| --- | --- |
| Không có key trong `variables` | Variable không được cung cấp; nếu có default thì dùng default |
| Có key và giá trị `null` | Variable được cung cấp với giá trị null |
| Có key và giá trị khác null | Variable nhận giá trị được gửi |

Explicit null không kích hoạt default value. Ví dụ `$page: Int = 0` nếu client gửi `"page": null`, giá trị vẫn là null chứ không quay về 0.

Để bỏ qua variable, không thêm key đó vào map. Để gửi explicit null, map phải có key với giá trị null. Java `Map.of(...)` không cho phép null, nên dùng `HashMap` hoặc `LinkedHashMap`:

~~~java
import java.util.LinkedHashMap;

Map<String, Object> variables = new LinkedHashMap<>();
variables.put("keyword", "spring");
variables.put("page", null);

graphQlClient.document(searchBooksDocument)
        .variables(variables)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Trong ví dụ này, `page` được gửi explicit null. Nếu muốn dùng default page 0, hãy bỏ hẳn key `page`.

Với input object, omitted field và explicit null cũng có thể có semantics khác nhau. Điều này đặc biệt quan trọng với mutation cập nhật một phần: omitted thường có nghĩa giữ nguyên giá trị cũ, còn explicit null có thể có nghĩa xóa giá trị. Server cần dùng kiểu binding có thể giữ được sự khác biệt đó nếu nghiệp vụ yêu cầu.

## 10. Operation name và document ổn định

Operation name giúp server, log và tracing xác định operation đang chạy. Khi document chỉ có một operation, tên có thể được bỏ qua; khi document chứa nhiều operation, client phải chỉ định operation name phù hợp.

~~~java
graphQlClient.document(searchBooksDocument)
        .operationName("SearchBooks")
        .variable("keyword", "spring")
        .variable("page", 0)
        .variable("size", 20)
        .retrieve("searchBooks")
        .toEntity(BookPage.class);
~~~

Nên giữ GraphQL document ổn định và chỉ thay đổi variables giữa các request. Có thể đặt document trong file `.graphql` hoặc constant để dễ quản lý, review và kiểm thử. Đừng dựng document bằng cách nối giá trị user input vào chuỗi query.

Operation name là tên của operation trong GraphQL document. Nó không phải tên field resolver và cũng không phải tên variable. Hãy giữ các tên này nhất quán để log và telemetry dễ đọc.

## 11. Variables và JSON codec

`GraphQlClient` truyền variables dưới dạng map key/value; transport client chịu trách nhiệm encode chúng vào request payload.

Với `HttpGraphQlClient`, việc encode/decode HTTP được thực hiện qua `WebClient` và các codec đã cấu hình. Nếu client dùng DTO, hãy kiểm tra Jackson hoặc codec tương ứng có thể serialize record, enum, ngày giờ và nested object đúng cách.

Ví dụ tùy chỉnh `WebClient` trước khi tạo GraphQL client:

~~~java
ObjectMapper objectMapper = new ObjectMapper()
        .findAndRegisterModules();

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .codecs(configurer ->
                configurer.defaultCodecs()
                        .jackson2JsonEncoder(
                                new Jackson2JsonEncoder(objectMapper)
                        )
                        .jackson2JsonDecoder(
                                new Jackson2JsonDecoder(objectMapper)
                        )
        )
        .build();

GraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Cấu hình codec cụ thể có thể khác theo phiên bản Spring Framework và cách ứng dụng đã cấu hình `WebClient`. Nếu dùng `WebClient.Builder` do Spring Boot cung cấp, cân nhắc tái sử dụng cấu hình codec chung của ứng dụng thay vì tự tạo một ObjectMapper không đồng nhất.

Không cần tự chuyển variables thành JSON string. Hãy truyền `Map`, list hoặc DTO cho `GraphQlClient`; codec sẽ encode payload. Chỉ khi một scalar có định dạng đặc biệt, hãy cấu hình serializer hoặc chuyển giá trị sang JSON representation đúng theo scalar contract.

## 12. Tái sử dụng client và cấu hình theo transport

`GraphQlClient` là abstraction dùng chung cho nhiều transport. Client HTTP, WebSocket và RSocket khác nhau ở phần kết nối và vòng đời connection, nhưng cách khai báo document và truyền variables vẫn theo cùng mô hình request.

Ví dụ HTTP client:

~~~java
GraphQlClient httpClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Ví dụ WebSocket client được tạo từ WebSocket URI và implementation WebSocket client tương ứng:

~~~java
import java.net.URI;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI uri = URI.create("ws://localhost:8080/graphql");

// webSocketClient is a configured WebSocketClient instance.
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(uri, webSocketClient).build();
~~~

RSocket client có thể được tạo từ `RSocketRequester` đã cấu hình:

~~~java
import org.springframework.graphql.client.RSocketGraphQlClient;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketGraphQlClient rsocketClient =
        RSocketGraphQlClient.builder(rSocketRequester).build();
~~~

Tên builder và các kiểu transport cụ thể phụ thuộc implementation Spring đang dùng, nhưng phần request có thể viết tương tự:

~~~java
Mono<Book> book = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .retrieve("book")
        .toEntity(Book.class);
~~~

Đừng tạo một client mới cho từng operation. Thường nên cấu hình và tái sử dụng client bean để dùng connection pool, codec, authentication và interceptor nhất quán. Với WebSocket, cần quản lý lifecycle của connection; không mở connection mới cho mỗi lần gọi nếu ứng dụng có thể dùng lại session hiện tại.

## 13. Đọc kết quả và xử lý GraphQL errors

Có hai cách đọc response:

- `retrieve(path)` là cách ngắn gọn khi chỉ cần một field cụ thể.
- `execute()` trả về `ClientGraphQlResponse` để kiểm tra toàn bộ response, bao gồm `data`, `errors` và `extensions`.

Ví dụ lấy một field:

~~~java
Mono<Book> book = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .retrieve("book")
        .toEntity(Book.class);
~~~

Nếu field được chọn có lỗi hoặc không thể truy cập, API retrieve có thể phát sinh `FieldAccessException`. Có thể xử lý ở tầng service/client adapter để chuyển lỗi sang kiểu lỗi ứng dụng phù hợp.

Khi cần kiểm tra errors rõ ràng:

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient
        .document(bookByIdDocument)
        .variable("id", bookId)
        .execute();

Mono<Book> result = responseMono.map(response -> {
    if (!response.isValid()) {
        throw new IllegalStateException(
                "GraphQL request returned errors: " + response.getErrors()
        );
    }

    return response.field("book").toEntity(Book.class);
});
~~~

Ví dụ trên minh họa cách kiểm tra response; ứng dụng thực tế nên dùng exception riêng và tránh ghi log toàn bộ variable values nếu chúng chứa dữ liệu nhạy cảm. GraphQL response có thể chứa cả `data` và `errors`, nên không phải mọi lỗi đều đồng nghĩa toàn bộ operation không có dữ liệu.

Khi dùng `retrieve(path)`, client tập trung vào field cần lấy. Khi cần quyết định dựa trên nhiều field, partial data hoặc extension metadata, dùng `execute()` và kiểm tra response đầy đủ.

## 14. Không ghép user input vào GraphQL document

Không tạo query bằng cách nối chuỗi:

~~~java
// Không nên: userInput được ghép trực tiếp vào GraphQL syntax.
String document = "query { book(id: \"" + userInput + "\") { id title } }";
~~~

Cách này dễ hỏng khi giá trị có dấu ngoặc kép, dấu gạch chéo hoặc ký tự đặc biệt. Nguy hiểm hơn, nếu input làm thay đổi cấu trúc document, client có thể vô tình gửi một operation khác với dự định.

Dùng variable:

~~~java
graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
        .variable("id", userInput)
        .retrieve("book")
        .toEntity(Book.class);
~~~

GraphQL document vẫn giữ nguyên cấu trúc, còn giá trị được serialize như dữ liệu. Đây là cách truyền input đúng theo GraphQL và giảm rủi ro injection qua việc dựng query động.

Nếu cần chọn field hoặc operation động, không thể thay tên field bằng variable vì GraphQL variables chỉ truyền value, không thay thế cú pháp hoặc identifier. Hãy dùng allowlist để chọn giữa các document/operation đã định nghĩa sẵn.


## 15. Kiểm thử variables với GraphQlTester

`GraphQlTester` kiểm thử GraphQL server và cho phép gửi variables theo cách gần với request thật. Đây là cách kiểm tra schema có chấp nhận variable type, coercion và resolver có nhận đúng giá trị hay không.

Ví dụ kiểm thử query:

~~~java
@Test
void findsBookByVariableId() {
    graphQlTester.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .operationName("BookById")
            .variable("id", "book-42")
            .execute()
            .path("book.id")
            .entity(String.class)
            .isEqualTo("book-42");
}
~~~

Có thể kiểm thử nested input object:

~~~java
@Test
void createsBookWithInputVariable() {
    Map<String, Object> input = Map.of(
            "title", "Spring for GraphQL",
            "isbn", "9780132350884",
            "pageCount", 420
    );

    graphQlTester.document("""
            mutation CreateBook($input: CreateBookInput!) {
                createBook(input: $input) {
                    title
                    isbn
                }
            }
            """)
            .variable("input", input)
            .execute()
            .path("createBook.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

Các trường hợp nên có trong test:

- Variable non-null bị thiếu.
- Variable non-null nhận explicit null.
- Variable có kiểu sai, ví dụ truyền chuỗi cho `Int`.
- Variable list có phần tử null khi khai báo `[ID!]!`.
- Input object thiếu field non-null.
- Variable được bỏ qua để kiểm tra default value.
- Explicit null không bị hiểu nhầm thành default.
- Nhiều operation trong một document có operation name rõ ràng.
- Resolver không được gọi khi input coercion thất bại.

`GraphQlTester` kiểm tra server contract. Nếu cần kiểm tra chính client HTTP serialize đúng variables, có thể viết integration test với mock HTTP server hoặc test server và xác nhận JSON request body. Không nên chỉ unit test method mapping mà bỏ qua JSON codec khi client dùng DTO hoặc custom scalar.

## 16. Mapping tên variable với Java property

Tên variable trong operation và key trong map phải khớp chính xác, nhưng tên Java property bên trong DTO phải serialize thành field name của GraphQL input type.

Ví dụ schema:

~~~graphql
input CreateBookInput {
    pageCount: Int
}

type Mutation {
    createBook(input: CreateBookInput!): Book
}
~~~

Java DTO:

~~~java
public record CreateBookInput(
        Integer pageCount
) {
}
~~~

Nếu DTO dùng property name khác, chẳng hạn `pages`, cần cấu hình JSON naming hoặc mapping phù hợp để gửi đúng key `pageCount`. Không nên trông chờ GraphQL server tự đoán tên property Java.

Tương tự với enum, custom scalar và ngày giờ: JSON representation sau serialize phải khớp contract của schema. Hãy kiểm tra payload thực tế trong integration test khi dùng naming strategy, Jackson annotation hoặc custom serializer.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Variable "$id" was not provided` | Thiếu key `id` trong variables map | Truyền variable bắt buộc hoặc khai báo default phù hợp |
| `Variable "$id" of non-null type ... must not be null` | Client gửi explicit null cho variable non-null | Kiểm tra dữ liệu trước khi gửi hoặc đổi schema nếu null được phép |
| `Variable "$page" got invalid value` | Giá trị JSON không tương thích scalar/list/enum | Kiểm tra kiểu Java và JSON payload |
| Field input không nhận giá trị | Key trong map/DTO khác tên field SDL | Đồng bộ JSON property name với input type |
| Nested input bị null | DTO không serialize đúng cấu trúc hoặc thiếu nested property | Kiểm tra DTO và JSON codec |
| Default value không được dùng | Client gửi key explicit null thay vì bỏ key | Bỏ key khỏi variables map nếu muốn dùng default |
| `Map.of` ném NullPointerException | Java immutable map factory không chấp nhận null | Dùng `HashMap` hoặc `LinkedHashMap` |
| Query document bị lỗi khi giá trị có dấu ngoặc kép | Ghép user input trực tiếp vào chuỗi GraphQL | Dùng variable và để codec serialize |
| `retrieve(path)` phát sinh `FieldAccessException` | Field path có lỗi hoặc không có dữ liệu truy cập được | Kiểm tra response errors và chọn path đúng |
| DTO nhận ngày giờ sai định dạng | JSON codec và custom scalar không thống nhất | Chuẩn hóa serializer theo scalar contract |
| Operation sai được chạy hoặc không được chọn | Document có nhiều operation nhưng thiếu/sai operationName | Đặt operation name khớp chính xác |
| Test pass nhưng request thực tế sai | Chỉ kiểm thử resolver, chưa kiểm tra payload variables | Bổ sung GraphQlTester và client integration test |

## 18. Quy trình xây dựng request có variables

Khi viết một operation dùng variables, có thể làm theo trình tự:

1. Xác định field hoặc mutation cần gọi và các argument của nó.
2. Khai báo variable trong operation với đúng GraphQL type.
3. Chọn nullability theo hợp đồng API; dùng non-null cho dữ liệu thực sự bắt buộc.
4. Đưa variable vào argument hoặc input object tại vị trí cần thiết.
5. Truyền giá trị bằng `variable(name, value)` hoặc `variables(map)`.
6. Dùng DTO khi input có cấu trúc ổn định; dùng map khi cần payload linh hoạt.
7. Kiểm tra omitted, explicit null và default value.
8. Đặt operation name khi document có nhiều operation.
9. Để JSON codec serialize dữ liệu; không tự ghép giá trị vào GraphQL document.
10. Dùng `retrieve(path)` khi cần một field, hoặc `execute()` khi cần kiểm tra toàn response.
11. Kiểm thử variable coercion, input object và serialization bằng GraphQlTester/integration test.
12. Không log toàn bộ variables nếu có dữ liệu cá nhân hoặc bí mật.

## 19. Những điểm cần ghi nhớ

- GraphQL variable tách dữ liệu đầu vào khỏi document.
- Variable được khai báo bằng tên và GraphQL type trong phần đầu operation.
- Dấu `!` biểu thị non-null; list có thể kết hợp nullability ở cấp list và phần tử.
- `GraphQlClient` truyền từng giá trị bằng `variable(...)` hoặc cả map bằng `variables(...)`.
- Key trong variables map không có dấu `$` và phải khớp tên variable trong document.
- Input object có thể được truyền bằng map lồng nhau hoặc DTO được JSON codec serialize.
- Custom scalar phụ thuộc JSON representation mà server scalar chấp nhận.
- Omitted khác explicit null; explicit null không kích hoạt default value.
- `operationName` xác định operation cần chạy khi document có nhiều operation.
- Dùng variables giúp tránh dựng query bằng cách nối user input vào GraphQL syntax.
- `retrieve(path)` tiện cho một field; `execute()` phù hợp khi cần kiểm tra toàn bộ data/errors/extensions.
- Kiểm thử cả server variable coercion lẫn client JSON serialization.

GraphQL variables là cơ chế chuẩn để truyền dữ liệu vào operation. Khi khai báo type đúng, giữ document ổn định, phân biệt omitted với null và để client codec serialize payload, request sẽ dễ tái sử dụng, kiểm thử và bảo trì hơn.

## Tài liệu tham khảo

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient](https://docs.spring.io/spring-graphql/reference/client.html#client.graphqlclient)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Variables](https://spec.graphql.org/October2021/#sec-Language.Variables)
- [GraphQL Specification — Input Objects](https://spec.graphql.org/October2021/#sec-Input-Objects)

