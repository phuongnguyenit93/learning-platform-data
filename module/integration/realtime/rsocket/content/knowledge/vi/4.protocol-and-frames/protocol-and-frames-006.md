# REQUEST_N và CANCEL trong điều khiển luồng tương tác

## Bối cảnh: một stream cần cơ chế điều khiển vòng đời

RSocket hỗ trợ giao tiếp bất đồng bộ giữa client và server qua TCP hoặc WebSocket. Một tương tác có thể chỉ trao đổi một request-response, hoặc có thể duy trì một luồng payload trong thời gian dài như telemetry, trạng thái thiết bị, giá thị trường hay lệnh điều khiển realtime.

Với luồng dữ liệu, bên phát cần biết bên nhận còn muốn nhận bao nhiêu payload. Nếu cứ gửi liên tục khi bên nhận chưa xử lý kịp, dữ liệu có thể tích tụ trong bộ nhớ và làm tăng độ trễ. Bên nhận cũng cần cách kết thúc một tương tác khi người dùng rời màn hình, hủy thao tác hoặc không còn cần dữ liệu.

RSocket giải quyết hai nhu cầu điều khiển quan trọng ở cấp giao thức:

- **REQUEST_N** cho biết bên nhận muốn nhận thêm bao nhiêu payload từ peer trên một stream.
- **CANCEL** cho biết requester muốn hủy toàn bộ tương tác đang diễn ra trên stream đó.

Hai frame này có vai trò khác nhau. REQUEST_N điều chỉnh nhu cầu dữ liệu trong khi stream còn hoạt động; CANCEL kết thúc tương tác. Hiểu đúng chúng giúp xây dựng RSocket client/server có khả năng điều tiết tải, dừng công việc đúng lúc và quản lý tài nguyên khi số lượng stream tăng.

## 1. Frame và stream trong RSocket

Mỗi tương tác RSocket được nhận diện bằng một **stream ID**. Các frame thuộc cùng một tương tác mang cùng stream ID để hai phía biết payload hoặc tín hiệu điều khiển đang nói đến stream nào.

Một kết nối RSocket có thể đồng thời mang nhiều stream. Vì thế, hủy một stream không đồng nghĩa đóng toàn bộ kết nối TCP hoặc WebSocket. Những stream khác trên cùng kết nối vẫn có thể tiếp tục hoạt động.

Một frame RSocket thường có header chứa stream ID, loại frame và flags; phần nội dung sau header phụ thuộc loại frame. Trong nhóm frame được dùng để điều khiển stream:

| Frame | Frame type ID | Nội dung chính | Ý nghĩa |
|---|---:|---|---|
| REQUEST_N | **0x08** | Stream ID và số lượng N | Yêu cầu peer gửi thêm N payload |
| CANCEL | **0x09** | Stream ID | Hủy tương tác trên stream được chỉ định |
| PAYLOAD | **0x0A** | Data và/hoặc metadata, kèm flags NEXT/COMPLETE | Mang dữ liệu hoặc tín hiệu hoàn tất một hướng |

REQUEST_N và CANCEL là frame điều khiển, không phải payload nghiệp vụ. Chúng không mang một Reading, DeviceCommand hay đối tượng DTO của ứng dụng. REQUEST_N mang số lượng nhu cầu; CANCEL chỉ cần xác định stream cần hủy.

Trong PAYLOAD, flag NEXT cho biết frame mang payload dữ liệu; flag COMPLETE cho biết phía gửi đã kết thúc việc phát dữ liệu trên hướng đó. COMPLETE là flag của PAYLOAD, không phải một frame độc lập. Với request-channel, một phía có thể gửi PAYLOAD kèm COMPLETE để đóng hướng gửi của mình trong khi vẫn tiếp tục nhận dữ liệu từ peer.

### REQUEST_N có cấu trúc gì?

Về mặt logic, REQUEST_N chứa:

- Stream ID: stream mà bên nhận muốn điều tiết.
- Request N: số lượng payload bổ sung mà bên gửi frame sẵn sàng tiếp nhận.

Trường Request N là số nguyên dương 31-bit theo định dạng giao thức. Giá trị N phải lớn hơn 0. Một frame REQUEST_N cấp thêm N quyền gửi, không thay thế tổng nhu cầu đã cấp trước đó.

Mỗi PAYLOAD mang NEXT được gửi theo hướng được cấp nhu cầu sẽ tiêu thụ một đơn vị credit. Một PAYLOAD có thể chứa data, metadata hoặc cả hai; dù có nhiều trường nội dung, nó vẫn là một payload frame và tiêu thụ một đơn vị nhu cầu.

### CANCEL có cấu trúc gì?

CANCEL chỉ cần Stream ID. Khi requester gửi frame này, nó thông báo rằng không còn muốn duy trì tương tác trên stream đó. Peer phải dừng việc phát dữ liệu của tương tác và hủy công việc upstream tương ứng nếu có thể.

CANCEL không phải một payload rỗng, không phải một giá trị lỗi và cũng không phải tín hiệu hoàn tất bình thường. Nó là tín hiệu hủy tương tác.

## 2. REQUEST_N điều tiết số payload được gửi

Trong giao tiếp streaming, bên nhận không nhất thiết xử lý được dữ liệu nhanh bằng tốc độ bên phát tạo ra dữ liệu. REQUEST_N cho phép bên nhận cấp credit theo khả năng tiêu thụ.

Giả sử client theo dõi cảm biến. Ban đầu client chỉ sẵn sàng xử lý hai payload. Server gửi tối đa hai payload theo nhu cầu ban đầu. Sau khi xử lý xong và có thêm khả năng tiếp nhận, client gửi REQUEST_N với N bằng 3 để yêu cầu thêm ba payload.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: REQUEST_STREAM(streamId=1, initialN=2)
    S-->>C: PAYLOAD Reading 1
    S-->>C: PAYLOAD Reading 2
    Note over C: Đã dùng hết 2 credit
    C->>S: REQUEST_N(streamId=1, N=3)
    S-->>C: PAYLOAD Reading 3
    S-->>C: PAYLOAD Reading 4
    S-->>C: PAYLOAD Reading 5
    Note over C: Đã dùng hết 3 credit mới
    C->>S: CANCEL(streamId=1)
~~~

Luồng trên cho thấy ba điểm:

1. Client cấp nhu cầu ban đầu ngay trong frame mở đầu REQUEST_STREAM thông qua initialN.
2. Mỗi payload server gửi làm giảm credit còn lại của server đối với stream đó.
3. Khi muốn nhận thêm, client gửi REQUEST_N để cấp thêm credit.

initialN là nhu cầu ban đầu được mang trong REQUEST_STREAM hoặc REQUEST_CHANNEL. REQUEST_N được dùng để cấp thêm nhu cầu sau khi tương tác đã được mở.

### Credit được tính theo payload frame

REQUEST_N đếm số PAYLOAD frame, không đếm số byte, số trường metadata hay số giây. Ví dụ, một PAYLOAD có data 10 byte và metadata 2 KB vẫn tiêu thụ một credit. Vì vậy, điều tiết theo số frame không thay thế giới hạn kích thước payload.

Nếu mỗi payload có kích thước rất lớn, bên nhận vẫn có thể tiêu thụ nhiều bộ nhớ dù số credit nhỏ. Ứng dụng cần kết hợp flow control với giới hạn payload, buffer và tốc độ xử lý.

### REQUEST_N là nhu cầu bổ sung

Giả sử client đã cấp 10 credit và server đã gửi 4 payload. Nếu client gửi REQUEST_N với N bằng 5, tổng credit khả dụng tăng thêm 5. Server lúc này có thể gửi tối đa 11 payload nữa trước khi cần thêm nhu cầu.

Không nên hiểu REQUEST_N(5) là đặt tổng nhu cầu của stream thành 5. Nó cộng thêm năm payload vào nhu cầu đã cấp trước đó.

### Điều gì xảy ra khi chưa có credit?

Với stream có flow control, bên phát phải tôn trọng nhu cầu do peer cấp. Khi đã sử dụng hết credit, bên phát phải chờ thêm REQUEST_N trước khi gửi PAYLOAD tiếp theo trên hướng đó.

Đây là cơ chế phối hợp tốc độ phát và tốc độ tiêu thụ. Nó giúp hạn chế việc một producer nhanh đẩy vô hạn dữ liệu sang consumer chậm. Tuy nhiên, nếu ứng dụng đã tạo một hàng đợi không giới hạn ở phía producer, dữ liệu vẫn có thể tích tụ trước khi đi vào lớp giao thức.

## 3. REQUEST_N trong các interaction model

REQUEST_N có ý nghĩa rõ nhất với các tương tác có thể phát nhiều payload theo thời gian. Không phải interaction model nào cũng cần cấp credit bổ sung.

| Interaction model | Cách mở tương tác | REQUEST_N có vai trò gì? |
|---|---|---|
| Request-response | REQUEST_RESPONSE | Một response đơn lẻ; không cần cấp thêm nhu cầu |
| Fire-and-forget | REQUEST_FNF | Không có response stream; không dùng REQUEST_N cho response |
| Request-stream | REQUEST_STREAM kèm initialN | Requester cấp nhu cầu cho các payload server gửi về |
| Request-channel | REQUEST_CHANNEL kèm initialN và payload đầu tiên | Hai hướng có nhu cầu độc lập; mỗi bên có thể cấp thêm credit cho payload từ peer |

### Request-stream: requester điều tiết luồng response

Trong request-stream, requester gửi một request mở đầu và cho biết số payload response ban đầu mà nó muốn nhận. Sau đó requester có thể gửi REQUEST_N nhiều lần để cấp thêm nhu cầu.

~~~text
Requester                         Responder
    |                                  |
    | REQUEST_STREAM(initialN = 4)     |
    |--------------------------------->|
    |                                  |
    | PAYLOAD 1                        |
    |<---------------------------------|
    | PAYLOAD 2                        |
    |<---------------------------------|
    | PAYLOAD 3                        |
    |<---------------------------------|
    | PAYLOAD 4                        |
    |<---------------------------------|
    |                                  |
    | REQUEST_N(N = 4)                 |
    |--------------------------------->|
    |                                  |
    | PAYLOAD 5..8                     |
    |<---------------------------------|
~~~

Requester là bên quyết định khi nào cần thêm response. Responder phải theo dõi nhu cầu hiện tại của stream và chỉ gửi payload trong giới hạn đó.

### Request-channel: hai hướng có credit riêng

Request-channel cho phép cả hai phía gửi nhiều payload. Vì mỗi phía vừa có thể là producer vừa có thể là consumer, nhu cầu của hai hướng cần được điều khiển độc lập.

Khi mở channel, requester gửi frame REQUEST_CHANNEL gồm payload mở đầu và initialN, thể hiện nhu cầu ban đầu đối với các response từ responder. Nếu responder cần nhận thêm command từ requester, responder gửi REQUEST_N theo chiều ngược lại. Sau đó requester cũng có thể gửi REQUEST_N để yêu cầu thêm response từ responder.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: REQUEST_CHANNEL(initialN=2, Command 0)
    S-->>C: PAYLOAD Event 1
    S-->>C: PAYLOAD Event 2
    S->>C: REQUEST_N(N=3)
    C->>S: PAYLOAD Command 1
    C->>S: PAYLOAD Command 2
    C->>S: PAYLOAD Command 3
    C->>S: REQUEST_N(N=2)
    S-->>C: PAYLOAD Event 3
    S-->>C: PAYLOAD Event 4
    C->>S: CANCEL
~~~

Có thể hình dung hai hướng như hai luồng dữ liệu riêng:

- Client → Server: server cấp nhu cầu bằng REQUEST_N để nhận thêm command.
- Server → Client: client cấp nhu cầu bằng initialN hoặc REQUEST_N để nhận thêm event.

Payload mở đầu được mang trực tiếp trong REQUEST_CHANNEL. Các payload tiếp theo ở mỗi hướng phải tuân theo nhu cầu mà peer cấp cho hướng đó.

### Vì sao request-response và fire-and-forget không cần REQUEST_N?

Request-response có một request và một response nghiệp vụ. Fire-and-forget gửi một request mà không mở response stream. Hai mô hình này không có một chuỗi PAYLOAD response cần điều tiết bằng credit như request-stream hoặc request-channel.

Nếu nghiệp vụ cần nhận nhiều kết quả theo thời gian, hãy chọn request-stream hoặc request-channel thay vì cố dùng request-response lặp lại.

## 4. CANCEL kết thúc một tương tác

Một stream có thể không bao giờ tự hoàn tất, ví dụ luồng telemetry của một thiết bị đang hoạt động. Khi client rời trang dashboard hoặc người dùng nhấn nút dừng theo dõi, việc tiếp tục phát dữ liệu sẽ lãng phí tài nguyên.

Requester có thể gửi CANCEL để hủy tương tác trên stream tương ứng.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: REQUEST_STREAM(sensor.readings)
    S-->>C: PAYLOAD Reading 1
    S-->>C: PAYLOAD Reading 2
    S-->>C: PAYLOAD Reading 3
    Note over C: Người dùng rời dashboard
    C->>S: CANCEL(streamId)
    Note over S: Hủy subscription và dừng nguồn dữ liệu nếu có thể
~~~

CANCEL có những đặc điểm quan trọng:

- Hủy tương tác được nhận diện bởi stream ID trong frame.
- Không đóng kết nối RSocket đang mang stream đó.
- Không hủy các stream khác trên cùng kết nối.
- Không hoàn tác những payload đã được xử lý hoặc tác dụng phụ đã xảy ra.
- Cần được truyền tới publisher hoặc tài nguyên upstream để công việc thực sự dừng.

Việc hủy là bất đồng bộ. Một payload có thể đã được gửi hoặc đang trên đường truyền khi CANCEL được xử lý. Vì vậy, ứng dụng không nên xem CANCEL như một giao dịch rollback hoặc bảo đảm rằng không còn bất kỳ tác dụng phụ nào đã bắt đầu.

### CANCEL khác COMPLETE và ERROR

Ba tín hiệu này có ngữ nghĩa khác nhau:

| Tín hiệu | Ý nghĩa | Tình huống |
|---|---|---|
| CANCEL | Requester không muốn tiếp tục tương tác | Người dùng dừng theo dõi |
| COMPLETE | Một phía kết thúc việc gửi payload bình thường | Server đã gửi xong dữ liệu |
| ERROR | Tương tác kết thúc do lỗi | Không thể đọc dữ liệu hoặc xử lý command |

Trong request-channel, COMPLETE có thể kết thúc hướng gửi payload của một phía trong khi phía còn lại vẫn tiếp tục gửi dữ liệu. Đây là cách đóng một chiều của channel. CANCEL hủy toàn bộ tương tác theo stream.

Không dùng CANCEL để biểu diễn “không còn dữ liệu”. Nếu stream đã gửi xong, hãy hoàn tất bình thường. Nếu có lỗi, hãy phát lỗi phù hợp để peer có thể phân biệt nguyên nhân.

### CANCEL không phải cách dừng fire-and-forget

Fire-and-forget không duy trì một response stream để requester tiếp tục điều khiển bằng CANCEL. Khi payload đã được gửi đi, requester không thể dùng CANCEL để thu hồi công việc nghiệp vụ đã bắt đầu ở server.

Nếu cần khả năng theo dõi hoặc dừng một công việc dài, hãy thiết kế tương tác có phản hồi, chẳng hạn request-response trả về operation ID kết hợp với một route điều khiển riêng, hoặc dùng request-stream/request-channel phù hợp.

## 5. Vòng đời của một stream có REQUEST_N và CANCEL

Một request-stream thường trải qua các giai đoạn sau:

1. **Mở stream:** requester gửi REQUEST_STREAM cùng request payload và initialN.
2. **Phát dữ liệu:** responder gửi PAYLOAD theo số credit hiện có.
3. **Cấp thêm nhu cầu:** requester gửi REQUEST_N khi có khả năng nhận thêm.
4. **Tiếp tục hoặc kết thúc:** responder tiếp tục phát, hoàn tất bình thường hoặc gửi lỗi.
5. **Hủy:** requester gửi CANCEL nếu không còn cần tương tác.

~~~mermaid
stateDiagram-v2
    [*] --> Open: REQUEST_STREAM
    Open --> Sending: nhận nhu cầu ban đầu
    Sending --> Waiting: hết credit
    Waiting --> Sending: REQUEST_N
    Sending --> Completed: COMPLETE
    Sending --> Failed: ERROR
    Open --> Failed: ERROR
    Waiting --> Failed: ERROR
    Open --> Cancelled: CANCEL
    Sending --> Cancelled: CANCEL
    Waiting --> Cancelled: CANCEL
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
~~~

Sơ đồ mô tả vòng đời khái quát. Một tương tác thực tế có thể kết thúc ngay sau khi mở do lỗi, hoặc hoàn tất trước khi cần REQUEST_N bổ sung.

### Trạng thái nhu cầu của bên phát

Để hiểu flow control, hãy xem bên phát duy trì một lượng credit cho hướng gửi dữ liệu:

- Khi nhận initialN, bên phát có nhu cầu ban đầu để gửi.
- Mỗi PAYLOAD được gửi đi tiêu thụ một credit.
- Khi nhận REQUEST_N(N), bên phát cộng thêm N credit.
- Khi credit bằng 0, bên phát phải chờ thêm nhu cầu.
- Khi stream bị hủy hoặc kết thúc, bên phát dừng phát payload cho stream đó.

Credit là trạng thái của từng stream và từng hướng dữ liệu. Không nên dùng một bộ đếm toàn cục cho mọi stream trên kết nối.

### Tương tác giữa flow control và cancellation

REQUEST_N và CANCEL bổ sung cho nhau. REQUEST_N giúp một stream tiếp tục chạy theo nhịp consumer; CANCEL giúp kết thúc stream khi consumer không còn nhu cầu.

Nếu client chậm, nó có thể tạm thời không cấp thêm credit. Nếu client không còn quan tâm đến dữ liệu, nó hủy stream. Việc không cấp thêm credit chỉ làm bên phát chờ; nó không tự giải phóng mọi tài nguyên liên quan đến stream. Khi đã quyết định dừng hẳn, cần hủy subscription hoặc gửi CANCEL để vòng đời được kết thúc.

## 6. Ánh xạ REQUEST_N và CANCEL vào Reactor

Trong ứng dụng Spring RSocket, lập trình viên thường thao tác với Mono, Flux và Subscription thay vì tự tạo frame REQUEST_N hoặc CANCEL. RSocket runtime chuyển các tín hiệu nhu cầu và hủy của Reactive Streams thành frame giao thức tương ứng.

### Consumer yêu cầu dữ liệu qua Subscription

Trong Reactive Streams, subscriber gọi request(n) để thể hiện số phần tử muốn nhận. Khi dữ liệu được tiêu thụ và cần thêm, subscriber có thể yêu cầu thêm phần tử. Trên RSocket, nhu cầu này được chuyển thành initialN khi mở stream hoặc REQUEST_N trong quá trình tương tác.

Không cần tự gửi REQUEST_N trong controller Spring thông thường. Hãy để runtime quản lý demand thông qua publisher/subscriber và chọn toán tử phù hợp với nhịp tiêu thụ.

### Hủy bằng Disposable

Ví dụ client đăng ký nhận dữ liệu:

~~~java
Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01"))
    .retrieveFlux(Reading.class);

Disposable subscription = readings.subscribe(
    reading -> updateDashboard(reading),
    error -> showConnectionError(error)
);

// Khi người dùng rời dashboard:
subscription.dispose();
~~~

Khi dispose subscription, Reactor gửi tín hiệu cancel upstream. Với một request-stream RSocket, runtime sử dụng tín hiệu này để hủy stream, thường bằng frame CANCEL. Publisher phía server nhận cancellation và cần dừng nguồn dữ liệu tương ứng.

### Hủy tự động bằng take

Nếu client chỉ cần một số lượng hữu hạn response, toán tử take có thể tự hủy upstream sau khi nhận đủ phần tử:

~~~java
Flux<Reading> firstTenReadings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01"))
    .retrieveFlux(Reading.class)
    .take(10);
~~~

Khi đã nhận đủ 10 phần tử, take hoàn tất luồng downstream và hủy subscription upstream. Với stream RSocket, tín hiệu hủy được runtime chuyển thành CANCEL. Cách này hữu ích cho truy vấn lấy một phần dữ liệu từ một stream dài.

### Quan sát cancellation ở server

~~~java
@MessageMapping("sensor.readings")
Flux<Reading> readings(SensorQuery query) {
    return sensorService.readings(query.sensorId())
        .doOnCancel(() -> logger.info(
            "Client cancelled sensor stream: {}",
            query.sensorId()
        ))
        .doFinally(signal -> metrics.streamEnded(
            query.sensorId(),
            signal
        ));
}
~~~

doOnCancel cho phép quan sát tín hiệu hủy; doFinally chạy khi publisher kết thúc bằng complete, error hoặc cancel. Nếu nguồn dữ liệu giữ socket, cursor, subscription tới message broker hoặc tài nguyên khác, service cần giải phóng chúng khi cancellation được truyền tới.

Không phải nguồn dữ liệu nào cũng dừng tức thì. Một lời gọi blocking có thể không phản ứng với cancellation; khi tích hợp nguồn blocking, cần thiết kế timeout, cơ chế interrupt hoặc API dừng riêng phù hợp.

## 7. Áp dụng trong request-channel

Request-channel có hai hướng dữ liệu nên cần chú ý cả demand lẫn cancellation. Ví dụ client gửi command và nhận event:

~~~java
Flux<DeviceCommand> commands = commandSource();

Flux<DeviceEvent> events = requester
    .route("device.control")
    .data(commands)
    .retrieveFlux(DeviceEvent.class);
~~~

Trong ví dụ này:

- Client phát command qua publisher commands.
- Server có thể cấp demand để nhận thêm command từ client.
- Client nhận event qua events và demand của client điều tiết số response server gửi.
- Khi subscription events bị hủy, toàn bộ tương tác channel được hủy; client không tiếp tục gửi command cho stream đó.

Phía server có thể xử lý tuần tự các command để bảo toàn thứ tự:

~~~java
@MessageMapping("device.control")
Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
    return commands
        .concatMap(deviceService::handle);
}
~~~

Nếu command được xử lý đồng thời bằng flatMap, event có thể được phát theo thứ tự hoàn tất của các thao tác con. Chọn toán tử theo yêu cầu thứ tự của nghiệp vụ.

Với channel, đừng nhầm việc một phía hoàn tất gửi dữ liệu với việc toàn bộ tương tác đã kết thúc. Nếu client gửi hết command và hoàn tất publisher đầu vào, server vẫn có thể gửi các event còn lại. Khi client hủy subscription nhận event, tương tác channel mới bị hủy toàn bộ.

## 8. Những lỗi thiết kế thường gặp

| Cách làm | Hệ quả | Cách xử lý |
|---|---|---|
| Xem REQUEST_N là tổng số payload được phép gửi | Bên phát tính sai credit còn lại | Coi mỗi REQUEST_N là nhu cầu bổ sung |
| Gửi payload khi đã hết credit | Vi phạm flow control của stream | Chờ peer cấp thêm demand |
| Dùng chung credit cho mọi stream | Một stream ảnh hưởng sai đến stream khác | Theo dõi demand theo stream và hướng |
| Nghĩ REQUEST_N giới hạn byte | Payload lớn vẫn có thể gây áp lực bộ nhớ | Giới hạn kích thước payload riêng |
| Không hủy stream khi client rời màn hình | Server tiếp tục tạo dữ liệu và giữ tài nguyên | Propagate cancellation hoặc dispose subscription |
| Coi CANCEL là rollback | Tác dụng phụ đã thực hiện vẫn có thể tồn tại | Thiết kế command idempotent và cơ chế bù trừ nếu nghiệp vụ cần |
| Coi COMPLETE và CANCEL giống nhau | Mất ngữ nghĩa hoàn tất bình thường và hủy | Dùng COMPLETE để kết thúc hướng gửi bình thường, CANCEL để hủy tương tác |
| Dùng CANCEL cho fire-and-forget | Không thể thu hồi công việc đã gửi | Dùng mô hình có vòng đời và khả năng điều khiển phù hợp |
| Giả định request-channel chỉ có một chiều demand | Một hướng có thể gửi quá nhanh | Quản lý demand độc lập ở cả hai hướng |
| Chỉ hủy ở client mà không giải phóng nguồn server | Tài nguyên upstream có thể còn hoạt động | Quan sát doOnCancel/doFinally và đóng tài nguyên đúng cách |

## Kết luận

REQUEST_N và CANCEL là hai frame điều khiển quan trọng của RSocket. REQUEST_N cấp thêm nhu cầu nhận payload theo từng stream; mỗi payload được gửi sẽ tiêu thụ một credit. CANCEL cho phép requester kết thúc tương tác khi không còn cần dữ liệu, đồng thời yêu cầu peer dừng công việc liên quan.

Trong request-stream, requester điều tiết response bằng initialN và REQUEST_N. Trong request-channel, mỗi hướng có demand riêng vì cả client và server đều có thể phát payload. Khi dùng Reactor và Spring, các tín hiệu request(n) và cancel thường được runtime ánh xạ thành frame giao thức. Thiết kế đúng vòng đời publisher, backpressure và cancellation sẽ giúp ứng dụng realtime sử dụng tài nguyên hợp lý và phản ứng tốt khi client thay đổi nhu cầu.
