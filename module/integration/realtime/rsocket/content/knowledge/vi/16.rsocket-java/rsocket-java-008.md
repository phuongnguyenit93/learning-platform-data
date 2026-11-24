# Cung cấp responder phía mở kết nối để nhận yêu cầu ngược

RSocket là giao thức hai chiều. Client thường là bên chủ động mở kết nối và gửi request tới server, nhưng sau khi phiên RSocket được thiết lập, server cũng có thể gửi request ngược lại client trên cùng kết nối. Muốn nhận các request đó, client phải cung cấp một responder ngay trong quá trình tạo kết nối.

Với RSocket Java, điểm cấu hình quan trọng là phương thức acceptor trên RSocketConnector. Acceptor trả về một đối tượng RSocket hoặc AbstractRSocket để xử lý các tương tác do peer khởi tạo. Ở phía server, SocketAcceptor cũng nhận một RSocket đại diện cho khả năng gửi request tới client. Hai thành phần này tạo nên hai chiều requester/responder của cùng một phiên.

## 1. Hiểu đúng vai trò hai phía

Tên gọi client và server mô tả cách kết nối được thiết lập và nơi dịch vụ thường lắng nghe. Chúng không giới hạn chiều khởi tạo request sau khi kết nối RSocket đã sẵn sàng.

- Client mở TCP hoặc WebSocket tới server, gửi SETUP và thường dùng RSocket mà connector trả về để gọi các route phía server.
- Client đồng thời cung cấp responder qua RSocketConnector.acceptor(...). Responder này nhận request do server chủ động gửi tới client.
- Server cung cấp responder qua SocketAcceptor để nhận request từ client.
- Trong SocketAcceptor phía server, tham số sendingSocket cho phép server gửi request ngược lại client.

~~~mermaid
flowchart LR
    subgraph Client
        CR[Requester tới server]
        CP[Responder của client]
    end
    subgraph Server
        SR[Responder của server]
        SP[Requester tới client]
    end
    CR -->|Request do client khởi tạo| SR
    SR -->|Response| CR
    SP -->|Request ngược do server khởi tạo| CP
    CP -->|Response| SP
~~~

Do đó, một kết nối RSocket có hai hướng request độc lập. Mỗi hướng có stream ID và vòng đời tương tác riêng. Client không cần mở thêm một kết nối TCP thứ hai chỉ để nhận request từ server.

## 2. RSocketConnector.acceptor(...) ở phía client

RSocketConnector là thành phần tạo kết nối RSocket phía client trong RSocket Java. Phương thức connect(...) mở transport và thiết lập phiên. Phương thức acceptor(...) đăng ký responder cục bộ mà peer có thể gọi sau khi phiên sẵn sàng.

Ví dụ client cung cấp responder xử lý một request-response từ server:

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.RSocketConnector;
import io.rsocket.util.DefaultPayload;
import io.rsocket.transport.netty.client.TcpClientTransport;
import reactor.core.publisher.Mono;

RSocket clientRequester = RSocketConnector.create()
    .acceptor((setup, sendingSocket) ->
        Mono.just(new AbstractRSocket() {
            @Override
            public Mono<Payload> requestResponse(Payload request) {
                String command = request.getDataUtf8();

                if ("client.status".equals(command)) {
                    return Mono.just(DefaultPayload.create(
                        "CLIENT_READY"
                    ));
                }

                return Mono.error(new IllegalArgumentException(
                    "Unsupported command: " + command
                ));
            }
        })
    )
    .connect(TcpClientTransport.create("localhost", 7000))
    .block();
~~~

Đoạn code có hai vai trò khác nhau:

- Giá trị trả về từ connect(...) là RSocket requester mà client dùng để gửi request tới server.
- AbstractRSocket được trả về từ acceptor(...) là responder của client, xử lý request do server gửi ngược lại.

Tham số setup cung cấp thông tin phiên mà server gửi trong quá trình SETUP. Tham số sendingSocket trong callback phía client là requester để client gửi request tới server trong lúc thiết lập responder. Nếu ví dụ không cần khởi tạo request ngược ngay lúc kết nối, có thể không sử dụng tham số này.

Acceptor được gọi trong quá trình thiết lập kết nối để cung cấp responder cho phiên đó. Server chỉ nên gửi request ngược sau khi quá trình setup hoàn tất và phiên đã sẵn sàng; phía client có thể chờ publisher connect(...) phát ra RSocket trước khi sử dụng requester trả về.

Không nhầm acceptor(...) với SocketAcceptor phía server. Cả hai đều cung cấp responder, nhưng chúng được cấu hình ở hai phía khác nhau của kết nối.

## 3. Server gửi request ngược lại client

Ở phía server, SocketAcceptor nhận hai đối số: thông tin SETUP và một RSocket có thể dùng để gửi request tới peer. Server trả về AbstractRSocket để xử lý request do client khởi tạo, đồng thời có thể lưu requester tới client để dùng khi cần gọi ngược.

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

RSocketServer.create((setup, sendingSocket) -> {
    // Đăng ký requester riêng của kết nối này để service có thể gọi client.
    clientPeerRegistry.register(sendingSocket);

    return Mono.just(new AbstractRSocket() {
        @Override
        public Mono<Payload> requestResponse(Payload request) {
            String query = request.getDataUtf8();
            return Mono.just(DefaultPayload.create(
                "SERVER_HANDLED:" + query
            ));
        }
    });
})
.bind(TcpServerTransport.create("0.0.0.0", 7000))
.block();
~~~

clientPeerRegistry là thành phần quản lý kết nối do ứng dụng định nghĩa. Mỗi kết nối cần một requester riêng; không dùng chung một RSocket của client này để gửi request tới client khác. Khi phiên đóng, cần xóa requester tương ứng khỏi registry để tránh giữ tham chiếu tới kết nối đã hết hiệu lực.

Khi một sự kiện nghiệp vụ cần hỏi client, service lấy requester của đúng kết nối rồi gọi requestResponse(...):

~~~java
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

Mono<String> askClientForStatus(RSocket clientRequester) {
    return clientRequester
        .requestResponse(DefaultPayload.create("client.status"))
        .map(Payload::getDataUtf8);
}
~~~

Request này đi tới phương thức requestResponse(...) trong AbstractRSocket mà client đã đăng ký ở phần trước. Response quay lại server dưới dạng Payload và được chuyển thành String trong pipeline reactive.

Trong ứng dụng thực tế, không nên gọi subscribe() tùy tiện bên trong handler chỉ để kích hoạt request ngược. Hãy trả publisher cho tầng gọi hoặc ghép nó vào pipeline đang xử lý để lỗi, timeout và vòng đời tương tác được quản lý tập trung.

## 4. Phân biệt hai loại RSocket trong callback

Các tham số có tên gần giống nhau dễ gây nhầm hướng. Hãy xác định chúng theo nơi callback chạy:

| Vị trí callback | RSocket được truyền vào | Dùng để làm gì? |
|---|---|---|
| Client: RSocketConnector.acceptor(...) | sendingSocket | Client gửi request tới server |
| Server: RSocketServer.create(SocketAcceptor) | sendingSocket | Server gửi request tới client |
| Client: RSocketConnector.acceptor(...) trả về | AbstractRSocket | Client nhận request từ server |
| Server: SocketAcceptor trả về | AbstractRSocket | Server nhận request từ client |
| Kết quả client connect(...) | RSocket | Client gửi request tới server sau khi kết nối thành công |

Tên sendingSocket chỉ hướng gửi từ phía đang chạy callback tới peer. Đối tượng RSocket được trả về từ acceptor là responder cho chiều ngược lại. Cách nhìn này giúp xác định đúng hướng khi đọc API và tránh gọi nhầm phương thức trên đối tượng không đúng vai trò.

## 5. Nhận nhiều kiểu tương tác từ server

AbstractRSocket cho phép override các phương thức tương ứng với những kiểu tương tác RSocket. Nếu server gửi request-response, client triển khai requestResponse(...). Nếu server gửi request-stream, client triển khai requestStream(...). Tương tự, fire-and-forget và request-channel có phương thức xử lý riêng.

Ví dụ client trả về một luồng dữ liệu khi server yêu cầu:

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

AbstractRSocket clientResponder = new AbstractRSocket() {
    @Override
    public Mono<Payload> requestResponse(Payload request) {
        return Mono.just(DefaultPayload.create(
            "ACK:" + request.getDataUtf8()
        ));
    }

    @Override
    public Flux<Payload> requestStream(Payload request) {
        String topic = request.getDataUtf8();
        return Flux.just(
            DefaultPayload.create(topic + ":event-1"),
            DefaultPayload.create(topic + ":event-2"),
            DefaultPayload.create(topic + ":event-3")
        );
    }
};
~~~

Ví dụ cho thấy responder có thể xử lý nhiều kiểu tương tác. Trong ứng dụng thật, dữ liệu stream thường đến từ service reactive hoặc event source thay vì Flux.just cố định. Cần bảo đảm publisher tôn trọng cancellation và backpressure; khi server hủy stream, công việc phát dữ liệu ở client nên được dừng nếu có thể.

Không cần override tất cả phương thức nếu client chỉ hỗ trợ một số lệnh ngược. Hãy chỉ mở các tương tác mà hợp đồng ứng dụng yêu cầu và trả lỗi rõ ràng cho loại request không được hỗ trợ.

## 6. Đóng gói responder thành lớp riêng

Để tránh đặt toàn bộ logic nghiệp vụ trong callback connect, nên tạo một lớp responder chuyên trách. Lớp này có thể phụ thuộc service, validator và các thành phần cần thiết.

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

public final class ClientCommandResponder extends AbstractRSocket {

    private final ClientCommandService commandService;

    public ClientCommandResponder(ClientCommandService commandService) {
        this.commandService = commandService;
    }

    @Override
    public Mono<Payload> requestResponse(Payload request) {
        String command = request.getDataUtf8();

        if (!"client.status".equals(command)) {
            return Mono.error(new IllegalArgumentException(
                "Unsupported client command"
            ));
        }

        return commandService.currentStatus()
            .map(DefaultPayload::create);
    }
}
~~~

Sau đó đăng ký lớp responder khi tạo connector:

~~~java
RSocket clientRequester = RSocketConnector.create()
    .acceptor((setup, sendingSocket) ->
        Mono.just(new ClientCommandResponder(commandService))
    )
    .connect(TcpClientTransport.create("localhost", 7000))
    .block();
~~~

Tách responder thành lớp riêng giúp kiểm thử độc lập, giới hạn các lệnh được phép gọi và dễ thay đổi logic mà không ảnh hưởng cấu hình transport.

## 7. Kết hợp responder với Spring

RSocketRequester là API thuận tiện của Spring để client gửi request ra ngoài. Nó không tự động biến mọi client thành một endpoint nhận request ngược. Khi cần server gọi ngược client theo mô hình Spring Messaging, client cũng phải cung cấp một SocketAcceptor có khả năng dispatch request tới các phương thức handler.

Spring RSocket có RSocketMessageHandler để ánh xạ các phương thức @MessageMapping thành responder. Ở phía client, RSocketMessageHandler có thể cung cấp SocketAcceptor thông qua API responder() để tích hợp vào RSocketConnector.acceptor(...), cùng RSocketStrategies tương ứng với codec và metadata mà hai bên thống nhất. Cách khởi tạo handler và đăng ký bean phụ thuộc phiên bản Spring đang dùng; cần kiểm tra API của phiên bản dự án trước khi triển khai.

Về mặt kiến trúc, hai chiều có thể được tổ chức như sau:

- Client dùng RSocketRequester hoặc RSocket requester thuần để gọi route phía server.
- Client-side RSocketMessageHandler ánh xạ các request ngược tới controller/handler của client.
- RSocketConnector nhận SocketAcceptor được tạo từ responder đó.
- Server giữ requester của từng client trong phạm vi session và gọi route ngược khi cần.

Nếu ứng dụng chỉ cần một vài lệnh đơn giản, AbstractRSocket có thể ít thành phần hơn. Nếu muốn dùng annotation, message conversion và các cơ chế dispatch của Spring, tích hợp RSocketMessageHandler giúp đồng nhất mô hình lập trình với phía server.

## 8. Quản lý vòng đời responder và kết nối

Responder được đăng ký cho một kết nối cụ thể. Khi client mở nhiều kết nối, mỗi kết nối có thể có một responder và ngữ cảnh riêng. Khi kết nối đóng, requester phía peer cũng không còn dùng được.

Một registry phía server thường cần quản lý:

- Định danh client đã được xác thực, không chỉ dựa vào giá trị client tự khai báo.
- RSocket requester gắn với kết nối đó.
- Thời điểm kết nối được tạo và trạng thái hiện tại.
- Cơ chế xóa entry khi kết nối đóng hoặc khi client bị thu hồi quyền.
- Giới hạn số request ngược đồng thời và timeout cho mỗi request.

Không giữ requester trong static map vô thời hạn. Nếu không xóa entry khi session đóng, registry sẽ giữ tham chiếu tới object cũ và có thể gây rò rỉ bộ nhớ. Khi client reconnect bằng một session mới, server cần đăng ký requester mới và thay thế hoặc loại bỏ entry cũ theo chính sách của ứng dụng.

Request ngược cũng cần timeout. Nếu client mất kết nối hoặc responder không phát response, server không nên chờ vô hạn. Hãy áp dụng timeout, ghi nhận lỗi và quyết định có gửi lại hay không theo tính chất của lệnh.

## 9. Bảo mật request ngược

Khả năng server chủ động gọi client rất hữu ích, nhưng cũng mở ra một bề mặt quyền hạn mới. Client phải xác thực peer và kiểm tra từng loại lệnh được phép xử lý. Không nên để responder thực thi tùy ý tên method hoặc câu lệnh do server gửi.

Một số nguyên tắc nên áp dụng:

- Chỉ kết nối tới server tin cậy và xác minh TLS certificate khi dùng TLS.
- Xác thực phiên và ràng buộc danh tính client với kết nối.
- Allowlist các command/route mà client chấp nhận.
- Kiểm tra quyền của server đối với từng command, đặc biệt nếu command có tác dụng phụ trên client.
- Validate payload, giới hạn kích thước và thời gian xử lý.
- Không ghi token, thông tin bí mật hoặc toàn bộ payload nhạy cảm vào log.

Nếu server gửi lệnh cập nhật cấu hình hoặc xóa dữ liệu cục bộ, responder cần kiểm tra chính sách và phạm vi cho phép. Một kết nối đã xác thực không có nghĩa mọi hành động đều được phép.

## 10. Xử lý lỗi và kiểm thử

Lỗi trong responder client thường kết thúc stream tương ứng bằng lỗi. Điều đó không nhất thiết đóng toàn bộ kết nối. Server gọi ngược sẽ nhận lỗi trong publisher của request đó và có thể xử lý theo route, loại lỗi và chính sách retry.

Ví dụ thêm timeout và log cho request ngược:

~~~java
import java.time.Duration;
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

Mono<String> requestClientStatus(RSocket clientRequester) {
    return clientRequester
        .requestResponse(DefaultPayload.create("client.status"))
        .timeout(Duration.ofSeconds(3))
        .map(Payload::getDataUtf8)
        .doOnError(error ->
            log.warn("Request ngược tới client thất bại", error)
        );
}
~~~

Nên kiểm thử ít nhất các trường hợp sau:

1. Client kết nối tới server và vẫn gọi được request-response theo chiều client tới server.
2. Server gửi request-response tới client; responder phía client trả đúng response.
3. Server gửi request-stream tới client; client phát các phần tử theo demand và dừng khi bị cancel.
4. Client trả lỗi cho một request ngược; server nhận lỗi ở đúng publisher và kết nối vẫn có thể tiếp tục.
5. Client đóng kết nối; registry phía server loại bỏ requester tương ứng.
6. Server gửi command không nằm trong allowlist; client từ chối và ghi nhận sự kiện bảo mật.
7. Nhiều client kết nối đồng thời; server gửi request tới đúng responder của từng client.

Một unit test có thể gọi trực tiếp responder mà không cần mở socket:

~~~java
import io.rsocket.Payload;
import io.rsocket.util.DefaultPayload;
import reactor.test.StepVerifier;

StepVerifier.create(
        clientResponder.requestResponse(
            DefaultPayload.create("client.status")
        )
    )
    .expectNextMatches(payload ->
        "CLIENT_READY".equals(payload.getDataUtf8())
    )
    .verifyComplete();
~~~

Unit test xác nhận logic responder. Integration test vẫn cần thiết để xác nhận connector đã đăng ký responder và server thực sự gửi request qua transport tới đúng client.

## 11. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Client gọi server được nhưng server không gọi ngược được | Client chưa cấu hình acceptor | Kiểm tra RSocketConnector.acceptor(...) trước connect(...) |
| Request ngược tới client trả lỗi unsupported | Responder chưa override kiểu tương tác được gọi | Đối chiếu requestResponse, requestStream, fireAndForget hoặc requestChannel |
| Server gọi nhầm client | Dùng chung requester hoặc registry key không đúng | Lưu requester theo từng session đã xác thực |
| Request ngược bị treo | Responder không phát terminal signal hoặc không có timeout | Kiểm tra publisher, cancellation và timeout |
| Client reconnect nhưng server vẫn dùng socket cũ | Registry không được cập nhật theo lifecycle | Thay entry khi session mới được thiết lập và xóa entry cũ |
| Payload decode lỗi | Codec hoặc MIME type hai phía không thống nhất | Cấu hình RSocketStrategies/codec tương thích |

## 12. Kết luận

Trong RSocket, bên mở kết nối không chỉ là requester. Client có thể cung cấp responder ngay khi tạo connector bằng RSocketConnector.acceptor(...), từ đó nhận các request do server khởi tạo trên cùng phiên. Ở phía server, SocketAcceptor trả về responder xử lý request từ client và cung cấp sendingSocket để server gửi request ngược lại.

Hãy quản lý requester theo từng kết nối, giới hạn command mà responder chấp nhận, xử lý timeout và dọn dẹp khi session đóng. Khi kết hợp Spring, có thể dùng RSocketMessageHandler để ánh xạ request ngược tới handler theo mô hình Spring Messaging. Cấu hình đúng hai chiều giúp ứng dụng khai thác giao tiếp realtime hai chiều mà không cần mở một kết nối riêng cho mỗi hướng.
