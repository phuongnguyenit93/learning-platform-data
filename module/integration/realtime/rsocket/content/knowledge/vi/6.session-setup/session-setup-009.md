# Quản lý thông tin phiên và tài nguyên gắn với kết nối

Một kết nối RSocket có thể tồn tại lâu và mang nhiều request hoặc stream đồng thời. Trong thời gian đó, server thường cần giữ một số thông tin chung cho peer đang kết nối, chẳng hạn danh tính đã xác thực, tenant, phiên bản client, khả năng được hỗ trợ và các tài nguyên phục vụ giao tiếp hai chiều. Những dữ liệu và tài nguyên này thuộc phạm vi của một phiên kết nối (connection session), không phải của riêng một request.

RSocket cung cấp frame SETUP để hai phía bắt đầu phiên và thỏa thuận các tham số giao tiếp. Ứng dụng có thể gửi dữ liệu khởi tạo trong SETUP, xác thực thông tin đó, tạo session context ở phía server rồi gắn các tài nguyên có cùng vòng đời với connection. Khi connection đóng, các tài nguyên này phải được giải phóng. Nếu client kết nối lại, đó là một phiên mới và server cần thiết lập lại context theo chính sách của hệ thống.

## 1. Phân biệt thông tin phiên và thông tin request

Một ứng dụng realtime thường có ba phạm vi dữ liệu:

| Phạm vi | Ví dụ | Vòng đời |
| --- | --- | --- |
| Connection/session | Principal đã xác thực, tenant đã kiểm tra, client ID, phiên bản ứng dụng, capability, subscription dùng chung. | Từ khi SETUP được chấp nhận đến khi connection đóng. |
| Request/stream | Route, correlation ID, dữ liệu nghiệp vụ, deadline, thông tin phân trang. | Trong một request hoặc stream cụ thể. |
| Ứng dụng | Cấu hình chung, connection pool, service singleton, serializer. | Theo vòng đời ứng dụng hoặc bean. |

Thông tin chỉ thay đổi theo từng request không nên được lưu thành trạng thái connection. Ví dụ, một client có thể gửi nhiều request tìm đơn hàng với các mã đơn hàng khác nhau; mỗi mã thuộc data của request. Ngược lại, tenant đã được xác thực và gắn với phiên có thể được dùng làm ngữ cảnh chung cho các request trên connection đó.

Không nên đồng nhất connection với người dùng. Một người dùng có thể mở nhiều connection từ nhiều thiết bị hoặc tab trình duyệt. Mỗi connection có vòng đời và tài nguyên riêng, dù chúng cùng ánh xạ tới một principal. Vì vậy, cần phân biệt user ID, client ID và connection/session ID.

## 2. SETUP là điểm khởi đầu của phiên

Trong RSocket, client gửi frame SETUP đầu tiên sau khi transport TCP hoặc WebSocket được thiết lập. SETUP khởi tạo phiên giao thức và mang các tham số như:

- Phiên bản giao thức RSocket.
- Khoảng thời gian KEEPALIVE và thời gian tối đa cho phép không nhận frame.
- Data MIME type mặc định cho payload.
- Metadata MIME type mặc định cho metadata.
- Các cờ tính năng như Resume hoặc Lease nếu được sử dụng.
- Setup payload, có thể chứa data và metadata khởi tạo.

Setup payload phù hợp để truyền thông tin cần thiết khi bắt đầu một connection, ví dụ tên ứng dụng client, phiên bản giao thức nghiệp vụ, capability hoặc credential theo cơ chế xác thực đã thống nhất. Server có thể kiểm tra dữ liệu này trước khi chấp nhận phiên.

Trình tự khái quát:

~~~text
Client                              Server
  |                                    |
  |---- mở TCP / WebSocket ---------->|
  |                                    |
  |---- SETUP ------------------------>|
  |     data MIME type                 |
  |     metadata MIME type             |
  |     keepalive parameters           |
  |     setup payload                  |
  |                                    |
  |                         kiểm tra SETUP
  |                         xác thực / tạo context
  |                                    |
  |<======= session READY ============>|
  |                                    |
  |---- request / stream ------------->|
  |<--- response / stream -------------|
  |                                    |
  |---- đóng hoặc mất connection ----->|
  |                         giải phóng tài nguyên
~~~

SETUP là thông điệp khởi tạo ở cấp connection, không phải một request nghiệp vụ thông thường. Data hoặc metadata trong SETUP không tự động được chèn vào mọi request tiếp theo. Nếu một giá trị cần thay đổi theo từng message, client phải gửi nó trong payload hoặc metadata của message tương ứng.

RSocket không dùng một frame SETUP_ACK riêng để xác nhận thành công. Ở phía client, API connect chỉ phát ra đối tượng RSocket sau khi quá trình thiết lập được chấp nhận; nếu setup bị từ chối, Publisher connect kết thúc bằng lỗi. Ở phía server, ứng dụng nhận sự kiện setup hoặc callback acceptor để xác thực và tạo responder.

## 3. Gửi thông tin khởi tạo từ client

Với Spring, <code>RSocketRequester.Builder</code> cho phép cấu hình data MIME type, metadata MIME type và dữ liệu gửi trong SETUP. Ví dụ dưới đây gửi một thông tin nhận diện client và capability:

~~~java
MimeType compositeMimeType = MimeTypeUtils.parseMimeType(
    "message/x.rsocket.composite-metadata.v0"
);
MimeType clientContextMimeType = MimeTypeUtils.parseMimeType(
    "application/vnd.example.client-context"
);

Mono<RSocketRequester> requesterMono = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(compositeMimeType)
    .setupRoute("client.connect")
    .setupData(new ClientHello(
        "web-dashboard",
        "2.4.0",
        List.of("orders.watch", "inventory.read")
    ))
    .setupMetadata(
        new ClientContext("tenant-42", "browser"),
        clientContextMimeType
    )
    .connect(TcpClientTransport.create("localhost", 7000));
~~~

Trong ví dụ, route <code>client.connect</code> được dùng để định tuyến thông tin SETUP tới handler khởi tạo connection ở server. <code>ClientHello</code> là data của SETUP; <code>ClientContext</code> là một entry metadata có MIME type riêng. Metadata MIME type của phiên được đặt là Composite Metadata để có thể mang nhiều entry. Client và server phải thống nhất serializer, MIME type và cấu trúc của từng kiểu dữ liệu.

Đối với WebSocket, phần cấu hình setup payload tương tự; chỉ thay transport bằng WebSocket transport và địa chỉ endpoint tương ứng. Các tham số setup khác vẫn thuộc về phiên RSocket sau khi transport được mở.

Không nên gửi một object chứa toàn bộ cấu hình client, thông tin cá nhân và bí mật vào SETUP. Chỉ gửi các trường thực sự cần cho việc khởi tạo session. Credential nên dùng cơ chế xác thực RSocket/Spring Security tương ứng và phải được bảo vệ bằng TLS khi truyền qua mạng.

## 4. Xử lý SETUP ở phía server với Spring

Spring RSocket hỗ trợ <code>@ConnectMapping</code> để xử lý sự kiện thiết lập connection. Route của <code>@ConnectMapping</code> được đối chiếu với setup route mà client gửi. Handler có thể đọc setup data, xác minh thông tin ban đầu và từ chối connection nếu điều kiện khởi tạo không hợp lệ.

Ví dụ:

~~~java
@Controller
public class ClientConnectionController {

    private final ClientPolicy clientPolicy;

    public ClientConnectionController(ClientPolicy clientPolicy) {
        this.clientPolicy = clientPolicy;
    }

    @ConnectMapping("client.connect")
    public Mono<Void> onConnect(@Payload ClientHello hello) {
        return clientPolicy.validate(
                hello.clientName(),
                hello.clientVersion(),
                hello.capabilities()
            )
            .then();
    }
}
~~~

Method này được gọi trong giai đoạn connection setup. Nếu validation trả về lỗi, quá trình setup có thể bị từ chối và client không nhận được RSocket requester sẵn sàng. Không nên dùng <code>@ConnectMapping</code> để thực hiện công việc nghiệp vụ dài hoặc chờ một tác vụ không có giới hạn; setup cần hoàn tất nhanh để client có thể bắt đầu sử dụng session.

<code>@ConnectMapping</code> phù hợp để kiểm tra thông tin khởi tạo và áp dụng chính sách ở tầng Spring. Nếu ứng dụng cần kiểm soát trực tiếp vòng đời của responder, connection-specific state hoặc tài nguyên cấp thấp, có thể dùng <code>SocketAcceptor</code> của RSocket Java. Cần chọn một nơi sở hữu rõ ràng việc tạo và giải phóng session context để tránh hai tầng cùng quản lý một tài nguyên.

## 5. Tạo session context gắn với connection

Sau khi xác thực thành công, server có thể tạo một đối tượng context đại diện cho connection. Context thường chứa dữ liệu đã được kiểm tra và các tài nguyên có vòng đời không vượt quá connection:

~~~java
public final class ConnectionSession {
    private final String connectionId;
    private final Principal principal;
    private final String tenantId;
    private final String clientName;
    private final String clientVersion;
    private final Disposable.Composite resources =
        Disposables.composite();

    public ConnectionSession(
            String connectionId,
            Principal principal,
            String tenantId,
            String clientName,
            String clientVersion) {
        this.connectionId = connectionId;
        this.principal = principal;
        this.tenantId = tenantId;
        this.clientName = clientName;
        this.clientVersion = clientVersion;
    }

    public void addResource(Disposable resource) {
        resources.add(resource);
    }

    public void close() {
        resources.dispose();
    }

    public String connectionId() {
        return connectionId;
    }

    public Principal principal() {
        return principal;
    }

    public String tenantId() {
        return tenantId;
    }
}
~~~

Đây là ví dụ minh họa cách gom tài nguyên vào một owner. Các trường định danh nên được thiết lập một lần sau khi xác thực và không thay đổi tùy tiện trong suốt phiên. Các tài nguyên reactive được đăng ký vào <code>Disposable.Composite</code>; khi connection đóng, gọi <code>dispose()</code> để hủy các subscription thuộc phiên.

Không nên lưu trực tiếp token thô nếu chỉ cần danh tính đã xác thực. Hãy giữ principal hoặc một đối tượng identity tối thiểu theo chính sách bảo mật. Nếu cần lưu thông tin tenant, hãy lấy tenant đã được xác minh từ principal hoặc bước authorization, thay vì tin vào chuỗi tenant do client tự khai báo.

## 6. Gắn context và tài nguyên vào responder

Ở tầng RSocket Java, <code>SocketAcceptor</code> nhận setup payload và socket dùng để gửi dữ liệu về phía client. Đây là điểm có thể xác thực thông tin setup, tạo session context và xây dựng responder riêng cho connection đó.

~~~java
SocketAcceptor acceptor = (setup, sendingSocket) ->
    authenticate(setup)
        .map(identity -> {
            ConnectionSession session =
                sessionRegistry.open(identity);

            RSocket responder =
                new SessionResponder(session, sendingSocket);

            responder.onClose()
                .doFinally(signal ->
                    sessionRegistry.close(session.connectionId()))
                .subscribe();

            return responder;
        });
~~~

<code>SessionResponder</code> là responder do ứng dụng triển khai; nó nhận <code>ConnectionSession</code> qua constructor và dùng context đó khi xử lý request. <code>sendingSocket</code> cho phép server khởi tạo tương tác ngược về client nếu ứng dụng cần giao tiếp hai chiều. Mỗi lần acceptor tạo một responder tương ứng với một connection, nhờ đó trạng thái của connection này không bị trộn với connection khác.

Đoạn mã là khung tổ chức, các hàm <code>authenticate</code>, <code>sessionRegistry.open</code>, <code>sessionRegistry.close</code> và <code>SessionResponder</code> cần được triển khai theo mô hình bảo mật và nghiệp vụ của ứng dụng. Khi dùng Spring, có thể để framework xử lý routing và serialization, còn một thành phần quản lý session chịu trách nhiệm sở hữu context và resource cleanup.

Một registry có thể dùng <code>ConcurrentMap</code> để tra cứu session theo connection ID:

~~~java
public final class SessionRegistry {
    private final ConcurrentMap<String, ConnectionSession> sessions =
        new ConcurrentHashMap<>();

    public ConnectionSession open(AuthenticatedIdentity identity) {
        ConnectionSession session = createSession(identity);
        sessions.put(session.connectionId(), session);
        return session;
    }

    public void close(String connectionId) {
        ConnectionSession session = sessions.remove(connectionId);
        if (session != null) {
            session.close();
        }
    }

    private ConnectionSession createSession(
            AuthenticatedIdentity identity) {
        return new ConnectionSession(
            UUID.randomUUID().toString(),
            identity.principal(),
            identity.tenantId(),
            identity.clientName(),
            identity.clientVersion()
        );
    }
}
~~~

Thao tác <code>remove</code> trước khi đóng giúp nhiều tín hiệu kết thúc lặp lại không giải phóng cùng session nhiều lần qua registry. Bản thân <code>ConnectionSession.close()</code> cũng nên idempotent để chống race condition giữa shutdown, timeout và lỗi transport.

## 7. Chọn tài nguyên nào nên gắn với connection?

Một tài nguyên chỉ nên gắn với connection nếu nó thực sự cần tồn tại trong suốt phiên và được dùng chung bởi các request thuộc phiên đó.

| Tài nguyên | Có thể gắn với connection? | Lưu ý |
| --- | --- | --- |
| Danh tính đã xác thực và tenant đã kiểm tra | Có | Dùng làm ngữ cảnh bảo mật; vẫn kiểm tra quyền trên từng tài nguyên nghiệp vụ. |
| Subscription theo dõi sự kiện dùng chung | Có | Hủy khi connection đóng hoặc khi client bỏ đăng ký. |
| Sink gửi thông báo về một client | Có | Giới hạn buffer và xử lý subscriber chậm. |
| Bộ đếm, metric theo connection | Có | Gắn nhãn bằng ID có kiểm soát, tránh cardinality quá cao. |
| Cache nhỏ chỉ phục vụ session | Có, nếu có giới hạn | Có TTL hoặc giới hạn dung lượng và được xóa khi đóng. |
| DTO của một request | Không | Chỉ tồn tại trong phạm vi xử lý request. |
| Connection pool tới database | Không | Là tài nguyên dùng chung cấp ứng dụng, không tạo một pool cho mỗi RSocket session. |
| Transaction database | Thông thường không | Không giữ transaction mở trong toàn bộ connection lâu dài. |
| File descriptor hoặc buffer tạm của một message | Không | Giải phóng khi xử lý message hoàn tất. |

Việc gắn quá nhiều tài nguyên vào một connection có thể làm server tiêu thụ bộ nhớ tăng theo số client. Nếu mỗi connection giữ một subscription, buffer lớn và cache không giới hạn, số lượng client đồng thời sẽ quyết định trực tiếp mức tiêu thụ tài nguyên.

Hãy xác định giới hạn số session, số subscription mỗi session, kích thước buffer và thời gian idle. Khi client mất mạng đột ngột, cleanup có thể chỉ diễn ra sau khi keepalive hoặc timeout phát hiện sự cố; do đó, tài nguyên session cần có giới hạn và timeout độc lập nếu cần.

## 8. Quản lý tài nguyên theo vòng đời

Vòng đời của một session context nên bám theo vòng đời connection:

1. **Tạo:** transport mở và SETUP được chấp nhận.
2. **Xác thực:** kiểm tra credential, principal, tenant và policy của client.
3. **Khởi tạo:** tạo session context và đăng ký các tài nguyên cần thiết.
4. **Sử dụng:** nhiều request hoặc stream truy cập context trong giới hạn quyền.
5. **Đóng:** connection hoàn tất, bị dispose, gặp lỗi hoặc timeout.
6. **Dọn dẹp:** hủy subscription, đóng sink, xóa registry entry và giải phóng cache/buffer thuộc session.

Một ví dụ quản lý subscription:

~~~java
Disposable subscription = eventBus
    .eventsFor(session.tenantId())
    .subscribe(event -> sendToClient(session, event));

session.addResource(subscription);
~~~

Khi connection đóng, <code>session.close()</code> dispose subscription và ngừng việc gửi sự kiện cho client đó. Nếu <code>sendToClient</code> thực hiện request trên RSocket, cần xử lý lỗi gửi và kiểm tra trạng thái đóng; không nên để lỗi trong callback làm mất khả năng cleanup các tài nguyên còn lại.

Không giữ một subscription toàn cục rồi phát dữ liệu của tất cả tenant tới mọi connection. Hãy lọc dữ liệu theo principal và tenant đã xác thực trước khi đưa vào luồng của từng session. Nếu một stream được chia sẻ giữa nhiều client, cần có cơ chế quản lý reference count và tách rõ vòng đời của stream dùng chung với vòng đời từng subscriber.

## 9. Đóng connection và xử lý cleanup

Connection có thể kết thúc theo nhiều cách:

- Client chủ động gọi dispose hoặc đóng transport.
- Server chủ động đóng phiên khi shutdown hoặc thu hồi quyền truy cập.
- Peer gửi tín hiệu đóng connection.
- Transport bị ngắt do lỗi mạng, proxy hoặc tiến trình bị dừng.
- KEEPALIVE phát hiện peer không còn phản hồi trong thời gian cho phép.

Ứng dụng nên dùng một đường cleanup thống nhất cho các trường hợp này. Ví dụ, khi theo dõi <code>RSocket.onClose()</code>, callback cuối cùng có thể gọi <code>SessionRegistry.close(connectionId)</code>. Khi ứng dụng chủ động shutdown, cùng phương thức registry cũng được gọi. Cleanup phải an toàn khi được gọi nhiều lần.

Không nên dựa hoàn toàn vào sự kiện disconnect từ client. Client có thể tắt máy hoặc mất mạng mà không gửi thông điệp đóng có chủ đích. KEEPALIVE và timeout giúp server phát hiện session bị bỏ lại; đồng thời các tài nguyên có TTL hoặc giới hạn dung lượng giúp hệ thống không phụ thuộc vào một tín hiệu đóng hoàn hảo.

Nếu cần chờ các stream đang hoạt động kết thúc, hãy đặt thời hạn cụ thể. Khi hết thời hạn, hủy các tài nguyên còn lại rồi đóng session. Không chờ vô hạn vì một stream có thể không bao giờ hoàn tất.

## 10. Reconnect tạo session mới

Khi client reconnect sau khi mất kết nối, transport và RSocket session mới được tạo. Server phải chạy lại quá trình SETUP, xác thực lại thông tin và tạo context mới. Connection ID mới giúp phân biệt session mới với session cũ.

Không nên mặc định các tài nguyên của session cũ được chuyển sang session mới. Các subscription, sink hoặc buffer gắn với connection cũ cần được đóng; client đăng ký lại những luồng mà nó vẫn cần. Nếu nghiệp vụ cần khôi phục trạng thái, hãy lưu trạng thái quan trọng ở tầng ứng dụng hoặc database với khóa ổn định, thay vì chỉ giữ trong object session.

Resume là một extension riêng của RSocket, có thể khôi phục một số trạng thái giao thức khi hai bên hỗ trợ và cấu hình phù hợp. Resume không biến mọi tài nguyên Java gắn với object connection cũ thành tài nguyên tự động sống tiếp. Ứng dụng vẫn cần xác định cách xử lý session context, subscription và side effect khi resume thành công hoặc thất bại.

Nếu một người dùng mở hai thiết bị, hai connection có thể cùng được xác thực bởi một principal nhưng có hai connection context độc lập. Khi người dùng đăng xuất, hệ thống có thể cần thu hồi một connection cụ thể hoặc toàn bộ connection của principal đó; đây là chính sách quản lý phiên của ứng dụng.

## 11. Bảo mật thông tin phiên

Setup data và metadata đến từ client nên được xem là dữ liệu đầu vào không đáng tin cho đến khi được xác minh. Việc một client gửi tenant-42, role=ADMIN hoặc danh sách capability không chứng minh rằng client có quyền tương ứng.

Các nguyên tắc quan trọng:

- Xác thực bằng cơ chế bảo mật phù hợp, chẳng hạn authentication metadata được Spring Security hỗ trợ.
- Lấy principal từ kết quả xác thực của server, không tự dựng principal từ tên người dùng do client khai báo.
- Ràng buộc tenant với danh tính đã xác thực và kiểm tra quyền trên từng tài nguyên.
- Chỉ lưu các thông tin cần thiết trong session context; tránh giữ token thô hoặc bí mật lâu hơn cần thiết.
- Giới hạn kích thước setup payload và metadata để tránh tiêu thụ tài nguyên bất thường.
- Không ghi token, credential hoặc payload nhạy cảm vào log.
- Có chính sách hết hạn và thu hồi phiên khi credential bị thu hồi hoặc người dùng bị khóa.

Setup payload là dữ liệu khởi tạo một connection, không phải một cơ chế authorization hoàn chỉnh. Những route nhạy cảm vẫn phải kiểm tra quyền khi được gọi, vì quyền có thể thay đổi trong khi connection vẫn đang mở.

## 12. Kiểm thử quản lý session và tài nguyên

Nên kiểm thử vòng đời của session context cùng với hành vi giao tiếp:

| Tình huống | Kết quả cần xác nhận |
| --- | --- |
| SETUP hợp lệ | Server xác thực và tạo đúng một session context. |
| SETUP thiếu hoặc sai credential | Connection bị từ chối; không để lại session hoặc subscription. |
| Tenant không hợp lệ | Không tạo context có quyền truy cập tenant đó. |
| Nhiều connection cùng principal | Mỗi connection có context và resource riêng. |
| Một connection đóng bình thường | Chỉ resource của connection đó được dispose và registry entry được xóa. |
| Transport mất đột ngột | Cleanup diễn ra sau khi lỗi hoặc timeout được phát hiện. |
| Cleanup được gọi nhiều lần | Không lỗi và không giải phóng nhầm tài nguyên của session khác. |
| Client reconnect | Tạo connection ID và context mới; subscription cần thiết được khôi phục theo chính sách. |
| Một stream bị hủy | Resource riêng của stream được giải phóng mà không đóng toàn bộ session nếu không cần. |
| Server shutdown | Ngừng nhận session mới và giải phóng các session còn lại trong thời hạn cho phép. |

Có thể dùng integration test với RSocket server thật trên transport thử nghiệm và kiểm tra số session trong registry, số subscription còn hoạt động, cũng như việc <code>Disposable</code> được dispose. Với các luồng bất đồng bộ, dùng <code>StepVerifier</code> hoặc latch có timeout để tránh kiểm thử treo vô hạn.

## 13. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Lưu tenant hoặc principal toàn cục | Request từ các connection khác nhau có thể dùng nhầm context. | Tạo context riêng cho từng connection và kiểm tra quyền theo request. |
| Tin setup data như danh tính đã xác thực | Client có thể tự khai báo tenant hoặc role giả. | Xác thực credential và lấy identity từ server security context. |
| Đưa dữ liệu từng request vào session | Context cũ hoặc sai dữ liệu được tái sử dụng. | Giữ request data ở phạm vi message/stream. |
| Không dispose subscription khi disconnect | Subscription và buffer tiếp tục giữ tài nguyên. | Gom resource vào session context và cleanup khi <code>onClose</code>. |
| Cleanup không idempotent | Tín hiệu đóng lặp gây lỗi hoặc giải phóng nhầm. | Dùng registry remove nguyên tử và phương thức close an toàn khi gọi nhiều lần. |
| Giữ transaction hoặc pool theo từng session | Tài nguyên tăng mạnh theo số connection. | Dùng pool cấp ứng dụng và transaction ngắn theo thao tác nghiệp vụ. |
| Chuyển nguyên session object qua reconnect | Tài nguyên cũ có thể đã đóng hoặc không còn hợp lệ. | Tạo context mới và phục hồi trạng thái nghiệp vụ có kiểm soát. |

## 14. Ghi nhớ

- SETUP khởi tạo phiên RSocket và có thể mang setup data cùng metadata.
- Thông tin phiên có vòng đời connection; dữ liệu nghiệp vụ từng lần gọi thuộc request hoặc stream.
- Xác thực setup trước khi tạo context và chỉ lưu identity đã được server xác minh.
- Mỗi connection nên có session context và tập tài nguyên riêng, có giới hạn rõ ràng.
- Theo dõi <code>onClose()</code> và dùng một đường cleanup thống nhất để dispose subscription, sink và cache thuộc phiên.
- Reconnect tạo session mới; ứng dụng phải xác thực và khởi tạo lại context.
- Session context không thay thế authorization ở từng request, và không nên giữ transaction hoặc connection pool lâu dài theo từng client.
