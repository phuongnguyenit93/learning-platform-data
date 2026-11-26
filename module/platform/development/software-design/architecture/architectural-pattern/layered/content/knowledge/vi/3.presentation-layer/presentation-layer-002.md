# Chuyển dữ liệu giao thức thành yêu cầu đầu vào của ca sử dụng

Trong chương **Tầng trình bày**, bài học này giải thích cách tiếp nhận dữ liệu từ một giao thức bên ngoài và chuyển nó thành đầu vào mà ứng dụng có thể hiểu. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày tiếp xúc với người dùng hoặc hệ thống bên ngoài, tầng ứng dụng điều phối ca sử dụng, các thành phần nghiệp vụ thực hiện quy tắc và tầng dữ liệu xử lý việc lưu trữ.

Một yêu cầu HTTP thường chứa nhiều loại thông tin: đường dẫn, query parameter, header, nội dung JSON, danh tính đã xác thực và ngữ cảnh giao thức. Các thông tin này có cấu trúc phù hợp với HTTP, nhưng không nhất thiết phù hợp với ca sử dụng. Công việc của tầng trình bày là đọc và kiểm tra hình thức của dữ liệu giao thức, chuyển đổi nó thành một yêu cầu có ý nghĩa đối với ứng dụng, gọi ca sử dụng và chuyển kết quả thành phản hồi của giao thức.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu giao thức với dữ liệu đầu vào của ca sử dụng.
- Xác định trách nhiệm tiếp nhận, chuyển đổi, kiểm tra dữ liệu và gọi dịch vụ ứng dụng trong tầng trình bày.
- Thiết kế DTO và command phù hợp cho một endpoint Java/Spring.
- Phân biệt lỗi định dạng đầu vào với lỗi quy tắc nghiệp vụ và ánh xạ chúng thành phản hồi thích hợp.
- Kiểm thử việc chuyển đổi ở ranh giới mà không buộc tầng ứng dụng phụ thuộc vào HTTP hoặc Spring MVC.

## 1. Vì sao cần chuyển đổi ở ranh giới trình bày?

Giao thức mô tả cách hai bên trao đổi thông tin. Với HTTP, client có thể gửi một request như sau:

~~~http
POST /orders HTTP/1.1
Content-Type: application/json
Accept: application/json
Authorization: Bearer <token>
Idempotency-Key: 5a2f9c

{
  "lines": [
    { "productCode": "BOOK-101", "quantity": 2 },
    { "productCode": "PEN-202", "quantity": 3 }
  ]
}
~~~

Thông tin trên có nhiều phần mang tính giao thức:

- `POST /orders` xác định phương thức và tài nguyên HTTP.
- `Content-Type` cho biết cách diễn giải phần thân request.
- `Accept` mô tả định dạng phản hồi client có thể nhận.
- `Authorization` mang thông tin xác thực để lớp bảo mật xác định người gọi.
- `Idempotency-Key` là header mà API có thể quy định để nhận diện yêu cầu lặp.
- JSON mô tả cấu trúc dữ liệu theo hợp đồng của endpoint.

Ca sử dụng đặt hàng không nên phải biết `HttpServletRequest`, cách đọc header hay cách giải mã JSON. Nó cần một yêu cầu có ý nghĩa trong ngôn ngữ của ứng dụng, ví dụ: khách hàng đã xác thực muốn đặt những mặt hàng và số lượng cụ thể, kèm khóa chống xử lý lặp nếu nghiệp vụ hỗ trợ cơ chế đó.

Nếu chuyển nguyên request HTTP vào dịch vụ ứng dụng, tầng ứng dụng sẽ bị gắn với Spring MVC và HTTP. Điều đó khiến cùng ca sử dụng khó được gọi từ giao diện dòng lệnh, tác vụ nền, message consumer hoặc một API khác. Nếu controller tự thực hiện cả kiểm tra tồn kho, tính tổng tiền và lưu đơn, quy tắc nghiệp vụ lại bị đặt sai tầng. Ranh giới trình bày giúp giải quyết hai vấn đề này bằng một bước chuyển đổi rõ ràng.

## 2. Phân biệt dữ liệu giao thức, DTO và command

Ba khái niệm này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Dữ liệu giao thức | Thông tin được truyền theo cơ chế của giao thức | HTTP method, path, query, header, JSON body, thông tin xác thực. |
| DTO trình bày (request/response DTO) | Cấu trúc dữ liệu công bố cho client hoặc adapter giao tiếp | `CreateOrderRequest` có danh sách dòng hàng theo JSON của endpoint. |
| Command/query của ứng dụng | Yêu cầu diễn đạt một ca sử dụng hoặc nhu cầu đọc dữ liệu | `PlaceOrderCommand` yêu cầu ứng dụng thực hiện việc đặt hàng. |

DTO trình bày phản ánh hợp đồng của giao thức. Nó có thể mang tên trường, kiểu dữ liệu, cấu trúc lồng nhau và quy tắc tương thích mà API công bố. Command phản ánh ý định mà ứng dụng cần thực hiện. Hai kiểu có thể giống nhau trong một ứng dụng nhỏ, nhưng tách riêng khi nhu cầu của API và nhu cầu của ca sử dụng khác nhau.

Ví dụ, API có thể nhận `productCode` dưới dạng chuỗi vì đó là cách client nhận diện sản phẩm. Tầng trình bày có thể chuẩn hóa chuỗi hoặc chuyển nó thành kiểu định danh mà ứng dụng sử dụng. Command không cần chứa `@RequestBody`, `HttpHeaders` hay annotation của Spring. Nó chỉ chứa dữ liệu cần thiết để thực hiện ca sử dụng.

Không phải endpoint nào cũng cần một command riêng. Nếu DTO đã phù hợp với ý nghĩa và vòng đời của ca sử dụng, có thể dùng trực tiếp. Quyết định tách kiểu nên dựa trên sự khác biệt giữa hai hợp đồng và nhu cầu thay đổi độc lập, không phải một quy tắc máy móc rằng mỗi request luôn phải có hai lớp dữ liệu.

## 3. Các bước chuyển request thành đầu vào ca sử dụng

Một luồng xử lý thông thường ở tầng trình bày gồm các bước sau:

1. **Tiếp nhận request:** framework hoặc adapter đọc phương thức, đường dẫn, query, header và body theo giao thức.
2. **Giải mã và chuyển kiểu:** JSON được chuyển thành DTO; giá trị trên path hoặc query được chuyển thành kiểu dữ liệu tương ứng.
3. **Kiểm tra hình thức:** xác nhận trường bắt buộc, định dạng, giới hạn kích thước và kiểu dữ liệu có hợp lệ theo hợp đồng giao tiếp hay không.
4. **Lấy ngữ cảnh đáng tin cậy:** sử dụng danh tính đã xác thực hoặc thông tin được hệ thống bảo mật xác minh; không mặc nhiên tin một định danh do client tự khai báo.
5. **Ánh xạ sang đầu vào ca sử dụng:** tạo command/query bằng các kiểu và ý nghĩa mà ứng dụng hiểu.
6. **Gọi ca sử dụng:** chuyển quyền điều phối cho tầng ứng dụng.
7. **Chuyển kết quả thành phản hồi:** ánh xạ kết quả hoặc lỗi đã được phân loại thành status code, header và response body theo hợp đồng giao thức.

Các bước này là trách nhiệm logic, không bắt buộc mỗi bước phải nằm trong một lớp riêng. Spring MVC có thể tự thực hiện một phần giải mã và chuyển kiểu thông qua argument resolver và message converter. Controller hoặc mapper đảm nhận phần chuyển đổi còn lại.

## 4. Ví dụ với Java và Spring MVC

Giả sử API cung cấp endpoint tạo đơn hàng. Client gửi danh sách sản phẩm và số lượng. Danh tính khách hàng được lấy từ principal đã xác thực, không lấy từ một trường `customerId` tùy ý trong JSON.

### Request DTO

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.util.List;

public record CreateOrderRequest(
        @NotEmpty List<@Valid OrderLineRequest> lines
) {
    public record OrderLineRequest(
            @NotBlank String productCode,
            @Positive int quantity
    ) {}
}
~~~

`CreateOrderRequest` mô tả cấu trúc mà endpoint nhận. Annotation Bean Validation kiểm tra các điều kiện đầu vào cơ bản: danh sách phải có ít nhất một phần tử, mã sản phẩm không được để trống và số lượng phải lớn hơn không. Những quy tắc này phù hợp để từ chối request sai hình thức trước khi gọi ca sử dụng.

### Command thuộc ứng dụng

~~~java
import java.util.List;
import java.util.UUID;

public record PlaceOrderCommand(
        UUID customerId,
        List<Line> lines,
        String idempotencyKey
) {
    public record Line(String productCode, int quantity) {}
}
~~~

Command không chứa kiểu của Spring hoặc HTTP. Nó biểu đạt khách hàng nào đang đặt hàng, các dòng hàng cần đặt và khóa chống lặp nếu ứng dụng hỗ trợ hành vi đó. `UUID` và kiểu dữ liệu của command có thể khác với DTO công khai mà client gửi.

### Hợp đồng ca sử dụng và kết quả

~~~java
public interface PlaceOrder {
    OrderReceipt handle(PlaceOrderCommand command);
}

public record OrderReceipt(String orderId, String status) {}

public record OrderResponse(String orderId, String status) {}
~~~

Interface `PlaceOrder` thuộc ranh giới ứng dụng. Tầng trình bày biết cách gọi ca sử dụng qua hợp đồng này, nhưng không biết dịch vụ ứng dụng kiểm tra điều kiện đặt hàng hoặc lưu dữ liệu bằng công nghệ nào.

### Controller chuyển đổi request

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import java.util.stream.Collectors;

@RestController
class OrderController {
    private final PlaceOrder placeOrder;

    OrderController(PlaceOrder placeOrder) {
        this.placeOrder = placeOrder;
    }

    @PostMapping("/orders")
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request,
            @AuthenticationPrincipal AppPrincipal principal,
            @RequestHeader(value = "Idempotency-Key", required = false)
                    String idempotencyKey) {

        var lines = request.lines().stream()
                .map(line -> new PlaceOrderCommand.Line(
                        line.productCode(), line.quantity()))
                .collect(Collectors.toList());

        var command = new PlaceOrderCommand(
                principal.customerId(), lines, idempotencyKey);

        var receipt = placeOrder.handle(command);
        var response = new OrderResponse(
                receipt.orderId(), receipt.status());

        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
~~~

`AppPrincipal` là kiểu principal do ứng dụng định nghĩa và được Spring Security cung cấp sau khi xác thực. Tên lớp và cách cấu hình principal tùy dự án. Ví dụ này thể hiện một nguyên tắc quan trọng: nếu khách hàng được xác định từ phiên đăng nhập, controller lấy định danh từ ngữ cảnh xác thực đã được kiểm chứng thay vì tin một `customerId` do client gửi trong body.

Controller chuyển từng dòng request sang kiểu dòng hàng của command, kết hợp với ngữ cảnh xác thực và header có ý nghĩa đối với ca sử dụng, rồi gọi `PlaceOrder`. Nó không tính tổng tiền, kiểm tra tồn kho, quyết định khách hàng có được đặt hàng hay ghi trực tiếp vào repository. Những việc đó thuộc ứng dụng hoặc nghiệp vụ theo trách nhiệm cụ thể.

Ví dụ rút gọn trên giả định endpoint được bảo vệ để `principal` luôn tồn tại và command được ứng dụng hỗ trợ idempotency. Trong hệ thống thực tế, cần xác định rõ chính sách khi header bị thiếu, principal không hợp lệ hoặc client gửi khóa lặp; các chính sách đó phải được phản ánh trong hợp đồng API và ca sử dụng.

## 5. Chuyển đổi path, query và header

Không phải mọi dữ liệu đầu vào đều nằm trong JSON body. Ví dụ endpoint đọc đơn hàng có thể nhận mã đơn trên path và tùy chọn phân trang trên query:

~~~java
@GetMapping("/orders/{orderId}")
OrderResponse getOrder(
        @PathVariable UUID orderId,
        @RequestParam(defaultValue = "false") boolean includeLines) {

    var query = new GetOrderQuery(orderId, includeLines);
    var result = getOrder.handle(query);
    return new OrderResponse(result.orderId(), result.status());
}
~~~

Spring chuyển chuỗi trong path thành `UUID`. Nếu giá trị không đúng định dạng, request có thể bị từ chối ngay ở bước chuyển kiểu. `includeLines` là tùy chọn của hợp đồng HTTP và được chuyển thành boolean để query của ứng dụng không phải tự đọc query string.

Header cũng cần được chọn lọc. Một số header chỉ phục vụ giao thức, chẳng hạn `Accept` hoặc `Content-Type`, và thường do framework xử lý. Header khác có thể mang ý nghĩa đối với ca sử dụng, ví dụ khóa chống lặp hoặc mã tương quan. Chỉ chuyển thông tin thực sự cần thiết sang command hoặc context của ứng dụng; tránh chuyển nguyên `HttpHeaders` hay `HttpServletRequest` xuống tầng nghiệp vụ.

## 6. Kiểm tra đầu vào ở đúng tầng

Không phải mọi kiểm tra đều thuộc tầng trình bày. Có thể phân biệt ba nhóm:

| Nhóm kiểm tra | Câu hỏi | Nơi thường xử lý | Ví dụ |
|---|---|---|---|
| Giao thức và cú pháp | Request có đúng định dạng và cấu trúc API không? | Framework/adapter trình bày | JSON hỏng, UUID sai định dạng, thiếu body, Content-Type không hỗ trợ. |
| Ràng buộc dữ liệu đầu vào | Giá trị có đáp ứng điều kiện hình thức của hợp đồng không? | Tầng trình bày, thường dùng Bean Validation | Tên không rỗng, số lượng dương, giới hạn độ dài chuỗi. |
| Quy tắc nghiệp vụ | Yêu cầu có hợp lệ trong trạng thái và ngữ cảnh hiện tại của hệ thống không? | Tầng ứng dụng/nghiệp vụ | Khách hàng bị khóa, sản phẩm ngừng bán, số lượng vượt tồn kho. |

Ví dụ, `quantity` phải là số nguyên dương là điều kiện đầu vào đơn giản. Nhưng số lượng đó có được phép đặt hay không có thể phụ thuộc tồn kho, giới hạn của khách hàng, thời điểm khuyến mãi hoặc trạng thái sản phẩm. Controller không nên truy vấn repository để tự kiểm tra các điều kiện này rồi lặp lại trong dịch vụ ứng dụng. Ca sử dụng hoặc mô hình nghiệp vụ cần kiểm tra chúng tại nơi có đủ dữ liệu và quyền quyết định.

Một kiểm tra có thể xuất hiện ở nhiều tầng vì lý do khác nhau. Tầng trình bày có thể kiểm tra sớm để trả lỗi rõ ràng cho client; tầng ứng dụng vẫn phải bảo vệ quy tắc của mình vì ca sử dụng có thể được gọi từ nhiều adapter khác nhau. Không được xem kiểm tra ở giao diện hoặc API là cơ chế bảo vệ duy nhất cho nghiệp vụ.

## 7. Ánh xạ lỗi thành phản hồi giao thức

Lỗi ở ranh giới trình bày cần được diễn đạt theo hợp đồng mà client hiểu. Một cách phân loại thường gặp:

- Request sai cú pháp hoặc sai kiểu dữ liệu: phản hồi `400 Bad Request`.
- Người gọi chưa xác thực: phản hồi `401 Unauthorized` theo cơ chế xác thực của API.
- Người gọi đã xác thực nhưng không có quyền: phản hồi `403 Forbidden`.
- Tài nguyên được yêu cầu không tồn tại: phản hồi `404 Not Found`.
- Xung đột trạng thái hoặc vi phạm điều kiện nghiệp vụ được mô hình hóa là xung đột: có thể phản hồi `409 Conflict`.
- Lỗi hệ thống ngoài dự kiến: phản hồi `500 Internal Server Error` với thông tin an toàn cho client.

Mã trạng thái cụ thể phụ thuộc hợp đồng API và bản chất lỗi. Không nên ánh xạ mọi exception thành `400`, cũng không nên gửi stack trace, câu SQL hoặc thông tin nội bộ của hệ thống ra response.

Trong Spring, `@RestControllerAdvice` có thể tập trung chuyển lỗi thành response. Ví dụ minh họa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.MethodArgumentNotValidException;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> handleInvalidInput(
            MethodArgumentNotValidException exception) {
        var error = new ApiError(
                "INVALID_REQUEST", "Dữ liệu gửi lên không hợp lệ");
        return ResponseEntity.badRequest().body(error);
    }

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ApiError> handleOrderConflict(
            OrderConflictException exception) {
        var error = new ApiError(
                "ORDER_CONFLICT", exception.getMessage());
        return ResponseEntity.status(HttpStatus.CONFLICT).body(error);
    }
}

record ApiError(String code, String message) {}
~~~

Trong hệ thống thực tế, nội dung lỗi nghiệp vụ cần được kiểm soát để không tiết lộ dữ liệu nhạy cảm hoặc chi tiết triển khai. Có thể dùng `ProblemDetail` của Spring Framework hoặc một cấu trúc lỗi thống nhất của API. Bộ xử lý lỗi cũng cần xử lý các trường hợp chuyển kiểu và giải mã JSON thất bại, vì những lỗi đó có thể xảy ra trước khi phương thức controller được gọi.

## 8. Những cách làm khiến ranh giới bị phá vỡ

| Cách làm | Vấn đề | Cách cải thiện |
|---|---|---|
| Truyền `HttpServletRequest` vào dịch vụ ứng dụng. | Ca sử dụng bị gắn với servlet và HTTP. | Trích xuất các giá trị cần thiết thành command hoặc context độc lập giao thức. |
| Trả JPA entity trực tiếp cho client và dùng entity làm request DTO. | Hợp đồng API bị gắn với mô hình lưu trữ, mapping ORM và trường nội bộ. | Dùng DTO trình bày phù hợp với API và ánh xạ ở ranh giới. |
| Controller tự kiểm tra tồn kho rồi tính giá và lưu đơn. | Quy tắc nghiệp vụ và điều phối bị đặt trong tầng trình bày. | Controller tạo command và giao việc cho ca sử dụng. |
| Dùng dữ liệu `customerId` trong body để xác định người đang đăng nhập. | Client có thể khai báo định danh không thuộc quyền của mình. | Lấy danh tính từ principal hoặc context đã được xác thực, rồi áp dụng kiểm tra quyền ở tầng phù hợp. |
| Đưa toàn bộ header và query string vào command. | Hợp đồng ứng dụng bị nhiễm chi tiết giao thức không cần thiết. | Chỉ ánh xạ những giá trị có ý nghĩa đối với ca sử dụng. |
| Dùng một DTO khổng lồ cho nhiều endpoint không liên quan. | Hợp đồng khó hiểu và thay đổi một endpoint có thể ảnh hưởng endpoint khác. | Tạo kiểu đầu vào theo nhu cầu thực tế của từng hợp đồng; chia sẻ kiểu nhỏ khi ngữ nghĩa thực sự giống nhau. |

Một controller mỏng không có nghĩa là controller không được chuyển đổi dữ liệu. Việc ánh xạ request thành command và kết quả thành response chính là một phần trách nhiệm của tầng trình bày. Controller trở nên quá tải khi nó chứa quy tắc nghiệp vụ, truy cập trực tiếp dữ liệu hoặc tự điều phối nhiều tầng thay cho ca sử dụng.

## 9. Tầng trình bày không chỉ có HTTP

HTTP và Spring MVC là ví dụ phổ biến, nhưng tầng trình bày có thể tiếp nhận dữ liệu từ nhiều giao thức hoặc hình thức tương tác:

- Giao diện dòng lệnh chuyển đối số và tùy chọn thành command.
- Message consumer giải mã message, kiểm tra metadata và chuyển payload thành yêu cầu ứng dụng.
- WebSocket adapter chuyển message thành thao tác của ca sử dụng.
- Một API gRPC chuyển protobuf request thành kiểu đầu vào của ứng dụng.

Các adapter này có thể có DTO, cách xác thực, cách kiểm tra và cách ánh xạ lỗi khác nhau. Chúng vẫn có thể gọi cùng một hợp đồng ứng dụng nếu cùng biểu đạt một ca sử dụng. Điều này giúp nghiệp vụ không cần biết yêu cầu đến từ trình duyệt, message broker hay dòng lệnh.

Các tầng logic cũng không bắt buộc phải chạy ở các tiến trình hoặc máy chủ riêng. Controller, dịch vụ ứng dụng, nghiệp vụ và adapter dữ liệu có thể nằm trong cùng một ứng dụng Spring. Tách tầng là cách phân chia trách nhiệm và phụ thuộc trong thiết kế; quyết định triển khai thành các tier riêng là một lựa chọn kiến trúc khác.

## 10. Kiểm thử việc chuyển đổi ở ranh giới

Kiểm thử tầng trình bày nên xác nhận hợp đồng giao thức và cách ánh xạ sang ứng dụng:

| Loại kiểm thử | Nội dung cần xác nhận | Ví dụ |
|---|---|---|
| Kiểm thử controller | Request hợp lệ tạo đúng command và phản hồi đúng | Gửi JSON có hai dòng hàng, xác nhận ca sử dụng nhận đúng mã sản phẩm và số lượng; response có status và body theo hợp đồng. |
| Kiểm thử validation | Dữ liệu sai bị từ chối trước khi gọi ca sử dụng | Số lượng bằng 0 hoặc danh sách rỗng trả lỗi 400; dịch vụ ứng dụng không được gọi. |
| Kiểm thử bảo mật ở endpoint | Ngữ cảnh người gọi được lấy đúng | Request của principal A tạo command với customer ID của A; người chưa xác thực bị từ chối theo cấu hình. |
| Kiểm thử ánh xạ lỗi | Lỗi ứng dụng được chuyển thành lỗi giao thức phù hợp | Lỗi xung đột của ca sử dụng trở thành HTTP 409 và response không chứa chi tiết nội bộ. |
| Kiểm thử tích hợp | Bộ giải mã và cấu hình Spring phối hợp đúng | JSON, header, validation và bộ xử lý lỗi hoạt động như khi chạy ứng dụng. |

Có thể dùng `MockMvc` để kiểm tra controller qua HTTP giả lập và thay hợp đồng ca sử dụng bằng mock hoặc fake. Những kiểm thử này giúp phát hiện việc đổi tên trường JSON, thay đổi quy tắc validation hoặc ánh xạ nhầm header. Tầng ứng dụng cần có unit test riêng cho quy tắc ca sử dụng; không nên dựa vào test controller để chứng minh nghiệp vụ đúng.

Một kiểm tra hữu ích là gọi cùng một ca sử dụng từ một adapter khác, chẳng hạn một message consumer hoặc test trực tiếp dịch vụ ứng dụng. Nếu phải dựng `HttpServletRequest` chỉ để gọi nghiệp vụ, có thể hợp đồng ứng dụng đang chứa dữ liệu giao thức không cần thiết.

## 11. Tự rà soát thiết kế

Khi xây dựng một endpoint hoặc adapter trình bày, hãy tự hỏi:

1. Dữ liệu nào đến từ path, query, header, body và ngữ cảnh xác thực?
2. Phần nào chỉ phục vụ giao thức, phần nào thuộc hợp đồng DTO, và phần nào thật sự cần cho ca sử dụng?
3. Kiểu đầu vào của ứng dụng có phụ thuộc vào HTTP, Spring MVC hoặc cấu trúc JSON không?
4. Các kiểm tra ở controller có giới hạn ở cú pháp và ràng buộc đầu vào, hay đã bắt đầu lặp lại quy tắc nghiệp vụ?
5. Định danh và quyền của người gọi có đến từ nguồn đã xác thực không?
6. Lỗi được ánh xạ theo hợp đồng API mà không làm lộ chi tiết nội bộ không?
7. Có thể kiểm thử việc chuyển đổi mà không khởi động toàn bộ hệ thống lưu trữ không?

Nếu tầng ứng dụng phải đọc header, giải mã JSON hoặc biết status code HTTP, hãy xem lại nơi chuyển đổi. Nếu controller tự truy cập dữ liệu hoặc quyết định quy tắc miền, hãy chuyển trách nhiệm về ca sử dụng hoặc thành phần nghiệp vụ tương ứng. Mục tiêu là để mỗi tầng sử dụng ngôn ngữ và kiểu dữ liệu phù hợp với vai trò của nó.

## Kết luận

Tầng trình bày là ranh giới chuyển dữ liệu giao thức thành ý định mà ứng dụng có thể xử lý. Nó tiếp nhận và giải mã request, kiểm tra hình thức, lấy ngữ cảnh đã xác thực, ánh xạ thành command/query, gọi ca sử dụng và chuyển kết quả hoặc lỗi thành phản hồi giao thức. Giữ bước chuyển đổi này rõ ràng giúp tầng ứng dụng độc lập với HTTP và Spring, đồng thời giúp API thay đổi có kiểm soát mà không làm rò rỉ chi tiết trình bày vào nghiệp vụ.
