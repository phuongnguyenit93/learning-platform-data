# Route với tham số và metadata theo yêu cầu trong Spring RSocket

## 1. Vai trò của route và metadata

Trong giao tiếp RSocket của Spring, một request có thể mang các phần thông tin với mục đích khác nhau:

- **Route** xác định handler hoặc luồng xử lý ở phía server. Route được truyền dưới dạng routing metadata của RSocket.
- **Tham số route** cung cấp các giá trị để hoàn thiện mẫu route, chẳng hạn mã đơn hàng hoặc mã người dùng.
- **Payload** chứa dữ liệu nghiệp vụ mà handler cần xử lý, ví dụ bộ lọc tìm kiếm hoặc nội dung lệnh.
- **Metadata ứng dụng** mang thông tin phụ trợ gắn với request, ví dụ tenant, correlation id, locale hoặc thông tin xác thực theo cơ chế đã cấu hình.

Route và metadata không thay thế payload. Ví dụ, với một request lấy sự kiện của đơn hàng, route có thể là **orders.{orderId}.events**, tham số route là **orderId**, payload là bộ lọc trạng thái, còn metadata có thể chứa tenant hiện tại.

Spring cung cấp **RSocketRequester** để tạo request theo cách này. Mỗi request có thể chọn route, truyền tham số, bổ sung metadata khi cần, gửi payload và chọn kiểu nhận kết quả.

## 2. Khai báo route có tham số

Dùng **route(String route, Object... routeVars)** để khai báo route template và các giá trị thay thế cho placeholder nằm trong dấu ngoặc nhọn.

~~~java
Mono<OrderSummary> result = requester
    .route("orders.{orderId}.summary", orderId)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Trong ví dụ này:

- **orders.{orderId}.summary** là route template.
- **orderId** là giá trị thay thế cho placeholder **{orderId}**.
- **data(...)** đặt payload của request.
- **retrieveMono(...)** yêu cầu một kết quả.

Khi có nhiều placeholder, truyền các giá trị theo đúng thứ tự xuất hiện trong route template:

~~~java
Mono<OrderSummary> result = requester
    .route("customers.{customerId}.orders.{orderId}",
           customerId, orderId)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Không truyền một đối tượng map với ý định Spring tự tìm giá trị theo tên placeholder. API nhận các route variable qua danh sách tham số biến đổi; vì vậy thứ tự đối số phải khớp thứ tự placeholder.

Ở phía server, route template tương ứng được khai báo bằng **@MessageMapping**. Có thể lấy giá trị placeholder bằng **@DestinationVariable**:

~~~java
@Controller
class OrderRSocketController {

    private final OrderService orderService;

    OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("customers.{customerId}.orders.{orderId}")
    Mono<OrderSummary> summary(
            @DestinationVariable("customerId") String customerId,
            @DestinationVariable("orderId") String orderId,
            @Payload SummaryQuery query) {

        return orderService.summary(customerId, orderId, query);
    }
}
~~~

Route ở client và route pattern ở server phải thống nhất. Nếu route không khớp handler đã đăng ký, request không được chuyển đến method mong muốn. Nên dùng tên route ổn định, có cấu trúc và có ý nghĩa nghiệp vụ; tránh ghép chuỗi tùy tiện từ dữ liệu đầu vào chưa được kiểm tra.

## 3. Gắn metadata cho từng request

Metadata được thêm vào request bằng **metadata(Object metadata, MimeType mimeType)**. Đối tượng metadata được mã hóa theo MIME type đã chỉ định. Phía nhận phải có decoder và cấu hình trích xuất metadata tương ứng.

Ví dụ, định nghĩa metadata tenant:

~~~java
public record TenantMetadata(String tenantId) {
}
~~~

Khai báo MIME type riêng cho metadata này:

~~~java
private static final MimeType TENANT_MIME_TYPE =
    MimeTypeUtils.parseMimeType(
        "application/vnd.example.tenant+json");
~~~

Gắn metadata vào một request:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.{orderId}.events", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new OrderFilter("PAID"))
    .retrieveFlux(OrderEvent.class);
~~~

Request trên có các thành phần tách biệt:

- Route **orders.{orderId}.events** chọn luồng sự kiện của đơn hàng.
- **orderId** hoàn thiện route template.
- **TenantMetadata** cung cấp tenant context.
- **OrderFilter** là payload nghiệp vụ.
- **retrieveFlux(OrderEvent.class)** nhận một luồng sự kiện.

Metadata nên chứa thông tin ngắn, có tính chất mô tả hoặc điều khiển request. Dữ liệu nghiệp vụ lớn, nội dung tìm kiếm và lệnh xử lý vẫn nên nằm trong payload. MIME type phải được hai phía thống nhất; ví dụ trên sử dụng JSON media type riêng cho metadata tenant.

## 4. Chỉ thêm metadata khi request cần

Metadata là tùy chọn ở cấp request. Có thể tạo request spec trước, sau đó chỉ thêm metadata khi đã có giá trị cần gửi:

~~~java
RSocketRequester.RequestSpec spec =
    requester.route("orders.{orderId}.summary", orderId);

if (tenantId != null && !tenantId.isBlank()) {
    spec = spec.metadata(
        new TenantMetadata(tenantId),
        TENANT_MIME_TYPE);
}

Mono<OrderSummary> result = spec
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Cách này hữu ích khi một route phục vụ nhiều tình huống:

- Request nội bộ đã có tenant context thì gửi metadata tenant.
- Request không có tenant context thì bỏ metadata tùy chọn.
- Một loại request khác cần correlation id hoặc locale thì bổ sung metadata tương ứng theo hợp đồng đã thống nhất.

Nếu server bắt buộc phải có metadata, hãy kiểm tra điều kiện đó ở server và trả lỗi rõ ràng khi thiếu hoặc không hợp lệ. Không nên dựa vào việc client luôn gửi metadata để bỏ qua xác thực dữ liệu đầu vào.

## 5. Cấu hình MIME type và metadata extraction

RSocket phân biệt MIME type của data và MIME type của metadata. Khi dùng composite metadata, một payload metadata có thể chứa nhiều entry với MIME type riêng. Composite metadata giúp route metadata và metadata ứng dụng cùng tồn tại trong một request.

Ví dụ cấu hình client dùng JSON cho data và composite metadata cho phần metadata:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .rsocketStrategies(strategies)
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .metadataMimeType(MimeTypeUtils.parseMimeType(
        "message/x.rsocket.composite-metadata.v0"))
    .connectTcp("localhost", 7000)
    .block();
~~~

Đoạn code minh họa việc thiết lập kết nối TCP và nhận **RSocketRequester**. Trong ứng dụng thực tế, nên quản lý vòng đời kết nối theo vòng đời ứng dụng và không gọi **block()** trên event-loop hoặc trong luồng xử lý request reactive.

Ở phía server, đăng ký cách giải mã và ánh xạ metadata MIME type thành message header. Ví dụ sau ánh xạ metadata tenant vào header có tên **tenant**:

~~~java
@Bean
RSocketStrategies rSocketStrategies() {
    return RSocketStrategies.builder()
        .metadataExtractorRegistry(registry ->
            registry.metadataToExtract(
                TENANT_MIME_TYPE,
                TenantMetadata.class,
                "tenant"))
        .build();
}
~~~

Cần bảo đảm **RSocketStrategies** có encoder/decoder phù hợp với MIME type và kiểu dữ liệu metadata. Nếu dùng JSON cho **TenantMetadata**, hai phía phải có JSON encoder/decoder tương thích. Cấu hình strategy của client phải mã hóa đúng MIME type; strategy của server phải giải mã và trích xuất đúng kiểu dữ liệu.

Sau khi metadata đã được ánh xạ thành message header, handler có thể nhận nó bằng **@Header**:

~~~java
@MessageMapping("orders.{orderId}.events")
Flux<OrderEvent> events(
        @DestinationVariable("orderId") String orderId,
        @Header("tenant") TenantMetadata tenant,
        @Payload OrderFilter filter) {

    return orderService.eventsFor(
        tenant.tenantId(), orderId, filter);
}
~~~

Ở đây **@Header("tenant")** đọc header do metadata extractor tạo ra. Nếu không đăng ký ánh xạ metadata, không nên giả định một metadata MIME type tùy chỉnh sẽ tự động xuất hiện dưới dạng header có tên **tenant**.

## 6. Chọn kiểu tương tác theo kết quả mong đợi

Sau khi cấu hình route, metadata và payload, chọn phương thức kết thúc request theo kiểu tương tác:

| Phương thức | Kiểu kết quả | Trường hợp sử dụng |
|---|---|---|
| **retrieveMono(Type.class)** | Một giá trị hoặc hoàn tất rỗng | Request-response |
| **retrieveFlux(Type.class)** | Luồng nhiều giá trị | Request-stream |
| **send()** | **Mono<Void>** | Fire-and-forget, không cần payload phản hồi |

Ví dụ request-response:

~~~java
Mono<OrderSummary> summary = requester
    .route("orders.{orderId}.summary", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new SummaryQuery(true))
    .retrieveMono(OrderSummary.class);
~~~

Ví dụ request-stream:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.{orderId}.events", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new OrderFilter("PAID"))
    .retrieveFlux(OrderEvent.class);
~~~

Ví dụ gửi lệnh không cần phản hồi:

~~~java
Mono<Void> sent = requester
    .route("orders.{orderId}.refresh", orderId)
    .metadata(new TenantMetadata(tenantId), TENANT_MIME_TYPE)
    .data(new RefreshCommand())
    .send();
~~~

Việc chọn **retrieveMono**, **retrieveFlux** hay **send** phải khớp với interaction model mà server cung cấp. **send()** chỉ phù hợp khi client không cần đọc response data; lỗi truyền tải hoặc lỗi xử lý vẫn cần được xử lý qua reactive pipeline.

## 7. Phân biệt route variable, payload và metadata

| Thành phần | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Route | Gọi chức năng hoặc handler nào? | **orders.{orderId}.events** |
| Route variable | Đối tượng hoặc tài nguyên nào? | **orderId = "ORD-42"** |
| Payload | Cần xử lý dữ liệu gì? | **OrderFilter("PAID")** |
| Metadata | Request có context phụ trợ nào? | **TenantMetadata("tenant-a")** |

Một quy tắc thực tế là đặt định danh dùng để định tuyến vào route variable, dữ liệu nghiệp vụ vào payload và context dùng chung hoặc thông tin điều khiển vào metadata. Không nên đưa toàn bộ payload lên route hoặc dùng metadata làm nơi chứa một object nghiệp vụ lớn.

Không đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào route variable. Route thường xuất hiện trong log, metric hoặc thông tin chẩn đoán; hãy dùng cơ chế xác thực và bảo mật RSocket phù hợp. Một metadata tùy chỉnh như **TenantMetadata** cũng không tự tạo ra xác thực hay phân quyền. Server phải xác minh tenant và quyền truy cập trước khi trả dữ liệu.

## 8. Lỗi thường gặp và cách kiểm tra

**Route template không khớp**

- Đối chiếu route ở client với **@MessageMapping** phía server.
- Kiểm tra số lượng và thứ tự route variable.
- Tránh tự nối các đoạn route từ dữ liệu đầu vào không được kiểm tra.

**Metadata không đến được handler**

- Kiểm tra client có gọi **metadata(...)** trên đúng request spec hay không.
- Kiểm tra MIME type metadata và composite metadata MIME type.
- Kiểm tra server có metadata extractor cho MIME type đó hay chưa.
- Kiểm tra decoder có hỗ trợ kiểu metadata được yêu cầu hay không.
- Kiểm tra tên header trong **metadataToExtract(...)** trùng với tên trong **@Header(...)**.

**Lỗi giải mã metadata hoặc payload**

- Xác nhận hai phía thống nhất data MIME type và metadata MIME type.
- Xác nhận JSON encoder/decoder có hỗ trợ kiểu Java tương ứng.
- Kiểm tra cấu trúc dữ liệu gửi đi có tương thích với DTO phía nhận.

**Thiếu metadata bắt buộc**

- Xác định metadata là bắt buộc hay tùy chọn trong hợp đồng request.
- Nếu bắt buộc, xác thực ở server và trả lỗi có ý nghĩa khi thiếu.
- Nếu tùy chọn, xử lý trường hợp header không tồn tại thay vì giả định luôn có giá trị.

**Không nhận được response như mong đợi**

- Dùng **retrieveMono** cho một kết quả, **retrieveFlux** cho luồng kết quả và **send** khi không cần response data.
- Theo dõi lỗi trong reactive pipeline bằng các toán tử như **doOnError** và xử lý ở ranh giới phù hợp.
- Kiểm tra server handler thực sự trả đúng kiểu dữ liệu mà client yêu cầu.

## 9. Checklist khi triển khai

1. Xác định route và các placeholder cần thiết.
2. Truyền route variable theo đúng thứ tự placeholder.
3. Khai báo route pattern tương ứng trên server bằng **@MessageMapping**.
4. Chọn payload type và data MIME type phù hợp.
5. Chỉ thêm metadata khi request cần; xác định MIME type cho từng loại metadata.
6. Nếu dùng composite metadata, cấu hình metadata MIME type tương thích ở client và server.
7. Đăng ký encoder/decoder và metadata extractor cho metadata tùy chỉnh.
8. Dùng **@DestinationVariable**, **@Payload** và **@Header** đúng vai trò.
9. Chọn **retrieveMono**, **retrieveFlux** hoặc **send** theo interaction model.
10. Xác thực metadata ở server trước khi dùng nó cho tenant isolation, xác thực hoặc phân quyền.

**RSocketRequester** cho phép xây dựng request linh hoạt theo từng lần gọi: route chọn handler, route variable xác định đích cụ thể, payload mang dữ liệu nghiệp vụ và metadata bổ sung context khi cần. Thiết kế rõ ràng hợp đồng của từng phần giúp client và server phối hợp ổn định, dễ kiểm tra và dễ mở rộng.