# WebSocketDisconnectedException

Khi một ứng dụng dùng Spring for GraphQL để gọi server qua WebSocket, kết nối có thể bị đóng trong lúc một GraphQL request hoặc subscription vẫn đang chạy. Khi đó client có thể nhận **WebSocketDisconnectedException**. Đây là exception ở tầng transport, cho biết client không còn nhận được kết quả qua WebSocket của operation đang thực thi.

Exception này thuộc package org.springframework.graphql.client và kế thừa GraphQlTransportException. Nó mang thông tin về request đang chạy và trạng thái đóng WebSocket. Ứng dụng có thể dùng thông tin đó để ghi log, phân loại lỗi và quyết định có nên kết nối lại hoặc đăng ký lại subscription.

Lớp exception này có từ Spring for GraphQL 1.0.0.

Điều cần nhớ là WebSocketDisconnectedException không có nghĩa GraphQL resolver đã trả về lỗi nghiệp vụ. Nó cho biết kênh truyền bị mất trong lúc client đang chờ kết quả. Server có thể đã xử lý một phần hoặc toàn bộ request trước khi kết nối bị đóng, vì vậy cách khôi phục phải phụ thuộc loại operation.

## WebSocketDisconnectedException xuất hiện khi nào?

Spring for GraphQL cung cấp WebSocketGraphQlClient để gửi GraphQL request qua một WebSocket connection dùng chung. Client có thể thực hiện Query, Mutation và Subscription trên cùng connection. Khi connection bị đóng hoặc mất trong lúc một request hay subscription đang chạy, Spring phát sinh WebSocketDisconnectedException.

Một số nguyên nhân thường gặp:

- Server restart, deploy hoặc đóng session.
- Reverse proxy hay load balancer đóng connection idle.
- Mạng giữa client và server bị gián đoạn.
- Thiết bị client chuyển mạng, sleep hoặc mất Wi-Fi.
- WebSocket server gặp lỗi và đóng connection.
- Firewall hoặc NAT loại bỏ connection lâu không có traffic.
- Ứng dụng gọi stop() khi operation vẫn đang chạy; client kết thúc các request đang chạy bằng error signal.

Lỗi có thể xảy ra ngay sau khi gửi request hoặc sau khi subscription đã nhận nhiều event. Trong cả hai trường hợp, operation đang chạy không thể tiếp tục nhận dữ liệu trên connection cũ.

## Vị trí trong exception hierarchy

WebSocketDisconnectedException thuộc nhóm lỗi client và transport:

~~~text
Throwable
  └── Exception
      └── RuntimeException
          └── NestedRuntimeException
              └── GraphQlClientException
                  ├── FieldAccessException
                  └── GraphQlTransportException
                      ├── SubscriptionErrorException
                      └── WebSocketDisconnectedException
~~~

Các lớp có ý nghĩa khác nhau:

| Exception | Ý nghĩa |
| --- | --- |
| GraphQlClientException | Lớp cơ sở cho exception phía GraphQL client |
| GraphQlTransportException | Lỗi khi transport thực thi request hoặc lỗi liên quan encode/decode transport |
| WebSocketDisconnectedException | WebSocket bị đóng hoặc mất khi request/subscription đang chạy |
| SubscriptionErrorException | Server kết thúc subscription bằng message error của GraphQL over WebSocket |
| FieldAccessException | Client không truy cập/giải mã được field theo đường dẫn retrieve do field error hoặc null có lỗi |

Không gom các exception này thành một loại lỗi chung. Mất kết nối cần chính sách reconnect; SubscriptionErrorException thường phản ánh lỗi được server gửi cho operation; FieldAccessException cần xem GraphQL response và field path.

## Phân biệt lỗi transport và GraphQL error

GraphQL response có thể chứa data và errors. Đây là kết quả từ GraphQL execution, không nhất thiết làm Mono hoặc Flux phát lỗi ở tầng Reactor. Ngược lại, WebSocketDisconnectedException là tín hiệu lỗi transport khiến publisher kết thúc bằng onError.

| Tình huống | Cách client nhận biết |
| --- | --- |
| Resolver trả lỗi nghiệp vụ trong GraphQL response | ClientGraphQlResponse chứa errors; kiểm tra isValid hoặc lỗi của field |
| Field được chọn có lỗi và retrieve không giải mã được | Có thể phát FieldAccessException |
| Server gửi message error để kết thúc subscription | SubscriptionErrorException |
| WebSocket bị đóng khi operation đang chạy | WebSocketDisconnectedException |
| Không thiết lập được connection hoặc GraphQL session | Có thể là GraphQlTransportException hoặc exception khởi tạo transport/session khác |

Ví dụ, nếu server trả response:

~~~json
{
  "data": {
    "account": null
  },
  "errors": [
    {
      "message": "Không tìm thấy tài khoản",
      "path": ["account"]
    }
  ]
}
~~~

Đây là GraphQL execution error. Client đã nhận được response nên có thể đọc errors, hiển thị thông báo phù hợp hoặc xử lý theo nghiệp vụ.

Nếu WebSocket bị mất trước khi response tới client, client không thể biết chắc server đã xử lý operation tới đâu. Khi đó WebSocketDisconnectedException biểu diễn trạng thái không xác định của lần trao đổi qua transport.

## Thông tin có thể đọc từ exception

WebSocketDisconnectedException có constructor nhận ba thông tin:

- closeStatusMessage: thông báo đóng kết nối nhận được.
- request: GraphQL request đang chạy khi kết nối bị đóng.
- status: CloseStatus của WebSocket session.

Hai phương thức hữu ích:

| Phương thức | Công dụng |
| --- | --- |
| getCloseStatus() | Lấy CloseStatus dùng để đóng WebSocket session |
| getRequest() | Lấy GraphQlRequest gốc; được kế thừa từ GraphQlClientException |

CloseStatus cung cấp mã đóng và lý do đóng. Có thể dùng mã này để phân loại tình huống, nhưng không nên kết luận nguyên nhân chỉ dựa trên một mã. Cần kết hợp log ở client, server, proxy và thời điểm xảy ra lỗi.

Ví dụ ghi log:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import org.springframework.web.socket.CloseStatus;

private void logDisconnect(WebSocketDisconnectedException exception) {
    CloseStatus status = exception.getCloseStatus();

    if (status != null) {
        log.warn(
                "GraphQL WebSocket disconnected: code={}, reason={}",
                status.getCode(),
                status.getReason());
    }
    else {
        log.warn("GraphQL WebSocket disconnected: {}", exception.getMessage());
    }

    if (exception.getRequest() != null) {
        log.warn("A GraphQL request was active when the connection closed");
    }
}
~~~

Không ghi nguyên access token, cookie, variables nhạy cảm hoặc toàn bộ request body vào log. Nếu cần liên kết log, hãy gắn correlation ID và operation name đã được kiểm soát.

## Tạo WebSocketGraphQlClient

WebSocketGraphQlClient sử dụng WebSocketClient của Spring WebFlux. Ví dụ tạo client bằng Reactor Netty:

~~~java
import java.net.URI;
import java.time.Duration;

import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;

URI url = URI.create("wss://api.example.com/graphql");
WebSocketClient transport = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, transport)
                .keepAlive(Duration.ofSeconds(25))
                .build();
~~~

WebSocketGraphQlClient là client hướng kết nối và hỗ trợ multiplex. Nó giữ một connection dùng chung cho nhiều request. Nên tái sử dụng một instance cho mỗi GraphQL server trong ứng dụng, thay vì tạo một client mới cho từng request.

Kết nối được tạo tự động khi client bắt đầu thực hiện request. Nếu cần chủ động kiểm tra connection trước khi gửi operation, có thể gọi start():

~~~java
graphQlClient.start()
        .timeout(Duration.ofSeconds(10))
        .block();
~~~

Ví dụ block() phù hợp cho chương trình command-line hoặc luồng khởi động imperative. Trong ứng dụng WebFlux, không block event loop; hãy ghép Mono<Void> từ start() vào lifecycle reactive của ứng dụng.

## Cách WebSocketGraphQlClient phục hồi connection

WebSocketGraphQlClient có hai hành vi cần phân biệt:

1. Khi connection bị mất, các request hoặc subscription đang chạy trên connection đó kết thúc bằng lỗi, trong đó có thể là WebSocketDisconnectedException.
2. Connection được thiết lập lại khi client nhận request tiếp theo hoặc khi gọi start() lần nữa.

Việc tự thiết lập lại connection không có nghĩa operation cũ được tự động phát lại. Client không thể tự biết một mutation đã commit ở server hay chưa, cũng không thể tự khôi phục các event đã phát trong khoảng mất kết nối.

Vòng đời tổng quát:

~~~mermaid
flowchart TD
    A["GraphQlClient gửi operation"] --> B["WebSocket connection đang hoạt động"]
    B --> C{"Connection còn mở?"}
    C -->|Có| D["Nhận GraphQL response hoặc event"]
    D --> B
    C -->|Không| E["Operation đang chạy kết thúc bằng lỗi"]
    E --> F["WebSocketDisconnectedException"]
    F --> G{"Có request mới hoặc gọi start()?"}
    G -->|Có| H["Client thiết lập connection mới"]
    H --> I["Gửi operation mới hoặc đăng ký lại"]
    G -->|Không| J["Client chờ request tiếp theo"]
~~~

Connection mới là một GraphQL session mới. Nếu server yêu cầu connection_init, client cần khởi tạo session và chờ connection_ack trước khi operation mới được gửi.

## Quản lý start() và stop()

WebSocketGraphQlClient cung cấp start() và stop():

- start() kết nối WebSocket, gửi connection_init và chờ connection_ack. Mono hoàn tất khi GraphQL session sẵn sàng nhận request.
- stop() đóng WebSocket với CloseStatus.NORMAL, kết thúc các request đang chạy bằng error signal và từ chối request mới.
- Sau stop(), có thể gọi start() để cho phép request mới.

Ví dụ dừng client khi ứng dụng đóng:

~~~java
graphQlClient.stop()
        .timeout(Duration.ofSeconds(5))
        .block();
~~~

Đây cũng là ví dụ cho luồng imperative. Trong ứng dụng reactive, hãy nối stop() vào quá trình shutdown mà không block event loop.

Không coi error signal phát sinh khi chính ứng dụng gọi stop() là sự cố mạng cần retry. Kiểu exception cụ thể phụ thuộc tình huống đóng session. Nếu retry loop tiếp tục tạo request trong khi ứng dụng đang shutdown, client có thể reconnect ngoài ý muốn và làm quá trình đóng ứng dụng kéo dài.

## Bắt WebSocketDisconnectedException với Mono

Query hoặc Mutation trả một response thường được thực thi qua Mono:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Mono;

Mono<Account> accountMono = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .doOnError(WebSocketDisconnectedException.class, this::logDisconnect);
~~~

Có thể chuyển lỗi thành lỗi ứng dụng để tầng gọi quyết định:

~~~java
Mono<Account> accountMono = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .onErrorMap(
                WebSocketDisconnectedException.class,
                exception -> new RemoteGraphQlUnavailableException(
                        "GraphQL connection was lost", exception));
~~~

Chỉ chuyển đổi exception khi tầng ứng dụng cần abstraction riêng. Nếu caller cần phân tích CloseStatus hoặc request gốc, giữ lại WebSocketDisconnectedException làm cause hoặc xử lý trực tiếp.

## Bắt lỗi trong Subscription Flux

Subscription trả về Flux. Nếu WebSocket bị mất khi subscription đang chạy, Flux có thể kết thúc bằng WebSocketDisconnectedException:

~~~java
import reactor.core.publisher.Flux;

Flux<PriceUpdate> updates = graphQlClient.document("""
        subscription PriceUpdates($symbol: String!) {
            priceUpdates(symbol: $symbol) {
                eventId
                symbol
                price
            }
        }
        """)
        .variable("symbol", "ACME")
        .retrieveSubscription("priceUpdates")
        .toEntity(PriceUpdate.class)
        .doOnError(WebSocketDisconnectedException.class, this::logDisconnect);
~~~

Nếu server chủ động gửi message error cho subscription, Flux có thể kết thúc bằng SubscriptionErrorException. Nếu connection bị đóng, Flux có thể kết thúc bằng WebSocketDisconnectedException. Hai trường hợp cần chính sách khác nhau:

- SubscriptionErrorException: kiểm tra GraphQL errors, quyền truy cập, input và trạng thái server.
- WebSocketDisconnectedException: kiểm tra close status, mạng, proxy và khởi động lại connection/subscription khi phù hợp.

Không chuyển mọi lỗi thành Flux.empty(). Làm như vậy sẽ biến một subscription bị gián đoạn thành stream hoàn tất bình thường và khiến tầng gọi không biết dữ liệu thời gian thực đã bị ngắt.

## Retry với Reactor

Spring for GraphQL cho phép dùng Reactor retry operator để bắt đầu lại subscription khi connection bị mất. Với ứng dụng production, nên giới hạn số lần thử, thêm backoff và chỉ retry loại lỗi được xác định.

Ví dụ:

~~~java
import java.time.Duration;

import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

Retry disconnectRetry = Retry.backoff(4, Duration.ofSeconds(1))
        .maxBackoff(Duration.ofSeconds(10))
        .jitter(0.5)
        .filter(WebSocketDisconnectedException.class::isInstance)
        .doBeforeRetry(signal ->
                log.warn(
                        "Retry GraphQL WebSocket after disconnect, attempt={}",
                        signal.totalRetries() + 1));

Flux<PriceUpdate> updates = graphQlClient.document("""
        subscription PriceUpdates($symbol: String!) {
            priceUpdates(symbol: $symbol) {
                eventId
                symbol
                price
            }
        }
        """)
        .variable("symbol", "ACME")
        .retrieveSubscription("priceUpdates")
        .toEntity(PriceUpdate.class)
        .retryWhen(disconnectRetry);
~~~

Chính sách trên thử lại tối đa bốn lần với thời gian chờ tăng dần và có jitter. Retry chỉ áp dụng cho WebSocketDisconnectedException; lỗi GraphQL nghiệp vụ hoặc lỗi khác sẽ tiếp tục truyền ra ngoài.

Khi retry tạo subscription mới, WebSocketGraphQlClient sẽ thiết lập lại connection nếu cần. Mỗi lần đăng ký lại là một operation mới, không phải tiếp tục luồng byte/event cũ.

Với query chỉ đọc, retry có giới hạn thường có thể chấp nhận được nếu request không có side effect. Với mutation, cần thận trọng hơn vì server có thể đã thực hiện thay đổi trước khi connection bị mất.

Ví dụ retry một Query chỉ đọc:

~~~java
import reactor.core.publisher.Mono;

Mono<Account> account = graphQlClient.document("""
        query Account($id: ID!) {
            account(id: $id) {
                id
                name
            }
        }
        """)
        .variable("id", "account-42")
        .retrieve("account")
        .toEntity(Account.class)
        .retryWhen(disconnectRetry);
~~~

Chỉ dùng cách này khi query không gây side effect và việc đọc lại dữ liệu sau reconnect là phù hợp với nghiệp vụ.

## Không retry Mutation một cách mù quáng

Giả sử client gửi mutation:

~~~graphql
mutation Transfer($input: TransferInput!) {
  transfer(input: $input) {
    transactionId
    status
  }
}
~~~

Server có thể đã chuyển tiền thành công, nhưng WebSocket bị đóng trước khi response tới client. Client nhận WebSocketDisconnectedException và không biết mutation đã commit hay chưa.

Nếu client retry mutation ngay lập tức, server có thể thực hiện giao dịch lần thứ hai. Đây là trạng thái kết quả không xác định, không phải bằng chứng mutation thất bại.

Các cách giảm rủi ro:

- Dùng idempotency key hoặc command ID duy nhất cho mỗi thao tác nghiệp vụ.
- Lưu kết quả xử lý command ở server và bảo đảm cùng key chỉ được áp dụng một lần.
- Sau disconnect, truy vấn trạng thái giao dịch bằng ID trước khi gửi lại command.
- Chỉ retry mutation khi API có semantics idempotent được thiết kế và kiểm thử rõ ràng.
- Không dựa vào client request timeout hoặc WebSocket close code để kết luận server chưa xử lý mutation.

Ví dụ mutation mang command ID:

~~~graphql
input TransferInput {
  commandId: ID!
  fromAccountId: ID!
  toAccountId: ID!
  amountMinorUnits: Int!
}

type Mutation {
  transfer(input: TransferInput!): TransferResult!
}
~~~

Server cần lưu commandId với unique constraint hoặc cơ chế deduplication tương đương. Khi nhận lại cùng commandId, server trả kết quả đã ghi nhận thay vì thực hiện side effect lần nữa.

## Khôi phục Subscription mà không bỏ lỡ event

Retry subscription chỉ tạo một subscription mới. Nếu nguồn event tiếp tục phát trong thời gian connection mất, client có thể bỏ lỡ event. WebSocketDisconnectedException không chứa event bị mất và cũng không cung cấp cursor để tự resume.

Muốn khôi phục liên tục, schema và event source cần hỗ trợ cursor hoặc event ID:

~~~graphql
type Subscription {
  priceUpdates(symbol: String!, afterEventId: ID): PriceUpdate!
}

type PriceUpdate {
  eventId: ID!
  symbol: String!
  price: Float!
}
~~~

Client lưu event ID cuối cùng đã xử lý thành công. Khi đăng ký lại, client truyền event ID đó để server phát lại những event tiếp theo:

~~~java
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

AtomicReference<String> lastProcessedEventId = new AtomicReference<>();

Flux<PriceUpdate> updates = Flux.defer(() ->
        graphQlClient.document("""
                subscription PriceUpdates(
                    $symbol: String!,
                    $afterEventId: ID
                ) {
                    priceUpdates(
                        symbol: $symbol,
                        afterEventId: $afterEventId
                    ) {
                        eventId
                        symbol
                        price
                    }
                }
                """)
                .variable("symbol", "ACME")
                .variable("afterEventId", lastProcessedEventId.get())
                .retrieveSubscription("priceUpdates")
                .toEntity(PriceUpdate.class))
        .retryWhen(disconnectRetry);
~~~

Flux.defer tạo lại request spec mỗi lần retry subscribe lại, vì vậy giá trị cursor mới nhất được đọc tại thời điểm đăng ký lại. Khi xử lý event, chỉ cập nhật cursor sau khi nghiệp vụ đã xử lý thành công:

~~~java
updates.concatMap(update ->
        processPriceUpdate(update)
                .then(Mono.fromRunnable(() ->
                        lastProcessedEventId.set(update.eventId()))));
~~~

Ví dụ dùng AtomicReference trong một process. Với consumer cần sống qua restart, lưu checkpoint vào database hoặc storage bền vững. Server phải có event retention và semantics rõ ràng cho afterEventId; nếu server không hỗ trợ replay, cursor phía client không thể tự khôi phục event đã mất.

Khi server replay, một event có thể được gửi lại nếu client đã xử lý nhưng chưa kịp ghi checkpoint. Vì vậy, xử lý event nên idempotent theo eventId và chấp nhận duplicate.

## Xác thực lại khi connection được tạo mới

Một WebSocket connection mới cần khởi tạo GraphQL session mới. Nếu ứng dụng gửi token trong connection_init, token cần còn hiệu lực ở lần kết nối lại.

Spring for GraphQL cung cấp WebSocketGraphQlClientInterceptor với callback connectionInitPayload() và handleConnectionAck(). Có thể dùng connectionInitPayload() để lấy access token hiện hành mỗi lần tạo connection:

~~~java
import java.util.Map;

import org.springframework.graphql.client.ClientGraphQlRequest;
import org.springframework.graphql.client.ClientGraphQlResponse;
import org.springframework.graphql.client.GraphQlClientInterceptor.Chain;
import org.springframework.graphql.client.GraphQlClientInterceptor.SubscriptionChain;
import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class AuthWebSocketInterceptor
        implements WebSocketGraphQlClientInterceptor {

    private final TokenProvider tokenProvider;

    public AuthWebSocketInterceptor(TokenProvider tokenProvider) {
        this.tokenProvider = tokenProvider;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return tokenProvider.currentAccessToken()
                .map(token -> (Object) Map.of(
                        "Authorization",
                        "Bearer " + token));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {
        return chain.next(request);
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {
        return chain.next(request);
    }
}
~~~

Khi token hết hạn, token provider cần làm mới token trước lần kết nối lại. Nếu connection bị từ chối do authentication hoặc authorization, retry liên tục với cùng token sẽ không giải quyết được vấn đề. Hãy phân biệt lỗi credential với lỗi mạng và chỉ retry sau khi token đã được làm mới hoặc người dùng đã xác thực lại.

Đăng ký interceptor trên client builder:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .interceptor(new AuthWebSocketInterceptor(tokenProvider))
                .build();
~~~

Trong một interceptor chain chỉ nên có tối đa một WebSocketGraphQlClientInterceptor. Có thể kết hợp các GraphQlClientInterceptor thông thường cho request logging, tracing hoặc metrics.

## Keep-alive và timeout

Một số proxy và load balancer đóng WebSocket nếu không có traffic trong một khoảng thời gian. WebSocketGraphQlClient hỗ trợ ping định kỳ:

~~~java
WebSocketGraphQlClient graphQlClient =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .keepAlive(Duration.ofSeconds(25))
                .build();
~~~

Keep-alive giúp duy trì connection qua các thiết bị có idle timeout và có thể phát hiện một số tình huống mất kết nối. Nó không bảo đảm connection luôn tồn tại và không thay thế retry hoặc resume logic.

Hãy cấu hình thời gian ping ngắn hơn idle timeout của proxy/load balancer với một khoảng đệm hợp lý. Đồng thời theo dõi:

- Số lần connection đóng theo close code.
- Thời gian từ disconnect tới khi reconnect thành công.
- Số retry và số lần retry hết giới hạn.
- Số subscription đang hoạt động.
- Khoảng thời gian không nhận event.
- Số event replay và duplicate sau reconnect.
- Tỷ lệ connection init hoặc authentication thất bại.

## Kiểm thử WebSocketDisconnectedException

Nên kiểm thử riêng việc phân loại exception và hành vi phục hồi.

Các tình huống cần có:

1. Server đóng WebSocket trong khi Query đang chờ response.
2. Server đóng connection sau khi Subscription đã phát một số event.
3. Server gửi GraphQL error message nhưng connection vẫn hoạt động.
4. Client gọi stop() trong khi operation còn chạy.
5. Client retry và connection mới được thiết lập thành công.
6. Retry hết số lần cho phép và lỗi được chuyển lên caller.
7. Mutation bị disconnect sau khi server commit và client không tạo side effect lần hai.
8. Subscription reconnect với cursor và không bỏ lỡ event theo semantics của event source.
9. Token hết hạn rồi được làm mới trước connection_init kế tiếp.

Có thể dùng StepVerifier để xác minh Flux kết thúc với exception mong muốn:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(subscriptionFlux)
        .expectNextCount(1)
        .expectError(WebSocketDisconnectedException.class)
        .verify();
~~~

Trong integration test, cần một WebSocket server test có khả năng đóng connection tại thời điểm xác định. Sau đó xác minh client nhận exception, close status được giữ lại và request đang chạy được nhận diện. Với retry test, server test cần chấp nhận connection mới và trả event cho operation đăng ký lại.

Đối với Subscription có replay, test phải xác minh cả event ID, thứ tự event, duplicate và checkpoint. Chỉ xác nhận connection đã mở lại là chưa đủ để chứng minh dữ liệu không bị mất.

## Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Query hoặc Mutation phát WebSocketDisconnectedException | Connection đóng trước khi response tới client | Kiểm tra close status, request đang chạy và kết nối |
| Subscription kết thúc bất ngờ | WebSocket mất trong lúc stream đang hoạt động | Dùng retry có giới hạn và thiết kế resume nếu cần |
| Nhầm disconnect với GraphQL error | Không phân biệt transport exception và response errors | Kiểm tra exception hierarchy và ClientGraphQlResponse |
| Retry nhưng vẫn không kết nối được | Server chưa sẵn sàng, proxy lỗi hoặc credential hết hạn | Backoff, kiểm tra endpoint và làm mới token |
| Mutation bị thực hiện hai lần | Retry sau khi server đã commit nhưng response bị mất | Dùng command ID/idempotency key |
| Reconnect thành công nhưng mất event | Subscription mới bắt đầu từ thời điểm hiện tại | Dùng cursor, event ID và replay ở server |
| Nhận event trùng sau retry | Server replay event đã xử lý trước checkpoint | Deduplicate theo event ID |
| Retry loop chạy khi ứng dụng shutdown | stop() bị xem như lỗi mạng | Phân biệt shutdown có chủ đích và disconnect bất ngờ |
| Keep-alive vẫn không ngăn được disconnect | Proxy/server restart hoặc mạng thực sự bị mất | Kết hợp retry, reconnect và monitoring |
| Connection mới bị từ chối | Token cũ hoặc quyền truy cập đã thay đổi | Làm mới credential và xác thực lại |

## Nguyên tắc xử lý WebSocketDisconnectedException

Khi sử dụng WebSocketGraphQlClient, hãy nhớ:

1. **Nhận diện đúng loại lỗi.** WebSocketDisconnectedException là GraphQlTransportException, không phải GraphQL business error.
2. **Đọc CloseStatus và request gốc.** Dùng getCloseStatus() và getRequest() để chẩn đoán.
3. **Hiểu hành vi reconnect.** Client tạo connection mới ở request kế tiếp hoặc khi gọi start(); operation đang chạy vẫn kết thúc bằng lỗi.
4. **Retry có giới hạn.** Dùng backoff, jitter và chỉ retry lỗi transport phù hợp.
5. **Không retry mutation mù quáng.** Dùng idempotency key hoặc truy vấn trạng thái trước khi gửi lại.
6. **Resume subscription bằng cursor.** Reconnect không tự phát lại event đã mất.
7. **Xử lý duplicate.** Dùng event ID và checkpoint sau khi xử lý thành công.
8. **Làm mới authentication.** connection_init của connection mới cần credential còn hiệu lực.
9. **Phân biệt shutdown và sự cố.** stop() chủ động kết thúc operation, không nên kích hoạt reconnect loop.
10. **Theo dõi connection lifecycle.** Đo close code, retry, reconnect latency, active subscription và event gap.

WebSocketDisconnectedException cho biết WebSocket connection bị đóng hoặc mất khi một GraphQL request hay subscription đang chạy. Spring for GraphQL cung cấp close status và request gốc để ứng dụng chẩn đoán. WebSocketGraphQlClient có thể thiết lập connection mới cho request tiếp theo, còn operation đang chạy cần được retry hoặc đăng ký lại theo chính sách của ứng dụng. Query có thể retry khi phù hợp; Mutation cần idempotency vì kết quả server có thể chưa rõ; Subscription cần cursor và replay nếu không được phép mất event. Phân loại lỗi đúng và thiết kế phục hồi theo semantics của từng operation giúp client chịu được gián đoạn mạng mà không tạo side effect trùng hoặc mất dữ liệu.

## Tài liệu tham khảo

- [Spring for GraphQL - Client: WebSocketGraphQlClient và Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL API - WebSocketDisconnectedException](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketDisconnectedException.html)
- [Spring for GraphQL API - WebSocketGraphQlClient](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClient.html)
- [Spring for GraphQL API - GraphQlClient.RequestSpec](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
