# Client document

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích GraphQL document và vai trò của nó trong một client request.
- Tạo request bằng GraphQlClient.document(String).
- Phân biệt document text với operation name.
- Truyền variables bằng variable() và variables().
- Chọn operation khi một document chứa nhiều operation.
- Tái sử dụng fragment trong document.
- Lưu GraphQL document thành file và tải bằng documentName().
- Chọn retrieve() hoặc execute() sau khi khai báo document.
- Tránh lỗi khi xây dựng document và kiểm thử client request.

## GraphQL document là gì?

GraphQL document là nội dung GraphQL mà client gửi tới server để mô tả operation cần thực thi. Document có thể chứa một hoặc nhiều operation như query, mutation, subscription và các fragment được những operation đó sử dụng.

Ví dụ một query document:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}
~~~

Document này gồm:

- Tên operation: BookById.
- Loại operation: query.
- Variable declaration: $id có kiểu ID!.
- Selection set: yêu cầu các field bookById.id và bookById.title.

Document mô tả dữ liệu client muốn lấy. Server dùng schema để parse, validate và thực thi operation. Client không cần biết resolver Java nào sẽ xử lý field; nó chỉ cần gửi document hợp lệ theo schema.

Trong Spring for GraphQL, GraphQlClient cung cấp một workflow chung để gửi request qua nhiều transport. Client bắt đầu tạo request bằng document(String) hoặc documentName(String), sau đó thêm variables, operation name và chọn cách đọc response. Cách xây dựng request cơ bản giống nhau giữa HTTP, WebSocket và RSocket. [Tài liệu Spring for GraphQL – Client](https://docs.spring.io/spring-graphql/reference/client.html)

## Khởi tạo GraphQlClient

GraphQlClient là abstraction chung. Ứng dụng chọn implementation theo transport:

| Client | Transport | Đặc điểm |
| --- | --- | --- |
| HttpGraphQlClient | HTTP qua WebClient | Non-blocking, thường dùng trong ứng dụng reactive hoặc service |
| HttpSyncGraphQlClient | HTTP qua RestClient | Blocking, phù hợp với luồng đồng bộ |
| WebSocketGraphQlClient | WebSocket | Dùng chung connection, hỗ trợ subscription stream |
| RSocketGraphQlClient | RSocket | Request/response và streaming qua RSocket |

Ví dụ tạo HTTP client:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Sau khi tạo client, có thể dùng document() để bắt đầu request. Phần còn lại của bài tập trung vào document; cấu hình authentication, headers và interceptors thuộc phần cấu hình client/transport.

## Tạo request bằng document(String)

Phương thức document(String) nhận GraphQL document dưới dạng String và trả về RequestSpec để tiếp tục cấu hình:

~~~java
String document = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                id
                title
            }
        }
        """;

Mono<Book> book = graphQlClient.document(document)
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

Trong ví dụ:

1. document(document) cung cấp nội dung operation.
2. variable("id", "book-101") gán giá trị cho variable $id.
3. retrieve("bookById") chọn field trong phần data của response.
4. toEntity(Book.class) chuyển giá trị field thành Java object.

HttpGraphQlClient trả kết quả theo reactive API, nên retrieve() tạo một publisher như Mono<Book>. Request chỉ được thực thi khi publisher được subscribe bởi runtime hoặc được kiểm thử bằng Reactor Test. Không gọi block() trong WebFlux pipeline chỉ để lấy kết quả đồng bộ.

Với HTTP client blocking, có thể dùng HttpSyncGraphQlClient và retrieveSync():

~~~java
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

HttpSyncGraphQlClient syncClient =
        HttpSyncGraphQlClient.create(
                RestClient.create("https://api.example.com/graphql"));

Book book = syncClient.document(document)
        .variable("id", "book-101")
        .retrieveSync("bookById")
        .toEntity(Book.class);
~~~

Chọn blocking hay non-blocking theo kiến trúc ứng dụng và transport đang dùng. Cú pháp khai báo document và variables vẫn tương tự.

## Phân biệt document với operation name

Document là toàn bộ nội dung GraphQL gửi đi. Operation name là tên của một operation cụ thể nằm bên trong document.

Ví dụ document chứa hai query:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
  }
}

query RecentBooks($first: Int!) {
  recentBooks(first: $first) {
    id
    title
  }
}
~~~

Document có hai operation. GraphQL server cần biết operation nào được chọn để thực thi. Client dùng operationName():

~~~java
Mono<Book> book = graphQlClient.document(document)
        .operationName("BookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

Operation name phải khớp chính xác với tên khai báo trong document. Nếu document chỉ có một operation, client thường không cần đặt operationName. Nếu document chứa nhiều operation, request phải chỉ rõ operation cần thực thi.

Đừng nhầm:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Document | Toàn bộ đoạn GraphQL | Nội dung request |
| Operation name | BookById | Chọn operation trong document |
| Field path | bookById | Vị trí dữ liệu cần đọc trong response.data |
| Variable name | id | Tên biến được khai báo trong operation |

retrieve("bookById") không chọn operation có tên BookById. Nó chọn đường dẫn field bookById trong response data. Việc chọn operation và chọn field path là hai bước độc lập.

## Truyền variables cho document

Không nên nối giá trị đầu vào trực tiếp vào chuỗi GraphQL. Hãy khai báo variables trong document rồi gán giá trị bằng variable() hoặc variables().

Ví dụ document:

~~~graphql
query SearchBooks($keyword: String!, $first: Int!) {
  searchBooks(keyword: $keyword, first: $first) {
    id
    title
  }
}
~~~

Gán từng variable:

~~~java
Mono<List<Book>> books = graphQlClient
        .document(searchBooksDocument)
        .variable("keyword", "Spring")
        .variable("first", 10)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

Hoặc truyền nhiều variables bằng Map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10);

Mono<List<Book>> books = graphQlClient
        .document(searchBooksDocument)
        .variables(variables)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

Tên key trong Map phải trùng với tên variable trong document, không có ký tự $ ở đầu. Giá trị cần tương thích với kiểu GraphQL đã khai báo, ví dụ String cho String!, số nguyên cho Int! và input object cho input type.

### Truyền input object

GraphQL variables có thể chứa object tương ứng với input type:

~~~graphql
input BookFilter {
  keyword: String
  category: String
  publishedAfter: String
}

query FilterBooks($filter: BookFilter!, $first: Int!) {
  books(filter: $filter, first: $first) {
    id
    title
  }
}
~~~

Java có thể dùng Map:

~~~java
Map<String, Object> filter = Map.of(
        "keyword", "GraphQL",
        "category", "TECHNOLOGY");

Map<String, Object> variables = Map.of(
        "filter", filter,
        "first", 20);

Mono<List<Book>> books = graphQlClient
        .document(filterBooksDocument)
        .variables(variables)
        .retrieve("books")
        .toEntityList(Book.class);
~~~

Hoặc dùng DTO/record:

~~~java
public record BookFilter(
        String keyword,
        String category,
        String publishedAfter) {
}

public record FilterBooksVariables(
        BookFilter filter,
        int first) {
}
~~~

~~~java
FilterBooksVariables requestVariables =
        new FilterBooksVariables(
                new BookFilter("GraphQL", "TECHNOLOGY", null),
                20);

Mono<List<Book>> books = graphQlClient
        .document(filterBooksDocument)
        .variable("filter", requestVariables.filter())
        .variable("first", requestVariables.first())
        .retrieve("books")
        .toEntityList(Book.class);
~~~

Việc serialize DTO thành variables phụ thuộc JSON codec của transport. Với HTTP client dựa trên WebClient, Spring dùng codec được cấu hình trên WebClient. Hãy kiểm tra codec và cách xử lý null/omitted nếu ứng dụng dùng input object có trạng thái cập nhật một phần.

### Không nội suy input vào document

Không xây dựng query bằng cách ghép chuỗi:

~~~java
// Không nên: input có thể làm hỏng cú pháp và tạo rủi ro injection.
String document = "query { bookById(id: \"" + id + "\") { title } }";
~~~

Hãy dùng variable:

~~~java
String document = """
        query BookById($id: ID!) {
            bookById(id: $id) {
                title
            }
        }
        """;

Mono<Book> book = graphQlClient.document(document)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

GraphQL variables tách operation text khỏi dữ liệu đầu vào. Điều này giúp document ổn định, dễ validate, dễ tái sử dụng và tránh lỗi escape khi giá trị chứa dấu nháy hoặc ký tự đặc biệt.

## Dùng fragment để tái sử dụng selection set

Fragment cho phép định nghĩa một nhóm field và sử dụng lại trong nhiều operation hoặc nhiều vị trí của cùng document.

~~~graphql
fragment BookSummary on Book {
  id
  title
  publishedAt
}

query BookById($id: ID!) {
  bookById(id: $id) {
    ...BookSummary
    author {
      id
      name
    }
  }
}
~~~

Fragment giúp selection set nhất quán giữa các request. Nếu cần thêm field vào BookSummary, các operation dùng fragment sẽ nhận thay đổi đó.

Khi dùng fragment:

- Fragment phải có tên duy nhất trong document.
- Type condition sau on phải khớp object/interface/union phù hợp trong schema.
- Operation phải tham chiếu fragment bằng spread ...BookSummary.
- Nếu fragment tham chiếu fragment khác, document phải chứa các định nghĩa liên quan.

Không tạo một fragment quá lớn chỉ để tái sử dụng mọi field. Client nên chọn đúng dữ liệu cần thiết cho use case; fragment nên đại diện cho một selection set có ý nghĩa.

## Lưu document thành file và dùng documentName()

Với query dài hoặc được dùng ở nhiều nơi, có thể lưu document trong file .graphql hoặc .gql thay vì nhúng chuỗi trong Java.

Theo cấu hình mặc định của Spring for GraphQL, document file có thể đặt dưới graphql-documents/ trên classpath:

~~~text
src/
  main/
    resources/
      graphql-documents/
        bookById.graphql
        searchBooks.graphql
~~~

Nội dung file bookById.graphql:

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    author {
      id
      name
    }
  }
}
~~~

Client tải document theo tên:

~~~java
Mono<Book> book = graphQlClient
        .documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

documentName("bookById") yêu cầu DocumentSource tìm file tương ứng, ví dụ bookById.graphql. Tên truyền vào là document key, không phải operation name. Operation bên trong file có thể tên BookById; hai tên này không bắt buộc giống nhau.

DocumentSource là cơ chế tải document theo tên. Builder của GraphQlClient cho phép tùy chỉnh DocumentSource nếu cấu trúc hoặc cách lưu document của ứng dụng khác mặc định. Khi document không tải được, request chưa được gửi tới server; hãy kiểm tra classpath, tên file và cấu hình source.

### Khi nào dùng document(String), khi nào dùng documentName()?

| Cách dùng | Phù hợp khi |
| --- | --- |
| document(String) | Operation ngắn, sinh động theo code hoặc được giữ trong constant |
| documentName(String) | Operation dài, cần lưu file, review độc lập hoặc tái sử dụng |
| Code-generated request | Dự án dùng DGS Codegen hoặc công cụ sinh client API |

File .graphql thường dễ review trong pull request và có thể được IDE hỗ trợ syntax highlighting, completion hoặc kiểm tra schema. Đặt tên file theo use case, ví dụ bookById.graphql, createBook.graphql hoặc searchBooks.graphql.

Không dùng documentName để thay operationName. Document name định vị file; operation name chọn operation nằm trong nội dung file.

## Kết hợp document với retrieve() và execute()

Sau khi tạo RequestSpec bằng document() hoặc documentName(), client chọn cách xử lý response.

### retrieve() đọc một field path

retrieve(path) là shortcut để đọc một field từ phần data:

~~~java
Mono<Book> book = graphQlClient.documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById")
        .toEntity(Book.class);
~~~

Path là đường dẫn tương đối với data. Với field lồng nhau, có thể dùng dấu chấm:

~~~java
Mono<String> authorName = graphQlClient.documentName("bookById")
        .variable("id", "book-101")
        .retrieve("bookById.author.name")
        .toEntity(String.class);
~~~

Với list, path hỗ trợ index như books[0].title. Chỉ dùng path tương ứng với selection set thực tế trong document.

Nếu field không tồn tại hoặc có giá trị null kèm GraphQL error, retrieve có thể phát sinh FieldAccessException. Exception cung cấp response và field để ứng dụng kiểm tra lỗi hoặc chọn fallback. Nếu field tồn tại nhưng không thể decode sang kiểu Java được yêu cầu, client có thể phát sinh GraphQlClientException.

### execute() đọc toàn bộ response

Khi cần kiểm tra nhiều field, partial data hoặc errors, dùng execute():

~~~java
Mono<ClientGraphQlResponse> responseMono = graphQlClient
        .documentName("bookById")
        .variable("id", "book-101")
        .execute();
~~~

Sau đó có thể kiểm tra response:

~~~java
Mono<Book> bookResult = responseMono.map(response -> {
    if (!response.isValid()) {
        // Request có lỗi và không có response data hợp lệ.
        throw new IllegalStateException("GraphQL request failed");
    }

    ClientResponseField field = response.field("bookById");
    if (field.getValue() == null) {
        if (field.getErrors().isEmpty()) {
            // Field nullable không có giá trị.
        }
        else {
            // Field null do execution error.
        }
    }

    return field.toEntity(Book.class);
});
~~~

retrieve() phù hợp khi chỉ cần một kết quả đã decode. execute() phù hợp khi cần đọc nhiều field, kiểm tra lỗi theo path hoặc phân biệt field null bình thường với field null do execution error.

## Client document cho Mutation

Document có thể là mutation. Cách khai báo và truyền variables giống query:

~~~graphql
mutation CreateBook($input: CreateBookInput!) {
  createBook(input: $input) {
    id
    title
  }
}
~~~

Java request:

~~~java
public record CreateBookInput(
        String title,
        String authorId) {
}

CreateBookInput input =
        new CreateBookInput("Spring for GraphQL", "author-12");

Mono<Book> createdBook = graphQlClient
        .documentName("createBook")
        .variable("input", input)
        .retrieve("createBook")
        .toEntity(Book.class);
~~~

Selection set của mutation quyết định dữ liệu trả về sau khi server thực hiện thay đổi. Chỉ yêu cầu các field client cần dùng; không cần truy vấn toàn bộ object nếu giao diện chỉ cần ID và title.

Với mutation cập nhật một phần, cần hiểu khác biệt giữa field omitted và field được gửi null. GraphQL input mặc định cho phép field nullable có thể không được cung cấp hoặc được gửi null. Hai trạng thái có thể mang ý nghĩa khác nhau: omitted là giữ nguyên, null là xóa giá trị. Nếu dùng ArgumentValue<T> ở phía client, cần cấu hình Jackson với GraphQlJacksonModule để serialize trạng thái omitted đúng cách. Không tự giả định mọi JSON codec đều hiểu wrapper này.

## Client document cho Subscription

Document cũng có thể khai báo subscription:

~~~graphql
subscription BookCreated {
  bookCreated {
    eventId
    book {
      id
      title
    }
  }
}
~~~

Client cần transport hỗ trợ streaming, ví dụ WebSocketGraphQlClient hoặc RSocketGraphQlClient. Khi đó, có thể dùng cùng cách tạo request:

~~~java
Flux<BookCreatedEvent> events = webSocketGraphQlClient
        .documentName("bookCreated")
        .retrieveSubscription("bookCreated")
        .toEntity(BookCreatedEvent.class);
~~~

retrieveSubscription trả về Flux, mỗi phần tử tương ứng một kết quả subscription. Để dừng nhận event, cần hủy subscription reactive. Document là nội dung operation; transport và lifecycle streaming được quản lý bởi client tương ứng.

## Kiểm thử document và request

Nên kiểm tra document bằng schema thật hoặc test server để phát hiện lỗi syntax, tên field, variable type và fragment trước khi tích hợp với hệ thống từ xa.

Một số trường hợp cần kiểm thử:

1. Document có đúng operation type và field cần thiết.
2. Variable name khớp với khai báo trong document.
3. Variable value tương thích với GraphQL input type.
4. Document có nhiều operation luôn chỉ rõ operationName.
5. Fragment được định nghĩa và tham chiếu đúng.
6. documentName tìm được file trên classpath.
7. retrieve path trỏ đúng field trong response.data.
8. execute xử lý được errors và partial data.
9. Mutation gửi input object đúng cấu trúc.
10. Subscription dùng transport streaming và được cancel khi không còn cần.

Có thể mock GraphQlClient để kiểm thử service gọi đúng document và variables, nhưng mock không xác minh GraphQL document hợp lệ với schema. Để kiểm tra schema và response thực tế, hãy dùng integration test với GraphQL endpoint hoặc test server phù hợp.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Server báo thiếu variable | Quên gọi variable() hoặc variables() | So khớp khai báo $variable và key được truyền |
| Variable không được nhận | Sai tên key hoặc sai cấu trúc input object | Dùng đúng tên không có ký tự $ và kiểm tra DTO/Map |
| Document chứa nhiều operation bị từ chối | Không chỉ rõ operation cần chạy | Gọi operationName() |
| retrieve không tìm thấy field | Path không khớp response data | Kiểm tra alias, selection set và path |
| documentName không tải được file | Sai tên file, extension hoặc classpath location | Đặt file trong graphql-documents và dùng document key đúng |
| Fragment không hợp lệ | Thiếu fragment definition hoặc type condition sai | Kiểm tra fragment spread và schema type |
| Query lỗi khi input chứa dấu nháy | Nội suy chuỗi trực tiếp vào document | Truyền dữ liệu bằng GraphQL variables |
| Client không phân biệt null và lỗi | Chỉ dùng retrieve mà không kiểm tra FieldAccessException | Dùng execute khi cần đọc field errors và response |
| DTO input serialize sai | Codec không xử lý kiểu Java như mong đợi | Kiểm tra JSON codec và cấu hình mapper |
| Subscription không trả Flux | Dùng transport chỉ hỗ trợ request/response đơn | Chọn WebSocket, RSocket hoặc HTTP SSE |

## Thực hành tổng hợp

Xây dựng một BookGraphQlClient:

1. Tạo HttpGraphQlClient dùng WebClient.
2. Viết query BookById có variable $id: ID!.
3. Gửi document bằng document(String) và truyền ID bằng variable().
4. Tạo file bookById.graphql trong src/main/resources/graphql-documents.
5. Gửi cùng query bằng documentName("bookById").
6. Tạo document chứa hai operation và chọn một operation bằng operationName().
7. Tạo fragment BookSummary và tái sử dụng trong query.
8. Viết mutation createBook với input object và variables().
9. Dùng retrieve() để đọc một field, sau đó dùng execute() để kiểm tra errors.
10. Viết test xác minh document name, variables và operation được chọn.

Sau khi hoàn thành, hãy giải thích sự khác nhau giữa document name, operation name và response field path; vì sao nên truyền input qua variables; và khi nào nên chuyển document từ Java string sang file .graphql.

## Ghi nhớ

Client document là nội dung GraphQL mô tả operation và selection set mà client gửi tới server. Spring for GraphQL dùng GraphQlClient.document(String) cho document text và documentName(String) để tải document qua DocumentSource. Sau khi khai báo document, dùng operationName() để chọn operation khi có nhiều operation, variable() hoặc variables() để truyền input và retrieve() hoặc execute() để đọc response. Fragment giúp tái sử dụng selection set; file .graphql giúp document dài dễ review và hỗ trợ IDE. Luôn truyền dữ liệu bằng variables thay vì nối chuỗi, kiểm tra path theo response data và chọn transport phù hợp với query, mutation hoặc subscription.

## Tài liệu tham khảo

- [Spring for GraphQL – Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClient API – document and documentName](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/client/GraphQlClient.html)
- [GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/1.4.2/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [GraphQL – Learn: Queries and Variables](https://graphql.org/learn/queries/)
