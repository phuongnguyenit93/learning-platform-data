# Mô hình request-response: một yêu cầu và tối đa một phản hồi

Request-response là mô hình tương tác cơ bản của RSocket: requester gửi một payload để yêu cầu xử lý và responder trả về tối đa một payload kết quả. Mô hình này phù hợp với các thao tác có đầu vào xác định và một kết quả đơn lẻ, chẳng hạn lấy thông tin đơn hàng, kiểm tra tồn kho, xác nhận quyền truy cập hoặc tính phí giao dịch.

Trong Java, Reactor biểu diễn lời gọi request-response bằng Mono. Spring RSocket cung cấp RSocketRequester ở phía client và @MessageMapping ở phía server để ánh xạ route vào handler. Hiểu đúng vòng đời request, response, lỗi và timeout giúp thiết kế API realtime rõ ràng, đồng thời tránh việc retry gây lặp tác dụng phụ.

Sau bài học, bạn có thể:

- Mô tả luồng request-response và các frame chính của một interaction.
- Phân biệt request-response với fire-and-forget, request-stream và request-channel.
- Gửi request và nhận response bằng RSocketRequester.
- Viết handler Spring trả về Mono và xác định rõ trường hợp không có dữ liệu.
- Xử lý lỗi, timeout, hủy request và retry an toàn.
- Kiểm thử hành vi bằng StepVerifier và kiểm thử tích hợp client/server.

## 1. Request-response giải quyết bài toán nào?

Một thao tác nghiệp vụ thường có dạng: gửi một yêu cầu, chờ hệ thống xử lý và nhận một kết quả. Ví dụ:

- Tra cứu đơn hàng theo mã.
- Lấy hồ sơ người dùng.
- Kiểm tra một sản phẩm còn hàng hay không.
- Yêu cầu dịch vụ định giá tính tổng tiền.
- Gửi lệnh xác nhận và nhận trạng thái xử lý.

Với HTTP, ứng dụng thường dùng một request và một response theo chu kỳ của HTTP. RSocket cũng có mô hình một request và một response, nhưng interaction được quản lý bằng stream ID trên một kết nối hai chiều có thể tồn tại lâu dài. RSocket còn cung cấp các mô hình stream và channel khi một response đơn lẻ không đủ.

Request-response phù hợp khi bên gọi cần một kết quả cho một thao tác cụ thể. Nó không phù hợp nếu server cần liên tục đẩy nhiều cập nhật về sau; trường hợp đó nên cân nhắc request-stream.

~~~mermaid
sequenceDiagram
    participant C as Requester
    participant S as Responder
    C->>S: REQUEST_RESPONSE (request payload)
    Note over S: Xử lý request
    alt Thành công
        S-->>C: PAYLOAD (response, NEXT + COMPLETE)
    else Thất bại
        S-->>C: ERROR
    else Request bị hủy trước khi hoàn tất
        C--xS: CANCEL
    end
~~~

Mỗi interaction có một stream ID riêng. Nhiều request-response có thể đang chờ đồng thời trên cùng một kết nối, mỗi interaction được ghép cặp bằng stream ID của nó. Vì vậy, ứng dụng không cần mở một kết nối TCP mới cho mỗi lời gọi.

## 2. Cardinality: một request, tối đa một response

Trong Reactor, kiểu trả về điển hình của request-response là **Mono<T>**:

- Mono có thể phát một giá trị rồi hoàn tất.
- Mono có thể hoàn tất rỗng, tức không phát giá trị.
- Mono có thể kết thúc bằng lỗi.
- Mono không phát nhiều giá trị.

Ở mức hợp đồng nghiệp vụ, request-response thường được thiết kế để trả một response payload. Nếu nghiệp vụ có khả năng “không tìm thấy”, hãy quyết định rõ cách biểu diễn trường hợp đó. Có thể trả một response DTO chứa trạng thái NOT_FOUND, hoặc phát một lỗi miền nếu đó là điều kiện thất bại theo hợp đồng.

Ví dụ DTO có trạng thái rõ ràng:

~~~java
public record GetOrderRequest(String orderId) {}

public record OrderResponse(
    String orderId,
    String status,
    String message
) {
    public static OrderResponse found(Order order) {
        return new OrderResponse(
            order.id(),
            "FOUND",
            order.status()
        );
    }

    public static OrderResponse notFound(String orderId) {
        return new OrderResponse(
            orderId,
            "NOT_FOUND",
            "Không tìm thấy đơn hàng"
        );
    }
}
~~~

Nếu service trả về Mono rỗng, có thể chuyển trạng thái đó thành response cụ thể:

~~~java
Mono<OrderResponse> getOrder(String orderId) {
    return orderRepository.findById(orderId)
        .map(OrderResponse::found)
        .defaultIfEmpty(OrderResponse.notFound(orderId));
}
~~~

Cách này làm cho bên gọi luôn nhận được một đối tượng OrderResponse ở cả trường hợp tìm thấy và không tìm thấy. Nếu hợp đồng yêu cầu không tìm thấy là lỗi, có thể dùng switchIfEmpty(Mono.error(...)) thay cho defaultIfEmpty.

Không nên để client phải suy đoán ý nghĩa của một Mono rỗng. Hãy thống nhất rõ server sẽ trả DTO trạng thái, lỗi miền hay một kết quả không có giá trị theo cách ánh xạ cụ thể của framework đang dùng. Khi cần một response có thể xử lý nhất quán giữa các client, DTO trạng thái thường là lựa chọn dễ hiểu.

## 3. Vòng đời request-response ở tầng giao thức

Requester gửi một REQUEST_RESPONSE frame chứa payload yêu cầu. Frame mang stream ID để liên kết phản hồi với interaction đang mở. Responder xử lý request và kết thúc interaction theo một trong các cách:

| Frame | Hướng truyền | Vai trò |
|---|---|---|
| REQUEST_RESPONSE | Requester → Responder | Gửi request payload và mở interaction |
| PAYLOAD với NEXT và COMPLETE | Responder → Requester | Trả một response payload và kết thúc interaction |
| ERROR | Responder → Requester | Kết thúc interaction bằng lỗi |
| CANCEL | Requester → Responder | Hủy interaction đang chờ xử lý |

### Thành công

Responder trả một PAYLOAD frame với cờ NEXT và COMPLETE. NEXT cho biết frame mang một payload; COMPLETE cho biết interaction kết thúc sau payload này. Không có luồng response tiếp tục như request-stream.

### Lỗi

Nếu responder không thể xử lý request, nó có thể kết thúc interaction bằng ERROR frame. ERROR mang mã lỗi giao thức và thông tin lỗi. Framework có thể ánh xạ lỗi ứng dụng thành lỗi RSocket theo cơ chế của nó.

Một response DTO có trường status="FAILED" vẫn là một response thành công ở tầng giao thức. Ngược lại, ERROR frame kết thúc interaction bằng lỗi. Hai cách biểu diễn có ý nghĩa khác nhau đối với client và cần được lựa chọn có chủ đích.

### Hủy request

Nếu requester không còn cần kết quả, nó có thể hủy subscription. Khi interaction vẫn đang hoạt động, việc hủy được truyền qua CANCEL frame. Responder nên tôn trọng việc hủy để dừng công việc có thể dừng, giải phóng tài nguyên và không tiếp tục xử lý tốn kém khi kết quả không còn được sử dụng.

Việc hủy không thể đảo ngược một tác dụng phụ đã hoàn tất. Nếu server đã ghi dữ liệu trước khi nhận CANCEL, dữ liệu đó vẫn có thể đã được ghi.

## 4. Phân biệt request-response với các interaction khác

| Interaction | Request phía gửi | Response phía nhận | Kiểu Reactor thường dùng |
|---|---|---|---|
| Request-response | Một payload | Tối đa một payload | Mono<T> |
| Fire-and-forget | Một payload | Không có response payload | Mono<Void> cho API gửi |
| Request-stream | Một payload | Không hoặc nhiều payload | Flux<T> |
| Request-channel | Một luồng payload | Một luồng payload | Flux<T> đầu vào và Flux<R> đầu ra |

Ví dụ lựa chọn:

- Lấy một đơn hàng: request-response.
- Gửi một sự kiện audit và không cần xác nhận xử lý: fire-and-forget.
- Theo dõi giá sản phẩm liên tục: request-stream.
- Gửi liên tục dữ liệu cảm biến và nhận kết quả xử lý tương ứng: request-channel.

Không chọn request-response chỉ vì một API hiện tại trả về một giá trị. Nếu yêu cầu thực tế là nhận các cập nhật tiếp tục trong tương lai, request-stream sẽ mô tả đúng hành vi hơn.

## 5. Tạo responder bằng Spring Boot

Spring ánh xạ route của RSocket vào method được đánh dấu @MessageMapping. Method trả về Mono khi xử lý một request-response.

Ví dụ controller:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.get")
    public Mono<OrderResponse> getOrder(GetOrderRequest request) {
        return orderService.findById(request.orderId())
            .map(OrderResponse::found)
            .defaultIfEmpty(
                OrderResponse.notFound(request.orderId())
            );
    }
}
~~~

Requester gửi route "orders.get". Spring dùng routing metadata để tìm method tương ứng. Nội dung data được giải mã thành GetOrderRequest, sau đó kết quả Mono<OrderResponse> được mã hóa thành response payload.

Service nên giữ xử lý bất đồng bộ xuyên suốt:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Mono<Order> findById(String orderId) {
        return orderRepository.findById(orderId);
    }
}
~~~

Nếu repository là reactive repository, không cần block() để lấy kết quả. Việc gọi block() trong handler có thể chặn event-loop thread và làm giảm khả năng phục vụ đồng thời của server.

### Xử lý dữ liệu đầu vào

Kiểm tra request trước khi gọi tầng dữ liệu. Có thể trả lỗi miền nếu dữ liệu không hợp lệ:

~~~java
@MessageMapping("orders.get")
public Mono<OrderResponse> getOrder(GetOrderRequest request) {
    if (request == null
            || request.orderId() == null
            || request.orderId().isBlank()) {
        return Mono.error(
            new InvalidRequestException("orderId là bắt buộc")
        );
    }

    return orderService.findById(request.orderId())
        .map(OrderResponse::found)
        .defaultIfEmpty(
            OrderResponse.notFound(request.orderId())
        );
}
~~~

Ở hệ thống thực tế, nên dùng validation nhất quán với DTO và chuẩn hóa lỗi đầu vào thành mã lỗi ứng dụng mà client hiểu được. Không trả stack trace hoặc thông tin nội bộ của database cho requester.

## 6. Gửi request-response bằng RSocketRequester

RSocketRequester là API fluent của Spring để gửi data và metadata. Ví dụ kết nối qua TCP:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.APPLICATION_JSON)
    .tcp("localhost", 7000);
~~~

Sau khi tạo requester, client gọi route và yêu cầu một response kiểu OrderResponse:

~~~java
Mono<OrderResponse> response = requester
    .route("orders.get")
    .data(new GetOrderRequest("order-42"))
    .retrieveMono(OrderResponse.class);
~~~

Có thể xử lý kết quả bằng các toán tử Reactor:

~~~java
response
    .doOnNext(order -> log.info(
        "Order response status: {}",
        order.status()
    ))
    .doOnError(error -> log.warn(
        "Request-response failed",
        error
    ))
    .subscribe();
~~~

Trong code ứng dụng, thường nên trả Mono từ method của tầng service hoặc controller để caller quyết định subscribe ở ranh giới phù hợp. Tránh subscribe lồng nhau bên trong service vì nó tách vòng đời request khỏi bên gọi và làm lỗi khó được quản lý.

Ví dụ service phía client:

~~~java
@Service
public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester requester) {
        this.requester = requester;
    }

    public Mono<OrderResponse> getOrder(String orderId) {
        return requester
            .route("orders.get")
            .data(new GetOrderRequest(orderId))
            .retrieveMono(OrderResponse.class);
    }
}
~~~

Requester có thể được tái sử dụng cho nhiều lời gọi trên kết nối. Không tạo kết nối mới cho mỗi request nếu ứng dụng có thể dùng lại một kết nối đang hoạt động.

### Gửi metadata kèm request

Route được truyền qua routing metadata. Có thể gửi thêm metadata như correlation ID hoặc tenant context:

~~~java
Mono<OrderResponse> getOrder(
        String orderId,
        String tenantId,
        String correlationId) {

    return requester
        .route("orders.get")
        .metadata(
            new TenantMetadata(tenantId),
            TENANT_METADATA_MIME_TYPE
        )
        .metadata(
            new CorrelationMetadata(correlationId),
            CORRELATION_METADATA_MIME_TYPE
        )
        .data(new GetOrderRequest(orderId))
        .retrieveMono(OrderResponse.class);
}
~~~

Các MIME type tùy chỉnh phải được đăng ký encoder/decoder phù hợp ở hai phía và kết nối phải dùng Composite Metadata. Tenant ID do client gửi chỉ là ngữ cảnh yêu cầu; server vẫn phải xác minh tenant đó thuộc quyền của principal đã xác thực.

## 7. Dùng RSocket Java API trực tiếp

Ở tầng thấp, interface RSocket cung cấp phương thức requestResponse nhận một Payload và trả về Mono<Payload>:

~~~java
Mono<Payload> responsePayload =
    rSocket.requestResponse(
        DefaultPayload.create(
            requestBytes,
            requestMetadata
        )
    );
~~~

Requester và responder làm việc với Payload thay vì DTO. Ứng dụng cần mã hóa data/metadata trước khi gửi và giải mã response sau khi nhận. RSocket Java sử dụng reference counting cho payload và buffer; cần tuân thủ quy tắc ownership của API đang dùng, release payload đúng lúc và không giữ ByteBuf slice vượt quá vòng đời buffer gốc.

Ví dụ đọc response payload ở mức khái niệm:

~~~java
Mono<OrderResponse> response =
    rSocket.requestResponse(requestPayload)
        .map(payload -> {
            try {
                return decodeOrderResponse(payload.getData());
            } finally {
                payload.release();
            }
        });
~~~

Đoạn mã minh họa cần được điều chỉnh theo codec thực tế và ownership của requestPayload trong phiên bản RSocket Java được sử dụng. Nếu dùng Spring RSocketRequester, framework quản lý việc chuyển đổi Payload và DTO, nên ứng dụng thường không cần thao tác ByteBuf trực tiếp.

## 8. Xử lý lỗi ở hai phía

Lỗi request-response thường thuộc một trong các nhóm:

- Request không hợp lệ.
- Không có quyền truy cập tài nguyên.
- Tài nguyên không tồn tại.
- Dịch vụ downstream không sẵn sàng.
- Lỗi serialize/deserialize data hoặc metadata.
- Kết nối bị đóng trong lúc interaction đang chờ.
- Request hết thời gian chờ.

Hãy phân biệt lỗi nghiệp vụ và lỗi hạ tầng. Ví dụ:

~~~java
Mono<OrderResponse> getOrder(String orderId) {
    return orderService.findById(orderId)
        .map(OrderResponse::found)
        .switchIfEmpty(
            Mono.error(new OrderNotFoundException(orderId))
        )
        .onErrorMap(
            DataAccessException.class,
            error -> new OrderServiceUnavailableException(error)
        );
}
~~~

Ở client, có thể chuyển lỗi kỹ thuật thành lỗi phù hợp với tầng gọi:

~~~java
Mono<OrderResponse> response = requester
    .route("orders.get")
    .data(new GetOrderRequest("order-42"))
    .retrieveMono(OrderResponse.class)
    .onErrorMap(
        RSocketException.class,
        error -> new RemoteOrderServiceException(error)
    );
~~~

Không nên gom mọi lỗi thành một response mặc định. Nếu server gặp lỗi database mà trả một DTO giống như "không tìm thấy", client có thể đưa ra quyết định nghiệp vụ sai. Hãy giữ phân biệt giữa NOT_FOUND, FORBIDDEN, INVALID_REQUEST và SERVICE_UNAVAILABLE theo hợp đồng đã công bố.

### Lỗi response và lỗi giao thức

Có hai lựa chọn phổ biến:

1. **Response DTO**: dùng khi đây là kết quả nghiệp vụ bình thường mà client cần đọc, ví dụ trạng thái NOT_FOUND hoặc REJECTED.
2. **ERROR frame**: dùng khi interaction thất bại và không thể trả response theo hợp đồng, ví dụ request sai, không được phép hoặc dịch vụ không thể xử lý.

Đừng đưa thông tin nhạy cảm vào message của lỗi. Server nên ghi log chi tiết nội bộ cùng correlation ID, còn client chỉ nhận thông tin đủ để xử lý.

## 9. Timeout và hủy request

Request-response thường phụ thuộc một dịch vụ khác, vì vậy client cần giới hạn thời gian chờ. Reactor có thể áp dụng timeout:

~~~java
Mono<OrderResponse> getOrder(String orderId) {
    return requester
        .route("orders.get")
        .data(new GetOrderRequest(orderId))
        .retrieveMono(OrderResponse.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

Nếu response không đến trong ba giây, Mono kết thúc bằng TimeoutException. Toán tử timeout hủy subscription upstream; nếu request còn đang hoạt động, RSocket có thể truyền CANCEL để responder biết requester không còn chờ kết quả.

Timeout cần được chọn theo SLA và thời gian xử lý thực tế của dịch vụ. Giá trị quá ngắn làm tăng số request bị hủy dù server có thể hoàn tất ngay sau đó; giá trị quá dài khiến tài nguyên và tác vụ chờ bị giữ lâu.

Có thể ánh xạ timeout thành lỗi ứng dụng:

~~~java
return requester
    .route("orders.get")
    .data(new GetOrderRequest(orderId))
    .retrieveMono(OrderResponse.class)
    .timeout(Duration.ofSeconds(3))
    .onErrorMap(
        TimeoutException.class,
        error -> new OrderRequestTimeoutException(orderId, error)
    );
~~~

Timeout ở client không chứng minh server chưa xử lý request. Server có thể đã ghi dữ liệu và chỉ response bị trễ hoặc thất lạc. Vì vậy, timeout không nên tự động được hiểu là giao dịch đã thất bại hoàn toàn.

## 10. Retry và tính idempotent

Retry có thể hữu ích khi lỗi là tạm thời, nhưng request-response không đảm bảo một thao tác nghiệp vụ chỉ được thực hiện một lần. Ví dụ client gửi yêu cầu tạo thanh toán; server đã tạo giao dịch, nhưng response không về kịp. Client retry có thể tạo giao dịch thứ hai.

Trước khi retry, cần trả lời:

- Lỗi có khả năng tạm thời hay là lỗi nghiệp vụ?
- Server có thể đã nhận và xử lý request chưa?
- Lặp lại request có tạo thêm tác dụng phụ không?
- Có idempotency key để nhận diện cùng một thao tác không?

Ví dụ retry có giới hạn cho một truy vấn đọc:

~~~java
Mono<OrderResponse> getOrder(String orderId) {
    return requester
        .route("orders.get")
        .data(new GetOrderRequest(orderId))
        .retrieveMono(OrderResponse.class)
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(200))
                .filter(this::isTransientFailure)
        );
}
~~~

Ví dụ này thực hiện tối đa hai lần retry sau lần gọi đầu tiên. Chỉ retry những lỗi được xác định là tạm thời. Không retry lỗi validation, lỗi quyền truy cập hoặc lỗi nghiệp vụ không thể tự phục hồi.

Với lệnh ghi, hãy gửi một idempotency key ổn định trong request data hoặc metadata. Server lưu kết quả theo key và trả lại kết quả cũ khi nhận lại cùng một thao tác. Key phải được ràng buộc với người dùng/tenant và loại thao tác phù hợp để tránh dùng nhầm giữa các giao dịch.

## 11. Bảo mật và kiểm soát truy cập

Request-response thường truy cập dữ liệu cụ thể, vì vậy responder phải xác thực và phân quyền ở phía server:

1. Xác thực credential bằng cơ chế bảo mật đã cấu hình.
2. Xác định principal và tenant từ thông tin đã xác thực.
3. Kiểm tra principal có quyền thực hiện route và truy cập tài nguyên được yêu cầu.
4. Kiểm tra quyền trên từng tài nguyên, không chỉ dựa vào route.
5. Chỉ trả các trường mà caller được phép xem.

Không tin userId, tenantId hoặc role do client gửi trong data hay metadata nếu chưa đối chiếu với principal đã xác thực. Metadata chỉ vận chuyển ngữ cảnh; nó không tự tạo ra quyền.

Khi chạy qua mạng không tin cậy, dùng TLS cho TCP hoặc WSS cho WebSocket. Không ghi token, mật khẩu hay dữ liệu nhạy cảm vào log. Với tracing, nên loại bỏ hoặc che các trường có thể chứa thông tin cá nhân.

## 12. Kiểm thử request-response

StepVerifier cho phép kiểm tra giá trị response, lỗi và timeout ở cấp reactive publisher.

Kiểm tra response thành công:

~~~java
@Test
void returnsOrderResponse() {
    Mono<OrderResponse> response =
        Mono.just(new OrderResponse(
            "order-42",
            "FOUND",
            "Đã tìm thấy"
        ));

    StepVerifier.create(response)
        .expectNextMatches(result ->
            result.orderId().equals("order-42")
                && result.status().equals("FOUND")
        )
        .verifyComplete();
}
~~~

Kiểm tra không tìm thấy được ánh xạ thành DTO:

~~~java
@Test
void returnsNotFoundResponse() {
    Mono<OrderResponse> response =
        Mono.<Order>empty()
            .map(OrderResponse::found)
            .defaultIfEmpty(
                OrderResponse.notFound("order-42")
            );

    StepVerifier.create(response)
        .expectNextMatches(result ->
            result.status().equals("NOT_FOUND")
        )
        .verifyComplete();
}
~~~

Kiểm tra lỗi:

~~~java
@Test
void propagatesServiceFailure() {
    Mono<OrderResponse> response =
        Mono.error(
            new OrderServiceUnavailableException(
                new IllegalStateException("database unavailable")
            )
        );

    StepVerifier.create(response)
        .expectError(OrderServiceUnavailableException.class)
        .verify();
}
~~~

Kiểm tra timeout:

~~~java
@Test
void timesOutWhenResponseIsTooSlow() {
    Mono<String> response = Mono.<String>never()
        .timeout(Duration.ofMillis(100));

    StepVerifier.create(response)
        .expectError(TimeoutException.class)
        .verify();
}
~~~

Kiểm thử tích hợp nên chạy requester và responder thật qua transport được triển khai, rồi xác nhận:

- Route được ánh xạ đến đúng @MessageMapping.
- Request DTO được deserialize đúng.
- Response DTO được serialize và deserialize đúng.
- Metadata và quyền truy cập được xử lý đúng.
- Lỗi server đến client theo hợp đồng.
- Timeout hoặc cancel không để lại công việc không cần thiết.
- Nhiều request đồng thời không bị ghép nhầm response.

## 13. Quan sát và vận hành

Request-response thường là điểm nối giữa nhiều dịch vụ. Nên ghi nhận các chỉ số sau:

| Chỉ số | Ý nghĩa |
|---|---|
| Request count | Số request theo route |
| Response latency | Thời gian từ gửi request đến nhận response |
| Error rate | Tỷ lệ interaction kết thúc bằng lỗi |
| Timeout count | Số request vượt thời gian chờ |
| Cancellation count | Số request bị hủy trước khi hoàn tất |
| In-flight requests | Số interaction đang chờ response |
| Payload size | Kích thước data và metadata |

Gắn correlation ID hoặc trace context để liên kết log ở requester, responder và dịch vụ downstream. Không dùng orderId, email hoặc token làm nhãn metric có cardinality cao hoặc chứa thông tin nhạy cảm.

Khi điều tra request chậm, hãy tách thời gian kết nối, thời gian chờ xử lý server, thời gian gọi downstream và thời gian serialize/deserialize. Đo riêng từng giai đoạn giúp xác định nơi gây trễ thay vì chỉ tăng timeout.

## 14. Quy trình thiết kế một API request-response

Khi tạo một route mới, hãy xác định lần lượt:

1. Request DTO gồm những trường nào và validation ra sao?
2. Response DTO thể hiện thành công, không tìm thấy và trạng thái nghiệp vụ như thế nào?
3. Lỗi nào được trả thành response status, lỗi nào kết thúc interaction bằng ERROR?
4. Route, authentication, tenant và tracing metadata được truyền ra sao?
5. Timeout phù hợp với SLA của thao tác là bao lâu?
6. Có cần retry không, và thao tác có idempotent không?
7. Cần metric, log và trace nào để theo dõi interaction?
8. Kiểm thử đồng thời, lỗi, timeout, cancel và serialization đã đủ chưa?

Một request-response tốt có hợp đồng đầu vào/đầu ra rõ ràng, kết thúc đúng thời hạn và giữ được ngữ nghĩa lỗi. Với các thao tác cần nhiều response hoặc cần dữ liệu cập nhật liên tục, hãy chọn interaction khác phù hợp với cardinality thay vì kéo dài một request-response thành một luồng ngầm định.

## Ghi nhớ

- Request-response gửi một request payload và trả tối đa một response payload.
- Trong Reactor, Mono biểu diễn kết quả 0..1; hãy xác định rõ chính sách khi không có giá trị.
- RSocket liên kết interaction bằng stream ID; response thành công kết thúc bằng PAYLOAD có NEXT và COMPLETE, còn lỗi dùng ERROR.
- Spring dùng RSocketRequester ở client và @MessageMapping ở responder.
- Timeout có thể dẫn đến hủy request, nhưng không chứng minh server chưa thực hiện tác dụng phụ.
- Retry phải dựa trên lỗi tạm thời và tính idempotent của thao tác.
- Xác thực, phân quyền, tracing và kiểm thử cần được thiết kế cùng hợp đồng route.

## Tài liệu tham khảo

- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [RSocket Protocol: Request-Response](https://github.com/rsocket/rsocket/blob/master/Protocol.md)
- [Spring Framework: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [RSocket Java](https://github.com/rsocket/rsocket-java)

