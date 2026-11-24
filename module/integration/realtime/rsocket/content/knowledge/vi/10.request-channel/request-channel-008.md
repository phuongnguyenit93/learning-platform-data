# Quản lý trạng thái và tài nguyên trong một kênh dài hạn

Request-channel là interaction model của RSocket cho phép hai phía trao đổi dữ liệu theo hai luồng đồng thời trên cùng một tương tác: requester gửi một luồng payload tới responder và responder cũng trả về một luồng payload. Mô hình này phù hợp với phiên làm việc cần trao đổi liên tục, chẳng hạn phòng cộng tác realtime, phiên điều khiển thiết bị, đồng bộ trạng thái hoặc một quy trình tương tác kéo dài.

Vì một channel có thể tồn tại lâu hơn một request thông thường, ứng dụng phải quản lý trạng thái và tài nguyên gắn với channel. Khi channel được mở, server có thể đăng ký listener, tạo bộ đệm hoặc cấp phát context riêng. Khi một chiều dữ liệu hoàn tất, channel bị hủy, gặp lỗi hoặc connection mất, những tài nguyên này cần được xử lý theo đúng vòng đời. Nếu không, hệ thống có thể giữ listener và buffer không còn được dùng, gây rò rỉ bộ nhớ hoặc tiếp tục làm việc sau khi client đã rời đi.

## 1. Request-channel có hai luồng dữ liệu

Trong request-channel, requester gửi một luồng đầu vào và nhận một luồng đầu ra. Hai luồng hoạt động độc lập về hướng truyền:

~~~text
Requester (client)                         Responder (server)
       |                                           |
       |--- REQUEST_CHANNEL (initial payload) ---->|
       |                                           |
       |--- PAYLOAD (client item 2) -------------->|
       |<---------------- PAYLOAD (server item 1) -|
       |--- PAYLOAD (client item 3) -------------->|
       |<---------------- PAYLOAD (server item 2) -|
       |                                           |
       |--- PAYLOAD (COMPLETE) ------------------->|  Client ngừng gửi
       |<---------------- PAYLOAD (server item 3) -|  Server vẫn có thể trả dữ liệu
       |<---------------- PAYLOAD (COMPLETE) ------|  Server kết thúc chiều phản hồi
       |                                           |
~~~

Request-channel khác request-stream ở chỗ client có thể tiếp tục gửi nhiều phần tử sau request đầu tiên. Nó cũng khác request-response vì phản hồi không bị giới hạn ở một giá trị.

Một điểm quan trọng là hai chiều có thể hoàn tất độc lập. Khi client gửi tín hiệu hoàn tất chiều gửi, server vẫn có thể tiếp tục phát phản hồi nếu thiết kế nghiệp vụ yêu cầu. Tương tự, server có thể hoàn tất chiều phản hồi trong khi client vẫn còn gửi dữ liệu. Việc hủy toàn bộ channel hoặc lỗi ở cấp stream mới chấm dứt tương tác chung.

## 2. Phân biệt trạng thái channel và trạng thái connection

Một RSocket connection có thể mang nhiều channel cùng lúc. Do đó, trạng thái của một channel không được dùng làm trạng thái của toàn bộ connection.

| Phạm vi | Ví dụ trạng thái | Ý nghĩa |
| --- | --- | --- |
| Connection/session | CONNECTING, READY, CLOSING, CLOSED | Khả năng sử dụng phiên RSocket để mở và phục vụ stream. |
| Channel | OPENING, ACTIVE, INPUT_COMPLETED, OUTPUT_COMPLETED, TERMINATED | Vòng đời của một tương tác request-channel cụ thể. |
| Tài nguyên channel | ALLOCATED, IN_USE, RELEASING, RELEASED | Trạng thái của context, listener, buffer hoặc tài nguyên riêng của channel. |

Ví dụ, client có thể mở ba channel: một channel cộng tác tài liệu, một channel điều khiển thiết bị và một channel đồng bộ dữ liệu. Nếu channel điều khiển thiết bị bị lỗi, hai channel còn lại vẫn có thể hoạt động trên cùng connection.

Mỗi channel nên có định danh riêng ở tầng ứng dụng nếu cần theo dõi, log hoặc quản lý tài nguyên. Stream ID của giao thức hữu ích trong phạm vi connection, nhưng không nên dùng nó làm định danh nghiệp vụ bền vững qua reconnect.

## 3. Mô hình trạng thái cho channel dài hạn

Một state machine ở tầng ứng dụng giúp xác định rõ thời điểm tạo, sử dụng và giải phóng tài nguyên:

~~~text
          open request-channel
                   |
                   v
                OPENING
                   |
          handler accepted input
                   |
                   v
                 ACTIVE
                /      \
               /        \
     input completes   output completes
             |               |
             v               v
      INPUT_COMPLETED   OUTPUT_COMPLETED
             \               /
              \             /
               \           /
             both directions end
                     |
                     v
                 TERMINATED

ACTIVE / INPUT_COMPLETED / OUTPUT_COMPLETED
                     |
          cancel, stream error,
          connection loss or timeout
                     |
                     v
                 TERMINATED
                     |
                     v
              RELEASE RESOURCES
~~~

Đây là mô hình quản lý ở tầng ứng dụng, không phải danh sách trạng thái bắt buộc của RSocket Java. Ứng dụng có thể dùng enum đơn giản hơn, miễn là phân biệt được channel đang hoạt động, một chiều đã hoàn tất và toàn bộ channel đã kết thúc.

Các trạng thái cần hiểu:

- **OPENING:** client gửi request-channel ban đầu; server xác thực, kiểm tra route và khởi tạo context.
- **ACTIVE:** hai chiều có thể gửi và nhận phần tử.
- **INPUT_COMPLETED:** requester đã hoàn tất chiều gửi; responder có thể xử lý phần dữ liệu đã nhận và tiếp tục phát kết quả.
- **OUTPUT_COMPLETED:** responder đã hoàn tất chiều phản hồi; requester có thể vẫn đang gửi nếu giao thức và hợp đồng ứng dụng cho phép.
- **TERMINATED:** channel kết thúc do cả hai chiều hoàn tất, cancellation, lỗi hoặc connection bị đóng.
- **RELEASED:** tài nguyên gắn với channel đã được giải phóng.

Không nên đồng nhất hoàn tất một chiều với việc channel đã TERMINATED. Nếu giải phóng context ngay khi inbound hoàn tất nhưng server vẫn còn phát event, dữ liệu phản hồi có thể truy cập vào tài nguyên đã đóng.

## 4. Tài nguyên nào cần quản lý theo channel?

Một channel dài hạn có thể sở hữu nhiều loại tài nguyên:

| Tài nguyên | Ví dụ | Khi kết thúc channel |
| --- | --- | --- |
| Channel context | Người dùng, tenant, trạng thái phiên cộng tác | Xóa khỏi registry và giải phóng tham chiếu. |
| Subscription nguồn | Listener từ event bus, topic broker hoặc thiết bị | Hủy subscription để không nhận thêm sự kiện. |
| Buffer/queue | Hàng đợi lệnh và event chờ gửi | Xả hoặc loại bỏ theo chính sách, sau đó giải phóng bộ nhớ. |
| Timer/heartbeat | Tác vụ kiểm tra idle hoặc lịch gửi heartbeat | Hủy timer và tác vụ định kỳ. |
| Tài nguyên I/O | Cursor, file handle, socket phụ hoặc session downstream | Đóng bằng API tương ứng. |
| Bộ đếm và quota | Số channel hoạt động của người dùng hoặc tenant | Giảm bộ đếm đúng một lần. |

Không phải mọi tài nguyên đều thuộc channel. Connection pool, scheduler dùng chung, client tới message broker hoặc cache toàn ứng dụng thường có vòng đời dài hơn. Channel chỉ nên giữ subscription hoặc handle riêng mà nó đã tạo; khi channel kết thúc, không được đóng tài nguyên dùng chung của các channel khác.

Quy tắc sở hữu rõ ràng giúp tránh hai lỗi đối nghịch: rò rỉ vì không giải phóng tài nguyên riêng, và làm gián đoạn các channel khác vì đóng nhầm tài nguyên dùng chung.

## 5. Tạo và giải phóng context theo vòng đời Publisher

Với Reactor, cách an toàn là tạo context khi Publisher được subscribe và gắn thao tác cleanup vào tín hiệu kết thúc của Publisher trả về. <code>doFinally</code> được gọi khi luồng hoàn tất, lỗi hoặc bị hủy:

~~~java
@MessageMapping("collaboration.open")
public Flux<ChannelOutput> open(Flux<ChannelInput> inbound) {
    return Flux.defer(() -> {
        ChannelContext context = channelRegistry.open();

        Flux<ChannelOutput> commandReplies =
            inbound.concatMap(context::handle);

        Flux<ChannelOutput> serverEvents =
            context.events();

        return Flux.merge(commandReplies, serverEvents)
            .doFinally(signal -> {
                context.close();
                channelRegistry.remove(context.id());
                log.info(
                    "Channel {} terminated: {}",
                    context.id(),
                    signal
                );
            });
    });
}
~~~

Ví dụ minh họa một channel nhận lệnh từ client đồng thời phát event từ server. <code>Flux.defer</code> tạo context cho mỗi lần subscribe. <code>concatMap</code> xử lý lệnh tuần tự để tránh nhiều lệnh đồng thời sửa cùng trạng thái. <code>Flux.merge</code> ghép phản hồi từ lệnh với event chủ động của server.

<code>merge</code> có thể xen kẽ phần tử từ hai nguồn; thứ tự giữa hai nguồn không được bảo đảm. Thứ tự trong từng nguồn vẫn được giữ. Nếu nghiệp vụ yêu cầu một thứ tự tổng thể, hãy gắn sequence number hoặc đưa cả lệnh và event vào một bộ điều phối tuần tự thay vì dựa vào thứ tự tình cờ của merge.

Phương thức <code>context.close()</code> cần idempotent: gọi nhiều lần vẫn an toàn. Điều này quan trọng vì cleanup có thể được kích hoạt bởi nhiều nhánh shutdown hoặc lỗi cạnh tranh. Registry cũng cần kiểm tra định danh context trước khi xóa để không xóa nhầm context mới.

Với tài nguyên cần đóng bất đồng bộ, có thể dùng <code>usingWhen</code> để gắn thao tác cleanup vào cả ba nhánh hoàn tất, lỗi và cancellation:

~~~java
return Flux.usingWhen(
    channelRegistry.openAsync(),
    context -> buildChannelOutput(inbound, context),
    ChannelContext::closeAsync,
    (context, error) -> context.closeAsync(),
    ChannelContext::closeAsync
);
~~~

Mẫu này phù hợp khi việc đóng tài nguyên trả về một Publisher, chẳng hạn đóng session downstream hoặc ghi nhận trạng thái cuối cùng qua một API bất đồng bộ. Cần bảo đảm cleanup có timeout và lỗi cleanup được ghi nhận; không để quá trình giải phóng treo vô hạn.

## 6. Triển khai phía server với Spring Boot

Spring RSocket ánh xạ request-channel tới method nhận một Publisher đầu vào và trả về một Publisher đầu ra. Trong Reactor, hai kiểu thường là <code>Flux&lt;ClientMessage&gt;</code> và <code>Flux&lt;ServerMessage&gt;</code>.

Ví dụ một channel cộng tác:

~~~java
@Controller
public class CollaborationController {

    private final CollaborationService collaborationService;

    public CollaborationController(
            CollaborationService collaborationService) {
        this.collaborationService = collaborationService;
    }

    @MessageMapping("room.join")
    public Flux<RoomEvent> join(Flux<RoomCommand> commands) {
        return Flux.defer(() -> {
            RoomChannel channel = collaborationService.openChannel();

            Flux<RoomEvent> commandResults =
                commands.concatMap(channel::handle);

            Flux<RoomEvent> broadcasts =
                channel.broadcasts();

            return Flux.merge(commandResults, broadcasts)
                .doFinally(signal -> channel.close());
        });
    }
}
~~~

Client gửi các lệnh như tham gia phòng, chỉnh sửa tài liệu hoặc rời phòng. Server có thể trả kết quả cho từng lệnh và đồng thời phát broadcast từ những người tham gia khác.

Ví dụ này chỉ mô tả cấu trúc xử lý. Trong ứng dụng thật, channel cần gắn với principal đã xác thực, room ID, tenant và quyền truy cập đã kiểm tra. Không được tạo context hoặc đăng ký broadcast trước khi xác minh client có quyền tham gia phòng.

### Chọn cách xử lý lệnh đồng thời

<code>concatMap</code> xử lý từng command theo thứ tự, phù hợp khi các command cùng cập nhật một state machine. Nếu mỗi command độc lập và service an toàn khi chạy song song, có thể dùng <code>flatMap</code> với concurrency được giới hạn:

~~~java
Flux<RoomEvent> results =
    commands.flatMap(channel::handle, 8);
~~~

Không nên dùng concurrency không giới hạn cho một channel dài hạn. Một client có thể gửi nhiều command nhanh hơn tốc độ xử lý; giới hạn concurrency và buffer giúp bảo vệ tài nguyên. Khi cần bảo toàn thứ tự nghiệp vụ, ưu tiên xử lý tuần tự hoặc dùng sequence number để phát hiện lệnh đến sai thứ tự.

## 7. Mở channel và gửi dữ liệu từ client

Với Spring <code>RSocketRequester</code>, client chỉ định route, cung cấp Publisher đầu vào và nhận Publisher phản hồi bằng <code>retrieveFlux</code>:

~~~java
Flux<RoomCommand> commands = commandSource();

Flux<RoomEvent> events = requester
    .route("room.join")
    .data(commands)
    .retrieveFlux(RoomEvent.class);

Disposable channel = events.subscribe(
    event -> render(event),
    error -> log.error("Room channel failed", error),
    () -> log.info("Room channel completed")
);
~~~

Publisher đầu vào và Subscriber đầu ra hoạt động đồng thời. Client có thể gửi command mới trong khi đang nhận broadcast từ server.

Request-channel cần một payload ban đầu để mở tương tác. Nếu Publisher đầu vào hoàn tất mà không phát phần tử nào, client không có payload ban đầu để gửi REQUEST_CHANNEL. Nếu ứng dụng cần mở channel trước rồi mới có command, hãy gửi một message khởi tạo rõ ràng, chẳng hạn <code>JoinRoom</code> hoặc <code>OpenSession</code>, sau đó mới gửi các message tiếp theo.

Khi người dùng rời phòng hoặc đóng màn hình, client hủy subscription của channel:

~~~java
channel.dispose();
~~~

Cancellation kết thúc tương tác và cần được truyền tới server để server dừng broadcast, hủy listener và giải phóng context. Client nên giữ handle theo từng channel; không dùng chung một Disposable cho nhiều phòng hoặc nhiều phiên làm việc.

## 8. Quản lý hai chiều hoàn tất độc lập

Trong channel, mỗi phía có thể ngừng gửi dữ liệu của mình mà không nhất thiết chấm dứt ngay chiều còn lại. Đây thường được gọi là half-close ở góc nhìn luồng hai chiều.

Ví dụ, client gửi xong một batch lệnh nhưng vẫn chờ server trả kết quả xử lý. Client hoàn tất chiều input; server tiếp tục phát các kết quả còn lại rồi mới hoàn tất chiều output. Một ví dụ khác là server đã gửi xong snapshot ban đầu nhưng client vẫn tiếp tục gửi các thay đổi.

Khi thiết kế state machine, cần quyết định rõ:

- Khi input hoàn tất, server có tiếp tục phát event chủ động không?
- Khi output hoàn tất, server còn chấp nhận command mới không?
- Điều kiện nào khiến toàn bộ channel kết thúc?
- Ai sở hữu context cho tới thời điểm cuối cùng?
- Nếu một chiều im lặng lâu, đó là bình thường hay là timeout?

Nếu server cần giữ channel hoạt động sau khi input hoàn tất, output Publisher phải còn nguồn phát và context phải được giữ đến khi output kết thúc hoặc bị hủy. Nếu nghiệp vụ yêu cầu cả hai chiều kết thúc cùng lúc, ứng dụng phải điều phối điều kiện đóng rõ ràng thay vì giả định framework tự đóng cả hai chiều khi một Publisher hoàn tất.

## 9. Backpressure và giới hạn tài nguyên

Hai chiều của request-channel có demand riêng. Client điều tiết số phần tử phản hồi nó nhận từ server; server cũng tiêu thụ luồng command từ client theo demand của Publisher phía server. Vì vậy, ứng dụng cần xem xét backpressure ở cả hai hướng.

Backpressure không tự giới hạn số channel mà một người dùng có thể mở. Một client vẫn có thể mở hàng nghìn channel, mỗi channel giữ listener và buffer. Cần thêm các giới hạn ở tầng ứng dụng:

- Số channel đồng thời trên mỗi connection, user hoặc tenant.
- Kích thước payload và metadata tối đa.
- Số command đang chờ xử lý trên mỗi channel.
- Kích thước buffer cho event chưa được gửi.
- Concurrency của các thao tác bất đồng bộ.
- Thời gian sống tối đa và thời gian idle nếu nghiệp vụ có giới hạn.

Nếu event là trạng thái mới nhất, có thể coalesce nhiều thay đổi thành một snapshot. Nếu event là lệnh hoặc audit record cần bảo toàn, cần hàng đợi có giới hạn và chính sách từ chối hoặc lưu bền vững khi quá tải. Không nên âm thầm bỏ dữ liệu quan trọng.

Một số metric hữu ích gồm số channel đang mở, tuổi channel, số subscription nguồn, kích thước queue, số lần cancel, số channel kết thúc do lỗi và thời gian cleanup.

## 10. Timeout, heartbeat và channel im lặng

Channel dài hạn có thể có khoảng thời gian không phát dữ liệu. Điều đó không nhất thiết có nghĩa connection hỏng. Một phòng cộng tác không có người chỉnh sửa có thể im lặng nhiều phút; một channel điều khiển thiết bị có thể cần heartbeat thường xuyên hơn.

Cần phân biệt:

| Cơ chế | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| RSocket KEEPALIVE | Connection/session | Phát hiện peer hoặc đường truyền không trao đổi frame trong thời gian cho phép. |
| Channel heartbeat | Một channel | Xác nhận channel hoặc ứng dụng ở hai đầu vẫn tham gia phiên nghiệp vụ. |
| Idle timeout | Một channel hoặc người dùng | Đóng channel sau thời gian không có hoạt động theo chính sách sản phẩm. |
| Operation timeout | Một command | Giới hạn thời gian xử lý một thao tác cụ thể trong channel. |

Không nên áp dụng <code>timeout</code> ngắn lên toàn bộ channel nếu nguồn event có thể im lặng hợp lệ. Có thể đặt timeout cho từng command, dùng heartbeat riêng hoặc kiểm tra idle dựa trên hoạt động nghiệp vụ. Khi idle timeout kết thúc channel, phải đi qua cùng đường cleanup như cancellation và lỗi.

## 11. Xử lý lỗi và phục hồi

Lỗi trong một channel có thể xuất phát từ command không hợp lệ, quyền truy cập bị từ chối, nguồn broadcast lỗi, downstream timeout hoặc connection mất. Khi lỗi ở cấp stream kết thúc channel, các tài nguyên gắn với channel cần được giải phóng.

Nếu một command lỗi nhưng channel vẫn có thể tiếp tục, hãy phục hồi lỗi ở phạm vi command. Ví dụ:

~~~java
Flux<RoomEvent> commandResults =
    commands.concatMap(command ->
        channel.handle(command)
            .onErrorResume(error ->
                Mono.just(RoomEvent.commandRejected(
                    command.id(),
                    safeErrorCode(error)
                ))
            )
    );
~~~

Trong ví dụ này, lỗi của một command được chuyển thành event từ chối để các command tiếp theo vẫn có thể được xử lý. Chỉ nên làm vậy với lỗi có thể cô lập ở từng command. Lỗi hỏng state, mất quyền truy cập, vi phạm bảo mật hoặc lỗi nguồn dùng chung có thể yêu cầu kết thúc toàn bộ channel.

Khi connection bị mất, các channel trên connection đó có thể kết thúc. Reconnect tạo session mới và không tự động khôi phục state hoặc subscription cũ. Nếu cần tiếp tục một phiên nghiệp vụ, client nên gửi channel ID hoặc resume token ở mức ứng dụng cùng sequence number đã xác nhận. Server cần xác minh quyền sở hữu và thời hạn của phiên trước khi khôi phục.

RSocket Resume là extension ở cấp giao thức giúp tiếp tục truyền frame khi hai phía hỗ trợ và còn giữ trạng thái cần thiết. Nó không thay thế checkpoint nghiệp vụ, idempotency hoặc deduplication. Một command đã được xử lý nhưng phản hồi chưa tới client có thể bị gửi lại sau reconnect; hãy dùng command ID hoặc idempotency key nếu thao tác có side effect.

## 12. Bảo mật và quyền sở hữu channel

Channel dài hạn giữ ngữ cảnh trong thời gian lâu hơn một request đơn lẻ. Vì vậy, cần kiểm tra danh tính và quyền ngay khi mở channel, sau đó áp dụng chính sách cho mọi command và event.

- Ràng buộc channel với principal, tenant và tài nguyên đã được xác thực.
- Kiểm tra quyền cho từng loại command, không chỉ kiểm tra quyền tham gia channel ban đầu nếu quyền có thể thay đổi.
- Không tin channel ID hoặc tenant ID do client tự khai báo nếu chưa xác minh.
- Giới hạn số channel và tài nguyên theo user/tenant để ngăn mở channel hàng loạt.
- Không ghi token hoặc payload nhạy cảm vào log.
- Khi principal bị thu hồi quyền hoặc phiên đăng nhập hết hạn, đóng channel và giải phóng listener liên quan.

Nếu channel phát broadcast cho nhiều người dùng, mỗi người chỉ nên nhận event mà họ có quyền xem. Việc lọc quyền phải được thực hiện ở tầng phân phối event hoặc trong service có hiểu biết về tenant, không dựa vào client tự lọc dữ liệu sau khi đã nhận.

## 13. Kiểm thử vòng đời và cleanup

Kiểm thử channel cần xác nhận cả dữ liệu hai chiều và tài nguyên được giải phóng đúng lúc. Một test chỉ kiểm tra các phần tử phản hồi có thể bỏ sót listener vẫn còn hoạt động sau cancellation.

Có thể kiểm tra cleanup của Publisher bằng <code>StepVerifier</code>:

~~~java
AtomicBoolean cleaned = new AtomicBoolean();

Flux<Integer> channelOutput = Flux.<Integer>never()
    .doFinally(signal -> cleaned.set(true));

StepVerifier.create(channelOutput)
    .thenCancel()
    .verify();

assertTrue(cleaned.get());
~~~

Trong integration test RSocket, nên kiểm tra:

1. Client gửi nhiều command và nhận nhiều event trên cùng channel.
2. Client hoàn tất chiều gửi nhưng server vẫn phát các phản hồi còn lại nếu hợp đồng cho phép.
3. Server hoàn tất chiều phản hồi theo chính sách đã định.
4. Client cancel và server dừng listener, timer, buffer và subscription.
5. Một command lỗi được cô lập hoặc kết thúc channel đúng theo chính sách.
6. Connection mất làm channel kết thúc và cleanup được gọi.
7. Nhiều channel đồng thời không dùng chung nhầm context hoặc Disposable.
8. Cleanup được gọi đúng một lần về mặt hiệu ứng dù nhiều nhánh kết thúc cạnh tranh.
9. Giới hạn channel, queue và payload được áp dụng khi tải tăng.
10. Reconnect khôi phục channel theo checkpoint mà không phát lại side effect ngoài ý muốn.

Nên kiểm tra cả completion, error và cancellation. Trong Reactor, <code>doFinally</code> hữu ích để quan sát cả ba nhánh; <code>doOnCancel</code> chỉ chạy khi subscription bị hủy.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| Listener vẫn chạy sau khi client rời channel | Không gắn cleanup với cancellation hoặc tự subscribe ở bên trong service. | Trả Publisher cho framework và hủy subscription nguồn khi channel kết thúc. |
| Channel bị đóng khi input vừa hoàn tất | Ứng dụng nhầm hoàn tất một chiều là kết thúc toàn bộ channel. | Mô hình hóa trạng thái hai chiều và chỉ cleanup khi toàn channel kết thúc. |
| Event bị đảo thứ tự | Dùng xử lý song song hoặc merge nhiều nguồn mà không có sequence. | Dùng concatMap, sequence number hoặc bộ điều phối tuần tự. |
| Bộ nhớ tăng theo số channel | Buffer không giới hạn hoặc channel không có quota. | Giới hạn queue, số channel, tuổi channel và chính sách quá tải. |
| Đóng một channel làm hỏng channel khác | Đóng tài nguyên dùng chung thay vì tài nguyên riêng. | Xác định ownership và chỉ release handle do channel sở hữu. |
| Channel bị timeout khi không có event | Timeout được áp dụng cho toàn stream dù im lặng là hợp lệ. | Dùng heartbeat hoặc idle policy theo nghiệp vụ. |
| Command bị xử lý lặp sau reconnect | Không có command ID hoặc checkpoint nghiệp vụ. | Dùng idempotency key, sequence number và deduplication. |

## 15. Ghi nhớ

- Request-channel trao đổi hai luồng: requester gửi nhiều phần tử và responder cũng trả nhiều phần tử.
- Hai chiều có thể hoàn tất độc lập; hoàn tất input không nhất thiết kết thúc output.
- Trạng thái channel phải tách biệt trạng thái connection và các channel khác trên cùng connection.
- Tài nguyên riêng như listener, timer, buffer và context phải được gắn với vòng đời Publisher và giải phóng khi complete, error hoặc cancel.
- Dùng <code>Flux.defer</code>, <code>doFinally</code> hoặc <code>usingWhen</code> để quản lý việc tạo và cleanup tài nguyên.
- Backpressure tồn tại ở cả hai chiều, nhưng ứng dụng vẫn cần quota, buffer có giới hạn, timeout và concurrency limit.
- Reconnect không tự khôi phục state nghiệp vụ; dùng channel ID, checkpoint, sequence number và idempotency khi cần tiếp tục an toàn.
- Kiểm thử cả dữ liệu hai chiều, half-close, cancellation, lỗi, connection loss và cleanup tài nguyên.
