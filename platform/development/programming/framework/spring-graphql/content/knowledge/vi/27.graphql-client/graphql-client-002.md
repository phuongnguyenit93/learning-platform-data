# HttpGraphQlClient

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vai trò của **HttpGraphQlClient** trong Spring for GraphQL.
- Tạo client HTTP từ **WebClient** và cấu hình endpoint.
- Xây dựng GraphQL request bằng document, operation name và variables.
- Dùng **retrieve()** để ánh xạ một field sang Java object.
- Dùng **execute()** khi cần kiểm tra toàn bộ GraphQL response và errors.
- Tải GraphQL document từ file trên classpath.
- Cấu hình header, authentication, codec và interceptor.
- Thiết lập timeout, retry có kiểm soát và xử lý lỗi transport.
- Hiểu khả năng subscription qua Server-Sent Events của HTTP client.
- Phân biệt **HttpGraphQlClient** với **HttpSyncGraphQlClient**.
- Kiểm thử việc gọi GraphQL server từ client.

## 1. HttpGraphQlClient là gì?

Spring for GraphQL cung cấp client API để một ứng dụng Java gọi GraphQL server. **HttpGraphQlClient** là triển khai dùng **WebClient** của Spring WebFlux để gửi GraphQL request qua HTTP theo mô hình non-blocking.

Client này phù hợp khi ứng dụng cần:

- Gọi GraphQL API của một service khác.
- Gửi Query hoặc Mutation từ backend.
- Kết hợp dữ liệu từ nhiều GraphQL server.
- Tích hợp GraphQL vào reactive pipeline.
- Dùng chung cách xây request và đọc response với các GraphQL client transport khác của Spring.

Spring for GraphQL định nghĩa abstraction chung **GraphQlClient**. Các transport-specific client như **HttpGraphQlClient**, **WebSocketGraphQlClient** và **RSocketGraphQlClient** dùng chung workflow request, retrieve và execute. Vì vậy, phần lớn code tạo operation và ánh xạ response không phụ thuộc transport.

**HttpGraphQlClient** dùng HTTP request-response cho Query và Mutation. Với subscription, HTTP client chỉ hoạt động khi server hỗ trợ streaming qua Server-Sent Events (SSE). Nếu server dùng WebSocket hoặc RSocket, hãy chọn client tương ứng.

## 2. Chuẩn bị WebClient

**HttpGraphQlClient** xây dựng trên **WebClient**, vì vậy cần có Spring WebFlux **WebClient** trên classpath. Điều này không bắt buộc ứng dụng server phải chuyển sang WebFlux; một ứng dụng Spring MVC vẫn có thể dùng WebClient làm HTTP client.

Ví dụ tạo WebClient với URL GraphQL endpoint:

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com/graphql")
        .build();
~~~

Sau đó tạo **HttpGraphQlClient**:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.create(webClient);
~~~

Hoặc dùng builder để cấu hình thêm header:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBearerAuth(accessToken))
                .build();
~~~

Trong ví dụ, **accessToken** là token đã được lấy từ cơ chế xác thực của ứng dụng. Không hard-code token thật vào source code hoặc file cấu hình được commit vào repository.

### Đăng ký client thành Spring bean

Nếu nhiều service hoặc component cần gọi cùng một GraphQL endpoint, hãy tạo client dùng chung thay vì tạo mới cho từng request:

~~~java
@Configuration
public class GraphQlClientConfiguration {

    @Bean
    HttpGraphQlClient catalogGraphQlClient(WebClient.Builder builder) {
        WebClient webClient = builder
                .baseUrl("https://catalog.example.com/graphql")
                .build();

        return HttpGraphQlClient.builder(webClient).build();
    }
}
~~~

Component có thể inject client:

~~~java
@Service
public class CatalogGateway {

    private final HttpGraphQlClient graphQlClient;

    public CatalogGateway(HttpGraphQlClient graphQlClient) {
        this.graphQlClient = graphQlClient;
    }
}
~~~

Client giữ cấu hình transport và codec. Với credential thay đổi theo người dùng hoặc tenant, cần thiết kế việc truyền token theo request hoặc tạo client có cấu hình tương ứng; không đặt token của một người dùng thành default header dùng chung cho mọi request.

## 3. Tạo GraphQL request bằng document

Request bắt đầu từ một GraphQL document. Document có thể là chuỗi viết trực tiếp, hằng số hoặc file .graphql trên classpath.

Ví dụ SDL phía server:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  publishedYear: Int
}
~~~

Client gọi Query:

~~~java
String document = """
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
                publishedYear
            }
        }
        """;

Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Các bước:

1. **document(document)** cung cấp operation.
2. **variable("id", "b-01")** truyền giá trị cho biến $id.
3. **retrieve("book")** chọn field book trong phần data của response.
4. **toEntity(Book.class)** ánh xạ giá trị field thành Java object.
5. Kết quả là **Mono<Book>**, vì HTTP client thực thi non-blocking.

Sử dụng variables thay vì nối giá trị trực tiếp vào GraphQL document. Cách này giữ query ổn định, tránh lỗi escaping và giúp tái sử dụng operation.

## 4. Truyền nhiều variables và operation name

Một request có thể chứa nhiều variables. Dùng **variables(Map)** khi muốn truyền cả map:

~~~java
Map<String, Object> variables = Map.of(
        "keyword", "Spring",
        "first", 10
);

Mono<List<Book>> booksMono = graphQlClient.document("""
        query SearchBooks($keyword: String!, $first: Int!) {
            searchBooks(keyword: $keyword, first: $first) {
                id
                title
            }
        }
        """)
        .operationName("SearchBooks")
        .variables(variables)
        .retrieve("searchBooks")
        .toEntityList(Book.class);
~~~

**operationName("SearchBooks")** xác định operation cần chạy khi document có nhiều operation hoặc khi muốn ghi rõ tên operation trong request.

Có thể truyền từng variable bằng nhiều lần gọi **variable(name, value)**:

~~~java
graphQlClient.document(document)
        .operationName("BookById")
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Tên variable và kiểu dữ liệu phải khớp với khai báo trong GraphQL document và schema server. GraphQL server vẫn thực hiện validation và coercion; client không thay thế bước kiểm tra đó.

## 5. retrieve(): lấy một field từ response

**retrieve(path)** là cách ngắn gọn khi client chỉ cần một field cụ thể trong phần data.

Ví dụ response server:

~~~json
{
  "data": {
    "book": {
      "id": "b-01",
      "title": "GraphQL in Practice"
    }
  }
}
~~~

Client:

~~~java
Mono<Book> bookMono = graphQlClient.document("""
        query {
            book(id: "b-01") {
                id
                title
            }
        }
        """)
        .retrieve("book")
        .toEntity(Book.class);
~~~

Path được tính tương đối từ key data. Với field lồng nhau, dùng dấu chấm:

~~~java
Mono<String> authorName = graphQlClient.document(document)
        .retrieve("book.author.name")
        .toEntity(String.class);
~~~

Với list, có thể dùng index trong path:

~~~java
Mono<String> firstBookTitle = graphQlClient.document("""
        query {
            books {
                title
            }
        }
        """)
        .retrieve("books[0].title")
        .toEntity(String.class);
~~~

Nếu cần ánh xạ cả danh sách:

~~~java
Mono<List<Book>> books = graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
        .retrieve("books")
        .toEntityList(Book.class);
~~~

**retrieve()** phù hợp khi response path đã biết và client chỉ cần một giá trị. Nếu cần đọc nhiều field, xem errors ở nhiều nhánh hoặc xử lý partial data, hãy dùng **execute()**.

## 6. execute(): kiểm soát toàn bộ GraphQL response

**execute()** trả về **Mono<ClientGraphQlResponse>**. Cách này cho phép kiểm tra request validity, truy cập nhiều field và đọc errors gắn với từng field.

~~~java
Mono<ClientGraphQlResponse> responseMono =
        graphQlClient.document("""
                query {
                    book(id: "b-01") {
                        id
                        title
                    }
                    latestBooks {
                        id
                        title
                    }
                }
                """)
                .execute();
~~~

Xử lý response:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .execute()
        .flatMap(response -> {
            if (!response.isValid()) {
                return Mono.error(
                        new IllegalStateException(
                                "GraphQL request was rejected"));
            }

            ClientResponseField field = response.field("book");

            if (field.getValue() == null) {
                if (field.getErrors().isEmpty()) {
                    return Mono.empty();
                }

                return Mono.error(
                        new IllegalStateException(
                                "The book field could not be resolved"));
            }

            return Mono.just(field.toEntity(Book.class));
        });
~~~

Cần phân biệt các trường hợp:

- **response.isValid() == false**: request-level failure, chẳng hạn GraphQL document hoặc variables không hợp lệ.
- Field có giá trị null và không có errors: field nullable có thể đơn giản là không có dữ liệu.
- Field có giá trị null và có errors: resolver field đã thất bại hoặc GraphQL null propagation đã ảnh hưởng tới field.
- Field có giá trị nhưng không thể decode sang Java type: phát sinh lỗi chuyển đổi của client.

**execute()** hữu ích khi client cần xử lý partial data. Một field có thể lỗi trong khi các field khác vẫn có dữ liệu hợp lệ.

## 7. Xử lý FieldAccessException và GraphQlClientException

Với **retrieve(path)**, Spring cần tìm đúng response field và chuyển giá trị thành Java type. Quá trình này có thể phát sinh lỗi:

- **FieldAccessException**: path không tồn tại hoặc field có giá trị null kèm GraphQL errors.
- **GraphQlClientException**: field tồn tại nhưng giá trị không thể decode sang kiểu Java được yêu cầu.
- **GraphQlTransportException**: lỗi ở tầng transport, chẳng hạn không kết nối được server hoặc response không thể được xử lý như GraphQL response.

Ví dụ xử lý field error trong reactive pipeline:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorResume(FieldAccessException.class, exception -> {
            ClientGraphQlResponse response = exception.getResponse();
            ClientResponseField field = exception.getField();

            log.warn(
                    "Book field failed, errors={}",
                    field.getErrors());

            return Mono.empty();
        });
~~~

Không nên chuyển mọi lỗi thành **Mono.empty()**. Cách đó có thể khiến ứng dụng nhầm lẫn giữa trường hợp không có dữ liệu và lỗi server. Chỉ dùng fallback khi nghiệp vụ chấp nhận được kết quả thay thế.

Nếu cần phân biệt lỗi request và lỗi field một cách đầy đủ, dùng **execute()** để đọc **ClientGraphQlResponse** và **ClientResponseField**.

## 8. Tải GraphQL document từ file

Khi query dài hoặc được dùng ở nhiều nơi, nên lưu document thành file thay vì nhúng chuỗi trong Java.

Đặt file trong thư mục:

~~~text
src/main/resources/graphql-documents/bookById.graphql
~~~

Nội dung file:

~~~graphql
query BookById($id: ID!) {
  book(id: $id) {
    id
    title
    publishedYear
  }
}
~~~

Gọi bằng tên document:

~~~java
Mono<Book> bookMono = graphQlClient.documentName("bookById")
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class);
~~~

Spring for GraphQL có **DocumentSource** để tải document từ classpath. Mặc định, các file .graphql hoặc .gql được tìm trong **graphql-documents/**.

Có thể cấu hình **DocumentSource** qua GraphQlClient builder nếu ứng dụng cần thư mục hoặc chiến lược tải document khác.

Lưu operation thành file có một số lợi ích:

- Query dễ review và quản lý phiên bản.
- IDE có thể hỗ trợ syntax highlight và completion.
- Có thể kiểm tra document riêng với schema.
- Java code tập trung vào variables và xử lý kết quả.

Nên đặt tên file và operation thống nhất, tránh một file chứa quá nhiều operation không liên quan.

## 9. Cấu hình header và authentication

Builder của **HttpGraphQlClient** cho phép thiết lập HTTP headers dùng chung cho các request qua client.

Ví dụ Basic Authentication:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBasicAuth(username, password))
                .build();
~~~

Ví dụ Bearer token:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .headers(headers ->
                        headers.setBearerAuth(accessToken))
                .build();
~~~

Có thể dùng **mutate()** trên client đã tạo để xây một client mới với cấu hình transport khác:

~~~java
HttpGraphQlClient serviceAccountClient =
        graphQlClient.mutate()
                .headers(headers ->
                        headers.setBearerAuth(serviceToken))
                .build();
~~~

Client mới được xây từ cấu hình hiện có nhưng có thể dùng headers riêng. Điều này hữu ích khi một ứng dụng gọi cùng server bằng các credential hoặc cấu hình khác nhau.

Không dùng một singleton client với header chứa token người dùng thay đổi liên tục. Nếu mỗi request có principal khác nhau, hãy thiết kế cơ chế cấp token và truyền header theo request bằng WebClient filter/interceptor phù hợp, hoặc tạo client riêng theo security context. Không lưu token của request trước vào state dùng chung.

## 10. Tùy chỉnh WebClient và codec

Vì **HttpGraphQlClient** dùng WebClient, có thể tùy chỉnh các tính năng HTTP như:

- Base URL.
- Default headers.
- TLS và proxy.
- Connection pool.
- HTTP connector.
- Codec và giới hạn kích thước buffer.
- Exchange filter để tích hợp tracing hoặc authentication.

Ví dụ cấu hình WebClient với base URL và filter:

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("https://catalog.example.com/graphql")
        .filter((request, next) -> {
            log.debug("Calling GraphQL endpoint: {}", request.url());
            return next.exchange(request);
        })
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

Nếu cần serialize kiểu đặc biệt hoặc hỗ trợ **ArgumentValue** để phân biệt input bị bỏ qua với explicit null, cần cấu hình Jackson module phù hợp của Spring for GraphQL.

Ví dụ với Jackson 3:

~~~java
@Bean
GraphQlJacksonModule graphQlJacksonModule() {
    return new GraphQlJacksonModule();
}
~~~

Với Jackson 2, Spring for GraphQL cung cấp **GraphQlJackson2Module**. Khi tự tạo WebClient và codec, bảo đảm encoder/decoder thực sự sử dụng ObjectMapper đã đăng ký module đó.

Không thay codec mặc định nếu chưa có yêu cầu cụ thể. Cấu hình codec sai có thể khiến variables không serialize đúng hoặc làm mất khả năng decode response.

## 11. GraphQlClientInterceptor

**GraphQlClientInterceptor** cho phép can thiệp vào request và response GraphQL ở tầng client. Với non-blocking client như **HttpGraphQlClient**, interceptor sử dụng Reactor **Mono** và **Flux**.

Ví dụ interceptor ghi nhận response validity:

~~~java
public class LoggingGraphQlClientInterceptor
        implements GraphQlClientInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(
                    LoggingGraphQlClientInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        return chain.next(request)
                .doOnNext(response ->
                        log.debug(
                                "GraphQL response valid={}",
                                response.isValid()));
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return chain.next(request);
    }
}
~~~

Đăng ký interceptor khi tạo client:

~~~java
HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient)
                .interceptor(
                        new LoggingGraphQlClientInterceptor())
                .build();
~~~

Interceptor phù hợp với logic dùng chung cho nhiều request:

- Ghi log operation hoặc correlation metadata.
- Đo thời gian gọi GraphQL server.
- Gắn tracing.
- Chuẩn hóa xử lý lỗi transport.
- Thêm hoặc chuyển tiếp metadata theo chính sách client.

Không ghi toàn bộ variables nếu chúng có thể chứa password, token hoặc dữ liệu cá nhân. Nên ghi operation name, endpoint, thời gian, request ID và mã lỗi cần thiết.

## 12. Timeout, retry và cancellation

Vì **HttpGraphQlClient** trả về reactive publisher, có thể kết hợp các Reactor operator để giới hạn thời gian và xử lý lỗi tạm thời.

Ví dụ timeout cho một Query:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class)
        .timeout(Duration.ofSeconds(3));
~~~

Nếu response không đến trong thời gian quy định, publisher phát lỗi timeout và subscription của request bị hủy.

Có thể retry với lỗi transport tạm thời:

~~~java
Mono<Book> bookMono = graphQlClient.document(document)
        .variable("id", "b-01")
        .retrieve("book")
        .toEntity(Book.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(GraphQlTransportException.class::isInstance)
        );
~~~

Chỉ retry khi lỗi có thể phục hồi và operation an toàn để chạy lại. Query thường phù hợp hơn mutation. Nếu server đã thực hiện mutation nhưng response bị mất trên mạng, client không thể biết chắc thao tác đã commit hay chưa. Retry mutation có thể tạo dữ liệu trùng hoặc thực hiện side effect hai lần.

Nếu mutation cần retry, hãy thiết kế idempotency key hoặc cơ chế chống lặp ở server. Không retry mọi GraphQL field error như thể đó là lỗi kết nối.

Khi downstream không còn cần kết quả và subscriber hủy publisher, cancellation được truyền qua reactive chain để WebClient dừng request khi có thể.

## 13. Dùng HttpGraphQlClient cho Subscription qua SSE

**HttpGraphQlClient** chủ yếu được dùng cho HTTP request-response, nhưng Spring for GraphQL cũng hỗ trợ subscription qua HTTP khi server cung cấp Server-Sent Events (SSE).

Ví dụ:

~~~java
Flux<Book> bookEvents = graphQlClient.document("""
        subscription {
            bookAdded {
                id
                title
            }
        }
        """)
        .retrieveSubscription("bookAdded")
        .toEntity(Book.class);
~~~

**retrieveSubscription(...)** trả về Flux vì client có thể nhận nhiều response theo thời gian.

Điều kiện:

- Server phải cấu hình GraphQL subscription qua SSE.
- HTTP endpoint và content negotiation phải hỗ trợ streaming response.
- Client phải xử lý lỗi stream, timeout và cancellation.
- Hạ tầng proxy/load balancer phải cho phép kết nối SSE tồn tại đủ lâu.

Nếu server chỉ hỗ trợ WebSocket, dùng **WebSocketGraphQlClient**. Nếu dùng RSocket, dùng **RSocketGraphQlClient**. Không giả định mọi HTTP GraphQL endpoint đều tự động hỗ trợ subscription.

## 14. Phân biệt HttpGraphQlClient và HttpSyncGraphQlClient

Spring for GraphQL có hai client HTTP chính:

| Tiêu chí | **HttpGraphQlClient** | **HttpSyncGraphQlClient** |
|---|---|---|
| HTTP API | WebClient | RestClient |
| Mô hình | Non-blocking | Blocking |
| Kiểu kết quả | Mono/Flux | Giá trị đồng bộ |
| Interceptor | GraphQlClientInterceptor | SyncGraphQlClientInterceptor |
| Phù hợp | Reactive pipeline, WebFlux, async integration | Code imperative/blocking |
| Tên thao tác đọc field | retrieve(...) | retrieveSync(...) |
| Execute | execute() | executeSync() |

Nếu ứng dụng đang dùng WebFlux hoặc muốn giữ chuỗi xử lý non-blocking, chọn **HttpGraphQlClient**.

Nếu ứng dụng imperative dùng **RestClient** và cần API đồng bộ, chọn **HttpSyncGraphQlClient**. Không nên gọi **block()** tùy tiện trên **HttpGraphQlClient** trong event-loop hoặc reactive pipeline để giả lập client đồng bộ.

Cả hai client dùng chung workflow **GraphQlClient** nên cách viết document, variables, retrieve và execute rất giống nhau.

## 15. Kiểm thử việc gọi GraphQL server

Có hai phạm vi kiểm thử cần phân biệt:

- Kiểm thử GraphQL server bằng **HttpGraphQlTester** hoặc **WebTestClient**.
- Kiểm thử ứng dụng client gọi một GraphQL server khác bằng **HttpGraphQlClient**.

Khi kiểm thử client, có thể chạy một GraphQL server test cục bộ hoặc dùng mock HTTP server như MockWebServer/WireMock để kiểm tra request body và response mapping.

Ví dụ một integration test gọi server test đã chạy:

~~~java
@Test
void shouldFetchBookFromGraphQlServer() {
    Mono<Book> result = graphQlClient.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
            .variable("id", "b-01")
            .retrieve("book")
            .toEntity(Book.class);

    StepVerifier.create(result)
            .assertNext(book -> {
                assertThat(book.id()).isEqualTo("b-01");
                assertThat(book.title())
                        .isEqualTo("GraphQL in Practice");
            })
            .verifyComplete();
}
~~~

Test trên giả định GraphQL server test trả về Book tương ứng và **graphQlClient** đã được cấu hình trỏ tới server đó.

Nên kiểm thử:

1. Query với variables hợp lệ.
2. Mutation với input object.
3. Operation name khi document có nhiều operation.
4. Mapping response sang record/DTO.
5. Field nullable trả null mà không có error.
6. Field lỗi tạo **FieldAccessException** khi dùng retrieve.
7. **execute()** đọc request-level và field-level errors.
8. HTTP transport failure được xử lý phù hợp.
9. Timeout và retry chỉ áp dụng cho loại operation an toàn.
10. Header authentication được gửi đúng.
11. Document source tải đúng file trên classpath.
12. Subscription qua SSE nhận nhiều event và dừng khi cancellation.

Nếu dùng mock HTTP server, ngoài response body hãy kiểm tra method, URL, Content-Type, Accept, authorization header và JSON request payload.

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không kết nối được server | Sai base URL, DNS hoặc TLS | Kiểm tra endpoint và HTTP connector |
| Server trả 401/403 | Thiếu hoặc sai credential | Kiểm tra Bearer token và quyền truy cập |
| Field path không tồn tại | Sai path truyền vào retrieve | Đối chiếu với response data |
| Retrieve phát FieldAccessException | Field null kèm GraphQL error hoặc path không có | Dùng execute để đọc field errors |
| Không decode được DTO | Java type không khớp response shape | Kiểm tra field, generic type và codec |
| Variables không được gửi | Tên variable hoặc Map sai | Đối chiếu document và schema |
| Request bị block | Gọi block trong reactive/event-loop | Giữ Mono/Flux hoặc dùng HttpSyncGraphQlClient |
| Retry tạo dữ liệu trùng | Retry mutation không idempotent | Dùng idempotency key hoặc bỏ retry |
| Subscription không nhận event | Server không hỗ trợ SSE hoặc dùng sai transport | Kiểm tra SSE, WebSocket hoặc RSocket |
| Header người dùng bị lẫn | Dùng credential mutable trên client dùng chung | Truyền credential theo request hoặc tách client |
| Document file không tìm thấy | Sai thư mục hoặc tên document | Kiểm tra classpath graphql-documents/ |

## 17. Nguyên tắc sử dụng HttpGraphQlClient

Khi xây dựng GraphQL client trong ứng dụng Spring:

- Dùng **HttpGraphQlClient** cho HTTP non-blocking dựa trên WebClient.
- Tái sử dụng client đã cấu hình cho cùng endpoint.
- Dùng variables thay vì nối chuỗi query.
- Đặt operation name có ý nghĩa.
- Dùng **retrieve()** khi chỉ cần một field; dùng **execute()** khi cần toàn response.
- Xử lý riêng request error, field error và transport error.
- Dùng document file cho operation dài hoặc được tái sử dụng.
- Cấu hình authentication và headers theo phạm vi credential.
- Dùng interceptor cho logging, tracing và metadata dùng chung.
- Đặt timeout phù hợp và chỉ retry operation có thể chạy lại an toàn.
- Không block reactive pipeline.
- Chọn SSE, WebSocket hoặc RSocket đúng với subscription transport.
- Kiểm thử request payload, headers, response mapping và error behavior.

## Kết luận

**HttpGraphQlClient** là GraphQL client non-blocking của Spring for GraphQL, sử dụng **WebClient** để gửi operation qua HTTP. Sau khi tạo client, ứng dụng dùng workflow chung của **GraphQlClient** để tạo document, truyền variables, chọn operation và đọc kết quả.

**retrieve()** giúp ánh xạ nhanh một field sang Java object; **execute()** cho phép kiểm tra toàn bộ response và phân biệt request-level với field-level errors. Kết hợp WebClient headers, codec, **GraphQlClientInterceptor**, timeout và retry có kiểm soát sẽ tạo một client dễ tái sử dụng và quan sát. Với subscription, cần server hỗ trợ SSE hoặc chọn WebSocket/RSocket client tương ứng.

## Tài liệu tham khảo

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — HttpGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/HttpGraphQlClient.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring for GraphQL — GraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientInterceptor.html)
- [Spring for GraphQL — Client Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
