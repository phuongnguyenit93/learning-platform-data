# So sánh RSocket với HTTP, WebSocket thuần, SSE và gRPC

Khi xây dựng một hệ thống realtime, có nhiều lựa chọn để truyền dữ liệu giữa client và server. HTTP phù hợp với API request-response phổ biến; WebSocket tạo một kênh hai chiều liên tục; Server-Sent Events (SSE) đẩy sự kiện từ server về client; gRPC cung cấp RPC có hợp đồng kiểu dữ liệu rõ ràng và hỗ trợ streaming; còn RSocket định nghĩa các kiểu tương tác bất đồng bộ, hai chiều và có điều tiết luồng.

Không có giao thức nào luôn tốt nhất. Lựa chọn đúng phụ thuộc vào hướng truyền dữ liệu, cách ứng dụng cần trao đổi thông điệp, yêu cầu backpressure, nền tảng client, hạ tầng mạng và khả năng vận hành. Bài này đặt RSocket cạnh HTTP, WebSocket thuần, SSE và gRPC để làm rõ những điểm khác nhau đó.

## 1. Phân biệt giao thức ứng dụng và transport

Trước khi so sánh, cần phân biệt hai lớp thường bị gọi chung là “giao thức giao tiếp”:

- **Giao thức ứng dụng** quy định ý nghĩa của thông điệp và cách hai phía tương tác: gửi yêu cầu, nhận phản hồi, mở luồng dữ liệu, hủy luồng hay truyền metadata.
- **Transport** chuyển byte giữa hai đầu và xử lý những vấn đề ở tầng truyền tải như kết nối, thứ tự byte và truyền lại gói tin.

HTTP và WebSocket có đặc tả giao tiếp ứng dụng riêng. SSE là cách biểu diễn luồng sự kiện trên HTTP. gRPC định nghĩa mô hình RPC và thường sử dụng HTTP/2 làm transport. RSocket là một giao thức ứng dụng có thể chạy trên những transport được implementation hỗ trợ, phổ biến trong phạm vi bài học này là TCP và WebSocket.

Vì vậy, **RSocket chạy trên WebSocket không đồng nghĩa với WebSocket thuần**. WebSocket cung cấp kết nối hai chiều và các frame dữ liệu; RSocket đóng gói thông điệp theo protocol riêng, gắn chúng với stream ID và quy định các kiểu tương tác như request-response, request-stream hay request-channel.

Tương tự, HTTP/2 có khả năng multiplex nhiều stream trên một kết nối và hỗ trợ truyền dữ liệu hai chiều ở tầng transport. Điều đó không tự động biến một API HTTP thông thường thành mô hình request-channel có ngữ nghĩa và điều tiết nhu cầu ở tầng ứng dụng. gRPC tận dụng HTTP/2 và bổ sung mô hình RPC, kiểu dữ liệu cùng quy tắc streaming.

## 2. RSocket cung cấp những kiểu tương tác nào?

Điểm nổi bật của RSocket là mô hình tương tác được định nghĩa sẵn. Ứng dụng chọn kiểu phù hợp với từng thao tác thay vì phải tự thiết kế toàn bộ quy ước thông điệp trên một kết nối thô.

| Kiểu tương tác | Hành vi | Ví dụ |
|---|---|---|
| Request-response | Client gửi một request và nhận tối đa một response cho request đó. | Lấy trạng thái đơn hàng hoặc giá hiện tại của một mã cổ phiếu. |
| Fire-and-forget | Client gửi một thông điệp và không chờ response ở tầng ứng dụng. | Phát một sự kiện telemetry hoặc ghi nhận một tín hiệu không cần kết quả đồng bộ. |
| Request-stream | Client gửi request ban đầu và nhận một stream gồm nhiều response. | Theo dõi giá cổ phiếu hoặc trạng thái thiết bị liên tục. |
| Request-channel | Client gửi một stream thông điệp; server cũng có thể trả về một stream thông điệp trên cùng tương tác. | Client gửi lệnh điều khiển trong khi nhận trạng thái thiết bị. |

RSocket còn có **metadata push** cho việc gửi metadata trên kết nối. Đây là một loại thông điệp riêng, không phải kiểu tương tác thứ năm tương đương với bốn mô hình ở bảng trên.

Với các tương tác dạng stream, RSocket có cơ chế demand-based flow control. Bên nhận có thể yêu cầu một số lượng phần tử tiếp theo; protocol biểu diễn nhu cầu đó bằng thông điệp `REQUEST_N`. Khi không còn cần dữ liệu, bên nhận có thể hủy stream. Cơ chế này giúp bên phát biết tốc độ mà bên nhận sẵn sàng tiếp nhận.

Backpressure không thay thế giới hạn tài nguyên, rate limit hay kiểm soát tải toàn hệ thống. Nó cũng không tự bảo đảm dữ liệu đã được lưu bền vững hoặc xử lý đúng một lần. Với fire-and-forget, client không nhận response nghiệp vụ để xác nhận server đã hoàn tất xử lý; nếu cần xác nhận, hãy chọn mô hình có phản hồi hoặc thiết kế cơ chế acknowledgement riêng.

RSocket multiplex nhiều stream logic trên một kết nối vật lý. Mỗi stream có định danh và vòng đời riêng, nên các tương tác độc lập có thể cùng tồn tại trên kết nối đó. Điều này hữu ích khi một client cần vừa gọi request-response, vừa theo dõi nhiều luồng sự kiện và gửi lệnh hai chiều.

## 3. So sánh tổng quan

Bảng sau mô tả cách các lựa chọn thường được sử dụng trong ứng dụng. Khả năng thực tế còn phụ thuộc phiên bản protocol, thư viện client/server và hạ tầng triển khai.

| Tiêu chí | HTTP API | WebSocket thuần | SSE | gRPC | RSocket |
|---|---|---|---|---|---|
| Mô hình chính | Request-response; có thể mở rộng bằng streaming hoặc các cơ chế khác | Kênh thông điệp hai chiều liên tục | Server đẩy sự kiện đến client | RPC unary và streaming | Request-response, fire-and-forget, request-stream, request-channel |
| Hướng truyền | Thường là client request, server response | Hai chiều sau khi kết nối được thiết lập | Một chiều server → client | Một chiều hoặc hai chiều tùy loại RPC | Một chiều hoặc hai chiều tùy kiểu tương tác |
| Streaming | Có thể thực hiện, nhưng cách dùng phụ thuộc HTTP version và API | Có thể gửi nhiều message trong cả hai hướng | Có luồng sự kiện server → client | Hỗ trợ client, server và bidirectional streaming | Hỗ trợ stream và channel ở tầng protocol |
| Backpressure | Không có một mô hình demand của ứng dụng thống nhất cho mọi HTTP API | TCP có điều khiển luồng ở tầng transport; WebSocket API phổ biến không cung cấp demand nghiệp vụ chuẩn | EventSource không cung cấp API demand cho từng event | HTTP/2 flow control và cơ chế flow control của thư viện gRPC | Demand-based flow control cho các tương tác stream |
| Hợp đồng dữ liệu | Thường dùng JSON/OpenAPI hoặc hợp đồng API riêng | Ứng dụng tự định nghĩa envelope, loại message và correlation ID | Thường là text/event-stream, dữ liệu event do ứng dụng định nghĩa | Protocol Buffers và service definition là lựa chọn phổ biến | Payload và metadata; schema/serialization do ứng dụng và hệ sinh thái chọn |
| Hỗ trợ trình duyệt | Rất rộng | Rộng qua WebSocket API | Rộng qua EventSource | Thường cần gRPC-Web hoặc gateway phù hợp | Cần client RSocket chạy trên WebSocket và hạ tầng tương thích |
| Tái kết nối | Client thực hiện retry theo chính sách API | Ứng dụng thường tự quản lý reconnect và đồng bộ trạng thái | EventSource hỗ trợ reconnect và `Last-Event-ID` theo cơ chế SSE | Thư viện có retry policy theo điều kiện; streaming cần xử lý lại phiên | Có keepalive; resume là khả năng tùy chọn và phụ thuộc implementation/cấu hình |
| Điểm mạnh | Tương thích rộng, dễ cache, dễ tích hợp gateway và công cụ | Linh hoạt cho tương tác realtime hai chiều | Đơn giản cho luồng thông báo một chiều | Hợp đồng rõ, sinh client, hỗ trợ đa ngôn ngữ và streaming | Mô hình tương tác phong phú, multiplexing và backpressure ở tầng protocol |
| Chi phí cần cân nhắc | Streaming và tương tác phức tạp cần thêm quy ước | Phải tự thiết kế protocol ứng dụng và quản lý luồng | Không phù hợp cho server nhận luồng message từ client | Phụ thuộc HTTP/2 và cần quản lý schema/code generation | Cần thư viện, công cụ quan sát và năng lực vận hành phù hợp |

## 4. RSocket và HTTP

### 4.1. HTTP phù hợp với API request-response

HTTP là lựa chọn mặc định hợp lý cho phần lớn API nghiệp vụ: tạo tài nguyên, truy vấn, cập nhật, xóa hoặc tải một kết quả. Phương thức, status code, header, cache và các công cụ trung gian đã được chuẩn hóa rộng rãi.

Ví dụ, client cần đọc giá hiện tại của một mã cổ phiếu có thể gọi:

```http
GET /api/quotes/ACME
Accept: application/json
```

Server trả về một tài liệu JSON. Nếu client cần giá mới sau vài giây, nó có thể gọi lại endpoint theo chu kỳ. Cách polling này dễ triển khai nhưng tạo request lặp lại ngay cả khi dữ liệu không thay đổi; độ trễ cập nhật phụ thuộc chu kỳ polling.

HTTP cũng có thể truyền dữ liệu dạng stream, và HTTP/2 hỗ trợ multiplexing nhiều stream trên một kết nối. Tuy nhiên, ứng dụng phải chọn cơ chế cụ thể như streaming response, SSE hoặc một giao thức xây dựng trên HTTP. HTTP request-response thông thường không tự cung cấp bốn kiểu tương tác và demand protocol giống RSocket.

### 4.2. RSocket phù hợp khi tương tác là một phần của API

Nếu client cần đăng ký một luồng giá và chỉ nhận dữ liệu theo nhu cầu, RSocket request-stream thể hiện trực tiếp ý định đó. Nếu client đồng thời gửi lệnh đăng ký/hủy hoặc lệnh điều khiển và nhận sự kiện liên tục, request-channel có thể biểu diễn hai luồng dữ liệu trong cùng một tương tác.

Một service Spring Boot có thể khai báo route cho stream như sau:

```java
@Controller
class QuoteRSocketController {

    private final QuoteService quoteService;

    QuoteRSocketController(QuoteService quoteService) {
        this.quoteService = quoteService;
    }

    @MessageMapping("quotes.{symbol}")
    Flux<Quote> stream(@DestinationVariable String symbol) {
        return quoteService.stream(symbol);
    }
}
```

Client dùng `RSocketRequester` để nhận một `Flux`:

```java
Flux<Quote> quotes = requester
    .route("quotes.{symbol}", "ACME")
    .retrieveFlux(Quote.class);
```

Đoạn code minh họa cách ánh xạ route và stream trong Spring Messaging. Cấu hình transport, serialization, xác thực và cách tạo `RSocketRequester` cần được thiết lập trong ứng dụng thực tế.

### 4.3. Khi nào chọn HTTP, khi nào chọn RSocket?

Chọn HTTP cho API công khai, CRUD, tích hợp đối tác, nội dung cần cache, hoặc khi client và hạ tầng đã hỗ trợ HTTP tốt. Chọn RSocket khi nghiệp vụ cần nhiều kiểu tương tác bất đồng bộ, stream liên tục, trao đổi hai chiều và điều tiết demand ở tầng protocol.

Hai lựa chọn có thể cùng tồn tại trong một hệ thống. Ví dụ, HTTP cung cấp endpoint tra cứu snapshot và quản trị; RSocket cung cấp luồng cập nhật realtime cho các client cần theo dõi liên tục.

## 5. RSocket và WebSocket thuần

### 5.1. WebSocket cung cấp kênh hai chiều

Sau bước handshake qua HTTP, WebSocket duy trì một kết nối để client và server gửi message cho nhau. Đây là lựa chọn tự nhiên cho chat, bảng điều khiển realtime, trò chơi nhiều người chơi hoặc ứng dụng cộng tác.

Ví dụ ở trình duyệt:

```javascript
const socket = new WebSocket("wss://api.example.com/live");

socket.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  renderUpdate(message);
});

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({ type: "subscribe", symbol: "ACME" }));
});
```

WebSocket chỉ quy định cách mở kết nối và trao đổi frame/message. Ứng dụng phải tự thống nhất cấu trúc message, tên hành động, mã tương quan request-response, quy tắc lỗi, xác thực ở cấp ứng dụng, subscription, hủy subscription, phiên bản schema và cách khôi phục trạng thái sau reconnect.

### 5.2. RSocket bổ sung ngữ nghĩa tương tác

RSocket có thể dùng WebSocket làm transport nhưng định nghĩa thêm lớp protocol. Thay vì tự quy ước rằng một JSON message có `type: "subscribe"` nghĩa là mở subscription, client có thể dùng request-stream. Thay vì tự quản lý một cặp message cho kênh hai chiều, client có thể dùng request-channel.

RSocket cũng quy định stream ID, các loại frame và cơ chế demand cho stream. Nhờ vậy, thư viện hai phía có thể phối hợp việc gửi, nhận và hủy stream theo cùng một mô hình. Metadata có thể mang thông tin định tuyến hoặc thông tin phụ trợ tùy cách ứng dụng cấu hình.

Điều đó không có nghĩa RSocket luôn thay thế WebSocket. WebSocket thuần thường phù hợp hơn nếu ứng dụng cần một kênh message đơn giản, client chủ yếu là trình duyệt, hoặc hệ thống đã có protocol message riêng và đội ngũ hiểu rõ cách vận hành nó. RSocket phù hợp khi lợi ích từ các kiểu tương tác, multiplexing và backpressure bù được chi phí đưa thêm protocol cùng thư viện vào hệ thống.

### 5.3. So sánh cách xây dựng tính năng

| Nhu cầu | WebSocket thuần | RSocket |
|---|---|---|
| Gửi một lệnh và nhận một kết quả | Tự tạo request ID, response ID và timeout | Dùng request-response |
| Gửi một thông điệp không chờ kết quả | Tự định nghĩa loại message và quy tắc lỗi | Dùng fire-and-forget khi không cần response nghiệp vụ |
| Nhận luồng sự kiện | Tự định nghĩa subscribe, event và unsubscribe | Dùng request-stream và hủy stream |
| Gửi và nhận hai luồng dữ liệu liên tục | Tự thiết kế giao thức hai chiều | Dùng request-channel |
| Điều tiết tốc độ gửi theo demand của bên nhận | Phải tự thiết kế cơ chế ở tầng ứng dụng; TCP chỉ xử lý flow control ở tầng transport | Có demand-based flow control cho stream |

## 6. RSocket và Server-Sent Events (SSE)

SSE là cơ chế gửi sự kiện từ server về client qua một HTTP response có content type `text/event-stream`. Trình duyệt có thể dùng `EventSource` để mở và duy trì luồng sự kiện:

```javascript
const events = new EventSource("/api/quotes/ACME/events");

events.onmessage = (event) => {
  const quote = JSON.parse(event.data);
  renderQuote(quote);
};

events.onerror = () => {
  showConnectionStatus("Đang kết nối lại...");
};
```

Một event SSE có thể gồm `event`, `data`, `id` và `retry`. Ví dụ response:

```text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

id: 42
event: quote
data: {"symbol":"ACME","price":123.45}

```

SSE có một hướng dữ liệu: server → client. Client gửi lệnh hoặc thay đổi subscription qua một request HTTP riêng. EventSource có cơ chế tự kết nối lại; nếu server phát event ID, trình duyệt có thể gửi `Last-Event-ID` khi reconnect để server tiếp tục từ vị trí phù hợp nếu ứng dụng hỗ trợ lưu và phát lại sự kiện.

RSocket request-stream cũng phù hợp với dữ liệu server phát liên tục, nhưng có thể tham gia vào các tương tác hai chiều khác và hỗ trợ demand ở tầng protocol. Request-channel còn cho phép client gửi stream dữ liệu trong cùng tương tác. Vì vậy, SSE thường đơn giản hơn cho bảng tin, thông báo hoặc cập nhật chỉ đi từ server đến trình duyệt; RSocket phù hợp khi luồng dữ liệu là một phần của phiên tương tác hai chiều hoặc cần backpressure rõ ràng.

SSE không cần WebSocket upgrade và tận dụng hạ tầng HTTP thông thường, nhưng cần cấu hình proxy để tránh buffer response hoặc đóng kết nối nhàn rỗi quá sớm. API `EventSource` trên trình duyệt cũng không cung cấp cách đặt tùy ý header cho request; ứng dụng cần cân nhắc cookie, cùng origin hoặc một cơ chế xác thực phù hợp.

## 7. RSocket và gRPC

### 7.1. gRPC là RPC có hợp đồng dịch vụ

gRPC thường dùng Protocol Buffers để mô tả service và message. Từ file `.proto`, công cụ có thể sinh mã client/server cho nhiều ngôn ngữ. Một service có thể khai báo các kiểu RPC sau:

```proto
service QuoteService {
  rpc GetQuote(QuoteRequest) returns (Quote);
  rpc WatchQuotes(QuoteRequest) returns (stream Quote);
  rpc UploadOrders(stream Order) returns (UploadSummary);
  rpc Trade(stream TradeCommand) returns (stream TradeEvent);
}
```

Các phương thức lần lượt minh họa unary request-response, server streaming, client streaming và bidirectional streaming. gRPC thường chạy trên HTTP/2, tận dụng multiplexing và flow control của HTTP/2. Thư viện gRPC còn cung cấp API điều khiển luồng ở một số nền tảng để ứng dụng điều chỉnh việc nhận dữ liệu.

### 7.2. Điểm giống và khác với RSocket

RSocket và gRPC đều hỗ trợ request-response và streaming; cả hai đều có thể dùng trong giao tiếp service-to-service. Một RPC bidirectional streaming của gRPC có mục tiêu gần với request-channel của RSocket: client và server trao đổi nhiều message trong một call. Server streaming của gRPC gần với request-stream. Tuy nhiên, mô hình và chi tiết điều khiển luồng của hai protocol không giống hệt nhau.

Khác biệt đáng chú ý nằm ở cách định nghĩa hợp đồng và phạm vi tương tác:

- **gRPC** đặt trọng tâm vào service/method và schema được mô tả rõ, thường bằng Protocol Buffers. Code generation giúp các nhóm đa ngôn ngữ chia sẻ hợp đồng và giảm lỗi khi gọi service.
- **RSocket** đặt trọng tâm vào các kiểu tương tác và stream. Route cùng payload/metadata được trao đổi qua protocol; schema và serialization của dữ liệu nghiệp vụ do ứng dụng lựa chọn và quản lý.
- **RSocket** có fire-and-forget như một kiểu tương tác được định nghĩa trong protocol. Với gRPC, ứng dụng thường biểu diễn thao tác không cần kết quả bằng một RPC có response rỗng hoặc bằng một cơ chế gửi sự kiện khác; ngữ nghĩa không giống fire-and-forget của RSocket.
- **gRPC** có hệ sinh thái sinh mã, interceptor, status, deadline và tích hợp đa ngôn ngữ trưởng thành. **RSocket** thuận tiện khi ứng dụng reactive cần nhiều kiểu tương tác trên một kết nối và muốn demand-based flow control thống nhất cho stream.

gRPC không chỉ dành cho request-response: bidirectional streaming là khả năng quan trọng của nó. Ngược lại, RSocket cũng không tự cung cấp hợp đồng kiểu dữ liệu sinh mã tương đương `.proto`. Khi cần hợp đồng liên ngôn ngữ chặt chẽ và API RPC chuẩn hóa, gRPC thường là lựa chọn rõ ràng. Khi cần mô hình reactive với request-channel, fire-and-forget và stream multiplexed, RSocket đáng cân nhắc.

### 7.3. Giới hạn khi gọi từ trình duyệt

gRPC thông thường dựa trên HTTP/2 và các khả năng của runtime gRPC. Trình duyệt không cung cấp đầy đủ API HTTP/2 mà gRPC native cần, nên ứng dụng web thường dùng gRPC-Web cùng proxy hoặc gateway tương thích. Khả năng streaming của gRPC-Web phụ thuộc implementation và không tương đương toàn bộ bidirectional streaming của gRPC native.

RSocket trong trình duyệt thường cần một implementation client hỗ trợ WebSocket transport. WebSocket API sẵn có không tự hiểu RSocket; ứng dụng phải dùng thư viện RSocket tương ứng và server phải cho phép transport đó. WebSocket thuần và SSE thường dễ tiếp cận hơn nếu yêu cầu phía trình duyệt đơn giản.

## 8. Metadata, bảo mật và vòng đời kết nối

### 8.1. Metadata và định tuyến

Trong RSocket, payload có thể mang phần data và metadata. Data thường chứa nội dung nghiệp vụ; metadata có thể mang route, MIME type hoặc thông tin phụ trợ như xác thực và tracing tùy convention của ứng dụng. Composite metadata cho phép kết hợp nhiều mục metadata trên một payload. Hai phía phải thống nhất MIME type, encoding và quy ước metadata; không nên giả định mọi implementation tự hiểu cùng một metadata tùy biến.

HTTP dùng header và URL; WebSocket thuần thường truyền metadata trong handshake hoặc message do ứng dụng tự định nghĩa; SSE dùng header của HTTP request và field của event; gRPC có metadata/header riêng cùng schema message. Mỗi cơ chế có phạm vi và quy tắc riêng, nên cần xác định rõ thông tin nào dùng để xác thực, thông tin nào dùng để định tuyến và thông tin nào chỉ phục vụ quan sát.

### 8.2. Bảo mật

RSocket không tự động làm cho kết nối an toàn. Ứng dụng cần dùng transport bảo mật phù hợp, chẳng hạn TLS cho kết nối TCP hoặc WSS khi chạy trên WebSocket; xác thực danh tính client; kiểm tra quyền trên từng route/thao tác; bảo vệ secret; và giới hạn kích thước, tốc độ cũng như thời gian sống của kết nối. Nếu dùng metadata để gửi thông tin xác thực, cần bảo vệ dữ liệu đó trên đường truyền và tránh ghi token vào log.

HTTP, SSE và gRPC có thể tận dụng TLS, cơ chế xác thực ở gateway và các công cụ bảo mật HTTP. WebSocket thường xác thực qua handshake, cookie hoặc cơ chế token do ứng dụng thiết kế. Dù chọn công nghệ nào, xác thực kết nối không thay thế authorization cho từng tài nguyên hoặc hành động.

### 8.3. Keepalive, reconnect và resume

Kết nối realtime có thể bị gián đoạn bởi mạng di động, proxy, load balancer hoặc việc triển khai lại server. Cần phân biệt ba việc:

1. **Keepalive** giúp phát hiện kết nối không còn hoạt động trong khoảng thời gian cấu hình.
2. **Reconnect** tạo một kết nối mới sau khi kết nối cũ bị mất. Ứng dụng phải quyết định đăng ký lại stream, gửi lại lệnh nào và đồng bộ trạng thái ra sao.
3. **Resume** tiếp tục một phiên RSocket có thể khôi phục nếu cả hai phía, transport và cấu hình đều hỗ trợ. Resume có thể cần lưu trạng thái/frame trong một khoảng thời gian và không phải bảo đảm giao hàng đúng một lần cho mọi nghiệp vụ.

RSocket có cơ chế keepalive và khả năng resume tùy chọn trong protocol, nhưng khả năng thực tế phụ thuộc implementation và cấu hình. WebSocket thuần thường cần ứng dụng tự thiết kế heartbeat, reconnect và đồng bộ lại subscription. SSE có reconnect tích hợp ở EventSource và có thể dùng event ID để tiếp tục luồng nếu server lưu được lịch sử. gRPC có retry policy cho một số trường hợp, nhưng stream đang hoạt động vẫn cần logic phục hồi phù hợp. HTTP request-response thường dễ retry hơn, với điều kiện thao tác có tính idempotent hoặc có idempotency key.

Không nên coi reconnect là bằng chứng rằng mọi message trong thời gian mất mạng đã được xử lý. Với thao tác quan trọng như thanh toán hoặc tạo đơn hàng, cần thiết kế idempotency, acknowledgement, lưu trạng thái và đối soát ở tầng nghiệp vụ.

## 9. Chọn công nghệ theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| CRUD, API công khai, tích hợp hệ thống bên ngoài | HTTP/REST | Tương thích rộng, dễ cache, dễ kiểm thử và được hỗ trợ bởi gateway/tooling phổ biến. |
| Server chỉ cần đẩy thông báo hoặc cập nhật đến trình duyệt | SSE | Mô hình một chiều đơn giản, EventSource hỗ trợ reconnect. |
| Chat hoặc giao diện web cần gửi/nhận message hai chiều | WebSocket | Kênh hai chiều trực tiếp; phù hợp khi protocol message do ứng dụng kiểm soát. |
| Giao tiếp giữa service đa ngôn ngữ, cần schema và code generation | gRPC | Hợp đồng `.proto`, client/server sinh mã và nhiều kiểu streaming. |
| Ứng dụng Java reactive cần request-channel, nhiều kiểu tương tác và backpressure | RSocket | Mô hình tương tác phong phú, multiplexing và demand-based flow control. |

Một hệ thống có thể dùng nhiều công nghệ ở các ranh giới khác nhau. Ví dụ, nền tảng quản lý thiết bị có thể dùng HTTP cho cấu hình và truy vấn lịch sử, SSE cho trang giám sát chỉ đọc, RSocket giữa các service reactive cần gửi lệnh và nhận telemetry hai chiều, hoặc gRPC cho các API nội bộ có schema được chia sẻ giữa nhiều ngôn ngữ.

Không nên chọn RSocket chỉ vì hệ thống có chữ “realtime”. Nếu dữ liệu chỉ cần đẩy một chiều đến trình duyệt, SSE có thể ít phức tạp hơn. Nếu cần một kênh hai chiều đơn giản, WebSocket có thể đủ. Nếu cần RPC có hợp đồng đa ngôn ngữ, gRPC thường phù hợp hơn. RSocket có giá trị khi các đặc tính của nó giải quyết trực tiếp nhu cầu tương tác và điều tiết luồng của hệ thống.

## 10. Những yếu tố cần đánh giá trước khi triển khai

Trước khi quyết định, hãy trả lời các câu hỏi sau:

1. **Hướng dữ liệu:** Client chỉ gửi request, chỉ nhận event, hay hai phía đều gửi dữ liệu liên tục?
2. **Số lượng và vòng đời stream:** Một kết nối cần một stream hay nhiều stream độc lập? Client có thường xuyên mở/hủy subscription không?
3. **Điều tiết tải:** Bên nhận có thể xử lý chậm hơn bên phát không? Có cần demand-based backpressure hay chỉ cần giới hạn tốc độ ở tầng ứng dụng?
4. **Client mục tiêu:** Client là Java service, ứng dụng mobile, trình duyệt hay nhiều nền tảng? Thư viện có hỗ trợ transport và tính năng cần dùng không?
5. **Hạ tầng:** Load balancer, reverse proxy, firewall, service mesh và nền tảng triển khai có hỗ trợ kết nối dài, TCP hoặc WebSocket không?
6. **Hợp đồng và phiên bản:** Schema được quản lý bằng OpenAPI, Protocol Buffers hay DTO/serialization riêng? Làm thế nào để nâng cấp client và server độc lập?
7. **Phục hồi:** Khi mất kết nối, cần retry, reconnect, replay event hay resume? Có yêu cầu idempotency và acknowledgement nào?
8. **Bảo mật và quan sát:** Xác thực, authorization, tracing, metrics, log và giới hạn tài nguyên được thực hiện ở đâu?

Cuối cùng, không nên kết luận một protocol nhanh hơn chỉ dựa trên tên hoặc mô hình của nó. Độ trễ và throughput phụ thuộc kích thước payload, serialization, số lượng stream, tần suất message, mạng, cấu hình runtime và cách xử lý ở hai đầu. Hãy benchmark trên workload đại diện và đo cả latency, throughput, CPU, bộ nhớ, số kết nối, khả năng phục hồi cũng như độ phức tạp vận hành.

## 11. Kết luận

HTTP là nền tảng linh hoạt cho API request-response và tích hợp phổ thông. WebSocket cung cấp kênh hai chiều nhưng để ứng dụng tự định nghĩa protocol message. SSE giải quyết tốt luồng sự kiện một chiều từ server đến trình duyệt. gRPC bổ sung mô hình RPC có schema và hỗ trợ unary cùng nhiều kiểu streaming. RSocket cung cấp các kiểu tương tác bất đồng bộ được định nghĩa ở tầng protocol, multiplexing và backpressure cho stream, đồng thời có thể chạy trên TCP hoặc WebSocket.

Khi thiết kế hệ thống Java realtime, hãy bắt đầu từ mô hình tương tác và yêu cầu vận hành. Nếu cần request-channel, fire-and-forget, request-stream và điều tiết demand trong cùng một mô hình reactive, RSocket là một lựa chọn đáng thử nghiệm. Nếu nhu cầu đơn giản hơn, các công nghệ HTTP, SSE, WebSocket hoặc gRPC có thể đáp ứng với chi phí hệ thống thấp hơn.
