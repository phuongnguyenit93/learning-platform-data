# Transport và execution tách biệt

Một GraphQL API có thể được gọi qua HTTP, WebSocket hoặc RSocket. Dù cách gửi request và nhận response khác nhau, schema, resolver và quy tắc thực thi GraphQL vẫn có thể được dùng chung. Spring for GraphQL tổ chức các thành phần theo hướng tách lớp: transport adapter xử lý giao thức; execution service chuyển request thành lời gọi GraphQL engine; resolver thực hiện logic lấy dữ liệu.

Hiểu ranh giới này giúp thiết kế server dễ mở rộng. Ta có thể thêm một transport cho nhu cầu mới mà không phải viết lại toàn bộ resolver, đồng thời có thể kiểm thử logic GraphQL trực tiếp mà không cần dựng HTTP server. Tuy vậy, mỗi transport có vòng đời kết nối, cách xác thực, timeout và mô hình truyền dữ liệu riêng; các yếu tố đó vẫn cần được xử lý đúng ở lớp biên.

Sau bài này, bạn có thể giải thích đường đi của một GraphQL request trong Spring for GraphQL, phân biệt trách nhiệm của transport và execution, chọn HTTP/WebSocket/RSocket theo nhu cầu, truyền context an toàn tới resolver và kiểm thử từng lớp phù hợp.

## 1. Transport và execution là hai trách nhiệm khác nhau

**Transport** là cách một request đi từ client đến server và cách kết quả được gửi trở lại. Transport quyết định những vấn đề như:

- Request được gửi bằng HTTP, WebSocket hay RSocket.
- Dữ liệu được đóng gói trong JSON body, query parameters hay frame/message.
- Kết nối tồn tại trong một request hay được duy trì lâu dài.
- Response được gửi một lần hay theo một luồng sự kiện.
- Header, cookie, token, metadata và thông tin kết nối được truyền như thế nào.
- Timeout, giới hạn payload, ngắt kết nối và backpressure được áp dụng ra sao.

**Execution** là quá trình xử lý một GraphQL operation theo schema. Nó bao gồm:

- Phân tích tài liệu GraphQL và xác định operation cần chạy.
- Kiểm tra operation có hợp lệ với schema hay không.
- Kiểm tra và chuyển đổi variables theo kiểu đã khai báo.
- Thực thi các field, gọi data fetcher/resolver và phối hợp kết quả.
- Thu thập lỗi, dữ liệu trả về và extensions.

Ví dụ, client gửi cùng một operation lấy sách qua HTTP hoặc WebSocket. Request envelope và cách truyền dữ liệu có thể khác, nhưng GraphQL vẫn kiểm tra field, gọi resolver của Query và tạo kết quả theo cùng schema. Resolver không nên phải biết request đến từ HTTP hay WebSocket nếu nghiệp vụ không phụ thuộc vào thông tin đó.

Có thể hình dung ranh giới như sau:

~~~mermaid
flowchart TD
    C[GraphQL client] --> T[Transport]
    T --> A[Transport adapter]
    A --> W[WebGraphQlHandler cho web transport]
    A --> E[ExecutionGraphQlService]
    W --> E
    S[GraphQlSource: schema và wiring] --> E
    E --> G[GraphQL Java execution]
    G --> R[Data fetcher và resolver]
    R --> D[(Service / repository / external systems)]
    D --> R
    R --> G
    G --> E
    E --> A
    A --> T
    T --> C
~~~

Sơ đồ thể hiện ranh giới khái niệm. HTTP và WebSocket thường đi qua web handler/interceptor pipeline; RSocket có handler và cơ chế tích hợp riêng. Các đường đi cụ thể khác nhau theo transport, nhưng phần thực thi GraphQL có thể dùng chung.

## 2. Kiến trúc xử lý trong Spring for GraphQL

Spring for GraphQL kết hợp GraphQL Java với các abstraction của Spring. Những thành phần quan trọng có vai trò như sau:

| Thành phần | Trách nhiệm |
|---|---|
| GraphQlSource | Tạo GraphQL schema và runtime wiring, từ SDL cùng các cấu hình scalar, resolver, directive hoặc type resolver |
| ExecutionGraphQlService | Nhận một GraphQL request ở mức thực thi và gọi GraphQL engine |
| WebGraphQlHandler | Điều phối web request qua chuỗi WebGraphQlInterceptor rồi chuyển đến ExecutionGraphQlService |
| WebGraphQlInterceptor | Xử lý concern ở biên web như xác thực, bổ sung GraphQL context, ghi log hoặc điều chỉnh response |
| Transport handler/adapter | Chuyển request của HTTP hoặc WebSocket thành dạng request mà Spring GraphQL hiểu, rồi chuyển response thành dạng của giao thức |
| GraphQL Java | Parse, validate và execute operation theo schema |
| DataFetcher/resolver | Cung cấp giá trị cho từng field |

### GraphQlSource: schema được xây dựng ở đâu

GraphQlSource là nguồn cung cấp GraphQL instance đã được cấu hình. Nó kết hợp SDL, runtime wiring và các thành phần mở rộng để tạo schema có thể thực thi. Những thành phần như annotated controller, custom scalar, type resolver và instrumentation tham gia vào quá trình cấu hình này.

Schema không thuộc riêng HTTP hoặc WebSocket. Một schema đã được tạo có thể được dùng khi cùng ứng dụng phục vụ nhiều transport. Nếu đổi từ HTTP sang WebSocket để hỗ trợ subscription, không cần khai báo lại các object type hoặc viết lại resolver chỉ vì giao thức thay đổi.

### ExecutionGraphQlService: điểm vào của phần thực thi

ExecutionGraphQlService nhận request ở mức GraphQL, xây dựng ExecutionInput và gọi GraphQL Java. Kết quả là response ở mức GraphQL, gồm dữ liệu, lỗi và extensions nếu có. DefaultExecutionGraphQlService là implementation mặc định thường được Spring Boot cấu hình.

Thành phần này không cần tự biết HTTP method, WebSocket frame hay RSocket interaction model. Các adapter chịu trách nhiệm chuyển đổi giao thức thành request phù hợp trước khi gọi execution service.

### WebGraphQlHandler và interceptor chain

Với các web transport, WebGraphQlHandler cung cấp một pipeline chung. WebGraphQlRequest chứa thông tin của GraphQL operation cùng các thuộc tính web như URI, headers, cookies, locale và attributes. WebGraphQlInterceptor có thể đọc request, bổ sung thông tin cần thiết rồi gọi interceptor tiếp theo trong chain.

Sau khi execution hoàn tất, interceptor cũng có thể quan sát hoặc điều chỉnh response. Điều này phù hợp cho logging, tracing, xác thực, bổ sung context và xử lý chính sách chung ở biên web.

RSocket có mô hình request và metadata riêng. Khi tích hợp RSocket, dùng các thành phần handler/interceptor dành cho RSocket thay vì giả định mọi request đều là WebGraphQlRequest. Điểm cần giữ nhất quán là logic nghiệp vụ và GraphQL schema được dùng chung ở tầng execution.

## 3. Luồng xử lý một request

Với một request HTTP, đường đi điển hình gồm các bước:

1. Client gửi payload GraphQL tới endpoint.
2. HTTP handler đọc body hoặc query parameters, headers và thông tin request.
3. Adapter tạo đối tượng request mà Spring GraphQL có thể xử lý.
4. WebGraphQlHandler chạy chuỗi WebGraphQlInterceptor.
5. ExecutionGraphQlService tạo ExecutionInput và gọi GraphQL Java.
6. GraphQL Java parse, validate, coercion variables và thực thi operation.
7. Resolver/data fetcher được gọi để lấy dữ liệu; các lỗi được thu thập theo quy tắc GraphQL.
8. Execution service tạo GraphQL response.
9. Adapter chuyển response thành JSON hoặc định dạng truyền tải tương ứng rồi gửi về client.

Luồng này có thể biểu diễn ngắn gọn:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as HTTP adapter
    participant I as WebGraphQlInterceptor
    participant E as ExecutionGraphQlService
    participant G as GraphQL Java
    participant R as Resolver
    C->>A: HTTP request với GraphQL payload
    A->>I: WebGraphQlRequest
    I->>E: Tiếp tục sau khi bổ sung context
    E->>G: ExecutionInput
    G->>G: Parse, validate, coerce variables
    G->>R: Resolve các field
    R-->>G: Giá trị hoặc lỗi
    G-->>E: ExecutionResult
    E-->>I: GraphQL response
    I-->>A: Response sau interceptor chain
    A-->>C: HTTP response
~~~

Đây là mô hình tổng quát. Với WebSocket, adapter duy trì kết nối và ánh xạ message theo protocol. Với RSocket, adapter ánh xạ request-response hoặc request-stream. Không nên đồng nhất một message trên transport với một resolver: một operation có thể gọi nhiều resolver, còn một kết nối WebSocket có thể mang nhiều operation độc lập.

## 4. HTTP: request-response cho Query và Mutation

HTTP là lựa chọn phổ biến cho Query và Mutation vì mô hình request-response đơn giản, dễ tích hợp với reverse proxy, gateway, observability và hạ tầng web hiện có.

Với Spring Boot, endpoint GraphQL HTTP mặc định thường là **/graphql**. Có thể đổi path bằng cấu hình:

~~~properties
spring.graphql.path=/api/graphql
~~~

Một request POST thường gửi JSON body:

~~~http
POST /api/graphql HTTP/1.1
Content-Type: application/json
Authorization: Bearer <access-token>

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "operationName": "FindBook",
  "variables": {
    "id": "book-01"
  }
}
~~~

Các trường thường gặp trong request payload:

| Trường | Ý nghĩa |
|---|---|
| query | GraphQL document chứa một hoặc nhiều operation |
| operationName | Tên operation cần thực thi khi document có nhiều operation |
| variables | Giá trị biến đầu vào |
| extensions | Metadata mở rộng theo thỏa thuận giữa client và server |

Response thành công có thể có dạng:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": "GraphQL with Spring"
    }
  }
}
~~~

Nếu một field gặp lỗi, GraphQL có thể trả về cả phần data đã lấy được và mảng errors:

~~~json
{
  "data": {
    "book": {
      "id": "book-01",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải tiêu đề sách",
      "path": ["book", "title"]
    }
  ]
}
~~~

Hình dạng response và HTTP status code là hai lớp thông tin khác nhau. Client nên đọc cả status, content type và GraphQL response body. Một GraphQL execution error không đồng nghĩa toàn bộ HTTP request đã thất bại ở tầng mạng; ngược lại, lỗi kết nối hoặc lỗi gateway có thể xảy ra trước khi GraphQL engine được gọi.

GraphQL over HTTP có thể cho phép GET đối với Query tùy cách triển khai và quy tắc giao thức. Mutation không nên được gửi bằng GET vì GET được kỳ vọng là phương thức an toàn, không tạo thay đổi trạng thái. POST thường là lựa chọn rõ ràng cho Query và Mutation. Nếu sử dụng GET, cần chú ý query và variables nằm trong URL, có thể xuất hiện trong browser history, proxy log hoặc access log.

HTTP phù hợp khi mỗi lần gọi có thể hoàn tất bằng một response hữu hạn. Nó cũng có thể dùng cho các truy vấn có độ trễ dài, nhưng cần đặt timeout ở client, server và gateway sao cho nhất quán. Subscription tạo ra một luồng kết quả kéo dài nên cần transport hỗ trợ streaming rõ ràng.

## 5. WebSocket: kết nối lâu dài và Subscription

WebSocket bắt đầu bằng một HTTP handshake rồi nâng cấp thành kết nối hai chiều. Sau khi kết nối được thiết lập, client và server có thể trao đổi nhiều message mà không phải mở một HTTP request mới cho từng message.

Spring for GraphQL hỗ trợ GraphQL over WebSocket cho các operation cần giao tiếp qua kết nối lâu dài, đặc biệt là Subscription. WebSocket cũng có thể mang Query và Mutation; việc chọn transport không làm thay đổi ý nghĩa của các operation đó.

Trong GraphQL over WebSocket protocol hiện đại, client và server trao đổi các message theo vòng đời kết nối và operation. Một luồng điển hình:

1. Client mở WebSocket connection và thương lượng subprotocol phù hợp, thường là **graphql-transport-ws**.
2. Client gửi **connection_init**, có thể kèm payload xác thực hoặc metadata.
3. Server xác nhận kết nối bằng **connection_ack**.
4. Client gửi **subscribe** với operation và variables.
5. Server phát các message **next** khi có kết quả.
6. Client hoặc server gửi **complete** khi operation kết thúc; message **error** biểu diễn lỗi operation theo protocol.
7. Khi không còn sử dụng, client đóng kết nối.

Ví dụ một subscription GraphQL:

~~~graphql
subscription OnBookPublished($authorId: ID!) {
  bookPublished(authorId: $authorId) {
    id
    title
    publishedAt
  }
}
~~~

Resolver subscription thường cung cấp một Publisher hoặc một nguồn sự kiện reactive. Mỗi sự kiện phát ra sẽ kích hoạt việc thực thi selection set để tạo payload gửi đến client. Vì thế cần phân biệt hai việc: nguồn sự kiện tạo ra các giá trị; GraphQL execution áp dụng selection set lên từng giá trị để tạo response.

Một kết nối WebSocket có thể mang nhiều operation. Mỗi operation có định danh riêng trong protocol và có thể được kết thúc độc lập. Đóng một subscription không nhất thiết đồng nghĩa đóng toàn bộ kết nối; đóng kết nối thì mọi operation gắn với kết nối đó đều cần được dọn dẹp.

WebSocket có lợi khi client cần nhận cập nhật liên tục như trạng thái đơn hàng, thông báo hoặc dữ liệu theo dõi trực tiếp. Đổi lại, server phải quản lý kết nối lâu dài, giới hạn số kết nối và subscription, heartbeat, timeout, reconnect và cleanup. Không nên mở subscription cho mọi màn hình nếu client chỉ cần một lần đọc dữ liệu.

## 6. RSocket: request-response, stream và backpressure

RSocket là giao thức message-oriented hỗ trợ nhiều interaction model. Spring for GraphQL có tích hợp RSocket để đưa GraphQL request qua các interaction model này.

| RSocket interaction model | Cách dùng thường gặp với GraphQL |
|---|---|
| Request-response | Query hoặc Mutation trả về một kết quả |
| Request-stream | Subscription phát ra nhiều kết quả theo thời gian |
| Fire-and-forget | Không phải lựa chọn thông thường cho GraphQL operation cần response |
| Request-channel | Trao đổi luồng hai chiều; chỉ dùng khi ứng dụng có use case cụ thể và hỗ trợ phù hợp |

Điểm đáng chú ý của RSocket là hỗ trợ backpressure trong các luồng dữ liệu. Subscriber có thể điều tiết lượng item muốn nhận, giúp hệ thống phối hợp tốc độ phát và tốc độ tiêu thụ. Điều đó không tự động giới hạn chi phí resolver hoặc truy vấn cơ sở dữ liệu; server vẫn cần giới hạn query, số subscription, kích thước dữ liệu và tài nguyên xử lý.

RSocket thường phù hợp với hệ thống service-to-service hoặc ứng dụng đã dùng RSocket cho giao tiếp reactive. Việc lựa chọn RSocket cần cân nhắc khả năng hỗ trợ của gateway, client, hạ tầng triển khai và công cụ quan sát. Với ứng dụng web thông thường, HTTP cho request-response và WebSocket cho subscription có thể dễ vận hành hơn.

RSocket sử dụng metadata và routing riêng. Vì vậy không nên giả định có HTTP headers hoặc servlet request trong mọi resolver. Nếu nghiệp vụ cần tenant, principal hoặc trace context, hãy ánh xạ thông tin từ metadata của RSocket vào GraphQL context qua điểm tích hợp thích hợp.

## 7. Execution semantics không phụ thuộc transport

Dù request đến qua HTTP, WebSocket hay RSocket, GraphQL operation vẫn tuân theo quy tắc thực thi của GraphQL:

- **Query:** các field ở cùng một cấp có thể được thực thi song song; không nên dựa vào thứ tự gọi resolver của Query.
- **Mutation:** các top-level field được thực thi tuần tự theo thứ tự xuất hiện trong operation. Điều này giúp biểu diễn các bước thay đổi có thứ tự trong cùng mutation operation.
- **Subscription:** subscription operation có một root field tạo nguồn sự kiện. Với mỗi sự kiện, server thực thi selection set để tạo một response mới.

Ví dụ Query:

~~~graphql
query Dashboard {
  profile {
    id
    name
  }
  notifications {
    id
    message
  }
}
~~~

Resolver của **profile** và **notifications** có thể được chạy đồng thời. Nếu chúng cùng sửa một mutable state hoặc phụ thuộc vào thứ tự thực thi, thiết kế đó có thể gây lỗi khó đoán.

Ví dụ Mutation:

~~~graphql
mutation CompleteOrder($id: ID!) {
  reserveInventory(orderId: $id) {
    reservationId
  }
  confirmOrder(orderId: $id) {
    status
  }
}
~~~

Các top-level field của mutation được xử lý tuần tự trong operation. Tuy nhiên, việc tuần tự này không tự tạo transaction cơ sở dữ liệu. Nếu cần hai thay đổi cùng thành công hoặc cùng rollback, hãy thực hiện transaction ở service layer phù hợp.

Transport cũng không thay đổi quy tắc nullability, validation, field selection, authorization hoặc cách GraphQL biểu diễn partial data và errors. Các quy tắc này thuộc schema, execution engine và chính sách server.

## 8. Truyền authentication và GraphQL context

Resolver cần biết thông tin người dùng, tenant, correlation ID hoặc locale trong một số nghiệp vụ. Tuy nhiên, resolver không nên tự đọc trực tiếp một loại transport cụ thể. Thay vào đó, lớp biên trích xuất thông tin từ request rồi đưa vào context của lần thực thi GraphQL.

Với HTTP, thông tin có thể đến từ Authorization header, cookie hoặc request attributes. Với WebSocket, thông tin có thể được gửi trong handshake hoặc connection initialization payload. Với RSocket, thông tin có thể nằm trong metadata. Mỗi transport có điểm tiếp nhận khác nhau, nhưng sau khi xác thực, ứng dụng có thể chuẩn hóa các giá trị cần thiết thành GraphQL context.

Ví dụ dùng WebGraphQlInterceptor để đưa tenant identifier vào GraphQL context:

~~~java
@Component
public class TenantGraphQlInterceptor implements WebGraphQlInterceptor {

    private final TenantResolver tenantResolver;

    public TenantGraphQlInterceptor(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenantId = tenantResolver.resolve(request.getHeaders());

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenantId", tenantId)).build());

        return chain.next(request);
    }
}
~~~

Resolver có thể đọc context qua DataFetchingEnvironment:

~~~java
@QueryMapping
public Book book(
        @Argument String id,
        DataFetchingEnvironment environment) {

    String tenantId = environment.getGraphQlContext().get("tenantId");
    return bookService.findBook(tenantId, id);
}
~~~

Đây là ví dụ cho web transport. Với RSocket, cần lấy tenant từ metadata và đưa vào context bằng tích hợp RSocket tương ứng. Không nên dùng một HTTP interceptor như thể nó tự chạy cho mọi loại transport.

Một số nguyên tắc bảo mật quan trọng:

- Xác thực ở ranh giới transport trước khi cho phép operation truy cập dữ liệu cần bảo vệ.
- Phân quyền theo người dùng và theo field/resource trong service hoặc resolver phù hợp; chỉ có kết nối hợp lệ không đồng nghĩa mọi field đều được phép truy cập.
- Với WebSocket, kiểm tra danh tính lúc handshake hoặc connection initialization và có chính sách cho token hết hạn, thu hồi quyền, đóng kết nối và xác thực lại.
- Không coi metadata do client tự gửi như tenant ID hoặc role là dữ liệu đáng tin nếu chưa được xác minh.
- Không lưu thông tin người dùng mutable trong một singleton interceptor hoặc biến dùng chung giữa các request; context cần gắn với request/operation phù hợp.
- Không ghi access token, session secret hoặc dữ liệu nhạy cảm vào log.

## 9. Phân biệt interceptor, instrumentation và resolver

Các lớp mở rộng của Spring for GraphQL và GraphQL Java có mục đích khác nhau:

| Cơ chế | Phạm vi phù hợp | Ví dụ |
|---|---|---|
| Transport adapter | Giao thức và định dạng truyền nhận | HTTP body, WebSocket message, RSocket payload |
| WebGraphQlInterceptor | Biên của web GraphQL request/response | Xác thực, context, log request, response headers |
| RSocket-specific integration | Metadata và lifecycle của RSocket | Ánh xạ principal hoặc trace metadata |
| GraphQL Instrumentation | Vòng đời thực thi GraphQL | Đo thời gian execution, theo dõi field, tracing |
| DataFetcherExceptionResolver | Chuyển exception từ data fetcher thành GraphQL error | Chuẩn hóa mã lỗi nghiệp vụ |
| Resolver/DataFetcher | Logic lấy dữ liệu cho field | Gọi service, repository hoặc API khác |

Ví dụ, ghi nhận URI và request ID là concern ở biên transport. Đo thời gian resolver hoặc số field được thực thi là concern của execution. Kiểm tra một người dùng có quyền xem hóa đơn cụ thể hay không thuộc logic bảo mật nghiệp vụ. Đặt các concern đúng lớp giúp cùng một resolver hoạt động nhất quán trên nhiều transport.

Không phải mọi lỗi đều đi qua resolver. Lỗi parse, validation hoặc coercion variables có thể xảy ra trước khi resolver được gọi. Lỗi kết nối, handshake hoặc giải mã payload có thể xảy ra trước khi request tới GraphQL engine. Logging và monitoring cần phân biệt các giai đoạn này để xác định nguyên nhân.

## 10. Cấu hình transport trong Spring Boot

Một ứng dụng Spring Boot thường bắt đầu với GraphQL starter và một web runtime:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

Nếu ứng dụng dùng WebFlux, chọn starter WebFlux tương ứng thay cho Spring MVC web starter. Không cần đưa cả hai web stack vào ứng dụng nếu không có lý do rõ ràng.

Schema SDL thường nằm dưới:

~~~text
src/main/resources/graphql/
~~~

Spring Boot tự cấu hình GraphQL source và HTTP endpoint theo convention. Có thể đổi endpoint bằng:

~~~properties
spring.graphql.path=/api/graphql
~~~

Để bật WebSocket, bổ sung hỗ trợ WebSocket tương ứng với web stack đang sử dụng và cấu hình path:

~~~properties
spring.graphql.websocket.path=/graphql
~~~

Path WebSocket có thể trùng path HTTP vì handshake và HTTP request được phân biệt theo cơ chế giao thức. Khi triển khai qua reverse proxy, cần cấu hình proxy chuyển tiếp WebSocket upgrade và timeout đủ dài cho kết nối. Không nên giả định việc đổi HTTP path sẽ tự động cấu hình toàn bộ gateway hoặc proxy.

RSocket được cấu hình qua tích hợp RSocket của Spring. Ứng dụng cần chọn route, mapping, serialization, authentication metadata và interaction model phù hợp với hạ tầng. Cấu hình cụ thể phụ thuộc topology RSocket và phiên bản Spring Boot/Spring for GraphQL đang dùng; điểm kiến trúc cần giữ là RSocket handler chuyển request vào GraphQL execution service, không nhân bản schema và resolver.

## 11. Kiểm thử execution và kiểm thử transport

Vì transport và execution tách biệt, nên có thể kiểm thử ở nhiều mức:

| Mức kiểm thử | Công cụ phù hợp | Điều cần xác minh |
|---|---|---|
| Resolver/service | Unit test thông thường | Logic nghiệp vụ, phân quyền, xử lý dữ liệu |
| GraphQL execution | ExecutionGraphQlServiceTester hoặc tester ở mức service | Schema, operation, variables, resolver mapping, errors |
| Web GraphQL pipeline | WebGraphQlTester | Interceptor, context, execution và response web |
| HTTP endpoint | HttpGraphQlTester | URL, headers, serialization, status và response |
| WebSocket | WebSocketGraphQlTester | Handshake, protocol, nhiều message, subscription và cleanup |
| RSocket | RSocketGraphQlTester | Route, metadata, request-response và request-stream |

Ví dụ kiểm tra một operation ở mức GraphQlTester:

~~~java
graphQlTester.document("""
        query FindBook($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-01")
    .execute()
    .path("book.title")
    .entity(String.class)
    .isEqualTo("GraphQL with Spring");
~~~

Test ở mức execution hữu ích để kiểm tra schema và resolver nhanh chóng. Nhưng nó không chứng minh HTTP endpoint đã nhận đúng content type, WebSocket handshake thành công hay RSocket metadata được giải mã đúng. Những phần đó cần test qua transport tương ứng.

Với Subscription, cần kiểm tra cả việc nhận sự kiện lẫn vòng đời stream: sự kiện có đúng payload, client cancel có dừng nguồn phát khi phù hợp, lỗi được chuyển tới client như thế nào và kết nối đóng có giải phóng tài nguyên không. Chỉ kiểm tra resolver trả về Publisher là chưa đủ để xác nhận protocol hoạt động.

## 12. Lựa chọn transport theo use case

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Đọc dữ liệu và ghi dữ liệu theo request-response | HTTP | Đơn giản, tương thích hạ tầng web và gateway |
| Client cần cập nhật liên tục qua kết nối hai chiều | WebSocket | Kết nối lâu dài và truyền nhiều message |
| Service reactive trao đổi request-response và stream | RSocket | Có nhiều interaction model và backpressure |
| Kiểm tra schema/resolver mà không quan tâm mạng | Execution-level test | Tập trung vào GraphQL execution |

Không nên chọn transport chỉ vì nó mới hơn hoặc có thông lượng lý thuyết cao hơn. Hãy xem client có hỗ trợ giao thức không, gateway có chuyển tiếp được không, hệ thống cần streaming hay không, và đội vận hành có khả năng giám sát kết nối dài hạn hay không.

Một ứng dụng có thể dùng nhiều transport đồng thời: HTTP cho Query/Mutation, WebSocket cho Subscription, hoặc RSocket cho giao tiếp nội bộ. Khi đó schema và resolver có thể dùng chung, còn xác thực, context và timeout được nối vào từng transport theo cơ chế thích hợp.

## 13. Những lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
|---|---|---|
| Đặt logic HTTP header trực tiếp trong resolver | Resolver khó tái sử dụng qua WebSocket/RSocket | Chuẩn hóa thông tin cần thiết vào GraphQL context |
| Nghĩ WebSocket connection tương đương một GraphQL operation | Không quản lý đúng nhiều operation trên cùng kết nối | Phân biệt connection lifecycle và operation lifecycle |
| Dùng HTTP request-response cho luồng sự kiện kéo dài | Khó xử lý streaming và ngắt kết nối | Dùng transport hỗ trợ streaming phù hợp |
| Chỉ test ExecutionGraphQlService | Không phát hiện lỗi handshake, route hoặc serialization | Bổ sung test qua transport thực tế |
| Chỉ xác thực lúc WebSocket handshake nhưng bỏ qua vòng đời token | Kết nối lâu dài có thể giữ quyền đã hết hiệu lực | Thiết kế thời hạn, thu hồi và re-authentication |
| Tin tenant/role do client tự gửi | Có nguy cơ truy cập chéo tenant hoặc nâng quyền | Xác minh claim/metadata ở server |
| Ghi log toàn bộ payload và headers | Có thể làm lộ token hoặc dữ liệu nhạy cảm | Redact trường nhạy cảm và log metadata cần thiết |
| Không giới hạn số subscription | Tăng tải và giữ tài nguyên lâu dài | Áp dụng giới hạn, timeout, quota và cleanup |
| Cho rằng RSocket backpressure tự giới hạn chi phí GraphQL | Resolver hoặc database vẫn có thể bị quá tải | Giới hạn query complexity, batch size và tài nguyên |

## 14. Checklist khi thiết kế nhiều transport

Trước khi đưa nhiều transport vào một GraphQL server, hãy rà soát:

1. Schema và resolver có thực sự độc lập với HTTP/WebSocket/RSocket không?
2. Mỗi transport có adapter và cơ chế xác thực phù hợp không?
3. Principal, tenant, locale và trace ID được đưa vào GraphQL context một cách nhất quán chưa?
4. Chính sách phân quyền có được áp dụng ở mọi đường vào không?
5. Timeout, payload size, query depth/complexity và concurrency có giới hạn không?
6. Subscription có giới hạn số lượng, thời gian sống và cleanup khi client disconnect không?
7. Log và tracing có phân biệt lỗi transport với lỗi parse, validation và execution không?
8. Có test cả execution service và các transport được triển khai không?

Tách transport khỏi execution giúp Spring for GraphQL dùng chung schema, resolver và logic nghiệp vụ cho nhiều cách giao tiếp. Transport adapter xử lý đặc điểm của giao thức; execution service và GraphQL Java xử lý operation theo schema. Khi giữ đúng ranh giới này, ứng dụng dễ mở rộng giao thức, dễ kiểm thử và ít phụ thuộc vào chi tiết kết nối hơn, trong khi vẫn có thể áp dụng chính sách bảo mật và vận hành riêng cho từng transport.
