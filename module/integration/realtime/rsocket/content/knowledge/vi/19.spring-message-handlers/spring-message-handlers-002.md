# Thiết kế route, tiền tố ở cấp lớp và biến đường dẫn

Trong Spring RSocket, route là metadata giúp server chọn phương thức xử lý cho một tương tác. `@MessageMapping` khai báo route ở cấp controller hoặc phương thức; `@DestinationVariable` lấy giá trị từ các biến trong route. Khi thiết kế route có quy ước rõ ràng, ứng dụng có thể tổ chức handler theo tài nguyên, giữ tên route nhất quán và ánh xạ chính xác bốn interaction model của RSocket.

Module `INTEGRATION_REALTIME_RSOCKET` tập trung vào giao tiếp bất đồng bộ, hai chiều và reactive qua TCP hoặc WebSocket. Transport không làm thay đổi cách định tuyến ở tầng Spring: client gửi route trong metadata, còn Spring tìm handler phù hợp và chuyển payload vào tham số phương thức.

## 1. Route nằm trong metadata của RSocket

Một request RSocket thường mang payload và metadata. Với Spring RSocket, route được truyền dưới dạng metadata theo MIME type định tuyến của RSocket. Server sử dụng route để tìm handler được khai báo bằng `@MessageMapping`.

Ví dụ một route có thể là:

```text
devices.device-42.status.get
```

Có thể đọc route theo từng phần:

| Phần | Ý nghĩa |
|---|---|
| `devices` | Nhóm tài nguyên hoặc miền nghiệp vụ. |
| `device-42` | Định danh thiết bị cụ thể. |
| `status` | Nhóm thao tác. |
| `get` | Hành động cần thực hiện. |

Route là địa chỉ logic của handler; nó không phải URL HTTP và không quyết định transport TCP hay WebSocket. Với RSocket, client có thể gọi cùng route qua hai transport khác nhau nếu hai phía đã thiết lập kết nối và cấu hình mapping tương ứng.

## 2. Khai báo route bằng @MessageMapping

`@MessageMapping` có thể đặt ở cấp lớp và cấp phương thức:

- Mapping cấp lớp tạo tiền tố dùng chung cho các handler trong controller.
- Mapping cấp phương thức chỉ ra route cụ thể của handler.
- Khi kết hợp hai cấp, route hoàn chỉnh gồm tiền tố lớp và phần route của phương thức.

Ví dụ:

```java
@Controller
@MessageMapping("devices")
public class DeviceController {

    @MessageMapping("status.get")
    public Mono<DeviceStatus> getStatus(StatusQuery query) {
        // xử lý truy vấn trạng thái
        return deviceService.getStatus(query.deviceId());
    }
}
```

Handler trên được ánh xạ tới route `devices.status.get`. Tiền tố `devices` giúp các phương thức trong controller có chung một namespace. Khi module có nhiều nhóm tài nguyên, có thể tách controller theo miền như `devices`, `telemetry` hoặc `sessions`.

Nếu route cấp lớp chứa biến, biến đó có thể được sử dụng trong phương thức:

```java
@Controller
@MessageMapping("devices.{deviceId}")
public class DeviceController {

    @MessageMapping("status.get")
    public Mono<DeviceStatus> getStatus(
            @DestinationVariable("deviceId") String deviceId,
            @Payload StatusQuery query) {
        return deviceService.getStatus(deviceId, query);
    }
}
```

Route hoàn chỉnh là `devices.device-42.status.get`. Spring lấy phần `device-42` và đưa vào tham số `deviceId` thông qua `@DestinationVariable`. `@Payload` đánh dấu tham số chứa nội dung nghiệp vụ của request.

## 3. Biến đường dẫn với @DestinationVariable

Biến route được đặt trong dấu ngoặc nhọn, ví dụ `{deviceId}`. Handler khai báo biến bằng `@DestinationVariable`; nên chỉ rõ tên biến để code dễ đọc và không phụ thuộc vào việc compiler giữ tên tham số.

```java
@MessageMapping("{deviceId}.telemetry.watch")
public Flux<TelemetryReading> watch(
        @DestinationVariable("deviceId") String deviceId,
        @Payload WatchRequest request) {
    return telemetryService.watch(deviceId, request.from());
}
```

Nếu controller có tiền tố `@MessageMapping("devices")`, route hoàn chỉnh sẽ là `devices.{deviceId}.telemetry.watch`.

Biến route phù hợp với giá trị định danh nằm trong địa chỉ logic, chẳng hạn `deviceId`, `sessionId` hoặc `tenantKey`. Payload phù hợp với nội dung nghiệp vụ có cấu trúc như bộ lọc, khoảng thời gian hoặc lệnh. Không nên đưa toàn bộ dữ liệu request vào route; route nên ngắn, ổn định và dễ quản lý.

Khi dùng biến route, cần kiểm tra:

- Giá trị biến có tồn tại và đúng định dạng không.
- Định danh có thuộc principal/tenant đã xác thực không.
- Giá trị có được phép truy cập hay không; biết `deviceId` không đồng nghĩa có quyền điều khiển thiết bị.
- Các route pattern có bị chồng lấn hoặc tạo mapping mơ hồ không.

## 4. Quy ước tổ chức route

Một convention hữu ích là đặt tên theo thứ tự **tài nguyên → định danh → nhóm thao tác → hành động**. Ví dụ:

| Interaction model | Route gợi ý | Ý nghĩa |
|---|---|---|
| Request-Response | `devices.{deviceId}.status.get` | Lấy trạng thái hiện tại của một thiết bị. |
| Fire-and-Forget | `devices.{deviceId}.telemetry.publish` | Gửi một mẫu đo không cần phản hồi ứng dụng. |
| Request-Stream | `devices.{deviceId}.telemetry.watch` | Đăng ký nhận nhiều bản cập nhật. |
| Request-Channel | `devices.{deviceId}.control.channel` | Gửi nhiều lệnh và nhận nhiều trạng thái trong cùng phiên. |

Nên giữ các nguyên tắc sau:

- Dùng một kiểu phân cách nhất quán. Trong ví dụ Spring RSocket, route được viết theo các segment phân cách bằng dấu chấm.
- Dùng tên hành động thể hiện ý định như `get`, `publish`, `watch` hoặc `channel`.
- Tránh route quá tổng quát như `data` hoặc `process`, vì khó phân quyền, theo dõi và phát triển phiên bản.
- Không gắn thông tin thay đổi liên tục như timestamp hoặc sequence number vào route; đặt chúng trong payload.
- Tránh khai báo nhiều handler có cùng route hoàn chỉnh. Dùng route riêng cho từng thao tác và từng interaction model để mapping rõ ràng.
- Xem route là một phần hợp đồng API; thay đổi tên route cần được quản lý tương thích giữa client và server.

## 5. Ánh xạ bốn interaction model vào handler

Spring sử dụng hình dạng dữ liệu vào và kiểu trả về reactive để ánh xạ tương tác. Route xác định handler; interaction model được requester khởi tạo ở phía client và được thể hiện ở chữ ký phương thức phía server.

| Interaction model | Client gửi | Server nhận | Server trả |
|---|---|---|---|
| Request-Response | Một payload | Một đối tượng request | `Mono<Response>` |
| Fire-and-Forget | Một payload | Một đối tượng event/command | `Mono<Void>` hoặc `void` |
| Request-Stream | Một payload mở đầu | Một đối tượng request | `Flux<Response>` |
| Request-Channel | Một luồng payload | `Flux<Request>` | `Flux<Response>` |

Ví dụ dưới đây gom bốn handler trong một controller dùng chung tiền tố `devices.{deviceId}`:

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
@MessageMapping("devices.{deviceId}")
public class DeviceRSocketController {

    private final DeviceService deviceService;
    private final TelemetryService telemetryService;

    public DeviceRSocketController(
            DeviceService deviceService,
            TelemetryService telemetryService) {
        this.deviceService = deviceService;
        this.telemetryService = telemetryService;
    }

    // Request-Response: một request, tối đa một response
    @MessageMapping("status.get")
    public Mono<DeviceStatus> getStatus(
            @DestinationVariable("deviceId") String deviceId,
            @Payload StatusQuery query) {
        return deviceService.getStatus(deviceId, query);
    }

    // Fire-and-Forget: một event, không có response payload
    @MessageMapping("telemetry.publish")
    public Mono<Void> publishTelemetry(
            @DestinationVariable("deviceId") String deviceId,
            @Payload TelemetryEvent event) {
        return telemetryService.accept(deviceId, event);
    }

    // Request-Stream: một request mở đầu, nhiều response
    @MessageMapping("telemetry.watch")
    public Flux<TelemetryReading> watchTelemetry(
            @DestinationVariable("deviceId") String deviceId,
            @Payload WatchRequest request) {
        return telemetryService.watch(deviceId, request);
    }

    // Request-Channel: nhiều request và nhiều response
    @MessageMapping("control.channel")
    public Flux<DeviceUpdate> control(
            @DestinationVariable("deviceId") String deviceId,
            @Payload Flux<DeviceCommand> commands) {
        return commands.concatMap(command ->
            deviceService.apply(deviceId, command)
        );
    }
}
```

Các kiểu `StatusQuery`, `TelemetryEvent`, `WatchRequest`, `DeviceCommand`, `DeviceStatus`, `TelemetryReading` và `DeviceUpdate` là DTO của ứng dụng. Controller trả publisher do service cung cấp để Spring/RSocket quản lý subscription, demand và cancellation. Với Request-Channel, tham số `Flux<DeviceCommand>` thể hiện luồng đầu vào, còn `Flux<DeviceUpdate>` là luồng phản hồi.

### 5.1. Request-Response

Client gửi một payload và nhận tối đa một kết quả:

```java
Mono<DeviceStatus> status = requester
    .route("devices.{deviceId}.status.get", deviceId)
    .data(new StatusQuery())
    .retrieveMono(DeviceStatus.class);
```

Handler trả `Mono<DeviceStatus>`. Dùng mô hình này cho truy vấn hoặc lệnh cần một kết quả nghiệp vụ rõ ràng.

### 5.2. Fire-and-Forget

Client gửi một payload và không yêu cầu response payload:

```java
Mono<Void> sent = requester
    .route("devices.{deviceId}.telemetry.publish", deviceId)
    .data(event)
    .send();
```

Handler trả `Mono<Void>` để biểu diễn công việc bất đồng bộ phía server. `send()` hoàn tất ở client không xác nhận server đã lưu hoặc xử lý thành công event. Nếu cần xác nhận nghiệp vụ, dùng Request-Response hoặc một cơ chế receipt riêng.

### 5.3. Request-Stream

Client gửi một payload mô tả subscription và nhận nhiều phần tử:

```java
Flux<TelemetryReading> readings = requester
    .route("devices.{deviceId}.telemetry.watch", deviceId)
    .data(new WatchRequest(fromTime))
    .retrieveFlux(TelemetryReading.class);
```

Handler nhận một `WatchRequest` và trả `Flux<TelemetryReading>`. Đây là lựa chọn phù hợp cho dữ liệu cảm biến hoặc trạng thái thay đổi theo thời gian.

### 5.4. Request-Channel

Client gửi một publisher và đồng thời nhận một luồng phản hồi:

```java
Flux<DeviceCommand> commands = commandSource.commands();

Flux<DeviceUpdate> updates = requester
    .route("devices.{deviceId}.control.channel", deviceId)
    .data(commands, DeviceCommand.class)
    .retrieveFlux(DeviceUpdate.class);
```

Handler nhận `Flux<DeviceCommand>` và trả `Flux<DeviceUpdate>`. Hai hướng có demand độc lập. `concatMap` trong ví dụ giữ thứ tự xử lý lệnh; nếu dùng `flatMap`, cần giới hạn concurrency và chấp nhận kết quả có thể không theo thứ tự đầu vào.

## 6. Route template ở phía RSocketRequester

`RSocketRequester.route(...)` nhận route template và các giá trị route variable. Các giá trị được truyền theo thứ tự xuất hiện của biến trong template:

```java
requester.route("devices.{deviceId}.telemetry.watch", deviceId)
```

Nếu route có nhiều biến, thứ tự đối số phải khớp thứ tự khai báo:

```java
requester.route(
    "tenants.{tenantId}.devices.{deviceId}.status.get",
    tenantId,
    deviceId
)
```

Phía server nhận các giá trị tương ứng bằng `@DestinationVariable("tenantId")` và `@DestinationVariable("deviceId")`. Không tự nối chuỗi thủ công nếu API hỗ trợ route template; dùng template giúp code thể hiện rõ vị trí biến và tránh lỗi định dạng route.

Route variable là dữ liệu đầu vào không đáng tin cậy. Server vẫn phải xác thực định dạng, kiểm tra quyền truy cập và xác nhận định danh thuộc tenant hiện tại. Không dùng route variable làm bằng chứng xác thực.

## 7. Phân biệt route, payload và metadata khác

Một thông điệp RSocket có thể mang nhiều loại thông tin:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Route | Chọn handler | `devices.device-42.status.get` |
| Payload data | Nội dung nghiệp vụ | `StatusQuery`, `TelemetryEvent` |
| Metadata khác | Thông tin bổ sung theo hợp đồng | MIME type, tracing context hoặc authentication metadata |
| Stream ID | Định danh tương tác ở tầng giao thức | Một ID do RSocket quản lý cho mỗi stream |

Không đưa dữ liệu nghiệp vụ lớn vào route. Không nhầm `deviceId` trong route với Stream ID: route là metadata định tuyến ở tầng ứng dụng, còn Stream ID là định danh do giao thức RSocket sử dụng để ghép các frame của tương tác.

## 8. Xử lý lỗi và kiểm soát truy cập ở handler

Route mapping chỉ chọn phương thức; handler vẫn cần kiểm tra đầu vào và quyền thực hiện. Một route hợp lệ không có nghĩa payload hợp lệ hoặc caller có quyền truy cập tài nguyên.

- Kiểm tra `deviceId` có tồn tại và thuộc tenant của principal đã xác thực.
- Validate payload trước khi gọi service; giới hạn kích thước và giá trị trường.
- Trả lỗi theo semantics của interaction model. Request-Response có thể phát lỗi cho request; Request-Stream/Channel có thể kết thúc stream bằng lỗi; Fire-and-Forget không có response payload để trả lỗi nghiệp vụ về requester.
- Gắn correlation ID vào log/trace để theo dõi một request hoặc channel.
- Với Request-Channel, hủy publisher upstream khi stream bị cancel và không giữ tác vụ theo phiên sau khi requester đã rời đi, trừ khi công việc được thiết kế là durable job.

Không dùng cùng một route cho các handler có chữ ký khác nhau chỉ với hy vọng Spring sẽ tự chọn theo interaction model. Hãy đặt route riêng cho từng hành động, như `status.get`, `telemetry.publish`, `telemetry.watch` và `control.channel`, rồi kiểm thử mapping trên đúng phiên bản Spring Framework.

## 9. Kiểm thử route và handler mapping

Các ca kiểm thử nên xác nhận route hoàn chỉnh và interaction model, không chỉ gọi trực tiếp phương thức Java:

1. Gửi route `devices.device-42.status.get`; xác nhận handler Request-Response nhận đúng `deviceId` và payload.
2. Gửi `devices.device-42.telemetry.publish`; xác nhận handler Fire-and-Forget được gọi và không phát response payload.
3. Gửi `devices.device-42.telemetry.watch`; xác nhận client nhận nhiều phần tử và cancellation dừng publisher khi client hủy.
4. Mở `devices.device-42.control.channel`; xác nhận nhiều lệnh được nhận, nhiều cập nhật được trả và demand được tôn trọng.
5. Gửi route thiếu segment hoặc sai tên; xác nhận không ánh xạ nhầm sang handler khác.
6. Gửi route variable không hợp lệ hoặc thuộc tenant khác; xác nhận validation/authorization từ chối.
7. Tạo hai mapping có thể trùng pattern; xác nhận ứng dụng phát hiện xung đột thay vì chọn handler ngoài ý muốn.
8. Kiểm tra route qua cả TCP và WebSocket nếu ứng dụng hỗ trợ hai transport.

Trong test tích hợp, dùng `RSocketRequester` thật để kiểm tra metadata route được mã hóa và giải mã đúng. Kiểm tra riêng payload, route variable, lỗi, backpressure và cancellation để phát hiện sai khác giữa chữ ký handler và interaction model client khởi tạo.

## 10. Kết luận

`@MessageMapping` cấp lớp giúp tạo tiền tố route chung; `@MessageMapping` cấp phương thức bổ sung phần route cụ thể; `@DestinationVariable` ánh xạ các segment nằm trong `{...}` vào tham số handler. Hãy đặt route theo convention ổn định và dùng route riêng cho từng hành động. Request-Response thường nhận một payload và trả `Mono<T>`; Fire-and-Forget nhận một payload và trả `Mono<Void>`; Request-Stream nhận một payload và trả `Flux<T>`; Request-Channel nhận `Flux<T>` và trả `Flux<R>`. Kết hợp route rõ ràng với kiểm tra quyền, validation và test tích hợp để các handler Spring ánh xạ đúng giao tiếp realtime.
