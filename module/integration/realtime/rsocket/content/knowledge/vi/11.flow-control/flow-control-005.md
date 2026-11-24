# Điều tiết hai chiều trong request-channel

## Bối cảnh: cả hai phía đều có thể phát dữ liệu

RSocket hỗ trợ request-channel để client và server trao đổi nhiều payload theo cả hai hướng trong cùng một interaction. Ví dụ, ứng dụng điều khiển robot gửi lệnh di chuyển liên tục trong khi server trả trạng thái vị trí; client gửi yêu cầu theo dõi thiết bị và server phát cảnh báo; hoặc một phiên cộng tác realtime trao đổi thao tác từ cả hai phía.

Khi cả hai bên cùng phát dữ liệu, mỗi bên vừa là producer vừa là consumer. Client có thể gửi command nhanh hơn server xử lý; đồng thời server có thể phát event nhanh hơn client hiển thị hoặc lưu trữ. Nếu chỉ điều tiết một hướng, hướng còn lại vẫn có thể tích tụ dữ liệu và làm tăng độ trễ hoặc bộ nhớ.

RSocket xử lý tình huống này bằng cách quản lý nhu cầu nhận dữ liệu độc lập ở từng hướng:

- **Client cấp demand cho payload server gửi về** bằng initialN trong frame mở REQUEST_CHANNEL và các frame REQUEST_N tiếp theo.
- **Server cấp demand cho payload client gửi tiếp** bằng cách gửi REQUEST_N theo chiều ngược lại.
- Mỗi payload được gửi theo một hướng tiêu thụ một đơn vị credit đã được cấp cho hướng đó.
- Khi một phía không còn gửi dữ liệu, phía đó có thể hoàn tất hướng gửi bằng flag COMPLETE; requester có thể hủy toàn bộ interaction bằng CANCEL.

Điều tiết hai chiều giúp phối hợp tốc độ phát và tốc độ tiêu thụ ở cả client lẫn server. Để sử dụng đúng, cần xác định rõ ai đang yêu cầu dữ liệu từ ai, credit thuộc hướng nào và khi nào một hướng hoặc toàn bộ channel kết thúc.

## 1. Request-channel có hai luồng dữ liệu độc lập

Trong request-channel, client mở interaction bằng frame REQUEST_CHANNEL. Frame này chứa payload request đầu tiên và initialN, tức số payload response mà client sẵn sàng nhận từ server ở thời điểm bắt đầu.

Sau khi channel được mở:

- Client gửi các payload tiếp theo theo demand mà server cấp.
- Server gửi các payload response theo demand mà client cấp.
- Mỗi hướng có bộ đếm credit riêng.
- Hai hướng có thể hoạt động đồng thời, hoặc một hướng tạm dừng trong khi hướng còn lại vẫn tiếp tục.

Có thể mô hình hóa channel như hai luồng một chiều chạy song song:

~~~mermaid
flowchart TB
    subgraph Up["Client → Server"]
        C1["Client producer<br/>Command / Input"] -->|PAYLOAD| S1["Server consumer<br/>REQUEST_N do Server cấp"]
    end
    subgraph Down["Server → Client"]
        S2["Server producer<br/>Event / Result"] -->|PAYLOAD| C2["Client consumer<br/>initialN / REQUEST_N do Client cấp"]
    end
~~~

Điểm cần nhớ là REQUEST_N luôn được gửi từ bên muốn nhận thêm payload tới bên đang phát payload. Không có một bộ credit chung cho cả channel.

### Vai trò của initialN

initialN nằm trong frame REQUEST_CHANNEL do client khởi tạo. Nó cấp nhu cầu ban đầu cho hướng server → client. Ví dụ client đặt initialN = 5, server có thể phát tối đa năm payload response trước khi cần client cấp thêm demand.

Payload mở đầu của client được mang trực tiếp trong REQUEST_CHANNEL. Sau payload mở đầu, các payload client gửi tiếp phải tuân theo demand mà server cấp qua REQUEST_N.

### Vai trò của REQUEST_N trong channel

Sau khi channel mở, bên nhận có thể gửi REQUEST_N(N) để cấp thêm N payload cho peer gửi về. Trong request-channel, cả hai bên đều có thể gửi REQUEST_N, nhưng mỗi frame điều tiết hướng ngược lại với bên gửi frame:

| Frame được gửi bởi | Hướng payload được cấp thêm credit | Ý nghĩa |
|---|---|---|
| Client gửi REQUEST_N(N) | Server → Client | Client muốn nhận thêm N response/event |
| Server gửi REQUEST_N(N) | Client → Server | Server muốn nhận thêm N command/input |

REQUEST_N cấp thêm nhu cầu, không đặt lại tổng credit. Nếu client đã cấp 4 credit, server đã gửi 3 payload, sau đó client gửi REQUEST_N(2), server có thể gửi thêm tối đa 3 payload nữa trước khi cần demand tiếp theo.

## 2. Luồng điều tiết hai chiều

Giả sử client điều khiển một thiết bị. Client gửi command MOVE, SET_SPEED, STOP; server trả các event POSITION_CHANGED, SPEED_UPDATED và COMMAND_REJECTED.

Client mở channel với initialN = 2, nghĩa là client ban đầu sẵn sàng nhận hai event. Payload đầu tiên là command MOVE. Server nhận command này, sau đó cấp thêm ba credit để nhận các command tiếp theo. Khi client xử lý xong hai event đầu tiên, nó cấp thêm hai credit cho server.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: REQUEST_CHANNEL(initialN=2, MOVE)
    S->>C: REQUEST_N(N=3)
    S-->>C: PAYLOAD POSITION_CHANGED
    S-->>C: PAYLOAD COMMAND_ACCEPTED
    C->>S: PAYLOAD SET_SPEED
    C->>S: PAYLOAD STOP
    C->>S: REQUEST_N(N=2)
    S-->>C: PAYLOAD SPEED_UPDATED
    S-->>C: PAYLOAD STOPPED
~~~

Đọc luồng theo hai hướng:

1. Client cấp hai credit ban đầu cho server qua initialN.
2. Server gửi REQUEST_N(3) để client có thể gửi thêm ba command sau payload mở đầu.
3. Server phát tối đa hai event theo demand ban đầu của client.
4. Khi cần nhận thêm event, client gửi REQUEST_N(2).
5. Server có thể gửi thêm hai event; đồng thời hai bên vẫn quản lý credit độc lập ở hướng còn lại.

Một phía hết credit không làm channel tự động dừng. Nó chỉ phải chờ bên nhận cấp thêm demand ở hướng đó. Hướng ngược lại vẫn có thể tiếp tục nếu còn credit.

### Theo dõi credit riêng cho từng hướng

Có thể dùng bảng trạng thái để theo dõi ví dụ trên:

| Thời điểm | Credit Client → Server | Credit Server → Client |
|---|---:|---:|
| Mở channel | Payload mở đầu được gửi trong REQUEST_CHANNEL | 2 từ initialN |
| Server cấp thêm nhu cầu | 3 cho các command tiếp theo | 2 |
| Client gửi SET_SPEED | Còn 2 | 2 |
| Client gửi STOP | Còn 1 | 2 |
| Server gửi hai event | 1 | Còn 0 |
| Client gửi REQUEST_N(2) | 1 | Tăng lên 2 |

Các con số trong bảng chỉ minh họa một thời điểm trong luồng. Trong implementation thực tế, runtime quản lý demand và các frame; ứng dụng thường làm việc với Flux, Subscription và các toán tử Reactor thay vì tự duy trì bộ đếm.

## 3. Vì sao phải điều tiết độc lập hai hướng?

Tốc độ phát và khả năng tiêu thụ của client/server có thể khác nhau theo từng hướng. Ví dụ, một ứng dụng gửi lệnh với tốc độ 200 command/giây, trong khi server chỉ xử lý an toàn 50 command/giây. Server cần kiểm soát số command được gửi đến.

Ở chiều ngược lại, server có thể phát 1.000 event/giây trong khi client chỉ ghi được 300 event/giây. Client cần điều tiết số event server phát về.

Nếu chỉ điều tiết chiều client → server, server vẫn có thể làm quá tải client bằng response. Nếu chỉ điều tiết chiều server → client, client vẫn có thể gửi quá nhiều command làm quá tải server.

| Hướng | Producer | Consumer | Rủi ro khi không điều tiết | Bên cấp demand |
|---|---|---|---|---|
| Client → Server | Client | Server | Server quá tải, command queue tăng | Server |
| Server → Client | Server | Client | Client chậm, response buffer tăng | Client |

Flow control không có nghĩa hai phía phải phát cùng tốc độ. Nó giúp mỗi consumer thông báo khả năng tiếp nhận của mình, để producer điều chỉnh theo demand tương ứng.

### Backpressure không phải rate limit

REQUEST_N cấp số lượng payload mà peer được phép gửi theo nhu cầu. Nó không trực tiếp giới hạn số payload mỗi giây hoặc số byte mỗi giây.

Ví dụ, client cấp 100 credit. Server có thể gửi 100 payload rất nhanh nếu nguồn dữ liệu sẵn sàng. Nếu muốn giới hạn 100 command/giây, ứng dụng cần thêm rate limiter hoặc cơ chế điều tiết theo thời gian.

Tương tự, một payload có thể rất lớn. Flow control theo số payload không thay thế giới hạn kích thước payload, dung lượng buffer hoặc băng thông.

## 4. Điều gì xảy ra khi một hướng hết credit?

Giả sử server đã gửi hết số response mà client yêu cầu. Server phải dừng phát thêm payload theo hướng server → client cho đến khi nhận được REQUEST_N mới từ client.

Trong lúc đó, client vẫn có thể gửi command nếu server đã cấp đủ credit ở hướng client → server. Hai hướng độc lập nên channel không bị khóa toàn bộ chỉ vì một phía đang chờ demand.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: REQUEST_CHANNEL(initialN=1, START)
    S->>C: REQUEST_N(N=2)
    S-->>C: PAYLOAD STATUS_1
    Note over S,C: Server đã gửi hết credit response
    C->>S: PAYLOAD COMMAND_1
    C->>S: PAYLOAD COMMAND_2
    Note over C,S: Client vẫn gửi theo credit server đã cấp
    S-->>C: PAYLOAD STATUS_2
    Note over S,C: Payload này cần credit mới từ client
    C->>S: REQUEST_N(N=1)
    S-->>C: PAYLOAD STATUS_3
~~~

Khi không có credit, producer không được tự ý gửi thêm payload theo hướng đó. Nếu producer tiếp tục tạo dữ liệu từ nguồn nóng, ứng dụng cần đảm bảo dữ liệu không tích tụ trong một hàng đợi không giới hạn trước khi được phép gửi.

### Không cấp thêm demand có thể là một quyết định có chủ đích

Consumer có thể tạm thời không cấp thêm demand khi đang bận xử lý. Điều đó tạo một khoảng dừng tự nhiên ở hướng tương ứng.

Tuy nhiên, không cấp demand khác với hủy channel:

- Không cấp demand: channel còn hoạt động; producer chờ.
- Gửi REQUEST_N: cho phép producer gửi thêm payload.
- Hoàn tất hướng gửi: phía gửi thông báo không còn payload tiếp theo.
- Hủy interaction: requester kết thúc toàn bộ channel.

Nếu client không còn quan tâm đến phiên điều khiển, cần hủy interaction hoặc kết thúc theo hợp đồng; giữ channel mở nhưng không bao giờ cấp demand có thể giữ connection state và tài nguyên lâu hơn cần thiết.

## 5. Half-close: kết thúc một hướng nhưng giữ hướng còn lại

Request-channel hỗ trợ hai hướng dữ liệu có vòng đời riêng. Một phía có thể kết thúc việc gửi payload của mình mà vẫn tiếp tục nhận dữ liệu từ peer. Đây thường được gọi là **half-close**.

Trong RSocket, phía gửi dùng flag COMPLETE trên PAYLOAD để báo rằng nó không gửi thêm payload ở hướng đó. Nếu frame cuối vẫn mang dữ liệu, frame có thể mang cả NEXT và COMPLETE. COMPLETE là flag trên PAYLOAD, không phải một frame độc lập.

Ví dụ client đã gửi xong command nhưng vẫn muốn nhận các event xử lý còn lại:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: REQUEST_CHANNEL(initialN=3, START)
    S->>C: REQUEST_N(N=2)
    C->>S: PAYLOAD SET_SPEED
    C->>S: PAYLOAD STOP
    C->>S: PAYLOAD COMPLETE
    S-->>C: PAYLOAD COMMAND_ACCEPTED
    S-->>C: PAYLOAD DEVICE_STOPPED
    S-->>C: PAYLOAD COMPLETE
    Note over C,S: Cả hai hướng đã hoàn tất
~~~

Trong ví dụ này:

- Client gửi COMPLETE để kết thúc hướng command.
- Server vẫn có thể gửi các event còn lại theo demand client đã cấp.
- Khi server gửi COMPLETE ở hướng response, cả hai hướng đã đóng và channel kết thúc bình thường.

### Half-close khác CANCEL

| Tín hiệu | Phạm vi | Kết quả |
|---|---|---|
| COMPLETE trên PAYLOAD | Hướng gửi của peer phát frame | Peer đó không gửi thêm payload; hướng nhận vẫn có thể hoạt động |
| CANCEL | Toàn bộ interaction | Requester hủy channel, không tiếp tục trao đổi trên stream |
| ERROR | Toàn bộ interaction | Interaction kết thúc do lỗi |

Nếu client chỉ gửi hết command nhưng vẫn cần nhận kết quả, hãy hoàn tất publisher đầu vào của client. Không hủy subscription nhận response vì thao tác đó có thể hủy toàn bộ channel.

## 6. Ánh xạ flow control vào Reactor và Spring RSocket

Trong ứng dụng Spring, developer thường không tự tạo frame REQUEST_N. RSocket runtime ánh xạ demand của Reactive Streams thành initialN hoặc REQUEST_N ở cấp giao thức.

Ở phía client:

- Publisher commands cung cấp payload đi từ client tới server.
- Subscriber của events thể hiện số response client sẵn sàng nhận.
- Khi subscriber cần thêm phần tử, demand được truyền qua runtime về server.
- Khi publisher command hoàn tất, client đóng hướng gửi command nhưng vẫn có thể nhận event.

Ở phía server:

- Tham số Flux<DeviceCommand> nhận luồng command từ client.
- Các toán tử downstream thể hiện demand đối với luồng command.
- Publisher Flux<DeviceEvent> tạo response/event cho client.
- Demand của client điều tiết số event server có thể phát.

### Server xử lý tuần tự command

~~~java
@Controller
class DeviceChannelController {

    private final DeviceService deviceService;

    DeviceChannelController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("device.control")
    Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
        return commands
            .filter(DeviceCommand::isValid)
            .concatMap(deviceService::handle, 1);
    }
}
~~~

concatMap xử lý publisher con tuần tự theo thứ tự command nhận vào. Tham số prefetch bằng 1 hạn chế số phần tử được yêu cầu trước từ upstream, giúp demand bám sát khả năng xử lý tuần tự hơn. Nếu nghiệp vụ cho phép xử lý nhiều command đồng thời, có thể dùng flatMap với giới hạn concurrency:

~~~java
@MessageMapping("device.telemetry-control")
Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
    return commands
        .filter(DeviceCommand::isValid)
        .flatMap(deviceService::handle, 8);
}
~~~

Tham số 8 giới hạn số publisher con được xử lý đồng thời trong toán tử. Đây là giới hạn concurrency ở pipeline ứng dụng, không phải giá trị credit cố định của giao thức RSocket. Chọn concurrency theo giới hạn database, thiết bị, downstream và yêu cầu thứ tự.

### Client gửi command và nhận event

~~~java
Flux<DeviceCommand> commands = commandSource();

Flux<DeviceEvent> events = requester
    .route("device.control")
    .data(commands)
    .retrieveFlux(DeviceEvent.class);

Disposable subscription = events.subscribe(
    event -> updateDeviceView(event),
    error -> showControlError(error),
    () -> showChannelCompleted()
);
~~~

Khi events được subscribe, client mở request-channel. commands là nguồn payload đi lên; events là luồng response đi xuống. Demand của subscriber điều tiết response từ server; demand mà server cấp cho inbound command điều tiết payload client gửi tiếp.

Nếu command source hoàn tất tự nhiên, client ngừng gửi command và vẫn có thể nhận các event server phát ra. Nếu người dùng muốn dừng toàn bộ phiên, hủy subscription response:

~~~java
subscription.dispose();
~~~

Hủy subscription này phát tín hiệu cancellation upstream và runtime có thể gửi CANCEL để kết thúc interaction. Nó khác với việc chỉ hoàn tất commands.

## 7. Nguồn phát nóng và chính sách buffer

Flow control hoạt động tốt nhất khi producer có thể phản ứng với demand. Một Flux từ database reactive hoặc một pipeline Reactor có thể truyền backpressure ngược về nguồn.

Nhưng một số nguồn phát nóng không thể giảm tốc, ví dụ callback từ SDK thiết bị, listener hệ điều hành hoặc một message source không hỗ trợ demand. Khi nguồn này phát nhanh hơn channel gửi được, ứng dụng phải quyết định cách xử lý phần dữ liệu dư.

Một số chính sách thường gặp:

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| Buffer có giới hạn | Giữ tối đa N payload, quá giới hạn phải xử lý overflow | Cần giữ thứ tự và có thể chịu một lượng burst nhỏ |
| Drop | Bỏ payload không thể xử lý ngay | Dữ liệu telemetry trung gian có thể mất |
| Latest | Chỉ giữ giá trị mới nhất | Dashboard cần trạng thái hiện tại |
| Sample/window | Gộp hoặc lấy mẫu theo khoảng thời gian | Dữ liệu tốc độ cao dùng để hiển thị hoặc phân tích |
| Persist | Ghi dữ liệu vào log/store để xử lý sau | Sự kiện cần độ bền và không được bỏ |

Ví dụ, dashboard nhiệt độ có thể chỉ cần giá trị mới nhất. Nhưng lệnh thanh toán hoặc command điều khiển có tác dụng một lần không nên bị drop tùy tiện.

Nếu dùng buffer, phải đặt giới hạn và định nghĩa hành vi khi buffer đầy. Buffer không giới hạn có thể làm bộ nhớ tăng liên tục dù RSocket đã có flow control trên đường truyền.

### Flow control và rate limiting cần kết hợp

Một channel có thể có credit lớn và producer có thể phát nhanh trong thời gian ngắn. Nếu cần bảo vệ downstream theo số request mỗi giây, hãy thêm rate limiter ở tầng ứng dụng.

Cần tách ba giới hạn:

- **Demand/credit:** số payload consumer sẵn sàng nhận.
- **Concurrency:** số thao tác xử lý đồng thời.
- **Rate limit:** số thao tác trong một khoảng thời gian.

Ba cơ chế này bổ trợ nhau. Chỉ đặt concurrency không giới hạn số request theo thời gian; chỉ đặt rate limit không kiểm soát kích thước buffer; chỉ dùng credit không giới hạn byte hoặc chi phí xử lý của mỗi payload.

## 8. Lỗi, timeout và cancellation trong channel

Một channel có thể tồn tại lâu và mang dữ liệu hai chiều, vì vậy cần quy định rõ hành vi khi lỗi xảy ra ở từng phía.

### Lỗi xử lý command

Nếu server không xử lý được một command, có thể chọn:

- Phát một DeviceEvent nghiệp vụ như COMMAND_REJECTED rồi tiếp tục channel.
- Kết thúc toàn bộ interaction bằng lỗi nếu channel không thể tiếp tục an toàn.
- Ghi nhận lỗi của riêng command, nếu hợp đồng cho phép xử lý độc lập từng command.

Không biến mọi lỗi command thành lỗi toàn channel nếu các command sau vẫn có thể xử lý an toàn. Ngược lại, không nuốt lỗi nghiêm trọng khiến client tưởng command đã thành công.

### Timeout

Timeout có thể được áp dụng cho từng command hoặc cho toàn bộ phiên. Timeout của một command không nhất thiết phải kết thúc channel nếu service có thể trả event lỗi cho command đó và tiếp tục nhận command tiếp theo.

Một phiên điều khiển kéo dài cần có idle timeout hoặc session deadline để giải phóng tài nguyên khi client biến mất mà không đóng channel đúng cách.

### Cancellation

Khi requester hủy channel, server cần truyền cancellation tới publisher command và các công việc upstream có liên quan. Những tác vụ đang thực hiện cần được thiết kế để dừng an toàn hoặc có cơ chế idempotency nếu chúng không thể dừng ngay.

~~~java
@MessageMapping("device.control")
Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
    return commands
        .concatMap(deviceService::handle, 1)
        .doOnCancel(() -> logger.info("Device channel cancelled"))
        .doFinally(signal -> metrics.channelEnded(signal));
}
~~~

doOnCancel giúp quan sát việc hủy; doFinally quan sát complete, error hoặc cancel. Nếu nguồn giữ tài nguyên như socket thiết bị, cursor hoặc subscription tới broker, hãy giải phóng chúng khi publisher kết thúc.

## 9. Bảo vệ channel khi một phía gửi quá nhanh

Điều tiết luồng là một phần của bảo vệ tài nguyên. Với một channel nhiều command, server nên kết hợp demand với các giới hạn nghiệp vụ:

- Xác thực và phân quyền từng channel theo thiết bị hoặc tenant.
- Giới hạn số channel đồng thời trên mỗi client.
- Giới hạn kích thước payload và loại command được phép.
- Giới hạn concurrency của handler.
- Đặt giới hạn buffer và chính sách overflow.
- Đặt timeout cho command và idle timeout cho channel.
- Theo dõi số payload nhận/gửi, demand, độ trễ xử lý và cancellation.
- Không cho client tự tăng tải bằng cách mở vô hạn channel mới.

Ở phía client cũng cần bảo vệ giao diện và bộ nhớ. Nếu server gửi event nhanh hơn khả năng hiển thị, client có thể gộp cập nhật hoặc chỉ hiển thị trạng thái mới nhất nếu nghiệp vụ cho phép.

### Quan sát demand và độ trễ

Các chỉ số hữu ích gồm:

| Metric | Điều cần phát hiện |
|---|---|
| Channel đang hoạt động | Số phiên hai chiều hiện tại |
| Payload command nhận được | Tốc độ gửi từ client |
| Payload event phát ra | Tốc độ gửi từ server |
| Thời gian xử lý command | Handler hoặc dependency đang chậm |
| Số publisher con đang chạy | Mức concurrency thực tế |
| Buffer depth/overflow | Nguồn phát nhanh hơn consumer |
| Số lần cancel/timeout | Client rời phiên hoặc kết nối không ổn định |
| Payload bị drop | Mức mất dữ liệu theo chính sách |

Không nên chỉ theo dõi tổng số frame. Cần phân biệt hướng gửi và route để biết bên nào đang chậm.

## 10. Kiểm thử điều tiết hai chiều

Kiểm thử request-channel cần xác nhận cả hai hướng có thể tiến triển độc lập và không gửi vượt quá demand đã cấp.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Client mở channel với initialN = 2 | Server chỉ phát tối đa hai response payload trước khi có demand thêm |
| Server chưa cấp demand cho command tiếp theo | Client không gửi thêm payload vượt quá nhu cầu |
| Client gửi REQUEST_N(3) | Server được phép gửi thêm tối đa ba payload response |
| Server gửi REQUEST_N(4) | Client được phép gửi thêm tối đa bốn command sau payload mở đầu |
| Hết credit ở hướng server → client | Server chờ; hướng client → server vẫn có thể hoạt động nếu còn credit |
| Hết credit ở hướng client → server | Client chờ; server vẫn có thể gửi response nếu còn credit |
| Client half-close command input | Server vẫn có thể gửi các response còn lại |
| Client cancel channel | Cả interaction kết thúc và công việc liên quan nhận cancellation |
| Nguồn nóng phát vượt khả năng gửi | Chính sách buffer/drop/latest hoạt động đúng giới hạn |
| Handler xử lý tuần tự | Thứ tự command được bảo toàn |
| Handler xử lý đồng thời | Concurrency không vượt giới hạn và thứ tự được kiểm tra theo hợp đồng |

### Kiểm thử handler bằng StepVerifier

Có thể kiểm tra thứ tự xử lý command ở tầng service/controller:

~~~java
@Test
void processesCommandsInOrder() {
    Flux<DeviceCommand> commands = Flux.just(
        new DeviceCommand("START"),
        new DeviceCommand("SET_SPEED"),
        new DeviceCommand("STOP")
    );

    Flux<DeviceEvent> events = commands.concatMap(deviceService::handle);

    StepVerifier.create(events)
        .expectNextMatches(event -> event.commandName().equals("START"))
        .expectNextMatches(event -> event.commandName().equals("SET_SPEED"))
        .expectNextMatches(event -> event.commandName().equals("STOP"))
        .verifyComplete();
}
~~~

Test này xác nhận pipeline phát event theo thứ tự khi service trả một publisher cho mỗi command. Nó chưa kiểm tra frame flow control thực tế.

### Kiểm thử integration với RSocket

Với RSocket integration test, nên dùng client/server thật trong test để kiểm tra:

1. Client mở request-channel và gửi payload đầu tiên.
2. Server chỉ nhận payload tiếp theo sau khi có demand phù hợp.
3. Client điều tiết số response server gửi bằng initialN và REQUEST_N.
4. Server điều tiết số command client gửi bằng REQUEST_N.
5. Một hướng hết credit không làm dừng hướng còn lại.
6. Half-close một hướng vẫn cho phép nhận payload ở hướng còn lại.
7. CANCEL kết thúc toàn bộ channel và giải phóng publisher.
8. Buffer và giới hạn concurrency giữ đúng chính sách khi tải tăng.

Các test protocol-level có thể cần subscriber điều khiển demand thủ công để quan sát việc cấp thêm request(n). Với ứng dụng Spring thông thường, runtime quản lý frame; hãy kiểm tra hành vi qua subscription, số payload nhận được và cancellation thay vì tự tạo frame trong controller.

## 11. Những lỗi thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ initialN điều tiết cả hai hướng | Một hướng không được kiểm soát đúng | Nhớ initialN trong REQUEST_CHANNEL cấp response demand từ server về client |
| Chỉ client gửi REQUEST_N | Server có thể nhận command vượt khả năng xử lý | Server cũng phải cấp demand cho client |
| Dùng chung một credit counter | Hai hướng ảnh hưởng lẫn nhau | Theo dõi demand riêng cho từng hướng |
| Gửi payload khi hết credit | Vi phạm flow control | Chờ REQUEST_N từ consumer |
| Coi REQUEST_N là giới hạn payload theo byte | Payload lớn vẫn gây áp lực bộ nhớ | Giới hạn kích thước payload riêng |
| Dùng flatMap không giới hạn cho command | Quá nhiều thao tác chạy đồng thời, khó giữ thứ tự | concatMap hoặc flatMap có concurrency |
| Dùng buffer không giới hạn cho nguồn nóng | Bộ nhớ tăng liên tục khi consumer chậm | Buffer có giới hạn và chính sách overflow |
| Dùng CANCEL khi chỉ muốn ngừng gửi command | Mất luôn response còn cần nhận | Hoàn tất publisher command để half-close |
| Coi COMPLETE là hủy toàn channel | Mất khả năng nhận dữ liệu ở hướng còn lại | COMPLETE chỉ đóng hướng gửi của phía đó |
| Không giải phóng tài nguyên khi cancel | Handler hoặc subscription tiếp tục chạy | Propagate cancellation và đóng tài nguyên |
| Xem backpressure là rate limit | Burst traffic vẫn có thể gây tải lớn | Kết hợp credit, concurrency và rate limit |

## Kết luận

Request-channel là interaction hai chiều, nên flow control phải được hiểu như hai cơ chế demand độc lập. Client dùng initialN và REQUEST_N để điều tiết payload server gửi về; server dùng REQUEST_N để điều tiết payload client gửi tiếp. Mỗi hướng tiêu thụ credit riêng và có thể tạm dừng mà không buộc hướng còn lại dừng theo.

Khi triển khai bằng Spring và Reactor, demand của Subscription được RSocket runtime ánh xạ thành flow control ở cấp giao thức. Hãy chọn concatMap khi cần giữ thứ tự, giới hạn concurrency khi xử lý song song, đặt buffer có giới hạn cho nguồn nóng và phân biệt half-close bằng COMPLETE với hủy toàn interaction bằng CANCEL.

Một channel realtime ổn định cần quản lý cả hai hướng: nhu cầu nhận, tốc độ phát, kích thước payload, concurrency, timeout, cancellation và quyền truy cập.
