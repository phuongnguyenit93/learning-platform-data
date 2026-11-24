# Bảo vệ riêng yêu cầu ngược từ máy chủ về phía kết nối

## Bối cảnh: máy chủ cũng có thể gọi ngược về client

RSocket là giao thức hai chiều. Sau khi kết nối được thiết lập, hai peer đều có thể vừa gửi request vừa xử lý request từ phía bên kia. Vì vậy, một ứng dụng thường được gọi là client vẫn có thể đóng vai trò responder và nhận yêu cầu do máy chủ khởi tạo.

Ví dụ, một dịch vụ quản lý thiết bị giữ kết nối RSocket tới các gateway. Khi cần đồng bộ cấu hình hoặc yêu cầu gateway chụp trạng thái, máy chủ dùng requester gắn với kết nối để gửi request ngược về gateway. Gateway nhận request qua responder cục bộ và thực thi hành động trên thiết bị.

Luồng này tạo ra một ranh giới bảo mật riêng:

- Ở chiều thông thường, client gửi request tới server; server xác thực và phân quyền request đến.
- Ở chiều ngược, server gửi request tới client; client phải xác thực danh tính server và kiểm tra server có được phép gọi route đó hay không.

Cấu hình bảo vệ các route phía server không tự động bảo vệ responder phía client. Nếu client chấp nhận request ngược mà không kiểm tra danh tính peer, bất kỳ thành phần nào có thể gửi request qua kết nối hoặc chiếm quyền kết nối đều có thể kích hoạt handler nhạy cảm.

Bài học này tập trung vào cách đăng ký responder phía client, đặt interceptor bảo mật đúng tại điểm nhận request ngược, xác thực server bằng token hoặc danh tính transport, phân quyền theo route và kiểm thử các trường hợp bị từ chối.

## 1. Hiểu đúng hướng của request trong RSocket

Trong HTTP truyền thống, client thường gửi request và server trả response. RSocket giữ kết nối hai chiều và cho phép mỗi peer khởi tạo request sau khi SETUP hoàn tất. Vì vậy, từ “client” và “server” chỉ mô tả vai trò lúc thiết lập kết nối hoặc vai trò triển khai; chúng không quyết định cố định bên nào được gửi request.

Ví dụ kết nối giữa máy chủ quản lý và gateway:

~~~mermaid
sequenceDiagram
    participant G as Gateway (client)
    participant S as Server quản lý
    G->>S: SETUP + thông tin xác thực gateway
    Note over G,S: Kết nối RSocket được thiết lập
    G->>S: REQUEST_RESPONSE gateway.status
    S-->>G: PAYLOAD trạng thái
    S->>G: REQUEST_RESPONSE gateway.apply-config
    Note over G: Gateway xác thực server và kiểm tra quyền route
    G-->>S: PAYLOAD kết quả áp dụng
~~~

Trong ví dụ:

- Gateway là requester khi gửi gateway.status.
- Server là responder cho request gateway.status.
- Server trở thành requester khi gọi gateway.apply-config.
- Gateway trở thành responder cho request ngược gateway.apply-config.

Mỗi interaction có một requester và một responder cụ thể. Hai vai trò này đổi theo hướng của request, không phải theo tên client/server.

### Ba lớp cần phân biệt

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Kết nối | Peer nào đã thiết lập session? | Gateway kết nối tới server |
| Xác thực | Ai đang gửi request hiện tại? | Dịch vụ device-orchestrator |
| Phân quyền | Peer đó được gọi route nào? | Chỉ được gọi gateway.refresh và gateway.apply-config |

Xác thực gateway trong SETUP giúp server biết gateway nào đang kết nối. Điều đó không tự chứng minh với gateway rằng request ngược thực sự do server đáng tin cậy gửi. Gateway cần một cơ chế xác thực server độc lập.

## 2. Xác định đúng điểm nhận request ngược

Phía client cần có responder để xử lý request do server gửi. Spring Framework cho phép dùng RSocketMessageHandler với các phương thức @MessageMapping để tạo responder phía client.

Ví dụ handler:

~~~java
class GatewayReverseHandler {

    private final GatewayCommandService commandService;

    GatewayReverseHandler(GatewayCommandService commandService) {
        this.commandService = commandService;
    }

    @MessageMapping("gateway.refresh")
    Mono<CommandAck> refresh(@Payload RefreshCommand command) {
        return commandService.refresh(command);
    }

    @MessageMapping("gateway.apply-config")
    Mono<CommandAck> applyConfig(@Payload ConfigCommand command) {
        return commandService.apply(command);
    }
}
~~~

Các route này là API mà gateway công bố cho server gọi ngược. Chỉ đăng ký những route cần thiết; không tạo một handler tổng quát có thể thực thi lệnh tùy ý.

Tạo responder và gắn vào RSocketRequester.Builder:

~~~java
SocketAcceptor clientResponder =
    RSocketMessageHandler.responder(
        strategies,
        new GatewayReverseHandler(commandService)
    );

RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .rsocketConnector(connector ->
        connector.acceptor(clientResponder)
    )
    .tcp(serverHost, serverPort);
~~~

RSocketMessageHandler.responder(...) tạo một SocketAcceptor từ các handler có annotation. RSocketConnector.acceptor(...) đăng ký responder cục bộ để xử lý request đến từ peer. RSocketRequester.Builder.rsocketConnector(...) mở điểm cấu hình connector cấp thấp.

Đoạn code trên chỉ đăng ký responder. Nó chưa áp dụng xác thực hoặc phân quyền cho các request ngược. Phần bảo mật cần được gắn vào chính acceptor của connector, nơi gateway nhận request từ server.

### Vì sao không chỉ bảo vệ controller phía server?

Spring Security RSocket thường được gắn vào RSocketServer để bảo vệ các request đến server. Cấu hình đó kiểm soát chiều client gọi server. Request ngược được xử lý bởi responder phía client, nằm trong RSocketConnector của gateway.

Do đó, cần có interceptor bảo mật tại connector phía gateway. Nếu chỉ cấu hình RSocketSecurity cho server mà không gắn policy vào client responder, route ngược vẫn có thể không được bảo vệ theo chính sách mà gateway mong muốn.

## 3. Xác thực server riêng với xác thực client trong SETUP

RSocket dùng frame SETUP do bên khởi tạo kết nối gửi để thương lượng MIME type và các tham số session. Trong mô hình gateway kết nối tới server, thông tin xác thực trong SETUP thường giúp server xác thực gateway.

Điều này tạo ra hai danh tính riêng:

- **Danh tính gateway:** được server xác thực khi gateway kết nối.
- **Danh tính server:** phải được gateway xác thực trước khi gateway thực thi request ngược.

Không nên lấy clientId trong payload hoặc thông tin gateway gửi lên SETUP rồi xem đó là bằng chứng danh tính server. Đó là thông tin do phía khởi tạo kết nối cung cấp.

Có hai cách phổ biến để xác thực peer gửi request ngược:

### Cách A: xác thực server bằng token ở từng request

Server gắn một bearer token do hệ thống cấp quyền phát hành vào metadata của từng request ngược. Gateway xác minh chữ ký, issuer, audience và thời hạn token trước khi phân quyền route.

Cách này phù hợp khi:

- Một kết nối được dùng chung cho nhiều service hoặc nhiều tenant.
- Quyền của server có thể thay đổi theo từng request.
- Cần thu hồi hoặc xoay token mà không phải đóng toàn bộ kết nối.
- Mỗi route cần một scope riêng.

### Cách B: xác thực server ở tầng transport

Có thể dùng TLS hai chiều (mTLS) để gateway kiểm tra chứng thư của server và server kiểm tra chứng thư gateway. Sau handshake, ứng dụng cần ánh xạ danh tính chứng thư đã được xác minh vào ngữ cảnh bảo mật của connection hoặc request.

mTLS xác thực peer ở tầng transport và mã hóa dữ liệu trên đường truyền. Nó không tự quyết định server được phép gọi mọi route của gateway. Gateway vẫn cần policy phân quyền ở tầng ứng dụng.

Trong nhiều hệ thống, mTLS và token theo request được kết hợp: mTLS bảo vệ kết nối và xác thực service ở tầng transport; token mang scope hoặc ngữ cảnh quyền cụ thể cho từng request.

## 4. Gửi token trong metadata của request ngược

Spring RSocket hỗ trợ bearer token qua metadata extension. Server có thể gửi token dưới dạng metadata của từng request.

Ví dụ server gửi lệnh cấu hình tới gateway:

~~~java
private static final MimeType BEARER_AUTH_MIME =
    MimeTypeUtils.parseMimeType(
        "message/x.rsocket.authentication.bearer.v0"
    );

Mono<CommandAck> sendConfig(
        RSocketRequester gatewayRequester,
        ConfigCommand command,
        String serverAccessToken) {

    return gatewayRequester
        .route("gateway.apply-config")
        .metadata(serverAccessToken, BEARER_AUTH_MIME)
        .data(command)
        .retrieveMono(CommandAck.class);
}
~~~

gatewayRequester là requester đại diện cho kết nối tới gateway. Server có thể lấy requester này trong @ConnectMapping hoặc @MessageMapping của Spring và quản lý nó theo vòng đời connection.

Token trong ví dụ phải là token do issuer đáng tin cậy cấp cho service server. Token cần có audience hướng tới gateway hoặc nhóm gateway tương ứng. Không dùng token người dùng cuối nếu gateway cần xác thực danh tính service gửi lệnh.

Metadata được mã hóa theo MIME type của authentication extension. Nếu dùng composite metadata, token có thể đi cùng route và các metadata entry khác trên cùng request.

### Token phải đại diện cho đúng service

Ví dụ claim JWT có thể chứa:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "device-orchestrator",
  "aud": ["gateway-control"],
  "scope": "gateway:refresh gateway:apply-config",
  "exp": 1795350000
}
~~~

Gateway cần kiểm tra ít nhất:

- Chữ ký token hợp lệ theo key của issuer tin cậy.
- iss đúng issuer đã cấu hình.
- aud bao gồm ứng dụng hoặc nhóm gateway nhận request.
- exp chưa hết hạn và nbf đã có hiệu lực nếu được sử dụng.
- Scope hoặc authority đủ cho route đang gọi.

JWT hợp lệ về chữ ký nhưng có audience sai vẫn phải bị từ chối. Không chỉ kiểm tra rằng token có thể decode được.

## 5. Cấu hình Spring Security cho responder phía client

Spring Security cung cấp RSocketSecurity để cấu hình xác thực và phân quyền payload. Với JWT, jwt() đăng ký cơ chế chuyển bearer metadata thành Authentication bằng BearerPayloadExchangeConverter. Gateway có thể dùng cùng cơ chế đó cho request ngược bằng cách gắn interceptor vào connector.

Ví dụ policy dành riêng cho các route gateway nhận từ server:

~~~java
@Configuration
@EnableRSocketSecurity
class GatewayReverseSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor reversePayloadSecurity(
            RSocketSecurity security) {

        security
            .authorizePayload(authorize -> authorize
                // SETUP do gateway gửi khi kết nối tới server.
                .setup().permitAll()

                // Chỉ service có scope tương ứng được gọi route này.
                .route("gateway.refresh")
                    .hasAuthority("SCOPE_gateway:refresh")
                .route("gateway.apply-config")
                    .hasAuthority("SCOPE_gateway:apply-config")

                // Từ chối request mới không có route được cho phép.
                .anyRequest().denyAll()

                // Các payload tiếp diễn của interaction đã được mở.
                .anyExchange().permitAll()
            )
            .jwt(Customizer.withDefaults());

        return security.build();
    }

}
~~~

Cấu hình trên giả định JWT authority converter ánh xạ các scope thành authority có tiền tố SCOPE_. Nếu hệ thống sử dụng quy tắc claim hoặc tiền tố khác, hãy cấu hình converter và tên authority tương ứng.

ReactiveJwtDecoder cũng cần được cấu hình để xác minh token:

~~~java
@Bean
ReactiveJwtDecoder jwtDecoder() {
    return ReactiveJwtDecoders.fromIssuerLocation(
        "https://identity.example.com"
    );
}
~~~

Trong hệ thống thực tế, cần thêm validator cho audience gateway-control và các quy tắc claim riêng của tổ chức. Không chỉ dựa vào issuer nếu token có thể được phát hành cho nhiều resource server khác nhau.

Ví dụ JWT cần Spring Security RSocket và OAuth 2.0 Resource Server/JWT support. Trong dự án Spring Boot, có thể dùng spring-security-rsocket cùng spring-boot-starter-oauth2-resource-server; để Spring Boot quản lý phiên bản dependency theo BOM của dự án.

### Vì sao có cả anyRequest() và anyExchange()?

Một request-stream hoặc request-channel bắt đầu bằng frame request chứa route và metadata. Các payload tiếp theo của cùng interaction có thể không lặp lại metadata route.

- anyRequest() áp dụng cho request mở đầu. Các route không khớp quy tắc cụ thể bị từ chối.
- anyExchange() áp dụng cho những exchange còn lại, bao gồm payload tiếp diễn của interaction đã được mở.

Vì vậy, policy trên cho phép payload tiếp diễn sau khi request mở đầu đã được xác thực và phân quyền. Nếu ứng dụng không sử dụng stream hoặc channel ngược, có thể thiết kế policy đơn giản hơn, nhưng vẫn cần từ chối request mới không có route được phép.

Trong cấu hình minh họa, anyExchange().permitAll() cũng cho phép các exchange không phải request, trong đó có metadata push. Nếu ứng dụng dùng METADATA_PUSH để thay đổi trạng thái hoặc quyền của connection, cần bổ sung PayloadInterceptor riêng để kiểm tra loại metadata, principal và nội dung trước khi xử lý; không dựa vào rule route của request.

Thứ tự rule rất quan trọng: rule route cụ thể phải đứng trước rule tổng quát. Spring Security sử dụng rule đầu tiên khớp với payload.

## 6. Gắn interceptor vào client-side RSocketConnector

Khai báo PayloadSocketAcceptorInterceptor chưa đủ. Interceptor cần được gắn vào connector của gateway để bảo vệ responder đang xử lý request đến.

~~~java
@Configuration
class GatewayRSocketClientConfiguration {

    @Bean
    RSocketRequester gatewayRequester(
            RSocketStrategies strategies,
            PayloadSocketAcceptorInterceptor reversePayloadSecurity,
            GatewayReverseHandler handler) {

        SocketAcceptor clientResponder =
            RSocketMessageHandler.responder(strategies, handler);
        SocketAcceptorInterceptor reverseSecurityInterceptor =
            new SecuritySocketAcceptorInterceptor(reversePayloadSecurity);

        return RSocketRequester.builder()
            .rsocketStrategies(strategies)
            .rsocketConnector(connector -> {
                connector.acceptor(clientResponder);
                connector.interceptors(registry ->
                    registry.forSocketAcceptor(
                        reverseSecurityInterceptor
                    )
                );
            })
            .tcp("rsocket-control.internal", 7000);
    }
}
~~~

Điểm quan trọng là forSocketAcceptor(...) được đăng ký trên RSocketConnector phía gateway. Đây là nơi connector nhận SETUP và tạo responder xử lý request từ server.

SecuritySocketAcceptorInterceptor bọc PayloadSocketAcceptorInterceptor để áp dụng security context và policy vào acceptor. Trong ứng dụng chỉ có client responder, cần tạo và gắn interceptor này rõ ràng. Auto-configuration RSocket Security của Spring Boot chủ yếu đăng ký interceptor cho RSocket server do ứng dụng mở; không nên giả định nó tự gắn policy vào mọi client-side responder.

Nếu ứng dụng vừa mở server endpoint vừa kết nối tới server khác, hãy xác định riêng policy cho từng acceptor. Không dùng chung một cấu hình rộng cho hai hướng nếu quyền của các route và danh tính peer khác nhau.

## 7. Lấy danh tính đã xác thực trong handler

Sau khi interceptor xác thực JWT, handler có thể lấy Authentication từ Reactor Security Context để ghi audit hoặc áp dụng thêm quy tắc nghiệp vụ.

~~~java
class GatewayReverseHandler {

    private final GatewayCommandService commandService;

    GatewayReverseHandler(GatewayCommandService commandService) {
        this.commandService = commandService;
    }

    @MessageMapping("gateway.apply-config")
    Mono<CommandAck> applyConfig(@Payload ConfigCommand command) {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                commandService.apply(
                    authentication.getName(),
                    command
                )
            );
    }
}
~~~

authentication.getName() ở đây đại diện cho service đã được xác thực từ bearer token. Không lấy tên service từ trường requestedBy trong payload rồi dùng làm danh tính. Payload chỉ chứa dữ liệu nghiệp vụ; danh tính phải đến từ security context do cơ chế xác thực tạo ra.

Có thể ghi audit gồm:

- Principal/service name đã xác thực.
- Route được gọi.
- Device hoặc tenant đích.
- Operation ID và correlation ID.
- Kết quả cho phép hoặc từ chối.
- Thời điểm và thời lượng xử lý.

Không ghi nguyên token hoặc secret vào log.

## 8. Server lấy requester của kết nối và gọi ngược về client

Phía server cần giữ requester đại diện cho kết nối gateway. Spring cho phép nhận RSocketRequester trong phương thức @ConnectMapping hoặc @MessageMapping.

Ví dụ đăng ký kết nối:

~~~java
@Controller
class GatewayConnectionController {

    private final GatewayConnectionRegistry registry;

    GatewayConnectionController(GatewayConnectionRegistry registry) {
        this.registry = registry;
    }

    @ConnectMapping
    Mono<Void> connected(RSocketRequester requester,
                         @Payload GatewayHello hello) {
        // clientPrincipal phải lấy từ xác thực connection ở server.
        return registry.register(
            authenticatedGatewayId(),
            requester
        );
    }
}
~~~

authenticatedGatewayId() trong ví dụ là placeholder cho principal được server xác thực từ connection context. Không dùng hello.gatewayId() làm khóa tin cậy nếu chưa đối chiếu nó với danh tính đã xác thực.

Sau khi connection đã được đăng ký và @ConnectMapping hoàn tất, service có thể lấy requester và gửi lệnh ngược:

~~~java
Mono<CommandAck> requestGatewayRefresh(
        RSocketRequester gatewayRequester,
        RefreshCommand command,
        String serverAccessToken) {

    return gatewayRequester
        .route("gateway.refresh")
        .metadata(serverAccessToken, BEARER_AUTH_MIME)
        .data(command)
        .retrieveMono(CommandAck.class);
}
~~~

Không nên khởi chạy request ngược đồng bộ ngay trong lúc đang xử lý SETUP nếu luồng xử lý cần connection hoàn tất trước. Hãy lưu requester sau khi xác thực và khởi chạy công việc sau khi quá trình thiết lập connection hoàn thành.

Khi connection đóng, registry phải loại bỏ requester tương ứng. Không giữ requester cũ rồi tiếp tục gửi command tới một session đã hết hiệu lực.

## 9. Bảo vệ từng route theo quyền tối thiểu

Không phải mọi request ngược đều có mức rủi ro giống nhau. Một route yêu cầu làm mới trạng thái có thể ít nhạy cảm hơn route cập nhật firmware hoặc mở khóa thiết bị.

Nên thiết kế authority theo hành động:

| Route | Authority đề xuất | Tác động |
|---|---|---|
| gateway.refresh | SCOPE_gateway:refresh | Yêu cầu gateway đồng bộ trạng thái |
| gateway.apply-config | SCOPE_gateway:apply-config | Thay đổi cấu hình thiết bị |
| gateway.restart | SCOPE_gateway:restart | Khởi động lại gateway |
| gateway.unlock | SCOPE_gateway:unlock | Thao tác điều khiển nhạy cảm |

Một service chỉ cần đồng bộ trạng thái không nên được cấp quyền restart hoặc unlock. Token nên chứa đúng scope mà service cần, có thời hạn ngắn và audience rõ ràng.

### Kiểm tra quyền ở cả route và nghiệp vụ

Route authorization xác định peer có được phép gọi chức năng đó hay không. Service nghiệp vụ vẫn cần kiểm tra điều kiện cụ thể:

- Gateway có thuộc tenant hoặc nhóm mà service được quản lý không?
- Lệnh có hợp lệ với trạng thái hiện tại của thiết bị không?
- Người dùng hoặc quy trình nghiệp vụ có phê duyệt thao tác nhạy cảm không?
- Operation ID đã được xử lý chưa?
- Lệnh có hết hạn hoặc vượt giới hạn tốc độ không?

Có quyền gọi gateway.apply-config không đồng nghĩa mọi cấu hình đều hợp lệ. Route security và business validation là hai lớp bổ sung.

## 10. Xử lý request-stream và request-channel ngược

Một request ngược có thể là request-response, request-stream hoặc request-channel. Quy tắc xác thực ban đầu vẫn cần áp dụng trước khi handler được chạy.

Với request-stream, server mở stream và gateway phát nhiều response. Gateway nên xác thực route và token ở request mở đầu. Các payload response tiếp theo thuộc cùng interaction và tuân theo vòng đời stream đó.

Với request-channel, hai phía có thể gửi payload trong cả hai hướng. Cần xác thực và phân quyền request mở đầu; nếu channel mang các lệnh có mức nhạy cảm khác nhau trên từng payload, hãy bổ sung kiểm tra nghiệp vụ trên từng phần tử thay vì dựa hoàn toàn vào route mở đầu.

Ví dụ channel nhận batch command:

~~~java
@MessageMapping("gateway.command-channel")
Flux<CommandAck> commands(@Payload Flux<GatewayCommand> input) {
    return input.concatMap(command ->
        commandService.validateAndExecute(command)
    );
}
~~~

Nếu route này được cho phép, mọi command trong channel vẫn cần được kiểm tra loại lệnh, phạm vi thiết bị, sequence, idempotency key và quyền thực hiện. Không nên coi việc channel đã được xác thực một lần là cho phép mọi payload bất kỳ.

## 11. Các ranh giới bảo mật cần chú ý

### SETUP credentials không phải danh tính server

Trong kết nối gateway tới server, metadata authentication trong SETUP thường là gateway gửi credential cho server. Nó không xác thực ngược server cho gateway. Muốn xác thực server, dùng token do server trình bày trên từng request ngược hoặc xác thực transport bằng mTLS.

### HTTP Security không tự bảo vệ RSocket responder

Một SecurityWebFilterChain cho HTTP không tự áp dụng cho các request RSocket trên kết nối TCP hoặc WebSocket. RSocket cần interceptor riêng gắn vào SocketAcceptor hoặc connector. Nếu dùng WebSocket transport, đừng giả định các route RSocket tự động được bảo vệ chỉ vì endpoint handshake đi qua hạ tầng HTTP.

### Metadata Push không phải request có route

METADATA_PUSH là thông báo metadata ở phạm vi connection, không phải một request route thông thường. Rule route(...) không thay thế policy cho metadata push. Nếu ứng dụng sử dụng metadata push để thay đổi trạng thái phiên, hãy xác thực nguồn gửi và kiểm tra loại metadata bằng interceptor hoặc logic chuyên biệt. Trong policy mẫu, exchange không phải request được cho phép để các payload tiếp diễn của stream/channel hoạt động; vì vậy phải bổ sung kiểm tra riêng nếu metadata push có tác động bảo mật.

### Không tin route hoặc identity do payload khai báo

Route được dùng để chọn handler và phân quyền, nhưng payload vẫn có thể chứa tenantId, deviceId hoặc requestedBy giả mạo. Hãy kiểm tra các giá trị này có thuộc phạm vi của principal đã xác thực hay không.

### Chống phát lại và request trùng

JWT hợp lệ có thể được dùng lại trong thời hạn hiệu lực. Với lệnh có tác dụng phụ, bổ sung operation ID hoặc idempotency key, timestamp/nonce nếu cần, và kiểm tra trạng thái đã thực hiện. Không dùng token làm mã định danh duy nhất cho từng lệnh.

## 12. Kiểm thử bảo vệ request ngược

Nên kiểm thử trên đúng client-side responder, không chỉ kiểm tra policy ở server.

| Tình huống | Kết quả mong đợi |
|---|---|
| Server gửi token hợp lệ và có scope cho route | Handler được gọi |
| Token hết hạn | Request bị từ chối trước khi chạy handler |
| Chữ ký token không hợp lệ | Request bị từ chối |
| Issuer hoặc audience không đúng | Request bị từ chối |
| Token hợp lệ nhưng thiếu authority | Request bị từ chối |
| Route không nằm trong allow-list | Request bị từ chối |
| Request không có bearer metadata | Request bị từ chối |
| Server gọi route được phép nhưng payload sai nghiệp vụ | Service từ chối theo validation |
| Connection đóng | Requester bị loại khỏi registry |
| Một connection khác gọi route | Policy được đánh giá theo danh tính của connection đó |

Ví dụ integration test với StepVerifier có thể kiểm tra route được phép và route bị từ chối:

~~~java
@Test
void acceptsReverseRequestWithRequiredScope() {
    StepVerifier.create(
        serverRequester.route("gateway.refresh")
            .metadata(validRefreshToken, BEARER_AUTH_MIME)
            .data(new RefreshCommand("gateway-01"))
            .retrieveMono(CommandAck.class)
    )
    .expectNextMatches(CommandAck::accepted)
    .verifyComplete();
}

@Test
void rejectsReverseRequestWithoutRequiredScope() {
    StepVerifier.create(
        serverRequester.route("gateway.apply-config")
            .metadata(refreshOnlyToken, BEARER_AUTH_MIME)
            .data(new ConfigCommand("gateway-01", "safe-mode"))
            .retrieveMono(CommandAck.class)
    )
    .expectError()
    .verify();
}
~~~

Hai test trên cần một RSocket server test có kết nối tới client responder đã gắn interceptor. validRefreshToken và refreshOnlyToken cần được ký bởi test issuer và chứa các claim khác nhau. Test thứ hai xác nhận token đã xác thực nhưng thiếu quyền vẫn không được thực thi.

Ngoài ra, hãy dùng spy hoặc counter để xác nhận service handler không bị gọi trong trường hợp bị từ chối. Chỉ kiểm tra client nhận lỗi là chưa đủ nếu có khả năng handler đã chạy trước khi lỗi được trả về.

### Kiểm thử khi kết nối bị thay thế

Khi gateway reconnect, requester mới phải được gắn cùng policy bảo mật. Kiểm thử rằng:

- Mỗi kết nối mới đều có client responder và security interceptor.
- Token cũ hết hạn không được chấp nhận sau reconnect.
- Requester cũ bị xóa khỏi registry khi connection đóng.
- Không có đường code tạo requester phụ mà bỏ qua interceptor.
- Token của một gateway không thể dùng để gọi route của gateway khác nếu audience hoặc scope không phù hợp.

## 13. Những lỗi triển khai thường gặp

| Cách làm | Rủi ro | Cách xử lý |
|---|---|---|
| Chỉ bảo vệ RSocket server | Request ngược tới client không có policy tương ứng | Gắn interceptor vào client-side connector |
| Nghĩ SETUP credential của client xác thực server | Chấp nhận nhầm danh tính peer | Xác thực server bằng token riêng hoặc mTLS |
| Chỉ kiểm tra JWT có chữ ký | Token sai audience vẫn được dùng | Kiểm tra issuer, audience, thời hạn và scope |
| Cho phép mọi route sau khi kết nối | Server có thể gọi chức năng ngoài nhu cầu | Allow-list route và quyền tối thiểu |
| Dùng một authority cho mọi lệnh | Quyền điều khiển quá rộng | Tách scope theo hành động |
| Tin clientId hoặc requestedBy trong payload | Có thể giả mạo tenant hoặc người gửi | Dùng Authentication đã xác thực |
| Gắn interceptor vào server nhưng quên connector | Chiều server gọi client không được bảo vệ | Đăng ký forSocketAcceptor trên RSocketConnector |
| Dùng HTTP filter chain thay cho RSocket security | Route RSocket có thể không được kiểm tra | Dùng PayloadSocketAcceptorInterceptor |
| Cho rằng metadata push được route matcher bảo vệ | Thông báo connection-level không có route | Viết policy riêng cho METADATA_PUSH |
| Không xóa requester khi connection đóng | Server gửi vào session cũ | Quản lý registry theo lifecycle connection |
| Không kiểm tra quyền trên từng command trong channel | Một route hợp lệ có thể mang lệnh không hợp lệ | Validate từng payload theo nghiệp vụ |
| Không kiểm thử handler có thực thi hay không | Có thể lọt tác dụng phụ dù client thấy lỗi | Dùng spy/counter để xác nhận từ chối trước handler |

## Kết luận

RSocket cho phép server chủ động gửi request về client sau khi connection đã được thiết lập. Khi đó client trở thành responder và phải bảo vệ các route mà nó công bố. Chính sách bảo vệ route phía server không tự động áp dụng cho responder phía client.

Hãy đăng ký client responder bằng RSocketMessageHandler và RSocketConnector, gắn SocketAcceptorInterceptor vào connector, xác thực danh tính server bằng bearer token theo request hoặc danh tính transport đáng tin cậy, rồi phân quyền theo route và scope tối thiểu. Đừng nhầm credential trong SETUP do client gửi với danh tính server; kiểm tra cả audience, issuer, expiry, route, payload nghiệp vụ và vòng đời requester.

Khi bảo vệ riêng chiều request ngược, mỗi kết nối chỉ nên thực thi các lệnh mà peer đã được xác thực và được cấp quyền rõ ràng. Điều này giúp tránh việc một server hoặc service có kết nối hợp lệ trở thành nguồn gửi lệnh không giới hạn tới client.

## Tài liệu tham khảo

- [Spring Framework RSocket — Client Responders và Server Requester](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Security — RSocket Authentication và Authorization](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [RSocketMessageHandler API](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [RSocketRequester.Builder API](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.Builder.html)
- [RSocketConnector API](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [SecuritySocketAcceptorInterceptor API](https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/rsocket/core/SecuritySocketAcceptorInterceptor.html)
