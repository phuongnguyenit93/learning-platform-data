# @MessageExceptionHandler và ánh xạ lỗi của bộ xử lý RSocket

## Mục tiêu

Sau bài này, bạn có thể xử lý lỗi phát sinh trong các phương thức `@MessageMapping` của RSocket, ánh xạ ngoại lệ sang một cấu trúc lỗi ổn định, phân biệt lỗi nghiệp vụ trong response với lỗi giao thức RSocket, và chọn đúng phạm vi xử lý cục bộ hoặc toàn cục.

## 1. Lỗi phát sinh ở đâu trong một RSocket handler?

Trong Spring Messaging, `RSocketMessageHandler` tìm và gọi các phương thức `@MessageMapping` theo route. Một handler có thể:

- Ném exception trực tiếp khi kiểm tra input hoặc thực hiện logic đồng bộ.
- Trả về `Mono` hoặc `Flux` và phát tín hiệu lỗi trong reactive pipeline.
- Hoàn tất bình thường và trả payload theo interaction model đã chọn.

Nếu không xử lý lỗi phù hợp, exception có thể trở thành lỗi của request ở tầng RSocket. Phía requester nhận tín hiệu lỗi qua reactive publisher. Điều này khác với việc handler chủ động chuyển lỗi nghiệp vụ thành một response DTO.

`@MessageExceptionHandler` là annotation đi kèm mô hình `@MessageMapping`. Nó đánh dấu phương thức xử lý exception phát sinh khi gọi message handler. Annotation thuộc package:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
~~~

Nó gắn với Spring Messaging, không phụ thuộc RSocket chạy qua TCP hay WebSocket. Với RSocket, các phương thức này được thực thi trong hạ tầng annotated responder do `RSocketMessageHandler` cung cấp.

## 2. Khai báo exception nào cần xử lý?

Có hai cách khai báo loại exception:

**Khai báo trực tiếp trên annotation**

~~~java
@MessageExceptionHandler(OrderNotFoundException.class)
public OrderResult handleNotFound(OrderNotFoundException exception) {
    return OrderResult.failure("ORDER_NOT_FOUND", "Không tìm thấy đơn hàng");
}
~~~

**Để Spring suy ra từ tham số exception**

~~~java
@MessageExceptionHandler
public OrderResult handleInvalidQuery(InvalidOrderQueryException exception) {
    return OrderResult.failure("INVALID_QUERY", "Dữ liệu truy vấn không hợp lệ");
}
~~~

Nếu thuộc tính của annotation để trống, các kiểu exception trong danh sách tham số sẽ được dùng làm kiểu cần xử lý. Có thể khai báo nhiều loại trong annotation:

~~~java
@MessageExceptionHandler({
        InvalidOrderQueryException.class,
        IllegalArgumentException.class
})
public OrderResult handleInvalidInput(Exception exception) {
    return OrderResult.failure("INVALID_INPUT", "Dữ liệu yêu cầu không hợp lệ");
}
~~~

Tham số exception cho phép đọc thông tin cần thiết để quyết định cách ánh xạ. Phương thức xử lý exception cũng hỗ trợ các kiểu tham số và giá trị trả về giống phương thức `@MessageMapping`, bao gồm các kiểu reactive phù hợp.

## 3. Phạm vi của exception handler

### Xử lý trong cùng controller

Theo mặc định, `@MessageExceptionHandler` áp dụng cho các phương thức message handler trong cùng lớp `@Controller` và hệ phân cấp lớp của nó. Đây là lựa chọn phù hợp khi lỗi chỉ có ý nghĩa trong một nhóm route.

~~~java
@Controller
public class OrderRSocketController {

    @MessageMapping("orders.find")
    public Mono<OrderResult> find(OrderQuery query) {
        // Logic tìm đơn hàng
        return Mono.empty();
    }

    @MessageExceptionHandler(OrderNotFoundException.class)
    public Mono<OrderResult> handleNotFound(OrderNotFoundException exception) {
        return Mono.just(
                OrderResult.failure(
                        "ORDER_NOT_FOUND",
                        "Không tìm thấy đơn hàng"
                )
        );
    }
}
~~~

### Xử lý dùng chung bằng @ControllerAdvice

Khi nhiều RSocket controller cần cùng một chính sách lỗi, có thể đặt `@MessageExceptionHandler` trong lớp có `@ControllerAdvice`.

~~~java
@ControllerAdvice
public class RSocketGlobalExceptionAdvice {

    @MessageExceptionHandler(InvalidOrderQueryException.class)
    public OrderResult handleInvalidQuery(InvalidOrderQueryException exception) {
        return OrderResult.failure(
                "INVALID_QUERY",
                "Dữ liệu truy vấn không hợp lệ"
        );
    }
}
~~~

Spring Boot tự cấu hình hạ tầng Spring Messaging cho RSocket và hỗ trợ `@ControllerAdvice` để xử lý exception. Hỗ trợ đăng ký messaging advice trong Spring Framework có từ phiên bản 5.3.5. Nếu tự tạo `RSocketMessageHandler` ngoài cấu hình tự động của Spring Boot, cần đăng ký advice phù hợp qua cơ chế `registerMessagingAdvice(...)`; `spring-messaging` không phụ thuộc trực tiếp vào `spring-web` để tự nhận mọi kiểu `@ControllerAdvice`.

## 4. Thiết kế hợp đồng lỗi cho ứng dụng

Không nên gửi nguyên exception hoặc stack trace cho client. Hãy chuyển lỗi nghiệp vụ sang một cấu trúc có các trường ổn định, ví dụ:

~~~java
public record ErrorInfo(
        String code,
        String message
) {
}
~~~

Với Request-Response, nên dùng cùng một kiểu response cho cả trường hợp thành công và thất bại. Nhờ vậy client chỉ cần giải mã một kiểu dữ liệu:

~~~java
public record OrderQuery(String orderId) {
}

public record OrderView(
        String orderId,
        String status
) {
}

public record OrderResult(
        OrderView data,
        ErrorInfo error
) {
    public static OrderResult success(OrderView data) {
        return new OrderResult(data, null);
    }

    public static OrderResult failure(String code, String message) {
        return new OrderResult(
                null,
                new ErrorInfo(code, message)
        );
    }
}
~~~

Quy ước của ví dụ:

- Thành công: `data` có giá trị, `error` là `null`.
- Thất bại nghiệp vụ đã được ánh xạ: `data` là `null`, `error` chứa mã và thông điệp ổn định.
- Lỗi giao thức hoặc lỗi ngoài chính sách ánh xạ: requester nhận tín hiệu lỗi thay vì một `OrderResult` bình thường.

Các mã như `ORDER_NOT_FOUND`, `INVALID_QUERY` và `INTERNAL_ERROR` là mã nghiệp vụ do ứng dụng định nghĩa, không phải HTTP status code. Giữ mã ổn định để client có thể xử lý mà không phụ thuộc câu chữ hiển thị.

## 5. Ví dụ đầy đủ: ánh xạ OrderNotFoundException

Giả sử service tìm đơn hàng trả về `Mono<OrderView>`. Khi không tìm thấy đơn hàng, service phát `Mono.empty()`. Handler chuyển trường hợp đó thành exception nghiệp vụ để một phương thức `@MessageExceptionHandler` xử lý.

### 5.1. Exception

~~~java
public final class OrderNotFoundException extends RuntimeException {

    private final String orderId;

    public OrderNotFoundException(String orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

### 5.2. Service contract

~~~java
import reactor.core.publisher.Mono;

public interface OrderService {
    Mono<OrderView> findById(String orderId);
}
~~~

### 5.3. RSocket controller

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.find")
    public Mono<OrderResult> find(OrderQuery query) {
        return orderService.findById(query.orderId())
                .map(OrderResult::success)
                .switchIfEmpty(Mono.error(
                        new OrderNotFoundException(query.orderId())
                ));
    }

    @MessageExceptionHandler(OrderNotFoundException.class)
    public Mono<OrderResult> handleNotFound(
            OrderNotFoundException exception) {

        return Mono.just(OrderResult.failure(
                "ORDER_NOT_FOUND",
                "Không tìm thấy đơn hàng"
        ));
    }
}
~~~

Giải thích:

1. `@MessageMapping("orders.find")` ánh xạ request có route `orders.find` tới phương thức `find`.
2. `findById(...)` trả publisher nên việc tìm kiếm diễn ra trong reactive pipeline.
3. `switchIfEmpty(Mono.error(...))` biến trường hợp không có đơn hàng thành tín hiệu lỗi. Nó không tự subscribe và không block.
4. Khi exception phù hợp được phát ra trong quá trình xử lý handler, Spring tìm phương thức `@MessageExceptionHandler` tương ứng.
5. Phương thức xử lý trả `OrderResult` thất bại. Với Request-Response, đây là response payload bình thường của request, không phải RSocket ERROR frame.

Trong ví dụ, `OrderQuery`, `OrderView`, `ErrorInfo`, `OrderResult`, `OrderService` và `OrderNotFoundException` là các kiểu riêng của ứng dụng. Đặt mỗi kiểu `public` trong file Java cùng tên khi tách thành project thực tế.

### 5.4. Client gọi route

~~~java
Mono<OrderResult> result = requester
        .route("orders.find")
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderResult.class);
~~~

Client đọc `OrderResult`:

- Nếu `result.data()` khác `null`, xử lý dữ liệu đơn hàng.
- Nếu `result.error()` khác `null`, xử lý mã lỗi nghiệp vụ.
- Nếu publisher phát `onError`, xử lý lỗi RSocket hoặc lỗi không được ánh xạ thành response.

Việc dùng một response envelope thống nhất giúp client không phải đoán response là `OrderView` hay `ErrorInfo` tùy theo kết quả của server.

## 6. Hai cách truyền lỗi tới requester

Cần phân biệt rõ hai hợp đồng sau.

| Cách xử lý | Điều requester nhận được | Cách client xử lý |
|---|---|---|
| `@MessageExceptionHandler` trả về DTO | Một response payload bình thường nếu interaction có response | Giải mã DTO và kiểm tra `error.code` |
| Exception tiếp tục được phát ra | Tín hiệu lỗi của request, được truyền qua RSocket | Xử lý bằng `onErrorResume`, `doOnError` hoặc cơ chế tương đương |

### Ánh xạ thành response DTO

Đây là lựa chọn phù hợp khi lỗi là một phần của hợp đồng nghiệp vụ. Ví dụ: đơn hàng không tồn tại, dữ liệu đầu vào không hợp lệ hoặc trạng thái nghiệp vụ không cho phép thao tác.

Ưu điểm là client nhận được cấu trúc có mã lỗi ổn định. Tuy nhiên, ở tầng giao thức, request đã có response bình thường. Client phải kiểm tra trường `error`; không thể chỉ dựa vào `onError` để phát hiện lỗi nghiệp vụ này.

### Giữ lỗi ở tầng giao thức

Nếu không có exception handler phù hợp, hoặc handler tiếp tục trả về một publisher lỗi, request vẫn thất bại và requester nhận tín hiệu lỗi.

~~~java
Mono<OrderResult> result = requester
        .route("orders.find")
        .data(new OrderQuery("ORD-42"))
        .retrieveMono(OrderResult.class)
        .doOnError(error ->
                log.warn("RSocket request failed", error)
        );
~~~

Đây là cách phù hợp cho lỗi khiến request không thể hoàn tất, chẳng hạn lỗi xử lý ngoài dự kiến hoặc lỗi cần được quản lý theo chính sách retry/timeout của client. Không giả định rằng class exception Java ở server sẽ được truyền nguyên vẹn sang JVM client; hãy dựa vào hợp đồng lỗi giao thức và thông tin ổn định mà ứng dụng chủ động gửi.

## 7. Lỗi trong reactive pipeline

Với handler trả `Mono` hoặc `Flux`, exception có thể xuất hiện sau khi phương thức đã trả publisher. Hãy giữ lỗi trong cùng reactive chain:

~~~java
@MessageMapping("orders.create")
public Mono<OrderResult> create(CreateOrder command) {
    return orderService.create(command)
            .map(OrderResult::success)
            .onErrorMap(
                    DuplicateOrderException.class,
                    ex -> new OrderConflictException(command.orderId())
            );
}
~~~

Exception được chuyển đổi trong pipeline có thể được ánh xạ bởi `@MessageExceptionHandler` nếu loại exception cuối cùng khớp với handler đã khai báo.

Không tự gọi `subscribe()` bên trong `@MessageMapping` chỉ để kích hoạt công việc:

~~~java
@MessageMapping("orders.create")
public void create(CreateOrder command) {
    orderService.create(command).subscribe();
}
~~~

Cách viết trên tách công việc khỏi lifecycle của request. Framework không còn nhận được publisher đại diện cho quá trình xử lý để quản lý completion và error theo request đó. Hãy trả về `Mono` hoặc `Flux` từ handler.

Cũng không nên âm thầm thay lỗi bằng `Mono.empty()` nếu client cần biết thao tác thất bại. Khi dùng `onErrorResume`, hãy chuyển sang response envelope có chủ đích hoặc phát tiếp lỗi theo đúng hợp đồng đã chọn.

## 8. Lựa chọn theo interaction model

`@MessageExceptionHandler` không thay đổi bản chất interaction của request.

| Interaction | Lưu ý khi thiết kế lỗi |
|---|---|
| Request-Response | Có thể trả một error envelope làm response payload để client kiểm tra |
| Request-Stream | Lỗi có thể kết thúc stream; nếu cần biểu diễn lỗi như một phần dữ liệu, phải thiết kế rõ kiểu phần tử và cách kết thúc stream |
| Channel | Cần xác định lỗi thuộc toàn bộ interaction hay chỉ là lỗi của một phần tử trong luồng; giữ quy ước giữa hai phía |
| Fire-and-Forget | Không có response payload để requester đọc error DTO; cần log, metric, sự kiện hoặc một route xác nhận riêng |

Đặc biệt, không dùng giá trị trả về của exception handler như ACK cho Fire-and-Forget. Nếu bên gửi cần biết server đã xử lý nghiệp vụ thành công hay thất bại, hãy chọn Request-Response hoặc thiết kế một cơ chế xác nhận riêng có correlation ID.

## 9. Phân loại lỗi và chính sách ánh xạ

Một chính sách thực tế có thể phân loại như sau:

| Nhóm lỗi | Mã ứng dụng gợi ý | Hành vi |
|---|---|---|
| Input sai định dạng hoặc thiếu dữ liệu | `INVALID_REQUEST` | Trả error envelope có thông điệp có thể hiển thị |
| Không tìm thấy tài nguyên | `NOT_FOUND` | Trả error envelope với định danh lỗi ổn định |
| Vi phạm quy tắc nghiệp vụ | `BUSINESS_RULE_VIOLATION` | Trả lỗi nghiệp vụ đã được kiểm soát |
| Không đủ quyền | `FORBIDDEN` | Không tiết lộ thông tin tài nguyên nhạy cảm |
| Lỗi ngoài dự kiến | `INTERNAL_ERROR` | Ghi log chi tiết ở server, trả thông điệp chung hoặc để lỗi được truyền theo chính sách giao thức |
| Mất kết nối, timeout ở requester | Không phải mã exception handler nghiệp vụ | Xử lý ở client/transport layer |

Không trả `exception.getMessage()` cho mọi loại lỗi một cách mặc định. Message của exception có thể chứa SQL, tên bảng, đường dẫn nội bộ, token hoặc chi tiết hạ tầng. Hãy ghi log đầy đủ ở server, tạo correlation ID nếu cần truy vết và chỉ gửi thông tin đã được phép công khai.

## 10. Các lỗi triển khai thường gặp

**Dùng nhầm `@ExceptionHandler` của Spring MVC/WebFlux**

`@ExceptionHandler` xử lý exception trong luồng HTTP controller. Với phương thức Spring Messaging được đánh dấu `@MessageMapping`, hãy dùng `@MessageExceptionHandler`.

**Đặt handler toàn cục nhưng thiếu hạ tầng đăng ký**

Một lớp có `@ControllerAdvice` chỉ hữu ích khi RSocket message handler nhận được messaging advice đó. Spring Boot auto-configuration hỗ trợ cấu hình này; nếu tự cấu hình `RSocketMessageHandler`, hãy kiểm tra việc đăng ký advice.

**Chỉ bắt exception đồng bộ**

Handler có thể trả `Mono` hoặc `Flux`. Lỗi phát ra sau đó vẫn cần nằm trong publisher được trả về để framework xử lý. Không tách công việc bằng `subscribe()` rồi kỳ vọng exception handler của request bắt được lỗi ở subscription độc lập.

**Trả hai kiểu DTO không thống nhất**

Nếu success trả `OrderView` còn lỗi trả `ErrorInfo`, client dùng một kiểu giải mã cố định sẽ khó xử lý. Hãy dùng envelope chung hoặc giữ lỗi ở tầng giao thức.

**Coi error envelope là lỗi giao thức**

Khi exception handler trả về DTO, requester nhận response bình thường. Nếu client chỉ gắn `onErrorResume` mà không kiểm tra trường `error`, lỗi nghiệp vụ đã ánh xạ sẽ bị bỏ sót.

**Kỳ vọng exception handler xử lý mọi lỗi kết nối**

Annotation này phục vụ exception của message handler. Nó không thay thế việc xử lý lỗi kết nối, timeout, hủy request hoặc lỗi transport ở phía requester.

## 11. Kiểm thử

Nên kiểm tra ít nhất ba trường hợp bằng integration test có RSocket requester/responder thực tế và Reactor Test (`StepVerifier`):

1. Route xử lý thành công: requester nhận envelope có `data` và không có `error`.
2. Route ném `OrderNotFoundException`: exception handler chạy và requester nhận envelope có mã `ORDER_NOT_FOUND`.
3. Route phát một exception không có handler: requester nhận tín hiệu lỗi, không nhận envelope thành công giả.

Với Request-Stream hoặc Fire-and-Forget, bổ sung test riêng cho interaction tương ứng. Đừng suy ra hành vi của một interaction từ test Request-Response.

Ví dụ kiểm tra response envelope:

~~~java
StepVerifier.create(
        requester.route("orders.find")
                .data(new OrderQuery("missing"))
                .retrieveMono(OrderResult.class)
)
.expectNextMatches(result ->
        result.data() == null
                && result.error() != null
                && "ORDER_NOT_FOUND".equals(result.error().code())
)
.verifyComplete();
~~~

Test này chứng minh client nhận một response payload chứa lỗi nghiệp vụ và publisher hoàn tất bình thường. Nó không chứng minh rằng một request lỗi giao thức cũng sẽ hoàn tất bình thường.

## 12. Checklist

- [ ] Dùng `@MessageExceptionHandler` cho exception của `@MessageMapping`.
- [ ] Khai báo rõ loại exception trong annotation hoặc tham số method.
- [ ] Chọn phạm vi cục bộ hay toàn cục bằng `@ControllerAdvice`.
- [ ] Xác nhận RSocketMessageHandler đã nhận global advice.
- [ ] Dùng error code ổn định và thông điệp không tiết lộ chi tiết nội bộ.
- [ ] Giữ lỗi trong reactive pipeline và trả publisher về framework.
- [ ] Phân biệt error envelope với RSocket error signal.
- [ ] Thiết kế theo interaction model; không dùng Fire-and-Forget để đợi ACK.
- [ ] Kiểm thử cả lỗi đã ánh xạ và lỗi không được xử lý.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): `RSocketMessageHandler`, annotated responders, `@MessageMapping`, interaction model và kiểu trả về.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): Spring Messaging auto-configuration và hỗ trợ `@ControllerAdvice`.
- [Spring Framework Javadoc — MessageExceptionHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html): thuộc tính `value` và hợp đồng annotation.
- [Spring Framework Javadoc — MessageMappingMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/reactive/MessageMappingMessageHandler.html): đăng ký messaging advice toàn cục.
