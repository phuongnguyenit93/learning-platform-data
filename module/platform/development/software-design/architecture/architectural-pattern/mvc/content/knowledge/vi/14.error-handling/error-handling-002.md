# Biểu diễn kết quả thất bại bằng kiểu trả về hoặc ngoại lệ

Trong ứng dụng MVC, một thao tác có thể thành công hoặc thất bại vì nhiều lý do: dữ liệu biểu mẫu không hợp lệ, tài nguyên không tồn tại, người dùng không đủ quyền, trạng thái hiện tại không cho phép thao tác, hoặc hệ thống lưu trữ gặp sự cố. Cách biểu diễn thất bại ảnh hưởng trực tiếp đến cách Controller phản hồi, cách Service điều phối nghiệp vụ, cách transaction kết thúc và cách người dùng hiểu điều gì đã xảy ra.

Hai cách thường dùng là trả về một kiểu dữ liệu biểu diễn cả thành công lẫn thất bại (Result/Either) hoặc ném ngoại lệ (exception). Không có một cách duy nhất phù hợp với mọi tình huống. Hãy chọn dựa trên ý nghĩa của thất bại, khả năng người gọi xử lý nó và ranh giới giữa nghiệp vụ với lỗi kỹ thuật.

## 1. Thất bại là một phần của hợp đồng xử lý

Một phương thức thường được viết như thể nó luôn trả về dữ liệu:

~~~java
OrderReceipt submitOrder(SubmitOrderCommand command);
~~~

Nhưng thực tế thao tác có thể không tạo được biên nhận. Đơn hàng có thể không tồn tại, đã bị hủy, thiếu hàng hoặc người dùng không được phép gửi. Nếu hợp đồng chỉ mô tả kiểu thành công, người gọi phải tìm hiểu thêm bằng cách đọc tài liệu, bắt ngoại lệ hoặc kiểm tra giá trị đặc biệt.

Một hợp đồng rõ ràng cần trả lời:

- Những điều kiện nào có thể khiến thao tác thất bại?
- Người gọi có thể dự đoán và xử lý từng loại thất bại không?
- Thất bại có phải kết quả bình thường của nghiệp vụ không?
- Có cần hủy transaction hay hoàn tác thay đổi không?
- Thất bại cần được ánh xạ thành mã HTTP hoặc thông báo nào?
- Chi tiết nào được phép hiển thị cho người dùng?

Ví dụ, “không đủ hàng” là một kết quả nghiệp vụ có thể dự đoán khi gửi đơn. “Không kết nối được cơ sở dữ liệu” là lỗi hạ tầng khiến ứng dụng không thể hoàn tất thao tác. Cả hai đều làm thao tác thất bại, nhưng cách xử lý và thông báo không giống nhau.

## 2. Hai cách biểu diễn chính

### 2.1. Kiểu trả về biểu diễn thành công hoặc thất bại

Một kiểu kết quả (Result, Either hoặc Outcome) chứa một trong hai nhánh:

- Nhánh thành công chứa dữ liệu cần trả về.
- Nhánh thất bại chứa mã lỗi hoặc thông tin lỗi có cấu trúc.

Ví dụ về hợp đồng:

~~~text
Result<OrderReceipt, OrderError>
    = Success(OrderReceipt)
    | Failure(OrderError)
~~~

Người gọi phải xử lý cả hai nhánh trước khi tiếp tục. Thất bại được thể hiện ngay trong kiểu trả về, nên có thể đọc chữ ký phương thức để biết thao tác có thể bị từ chối vì những lý do nào.

### 2.2. Ngoại lệ

Ngoại lệ biểu diễn một tình huống khiến luồng thực thi thông thường không thể tiếp tục theo cách hiện tại. Phương thức ném ngoại lệ; luồng gọi gần nhất có khối catch phù hợp sẽ xử lý, hoặc ngoại lệ đi lên ranh giới framework.

Ví dụ:

~~~java
Order order = repository.findById(orderId)
    .orElseThrow(() -> new OrderNotFoundException(orderId));
~~~

Nếu đơn hàng không tồn tại, phương thức không trả về một Order rỗng. Nó ném ngoại lệ để báo rằng luồng xử lý hiện tại không thể tiếp tục theo cách đã yêu cầu.

### 2.3. So sánh

| Tiêu chí | Kiểu Result | Exception |
|---|---|---|
| Vị trí biểu diễn lỗi | Trong giá trị trả về | Trong luồng điều khiển |
| Khả năng nhìn thấy từ chữ ký | Rõ nếu kiểu lỗi được khai báo | Runtime exception thường không hiện trong chữ ký |
| Cách xử lý | Người gọi kiểm tra hoặc fold/map các nhánh | Catch tại nơi có thể xử lý hoặc để lan tới boundary |
| Phù hợp | Từ chối nghiệp vụ dự kiến, validation, kết quả có nhiều nhánh | Lỗi bất thường, lỗi hạ tầng, vi phạm invariant hoặc không thể tiếp tục |
| Nguy cơ | Quên kiểm tra nhánh thất bại, lồng nhiều Result | Bắt quá rộng, dùng exception làm luồng điều khiển thường xuyên |
| Tích hợp MVC | Controller ánh xạ Result sang response | Exception handler ánh xạ ngoại lệ sang response |

Result làm cho thất bại trở thành một phần tường minh của hợp đồng. Exception giúp tách luồng thành công khỏi luồng lỗi và cho phép framework xử lý tập trung. Cả hai đều cần quy ước rõ ràng.

## 3. Phân loại thất bại trước khi chọn cách biểu diễn

Không nên quyết định dùng Result hay Exception chỉ dựa vào tên lỗi. Hãy xem lỗi có phải một kết quả dự kiến của thao tác hay không và ai có thể xử lý nó.

### 3.1. Lỗi đầu vào (input validation)

Ví dụ:

- Trường bắt buộc bị bỏ trống.
- Email sai định dạng.
- Số lượng nhỏ hơn hoặc bằng 0.
- Ngày kết thúc đứng trước ngày bắt đầu.

Đây là các lỗi thường có thể dự đoán trước khi chạy nghiệp vụ. Với biểu mẫu MVC, framework thường cung cấp cơ chế validation và BindingResult để trả lại form cùng thông báo theo từng trường. Với API, có thể trả cấu trúc lỗi validation có mã và danh sách trường không hợp lệ.

### 3.2. Từ chối theo quy tắc nghiệp vụ

Ví dụ:

- Đơn hàng không thể gửi vì đang ở trạng thái đã hủy.
- Không đủ tồn kho để giữ số lượng yêu cầu.
- Người dùng không thể đặt thêm chỗ vì đã đạt giới hạn.
- Yêu cầu nghỉ phép không thể duyệt vì đã được xử lý.

Những kết quả này thường là một phần bình thường của nghiệp vụ. Result với kiểu lỗi cụ thể có thể làm hợp đồng dễ hiểu và giúp Controller chọn phản hồi tương ứng. Một số dự án dùng domain exception cho các trường hợp này; điều đó vẫn có thể phù hợp nếu quy ước nhất quán và exception được xử lý tại boundary.

### 3.3. Không tìm thấy hoặc không có quyền

Không tìm thấy tài nguyên có thể là kết quả dự kiến của truy vấn, hoặc là lỗi khiến một ca sử dụng không thể tiếp tục. Việc dùng Result hay Exception phụ thuộc vào hợp đồng của Service.

Không có quyền thường cần được xử lý ở ranh giới bảo mật. Có thể trả một kiểu lỗi truy cập trong Result hoặc ném AccessDeniedException để cơ chế bảo mật/ControllerAdvice ánh xạ. Không được bỏ qua kiểm tra quyền chỉ vì giao diện đã ẩn nút thao tác.

### 3.4. Lỗi kỹ thuật hoặc lỗi hệ thống

Ví dụ:

- Cơ sở dữ liệu mất kết nối.
- Timeout khi gọi dịch vụ bên ngoài.
- Không thể đọc tệp do lỗi thiết bị.
- Cấu hình bắt buộc bị thiếu.
- Lỗi lập trình như NullPointerException.

Những lỗi này thường không phải kết quả nghiệp vụ mà người dùng có thể giải quyết bằng cách sửa một trường biểu mẫu. Chúng thường được biểu diễn bằng exception, giữ nguyên nguyên nhân (cause), được log ở boundary và ánh xạ thành phản hồi lỗi chung phù hợp.

### 3.5. Bảng định hướng

| Tình huống | Cách biểu diễn thường phù hợp | Hành động của ứng dụng |
|---|---|---|
| Form thiếu trường bắt buộc | Validation result/BindingResult | Hiển thị lỗi cạnh trường |
| Đơn hàng thiếu hàng | Result hoặc domain exception theo quy ước | Thông báo không đủ hàng |
| Đơn hàng không tồn tại | Result hoặc NotFoundException | Trả 404 hoặc trang không tìm thấy |
| Phiên bản dữ liệu đã cũ | Conflict result hoặc exception chuyên biệt | Trả 409/412, yêu cầu tải lại |
| Người dùng không có quyền | Security exception hoặc typed error | Trả 403 hoặc 404 theo chính sách |
| Cơ sở dữ liệu mất kết nối | Exception | Log, trả 5xx và thông báo chung |
| Lỗi lập trình ngoài dự kiến | Exception | Ghi nhận lỗi, trả 500 |

Bảng chỉ là định hướng. Điều quan trọng là cùng một loại thất bại cần có cách biểu diễn và ánh xạ nhất quán trong toàn ứng dụng.

## 4. Thiết kế kiểu Result có kiểu lỗi rõ ràng

Một Result hữu ích khi nó mô tả được các nhánh hợp lệ của một thao tác. Không nên chỉ trả boolean vì người gọi sẽ không biết tại sao thao tác thất bại.

### 4.1. Ví dụ kiểu Result trong Java

Java không có kiểu Result tổng quát trong thư viện chuẩn. Có thể định nghĩa bằng sealed interface và record (Java 17 trở lên):

~~~java
import java.util.function.Function;

public sealed interface Result<T, E>
        permits Result.Success, Result.Failure {

    <R> R fold(
        Function<? super T, ? extends R> onSuccess,
        Function<? super E, ? extends R> onFailure
    );

    static <T, E> Result<T, E> success(T value) {
        return new Success<>(value);
    }

    static <T, E> Result<T, E> failure(E error) {
        return new Failure<>(error);
    }

    record Success<T, E>(T value) implements Result<T, E> {
        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super E, ? extends R> onFailure) {
            return onSuccess.apply(value);
        }
    }

    record Failure<T, E>(E error) implements Result<T, E> {
        @Override
        public <R> R fold(
                Function<? super T, ? extends R> onSuccess,
                Function<? super E, ? extends R> onFailure) {
            return onFailure.apply(error);
        }
    }
}
~~~

Đây là một cách triển khai minh họa. Trong dự án thực tế, nên đặt các kiểu này ở package dùng chung phù hợp hoặc dùng thư viện Result đã được dự án lựa chọn. Không cần tự xây một framework functional phức tạp nếu ứng dụng chỉ có vài trường hợp.

### 4.2. Khai báo kiểu lỗi của nghiệp vụ

Nếu lỗi cần mang dữ liệu như mã tài nguyên hoặc danh sách mặt hàng thiếu, có thể dùng sealed hierarchy với từng record mô tả một trường hợp:

~~~java
public sealed interface OrderError
        permits OrderNotFound, AccessDenied, InvalidOrderState, InsufficientStock {}

public record OrderNotFound(UUID orderId) implements OrderError {}

public record AccessDenied() implements OrderError {}

public record InvalidOrderState(String currentState)
        implements OrderError {}

public record StockShortage(
    UUID productId,
    int requested,
    int available
) {}

public record InsufficientStock(List<StockShortage> items)
        implements OrderError {}
~~~

Mỗi kiểu top-level public trong ví dụ được đặt ở file Java riêng; các import như UUID và List được lược bớt để tập trung vào cấu trúc. Dữ liệu lỗi nên vừa đủ để tầng gọi quyết định phản hồi. Không đưa thông tin nhạy cảm hoặc chi tiết nội bộ như câu SQL, mật khẩu hay token vào error object.

### 4.3. Service trả Result

Ví dụ Service thực hiện thao tác gửi đơn:

~~~java
@Transactional
public Result<OrderReceipt, OrderError> submit(
        UUID orderId,
        UserId actor) {

    Optional<Order> found = orderRepository.findById(orderId);

    if (found.isEmpty()) {
        return Result.failure(new OrderNotFound(orderId));
    }

    Order order = found.get();

    if (!accessPolicy.canSubmit(actor, order)) {
        return Result.failure(new AccessDenied());
    }

    if (!order.canSubmit()) {
        return Result.failure(
            new InvalidOrderState(order.status().name())
        );
    }

    List<StockShortage> shortages =
        inventory.reserveIfAvailable(order.lines());
    if (!shortages.isEmpty()) {
        return Result.failure(new InsufficientStock(shortages));
    }

    order.submit();
    orderRepository.save(order);

    return Result.success(
        new OrderReceipt(order.id(), order.status())
    );
}
~~~

Ví dụ trên tập trung vào cấu trúc hợp đồng; các kiểu policy, inventory và domain model là thành phần của ứng dụng. Trong ví dụ, reserveIfAvailable được giả định là thao tác nguyên tử: hoặc giữ đủ số lượng cho toàn bộ đơn, hoặc trả danh sách mặt hàng thiếu mà không giữ một phần. Nếu kho hàng nằm ở một dịch vụ riêng, không thể giả định transaction cơ sở dữ liệu của đơn hàng bao trùm dịch vụ đó; cần thiết kế quy trình phối hợp và bù trừ phù hợp.

Lỗi cơ sở dữ liệu hoặc timeout không bị chuyển thành OrderError trong ví dụ này. Chúng tiếp tục được ném lên dưới dạng exception để boundary xử lý như lỗi kỹ thuật.

### 4.4. Người gọi phải xử lý cả hai nhánh

Controller có thể dùng fold để ánh xạ kết quả sang HTTP response:

~~~java
@PostMapping("/{id}/submit")
public ResponseEntity<?> submit(
        @PathVariable UUID id,
        Authentication authentication) {

    Result<OrderReceipt, OrderError> result =
        orderService.submit(id, currentUser.id(authentication));

    return result.fold(
        receipt -> ResponseEntity.ok(receipt),
        error -> mapOrderError(error)
    );
}

private ResponseEntity<?> mapOrderError(OrderError error) {
    if (error instanceof OrderNotFound) {
        return ResponseEntity.notFound().build();
    }
    if (error instanceof AccessDenied) {
        return ResponseEntity.status(HttpStatus.FORBIDDEN).build();
    }
    if (error instanceof InvalidOrderState) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(new ApiError("INVALID_ORDER_STATE"));
    }
    if (error instanceof InsufficientStock) {
        return ResponseEntity.unprocessableEntity()
            .body(new ApiError("INSUFFICIENT_STOCK"));
    }
    throw new IllegalStateException("Unhandled order error: " + error);
}
~~~

Đoạn mã dùng sealed hierarchy để minh họa việc xử lý đầy đủ các trường hợp. Trong dự án thực tế, có thể đặt logic ánh xạ trong một mapper riêng hoặc dùng ControllerAdvice để tránh lặp lại ở nhiều endpoint.

Nếu Result có nhiều loại lỗi và nhiều Controller cần cùng cách ánh xạ, hãy định nghĩa error code ổn định và một thành phần chuyển đổi dùng chung. Không nên để từng Controller tự diễn giải cùng một lỗi theo cách khác nhau.

## 5. Dùng Exception cho luồng lỗi không thể tiếp tục

Exception phù hợp khi thao tác không thể hoàn thành theo luồng bình thường và nơi gọi không cần xử lý từng trường hợp ngay tại dòng gọi.

### 5.1. Tạo ngoại lệ có ý nghĩa

Nên dùng tên ngoại lệ mô tả vấn đề và giữ nguyên dữ liệu cần thiết:

~~~java
public class OrderNotFoundException extends RuntimeException {

    private final UUID orderId;

    public OrderNotFoundException(UUID orderId) {
        super("Order not found: " + orderId);
        this.orderId = orderId;
    }

    public UUID orderId() {
        return orderId;
    }
}
~~~

Không nên dùng một RuntimeException chung cho mọi lỗi nếu ứng dụng cần phân biệt cách xử lý. Ngoại lệ chuyên biệt giúp handler chọn đúng mã HTTP và log phù hợp.

### 5.2. Ném ngoại lệ từ Service

~~~java
@Transactional
public OrderReceipt submit(UUID orderId, UserId actor) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    accessPolicy.requireCanSubmit(actor, order);
    order.submit();

    orderRepository.save(order);

    return new OrderReceipt(order.id(), order.status());
}
~~~

Khi đơn hàng không tồn tại hoặc không thể tiếp tục, exception đi lên khỏi Service. Controller không cần bao quanh từng dòng bằng try/catch nếu ứng dụng có cơ chế xử lý lỗi tập trung.

### 5.3. Checked và unchecked exception

Java phân biệt:

- **Checked exception:** kế thừa Exception nhưng không kế thừa RuntimeException. Caller phải catch hoặc khai báo throws.
- **Unchecked exception:** kế thừa RuntimeException hoặc Error. Caller không bị buộc phải khai báo trong chữ ký; Error thường dành cho tình huống nghiêm trọng của JVM và không nên dùng làm lỗi nghiệp vụ của ứng dụng.

Checked exception có ích khi caller có thể và cần xử lý một tình huống phục hồi cụ thể, chẳng hạn một API thư viện báo lỗi đọc tệp mà caller có thể yêu cầu chọn tệp khác. Unchecked exception thường được dùng cho lỗi nghiệp vụ được quy ước xử lý tại boundary, lỗi trạng thái không hợp lệ hoặc lỗi kỹ thuật trong nhiều ứng dụng Java.

Không nên chọn checked hay unchecked chỉ theo việc muốn tránh viết try/catch. Hãy xem ai có thể xử lý lỗi, xử lý ở đâu và hợp đồng nào rõ nhất.

### 5.4. Giữ nguyên nguyên nhân của lỗi

Khi chuyển một exception cấp thấp thành exception có ý nghĩa hơn, hãy giữ cause:

~~~java
try {
    paymentGateway.authorize(request);
} catch (GatewayTimeoutException exception) {
    throw new PaymentServiceUnavailableException(
        "Payment provider did not respond",
        exception
    );
}
~~~

Giữ cause giúp log và chẩn đoán tìm được nguyên nhân gốc. Không nên đưa nội dung exception cấp thấp trực tiếp ra giao diện vì có thể chứa URL nội bộ, SQL, thông tin xác thực hoặc dữ liệu nhạy cảm.

## 6. Ranh giới giữa Result và Exception trong MVC

Một quy tắc hữu ích là biểu diễn những thất bại nghiệp vụ có thể dự đoán trong hợp đồng của ca sử dụng; để lỗi kỹ thuật hoặc tình huống không thể tiếp tục đi theo exception đến boundary phù hợp. Nhưng ứng dụng cần thống nhất, không nên mỗi Service chọn cách riêng mà không có lý do.

### 6.1. Controller không nên xử lý lỗi theo cách tùy tiện

Controller nên tập trung vào:

- Bind và kiểm tra request.
- Lấy danh tính đã xác thực.
- Gọi ca sử dụng.
- Ánh xạ kết quả nghiệp vụ sang View hoặc HTTP response.
- Đưa thông tin lỗi phù hợp vào giao diện.

Nếu Service trả Result, Controller hoặc một adapter ánh xạ cả nhánh thành công và thất bại. Nếu Service ném exception, ControllerAdvice hoặc cơ chế xử lý chung có thể chuyển exception thành response.

### 6.2. Xử lý exception tập trung với @ControllerAdvice

Spring MVC hỗ trợ xử lý ngoại lệ toàn cục bằng @ControllerAdvice:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            OrderNotFoundException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "Không tìm thấy đơn hàng được yêu cầu."
        );
        problem.setTitle("Không tìm thấy tài nguyên");
        problem.setProperty("code", "ORDER_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
    }

    @ExceptionHandler(PaymentServiceUnavailableException.class)
    public ResponseEntity<ProblemDetail> handlePaymentUnavailable(
            PaymentServiceUnavailableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Dịch vụ thanh toán hiện chưa khả dụng. Vui lòng thử lại sau."
        );
        problem.setTitle("Dịch vụ tạm thời không khả dụng");
        problem.setProperty("code", "PAYMENT_UNAVAILABLE");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(problem);
    }
}
~~~

Ví dụ dùng ProblemDetail trong Spring Framework 6+. Với ứng dụng server-rendered, có thể dùng @ControllerAdvice trả ModelAndView hoặc tên View lỗi. Với API, @RestControllerAdvice phù hợp khi muốn trả JSON.

Handler nên ánh xạ các loại lỗi đã biết một cách cụ thể. Không nên bắt mọi Exception rồi trả 400 Bad Request, vì lỗi database hoặc lỗi lập trình không phải lỗi request của người dùng.

### 6.3. Validation của biểu mẫu

Với form server-rendered, Spring MVC có thể bind và validate dữ liệu:

~~~java
@PostMapping("/orders")
public String create(
        @Valid @ModelAttribute("form") CreateOrderForm form,
        BindingResult bindingResult,
        Model model) {

    if (bindingResult.hasErrors()) {
        return "orders/new";
    }

    Result<OrderReceipt, OrderError> result =
        orderService.create(form.toCommand());

    return result.fold(
        receipt -> "redirect:/orders/" + receipt.orderId(),
        error -> {
            model.addAttribute("formError", errorMessage(error));
            return "orders/new";
        }
    );
}
~~~

BindingResult cần đặt ngay sau tham số được validate để Spring gắn lỗi binding/validation vào đúng đối tượng. Khi có lỗi trường, trả lại cùng View để người dùng sửa và giữ các giá trị đã nhập.

Nếu Service trả Result cho lỗi nghiệp vụ, Controller có thể hiển thị thông báo tổng quát hoặc gắn lỗi vào trường liên quan nếu có ánh xạ rõ. Không nên giả lập lỗi validation trường cho một lỗi hạ tầng.

### 6.4. Dùng cùng Service cho HTML và API

Một Service có thể được gọi bởi Controller HTML và Controller API. Service không nên trả chuỗi thông báo đã dịch hoặc mã HTTP vì đó là trách nhiệm trình bày/giao thức.

Ví dụ Service trả OrderError ổn định. Controller HTML chuyển thành thông điệp theo Locale; Controller API chuyển thành mã lỗi và ProblemDetail. Cùng một kết quả nghiệp vụ có thể có cách trình bày khác nhau nhưng giữ nguyên ý nghĩa.

## 7. Ánh xạ thất bại sang HTTP response

HTTP status code là một phần hợp đồng giữa máy chủ và client. Không ánh xạ mọi lỗi thành một mã duy nhất.

| Loại thất bại | Status thường dùng | Ghi chú |
|---|---:|---|
| Request sai cú pháp hoặc tham số không hợp lệ | 400 | Ví dụ kiểu dữ liệu không thể bind |
| Nội dung đúng cú pháp nhưng không đạt validation | 422 hoặc 400 theo hợp đồng | Cần nhất quán giữa API |
| Chưa xác thực | 401 | Client cần xác thực |
| Đã xác thực nhưng không đủ quyền | 403 | Có thể dùng 404 nếu chính sách cần che giấu tài nguyên |
| Không tìm thấy tài nguyên | 404 | Không nhầm với danh sách rỗng |
| Xung đột trạng thái hoặc version | 409 | Ví dụ dữ liệu đã được cập nhật |
| HTTP precondition không thỏa mãn | 412 | Ví dụ If-Match không khớp |
| Giới hạn tần suất bị vượt | 429 | Có thể kèm Retry-After |
| Lỗi hệ thống tạm thời | 503 | Có thể thử lại theo chính sách |
| Lỗi máy chủ không dự kiến | 500 | Không tiết lộ chi tiết nội bộ |

Một lỗi nghiệp vụ không tự động tương ứng với một status code cố định. Hãy xem semantics của HTTP và hợp đồng API. Ví dụ, thiếu tồn kho có thể được mô hình hóa là 409 do xung đột trạng thái tài nguyên hoặc 422 do không thể xử lý nội dung theo quy tắc nghiệp vụ. Quan trọng là chọn nhất quán và tài liệu hóa.

## 8. Transaction khi dùng Result hoặc Exception

Đây là khác biệt kỹ thuật quan trọng trong Spring: transaction không tự động rollback chỉ vì một phương thức trả về Result.failure.

### 8.1. Exception và rollback

Theo mặc định, Spring transaction thường rollback khi có RuntimeException hoặc Error đi ra khỏi phương thức transactional. Checked exception không tự động kích hoạt rollback theo mặc định, trừ khi cấu hình rollbackFor hoặc chính sách khác.

Ví dụ:

~~~java
@Transactional
public void transfer(Account from, Account to, Money amount) {
    from.withdraw(amount);
    to.deposit(amount);
    accountRepository.save(from);
    accountRepository.save(to);

    throw new IllegalStateException("Unexpected failure");
}
~~~

Nếu ngoại lệ unchecked thoát khỏi transaction boundary, transaction được rollback theo cấu hình mặc định. Nếu ngoại lệ bị bắt và không được ném tiếp, Spring có thể xem phương thức kết thúc bình thường và commit, trừ khi transaction đã được đánh dấu rollback-only.

### 8.2. Result.failure không tự rollback

Ví dụ:

~~~java
@Transactional
public Result<Receipt, TransferError> transfer(Command command) {
    debit(command);
    if (!creditAllowed(command)) {
        return Result.failure(TransferError.CREDIT_REJECTED);
    }
    credit(command);
    return Result.success(new Receipt());
}
~~~

Nếu debit đã ghi thay đổi rồi phương thức trả Failure bình thường, Spring có thể commit transaction. Điều đó có thể để lại trạng thái dở dang.

Thiết kế an toàn hơn:

- Kiểm tra mọi điều kiện có thể kiểm tra trước khi ghi.
- Thực hiện các cập nhật nguyên tử trong transaction.
- Nếu một bước thất bại sau khi đã ghi, đánh dấu rollback-only hoặc ném một exception nội bộ để transaction rollback.
- Không trả Result.failure như thể không có thay đổi nếu dữ liệu đã được ghi một phần.

Ví dụ minh họa kiểm tra trước:

~~~java
@Transactional
public Result<Receipt, TransferError> transfer(Command command) {
    Account from = loadSource(command);
    Account to = loadTarget(command);

    if (!from.canWithdraw(command.amount())) {
        return Result.failure(TransferError.INSUFFICIENT_FUNDS);
    }

    if (!to.canReceive(command.amount())) {
        return Result.failure(TransferError.RECEIVER_REJECTED);
    }

    from.withdraw(command.amount());
    to.deposit(command.amount());

    return Result.success(new Receipt());
}
~~~

Trong thực tế, các điều kiện có thể thay đổi đồng thời giữa lúc kiểm tra và lúc ghi. Cần kết hợp locking, version hoặc cập nhật có điều kiện để giữ tính nguyên tử. Ví dụ trên chỉ minh họa thứ tự kiểm tra trước khi thay đổi.

### 8.3. Khi dùng checked exception

Nếu phương thức transactional ném checked exception và nghiệp vụ yêu cầu rollback, có thể cấu hình:

~~~java
@Transactional(rollbackFor = PaymentRejectedException.class)
public PaymentReceipt charge(PaymentCommand command)
        throws PaymentRejectedException {
    accountRepository.debit(command.accountId(), command.amount());
    paymentLedger.record(command); // Có thể ném checked PaymentRejectedException
    return new PaymentReceipt(command.paymentId());
}
~~~

Hãy khai báo chính xác loại exception cần rollback. Không nên bật rollback cho mọi Throwable một cách tùy tiện nếu ứng dụng có quy ước khác.

## 9. Không che giấu lỗi và không biến lỗi kỹ thuật thành lỗi nghiệp vụ

Một lỗi phổ biến là bắt exception quá rộng rồi trả một giá trị mặc định:

~~~java
public Order findOrder(UUID id) {
    try {
        return repository.findById(id).orElse(null);
    } catch (Exception exception) {
        return null;
    }
}
~~~

Cách này khiến “không tìm thấy đơn hàng”, “database mất kết nối” và “lỗi lập trình” đều trở thành null. Caller không thể biết điều gì đã xảy ra và có thể tiếp tục với dữ liệu sai.

Một cách rõ ràng hơn:

~~~java
public Optional<Order> findOrder(UUID id) {
    return repository.findById(id);
}
~~~

Optional phù hợp khi việc không có kết quả là một phần bình thường của truy vấn. Nếu một ca sử dụng yêu cầu tài nguyên bắt buộc phải tồn tại, có thể chuyển thành typed Result hoặc NotFoundException tại application boundary.

Các nguyên tắc cần giữ:

- Không catch Exception chỉ để trả null hoặc danh sách rỗng.
- Không log rồi nuốt exception nếu caller cần biết thao tác thất bại.
- Không chuyển mọi lỗi kỹ thuật thành “dữ liệu không hợp lệ”.
- Không trả thông báo nội bộ hoặc stack trace cho client.
- Khi wrap exception, giữ cause.
- Chỉ catch tại nơi có thể phục hồi, bổ sung ngữ cảnh hoặc chuyển đổi hợp đồng.

## 10. Thiết kế mã lỗi và thông điệp cho người dùng

Mã lỗi nên ổn định và không phụ thuộc câu chữ đã dịch. Ví dụ:

| Error code | Ý nghĩa | Thông điệp tiếng Việt |
|---|---|---|
| ORDER_NOT_FOUND | Không tìm thấy đơn | Không tìm thấy đơn hàng |
| INVALID_ORDER_STATE | Trạng thái không cho phép | Đơn hàng hiện không thể thực hiện thao tác này |
| INSUFFICIENT_STOCK | Không đủ tồn kho | Số lượng yêu cầu hiện không còn đủ |
| STALE_VERSION | Dữ liệu đã thay đổi | Dữ liệu vừa được cập nhật. Hãy tải lại trước khi lưu |
| VALIDATION_FAILED | Dữ liệu đầu vào không hợp lệ | Vui lòng kiểm tra các trường được đánh dấu |
| INTERNAL_ERROR | Lỗi không dự kiến | Hệ thống chưa thể xử lý yêu cầu |

Mã lỗi dùng cho client hoặc log có thể được lưu trong enum hoặc error object. Thông điệp hiển thị nên nằm trong message bundle để hỗ trợ nhiều Locale.

Không đưa thông tin nhạy cảm vào message. Ví dụ, thay vì nói “Tài khoản này tồn tại nhưng thuộc tổ chức X”, có thể dùng thông báo chung nếu việc tiết lộ đó tạo rủi ro bảo mật.

## 11. Logging, tracing và quan sát lỗi

Không phải mọi thất bại đều cần log ở cùng mức độ:

- Validation do người dùng nhập sai thường không cần ghi stack trace ở mức ERROR.
- Từ chối nghiệp vụ có thể được ghi nhận ở mức INFO hoặc audit nếu có yêu cầu.
- Timeout, mất kết nối hoặc lỗi hạ tầng cần log đủ ngữ cảnh để điều tra.
- Lỗi lập trình không dự kiến cần stack trace ở boundary và cảnh báo phù hợp.

Nên tránh log cùng một exception ở mọi tầng. Nếu Repository, Service, Controller và exception handler đều log cùng lỗi, một sự cố sẽ tạo nhiều bản ghi trùng. Thường log đầy đủ tại boundary xử lý cuối cùng, còn các tầng dưới bổ sung context bằng cách wrap hoặc gắn correlation ID.

Không log password, access token, session cookie, dữ liệu thẻ hoặc toàn bộ payload có thông tin cá nhân nếu không có nhu cầu và chính sách bảo vệ phù hợp.

## 12. Kiểm thử Result và Exception

Mỗi cách biểu diễn cần được kiểm thử ở nơi có trách nhiệm.

### 12.1. Kiểm thử Result

Với Service trả Result, kiểm tra từng nhánh:

- Thành công trả dữ liệu đúng.
- Mỗi loại lỗi nghiệp vụ trả error code đúng.
- Không ghi dữ liệu khi thất bại.
- Người gọi xử lý đủ các nhánh.
- Không chuyển lỗi kỹ thuật thành Result nghiệp vụ nếu không có chủ đích.

Ví dụ:

~~~java
@Test
void submitReturnsInsufficientStockWhenInventoryIsLow() {
    Result<OrderReceipt, OrderError> result =
        service.submit(orderId, userId);

    assertThat(result).isInstanceOf(Result.Failure.class);
    verify(orderRepository, never()).save(any());
}
~~~

Trong test thực tế, cần cấu hình fixture và mock inventory để xác định rõ tồn kho thấp. Nếu dùng Result sealed hierarchy, có thể kiểm tra bằng fold hoặc helper assertion riêng.

### 12.2. Kiểm thử Exception

Kiểm tra:

- Đúng loại exception được ném.
- Exception giữ cause khi wrap lỗi kỹ thuật.
- Transaction rollback theo cấu hình.
- Exception handler ánh xạ đúng HTTP status và error code.
- Phản hồi không chứa stack trace hoặc dữ liệu nhạy cảm.

Ví dụ:

~~~java
assertThatThrownBy(() -> service.submit(missingOrderId, userId))
    .isInstanceOf(OrderNotFoundException.class);
~~~

### 12.3. Kiểm thử MVC boundary

Với Spring MVC, dùng MockMvc hoặc công cụ tích hợp tương đương để xác nhận:

- Request sai định dạng trả 400.
- Validation lỗi trả lại form hoặc response validation theo hợp đồng.
- NotFoundException trả 404.
- Conflict trả 409.
- Lỗi kỹ thuật không bị ánh xạ nhầm thành 400.
- Trang HTML hiển thị thông báo phù hợp Locale.
- API trả JSON error contract ổn định.

### 12.4. Kiểm thử transaction

Với lỗi sau khi đã có thao tác ghi, xác nhận transaction rollback và dữ liệu không ở trạng thái một phần. Đây là kiểm thử tích hợp cần database hoặc môi trường persistence thực tế; unit test chỉ xác nhận Result.failure chưa chứng minh transaction đã rollback.

## 13. Những lỗi thiết kế thường gặp

### Dùng boolean để biểu diễn mọi thất bại

Boolean chỉ nói thành công hay thất bại, không cho biết nguyên nhân. Nếu caller cần phản hồi khác nhau, hãy dùng typed Result hoặc exception chuyên biệt.

### Dùng null làm tín hiệu lỗi

Null dễ làm mất thông tin và gây NullPointerException ở nơi khác. Dùng Optional cho kết quả có thể vắng mặt hoặc Result/Exception cho thất bại có ý nghĩa.

### Dùng exception cho mọi nhánh nghiệp vụ thông thường

Nếu một thao tác thường xuyên bị từ chối do điều kiện dự kiến, dùng exception làm luồng điều khiển có thể khiến mã khó đọc và tạo nhiều stack trace không cần thiết. Cân nhắc Result cho những kết quả từ chối mà caller cần xử lý trực tiếp.

### Trả Result nhưng caller bỏ qua nhánh thất bại

Result chỉ hữu ích nếu caller buộc phải hoặc có quy ước xử lý cả hai nhánh. Dùng fold, match hoặc helper rõ ràng; không gọi lấy value mà không kiểm tra.

### Catch quá rộng và nuốt lỗi

Bắt mọi Exception rồi trả dữ liệu mặc định che giấu lỗi hệ thống và làm sai nghiệp vụ. Chỉ catch lỗi mà tầng hiện tại có thể xử lý hoặc chuyển đổi.

### Ánh xạ mọi exception thành 400

Lỗi database, lỗi cấu hình và bug không phải lỗi đầu vào. Hãy phân loại lỗi và ánh xạ status code theo ý nghĩa HTTP.

### Trả thông điệp kỹ thuật trực tiếp cho người dùng

Stack trace, tên bảng, câu SQL và URL nội bộ có thể làm lộ thông tin. Dùng mã lỗi ổn định và thông điệp đã được kiểm soát.

### Trả Failure sau khi đã ghi một phần dữ liệu

Result.failure không tự rollback transaction. Hãy kiểm tra trước khi ghi, dùng cập nhật nguyên tử hoặc đánh dấu rollback khi một bước thất bại sau khi đã thay đổi dữ liệu.

## 14. Quy trình chọn cách biểu diễn thất bại

Trước khi thiết kế chữ ký Service hoặc Controller, hãy đặt các câu hỏi:

1. Thất bại có phải kết quả bình thường, có thể dự đoán của nghiệp vụ không?
2. Caller có cần xử lý từng loại thất bại ngay tại nơi gọi không?
3. Có tập mã lỗi ổn định và hữu hạn hay không?
4. Thất bại có cần làm transaction rollback không?
5. Framework đã có cơ chế exception hoặc validation phù hợp chưa?
6. Có cần cùng một Service phục vụ HTML và API không?
7. Thông tin lỗi nào được phép đưa ra ngoài?
8. Các module khác có thể hiểu và xử lý hợp đồng này mà không phụ thuộc chi tiết triển khai không?

Gợi ý lựa chọn:

- Dùng **Result** khi thất bại là nhánh nghiệp vụ dự kiến và caller cần quyết định cách tiếp tục.
- Dùng **Exception** khi luồng không thể tiếp tục, lỗi kỹ thuật phát sinh hoặc framework đã có boundary xử lý tập trung.
- Dùng **Optional** khi chỉ cần biểu diễn một truy vấn có thể không có kết quả, không cần mô tả nhiều loại lỗi.
- Dùng **BindingResult/validation result** cho lỗi binding và validation của biểu mẫu.
- Không trộn nhiều kiểu cho cùng một loại lỗi nếu không có ranh giới rõ ràng.

## Kết luận

Kiểu Result và Exception là hai công cụ bổ sung để biểu diễn thất bại trong ứng dụng MVC. Result làm rõ những nhánh nghiệp vụ dự kiến trong hợp đồng của Service và buộc tầng gọi lựa chọn cách phản hồi. Exception phù hợp với luồng không thể tiếp tục, lỗi kỹ thuật hoặc tình huống cần được xử lý tại boundary chung. Controller ánh xạ thất bại thành View hoặc HTTP response; Service và Model giữ quy tắc nghiệp vụ; transaction phải được thiết kế để không commit dữ liệu dở dang. Khi chọn đúng cách biểu diễn và xử lý nhất quán, ứng dụng dễ kiểm thử, dễ quan sát và phản hồi lỗi rõ ràng hơn.

