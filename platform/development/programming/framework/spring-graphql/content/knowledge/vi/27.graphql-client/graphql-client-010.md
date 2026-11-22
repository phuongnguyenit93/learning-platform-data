# Client error handling

Một GraphQL client không thể chỉ kiểm tra HTTP status rồi kết luận request thành công hay thất bại. GraphQL có thể trả về data cùng errors trong một response: một field lỗi nhưng những field khác vẫn có dữ liệu. Ngược lại, request có thể thất bại trước khi nhận được GraphQL response vì DNS, TLS, timeout, HTTP transport hoặc lỗi protocol.

Với Spring for GraphQL, GraphQlClient cung cấp hai cách xử lý phổ biến: dùng execute() để nhận toàn bộ ClientGraphQlResponse và tự quyết định cách xử lý data/errors, hoặc dùng retrieve(path) để lấy một field cụ thể và nhận lỗi khi field đó không truy cập được. Chọn đúng cách giúp client giữ được partial data, phân loại lỗi nhất quán và retry an toàn.

## 1. Phân biệt GraphQL error và transport error

Đây là khác biệt quan trọng nhất khi thiết kế client:

| Loại lỗi | Xảy ra khi nào | Ví dụ | Cách xử lý |
| --- | --- | --- | --- |
| GraphQL request error | Server nhận được request nhưng không thể thực thi document | Parse error, validation error, variable coercion error | Sửa document hoặc variables; không retry cùng request một cách mù quáng |
| GraphQL execution error | Một field resolver lỗi trong lúc thực thi | NOT_FOUND, FORBIDDEN, downstream failure ở một field | Đọc errors, path, extensions; có thể vẫn sử dụng partial data |
| Transport error | Client không nhận được GraphQL response hợp lệ | DNS, TLS, connection reset, timeout, WebSocket close | Phân loại nguyên nhân; cân nhắc retry nếu thao tác an toàn |
| HTTP/protocol error | Transport trả status hoặc payload không phù hợp | 401, 403, 413, 429, 502, response body sai định dạng | Xử lý theo status, authentication, rate limit hoặc cấu hình server |
| Client-side mapping error | Response nhận được nhưng không chuyển thành kiểu Java được | Sai kiểu DTO, dữ liệu không tương thích | Sửa schema/DTO hoặc mapping; không retry network |

Một GraphQL execution error thường nằm trong response errors, không nhất thiết làm Mono/CompletableFuture của client chuyển sang trạng thái error. Trong khi đó, lỗi kết nối thường đi qua error channel của reactive publisher.

Ví dụ, server trả HTTP response hợp lệ với:

~~~json
{
  "data": {
    "bookById": null,
    "latestBooks": [
      { "id": "book-01", "title": "Spring in Action" }
    ]
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

Client đã nhận được response. Đây không phải lỗi DNS hoặc timeout; client cần quyết định có hiển thị danh sách mới nhất dù bookById bị lỗi hay không.

## 2. Tạo GraphQlClient

Spring for GraphQL cung cấp GraphQlClient làm API chung cho các transport. Với HTTP, có thể dùng HttpGraphQlClient kết hợp WebClient:

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

Ứng dụng cũng có thể dùng WebSocketGraphQlClient cho subscription hoặc RSocketGraphQlClient khi hệ thống giao tiếp qua RSocket. Cách cấu hình transport khác nhau, nhưng cách tạo operation và đọc GraphQL response qua GraphQlClient có cùng mô hình.

Nên cấu hình base URL, TLS, connection pool, timeout, authentication và tracing ở transport/client configuration. Không tạo một client mới cho từng resolver hoặc từng request nếu client có thể được tái sử dụng an toàn như bean dùng chung.

## 3. Hai cách đọc response: execute và retrieve

GraphQlClient có hai kiểu API:

| API | Mục đích | Hành vi lỗi |
| --- | --- | --- |
| execute() | Nhận toàn bộ ClientGraphQlResponse | GraphQL errors nằm trong response để ứng dụng tự kiểm tra |
| retrieve("path") | Lấy một field trong response theo path | Có thể phát sinh FieldAccessException nếu field có lỗi liên quan |

Dùng execute() khi client cần partial data, nhiều field độc lập hoặc muốn tự phân loại mọi GraphQL error. Dùng retrieve(path) khi chỉ cần một field và muốn luồng xử lý dừng nếu chính field đó không truy cập được.

Ví dụ dùng retrieve:

~~~java
public Mono<Book> findBook(String id) {
    return graphQlClient.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class);
}
~~~

retrieve("bookById") tập trung vào field được yêu cầu. Nếu field đó có lỗi GraphQL, client có thể nhận FieldAccessException; lỗi ở một field không liên quan không nhất thiết phải làm field đang retrieve thất bại. Nếu cần xem tất cả errors hoặc giữ partial data, dùng execute() thay vì chỉ retrieve một field.

## 4. Đọc toàn bộ ClientGraphQlResponse

Với execute(), client có thể kiểm tra getErrors(), lấy dữ liệu và xử lý theo extensions.code:

~~~java
public Mono<BookLookupResult> findBookAndLatestBooks(String id) {
    return graphQlClient.document("""
            query BookLookup($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
                latestBooks {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .execute()
        .map(response -> {
            List<ResponseError> errors = response.getErrors();

            Object bookValue = response.field("bookById").getValue();
            Object latestValue = response.field("latestBooks").getValue();

            Book book = bookValue == null
                ? null
                : objectMapper.convertValue(bookValue, Book.class);
            List<Book> latestBooks = objectMapper.convertValue(
                latestValue, new TypeReference<List<Book>>() {});

            return new BookLookupResult(book, latestBooks, errors);
        });
}
~~~

Ví dụ minh họa cách lấy raw field value và chuyển sang DTO. Cần khai báo ObjectMapper và các kiểu dữ liệu tương ứng trong ứng dụng. Với response có nhiều lỗi, hãy giữ lại danh sách lỗi thay vì chỉ nhìn vào isValid() hoặc bỏ qua getErrors().

ClientGraphQlResponse cung cấp thông tin response tổng thể, gồm data, errors và extensions. response.field("...") cho phép truy cập một field theo response path. Khi dùng execute(), GraphQL errors là dữ liệu của response; chúng không tự động biến thành exception trong reactive chain.

Không nên ném exception cho mọi error nếu ứng dụng muốn hiển thị partial data. Ví dụ, trang dashboard có thể vẫn hiển thị profile dù widget orders lỗi. Hãy giữ cả phần dữ liệu thành công và các lỗi gắn với field tương ứng.

## 5. Field path, alias và list index

GraphQL error có path xác định vị trí field bị lỗi trong response. Path dùng response key, nghĩa là alias nếu client đặt alias:

~~~graphql
query {
    featured: bookById(id: "missing") {
        id
        title
    }
    recent: latestBooks {
        id
        title
    }
}
~~~

Nếu featured lỗi, path có thể là ["featured"]. Với field lồng nhau, path có thể là ["recent", 2, "author", "name"]. Chỉ số số nguyên đại diện vị trí phần tử trong list.

Client nên dùng path để gắn lỗi vào đúng phần giao diện hoặc log đúng field. Không nên suy luận path chỉ từ tên schema field vì alias và nested selection có thể thay đổi response path.

## 6. Phân loại bằng extensions.code

Message được viết cho con người và có thể thay đổi theo ngôn ngữ. Client nên dựa vào mã ổn định trong extensions.code:

~~~json
{
  "message": "The requested book could not be found",
  "path": ["bookById"],
  "extensions": {
    "code": "BOOK_NOT_FOUND",
    "category": "NOT_FOUND"
  }
}
~~~

Một enum ở client giúp tránh so sánh chuỗi rải rác:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    FORBIDDEN,
    UNAUTHENTICATED,
    VALIDATION_FAILED,
    RATE_LIMITED,
    INTERNAL_ERROR,
    UNKNOWN
}
~~~

Hàm chuyển đổi nên chịu được code không biết:

~~~java
public ApiErrorCode parseCode(ResponseError error) {
    Object rawCode = error.getExtensions().get("code");
    if (!(rawCode instanceof String code)) {
        return ApiErrorCode.UNKNOWN;
    }

    try {
        return ApiErrorCode.valueOf(code);
    }
    catch (IllegalArgumentException ex) {
        return ApiErrorCode.UNKNOWN;
    }
}
~~~

Không để một mã lỗi mới từ server làm client crash. Khi code chưa biết, giữ message an toàn nếu cần hiển thị, ghi nhận telemetry và dùng fallback tổng quát.

Không parse message để tìm từ khóa như "not found" hoặc "forbidden". Message có thể được dịch hoặc chỉnh sửa mà không thay đổi semantics.

## 7. Field error và partial data

Một operation có thể có nhiều field độc lập. Khi một field lỗi, client cần quyết định cách dùng phần còn lại:

~~~java
return graphQlClient.document(DASHBOARD_QUERY)
    .execute()
    .map(response -> {
        DashboardView view = mapAvailableData(response);
        List<ClientFieldError> errors = response.getErrors().stream()
            .map(this::toClientFieldError)
            .toList();

        return new DashboardResult(view, errors);
    });
~~~

mapAvailableData cần kiểm tra null và field availability trước khi chuyển DTO. GraphQL nullability có thể làm null lan lên parent; một lỗi ở nested field non-null có thể khiến cả object parent thành null. Client không nên giả định một nested object luôn tồn tại chỉ vì query yêu cầu field đó.

Các chiến lược UI thường gặp:

- Giữ dữ liệu cũ và hiển thị trạng thái refresh thất bại.
- Hiển thị phần dữ liệu thành công, đánh dấu widget bị lỗi.
- Với lỗi authorization, ẩn phần dữ liệu bị từ chối và hiển thị thông báo phù hợp.
- Với lỗi toàn operation như parse/validation, hiển thị lỗi request tổng quát và không dùng data thiếu.

Không biến mọi null thành "not found". Null có thể do field nullable, resolver trả null hợp lệ, lỗi execution hoặc null propagation. Hãy xem errors và path để phân biệt.

## 8. Xử lý FieldAccessException khi dùng retrieve

retrieve(path) là shortcut tiện lợi, nhưng khi field có error liên quan, toEntity có thể phát FieldAccessException. Có thể bắt lỗi này để ánh xạ sang exception ở application client:

~~~java
public Mono<Book> findBook(String id) {
    return graphQlClient.document(BOOK_QUERY)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class)
        .onErrorMap(FieldAccessException.class, ex ->
            new RemoteBookLookupException(
                "Could not read book from catalog", ex));
}
~~~

Khi cần phân biệt BOOK_NOT_FOUND, FORBIDDEN và lỗi khác, hãy đọc response errors có sẵn trong exception theo API của phiên bản Spring for GraphQL hoặc dùng execute() để kiểm tra trực tiếp. Không gộp mọi FieldAccessException thành NOT_FOUND vì field có thể thất bại do nhiều nguyên nhân.

FieldAccessException là lỗi khi truy cập field trong GraphQL response. Nó khác transport exception: server có thể đã trả về một response hợp lệ chứa lỗi field.

## 9. Xử lý transport exception trong Reactor

Với client reactive, lỗi kết nối hoặc protocol đi qua error channel của Mono/Flux. Có thể dùng onErrorMap, onErrorResume, doOnError và retryWhen:

~~~java
public Mono<ClientGraphQlResponse> executeQuery(String id) {
    return graphQlClient.document(BOOK_QUERY)
        .variable("id", id)
        .execute()
        .doOnError(error ->
            log.warn("Catalog GraphQL transport failed", error))
        .onErrorMap(GraphQlTransportException.class, error ->
            new CatalogUnavailableException(
                "Catalog service is unavailable", error));
}
~~~

Tên và các subtype transport exception cụ thể phụ thuộc transport implementation và phiên bản thư viện. Ngoài lỗi GraphQL transport, WebClient có thể phát sinh exception HTTP hoặc network riêng. Hãy phân loại theo loại exception thực tế trong stack thay vì bắt mọi RuntimeException.

doOnError chỉ phù hợp cho side effect như logging/metrics. onErrorMap đổi loại lỗi; onErrorResume thay lỗi bằng một publisher khác. Chỉ dùng fallback nếu kết quả thay thế có ý nghĩa nghiệp vụ:

~~~java
return recommendationClient.loadForBook(bookId)
    .onErrorResume(CatalogUnavailableException.class, error -> {
        log.info("Recommendations unavailable; using empty section");
        return Mono.just(List.of());
    });
~~~

Fallback rỗng có thể phù hợp cho một widget gợi ý không bắt buộc. Không dùng nó cho dữ liệu bắt buộc, authorization failure hoặc mutation có side effect.

## 10. Không nhầm GraphQL errors với reactive onError

Hai đoạn code dưới đây có semantics khác nhau:

~~~java
// GraphQL errors nằm trong ClientGraphQlResponse.
graphQlClient.document(BOOK_QUERY)
    .execute()
    .doOnNext(response -> {
        if (!response.getErrors().isEmpty()) {
            log.warn("GraphQL execution returned field errors");
        }
    });

// Transport hoặc client execution failure đi qua reactive onError.
graphQlClient.document(BOOK_QUERY)
    .execute()
    .doOnError(error ->
        log.error("Could not obtain GraphQL response", error));
~~~

Nếu chỉ thêm onErrorResume, client có thể không xử lý GraphQL errors nằm bên trong response. Ngược lại, nếu chỉ kiểm tra getErrors(), client có thể bỏ sót timeout hoặc connection failure vì không có response để kiểm tra.

Một cách tổ chức tốt là tách hai bước:

1. Transport layer chuyển network/protocol failure thành lỗi client có kiểu.
2. GraphQL response mapper phân tích data/errors và ánh xạ error code theo contract.

## 11. Retry an toàn

Retry có thể giúp phục hồi từ lỗi tạm thời, nhưng retry mọi lỗi là nguy hiểm. Cần phân biệt:

| Tình huống | Retry? | Lý do |
| --- | --- | --- |
| DNS tạm thời, connection reset | Có thể | Request có thể chưa tới server hoặc bị gián đoạn |
| Timeout khi query đọc dữ liệu | Có thể, có giới hạn | Query nên không có side effect theo GraphQL semantics |
| HTTP 429 | Có thể | Tôn trọng Retry-After và backoff |
| HTTP 502/503/504 | Có thể | Lỗi upstream tạm thời |
| GraphQL validation error | Không | Cùng document/variables sẽ tiếp tục lỗi |
| FORBIDDEN/UNAUTHENTICATED | Không retry mù quáng | Cần thay đổi credential hoặc quyền |
| BOOK_NOT_FOUND | Thường không | Retry ngay không làm resource xuất hiện |
| Mutation timeout sau khi gửi request | Không retry tùy tiện | Server có thể đã thực hiện side effect nhưng response bị mất |

Ví dụ retry có giới hạn cho lỗi transport tạm thời:

~~~java
return graphQlClient.document(BOOK_QUERY)
    .variable("id", id)
    .execute()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(this::isTransientTransportFailure));
~~~

isTransientTransportFailure cần kiểm tra đúng loại lỗi như timeout, connection reset hoặc status tạm thời. Không retry mọi exception và không retry GraphQL error chỉ vì response có errors.

Với mutation, chỉ retry khi có cơ chế idempotency phù hợp. Một idempotency key phải được server lưu và áp dụng ở ranh giới command; chỉ gửi lại cùng GraphQL document không bảo đảm side effect chỉ xảy ra một lần.

## 12. Timeout, cancellation và deadline

Có thể đặt timeout ở reactive pipeline:

~~~java
return graphQlClient.document(BOOK_QUERY)
    .variable("id", id)
    .execute()
    .timeout(Duration.ofSeconds(3));
~~~

Timeout ở publisher giới hạn thời gian client chờ kết quả. Nó không bảo đảm server đã dừng resolver hoặc rollback công việc đang chạy. Cần cấu hình timeout ở HTTP/WebSocket client, proxy và dependency downstream; server cũng cần deadline và cancellation propagation phù hợp.

Khi client cancel subscription hoặc dispose request, transport có thể hủy việc đọc response. Điều đó không đồng nghĩa một mutation đã gửi sẽ bị hủy an toàn. Với thao tác ghi, cần thiết kế idempotency, trạng thái command và cách truy vấn lại kết quả sau timeout.

Không đặt một timeout chung quá ngắn cho mọi transport. Query đọc nhanh, mutation xử lý lâu và WebSocket subscription có lifecycle khác nhau.

## 13. Xử lý authentication và authorization errors

Nếu GraphQL response chứa UNAUTHENTICATED hoặc FORBIDDEN, client nên xử lý theo chính sách:

- UNAUTHENTICATED: thử refresh credential nếu hệ thống hỗ trợ; nếu không, yêu cầu đăng nhập lại.
- FORBIDDEN: thông báo người dùng không có quyền và không retry cùng credential.
- NOT_FOUND: hiển thị trạng thái không tồn tại hoặc che resource theo contract.
- VALIDATION_FAILED: gắn violations vào form field.
- INTERNAL_ERROR: hiển thị thông báo chung và ghi nhận correlation/trace ID để hỗ trợ.

Nếu HTTP layer trả 401 trước khi GraphQL execution chạy, client có thể không nhận GraphQL error body. Hãy xử lý HTTP authentication failure ở transport layer riêng.

Không tự động refresh token vô hạn hoặc đồng thời từ hàng trăm request. Dùng một cơ chế single-flight/token refresh nếu nhiều request cùng phát hiện token hết hạn; sau khi refresh thất bại, dừng retry và yêu cầu authentication mới.

## 14. Client error model

Ứng dụng thường không muốn để UI hoặc domain code phụ thuộc trực tiếp vào ResponseError. Có thể chuyển lỗi GraphQL sang một kiểu nội bộ:

~~~java
public record ClientGraphQlError(
        String code,
        String message,
        List<Object> path,
        Map<String, Object> extensions) {
}

public record GraphQlCallResult<T>(
        T data,
        List<ClientGraphQlError> errors) {

    public boolean hasErrors() {
        return !errors.isEmpty();
    }
}
~~~

Mapper:

~~~java
private ClientGraphQlError toClientError(ResponseError error) {
    Object code = error.getExtensions().get("code");

    return new ClientGraphQlError(
        code instanceof String value ? value : "UNKNOWN",
        error.getMessage(),
        error.getPath(),
        error.getExtensions());
}
~~~

Nếu extensions có thể chứa dữ liệu không được phép đưa vào log/UI, hãy lọc theo allowlist thay vì copy toàn bộ Map. Có thể chỉ giữ code, category và violations đã được chuẩn hóa.

Giữ data và errors cùng nhau trong result giúp tầng giao diện quyết định có dùng partial data hay không. Với use case bắt buộc thành công hoàn toàn, có thể chuyển GraphQL errors thành domain exception ở boundary phù hợp.

## 15. Logging và observability

Khi client nhận lỗi, log cần giúp phân biệt transport failure với GraphQL field error:

~~~java
log.warn(
    "GraphQL operation returned errors: operation={}, codes={}, correlationId={}",
    operationName, errorCodes, correlationId);
~~~

Với transport exception, log thêm dependency, elapsed time và exception type. Không log access token, cookie, password, toàn bộ variables hoặc response data nhạy cảm.

Correlation ID giúp nối log giữa client và server nếu được truyền qua header theo policy. Distributed trace nên dùng Micrometer Tracing/OpenTelemetry và trace context chuẩn. Không dùng correlation ID làm metric label vì mỗi request có thể tạo một giá trị duy nhất, dẫn đến cardinality cao.

Nên theo dõi các metric:

- Số transport failures theo dependency và exception category.
- Số GraphQL execution errors theo operation và error code.
- Latency và timeout rate.
- Retry count và retry exhaustion.
- Subscription disconnect/reconnect và số event bị bỏ lỡ nếu có cursor.

Không gắn user ID, email hoặc raw resource ID làm metric tag. Dùng tag có cardinality giới hạn và giữ dữ liệu chi tiết ở log/tracing có kiểm soát.

## 16. Subscription client errors

Với WebSocketGraphQlClient, lỗi có thể xuất hiện trong vòng đời dài:

- Connection không thiết lập được.
- Authentication hoặc connection initialization bị từ chối.
- Một subscription operation trả GraphQL error.
- Stream kết thúc bình thường.
- WebSocket đóng hoặc mất kết nối.
- Publisher phát lỗi transport.

Client cần phân biệt lỗi của một operation với lỗi của toàn connection. Nếu connection mất, nhiều operation có thể bị ảnh hưởng; reconnect có thể yêu cầu đăng ký lại subscription.

Khi reconnect, cần xem xét:

- Credential có còn hợp lệ không.
- Subscription có được phép đăng ký lại không.
- Có cursor/sequence ID để tiếp tục từ event cuối đã nhận không.
- Có thể nhận duplicate event sau reconnect không.
- Client có xử lý event theo idempotent manner không.

Không giả định reconnect tự động khôi phục chính xác mọi event đã mất. Nếu yêu cầu không bỏ sót event, protocol/application cần có resume cursor, replay window hoặc cơ chế đồng bộ trạng thái sau khi kết nối lại.

## 17. Kiểm thử client error handling

Nên kiểm thử riêng GraphQL response errors và transport failures. Một test chỉ mô phỏng HTTP 500 không chứng minh client xử lý được partial data hoặc error extensions.

Các tình huống nên có:

1. Response thành công, không có errors.
2. Response có data và một GraphQL field error.
3. Response có validation error và extensions.code.
4. Unknown error code được ánh xạ thành UNKNOWN thay vì làm client crash.
5. Field retrieve có lỗi tạo FieldAccessException phù hợp.
6. Transport timeout được ánh xạ thành lỗi unavailable.
7. HTTP 401/403/429 được phân loại theo policy.
8. Query transient failure được retry đúng số lần.
9. Mutation không bị retry tự động khi kết quả sau timeout chưa rõ.
10. Partial data vẫn được giữ nếu use case cho phép.
11. Error path có alias và list index được xử lý đúng.
12. Response thiếu field hoặc null được mapping an toàn.
13. Subscription reconnect không làm lộ credential và xử lý duplicate/resume theo contract.

Có thể dùng mock HTTP server như MockWebServer hoặc WireMock để trả fixture GraphQL response, status lỗi, delay và connection close. Với WebSocket client, cần test server/transport tương ứng để mô phỏng connection initialization, event stream và reconnect.

Nên kiểm tra cả request được gửi: operationName, variables, authorization header, correlation header và content type. Không đưa token thật hoặc dữ liệu production vào fixture.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| onErrorResume không chạy khi GraphQL field lỗi | Lỗi nằm trong ClientGraphQlResponse.errors | Kiểm tra getErrors() sau execute() |
| Bỏ mất partial data | Ném exception cho mọi response có errors | Giữ data và map lỗi theo field |
| Chỉ thấy FieldAccessException | Dùng retrieve(path) cho field lỗi | Kiểm tra error details hoặc dùng execute() |
| Retry validation error liên tục | Không phân biệt execution error và transport error | Chỉ retry lỗi transient |
| Mutation bị thực hiện hai lần | Retry sau timeout mà không có idempotency | Dùng idempotency key hoặc không retry tự động |
| Null bị coi là NOT_FOUND | Không xem errors/path/nullability | Kiểm tra response errors và field contract |
| Client crash khi server thêm error code | Parse enum không có fallback | Ánh xạ code lạ thành UNKNOWN |
| Log chứa dữ liệu nhạy cảm | Ghi raw variables/response | Allowlist và mask dữ liệu |
| Subscription mất event sau reconnect | Không có cursor/replay semantics | Thiết kế resume token hoặc resync |

## 19. Nguyên tắc thiết kế

Tách rõ GraphQL errors trong response với transport/protocol failures trên error channel. Dùng execute() khi cần partial data và tự phân loại errors; dùng retrieve(path) khi chỉ cần một field và chấp nhận FieldAccessException cho lỗi của field đó. Phân loại theo extensions.code ổn định, không parse message.

Chỉ retry lỗi transport tạm thời với giới hạn và backoff. Không retry validation, authorization hoặc NOT_FOUND một cách mù quáng; không retry mutation sau timeout nếu chưa có idempotency. Đặt timeout theo loại operation, hiểu cancellation không bảo đảm server đã dừng side effect và quản lý reconnect subscription bằng cursor/replay khi cần.

Giữ dữ liệu partial khi có giá trị, chuẩn hóa lỗi ở client boundary, ghi log có correlation/trace ID nhưng không log credential hay variables nhạy cảm. Với Spring for GraphQL, client error handling tốt là sự kết hợp giữa semantics của GraphQL response, hành vi transport và chính sách retry/hiển thị của ứng dụng.
