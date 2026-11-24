# Vì sao cần giao tiếp bất đồng bộ và truyền dữ liệu liên tục

## Bối cảnh: ứng dụng không chỉ trao đổi một lần rồi kết thúc

Một API tra cứu hồ sơ thường nhận một yêu cầu, xử lý và trả về một kết quả. Nhưng nhiều hệ thống hiện đại phải làm việc với dữ liệu thay đổi liên tục: thiết bị IoT gửi nhiệt độ, ứng dụng giao dịch nhận biến động giá, dashboard theo dõi trạng thái đơn hàng, hoặc dịch vụ vận hành nhận log và cảnh báo theo thời gian thực.

Nếu mọi tương tác đều được tổ chức theo kiểu “gửi yêu cầu, chờ phản hồi rồi mới làm tiếp”, hệ thống dễ lãng phí tài nguyên khi phải chờ mạng, khó xử lý nhiều luồng dữ liệu đồng thời và thường phải dùng polling để hỏi xem có dữ liệu mới hay chưa. Giao tiếp bất đồng bộ giúp các thành phần tiếp tục công việc trong lúc chờ kết quả; truyền dữ liệu liên tục giúp bên nhận nhận được cập nhật ngay khi chúng phát sinh.

Trong phạm vi tích hợp realtime, RSocket cung cấp các kiểu tương tác này trên một kết nối qua TCP hoặc WebSocket. RSocket hỗ trợ request-response, fire-and-forget, request-stream và request-channel, đồng thời có cơ chế điều tiết luồng theo nhu cầu của bên nhận. Để hiểu vì sao các khả năng đó hữu ích, trước hết cần nhìn vào giới hạn của giao tiếp đồng bộ.

## 1. Giới hạn của giao tiếp đồng bộ

Trong mô hình đồng bộ phổ biến, bên gọi gửi yêu cầu và chờ bên được gọi hoàn tất. Ví dụ, một ứng dụng gọi dịch vụ tồn kho để kiểm tra số lượng sản phẩm:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant I as Inventory API
    participant DB as Database
    C->>I: Kiểm tra tồn kho
    I->>DB: Truy vấn số lượng
    DB-->>I: Kết quả truy vấn
    I-->>C: Trả số lượng
~~~

Luồng này dễ hiểu và phù hợp với thao tác cần một kết quả ngay, nhưng có một số giới hạn khi thời gian xử lý hoặc số lượng tương tác tăng lên.

### Thời gian chờ chiếm tài nguyên

Giả sử một lời gọi mạng mất 800 ms. Trong thời gian đó, luồng xử lý của client có thể phải chờ phản hồi. Nếu hàng nghìn yêu cầu cùng chờ, máy chủ cần quản lý nhiều tác vụ đang chờ, bộ nhớ và số lượng kết nối tăng lên. Một lời gọi chậm ở dịch vụ phía sau cũng có thể kéo dài thời gian hoàn thành của toàn bộ chuỗi xử lý.

Các framework có thể dùng thread pool, non-blocking I/O hoặc virtual thread để quản lý việc chờ hiệu quả hơn. Tuy vậy, thay đổi cách quản lý thread không tự giải quyết được mọi vấn đề: ứng dụng vẫn cần mô hình để biểu diễn nhiều kết quả, dữ liệu hai chiều, nhu cầu tiêu thụ và việc hủy một luồng đang chạy.

### Độ trễ lan truyền qua nhiều dịch vụ

Một yêu cầu có thể gọi lần lượt dịch vụ xác thực, giá, tồn kho và thanh toán. Nếu mỗi bước phải chờ bước trước, tổng thời gian phản hồi chịu ảnh hưởng của tất cả các bước. Khi một dịch vụ chậm hoặc mất kết nối, các yêu cầu đang chờ có thể tích tụ ở những dịch vụ còn lại.

Giao tiếp bất đồng bộ cho phép bên gọi khởi chạy công việc rồi xử lý kết quả khi nó sẵn sàng. Với các công việc độc lập, ứng dụng cũng có thể khởi chạy chúng đồng thời và kết hợp kết quả sau đó. Điều này giúp sử dụng tài nguyên tốt hơn, nhưng không làm cho bản thân thao tác mạng hoặc xử lý nghiệp vụ tự nhiên nhanh hơn.

### Một yêu cầu thường chỉ trả về một ảnh chụp dữ liệu

Request-response truyền thống trả về một kết quả tại một thời điểm. Nếu client cần theo dõi trạng thái thay đổi, nó thường phải gọi API lặp lại:

~~~text
Client                         Server
  |---- trạng thái hiện tại ----->|
  |<--- trạng thái: đang xử lý ---|
  |                              |
  |---- trạng thái hiện tại ----->|
  |<--- trạng thái: đang đóng gói -|
  |                              |
  |---- trạng thái hiện tại ----->|
  |<--- trạng thái: đang giao ----|
~~~

Cách hỏi lặp này gọi là polling. Polling đơn giản và vẫn phù hợp khi dữ liệu ít thay đổi hoặc độ trễ vài giây có thể chấp nhận. Tuy nhiên, khi không có cập nhật, nhiều request vẫn được gửi đi; khi có cập nhật ngay sau một lần hỏi, client phải đợi đến chu kỳ tiếp theo mới nhìn thấy dữ liệu.

## 2. Giao tiếp bất đồng bộ giải quyết điều gì?

Giao tiếp bất đồng bộ cho phép một thành phần khởi tạo thao tác mà không cần giữ luồng thực thi ở trạng thái chờ cho đến khi có kết quả. Kết quả có thể được xử lý sau thông qua callback, Future, CompletableFuture, hoặc một publisher reactive như Mono và Flux.

Ví dụ với Java:

~~~java
CompletableFuture<Inventory> future =
    inventoryService.findAsync("SKU-001");

// Ứng dụng có thể thực hiện công việc độc lập trong lúc chờ.
prepareOrderSummary();

future.thenAccept(inventory ->
    updateOrderAvailability(inventory)
);
~~~

findAsync trả về một đối tượng đại diện cho kết quả sẽ có trong tương lai. Client đăng ký cách xử lý kết quả và tiếp tục phần việc độc lập. Khi kết quả hoàn tất, callback được thực thi theo cơ chế của executor hoặc framework đang dùng.

Điểm quan trọng là **bất đồng bộ mô tả cách phối hợp công việc và kết quả**, không nhất thiết mô tả cách dữ liệu được lưu hay truyền. Một lời gọi HTTP có thể được xử lý bất đồng bộ ở phía client; ngược lại, một hệ thống dùng message broker có thể tiếp nhận thông điệp bất đồng bộ và lưu nó bền vững trước khi xử lý. Hai cách triển khai này có đặc tính khác nhau.

| Khía cạnh | Giao tiếp đồng bộ kiểu chờ kết quả | Giao tiếp bất đồng bộ |
|---|---|---|
| Luồng điều khiển | Bên gọi thường chờ kết quả trước khi đi tiếp | Bên gọi có thể tiếp tục việc độc lập |
| Kết quả | Thường được nhận ngay trong luồng gọi | Được xử lý khi thao tác hoàn tất hoặc có dữ liệu |
| Tài nguyên | Có thể giữ thread trong thời gian chờ | Có thể dùng callback hoặc reactive pipeline để tránh giữ thread chờ I/O |
| Lỗi | Thường xuất hiện trực tiếp tại điểm gọi | Có thể xuất hiện muộn trong callback hoặc publisher và cần được xử lý tại đó |
| Trường hợp phù hợp | Truy vấn ngắn, cần kết quả trước khi tiếp tục | I/O có độ trễ, nhiều công việc đồng thời, luồng dữ liệu hoặc tương tác kéo dài |

Bất đồng bộ không có nghĩa là “không cần chờ” trong mọi tình huống. Ứng dụng vẫn có thể cần đợi một kết quả trước khi quyết định bước tiếp theo. Khác biệt nằm ở chỗ việc chờ được biểu diễn và quản lý như thế nào, có cần chiếm một thread trong lúc chờ hay không, và ứng dụng có thể xử lý nhiều kết quả theo thời gian hay không.

## 3. Vì sao cần truyền dữ liệu liên tục?

Với dữ liệu thay đổi theo thời gian, một phản hồi duy nhất nhanh chóng trở nên cũ. Truyền dữ liệu liên tục cho phép server phát ra nhiều phần dữ liệu trên cùng một tương tác; client nhận từng phần khi chúng sẵn sàng.

Ví dụ, dashboard theo dõi một thiết bị có thể nhận các sự kiện:

~~~text
10:00:01  temperature = 28.4°C
10:00:03  temperature = 28.6°C
10:00:04  fan           = ON
10:00:06  temperature = 27.9°C
~~~

Thay vì hỏi server mỗi vài giây, client đăng ký một luồng dữ liệu và nhận cập nhật khi có sự kiện mới. Cách này hữu ích với telemetry, giá thị trường, tiến trình xử lý dài, thông báo, trạng thái thiết bị và dữ liệu realtime.

Truyền liên tục đem lại một số lợi ích:

- **Dữ liệu mới hơn:** cập nhật có thể được gửi ngay khi phát sinh, giảm độ trễ do chu kỳ polling.
- **Giảm request thăm dò:** client không cần liên tục hỏi server khi không có thay đổi.
- **Biểu diễn tự nhiên cho nhiều kết quả:** một tương tác có thể phát ra 0, 1 hoặc nhiều phần tử theo thời gian.
- **Hỗ trợ tương tác hai chiều:** client có thể gửi lệnh trong khi server tiếp tục gửi trạng thái hoặc sự kiện.

Streaming cũng đặt ra yêu cầu mới. Client cần biết khi nào luồng kết thúc, cách hủy đăng ký, cách xử lý lỗi giữa chừng và cách phục hồi khi kết nối bị ngắt. Nếu ứng dụng cần phát lại những sự kiện đã bỏ lỡ, nó phải có chiến lược lưu hoặc truy vấn lại dữ liệu; một kết nối streaming đang hoạt động tự nó không phải kho lưu trữ sự kiện bền vững.

## 4. RSocket cung cấp mô hình tương tác nào?

RSocket là giao thức ứng dụng cho trao đổi dữ liệu bất đồng bộ theo kiểu reactive. Nó có thể chạy trên các transport như TCP và WebSocket. Trên một kết nối, hai bên có thể thiết lập nhiều luồng tương tác độc lập. Thay vì chỉ định nghĩa một kiểu request-response, RSocket cung cấp bốn interaction model để chọn theo hình dạng dữ liệu của nghiệp vụ.

| Interaction model | Dữ liệu trao đổi | Ví dụ sử dụng |
|---|---|---|
| **Request-response** | Một request, một response | Tra cứu trạng thái hiện tại của thiết bị |
| **Fire-and-forget** | Một request, không có response nghiệp vụ | Gửi một sự kiện telemetry hoặc lệnh không cần kết quả trả về |
| **Request-stream** | Một request, nhiều response theo thời gian | Đăng ký luồng nhiệt độ hoặc biến động giá |
| **Request-channel** | Nhiều request và nhiều response theo hai chiều | Client gửi lệnh liên tục, server trả trạng thái và kết quả xử lý |

### Request-response

Client gửi một payload và nhận đúng một response cho tương tác đó. Đây là mô hình gần với lời gọi API thông thường, nhưng có thể được triển khai theo hướng non-blocking và reactive.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: Request: sensor.status
    S-->>C: Response: DeviceStatus
~~~

Chọn request-response khi nghiệp vụ cần một kết quả đơn lẻ, chẳng hạn tra cứu trạng thái hiện tại hoặc tính toán một báo giá.

### Fire-and-forget

Client gửi một payload và không yêu cầu response nghiệp vụ. Mô hình này phù hợp khi bên gửi chỉ cần phát một thông điệp, ví dụ gửi mẫu telemetry hoặc ghi nhận một sự kiện không cần kết quả xử lý trả về ngay.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: Event: sensor.reading
    Note over C,S: Không có response nghiệp vụ
~~~

Vì không có response nghiệp vụ, client không thể dựa vào response để biết thao tác phía server đã hoàn tất hay chưa. Nếu nghiệp vụ cần xác nhận, kết quả xử lý hoặc khả năng truy vấn trạng thái, hãy dùng interaction model có response hoặc thiết kế một kênh xác nhận riêng. Khi gửi lại sau lỗi mạng, cần tính đến khả năng xử lý trùng lặp.

### Request-stream

Client gửi một request mở đầu và server trả về một luồng gồm nhiều response. Luồng có thể tiếp tục cho đến khi hoàn tất, xảy ra lỗi hoặc bị client hủy.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: Request: subscribe readings
    S-->>C: Reading 1
    S-->>C: Reading 2
    S-->>C: Reading 3
    S-->>C: ...
    C--xS: Cancel stream
~~~

Request-stream phù hợp với dashboard, giá thị trường, tiến trình dài hoặc dữ liệu cảm biến. Client không cần gửi một request mới cho mỗi phần tử trong luồng.

### Request-channel

Request-channel cho phép cả client và server gửi nhiều payload trong cùng một tương tác. Client có thể gửi lệnh hoặc dữ liệu đầu vào liên tục; server đồng thời phát sự kiện, kết quả hoặc trạng thái về client.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as RSocket Server
    C->>S: Command 1
    S-->>C: Status 1
    C->>S: Command 2
    S-->>C: Status 2
    S-->>C: Device event
    C->>S: Command 3
    S-->>C: Status 3
~~~

Mô hình này hữu ích cho điều khiển thiết bị realtime, phiên tương tác trực tiếp hoặc các quy trình mà hai phía đều có dữ liệu cần gửi. Nếu chỉ một phía phát nhiều dữ liệu, request-stream hoặc một mô hình một chiều có thể đơn giản hơn.

## 5. Reactive và backpressure: điều tiết tốc độ dữ liệu

Một luồng dữ liệu có thể được tạo ra nhanh hơn tốc độ client xử lý. Ví dụ, cảm biến phát 5.000 sự kiện mỗi giây nhưng dashboard chỉ xử lý được 500 sự kiện mỗi giây. Nếu server cứ gửi dữ liệu không giới hạn, dữ liệu có thể tích tụ trong buffer, làm tăng độ trễ và tiêu thụ bộ nhớ; cuối cùng ứng dụng có thể bị quá tải.

**Backpressure** là cơ chế để bên tiêu thụ thể hiện nhu cầu, giúp bên phát điều chỉnh lượng dữ liệu gửi đi. Trong Reactive Streams, subscriber yêu cầu một số lượng phần tử thông qua Subscription.request(n). RSocket có cơ chế flow control ở mức giao thức cho các luồng streaming: bên nhận cấp quyền gửi theo số lượng phần tử mà nó sẵn sàng tiếp nhận.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as Consumer
    C->>P: Request N (cấp nhu cầu)
    P-->>C: Gửi tối đa N payload
    C->>P: Request thêm M
    P-->>C: Gửi tối đa M payload
~~~

Ví dụ, client đang xử lý được 20 phần tử có thể cấp nhu cầu cho 20 phần tử tiếp theo. Khi xử lý xong và cần thêm dữ liệu, client tiếp tục yêu cầu. Nhờ vậy, tốc độ truyền có thể phối hợp với khả năng tiêu thụ thay vì mặc định đẩy dữ liệu không giới hạn.

Backpressure không tự động làm cho mọi đoạn trong hệ thống có giới hạn bộ nhớ. Nếu ứng dụng đặt một hàng đợi không giới hạn trước publisher, hoặc dùng chiến lược buffer không giới hạn, dữ liệu vẫn có thể tích tụ ở đó. Khi thiết kế stream, cần xác định rõ:

- Có thể làm chậm producer hay không.
- Khi quá tải thì nên buffer có giới hạn, bỏ dữ liệu cũ, bỏ dữ liệu mới hay lưu dữ liệu để xử lý sau.
- Phần tử nào bắt buộc phải xử lý đầy đủ, phần tử nào có thể lấy mẫu hoặc gộp lại.
- Khi client hủy subscription, công việc phía server có được dừng và giải phóng tài nguyên hay không.

Ví dụ, dashboard hiển thị nhiệt độ hiện tại có thể chỉ cần giá trị mới nhất; bỏ qua một số giá trị trung gian có thể chấp nhận được. Nhưng hệ thống ghi nhận giao dịch tài chính thường không thể tùy tiện bỏ sự kiện. Chiến lược điều tiết phải dựa trên yêu cầu nghiệp vụ.

## 6. Ví dụ với Spring Boot và RSocket

Spring hỗ trợ ánh xạ route RSocket vào các phương thức có @MessageMapping. Kiểu tham số và kiểu trả về reactive giúp thể hiện interaction model ngay trong chữ ký phương thức.

Ví dụ sau minh họa server cung cấp luồng dữ liệu cảm biến và nhận một luồng lệnh điều khiển:

~~~java
@Controller
class SensorRSocketController {

    private final SensorService sensorService;
    private final DeviceService deviceService;

    SensorRSocketController(
            SensorService sensorService,
            DeviceService deviceService) {
        this.sensorService = sensorService;
        this.deviceService = deviceService;
    }

    // Request-stream: một query, nhiều Reading.
    @MessageMapping("sensor.readings")
    Flux<Reading> readings(SensorQuery query) {
        return sensorService.readings(query.sensorId());
    }

    // Request-channel: nhận nhiều command và phát nhiều event.
    @MessageMapping("sensor.control")
    Flux<DeviceEvent> control(Flux<DeviceCommand> commands) {
        return commands.concatMap(deviceService::handle);
    }
}
~~~

Client có thể đăng ký luồng đọc dữ liệu bằng RSocketRequester:

~~~java
Flux<Reading> readings = requester
    .route("sensor.readings")
    .data(new SensorQuery("sensor-01"))
    .retrieveFlux(Reading.class);

Disposable subscription = readings.subscribe(
    reading -> updateDashboard(reading),
    error -> showConnectionError(error)
);

// Khi người dùng rời dashboard hoặc không cần dữ liệu nữa:
subscription.dispose();
~~~

retrieveFlux biểu diễn nhiều response theo thời gian. Khi subscription bị hủy, tín hiệu cancel được truyền qua pipeline để các thành phần liên quan có cơ hội dừng việc phát dữ liệu và giải phóng tài nguyên.

Các interaction model còn lại cũng có thể được thể hiện qua kiểu trả về của client:

~~~java
// Request-response: nhận một trạng thái.
Mono<DeviceStatus> status = requester
    .route("sensor.status")
    .data(new SensorQuery("sensor-01"))
    .retrieveMono(DeviceStatus.class);

// Fire-and-forget: gửi một sự kiện, không nhận response nghiệp vụ.
Mono<Void> sendReading = requester
    .route("sensor.telemetry")
    .data(new Reading("sensor-01", 28.4))
    .send();
~~~

Các đoạn mã trên giả định RSocketRequester, DTO và service đã được cấu hình trong ứng dụng. Chúng minh họa cách chọn interaction model; cấu hình transport, serializer, bảo mật và xử lý lỗi cần được bổ sung theo môi trường triển khai.

## 7. Những vấn đề cần thiết kế khi dùng giao tiếp bất đồng bộ

Giao tiếp bất đồng bộ và streaming giúp xử lý tương tác kéo dài, nhưng kết quả và lỗi không còn luôn xuất hiện ngay tại dòng gọi. Ứng dụng cần thiết kế rõ vòng đời của từng tương tác.

### Timeout và hủy tương tác

Một request không nên chờ vô hạn. Hãy đặt timeout theo yêu cầu nghiệp vụ và xử lý trường hợp hết thời gian. Với stream, xác định điều kiện hoàn tất và thời điểm client cần hủy subscription. Hủy stream giúp giảm công việc và tài nguyên khi người dùng rời màn hình hoặc dữ liệu không còn cần thiết.

### Lỗi và retry

Lỗi có thể xuất hiện khi thiết lập kết nối, trong lúc stream đang chạy hoặc khi xử lý một payload. Retry chỉ an toàn khi thao tác có thể thực hiện lại mà không gây tác dụng phụ ngoài ý muốn. Với lệnh tạo giao dịch hoặc cập nhật trạng thái, nên có mã định danh/idempotency key và quy tắc xử lý trùng lặp. Đặc biệt, nếu kết nối mất sau khi gửi nhưng trước khi client biết kết quả, client có thể không xác định được server đã xử lý payload hay chưa.

### Mất kết nối và phục hồi

Client realtime cần có chính sách reconnect với khoảng chờ phù hợp, giới hạn số lần thử và cách thông báo trạng thái kết nối. Kết nối lại không đồng nghĩa dữ liệu bị lỡ sẽ tự động được phát lại. Nếu cần khôi phục đầy đủ, ứng dụng có thể dùng sequence number, cursor hoặc timestamp để yêu cầu server gửi tiếp từ vị trí đã xử lý; dữ liệu nguồn phải được lưu đủ lâu để đáp ứng yêu cầu đó. RSocket có các khả năng resume tùy cấu hình và triển khai, nhưng ứng dụng không nên mặc định rằng mọi kết nối đều tự phục hồi và phát lại mọi payload.

### Thứ tự và tính nhất quán

Nếu nghiệp vụ phụ thuộc thứ tự sự kiện, cần xác định phạm vi thứ tự cần bảo đảm: trong một stream, theo một thiết bị, hay giữa nhiều nguồn. Khi xử lý song song, kết quả có thể hoàn tất khác thứ tự đầu vào. Ví dụ trong Spring, concatMap xử lý tuần tự từng command theo thứ tự nhận; các toán tử song song có thể tăng throughput nhưng cần được chọn cùng với yêu cầu về thứ tự.

### Bảo mật và metadata

Kết nối TCP nên được bảo vệ bằng TLS khi đi qua mạng không tin cậy; WebSocket triển khai bảo mật thường dùng WSS. Ứng dụng cần xác thực peer và phân quyền theo route hoặc tài nguyên mà người dùng được phép truy cập. RSocket metadata có thể mang thông tin định tuyến, xác thực hoặc tracing tùy cấu hình; cần quy định định dạng, kiểm tra đầu vào và tránh đưa bí mật vào metadata không được bảo vệ.

### Quan sát và giới hạn tài nguyên

Một stream có thể tồn tại lâu hơn một HTTP request thông thường. Nên theo dõi số kết nối, số stream đang hoạt động, thời gian sống, tốc độ phát/nhận, lỗi, lần reconnect và số lần hủy. Đồng thời cần giới hạn số stream trên mỗi client, kích thước payload, tốc độ gửi và dung lượng buffer để một client chậm không làm ảnh hưởng toàn hệ thống.

## 8. Khi nào nên chọn RSocket?

RSocket phù hợp khi ứng dụng cần nhiều kiểu tương tác trên cùng một mô hình giao tiếp, đặc biệt là stream dữ liệu, giao tiếp hai chiều và điều tiết luồng theo nhu cầu của bên nhận. Một số ví dụ:

| Nhu cầu | Interaction model thường phù hợp | Lý do |
|---|---|---|
| Tra cứu trạng thái hiện tại | Request-response | Một yêu cầu cần một kết quả |
| Gửi telemetry không cần phản hồi nghiệp vụ | Fire-and-forget | Chỉ cần phát một payload |
| Theo dõi nhiệt độ hoặc giá theo thời gian | Request-stream | Một yêu cầu mở ra nhiều cập nhật |
| Gửi lệnh và nhận sự kiện thiết bị liên tục | Request-channel | Cả hai phía đều có luồng dữ liệu |

Không phải mọi API đều cần RSocket. CRUD thông thường, tích hợp với hệ thống chỉ hỗ trợ HTTP hoặc tác vụ không cần cập nhật liên tục vẫn có thể phù hợp với REST. Server-Sent Events có thể đáp ứng nhu cầu server đẩy dữ liệu một chiều tới trình duyệt; WebSocket cung cấp kênh hai chiều khi ứng dụng cần tự định nghĩa giao thức trao đổi. RSocket đáng cân nhắc khi cần các interaction model request-response, fire-and-forget, stream và channel cùng cơ chế reactive flow control trong một giao thức.

| Tiêu chí | REST/HTTP request-response | SSE | WebSocket | RSocket |
|---|---|---|---|---|
| Request-response | Tự nhiên | Không phải mục tiêu chính | Ứng dụng tự thiết kế | Có sẵn |
| Server đẩy nhiều dữ liệu | Cần cơ chế streaming bổ sung | Có | Có | Có |
| Hai chiều | Có thể qua nhiều request | Một chiều server tới client | Có | Có |
| Các interaction model chuẩn hóa | Chủ yếu request-response | Event stream một chiều | Payload do ứng dụng định nghĩa | Request-response, fire-and-forget, request-stream, request-channel |
| Flow control theo nhu cầu consumer | Tùy giải pháp | Cần thiết kế theo ứng dụng | Cần thiết kế theo ứng dụng | Có cơ chế flow control cho stream |

Các công nghệ có thể kết hợp với nhau. Ví dụ, một hệ thống vẫn dùng REST cho thao tác quản trị và dùng RSocket cho dashboard realtime. Việc chọn giao thức nên dựa trên hình dạng tương tác, năng lực của client/server và chi phí vận hành, không chỉ dựa trên việc công nghệ nào mới hơn.

## Kết luận

Giao tiếp bất đồng bộ giúp ứng dụng phối hợp các công việc có độ trễ mà không phải giữ luồng xử lý ở trạng thái chờ; streaming giúp biểu diễn dữ liệu thay đổi liên tục bằng một tương tác kéo dài; backpressure giúp phối hợp tốc độ phát và tốc độ tiêu thụ. RSocket kết hợp các ý tưởng này qua bốn interaction model và hỗ trợ giao tiếp hai chiều trên TCP hoặc WebSocket.

Khi thiết kế một luồng realtime, hãy bắt đầu từ câu hỏi nghiệp vụ: cần một kết quả, gửi một sự kiện, nhận nhiều cập nhật hay trao đổi dữ liệu liên tục theo hai chiều? Sau đó chọn interaction model, xác định chính sách backpressure, timeout, hủy, retry, reconnect và bảo mật. Những quyết định này mới giúp một kết nối realtime hoạt động ổn định khi tải tăng hoặc mạng không còn hoàn hảo.
