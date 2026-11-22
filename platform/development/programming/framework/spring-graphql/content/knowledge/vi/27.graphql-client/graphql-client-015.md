# Client interceptor

Trong Spring for GraphQL, `GraphQlClientInterceptor` là điểm mở rộng phía client để quan sát và can thiệp vào quá trình gửi GraphQL request, nhận response và tiêu thụ subscription stream. Nó hữu ích khi ứng dụng cần dùng chung các hành vi như ghi log, đo thời gian, gắn correlation ID nội bộ, theo dõi lỗi hoặc thực hiện xử lý bổ sung quanh request.

Interceptor tham gia execution chain của `GraphQlClient`. Nó nhận `ClientGraphQlRequest`, chuyển tiếp request bằng `chain.next(request)`, sau đó có thể quan sát response hoặc lỗi. Với subscription, interceptor làm việc với `Flux` và có thể theo dõi từng event cùng tín hiệu kết thúc stream.

Cần phân biệt interceptor GraphQL dùng chung với cấu hình riêng của transport. Header HTTP được cấu hình qua `HttpGraphQlClient` hoặc `WebClient`; payload `connection_init` của WebSocket được tạo bằng `WebSocketGraphQlClientInterceptor`. `GraphQlClientInterceptor` không phải nơi tùy ý sửa HTTP header hay WebSocket handshake.

## 1. Interceptor nằm ở đâu trong GraphQlClient?

Spring for GraphQL cung cấp workflow client dùng chung cho nhiều transport:

- `HttpGraphQlClient` gửi query và mutation qua HTTP theo non-blocking contract.
- `HttpSyncGraphQlClient` gửi request HTTP theo blocking contract.
- `WebSocketGraphQlClient` dùng một WebSocket connection để thực hiện request và subscription.
- `RSocketGraphQlClient` gửi request qua RSocket session.

Các client này có builder riêng nhưng cùng hỗ trợ cấu hình interception phù hợp với execution model. Vì vậy, một `GraphQlClientInterceptor` non-blocking có thể được tái sử dụng giữa các transport non-blocking mà không cần viết lại logic đo thời gian hoặc ghi log theo từng giao thức.

~~~mermaid
flowchart TD
    A[Ứng dụng gọi GraphQlClient] --> B[GraphQL RequestSpec]
    B --> C[Client interceptor 1]
    C --> D[Client interceptor 2]
    D --> E[Transport: HTTP / WebSocket / RSocket]
    E --> F[GraphQL server]
    F --> G[ClientGraphQlResponse]
    G --> D
    D --> C
    C --> H[Ứng dụng đọc response]
~~~

Interceptor là một phần của client-side chain. Nó không chạy trên server và không thay thế `WebGraphQlInterceptor`, vốn xử lý request ở phía server.

## 2. Hai loại interceptor theo execution model

Spring for GraphQL có hai interface chính:

| Interface | Execution model | Dùng với |
| --- | --- | --- |
| `GraphQlClientInterceptor` | Non-blocking, Reactor | `HttpGraphQlClient`, `WebSocketGraphQlClient`, `RSocketGraphQlClient` |
| `SyncGraphQlClientInterceptor` | Blocking | `HttpSyncGraphQlClient` |

`GraphQlClientInterceptor` có hai phương thức:

- `intercept(ClientGraphQlRequest, Chain)` xử lý request đơn, thường là query hoặc mutation, và trả về `Mono<ClientGraphQlResponse>`.
- `interceptSubscription(ClientGraphQlRequest, SubscriptionChain)` xử lý subscription và trả về `Flux<ClientGraphQlResponse>`.

Cả hai phương thức có implementation mặc định chuyển tiếp request. Có thể override phương thức cần xử lý; nếu muốn áp dụng cùng logic cho cả query/mutation và subscription, hãy override cả hai.

`SyncGraphQlClientInterceptor` chỉ có một phương thức `intercept` đồng bộ, nhận request và trả về response trực tiếp. Không dùng `GraphQlClientInterceptor` cho blocking client hoặc gọi `block()` bên trong interceptor non-blocking.

## 3. Cấu trúc của một non-blocking interceptor

Ví dụ interceptor ghi log operation name và thời gian thực thi:

~~~java
package com.example.graphql.client;

import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ClientMetricsInterceptor implements GraphQlClientInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(ClientMetricsInterceptor.class);

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();
        String operationName = request.getOperationName();

        return chain.next(request)
            .doOnNext(response -> {
                long elapsedNanos = System.nanoTime() - startedAt;
                log.debug(
                    "GraphQL operation={} valid={} elapsedNanos={}",
                    operationName,
                    response.isValid(),
                    elapsedNanos
                );
            })
            .doOnError(error ->
                log.warn("GraphQL operation={} failed", operationName, error)
            );
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return Flux.defer(() -> {
            long startedAt = System.nanoTime();
            String operationName = request.getOperationName();

            return chain.next(request)
                .doOnNext(response ->
                    log.debug(
                        "GraphQL subscription operation={} valid={}",
                        operationName,
                        response.isValid()
                    )
                )
                .doOnError(error ->
                    log.warn(
                        "GraphQL subscription operation={} failed",
                        operationName,
                        error
                    )
                )
                .doFinally(signalType -> {
                    long elapsedNanos = System.nanoTime() - startedAt;
                    log.debug(
                        "GraphQL subscription operation={} terminated={} elapsedNanos={}",
                        operationName,
                        signalType,
                        elapsedNanos
                    );
                });
        });
    }
}
~~~

`chain.next(request)` chuyển request sang các interceptor tiếp theo rồi tới transport. Response đi ngược lại qua reactive chain, nên có thể dùng `doOnNext` để ghi metric và `doOnError` để quan sát lỗi transport hoặc lỗi phát sinh trong chain.

Đối với subscription, `chain.next(request)` trả về một `Flux`. `doOnNext` có thể chạy nhiều lần, một lần cho mỗi GraphQL response event. `doFinally` nhận tín hiệu kết thúc như complete, error hoặc cancel. Bọc logic khởi tạo timer trong `Flux.defer` để mỗi lần subscribe có thời điểm bắt đầu riêng.

Không gọi `subscribe()` hoặc `block()` bên trong interceptor. Hãy trả publisher để caller điều khiển subscription, backpressure và cancellation.

## 4. Đăng ký interceptor trên builder

Ví dụ dùng `HttpGraphQlClient`:

~~~java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://catalog.example.com/graphql")
    .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
    .interceptor(new ClientMetricsInterceptor())
    .build();
~~~

Mọi request được gửi qua instance `graphQlClient` sẽ đi qua interceptor đã đăng ký.

Có thể đăng ký nhiều interceptor trên builder. Nên chia trách nhiệm theo mục đích, ví dụ một interceptor cho metric, một interceptor cho audit metadata và một interceptor cho chuẩn hóa lỗi. Giữ mỗi interceptor nhỏ để thứ tự và tác động của chúng dễ kiểm tra.

Nếu cần tùy chỉnh toàn bộ danh sách, builder có API `interceptors(...)`. Khi nhiều interceptor cùng thay đổi hoặc quan sát một request, hãy xác định thứ tự mong muốn và viết test cho chain thay vì dựa vào giả định về thứ tự.

## 5. Chuyển tiếp request và short-circuit

Trong trường hợp thông thường, interceptor nên gọi `chain.next(request)` đúng một lần rồi xử lý kết quả:

~~~java
@Override
public Mono<ClientGraphQlResponse> intercept(
        ClientGraphQlRequest request,
        Chain chain) {

    return chain.next(request)
        .doOnNext(response -> log.debug("Response received"));
}
~~~

Có thể không gọi chain nếu interceptor chủ động short-circuit request và tự tạo một response thay thế, nhưng đây là hành vi đặc biệt. Nếu bỏ qua chain mà không trả kết quả phù hợp, request sẽ không tới server.

Không gọi `chain.next(request)` hai lần để "thử lại" request. Với mutation, việc gửi lại có thể thực hiện side effect hai lần. Retry phải được thiết kế riêng dựa trên loại lỗi, tính idempotent của operation và hợp đồng của server.

Interceptor cũng không nên âm thầm nuốt exception rồi trả response giả. Nếu không có fallback có chủ đích, hãy để lỗi truyền tới caller.

## 6. Đọc thông tin của ClientGraphQlRequest

`ClientGraphQlRequest` cung cấp thông tin của GraphQL request:

- `getDocument()`: GraphQL document.
- `getOperationName()`: tên operation nếu có.
- `getVariables()`: map variables.
- `getExtensions()`: protocol extensions.
- `getAttributes()`: thuộc tính chỉ dùng nội bộ trong client-side interceptor chain.

Có thể dùng operation name và attribute để gắn metric hoặc trace mà không cần parse lại toàn bộ GraphQL document.

Ví dụ gắn correlation ID ở nơi tạo request:

~~~java
Mono<BookView> result = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .attribute("correlationId", correlationId)
    .retrieve("book")
    .toEntity(BookView.class);
~~~

Interceptor đọc attribute:

~~~java
Object correlationId = request.getAttributes().get("correlationId");
~~~

Request attribute chỉ tồn tại trong client process và có thể được các interceptor đọc. Nó không tự được serialize hoặc gửi đến GraphQL server. Nếu cần gửi dữ liệu qua giao thức, dùng GraphQL variables, protocol extensions hoặc transport metadata phù hợp.

Không đặt access token, mật khẩu hoặc dữ liệu bí mật vào attribute nếu interceptor có khả năng ghi toàn bộ attributes ra log. Hãy chọn rõ những trường được phép quan sát.

## 7. Phân biệt attributes, extensions và variables

Ba khái niệm này có mục đích khác nhau:

| Thành phần | Nơi sử dụng | Có được gửi tới server? | Ví dụ |
| --- | --- | --- | --- |
| Variables | Input của GraphQL operation | Có | `id`, `filter`, `page` |
| Extensions | Metadata mở rộng của GraphQL protocol | Có, theo transport/protocol | tracing metadata hoặc persisted query metadata nếu hai bên hỗ trợ |
| Client attributes | Xử lý nội bộ trong client interceptor chain | Không | correlation ID nội bộ, nhãn metric, thông tin audit cục bộ |

Ví dụ protocol extension:

~~~java
graphQlClient.document("""
        query {
            books {
                id
                title
            }
        }
        """)
    .extension("clientMetadata", Map.of("source", "catalog-ui"))
    .retrieve("books")
    .toEntityList(BookView.class);
~~~

Server chỉ sử dụng extension nếu có logic hỗ trợ tương ứng. Không dùng extension để thay thế argument hoặc variable mà schema cần kiểm tra và định kiểu.

## 8. Quan sát GraphQL errors trong response

Một GraphQL response có thể chứa cả data và errors. Điều này khác với lỗi transport, nơi publisher có thể kết thúc bằng exception.

Interceptor có thể quan sát response trước khi caller dùng `retrieve`:

~~~java
@Override
public Mono<ClientGraphQlResponse> intercept(
        ClientGraphQlRequest request,
        Chain chain) {

    return chain.next(request)
        .doOnNext(response -> {
            if (!response.isValid()) {
                log.warn(
                    "GraphQL response contains errors; operation={}, errors={}",
                    request.getOperationName(),
                    response.getErrors().size()
                );
            }
        });
}
~~~

`response.isValid()` và `response.getErrors()` cho phép nhận biết GraphQL response có lỗi. GraphQL có thể trả partial data cùng errors; không nên mặc định mọi response có errors đều không có dữ liệu hữu ích.

Nếu caller cần kiểm soát chi tiết, dùng `execute()` và đọc `ClientGraphQlResponse`. `retrieve(path)` là shortcut để giải mã một field path; nó có thể phát sinh `FieldAccessException` khi field không có giá trị hoặc có lỗi liên quan. Lỗi decode kiểu dữ liệu có thể được biểu diễn bằng `GraphQlClientException`.

Không tự chuyển mọi GraphQL error thành reactive exception trong interceptor nếu ứng dụng cần hỗ trợ partial data. Hãy để chính sách lỗi ở client service hoặc caller quyết định dựa trên từng use case.

## 9. Xử lý lỗi transport và retry

Cần phân biệt:

- GraphQL errors là lỗi được trả trong response theo GraphQL protocol.
- Lỗi kết nối, timeout hoặc lỗi codec có thể được truyền dưới dạng `GraphQlTransportException` hoặc exception cụ thể của transport.
- Lỗi khi giải mã field có thể xuất hiện sau đó khi caller dùng `retrieve`.

Interceptor có thể ghi nhận lỗi được truyền qua chain:

~~~java
return chain.next(request)
    .doOnError(error ->
        log.warn(
            "GraphQL transport failed for operation={}",
            request.getOperationName(),
            error
        )
    );
~~~

Retry có thể đặt trong interceptor hoặc ở caller, nhưng phải xem operation có an toàn để gửi lại hay không. Query thường không tạo side effect, trong khi mutation có thể đã được server xử lý trước khi kết nối bị đứt. Nếu retry mutation, cần idempotency key hoặc một cơ chế xác minh trạng thái command.

Không retry các lỗi GraphQL validation, authorization hoặc business error như thể chúng là lỗi mạng. Retry vô điều kiện có thể tạo tải lặp và làm khó chẩn đoán.

## 10. Xử lý subscription bằng interceptSubscription

`interceptSubscription` là điểm mở rộng riêng cho request trả về nhiều response. Một subscription có thể phát hàng trăm event và tồn tại lâu, vì vậy interceptor nên giữ nguyên reactive stream.

Ví dụ đếm event và ghi nhận thời điểm kết thúc:

~~~java
@Override
public Flux<ClientGraphQlResponse> interceptSubscription(
        ClientGraphQlRequest request,
        SubscriptionChain chain) {

    return Flux.defer(() -> {
        AtomicLong eventCount = new AtomicLong();

        return chain.next(request)
            .doOnNext(response -> eventCount.incrementAndGet())
            .doFinally(signalType ->
                log.info(
                    "Subscription operation={} events={} signal={}",
                    request.getOperationName(),
                    eventCount.get(),
                    signalType
                )
            );
    });
}
~~~

`doFinally` được gọi khi stream complete, error hoặc bị cancel. Khi client hủy subscription, cancellation phải tiếp tục truyền qua chain tới transport. Tránh dùng `collectList()` để chờ toàn bộ stream vì subscription có thể không bao giờ hoàn tất tự nhiên.

Nếu interceptor cần buffer hoặc biến đổi event, hãy đặt giới hạn bộ nhớ và bảo đảm không phá backpressure. Với log/metric, operator dạng side effect thường phù hợp hơn việc giữ toàn bộ response.

## 11. WebSocketGraphQlClientInterceptor

WebSocket có thêm các thông điệp quản lý connection ngoài GraphQL operation, chẳng hạn `connection_init` và `connection_ack`. Khi cần can thiệp vào các thông điệp này, dùng `WebSocketGraphQlClientInterceptor`.

Interface này mở rộng `GraphQlClientInterceptor` và bổ sung hai callback:

- `connectionInitPayload()` tạo payload gửi trong thông điệp `connection_init`.
- `handleConnectionAck(payload)` xử lý payload của `connection_ack` nhận từ server.

Ví dụ gửi bearer token trong payload khởi tạo:

~~~java
package com.example.graphql.client;

import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import reactor.core.publisher.Mono;

public class WebSocketAuthInterceptor
        implements WebSocketGraphQlClientInterceptor {

    private final TokenProvider tokenProvider;

    public WebSocketAuthInterceptor(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return tokenProvider.currentAccessToken()
            .<Object>map(token -> Map.of(
                "Authorization",
                "Bearer " + token
            ));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }
}
~~~

`TokenProvider` là abstraction của ứng dụng trả về `Mono<String>` chứa access token hiện tại. Server phải có cơ chế xác thực payload `connection_init` tương ứng, ví dụ interceptor xác thực WebSocket của Spring for GraphQL.

Đăng ký interceptor:

~~~java
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

WebSocketGraphQlClient graphQlClient =
    WebSocketGraphQlClient.builder(
            "wss://catalog.example.com/graphql",
            new ReactorNettyWebSocketClient()
        )
        .interceptor(new WebSocketAuthInterceptor(tokenProvider))
        .interceptor(new ClientMetricsInterceptor())
        .build();
~~~

Chỉ có thể có tối đa một interceptor thuộc loại `WebSocketGraphQlClientInterceptor` trong chain. Các interceptor `GraphQlClientInterceptor` thông thường vẫn có thể đăng ký bổ sung để quan sát từng GraphQL request và subscription.

WebSocket client giữ một connection dùng chung cho nhiều operation. Payload khởi tạo gắn với connection; nếu token thay đổi, việc đổi token trong provider không tự cập nhật danh tính của connection đã mở. Ứng dụng cần đóng/reconnect connection theo chính sách credential của mình.

## 12. Cấu hình HTTP header không thuộc GraphQlClientInterceptor

Một nhầm lẫn thường gặp là cố thêm header HTTP bằng `GraphQlClientInterceptor`. Interface này nhận GraphQL request abstraction, không cung cấp API sửa header của HTTP transport.

Với `HttpGraphQlClient`, cấu hình header qua builder:

~~~java
HttpGraphQlClient graphQlClient =
    HttpGraphQlClient.builder(webClient)
        .headers(headers ->
            headers.setBearerAuth(accessToken)
        )
        .interceptor(new ClientMetricsInterceptor())
        .build();
~~~

Nếu token thay đổi theo từng request, cấu hình một header tĩnh khi build client có thể không phù hợp. Khi đó, dùng `WebClient` filter hoặc một cơ chế credential provider ở transport layer để lấy token cho từng lần gửi HTTP.

Với `WebSocketGraphQlClient`, header handshake và payload `connection_init` là hai cơ chế khác nhau. Trong browser, JavaScript WebSocket API không cho phép tùy ý đặt header Authorization; payload `connection_init` thường được dùng để gửi credential theo giao thức GraphQL over WebSocket.

Với RSocket, credential được cấu hình theo RSocket setup/metadata hoặc cơ chế bảo mật RSocket. Interceptor GraphQL dùng chung vẫn có thể quan sát request/response, nhưng không thay thế cấu hình transport metadata.

## 13. Interceptor cho blocking HttpSyncGraphQlClient

Nếu ứng dụng dùng blocking client, implement `SyncGraphQlClientInterceptor`:

~~~java
package com.example.graphql.client;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.SyncGraphQlClientInterceptor;

public class SyncAuditInterceptor implements SyncGraphQlClientInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SyncAuditInterceptor.class);

    @Override
    public ClientGraphQlResponse intercept(
            ClientGraphQlRequest request,
            Chain chain) {

        long startedAt = System.nanoTime();

        try {
            ClientGraphQlResponse response = chain.next(request);

            log.debug(
                "GraphQL operation={} valid={} elapsedNanos={}",
                request.getOperationName(),
                response.isValid(),
                System.nanoTime() - startedAt
            );

            return response;
        } catch (RuntimeException exception) {
            log.warn(
                "GraphQL operation={} failed",
                request.getOperationName(),
                exception
            );
            throw exception;
        }
    }
}
~~~

Đăng ký với `HttpSyncGraphQlClient`:

~~~java
RestClient restClient = RestClient.builder()
    .baseUrl("https://catalog.example.com/graphql")
    .build();

HttpSyncGraphQlClient graphQlClient =
    HttpSyncGraphQlClient.builder(restClient)
        .interceptor(new SyncAuditInterceptor())
        .build();
~~~

Interceptor blocking gọi `chain.next(request)` và nhận response đồng bộ. Không trả `Mono` hoặc `Flux` trong interface này. Nếu ứng dụng dùng `HttpGraphQlClient` non-blocking, hãy dùng `GraphQlClientInterceptor`.

## 14. Phân biệt client interceptor và server interceptor

Tên hai loại interceptor khá giống nhau nhưng chúng chạy ở hai phía khác nhau:

| Thành phần | Chạy ở đâu? | Mục đích |
| --- | --- | --- |
| `GraphQlClientInterceptor` | Ứng dụng gọi GraphQL | Quan sát request/response từ góc nhìn client |
| `SyncGraphQlClientInterceptor` | Blocking GraphQL client | Interception đồng bộ cho client blocking |
| `WebSocketGraphQlClientInterceptor` | WebSocket client | Bổ sung callback khởi tạo và acknowledge connection |
| `WebGraphQlInterceptor` | GraphQL server qua HTTP/WebSocket | Kiểm tra request transport, sửa ExecutionInput/ExecutionResult |
| `WebSocketGraphQlInterceptor` | GraphQL server qua WebSocket | Xử lý connection lifecycle và cancellation phía server |
| `RSocketQlInterceptor` | GraphQL server qua RSocket | Interception request/response RSocket ở server |

Ví dụ, interceptor client có thể ghi log operation name trước khi gửi request và thời gian nhận response. Interceptor server có thể đọc header HTTP, đưa principal vào GraphQL context hoặc thêm header response. Dùng đúng extension point giúp tránh phụ thuộc nhầm vào thông tin mà phía đó không có.

## 15. Bảo mật và dữ liệu nhạy cảm trong interceptor

Interceptor thường được dùng chung cho nhiều request, vì vậy cần cẩn trọng với log và state:

- Không log toàn bộ GraphQL variables nếu có mật khẩu, token, thông tin cá nhân hoặc dữ liệu nhạy cảm.
- Không log bearer token, cookie hoặc nội dung payload xác thực.
- Chỉ ghi operation name, correlation ID, thời gian, trạng thái response và số lượng lỗi nếu đủ cho mục đích giám sát.
- Không lưu dữ liệu request của một người dùng vào field mutable của interceptor singleton.
- Không chia sẻ token theo người dùng qua một client instance dùng chung nếu token có thể thay đổi theo caller.
- Không biến request attribute thành dữ liệu truyền tới server; attributes chỉ có phạm vi client.

Nếu interceptor cần giữ trạng thái cho một request, hãy dùng biến cục bộ bên trong phương thức hoặc Reactor context. Tránh dùng một biến instance như `currentRequestId` vì nhiều request có thể chạy đồng thời trên cùng client.

## 16. Kiểm thử interceptor

Có thể kiểm thử interceptor riêng bằng cách mock request, response và chain. Ví dụ với Mockito:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ClientMetricsInterceptorTest {

    @Test
    void delegatesRequestAndReturnsResponse() {
        ClientGraphQlRequest request = mock(ClientGraphQlRequest.class);
        ClientGraphQlResponse response = mock(ClientGraphQlResponse.class);
        GraphQlClientInterceptor.Chain chain =
            mock(GraphQlClientInterceptor.Chain.class);

        when(chain.next(request)).thenReturn(Mono.just(response));

        ClientMetricsInterceptor interceptor =
            new ClientMetricsInterceptor();

        StepVerifier.create(interceptor.intercept(request, chain))
            .expectNext(response)
            .verifyComplete();

        verify(chain).next(request);
    }
}
~~~

Test này xác minh interceptor chuyển tiếp request và không làm mất response. Với interceptor có logic phân loại lỗi, thêm test response có errors, lỗi transport và exception từ chain.

Với subscription interceptor, dùng `Flux` giả lập nhiều response và xác minh tất cả event được chuyển tiếp. Thêm test cancellation để bảo đảm interceptor không giữ stream sau khi subscriber hủy.

Integration test có thể dùng HTTP mock server để kiểm tra header do transport builder cấu hình, hoặc WebSocket server test để kiểm tra payload `connection_init`. Test interceptor GraphQL không thay thế test transport.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Interceptor không chạy | Chưa đăng ký vào builder của client đang sử dụng | Kiểm tra đúng client instance và builder |
| Dùng GraphQlClientInterceptor với blocking client | Nhầm execution model | Dùng SyncGraphQlClientInterceptor |
| Subscription không được quan sát | Chỉ override intercept, không override interceptSubscription | Implement cả hai phương thức khi cần |
| Request bị gửi hai lần | Gọi chain.next nhiều lần hoặc retry mutation không an toàn | Chỉ delegate một lần; thiết kế retry theo idempotency |
| HTTP Authorization header không xuất hiện | Cố thêm header trong GraphQlClientInterceptor | Cấu hình WebClient/HttpGraphQlClient builder |
| WebSocket connection thiếu token | Chỉ cấu hình HTTP header nhưng server đọc connection_init payload | Dùng WebSocketGraphQlClientInterceptor hoặc handshake auth phù hợp |
| WebSocket auth interceptor bị xung đột | Đăng ký nhiều WebSocketGraphQlClientInterceptor | Chỉ đăng ký một interceptor loại này |
| Correlation ID không tới server | Dùng RequestSpec attribute và nghĩ nó được serialize | Dùng protocol extension, variable hoặc transport metadata |
| GraphQL errors bị coi là lỗi kết nối | Không phân biệt response errors và transport exception | Kiểm tra ClientGraphQlResponse trước khi xử lý decode |
| Subscription không kết thúc | Buffer toàn bộ stream hoặc chặn cancellation | Giữ Flux, backpressure và cancellation propagation |
| Log lộ dữ liệu | Ghi toàn bộ variables hoặc headers | Chỉ log metadata đã cho phép |

## 18. Checklist trước khi triển khai

- Client đang dùng blocking hay non-blocking execution model?
- Đã chọn đúng `SyncGraphQlClientInterceptor` hoặc `GraphQlClientInterceptor`?
- Với non-blocking client, cả request đơn và subscription có được xử lý nếu cần?
- Interceptor có gọi `chain.next(request)` đúng cách và giữ nguyên reactive flow?
- Các interceptor đã được đăng ký trên đúng builder/client instance?
- Request attributes có được hiểu đúng là dữ liệu nội bộ client?
- HTTP header, WebSocket connection init và RSocket metadata có được cấu hình ở transport tương ứng?
- GraphQL errors có được phân biệt với transport/decode exception?
- Retry mutation có idempotency hoặc điều kiện an toàn?
- Subscription có giữ backpressure và truyền cancellation?
- Không có state mutable dùng chung gây lẫn request đồng thời?
- Log không chứa token, cookie, variables hoặc dữ liệu nhạy cảm?
- Unit test và integration test đã kiểm tra chain, transport và cancellation?

`GraphQlClientInterceptor` là điểm mở rộng để chuẩn hóa xử lý quanh request và response ở phía client. Dùng `GraphQlClientInterceptor` cho non-blocking client, `SyncGraphQlClientInterceptor` cho blocking client và `WebSocketGraphQlClientInterceptor` khi cần xử lý connection initialization/acknowledgement. Giữ nguyên reactive chain, phân biệt GraphQL errors với transport failures và cấu hình header/metadata ở đúng transport layer sẽ giúp client có logging, tracing, authentication và xử lý lỗi nhất quán mà không làm rối code gọi GraphQL.

## Tài liệu tham khảo

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [GraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientInterceptor.html)
- [SyncGraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SyncGraphQlClientInterceptor.html)
- [WebSocketGraphQlClientInterceptor API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClientInterceptor.html)
- [ClientGraphQlRequest API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/ClientGraphQlRequest.html)

