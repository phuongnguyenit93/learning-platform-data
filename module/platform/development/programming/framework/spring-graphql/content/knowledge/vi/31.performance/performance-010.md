# Timeout execution trong Spring for GraphQL

Một GraphQL request có thể cần gọi nhiều resolver, database và dịch vụ bên ngoài trước khi tạo response. Nếu một dependency bị treo hoặc operation tiêu tốn quá nhiều tài nguyên, request có thể giữ connection, thread, memory và downstream capacity lâu hơn mức hệ thống cho phép. Timeout là giới hạn thời gian để dừng chờ một công việc và giải phóng tài nguyên khi deadline đã hết.

Trong Spring for GraphQL cần phân biệt timeout toàn request với timeout của từng resolver hoặc dependency. `TimeoutWebGraphQlInterceptor` cung cấp request timeout cho web transports; `Mono.timeout(...)` có thể giới hạn một reactive operation; database driver và HTTP client cần timeout riêng cho I/O mà chúng quản lý. Các lớp này bổ sung cho nhau. Một HTTP client timeout đơn thuần không bảo đảm công việc đang chạy trên server cũng dừng lại.

Sau bài này, bạn có thể:

- Phân biệt request deadline, resolver timeout, downstream timeout và client/transport timeout.
- Cấu hình `TimeoutWebGraphQlInterceptor` trong Spring Boot.
- Hiểu HTTP status khi GraphQL request vượt thời gian.
- Đặt timeout cho reactive resolver và downstream call.
- Phân biệt timeout giữa các event với timeout tổng của một stream.
- Hiểu cancellation và giới hạn của việc dừng công việc đang chạy.
- Xử lý timeout trong GraphQL errors và mutation an toàn.
- Thiết kế timeout budget, kiểm thử và quan sát timeout trong production.

## 1. Timeout execution giải quyết vấn đề gì?

Một operation có thể gọi nhiều field:

```graphql
query Dashboard {
    profile {
        displayName
    }
    orders {
        id
        total
    }
    recommendations {
        id
        title
    }
}
```

Resolver `profile`, `orders` và `recommendations` có thể gọi các dependency khác nhau. Nếu recommendation service mất 20 giây mới trả lời, toàn bộ request có thể phải chờ dù hai nhánh còn lại đã có dữ liệu.

Timeout giúp hệ thống giới hạn thời gian chờ, từ đó:

- Tránh giữ request và connection vô hạn.
- Giới hạn lượng công việc đang chờ trong lúc downstream gặp sự cố.
- Giải phóng reactive subscription khi request không còn cần kết quả.
- Tạo điều kiện trả lỗi hoặc fallback trong ngân sách thời gian còn lại.
- Bảo vệ service khỏi việc một nhóm request chậm chiếm hết tài nguyên.

Timeout không làm một dependency vốn chậm trở nên nhanh hơn. Nó đặt giới hạn cho thời gian hệ thống sẵn sàng chờ và cần đi kèm giới hạn query complexity, pagination, rate limit, bulkhead và kiểm soát concurrency.

## 2. Phân biệt các loại timeout

Một request có thể đi qua nhiều lớp, mỗi lớp có một timeout riêng:

| Lớp | Timeout kiểm soát | Ví dụ |
| --- | --- | --- |
| Database/driver | Thời gian chờ query hoặc lấy connection | Query database tối đa 600 ms |
| Downstream client | Thời gian chờ HTTP/RPC response | Catalog API tối đa 700 ms |
| Resolver | Thời gian cho một field hoặc một pipeline | `Mono.timeout(Duration)` |
| GraphQL request | Thời gian tối đa để tạo response của một request | `TimeoutWebGraphQlInterceptor` |
| Gateway/proxy | Thời gian gateway chờ upstream | Reverse proxy timeout 2,5 giây |
| Client | Thời gian ứng dụng client chờ response | Mobile client timeout 3 giây |

Các timeout này không tự động đồng bộ. Ví dụ client ngừng chờ sau 2 giây nhưng server vẫn thực hiện query trong 10 giây nếu không có cancellation hoặc timeout phía server. Ngược lại, server có thể trả timeout trước khi client hết thời gian chờ.

Nên thiết kế deadline theo thứ tự từ trong ra ngoài. Dependency cần có timeout ngắn hơn resolver; request timeout cần đủ thời gian cho các resolver chạy song song và xử lý fallback; gateway/client nên chờ lâu hơn request timeout một khoảng để nhận được kết quả timeout từ server.

## 3. TimeoutWebGraphQlInterceptor

Spring for GraphQL cung cấp `TimeoutWebGraphQlInterceptor` để áp dụng request timeout cho web transports. Interceptor giới hạn thời gian từ lúc request đi vào web GraphQL interceptor chain cho tới khi response được materialize.

Khi timeout xảy ra, interceptor gửi tín hiệu cancel lên chain. Reactive data fetcher có thể nhận cancellation và tự hủy công việc đang thực hiện. Với HTTP, interceptor mặc định trả `408 Request Timeout`; có constructor cho phép chọn status khác.

`TimeoutWebGraphQlInterceptor` có từ Spring for GraphQL 1.4.0. Nếu dự án dùng phiên bản cũ hơn, cần thiết kế timeout tại web layer hoặc nâng cấp lên phiên bản hỗ trợ interceptor này.

## 4. Cấu hình timeout trong Spring Boot

Trong ứng dụng Spring Boot, chỉ cần khai báo interceptor thành bean:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(3));
    }
}
```

Spring Boot phát hiện bean `WebGraphQlInterceptor` và thêm vào interceptor chain của `WebGraphQlHandler`. Ví dụ đặt giới hạn ba giây cho request web GraphQL.

Không nhầm timeout này với `spring.mvc.async.request-timeout`, timeout của servlet container hoặc timeout của reverse proxy. Chúng thuộc các lớp khác nhau và có thể cùng tồn tại. Hãy xác nhận lớp nào kết thúc request trong log và test thay vì chỉ thay một property rồi cho rằng mọi công việc bên dưới đã được hủy.

## 5. Tùy chỉnh HTTP status khi timeout

Constructor mặc định dùng `HttpStatus.REQUEST_TIMEOUT`. Nếu API gateway hoặc quy ước vận hành của hệ thống yêu cầu status khác, có thể chỉ định status:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;
import org.springframework.http.HttpStatus;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(3),
                HttpStatus.GATEWAY_TIMEOUT);
    }
}
```

Chọn một status nhất quán với hợp đồng giữa GraphQL server, gateway và client. Với cấu hình mặc định, HTTP response timeout là `408 Request Timeout`. Nếu thay bằng `504 Gateway Timeout`, cần bảo đảm monitoring và client retry policy hiểu đúng ý nghĩa status đó.

Request timeout ở interceptor có thể kết thúc HTTP request trước khi có GraphQL response body hoàn chỉnh. Client cần xử lý HTTP status ở transport layer, không giả định mọi timeout đều xuất hiện dưới dạng `errors` trong GraphQL JSON envelope.

## 6. Cấu hình WebGraphQlHandler thủ công

Nếu tự tạo `WebGraphQlHandler` thay vì để Boot auto-configure, thêm interceptor vào chain:

```java
TimeoutWebGraphQlInterceptor timeoutInterceptor =
        new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(3));

WebGraphQlHandler handler = WebGraphQlHandler
        .builder(executionGraphQlService)
        .interceptor(timeoutInterceptor)
        .build();
```

Các interceptor khác như authentication, tenant context hoặc tracing cũng có thể được cấu hình trên handler. Thứ tự interceptor cần được thiết kế rõ ràng để xác thực và gắn context được thực hiện đúng trước khi resolver cần dữ liệu đó.

Nếu khai báo interceptor như Spring bean trong Boot, không đồng thời tự thêm cùng instance vào handler theo cách tạo hai lần timeout ngoài ý muốn.

## 7. Giới hạn của request timeout

`TimeoutWebGraphQlInterceptor` là timeout ở web request boundary, không phải timeout riêng cho từng resolver. Khi deadline request hết, toàn bộ request bị kết thúc. Điều này phù hợp để bảo vệ server khỏi operation chạy quá lâu.

Nó không thay thế timeout cho:

- Query database hoặc chờ connection pool.
- HTTP/RPC call tới dịch vụ bên ngoài.
- Một tác vụ blocking không hỗ trợ cancellation.
- Một publisher subscription sau khi stream đã được thiết lập.
- Một lời gọi `ExecutionGraphQlService` trực tiếp không đi qua web interceptor chain.
- Một request GraphQL qua RSocket, vì `TimeoutWebGraphQlInterceptor` thuộc web transports.

Nếu ứng dụng gọi `ExecutionGraphQlService` từ một integration nội bộ, job hoặc test mà không đi qua `WebGraphQlHandler`, `TimeoutWebGraphQlInterceptor` không tự được áp dụng. Hãy đặt timeout ở caller hoặc ở publisher/dependency tương ứng.

## 8. Timeout cho một reactive resolver bằng Mono.timeout

Khi chỉ một field có SLA ngắn hơn request deadline, đặt timeout ngay trên publisher của field:

```java
import java.util.concurrent.TimeoutException;

@QueryMapping
public Mono<BookView> book(@Argument String id) {
    return bookService.findById(id)
            .timeout(Duration.ofMillis(800));
}
```

Nếu `bookService.findById` không phát kết quả trong 800 ms, Reactor phát timeout error và hủy subscription upstream. GraphQL engine nhận lỗi từ resolver và xử lý theo exception mapping đã cấu hình.

Đây là timeout cho field publisher. Các field khác trong cùng query vẫn có thể hoàn tất; GraphQL response có thể chứa partial data cùng error nếu nullability của schema cho phép.

Timeout ở resolver không tự giới hạn toàn operation. Một query có nhiều resolver song song, mỗi resolver mất 700 ms, có thể có tổng thời gian gần 700 ms nếu chạy đồng thời hoặc lâu hơn nếu có dependency nối tiếp. Dùng request timeout để đặt deadline chung.

## 9. Ánh xạ timeout thành GraphQL error

Với resolver-level timeout, lỗi có thể được ánh xạ thành GraphQL error bằng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver`.

Ví dụ chuyển timeout thành exception nghiệp vụ:

```java
@QueryMapping
public Mono<BookView> book(@Argument String id) {
    return bookService.findById(id)
            .timeout(Duration.ofMillis(800))
            .onErrorMap(TimeoutException.class,
                    error -> new BookServiceTimeoutException(id, error));
}
```

Handler có thể trả error code ổn định:

```java
@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookServiceTimeout(
            BookServiceTimeoutException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Book service timed out")
                .extensions(Map.of("code", "BOOK_SERVICE_TIMEOUT"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` gắn path và location của field đang resolve. Không trả exception message nội bộ, URL downstream, SQL hoặc stack trace cho client.

Lưu ý: handler này dành cho timeout của field trong GraphQL execution. Timeout của `TimeoutWebGraphQlInterceptor` xảy ra ở request boundary và thường được biểu diễn bằng HTTP status, không phải cùng một field error.

## 10. Timeout cho Flux: idle timeout và total timeout

Với `Flux`, cần hiểu semantics của `timeout(Duration)`: operator phát timeout nếu không nhận được tín hiệu tiếp theo trong khoảng thời gian quy định. Vì vậy nó thường là giới hạn thời gian chờ giữa các event, không nhất thiết là giới hạn tổng thời gian của toàn stream.

Ví dụ idle timeout:

```java
Flux<OrderEvent> events = orderEventService.events(orderId)
        .timeout(Duration.ofSeconds(10));
```

Nếu event tiếp theo không đến trong 10 giây, publisher lỗi timeout. Nếu cứ mỗi 9 giây có một event, stream có thể tiếp tục lâu hơn 10 giây.

Nếu cần giới hạn tổng thời gian thu thập một danh sách cho query, hãy áp dụng timeout lên publisher đại diện cho toàn bộ việc thu thập:

```java
@QueryMapping
public Mono<List<BookView>> books() {
    return bookService.findAll()
            .collectList()
            .timeout(Duration.ofSeconds(2));
}
```

`collectList()` chỉ hoàn tất khi upstream hoàn tất; timeout trên `Mono<List<BookView>>` vì vậy giới hạn tổng thời gian chờ list. Đổi lại, list được giữ trong memory trước khi trả response. Với dữ liệu lớn, hãy dùng pagination/streaming thay vì gom một tập không giới hạn.

Với query/mutation thông thường, Spring for GraphQL mặc định chuyển giá trị `Flux` của data fetcher thành `List` trong response. Do đó, nếu muốn giới hạn tổng thời gian lấy list, hãy đặt deadline lên publisher hoàn tất toàn bộ collection như ví dụ trên. Với subscription, `Flux` được giữ như stream để phát nhiều response event.

Đối với GraphQL subscription, timeout giữa event và giới hạn tổng lifetime là hai policy khác nhau. Subscription có thể được thiết kế để tồn tại lâu dài; không áp dụng total timeout ngắn của query thông thường cho stream đó.

## 11. Timeout downstream HTTP client

Resolver thường gọi service bên ngoài. Cấu hình timeout ở HTTP client để connection hoặc response chậm không chiếm tài nguyên vô hạn.

Ví dụ với Reactor Netty và `WebClient`:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

`responseTimeout` của Reactor Netty giới hạn khoảng thời gian tối đa giữa các lần đọc dữ liệu mạng khi đang nhận response; nó là read-idle timeout, không phải tổng thời gian của toàn bộ HTTP call. Tùy loại request, còn cần xem xét connect timeout, connection pool acquire timeout và timeout của dịch vụ đích. Một timeout ở tầng HTTP client nên ngắn hơn timeout resolver để resolver còn thời gian xử lý fallback hoặc chuyển lỗi.

Nếu cần giới hạn tổng thời gian từ lúc bắt đầu kết nối đến khi nhận xong response, có thể đặt Reactor `timeout(...)` trên publisher của HTTP call. Giữ riêng hai policy: response read timeout phát hiện upstream ngừng gửi dữ liệu giữa chừng, còn operation timeout giới hạn toàn bộ lần gọi.

Không chỉ đặt `.timeout(...)` trên toàn `WebClient` call rồi bỏ qua timeout của connection pool hoặc TCP connect. Nếu connection không thể được thiết lập, request có thể chờ ở giai đoạn khác với response read.

## 12. Timeout database và connection pool

Database có thể chậm vì query plan, lock, connection pool cạn hoặc network. Hãy đặt timeout phù hợp tại driver/database layer để truy vấn có thể bị dừng ở nơi thực thi.

Với JDBC, có thể dùng query timeout trên `Statement` hoặc cơ chế tương ứng của repository/ORM. Với R2DBC, dùng các cấu hình statement/driver phù hợp với database. Timeout lấy connection từ pool cũng cần riêng biệt vì chờ connection không giống chờ câu SQL.

Ví dụ minh họa JDBC:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setQueryTimeout(1);
    // Bind parameters and execute the query.
}
```

`setQueryTimeout` nhận số giây, do đó giá trị `1` chỉ là ví dụ. Hãy xác nhận driver/database thực sự hỗ trợ việc hủy statement và chọn timeout phù hợp với SLA. Không giả định Reactor cancellation tự dừng một JDBC statement đang chạy trên thread khác.

## 13. Timeout budget và deadline propagation

Đừng đặt mọi timeout bằng cùng một con số. Hãy chia ngân sách từ dependency đến request boundary.

Ví dụ một query có ngân sách tổng 1,8 giây:

```text
Database query timeout       500 ms
Downstream HTTP timeout      700 ms
Resolver timeout             900 ms
GraphQL request timeout     1800 ms
Gateway/client timeout      2500 ms
```

Các giá trị trên chỉ minh họa. Một request có nhiều resolver song song nên request timeout không nhất thiết bằng tổng timeout của từng resolver; cần đo p95/p99 và dependency graph thực tế.

Khi request đi qua nhiều service, truyền deadline tuyệt đối hoặc remaining budget thay vì khởi tạo lại timeout đầy đủ ở mỗi hop. Nếu service A còn 400 ms, service B không nên tự chờ thêm 2 giây. Cần trừ thời gian đã tiêu thụ và giữ một phần ngân sách cho serialization, response write và network return.

Retry cũng phải nằm trong cùng deadline. Ba lần retry, mỗi lần chờ 800 ms, không phù hợp với request budget 1,5 giây. Hãy giới hạn retry count, backoff và remaining time; không retry timeout một cách vô hạn.

## 14. Cancellation và công việc thực sự dừng lại

Timeout và cancellation có liên quan nhưng không đồng nghĩa với việc mọi công việc đã dừng ngay lập tức.

- Với reactive publisher, cancellation được truyền upstream; operator và client có thể giải phóng subscription/tài nguyên nếu implementation hỗ trợ.
- Với `CompletableFuture`, hoàn tất future bằng timeout không bảo đảm tác vụ nền hoặc I/O bên dưới bị hủy.
- Với blocking JDBC hoặc SDK đồng bộ, thread có thể tiếp tục chạy nếu driver không hỗ trợ cancel hoặc code không kiểm tra interruption.
- Với mutation, side effect có thể đã commit trước khi response timeout xảy ra.

Hãy ưu tiên API có timeout/cancel native. Với blocking call, dùng driver query timeout, socket timeout hoặc cơ chế cancel cụ thể. Đừng coi việc client đóng connection là bằng chứng server đã dừng truy vấn.

Ví dụ kiểm tra reactive cleanup:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Mono<BookView> source = Mono.<BookView>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source.timeout(Duration.ofMillis(50)))
        .expectError(TimeoutException.class)
        .verify();

assertThat(cancelled).isTrue();
```

Test này xác nhận operator timeout hủy upstream subscription. Nó không chứng minh một JDBC query hoặc một HTTP server bên ngoài luôn dừng được; cần integration test với client/driver thực tế.

## 15. Timeout trong Mutation và idempotency

Timeout của mutation có rủi ro đặc biệt. Server có thể đã ghi dữ liệu thành công nhưng response không đến được client trước deadline. Client nhìn thấy timeout và không biết mutation đã commit hay chưa.

Nếu client retry mutation ngay, cùng một hành động có thể được thực hiện hai lần. Các mutation tạo đơn hàng, thanh toán, gửi email hoặc khởi tạo job nên có cơ chế idempotency key hoặc command ID duy nhất.

Ví dụ input:

```graphql
input CreateOrderInput {
    idempotencyKey: ID!
    productId: ID!
    quantity: Int!
}
```

Server lưu kết quả theo idempotency key và trả lại kết quả đã tạo khi nhận lại cùng key. Timeout không được xem là bằng chứng mutation thất bại; client nên tra cứu trạng thái hoặc retry an toàn theo contract của API.

Không dùng timeout để tự động rollback một side effect đã commit. Transaction timeout, database cancellation và business compensation là những cơ chế riêng cần được thiết kế phù hợp.

## 16. Timeout cho Subscription và streaming transport

`TimeoutWebGraphQlInterceptor` chỉ áp dụng timeout cho giai đoạn request cho tới khi response stream được thiết lập. Với subscription, sau khi stream đã bắt đầu, interceptor không giới hạn toàn bộ thời gian sống của stream.

Subscription thường cần policy khác:

- Timeout thiết lập subscription ban đầu.
- Idle timeout nếu không có event trong một khoảng thời gian.
- Heartbeat/keepalive để phát hiện connection chết.
- Giới hạn tuổi thọ hoặc số event nếu nghiệp vụ yêu cầu.
- Timeout riêng cho WebSocket/SSE transport handler.
- Cleanup khi client gửi complete/cancel hoặc connection đóng.

Spring for GraphQL có các cấu hình timeout riêng trên handler như `GraphQlWebSocketHandler` và `GraphQlSseHandler`. Hãy kiểm tra transport được dùng và phiên bản framework. Không áp dụng một HTTP request deadline ngắn cho subscription stream vốn được thiết kế tồn tại lâu.

## 17. GraphQL Java Instrumentation và timeout

GraphQL Java `Instrumentation` cung cấp hook để quan sát các giai đoạn parse, validation, execution và data fetcher. Nó hữu ích để đo thời gian tổng request hoặc thời gian từng field, ghi metric và thực hiện một số giới hạn trước khi execution bắt đầu.

Instrumentation đo thời gian không tự động hủy công việc đã chạy. Việc bọc `CompletableFuture` bằng `orTimeout(...)` có thể làm future hoàn tất bằng exception nhưng không bảo đảm database, HTTP call hoặc task nền bên dưới dừng lại. Nếu cần request timeout cho web transport, ưu tiên `TimeoutWebGraphQlInterceptor`; nếu cần giới hạn một dependency, dùng timeout/cancellation native của publisher hoặc client.

Các giới hạn query depth/complexity và pagination nên được kiểm tra trước hoặc trong quá trình lập kế hoạch execution. Chúng ngăn query tốn kém ngay từ đầu; timeout chỉ kết thúc công việc sau khi deadline đã bị tiêu thụ.

## 18. Xử lý timeout và partial data

Nếu một resolver timeout trong lúc các resolver khác vẫn hoàn tất, GraphQL execution có thể trả partial data và `errors`. Kết quả cụ thể phụ thuộc field nullability.

Ví dụ schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    recommendations: [Book!]
}
```

Nếu `recommendations` timeout và field này nullable, `book.id` và `book.title` vẫn có thể được trả về, trong khi `recommendations` là null và `errors` có path tới field bị timeout.

Nếu field được khai báo non-null, lỗi có thể lan null lên parent gần nhất có thể nhận null. Thiết kế nullability nên phản ánh khả năng một field phụ thuộc service chậm hoặc không sẵn sàng.

Không biến mọi timeout thành `Mono.empty()` chỉ để loại bỏ error. Cách đó có thể khiến client nhầm dữ liệu không tồn tại với dependency timeout. Hãy dùng error code riêng như `RECOMMENDATIONS_TIMEOUT` nếu client cần phân biệt.

## 19. Kiểm thử request timeout qua HTTP

Để kiểm tra `TimeoutWebGraphQlInterceptor`, cần đi qua web handler/HTTP transport. Một test chỉ gọi method resolver hoặc `ExecutionGraphQlService` trực tiếp sẽ không kích hoạt web interceptor.

Trong test application, cấu hình timeout ngắn và một resolver trả publisher không hoàn tất:

```java
@TestConfiguration
static class TimeoutTestConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofMillis(100));
    }
}
```

Sau đó gửi request bằng `WebTestClient` hoặc `MockMvc` tới endpoint `/graphql`:

```java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ slowField }"))
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.REQUEST_TIMEOUT);
```

Test giả định `slowField` dùng một publisher không phát kết quả trong thời gian timeout và ứng dụng dùng status mặc định. Nếu cấu hình status tùy chỉnh, assertion phải đổi theo status đã chọn.

Nên kiểm tra thêm resolver nhận cancellation và không tiếp tục chiếm tài nguyên sau timeout. Để tránh test flaky, dùng timeout đủ lớn so với scheduler/test environment nhưng vẫn ngắn; không dùng `Thread.sleep()` để tạo sự chậm giả nếu có thể dùng `Mono.never()` hoặc publisher điều khiển được.

## 20. Kiểm thử resolver timeout và downstream timeout

Resolver-level timeout có thể được kiểm tra bằng `StepVerifier`:

```java
import java.util.concurrent.TimeoutException;

@Test
void timesOutSlowBookLookup() {
    StepVerifier.create(
            Mono.<BookView>never()
                    .timeout(Duration.ofMillis(50)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
}
```

Test này kiểm tra Reactor operator. Để kiểm tra exception mapping, thực thi GraphQL operation bằng `GraphQlTester` và assert `errors[].extensions.code` cùng path. Để kiểm tra timeout HTTP client hoặc database driver, cần test adapter/driver thật hoặc test server mô phỏng dependency chậm.

Các test nên bao gồm:

1. Request hoàn tất trước deadline và trả dữ liệu bình thường.
2. Request vượt deadline và trả HTTP status timeout dự kiến.
3. Reactive publisher nhận cancellation khi timeout.
4. Một resolver timeout nhưng field độc lập vẫn trả partial data.
5. Timeout error có code/path đúng khi được ánh xạ thành GraphQL error.
6. Downstream HTTP call bị hủy hoặc kết thúc theo client timeout.
7. Database query timeout giải phóng statement/connection theo driver behavior.
8. Subscription stream không bị cắt sau khi đã thiết lập chỉ vì request setup timeout.
9. Mutation timeout có thể được retry an toàn bằng idempotency key.
10. Gateway/client timeout dài hơn server request timeout để nhận response timeout từ server.

## 21. Quan sát timeout trong production

Theo dõi timeout ở từng lớp để xác định bottleneck:

- Số GraphQL request timeout và tỷ lệ trên tổng request.
- Thời gian execution p50, p95 và p99 theo operation/field.
- Resolver timeout theo field path.
- Downstream HTTP timeout theo service và endpoint.
- Database query timeout, connection acquire timeout và pool saturation.
- Số cancellation được phát và số công việc downstream thực sự dừng.
- Retry count, fallback count và request budget còn lại.

Gắn `executionId` hoặc trace ID để liên kết log giữa GraphQL request và dependency calls. Tránh dùng query variables nhạy cảm, user ID hoặc resource ID làm metric label có cardinality cao.

Phân biệt timeout do server deadline với client disconnect, gateway timeout và dependency timeout. Nếu chỉ ghi một metric chung `request_failed`, khó xác định lớp nào cần điều chỉnh.

## 22. Những lỗi thường gặp

- **Chỉ đặt timeout ở client:** server có thể tiếp tục xử lý sau khi client đã ngừng chờ.
- **Chỉ đặt request timeout:** database hoặc HTTP call có thể không dừng nếu không hỗ trợ cancellation.
- **Nhầm request timeout với resolver timeout:** một cái giới hạn toàn request, cái kia giới hạn một publisher/field.
- **Cho rằng `CompletableFuture.orTimeout` hủy task bên dưới:** future timeout không bảo đảm I/O thực sự dừng.
- **Dùng `Flux.timeout` làm total duration timeout:** nó thường đo thời gian chờ giữa các tín hiệu.
- **Áp dụng request timeout ngắn cho subscription lifetime:** interceptor chỉ giới hạn đến lúc stream được thiết lập.
- **Không để client/gateway chờ lâu hơn server:** gateway có thể đóng connection trước khi server gửi status timeout.
- **Retry vượt deadline:** mỗi lần retry lại bắt đầu timeout mới và kéo dài request ngoài ngân sách.
- **Nuốt timeout thành null:** client không phân biệt được dữ liệu vắng mặt và dependency chậm.
- **Retry mutation không có idempotency:** side effect có thể được thực hiện hai lần.
- **Dùng instrumentation chỉ đo thời gian rồi kỳ vọng nó tự cancel:** quan sát không đồng nghĩa với timeout enforcement.
- **Không test cancellation:** request kết thúc nhưng tài nguyên downstream có thể vẫn bị giữ.

## 23. Quy trình thiết kế timeout execution

Khi triển khai timeout cho Spring for GraphQL, hãy thực hiện:

1. Đo latency thực tế và xác định SLA cho query/mutation.
2. Chọn request deadline ở web boundary bằng `TimeoutWebGraphQlInterceptor` nếu dùng Spring GraphQL 1.4+.
3. Chọn status timeout mặc định `408` hoặc status tùy chỉnh theo API contract.
4. Đặt timeout riêng cho resolver chậm và downstream client/database.
5. Với `Flux`, phân biệt idle timeout và tổng thời gian thu thập.
6. Truyền remaining deadline qua các service và không reset budget khi retry.
7. Bảo đảm reactive cancellation và driver/client timeout thực sự giải phóng công việc.
8. Ánh xạ field timeout thành GraphQL error có code ổn định khi cần partial data.
9. Thiết kế idempotency cho mutation có thể timeout sau khi commit.
10. Cấu hình timeout riêng cho WebSocket/SSE subscription transport.
11. Kiểm thử request, resolver, downstream, cancellation và transport ở đúng tầng.
12. Theo dõi timeout rate, latency, dependency và cancellation trong production.

Timeout execution trong Spring for GraphQL cần được thiết kế theo nhiều lớp. `TimeoutWebGraphQlInterceptor` giới hạn thời gian tạo response cho web request và phát cancellation khi hết hạn; timeout ở resolver và database/HTTP client giới hạn công việc cụ thể. Cần bảo đảm cancellation được hỗ trợ ở downstream, giữ một deadline chung qua các lần gọi, xử lý partial data đúng schema và thiết kế mutation có thể retry an toàn. Kiểm thử từng ranh giới và theo dõi timeout theo lớp sẽ giúp bảo vệ tài nguyên mà vẫn giữ hợp đồng GraphQL rõ ràng.

## Tài liệu tham khảo

- [Spring for GraphQL — Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html#graphql-request-timeout)
- [Spring for GraphQL 1.4.x — TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [Project Reactor — Handling Errors and Timeout](https://projectreactor.io/docs/core/release/reference/)
- [Reactor Netty — HTTP Client Timeout](https://projectreactor.io/docs/netty/release/reference/http-client.html#_httpclient_timeout)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
