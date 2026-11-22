# Requester, responder và tính đối xứng hai chiều

## Mục tiêu

RSocket là giao thức giao tiếp hai chiều, bất đồng bộ và đa luồng trên một kết nối. Khi mới thiết lập kết nối, một bên thường chủ động mở transport và bên kia chấp nhận kết nối. Nhưng sau khi RSocket SETUP hoàn tất, vai trò requester và responder được xác định theo từng request: bất kỳ đầu nào cũng có thể khởi tạo request, và đầu còn lại sẽ phản hồi.

Bài học này giải thích sự khác nhau giữa client/server và requester/responder, bốn kiểu tương tác của RSocket, cách dùng RSocketRequester trong Spring, cách một client cũng có thể làm responder, và cách thiết kế luồng hai chiều mà không chặn reactive pipeline.

Sau bài này, bạn có thể:

- Phân biệt vai trò ở tầng kết nối với vai trò ở từng request.
- Chọn đúng Request-Response, Fire-and-Forget, Request-Stream hoặc Request-Channel.
- Gửi request từ client đến server bằng RSocketRequester.
- Cho server chủ động gọi ngược về client đang kết nối.
- Đăng ký responder ở cả hai phía bằng @MessageMapping.
- Hiểu back pressure, cancellation, metadata và các giới hạn của cách giao tiếp hai chiều.

## 1. Client/server khác requester/responder như thế nào?

Ở tầng transport, client thường là bên khởi tạo kết nối TCP hoặc WebSocket; server là bên lắng nghe và chấp nhận kết nối. RSocket dùng frame SETUP để hai đầu thống nhất thông tin của connection như MIME type và cấu hình giao thức.

Sau khi SETUP thành công, sự phân biệt client/server không còn quyết định ai được gửi request. Hai đầu đều có thể bắt đầu request trên cùng một connection. Trong một request cụ thể:

- **Requester** là bên gửi request frame và khởi tạo interaction.
- **Responder** là bên nhận request, xử lý và phát response nếu interaction yêu cầu response.

Một connection có thể mang nhiều request đồng thời theo cả hai hướng. Vì vậy, một thiết bị được gọi là client ở tầng kết nối có thể là responder cho request do server gửi đến, rồi ngay sau đó lại là requester khi gửi một request khác đến server.

Ví dụ trong ứng dụng giám sát thiết bị:

- Thiết bị gửi telemetry đến server: thiết bị là requester, server là responder.
- Server gửi cấu hình mới đến thiết bị: server là requester, thiết bị là responder.
- Thiết bị gửi trạng thái xác nhận cấu hình: thiết bị lại là requester.
- Server yêu cầu thiết bị phát một luồng số đo trong vài phút: server là requester, thiết bị là responder cho request-stream đó.

Đây là tính đối xứng của RSocket: cả hai đầu đều có thể khởi tạo interaction, không bị giới hạn vào mô hình client chỉ gửi và server chỉ trả lời.

## 2. Bốn kiểu interaction của RSocket

RSocket định nghĩa bốn kiểu request chính:

| Kiểu | Requester gửi | Responder trả về | Trường hợp dùng |
| --- | --- | --- | --- |
| Request-Response | Một message | Một message | Tra cứu, tính toán, đọc trạng thái |
| Fire-and-Forget | Một message | Không có response payload | Gửi sự kiện không cần kết quả trực tiếp |
| Request-Stream | Một message | Một stream gồm nhiều message | Theo dõi số liệu, truy vấn danh sách lớn |
| Request-Channel | Một stream message | Một stream response | Trao đổi dữ liệu liên tục theo cả hai hướng |

Mỗi interaction được biểu diễn bằng một stream id riêng trong connection. Các stream có thể chạy đồng thời và được multiplex trên cùng transport.

### Request-Response

Requester gửi một message và chờ đúng một response. Trong Java với Spring, dạng response đơn thường là Mono<T>.

~~~text
Requester                  Responder
    |                           |
    | ---- request  ----------> |
    | <--- response ----------- |
    |                           |
~~~

Ví dụ: client gửi mã sản phẩm và nhận một ProductView.

### Fire-and-Forget

Requester gửi một message, không chờ response payload. Dạng này phù hợp với sự kiện không cần phản hồi nghiệp vụ trực tiếp.

~~~text
Requester                  Responder
    |                           |
    | ---- event -------------> |
    |                           |
~~~

Không có response payload không có nghĩa là ứng dụng được bảo đảm đã xử lý thành công. Requester chỉ có thể biết việc gửi ở tầng giao thức đã được thực hiện theo semantics của API; muốn biết nghiệp vụ hoàn tất cần một cơ chế xác nhận riêng.

### Request-Stream

Requester gửi một message ban đầu, responder trả về nhiều message theo thời gian. Trong Spring, response thường là Flux<T>.

~~~text
Requester                  Responder
    |                           |
    | ---- query -------------> |
    | <--- item 1 ------------- |
    | <--- item 2 ------------- |
    | <--- item 3 ------------- |
    | <--- COMPLETE ------------|
~~~

Ví dụ: client yêu cầu dữ liệu cảm biến của một thiết bị và nhận một luồng số đo liên tục.

### Request-Channel

Requester gửi một stream message và đồng thời nhận một stream response. Đây là kiểu hai chiều rõ nhất ở cấp một interaction.

~~~text
Requester                  Responder
    |                           |
    | ---- request stream ----> |
    | <--- response stream ---- |
    | ---- next request ------> |
    | <--- next response ------ |
    | ---- COMPLETE ----------> |
    | <--- COMPLETE ----------- |
~~~

Ví dụ: hai bên cùng gửi các bản cập nhật trong một phiên cộng tác hoặc client gửi mẫu cảm biến liên tục trong khi server trả về các cảnh báo tương ứng.

Request-Channel không phải là hai request-response độc lập được ghép thủ công. Nó là một interaction có hai luồng payload gắn với cùng stream, cùng cơ chế flow control và vòng đời.

## 3. Reactive Streams và back pressure

RSocket mang semantics Reactive Streams qua ranh giới mạng. Với Request-Stream và Request-Channel, requester phát tín hiệu demand để responder biết có thể gửi thêm bao nhiêu phần tử.

Trong Java, Spring dùng các kiểu Reactor quen thuộc:

- Mono<T>: không có hoặc có một phần tử.
- Flux<T>: một luồng có thể chứa nhiều phần tử, kết thúc bình thường, lỗi hoặc không kết thúc.

Requester không nhất thiết phải nhận toàn bộ dữ liệu vào bộ nhớ rồi mới xử lý. Nó có thể yêu cầu từng lượng phần tử, xử lý rồi yêu cầu tiếp. Tín hiệu demand được truyền qua giao thức, giúp responder điều chỉnh tốc độ phát theo khả năng tiêu thụ của requester.

Lợi ích:

- Hạn chế buffer tăng không kiểm soát khi consumer chậm.
- Cho phép xử lý dữ liệu lớn theo luồng.
- Hỗ trợ cancellation khi requester không còn cần kết quả.
- Tạo đường truyền reactive xuyên suốt từ publisher ở ứng dụng responder đến subscriber ở requester.

Back pressure không thay thế mọi biện pháp giới hạn tài nguyên. Ứng dụng vẫn cần giới hạn concurrency, kích thước payload, thời gian xử lý và tài nguyên bên ngoài như database hoặc file.

## 4. Dùng RSocketRequester từ client

Spring cung cấp RSocketRequester như một fluent API để gửi request và mã hóa/giải mã data, metadata.

Ví dụ kết nối TCP:

~~~java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .tcp("localhost", 7000);
~~~

Hoặc kết nối qua WebSocket:

~~~java
import java.net.URI;
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester =
        RSocketRequester.builder()
                .webSocket(URI.create("ws://localhost:8080/rsocket"));
~~~

Việc tạo requester không nhất thiết mở kết nối ngay. Kết nối được thiết lập khi request đầu tiên được thực hiện; requester có thể tái sử dụng connection cho nhiều interaction.

Mẫu gọi request:

~~~java
Mono<ProductView> response = requester
        .route("catalog.product")
        .data(new ProductQuery("SKU-42"))
        .retrieveMono(ProductView.class);
~~~

Các bước:

1. route("catalog.product") đặt route trong metadata của request.
2. data(...) cung cấp payload.
3. retrieveMono(ProductView.class) khai báo kiểu response đơn và trả về Mono<ProductView>.

Nếu responder trả nhiều phần tử, dùng retrieveFlux:

~~~java
Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class);
~~~

Nếu request không cần payload, bỏ qua data():

~~~java
Mono<ServerStatus> status = requester
        .route("system.status")
        .retrieveMono(ServerStatus.class);
~~~

Nếu không cần response payload, dùng send():

~~~java
Mono<Void> sent = requester
        .route("audit.record")
        .data(new AuditEvent("USER_LOGIN", "alice"))
        .send();
~~~

Mono<Void> của send() cho biết việc gửi đã hoàn tất ở tầng API; nó không xác nhận responder đã xử lý thành công sự kiện nghiệp vụ. Nếu cần kết quả xử lý, dùng Request-Response hoặc một cơ chế xác nhận khác.

## 5. Responder ở server bằng @MessageMapping

Spring hỗ trợ annotated responder bằng @MessageMapping. Một phương thức xử lý request có thể nhận payload và trả về Mono hoặc Flux tùy kiểu interaction.

Ví dụ responder ở server:

~~~java
package com.example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;
import reactor.core.publisher.Flux;

@Controller
public class CatalogResponder {

    @MessageMapping("catalog.product")
    public Mono<ProductView> product(ProductQuery query) {
        return productService.find(query.sku());
    }

    @MessageMapping("prices.watch")
    public Flux<PriceUpdate> watch(PriceWatchRequest request) {
        return priceService.watch(request.sku());
    }

    @MessageMapping("audit.record")
    public Mono<Void> record(AuditEvent event) {
        return auditService.append(event);
    }
}
~~~

Ví dụ trên minh họa ba cardinality:

| Payload đầu vào | Giá trị trả về | Interaction |
| --- | --- | --- |
| Một payload | Mono<ProductView> | Request-Response |
| Một payload | Flux<PriceUpdate> | Request-Stream |
| Một payload | Mono<Void> | Fire-and-Forget |

Các service và DTO là thành phần nghiệp vụ của ứng dụng; đoạn controller chỉ minh họa cách Spring ánh xạ route và cardinality. Cần khai báo các kiểu ProductQuery, ProductView, PriceWatchRequest, PriceUpdate và AuditEvent tương ứng trong dự án.

Spring xác định interaction type từ số lượng giá trị đầu vào và đầu ra. Với request-channel, đầu vào là một publisher nhiều phần tử, ví dụ Flux<Event>, và phương thức trả về Flux<Response> hoặc kiểu cardinality khác được giao thức hỗ trợ.

## 6. Server cũng có thể là requester

Tính đối xứng thể hiện rõ khi server muốn chủ động gửi request đến một client đã kết nối.

Trong các phương thức @ConnectMapping hoặc @MessageMapping, Spring có thể cung cấp một RSocketRequester đại diện cho connection tương ứng. Server dùng requester đó để gửi request đến client.

Ví dụ: khi thiết bị kết nối, server yêu cầu thiết bị gửi trạng thái hiện tại:

~~~java
@Controller
public class DeviceConnectionHandler {

    @ConnectMapping("device")
    public Mono<Void> connected(RSocketRequester requester) {
        return Mono.fromRunnable(() ->
                requester.route("device.status")
                        .retrieveMono(DeviceStatus.class)
                        .subscribe(
                                this::recordStatus,
                                this::recordFailure
                        )
        );
    }

    private void recordStatus(DeviceStatus status) {
        // Cập nhật trạng thái thiết bị.
    }

    private void recordFailure(Throwable error) {
        // Ghi nhận lỗi request đến thiết bị.
    }
}
~~~

Ý tưởng quan trọng là request đến client được khởi chạy bất đồng bộ và độc lập với quá trình xử lý SETUP. @ConnectMapping xử lý frame SETUP trước khi các request khác có thể bắt đầu; không nên giữ luồng xử lý SETUP chờ một request RSocket khác hoàn tất.

Trong ứng dụng thực tế, nên quản lý subscription hoặc disposable trả về từ reactive pipeline nếu request là stream dài hạn, đồng thời giải phóng khi connection đóng. Ví dụ trên dùng Request-Response ngắn hạn để minh họa việc server làm requester.

Cũng có thể inject RSocketRequester trong một phương thức @MessageMapping nếu server cần gửi request ngược lại trong khi đang xử lý request từ client.

## 7. Client cũng có thể làm responder

Một client không chỉ gửi request đến server. Nó có thể đăng ký các phương thức @MessageMapping để server gọi ngược lại.

Spring hỗ trợ đăng ký responder phía client bằng RSocketMessageHandler.responder(...) và gắn responder vào RSocketConnector:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientHandler());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
~~~

Lớp xử lý ở client:

~~~java
@Controller
public class ClientHandler {

    @MessageMapping("device.apply-config")
    public Mono<ConfigResult> applyConfig(DeviceConfig config) {
        return deviceService.apply(config);
    }

    @MessageMapping("device.ping")
    public Mono<Pong> ping(Ping request) {
        return Mono.just(new Pong(request.timestamp()));
    }
}
~~~

Sau khi connection được thiết lập, server có thể gửi request route device.apply-config hoặc device.ping đến client. Client trở thành responder cho những request đó, dù nó là bên đã khởi tạo TCP connection.

Khi ứng dụng có nhiều loại controller hoặc nhiều client responder trong cùng ApplicationContext, cần cấu hình predicate nhận diện handler phù hợp để tránh phát hiện nhầm controller. RSocketMessageHandler cho phép điều chỉnh handler predicate.

## 8. Một luồng hai chiều hoàn chỉnh

Giả sử hệ thống quản lý thiết bị có server và thiết bị:

1. Thiết bị mở TCP connection đến server và gửi SETUP.
2. Server xử lý @ConnectMapping để xác thực metadata và tạo trạng thái session.
3. Server lấy RSocketRequester của thiết bị và gửi request device.status.
4. Thiết bị xử lý request bằng ClientHandler.@MessageMapping và trả DeviceStatus.
5. Thiết bị tiếp tục gửi telemetry đến server bằng route device.telemetry.
6. Server xử lý telemetry trong @MessageMapping.
7. Khi phát hiện nhiệt độ vượt ngưỡng, server gửi request device.apply-config.
8. Thiết bị xử lý cấu hình, trả ConfigResult.
9. Hai bên tiếp tục trao đổi các request độc lập trên cùng connection cho đến khi connection đóng.

Trong luồng này, vai trò thay đổi theo từng request. Không cần mở một TCP connection mới chỉ vì server cần gọi một thao tác trên thiết bị.

## 9. Metadata và route

RSocket message có hai phần chính:

- Data: payload nghiệp vụ, thường được mã hóa JSON, CBOR, Protobuf hoặc định dạng khác.
- Metadata: thông tin điều khiển hoặc ngữ cảnh như route, security token, tracing.

Trong Spring, RSocketRequester hỗ trợ thêm metadata:

~~~java
MimeType authMimeType =
        MimeType.valueOf("message/x.rsocket.authentication.bearer.v0");

Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .metadata(accessToken, authMimeType)
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class);
~~~

Route thường được truyền qua routing metadata. Spring RSocketMessageHandler giải mã route để tìm phương thức @MessageMapping phù hợp. Composite metadata cho phép một message chứa nhiều entry metadata độc lập, mỗi entry có MIME type riêng.

Không đưa secret vào route hoặc log. Metadata xác thực cần được mã hóa khi truyền qua mạng, kiểm tra ở phía nhận và không ghi nguyên giá trị token ra log.

## 10. Cấu hình codec và MIME type

Hai đầu cần thống nhất cách mã hóa data và metadata trong SETUP. RSocketRequester.Builder cho phép cấu hình:

- dataMimeType(...): MIME type của data.
- metadataMimeType(...): MIME type của metadata.
- setupData(...): dữ liệu ở SETUP.
- setupRoute(...): route trong metadata SETUP.
- setupMetadata(...): metadata bổ sung ở SETUP.
- rsocketStrategies(...): cấu hình encoder, decoder và metadata extractor.

Spring chỉ đăng ký các codec cơ bản cho String, byte[] và ByteBuffer nếu không bổ sung codec khác. Để gửi DTO JSON hoặc CBOR, ứng dụng cần encoder/decoder tương ứng, thường thông qua spring-web.

Ví dụ cấu hình CBOR:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .build();

RSocketRequester requester = RSocketRequester.builder()
        .rsocketStrategies(strategies)
        .tcp("localhost", 7000);
~~~

Nếu hai đầu dùng MIME type hoặc schema không tương thích, request có thể kết nối thành công nhưng lỗi giải mã payload khi xử lý interaction. Hãy kiểm tra cả cấu hình SETUP và codec được đăng ký trên từng phía.

## 11. Back pressure, cancellation và vòng đời stream

Với Request-Stream và Request-Channel, requester điều khiển demand. Responder không nên phát vô hạn dữ liệu vào một consumer không có khả năng xử lý.

Trong Reactor:

- subscribe() bắt đầu tiêu thụ publisher.
- request(n) là khái niệm demand ở Reactive Streams subscriber.
- cancel() dừng việc tiêu thụ và báo hủy stream.
- onComplete() báo stream kết thúc bình thường.
- onError(error) báo stream kết thúc do lỗi.

Spring và RSocket truyền demand qua giao thức để responder có thể điều tiết số message phát ra. Khi client hủy subscription hoặc timeout, cancellation có thể truyền đến responder và giúp dừng công việc còn lại.

Ví dụ giới hạn số phần tử ở requester:

~~~java
Flux<PriceUpdate> firstTen = requester
        .route("prices.watch")
        .data(new PriceWatchRequest("SKU-42"))
        .retrieveFlux(PriceUpdate.class)
        .take(10);
~~~

take(10) hoàn tất sau khi nhận đủ mười phần tử và hủy phần stream còn lại. Responder nên thiết kế nguồn dữ liệu phản ứng với cancellation để không tiếp tục truy vấn hoặc phát sự kiện không cần thiết.

## 12. Xử lý lỗi và timeout

Lỗi có thể xảy ra ở nhiều tầng:

- Kết nối TCP/WebSocket hoặc SETUP thất bại.
- Không tìm thấy route hoặc responder.
- Payload/metadata không giải mã được.
- Logic nghiệp vụ trả lỗi.
- Request timeout hoặc connection bị đóng giữa stream.
- Client hủy interaction trước khi responder hoàn tất.

Với Reactor, xử lý lỗi ở pipeline:

~~~java
Mono<ProductView> product = requester
        .route("catalog.product")
        .data(new ProductQuery("SKU-42"))
        .retrieveMono(ProductView.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(error -> fallbackProduct());
~~~

Timeout là chính sách phía requester; nó không tự bảo đảm mọi công việc ở responder đã được dừng. Với stream dài hạn, hãy xác định rõ khi nào stream kết thúc, khi nào retry, khi nào reconnect và liệu việc retry có thể gây thực hiện trùng thao tác hay không.

Không retry Fire-and-Forget một cách mù quáng nếu thao tác không idempotent. Nếu request có thể được gửi lại sau timeout, hãy dùng idempotency key hoặc mã sự kiện để responder nhận diện lần gửi trùng.

## 13. Keepalive, session resumption và kết nối dài hạn

RSocket hỗ trợ keepalive để phát hiện kết nối không còn hoạt động. RSocketRequester.Builder cho phép cấu hình sâu hơn thông qua callback rsocketConnector(...), ví dụ keepalive interval, lifetime, interceptors hoặc session resumption.

Session resumption được thiết kế để phục hồi connection sau gián đoạn mạng, nhưng cần duy trì trạng thái giao thức và có giới hạn cấu hình. Không nên giả định rằng mọi request đã hoàn tất hoặc mọi tác dụng phụ nghiệp vụ đều được tự động khôi phục. Ứng dụng vẫn cần thiết kế idempotency, timeout và trạng thái nghiệp vụ.

Đối với kết nối lâu dài:

- Đặt keepalive interval và lifetime phù hợp với môi trường mạng.
- Theo dõi trạng thái connection và giải phóng tài nguyên khi đóng.
- Hạn chế số stream đồng thời nếu mỗi stream tiêu tốn tài nguyên đáng kể.
- Dùng back pressure để kiểm soát nguồn phát.
- Có chính sách reconnect/resume rõ ràng.
- Theo dõi latency, số request lỗi, số stream đang hoạt động và dung lượng buffer.

## 14. Khi nào nên dùng từng interaction?

| Nhu cầu | Interaction | Ví dụ |
| --- | --- | --- |
| Gửi dữ liệu và cần đúng một kết quả | Request-Response | Tra cứu thông tin thiết bị |
| Chỉ phát một sự kiện, không cần response | Fire-and-Forget | Ghi log telemetry không quan trọng |
| Gửi một truy vấn, nhận nhiều kết quả | Request-Stream | Stream số liệu cảm biến |
| Hai phía cùng gửi dữ liệu trong một phiên | Request-Channel | Đồng bộ trạng thái hoặc xử lý luồng tương tác |
| Server cần gọi một thao tác trên client | Server làm requester, client làm responder | Đẩy cấu hình xuống thiết bị |
| Client cần gọi một thao tác trên server | Client làm requester, server làm responder | Đăng ký thiết bị |

Request-Channel là một interaction hai luồng gắn với cùng request. Còn việc server và client khởi tạo các request riêng biệt theo hai hướng là nhiều interaction độc lập trên cùng connection. Hai cách này có thể cùng tồn tại.

## 15. Kiểm thử tính đối xứng hai chiều

Một integration test tốt nên chứng minh cả hai đầu đều có thể khởi tạo request:

1. Khởi chạy RSocket server và đăng ký responder server-side.
2. Kết nối client với server bằng RSocketRequester.
3. Client gửi Request-Response đến route server và xác nhận kết quả.
4. Cấu hình ClientHandler làm responder của client.
5. Server lấy RSocketRequester gắn với connection và gửi request đến route phía client.
6. Xác nhận client xử lý request và trả response.
7. Kiểm thử Request-Stream và xác nhận back pressure/cancellation hoạt động.
8. Đóng connection và xác nhận tài nguyên được giải phóng.
9. Kiểm tra lỗi route không tồn tại, timeout và payload sai MIME type.

Khi kiểm thử đối xứng, không chỉ kiểm tra client có thể gọi server. Phải có ít nhất một test server khởi tạo request đến client để xác nhận client responder đã được đăng ký đúng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Request từ client thành công nhưng server không gọi được client | Chưa đăng ký client responder vào connector | Kiểm tra SocketAcceptor và connector.acceptor(...). |
| Route không khớp | Sai route, sai separator hoặc route matcher | Đối chiếu route trong requester với @MessageMapping. |
| DTO không giải mã được | MIME type hoặc codec hai đầu không tương thích | Kiểm tra dataMimeType, metadataMimeType, Encoder và Decoder. |
| Server request trong @ConnectMapping bị treo | Giữ luồng SETUP chờ request đến client | Khởi chạy request độc lập, không chặn quá trình xử lý SETUP. |
| Stream tiêu thụ quá nhiều bộ nhớ | Responder phát nhanh hơn consumer hoặc thiếu back pressure | Dùng Flux đúng cách, kiểm tra demand và giới hạn buffer. |
| Timeout rồi nghiệp vụ chạy hai lần | Retry một request không idempotent | Dùng idempotency key hoặc sequence/event id. |
| Kết nối mất nhưng ứng dụng vẫn giữ tài nguyên | Không xử lý close/error hoặc không cleanup stream | Theo dõi connection lifecycle và hủy publisher liên quan. |
| Client và server nhầm vai trò | Đồng nhất client với requester, server với responder | Xác định requester/responder theo từng interaction. |

## 17. Ghi nhớ

- Client/server mô tả vai trò mở transport; requester/responder mô tả vai trò trong từng request.
- Sau SETUP, cả hai đầu có thể khởi tạo request trên cùng connection.
- RSocket hỗ trợ Request-Response, Fire-and-Forget, Request-Stream và Request-Channel.
- RSocketRequester là API Spring để gửi request, route, data và metadata.
- Server có thể dùng RSocketRequester gắn với connection để gọi ngược client.
- Client cũng có thể làm responder bằng RSocketMessageHandler.responder(...) và connector.acceptor(...).
- Mono biểu diễn tối đa một response; Flux biểu diễn stream nhiều response.
- Back pressure, cancellation và timeout cần được thiết kế cùng vòng đời stream.
- Tính đối xứng không có nghĩa tự động có exactly-once, durable delivery hoặc retry an toàn.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-requester)
- [Spring Framework — Annotated Responders](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-annotated-responders)
- [Spring Framework — RSocket Interface](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-interface)
- [RSocket Protocol — Specification](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [RSocket Java](https://github.com/rsocket/rsocket-java)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)

