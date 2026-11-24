# Đọc biến route bằng `@DestinationVariable`

Trong Spring RSocket, một route xác định handler sẽ nhận tương tác. Route có thể chứa các biến nằm trong dấu ngoặc nhọn, chẳng hạn `orders.{orderId}.events`. Annotation `@DestinationVariable` cho phép handler lấy giá trị của những biến này thành tham số Java có kiểu rõ ràng.

Biến route hữu ích khi một tương tác nhắm đến một tài nguyên hoặc một nhóm dữ liệu cụ thể: mã đơn hàng, mã thiết bị, tenant hoặc người dùng. Chúng nằm trong metadata định tuyến của RSocket, tách biệt với phần data chứa nội dung nghiệp vụ và metadata tùy chỉnh khác.

## 1. Route template và biến route

Trong Spring Messaging, `@MessageMapping` khai báo mẫu đích mà handler xử lý. Với RSocket, giá trị route được truyền trong routing metadata của request. Mẫu route có thể chứa các phần cố định và biến:

```java
@Controller
public class OrderController {

    @MessageMapping("orders.{orderId}.summary")
    public Mono<OrderSummary> summary(
            @DestinationVariable("orderId") UUID orderId) {
        return orderService.findSummary(orderId);
    }
}
```

Trong mẫu trên:

- `orders` là phần cố định của route.
- `{orderId}` là biến route.
- `summary` là phần cố định cuối cùng.
- `@DestinationVariable("orderId")` yêu cầu Spring lấy giá trị đã khớp với `{orderId}` và truyền vào tham số `UUID`.

Route template giúp một handler phục vụ nhiều giá trị khác nhau. Thay vì tạo một handler riêng cho từng đơn hàng, cùng một mapping có thể xử lý `orders.100.summary`, `orders.200.summary` và những route hợp lệ khác.

## 2. Gửi route variable từ RSocketRequester

Ở phía requester, dùng `RSocketRequester.route(...)` để chọn route. Các giá trị biến được truyền theo thứ tự xuất hiện trong template:

```java
Mono<OrderSummary> summary = requester
    .route("orders.{orderId}.summary", orderId)
    .data(new SummaryOptions(true))
    .retrieveMono(OrderSummary.class);
```

`route(...)` tạo routing metadata cho request. `data(...)` cung cấp payload nghiệp vụ; `retrieveMono(...)` cho biết caller mong đợi tối đa một response. Spring xử lý việc định dạng route và mã hóa metadata, vì vậy ứng dụng không cần tự xây dựng Composite Metadata chỉ để truyền biến route.

Nếu route có nhiều biến, truyền các giá trị theo đúng thứ tự:

```java
Flux<DeviceEvent> events = requester
    .route("tenants.{tenantId}.devices.{deviceId}.events",
        tenantId, deviceId)
    .data(new EventFilter("temperature"))
    .retrieveFlux(DeviceEvent.class);
```

Template có hai biến nên `tenantId` là giá trị thứ nhất và `deviceId` là giá trị thứ hai. Giữ thứ tự này nhất quán giữa template và các đối số giúp tránh định tuyến nhầm tài nguyên.

## 3. Bind biến route trong handler

`@DestinationVariable` nằm trong package `org.springframework.messaging.handler.annotation`. Có thể khai báo tên biến rõ ràng:

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class DeviceController {

    private final DeviceService deviceService;

    public DeviceController(DeviceService deviceService) {
        this.deviceService = deviceService;
    }

    @MessageMapping("devices.{deviceId}.status")
    public Mono<DeviceStatus> status(
            @DestinationVariable("deviceId") UUID deviceId) {
        return deviceService.getStatus(deviceId);
    }
}
```

Khi request có route `devices.8a2...status`, Spring tìm handler có mẫu tương ứng, lấy phần khớp với `{deviceId}` rồi bind vào tham số. Nếu chuyển đổi sang `UUID` thành công, handler nhận một `UUID` thay vì phải tự cắt chuỗi route.

Tên trong annotation phải khớp với tên biến trong template. Ví dụ `{deviceId}` đi với `@DestinationVariable("deviceId")`. Nếu tên không khớp, Spring không thể lấy đúng giá trị đã khớp.

### Có thể bỏ tên trong annotation không?

Có thể viết `@DestinationVariable UUID deviceId` khi Spring có thể khám phá tên tham số Java từ metadata biên dịch. Tuy nhiên, tên tham số có thể không được giữ lại nếu project không biên dịch với tùy chọn lưu parameter names. Ghi rõ tên trong annotation giúp mapping ổn định và dễ đọc hơn:

```java
public Mono<DeviceStatus> status(
        @DestinationVariable("deviceId") UUID id) {
    return deviceService.getStatus(id);
}
```

Tên biến Java có thể là `id`; giá trị trong annotation vẫn phải là `deviceId` theo template route.

## 4. Biến route có kiểu dữ liệu

Giá trị trong route được truyền qua metadata dưới dạng dữ liệu định tuyến dạng chuỗi. Spring dùng cơ chế chuyển đổi tham số để bind vào kiểu Java mà handler khai báo, nếu có converter phù hợp.

Các kiểu thường dùng:

| Kiểu tham số | Ví dụ giá trị route | Lưu ý |
|---|---|---|
| `String` | `devices.sensor-17.status` | Phù hợp với mã định danh dạng chuỗi. |
| `Long` hoặc `long` | `orders.1024.summary` | Giá trị phải chuyển đổi được thành số nguyên dài. |
| `Integer` hoặc `int` | `zones.12.readings` | Phù hợp với mã số trong phạm vi `int`. |
| `UUID` | `users.550e8400-e29b-41d4-a716-446655440000.profile` | Giá trị phải đúng định dạng UUID. |
| `Enum` | `devices.sensor-17.mode.AUTO` | Cần converter/format phù hợp với cách biểu diễn enum trong route. |

Ví dụ với nhiều kiểu:

```java
@MessageMapping("tenants.{tenantId}.orders.{orderId}")
public Mono<Order> getOrder(
        @DestinationVariable("tenantId") UUID tenantId,
        @DestinationVariable("orderId") long orderId) {
    return orderService.find(tenantId, orderId);
}
```

Nếu route chứa `tenants.not-a-uuid.orders.abc`, việc chuyển đổi có thể thất bại trước khi method được gọi. Hãy xác định rõ định dạng route mà requester phải gửi và xử lý lỗi chuyển đổi ở ranh giới message handling.

Với kiểu miền riêng, có thể đăng ký `Converter<String, T>` hoặc `ConverterFactory` trong conversion service phù hợp của ứng dụng. Không nên parse thủ công cùng một loại identifier ở nhiều handler khác nhau.

## 5. Kết hợp route variable với payload

Route variable và payload giải quyết hai mục đích khác nhau:

- Route variable chọn đích hoặc tài nguyên mà request hướng tới.
- Payload chứa nội dung nghiệp vụ cần xử lý tại đích đó.

Ví dụ client yêu cầu danh sách sự kiện của một thiết bị từ một thời điểm:

```java
Flux<DeviceEvent> events = requester
    .route("devices.{deviceId}.events", deviceId)
    .data(new EventQuery(from, to, 100))
    .retrieveFlux(DeviceEvent.class);
```

Handler nhận hai nguồn dữ liệu riêng:

```java
@MessageMapping("devices.{deviceId}.events")
public Flux<DeviceEvent> events(
        @DestinationVariable("deviceId") UUID deviceId,
        EventQuery query) {
    return eventService.findEvents(deviceId, query);
}
```

`deviceId` đến từ route; `EventQuery` đến từ data payload và được Spring chuyển đổi qua message codec. Không cần đưa `deviceId` lặp lại trong body nếu route đã là nguồn định danh chính của request, trừ khi hợp đồng nghiệp vụ yêu cầu kiểm tra hai giá trị nhất quán.

## 6. Nhiều biến route trong một handler

Một route có thể chứa nhiều biến ở các vị trí khác nhau. Mỗi biến được bind bằng một tham số `@DestinationVariable` riêng:

```java
@MessageMapping("tenants.{tenantId}.devices.{deviceId}.commands")
public Mono<CommandResult> sendCommand(
        @DestinationVariable("tenantId") UUID tenantId,
        @DestinationVariable("deviceId") UUID deviceId,
        DeviceCommand command) {

    return deviceService.sendCommand(tenantId, deviceId, command);
}
```

Requester tương ứng:

```java
Mono<CommandResult> result = requester
    .route("tenants.{tenantId}.devices.{deviceId}.commands",
        tenantId, deviceId)
    .data(new DeviceCommand("reboot"))
    .retrieveMono(CommandResult.class);
```

Giữ template route ở một nơi dùng chung nếu client và server cùng project hoặc cùng chia sẻ hợp đồng API. Điều này giảm lỗi sai tên biến, sai thứ tự tham số và sai chính tả route khi refactor.

## 7. Dùng biến route với các kiểu tương tác RSocket

`@DestinationVariable` chỉ làm nhiệm vụ bind biến từ route; nó không giới hạn handler vào một kiểu tương tác cụ thể. Kiểu trả về của handler biểu diễn response:

| Kiểu handler | Tương tác thường dùng | Ví dụ |
|---|---|---|
| `Mono<T>` | Request-response | Lấy trạng thái một thiết bị. |
| `Flux<T>` | Request-stream | Theo dõi sự kiện của một thiết bị. |
| `Mono<Void>` | Fire-and-forget | Gửi lệnh không cần response payload. |
| `Flux<T>` nhận một `Flux<Command>` | Request-channel | Nhận chuỗi lệnh và trả chuỗi cập nhật. |

Ví dụ request-stream:

```java
@MessageMapping("devices.{deviceId}.telemetry")
public Flux<Telemetry> telemetry(
        @DestinationVariable("deviceId") UUID deviceId,
        TelemetryFilter filter) {
    return telemetryService.stream(deviceId, filter);
}
```

Ví dụ request-channel:

```java
@MessageMapping("devices.{deviceId}.control")
public Flux<ControlUpdate> control(
        @DestinationVariable("deviceId") UUID deviceId,
        Flux<ControlCommand> commands) {
    return controlService.handle(deviceId, commands);
}
```

Trong cả hai trường hợp, route variable được xác định khi tương tác được mở. Các payload tiếp theo của stream/channel thuộc cùng tương tác; client không gửi lại route cho từng phần tử.

## 8. Khác biệt giữa DestinationVariable, Payload và Header

Spring có các annotation cho những nguồn dữ liệu khác nhau trong message:

| Annotation/Tham số | Nguồn dữ liệu | Dùng khi |
|---|---|---|
| `@DestinationVariable` | Biến được trích từ route template | Chọn tài nguyên/đích như `deviceId`, `tenantId`. |
| `@Payload` | Data payload sau khi message codec chuyển đổi | Nhận DTO hoặc nội dung nghiệp vụ. |
| `@Header` | Một header/metadata đã được extractor ánh xạ | Nhận trace ID, correlation ID hoặc metadata tùy chỉnh. |
| `@Headers` | Tập hợp message headers | Cần đọc nhiều header đã được ánh xạ. |

Ví dụ kết hợp:

```java
@MessageMapping("tenants.{tenantId}.orders.{orderId}.events")
public Flux<OrderEvent> events(
        @DestinationVariable("tenantId") UUID tenantId,
        @DestinationVariable("orderId") long orderId,
        @Header("traceId") String traceId,
        @Payload EventFilter filter) {

    return orderService.events(tenantId, orderId, filter, traceId);
}
```

`@Header` chỉ hoạt động khi metadata tương ứng đã được giải mã/ánh xạ vào message headers, ví dụ qua cấu hình metadata extractor. Không nhầm một biến route với custom metadata: route thuộc routing metadata, còn metadata tùy chỉnh cần MIME type và decoder/extractor tương ứng.

## 9. Route không khớp và lỗi chuyển đổi

Có hai nhóm lỗi cần phân biệt:

**Không tìm được handler phù hợp:** route gửi lên không khớp mapping hoặc thiếu/thừa segment cần thiết. Khi đó method có `@DestinationVariable` không được gọi. Cần kiểm tra route template, separator, wildcard và route thực tế mà requester tạo.

**Route khớp nhưng bind tham số thất bại:** route được chọn nhưng giá trị không chuyển đổi được sang kiểu tham số. Ví dụ `{orderId}` nhận chuỗi `abc` trong khi handler yêu cầu `long`. Method có thể không được gọi vì lỗi xảy ra trong bước resolve argument.

Ví dụ route hợp lệ:

```text
orders.1024.summary
```

Ví dụ route không hợp lệ với kiểu `long`:

```text
orders.not-a-number.summary
```

Nên kiểm thử hai trường hợp riêng. Lỗi không khớp route thường liên quan đến mapping; lỗi chuyển đổi liên quan đến dữ liệu biến và conversion service.

## 10. Validation và kiểm soát truy cập

Bind thành công chỉ có nghĩa giá trị chuyển đổi được sang kiểu Java. Nó không chứng minh rằng giá trị hợp lệ về nghiệp vụ hoặc caller có quyền truy cập tài nguyên đó.

Ví dụ kiểm tra quyền truy cập:

```java
@MessageMapping("tenants.{tenantId}.devices.{deviceId}.status")
public Mono<DeviceStatus> status(
        @DestinationVariable("tenantId") UUID tenantId,
        @DestinationVariable("deviceId") UUID deviceId,
        Principal principal) {

    return authorizationService
        .canReadDevice(principal, tenantId, deviceId)
        .filter(Boolean::booleanValue)
        .switchIfEmpty(Mono.error(new AccessDeniedException("Forbidden")))
        .then(deviceService.getStatus(tenantId, deviceId));
}
```

Đây là ví dụ minh họa luồng kiểm tra; kiểu `Principal` và cách cung cấp identity phụ thuộc cấu hình xác thực của ứng dụng. Hãy bảo đảm thông tin principal đến từ cơ chế bảo mật đáng tin cậy, không lấy quyền từ một route variable do client tự chọn.

Các nguyên tắc cần giữ:

1. Xác thực caller độc lập với giá trị route.
2. Kiểm tra caller có quyền trên đúng tenant và tài nguyên đã bind.
3. Không coi UUID khó đoán là cơ chế phân quyền.
4. Giới hạn độ dài và định dạng của các segment route nếu ứng dụng có yêu cầu.
5. Không đưa token hoặc dữ liệu cá nhân nhạy cảm vào route vì route có thể xuất hiện trong log và trace.

Nếu dùng Bean Validation cho tham số handler, cấu hình method validation theo phiên bản Spring và ứng dụng đang dùng. Dù có validation annotation, vẫn cần kiểm tra quyền truy cập ở tầng service hoặc security phù hợp.

## 11. Quy tắc thiết kế route template

Một route dễ bảo trì nên có cấu trúc ổn định, thể hiện rõ tài nguyên và hành động:

```text
devices.{deviceId}.status
devices.{deviceId}.telemetry
tenants.{tenantId}.orders.{orderId}.summary
tenants.{tenantId}.devices.{deviceId}.commands
```

Một số khuyến nghị:

- Dùng tên biến mô tả vai trò, như `{deviceId}` thay vì `{id}` nếu route có nhiều định danh.
- Giữ cùng một thứ tự biến ở client và server.
- Chọn kiểu dữ liệu ổn định cho identifier; UUID hoặc số nguyên thường dễ kiểm tra hơn chuỗi tự do.
- Tránh nhúng nội dung tùy ý hoặc dữ liệu lớn vào route; dùng payload cho dữ liệu đó.
- Tránh đặt route variable chứa separator của route matcher nếu không có quy tắc escape rõ ràng.
- Quản lý route template như hợp đồng API và kiểm thử khi đổi tên hoặc cấu trúc segment.

Route matcher và separator có thể được cấu hình trong ứng dụng. Hãy dùng cùng quy ước giữa requester và responder; không giả định mọi ứng dụng Spring RSocket đều dùng dấu chấm hoặc dấu gạch chéo theo cùng cách nếu đã tùy chỉnh matcher.

## 12. Kiểm thử @DestinationVariable

Nên có kiểm thử tích hợp với requester và responder để xác minh cả việc tạo route lẫn bind tham số:

1. Gửi route với một biến hợp lệ và xác minh handler nhận đúng giá trị.
2. Gửi route với nhiều biến và xác minh từng giá trị không bị đảo thứ tự.
3. Gửi giá trị chuyển đổi được sang `UUID` hoặc số nguyên.
4. Gửi giá trị sai định dạng và xác minh lỗi binding được truyền về requester.
5. Gửi route không khớp template và xác minh handler không bị gọi nhầm.
6. Gửi route đúng nhưng caller không có quyền; xác minh bị từ chối ở bước authorization.
7. Kết hợp route variable với payload DTO và metadata header để xác minh ba nguồn được bind độc lập.

Ví dụ kiểm thử publisher bằng StepVerifier:

```java
StepVerifier.create(
        requester.route("devices.{deviceId}.status", deviceId)
            .data(new StatusQuery())
            .retrieveMono(DeviceStatus.class))
    .expectNextMatches(status -> status.deviceId().equals(deviceId))
    .verifyComplete();
```

Test cần khởi tạo server test với mapping `devices.{deviceId}.status` và một fixture có trạng thái xác định. Nếu test chỉ kiểm tra method Java trực tiếp, nó không xác minh được route matcher hoặc argument resolver đã bind biến đúng.

## 13. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tên trong `@DestinationVariable` khác template | Spring không lấy đúng biến route. | Đồng bộ tên `{variable}` và annotation. |
| Thứ tự đối số `route(...)` bị đảo | Giá trị được gắn vào segment không như mong đợi. | Đối chiếu thứ tự biến trong template. |
| Không giữ tên tham số khi biên dịch nhưng bỏ tên annotation | Spring có thể không khám phá được tên tham số. | Ghi rõ `@DestinationVariable("name")`. |
| Dùng kiểu `UUID`/`long` nhưng gửi chuỗi sai định dạng | Conversion thất bại trước khi gọi handler. | Validate format ở client và xử lý lỗi binding. |
| Đưa DTO lớn vào route | Route metadata trở nên khó quản lý và không đúng mục đích. | Đưa nội dung nghiệp vụ vào payload. |
| Dùng route variable như cơ chế phân quyền | Caller có thể tự chọn ID tài nguyên khác. | Kiểm tra authorization với principal đã xác thực. |
| Nhầm route variable với custom metadata | Đọc sai nguồn dữ liệu và cấu hình decoder. | Dùng `@DestinationVariable` cho route, `@Header` cho metadata đã extract. |
| Test handler trực tiếp rồi kết luận route binding đúng | Bỏ qua route matcher và argument resolver. | Bổ sung kiểm thử requester-responder tích hợp. |

## Kết luận

`@DestinationVariable` liên kết một biến trong route template của `@MessageMapping` với tham số Java của handler. Requester truyền các giá trị theo thứ tự template qua `RSocketRequester.route(...)`; Spring khớp route, trích biến và chuyển đổi sang kiểu tham số nếu có converter phù hợp. Hãy dùng route variable cho định danh và lựa chọn đích, payload cho nội dung nghiệp vụ, header cho metadata đã được ánh xạ. Ghi rõ tên biến, kiểm tra lỗi chuyển đổi, xác thực quyền truy cập tài nguyên và kiểm thử qua kết nối RSocket thật để bảo đảm việc định tuyến hoạt động đúng.
