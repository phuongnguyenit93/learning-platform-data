# Các thành phần rsocket-core, rsocket-transport-netty và rsocket-test

## Bối cảnh: RSocket Java được chia thành các module theo trách nhiệm

RSocket Java là implementation Java của giao thức RSocket. Giao thức này cho phép hai peer trao đổi thông điệp bất đồng bộ trên một kết nối, hỗ trợ request-response, fire-and-forget, request-stream và request-channel. Trong ứng dụng Java, thư viện được chia thành nhiều artifact để tách phần giao thức, phần vận chuyển dữ liệu và công cụ phục vụ kiểm thử.

Ba module thường gặp là:

- **rsocket-core:** cung cấp API và phần xử lý cốt lõi của giao thức RSocket, gồm các interaction model, payload, frame, metadata, keepalive, resume, lease và SPI cho transport.
- **rsocket-transport-netty:** cung cấp transport dựa trên Netty để chạy RSocket qua TCP hoặc WebSocket.
- **rsocket-test:** cung cấp tiện ích và fixture phục vụ kiểm thử các thành phần RSocket.

Có thể hình dung luồng phụ thuộc như sau:

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B["rsocket-core"]
    A --> C["rsocket-transport-netty"]
    B --> C
    D["Bộ kiểm thử"] --> B
    D --> E["rsocket-test"]
    D --> F["reactor-test / StepVerifier"]
    C --> G["TCP hoặc WebSocket"]
~~~

Trong ứng dụng chạy thật, core định nghĩa cách trao đổi và xử lý tương tác; Netty kết nối các peer qua mạng. Khi viết test, rsocket-test bổ sung fixture để mô phỏng hoặc kiểm tra các thành phần giao thức mà không cần dựng mọi tình huống bằng một server mạng hoàn chỉnh.

Bài này giải thích vai trò của từng artifact, cách khai báo dependency, cách kết hợp chúng trong một ứng dụng Java và cách chọn mức kiểm thử phù hợp.

## 1. rsocket-core: API và giao thức cốt lõi

rsocket-core là phần trung tâm của RSocket Java. Module này định nghĩa các contract mà ứng dụng sử dụng để gửi hoặc xử lý tương tác. Nó không buộc ứng dụng phải dùng một transport cụ thể; transport được cung cấp qua các module bổ sung.

### Các API quan trọng

| API hoặc nhóm package | Vai trò |
|---|---|
| io.rsocket.RSocket | Contract cho các interaction model và trạng thái kết nối |
| io.rsocket.SocketAcceptor | Tiếp nhận SETUP và tạo RSocket xử lý request từ peer |
| io.rsocket.Payload | Đại diện cho data và metadata của một payload |
| io.rsocket.util.DefaultPayload | Tạo payload từ chuỗi, byte array, ByteBuffer hoặc ByteBuf |
| io.rsocket.core.RSocketConnector | Cấu hình và thiết lập kết nối phía client |
| io.rsocket.core.RSocketServer | Cấu hình và khởi động server RSocket |
| io.rsocket.exceptions | Các exception gắn với lỗi giao thức và lỗi ứng dụng |
| io.rsocket.metadata | Codec cho metadata, routing, authentication và composite metadata |
| io.rsocket.plugins | Interceptor cho transport, connection và request |
| io.rsocket.resume, io.rsocket.lease | Các thành phần hỗ trợ resume session và lease |

Contract RSocket có thể được dùng ở cả hai phía. Client thường giữ một RSocket để gọi server; server tạo một RSocket responder để xử lý các request nhận được. Vì RSocket là giao thức hai chiều, peer ở phía server cũng có thể gửi request về client nếu client đã cấu hình responder phù hợp.

### Bốn interaction model

Các phương thức của RSocket biểu diễn trực tiếp hình dạng dữ liệu của tương tác:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| requestResponse(Payload) | Mono<Payload> | Một request và tối đa một response |
| fireAndForget(Payload) | Mono<Void> | Gửi một request không yêu cầu response nghiệp vụ |
| requestStream(Payload) | Flux<Payload> | Một request mở ra nhiều response |
| requestChannel(Publisher<Payload>) | Flux<Payload> | Hai phía có thể trao đổi nhiều payload |

Các phương thức trả về Reactor publisher. Việc subscribe mới kích hoạt quá trình trao đổi dữ liệu. Vì vậy, code sử dụng core thường nối các thao tác bằng Mono và Flux thay vì tự quản lý thread chờ I/O.

Ví dụ, một client request-response:

~~~java
Mono<Payload> response = socket.requestResponse(
    DefaultPayload.create("device.status")
);
~~~

Ví dụ một client request-stream:

~~~java
Flux<Payload> readings = socket.requestStream(
    DefaultPayload.create("sensor-01")
);
~~~

Payload là đối tượng mang nội dung giao thức. Data có thể là JSON, CBOR, protobuf hoặc định dạng riêng do ứng dụng thỏa thuận. Metadata có thể mang routing, authentication, tracing hoặc thông tin phụ trợ. Hai peer cần thống nhất MIME type và cách mã hóa payload.

### RSocketConnector và RSocketServer

RSocketConnector là điểm vào phổ biến để tạo kết nối client. Nó nhận một ClientTransport và trả về Mono<RSocket>. Ngoài thiết lập kết nối, connector còn cho phép cấu hình data MIME type, metadata MIME type, SETUP payload, keepalive, interceptor, resume và lease.

RSocketServer khởi động server với một SocketAcceptor và một ServerTransport. SocketAcceptor xử lý thông tin SETUP của kết nối mới và tạo responder RSocket cho peer đó.

~~~java
Mono<RSocket> connection = RSocketConnector.create()
    .dataMimeType("application/json")
    .metadataMimeType("message/x.rsocket.composite-metadata.v0")
    .connect(transport);
~~~

~~~java
Mono<Closeable> server = RSocketServer
    .create(SocketAcceptor.with(responder))
    .bind(serverTransport);
~~~

Các đoạn mã trên minh họa API và có thể cần điều chỉnh kiểu handle theo transport cụ thể. Connector và server đều thuộc core; transport thực tế được truyền từ module khác.

### Payload và quản lý bộ nhớ

Payload trong RSocket Java có liên quan đến reference counting của Netty. Điều này đặc biệt quan trọng khi làm việc với ByteBuf hoặc bật chế độ zero-copy.

- Với PayloadDecoder.DEFAULT, data và metadata được sao chép khỏi frame đầu vào. Cách này dễ quản lý bộ nhớ hơn.
- Với PayloadDecoder.ZERO_COPY, data và metadata là các retained slice của ByteBuf nền. Ứng dụng phải quản lý vòng đời và release payload đúng lúc sau khi xử lý xong.
- Không giữ ByteBuf hoặc slice trong một tác vụ bất đồng bộ sau khi payload đã được giải phóng.
- Nếu cần dùng dữ liệu lâu hơn vòng đời payload, hãy sao chép sang kiểu dữ liệu do ứng dụng sở hữu.

Không nên bật zero-copy chỉ vì muốn tăng tốc. Hãy đo hiệu năng trước, sau đó kiểm tra kỹ ownership và leak khi bật chế độ này.

## 2. rsocket-transport-netty: vận chuyển qua TCP và WebSocket

Core định nghĩa các interface transport như ClientTransport và ServerTransport. rsocket-transport-netty triển khai các interface đó bằng Netty và cung cấp các adapter để kết nối qua TCP hoặc WebSocket.

Các lớp thường gặp:

| Lớp | Vai trò |
|---|---|
| TcpClientTransport | Client mở kết nối RSocket qua TCP |
| TcpServerTransport | Server lắng nghe RSocket qua TCP |
| WebsocketClientTransport | Client kết nối RSocket qua WebSocket |
| WebsocketServerTransport | Server nhận RSocket qua WebSocket |

Transport chịu trách nhiệm kết nối byte stream và chuyển dữ liệu thành các frame cho core. Nó không quyết định nghiệp vụ như tra cứu thiết bị, tạo đơn hàng hoặc xử lý telemetry.

### Khi nào dùng TCP?

TCP phù hợp với giao tiếp service-to-service hoặc client/server mà hai phía có thể sử dụng một kết nối TCP trực tiếp. Ví dụ, các service Java trong cùng mạng nội bộ có thể dùng TCP để trao đổi stream dữ liệu và command.

Ưu điểm của TCP transport:

- Kết nối trực tiếp, không cần lớp HTTP/WebSocket trung gian.
- Phù hợp cho giao tiếp giữa các backend có quyền kiểm soát cả hai đầu.
- Có thể dùng các cấu hình keepalive, giới hạn frame và fragmentation của RSocket.

Cần thiết kế TLS, xác thực, phân quyền mạng và chính sách kết nối phù hợp với môi trường triển khai. Không nên để một endpoint TCP RSocket công khai mà không có kiểm soát truy cập.

### Khi nào dùng WebSocket?

WebSocket phù hợp khi client cần kết nối qua hạ tầng web, reverse proxy hoặc môi trường trình duyệt hỗ trợ WebSocket. RSocket vẫn giữ các interaction model ở tầng giao thức; WebSocket chỉ là transport mang frame.

Ví dụ khởi tạo client WebSocket:

~~~java
ClientTransport transport = WebsocketClientTransport.create(
    URI.create("ws://localhost:8080/rsocket")
);

Mono<RSocket> socket = RSocketConnector.connectWith(transport);
~~~

Địa chỉ URI và đường dẫn phải khớp với endpoint server. Khi triển khai thực tế qua TLS, dùng WSS và cấu hình proxy/load balancer cho WebSocket upgrade, timeout và giới hạn kết nối.

### Ví dụ TCP client/server tối giản

Server tạo responder xử lý request-response:

~~~java
RSocket responder = new RSocket() {
    @Override
    public Mono<Payload> requestResponse(Payload request) {
        String message = request.getDataUtf8();
        request.release();

        return Mono.just(
            DefaultPayload.create("pong:" + message)
        );
    }
};

Closeable server = RSocketServer
    .create(SocketAcceptor.with(responder))
    .bind(TcpServerTransport.create("localhost", 7000))
    .block();
~~~

Client kết nối và gửi request:

~~~java
RSocket client = RSocketConnector
    .connectWith(TcpClientTransport.create("localhost", 7000))
    .block();

try {
    Payload response = client
        .requestResponse(DefaultPayload.create("ping"))
        .block();

    try {
        System.out.println(response.getDataUtf8());
    } finally {
        response.release();
    }
} finally {
    client.dispose();
    server.dispose();
}
~~~

Ví dụ minh họa cách nối core với Netty TCP transport. Trong ứng dụng thật, hãy quản lý server handle ở lifecycle của ứng dụng, đặt timeout cho các thao tác đồng bộ trong mã khởi động, cấu hình MIME type và xử lý lỗi khi kết nối hoặc request thất bại.

Phương thức requestResponse trả về Mono nên không nên gọi block() trên event loop hoặc trong controller reactive. block() trong ví dụ chỉ nhằm làm rõ trình tự của chương trình demo đồng bộ; ứng dụng reactive nên compose publisher và để runtime quản lý subscription.

## 3. rsocket-test: tiện ích kiểm thử RSocket

rsocket-test là artifact phục vụ kiểm thử, không phải dependency cần thiết cho ứng dụng production. Module này cung cấp các tiện ích và fixture cho dự án RSocket, giúp kiểm tra hành vi của các thành phần giao thức mà không phải tự xây dựng mọi test double hoặc transport giả.

Có thể dùng rsocket-test để hỗ trợ các nhóm kiểm thử như:

- Kiểm tra logic responder và requester với peer giả lập.
- Mô phỏng các tương tác RSocket trong những tình huống có kiểm soát.
- Kiểm tra luồng request, response, cancellation và lỗi.
- Hỗ trợ kiểm thử các thành phần core mà không phải mở cổng mạng thật cho từng test.

Tên lớp và API fixture cụ thể phụ thuộc phiên bản artifact. Hãy mở Javadoc hoặc xem nội dung artifact đúng phiên bản đang khai báo trước khi dùng một helper cụ thể. Không nên sao chép ví dụ từ một phiên bản cũ nếu package hoặc constructor đã thay đổi.

### Phân biệt rsocket-test với reactor-test

Hai dependency này phục vụ các mục tiêu khác nhau:

| Dependency | Mục đích |
|---|---|
| rsocket-test | Fixture và tiện ích dành riêng cho kiểm thử RSocket |
| reactor-test | Công cụ kiểm tra publisher Reactor, nổi bật là StepVerifier và virtual time |
| JUnit Jupiter | Test runner và assertion cho test Java |
| Mockito hoặc AssertJ | Mock và assertion bổ sung nếu dự án cần |

StepVerifier thuộc reactor-test, không thuộc rsocket-test. Nếu test dùng StepVerifier, hãy khai báo reactor-test rõ ràng thay vì dựa vào dependency bắc cầu.

### Kiểm tra publisher bằng StepVerifier

Ví dụ sau kiểm tra một responder giả lập trả đúng response. Nó kiểm tra contract RSocket và Reactor mà không mở kết nối mạng:

~~~java
@Test
void respondsToRequestResponse() {
    RSocket responder = new RSocket() {
        @Override
        public Mono<Payload> requestResponse(Payload request) {
            String value = request.getDataUtf8();
            request.release();

            return Mono.just(
                DefaultPayload.create("pong:" + value)
            );
        }
    };

    Mono<String> result = responder
        .requestResponse(DefaultPayload.create("ping"))
        .map(payload -> {
            try {
                return payload.getDataUtf8();
            } finally {
                payload.release();
            }
        });

    StepVerifier.create(result)
        .expectNext("pong:ping")
        .verifyComplete();
}
~~~

Đây là unit test cho contract và luồng tín hiệu. Nó chưa kiểm tra frame encoding, TCP, WebSocket, SETUP, metadata hoặc hành vi reconnect. Những phần đó cần integration test với transport thật hoặc fixture phù hợp.

### Chọn test ở đúng tầng

| Tầng kiểm thử | Công cụ phù hợp | Điều cần xác nhận |
|---|---|---|
| Logic nghiệp vụ | JUnit, Mockito, StepVerifier | Mapping payload, xử lý lỗi và kết quả |
| Contract RSocket | rsocket-test, stub hoặc fixture | Interaction model, demand, cancellation |
| Transport integration | rsocket-transport-netty và server/client loopback | SETUP, frame, kết nối TCP/WebSocket |
| Kiểm thử tải | Test harness và công cụ đo tải | Throughput, latency, concurrency, buffer và backpressure |

Không nên dùng một unit test để kết luận transport hoạt động đúng. Ngược lại, không cần dựng TCP server thật cho mọi phép kiểm tra một hàm chuyển đổi payload.

## 4. Khai báo dependency trong Maven và Gradle

Các artifact có cùng group ID là io.rsocket. Nên giữ phiên bản các module RSocket đồng nhất để tránh xung đột API và dependency.

Ví dụ dưới đây dùng phiên bản 1.1.5 làm mốc minh họa. Khi triển khai, hãy chọn phiên bản phát hành tương thích với Spring Boot, Reactor và Netty mà ứng dụng đang sử dụng. Tránh trộn release và snapshot trong cùng runtime.

### Maven

~~~xml
<properties>
    <rsocket.version>1.1.5</rsocket.version>
</properties>

<dependencies>
    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-core</artifactId>
        <version>${rsocket.version}</version>
    </dependency>

    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-transport-netty</artifactId>
        <version>${rsocket.version}</version>
    </dependency>

    <dependency>
        <groupId>io.rsocket</groupId>
        <artifactId>rsocket-test</artifactId>
        <version>${rsocket.version}</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong dự án thực tế, có thể thay các phiên bản lặp lại bằng property hoặc import BOM nếu dự án đã quản lý dependency theo BOM. Các thư viện test như JUnit Jupiter và reactor-test cần được khai báo theo dependency management của dự án.

### Gradle Kotlin DSL

~~~kotlin
val rsocketVersion = "1.1.5"

dependencies {
    implementation("io.rsocket:rsocket-core:$rsocketVersion")
    implementation("io.rsocket:rsocket-transport-netty:$rsocketVersion")

    testImplementation("io.rsocket:rsocket-test:$rsocketVersion")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Nếu dự án dùng Spring Boot, hãy kiểm tra xem spring-boot-starter-rsocket đã cung cấp core và transport phù hợp hay chưa. Tránh thêm một phiên bản RSocket khác đè lên phiên bản mà Spring Boot đang quản lý nếu chưa kiểm tra compatibility.

### Module nào nên xuất hiện ở từng classpath?

| Module | Runtime application | Test classpath |
|---|---:|---:|
| rsocket-core | Có | Có |
| rsocket-transport-netty | Có nếu chạy Netty TCP/WebSocket | Có khi test transport Netty |
| rsocket-test | Không | Có |
| reactor-test | Không | Có khi kiểm tra Mono/Flux bằng StepVerifier |

Một ứng dụng chỉ dùng RSocket API qua transport khác có thể không cần rsocket-transport-netty. Ngược lại, ứng dụng dùng TCP hoặc WebSocket Netty cần transport-netty ở runtime.

## 5. Cách ba module phối hợp trong một ứng dụng

Một luồng khởi tạo và xử lý request-response thường diễn ra như sau:

1. Ứng dụng tạo responder RSocket và đăng ký với SocketAcceptor.
2. RSocketServer trong core nhận SocketAcceptor.
3. TcpServerTransport hoặc WebsocketServerTransport trong Netty mở endpoint.
4. Client tạo TcpClientTransport hoặc WebsocketClientTransport.
5. RSocketConnector trong core thực hiện SETUP và tạo RSocket client.
6. Client gọi interaction model; core tạo và xử lý frame qua transport.
7. Server responder nhận payload, chạy logic và trả publisher response.
8. Khi ứng dụng đóng, client và server handle được dispose đúng vòng đời.

~~~mermaid
sequenceDiagram
    participant App as Java Application
    participant Core as rsocket-core
    participant Netty as rsocket-transport-netty
    participant Peer as Remote Peer
    App->>Core: Tạo RSocketServer / RSocketConnector
    Core->>Netty: bind hoặc connect transport
    Netty->>Peer: TCP hoặc WebSocket
    Peer-->>Core: SETUP / request frames
    Core-->>App: Gọi responder RSocket
    App-->>Core: Mono hoặc Flux response
    Core->>Netty: Encode và gửi frame
    Netty->>Peer: Response payload
~~~

rsocket-test không nằm trên đường xử lý production. Nó tham gia ở giai đoạn phát triển và kiểm thử, giúp kiểm tra hành vi core hoặc xây dựng test fixture.

## 6. Lỗi thường gặp khi sử dụng các module

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ thêm rsocket-core nhưng lại gọi TCP transport | Không có lớp triển khai TCP client/server | Thêm rsocket-transport-netty |
| Đưa rsocket-test vào runtime | Classpath production có dependency chỉ dành cho test | Dùng test scope hoặc testImplementation |
| Dùng rsocket-test thay cho reactor-test | Thiếu StepVerifier hoặc test publisher cần thiết | Khai báo reactor-test riêng |
| Dùng version khác nhau giữa các artifact | Có thể gặp lỗi binary compatibility hoặc dependency conflict | Đồng bộ version hoặc dùng BOM |
| Cho rằng core tự mở socket | Không có transport thực thi | Truyền ClientTransport/ServerTransport vào connector/server |
| Dùng WebSocket nhưng quên endpoint path | Client không kết nối được server | Đồng bộ URI và cấu hình WebSocket endpoint |
| Gọi block() trên event loop | Làm nghẽn các request khác | Compose Mono/Flux và chỉ block ở ranh giới demo hoặc ứng dụng imperative |
| Bỏ qua payload ownership | Có thể rò rỉ ByteBuf hoặc giải phóng quá sớm | Theo dõi reference count và release đúng lúc |
| Bật ZERO_COPY nhưng không quản lý buffer | Rò rỉ bộ nhớ hoặc lỗi truy cập buffer đã release | Chỉ dùng khi hiểu ownership và đã kiểm thử leak |
| Chỉ unit test responder rồi kết luận transport tốt | Bỏ sót lỗi frame, SETUP, network và lifecycle | Bổ sung integration test với Netty |
| Đóng RSocket client nhưng quên server handle | Server listener có thể vẫn chạy | Dispose cả client và server trong lifecycle tương ứng |

## 7. Lộ trình học và thực hành

Có thể học các module theo trình tự sau:

1. **Bắt đầu với rsocket-core:** đọc contract RSocket, Payload, SocketAcceptor, RSocketConnector và RSocketServer.
2. **Thêm rsocket-transport-netty:** dựng server TCP và client TCP, sau đó thử chuyển sang WebSocket.
3. **Kiểm tra payload:** trao đổi data và metadata, thống nhất MIME type và quản lý buffer.
4. **Thử các interaction model:** request-response, fire-and-forget, request-stream và request-channel.
5. **Thêm kiểm thử:** dùng rsocket-test cho fixture RSocket, reactor-test cho publisher và Netty loopback cho transport integration.
6. **Mở rộng vận hành:** kiểm tra keepalive, timeout, cancellation, resume, lease, giới hạn payload và logging frame.

Khi debug, có thể bật logger frame của RSocket ở mức phù hợp để quan sát các frame trao đổi. Trong production, cần kiểm soát mức log vì payload hoặc metadata có thể chứa thông tin nhạy cảm.

## Kết luận

Ba module có trách nhiệm bổ sung cho nhau. rsocket-core cung cấp contract và xử lý giao thức; rsocket-transport-netty đưa frame qua TCP hoặc WebSocket; rsocket-test hỗ trợ xây dựng kiểm thử cho các thành phần RSocket.

Hãy bắt đầu với core để hiểu API và interaction model, thêm Netty khi cần kết nối mạng, và đặt test utilities trong test classpath. Giữ phiên bản artifact nhất quán, quản lý Payload đúng vòng đời và kết hợp unit test với integration test. Khi ranh giới giữa protocol, transport và test rõ ràng, ứng dụng RSocket Java sẽ dễ cấu hình, kiểm thử và vận hành hơn.

## Tài liệu tham khảo

- [RSocket Java source repository](https://github.com/rsocket/rsocket-java)
- [rsocket-core 1.1.5 API](https://javadoc.io/doc/io.rsocket/rsocket-core/1.1.5/index.html)
- [rsocket-transport-netty 1.1.5 API](https://javadoc.io/doc/io.rsocket/rsocket-transport-netty/1.1.5/index.html)
- [rsocket-test 1.1.5 API](https://javadoc.io/doc/io.rsocket/rsocket-test/1.1.5/index.html)
- [rsocket-test artifact information](https://socket.dev/maven/package/io.rsocket/rsocket-test/1.1.5)
