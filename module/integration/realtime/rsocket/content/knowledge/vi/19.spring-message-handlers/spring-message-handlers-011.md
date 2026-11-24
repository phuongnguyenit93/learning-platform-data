# Nhận RSocketRequester trong handler để gọi ngược phía kết nối

RSocket là giao thức hai chiều: sau khi kết nối được thiết lập, cả hai phía đều có thể khởi tạo request. Vì vậy, server không chỉ trả lời request do client gửi đến; server cũng có thể chủ động gọi một route trên client đang kết nối. Trong Spring, các handler `@ConnectMapping` và `@MessageMapping` có thể nhận một tham số `RSocketRequester` đại diện cho chính connection đã mang thông điệp đến handler.

Trong module `INTEGRATION_REALTIME_RSOCKET`, khả năng gọi ngược này hữu ích cho ứng dụng realtime như server yêu cầu client làm mới dữ liệu, gửi lệnh đến thiết bị, đăng ký một luồng sự kiện hoặc hỏi trạng thái client. Bài học trình bày cách nhận requester theo connection, gửi request ngược, đăng ký responder ở client và quản lý vòng đời để không gửi nhầm connection hoặc giữ tài nguyên sau khi peer ngắt kết nối.

## 1. RSocketRequester trong handler là gì?

`RSocketRequester` là API fluent của Spring để gửi request RSocket bằng đối tượng Java và metadata thay vì thao tác trực tiếp với `Payload` và `ByteBuffer`. Nó hoạt động đối xứng: client dùng requester để gọi server, và server có thể dùng requester được cung cấp trong handler để gọi ngược client.

Khi Spring inject `RSocketRequester` vào một phương thức handler, requester đó được gắn với connection đã mang request hoặc connection event đến handler. Nó không phải một requester toàn cục, không phải `RSocketRequester.Builder`, và không đại diện cho một địa chỉ server tùy ý.

```mermaid
flowchart LR
    C[Client] <-->|Một RSocket connection| S[Server]
    C -->|REQUEST: client -> server| H1[@MessageMapping / @ConnectMapping]
    H1 -->|RSocketRequester gắn với connection| R[Server-side requester]
    R -->|REQUEST: server -> client| C
    C -->|Client responder xử lý route| CH[Client @MessageMapping]
```

Điểm quan trọng là server dùng requester của đúng connection để gọi lại peer tương ứng. Nếu có nhiều client cùng kết nối, mỗi connection có requester riêng và có thể có trạng thái, quyền truy cập, subscription khác nhau.

## 2. Vì sao server cần gọi ngược client?

Một số tình huống thực tế:

- Server yêu cầu ứng dụng client tải lại cấu hình hoặc refresh cache.
- Server gửi lệnh điều khiển đến một thiết bị và nhận acknowledgement.
- Server hỏi client về trạng thái giao diện, phiên làm việc hoặc tài nguyên cục bộ.
- Server đăng ký một request-stream từ client để nhận telemetry hoặc sự kiện.
- Hai phía phối hợp một quy trình realtime, trong đó client và server đều có thể khởi tạo request.

Nếu chỉ dùng response của request ban đầu, server bị giới hạn vào thời điểm client gọi trước. Khi server cần gửi lệnh bất kỳ lúc nào trong vòng đời connection, server-side requester là cách tự nhiên hơn.

## 3. Nhận requester trong @ConnectMapping

`@ConnectMapping` xử lý frame `SETUP` ban đầu và các thông báo `METADATA_PUSH` cấp connection. Spring hỗ trợ tham số `RSocketRequester` trong handler này. Đây là nơi phù hợp để xác thực thông tin setup, tạo session context và đăng ký requester theo connection.

Ví dụ:

```java
import reactor.core.Disposable;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.annotation.ConnectMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class ClientConnectionController {

    private final ClientSessionRegistry sessions;

    ClientConnectionController(ClientSessionRegistry sessions) {
        this.sessions = sessions;
    }

    @ConnectMapping("client.connect")
    Mono<Void> onConnect(
            @Payload ClientHello hello,
            RSocketRequester requester) {

        return sessions.register(hello.clientId(), requester)
            .doOnSuccess(session -> {
                Disposable events = startClientEvents(session.connectionId(), requester);
                sessions.attach(session.connectionId(), events);
                watchConnectionClose(session.connectionId(), requester, sessions);
            })
            .then();
    }
}
```

Client gửi route `client.connect` trong metadata của `SETUP` và data chứa `ClientHello`. Handler nhận cả payload lẫn requester gắn với connection đó. `Mono<Void>` đại diện cho quá trình xử lý setup; khi Mono hoàn tất thành công, server chấp nhận connection. Nếu Mono phát lỗi, server có thể từ chối setup.

Trong ví dụ, `sessions.register(...)` là service của ứng dụng trả về `Mono<ClientSession>` sau khi xác thực và tạo connection ID. Sau khi đăng ký thành công, handler khởi chạy luồng sự kiện ngược và đăng ký cleanup theo connection ID. Các thao tác này được tách khỏi Mono dùng để chấp nhận setup.

Phía client gửi setup route và setup data tương ứng:

```java
import org.springframework.messaging.rsocket.RSocketRequester;

RSocketRequester requester = RSocketRequester.builder()
    .setupRoute("client.connect")
    .setupData(new ClientHello("device-17"))
    .rsocketConnector(connector -> connector.acceptor(clientResponder))
    .tcp("localhost", 9898);
```

`clientResponder` là `SocketAcceptor` đã đăng ký các handler client ở phần sau. `setupRoute` và `setupData` được mã hóa theo MIME type cùng codec đã cấu hình cho connection.

`@ConnectMapping` không trả dữ liệu cho client. Nếu cần phản hồi có cấu trúc về một thao tác, hãy dùng request-response hoặc một route nghiệp vụ sau khi connection đã sẵn sàng.

## 4. Không chặn quá trình SETUP bằng request gọi ngược

Handler `@ConnectMapping` xử lý `SETUP`, và việc xử lý này phải hoàn tất trước khi các request ứng dụng bắt đầu. Vì vậy, không nên chờ một request ngược tới client hoàn tất bên trong chính pipeline dùng để chấp nhận setup. Làm như vậy có thể tạo vòng chờ: server đợi client xử lý request, trong khi client chưa thể bắt đầu các request thông thường cho tới khi setup hoàn tất.

Spring yêu cầu request khởi tạo từ tham số `RSocketRequester` phải chạy độc lập với thread xử lý `@ConnectMapping`, ví dụ subscribe trên scheduler khác. Một cách tổ chức là lưu requester và khởi chạy công việc theo dõi ở pipeline riêng:

```java
import reactor.core.Disposable;
import reactor.core.scheduler.Schedulers;

private Disposable startClientEvents(
        String connectionId,
        RSocketRequester requester) {

    return requester.route("client.events")
        .retrieveFlux(ClientEvent.class)
        .subscribeOn(Schedulers.parallel())
        .subscribe(
            event -> eventService.accept(connectionId, event),
            error -> log.warn("Client event stream failed: {}", connectionId, error),
            () -> log.info("Client event stream completed: {}", connectionId)
        );
}
```

`subscribeOn` giúp việc subscribe và request được thực hiện độc lập với thread đang xử lý setup. Subscription được trả về dưới dạng `Disposable` để registry có thể quản lý và hủy khi connection đóng.

Không gọi `block()` trong handler. Cũng không trả `retrieveMono(...)` hoặc `retrieveFlux(...)` của request ngược làm giá trị hoàn tất của `@ConnectMapping`; việc đó khiến setup phụ thuộc vào một request khác.

## 5. Gửi request-response từ server về client

Sau khi có requester của connection, server có thể gọi route mà client đã đăng ký làm responder:

```java
Mono<ClientAck> sendCommand(
        RSocketRequester requester,
        DeviceCommand command) {

    return requester.route("client.command")
        .data(command)
        .retrieveMono(ClientAck.class);
}
```

Các bước tương tự như khi client gọi server:

1. `route(...)` chọn route ở phía peer.
2. `data(...)` cung cấp payload request.
3. `retrieveMono(...)` khai báo kiểu response mong đợi.

Ở đây server là requester cho tương tác mới, còn client là responder. RSocket không bắt buộc client chỉ được gửi request và server chỉ được trả response; vai trò requester/responder được xác định theo từng tương tác.

Nếu không cần acknowledgement nghiệp vụ, server có thể dùng `.send()` cho Fire-and-Forget. `Mono<Void>` từ `send()` chỉ thể hiện thao tác gửi hoàn tất ở phía requester, không chứng minh client đã xử lý lệnh. Nếu cần kết quả, dùng `retrieveMono` hoặc một stream có acknowledgement.

## 6. Client phải đăng ký responder cho route gọi ngược

Server gọi `client.command` chỉ thành công nếu client có responder nhận route đó. Client có thể dùng `@MessageMapping` như server, nhưng phải đăng ký các handler này vào `RSocketConnector` khi tạo connection.

Ví dụ handler ở client:

```java
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
class ClientCommandHandler {

    private final LocalDeviceService deviceService;

    ClientCommandHandler(LocalDeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("client.command")
    Mono<ClientAck> handle(DeviceCommand command) {
        return deviceService.execute(command)
            .map(result -> new ClientAck(command.commandId(), result.accepted()));
    }
}
```

Phía client tạo `SocketAcceptor` từ annotated handler và gắn vào connector:

```java
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.messaging.rsocket.RSocketStrategies;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;
import io.rsocket.SocketAcceptor;

RSocketStrategies strategies = RSocketStrategies.builder()
    .routeMatcher(new PathPatternRouteMatcher())
    .build();

SocketAcceptor clientResponder =
    RSocketMessageHandler.responder(strategies, new ClientCommandHandler(deviceService));

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector -> connector.acceptor(clientResponder))
    .tcp("localhost", 9898);
```

`RSocketMessageHandler.responder(...)` tạo responder từ class có `@MessageMapping` hoặc `@ConnectMapping`; `connector.acceptor(...)` đăng ký responder này vào kết nối client. Nếu client dùng Spring context và có sẵn `RSocketMessageHandler` bean, có thể lấy `handler.responder()` thay vì tạo responder thủ công.

Khi cùng một tiến trình vừa là server vừa là client hoặc có nhiều nhóm client handler, cần cấu hình predicate phát hiện handler phù hợp để tránh đăng ký nhầm controller server thành responder client.

## 7. Gọi ngược dạng request-stream

Server cũng có thể mở stream từ client. Ví dụ server đăng ký nhận các sự kiện client phát trong suốt phiên:

```java
import reactor.core.publisher.Flux;

Flux<ClientEvent> events = requester.route("client.events")
    .retrieveFlux(ClientEvent.class);
```

Client responder trả về `Flux`:

```java
@MessageMapping("client.events")
Flux<ClientEvent> events() {
    return eventSource.events();
}
```

Đây là request-stream do server khởi tạo: server yêu cầu một nguồn dữ liệu từ client và nhận nhiều payload. Backpressure được truyền qua connection; client không nên phát nhanh hơn demand của server. Khi server không còn cần stream, subscription có thể bị cancel và client cần dừng nguồn sự kiện cùng tài nguyên gắn với stream.

Nếu cần dữ liệu hai chiều liên tục trong cùng tương tác, có thể dùng request-channel thay vì tạo nhiều request-stream độc lập.

## 8. Nhận requester trong @MessageMapping

Không chỉ `@ConnectMapping`, handler `@MessageMapping` cũng có thể nhận `RSocketRequester`. Requester đó vẫn đại diện cho connection đã mang request hiện tại đến server.

Ví dụ handler nhận yêu cầu đăng ký theo dõi đơn hàng, hỏi client về tùy chọn hiển thị rồi tạo stream cập nhật:

```java
@Controller
class OrderStreamController {

    private final OrderService orders;

    OrderStreamController(OrderService orders) {
        this.orders = orders;
    }

    @MessageMapping("orders.watch")
    Flux<OrderUpdate> watch(
            OrderFilter filter,
            RSocketRequester requester) {

        return requester.route("client.preferences")
            .retrieveMono(ClientPreferences.class)
            .flatMapMany(preferences -> orders.watch(filter, preferences));
    }
}
```

Trong ví dụ này, request ngược là một phần logic cần thiết trước khi tạo response stream, nên nó được compose trong pipeline trả về của `@MessageMapping`. Cách này khác với `@ConnectMapping`: không có ràng buộc phải hoàn tất `SETUP` trước khi xử lý một request thông thường. Tuy vậy, vẫn cần đặt timeout và xử lý lỗi nếu client không trả lời.

Nếu request ngược chỉ là tác vụ phụ và không quyết định response hiện tại, hãy chạy nó độc lập và quản lý subscription thay vì giữ request của client chờ vô thời hạn.

## 9. Lưu requester theo connection để gửi về sau

Trong một số hệ thống, server cần gửi lệnh đến client tại thời điểm không có request nào từ client đang chạy. Khi đó, có thể lưu requester theo một connection ID trong registry.

Ví dụ một registry đơn giản:

```java
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.Disposable;

class ClientSessionRegistry {

    private final ConcurrentHashMap<String, RSocketRequester> requesters =
        new ConcurrentHashMap<>();
    private final ConcurrentHashMap<String, Disposable> subscriptions =
        new ConcurrentHashMap<>();

    void put(String connectionId, RSocketRequester requester) {
        requesters.put(connectionId, requester);
    }

    RSocketRequester get(String connectionId) {
        return requesters.get(connectionId);
    }

    void attach(String connectionId, Disposable disposable) {
        subscriptions.put(connectionId, disposable);
    }

    void remove(String connectionId) {
        requesters.remove(connectionId);
        Disposable disposable = subscriptions.remove(connectionId);
        if (disposable != null) {
            disposable.dispose();
        }
    }
}
```

Đây là ví dụ tối giản cho một instance server. Production registry cần xử lý thêm trường hợp nhiều connection cùng một principal, requester bị thay thế, cleanup đồng thời và quyền gửi lệnh. Không nên dùng `clientId` làm key duy nhất nếu một người dùng hoặc thiết bị có thể mở nhiều connection. Tạo connection ID riêng và lưu principal/tenant như thuộc tính của session.

Nếu hệ thống chạy nhiều server instance, registry trong bộ nhớ chỉ nhìn thấy các connection đang nằm trên instance đó. Một message broker hoặc connection directory có thể giúp định tuyến lệnh đến đúng instance; bản thân `RSocketRequester` không thể serialize để chuyển sang node khác.

## 10. Cleanup khi connection đóng

Requester được inject chỉ có hiệu lực khi connection tương ứng còn hoạt động. Cần theo dõi `onClose()` của RSocket và gỡ requester cùng các subscription liên quan khi connection kết thúc:

```java
private void watchConnectionClose(
        String connectionId,
        RSocketRequester requester,
        ClientSessionRegistry registry) {

    requester.rsocket().onClose()
        .doFinally(signal -> registry.remove(connectionId))
        .subscribe();
}
```

`onClose()` là tín hiệu vòng đời của connection. `doFinally` giúp cleanup khi connection đóng bình thường hoặc kết thúc do lỗi/cancellation ở publisher tương ứng. Trong hệ thống thật, hàm remove nên idempotent và tránh xóa nhầm requester mới nếu cùng một client reconnect với connection ID mới.

`RSocketRequester.rsocket()` trả về underlying `RSocket` khi requester đang bọc một socket đang hoạt động; với requester được tạo theo một số chế độ client khác, phương thức này có thể trả `null`. Trong trường hợp dùng requester được inject vào handler cho connection đến, nó đại diện cho socket của connection đó. Nếu tái sử dụng helper cleanup với requester tự tạo, hãy kiểm tra null trước khi gọi `onClose()`.

Khi gỡ session, cần giải phóng:

- Requester khỏi registry.
- Subscription request-stream do server mở ngược tới client.
- Timer, heartbeat ứng dụng và listener gắn với connection.
- Pending command hoặc queue riêng của phiên theo chính sách nghiệp vụ.

Không dispose requester của connection khác chỉ vì một client cùng principal đã ngắt kết nối. Mỗi requester có lifecycle riêng.

## 11. Quản lý lỗi và timeout của request gọi ngược

Request ngược có thể thất bại vì client không có route responder, client đóng connection, handler client phát lỗi hoặc timeout. Server nên phân loại lỗi và đặt deadline cho request:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<ClientAck> sendCommand(
        RSocketRequester requester,
        DeviceCommand command) {

    return requester.route("client.command")
        .data(command)
        .retrieveMono(ClientAck.class)
        .timeout(Duration.ofSeconds(5))
        .onErrorResume(error -> {
            log.warn("Command delivery failed: {}", command.commandId(), error);
            return Mono.just(ClientAck.failed(command.commandId(), "CLIENT_UNAVAILABLE"));
        });
}
```

Trong ví dụ, server chuyển lỗi transport hoặc timeout thành kết quả nội bộ. Nếu caller cần phân biệt timeout, route không tồn tại và lỗi nghiệp vụ, hãy ánh xạ exception sang các mã lỗi riêng thay vì gom tất cả thành một mã.

`onErrorResume` chỉ nên dùng khi ứng dụng có kết quả fallback hợp lệ. Không nên biến lỗi bảo mật hoặc lỗi giao thức thành thành công giả. Với lệnh có side effect, timeout không chứng minh client chưa thực hiện lệnh; dùng `commandId` và idempotency để xử lý retry an toàn.

## 12. Bảo mật khi server chủ động gọi client

Server-side requester có thể gửi lệnh đến client, vì vậy cần ràng buộc requester với danh tính và quyền của connection:

- Xác thực client khi setup và lưu principal đã được xác minh trong session context.
- Kiểm tra quyền server được phép gọi route nào trên connection đó.
- Client cũng phải kiểm tra quyền và tính hợp lệ của từng lệnh; không thực thi mù quáng chỉ vì request đến từ connection RSocket.
- Không dùng client ID hoặc tenant ID do payload tự khai báo làm bằng chứng danh tính.
- Giới hạn kích thước payload, tần suất lệnh và số request đồng thời.
- Không ghi token, dữ liệu cá nhân hoặc payload nhạy cảm vào log khi request lỗi.

Nếu một principal có nhiều connection, cần xác định lệnh gửi đến tất cả connection, connection mới nhất hay một thiết bị cụ thể. Chính sách chọn đích phải rõ ràng và được kiểm tra quyền trước khi gửi.

## 13. Backpressure và giới hạn đồng thời

Request ngược dùng cùng các mô hình tương tác RSocket như request-response, request-stream, fire-and-forget và request-channel. Với stream, demand được truyền từ subscriber sang publisher qua connection. Server không nên mở vô hạn stream ngược hoặc tạo quá nhiều request đồng thời cho một client.

Các biện pháp hữu ích:

- Giới hạn số request-response đang chờ trên mỗi connection.
- Dùng `flatMap(..., concurrency)` với concurrency phù hợp khi gọi nhiều client.
- Dùng `concatMap` nếu lệnh cần giữ thứ tự.
- Hủy subscription stream khi client rời connection hoặc không còn quyền.
- Giới hạn queue và thời gian chờ acknowledgement.

Backpressure điều tiết dữ liệu trong stream; nó không thay thế quota nghiệp vụ theo client hoặc tenant. Nếu cần giới hạn số lệnh mỗi phút, hãy dùng rate limit riêng.

## 14. Kiểm thử gọi ngược qua RSocket

Một kiểm thử tích hợp cần có cả requester và responder. Nếu chỉ tạo `RSocketRequester` phía server mà client không đăng ký route responder, request ngược sẽ không có nơi xử lý.

Các trường hợp nên kiểm thử:

- `@ConnectMapping` nhận đúng requester của connection vừa setup.
- Server gửi request-response đến route client và nhận `ClientAck`.
- Server mở request-stream từ client và nhận nhiều event theo demand.
- Client không đăng ký route thì server nhận lỗi rõ ràng.
- Handler client phát lỗi hoặc không trả lời đúng timeout.
- Connection đóng thì requester và subscription được gỡ khỏi registry.
- Hai connection cùng principal không ghi đè hoặc cleanup nhầm requester của nhau.
- Client reconnect tạo connection ID mới và registry cập nhật đúng.
- Lệnh gửi lại với cùng `commandId` không tạo side effect trùng.
- Client từ chối lệnh không có quyền dù route đã được đăng ký.

Ví dụ kiểm tra logic tạo request ngược bằng `StepVerifier`:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ServerCommandServiceTest {

    // commandService và connectedClientRequester là fixture của bài kiểm thử.

    @Test
    void returnsClientAcknowledgement() {
        Mono<ClientAck> result = commandService.sendCommand(
            connectedClientRequester,
            new DeviceCommand("cmd-17", "device-4", "refresh")
        );

        StepVerifier.create(result)
            .assertNext(ack -> {
                assertEquals("cmd-17", ack.commandId());
                assertTrue(ack.accepted());
            })
            .verifyComplete();
    }
}
```

Test trên giả định `connectedClientRequester` đã được tạo từ kết nối test có client responder thật hoặc test double tương thích. Để xác minh wiring đầy đủ, hãy chạy RSocket server trên TCP/WebSocket test transport, đăng ký responder phía client và gọi route qua connection thực.

## 15. Những lỗi thường gặp

**Nhầm RSocketRequester với builder.** Tham số trong handler là requester gắn với connection hiện tại; builder dùng để tạo connection đi ra.

**Cho rằng server không thể khởi tạo request.** Sau khi connection được thiết lập, hai phía đều có thể là requester hoặc responder cho từng interaction.

**Không đăng ký responder phía client.** Server gửi route ngược nhưng client không có `@MessageMapping` hoặc acceptor phù hợp nên request thất bại.

**Chờ request ngược trong @ConnectMapping.** Handler này xử lý `SETUP`; request gọi ngược phải chạy độc lập với thread xử lý setup và không được giữ setup chờ response đó.

**Lưu requester thành singleton dùng chung.** Requester thuộc một connection cụ thể. Lưu theo connection ID và quản lý nhiều connection trên cùng principal.

**Không cleanup khi connection đóng.** Requester và stream ngược có thể giữ subscription hoặc tài nguyên. Theo dõi `onClose()` và hủy các tài nguyên liên quan.

**Xem Mono<Void> từ send() là acknowledgement.** Nó chỉ cho biết thao tác gửi hoàn tất ở requester; dùng request-response nếu cần kết quả xử lý.

**Retry lệnh sau timeout mà không idempotent.** Client có thể đã thực hiện lệnh nhưng response bị mất. Dùng command ID và cơ chế chống thực thi trùng.

## 16. Ghi nhớ

- `@ConnectMapping` và `@MessageMapping` có thể nhận `RSocketRequester` đại diện cho connection đã mang sự kiện/request đến handler.
- `RSocketRequester` dùng đối xứng ở client và server; server có thể chủ động gọi route trên client.
- `@ConnectMapping` xử lý `SETUP` và Metadata Push, trả `void` hoặc `Mono<Void>`; lỗi trong setup có thể khiến connection bị từ chối.
- Request gọi ngược trong `@ConnectMapping` phải chạy độc lập với thread xử lý setup; không block hoặc chờ response ngược trong pipeline chấp nhận connection.
- Client phải đăng ký responder bằng `@MessageMapping` và gắn `SocketAcceptor` vào `RSocketConnector`.
- `retrieveMono`/`retrieveFlux` dùng khi cần response; `send()` chỉ gửi Fire-and-Forget và không xác nhận nghiệp vụ.
- Lưu requester theo connection ID nếu cần gửi lệnh về sau; không dùng một requester toàn cục cho nhiều client.
- Theo dõi `requester.rsocket().onClose()` để cleanup requester và subscription gắn với connection.
- Áp dụng timeout, authorization, backpressure, giới hạn concurrency và idempotency cho các lệnh gọi ngược.

## Tài liệu tham khảo

- [Spring Framework Reference — Server Requester và RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference — Annotated Responders và @ConnectMapping](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework API — ConnectMapping](https://docs.spring.io/spring-framework/docs/6.0.9/javadoc-api/org/springframework/messaging/rsocket/annotation/ConnectMapping.html)
- [Spring Boot Reference — Calling RSocket Services with RSocketRequester](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
