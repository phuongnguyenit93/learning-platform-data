# Tạo máy chủ bằng RSocketServer và SocketAcceptor

Trong rsocket-java, **RSocketServer** chịu trách nhiệm mở transport, nhận kết nối và chạy giao thức RSocket. **SocketAcceptor** quyết định cách chấp nhận một kết nối mới và trả về một đối tượng **RSocket** để xử lý các interaction trên connection đó. Tách hai vai trò này giúp ứng dụng cấu hình TCP hoặc WebSocket ở tầng server, đồng thời giữ logic xử lý request trong responder riêng.

Một server tối thiểu cần ba bước: tạo SocketAcceptor, bind RSocketServer vào transport và quản lý vòng đời server. Sau khi client kết nối, acceptor nhận setup payload cùng socket chiều ngược lại, xác thực hoặc tạo context cho client, rồi trả về responder. Responder có thể xử lý request-response, fire-and-forget, request-stream và request-channel.

Bài học tập trung vào API Java của rsocket-java và cách tổ chức server có thể mở rộng trong ứng dụng Spring Boot. Các ví dụ dùng TCP làm transport chính; WebSocket được trình bày như một lựa chọn thay thế.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của RSocketServer, SocketAcceptor và RSocket responder.
- Tạo server và bind vào TCP hoặc WebSocket transport.
- Đọc setup payload và xây dựng context cho từng connection.
- Cài đặt handler cho bốn interaction model trong AbstractRSocket.
- Sử dụng socket chiều ngược để server chủ động gửi request đến client.
- Quản lý lỗi setup, lỗi interaction và vòng đời đóng server.
- Phân biệt server thuần rsocket-java với server messaging do Spring quản lý.

## 1. Kiến trúc server trong rsocket-java

Server RSocket có thể được nhìn thành các lớp:

~~~mermaid
flowchart TD
    A["Client TCP / WebSocket"] --> B["ServerTransport"]
    B --> C["RSocketServer"]
    C --> D["SocketAcceptor"]
    D --> E["ConnectionSetupPayload"]
    D --> F["RSocket responder"]
    F --> G["requestResponse"]
    F --> H["fireAndForget"]
    F --> I["requestStream"]
    F --> J["requestChannel"]
~~~

- **ServerTransport** mở cổng và nhận kết nối ở tầng transport, ví dụ TCP hoặc WebSocket.
- **RSocketServer** chạy giao thức RSocket trên các kết nối được transport chấp nhận.
- **SocketAcceptor** được gọi khi một RSocket connection mới hoàn tất bước setup. Nó quyết định có chấp nhận connection và responder nào sẽ phục vụ connection đó.
- **ConnectionSetupPayload** chứa data và metadata do requester gửi trong SETUP.
- **RSocket responder** nhận các interaction từ peer và trả về publisher tương ứng.

RSocket hỗ trợ multiplex nhiều interaction trên cùng một connection. Vì vậy, một SocketAcceptor không phải là handler được gọi lại cho từng request. Nó tạo responder gắn với connection; responder đó có thể nhận nhiều request và stream trong suốt vòng đời session.

### 1.1. Hai chiều RSocket trong SocketAcceptor

Phương thức **SocketAcceptor.accept** nhận hai tham số:

| Tham số | Vai trò |
|---|---|
| **ConnectionSetupPayload setup** | Setup data và metadata mà client gửi khi mở session |
| **RSocket sendingSocket** | Socket phía server dùng để chủ động gửi interaction đến client |

Giá trị trả về là **Mono<RSocket>**. Đối tượng RSocket được trả về xử lý request từ client. Tham số **sendingSocket** phục vụ chiều ngược: server có thể gọi request-response, fire-and-forget hoặc các interaction khác đến client nếu client cung cấp responder tương ứng.

Điều này làm RSocket trở thành giao tiếp hai chiều thực sự. Server không phải chỉ chờ client gọi; nó có thể chủ động gửi thông tin hoặc yêu cầu client xử lý.

## 2. Chuẩn bị dependency

Với Gradle, một ứng dụng server thuần rsocket-java cần core API và transport Netty:

~~~kotlin
dependencies {
    implementation("io.rsocket:rsocket-core")
    implementation("io.rsocket:rsocket-transport-netty")
}
~~~

Hãy dùng version được quản lý thống nhất trong version catalog hoặc dependency management của dự án. **rsocket-core** cung cấp RSocketServer, SocketAcceptor, Payload và các abstraction protocol; **rsocket-transport-netty** cung cấp TCP/WebSocket transport dựa trên Netty.

Nếu dự án dùng Spring Boot, chọn phiên bản Spring Framework/Spring Boot tương thích với phiên bản RSocket đang được dependency management quản lý. Tránh tự trộn nhiều version rsocket-core và transport-netty vì có thể gây lỗi binary hoặc hành vi không tương thích.

## 3. Tạo SocketAcceptor

SocketAcceptor là một functional interface. Có thể dùng lambda nếu logic chấp nhận ngắn:

~~~java
SocketAcceptor acceptor = (setup, sendingSocket) ->
        Mono.just(new AbstractRSocket() {
            @Override
            public Mono<Payload> requestResponse(Payload payload) {
                String name = payload.getDataUtf8();
                return Mono.just(
                        DefaultPayload.create("Xin chào " + name));
            }
        });
~~~

Ví dụ này chấp nhận mọi connection và trả về một responder có request-response handler. Trong ứng dụng thực tế, acceptor thường kiểm tra setup metadata, xác thực client và tạo responder mang context của connection.

### 3.1. Xác thực và tạo context theo connection

Setup payload có thể mang thông tin xác thực hoặc metadata khởi tạo. Server phải xác minh credential bằng security component trước khi tin danh tính client:

~~~java
SocketAcceptor acceptor = (setup, sendingSocket) ->
        authenticationService.authenticate(setup)
                .map(identity ->
                        new ClientResponder(
                                identity, sendingSocket, auditService));
~~~

**authenticationService.authenticate** là abstraction do ứng dụng cung cấp. Nó có thể kiểm tra bearer token, chứng thư hoặc cơ chế xác thực đã cấu hình. Khi xác thực thất bại, publisher có thể kết thúc bằng lỗi để từ chối setup; cần kiểm tra cách implementation ánh xạ lỗi acceptor thành lỗi protocol.

Không dùng userId, role hoặc tenantId do client tự khai trong setup metadata làm danh tính đã xác thực. Sau khi xác minh credential, tạo một context nội bộ như **ClientIdentity** và dùng context đó trong responder.

### 3.2. SocketAcceptor là ranh giới connection

Một acceptor nên thực hiện các công việc gắn với connection:

- Xác minh setup metadata và credential.
- Tạo principal hoặc context client đã xác thực.
- Kiểm tra client có được phép mở session hay không.
- Gắn các dependency hoặc service cần cho responder.
- Đăng ký lifecycle để giải phóng tài nguyên khi connection đóng.

Các quy tắc nghiệp vụ của từng request vẫn cần được kiểm tra trong handler. Xác thực connection không đồng nghĩa mọi route hoặc mọi thao tác trong connection đều được phép.

## 4. Cài đặt responder bằng AbstractRSocket

**AbstractRSocket** cung cấp các method mặc định cho interaction model. Ứng dụng kế thừa lớp này và override các method cần hỗ trợ. Ví dụ dưới đây minh họa một responder cho một client đã được xác thực:

~~~java
import io.rsocket.AbstractRSocket;
import io.rsocket.Payload;
import io.rsocket.RSocket;
import io.rsocket.util.DefaultPayload;
import org.reactivestreams.Publisher;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.concurrent.atomic.AtomicLong;

public final class ClientResponder extends AbstractRSocket {

    private final ClientIdentity identity;
    private final RSocket sendingSocket;
    private final AuditService auditService;
    private final AtomicLong eventSequence = new AtomicLong();

    public ClientResponder(
            ClientIdentity identity,
            RSocket sendingSocket,
            AuditService auditService) {
        this.identity = identity;
        this.sendingSocket = sendingSocket;
        this.auditService = auditService;
    }

    @Override
    public Mono<Payload> requestResponse(Payload payload) {
        String command = payload.getDataUtf8();
        return Mono.fromSupplier(() ->
                DefaultPayload.create(
                        "Client " + identity.clientId()
                                + " đã gửi: " + command));
    }

    @Override
    public Mono<Void> fireAndForget(Payload payload) {
        String event = payload.getDataUtf8();
        return Mono.fromRunnable(() ->
                auditService.record(identity.clientId(), event));
    }

    @Override
    public Flux<Payload> requestStream(Payload payload) {
        String topic = payload.getDataUtf8();
        return Flux.range(1, 5)
                .map(index -> DefaultPayload.create(
                        topic + "-" + eventSequence.incrementAndGet()));
    }

    @Override
    public Flux<Payload> requestChannel(Publisher<Payload> payloads) {
        return Flux.from(payloads)
                .map(Payload::getDataUtf8)
                .map(message -> DefaultPayload.create(
                        "ACK " + identity.clientId() + ": " + message));
    }

    public Mono<Void> notifyClient(String message) {
        return sendingSocket.fireAndForget(
                DefaultPayload.create(message));
    }
}
~~~

Đây là mã minh họa cấu trúc. **ClientIdentity** và **auditService** là kiểu/thành phần do ứng dụng định nghĩa; hãy inject service qua constructor thay vì dùng biến toàn cục. Trong responder thật, mỗi method cần gọi đúng service nghiệp vụ, kiểm tra quyền và xử lý lỗi tương ứng.

### 4.1. Request-response

**requestResponse** nhận một payload và trả về tối đa một payload. Đây là lựa chọn phù hợp cho truy vấn hoặc lệnh cần kết quả:

~~~java
@Override
public Mono<Payload> requestResponse(Payload payload) {
    String orderId = payload.getDataUtf8();
    return orderService.findVisibleTo(identity, orderId)
            .map(order -> DefaultPayload.create(
                    order.id() + "|" + order.status()));
}
~~~

Publisher có thể hoàn tất rỗng nếu không có kết quả hoặc phát lỗi nếu request không hợp lệ. Hãy xác định semantics rõ ràng để client phân biệt không tìm thấy dữ liệu với lỗi xử lý.

### 4.2. Fire-and-forget

**fireAndForget** nhận một payload và trả về **Mono<Void>**. Client không nhận response payload:

~~~java
@Override
public Mono<Void> fireAndForget(Payload payload) {
    String event = payload.getDataUtf8();
    return auditService.append(identity, event);
}
~~~

Fire-and-forget phù hợp khi caller không cần kết quả nghiệp vụ. Tuy nhiên, đừng coi nó là bảo đảm lưu bền vững nếu ứng dụng chưa có acknowledgement hoặc cơ chế quan sát lỗi phù hợp. Nếu client phải biết lệnh đã được chấp nhận, request-response thường phù hợp hơn.

### 4.3. Request-stream

**requestStream** nhận một request payload và trả về **Flux<Payload>**. Một request khởi tạo stream có thể phát nhiều response:

~~~java
@Override
public Flux<Payload> requestStream(Payload payload) {
    String deviceId = payload.getDataUtf8();
    return telemetryService.streamFor(identity, deviceId)
            .map(reading -> DefaultPayload.create(
                    reading.toWireFormat()));
}
~~~

Luồng dữ liệu chịu flow control của RSocket. Server nên trả publisher reactive và tránh tự tạo hàng đợi không giới hạn. Khi client cancel stream, pipeline cần truyền cancellation về nguồn để giải phóng tài nguyên.

### 4.4. Request-channel

**requestChannel** nhận một publisher payload từ client và trả về một publisher payload từ server. Hai phía có thể vừa gửi vừa nhận:

~~~java
@Override
public Flux<Payload> requestChannel(Publisher<Payload> payloads) {
    return Flux.from(payloads)
            .concatMap(inbound -> {
                String command = inbound.getDataUtf8();
                return commandService.process(identity, command)
                        .map(result -> DefaultPayload.create(
                                result.toWireFormat()));
            });
}
~~~

**concatMap** xử lý tuần tự và giữ thứ tự phản hồi theo thứ tự đầu vào. Nếu nghiệp vụ cho phép xử lý song song, có thể dùng **flatMap** với concurrency hữu hạn. Không dùng concurrency không giới hạn khi mỗi message gọi dịch vụ từ xa hoặc ghi database.

## 5. Khởi chạy server bằng RSocketServer

Sau khi tạo acceptor, bind server vào một transport. Với TCP:

~~~java
import io.rsocket.RSocketServer;
import io.rsocket.SocketAcceptor;
import io.rsocket.transport.netty.server.CloseableChannel;
import io.rsocket.transport.netty.server.TcpServerTransport;

public final class RSocketServerApplication {

    public static void main(String[] args) {
        SocketAcceptor acceptor = createSocketAcceptor();

        CloseableChannel server = RSocketServer
                .create(acceptor)
                .bind(TcpServerTransport.create("0.0.0.0", 7000))
                .block();

        if (server == null) {
            throw new IllegalStateException(
                    "Không thể bind RSocket server");
        }

        Runtime.getRuntime().addShutdownHook(
                new Thread(server::dispose));

        server.onClose().block();
    }
}
~~~

**RSocketServer.create(acceptor)** tạo server gắn với acceptor. **bind(...)** mở transport và trả về publisher của **CloseableChannel**. Gọi **block()** ở hàm main để chờ bind hoàn tất, sau đó chờ **onClose()** để giữ tiến trình server sống. Trong ứng dụng reactive đang chạy trên event loop, không gọi block trên event-loop thread.

**0.0.0.0** lắng nghe trên mọi network interface. Trong production, hãy chọn interface phù hợp với môi trường triển khai và cấu hình firewall/network policy. Không mở cổng ra mạng không tin cậy nếu chưa bật TLS và chính sách xác thực.

### 5.1. Thay đổi transport sang WebSocket

Cùng một SocketAcceptor có thể được dùng với WebSocket transport:

~~~java
CloseableChannel server = RSocketServer
        .create(acceptor)
        .bind(WebsocketServerTransport.create("0.0.0.0", 7001))
        .block();
~~~

Transport WebSocket dùng lớp **WebsocketServerTransport** từ package server của transport Netty.

Transport quyết định cách byte được truyền giữa hai peer. Interaction model, responder và SocketAcceptor vẫn giữ vai trò tương tự. Client phải kết nối bằng WebSocket transport tương ứng; TCP client không thể kết nối trực tiếp vào WebSocket endpoint.

### 5.2. RSocketServer và ServerTransport

Server có thể tách cấu hình transport khỏi logic acceptor:

~~~java
import io.rsocket.transport.ServerTransport;
import io.rsocket.transport.netty.server.TcpServerTransport;

ServerTransport transport =
        TcpServerTransport.create("localhost", 7000);

CloseableChannel server = RSocketServer
        .create(acceptor)
        .bind(transport)
        .block();
~~~

Điều này hữu ích khi cùng một ứng dụng cần chọn transport theo cấu hình môi trường. Không nên bind nhiều server lên cùng địa chỉ/cổng; mỗi bind cần một endpoint hợp lệ và vòng đời riêng.

## 6. Kết nối từ client để kiểm tra server

Client rsocket-java tạo kết nối bằng **RSocketConnector** và **TcpClientTransport**:

~~~java
import io.rsocket.RSocket;
import io.rsocket.RSocketConnector;
import io.rsocket.Payload;
import io.rsocket.util.DefaultPayload;
import io.rsocket.transport.netty.client.TcpClientTransport;

RSocket client = RSocketConnector.create()
        .connect(TcpClientTransport.create("localhost", 7000))
        .block();

if (client == null) {
    throw new IllegalStateException("Không kết nối được server");
}

Payload response = client.requestResponse(
        DefaultPayload.create("Lan")).block();

if (response != null) {
    try {
        System.out.println(response.getDataUtf8());
    } finally {
        response.release();
    }
}

client.dispose();
~~~

Ví dụ dùng **block()** cho chương trình kiểm tra nhỏ. Trong ứng dụng reactive, hãy compose các publisher thay vì block thread. Payload nhận về sử dụng buffer có quản lý reference count; khi ứng dụng giữ payload ngoài callback hoặc đọc thủ công ở tầng raw API, phải tuân thủ ownership và release đúng cách.

## 7. Setup payload và lifecycle của connection

SocketAcceptor được gọi khi một requester thiết lập RSocket session. Setup payload có thể chứa:

- Data do client gửi khi mở connection.
- Metadata như authentication hoặc thông tin khởi tạo.
- Các tham số protocol như MIME type và khả năng extension được thương lượng ở tầng setup.

Server có thể đọc setup data và metadata để tạo context. Ví dụ:

~~~java
SocketAcceptor acceptor = (setup, sendingSocket) -> {
    String clientLabel = setup.getDataUtf8();

    return authenticationService.authenticate(setup)
            .map(identity ->
                    new ClientResponder(
                            identity, sendingSocket, auditService));
};
~~~

**clientLabel** chỉ là nhãn do client gửi, không phải bằng chứng danh tính. Dùng kết quả xác thực để tạo **ClientIdentity**. Nếu setup không hợp lệ hoặc credential không được chấp nhận, kết thúc quá trình accept theo chính sách; đừng trả về một responder giả rồi cho request tiếp tục.

### 7.1. Một acceptor, nhiều connection

RSocketServer nhận nhiều connection và gọi acceptor cho từng connection mới. Mỗi lần accept thành công có thể tạo một responder với context riêng:

~~~text
RSocketServer
    ├── Connection A -> SocketAcceptor -> Responder A
    ├── Connection B -> SocketAcceptor -> Responder B
    └── Connection C -> SocketAcceptor -> Responder C
~~~

Không lưu danh tính client trong một mutable field dùng chung trên acceptor rồi ghi đè mỗi lần có connection mới. Hãy tạo responder hoặc context riêng theo connection. Các service dùng chung có thể được chia sẻ nếu thread-safe và không chứa state riêng của client.

### 7.2. Theo dõi connection đóng

Connection có thể kết thúc do client đóng, transport lỗi hoặc server shutdown. Cần gắn cleanup với lifecycle của RSocket/session để giải phóng permit, subscription, registry entry và tài nguyên theo connection.

Các stream đang chạy phải phản ứng với cancellation. Tránh tạo side effect khi responder được khởi tạo nếu chưa có request tương ứng. Nếu cần ghi nhận connection mở/đóng, dùng hook lifecycle phù hợp với implementation hoặc wrapper RSocket; đừng nhầm vòng đời connection với vòng đời một request.

## 8. SocketAcceptor và định tuyến request

SocketAcceptor quyết định responder cho connection, nhưng bản thân nó không phải route dispatcher. RSocket core truyền interaction type và payload; ứng dụng cần quyết định cách diễn giải metadata hoặc route.

Có hai cách tổ chức phổ biến:

1. **Raw RSocket API**: implement các method trong AbstractRSocket và tự đọc metadata để dispatch tới service/handler tương ứng.
2. **Spring Messaging**: dùng **@MessageMapping** và routing metadata để Spring dispatch tới method handler.

Nếu ứng dụng cần route như **orders.find** hoặc **telemetry.stream**, đừng giả định **RSocketServer.create(acceptor)** tự động tìm method theo chuỗi route. Route metadata cần được một lớp messaging hoặc dispatcher hiểu và xử lý.

### 8.1. Raw responder phù hợp khi nào?

Raw API hữu ích khi:

- Cần kiểm soát trực tiếp RSocket interaction và protocol.
- Xây dựng thư viện hoặc gateway RSocket.
- Cần tích hợp transport hoặc logic connection đặc thù.
- Muốn tự tổ chức dispatcher và payload codec.

Đổi lại, ứng dụng phải tự quản lý routing metadata, serialization, validation, security context và mapping lỗi.

### 8.2. Spring RSocket phù hợp khi nào?

Spring RSocket phù hợp khi ứng dụng đã dùng Spring và muốn khai báo handler bằng annotation:

~~~java
@Controller
public class GreetingController {

    @MessageMapping("greeting")
    public Mono<String> greeting(String name) {
        return Mono.just("Xin chào " + name);
    }
}
~~~

Spring cung cấp lớp tích hợp để dispatch theo route và chuyển đổi payload. Ứng dụng cấu hình RSocket server qua Spring Boot hoặc Spring Framework. Cách này giảm lượng mã protocol-level, trong khi raw RSocketServer/SocketAcceptor cho quyền kiểm soát trực tiếp hơn.

## 9. Quản lý lỗi

Nên phân biệt lỗi trong lúc accept connection với lỗi trong một interaction:

| Phạm vi | Ví dụ | Cách xử lý |
|---|---|---|
| Bind server | Cổng đã được dùng, transport không khởi động | Không đánh dấu server sẵn sàng; báo lỗi startup |
| Setup/accept | Credential sai, client không được phép mở session | Từ chối setup theo protocol |
| Request handler | Payload sai định dạng, không tìm thấy dữ liệu | Trả lỗi cho interaction tương ứng |
| Stream | Nguồn dữ liệu lỗi hoặc timeout | Kết thúc stream và giải phóng subscription |
| Connection | TCP/WebSocket đóng hoặc peer mất kết nối | Dọn tài nguyên theo lifecycle |
| Server shutdown | Tiến trình dừng có chủ đích | Ngừng nhận kết nối và đóng channel có kiểm soát |

### 9.1. Không chặn event loop

RSocket trên Netty hoạt động theo mô hình non-blocking. Không gọi JDBC blocking, **Thread.sleep** hoặc **block()** trong handler đang chạy trên event loop. Nếu phải gọi API blocking, chuyển công việc sang scheduler phù hợp hoặc dùng driver reactive.

Ví dụ, một thao tác blocking có thể được cô lập:

~~~java
return Mono.fromCallable(() -> legacyService.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Không chuyển mọi tác vụ sang boundedElastic theo mặc định. Ưu tiên client/database reactive; chỉ cô lập các thao tác blocking thực sự cần thiết và đặt giới hạn concurrency.

### 9.2. Giải phóng Payload và buffer

Payload raw API có thể chứa ByteBuf reference-counted. Đọc data thành kiểu bất biến như String trước khi xử lý bất đồng bộ thường đơn giản hơn việc giữ buffer. Nếu cần giữ hoặc chuyển buffer qua ranh giới bất đồng bộ, phải tuân thủ quy tắc retain/release của implementation. Không release hai lần hoặc truy cập buffer sau khi ownership đã kết thúc.

## 10. Bảo mật và cấu hình production

Một server có thể lắng nghe thành công nhưng vẫn chưa sẵn sàng cho production. Cần cấu hình thêm:

- **TLS** cho TCP hoặc WebSocket bảo mật (wss) khi đi qua mạng không tin cậy.
- **Authentication** ở setup hoặc cơ chế request metadata phù hợp.
- **Authorization** theo Principal, route và tenant trong từng interaction.
- **Payload/metadata size limits** để tránh message quá lớn.
- **Keepalive** để phát hiện peer không còn hoạt động.
- **Leasing** nếu server muốn điều tiết số request mới trên từng connection.
- **Resumption** nếu cần tiếp tục session sau gián đoạn transport và implementation hỗ trợ.
- **Metrics và tracing** để quan sát connection, request, stream, lỗi và độ trễ.
- **Graceful shutdown** để ngừng nhận kết nối và giải phóng session.

Các tính năng như TLS, keepalive, leasing và resumption được cấu hình ở server/transport theo API của phiên bản rsocket-java đang dùng. Không nên sao chép method từ phiên bản khác mà không kiểm tra dependency.

## 11. Kiểm thử server

Nên kiểm tra cả transport lẫn interaction:

1. Server bind thành công vào địa chỉ và cổng dự kiến.
2. Client TCP kết nối được và thực hiện request-response.
3. Fire-and-forget được chuyển đến service và lỗi được quan sát.
4. Request-stream phát nhiều phần tử và dừng khi client cancel.
5. Request-channel nhận luồng đầu vào và trả luồng phản hồi đúng thứ tự.
6. Setup metadata hợp lệ tạo context đúng cho từng connection.
7. Credential sai khiến setup bị từ chối.
8. Hai connection khác nhau không dùng chung danh tính hoặc tenant context.
9. Server-initiated interaction sử dụng sendingSocket hoạt động khi client có responder tương ứng.
10. Server dispose đóng channel và giải phóng tài nguyên.
11. Transport WebSocket hoạt động khi dùng đúng client transport.
12. Payload lớn, stream chậm và connection mất đột ngột không làm buffer tăng vô hạn.

Một kiểm thử tích hợp có thể khởi động server trên cổng tạm, tạo RSocketConnector client, thực hiện interaction rồi đóng client và server trong finally. Điều này giúp tránh để lại Netty event loop hoặc cổng lắng nghe sau khi test kết thúc.

## 12. Các lỗi thường gặp

### Nghĩ SocketAcceptor được gọi cho từng request

Acceptor được gọi khi thiết lập connection. Một responder được trả về để phục vụ nhiều interaction trên session đó.

### Dùng setup metadata như dữ liệu đã xác thực

Metadata do client gửi có thể bị giả mạo. Xác minh credential trước khi tạo Principal hoặc tenant context.

### Nghĩ RSocketServer tự hiểu route

RSocket core không tự dispatch chuỗi route thành Java method. Dùng Spring Messaging hoặc viết dispatcher/metadata parser.

### Dùng chung mutable state giữa các connection

Một acceptor có thể phục vụ nhiều connection. Tạo responder/context riêng cho từng client và chỉ chia sẻ dependency thread-safe.

### Block trong handler

Blocking trên event loop làm chậm các interaction khác trên connection hoặc server. Dùng reactive API hoặc cô lập công việc blocking có giới hạn.

### Quên quản lý lifecycle

Stream hoặc resource có thể tiếp tục giữ tài nguyên sau khi client rời đi. Gắn cleanup với cancellation, completion và connection close.

### Bind server nhưng không giữ tiến trình sống

Nếu chương trình kết thúc ngay sau bind, server cũng dừng theo tiến trình. Quản lý **CloseableChannel.onClose()** hoặc lifecycle của framework.

## 13. Checklist tạo RSocket server

Trước khi triển khai, hãy xác nhận:

1. Dependency rsocket-core và transport-netty cùng version tương thích.
2. SocketAcceptor được tạo với logic accept/setup rõ ràng.
3. Setup credential được xác minh trước khi chấp nhận connection.
4. Mỗi connection có responder và context riêng.
5. Các interaction cần hỗ trợ được implement đúng method.
6. Server-initiated request dùng sendingSocket đúng chiều.
7. Server bind vào transport, địa chỉ và cổng đã chọn.
8. Tiến trình quản lý onClose và graceful shutdown.
9. Handler không block event loop và xử lý cancellation.
10. TLS, authorization, size limit và observability đã được cấu hình.
11. Route dispatch được xử lý bởi Spring Messaging hoặc dispatcher riêng.
12. Có kiểm thử TCP/WebSocket, interaction và connection lifecycle.

## 14. Tổng kết

RSocketServer quản lý transport và protocol server; SocketAcceptor quyết định cách chấp nhận từng connection và trả về RSocket responder. Setup payload cung cấp dữ liệu khởi tạo, còn sendingSocket cho phép server chủ động giao tiếp ngược với client. Responder có thể implement request-response, fire-and-forget, request-stream và request-channel bằng AbstractRSocket.

Để tạo server, hãy xây dựng acceptor, bind RSocketServer vào TCP hoặc WebSocket transport và quản lý CloseableChannel. Trong production, cần xác thực setup, tách context theo connection, xử lý lỗi và cancellation, không block event loop, bảo vệ transport và quản lý lifecycle. Khi cần route-based handler và tích hợp Spring, dùng Spring Messaging; khi cần kiểm soát trực tiếp protocol, SocketAcceptor và AbstractRSocket cung cấp lớp API phù hợp.
