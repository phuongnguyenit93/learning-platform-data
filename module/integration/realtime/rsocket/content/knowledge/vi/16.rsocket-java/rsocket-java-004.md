# Tạo phía kết nối bằng RSocketConnector

Trong RSocket Java, **RSocketConnector** là điểm khởi đầu để tạo một kết nối từ phía client đến responder. Connector cấu hình transport, thông tin SETUP, MIME type, keepalive, leasing, resumption và cách client xử lý các request ngược từ peer. Sau khi kết nối thành công, ứng dụng nhận được một đối tượng RSocket để gọi request-response, fire-and-forget, request-stream hoặc request-channel.

Bài học này tập trung vào việc tạo và quản lý kết nối ở tầng RSocket Java. Đây là nền tảng để triển khai client/server Java và Spring Boot qua TCP hoặc WebSocket, trao đổi hai chiều, kiểm soát vòng đời kết nối và chuẩn bị cho các tính năng realtime.

Sau bài học, bạn có thể:

- Giải thích vai trò của RSocketConnector và phân biệt nó với RSocketRequester.
- Chọn ClientTransport phù hợp cho TCP hoặc WebSocket.
- Cấu hình SETUP payload, data MIME type, metadata MIME type và keepalive.
- Tạo kết nối bất đồng bộ bằng connect và sử dụng RSocket API.
- Đăng ký SocketAcceptor phía client để nhận request ngược từ server.
- Quản lý đóng kết nối, lỗi kết nối, resumption và leasing.
- Kiểm thử quá trình kết nối và các interaction sau khi kết nối thành công.

## 1. RSocketConnector nằm ở đâu trong kiến trúc?

RSocket là giao thức giao tiếp hai chiều. Sau khi kết nối được thiết lập, cả hai peer đều có thể gửi request theo các mô hình interaction được hỗ trợ. Ở phía client Java, RSocketConnector cấu hình quá trình bắt tay và tạo một phiên RSocket.

Một luồng kết nối cơ bản:

~~~mermaid
flowchart TD
    A[Application client] --> B[RSocketConnector]
    B --> C[SETUP configuration]
    B --> D[ClientTransport]
    D --> E[TCP or WebSocket]
    E --> F[Remote RSocket server]
    F --> G[SETUP accepted]
    G --> H[RSocket connection]
    H --> I[Request-response]
    H --> J[Fire-and-forget]
    H --> K[Request-stream]
    H --> L[Request-channel]
~~~

Các thành phần chính:

| Thành phần | Vai trò |
|---|---|
| RSocketConnector | Cấu hình và khởi tạo kết nối phía client |
| ClientTransport | Chọn cách truyền dữ liệu, ví dụ TCP hoặc WebSocket |
| SETUP frame | Trao đổi cấu hình ban đầu giữa hai peer |
| SocketAcceptor | Xử lý các request mà peer gửi ngược về client |
| RSocket | API dùng sau khi kết nối được thiết lập |
| RSocketRequester | API cấp cao của Spring để gửi object, route và metadata |

RSocketConnector là API mức thấp của RSocket Java. Nó làm việc trực tiếp với Payload và RSocket. RSocketRequester của Spring xây dựng trên tầng này và bổ sung chuyển đổi DTO, route, metadata cùng các API thuận tiện hơn.

Chọn RSocketConnector khi cần kiểm soát chi tiết kết nối hoặc làm việc trực tiếp với protocol API. Chọn RSocketRequester khi ứng dụng Spring chủ yếu trao đổi object và muốn framework quản lý serialization.

## 2. Chọn ClientTransport

Connector không tự quyết định địa chỉ mạng. Ứng dụng cung cấp một ClientTransport để chỉ rõ nơi và cách kết nối.

### Kết nối TCP

TCP phù hợp với giao tiếp giữa các dịch vụ hoặc ứng dụng Java trong mạng backend:

~~~java
ClientTransport transport =
    TcpClientTransport.create("localhost", 7000);

Mono<RSocket> connection =
    RSocketConnector.create()
        .connect(transport);
~~~

TcpClientTransport tạo transport kết nối tới host và port. Transport quản lý việc thiết lập kết nối mạng; RSocketConnector tiếp tục thực hiện quá trình SETUP của RSocket trên transport đó.

### Kết nối WebSocket

WebSocket hữu ích khi RSocket cần đi qua hạ tầng web hoặc giao tiếp với ứng dụng trình duyệt:

~~~java
ClientTransport transport =
    WebsocketClientTransport.create(
        URI.create("ws://localhost:8080/rsocket")
    );

Mono<RSocket> connection =
    RSocketConnector.create()
        .connect(transport);
~~~

Địa chỉ WebSocket phải trỏ tới endpoint đã được server cấu hình để phục vụ RSocket. Khi đi qua mạng không tin cậy, dùng WSS thay cho WS để mã hóa đường truyền và xác minh máy chủ.

### So sánh transport

| Tiêu chí | TCP | WebSocket |
|---|---|---|
| Địa chỉ | Host và port | URI và endpoint path |
| Thường dùng | Service-to-service, backend | Web app, gateway, môi trường web |
| Overhead | Ít lớp đóng gói hơn | Có lớp WebSocket framing |
| Tương thích hạ tầng web | Cần hỗ trợ TCP trực tiếp | Dễ đi qua proxy hỗ trợ WebSocket |
| Bảo vệ đường truyền | TLS tùy cấu hình transport | WSS dùng TLS |

Cùng một RSocket interaction có thể chạy trên các transport khác nhau nếu cả hai phía hỗ trợ transport đó và thống nhất cấu hình kết nối.

## 3. Cấu hình SETUP trước khi kết nối

Khi mở một kết nối RSocket mới, requester gửi SETUP frame. Frame này cung cấp thông tin để hai phía thống nhất cách diễn giải payload và duy trì kết nối.

Các thông tin quan trọng gồm:

- Data MIME type: định dạng của vùng data trong payload.
- Metadata MIME type: định dạng metadata được dùng trên kết nối.
- Setup payload: thông tin ban đầu do client gửi cho server.
- Keepalive interval và max lifetime: cấu hình kiểm tra trạng thái kết nối.
- Các cờ tính năng như leasing hoặc resumption khi được bật.

Ví dụ cấu hình connector:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .setupPayload(
        DefaultPayload.create(
            "{\"client\":\"order-service\",\"version\":1}"
        )
    )
    .dataMimeType("application/json")
    .metadataMimeType(
        WellKnownMimeType
            .MESSAGE_RSOCKET_COMPOSITE_METADATA
            .getString()
    )
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofMinutes(2)
    );
~~~

Trong ví dụ:

- Setup payload gửi thông tin nhận diện client ở thời điểm mở kết nối.
- Data MIME type cho biết data payload dùng JSON.
- Metadata MIME type khai báo Composite Metadata để một payload có thể mang nhiều mục metadata độc lập.
- Keepalive gửi tín hiệu định kỳ và xác định khoảng thời gian tối đa chờ peer còn hoạt động.

Setup payload không phải request nghiệp vụ. Nó được gửi một lần trong quá trình thiết lập kết nối. Nếu cần gửi route, tenant hoặc correlation ID cho từng request, hãy truyền metadata theo từng payload.

### Data MIME type và metadata MIME type

Hai MIME type có vai trò riêng:

| MIME type | Mô tả | Ví dụ |
|---|---|---|
| Data MIME type | Cách giải mã nội dung nghiệp vụ | application/json |
| Metadata MIME type | Cách giải mã vùng metadata | message/x.rsocket.composite-metadata.v0 |
| Routing entry MIME type | Định dạng route trong Composite Metadata | message/x.rsocket.routing.v0 |
| Authentication entry MIME type | Định dạng thông tin xác thực | message/x.rsocket.authentication.v0 |

Nếu client khai báo JSON nhưng server giải mã data theo một định dạng khác, quá trình deserialize có thể thất bại hoặc tạo dữ liệu sai. Hai phía phải thống nhất MIME type và codec.

Nếu chỉ dùng một loại metadata đơn giản, có thể khai báo metadata MIME type tương ứng. Nếu request cần route cùng authentication, tracing hoặc metadata tùy chỉnh, Composite Metadata thường phù hợp hơn.

## 4. Tạo kết nối bằng connect

Phương thức connect nhận ClientTransport và trả về Mono<RSocket>:

~~~java
Mono<RSocket> connection =
    RSocketConnector.create()
        .connect(
            TcpClientTransport.create("localhost", 7000)
        );
~~~

Mono biểu diễn một thao tác bất đồng bộ: kết nối có thể thành công và phát một RSocket, hoặc kết thúc bằng lỗi. Chỉ khi có subscriber thì quá trình kết nối mới được thực thi.

Ví dụ sử dụng kết nối để gửi một request-response:

~~~java
Mono<String> response =
    RSocketConnector.create()
        .dataMimeType("application/json")
        .connect(
            TcpClientTransport.create("localhost", 7000)
        )
        .flatMap(socket ->
            socket.requestResponse(
                DefaultPayload.create(
                    "{\"orderId\":\"order-42\"}"
                )
            )
            .map(payload -> {
                try {
                    return payload.getDataUtf8();
                } finally {
                    payload.release();
                }
            })
            .doFinally(signal -> socket.dispose())
        );
~~~

Ví dụ này tạo kết nối, gửi một request và đóng socket sau khi interaction kết thúc. Nó phù hợp để minh họa vòng đời một lần gọi. Ứng dụng realtime thường giữ kết nối lâu hơn và tái sử dụng socket cho nhiều request thay vì kết nối lại cho mỗi thao tác.

Không gọi block trong event-loop hoặc trong một pipeline reactive đang phục vụ request. Nếu cần chờ kết nối trong một chương trình khởi động đơn giản, có thể block ở ranh giới bootstrap; trong ứng dụng reactive, hãy compose Mono<RSocket> vào lifecycle của ứng dụng.

### Kết nối là một tài nguyên có vòng đời

Khi connect thành công, ứng dụng chịu trách nhiệm quản lý RSocket:

- Tái sử dụng kết nối cho các interaction phù hợp.
- Theo dõi trạng thái đóng hoặc lỗi.
- Dừng phát request mới khi kết nối không còn khả dụng.
- Gọi dispose khi ứng dụng không còn sử dụng kết nối.
- Không giữ Payload hoặc ByteBuf quá vòng đời sở hữu của chúng.

RSocket cung cấp onClose để quan sát khi kết nối đóng. Có thể kết hợp với logging và metrics để theo dõi vòng đời:

~~~java
connection.subscribe(socket -> {
    socket.onClose()
        .doFinally(signal ->
            log.info("RSocket connection closed: {}", signal)
        )
        .subscribe();

    // Đưa socket vào thành phần quản lý kết nối của ứng dụng.
});
~~~

Trong ứng dụng thực tế, nên để một thành phần quản lý kết nối sở hữu subscription và đóng socket khi application context dừng. Tránh tạo nhiều subscription độc lập từ cùng một Mono kết nối mà không có chủ đích, vì mỗi lần thực thi có thể tạo một kết nối riêng.

## 5. Cấu hình SocketAcceptor ở phía client

RSocket là giao thức hai chiều. Sau khi kết nối được thiết lập, server cũng có thể khởi tạo request gửi về client. Để nhận các request ngược đó, client cung cấp SocketAcceptor cho connector.

Ví dụ cấu hình một handler đơn giản:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .acceptor((setup, sendingSocket) ->
        Mono.just(new AbstractRSocket() {
            @Override
            public Mono<Payload> requestResponse(Payload payload) {
                String message;

                try {
                    message = payload.getDataUtf8();
                } finally {
                    payload.release();
                }

                return Mono.just(
                    DefaultPayload.create("client received: " + message)
                );
            }
        })
    );
~~~

SocketAcceptor được gọi trong quá trình thiết lập kết nối. Nó nhận thông tin SETUP và một RSocket đại diện cho phía gửi, sau đó trả về RSocket handler mà peer có thể gọi.

Trong ví dụ, client cung cấp một implementation xử lý request-response ngược. Phía server có thể dùng RSocket phía gửi để gọi request-response tới client sau khi kết nối đã sẵn sàng.

Nếu client chỉ cần gọi server và không cần server gọi ngược, có thể dùng acceptor mặc định hoặc không cấu hình handler tùy phiên bản thư viện.

Không nhầm SocketAcceptor của RSocketConnector với handler phía server. Acceptor ở connector thuộc phía client và xử lý interaction do peer khởi tạo ngược về client.

## 6. Gọi các interaction sau khi kết nối

Sau khi nhận được RSocket, ứng dụng có thể dùng các API tương ứng với bốn mô hình interaction:

~~~java
Mono<Payload> oneResponse =
    socket.requestResponse(
        DefaultPayload.create("{\"id\":\"42\"}")
    );

Mono<Void> noResponse =
    socket.fireAndForget(
        DefaultPayload.create("{\"event\":\"opened\"}")
    );

Flux<Payload> responseStream =
    socket.requestStream(
        DefaultPayload.create("{\"symbol\":\"ACME\"}")
    );

Flux<Payload> channel =
    socket.requestChannel(
        requestPublisher
    );
~~~

| API | Mô hình | Kiểu trả về |
|---|---|---|
| requestResponse | Một request, tối đa một response | Mono<Payload> |
| fireAndForget | Một request, không có response payload | Mono<Void> |
| requestStream | Một request, nhiều response | Flux<Payload> |
| requestChannel | Một stream request và một stream response | Flux<Payload> |

Payload là kiểu dữ liệu mức thấp. Ứng dụng cần mã hóa data và metadata theo MIME type đã khai báo. Khi nhận Payload, hãy giải mã nội dung và release đúng lúc để tránh rò rỉ bộ nhớ do reference counting.

Nếu sử dụng Spring RSocketRequester, framework có thể chuyển đổi DTO và metadata giúp ứng dụng. Không cần thao tác Payload trực tiếp trừ khi cần kiểm soát protocol ở tầng thấp.

## 7. Keepalive và phát hiện kết nối không còn hoạt động

RSocket có KEEPALIVE frame để peer kiểm tra kết nối còn hoạt động hay không. Connector cấu hình hai khoảng thời gian:

- Keepalive interval: khoảng cách giữa các lần gửi keepalive.
- Max lifetime: khoảng thời gian tối đa mà peer có thể không gửi keepalive trước khi kết nối được xem là không còn hoạt động.

Ví dụ:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .keepAlive(
        Duration.ofSeconds(20),
        Duration.ofMinutes(2)
    );
~~~

Nếu không nhận được keepalive trong giới hạn max lifetime, kết nối có thể bị đóng. Giá trị cần cân bằng giữa khả năng phát hiện kết nối lỗi và chi phí gửi tín hiệu định kỳ.

Keepalive không phải heartbeat nghiệp vụ. Nó không báo rằng một request cụ thể đã được xử lý, cũng không thay thế response payload. Nếu ứng dụng cần biết một thiết bị hoặc tiến trình còn hoạt động, hãy thiết kế heartbeat ở tầng nghiệp vụ riêng.

## 8. Leasing: chỉ khởi tạo request khi có quota

Connector có thể bật leasing để requester tuân thủ hạn ngạch do responder cấp:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .lease(spec ->
        spec.maxPendingRequests(128)
    );
~~~

Khi leasing được bật, connector gửi cờ hỗ trợ leasing trong SETUP và quản lý số request được phép khởi tạo theo LEASE frame từ peer.

maxPendingRequests giới hạn số request chờ lease ở phía requester. Nó không phải quota mà server cấp. Server cần cấu hình LeaseSender để phát TTL và số request phù hợp với năng lực.

Leasing kiểm soát số interaction mới trong một khoảng thời gian. Backpressure vẫn điều tiết số response item mà requester yêu cầu trong một stream. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 9. Resumption và khả năng phục hồi kết nối

Kết nối TCP hoặc WebSocket có thể bị gián đoạn tạm thời. RSocket hỗ trợ resumption để hai peer có thể tiếp tục một session nếu cả hai phía được cấu hình và còn giữ đủ trạng thái cần thiết.

Có thể bật khả năng resumption trên connector:

~~~java
RSocketConnector connector = RSocketConnector.create()
    .resume();
~~~

Resumption khác với việc tạo một kết nối mới:

| Cơ chế | Hành vi |
|---|---|
| Reconnect | Tạo một kết nối/session mới sau khi kết nối cũ thất bại |
| Resumption | Cố gắng khôi phục session RSocket trước đó và tiếp tục interaction theo trạng thái đã lưu |

Resumption cần sự hỗ trợ từ cả hai peer và phụ thuộc vào thời gian giữ session, resume token, buffer và cấu hình của implementation. Nếu session đã hết hạn hoặc dữ liệu cần tiếp tục không còn trong buffer, resumption có thể thất bại.

Không giả định bật resume là mọi request nghiệp vụ sẽ được thực hiện đúng một lần. Với lệnh ghi, vẫn cần idempotency key và cơ chế khôi phục trạng thái nghiệp vụ. Với stream sự kiện, cần cursor hoặc sequence number để xử lý trùng lặp và khoảng dữ liệu bị bỏ lỡ.

Nếu resumption không thành công, ứng dụng có thể tạo kết nối mới theo chính sách retry/backoff. Retry tạo session mới không đồng nghĩa tiếp tục chính xác vị trí stream cũ.

## 10. Fragmentation và payload lớn

RSocket có thể chia payload lớn thành nhiều fragment khi cấu hình fragmentation phù hợp. RSocketConnector có thể cấu hình kích thước fragment tối đa thông qua API fragment của phiên bản thư viện.

Fragmentation giúp truyền payload lớn qua giới hạn frame của transport, nhưng không thay thế việc kiểm soát kích thước dữ liệu. Ứng dụng vẫn cần:

- Giới hạn kích thước request và response.
- Chọn kích thước fragment phù hợp với transport.
- Tránh tạo object lớn không cần thiết.
- Xử lý timeout và cancellation khi truyền dữ liệu lâu.
- Kiểm thử trường hợp payload vượt giới hạn và peer không hỗ trợ cấu hình tương ứng.

Với dữ liệu lớn hoặc luồng liên tục, cân nhắc request-stream hoặc request-channel thay vì đóng gói toàn bộ dữ liệu thành một payload đơn lẻ.

## 11. Interceptor và quan sát kết nối

RSocket Java cho phép đăng ký interceptor để quan sát hoặc bổ sung hành vi ở các tầng khác nhau. Interceptor có thể phục vụ:

- Ghi nhận thời điểm kết nối được tạo và đóng.
- Đo thời gian request-response.
- Gắn trace context.
- Ghi nhận lỗi transport hoặc lỗi interaction.
- Thu thập số lượng stream đang hoạt động.

Không ghi payload nhạy cảm, access token hoặc dữ liệu cá nhân vào log. Nên dùng correlation ID và trace ID để nối log giữa client, server và dịch vụ downstream.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| Connection attempts | Số lần thử tạo kết nối |
| Connection success/failure | Số kết nối thành công và thất bại |
| Connection lifetime | Thời gian một kết nối tồn tại |
| Active interactions | Số interaction đang hoạt động |
| Request latency | Thời gian hoàn tất request |
| Reconnect/resume attempts | Số lần phục hồi |
| Keepalive timeout | Số lần kết nối bị đóng do thiếu keepalive |
| Payload size | Kích thước data và metadata |

Interceptor nên nhẹ và không block event-loop. Nếu cần gửi log hoặc metrics tới hệ thống ngoài, hãy dùng pipeline bất đồng bộ và giới hạn hàng đợi.

## 12. Xử lý lỗi khi connect

Kết nối có thể thất bại trước khi RSocket session được tạo. Nguyên nhân thường gặp:

- Host hoặc port không đúng.
- Server chưa chạy hoặc không lắng nghe.
- TCP/WebSocket handshake thất bại.
- Server từ chối SETUP do MIME type hoặc cấu hình không tương thích.
- Authentication hoặc setup validation thất bại.
- Timeout trong quá trình kết nối.
- Transport bị đóng giữa lúc bắt tay.

Có thể xử lý lỗi bằng Reactor:

~~~java
Mono<RSocket> connection =
    RSocketConnector.create()
        .connect(
            TcpClientTransport.create("localhost", 7000)
        )
        .doOnError(error ->
            log.error("Cannot establish RSocket connection", error)
        );
~~~

Nếu muốn retry, chỉ retry lỗi có khả năng tạm thời và đặt giới hạn cùng backoff:

~~~java
Mono<RSocket> connection =
    RSocketConnector.create()
        .connect(
            TcpClientTransport.create("localhost", 7000)
        )
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(500))
                .filter(this::isTransientConnectionFailure)
        );
~~~

Không retry vô hạn với khoảng chờ cố định. Khi server đang quá tải, retry dồn dập có thể làm tình hình nặng hơn. Có thể kết hợp jitter, giới hạn số lần thử và circuit breaker ở tầng ứng dụng.

Phân biệt lỗi connect với lỗi interaction sau khi kết nối. Nếu connect thành công nhưng request-response phát lỗi, vấn đề có thể nằm ở route, payload, quyền truy cập hoặc xử lý nghiệp vụ.

## 13. Bảo mật kết nối

RSocketConnector thiết lập kết nối nhưng không tự thay thế chính sách bảo mật của ứng dụng. Khi triển khai qua mạng không tin cậy:

- Dùng TLS cho TCP hoặc WSS cho WebSocket.
- Xác minh chứng thư và danh tính máy chủ.
- Dùng authentication metadata theo extension hoặc cơ chế Spring Security phù hợp.
- Không xem setup payload hoặc metadata do client gửi là bằng chứng đã xác thực.
- Giới hạn kích thước payload và metadata.
- Không ghi credential vào log.
- Kiểm tra quyền truy cập trên từng route và tài nguyên.

Setup payload có thể chứa thông tin phiên bản hoặc nhận diện client, nhưng không nên chứa secret dạng rõ. Authentication cần được xử lý bằng cơ chế bảo mật được thiết kế cho mục đích đó.

## 14. Kết hợp RSocketConnector với Spring RSocketRequester

Nếu ứng dụng dùng Spring, có thể cấu hình RSocketConnector thông qua RSocketRequester.Builder:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector
            .keepAlive(
                Duration.ofSeconds(20),
                Duration.ofMinutes(2)
            )
            .lease(spec ->
                spec.maxPendingRequests(128)
            )
    )
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

RSocketRequester quản lý chuyển đổi DTO, route và metadata. Callback rsocketConnector cho phép tùy chỉnh các thiết lập thấp hơn của kết nối.

Sau đó gửi request bằng API Spring:

~~~java
Mono<OrderView> order = requester
    .route("orders.get")
    .data(new GetOrderRequest("order-42"))
    .retrieveMono(OrderView.class);
~~~

Đây là cách phù hợp khi phần lớn ứng dụng làm việc với DTO. Dùng RSocketConnector trực tiếp khi cần API RSocket mức thấp, tự quản lý Payload hoặc triển khai hành vi kết nối đặc biệt.

## 15. Kiểm thử tạo và quản lý kết nối

Kiểm thử nên tách phần cấu hình connector, transport và interaction.

### Kiểm thử kết nối thành công

Với một server test đang lắng nghe, tạo connector và xác nhận Mono phát ra RSocket:

~~~java
StepVerifier.create(
    RSocketConnector.create()
        .connect(TcpClientTransport.create("localhost", 7000))
)
.assertNext(socket -> {
    assertThat(socket.availability()).isGreaterThan(0.0);
    socket.dispose();
})
.verifyComplete();
~~~

### Kiểm thử server không sẵn sàng

Khi transport không kết nối được, Mono phải kết thúc bằng lỗi thay vì phát RSocket:

~~~java
StepVerifier.create(
    RSocketConnector.create()
        .connect(TcpClientTransport.create("localhost", 7999))
)
.expectError()
.verify();
~~~

### Kiểm thử vòng đời

Ngoài kết nối thành công, hãy xác nhận:

- Client dispose socket thì tài nguyên transport được giải phóng.
- onClose phát tín hiệu khi kết nối đóng.
- Keepalive timeout được phát hiện theo cấu hình.
- SETUP payload và MIME type được hai phía hiểu thống nhất.
- Client acceptor xử lý được request ngược nếu ứng dụng cần giao tiếp hai chiều.
- Resumption hoạt động khi cả hai peer hỗ trợ và session còn hiệu lực.
- Lỗi connect và lỗi interaction được phân biệt trong log/metric.

Kiểm thử integration nên chạy với transport thực tế mà hệ thống sẽ dùng. Một test TCP không chứng minh endpoint WebSocket cũng đã được cấu hình đúng.

## 16. Quy trình tạo kết nối trong ứng dụng

Khi triển khai client RSocket, hãy thực hiện theo thứ tự:

1. Chọn transport và địa chỉ endpoint.
2. Thống nhất data MIME type và metadata MIME type với server.
3. Xác định setup payload cần gửi khi mở session.
4. Cấu hình keepalive theo đặc tính mạng và yêu cầu phát hiện kết nối lỗi.
5. Quyết định có cần client SocketAcceptor cho request ngược không.
6. Bật leasing hoặc resumption nếu hệ thống cần và cả hai peer hỗ trợ.
7. Gọi connect bất đồng bộ và xử lý lỗi thiết lập.
8. Tái sử dụng RSocket cho các interaction trong vòng đời phù hợp.
9. Theo dõi onClose, dispose khi shutdown và thu thập metrics.
10. Kiểm thử transport, SETUP, interaction, cancellation và phục hồi.

RSocketConnector cung cấp quyền kiểm soát quá trình tạo kết nối phía client. Khi transport, SETUP, MIME type và lifecycle được cấu hình nhất quán, ứng dụng có thể sử dụng một session RSocket lâu dài cho nhiều kiểu interaction và giao tiếp hai chiều.

## Ghi nhớ

- RSocketConnector tạo kết nối RSocket phía client thông qua ClientTransport.
- connect trả về Mono<RSocket>, vì vậy quá trình kết nối là bất đồng bộ và chỉ chạy khi có subscription.
- SETUP khai báo MIME type, setup payload, keepalive và các tính năng kết nối.
- SocketAcceptor trên connector xử lý request do peer gửi ngược về client.
- RSocket là API mức thấp; RSocketRequester của Spring bổ sung chuyển đổi DTO, route và metadata.
- Keepalive kiểm tra trạng thái kết nối, không thay thế heartbeat nghiệp vụ.
- Leasing giới hạn interaction mới; resumption cố gắng khôi phục session cũ.
- Luôn quản lý dispose/onClose, lỗi connect, timeout và bảo mật transport.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [RSocket Java — RSocketConnector](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocketConnector.html)
- [RSocket Java — RSocket](https://javadoc.io/doc/io.rsocket/rsocket-core/latest/io/rsocket/core/RSocket.html)
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)

