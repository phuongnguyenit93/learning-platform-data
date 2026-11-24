# Cấu hình connector, server và interceptor cho hành vi giao thức

Trong RSocket Java, RSocketConnector tạo kết nối từ phía client, RSocketServer tiếp nhận kết nối và SocketAcceptor chọn handler cho từng phiên. Các lớp này cung cấp điểm cấu hình cho những hành vi giao thức như MIME type, setup payload, keepalive, lease, resume, giới hạn payload và giải mã dữ liệu. Interceptor mở rộng khả năng quan sát hoặc điều chỉnh hành vi ở phạm vi transport, lúc chấp nhận connection, khi gửi request hoặc khi phản hồi request.

Cấu hình tốt cần đặt mỗi hành vi đúng phạm vi. Kiểm tra thông tin SETUP là việc ở giai đoạn acceptor; đo thời gian một request-response là việc ở phạm vi tương tác; quan sát frame đi qua transport là việc ở lớp connection. Nếu đặt logic sai phạm vi, log dễ thiếu ngữ cảnh, metric bị đếm trùng hoặc chính sách áp dụng lên cả connection dù chỉ cần áp dụng cho một loại request.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích vai trò của RSocketConnector, RSocketServer và SocketAcceptor.
- Cấu hình transport, setup payload, MIME type, keepalive, lease, resume và giới hạn payload.
- Phân biệt requester với responder khi cấu hình ở client và server.
- Chọn đúng phạm vi interceptor: connection, socket acceptor, requester, responder hoặc từng request.
- Dùng interceptor để quan sát request, điều tiết demand và kiểm tra metadata setup.
- Quản lý vòng đời RSocket, server channel và Payload.
- Kiểm thử cấu hình bằng log frame, metric và tình huống lỗi thực tế.

## 1. Bản đồ các thành phần

| Thành phần | Vai trò | Cấu hình hoặc trách nhiệm |
|---|---|---|
| ClientTransport | Mở kênh từ client tới server | TCP, WebSocket hoặc transport khác |
| RSocketConnector | Tạo RSocket client trên transport | SETUP, MIME type, keepalive, lease, resume, interceptor |
| RSocket phía requester | Gửi request tới peer | request-response, fire-and-forget, request-stream, request-channel |
| SocketAcceptor | Nhận thông tin SETUP và tạo RSocket handler cho connection | Kiểm tra setup context, gắn handler theo client/tenant |
| RSocketServer | Khởi tạo RSocket endpoint trên server transport | Acceptor, giới hạn frame/payload, interceptor, lease, resume |
| Interceptor | Bao quanh một tầng hoạt động để quan sát hoặc điều chỉnh | Frame, connection, acceptor, request lifecycle, requester/responder |

~~~mermaid
flowchart TB
    C[Client application] --> CON[RSocketConnector]
    CON --> CT[ClientTransport]
    CT <--> ST[ServerTransport]
    ST --> SERVER[RSocketServer]
    SERVER --> ACC[SocketAcceptor]
    ACC --> HANDLER[RSocket handler theo connection]
    HANDLER --> SERVICE[Application services]
    CON -. interceptors .-> CI[Client interceptor registry]
    SERVER -. interceptors .-> SI[Server interceptor registry]
~~~

RSocketConnector và RSocketServer là điểm cấu hình chính của thư viện lõi. Transport quyết định cách mở kênh mạng; RSocket protocol quyết định cách trao đổi request, payload và frame. Interceptor có thể được gắn ở nhiều điểm của đường đi này.

## 2. Phạm vi requester và responder

Requester và responder mô tả vai trò của một peer trong một tương tác cụ thể:

- **Requester** là phía khởi tạo request.
- **Responder** là phía nhận request và tạo phản hồi hoặc xử lý request một chiều.

Trên một connection, cả hai peer đều có thể vừa gửi request vừa xử lý request từ peer còn lại. Vì thế, một RSocket client có thể có cả requester socket lẫn responder socket; server cũng vậy.

| Nơi đăng ký | forRequester áp dụng cho | forResponder áp dụng cho |
|---|---|---|
| Client connector | Request do client gửi tới server | Request do server gửi ngược về client |
| Server | Request do server gửi ngược về client | Request do client gửi tới server |

Đừng hiểu forResponder luôn có nghĩa interceptor ở server. Trên client, responder là handler xử lý request mà server khởi tạo. Hãy xác định ai đang khởi tạo tương tác trước khi chọn registry.

## 3. Chuẩn bị dependency và transport

Ví dụ trong bài dùng API rsocket-core 1.1.5 để minh họa các chữ ký cụ thể. Dự án cần rsocket-core và transport tương ứng; ví dụ TCP/WebSocket dựa trên Netty:

~~~gradle
dependencies {
    implementation("io.rsocket:rsocket-core:1.1.5")
    implementation("io.rsocket:rsocket-transport-netty:1.1.5")
}
~~~

Nếu dùng Maven, khai báo cùng hai artifact trong pom.xml với version thống nhất. Trong dự án Spring Boot, hãy kiểm tra dependency management đang chọn phiên bản RSocket nào; không trộn các module RSocket Java khác version.

TCP client transport:

~~~java
ClientTransport transport =
        TcpClientTransport.create("localhost", 7000);
~~~

WebSocket client transport:

~~~java
ClientTransport transport =
        WebsocketClientTransport.create(
                URI.create("ws://localhost:8080/rsocket"));
~~~

Transport là đầu vào cho connector. Đổi TCP sang WebSocket không làm thay đổi interaction model, route hay cấu trúc payload của ứng dụng.

## 4. Cấu hình RSocketConnector

RSocketConnector.create() tạo builder để tùy chỉnh phiên trước khi kết nối. Một số cấu hình thường dùng:

| API | Mục đích |
|---|---|
| dataMimeType(...) | MIME type của data trong payload |
| metadataMimeType(...) | MIME type của metadata |
| setupPayload(...) | Data/metadata ban đầu gửi trong frame SETUP |
| keepAlive(interval, maxLifeTime) | Chu kỳ gửi KEEPALIVE và thời gian chờ tối đa |
| maxInboundPayloadSize(...) | Giới hạn payload inbound sau reassembly |
| fragment(mtu) | Chia frame lớn thành fragment |
| payloadDecoder(...) | Chọn cách tạo Payload từ frame |
| lease(...) | Bật cơ chế giới hạn số request bằng LEASE |
| resume(...) | Bật resumption khi transport bị gián đoạn |
| reconnect(...) | Tạo RSocket dùng chung và thử kết nối lại theo Retry |
| acceptor(...) | Cung cấp handler để client nhận request từ server |
| interceptors(...) | Đăng ký interceptor theo các phạm vi |

Ví dụ tạo client TCP:

~~~java
import io.rsocket.RSocket;
import io.rsocket.core.RSocketConnector;
import io.rsocket.metadata.WellKnownMimeType;
import io.rsocket.transport.netty.client.TcpClientTransport;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

import java.time.Duration;

Mono<RSocket> socketMono = RSocketConnector.create()
        .dataMimeType(
                WellKnownMimeType.APPLICATION_JSON.getString())
        .metadataMimeType(
                WellKnownMimeType.MESSAGE_RSOCKET_COMPOSITE_METADATA.getString())
        .setupPayload(
                DefaultPayload.create("{\"client\":\"telemetry\"}"))
        .keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90))
        .connect(TcpClientTransport.create("localhost", 7000));
~~~

Trong ví dụ:

- Data MIME type cho biết data ứng dụng được serialize theo JSON.
- Metadata MIME type dùng composite metadata để có thể mang nhiều entry như routing hoặc tracing.
- Setup payload gửi một thông tin nhận diện client trong giai đoạn mở phiên.
- Keepalive interval là 20 giây; max lifetime là 90 giây.
- connect(...) trả Mono<RSocket> vì việc mở kết nối là bất đồng bộ.

Hai peer phải thống nhất MIME type và cách serialize/deserialize. Khai báo application/json không tự động biến một object Java thành JSON; ứng dụng vẫn cần codec hoặc serializer phù hợp.

### Sử dụng kết nối

Sau khi Mono phát ra RSocket, client có thể gửi request:

~~~java
RSocket socket = socketMono.block();

try {
    Payload response = socket
            .requestResponse(
                    DefaultPayload.create("{\"deviceId\":\"sensor-17\"}"))
            .block();

    if (response != null) {
        try {
            System.out.println(response.getDataUtf8());
        } finally {
            response.release();
        }
    }
} finally {
    socket.dispose();
}
~~~

Đây là ví dụ chạy ở ứng dụng nhỏ hoặc công cụ thử nghiệm. Trong ứng dụng reactive, nên kết hợp Mono<RSocket> với chuỗi flatMap thay vì chặn bằng block(). Khi nhận Payload, quản lý vòng đời và giải phóng payload theo decoder cùng cách dùng của thư viện.

### Cấu hình acceptor ở phía client

Server có thể khởi tạo request ngược về client. Nếu client muốn xử lý các request đó, hãy đăng ký SocketAcceptor trên connector:

~~~java
RSocketConnector connector = RSocketConnector.create()
        .acceptor((setup, sendingRSocket) -> {
            // setup chứa thông tin phiên do server gửi.
            // sendingRSocket là requester socket để client gửi request ngược lại.
            return Mono.just(clientHandler);
        });
~~~

clientHandler là một implementation RSocket của ứng dụng. Nếu không cấu hình acceptor, handler mặc định không xử lý các request do server gửi tới và các tương tác đó có thể bị từ chối.

## 5. Cấu hình RSocketServer và SocketAcceptor

RSocketServer nhận một SocketAcceptor, sau đó bind lên server transport. Acceptor được gọi cho từng connection mới và nhận hai thông tin:

- ConnectionSetupPayload setup: nội dung, MIME type, keepalive và capability được khai báo trong SETUP.
- RSocket sendingRSocket: requester socket của server, dùng để server khởi tạo request tới client.

Acceptor trả về Mono<RSocket> chứa responder socket dành cho connection đó.

~~~java
import io.rsocket.RSocket;
import io.rsocket.util.RSocketProxy;
import io.rsocket.SocketAcceptor;
import io.rsocket.Payload;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;
import io.rsocket.util.DefaultPayload;
import reactor.core.publisher.Mono;

SocketAcceptor acceptor = (setup, sendingRSocket) -> {
    System.out.println("Data MIME type: " + setup.dataMimeType());
    System.out.println("Metadata MIME type: " + setup.metadataMimeType());
    System.out.println("Resume enabled: " + setup.isResumeEnabled());

    RSocket responder = new RSocketProxy(new RSocket() {}) {
        @Override
        public Mono<Payload> requestResponse(Payload payload) {
            String requestJson = payload.getDataUtf8();

            return deviceService.findStatus(requestJson)
                    .map(status -> DefaultPayload.create(status.toJson()));
        }
    };

    return Mono.just(responder);
};

RSocketServer.create(acceptor)
        .bind(TcpServerTransport.create("localhost", 7000))
        .block()
        .onClose()
        .block();
~~~

RSocketProxy là wrapper giúp override một hoặc một số interaction method và delegate các method còn lại. Trong ví dụ, handler chỉ tùy chỉnh requestResponse; các method khác giữ hành vi delegate mặc định của proxy. deviceService là service nghiệp vụ do ứng dụng cung cấp.

### Khi không cần đọc SETUP

Nếu server chỉ xử lý một kiểu tương tác và không cần tạo handler theo từng connection, có thể dùng factory method của SocketAcceptor:

~~~java
SocketAcceptor acceptor =
        SocketAcceptor.forRequestResponse(payload ->
                deviceService.findStatus(payload.getDataUtf8())
                        .map(status -> DefaultPayload.create(status.toJson())));

RSocketServer.create(acceptor)
        .bind(TcpServerTransport.create("localhost", 7000))
        .block()
        .onClose()
        .block();
~~~

Cách viết này gọn hơn cho handler request-response đơn giản. Dùng acceptor đầy đủ khi cần đọc setup metadata, xác định principal, gắn context theo connection hoặc hỗ trợ server khởi tạo request ngược về client.

## 6. Các tùy chọn cấu hình server

RSocketServer cung cấp các điểm cấu hình tương ứng với yêu cầu vận hành:

| API | Ý nghĩa |
|---|---|
| acceptor(...) | Chọn handler cho connection mới |
| bind(transport) | Khởi động server trên transport |
| maxTimeToFirstFrame(...) | Giới hạn thời gian chờ frame đầu tiên, thường là SETUP |
| maxInboundPayloadSize(...) | Giới hạn kích thước payload sau khi ghép fragment |
| fragment(mtu) | Chia frame lớn thành fragment |
| payloadDecoder(...) | Chọn decoder cho payload inbound |
| lease(...) | Phát LEASE để giới hạn số request được phép |
| resume(...) | Bật khả năng resume ở phía server |
| interceptors(...) | Đăng ký interceptor cho connection và tương tác |

Ví dụ cấu hình server có giới hạn thời gian chờ SETUP và interceptor điều tiết stream:

~~~java
RSocketServer.create(acceptor)
        .maxTimeToFirstFrame(Duration.ofSeconds(10))
        .interceptors(registry -> registry
                .forResponder(
                        LimitRateInterceptor.forResponder(64, 48)))
        .bind(TcpServerTransport.create("localhost", 7000))
        .block()
        .onClose()
        .block();
~~~

maxTimeToFirstFrame giúp server giải phóng các connection mở nhưng không gửi frame khởi tạo trong thời gian cho phép. Khi đặt maxInboundPayloadSize, phải bảo đảm giá trị không nhỏ hơn giới hạn frame tối đa của transport; nếu hai giới hạn không tương thích, frame inbound có thể bị từ chối trước khi reassembly hoàn tất.

### Decoder mặc định và zero-copy

RSocket Java mặc định dùng PayloadDecoder.DEFAULT, tạo bản sao data và metadata từ frame buffer. Đây là lựa chọn dễ dùng vì ứng dụng không phải tự quản lý reference count của buffer nguồn.

PayloadDecoder.ZERO_COPY dùng retained slice của buffer bên dưới để giảm sao chép và có thể cải thiện độ trễ. Đổi lại, mọi Payload phải được release đúng lúc. Nếu giữ payload sau khi xử lý mà quên release, ứng dụng có thể rò rỉ bộ nhớ Netty. Chỉ bật zero-copy khi đã có quy ước ownership rõ ràng và kiểm thử leak.

## 7. Keepalive, lease và resume

Các tính năng protocol cần được cấu hình có chủ đích ở cả hai peer.

### Keepalive

keepAlive(interval, maxLifeTime) cấu hình chu kỳ gửi KEEPALIVE và khoảng thời gian tối đa chấp nhận không nhận được keepalive từ peer. Giá trị mặc định trong API 1.1.5 là 20 giây và 90 giây.

Chọn interval dựa trên mạng và yêu cầu phát hiện mất kết nối. Interval quá ngắn làm tăng lưu lượng điều khiển; max lifetime quá ngắn có thể coi một mạng chậm tạm thời là đã mất kết nối. Proxy và load balancer cũng có thể có idle timeout riêng, cần tính đến khi cấu hình.

### Lease

Lease giới hạn số request mà một peer được phép gửi trong một khoảng thời gian. Server có thể phát LEASE theo nhịp và quota định trước; client phải tuân thủ quota trước khi mở request mới.

~~~java
RSocketConnector connector = RSocketConnector.create()
        .lease();

RSocketServer server = RSocketServer.create(acceptor)
        .lease(spec -> spec.sender(() ->
                Flux.interval(Duration.ofSeconds(1))
                        .map(tick -> Lease.create(
                                Duration.ofSeconds(2), 100))));
~~~

Đây là ví dụ khung: server cấp lease 2 giây với quota 100 request mỗi lần phát. Cấu hình lease cần được bật tương thích ở cả hai phía. Lease giới hạn số request được khởi tạo, không phải số payload mà một request-stream có thể trả về.

### Resume và reconnect

resume(Resume) bật khả năng nối lại phiên sau khi transport bị gián đoạn, với điều kiện peer còn giữ trạng thái phiên và đủ frame trong resume buffer. Client và server phải cùng hỗ trợ, cùng bật resume và có thể tìm lại đúng session state.

reconnect(Retry) tạo một Mono<RSocket> dùng chung, có thể mở một RSocket mới sau khi connection mất. Reconnect chỉ tạo lại kết nối; nó không tự khôi phục mọi stream đang chạy như resume. Trong API 1.1.5, resume(...) và reconnect(...) là hai tùy chọn loại trừ nhau; nếu cấu hình cả hai thì resume được ưu tiên.

Không nên retry nghiệp vụ một cách mù quáng sau khi connection mất. Request có thể đã được xử lý trước khi client nhận lỗi. Với thao tác có side effect, cần idempotency key hoặc cơ chế đối soát.

## 8. Bốn phạm vi interceptor

RSocket Java cho phép đăng ký interceptor ở bốn phạm vi chính và thêm hook cho từng request:

| Phạm vi | API đăng ký | Dữ liệu có thể quan sát | Trường hợp sử dụng |
|---|---|---|---|
| Transport connection | forConnection(...) | Duplex connection và frame hai chiều | Trace frame, chẩn đoán transport, đo byte |
| Chấp nhận connection | forSocketAcceptor(...) | SETUP và hai socket requester/responder | Kiểm tra setup, gắn context, log peer |
| Requester socket | forRequester(...) | Các interaction do socket này khởi tạo | Log outbound request, đo latency phía gọi |
| Responder socket | forResponder(...) | Các interaction do socket này xử lý | Log inbound request, đo thời gian xử lý |
| Vòng đời từng request | forRequestsInRequester(...), forRequestsInResponder(...) | Start, terminate, cancel, reject của từng stream | Đếm request, theo dõi hủy và từ chối |

Interceptor không thay thế handler nghiệp vụ. Nó bao quanh một lớp xử lý để quan sát hoặc thay đổi hành vi kỹ thuật. Tránh đưa quy tắc nghiệp vụ phức tạp vào interceptor vì logic sẽ khó kiểm thử và khó xác định phạm vi tác động.

## 9. Interceptor ở requester và responder

RSocketInterceptor là một hàm nhận một RSocket và trả về một RSocket đã được decorate. Cách này phù hợp để ghi log, đo thời gian, thêm metric hoặc giới hạn tốc độ cho một số interaction model.

Ví dụ dùng LimitRateInterceptor có sẵn:

~~~java
.interceptors(registry -> registry
        .forRequester(
                LimitRateInterceptor.forRequester(64, 48))
        .forResponder(
                LimitRateInterceptor.forResponder(64, 48)))
~~~

LimitRateInterceptor.forResponder(...) áp dụng cho các luồng outbound của responder, gồm request-stream và request-channel. forRequester(...) áp dụng cho request-channel được requester khởi tạo. Interceptor này điều tiết demand bằng Flux.limitRate(highTide, lowTide); nó không phải rate limiter theo số request mỗi giây.

### Tạo interceptor đo latency

RSocketProxy giúp decorate một method mà không phải tự delegate toàn bộ interface:

~~~java
RSocketInterceptor requestResponseMetrics = socket ->
        new RSocketProxy(socket) {
            @Override
            public Mono<Payload> requestResponse(Payload payload) {
                long startedAt = System.nanoTime();

                return super.requestResponse(payload)
                        .doFinally(signal -> metrics.record(
                                "rsocket.request_response",
                                System.nanoTime() - startedAt,
                                signal.name()));
            }
        };
~~~

Đăng ký ở server responder để đo thời gian xử lý request-response mà client gửi tới server:

~~~java
RSocketServer.create(acceptor)
        .interceptors(registry ->
                registry.forResponder(requestResponseMetrics))
        .bind(TcpServerTransport.create("localhost", 7000));
~~~

Đăng ký cùng interceptor ở client requester sẽ đo thời gian phía client chờ kết quả. Hai phép đo khác nhau vì phía client bao gồm thời gian truyền mạng và xử lý phản hồi, trong khi phía server đo phạm vi xử lý của responder socket.

Khi viết interceptor tùy chỉnh:

- Luôn delegate tới socket gốc để không làm mất hành vi protocol.
- Không subscribe thủ công bên trong interceptor; hãy nối operator reactive vào publisher trả về.
- Không đọc hoặc ghi đè payload nếu không cần thiết.
- Không ghi data/metadata nhạy cảm vào log.
- Xác định rõ metric đo từ lúc nào tới lúc nào để tránh so sánh hai phạm vi khác nhau.

## 10. Interceptor tại SocketAcceptor

SocketAcceptorInterceptor decorate acceptor và có quyền truy cập setup payload cùng hai socket của connection. Đây là nơi phù hợp để ghi lại MIME type, kiểm tra capability hoặc gắn ngữ cảnh theo connection.

~~~java
SocketAcceptorInterceptor setupAudit = next ->
        (setup, sendingRSocket) -> {
            log.info(
                    "RSocket setup: dataMimeType={}, metadataMimeType={}, resume={}",
                    setup.dataMimeType(),
                    setup.metadataMimeType(),
                    setup.isResumeEnabled());

            return next.accept(setup, sendingRSocket);
        };
~~~

Đăng ký:

~~~java
RSocketServer.create(acceptor)
        .interceptors(registry ->
                registry.forSocketAcceptor(setupAudit))
        .bind(TcpServerTransport.create("localhost", 7000));
~~~

Nếu cần từ chối connection vì setup không hợp lệ, có thể kiểm tra trước khi gọi next.accept(...) và trả publisher lỗi phù hợp. Việc xác thực danh tính và phân quyền vẫn cần một cơ chế bảo mật thực sự; MIME type hoặc resume flag không phải bằng chứng xác thực.

Không giữ ConnectionSetupPayload hoặc buffer metadata sau khi callback kết thúc nếu không quản lý reference count đúng cách. Chỉ trích xuất các giá trị cần thiết rồi lưu vào context của connection.

## 11. Interceptor ở transport connection

forConnection(DuplexConnectionInterceptor) cho phép decorate DuplexConnection ở tầng transport. Đây là phạm vi thấp nhất trong các interceptor được cung cấp bởi InterceptorRegistry.

Có thể dùng khi cần:

- Quan sát frame gửi đi và nhận về.
- Đo số byte và lưu lượng ở transport.
- Phân tích thời điểm connection đóng hoặc lỗi.
- Gắn công cụ trace ở mức frame khi thư viện quan sát request-level không đủ.

Transport interceptor nhìn thấy frame protocol, không phải object nghiệp vụ đã deserialize. Nếu cần biết request thuộc route nào, cần giải mã metadata đúng MIME type; không nên coi mọi metadata byte là chuỗi văn bản.

Vì interceptor này nằm sát transport, tránh sửa byte hoặc thay đổi thứ tự frame nếu không thực sự hiểu protocol. Một lỗi nhỏ ở đây có thể làm hỏng toàn bộ connection thay vì chỉ một request.

## 12. Theo dõi vòng đời từng request

Trong rsocket-core 1.1.x, forRequestsInRequester(...) và forRequestsInResponder(...) đăng ký một RequestInterceptor cho từng request. Các hook chính gồm:

| Hook | Khi nào được gọi | Metric có thể ghi |
|---|---|---|
| onStart(streamId, requestType, metadata) | Request được chấp nhận và bắt đầu | Số request theo loại frame, stream đang chạy |
| onTerminate(streamId, requestType, error) | Request đã bắt đầu kết thúc | Thành công, lỗi, thời gian chạy nếu có timestamp |
| onCancel(streamId, requestType) | Request đã bắt đầu bị hủy | Số stream bị cancel |
| onReject(cause, requestType, metadata) | Request không thể bắt đầu | Lease hết quota, payload không hợp lệ, request bị từ chối |

Khác với RSocketInterceptor, request lifecycle interceptor cho phép quan sát riêng từng stream mà không phải bọc từng method. Interface này cũng là Disposable; implementation cần giải phóng tài nguyên của chính nó khi bị dispose.

Khi dùng metadata trong hook, hãy đọc theo cấu trúc đã thỏa thuận và tránh ghi credential. Callback có thể chạy trên event loop; không thực hiện I/O blocking hoặc xử lý nặng bên trong hook.

## 13. Phối hợp nhiều interceptor

Một connection có thể cần nhiều interceptor cùng lúc: trace, metric, rate control và kiểm tra setup. Hãy xếp chúng theo trách nhiệm và giữ mỗi interceptor nhỏ.

Ví dụ:

~~~java
Consumer<InterceptorRegistry> instrumentation = registry -> registry
        .forSocketAcceptor(setupAudit)
        .forResponder(requestResponseMetrics)
        .forResponder(
                LimitRateInterceptor.forResponder(64, 48))
        .forRequestsInResponder(socket ->
                requestLifecycleMetrics.forSocket(socket));
~~~

requestLifecycleMetrics.forSocket(socket) đại diện cho factory do ứng dụng triển khai để tạo một tracker riêng cho socket/connection. Cách tổ chức này giúp tránh dùng chung state mutable giữa nhiều connection.

Một số nguyên tắc:

- Mỗi request nên có correlation ID hoặc trace context để ghép log giữa client và server.
- Metric nên gắn tag có cardinality giới hạn; không dùng request ID hoặc user ID làm tag metric.
- Thứ tự interceptor có thể ảnh hưởng cách publisher được decorate. Kiểm thử thứ tự nếu interceptor phụ thuộc nhau.
- Không tạo một bộ đếm toàn cục cho từng stream mà không có giới hạn vòng đời.
- Khi connection đóng, giải phóng tài nguyên được tạo riêng cho connection.

## 14. Cấu hình transport TCP và WebSocket

Connector và server đều nhận transport abstraction. Phần xử lý interaction model không cần biết frame đang đi qua TCP hay WebSocket.

Client TCP:

~~~java
RSocketConnector.create()
        .connect(TcpClientTransport.create("localhost", 7000));
~~~

Client WebSocket:

~~~java
RSocketConnector.create()
        .connect(WebsocketClientTransport.create(
                URI.create("ws://localhost:8080/rsocket")));
~~~

Server TCP:

~~~java
RSocketServer.create(acceptor)
        .bind(TcpServerTransport.create("localhost", 7000));
~~~

Với WebSocket, server sử dụng WebsocketServerTransport từ module Netty và cấu hình endpoint/path tương ứng. Hãy bảo đảm reverse proxy cho phép HTTP Upgrade và timeout đủ dài cho kết nối realtime. Khi triển khai TLS, dùng cấu hình transport bảo mật hoặc kết thúc TLS tại gateway theo chính sách của hệ thống; TLS không tự thay thế authentication và authorization ở tầng ứng dụng.

## 15. Kết hợp với Spring Boot

Spring Boot cung cấp tích hợp RSocket cho server và RSocketRequester cho client. Khi dùng Spring, các handler thường được khai báo bằng @MessageMapping, còn cấu hình transport và server có thể được quản lý qua thuộc tính ứng dụng hoặc bean cấu hình.

Ví dụ server TCP:

~~~yaml
spring:
  rsocket:
    server:
      transport: tcp
      port: 7000
~~~

Ví dụ server WebSocket:

~~~yaml
spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
      port: 8080
~~~

Ở phía client, Spring RSocketRequester.Builder cung cấp API cấp cao để tạo requester, thiết lập data/metadata MIME type và kết nối transport. Các interceptor ở tầng rsocket-java vẫn hữu ích khi cần quan sát hành vi protocol thấp hơn hoặc khi ứng dụng không dùng Spring handler abstraction.

Không nên cấu hình cùng một hành vi ở cả Spring và RSocket Java mà không hiểu thứ tự áp dụng. Ví dụ, một timeout ở tầng ứng dụng, một timeout ở connector và idle timeout của proxy có thể có phạm vi khác nhau.

## 16. Payload decoder và quản lý bộ nhớ

PayloadDecoder.DEFAULT là lựa chọn phù hợp khi ưu tiên tính đơn giản. Nó sao chép data và metadata ra khỏi frame buffer; ứng dụng không phải giữ reference tới buffer nguồn.

PayloadDecoder.ZERO_COPY tránh sao chép bằng retained slice. Khi bật, mọi Payload phải được release sau khi hoàn tất, kể cả nhánh lỗi hoặc cancel. Dùng try/finally hoặc các operator lifecycle phù hợp để bảo đảm release luôn xảy ra.

Ví dụ minh họa quản lý payload nhận được:

~~~java
socket.requestResponse(request)
        .doOnNext(payload -> {
            try {
                process(payload.getDataUtf8());
            } finally {
                payload.release();
            }
        });
~~~

Đoạn code chỉ phù hợp khi ứng dụng sở hữu payload theo cách cho phép release tại điểm đó. Nếu chuyển payload sang component khác hoặc giữ để xử lý bất đồng bộ, quyền sở hữu phải được chuyển giao rõ ràng. Không release hai lần và không truy cập payload sau khi đã release.

## 17. Quản lý vòng đời client và server

Connector trả publisher bất đồng bộ. Hãy chỉ dùng RSocket sau khi kết nối thành công và đóng socket khi ứng dụng dừng hoặc khi không còn cần connection.

Server bind trả về một closeable channel. Giữ handle này để đóng server có trật tự khi ứng dụng shutdown. Không tạo connector/server mới cho từng request; thông thường một RSocket connection dài hạn có thể multiplex nhiều stream.

Nên giám sát:

- RSocket.onClose() để biết connection-level error hoặc đóng bình thường.
- RSocket.availability() khi cần biết khả năng sẵn sàng của socket.
- Server channel onClose() để theo dõi server lifecycle.
- Số connection, số stream đang chạy, request theo interaction model.
- Tỷ lệ lỗi, timeout, cancel, reject và thời gian xử lý.

Không dùng onClose() của một stream-level publisher để thay thế theo dõi connection. Lỗi connection-level và lỗi của một request có phạm vi khác nhau.

## 18. Lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| TCP connect thành công nhưng SETUP thất bại | MIME type hoặc setup payload không tương thích | Kiểm tra connector và server setup |
| WebSocket trả HTTP 404/400 | Sai mapping path hoặc proxy chưa hỗ trợ Upgrade | Kiểm tra URI và cấu hình gateway |
| Request không tới handler | Sai route metadata hoặc codec | Kiểm tra metadata MIME type và routing |
| Server không xử lý request ngược | Client chưa cấu hình acceptor | Đăng ký RSocketConnector.acceptor(...) |
| Metric request bị đếm hai lần | Đăng ký cùng interceptor ở nhiều phạm vi | Xác định requester/responder và luồng gọi |
| Stream bị chậm dù network khỏe | Demand bị giới hạn hoặc consumer xử lý chậm | Kiểm tra LimitRateInterceptor, REQUEST_N và operator downstream |
| Buffer Netty tăng bất thường | Dùng zero-copy nhưng không release payload | Kiểm tra reference count và leak detector |
| Kết nối đóng sau thời gian idle | Keepalive hoặc proxy timeout không phù hợp | So sánh keepalive interval/max lifetime với timeout gateway |
| Payload lớn bị từ chối | Giới hạn inbound payload/frame không tương thích | Kiểm tra max frame length, fragmentation và reassembly limit |
| Request bị reject khi dùng lease | Hết quota hoặc chưa nhận LEASE mới | Kiểm tra cấu hình lease ở cả hai phía |

## 19. Checklist kiểm thử cấu hình

Một bộ kiểm thử tích hợp nên xác minh các lớp cấu hình riêng biệt:

1. **Transport:** kết nối TCP và WebSocket tới đúng endpoint.
2. **SETUP:** client gửi đúng data MIME type, metadata MIME type, setup payload và keepalive.
3. **Acceptor:** server đọc setup context và trả handler phù hợp cho từng connection.
4. **Interaction:** request-response, fire-and-forget, request-stream và request-channel hoạt động theo handler.
5. **Requester/responder:** request khởi tạo ở cả hai hướng nếu ứng dụng có dùng giao tiếp hai chiều.
6. **Interceptor:** xác minh mỗi request chỉ tạo metric đúng số lần và có kết quả cho success/error/cancel/reject.
7. **Flow control:** kiểm tra LimitRateInterceptor và backpressure không làm mất dữ liệu ngoài chính sách.
8. **Lease/resume:** kiểm tra quota và khôi phục connection khi các tính năng này được bật.
9. **Payload lifecycle:** kiểm tra không rò rỉ reference count khi dùng zero-copy.
10. **Shutdown:** đóng client và server channel, xác minh tài nguyên mạng được giải phóng.

Có thể bật logger io.rsocket.FrameLogger ở mức DEBUG trong môi trường thử nghiệm để quan sát frame. Không để log frame payload nhạy cảm ở production; frame logger có thể làm lộ metadata hoặc data ứng dụng và tạo lượng log rất lớn.

## 20. Nguyên tắc lựa chọn điểm cấu hình

| Nhu cầu | Điểm cấu hình phù hợp |
|---|---|
| Chọn TCP hay WebSocket | ClientTransport / ServerTransport |
| Đặt MIME type, setup payload và keepalive | RSocketConnector |
| Đặt timeout chờ SETUP và giới hạn inbound | RSocketServer |
| Tạo handler theo client hoặc connection | SocketAcceptor |
| Client nhận request từ server | RSocketConnector.acceptor(...) |
| Ghi log hoặc đo latency interaction | RSocketInterceptor ở requester/responder |
| Đo lifecycle của từng stream | RequestInterceptor |
| Quan sát frame ở transport | DuplexConnectionInterceptor |
| Kiểm tra metadata setup trước khi tạo handler | SocketAcceptorInterceptor |
| Giới hạn demand của stream outbound | LimitRateInterceptor hoặc operator trong handler |

Hãy bắt đầu từ hành vi cần quan sát hoặc điều chỉnh, sau đó chọn phạm vi nhỏ nhất có đủ thông tin. Cách này giúp interceptor dễ kiểm thử, dễ gỡ lỗi và ít tác động ngoài ý muốn tới các stream khác.

## Kết luận

RSocketConnector chịu trách nhiệm mở phiên từ client và cấu hình các tham số như MIME type, SETUP, keepalive, lease, resume và interceptor. RSocketServer bind transport, đặt giới hạn protocol và dùng SocketAcceptor để tạo handler theo connection. Interceptor mở rộng hành vi ở transport, acceptor, requester, responder hoặc lifecycle của từng request. Khi chọn đúng phạm vi, ứng dụng có thể đo lường, điều tiết và bảo vệ RSocket connection mà vẫn giữ rõ ranh giới giữa protocol và nghiệp vụ.

## Tài liệu tham khảo

- [RSocketConnector – rsocket-core 1.1.5 Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocketServer – rsocket-core 1.1.5 Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [InterceptorRegistry – rsocket-core 1.1.5 Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/plugins/InterceptorRegistry.html)
- [RequestInterceptor – rsocket-core 1.1.5 Javadoc](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/plugins/RequestInterceptor.html)
- [RSocket Java – GitHub](https://github.com/rsocket/rsocket-java)
