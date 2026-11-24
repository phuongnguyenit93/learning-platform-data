# Mô hình đe dọa cho kết nối dài hạn và luồng dữ liệu hai chiều

RSocket hỗ trợ kết nối lâu dài, multiplex nhiều stream và trao đổi dữ liệu theo cả hai hướng. Sau khi SETUP hoàn tất, hai peer có thể vừa gửi request vừa xử lý request từ peer còn lại. Request-stream và request-channel còn duy trì luồng dữ liệu trong thời gian dài, có thể kéo theo subscription, buffer, quyền truy cập và trạng thái xác thực tồn tại lâu hơn một HTTP request thông thường.

Đặc điểm này tạo ra một mô hình đe dọa riêng. Xác thực thành công lúc mở kết nối không đồng nghĩa mọi request sau đó đều được phép. Một route được cho phép cũng không có nghĩa mọi phần tử trong channel đều hợp lệ. Kết nối mở lâu làm tăng thời gian khai thác nếu token hết hạn, quyền bị thu hồi hoặc tài nguyên không được giải phóng. Mô hình bảo mật cần xét đồng thời **transport, connection, interaction, từng message và tài nguyên**.

## 1. Phạm vi và giả định của mô hình

Bài này xem xét một ứng dụng Java/Spring Boot dùng RSocket qua TCP hoặc WebSocket, có thể triển khai request-response, fire-and-forget, request-stream và request-channel. Các thành phần điển hình:

- Browser, mobile app hoặc service client.
- RSocket server dùng Spring Messaging và Spring Security.
- Reverse proxy, load balancer hoặc API gateway nếu có.
- Các service downstream, database, event broker và hệ thống lưu trữ.
- Peer nhận request ngược từ server trên cùng một kết nối.

RSocket là giao thức giao tiếp hai chiều, multiplex và có thể chạy trên TCP hoặc WebSocket. Sau khi kết nối được thiết lập, vai trò requester/responder có thể thay đổi theo từng tương tác; một peer không chỉ luôn là client còn peer kia luôn là server. Vì vậy, mỗi endpoint phải bảo vệ cả những request nó nhận từ peer.

### Sơ đồ trust boundary

~~~mermaid
flowchart LR
    A[Browser / Mobile / Service] -->|TLS hoặc WSS| B[Proxy / Load Balancer]
    B -->|Kênh nội bộ được bảo vệ| C[RSocket Server]
    C --> D[Spring Security + Message Handler]
    D --> E[Domain Authorization]
    E --> F[Database / Event Broker]
    D <--> |RSocket request hai chiều| G[Downstream RSocket Peer]
    G --> H[Service khác]
~~~

Các ranh giới tin cậy cần xem xét:

1. **Client đến transport:** dữ liệu đi qua mạng, có thể bị nghe lén hoặc sửa đổi nếu không mã hóa.
2. **Transport đến RSocket session:** kết nối được mở nhưng peer vẫn cần được xác thực.
3. **Session đến request:** một session có thể mang nhiều request từ cùng hoặc nhiều người dùng.
4. **Request đến stream:** một request-stream/channel có thể sống lâu và phát nhiều payload.
5. **Handler đến domain/data:** route được phép không thay thế kiểm tra quyền trên từng tài nguyên.
6. **Server đến downstream peer:** server có thể chủ động gửi request ngược, nên chiều dữ liệu này cũng cần xác thực và phân quyền.

## 2. Tài sản cần bảo vệ

Mô hình đe dọa bắt đầu bằng việc xác định dữ liệu và tài nguyên có giá trị:

| Tài sản | Ví dụ | Hậu quả khi bị xâm phạm |
|---|---|---|
| Danh tính | User ID, service identity, tenant | Giả mạo người dùng hoặc service |
| Credential | JWT, refresh token, chứng thư, session | Chiếm quyền kết nối và request |
| Dữ liệu nghiệp vụ | Hồ sơ, đơn hàng, telemetry, lệnh thiết bị | Rò rỉ, sửa đổi hoặc xóa dữ liệu |
| Quyền truy cập | Scope, role, quyền theo tài nguyên | Vượt quyền hoặc truy cập chéo tenant |
| Luồng sự kiện | Subscription, command channel, stream | Nghe lén, chèn lệnh, làm sai thứ tự |
| Tài nguyên kết nối | Socket, stream, buffer, queue, worker | Cạn bộ nhớ, CPU, connection pool |
| Trạng thái phục hồi | Cursor, sequence, resume state | Phát lại dữ liệu hoặc xử lý trùng |
| Dấu vết kiểm toán | Route, Stream ID, quyết định authorization | Không thể điều tra sự cố |

Một kết nối mở lâu có thể giữ credential và trạng thái phiên trong thời gian dài. Một stream có thể giữ tài nguyên dù người dùng đã rời trang hoặc service downstream đã mất khả năng xử lý. Các tài sản này cần được đưa vào thiết kế ngay từ đầu.

## 3. Tác nhân và mục tiêu tấn công

Không phải mọi cuộc tấn công đều đến từ người chưa đăng nhập. Với hệ thống realtime, một peer đã xác thực nhưng bị chiếm quyền hoặc có hành vi lạm dụng vẫn là nguồn rủi ro.

| Tác nhân | Khả năng | Mục tiêu có thể |
|---|---|---|
| Attacker trên mạng | Nghe lén, sửa byte, phát lại traffic nếu transport yếu | Lấy token, thay đổi message |
| Client chưa xác thực | Mở nhiều kết nối, gửi payload lỗi hoặc quá lớn | Exhaustion, dò route |
| Client hợp lệ nhưng độc hại | Gửi lệnh vượt quyền, flood stream, đổi tenant ID | Truy cập trái phép, DoS |
| Browser origin độc hại | Khởi tạo WebSocket từ trang không tin cậy trong phiên cookie của nạn nhân | Chiếm phiên realtime |
| Service downstream bị xâm nhập | Gửi request ngược hoặc response giả | Di chuyển ngang, lấy dữ liệu |
| Insider hoặc tài khoản bị đánh cắp | Sử dụng quyền hợp lệ vượt mục đích | Rò rỉ dữ liệu và lạm dụng nghiệp vụ |
| Proxy hoặc gateway cấu hình sai | Kết thúc TLS, log credential, timeout sai | Lộ dữ liệu hoặc làm gián đoạn stream |

## 4. Các đặc điểm RSocket làm thay đổi rủi ro

### Kết nối lâu dài

HTTP request thông thường kết thúc sau khi response hoàn tất. RSocket session có thể sống hàng giờ. Trong thời gian đó:

- Token có thể hết hạn.
- Người dùng có thể logout.
- Role hoặc quyền trên tài nguyên có thể bị thu hồi.
- Tenant có thể bị khóa.
- Một subscription có thể tiếp tục phát dữ liệu mà người dùng không còn được phép xem.
- Một socket có thể giữ buffer và tài nguyên dù phía client không còn sử dụng.

Do đó, thời điểm xác thực ban đầu không đủ để quản lý toàn bộ vòng đời phiên.

### Multiplex nhiều stream

Một kết nối có thể mang nhiều stream đồng thời. Lỗi hoặc hành vi độc hại ở một stream có thể gây tác động đến các stream khác nếu chúng dùng chung queue, scheduler, buffer hoặc connection pool.

Cần giới hạn theo cả connection và principal: số stream hoạt động, số request đồng thời, lượng byte, tốc độ message và thời gian giữ tài nguyên.

### Hai hướng dữ liệu

Trong request-channel, client gửi một stream command và server phát một stream response. Ngoài ra, peer cũng có thể chủ động khởi tạo request theo chiều ngược lại. Vì vậy cần bảo vệ:

- Dữ liệu client gửi lên server.
- Dữ liệu server gửi về client.
- Request mà server gửi ngược tới client.
- Dữ liệu client trả lời cho request do server khởi tạo.

Không được coi chiều outbound là an toàn chỉ vì nó xuất phát từ server. Quyền xem từng bản ghi và quyền nhận từng loại sự kiện vẫn cần được kiểm tra.

## 5. STRIDE: phân loại mối đe dọa

STRIDE giúp rà soát các nhóm rủi ro theo mục tiêu tấn công.

| Nhóm | Ví dụ trong RSocket | Biện pháp chính |
|---|---|---|
| Spoofing – giả mạo | Dùng token bị đánh cắp hoặc giả service identity | TLS, JWT/mTLS, xác thực SETUP và request |
| Tampering – sửa đổi | Sửa data, metadata, tenant hoặc command | TLS, schema validation, authorization và kiểm tra tính toàn vẹn |
| Repudiation – chối bỏ | Không chứng minh được ai đã gửi lệnh | Audit log có principal, route, Stream ID, request ID |
| Information Disclosure – lộ dữ liệu | Đọc stream của tenant khác hoặc log lộ token | Authorization theo tài nguyên, tenant isolation, redaction |
| Denial of Service – từ chối dịch vụ | Mở quá nhiều socket/stream, gửi payload lớn, làm chậm consumer | Quota, size limit, rate limit, timeout, backpressure và bounded queue |
| Elevation of Privilege – nâng quyền | Route đã xác thực nhưng command trong channel vượt quyền | Kiểm tra quyền theo từng hành động và tài nguyên |

STRIDE là cách phân loại để không bỏ sót nhóm rủi ro; nó không thay thế việc phân tích luồng dữ liệu và kiểm thử theo kiến trúc thực tế.

## 6. Xác thực tại SETUP hay tại từng request?

Spring Security hỗ trợ xác thực RSocket ở thời điểm SETUP, thời điểm request hoặc kết hợp cả hai.

**Xác thực tại SETUP** phù hợp khi một kết nối gắn với một danh tính duy nhất, ví dụ một mobile app của một người dùng hoặc một service identity. Peer gửi credential trong SETUP; server xác thực rồi gắn danh tính với session.

**Xác thực tại từng request** phù hợp khi một kết nối được chia sẻ cho nhiều người dùng. Ví dụ một backend gateway giữ một RSocket connection tới downstream service nhưng phục vụ nhiều người dùng cuối. Mỗi request cần mang credential hoặc context xác thực của người dùng tương ứng.

**Kết hợp hai tầng** phù hợp khi cần xác thực cả service mở kết nối và user tạo từng request. Credential ở SETUP có thể chứng minh gateway được phép kết nối; credential ở request xác định người dùng cuối và quyền nghiệp vụ.

| Mô hình | Phù hợp khi | Rủi ro nếu dùng sai |
|---|---|---|
| Auth ở SETUP | Một connection gắn với một identity | Một user bị thu hồi quyền nhưng session cũ vẫn còn |
| Auth ở request | Shared connection nhiều user | Quên credential ở một route hoặc một loại request |
| Auth cả hai | Gateway identity và end-user identity khác nhau | Nhầm quyền của gateway với quyền của user |

Không nên chia sẻ một requester đã xác thực bằng token của người dùng A rồi dùng nó để phục vụ người dùng B mà không có cơ chế xác thực theo request. Điều đó có thể khiến mọi request bị gắn với cùng một principal.

### Ví dụ gửi JWT trong SETUP

~~~java
MimeType authenticationMimeType =
    MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

String accessToken = tokenProvider.currentAccessToken();

RSocketRequester requester = RSocketRequester.builder()
    .setupMetadata(accessToken, authenticationMimeType)
    .tcp("rsocket.internal", 7000);
~~~

Đây là ví dụ cấu hình token cho một kết nối. Trong ứng dụng thực tế, token phải lấy từ nguồn quản lý credential an toàn, có thời hạn và không được ghi vào log.

### Ví dụ gửi JWT theo request

~~~java
Mono<OrderView> findOrder(
        RSocketRequester requester,
        String accessToken,
        String orderId) {

    MimeType authenticationMimeType =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    return requester
        .route("orders.find")
        .metadata(accessToken, authenticationMimeType)
        .data(new FindOrderRequest(orderId))
        .retrieveMono(OrderView.class);
}
~~~

Ví dụ dùng composite metadata mặc định của Spring RSocketRequester để gửi routing metadata và authentication metadata trong cùng request. Hai peer cần cấu hình Spring Security và codec tương thích.

## 7. Phân quyền theo route chưa đủ cho channel

Spring Security có thể áp dụng rule theo SETUP, route và request metadata. Ví dụ:

~~~java
@Configuration
@EnableRSocketSecurity
public class RSocketSecurityConfiguration {

    @Bean
    PayloadSocketAcceptorInterceptor rsocketInterceptor(
            RSocketSecurity security) {

        security
            .authorizePayload(authorize -> authorize
                .setup().hasRole("SETUP")
                .route("orders.find")
                    .hasAuthority("SCOPE_orders.read")
                .route("orders.commands")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .jwt(Customizer.withDefaults());

        return security.build();
    }
}
~~~

Ví dụ trên thể hiện:

- SETUP cần authority SETUP.
- Route orders.find cần scope đọc đơn hàng.
- Route orders.commands cần scope ghi lệnh.
- Request có route khác vẫn phải được xác thực.
- JWT được xác thực qua ReactiveJwtDecoder đã cấu hình trong ứng dụng.

Các authority trong ví dụ phải khớp với cách ứng dụng ánh xạ claim JWT thành GrantedAuthority. Spring Security mặc định ánh xạ scope thành authority có tiền tố SCOPE_; nếu dùng hasRole("SETUP"), token hoặc JwtAuthenticationConverter cần cung cấp ROLE_SETUP tương ứng.

Spring Boot có thể tự đăng ký security interceptor khi có các dependency RSocket Security phù hợp. Nếu tự cấu hình RSocket server, cần bảo đảm SecuritySocketAcceptorInterceptor thực sự được gắn vào SocketAcceptor của server.

**Điểm cần đặc biệt chú ý với request-channel:** rule route được đánh giá trên request mở interaction, tức message mang metadata route. Các payload tiếp theo trong channel không lặp lại route metadata. Tài liệu Spring Security phân biệt request đầu tiên với các payload bổ sung của exchange. Vì vậy, không thể coi route authorization là kiểm tra quyền cho mọi command bên trong channel.

Hãy kiểm tra quyền theo từng phần tử command trong handler hoặc domain service:

~~~java
@MessageMapping("orders.commands")
public Flux<CommandResult> commands(
        @Payload Flux<OrderCommand> commands) {

    return commands.concatMap(command ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Missing identity")))
            .flatMap(authentication ->
                orderAuthorization.requireCanExecute(
                    authentication, command))
            .then(Mono.defer(() ->
                orderService.execute(command)))
    );
}
~~~

Trong ví dụ, mỗi command được kiểm tra principal và quyền trên tài nguyên trước khi thực thi. Nếu nghiệp vụ cho phép bỏ qua một command bị từ chối và tiếp tục stream, có thể chuyển lỗi thành một CommandResult thất bại; nếu không, phát lỗi để kết thúc channel. Chính sách phải rõ ràng để tránh tiếp tục thực thi những command sau một lỗi bảo mật.

Với một channel, danh tính được xác định ở request mở stream. Nếu nhiều người dùng cùng sử dụng một kết nối, mỗi channel nên gắn với một identity rõ ràng. Không gom command của nhiều người dùng vào cùng channel rồi dựa vào metadata của frame mở đầu để xác định quyền cho tất cả.

## 8. Token hết hạn, logout và thu hồi quyền

Kết nối dài hạn có thể tồn tại lâu hơn access token hoặc phiên đăng nhập. Một token hợp lệ khi SETUP không có nghĩa nó sẽ luôn hợp lệ trong suốt đời socket.

Các tình huống cần xử lý:

- Access token hết hạn trong khi request-stream vẫn phát dữ liệu.
- Người dùng logout nhưng subscription vẫn mở.
- Role bị thu hồi trong lúc channel đang nhận command.
- Tenant bị khóa nhưng client vẫn giữ connection.
- Service identity bị rotate hoặc chứng thư bị thu hồi.

Thiết kế cần có chính sách rõ ràng:

1. Xác định token hết hạn thì request mới bị từ chối hay session bị đóng.
2. Theo dõi logout và sự kiện thu hồi credential.
3. Revalidate identity/authorization theo chu kỳ hoặc trước thao tác nhạy cảm.
4. Hủy stream và subscription đang phát dữ liệu mà principal không còn quyền.
5. Đóng connection khi identity bị thu hồi hoặc session hết hạn theo chính sách.
6. Cấp token mới và thiết lập lại session khi cần.

Không nên giả định Spring Security tự động kiểm tra lại JWT ở mọi phần tử của một Flux đã mở. Việc xác thực token diễn ra theo điểm tích hợp security; nếu cần thu hồi ngay, phải có cơ chế phát hiện và dừng các stream đang hoạt động.

## 9. TLS, mTLS và bảo vệ transport

RSocket qua TCP cần TLS khi đi qua mạng không tin cậy. Nếu dùng WebSocket, dùng WSS để bảo vệ HTTP handshake và dữ liệu WebSocket sau đó.

TLS bảo vệ tính bí mật và toàn vẹn dữ liệu trên từng chặng TLS. Nó không thay thế authentication ở tầng ứng dụng và không quyết định user có quyền gọi route nào.

Các điểm cần kiểm tra:

- Xác minh certificate của server ở client; không tắt hostname verification.
- Dùng mTLS khi cần xác thực service ở cả hai đầu.
- Quản lý vòng đời certificate, rotation và revocation.
- Nếu TLS kết thúc ở proxy/load balancer, bảo vệ cả chặng proxy đến RSocket server.
- Không gửi credential qua TCP hoặc WebSocket không mã hóa trong môi trường production.
- Giới hạn cipher/protocol theo chính sách TLS của tổ chức.

mTLS phù hợp để xác định service identity giữa các workload. JWT hoặc cơ chế authentication RSocket vẫn có thể cần thiết để xác định user, scope và quyền nghiệp vụ bên trong service.

## 10. Rủi ro riêng khi dùng WebSocket từ trình duyệt

Khi RSocket chạy trên WebSocket, handshake ban đầu đi qua HTTP. Nếu browser tự động gửi cookie phiên, trang web độc hại có thể tìm cách mở kết nối WebSocket đến server bằng phiên đã đăng nhập của nạn nhân. Đây là nhóm rủi ro Cross-Site WebSocket Hijacking (CSWSH).

Biện pháp cần có:

- Chỉ cho phép Origin nằm trong allowlist cụ thể.
- Không dùng wildcard hoặc kiểm tra substring lỏng lẻo.
- Kết hợp SameSite cookie và CSRF protection theo mô hình xác thực.
- Xác thực peer trước khi gửi dữ liệu được bảo vệ.
- Đóng connection khi logout hoặc session hết hạn.
- Không đưa token vào URL query string vì URL có thể xuất hiện trong access log.
- Không ghi token hoặc cookie vào log handshake.

Origin validation áp dụng cho WebSocket browser handshake; nó không thay thế RSocket authentication và không áp dụng theo cùng cách cho TCP transport thuần. Với TCP service-to-service, cần dựa vào TLS/mTLS và cơ chế identity tương ứng.

## 11. Input validation và deserialization

Mọi data và metadata từ peer đều là input không tin cậy, kể cả khi peer đã xác thực. Một client hợp lệ vẫn có thể bị xâm nhập hoặc gửi dữ liệu lỗi.

Các rủi ro:

- Payload chứa field ngoài schema hoặc kiểu dữ liệu không mong đợi.
- JSON quá sâu, collection quá lớn hoặc chuỗi cực dài.
- MIME type lạ khiến decoder xử lý sai hoặc thất bại.
- Dữ liệu chứa SQL injection, command injection hoặc biểu thức nguy hiểm.
- Byte payload được diễn giải nhầm thành loại file hoặc binary format khác.
- Metadata chứa tenant ID hoặc role giả mạo.

Biện pháp:

- Chỉ đăng ký codec cần thiết và tránh Java native serialization cho dữ liệu không tin cậy.
- Validate DTO bằng Bean Validation và kiểm tra domain.
- Giới hạn kích thước payload và metadata trước khi decode sâu.
- Giới hạn số phần tử trong collection, độ sâu cấu trúc và độ dài chuỗi.
- Kiểm tra enum, ID, range và trạng thái nghiệp vụ bằng allowlist.
- Dùng prepared statement hoặc API an toàn cho truy vấn database.
- Với binary upload, xác minh loại nội dung bằng chữ ký file và quét nếu nghiệp vụ yêu cầu.
- Chuẩn hóa lỗi để không trả stack trace hoặc thông tin nội bộ.

Validation ở client chỉ giúp phát hiện lỗi sớm; server luôn phải validate lại.

## 12. DoS và cạn tài nguyên trên kết nối dài hạn

Một attacker không cần gửi payload độc hại để gây gián đoạn. Chỉ cần mở nhiều kết nối, tạo nhiều stream hoặc khiến consumer xử lý chậm cũng có thể làm cạn tài nguyên.

| Bề mặt | Hành vi lạm dụng | Kiểm soát |
|---|---|---|
| Connection | Mở nhiều socket hoặc giữ socket idle | Connection quota theo IP/principal, handshake timeout, idle policy |
| Stream | Mở nhiều request-stream/channel | Giới hạn active stream theo connection và principal |
| Payload | Gửi frame/data/metadata lớn | Max frame size, payload size và metadata size |
| Producer | Phát nhanh hơn consumer | Demand, bounded buffer, giới hạn concurrency |
| Consumer | Không đọc hoặc xử lý rất chậm | Timeout, cancellation, slow-consumer policy |
| CPU | Gửi JSON sâu, deserialize tốn kém | Giới hạn độ sâu, kích thước và rate |
| Downstream | Mở quá nhiều truy vấn/command | Bulkhead, connection pool limit, concurrency cap |

Backpressure giúp producer không phát vượt demand đã cấp. Nhưng demand đếm số message, không đếm byte; một payload đơn lẻ vẫn có thể rất lớn. Một client độc hại cũng có thể yêu cầu lượng demand rất lớn. Vì vậy backpressure không thay thế rate limit, payload size limit hay resource quota.

Dùng bounded queue và giới hạn concurrency cho các operator như flatMap. Tránh buffer không giới hạn trong pipeline realtime. Khi vượt ngưỡng, từ chối request hoặc hủy stream theo chính sách đã định thay vì để bộ nhớ tăng vô hạn.

## 13. Cancellation, timeout và vòng đời subscription

Client có thể hủy stream khi đóng màn hình hoặc không còn cần dữ liệu. Server phải phản ứng với cancellation để dừng database cursor, listener, timer và tác vụ downstream.

Các câu hỏi cần trả lời:

- Timeout áp dụng cho lúc thiết lập connection, từng request hay toàn bộ stream?
- Stream không phát dữ liệu trong bao lâu thì bị đóng?
- Cancellation có dừng công việc downstream hay chỉ ngừng gửi response?
- Nếu channel bị hủy giữa lúc thực hiện command, giao dịch nghiệp vụ có được rollback không?
- Ai dọn buffer và subscription khi transport đóng?

Cancellation ở giao thức không đồng nghĩa nghiệp vụ đã rollback. Một command có thể đã được commit trước khi client hủy hoặc mất kết nối. Các thao tác ghi cần idempotency key và trạng thái kết quả có thể truy vấn lại.

Dùng timeout phù hợp cho từng dependency, idle stream và toàn bộ phiên. Không nhầm KEEPALIVE với authorization hoặc session expiry: keepalive giúp phát hiện peer không còn phản hồi, nhưng không xác định người dùng còn quyền truy cập hay không.

## 14. Resume, reconnect và phát lại dữ liệu

Nếu ứng dụng bật RSocket Resumption, hai peer có thể tiếp tục một session sau gián đoạn khi trạng thái phục hồi còn hiệu lực. Điều này hữu ích cho realtime nhưng tạo thêm câu hỏi về trạng thái và replay.

Cần xác định:

- Resume state được giữ ở đâu và trong bao lâu.
- Session có được gắn với đúng principal/tenant ban đầu không.
- Khi token hết hạn hoặc bị thu hồi, resume có bị từ chối không.
- Stream đang chạy được khôi phục từ vị trí nào.
- Ứng dụng xử lý thế nào nếu một event hoặc command được gửi lại.
- Cursor/sequence có được kiểm tra để tránh bỏ sót hoặc xử lý trùng không.

Không dựa vào transport resume để bảo đảm nghiệp vụ exactly-once. Dùng event ID, idempotency key, sequence number hoặc cursor bền vững ở tầng ứng dụng. Khi identity không còn hợp lệ, phải đóng hoặc từ chối resume theo chính sách, không tiếp tục phiên cũ chỉ vì transport có thể khôi phục.

## 15. Bảo vệ dữ liệu outbound và request ngược

Với RSocket, server có thể gửi request tới client hoặc downstream peer trên kết nối hiện có. Điều đó có nghĩa:

- Client cần xác thực request ngược từ server theo trust policy.
- Server cần giới hạn route mà peer được phép gọi ngược.
- Response stream chỉ được chứa bản ghi thuộc phạm vi quyền của subscriber.
- Không phát dữ liệu của tenant khác chỉ vì subscription ban đầu hợp lệ.
- Service downstream phải được xác thực, không tin mọi peer nội bộ.
- Mỗi hướng cần có timeout, concurrency và quota riêng.

Nếu một client được quyền subscribe telemetry của thiết bị A, server phải kiểm tra thiết bị A thuộc tenant mà principal được phép truy cập. Không lấy deviceId từ payload rồi phát dữ liệu mà bỏ qua kiểm tra ownership.

## 16. Logging, audit và phát hiện bất thường

Log HTTP handshake đơn thuần không đủ để điều tra một phiên RSocket kéo dài. Cần ghi nhận cả vòng đời connection và hoạt động message, nhưng không lưu toàn bộ payload nhạy cảm.

Trường nên ghi:

- Connection/session ID.
- Principal hoặc service identity đã xác thực.
- Route, interaction model và Stream ID.
- Thời điểm mở, đóng, reconnect, resume và cancellation.
- Quyết định authentication/authorization và lý do từ chối ở dạng mã.
- Kích thước payload/metadata, số message và thời gian xử lý.
- Rate limit, quota, timeout, protocol error và downstream failure.
- Correlation ID hoặc trace ID do hệ thống tạo/đã xác thực.

Không ghi access token, password, cookie, session secret hoặc nội dung message chứa dữ liệu nhạy cảm. Trace ID do client gửi chỉ nên dùng để tương quan sau khi validate; không dùng nó làm bằng chứng danh tính.

Metric và alert nên bao gồm số connection đang mở, active stream theo principal, số lần auth thất bại, route bị từ chối, payload size distribution, queue depth, direct memory, số cancellation và reconnect/resume thất bại.

## 17. Kiểm thử mô hình đe dọa

Kiểm thử cần bao gồm tình huống bình thường và các nhánh lỗi trong vòng đời kết nối.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| SETUP không có credential | Kết nối bị từ chối nếu policy yêu cầu xác thực |
| JWT hết hạn | Request mới bị từ chối; stream/session cũ được xử lý theo chính sách expiry |
| User logout | Các stream liên quan bị hủy hoặc connection bị đóng |
| Token của user A dùng cho request của user B | Không thể truy cập tài nguyên của B |
| Route không có scope | Authorization từ chối request |
| Channel gửi command trái quyền ở phần tử thứ hai | Command trái quyền không được thực thi |
| Tenant ID giả trong metadata | Server dùng identity đã xác thực và từ chối tenant không thuộc quyền |
| WebSocket từ Origin lạ | Handshake bị từ chối |
| Nhiều connection/stream vượt quota | Server từ chối hoặc đóng theo giới hạn |
| Payload hoặc metadata quá lớn | Bị từ chối trước khi tiêu tốn tài nguyên quá mức |
| Consumer chậm | Queue vẫn hữu hạn; producer bị điều tiết hoặc stream bị timeout |
| Hủy channel khi command đang chạy | Tài nguyên được cleanup; trạng thái nghiệp vụ được xác định rõ |
| Resume sau khi token bị thu hồi | Session không được tiếp tục bằng identity đã bị thu hồi |
| Client gửi event trùng sau reconnect | Idempotency/dedup ngăn tác dụng phụ lặp |

Nên có integration test qua TCP và WebSocket thật, kiểm thử Spring Security interceptor, domain authorization cho từng command và kiểm thử tải với nhiều stream đồng thời. Security test không chỉ kiểm tra route mở được hay không; phải xác minh dữ liệu outbound cũng bị giới hạn theo principal.

## 18. Quy trình threat modeling cho một route mới

Khi thêm route hoặc channel mới, nhóm phát triển có thể dùng quy trình sau:

1. **Mô tả dữ liệu:** route nhận data gì, metadata nào, response chứa dữ liệu gì.
2. **Xác định principal:** ai mở connection, ai gửi request và ai nhận response.
3. **Xác định trust boundary:** transport, proxy, server, downstream và tenant boundary.
4. **Liệt kê hành động:** route chỉ đọc, ghi, subscribe hay điều khiển thiết bị.
5. **Đặt rule authorization:** scope ở route, quyền trên tài nguyên và kiểm tra từng command trong channel.
6. **Đặt giới hạn:** payload bytes, metadata bytes, active stream, rate, concurrency và timeout.
7. **Xử lý vòng đời:** token expiry, logout, cancellation, reconnect, resume và shutdown.
8. **Định nghĩa audit:** correlation, principal, route, Stream ID, quyết định và mã lỗi.
9. **Viết abuse case:** giả mạo, vượt tenant, flood, replay, injection và slow consumer.
10. **Kiểm thử trước phát hành:** cả success path, negative path và tải đồng thời.

Không nên xem checklist là thủ tục giấy tờ. Mỗi quyết định cần gắn với route, code path hoặc cấu hình cụ thể để có thể kiểm tra lại.

## 19. Checklist bảo mật cho kết nối RSocket dài hạn

- Dùng TLS cho TCP hoặc WSS cho WebSocket trên mạng không tin cậy.
- Xác thực peer ở SETUP, request hoặc cả hai theo mô hình identity.
- Không dùng một principal của người dùng cho connection chia sẻ nhiều user.
- Đặt authorization theo route và quyền trên tài nguyên.
- Kiểm tra từng command trong request-channel.
- Kiểm tra dữ liệu outbound theo tenant và quyền subscriber.
- Revalidate khi token hết hạn, logout hoặc quyền bị thu hồi.
- Đóng connection và hủy stream khi identity không còn hợp lệ.
- Validate Origin khi dùng WebSocket từ browser.
- Giới hạn connection, stream, payload, metadata, rate và concurrency.
- Dùng bounded buffer và xử lý slow consumer.
- Có idempotency/cursor cho reconnect và resume.
- Không log token, credential hoặc payload nhạy cảm.
- Có audit/metric cho auth, authorization, cancellation và reconnect.
- Kiểm thử các nhánh bị từ chối và tải cao.

## 20. Kết luận

Mô hình đe dọa của RSocket phải xét đến kết nối dài hạn, multiplex nhiều stream và dữ liệu hai chiều. Xác thực lúc SETUP có thể phù hợp với connection một người dùng; kết nối chia sẻ nhiều người dùng cần nhận diện từng request. Authorization theo route giúp bảo vệ lúc mở interaction, nhưng request-channel còn cần kiểm tra quyền trên từng command và dữ liệu được phát về.

Bảo vệ hệ thống bằng nhiều lớp: TLS/mTLS, authentication, authorization, validation, quota, backpressure, timeout, cancellation cleanup, idempotency, audit và kiểm thử. Đặc biệt, cần có chính sách cho token expiry, logout, thu hồi quyền và resume để một session cũ không tiếp tục truy cập dữ liệu sau khi danh tính hoặc quyền đã thay đổi.

Tài liệu tham khảo:
- [Spring Security Reference – RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [OWASP WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)

