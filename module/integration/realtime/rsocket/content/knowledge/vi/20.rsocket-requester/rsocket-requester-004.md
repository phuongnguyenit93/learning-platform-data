# Gửi route và dữ liệu bằng route(...), data(...)

Trong Spring RSocket, **RSocketRequester** là API phía client để tạo và gửi các tương tác tới server. Hai lời gọi **route(...)** và **data(...)** là phần đầu của API fluent: route xác định handler đích thông qua routing metadata; data cung cấp nội dung payload mà server sẽ nhận và giải mã.

Hai phần này có vai trò riêng. Route không phải URL HTTP và không chứa mặc định toàn bộ dữ liệu nghiệp vụ. Data không tự chọn handler; nó là nội dung được gửi tới route đã chỉ định. Sau khi xây dựng request, client chọn cách kết thúc tương tác bằng **retrieveMono()**, **retrieveFlux()** hoặc **send()** tùy interaction model.

## 1. RSocketRequester và RequestSpec

RSocketRequester cung cấp một API thuận tiện để gửi request mà không cần tự tạo frame hoặc mã hóa routing metadata bằng tay. Lời gọi route(...) trả về một RequestSpec để tiếp tục cấu hình nội dung message.

Một chuỗi thao tác điển hình:

~~~java
Mono<OrderView> result = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Có thể hiểu từng bước:

1. **requester** đại diện cho một kết nối/phiên RSocket đã được thiết lập.
2. **route("orders.find")** chọn route mà server dùng để tìm handler.
3. **data(...)** cung cấp data payload của request.
4. **retrieveMono(OrderView.class)** khai báo client mong đợi một response được decode thành OrderView.

RequestSpec là đối tượng mô tả request. Các lời gọi route(...) và data(...) chưa tự gửi dữ liệu ngay. Việc gửi diễn ra khi publisher cuối cùng được subscribe; trong ví dụ trên, đó là Mono được trả về bởi retrieveMono(...).

Điều này phù hợp với mô hình reactive: tạo publisher không đồng nghĩa với thực thi ngay. Nếu publisher không được subscribe, request sẽ không được gửi.

## 2. route(...) xác định handler đích

route(...) gắn tên route vào routing metadata của message. Server dùng giá trị này để ánh xạ tới method có @MessageMapping tương ứng.

Ví dụ server:

~~~java
@Controller
public class OrderController {

    @MessageMapping("orders.find")
    public Mono<OrderView> find(
            @Payload FindOrderRequest request) {
        return orderService.find(request.orderId());
    }
}
~~~

Client gọi đúng route:

~~~java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Tên route trong client phải khớp với mapping phía server. Nếu server đăng ký orders.find nhưng client gửi order.find, Spring không tìm thấy handler tương ứng và tương tác sẽ kết thúc bằng lỗi.

Route RSocket là định danh logic trong routing metadata, không phải đường dẫn HTTP. Việc gọi route orders.find không tạo endpoint REST /orders/find và không phụ thuộc vào HTTP controller.

### Quy ước đặt tên route

Nên đặt route theo miền nghiệp vụ và hành động:

- orders.find
- orders.create
- prices.watch
- telemetry.subscribe
- devices.commands

Route nên ổn định, dễ đọc và được quản lý như một phần hợp đồng API. Khi đổi tên route, cần cập nhật cả client và server hoặc duy trì route cũ trong thời gian chuyển đổi.

## 3. Route template và route variables

RSocketRequester hỗ trợ truyền route variables khi route được khai báo theo template. Ví dụ:

~~~java
Mono<DeviceView> device = requester
    .route("devices.{deviceId}.details", deviceId)
    .data(new DeviceDetailsQuery(false))
    .retrieveMono(DeviceView.class);
~~~

Server có thể nhận biến từ route bằng @DestinationVariable:

~~~java
@Controller
public class DeviceController {

    @MessageMapping("devices.{deviceId}.details")
    public Mono<DeviceView> details(
            @DestinationVariable String deviceId,
            @Payload DeviceDetailsQuery query) {
        return deviceService.details(deviceId, query);
    }
}
~~~

Route variables là thành phần của route, không phải data payload. Chúng hữu ích khi một phần định danh tài nguyên nằm trong route, còn phần thân request mang các tham số truy vấn khác.

Ví dụ, deviceId chọn thiết bị; query có thể chọn có lấy telemetry gần nhất hay không. Không nên đưa toàn bộ object nghiệp vụ phức tạp vào route. Hãy giữ route ngắn và dễ quản lý, còn nội dung có cấu trúc nên đặt trong DTO data.

Cú pháp template và quy tắc phân tách route phụ thuộc RouteMatcher được cấu hình. Client và server cần dùng cùng quy ước, đặc biệt khi giá trị route variable chứa ký tự phân tách hoặc ký tự cần encode.

## 4. data(...) cung cấp data payload

data(...) đặt nội dung data của RSocket payload. Giá trị có thể là DTO, chuỗi, byte array hoặc kiểu dữ liệu khác mà codec của RSocketStrategies hỗ trợ.

Ví dụ với DTO:

~~~java
public record FindOrderRequest(
    String orderId,
    boolean includeLines
) {}

Mono<OrderView> response = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001", true))
    .retrieveMono(OrderView.class);
~~~

Spring sử dụng encoder/codec phù hợp để chuyển object thành byte. Ở phía server, message converter/decoder chuyển byte trở lại kiểu tham số của handler.

Do đó, client và server phải thống nhất:

- Kiểu dữ liệu và schema của DTO.
- Data MIME type.
- Codec có khả năng encode/decode kiểu đó.
- Quy tắc tương thích khi schema thay đổi.

Không nên giả định mọi Java object đều tự động serialize được. Nếu codec không hỗ trợ kiểu dữ liệu hoặc hai bên cấu hình MIME type không tương thích, request có thể lỗi khi encode hoặc decode.

### Gửi kiểu dữ liệu cụ thể

Với dữ liệu đơn giản, có thể gửi String hoặc byte[] nếu hợp đồng hai phía thống nhất. Với request nghiệp vụ, DTO thường dễ mở rộng và kiểm tra hơn:

~~~java
public record CreateOrderRequest(
    String customerId,
    List<OrderLineRequest> items
) {}

public record OrderLineRequest(
    String sku,
    int quantity
) {}
~~~

DTO giúp định nghĩa rõ trường bắt buộc, kiểu dữ liệu và validation. Không nên truyền trực tiếp entity database có quan hệ nội bộ hoặc trường quản trị không dành cho client.

## 5. Phân biệt route, data và metadata

Một RSocket payload có thể chứa data và metadata. Route là một loại metadata phục vụ định tuyến; ứng dụng cũng có thể gửi metadata riêng cho tracing, tenant context hoặc thông tin phụ trợ theo hợp đồng.

| Thành phần | Mục đích | API phía client |
|---|---|---|
| Route | Chọn handler | route(...) |
| Data | Nội dung nghiệp vụ | data(...) |
| Custom metadata | Thông tin phụ trợ | metadata(value, mimeType) |
| Response | Dữ liệu trả về | retrieveMono(...) / retrieveFlux(...) |
| Không có response payload | Gửi kiểu fire-and-forget | send() |

Ví dụ gửi data và custom metadata:

~~~java
Mono<OrderView> response = requester
    .route("orders.find")
    .metadata(
        new TraceMetadata("trace-8f31"),
        MimeType.valueOf("message/x.example-trace.v1")
    )
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Custom metadata cần MIME type riêng và codec/metadata encoder phù hợp. Ví dụ này giả định kết nối dùng composite metadata (mặc định của Spring RSocketRequester), vì composite metadata cho phép route và nhiều mục metadata có MIME type riêng cùng tồn tại. Server phải biết cách đọc metadata tương ứng. Không thể gửi một object metadata tùy ý mà không đăng ký cơ chế encode/decode cho nó.

Không đưa access token, role hoặc tenant ID do client tự khai báo vào metadata rồi coi chúng là danh tính đã xác thực. Thông tin bảo mật cần được xác thực bằng cơ chế security của phiên và được kiểm tra quyền ở server.

## 6. Cấu hình data MIME type và codec

MIME type mô tả định dạng của data hoặc metadata. Hai peer cần tương thích về cách diễn giải byte nhận được.

Data MIME type được chọn ở cấp kết nối. Với Spring Boot, có thể inject RSocketRequester.Builder đã được auto-configure cùng codec phù hợp. Ví dụ một service tạo requester TCP:

~~~java
@Service
public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("localhost", 7000);
    }
}
~~~

Trong Spring Boot, builder được auto-configure với các codec ứng dụng. Builder là prototype bean vì nó có trạng thái cấu hình; mỗi nơi cần một requester với setup khác nhau nên nhận một builder riêng. Lời gọi tcp(...) tạo requester nhưng chưa mở kết nối ngay. Kết nối dùng chung được thiết lập khi request đầu tiên được gửi.

RSocketStrategies quản lý encoder và decoder được dùng để chuyển đổi data/metadata. Nếu có DTO tùy chỉnh hoặc định dạng riêng, cần đăng ký codec tương ứng ở cả hai phía.

Nếu tự tạo RSocketStrategies mà không dùng cấu hình Spring Boot, lưu ý bộ codec cơ bản từ spring-core chỉ hỗ trợ String, byte[] và ByteBuffer. Muốn gửi DTO JSON cần bổ sung encoder/decoder JSON, thường có từ spring-web. Spring Boot auto-configures RSocketRequester.Builder với các codec ứng dụng đã cấu hình.

Nếu không dùng Spring Boot auto-configuration, hãy cung cấp RSocketStrategies có encoder/decoder phù hợp và cấu hình dataMimeType(...) trên Builder trước khi tạo requester. Ví dụ cấu hình MIME type JSON ở cấp kết nối:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .rsocketStrategies(jsonStrategies)
    .tcp("localhost", 7000);
~~~

MIME type ở cấp kết nối áp dụng cho data của các request trên kết nối đó. Việc đặt dataMimeType(...) không tự tạo codec mới; encoder/decoder tương ứng vẫn phải được đăng ký trong RSocketStrategies. Không có overload data(Object, MimeType) trong RequestSpec hiện hành để đổi MIME type riêng cho từng payload.

## 7. retrieveMono(...) nhận một response

Sau khi cấu hình route và data, dùng retrieveMono(...) khi interaction trả về tối đa một response.

~~~java
Mono<OrderView> order = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);
~~~

Publisher trả về có thể:

- Phát một OrderView rồi hoàn tất.
- Hoàn tất mà không phát giá trị khi client dùng Mono<Void> và chỉ cần chờ interaction hoàn tất.
- Phát lỗi nếu server trả ERROR hoặc xảy ra lỗi encode/decode/transport.

Với kết quả nghiệp vụ cần phân biệt rõ, chẳng hạn không tìm thấy đơn hàng, nên trả lỗi đã chuẩn hóa hoặc một DTO kết quả như OrderLookupResult có trạng thái FOUND/NOT_FOUND. Tránh dùng một Mono rỗng mơ hồ nếu client cần biết kết quả tra cứu.

Với kiểu generic phức tạp, dùng ParameterizedTypeReference để giữ thông tin kiểu ở runtime:

~~~java
ParameterizedTypeReference<ApiResponse<OrderView>> type =
    new ParameterizedTypeReference<>() {};

Mono<ApiResponse<OrderView>> result = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(type);
~~~

Nếu dùng Class<T> cho một kiểu generic đã bị type erasure, decoder có thể không biết kiểu phần tử bên trong collection hoặc wrapper. ParameterizedTypeReference giúp truyền mô tả kiểu đầy đủ hơn.

Nếu route không cần data payload, có thể bỏ qua bước data(...):

~~~java
Mono<AirportLocation> location = requester
    .route("find.radar.EWR")
    .retrieveMono(AirportLocation.class);
~~~

## 8. retrieveFlux(...) nhận một response stream

Dùng retrieveFlux(...) khi server trả nhiều response payload theo thời gian:

~~~java
Flux<PriceTick> ticks = requester
    .route("prices.watch")
    .data(new PriceSubscription("ACME"))
    .retrieveFlux(PriceTick.class);
~~~

Mỗi payload response được decode thành một PriceTick. Client có thể áp dụng các operator Reactor để lọc, biến đổi hoặc giới hạn thời gian theo dõi.

~~~java
Flux<PriceTick> recentTicks = requester
    .route("prices.watch")
    .data(new PriceSubscription("ACME"))
    .retrieveFlux(PriceTick.class)
    .filter(tick -> tick.price().signum() > 0)
    .take(Duration.ofMinutes(1));
~~~

Request-stream sử dụng flow control. Consumer yêu cầu demand; responder chỉ được phát trong lượng credit đã cấp. Các operator downstream và queue nội bộ vẫn cần được cấu hình hợp lý để tránh tích lũy backlog.

Khi subscriber hủy Flux, cancellation được truyền tới tương tác RSocket đang hoạt động. Hãy đảm bảo phía server có thể dừng nguồn dữ liệu và giải phóng tài nguyên.

## 9. send() cho fire-and-forget

Khi client không cần response payload, dùng send():

~~~java
Mono<Void> sent = requester
    .route("audit.record")
    .data(new AuditEvent(
        "EVT-1001",
        "ORDER_VIEWED",
        Instant.now()
    ))
    .send();
~~~

send() trả về Mono<Void> để biểu diễn việc gửi theo API requester. Nó không phải response nghiệp vụ từ server và không chứng minh rằng server đã commit dữ liệu.

Nếu cần xác nhận server đã tiếp nhận hoặc xử lý thành công, hãy thiết kế route request-response trả về acknowledgement:

~~~java
Mono<Accepted> accepted = requester
    .route("jobs.submit")
    .data(new SubmitJobRequest("JOB-1"))
    .retrieveMono(Accepted.class);
~~~

Với lệnh có tác dụng phụ, cần idempotency key hoặc event ID để tránh xử lý trùng khi client retry sau timeout hoặc mất kết nối.

## 10. data(Publisher, elementType) cho request-channel

Request-channel cho phép client gửi một stream request và nhận một stream response. Trong RSocketRequester, data(...) có overload nhận Publisher cùng kiểu phần tử để codec biết cách encode từng phần tử. API data(Object) cũng nhận Publisher; overload có element type giúp encoder được tìm một lần trước khi xử lý các phần tử thay vì kiểm tra kiểu và tìm encoder cho từng giá trị.

~~~java
Flux<Command> commands = commandSource();

Flux<CommandResult> results = requester
    .route("devices.commands")
    .data(commands, Command.class)
    .retrieveFlux(CommandResult.class);
~~~

Server nhận Flux<Command> và trả Flux<CommandResult>. Hai hướng có demand độc lập: client điều tiết response mà nó nhận; server điều tiết request mà nó tiêu thụ. Spring suy ra interaction model từ cardinality đầu vào và đầu ra: một giá trị đầu vào cùng Flux response là request-stream; Publisher nhiều giá trị đầu vào cùng Flux response là request-channel.

Với kiểu phần tử generic, có thể dùng ParameterizedTypeReference tương ứng nếu overload của phiên bản Spring đang dùng hỗ trợ.

Không coi Publisher đầu vào là một object đơn. Khi truyền Publisher nhiều phần tử, chọn overload có kiểu phần tử để tránh encoder lookup lặp lại và giúp request-channel có hợp đồng kiểu rõ ràng.

## 11. Thời điểm request được gửi và subscription

API RSocketRequester dựa trên Reactor. Các publisher được tạo ra một cách lazy; thao tác mạng bắt đầu khi publisher được subscribe.

Ví dụ:

~~~java
Mono<OrderView> request = requester
    .route("orders.find")
    .data(new FindOrderRequest("ORD-1001"))
    .retrieveMono(OrderView.class);

// Chưa gửi request nếu chưa có subscription.
request.subscribe(
    order -> log.info("Order: {}", order),
    error -> log.error("Request failed", error)
);
~~~

Trong ứng dụng Spring WebFlux hoặc service reactive, thường không cần gọi subscribe() thủ công. Hãy trả publisher cho framework hoặc kết hợp nó vào pipeline hiện có:

~~~java
public Mono<OrderView> find(String orderId) {
    return requester
        .route("orders.find")
        .data(new FindOrderRequest(orderId))
        .retrieveMono(OrderView.class);
}
~~~

Tự subscribe bên trong service thường tách request khỏi vòng đời của caller, khiến lỗi, cancellation và kết quả khó được quản lý. Chỉ dùng subscribe ở ranh giới ứng dụng khi thực sự cần khởi chạy một tác vụ độc lập và đã có chính sách lifecycle rõ ràng.

## 12. Validation và giới hạn payload trước khi gửi

route(...) và data(...) không tự kiểm tra tính hợp lệ nghiệp vụ của DTO. Client nên kiểm tra dữ liệu đầu vào trước khi gửi để tránh request sai định dạng hoặc quá lớn; server vẫn phải validate lại vì client không phải ranh giới tin cậy.

Ví dụ kiểm tra đơn giản trước khi gửi:

~~~java
Mono<OrderView> findOrder(String orderId) {
    if (orderId == null || orderId.isBlank()) {
        return Mono.error(
            new IllegalArgumentException("orderId is required"));
    }

    if (orderId.length() > 40) {
        return Mono.error(
            new IllegalArgumentException("orderId is too long"));
    }

    return requester
        .route("orders.find")
        .data(new FindOrderRequest(orderId))
        .retrieveMono(OrderView.class);
}
~~~

Giới hạn ở client giúp phát hiện lỗi sớm. Server vẫn cần kiểm tra schema, kích thước byte, quyền truy cập và quy tắc nghiệp vụ. Đặc biệt, @Size trên String thường giới hạn ký tự theo validator chứ không phải byte UTF-8; nếu hợp đồng quy định byte, cần kiểm tra byte riêng.

## 13. Xử lý lỗi khi route hoặc data không đúng

Các lỗi phổ biến có thể xảy ra ở nhiều giai đoạn:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy handler | Route sai hoặc server chưa đăng ký mapping | So khớp route(...) với @MessageMapping |
| Decode lỗi | MIME type hoặc codec không tương thích | Kiểm tra dataMimeType và RSocketStrategies |
| Thiếu tham số handler | DTO thiếu field hoặc payload không đúng schema | Kiểm tra DTO và validation |
| Metadata không đọc được | MIME type hoặc metadata encoder không khớp | Kiểm tra metadata(...) và decoder phía server |
| Request không chạy | Publisher chưa được subscribe | Kiểm tra pipeline và điểm subscribe |
| Client nghĩ FNF đã thành công | Nhầm send completion với acknowledgement nghiệp vụ | Dùng request-response nếu cần xác nhận |
| Stream bị hủy | Timeout hoặc subscriber cancellation | Kiểm tra doOnCancel và timeout |

Xử lý lỗi nên phân biệt lỗi route, lỗi decode, lỗi nghiệp vụ và lỗi transport. Không chuyển tất cả thành một thông báo chung vì sẽ khó chẩn đoán và retry sai loại lỗi.

## 14. Kiểm thử route và data

Có thể kiểm tra publisher được tạo bởi requester bằng StepVerifier nếu có mock/fake requester phù hợp. Tuy nhiên, để xác nhận route metadata và serialization thực sự hoạt động, nên có integration test với RSocket server/client.

Các trường hợp cần kiểm tra:

1. Client gửi route đúng và server gọi đúng handler.
2. Route sai dẫn tới lỗi không tìm thấy mapping.
3. DTO được encode/decode đúng theo MIME type.
4. Data có field thiếu hoặc sai kiểu bị validation từ chối.
5. Custom metadata được encode và đọc đúng.
6. retrieveMono nhận một response đúng kiểu.
7. retrieveFlux nhận nhiều response và tôn trọng demand.
8. send() không bị hiểu nhầm là acknowledgement nghiệp vụ.
9. data(Publisher, elementType) gửi channel đúng kiểu phần tử.
10. Cancellation hoặc timeout được truyền xuống stream.

Ví dụ kiểm thử publisher trả về:

~~~java
StepVerifier.create(
        requester.route("orders.find")
            .data(new FindOrderRequest("ORD-1001"))
            .retrieveMono(OrderView.class))
    .expectNextMatches(order ->
        order.orderId().equals("ORD-1001"))
    .verifyComplete();
~~~

Test này chỉ đầy đủ khi requester được kết nối tới server test hoặc được thay bằng test fixture phù hợp. Integration test qua transport thật giúp phát hiện lỗi mapping, MIME type và codec mà unit test riêng lẻ không thể bao phủ.

## 15. Checklist khi dùng route(...) và data(...)

- Route khớp với @MessageMapping phía server.
- Route được xem như routing metadata, không nhầm với URL HTTP.
- Route chỉ mang thông tin định tuyến; DTO nghiệp vụ nằm trong data.
- Data type được codec hai phía hỗ trợ.
- Data MIME type tương thích với serializer/deserializer.
- Custom metadata dùng metadata(...) và MIME type phù hợp.
- Request-response dùng retrieveMono(...).
- Request-stream dùng retrieveFlux(...).
- Fire-and-forget dùng send() và không giả định có acknowledgement.
- Request-channel truyền Publisher với element type rõ ràng.
- Publisher được subscribe ở đúng ranh giới reactive.
- Client validate sớm, server validate lại và kiểm tra quyền.
- Có timeout, cancellation và xử lý lỗi phù hợp.
- Integration test xác nhận route, payload và codec qua kết nối thật.

## 16. Kết luận

route(...) xác định handler đích bằng routing metadata; data(...) cung cấp phần data payload được codec chuyển thành byte. Custom metadata được gửi riêng bằng metadata(...). Sau khi cấu hình RequestSpec, client chọn retrieveMono(...) cho một response, retrieveFlux(...) cho stream hoặc send() cho fire-and-forget.

Với request-channel, data(...) nhận Publisher và kiểu phần tử để gửi nhiều payload request trong khi client nhận stream response. Vì RSocketRequester hoạt động theo mô hình reactive, request chỉ thực sự được gửi khi publisher được subscribe. Hãy giữ route, DTO, MIME type và codec như một hợp đồng thống nhất giữa hai peer, đồng thời kiểm tra validation, timeout, cancellation và lỗi để các tương tác realtime có thể vận hành ổn định.

Tài liệu tham khảo:
- [Spring Framework Reference – RSocketRequester](https://docs.spring.io/spring-framework/reference/rsocket.html#rsocket-requester)
- [Spring Framework Javadoc – RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html)

