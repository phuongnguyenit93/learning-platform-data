# Bốn mô hình tương tác và cách chọn theo nhu cầu trao đổi dữ liệu

Trong module `INTEGRATION_REALTIME_RSOCKET`, chúng ta tìm hiểu RSocket như một giao thức giao tiếp bất đồng bộ, hai chiều và reactive, có thể chạy trên TCP hoặc WebSocket. Một kết nối RSocket có thể phục vụ nhiều luồng tương tác độc lập. Mỗi luồng bắt đầu từ một yêu cầu; tùy mô hình, luồng có thể trả dữ liệu, kết thúc hoặc phát sinh lỗi. Với luồng có phản hồi, requester cũng có thể hủy subscription khi không còn cần dữ liệu.

Điểm quan trọng khi thiết kế ứng dụng RSocket là chọn đúng mô hình tương tác. RSocket cung cấp bốn mô hình: **Request-Response**, **Fire-and-Forget**, **Request-Stream** và **Request-Channel**. Chúng khác nhau ở số lượng thông điệp được trao đổi và hướng dữ liệu di chuyển. Chọn đúng mô hình giúp API thể hiện rõ ý định, tận dụng backpressure và tránh tạo ra cơ chế xác nhận không cần thiết.

## 1. Hai vai trò trong một tương tác

Trong một tương tác RSocket, hai bên có vai trò:

- **Requester** là bên khởi tạo tương tác bằng cách gửi yêu cầu.
- **Responder** là bên nhận yêu cầu và xử lý nó; tùy mô hình, responder có thể gửi lại một hoặc nhiều payload.

Requester và responder là tên vai trò của một tương tác cụ thể. Trên cùng kết nối, một ứng dụng có thể khởi tạo tương tác này và đồng thời xử lý tương tác khác. Vì vậy, không nên hiểu RSocket là kết nối cố định theo kiểu một bên chỉ gửi và bên kia chỉ nhận.

Mỗi payload có thể mang dữ liệu ứng dụng và metadata. Với Spring Boot, metadata định tuyến thường được khai báo bằng `route(...)`, còn phương thức phía server được ánh xạ bằng `@MessageMapping`. Bốn mô hình dưới đây mô tả cách trao đổi payload; chúng không phụ thuộc vào việc kết nối sử dụng TCP hay WebSocket.

## 2. Bốn mô hình tương tác

### 2.1. Request-Response: một yêu cầu, tối đa một phản hồi

Requester gửi một payload và chờ tối đa một payload phản hồi từ responder. Tương tác có thể hoàn tất với một kết quả hoặc kết thúc mà không có payload. Trong Java reactive, phía gọi thường nhận một `Mono<T>`.

Mô hình này phù hợp khi bên gọi cần kết quả của một thao tác cụ thể, chẳng hạn tra cứu trạng thái đơn hàng, lấy thông tin hồ sơ hoặc yêu cầu máy chủ tính một giá trị.

```java
Mono<OrderStatus> status = requester
    .route("orders.status")
    .data(new OrderStatusQuery(orderId))
    .retrieveMono(OrderStatus.class);
```

Phía server có thể xử lý yêu cầu bằng một phương thức trả về `Mono`:

```java
@MessageMapping("orders.status")
public Mono<OrderStatus> status(OrderStatusQuery query) {
    return orderService.findStatus(query.orderId());
}
```

Không nên dùng Request-Response để mô phỏng một luồng dữ liệu liên tục bằng cách gọi lặp lại thật nhanh. Nếu mục tiêu là đăng ký nhận nhiều bản cập nhật, Request-Stream thường thể hiện đúng ý định hơn.

### 2.2. Fire-and-Forget: gửi một chiều, không chờ phản hồi ứng dụng

Requester gửi một payload và không yêu cầu responder trả payload kết quả. Mô hình này phù hợp với thông báo hoặc sự kiện mà bên gửi không cần biết kết quả xử lý ngay trong cùng tương tác, ví dụ gửi tín hiệu telemetry, ghi nhận một sự kiện phụ hoặc phát thông báo không yêu cầu xác nhận.

Với Spring `RSocketRequester`, phía client có thể gọi `send()`:

```java
Mono<Void> sendCompletion = requester
    .route("notifications.publish")
    .data(notification)
    .send();
```

Phía server có thể nhận và xử lý payload như sau:

```java
@MessageMapping("notifications.publish")
public Mono<Void> publish(Notification notification) {
    return notificationService.publish(notification);
}
```

`Mono<Void>` từ `send()` biểu thị thao tác gửi ở phía client đã hoàn tất theo API. Nó không phải phản hồi nghiệp vụ từ server và không chứng minh rằng server đã xử lý hoặc lưu bền vững sự kiện. Nếu người dùng cần biết lệnh đã được chấp nhận, cần mã kết quả hoặc cần xác nhận giao dịch đã commit, hãy dùng Request-Response hoặc một cơ chế xác nhận phù hợp.

Fire-and-Forget cũng không tự tạo ra hàng đợi bền vững. Nếu ứng dụng cần bảo đảm giao sự kiện qua thời điểm mất kết nối, cần thiết kế thêm lưu trữ, retry, định danh chống trùng hoặc dùng hệ thống messaging có khả năng lưu giữ thông điệp. Không nên dùng Fire-and-Forget cho thao tác thanh toán hay cập nhật dữ liệu quan trọng khi bên gọi cần biết kết quả.

### 2.3. Request-Stream: một yêu cầu, nhiều phản hồi

Requester gửi một payload để mô tả dữ liệu muốn nhận. Responder sau đó phát ra một luồng gồm không, một hoặc nhiều payload. Phía client thường nhận một `Flux<T>`.

Ví dụ, client đăng ký theo dõi giá của một mã cổ phiếu. Client chỉ cần gửi điều kiện đăng ký một lần; server gửi các bản cập nhật tiếp theo khi có dữ liệu:

```java
Flux<PriceTick> ticks = requester
    .route("prices.watch")
    .data(new PriceSubscription("ACME"))
    .retrieveFlux(PriceTick.class);
```

Phía server trả về một `Flux`:

```java
@MessageMapping("prices.watch")
public Flux<PriceTick> watch(PriceSubscription subscription) {
    return priceService.watch(subscription.symbol());
}
```

Request-Stream thích hợp cho bảng giá trực tiếp, trạng thái cảm biến, tiến độ xử lý, log theo dõi hoặc danh sách sự kiện mà server phát cho một client sau một yêu cầu đăng ký. Client có thể hủy subscription khi không còn cần dữ liệu; việc hủy được truyền về luồng để tài nguyên phía server có thể được giải phóng nếu publisher xử lý cancellation đúng cách.

Request-Stream là luồng một chiều sau yêu cầu khởi tạo: requester mô tả thứ mình muốn nhận, còn dữ liệu liên tục đi từ responder về requester. Nếu client cũng cần gửi nhiều thông điệp trong suốt phiên tương tác, hãy xem xét Request-Channel.

### 2.4. Request-Channel: nhiều thông điệp theo cả hai hướng

Requester khởi tạo một luồng đầu vào và đồng thời nhận một luồng đầu ra. Sau payload mở đầu, requester có thể tiếp tục gửi nhiều payload; responder cũng có thể phát nhiều payload về requester. Hai hướng có thể diễn ra đồng thời, và số lượng phản hồi không bắt buộc phải khớp một-một với số lượng yêu cầu.

Ví dụ, một client điều khiển phiên làm việc realtime liên tục gửi thao tác của người dùng và nhận trạng thái mới từ server:

```java
Flux<ClientSignal> clientSignals = signalSource.asFlux();

Flux<ServerUpdate> updates = requester
    .route("session.interact")
    .data(clientSignals)
    .retrieveFlux(ServerUpdate.class);
```

Phía server nhận một luồng tín hiệu và trả về một luồng cập nhật:

```java
@MessageMapping("session.interact")
public Flux<ServerUpdate> interact(Flux<ClientSignal> signals) {
    return signals.concatMap(sessionService::handle);
}
```

Đoạn xử lý trên minh họa chữ ký hai luồng: server nhận nhiều `ClientSignal` và phát nhiều `ServerUpdate`. Trong ứng dụng thực tế, luồng đầu ra cũng có thể kết hợp kết quả xử lý từng tín hiệu với các sự kiện realtime phát sinh độc lập từ server. `concatMap` được dùng khi cần xử lý tín hiệu tuần tự và giữ thứ tự kết quả; nếu nghiệp vụ cho phép xử lý song song, có thể cân nhắc toán tử khác nhưng phải xác định rõ yêu cầu về thứ tự.

Request-Channel phù hợp với phiên cộng tác, điều khiển thiết bị, trò chơi realtime, phiên tương tác trực tiếp hoặc giao diện mà client liên tục gửi thao tác trong khi server liên tục đẩy cập nhật. Nếu chỉ cần gửi một sự kiện một chiều, Request-Channel thường phức tạp hơn mức cần thiết.

## 3. So sánh nhanh để chọn mô hình

| Mô hình | Dữ liệu requester gửi | Dữ liệu responder gửi | Kiểu reactive thường gặp | Ví dụ phù hợp |
|---|---:|---:|---|---|
| Request-Response | Một yêu cầu | Tối đa một phản hồi | Yêu cầu → `Mono<Response>` | Tra cứu trạng thái đơn hàng |
| Fire-and-Forget | Một payload | Không có payload phản hồi | `send()` → `Mono<Void>` | Gửi telemetry không cần xác nhận |
| Request-Stream | Một yêu cầu khởi tạo | Một luồng phản hồi | Yêu cầu → `Flux<Response>` | Theo dõi giá hoặc cảm biến |
| Request-Channel | Một luồng payload | Một luồng payload | `Flux<Request>` → `Flux<Response>` | Phiên điều khiển hai chiều |

Có thể chọn theo ba câu hỏi sau:

1. **Bên gửi có cần kết quả nghiệp vụ không?** Nếu không cần phản hồi, Fire-and-Forget có thể phù hợp. Nếu cần phản hồi, tiếp tục xác định số lượng kết quả.
2. **Responder trả một kết quả hay phát nhiều kết quả theo thời gian?** Một kết quả phù hợp với Request-Response; nhiều kết quả phù hợp với Request-Stream.
3. **Requester có cần tiếp tục gửi dữ liệu trong khi đang nhận luồng phản hồi không?** Nếu có, chọn Request-Channel. Nếu requester chỉ gửi yêu cầu đăng ký ban đầu, Request-Stream đơn giản hơn.

| Nhu cầu thực tế | Mô hình nên cân nhắc | Lý do |
|---|---|---|
| Gửi lệnh và cần biết lệnh thành công hay thất bại | Request-Response | Có một kết quả nghiệp vụ để client xử lý |
| Phát một sự kiện không cần xác nhận ngay | Fire-and-Forget | Không cần mở luồng phản hồi |
| Đăng ký nhận các thay đổi từ server | Request-Stream | Một yêu cầu mở đầu, nhiều dữ liệu trả về |
| Vừa gửi thao tác liên tục vừa nhận cập nhật liên tục | Request-Channel | Hai phía đều có luồng dữ liệu |

## 4. Backpressure và vòng đời của luồng

RSocket được thiết kế để làm việc với Reactive Streams. Với Request-Stream và Request-Channel, bên nhận dữ liệu có thể biểu thị nhu cầu bằng số lượng phần tử muốn nhận. Trong giao thức, cơ chế này được thể hiện qua các thông điệp `REQUEST_N`; publisher phía gửi chỉ nên phát dữ liệu theo lượng demand đã được cấp. Nhờ đó, một client xử lý chậm có thể điều tiết tốc độ dữ liệu đi vào thay vì buộc server đẩy vô hạn.

Trong Request-Channel, hai hướng có nhu cầu độc lập. Client có thể yêu cầu số lượng cập nhật server gửi về, đồng thời server cũng quan sát nhu cầu đối với các tín hiệu client gửi lên. Khi triển khai, cần chú ý các điểm sau:

- Không biến một luồng có tốc độ cao thành bộ đệm vô hạn. Nếu cần buffer, hãy giới hạn kích thước và xác định cách xử lý khi buffer đầy.
- Chọn toán tử reactive theo yêu cầu về thứ tự và mức độ song song. `concatMap` giữ thứ tự xử lý; `flatMap` cho phép các tác vụ chạy đồng thời và kết quả có thể đến khác thứ tự đầu vào.
- Hủy subscription khi người dùng rời màn hình hoặc phiên làm việc kết thúc để dừng công việc không còn cần thiết.
- Fire-and-Forget không có luồng phản hồi để điều tiết công việc nghiệp vụ. Nếu producer có thể gửi nhanh hơn khả năng xử lý của server, cần giới hạn tốc độ, gom lô, dùng hàng đợi có giới hạn hoặc chọn cơ chế có xác nhận.

Backpressure chỉ phát huy tác dụng khi các publisher và subscriber trong chuỗi xử lý tôn trọng Reactive Streams. Một thành phần tự tạo bộ đệm không giới hạn hoặc bỏ qua demand vẫn có thể làm ứng dụng tiêu thụ quá nhiều bộ nhớ.

## 5. Lỗi, retry và phục hồi kết nối

Với Request-Response, lỗi xử lý thường được chuyển thành tín hiệu lỗi của `Mono`. Với Request-Stream và Request-Channel, lỗi kết thúc luồng tương ứng; client cần quyết định hiển thị lỗi, kết thúc phiên hay thử lại. Khi client hủy luồng, responder nên dừng công việc liên quan nếu có thể.

Fire-and-Forget không cung cấp payload phản hồi để client nhận lỗi nghiệp vụ từ handler. Vì vậy, những tác vụ cần kiểm tra kết quả phải có đường quan sát khác, chẳng hạn log có correlation ID, trạng thái truy vấn được bằng Request-Response hoặc một thông điệp xác nhận riêng.

Retry cần được thiết kế cùng tính idempotent. Nếu client gửi lại một yêu cầu sau khi mất kết nối, server có thể đã xử lý yêu cầu trước đó nhưng phản hồi chưa đến client. Với lệnh làm thay đổi dữ liệu, nên dùng idempotency key hoặc mã sự kiện để tránh áp dụng cùng một tác động nhiều lần.

Khả năng kết nối lại và khả năng tiếp tục một luồng đang chạy là hai vấn đề khác nhau. RSocket có cơ chế Resume, nhưng ứng dụng phải cấu hình và duy trì trạng thái cần thiết; không nên giả định rằng chỉ cần mở lại TCP hoặc WebSocket là mọi luồng trước đó tự tiếp tục. Cần xác định rõ hành vi khi mất kết nối: tạo subscription mới, truy vấn lại trạng thái, phát lại từ sequence number hay dùng cơ chế resume đã cấu hình.

## 6. Những nhầm lẫn thường gặp

- **Dùng Fire-and-Forget cho lệnh cần xác nhận:** client không nhận được kết quả nghiệp vụ trong tương tác đó. Hãy dùng Request-Response nếu cần biết lệnh đã được chấp nhận hoặc hoàn tất.
- **Dùng Request-Response để polling liên tục:** mỗi lần polling tạo một tương tác mới. Nếu server có thể phát thay đổi theo thời gian, Request-Stream thường phù hợp hơn.
- **Dùng Request-Stream khi hai phía đều cần gửi dữ liệu liên tục:** Request-Stream chỉ có một luồng phản hồi sau yêu cầu khởi tạo. Hãy cân nhắc Request-Channel.
- **Dùng Request-Channel cho một yêu cầu đơn giản:** một luồng hai chiều làm tăng độ phức tạp quản lý vòng đời. Request-Response thường dễ hiểu hơn nếu chỉ cần một kết quả.
- **Cho rằng `send()` đồng nghĩa dữ liệu đã được lưu:** hoàn tất thao tác gửi không phải xác nhận commit từ server. Nếu cần bảo đảm nghiệp vụ, hãy thiết kế phản hồi hoặc cơ chế xác nhận riêng.

## 7. Kết luận

Hãy chọn mô hình dựa trên số lượng payload và hướng trao đổi dữ liệu: Request-Response cho một yêu cầu cần một kết quả; Fire-and-Forget cho một payload không cần phản hồi ứng dụng; Request-Stream cho một yêu cầu mở đầu và nhiều phản hồi; Request-Channel cho hai luồng dữ liệu cùng tồn tại theo hai hướng. Sau khi chọn mô hình, hãy thiết kế thêm backpressure, xử lý lỗi, hủy luồng, retry và phục hồi kết nối theo yêu cầu của nghiệp vụ realtime.
