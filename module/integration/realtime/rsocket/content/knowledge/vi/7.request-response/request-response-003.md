# Biểu diễn phản hồi có dữ liệu, hoàn thành rỗng và thất bại

Request-response là interaction model của RSocket dành cho thao tác gửi một request và nhận tối đa một kết quả. Trong Java, Reactor thường biểu diễn kết quả đó bằng **Mono<T>**. Một Mono có thể phát một giá trị rồi hoàn tất, hoàn tất mà không phát giá trị, hoặc kết thúc bằng lỗi. Ba trạng thái này mang ý nghĩa khác nhau đối với client và cần được thiết kế rõ ràng ở cả server lẫn client.

Ví dụ, khi tìm đơn hàng, server có thể trả về đơn hàng tìm thấy, cho biết không có đơn hàng phù hợp, hoặc báo lỗi khi request không hợp lệ hay dịch vụ lưu trữ gặp sự cố. Cách chọn giữa một phản hồi có dữ liệu, một completion rỗng và một lỗi ảnh hưởng đến cách client hiển thị kết quả, retry, ghi log và xử lý nghiệp vụ.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Mô tả ba trạng thái kết thúc của **Mono** trong một request-response.
- Triển khai handler Spring RSocket trả về kết quả có dữ liệu, rỗng hoặc lỗi.
- Phân biệt trường hợp không tìm thấy dữ liệu với lỗi kỹ thuật và lỗi nghiệp vụ.
- Xử lý empty completion và error signal ở phía client.
- Chọn thời điểm dùng response DTO có kiểu kết quả rõ ràng thay vì dùng lỗi cho mọi trường hợp.
- Áp dụng timeout, retry có điều kiện và cancellation mà không làm sai ngữ nghĩa request.
- Kiểm thử từng trạng thái bằng Reactor Test và StepVerifier.

## 1. Request-response và Mono

Request-response gồm một request từ requester và một kết quả từ responder. Nó phù hợp với các thao tác như đọc hồ sơ, kiểm tra trạng thái đơn hàng, tính phí hoặc xác nhận một lệnh.

Trong Spring RSocket, handler thường trả về **Mono<T>**:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderView> find(@Payload OrderQuery query) {
        return orderService.findById(query.orderId());
    }
}
~~~

Phía client dùng **RSocketRequester** để gửi request và giải mã response thành kiểu mong muốn:

~~~java
Mono<OrderView> response = requester
        .route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class);
~~~

**retrieveMono(OrderView.class)** trả về một Mono. Client cần xử lý cả ba khả năng: có OrderView, không có giá trị nhưng hoàn tất, hoặc kết thúc bằng lỗi. Không nên giả định rằng mọi request thành công đều nhất thiết phát ra một object.

### 1.1. Ba trạng thái của Mono

| Trạng thái | Tín hiệu Reactor | Ý nghĩa ở tầng ứng dụng |
|---|---|---|
| Có dữ liệu | **onNext(value)** rồi **onComplete()** | Server trả về một kết quả |
| Hoàn thành rỗng | **onComplete()** mà không có **onNext** | Request hoàn tất thành công nhưng không có giá trị |
| Thất bại | **onError(error)** | Request không hoàn tất thành công; client nhận lỗi |

Một Mono chỉ phát tối đa một giá trị. Sau **onComplete** hoặc **onError**, publisher đã kết thúc và không phát thêm tín hiệu. **onError** là tín hiệu terminal; nếu muốn phục hồi, phải chuyển sang một publisher khác bằng operator như **onErrorResume** hoặc thực hiện retry.

Ở ranh giới RSocket, runtime chuyển kết quả reactive thành tín hiệu của interaction. Một response có dữ liệu được gửi dưới dạng payload hoàn tất; một kết quả rỗng được quan sát ở client như completion mà không có giá trị ứng dụng; lỗi được truyền qua đường lỗi của interaction. Cách biểu diễn byte cụ thể của payload rỗng phụ thuộc vào adapter và codec, vì vậy code ứng dụng nên dựa trên semantics của Mono thay vì giả định có một object rỗng.

## 2. Phản hồi thành công có dữ liệu

Khi tìm thấy dữ liệu, service phát một giá trị. **Mono.just** phù hợp khi giá trị đã có sẵn:

~~~java
public Mono<OrderView> findCached(String orderId) {
    OrderView cached = cache.get(orderId);

    if (cached == null) {
        return Mono.empty();
    }

    return Mono.just(cached);
}
~~~

Với thao tác bất đồng bộ, repository hoặc service thường trả về Mono:

~~~java
public Mono<OrderView> findById(String orderId) {
    return orderRepository.findById(orderId)
            .map(order -> new OrderView(
                    order.getId(),
                    order.getStatus(),
                    order.getTotal()
            ));
}
~~~

Nếu repository tìm thấy đơn hàng, **map** chuyển entity thành DTO và Mono phát đúng một OrderView. Khi client nhận giá trị, có thể tiếp tục xử lý bằng **map**, **flatMap** hoặc **doOnNext**:

~~~java
Mono<OrderView> response = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .doOnNext(order -> log.info(
                "Received order {} with status {}",
                order.id(), order.status()
        ));
~~~

**doOnNext** chỉ chạy khi Mono phát giá trị. Nó không chạy khi response hoàn tất rỗng. Nếu cần quan sát mọi kết thúc, kể cả rỗng và lỗi, hãy chọn các hook phù hợp như **doOnSuccess**, **doOnError** và **doFinally**, đồng thời hiểu rằng tham số của **doOnSuccess** có thể là null khi Mono hoàn tất rỗng.

### 2.1. Không dùng null làm response

Reactive Streams không cho phép phát null như một phần tử. Đoạn code sau là sai:

~~~java
// Không hợp lệ: Mono.just không chấp nhận null.
return Mono.just(null);
~~~

Nếu không có giá trị, dùng **Mono.empty()**. Nếu có một giá trị hợp lệ, dùng **Mono.just(value)** hoặc publisher bất đồng bộ tương ứng. **Mono.fromCallable** cũng hoàn tất rỗng khi callable trả về null, nhưng nên tránh trả null nếu có thể biểu diễn trạng thái rõ ràng hơn.

## 3. Hoàn thành rỗng: request thành công nhưng không có giá trị

**Mono.empty()** phát **onComplete** mà không phát **onNext**. Đây không phải lỗi. Nó diễn đạt rằng thao tác đã kết thúc bình thường nhưng không có kết quả để trả về.

Ví dụ, repository không tìm thấy đơn hàng:

~~~java
public Mono<OrderView> findById(String orderId) {
    return orderRepository.findById(orderId)
            .map(this::toView);
}
~~~

Nếu repository trả về **Mono.empty()**, handler cũng hoàn tất rỗng. Điều này có thể phù hợp khi “không có bản ghi” là kết quả bình thường của truy vấn.

Một thao tác không cần giá trị trả về cũng có thể dùng **Mono<Void>**:

~~~java
public Mono<Void> recordAuditEvent(AuditEvent event) {
    return auditRepository.save(event).then();
}
~~~

**then()** bỏ giá trị của publisher nguồn và chỉ giữ tín hiệu hoàn tất hoặc lỗi. Khi dùng **Mono<Void>** cho request-response, client thường chỉ quan tâm request hoàn tất thành công hay thất bại, không mong nhận một DTO.

### 3.1. Xử lý empty response ở client

Client có thể chuyển empty completion thành một kết quả mặc định bằng **defaultIfEmpty**:

~~~java
Mono<String> orderIdResult = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .map(OrderView::id)
        .defaultIfEmpty("NOT_FOUND");
~~~

Hoặc dùng **switchIfEmpty** khi muốn chạy một publisher thay thế:

~~~java
Mono<OrderView> order = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .switchIfEmpty(Mono.defer(() -> {
            log.info("Order ORD-1042 was not found");
            return Mono.empty();
        }));
~~~

**defaultIfEmpty** phát ra giá trị thay thế. **switchIfEmpty** đăng ký publisher thay thế nếu nguồn hoàn tất rỗng. Dùng **defer** khi việc tạo publisher thay thế có side effect hoặc cần trì hoãn cho đến lúc thực sự cần.

Nếu client muốn biến trường hợp rỗng thành lỗi ở tầng ứng dụng, có thể làm rõ điều đó:

~~~java
Mono<OrderView> requiredOrder = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .switchIfEmpty(Mono.error(
                new OrderNotFoundException("ORD-1042")
        ));
~~~

Trong ví dụ này, remote interaction đã hoàn tất rỗng; chính client chủ động diễn giải trạng thái đó thành **OrderNotFoundException**. Đây là quyết định của client, không có nghĩa server đã gửi một error response.

### 3.2. Khi nào nên dùng empty và khi nào nên trả DTO?

Empty completion gọn khi caller chỉ cần biết có hay không có kết quả. Tuy nhiên, nó không mang theo lý do hoặc dữ liệu bổ sung. Nếu client cần phân biệt nhiều kết quả nghiệp vụ, hãy trả một response có kiểu rõ ràng.

Ví dụ, một truy vấn có thể trả về **Found** hoặc **NotFound**:

~~~java
public sealed interface OrderLookupResult {
    record Found(OrderView order) implements OrderLookupResult {}
    record NotFound(String orderId) implements OrderLookupResult {}
}
~~~

Service chuyển kết quả repository thành một trong hai kiểu:

~~~java
public Mono<OrderLookupResult> lookup(String orderId) {
    return orderRepository.findById(orderId)
            .map(this::toView)
            .map(order -> (OrderLookupResult)
                    new OrderLookupResult.Found(order))
            .defaultIfEmpty(new OrderLookupResult.NotFound(orderId));
}
~~~

Trong thiết kế này, cả hai kết quả đều là response thành công có dữ liệu. Client có thể hiển thị trạng thái “không tìm thấy” mà không phải đi qua nhánh xử lý exception. Cách này hữu ích khi “không tìm thấy” là một kết quả nghiệp vụ được dự kiến trước.

| Cách biểu diễn | Nên dùng khi |
|---|---|
| **Mono.empty()** | Không có kết quả là bình thường và caller không cần thêm thông tin |
| DTO **Found** / **NotFound** | Caller cần phân biệt nhiều kết quả nghiệp vụ hoặc cần dữ liệu mô tả kết quả |
| **Mono.error(...)** | Request không thể hoàn tất do lỗi xác thực, dữ liệu đầu vào, trạng thái hệ thống hoặc điều kiện bất thường theo hợp đồng API |

Không có quy tắc rằng mọi trường hợp “not found” đều phải là empty hoặc đều phải là error. Hãy chọn theo hợp đồng API và áp dụng nhất quán cho mọi client.

## 4. Thất bại: error signal và lỗi của RSocket

Khi thao tác không thể hoàn tất, publisher phát **onError**. Tạo lỗi trong Reactor bằng **Mono.error**:

~~~java
public Mono<OrderView> findRequired(String orderId) {
    return orderRepository.findById(orderId)
            .map(this::toView)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(orderId)
            ));
}
~~~

Ở đây, service chọn hợp đồng rằng không tìm thấy đơn hàng là lỗi. Khi handler trả Mono lỗi, RSocket runtime chuyển lỗi thành kết quả thất bại của interaction. Client quan sát một error signal trong Mono nhận được.

Không nên dựa vào giả định rằng object exception tùy chỉnh ở server sẽ được tái tạo nguyên vẹn ở client. Qua ranh giới mạng, runtime có thể chỉ truyền mã lỗi và thông tin mô tả. Nếu client cần một cấu trúc lỗi ổn định, hãy định nghĩa error contract rõ ràng hoặc dùng response DTO cho các kết quả nghiệp vụ dự kiến.

### 4.1. Phân loại lỗi

Một API request-response nên phân biệt các nhóm lỗi:

| Nhóm | Ví dụ | Hành vi client thường phù hợp |
|---|---|---|
| Validation | Thiếu order ID, định dạng sai | Hiển thị lỗi đầu vào; không retry |
| Authentication | Token không hợp lệ hoặc hết hạn | Yêu cầu đăng nhập lại hoặc làm mới credential |
| Authorization | Người dùng không có quyền xem đơn | Hiển thị từ chối truy cập; không retry tự động |
| Domain conflict | Đơn đã bị hủy hoặc trạng thái không cho phép thao tác | Hiển thị xung đột hoặc yêu cầu bước nghiệp vụ khác |
| Not found | Bản ghi không tồn tại | Empty, response DTO hoặc lỗi theo hợp đồng |
| Transient infrastructure | Database tạm thời không khả dụng | Có thể retry có giới hạn nếu thao tác an toàn |
| Timeout | Không có phản hồi trong thời hạn | Có thể thử lại nếu request idempotent và còn deadline |

Các lỗi dự kiến trong nghiệp vụ thường dễ xử lý hơn khi biểu diễn thành response DTO. Error signal nên dành cho trường hợp request không thể hoàn tất theo hợp đồng hoặc cần đi vào nhánh xử lý lỗi của caller.

### 4.2. Chuyển đổi và phục hồi lỗi trong Reactor

**onErrorMap** chuyển một lỗi thành lỗi khác mà vẫn giữ trạng thái thất bại:

~~~java
public Mono<OrderView> find(String orderId) {
    return orderRepository.findById(orderId)
            .map(this::toView)
            .onErrorMap(
                    DataAccessException.class,
                    ex -> new OrderServiceException(
                            "Unable to read order", ex
                    )
            );
}
~~~

**onErrorResume** thay publisher lỗi bằng một publisher khác:

~~~java
public Mono<PriceQuote> quote(String productId) {
    return quoteClient.fetch(productId)
            .onErrorResume(
                    QuoteProviderUnavailableException.class,
                    ex -> cachedQuote(productId)
            );
}
~~~

Fallback chỉ nên áp dụng cho nhóm lỗi đã xác định và khi dữ liệu thay thế có thể chấp nhận được. Không dùng fallback để che lỗi xác thực, lỗi phân quyền hoặc lỗi dữ liệu có thể làm sai kết quả.

**onErrorReturn** thay lỗi bằng một giá trị cố định. Nó phù hợp với trường hợp fallback thật sự có ý nghĩa, nhưng dễ làm mất thông tin nguyên nhân nếu áp dụng quá rộng:

~~~java
Mono<Integer> stock = inventoryClient.available("SKU-100")
        .onErrorReturn(0);
~~~

Ví dụ trên chỉ đúng nếu nghiệp vụ chấp nhận coi lỗi hệ thống như số lượng bằng không. Trong nhiều hệ thống tồn kho, cách đó có thể gây hiểu nhầm giữa “hết hàng” và “không thể kiểm tra tồn kho”.

**onErrorComplete** biến lỗi thành completion rỗng. Chỉ dùng khi hợp đồng cho phép bỏ qua lỗi và caller không cần biết thao tác đã thất bại:

~~~java
Mono<Void> optionalAudit = auditClient.write(event)
        .onErrorComplete(AuditUnavailableException.class);
~~~

Nếu ghi audit là yêu cầu bắt buộc, không được nuốt lỗi theo cách này.

### 4.3. Tránh xử lý lỗi quá rộng

Đoạn code sau có thể che giấu mọi lỗi:

~~~java
// Không nên dùng như chính sách mặc định.
return orderService.findById(orderId)
        .onErrorResume(ex -> Mono.empty());
~~~

Sau khi chuyển mọi lỗi thành empty, client không thể phân biệt “không có đơn hàng” với “database đang lỗi”, “request bị từ chối” hoặc “lỗi lập trình”. Hãy lọc đúng loại lỗi:

~~~java
return orderService.findById(orderId)
        .onErrorResume(
                OptionalAuditException.class,
                ex -> Mono.empty()
        );
~~~

Ngay cả khi lọc đúng kiểu exception, cần kiểm tra rằng empty completion là kết quả hợp lệ theo hợp đồng của thao tác.

## 5. Xử lý kết quả ở phía client

Client nên gom logic xử lý dữ liệu, completion rỗng và lỗi vào cùng một pipeline để không bỏ sót nhánh kết thúc:

~~~java
Mono<OrderView> lookup = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class);

Mono<OrderScreenState> screenState = lookup
        .<OrderScreenState>map(OrderScreenState.Loaded::new)
        .defaultIfEmpty(new OrderScreenState.Missing("ORD-1042"))
        .onErrorResume(
                TimeoutException.class,
                ex -> Mono.just(
                        new OrderScreenState.TemporarilyUnavailable()
                )
        );
~~~

**map** xử lý response có dữ liệu. **defaultIfEmpty** xử lý completion rỗng. **onErrorResume** xử lý timeout đã chọn. Những lỗi khác vẫn được truyền tiếp, giúp caller hoặc tầng cao hơn quyết định cách xử lý.

Ví dụ này giả định ứng dụng có kiểu trạng thái giao diện:

~~~java
public sealed interface OrderScreenState {
    record Loaded(OrderView order) implements OrderScreenState {}
    record Missing(String orderId) implements OrderScreenState {}
    record TemporarilyUnavailable() implements OrderScreenState {}
}
~~~

### 5.1. Timeout và cancellation

Client có thể đặt timeout cho request:

~~~java
Mono<OrderView> response = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu hết thời gian mà chưa có kết quả, **timeout** phát lỗi **TimeoutException** và hủy subscription nguồn. RSocket có thể truyền cancellation đến responder nếu interaction vẫn còn hoạt động. Tuy nhiên, cancellation không đảm bảo một side effect đã bắt đầu ở server được rollback. Với lệnh ghi dữ liệu, service vẫn cần transaction, idempotency và quy tắc xử lý trạng thái nhất quán.

### 5.2. Retry có điều kiện

Không retry mọi lỗi. Validation, authentication và authorization thường không thể được sửa bằng cách gửi lại cùng request. Với lỗi tạm thời, có thể retry có giới hạn:

~~~java
Mono<OrderView> response = requester.route("orders.find")
        .data(new OrderQuery("ORD-1042"))
        .retrieveMono(OrderView.class)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                        .filter(this::isTransientFailure)
        );
~~~

**isTransientFailure** phải phân loại lỗi theo hợp đồng của ứng dụng. Backoff giảm áp lực lên dịch vụ đang gặp sự cố. Nếu request có side effect, chỉ retry khi thao tác idempotent hoặc có idempotency key được server thực thi đúng cách.

## 6. Thiết kế response contract rõ ràng

Một response contract tốt giúp client hiểu chính xác kết quả mà không phải đoán từ việc Mono có phát giá trị hay không.

### 6.1. Response envelope cho nhiều kết quả nghiệp vụ

Khi cần trả nhiều trạng thái nghiệp vụ, có thể dùng một envelope:

~~~java
public record ApiResult<T>(
        String status,
        T data,
        String code,
        String message) {

    public static <T> ApiResult<T> success(T data) {
        return new ApiResult<>("SUCCESS", data, null, null);
    }

    public static <T> ApiResult<T> failure(
            String code, String message) {
        return new ApiResult<>("FAILURE", null, code, message);
    }
}
~~~

Ví dụ handler trả kết quả:

~~~java
public Mono<ApiResult<OrderView>> find(String orderId) {
    return orderRepository.findById(orderId)
            .map(this::toView)
            .map(ApiResult::success)
            .defaultIfEmpty(ApiResult.failure(
                    "ORDER_NOT_FOUND",
                    "Không tìm thấy đơn hàng"
            ));
}
~~~

Envelope là một response có dữ liệu trong cả hai trường hợp. Dùng cách này khi caller cần một schema thống nhất và nhiều mã kết quả nghiệp vụ. Không nên trả **status=FAILURE** trong payload cho mọi lỗi hệ thống; lỗi hạ tầng và lỗi protocol vẫn cần được thể hiện bằng error signal để hệ thống có thể quan sát và xử lý đúng.

### 6.2. Giữ error contract ổn định

Nếu dùng error signal cho các trường hợp như validation hoặc authorization, hãy chuẩn hóa:

- Mã lỗi ổn định, không phụ thuộc nội dung exception nội bộ.
- Thông điệp dành cho client, không chứa stack trace hoặc dữ liệu nhạy cảm.
- Quy tắc ánh xạ lỗi nội bộ sang lỗi giao thức.
- Chính sách log và trace ID để đội vận hành tìm nguyên nhân.
- Quy tắc retry cho từng nhóm lỗi.

RSocket có các mã lỗi ở cấp protocol, nhưng chi tiết ánh xạ exception phụ thuộc runtime và framework. Client nên dựa trên error contract mà ứng dụng công bố thay vì phụ thuộc vào tên class exception riêng của server.

## 7. Kiểm thử ba trạng thái với StepVerifier

**StepVerifier** của Reactor Test cho phép xác nhận thứ tự tín hiệu mà không cần gọi **block()**:

~~~java
@Test
void emitsOrderWhenFound() {
    OrderView order = new OrderView(
            "ORD-1042", "PAID", new BigDecimal("125.00")
    );

    StepVerifier.create(orderService.findById("ORD-1042"))
            .expectNext(order)
            .verifyComplete();
}
~~~

Kiểm thử completion rỗng:

~~~java
@Test
void completesEmptyWhenOrderDoesNotExist() {
    StepVerifier.create(orderService.findById("MISSING"))
            .verifyComplete();
}
~~~

**verifyComplete()** xác nhận publisher hoàn tất bình thường và không phát giá trị ngoài những tín hiệu đã khai báo. Nếu service phải chuyển not found thành lỗi, kiểm thử rõ error type:

~~~java
@Test
void reportsNotFoundWhenRequiredOrderIsMissing() {
    StepVerifier.create(orderService.findRequired("MISSING"))
            .expectError(OrderNotFoundException.class)
            .verify();
}
~~~

Kiểm thử fallback:

~~~java
@Test
void usesCachedQuoteWhenProviderIsUnavailable() {
    StepVerifier.create(quoteService.quote("SKU-100"))
            .expectNextMatches(quote -> quote.source().equals("CACHE"))
            .verifyComplete();
}
~~~

Ngoài kiểm thử service, integration test RSocket nên kiểm tra cả đường đi qua requester và responder: response được decode đúng kiểu, empty completion không bị biến thành lỗi ngoài ý muốn, và error từ server được client quan sát như một error signal. Điều này đặc biệt quan trọng khi thay đổi codec, phiên bản RSocket hoặc cấu hình Spring.

## 8. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Dùng **Mono.just(null)** | Phát sinh lỗi vì Reactive Streams không chấp nhận null | Dùng **Mono.empty()** hoặc một DTO hợp lệ |
| Coi empty completion là lỗi | Client tạo exception không cần thiết | Xác định empty có phải kết quả nghiệp vụ bình thường không |
| Coi mọi lỗi là empty | Che giấu lỗi hạ tầng và lỗi bảo mật | Chỉ phục hồi nhóm lỗi đã xác định |
| Dùng error cho mọi trường hợp not found | Caller phải xử lý exception cho một kết quả dự kiến | Cân nhắc empty hoặc response DTO |
| Dùng empty khi cần nhiều trạng thái nghiệp vụ | Mất lý do hoặc thông tin mô tả | Trả response có kiểu **Found**/**NotFound** |
| Retry lệnh ghi không có idempotency | Có thể tạo side effect trùng lặp | Dùng idempotency key và giới hạn retry |
| Chỉ log **doOnNext** | Bỏ sót empty và error | Theo dõi completion và lỗi bằng hook phù hợp |
| Cho rằng timeout đồng nghĩa server rollback | Side effect có thể vẫn hoàn tất ở server | Thiết kế cancellation, transaction và idempotency |

## 9. Quy trình chọn cách biểu diễn response

Khi thiết kế một route request-response, hãy lần lượt xác định:

1. **Có một giá trị domain cần trả về không?** Nếu có, trả **Mono<T>** phát một giá trị.
2. **Không có giá trị có phải kết quả bình thường không?** Nếu có và caller không cần thêm thông tin, dùng **Mono.empty()**.
3. **Caller cần phân biệt nhiều kết quả nghiệp vụ?** Trả response DTO hoặc sealed result type.
4. **Request không thể hoàn tất do lỗi?** Phát error signal với error contract rõ ràng.
5. **Client cần fallback hoặc retry?** Chỉ áp dụng cho nhóm lỗi và điều kiện đã xác định.
6. **Request có side effect?** Định nghĩa idempotency và cancellation trước khi bật retry.

Quy trình này giúp server và client có cùng cách hiểu về thành công, không có kết quả và thất bại.

## 10. Tổng kết

Trong Spring RSocket, request-response thường được biểu diễn bằng **Mono<T>** với ba trạng thái: phát một giá trị rồi hoàn tất, hoàn tất rỗng, hoặc kết thúc bằng lỗi. Giá trị phù hợp khi có kết quả cần trả về; empty phù hợp khi không có giá trị và đó là kết quả được chấp nhận; error dành cho request không thể hoàn tất theo hợp đồng. Nếu caller cần phân biệt nhiều trạng thái nghiệp vụ, một response DTO có kiểu rõ ràng thường dễ dùng hơn việc biến mọi trường hợp thành exception. Client cần xử lý đủ ba nhánh, đặt timeout hợp lý, retry có điều kiện và kiểm thử tín hiệu bằng StepVerifier.
