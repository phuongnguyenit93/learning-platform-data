# Xử lý ngoại lệ bằng @MessageExceptionHandler

Trong ứng dụng RSocket dùng Spring, các method được đánh dấu @MessageMapping tiếp nhận request theo route và trả kết quả bất đồng bộ. Khi xử lý nghiệp vụ, method có thể gặp lỗi như request không hợp lệ, không tìm thấy tài nguyên, không đủ quyền hoặc dịch vụ phụ thuộc tạm thời không hoạt động. Nếu để mỗi handler tự chuyển đổi tất cả lỗi, logic xử lý ngoại lệ dễ bị lặp và phản hồi giữa các route thiếu nhất quán.

Spring cung cấp **@MessageExceptionHandler** để xử lý ngoại lệ phát sinh từ các message handler. Có thể đặt phương thức xử lý lỗi ngay trong controller sở hữu route hoặc dùng **@ControllerAdvice** để áp dụng quy tắc chung cho nhiều controller. Bài học này giải thích cách chọn phạm vi, ánh xạ exception thành phản hồi, giữ đúng ngữ nghĩa của các interaction RSocket và kiểm thử cả lỗi đã được xử lý lẫn lỗi tiếp tục truyền về client.

Sau bài học, bạn có thể:

- Giải thích vai trò của @MessageExceptionHandler trong RSocket responder của Spring.
- Xử lý lỗi cục bộ trong một @Controller hoặc tập trung bằng @ControllerAdvice.
- Ánh xạ loại exception cụ thể thành error DTO có cấu trúc ổn định.
- Phân biệt một error DTO được trả như response payload với lỗi kết thúc interaction.
- Xử lý lỗi phát sinh trong Mono/Flux mà không tách rời pipeline reactive.
- Thiết kế thông tin lỗi an toàn, có correlation ID và không làm lộ chi tiết nội bộ.
- Kiểm thử exception handler bằng StepVerifier và RSocket integration test.

## 1. @MessageExceptionHandler nằm trong luồng xử lý nào?

Spring Messaging dùng @MessageMapping để ánh xạ route của RSocket vào method trong một controller. RSocketMessageHandler phát hiện các controller, phân giải route, chuyển đổi payload thành tham số method và chuyển giá trị trả về thành response payload.

Nếu method hoặc reactive pipeline của nó phát sinh exception, Spring có thể tìm một phương thức @MessageExceptionHandler phù hợp để xử lý lỗi.

~~~mermaid
flowchart TD
    A[Client sends RSocket request] --> B[RSocketMessageHandler]
    B --> C[Resolve route and payload]
    C --> D[@MessageMapping method]
    D --> E{Handler completes?}
    E -->|Yes| F[Encode response payload]
    E -->|No: exception/onError| G[Resolve @MessageExceptionHandler]
    G --> H{Matching handler found?}
    H -->|Yes| I[Invoke exception handler]
    I --> J[Encode handled result]
    H -->|No| K[Propagate interaction error]
~~~

Ví dụ:

~~~java
@Controller
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @MessageMapping("products.get")
    public Mono<ProductView> getProduct(ProductRequest request) {
        return productService.findById(request.productId())
            .switchIfEmpty(Mono.error(
                new ProductNotFoundException(request.productId())
            ));
    }

    @MessageExceptionHandler
    public ProductError handleNotFound(
            ProductNotFoundException exception) {

        return new ProductError(
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm"
        );
    }
}
~~~

Khi ProductService trả Mono rỗng, switchIfEmpty chuyển trạng thái đó thành ProductNotFoundException. Spring tìm handler phù hợp trong controller và gọi handleNotFound. Kết quả ProductError được serialize thành response payload theo cấu hình codec.

@MessageExceptionHandler là cơ chế xử lý lỗi của Spring Messaging. Nó không phải @ExceptionHandler dành cho Spring MVC và cũng không phải một HTTP status handler.

## 2. Khai báo loại exception cần xử lý

Có hai cách phổ biến để cho Spring biết phương thức xử lý loại exception nào.

### Suy ra từ tham số exception

Nếu phương thức nhận một tham số exception, Spring có thể suy ra loại cần xử lý:

~~~java
@MessageExceptionHandler
public ProductError handle(ProductNotFoundException exception) {
    return new ProductError(
        "PRODUCT_NOT_FOUND",
        "Không tìm thấy sản phẩm"
    );
}
~~~

Cách này ngắn gọn khi method chỉ xử lý một loại exception.

### Khai báo rõ trong annotation

Có thể khai báo loại exception trực tiếp trong annotation:

~~~java
@MessageExceptionHandler(AccessDeniedException.class)
public ApiError handleAccessDenied(AccessDeniedException exception) {
    return new ApiError(
        "FORBIDDEN",
        "Bạn không có quyền thực hiện thao tác này"
    );
}
~~~

Khai báo rõ rất hữu ích khi muốn method có chữ ký khác hoặc muốn thể hiện rõ hợp đồng xử lý lỗi ngay tại annotation. Annotation cũng có thể nhận nhiều loại exception:

~~~java
@MessageExceptionHandler({
    InvalidOrderException.class,
    InvalidQuantityException.class
})
public ApiError handleInvalidOrder(RuntimeException exception) {
    return new ApiError(
        "INVALID_ORDER",
        "Thông tin đơn hàng không hợp lệ"
    );
}
~~~

Chỉ gom nhiều exception vào cùng một handler nếu chúng có cùng cách phản hồi. Nếu mỗi loại lỗi cần mã lỗi, mức độ log hoặc hành động khác nhau, hãy tạo handler riêng.

Khi có các handler cho lớp exception cha và lớp con, nên khai báo rõ loại lỗi và tránh các mapping chồng chéo không cần thiết. Hãy kiểm thử để xác nhận loại exception cụ thể được xử lý bởi method mong muốn.

## 3. Phạm vi cục bộ trong controller

Mặc định, phương thức @MessageExceptionHandler áp dụng trong controller nơi nó được khai báo và trong class hierarchy tương ứng. Đây là lựa chọn tốt khi lỗi mang ý nghĩa riêng của một nhóm route.

Ví dụ controller đơn hàng:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.reserve")
    public Mono<ReservationResult> reserve(ReserveRequest request) {
        return orderService.reserve(request);
    }

    @MessageExceptionHandler(InsufficientStockException.class)
    public ReservationResult handleInsufficientStock(
            InsufficientStockException exception) {

        return ReservationResult.rejected(
            exception.productId(),
            "Không đủ hàng trong kho"
        );
    }

    @MessageExceptionHandler(OrderNotFoundException.class)
    public OrderError handleOrderNotFound(
            OrderNotFoundException exception) {

        return new OrderError(
            "ORDER_NOT_FOUND",
            "Không tìm thấy đơn hàng"
        );
    }
}
~~~

Các route trong OrderController có thể dùng chung quy tắc xử lý hai exception này. Controller khác không tự động dùng các handler cục bộ đó.

Nên đặt handler cục bộ khi:

- Exception chỉ có ý nghĩa trong một miền nghiệp vụ.
- Hai route trong cùng controller cần cùng một response DTO.
- Controller cần bổ sung thông tin ngữ cảnh riêng khi chuyển đổi lỗi.
- Cách phản hồi không phù hợp để dùng chung toàn hệ thống.

Không nên đặt mọi lỗi kỹ thuật của toàn ứng dụng vào một controller chỉ vì controller đó đang có sẵn phương thức xử lý lỗi.

## 4. Xử lý lỗi dùng chung bằng @ControllerAdvice

Khi nhiều controller cần cùng quy tắc phản hồi, có thể tách phương thức xử lý ngoại lệ sang một class có @ControllerAdvice.

~~~java
@ControllerAdvice
public class RSocketExceptionAdvice {

    @MessageExceptionHandler(AccessDeniedException.class)
    public ApiError handleAccessDenied(
            AccessDeniedException exception) {

        return new ApiError(
            "FORBIDDEN",
            "Bạn không có quyền thực hiện thao tác này"
        );
    }

    @MessageExceptionHandler(InvalidRequestException.class)
    public ApiError handleInvalidRequest(
            InvalidRequestException exception) {

        return new ApiError(
            "INVALID_REQUEST",
            "Dữ liệu yêu cầu không hợp lệ"
        );
    }
}
~~~

Các controller có thể tiếp tục tập trung vào nghiệp vụ:

~~~java
@Controller
public class InventoryController {

    private final InventoryService inventoryService;

    public InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @MessageMapping("inventory.reserve")
    public Mono<ReservationResult> reserve(ReserveRequest request) {
        return inventoryService.reserve(request);
    }
}
~~~

Spring Boot tự cấu hình hạ tầng Spring Messaging cho RSocket và phát hiện các controller. Một class @ControllerAdvice được Spring quản lý có thể cung cấp các @MessageExceptionHandler dùng chung. Nếu tự cấu hình RSocketMessageHandler, hãy bảo đảm handler được khởi tạo trong ApplicationContext và có thể phát hiện các controller/advice tương ứng.

Có thể dùng các thuộc tính chọn phạm vi của @ControllerAdvice như basePackages, assignableTypes hoặc annotations khi ứng dụng cần giới hạn nhóm controller được áp dụng. Điều này hữu ích khi một ứng dụng có nhiều nhóm API RSocket với quy tắc lỗi khác nhau.

### Khi nào dùng cục bộ, khi nào dùng toàn cục?

| Tiêu chí | Handler trong controller | @ControllerAdvice |
|---|---|---|
| Phạm vi | Controller và class hierarchy | Nhiều controller theo phạm vi advice |
| Lỗi miền đặc thù | Phù hợp | Có thể quá rộng |
| Lỗi chung như invalid request | Có thể lặp | Phù hợp |
| Thông tin ngữ cảnh riêng | Dễ truy cập | Cần truyền qua exception hoặc context |
| Tổ chức mã | Gần route và nghiệp vụ | Tập trung chính sách lỗi |

Một ứng dụng có thể dùng cả hai. Hãy dành handler cục bộ cho lỗi đặc thù, còn advice xử lý các lỗi chung có cùng hợp đồng phản hồi.

## 5. Thiết kế error DTO cho client

Không nên gửi nguyên exception hoặc stack trace cho client. Hãy định nghĩa một DTO ổn định, chỉ chứa thông tin mà bên gọi cần để quyết định bước tiếp theo.

~~~java
public record ApiError(
    String code,
    String message,
    String correlationId
) {}
~~~

Ví dụ chuyển lỗi miền thành DTO:

~~~java
@ControllerAdvice
public class DomainExceptionAdvice {

    @MessageExceptionHandler(ProductNotFoundException.class)
    public ApiError handleProductNotFound(
            ProductNotFoundException exception) {

        return new ApiError(
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm",
            exception.correlationId()
        );
    }
}
~~~

Nên thống nhất các trường:

| Trường | Ý nghĩa | Ví dụ |
|---|---|---|
| code | Mã lỗi ổn định để client xử lý | PRODUCT_NOT_FOUND |
| message | Nội dung an toàn cho người dùng | Không tìm thấy sản phẩm |
| correlationId | Định danh để tra log | req-7f21 |

Client nên dựa vào code thay vì phân tích message. Message có thể được bản địa hóa hoặc thay đổi câu chữ mà không làm hỏng logic client.

Không đưa các thông tin sau vào error DTO công khai:

- Stack trace.
- SQL hoặc câu truy vấn nội bộ.
- Tên host, port, đường dẫn nội bộ.
- Access token, mật khẩu hoặc credential.
- Thông tin cá nhân không cần thiết.
- Chi tiết cấu hình hoặc phiên bản hạ tầng có thể hỗ trợ việc dò tìm hệ thống.

Ghi chi tiết exception ở server log, gắn correlation ID để truy vết. Client chỉ nhận mã lỗi và thông tin cần thiết.

## 6. Exception handler có thể trả về kiểu reactive

@MessageExceptionHandler hỗ trợ các kiểu tham số và kiểu trả về linh hoạt tương tự @MessageMapping. Có thể trả về object trực tiếp, Mono hoặc Flux tùy kết quả và interaction.

Ví dụ trả Mono:

~~~java
@MessageExceptionHandler(ProductNotFoundException.class)
public Mono<ApiError> handleNotFound(
        ProductNotFoundException exception) {

    return Mono.just(new ApiError(
        "PRODUCT_NOT_FOUND",
        "Không tìm thấy sản phẩm",
        exception.correlationId()
    ));
}
~~~

Ví dụ xử lý lỗi của một request-stream:

~~~java
@MessageExceptionHandler(PriceFeedUnavailableException.class)
public Flux<PriceUpdate> handleFeedUnavailable(
        PriceFeedUnavailableException exception) {

    return Flux.just(
        PriceUpdate.unavailable(
            exception.symbol(),
            "Nguồn giá hiện không khả dụng"
        )
    );
}
~~~

Ví dụ stream fallback phát một trạng thái rồi hoàn tất. Hãy bảo đảm kiểu dữ liệu trả về phù hợp với hợp đồng response mà client đang sử dụng.

| Kiểu trả về | Ý nghĩa |
|---|---|
| DTO cụ thể | Một giá trị kết quả đồng bộ |
| Mono<DTO> | Kết quả bất đồng bộ đơn |
| Flux<DTO> | Chuỗi kết quả |
| void hoặc Mono<Void> | Không có response value |

Kiểu trả về của exception handler không thay đổi loại interaction mà requester đã khởi tạo. Ví dụ request-response vẫn là request-response; request-stream vẫn là request-stream. Handler phải trả kết quả phù hợp với cách client đang đọc response.

Với fire-and-forget, requester không có response payload để nhận. Nếu handler xử lý lỗi bằng Mono<Void> hoặc hoàn tất, client không thể xem đó là xác nhận nghiệp vụ thành công. Nếu client cần biết thao tác được chấp nhận hay thất bại, hãy thiết kế request-response hoặc interaction có phản hồi.

## 7. Phân biệt error DTO với lỗi kết thúc interaction

Đây là điểm quan trọng nhất trong hợp đồng API.

Khi @MessageExceptionHandler trả về một DTO, Spring serialize DTO đó thành response payload. Ở tầng RSocket, interaction đã có một response hợp lệ. Client nhận một giá trị và có thể xử lý code trong DTO.

Khi exception không được xử lý, lỗi tiếp tục truyền qua interaction. RSocket kết thúc interaction bằng tín hiệu lỗi; client nhận lỗi reactive qua onError.

| Tình huống | Điều client nhận | Cách xử lý |
|---|---|---|
| Handler trả kết quả bình thường | Response payload | Đọc dữ liệu |
| Exception được chuyển thành error DTO | Response payload chứa mã lỗi | Kiểm tra code |
| Exception không có handler phù hợp | Lỗi interaction | Xử lý onError |
| Kết nối bị đóng hoặc timeout | Lỗi kết nối/timeout | Chính sách phục hồi ở client |
| Fire-and-forget bị lỗi | Không có response payload | Không thể nhận error DTO qua interaction đó |

Ví dụ error DTO:

~~~java
@MessageExceptionHandler(InsufficientBalanceException.class)
public PaymentResult handleInsufficientBalance(
        InsufficientBalanceException exception) {

    return PaymentResult.declined(
        "INSUFFICIENT_BALANCE",
        "Số dư không đủ"
    );
}
~~~

Ví dụ để exception tiếp tục truyền:

~~~java
@MessageMapping("payments.charge")
public Mono<PaymentReceipt> charge(ChargeRequest request) {
    return paymentService.charge(request);
}
~~~

Nếu không có exception handler phù hợp, lỗi phát sinh từ paymentService.charge được truyền về client như lỗi interaction.

Không biến mọi exception thành DTO mặc định. Lỗi nghiệp vụ dự kiến như NOT_FOUND hoặc INSUFFICIENT_BALANCE có thể là kết quả ứng dụng bình thường. Lỗi hạ tầng như database unavailable hoặc lỗi lập trình cần được phân biệt và có thể tiếp tục truyền thành lỗi để client áp dụng retry/fallback phù hợp.

## 8. Xử lý lỗi trong pipeline Mono và Flux

Trong ứng dụng reactive, exception có thể phát sinh ngay khi gọi method hoặc phát ra sau đó dưới dạng onError. Hãy trả publisher cho Spring để framework quan sát toàn bộ vòng đời lỗi.

Ví dụ chuyển empty thành exception:

~~~java
@MessageMapping("orders.get")
public Mono<OrderView> getOrder(OrderRequest request) {
    return orderService.findById(request.orderId())
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(request.orderId())
        ));
}
~~~

Exception handler:

~~~java
@MessageExceptionHandler(OrderNotFoundException.class)
public OrderError handleOrderNotFound(
        OrderNotFoundException exception) {

    return new OrderError(
        "ORDER_NOT_FOUND",
        "Không tìm thấy đơn hàng"
    );
}
~~~

Không gọi subscribe() bên trong @MessageMapping nếu mục tiêu là trả kết quả cho requester:

~~~java
// Không nên: tách công việc khỏi vòng đời request.
@MessageMapping("orders.get")
public Mono<Void> getOrder(OrderRequest request) {
    orderService.findById(request.orderId())
        .subscribe();

    return Mono.empty();
}
~~~

Khi tự subscribe, exception phát sinh trong subscription bên trong không còn nằm trong publisher mà Spring đang quản lý. @MessageExceptionHandler có thể không nhận được lỗi đó. Hãy compose pipeline:

~~~java
@MessageMapping("orders.get")
public Mono<OrderView> getOrder(OrderRequest request) {
    return orderService.findById(request.orderId());
}
~~~

Nếu cần fallback kỹ thuật ngay trong pipeline, dùng onErrorResume. Nếu muốn chuyển exception thành response thống nhất ở tầng message handler, dùng @MessageExceptionHandler. Hai cơ chế có thể phối hợp nhưng giải quyết hai trách nhiệm khác nhau.

### Dùng onErrorResume cho fallback, dùng exception handler cho hợp đồng lỗi

~~~java
@MessageMapping("catalog.product.get")
public Mono<ProductView> getProduct(ProductRequest request) {
    return primaryCatalog.findById(request.productId())
        .onErrorResume(
            CatalogUnavailableException.class,
            error -> cachedCatalog.findById(request.productId())
        )
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(request.productId())
        ));
}
~~~

Trong ví dụ, service thử nguồn dự phòng khi catalog chính tạm thời không hoạt động. Nếu cuối cùng vẫn không tìm thấy sản phẩm, exception handler có thể chuyển ProductNotFoundException thành error DTO.

Không dùng @MessageExceptionHandler thay cho retry hoặc fallback ở tầng service. Exception handler phù hợp để quyết định cách biểu diễn lỗi cho peer.

## 9. Lỗi trong request-stream và request-channel

Một request-stream có thể phát nhiều response trước khi nguồn gặp lỗi. Khi lỗi terminal xảy ra, các response đã phát không bị thu hồi; interaction kết thúc và không phát thêm response item.

Nếu exception handler thay lỗi bằng một Flux fallback, hãy xác định rõ client có thể nhận một sự kiện trạng thái cuối cùng hay không:

~~~java
@MessageMapping("prices.watch")
public Flux<PriceUpdate> watch(WatchPriceRequest request) {
    return priceService.watch(request.symbol());
}

@MessageExceptionHandler(PriceFeedUnavailableException.class)
public Flux<PriceUpdate> handleFeedError(
        PriceFeedUnavailableException exception) {

    return Flux.just(
        PriceUpdate.unavailable(
            exception.symbol(),
            "Không thể tiếp tục nhận dữ liệu"
        )
    );
}
~~~

Nếu nguồn đã phát một số cập nhật rồi mới lỗi, client có thể đã nhận các cập nhật đó trước khi nhận kết quả fallback hoặc lỗi terminal. Ứng dụng cần quy định rõ trạng thái cuối có phải là event trong stream hay stream kết thúc bằng error.

Với request-channel, lỗi có thể phát sinh khi xử lý một phần tử đầu vào hoặc khi tạo response. Hãy kiểm tra cleanup khi input stream bị lỗi hoặc bị hủy; không giữ file handle, subscription hoặc buffer nếu interaction đã kết thúc.

Không giả định một exception handler có thể phục hồi mọi lỗi xảy ra trong transport. Nó xử lý exception thuộc quá trình xử lý message của Spring; lỗi kết nối, SETUP, đóng session hoặc timeout ở phía client cần được xử lý ở tầng connection/client.

## 10. Phân loại lỗi theo miền nghiệp vụ

Một ứng dụng nên định nghĩa exception theo ý nghĩa nghiệp vụ thay vì để client phụ thuộc vào tên class hoặc message nội bộ.

Ví dụ:

~~~java
public class ProductNotFoundException extends RuntimeException {
    private final String productId;

    public ProductNotFoundException(String productId) {
        super("Product not found: " + productId);
        this.productId = productId;
    }

    public String productId() {
        return productId;
    }
}
~~~

~~~java
public class InventoryConflictException extends RuntimeException {
    public InventoryConflictException(String message) {
        super(message);
    }
}
~~~

Sau đó ánh xạ các exception miền thành mã lỗi ổn định:

~~~java
@ControllerAdvice
public class InventoryExceptionAdvice {

    @MessageExceptionHandler(ProductNotFoundException.class)
    public ApiError handleNotFound(ProductNotFoundException exception) {
        return new ApiError(
            "PRODUCT_NOT_FOUND",
            "Không tìm thấy sản phẩm",
            null
        );
    }

    @MessageExceptionHandler(InventoryConflictException.class)
    public ApiError handleConflict(InventoryConflictException exception) {
        return new ApiError(
            "INVENTORY_CONFLICT",
            "Trạng thái kho đã thay đổi, vui lòng thử lại",
            null
        );
    }
}
~~~

Mã lỗi nên ổn định giữa các phiên bản client/server. Có thể bổ sung correlation ID từ metadata hoặc tracing context. Không dùng exception class name làm giao thức công khai vì tên class có thể thay đổi khi refactor.

## 11. Những lỗi không nên xử lý thành thông báo chung

Không nên dùng một handler quá rộng để bắt mọi Throwable rồi trả về "Có lỗi xảy ra" mà không phân loại. Cách này có thể che giấu lỗi lập trình và làm mất tín hiệu cần thiết cho giám sát.

Một số nguyên tắc:

- Validation error: trả mã lỗi đầu vào rõ ràng.
- Not found: trả mã không tìm thấy nếu đó là kết quả nghiệp vụ dự kiến.
- Access denied: trả thông báo an toàn, không tiết lộ tài nguyên có tồn tại hay không nếu chính sách bảo mật yêu cầu.
- Dependency unavailable: ghi log và trả lỗi dịch vụ tạm thời hoặc để lỗi truyền tiếp theo hợp đồng.
- Unexpected runtime exception: ghi log đầy đủ phía server, trả thông báo tổng quát hoặc để interaction kết thúc bằng lỗi.
- Cancellation: dừng công việc có thể dừng và cleanup; không coi cancel là lỗi nghiệp vụ.

Không bắt Error của JVM như OutOfMemoryError để tiếp tục hoạt động bình thường. Những lỗi nghiêm trọng như vậy cần được xử lý ở cấp vận hành và vòng đời tiến trình.

## 12. Xử lý lỗi ở phía RSocketRequester

Nếu server trả error DTO, client nhận nó như một response object:

~~~java
Mono<PaymentResult> result =
    requester.route("payments.charge")
        .data(new ChargeRequest("order-42"))
        .retrieveMono(PaymentResult.class)
        .map(response -> {
            if (response.status().equals("DECLINED")) {
                log.info("Payment declined: {}", response.code());
            }
            return response;
        });
~~~

Nếu server không xử lý exception, client nhận lỗi reactive:

~~~java
Mono<PaymentReceipt> result =
    requester.route("payments.charge")
        .data(new ChargeRequest("order-42"))
        .retrieveMono(PaymentReceipt.class)
        .onErrorResume(error -> {
            log.warn("Payment interaction failed", error);
            return Mono.error(
                new RemotePaymentException("Payment service failed", error)
            );
        });
~~~

Có thể dùng onErrorMap để chuyển lỗi từ tầng RSocket thành exception của client, hoặc onErrorResume để chọn nguồn dự phòng. Chỉ retry nếu lỗi có khả năng tạm thời và thao tác an toàn khi lặp lại. Với lệnh ghi, cần idempotency key để tránh thực hiện giao dịch nhiều lần khi client không nhận được response.

Client không thể dùng retrieveMono(PaymentReceipt.class) để nhận một PaymentResult khác kiểu nếu server có thể trả nhiều loại DTO. Hãy thiết kế một response envelope chung hoặc một kiểu response có discriminator rõ ràng nếu server trả cả success và error như payload.

## 13. Kiểm thử @MessageExceptionHandler

Nên kiểm tra ba lớp hành vi:

1. Exception được ánh xạ thành response DTO đúng.
2. Exception không có handler phù hợp tiếp tục truyền về client.
3. Lỗi phát sinh bất đồng bộ trong Mono/Flux cũng được xử lý theo hợp đồng.

### Kiểm thử handler method

Có thể kiểm tra trực tiếp logic chuyển exception thành DTO:

~~~java
@Test
void mapsProductNotFoundToApiError() {
    ProductExceptionAdvice advice = new ProductExceptionAdvice();

    ApiError error = advice.handleNotFound(
        new ProductNotFoundException("p-42")
    );

    assertThat(error.code()).isEqualTo("PRODUCT_NOT_FOUND");
}
~~~

Unit test này xác nhận mapping dữ liệu nhưng chưa chứng minh Spring đã đăng ký và gọi đúng method xử lý ngoại lệ.

### Kiểm thử tích hợp bằng RSocketRequester

Với Spring Boot test đang chạy RSocket server, gửi request thực tế và xác nhận response payload:

~~~java
@Test
void returnsErrorPayloadForMissingProduct() {
    Mono<ApiError> response = requester
        .route("products.get")
        .data(new ProductRequest("missing-product"))
        .retrieveMono(ApiError.class);

    StepVerifier.create(response)
        .expectNextMatches(error ->
            error.code().equals("PRODUCT_NOT_FOUND")
                && error.message().equals("Không tìm thấy sản phẩm")
        )
        .verifyComplete();
}
~~~

### Kiểm thử exception không được xử lý

~~~java
@Test
void propagatesUnhandledException() {
    Mono<ProductView> response = requester
        .route("products.internal-failure")
        .data(new ProductRequest("p-42"))
        .retrieveMono(ProductView.class);

    StepVerifier.create(response)
        .expectError()
        .verify();
}
~~~

Không ràng buộc test vào message exception nội bộ nếu message đó không phải hợp đồng công khai. Nếu ứng dụng có quy định mã lỗi RSocket cụ thể, hãy kiểm tra mã lỗi theo API phiên bản đang dùng.

### Kiểm thử stream

~~~java
@Test
void streamReturnsTerminalStatusWhenFeedFails() {
    Flux<PriceUpdate> updates = requester
        .route("prices.watch")
        .data(new WatchPriceRequest("ACME"))
        .retrieveFlux(PriceUpdate.class);

    StepVerifier.create(updates)
        .expectNextMatches(update ->
            update.status().equals("UNAVAILABLE")
        )
        .verifyComplete();
}
~~~

Bổ sung test cho trường hợp stream đã phát dữ liệu trước khi lỗi, exception handler tự phát sinh lỗi và client cancel stream. Kiểm tra cả cleanup và log/metric, không chỉ giá trị response.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Dùng @ExceptionHandler của Spring MVC cho RSocket message | Dùng @MessageExceptionHandler trong Spring Messaging |
| Đặt handler trong một controller và mong mọi controller dùng được | Handler cục bộ chỉ áp dụng trong controller/class hierarchy; dùng @ControllerAdvice cho phạm vi chung |
| Trả error DTO nghĩa là interaction vẫn là lỗi | DTO là response payload bình thường ở tầng giao thức |
| Mọi exception đều nên đổi thành DTO | Lỗi không xử lý có thể cần truyền thành lỗi interaction |
| Gọi subscribe() trong @MessageMapping rồi mong exception handler bắt lỗi | Lỗi của subscription tách rời không còn nằm trong pipeline do Spring quản lý |
| Dùng exception handler để retry service | Retry/fallback thuộc reactive service pipeline |
| Dùng exception handler để xử lý disconnect hoặc SETUP failure | Các lỗi kết nối cần xử lý ở tầng connection/client |
| Fire-and-forget có thể gửi error DTO về client | Fire-and-forget không có response payload |
| Gửi stack trace cho client để dễ debug | Ghi chi tiết ở server log và trả mã lỗi an toàn |

## 15. Quy trình thiết kế chính sách ngoại lệ

Khi thêm route RSocket mới, hãy xác định:

1. Những exception nghiệp vụ nào có thể phát sinh?
2. Trường hợp nào là kết quả bình thường cần thể hiện bằng DTO?
3. Trường hợp nào phải kết thúc interaction bằng lỗi?
4. Lỗi có phạm vi một controller hay dùng chung nhiều controller?
5. DTO lỗi có code ổn định và message an toàn không?
6. Có correlation ID để nối log giữa client và server không?
7. Lỗi trong Mono/Flux có nằm trong pipeline Spring quản lý không?
8. Client xử lý error payload và onError ra sao?
9. Test đã xác nhận cả lỗi được xử lý, lỗi chưa xử lý và cancellation chưa?

@MessageExceptionHandler giúp tập trung cách chuyển exception thành phản hồi của RSocket message handler. Khi chọn đúng phạm vi, giữ nguyên ngữ nghĩa của interaction và công bố mã lỗi ổn định, client có thể xử lý lỗi nhất quán mà không phụ thuộc vào chi tiết nội bộ của server.

## Ghi nhớ

- @MessageExceptionHandler xử lý exception phát sinh từ @MessageMapping methods.
- Có thể khai báo exception type trong annotation hoặc suy ra từ tham số exception.
- Handler đặt trong controller có phạm vi cục bộ; @ControllerAdvice cho phép áp dụng quy tắc chung.
- DTO trả về từ exception handler là response payload, không phải error frame.
- Exception không được xử lý tiếp tục kết thúc interaction bằng lỗi.
- Mono/Flux error cần được giữ trong reactive pipeline; tránh subscribe ẩn trong handler.
- Fire-and-forget không có response payload để gửi error DTO.
- Không để lộ stack trace hoặc chi tiết hạ tầng; dùng error code và correlation ID.
- Kiểm thử cả handler cục bộ, advice toàn cục, lỗi chưa xử lý và lỗi trong stream.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — Annotated Controllers and @MessageExceptionHandler](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Boot — RSocket support](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Framework — RSocketMessageHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/annotation/support/RSocketMessageHandler.html)
- [RSocket Protocol](https://rsocket.io/about/protocol/)
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/)

