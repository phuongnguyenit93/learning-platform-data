# Metadata định tuyến (routing metadata) và tên tuyến xử lý

Trong một ứng dụng RSocket, một connection có thể mang nhiều tương tác độc lập. Server cần biết mỗi request phải được chuyển tới handler nào, trong khi payload vẫn chứa dữ liệu nghiệp vụ cần xử lý. RSocket giải quyết việc định tuyến ở cấp message bằng routing metadata: client gửi một tên tuyến xử lý (route name) trong metadata, server dùng tên đó để tìm handler tương ứng.

Routing metadata giúp tách thông tin điều khiển khỏi dữ liệu nghiệp vụ. Ví dụ, khi client gọi tuyến <code>orders.find</code>, route cho biết yêu cầu cần đi tới chức năng tìm đơn hàng; payload mang mã đơn hàng cần tìm. Hai phần có vai trò khác nhau và được giải mã theo cách khác nhau.

## 1. Phân biệt data, metadata và route

Một RSocket Payload có thể chứa hai phần độc lập:

| Thành phần | Mục đích | Ví dụ |
| --- | --- | --- |
| Data | Nội dung nghiệp vụ của message. | Mã đơn hàng, thông tin người dùng, dữ liệu cảm biến. |
| Metadata | Thông tin mô tả hoặc điều khiển message. | Route, tenant, thông tin xác thực, correlation ID, tracing context. |

Data thường được serialize thành JSON, CBOR, Protobuf hoặc định dạng mà hai phía đã thống nhất. Metadata có MIME type riêng để receiver biết cách giải mã. Một message có thể không có data, không có metadata hoặc có cả hai, tùy interaction và hợp đồng ứng dụng.

Route là một giá trị trong routing metadata. Nó trả lời câu hỏi “message này gọi chức năng nào?”. Data trả lời câu hỏi “chức năng đó cần xử lý dữ liệu gì?”. Ví dụ:

~~~text
RSocket request
  |
  +-- metadata
  |     |
  |     +-- routing: orders.find
  |     +-- tenant: tenant-42
  |     +-- tracing: trace context
  |
  +-- data
        |
        +-- { "orderId": "ORD-2026-018" }
~~~

Tên route không phải địa chỉ IP, cổng TCP hay URL HTTP. Nó là định danh ở tầng ứng dụng được gửi trong metadata của một tương tác RSocket. Nhiều route khác nhau có thể được xử lý trên cùng một transport connection.

## 2. Routing metadata hoạt động như thế nào?

RSocket định nghĩa MIME type dành cho routing metadata là <code>message/x.rsocket.routing.v0</code>. Nội dung routing metadata là một chuỗi tag. Mỗi tag được mã hóa bằng UTF-8 và có byte độ dài đứng trước; vì trường độ dài chiếm một byte, một tag riêng lẻ bị giới hạn tối đa 255 byte sau khi mã hóa.

Ở mức ứng dụng, tag thường là tên tuyến như <code>orders.find</code> hoặc <code>inventory.stock.watch</code>. Framework phía server đọc routing metadata, lấy route name và so khớp với các handler đã đăng ký.

Quá trình xử lý có thể hình dung như sau:

~~~text
Client
  |
  |  route = "orders.find"
  |  data  = OrderQuery(orderId)
  v
RSocket Payload
  |
  +-- routing metadata
  |       "orders.find"
  |
  +-- data
          OrderQuery
  |
  v
RSocket Server
  |
  |  đọc routing metadata
  |  tìm handler khớp route
  v
@MessageMapping("orders.find")
  |
  v
OrderService.find(...)
~~~

Khi metadata chỉ chứa một loại metadata, hai bên có thể dùng MIME type metadata đã thỏa thuận cho phiên. Trong ứng dụng cần mang nhiều loại metadata cùng lúc, RSocket thường dùng Composite Metadata với MIME type <code>message/x.rsocket.composite-metadata.v0</code>. Composite Metadata đóng gói nhiều entry, mỗi entry có MIME type và nội dung riêng. Nhờ vậy, routing metadata có thể cùng tồn tại với metadata xác thực, tracing hoặc metadata nghiệp vụ khác.

Routing metadata và Composite Metadata là hai khái niệm khác nhau: routing metadata là nội dung định tuyến; Composite Metadata là định dạng bao ngoài để mang nhiều entry metadata. Không nên nhầm MIME type của Composite Metadata với MIME type của route entry bên trong.

## 3. Đặt tên route rõ ràng và ổn định

Route name là một phần của hợp đồng giao tiếp giữa client và server. Khi client và server được triển khai hoặc phát hành độc lập, việc đổi route có thể làm các client cũ không còn tìm được handler. Vì vậy, tên route cần có quy ước nhất quán và được quản lý như API.

Một quy ước dễ đọc là dùng các phần theo miền nghiệp vụ, tài nguyên và hành động:

| Route | Ý nghĩa |
| --- | --- |
| <code>orders.find</code> | Tìm một đơn hàng. |
| <code>orders.create</code> | Tạo đơn hàng. |
| <code>orders.events.watch</code> | Theo dõi sự kiện của đơn hàng. |
| <code>inventory.stock.get</code> | Đọc số lượng tồn kho. |
| <code>inventory.stock.watch</code> | Theo dõi thay đổi tồn kho. |
| <code>users.profile.update</code> | Cập nhật hồ sơ người dùng. |

Một route tốt nên:

- Thể hiện chức năng hoặc tài nguyên nghiệp vụ, không phụ thuộc tên class Java hay tên method nội bộ.
- Có quy tắc viết nhất quán, chẳng hạn chữ thường và dấu chấm phân cấp.
- Đủ cụ thể để tránh hai handler cùng nhận một route ngoài ý muốn.
- Ổn định qua các lần refactor nội bộ.
- Có chiến lược tương thích khi cần thay đổi hợp đồng, ví dụ thêm phiên bản route hoặc duy trì route cũ trong giai đoạn chuyển đổi.

Không nên đưa mã người dùng, mã đơn hàng hoặc giá trị thay đổi theo từng request vào route. Những giá trị đó thuộc payload hoặc metadata ngữ cảnh. Ví dụ, dùng <code>orders.find</code> làm route và truyền <code>orderId</code> trong data sẽ dễ kiểm thử, kiểm soát quyền và thống kê hơn route dạng <code>orders.find.ORD-2026-018</code>.

Tên route cũng không nên chứa bí mật, token truy cập hoặc thông tin cá nhân. Route thường xuất hiện trong log, metric và trace; hãy coi nó là định danh API có thể được quan sát bởi hạ tầng vận hành.

## 4. Khai báo route ở phía server bằng Spring Boot

Trong Spring Boot RSocket, handler có thể được khai báo bằng <code>@MessageMapping</code>. Giá trị annotation là route mà server dùng để ánh xạ request tới method.

~~~java
@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(OrderQuery query) {
        return orderService.find(query.orderId());
    }

    @MessageMapping("orders.events.watch")
    public Flux<OrderEvent> watch(OrderWatchRequest request) {
        return orderService.watch(request.orderId());
    }

    @MessageMapping("orders.create")
    public Mono<OrderView> create(CreateOrderCommand command) {
        return orderService.create(command);
    }
}
~~~

Ở đây, route được dùng để chọn method; các tham số method là data được giải mã thành kiểu Java tương ứng. <code>Mono&lt;OrderView&gt;</code> biểu diễn kết quả đơn lẻ hoặc rỗng, còn <code>Flux&lt;OrderEvent&gt;</code> biểu diễn luồng nhiều sự kiện. Kiểu trả về cũng tham gia xác định cách tương tác được xử lý.

Route là một phần của message mapping, không phải tên bean hoặc tên method. Có thể đổi tên method Java mà không phải đổi route nếu hợp đồng bên ngoài vẫn giữ nguyên. Ngược lại, đổi chuỗi trong <code>@MessageMapping</code> là thay đổi hợp đồng mà client cần biết.

Spring cũng hỗ trợ các mẫu route và biến route theo cơ chế mapping của framework. Khi dùng mẫu động, cần thống nhất quy ước với client và kiểm tra rõ ràng các trường hợp trùng hoặc mơ hồ. Với API công khai hoặc được nhiều nhóm sử dụng, route tĩnh và cụ thể thường dễ quản lý hơn.

## 5. Gọi route từ client bằng RSocketRequester

<code>RSocketRequester</code> cung cấp API mức cao để tạo request. Phương thức <code>route(...)</code> chỉ định route name; <code>data(...)</code> gắn payload nghiệp vụ; phương thức <code>retrieve...</code> xác định kiểu phản hồi mong đợi.

Ví dụ gọi request-response:

~~~java
Mono<OrderView> result = requester
    .route("orders.find")
    .data(new OrderQuery("ORD-2026-018"))
    .retrieveMono(OrderView.class);
~~~

Client gửi route <code>orders.find</code> trong routing metadata và gửi <code>OrderQuery</code> trong data. Server tìm method <code>@MessageMapping("orders.find")</code>, giải mã data thành <code>OrderQuery</code> rồi trả về <code>OrderView</code>.

Ví dụ đăng ký request-stream:

~~~java
Flux<OrderEvent> events = requester
    .route("orders.events.watch")
    .data(new OrderWatchRequest("ORD-2026-018"))
    .retrieveFlux(OrderEvent.class);

events.subscribe(
    event -> log.info("Order event: {}", event),
    error -> log.error("Không thể theo dõi đơn hàng", error)
);
~~~

Mỗi phần tử server phát ra trở thành một giá trị trong <code>Flux</code>. Client có thể kết hợp luồng này với các toán tử Reactor, áp dụng timeout, xử lý lỗi hoặc hủy subscription khi không còn cần theo dõi.

Đối với fire-and-forget:

~~~java
Mono<Void> sent = requester
    .route("orders.audit.record")
    .data(new AuditRecord("ORD-2026-018", "VIEWED"))
    .send();
~~~

<code>send()</code> không cung cấp một response nghiệp vụ từ handler. Việc Publisher hoàn tất cho biết thao tác gửi ở phía client đã hoàn thành theo ngữ nghĩa của API; nó không phải bằng chứng rằng nghiệp vụ phía server đã xử lý và lưu dữ liệu thành công. Nếu cần xác nhận kết quả xử lý, hãy dùng request-response hoặc một cơ chế xác nhận riêng.

Với request-channel, client có thể gửi một luồng data và nhận một luồng phản hồi:

~~~java
Flux<StockUpdate> updates = requester
    .route("inventory.stock.sync")
    .data(stockCommandFlux)
    .retrieveFlux(StockUpdate.class);
~~~

Trong trường hợp này, route vẫn xác định handler cho tương tác channel. Publisher truyền vào <code>data(...)</code> là luồng đầu vào của client; <code>retrieveFlux(...)</code> biểu diễn luồng đầu ra mà server trả về. Cả hai chiều có vòng đời và nhu cầu dữ liệu riêng.

## 6. Kết hợp routing metadata với metadata khác

Một request có thể cần thêm tenant ID, thông tin xác thực, correlation ID hoặc tracing context. Những giá trị này không nên nhồi vào route name hay data nghiệp vụ nếu chúng có vai trò là ngữ cảnh của message.

Khi sử dụng Spring RSocket, có thể gắn metadata tùy chỉnh với MIME type đã thống nhất giữa hai phía. Ví dụ sau minh họa ý tưởng truyền tenant metadata:

~~~java
MimeType tenantMimeType =
    MimeTypeUtils.parseMimeType("application/vnd.example.tenant");

Mono<OrderView> result = requester
    .route("orders.find")
    .metadata(new TenantMetadata("tenant-42"), tenantMimeType)
    .data(new OrderQuery("ORD-2026-018"))
    .retrieveMono(OrderView.class);
~~~

Để nhiều entry metadata cùng tồn tại, phiên cần sử dụng Composite Metadata làm metadata MIME type và hai phía phải đăng ký hoặc hỗ trợ các MIME type của từng entry. Spring RSocket có thể thực hiện việc mã hóa và giải mã thông qua metadata encoder/decoder được cấu hình trong <code>RSocketStrategies</code>.

Ở phía server, có thể trích xuất metadata bằng <code>@Header</code> nếu metadata đã được framework chuyển thành header tương ứng, hoặc dùng cơ chế metadata extraction phù hợp với phiên bản Spring đang dùng. Ví dụ về ý tưởng xử lý:

~~~java
@MessageMapping("orders.find")
public Mono<OrderView> find(
        OrderQuery query,
        @Header("tenant") String tenantId) {
    return orderService.findForTenant(tenantId, query.orderId());
}
~~~

Tên header cụ thể phụ thuộc vào cách cấu hình <code>MetadataExtractor</code> và metadata key được ánh xạ. Client và server phải thống nhất tên, MIME type, định dạng và quy tắc giải mã; chỉ gửi một object metadata mà không cấu hình decoder tương ứng sẽ không tự động biến nó thành header Java.

Composite Metadata hữu ích khi nhiều concern độc lập cần chia sẻ cùng một request:

| Entry metadata | Vai trò |
| --- | --- |
| Routing metadata | Chọn handler hoặc route. |
| Authentication metadata | Mang credential hoặc token theo cơ chế bảo mật đã thống nhất. |
| Tenant metadata | Xác định tenant để áp dụng ranh giới dữ liệu. |
| Tracing metadata | Truyền trace/span context qua các dịch vụ. |
| Custom metadata | Mang ngữ cảnh nghiệp vụ bổ sung khi cần. |

Mỗi entry nên có MIME type riêng và hợp đồng rõ ràng. Không nên dùng một entry tùy ý rồi để receiver đoán định dạng bằng cách phân tích chuỗi.

## 7. Route name và interaction model

Route chỉ định chức năng được gọi; interaction model xác định cách trao đổi dữ liệu. Cùng một quy ước route có thể được dùng cho các kiểu tương tác khác nhau, nhưng hợp đồng giữa client và server phải thống nhất kiểu phản hồi.

| Interaction model | API client thường dùng | Kiểu handler thường gặp | Ví dụ route |
| --- | --- | --- | --- |
| Request-response | <code>retrieveMono(T.class)</code> | <code>Mono&lt;T&gt;</code> | <code>orders.find</code> |
| Fire-and-forget | <code>send()</code> | <code>Mono&lt;Void&gt;</code> hoặc handler không trả response nghiệp vụ | <code>orders.audit.record</code> |
| Request-stream | <code>retrieveFlux(T.class)</code> | <code>Flux&lt;T&gt;</code> | <code>orders.events.watch</code> |
| Request-channel | <code>data(Publisher).retrieveFlux(T.class)</code> | Nhận <code>Flux&lt;I&gt;</code> và trả <code>Flux&lt;O&gt;</code> | <code>inventory.stock.sync</code> |

Không nên chọn interaction model chỉ dựa trên tên route. Một route tên <code>orders.events.watch</code> gợi ý stream nhưng chính kiểu API client và chữ ký handler mới xác định cách trao đổi. Nếu client gọi <code>retrieveMono</code> trong khi handler trả về một luồng không hoàn tất, request có thể không cho kết quả như mong đợi.

## 8. Xử lý route không hợp lệ và lỗi định tuyến

Một request có thể không tìm được handler vì nhiều lý do:

- Client gửi route name sai chính tả hoặc dùng route cũ.
- Server chưa triển khai handler tương ứng.
- Route pattern không khớp với giá trị metadata thực tế.
- Có nhiều mapping xung đột hoặc mơ hồ.
- Client và server không thống nhất cách phân tách hoặc chuẩn hóa route.

Khi không có handler phù hợp, server có thể kết thúc tương tác bằng lỗi. Client cần xử lý lỗi bất đồng bộ ở <code>Mono</code> hoặc <code>Flux</code>; không nên giả định mọi lỗi đều là lỗi mạng. Hãy phân loại lỗi định tuyến, lỗi xác thực, lỗi nghiệp vụ và lỗi transport để quyết định có nên retry hay không.

Một số thực hành hữu ích:

1. Khai báo route trong hằng số hoặc một lớp contract dùng chung khi client và server cùng nằm trong một hệ sinh thái build.
2. Nếu hai bên phát hành độc lập, công bố danh mục route và phiên bản hợp đồng.
3. Thêm kiểm thử contract xác nhận route quan trọng có handler và client có thể gọi được.
4. Ghi log route name khi lỗi, nhưng tránh ghi data nhạy cảm hoặc toàn bộ metadata xác thực.
5. Khi đổi route, duy trì route cũ trong thời gian chuyển tiếp nếu vẫn còn client phiên bản trước.

## 9. Bảo mật khi dùng routing metadata

Route name là dữ liệu do client gửi. Server không được coi việc client gọi được một route là bằng chứng client có quyền thực hiện nghiệp vụ đó. Việc định tuyến và việc cấp quyền là hai bước riêng biệt.

Ví dụ, <code>orders.find</code> có thể được gọi bởi nhiều tenant, nhưng server vẫn phải xác minh người dùng được phép xem đơn hàng cụ thể và đơn hàng thuộc tenant phù hợp. Không được chỉ dựa vào tenant ID do client gửi trong metadata để quyết định quyền truy cập; giá trị này phải được ràng buộc với danh tính đã xác thực.

Các nguyên tắc cần tuân thủ:

- Xác thực connection hoặc request theo cơ chế bảo mật của hệ thống.
- Kiểm tra quyền trên từng route và trên tài nguyên mà payload tham chiếu.
- Xác minh tenant context với principal đã xác thực.
- Giới hạn các route được phép gọi từ từng loại client.
- Không đưa token, mật khẩu hoặc dữ liệu cá nhân vào route name.
- Không ghi credential hoặc metadata nhạy cảm vào log, trace hay metric.
- Giới hạn kích thước metadata và data để giảm nguy cơ tiêu thụ tài nguyên bất thường.

Metadata là một phần của giao thức message, không mặc nhiên được mã hóa hoặc bảo vệ chỉ vì nó nằm ngoài data. Nếu cần bảo mật khi truyền qua mạng, hãy cấu hình TLS và cơ chế xác thực phù hợp cho transport/session.

## 10. Kiểm thử routing metadata và route name

Nên kiểm tra cả hai phía của hợp đồng: client phát đúng route và server ánh xạ đúng handler. Với Spring, có thể viết integration test khởi chạy RSocket server trên transport thử nghiệm rồi dùng <code>RSocketRequester</code> gửi request tới route thực tế.

Ở mức kiểm thử pipeline Reactor, <code>StepVerifier</code> giúp xác nhận response và lỗi:

~~~java
StepVerifier.create(
        requester.route("orders.find")
            .data(new OrderQuery("ORD-2026-018"))
            .retrieveMono(OrderView.class))
    .assertNext(order -> {
        assertEquals("ORD-2026-018", order.orderId());
    })
    .verifyComplete();
~~~

Các trường hợp nên có:

- Route hợp lệ trả về đúng kiểu dữ liệu.
- Route stream phát nhiều phần tử và hoàn tất đúng cách.
- Route fire-and-forget không tạo response nghiệp vụ.
- Route không tồn tại trả lỗi mà client có thể quan sát.
- Metadata tenant được giải mã và áp dụng đúng ranh giới dữ liệu.
- Thiếu hoặc sai metadata bắt buộc bị từ chối.
- Client cũ gọi route cũ trong thời gian tương thích vẫn hoạt động nếu hệ thống cam kết hỗ trợ.
- Các route nhạy cảm từ chối principal không đủ quyền.

Nếu tự kiểm thử encoding ở tầng thấp, cần xác nhận MIME type, tag UTF-8 và giới hạn độ dài theo định dạng RSocket. Trong đa số ứng dụng Spring, nên dùng API routing và metadata của framework thay vì tự ghép byte thủ công.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể có | Hướng xử lý |
| --- | --- | --- |
| Server không tìm thấy handler | Route client và <code>@MessageMapping</code> không khớp. | So sánh route name chính xác và kiểm tra mapping đã được đăng ký. |
| Data giải mã sai kiểu | Client và server không thống nhất data MIME type hoặc schema. | Đồng bộ serializer, MIME type và phiên bản DTO. |
| Metadata tùy chỉnh không xuất hiện ở server | Chưa cấu hình Composite Metadata, MIME type hoặc extractor/decoder. | Kiểm tra metadata MIME type và <code>RSocketStrategies</code>. |
| Route động khớp sai handler | Pattern bị chồng lấn hoặc quy ước phân cấp không rõ. | Làm rõ pattern và thêm kiểm thử cho trường hợp biên. |
| Request bị từ chối dù route đúng | Lỗi xác thực, tenant hoặc quyền trên tài nguyên. | Kiểm tra principal và chính sách authorization riêng với định tuyến. |
| Log và metric có quá nhiều nhãn | Dùng ID động làm route hoặc label. | Dùng route name ổn định; đưa ID động vào log có kiểm soát hoặc trace. |

## 12. Ghi nhớ

- Routing metadata mang route name để server tìm handler cho một message.
- Data chứa nội dung nghiệp vụ; metadata chứa thông tin định tuyến và ngữ cảnh.
- MIME type routing metadata là <code>message/x.rsocket.routing.v0</code>; Composite Metadata có thể đóng gói routing cùng các entry metadata khác.
- Trong Spring RSocket, <code>RSocketRequester.route(...)</code> gửi route từ client và <code>@MessageMapping(...)</code> khai báo handler ở server.
- Route name là hợp đồng API: cần ổn định, có quy ước và có chiến lược tương thích khi thay đổi.
- Route không thay thế xác thực hoặc phân quyền. Server vẫn phải kiểm tra principal, tenant và quyền truy cập tài nguyên.
- Hãy kiểm thử route hợp lệ, route không tồn tại, metadata tùy chỉnh, các interaction model và các trường hợp không đủ quyền.
