# `@Controller`, `@MessageMapping` và ánh xạ route trong RSocket

## Mục tiêu

Trong Spring Messaging, `@Controller` đánh dấu lớp chứa các phương thức xử lý thông điệp; `@MessageMapping` gắn một phương thức với route của thông điệp RSocket. Khi requester gửi một request có route phù hợp, Spring tìm handler, giải mã payload, gọi phương thức và mã hóa kết quả trả về.

Cơ chế này là mô hình responder của RSocket, không phải ánh xạ URL HTTP. RSocket cũng có tính đối xứng: sau khi kết nối được thiết lập, mỗi đầu kết nối đều có thể gửi request và xử lý request nhận được.

## 1. Request RSocket được ánh xạ như thế nào?

Một request RSocket có thể mang **data** và **metadata**. Route thường nằm trong routing metadata; payload nghiệp vụ nằm trong data. Với Spring, requester khai báo route bằng `RSocketRequester.route(...)`, còn responder khai báo route cần xử lý bằng `@MessageMapping(...)`.

Luồng xử lý điển hình:

1. Requester gửi request, kèm route, payload và metadata tùy chọn.
2. `RSocketMessageHandler` lấy route từ metadata và tìm phương thức có mẫu `@MessageMapping` khớp với route đó.
3. Spring dùng các `Decoder` đã cấu hình để chuyển data thành kiểu Java của tham số payload; các metadata đã đăng ký được đưa vào header.
4. Phương thức handler chạy và trả về giá trị, `Mono`, `Flux` hoặc kiểu không có kết quả.
5. Spring mã hóa kết quả thành payload phản hồi theo kiểu tương tác RSocket tương ứng.

Ví dụ, route `radar.find.42` có thể được ánh xạ tới `@MessageMapping("radar.find.{id}")`. Giá trị `42` được lấy ra thành biến route `id`; payload, nếu có, vẫn là phần data riêng.

## 2. Vai trò của các annotation và thành phần

### `@Controller`

- Đánh dấu một Spring bean có các phương thức xử lý thông điệp.
- `RSocketMessageHandler` dùng các bean `@Controller` để phát hiện phương thức `@MessageMapping` và `@ConnectMapping`.
- Lớp phải được Spring quản lý, thường thông qua component scanning hoặc khai báo bean.
- Chỉ thêm `@Controller` không tự mở cổng RSocket. Ứng dụng còn cần cấu hình responder và gắn nó với RSocket server hoặc dùng cấu hình tự động tương ứng của Spring Boot.

### `@MessageMapping`

- Gắn phương thức với một route hoặc mẫu route.
- Mỗi request có route khớp sẽ được chuyển tới phương thức tương ứng.
- Phương thức có thể nhận payload, biến route, metadata đã trích xuất hoặc một `RSocketRequester`.
- Giá trị trả về quyết định số lượng phản hồi và góp phần xác định kiểu tương tác RSocket.

### `RSocketMessageHandler`

Đây là thành phần kết nối annotation với RSocket responder. Ở cấu hình Spring Framework thủ công, có thể khai báo handler như sau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.rsocket.annotation.support.RSocketMessageHandler;
import org.springframework.web.util.pattern.PathPatternRouteMatcher;

@Configuration
class RSocketHandlerConfig {

    @Bean
    RSocketMessageHandler rSocketMessageHandler() {
        RSocketMessageHandler handler = new RSocketMessageHandler();
        handler.setRouteMatcher(new PathPatternRouteMatcher());
        return handler;
    }
}
```

Mặc định, `RSocketMessageHandler` dùng `SimpleRouteMatcher`, dựa trên `AntPathMatcher`. Có thể dùng `PathPatternRouteMatcher` từ module `spring-web` để so khớp route hiệu quả hơn. Với Spring Boot, hạ tầng Spring Messaging cho RSocket và `RSocketMessageHandler` thường được auto-configure khi các dependency và cấu hình server phù hợp đã có; khi đó không cần khai báo lại bean chỉ để bật annotation mapping.

## 3. Thiết kế và so khớp route

Route RSocket là tên phân cấp được truyền qua metadata. Nó **không phải URL path**. Các route matcher mặc định dùng dấu chấm (`.`) làm ký tự phân tách; không áp dụng quy tắc URL decoding như khi xử lý HTTP URL.

Ví dụ về quy ước route:

| Route | Ý nghĩa |
|---|---|
| `radar.find.42` | Tìm radar có mã `42` |
| `radar.search` | Tìm nhiều radar theo payload |
| `radar.report` | Gửi một báo cáo radar |
| `radar.filter` | Gửi một luồng điều kiện lọc |

Một mẫu route có biến:

```java
@MessageMapping("radar.find.{id}")
Mono<Radar> find(@DestinationVariable("id") String id) {
    return radarService.findById(id);
}
```

Request có route `radar.find.42` sẽ đưa chuỗi `42` vào tham số `id`. `@DestinationVariable` lấy giá trị từ phần biến trong mẫu route; nên ghi rõ tên biến trong annotation để tránh phụ thuộc vào metadata tên tham số khi biên dịch.

Khi thiết kế route:

- Dùng tên có cấu trúc và nhất quán, chẳng hạn `resource.action.identifier`.
- Thống nhất chữ hoa/chữ thường, dấu phân tách và cách đặt tên giữa requester và responder.
- Không tự thêm dấu gạch chéo đầu route theo thói quen của URL HTTP.
- Không đưa dữ liệu nghiệp vụ vào route nếu dữ liệu đó nên nằm trong payload.
- Chọn route cụ thể để tránh nhiều handler cùng khớp một request.
- Kiểm tra route thực tế mà requester gửi phải khớp với mẫu `@MessageMapping`.

## 4. Tham số của phương thức handler

| Tham số | Công dụng |
|---|---|
| `@Payload T` | Nhận data của request sau khi được giải mã thành kiểu `T`. Annotation có thể bỏ qua nếu tham số là kiểu payload không đơn giản và không thuộc nhóm tham số đặc biệt khác; viết tường minh thường dễ đọc hơn. |
| `@Payload Mono<T>` | Nhận một payload theo dạng bất đồng bộ. |
| `@Payload Flux<T>` | Nhận một luồng payload; thường dùng cho phía đầu vào của tương tác Channel. |
| `@DestinationVariable("id")` | Lấy giá trị biến từ mẫu route, ví dụ `{id}`. |
| `@Header("tenant-id")` | Lấy một metadata value đã được `MetadataExtractor` giải mã và đăng ký. |
| `@Headers Map<String, Object>` | Nhận các metadata value đã được trích xuất dưới dạng map. |
| `RSocketRequester` | Gửi request ngược lại đầu kết nối hiện tại. RSocket cho phép hai phía đều đóng vai requester và responder. |

Không phải mọi metadata đều tự động trở thành header. Với metadata tùy chỉnh, cần cấu hình MIME type, `Decoder` và `MetadataExtractor` phù hợp. Nếu không đăng ký bộ giải mã hoặc khóa trích xuất, tham số `@Header` có thể không nhận được giá trị mong muốn.

## 5. Kiểu trả về và bốn interaction model

Spring suy ra interaction model dựa trên **cardinality** của payload đầu vào và kết quả đầu ra:

- Cardinality `0`: không có tham số payload ở đầu vào; ở đầu ra là `void` hoặc `Mono<Void>`.
- Cardinality `1`: một giá trị đồng bộ hoặc một kiểu bất đồng bộ đơn như `Mono<T>`.
- Cardinality `many`: một luồng nhiều giá trị như `Flux<T>`.

Các tổ hợp thường dùng:

| Payload đầu vào | Kết quả đầu ra | Interaction model | Cách dùng |
|---|---|---|---|
| Một giá trị (`T` hoặc `Mono<T>`) | Một giá trị (`T` hoặc `Mono<T>`) | Request-Response | Gửi một yêu cầu và nhận một kết quả |
| Một giá trị | `Flux<T>` | Request-Stream | Gửi một yêu cầu và nhận luồng kết quả |
| Một giá trị | `void` hoặc `Mono<Void>` | Fire-and-Forget | Gửi một thông điệp không cần dữ liệu phản hồi |
| `Flux<T>` | Không có, một hoặc nhiều giá trị | Request-Channel | Gửi luồng thông điệp và có thể nhận luồng phản hồi |

Ví dụ:

- `Mono<Radar>` phù hợp khi tìm một radar.
- `Flux<Radar>` phù hợp khi truy vấn trả về nhiều radar.
- `Mono<Void>` phù hợp khi ghi nhận một sự kiện mà giao thức ứng dụng không cần phản hồi dữ liệu.
- `Flux<Query>` ở đầu vào biểu thị requester có thể gửi nhiều query trên cùng request Channel.

RSocket dùng Reactive Streams cho các luồng; backpressure cho phép bên nhận điều tiết số lượng phần tử được gửi tiếp. Tránh chuyển các luồng này thành thao tác blocking trong handler.

## 6. Ví dụ controller

Đoạn mã sau minh họa ba interaction model và một Channel. Đây là phần mã controller; để chạy trong ứng dụng, cần có implementation của `RadarService`, các dependency Spring Messaging/Reactor, bean cấu hình responder và kết nối RSocket tương ứng.

```java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record Radar(String id, String name) {}
record RadarQuery(String region) {}

interface RadarService {
    Mono<Radar> findById(String id);

    Flux<Radar> search(RadarQuery query);

    Mono<Void> report(Radar radar);

    Flux<Radar> filter(Flux<RadarQuery> queries);
}

@Controller
public class RadarController {

    private final RadarService radarService;

    public RadarController(RadarService radarService) {
        this.radarService = radarService;
    }

    // Request-Response: một route variable, một Radar trả về.
    @MessageMapping("radar.find.{id}")
    public Mono<Radar> find(
            @DestinationVariable("id") String id) {
        return radarService.findById(id);
    }

    // Request-Stream: một payload, nhiều Radar trả về.
    @MessageMapping("radar.search")
    public Flux<Radar> search(@Payload RadarQuery query) {
        return radarService.search(query);
    }

    // Fire-and-Forget: nhận payload, không trả dữ liệu.
    @MessageMapping("radar.report")
    public Mono<Void> report(@Payload Radar radar) {
        return radarService.report(radar);
    }

    // Request-Channel: nhận một luồng query và trả một luồng Radar.
    @MessageMapping("radar.filter")
    public Flux<Radar> filter(@Payload Flux<RadarQuery> queries) {
        return radarService.filter(queries);
    }
}
```

Điểm cần quan sát:

- Tên route nằm trong annotation, còn dữ liệu tìm kiếm nằm trong `RadarQuery`.
- Biến `{id}` được chuyển thành tham số Java qua `@DestinationVariable`.
- Kiểu trả về thể hiện số lượng phản hồi: `Mono` là tối đa một phần tử, `Flux` là luồng phần tử.
- Phương thức `report` trả `Mono<Void>`; requester không nhận một đối tượng xác nhận nghiệp vụ từ handler.

## 7. Gọi các route từ requester

Khi đã có một kết nối và một `RSocketRequester`, requester gọi route tương ứng như sau:

```java
// Request-Response
Mono<Radar> one = requester.route("radar.find.42")
        .retrieveMono(Radar.class);

// Request-Stream
Flux<Radar> many = requester.route("radar.search")
        .data(new RadarQuery("north"))
        .retrieveFlux(Radar.class);

// Fire-and-Forget
Mono<Void> sent = requester.route("radar.report")
        .data(new Radar("42", "North radar"))
        .send();

// Request-Channel
Flux<Radar> filtered = requester.route("radar.filter")
        .data(Flux.just(
                new RadarQuery("north"),
                new RadarQuery("south")),
                RadarQuery.class)
        .retrieveFlux(Radar.class);
```

Các biến trên là publisher; request được thực thi khi publisher được subscribe. Trong ứng dụng reactive, thường trả publisher cho tầng gọi tiếp theo hoặc subscribe tại ranh giới phù hợp, thay vì gọi `block()` trong luồng xử lý.

Với Fire-and-Forget, `send()` trả về `Mono<Void>` để báo việc gửi thông điệp đã hoàn tất. Nó **không xác nhận rằng handler phía nhận đã xử lý xong**. Nếu nghiệp vụ cần xác nhận, hãy thiết kế route trả về một kết quả, ví dụ `Mono<ReportAccepted>`, và dùng Request-Response.

## 8. Metadata và giao tiếp ngược với requester

Payload chứa dữ liệu nghiệp vụ; metadata thường chứa route hoặc thông tin phụ như tenant, token hay tracing. Spring hỗ trợ:

- `@Header` để lấy một metadata value đã được giải mã.
- `@Headers` để lấy map các metadata value đã trích xuất.
- `RSocketRequester` trong tham số handler để gửi request tới peer đang kết nối.

Ví dụ về route variable kết hợp metadata:

```java
@MessageMapping("radar.tenant.{id}")
Mono<Radar> findForTenant(
        @DestinationVariable("id") String id,
        @Header("tenant-id") String tenantId) {
    return radarService.findByIdForTenant(id, tenantId);
}
```

Đoạn này chỉ hoạt động khi metadata có MIME type phù hợp và đã được `MetadataExtractor` cấu hình để tạo khóa `tenant-id`. Không nên xem header là dữ liệu đã được xác thực; xác thực và phân quyền vẫn phải được thực hiện ở tầng bảo mật/nghiệp vụ.

## 9. Phân biệt `@MessageMapping` và `@ConnectMapping`

- `@MessageMapping` xử lý từng request theo route, ví dụ `radar.find.42`.
- `@ConnectMapping` xử lý sự kiện ở cấp kết nối: frame `SETUP` lúc bắt đầu kết nối và các thông báo `METADATA_PUSH` tiếp theo.

Dùng `@ConnectMapping` cho xử lý gắn với vòng đời kết nối hoặc metadata cấp kết nối. Không dùng nó thay cho route xử lý request nghiệp vụ thông thường.

## 10. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy handler | Controller chưa là Spring bean hoặc responder chưa được đăng ký | Kiểm tra component scanning, bean `RSocketMessageHandler` và việc gắn `handler.responder()` vào server |
| Route không khớp | Sai tên, dấu phân tách, chữ hoa/thường hoặc mẫu route | So sánh chuỗi truyền vào `requester.route(...)` với `@MessageMapping` |
| Biến route rỗng hoặc lỗi binding | Tên trong `@DestinationVariable` không khớp placeholder | Đối chiếu `{id}` với `@DestinationVariable("id")` |
| Payload không giải mã được | Thiếu hoặc sai `Decoder`, MIME type hay kiểu dữ liệu | Kiểm tra `RSocketStrategies`, data MIME type và codec cho DTO |
| `@Header` không có giá trị | Metadata chưa được giải mã/trích xuất | Kiểm tra `MetadataExtractor`, MIME type và tên khóa |
| Client không nhận phản hồi | Handler trả `void`/`Mono<Void>` hoặc requester chọn sai kiểu retrieve | Kiểm tra interaction model và kiểu trả về |
| Client hiểu nhầm Fire-and-Forget là đã xử lý | `send()` chỉ báo gửi hoàn tất | Dùng Request-Response nếu cần ACK nghiệp vụ |
| Luồng bị nghẽn hoặc tiêu thụ tài nguyên cao | Blocking hoặc xử lý `Flux` không tôn trọng backpressure | Loại bỏ blocking trong handler và dùng các toán tử Reactor phù hợp |

Khi debug, kiểm tra theo thứ tự: route requester gửi, route pattern trong annotation, việc đăng ký controller, cấu hình responder, rồi mới kiểm tra codec và metadata. Cách này giúp phân biệt lỗi định tuyến với lỗi chuyển đổi payload.

## 11. Checklist khi triển khai

- [ ] Controller được Spring quản lý và có constructor injection cho service.
- [ ] Mỗi `@MessageMapping` có route rõ ràng, không trùng hoặc mơ hồ.
- [ ] Route ở requester khớp chính xác với route pattern ở responder.
- [ ] Placeholder trong route khớp với `@DestinationVariable`.
- [ ] Chọn `Mono`, `Flux` hoặc `Mono<Void>` theo interaction model cần dùng.
- [ ] Có encoder/decoder cho các DTO được gửi và nhận.
- [ ] Metadata tùy chỉnh đã được đăng ký trước khi đọc bằng `@Header`/`@Headers`.
- [ ] Fire-and-Forget không được dùng khi nghiệp vụ cần xác nhận xử lý.
- [ ] Handler không gọi blocking operation trên luồng reactive.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket, Annotated Responders và `@MessageMapping`](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [RSocket Protocol Specification](https://rsocket.io/about/protocol/)
