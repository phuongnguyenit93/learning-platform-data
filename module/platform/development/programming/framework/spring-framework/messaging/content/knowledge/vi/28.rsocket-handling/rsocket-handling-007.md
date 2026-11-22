# Xử lý yêu cầu ngược từ server tới client trong Spring RSocket

## Mục tiêu

Trong nhiều ứng dụng RSocket, client thường mở kết nối tới server rồi gửi yêu cầu. Tuy nhiên, sau khi kết nối được thiết lập, server cũng có thể chủ động gửi yêu cầu qua chính kết nối đó để lấy dữ liệu, yêu cầu client thực hiện một hành động hoặc gửi thông báo. Đây là mô hình giao tiếp hai chiều của RSocket.

Spring Framework hỗ trợ chiều giao tiếp này thông qua `RSocketRequester` ở phía server và một responder được đăng ký ở phía client. Phần quan trọng là hiểu đúng vai trò requester/responder sau khi kết nối được thiết lập, lấy đúng `RSocketRequester` gắn với từng kết nối và cấu hình handler phía client để nhận route do server gửi.

## Vì sao server có thể gửi yêu cầu tới client?

RSocket là giao thức giao tiếp hai chiều, đa luồng (multiplexed) và full-duplex. Client là bên khởi tạo kết nối ở tầng transport và gửi frame `SETUP`, nhưng sau khi kết nối được chấp nhận, sự phân biệt client/server không còn giới hạn bên nào được gửi request. Mỗi đầu có thể trở thành requester hoặc responder tùy theo từng request.

Ví dụ, sau khi client kết nối tới server:

1. Client gửi request `inventory.lookup` tới server; server xử lý và trả kết quả.
2. Server có thể gửi request `client.health` ngược lại trên cùng kết nối; client xử lý và trả trạng thái.
3. Server có thể gửi một thông báo một chiều tới client bằng Fire-and-Forget.
4. Hai bên có thể mở các luồng dữ liệu hai chiều bằng Request-Channel.

Không cần mở thêm kết nối TCP hoặc WebSocket chỉ để server gửi dữ liệu ngược. Server dùng kết nối RSocket đang hoạt động và gửi request bằng vai trò requester.

## Bốn kiểu tương tác và chiều dữ liệu

RSocket định nghĩa bốn kiểu request chính. Khi server là requester và client là responder, chiều dữ liệu được hiểu như sau:

| Kiểu tương tác | Server gửi | Client trả về | Cách gọi phổ biến ở server |
| --- | --- | --- | --- |
| Request-Response | Một payload | Một kết quả | `retrieveMono(Type.class)` |
| Request-Stream | Một payload | Một luồng kết quả | `retrieveFlux(Type.class)` |
| Fire-and-Forget | Một payload | Không có response payload | `send()` |
| Request-Channel | Một luồng payload | Có thể trả về một luồng kết quả | `data(Flux, elementType)` và `retrieveFlux(...)` |

Request-Stream có nghĩa server gửi một yêu cầu rồi nhận một `Flux` từ client. Nếu mục tiêu là server gửi nhiều phần tử dữ liệu sang client, cần chọn Request-Channel hoặc gửi nhiều request một chiều; không nên nhầm `retrieveFlux` với việc server đang phát một luồng payload đi.

## Các thành phần Spring liên quan

- `RSocketRequester`: API fluent để gửi request qua một kết nối RSocket. API này có thể dùng đối xứng ở client và server.
- `@ConnectMapping`: xử lý frame `SETUP` ban đầu và các metadata push ở cấp kết nối. Ở phía server, phương thức có thể nhận `RSocketRequester` đại diện cho kết nối vừa được thiết lập.
- `@MessageMapping`: xử lý request có route. Phương thức ở server hoặc client đều có thể nhận `RSocketRequester` để chủ động gửi request về đầu bên kia.
- `RSocketMessageHandler`: phát hiện và gọi các phương thức responder được đánh dấu bằng `@MessageMapping` hoặc `@ConnectMapping`.
- `RSocketMessageHandler.responder(...)`: tạo `SocketAcceptor` từ các handler để đăng ký responder ở phía client.
- `RSocketStrategies`: cấu hình encoder, decoder, route matcher và metadata extractor cho requester/responder. Hai đầu phải có codec tương thích với định dạng dữ liệu truyền qua mạng.

`@ConnectMapping` không phải là handler cho mọi thông điệp từ client. Nó dành cho sự kiện thiết lập kết nối và metadata push. Các request nghiệp vụ có route được xử lý bằng `@MessageMapping`.

## Bước 1: Đăng ký responder ở phía client

Client phải khai báo route mà server sẽ gọi. Ví dụ sau tạo một responder xử lý route `client.health` và trả về một chuỗi trạng thái:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import reactor.core.publisher.Mono;

public class ClientResponder {

    @MessageMapping("client.health")
    public Mono<String> health(String command) {
        return Mono.just("READY: " + command);
    }
}
```

Đăng ký handler vào `RSocketRequester.Builder` thông qua `SocketAcceptor`: 

```java
import io.rsocket.SocketAcceptor;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

RSocketStrategies strategies = RSocketStrategies.builder()
        .routeMatcher(new PathPatternRouteMatcher())
        .build();

SocketAcceptor clientResponder =
        RSocketMessageHandler.responder(strategies, new ClientResponder());

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(clientResponder))
        .tcp("localhost", 7000);
```

Đây là cách đăng ký handler theo chương trình. `RSocketMessageHandler.responder(strategies, ...)` nhận các object có phương thức annotated và tạo responder. Các object được truyền trực tiếp không bắt buộc phải có stereotype `@Controller`. `PathPatternRouteMatcher` cần `spring-web`; nếu không dùng `spring-web`, có thể giữ route matcher mặc định.

`RSocketRequester` ở đoạn code này là requester của client, dùng để client gửi request lên server. Cùng lúc đó, `clientResponder` cho phép server gửi request ngược về client trên chính kết nối này. Hai khả năng được cấu hình trên cùng một RSocket connection.

Kết nối thường được thiết lập khi có request đầu tiên. Client phải đăng ký responder trước khi kết nối được dùng để server có thể tìm thấy route tương ứng.

### Đăng ký handler qua Spring bean

Trong ứng dụng Spring, cũng có thể khai báo `RSocketMessageHandler` làm bean rồi truyền `handler.responder()` vào connector:

```java
RSocketMessageHandler handler = applicationContext.getBean(RSocketMessageHandler.class);

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector.acceptor(handler.responder()))
        .tcp("localhost", 7000);
```

Khi client có nhiều nhóm handler hoặc chạy chung context với các handler phía server, cần chú ý predicate mà `RSocketMessageHandler` dùng để phát hiện handler. Có thể cấu hình `setHandlerPredicate` hoặc dùng một stereotype riêng để tránh đăng ký nhầm handler của server thành responder của client.

## Bước 2: Lấy requester của client ở phía server

Trong các phương thức `@ConnectMapping` và `@MessageMapping` phía server, Spring hỗ trợ inject một `RSocketRequester` đại diện cho đầu client của kết nối hiện tại. Server dùng instance này để gửi request tới client tương ứng.

Ví dụ sau gọi route `client.health` ngay sau khi client kết nối:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ClientConnectionHandler {

    @ConnectMapping
    public Mono<Void> onConnect(RSocketRequester requester) {
        requester.route("client.health")
                .data("initial-check")
                .retrieveMono(String.class)
                .subscribe(
                        status -> System.out.println("Client status: " + status),
                        error -> System.err.println("Client request failed: " + error.getMessage()));

        return Mono.empty();
    }
}
```

`requester.route("client.health")` đặt route trong metadata của request. `.data(...)` đặt payload gửi sang client. `.retrieveMono(String.class)` khai báo server mong nhận một response kiểu `String`. Phương thức `health` ở `ClientResponder` nhận payload và tạo response tương ứng.

### Lưu ý đặc biệt với @ConnectMapping

`@ConnectMapping` xử lý frame `SETUP`; server hoàn tất việc xử lý frame này trước khi request mới có thể bắt đầu trên kết nối. Vì vậy, request ngược khởi chạy ngay lúc kết nối phải được tách khỏi luồng xử lý setup. Ví dụ dùng `subscribe(...)` để khởi chạy request độc lập, sau đó trả `Mono<Void>` hoàn tất xử lý kết nối.

Không ghép request ngược vào `Mono<Void>` trả về của `@ConnectMapping` theo cách chờ response từ client trước khi hoàn tất setup. Cách đó có thể tạo vòng chờ: setup chưa hoàn tất nên request chưa được phép bắt đầu, trong khi setup lại đang chờ response của request đó.

Việc gọi `subscribe()` là điểm chủ động khởi chạy publisher. Vì vậy, cần cung cấp callback xử lý lỗi, ghi log phù hợp và quản lý vòng đời subscription. Với logic cần được điều phối lâu dài, hãy chuyển việc gửi request sang một service quản lý phiên kết nối thay vì để callback setup tự quản lý toàn bộ nghiệp vụ.

## Bước 3: Gửi request từ server sau khi kết nối đã hoạt động

Khi kết nối đã được thiết lập, một phương thức `@MessageMapping` phía server cũng có thể nhận `RSocketRequester`. Ví dụ server xử lý một request đến và đồng thời gọi ngược client để kiểm tra trạng thái:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class ServerOperationsHandler {

    @MessageMapping("server.check-client")
    public Mono<String> checkClient(String command, RSocketRequester requester) {
        return requester.route("client.health")
                .data(command)
                .retrieveMono(String.class);
    }
}
```

Khác với ví dụ `@ConnectMapping`, ở đây server có thể trả trực tiếp publisher của request ngược vì kết nối đã hoạt động. Spring sẽ subscribe vào `Mono` trả về để tạo response cho request ban đầu. Ví dụ này phù hợp khi việc gọi client là một phần của quá trình xử lý request đang đến server.

## Bước 4: Chọn cách gửi thông báo hoặc yêu cầu có phản hồi

### Request-Response khi cần xác nhận từ client

```java
Mono<String> result = requester.route("client.health")
        .data("ping")
        .retrieveMono(String.class);
```

Client xử lý route bằng `Mono<String>`. Server chỉ nhận được kết quả khi client trả response. Đây là lựa chọn phù hợp cho lệnh cần kết quả hoặc xác nhận nghiệp vụ.

### Fire-and-Forget khi chỉ cần gửi một thông báo

```java
Mono<Void> sent = requester.route("client.notification")
        .data("A new task is available")
        .send();
```

Client có thể xử lý route bằng một phương thức trả `void` hoặc `Mono<Void>`. `send()` hoàn tất khi message đã được gửi theo giao thức; nó không chứng minh rằng client đã thực thi xong handler. Nếu cần xác nhận đã nhận hoặc đã xử lý, dùng Request-Response và trả một kiểu `Acknowledgement` rõ ràng.

### Request-Stream khi server cần nhận một luồng phản hồi từ client

```java
Flux<String> reports = requester.route("client.reports")
        .data("collect")
        .retrieveFlux(String.class);
```

Client responder trả `Flux<String>`. Đây là luồng response đi từ client về server sau một request ban đầu của server. Backpressure được truyền qua RSocket để server điều tiết tốc độ tiêu thụ.

### Request-Channel khi hai bên cần trao đổi luồng

Request-Channel cho phép server gửi một luồng payload và đồng thời nhận một luồng response từ client. Ở phía server, có thể dùng overload `data(producer, elementClass)` để khai báo kiểu phần tử khi gửi một `Flux`:

```java
Flux<Acknowledgement> acknowledgements = requester.route("client.process-events")
        .data(events, Event.class)
        .retrieveFlux(Acknowledgement.class);
```

Ở phía client, handler tương ứng có thể nhận `Flux<Event>` và trả `Flux<Acknowledgement>`. Hai luồng tuân theo backpressure. Chỉ chọn channel khi cả chiều request và chiều response đều có ý nghĩa trong nghiệp vụ.

## Bước 5: Quản lý nhiều kết nối client

`RSocketRequester` nhận trong handler gắn với một kết nối cụ thể. Nếu server cần gửi yêu cầu từ một service hoặc tác vụ nền không nằm trong `@ConnectMapping` hay `@MessageMapping`, ứng dụng thường cần một registry lưu requester theo phiên kết nối.

Một cách tổ chức thường gặp:

1. Khi nhận kết nối mới, xác thực thông tin client từ cơ chế bảo mật hoặc metadata setup.
2. Lưu requester của kết nối vào registry theo định danh client và mã phiên kết nối duy nhất.
3. Khi có sự kiện nghiệp vụ, tìm đúng requester rồi gửi route phù hợp.
4. Khi kết nối đóng, xóa entry tương ứng để tránh giữ requester đã hết hiệu lực.
5. Khi client kết nối lại, cập nhật phiên mới và tránh để phiên cũ ghi đè hoặc xóa nhầm phiên mới.

Không dùng một biến `RSocketRequester` toàn cục cho tất cả client. Mỗi client có một kết nối và một responder riêng; gửi qua requester của client A sẽ định tuyến request tới client A. Nếu cùng một người dùng mở nhiều thiết bị, khóa registry chỉ bằng user ID có thể làm mất một kết nối. Có thể dùng khóa gồm user ID và connection/session ID.

`@ConnectMapping` giúp xử lý setup nhưng không phải callback đóng kết nối. Cần dùng cơ chế vòng đời kết nối của RSocket server hoặc transport để phát hiện đóng và dọn registry. `RSocketRequester` cũng là một `Disposable`; gọi `dispose()` sẽ đóng kết nối tương ứng, vì vậy không gọi nó chỉ để xóa một entry khỏi map.

## Data, metadata và khả năng tương thích codec

Route được gửi trong metadata của request. Payload nghiệp vụ nằm trong phần data. Hai đầu cần thống nhất data MIME type và có encoder/decoder tương ứng với kiểu dữ liệu.

- Các kiểu cơ bản như `String`, `byte[]` và `ByteBuffer` được hỗ trợ bởi codec cơ bản của Spring.
- Với DTO, đăng ký codec phù hợp như JSON, CBOR hoặc Protobuf trong `RSocketStrategies` ở cả client và server.
- Nếu dùng composite metadata để gửi token, trace context hoặc metadata tùy chỉnh, phía nhận cần có metadata extractor và decoder tương ứng.
- Route mà server gọi phải khớp chính xác với `@MessageMapping` ở client. Route là tên phân cấp, không phải URL HTTP; mặc định dấu chấm (`.`) là ký tự phân cấp.
- MIME type được khai báo ở cấp kết nối trong `SETUP`; thay đổi codec hoặc định dạng payload ở một phía phải được phản ánh ở phía còn lại.

Ví dụ trong bài dùng `String` để tập trung vào luồng hai chiều và tận dụng codec cơ bản. Khi thay bằng DTO, cần cấu hình encoder/decoder cho DTO ở cả hai phía trước khi gửi.

## Bảo mật khi server gọi ngược client

Request ngược có thể kích hoạt hành động trên thiết bị hoặc ứng dụng client, vì vậy cần áp dụng chính sách xác thực và phân quyền cho cả chiều request này:

- Xác thực kết nối và thông tin định danh client trước khi đưa requester vào registry.
- Chỉ gửi route mà client được phép thực hiện; kiểm tra quyền ở cả phía server và client.
- Không coi `clientId` do client tự gửi trong metadata là danh tính đáng tin cậy nếu chưa được xác thực.
- Tránh gửi access token hoặc dữ liệu nhạy cảm trong payload/log nếu không cần thiết.
- Giới hạn kích thước payload, tần suất request và số lượng stream đang hoạt động theo khả năng của client.
- Xử lý reconnect, timeout, lỗi transport và client offline; không giả định requester luôn còn hoạt động.

## Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| Server gọi route nhưng client báo không tìm thấy handler | Client chưa đăng ký `SocketAcceptor`, hoặc route không khớp | Kiểm tra `connector.acceptor(...)`, `RSocketMessageHandler.responder(...)` và tên `@MessageMapping`. |
| Client có handler nhưng server không gọi được | Handler chưa được đưa vào responder đang dùng cho kết nối | Kiểm tra đúng `RSocketRequester.Builder` và đúng connector đã gắn acceptor. |
| Request ngược thất bại ngay khi client vừa kết nối | Server đang chờ request ngược trong lúc xử lý `SETUP` | Tách request khỏi publisher hoàn tất `@ConnectMapping`; không chờ response client trong bước setup. |
| Gửi được nhưng không biết client đã xử lý chưa | Đang dùng Fire-and-Forget | Dùng Request-Response với acknowledgement nếu cần xác nhận nghiệp vụ. |
| Không giải mã được DTO | Codec hoặc MIME type hai đầu không tương thích | Kiểm tra `RSocketStrategies`, encoder/decoder và MIME type đã thương lượng trong `SETUP`. |
| Server gửi nhầm thiết bị | Registry dùng khóa không duy nhất hoặc giữ requester cũ | Quản lý theo connection/session ID và cập nhật khi reconnect. |
| Gửi request tới client đã ngắt kết nối | Registry chưa dọn entry hoặc requester đã đóng | Xử lý lỗi transport, kiểm tra vòng đời kết nối và loại bỏ phiên đã đóng. |
| Stream tăng bộ nhớ hoặc chậm dần | Không xử lý backpressure hoặc giữ subscription không giới hạn | Dùng `Flux` có giới hạn, xử lý cancellation và quản lý số stream đồng thời. |

## Checklist triển khai

- Client đăng ký responder bằng `RSocketMessageHandler.responder(...)` hoặc một `RSocketMessageHandler` bean được gắn vào connector.
- Route ở server trùng với route `@MessageMapping` trên client.
- Server lấy `RSocketRequester` theo đúng kết nối cần gọi.
- Request phát sinh trong `@ConnectMapping` được tách khỏi quá trình hoàn tất `SETUP`.
- Kiểu tương tác được chọn đúng: Request-Response, Request-Stream, Fire-and-Forget hoặc Request-Channel.
- Hai đầu có codec và MIME type tương thích.
- Registry có định danh phiên duy nhất và dọn requester khi kết nối đóng.
- Có xử lý lỗi, reconnect, timeout, cancellation, backpressure và quyền truy cập.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — mục RSocketRequester, Server Requester, Client Responders và Annotated Responders.
- [Spring Framework Javadoc — RSocketMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html) — tạo responder và đăng ký handler.
- [Spring Framework Javadoc — RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html) — API gửi request và quản lý requester.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — mô hình giao tiếp hai chiều, các frame request và metadata.