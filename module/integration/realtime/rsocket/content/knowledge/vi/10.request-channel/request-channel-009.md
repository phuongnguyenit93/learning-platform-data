# Thực hành hội thoại hoặc điều khiển thiết bị theo thời gian thực

RSocket **request-channel** phù hợp khi hai bên cần trao đổi nhiều thông điệp trên cùng một interaction. Requester có thể gửi liên tục lệnh hoặc dữ liệu; đồng thời responder có thể gửi nhiều phản hồi, tiến độ và sự kiện trở lại. Hai hướng truyền có vòng đời và demand riêng, nên client và server có thể vừa gửi vừa nhận mà không phải mở một request mới cho từng thông điệp.

Bài học này dùng tình huống điều khiển thiết bị làm ví dụ chính: client gửi lệnh thay đổi chế độ, đặt mục tiêu hoặc dừng thiết bị; server trả acknowledgement, tiến độ thực hiện và trạng thái thiết bị. Mẫu tương tự áp dụng cho hội thoại realtime, nơi client gửi nhiều tin nhắn và server phát nhiều phần phản hồi hoặc token.

Trong Java, Spring RSocket ánh xạ đầu vào của channel thành Flux<Request> và đầu ra thành Flux<Response>. Sau bài học, bạn có thể:

- Giải thích cách request-channel duy trì hai luồng dữ liệu hai chiều.
- Phân biệt channel với request-response và request-stream.
- Triển khai handler nhận Flux lệnh và trả Flux sự kiện.
- Tạo requester gửi nhiều lệnh và nhận nhiều phản hồi đồng thời.
- Quản lý demand, backpressure, completion, error và cancellation ở cả hai hướng.
- Thiết kế correlation ID, thứ tự xử lý, idempotency và kiểm thử channel.

## 1. Khi nào cần request-channel?

Một tương tác thông thường có thể chỉ cần một request và một response, ví dụ truy vấn thông tin thiết bị. Nếu server cần phát nhiều cập nhật sau request ban đầu, request-stream phù hợp hơn. Nhưng có những ứng dụng cần gửi dữ liệu liên tục theo cả hai chiều:

- Bảng điều khiển gửi lệnh đến thiết bị và nhận trạng thái thực thi.
- Ứng dụng hội thoại gửi tin nhắn trong khi nhận câu trả lời dạng stream.
- Client gửi dữ liệu cảm biến đã xử lý và nhận cảnh báo hoặc lệnh điều chỉnh.
- Công cụ điều khiển từ xa gửi thao tác bàn phím/chuột và nhận trạng thái màn hình.
- Phiên cộng tác gửi thao tác chỉnh sửa và nhận thay đổi từ những người tham gia khác.

Request-channel mở một interaction với một luồng request từ requester đến responder và một luồng response từ responder về requester. Cả hai phía có thể tiếp tục gửi payload trong khi channel còn hoạt động.

~~~mermaid
sequenceDiagram
    participant C as Client / Requester
    participant S as Server / Responder
    C->>S: REQUEST_CHANNEL (lệnh đầu tiên + initial response demand)
    S->>C: REQUEST_N (cấp demand cho luồng lệnh tiếp theo)
    par Client gửi lệnh
        C-->>S: PAYLOAD command-2
        C-->>S: PAYLOAD command-3
    and Server gửi sự kiện
        S-->>C: PAYLOAD accepted
        S-->>C: PAYLOAD progress
        S-->>C: PAYLOAD device-status
    end
    C->>S: PAYLOAD COMPLETE (hết lệnh)
    S-->>C: PAYLOAD COMPLETE (hết sự kiện)
~~~

Không có quy tắc bắt buộc mỗi request payload phải tạo đúng một response payload. Một lệnh có thể tạo nhiều sự kiện tiến độ; nhiều lệnh có thể được tổng hợp thành một trạng thái; server cũng có thể gửi sự kiện độc lập với lệnh đang xử lý. Nếu cần ghép kết quả với một lệnh cụ thể, hãy dùng commandId hoặc correlationId trong schema ứng dụng.

## 2. Request-channel hoạt động như thế nào?

Khi requester bắt đầu channel, nó gửi REQUEST_CHANNEL frame chứa payload đầu tiên và initial request N cho hướng response. Giá trị initial request N phải lớn hơn 0. Sau đó, hai bên có thể gửi thêm payload và yêu cầu thêm demand.

| Thành phần | Hướng | Ý nghĩa |
|---|---|---|
| REQUEST_CHANNEL | Requester → Responder | Mở channel, mang payload đầu tiên và initial response demand |
| PAYLOAD với NEXT | Cả hai hướng | Gửi thêm một payload trong luồng của bên gửi |
| REQUEST_N | Cả hai hướng | Yêu cầu bên kia phát thêm số lượng payload tương ứng |
| PAYLOAD với COMPLETE | Cả hai hướng | Đóng luồng gửi payload của bên gửi |
| ERROR | Cả hai hướng | Kết thúc interaction do lỗi |
| CANCEL | Requester → Responder | Hủy channel từ phía requester |

Một số điểm quan trọng:

- REQUEST_CHANNEL mở interaction và mang payload đầu tiên từ requester.
- Các payload tiếp theo từ requester đi trong PAYLOAD frame.
- Responder phát các response payload theo demand của requester.
- Responder phải gửi REQUEST_N để cấp demand ban đầu cho các request payload tiếp theo; sau đó có thể yêu cầu thêm bằng các REQUEST_N khác.
- Requester không gửi PAYLOAD tiếp theo trước khi nhận demand tương ứng từ responder.
- Khi requester hoàn tất luồng gửi, responder vẫn có thể phát các response còn lại hoặc tiếp tục phát sự kiện nếu nguồn response vẫn hoạt động.
- Khi responder hoàn tất luồng response, requester có thể đã hoàn tất luồng gửi hoặc vẫn còn dữ liệu cần gửi; hai hướng kết thúc độc lập.

Requester có thể đánh dấu hướng gửi đã hoàn tất ngay trên REQUEST_CHANNEL đầu tiên hoặc trên PAYLOAD cuối cùng. Sau khi gửi cờ COMPLETE, requester không được gửi thêm payload trên hướng đó.

**Hoàn tất một hướng không đồng nghĩa channel đã đóng hoàn toàn.** Ví dụ, client gửi xong các lệnh khởi tạo nhưng vẫn muốn nhận trạng thái thiết bị; server có thể tiếp tục phát event cho đến khi phiên kết thúc. Ngược lại, server có thể ngừng phát response trong khi client vẫn gửi dữ liệu theo hợp đồng đã thiết kế.

## 3. Phân biệt request-channel với các interaction khác

| Mô hình | Dữ liệu requester gửi | Dữ liệu responder gửi | Khi phù hợp |
|---|---|---|---|
| Request-response | Một request | Tối đa một response | Truy vấn hoặc lệnh có một kết quả |
| Request-stream | Một request | Không hoặc nhiều response | Client đăng ký nhận feed |
| Fire-and-forget | Một request | Không có response payload | Gửi sự kiện không cần phản hồi |
| Request-channel | Không hoặc nhiều request payload | Không hoặc nhiều response payload | Hai bên trao đổi liên tục |

Request-channel không chỉ là request-stream cộng với nhiều request riêng lẻ. Hai hướng truyền thuộc cùng một interaction, có thể cùng hoạt động và có flow control riêng. Điều này đặc biệt hữu ích khi client cần gửi lệnh mới trong lúc vẫn nhận phản hồi cho những lệnh trước.

## 4. Thiết kế hợp đồng cho phiên điều khiển thiết bị

Trước khi viết handler, hãy xác định schema của thông điệp. Với ví dụ điều khiển thiết bị, có thể dùng các loại dữ liệu sau:

~~~java
public record DeviceCommand(
    String commandId,
    String type,
    String value,
    long sequence
) {}

public record DeviceEvent(
    String eventId,
    String commandId,
    String type,
    String status,
    String detail,
    Instant occurredAt
) {}
~~~

Một số loại command có thể là:

| Command | Ví dụ dữ liệu | Ý nghĩa |
|---|---|---|
| SET_TARGET | temperature = 22 | Đặt mục tiêu thiết bị |
| SET_MODE | mode = ECO | Chuyển chế độ |
| STOP | reason = user-request | Yêu cầu dừng hoạt động |
| QUERY_STATUS | không cần value | Yêu cầu trạng thái hiện tại |

Server có thể trả các loại event:

| Event | Ý nghĩa |
|---|---|
| ACCEPTED | Đã nhận và chấp nhận lệnh |
| PROGRESS | Lệnh đang được thực hiện |
| COMPLETED | Lệnh đã hoàn tất |
| REJECTED | Lệnh bị từ chối theo quy tắc nghiệp vụ |
| DEVICE_STATUS | Trạng thái thiết bị thay đổi |
| WARNING | Thiết bị hoặc tiến trình phát cảnh báo |

commandId cho phép client ghép ACCEPTED, PROGRESS và COMPLETED với đúng lệnh. sequence giúp phát hiện lệnh đến trùng hoặc sai thứ tự nếu nghiệp vụ yêu cầu thứ tự. eventId giúp client loại bỏ event trùng khi ứng dụng có cơ chế retry hoặc phục hồi.

Không nên dùng vị trí phần tử trong Flux làm định danh. Khi hai luồng xử lý đồng thời, event có thể xen kẽ; ID tường minh giúp client hiểu đúng quan hệ giữa lệnh và kết quả.

## 5. Triển khai responder với Spring RSocket

Spring ánh xạ request-channel vào method có đầu vào Flux và đầu ra Flux. Ví dụ sau nhận nhiều lệnh và phát các event xử lý tương ứng:

~~~java
@Controller
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.control")
    public Flux<DeviceEvent> control(
            Flux<DeviceCommand> commands,
            @Header("deviceId") String deviceId) {

        return commands.concatMap(command ->
            deviceService.execute(deviceId, command)
                .map(progress -> DeviceEventMapper.progress(
                    command.commandId(),
                    progress
                ))
                .concatWith(Mono.just(
                    DeviceEventMapper.completed(command.commandId())
                ))
                .onErrorResume(
                    CommandRejectedException.class,
                    error -> Flux.just(
                        DeviceEventMapper.rejected(
                            command.commandId(),
                            error.getMessage()
                        )
                    )
                )
        );
    }
}
~~~

Trong ví dụ này:

- commands là luồng payload client gửi lên.
- concatMap xử lý lần lượt từng lệnh và giữ thứ tự bắt đầu xử lý.
- deviceService.execute có thể phát nhiều tiến độ cho một command.
- Sau khi tiến độ hoàn tất, server phát event COMPLETED.
- Lỗi nghiệp vụ có thể được chuyển thành REJECTED event để channel tiếp tục xử lý các lệnh tiếp theo.
- Lỗi hạ tầng hoặc lỗi không được xử lý vẫn có thể kết thúc channel bằng onError.

Để ví dụ hoạt động, ứng dụng cần có MetadataExtractor trích xuất metadata MIME type của device ID thành header deviceId. Có thể dùng route có chứa định danh phiên hoặc lấy device ID từ principal đã xác thực. Không lấy ID do client gửi làm cơ sở phân quyền mà chưa kiểm tra quyền truy cập.

Đây là handler cơ bản, trong đó response được tạo từ các command đầu vào. Phần tiếp theo mở rộng cùng handler để phát thêm trạng thái thiết bị độc lập với command.

### Phát trạng thái độc lập với lệnh

Một bảng điều khiển thường cần nhận trạng thái thiết bị ngay cả khi người dùng chưa gửi lệnh mới. Có thể kết hợp luồng acknowledgement với luồng trạng thái:

~~~java
@MessageMapping("devices.control")
public Flux<DeviceEvent> control(
        Flux<DeviceCommand> commands,
        @Header("deviceId") String deviceId) {

    Flux<DeviceEvent> commandEvents =
        commands.concatMap(command ->
            deviceService.execute(deviceId, command)
                .map(progress -> DeviceEventMapper.progress(
                    command.commandId(),
                    progress
                ))
                .concatWith(Mono.just(
                    DeviceEventMapper.completed(command.commandId())
                ))
                .onErrorResume(
                    CommandRejectedException.class,
                    error -> Flux.just(
                        DeviceEventMapper.rejected(
                            command.commandId(),
                            error.getMessage()
                        )
                    )
                )
        );

    Flux<DeviceEvent> statusEvents =
        deviceService.watchStatus(deviceId);

    return Flux.merge(commandEvents, statusEvents);
}
~~~

Đây là phiên bản mở rộng thay cho method cơ bản phía trên; không khai báo đồng thời hai method cùng route trong một controller.

Flux.merge cho phép event từ hai nguồn xen kẽ. Vì vậy, client không được giả định toàn bộ acknowledgement luôn đứng trước mọi status event. Dùng commandId, eventId và timestamp để ghép dữ liệu. Nếu thứ tự nghiệp vụ là bắt buộc, hãy tuần tự hóa nguồn tương ứng hoặc dùng sequence number và quy tắc sắp xếp rõ ràng.

Trong phiên điều khiển, statusEvents có thể là nguồn liên tục. Khi client hủy channel, subscription của các nguồn response cần được hủy và tài nguyên theo dõi thiết bị cần được giải phóng.

## 6. Gửi channel từ client bằng RSocketRequester

Ở phía requester, truyền một Publisher làm data đầu vào và dùng retrieveFlux để nhận luồng response.

~~~java
Flux<DeviceCommand> commands = Flux.just(
    new DeviceCommand("cmd-101", "SET_MODE", "ECO", 1),
    new DeviceCommand("cmd-102", "SET_TARGET", "22", 2),
    new DeviceCommand("cmd-103", "QUERY_STATUS", null, 3)
);

Flux<DeviceEvent> events = requester
    .route("devices.control")
    .metadata("device-42", DEVICE_ID_MIME_TYPE)
    .data(commands)
    .retrieveFlux(DeviceEvent.class);
~~~

data(commands) cho Spring biết request data là một publisher. Spring ánh xạ nó thành request-channel; các phần tử của publisher được gửi theo thứ tự và response được giải mã thành Flux<DeviceEvent>.

REQUEST_CHANNEL frame cần payload đầu tiên để mở interaction. Vì vậy, publisher đầu vào phải phát ít nhất một phần tử. Nếu phiên cần mở trước khi có command nghiệp vụ, hãy định nghĩa một message mở phiên như OpenDeviceSession thay vì gửi một Flux rỗng.

Ví dụ trên dùng luồng lệnh hữu hạn. Khi ba lệnh được gửi xong, phía client hoàn tất hướng request. Client vẫn có thể nhận những response còn lại hoặc status event từ server cho đến khi phía response hoàn tất hoặc client hủy subscription.

Với nguồn lệnh liên tục, có thể dùng publisher lấy dữ liệu từ UI hoặc command bus:

~~~java
Flux<DeviceCommand> commands = commandBus.commandsFor("device-42");

Flux<DeviceEvent> events = requester
    .route("devices.control")
    .metadata("device-42", DEVICE_ID_MIME_TYPE)
    .data(commands)
    .retrieveFlux(DeviceEvent.class);
~~~

Nếu command bus là hot source, cần xác định cách nó xử lý demand và subscriber mới. Không dùng một hàng đợi vô hạn để đệm lệnh khi thiết bị xử lý chậm.

Nếu giao diện cần nhận status ngay khi chưa có command nghiệp vụ, hãy phát message mở phiên làm payload đầu tiên rồi mới nối command bus:

~~~java
Flux<DeviceCommand> commands = Flux.concat(
    Mono.just(new DeviceCommand(
        "session-1", "OPEN_SESSION", "device-42", 0
    )),
    commandBus.commandsFor("device-42")
);
~~~

Server xử lý OPEN_SESSION để xác thực quyền và chuẩn bị nguồn status. Sau đó channel vẫn nhận các command mới trong khi client nhận status event.

### Đăng ký metadata thiết bị

Ví dụ này dùng metadata text/plain để truyền device ID; Spring có codec chuỗi cho MIME type này. Nếu ứng dụng chọn MIME type tùy chỉnh, cả hai phía phải đăng ký encoder và decoder tương ứng:

~~~java
private static final MimeType DEVICE_ID_MIME_TYPE =
    MimeTypeUtils.TEXT_PLAIN;

RSocketStrategies strategies = RSocketStrategies.builder()
    .metadataExtractorRegistry(registry ->
        registry.metadataToExtract(
            MimeTypeUtils.TEXT_PLAIN,
            String.class,
            "deviceId"
        )
    )
    .build();
~~~

Requester cần dùng RSocketStrategies có encoder phù hợp cho chuỗi metadata; responder dùng decoder và MetadataExtractor tương ứng. Nếu metadata được gửi qua Composite Metadata, cấu hình metadata MIME type của kết nối phải phù hợp ở cả hai phía.

Khi tạo requester, gắn strategies và khai báo Composite Metadata cho kết nối, ví dụ:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"
    ))
    .tcp("localhost", 7000);
~~~

## 7. Thực hành hội thoại realtime

Cùng mô hình channel có thể dùng cho hội thoại. Client gửi nhiều tin nhắn trong một phiên; server có thể phát nhiều token, trạng thái hoặc event cho từng tin nhắn.

~~~java
public record ChatMessage(
    String conversationId,
    String messageId,
    String text
) {}

public record ChatEvent(
    String conversationId,
    String messageId,
    String type,
    String content
) {}
~~~

Handler:

~~~java
@MessageMapping("chat.conversation")
public Flux<ChatEvent> converse(Flux<ChatMessage> messages) {
    return messages.concatMap(message ->
        chatService.respond(message)
            .map(token -> new ChatEvent(
                message.conversationId(),
                message.messageId(),
                "TOKEN",
                token
            ))
            .concatWith(Mono.just(new ChatEvent(
                message.conversationId(),
                message.messageId(),
                "MESSAGE_COMPLETED",
                ""
            )))
    );
}
~~~

Một tin nhắn có thể tạo ra nhiều TOKEN event rồi một MESSAGE_COMPLETED event. Client có thể gửi tin nhắn tiếp theo trong cùng channel theo chính sách ứng dụng. concatMap đảm bảo server xử lý tuần tự; nếu muốn xử lý nhiều câu trả lời đồng thời, có thể dùng flatMap với giới hạn concurrency, nhưng event sẽ có thể xen kẽ. Khi đó messageId là bắt buộc để ghép token với đúng câu hỏi.

Nếu client cần nhận event từ server ngay cả khi không có tin nhắn mới, hãy kết hợp luồng xử lý message với luồng notification của hội thoại. Cũng như ví dụ thiết bị, phải xác định rõ ai sở hữu session và điều kiện kết thúc notification stream.

## 8. Backpressure ở cả hai hướng

Request-channel có hai luồng dữ liệu, vì vậy demand được điều tiết độc lập ở từng hướng:

- Requester yêu cầu responder gửi thêm response bằng initial request N trong REQUEST_CHANNEL và các REQUEST_N tiếp theo.
- Responder phải gửi REQUEST_N để cấp demand ban đầu cho luồng request từ requester; các REQUEST_N tiếp theo điều chỉnh demand theo hướng ngược lại.
- Mỗi bên chỉ nên phát số payload tương ứng với demand mà bên nhận đã cấp.
- Spring và RSocket Java chuyển demand của Reactive Streams thành flow control của giao thức.

Requester chỉ được gửi các PAYLOAD tiếp theo sau khi responder cấp demand. Initial request N trong REQUEST_CHANNEL điều khiển số response mà requester muốn nhận; REQUEST_N đầu tiên do responder gửi điều khiển số request payload mà responder sẵn sàng nhận. Đây là hai bộ đếm demand độc lập.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: REQUEST_CHANNEL (response demand = 4)
    S->>C: REQUEST_N (request demand = 2)
    C-->>S: command-1
    C-->>S: command-2
    S-->>C: accepted-1
    S-->>C: progress-1
    S-->>C: accepted-2
    S-->>C: status-update
    C->>S: REQUEST_N (request demand = 3)
    S->>C: REQUEST_N (response demand = 2)
~~~

Điều này không có nghĩa hai bên phải gửi cùng số lượng phần tử. Client có thể gửi mười command trong khi server phát hàng trăm status event. Mỗi hướng có nhu cầu riêng.

### Khi nguồn không hỗ trợ backpressure

Một thiết bị hoặc broker có thể đẩy sự kiện độc lập với tốc độ consumer. Khi đó cần chiến lược bảo vệ bộ nhớ và tính đúng đắn:

| Chiến lược | Cách xử lý | Trường hợp phù hợp |
|---|---|---|
| Buffer giới hạn | Đệm tối đa N phần tử rồi áp dụng chính sách khi đầy | Event có thể chờ ngắn hạn |
| Drop | Bỏ phần tử theo quy tắc | Telemetry có thể mất mẫu |
| Latest | Giữ trạng thái mới nhất | UI chỉ cần giá trị hiện tại |
| Throttle/sample | Giảm tần suất event | Cập nhật cảm biến quá dày |
| Persist | Lưu bền vững và đọc theo offset | Lệnh hoặc event không được phép mất |
| Reject/close | Từ chối tải mới hoặc đóng channel | Quá tải vượt khả năng an toàn |

Với lệnh điều khiển, không nên tùy tiện drop command. Nếu client gửi quá nhanh, có thể giới hạn số lệnh đang chờ, trả event REJECTED/OVERLOADED hoặc tạm dừng nguồn phát lệnh. Với status telemetry, có thể dùng latest hoặc sample nếu nghiệp vụ chỉ cần trạng thái gần nhất.

## 9. Completion và cancellation của channel

Hai hướng của channel có thể hoàn tất độc lập.

**Client hoàn tất luồng lệnh:** Publisher truyền vào data(commands) phát hết phần tử và gọi onComplete. Framework báo completion cho hướng gửi request. Server không nhận thêm command mới từ hướng này, nhưng response stream vẫn có thể phát tiến độ cuối cùng hoặc status event.

**Server hoàn tất luồng response:** Flux trả về từ handler gọi onComplete. Client không nhận thêm response event, nhưng điều này không đồng nghĩa mọi command đã được xử lý thành công trừ khi hợp đồng ứng dụng quy định rõ.

Channel kết thúc bình thường sau khi cả requester và responder đều đã hoàn tất hướng gửi của mình. Nếu một bên phát ERROR hoặc requester gửi CANCEL, interaction kết thúc theo tín hiệu terminal đó.

**Client hủy channel:** Khi client không còn cần kết quả, hủy subscription của retrieveFlux. Việc hủy được truyền qua CANCEL khi interaction còn hoạt động. Server cần hủy các nguồn đang theo dõi, dừng công việc có thể dừng và giải phóng tài nguyên.

~~~java
Flux<DeviceEvent> events = requester
    .route("devices.control")
    .metadata("device-42", DEVICE_ID_MIME_TYPE)
    .data(commandBus.commandsFor("device-42"))
    .retrieveFlux(DeviceEvent.class);

Disposable session = events.subscribe(this::handleDeviceEvent);

// Khi người dùng đóng màn hình điều khiển:
session.dispose();
~~~

Trong ứng dụng reactive, có thể quản lý subscription bằng lifecycle của UI hoặc service. Tránh tạo subscription không có nơi quản lý vì channel liên tục có thể giữ socket, buffer và listener lâu hơn dự kiến.

Ở phía server, dùng doFinally để quan sát COMPLETE, ERROR và CANCEL. Nếu cần đóng tài nguyên bất đồng bộ, dùng usingWhen hoặc cơ chế cleanup của nguồn dữ liệu để bảo đảm cleanup cũng chạy khi bị hủy.

## 10. Lỗi trong một hướng ảnh hưởng đến channel

Lỗi terminal trong luồng request hoặc response có thể kết thúc interaction. Hãy phân biệt lỗi của một command với lỗi khiến toàn bộ phiên không thể tiếp tục.

Ví dụ, lệnh không hợp lệ có thể được biểu diễn thành REJECTED event để channel vẫn hoạt động:

~~~java
commands.concatMap(command ->
    deviceService.execute(deviceId, command)
        .map(progress -> DeviceEventMapper.progress(
            command.commandId(),
            progress
        ))
        .onErrorResume(
            CommandRejectedException.class,
            error -> Flux.just(
                DeviceEventMapper.rejected(
                    command.commandId(),
                    error.getMessage()
                )
            )
        )
);
~~~

Nếu thiết bị mất kết nối hoặc session không còn hợp lệ, tiếp tục giữ channel có thể không có ý nghĩa. Server nên phát lỗi phù hợp để kết thúc interaction. Client có thể tạo channel mới sau khi xác định trạng thái thiết bị và chính sách phục hồi.

Không nên biến mọi lỗi thành REJECTED. Lỗi validation của một command có thể không ảnh hưởng các command khác; lỗi hạ tầng hoặc lỗi giao thức có thể khiến toàn bộ channel không còn đáng tin cậy.

## 11. Thứ tự, correlation và idempotency

Trong channel, nhiều command và event có thể xen kẽ. Thiết kế schema nên hỗ trợ ghép cặp và phát hiện trùng:

- commandId: định danh duy nhất của lệnh.
- correlationId: định danh phiên hoặc chuỗi thao tác liên quan.
- sequence: số thứ tự do client cấp trong một phiên nếu cần phát hiện lệnh đến sai thứ tự.
- eventId: định danh event để loại bỏ bản sao.
- occurredAt: thời điểm event được tạo, dùng để hiển thị hoặc phân tích.

Dùng concatMap khi lệnh cần thực thi tuần tự, ví dụ di chuyển thiết bị theo từng bước. Dùng flatMap có giới hạn khi các lệnh độc lập có thể chạy song song. Nếu dùng flatMap, đừng giả định response đến theo thứ tự lệnh gửi.

Với lệnh có tác dụng phụ, hãy hỗ trợ idempotency. Nếu client mất kết nối sau khi gửi lệnh nhưng trước khi nhận acknowledgement, client có thể không biết lệnh đã được thực hiện hay chưa. Khi gửi lại cùng commandId, server nên tra kết quả đã lưu và tránh thực hiện lặp tác dụng phụ.

Đối với thiết bị vật lý, cần xác thực quyền trên từng command và giới hạn những thao tác nguy hiểm theo trạng thái thiết bị. Không xem việc mở được channel là bằng chứng rằng client có quyền điều khiển mọi thiết bị.

## 12. Bảo mật phiên điều khiển

Một channel có thể tồn tại lâu và mang nhiều command, vì vậy bảo mật cần được áp dụng xuyên suốt session:

1. Xác thực requester khi thiết lập kết nối hoặc theo cơ chế bảo mật đã cấu hình.
2. Ràng buộc deviceId với principal/tenant đã xác thực.
3. Kiểm tra quyền cho từng loại command.
4. Kiểm tra miền giá trị, tốc độ và trạng thái hiện tại của thiết bị.
5. Giới hạn số channel và số command đang chờ trên mỗi principal.
6. Không ghi credential hoặc dữ liệu nhạy cảm vào log.
7. Dùng TLS cho TCP hoặc WSS khi dữ liệu đi qua mạng không tin cậy.

Nếu quyền của người dùng bị thu hồi trong khi channel vẫn mở, ứng dụng cần chính sách kết thúc session hoặc kiểm tra lại quyền theo từng command. Không nên giả định quyền lúc mở channel luôn hợp lệ cho toàn bộ vòng đời dài của channel.

## 13. Kiểm thử request-channel

Kiểm thử handler có thể dùng Flux đầu vào hữu hạn và xác minh nhiều event đầu ra:

~~~java
@Test
void processesCommandsAndEmitsEvents() {
    Flux<DeviceCommand> commands = Flux.just(
        new DeviceCommand("cmd-1", "SET_MODE", "ECO", 1),
        new DeviceCommand("cmd-2", "QUERY_STATUS", null, 2)
    );

    Flux<DeviceEvent> events =
        deviceController.control(commands, "device-42");

    StepVerifier.create(events)
        .expectNextMatches(event ->
            event.commandId().equals("cmd-1")
                && event.type().equals("PROGRESS")
        )
        .expectNextMatches(event ->
            event.commandId().equals("cmd-1")
                && event.type().equals("COMPLETED")
        )
        .expectNextMatches(event ->
            event.commandId().equals("cmd-2")
                && event.type().equals("PROGRESS")
        )
        .expectNextMatches(event ->
            event.commandId().equals("cmd-2")
                && event.type().equals("COMPLETED")
        )
        .verifyComplete();
}
~~~

Ví dụ này giả định deviceService.execute phát đúng một tiến độ cho mỗi command và các mapper tạo event tương ứng. Trong test thực tế, hãy cấu hình service mock theo số tiến độ mà bạn muốn xác minh; nếu service phát nhiều tiến độ, thêm các kỳ vọng tương ứng trước event COMPLETED.

Kiểm tra backpressure ở publisher đầu ra:

~~~java
@Test
void respectsSubscriberDemand() {
    Flux<Integer> events = Flux.range(1, 3);

    StepVerifier.create(events, 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(2)
        .expectNext(2, 3)
        .verifyComplete();
}
~~~

Kiểm tra hủy subscription:

~~~java
@Test
void cancellationReachesChannelSource() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<DeviceEvent> events = Flux.<DeviceEvent>never()
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(events)
        .thenCancel()
        .verify();

    assertThat(cancelled).isTrue();
}
~~~

Kiểm thử tích hợp nên chạy requester và responder qua transport thực tế, rồi xác nhận:

- Client gửi nhiều command trong một channel.
- Server phát nhiều event cho một command.
- Server phát status event độc lập khi client không gửi command mới.
- Hai hướng có thể kết thúc ở những thời điểm khác nhau.
- Backpressure được giữ ở cả hai hướng.
- Client cancel làm server cleanup nguồn theo dõi.
- Lỗi command riêng lẻ được chuyển thành event nếu hợp đồng cho phép.
- Lỗi session kết thúc channel và client phục hồi theo cursor/commandId.
- Event xen kẽ vẫn được ghép đúng bằng ID.

## 14. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Client chỉ nhận một response | Server trả Mono thay vì Flux hoặc nguồn hoàn tất sớm | Trả Flux và kiểm tra vòng đời publisher |
| Server chỉ nhận một command | Client truyền một object thay vì Publisher vào data | Dùng data(commands) với Flux |
| Không nhận status khi client ngừng gửi | Response chỉ được tạo từ command đầu vào | Kết hợp luồng status độc lập nếu nghiệp vụ cần |
| Event đến sai thứ tự | Dùng flatMap hoặc merge nhưng giả định thứ tự | Dùng concatMap hoặc sequence/correlation |
| Channel không đóng | Một trong hai publisher không hoàn tất | Định nghĩa điều kiện completion hoặc cancel |
| Tài nguyên vẫn bị giữ sau khi client rời đi | Nguồn không cleanup khi cancel | Dùng doFinally/usingWhen và kiểm thử |
| Mất command khi quá tải | Buffer/drop không phù hợp với lệnh | Giới hạn demand, persist hoặc reject rõ ràng |
| Lệnh bị thực thi hai lần sau reconnect | Không có idempotency key | Dùng commandId và lưu kết quả xử lý |
| Client ghép nhầm response | Giả định một command chỉ có một response | Dùng commandId và eventId |

## 15. Quy trình thiết kế một channel thực tế

Khi triển khai điều khiển thiết bị hoặc hội thoại realtime, hãy xác định:

1. Schema của request và response gồm những trường nào?
2. Một request có thể tạo nhiều response hay không?
3. Có event server-initiated độc lập với request không?
4. Hai hướng hoàn tất theo điều kiện nào?
5. Ai có quyền hủy channel và tài nguyên nào cần cleanup?
6. Mỗi hướng xử lý demand và nguồn không hỗ trợ backpressure ra sao?
7. Lệnh có cần tuần tự hóa, sequence number hoặc idempotency key không?
8. Lỗi nào chỉ ảnh hưởng một command, lỗi nào kết thúc cả session?
9. Client phục hồi từ đâu sau mất kết nối?
10. Quyền điều khiển được xác minh ở thời điểm nào trong vòng đời channel?

Request-channel giúp hai bên duy trì một phiên trao đổi nhiều thông điệp theo cả hai hướng. Khi hợp đồng định nghĩa rõ schema, thứ tự, demand, completion, cancellation và quyền truy cập, mô hình này phù hợp cho hội thoại realtime, điều khiển thiết bị và các ứng dụng cộng tác tương tác liên tục.

## Ghi nhớ

- Request-channel mở một interaction với luồng request và luồng response hai chiều.
- Hai hướng có demand và điều kiện hoàn tất riêng.
- Spring biểu diễn đầu vào bằng Flux<Request> và đầu ra bằng Flux<Response>.
- Không có quy tắc một command phải tương ứng đúng một event.
- Dùng concatMap để giữ thứ tự; dùng flatMap có giới hạn khi xử lý song song và luôn mang correlation ID.
- Completion của một hướng không nhất thiết đóng hướng còn lại.
- CANCEL cần dẫn đến cleanup của nguồn và tài nguyên.
- Backpressure, idempotency, bảo mật và phục hồi phải được thiết kế cho toàn bộ vòng đời channel.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Protocol: Request-Channel](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Framework: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm)

