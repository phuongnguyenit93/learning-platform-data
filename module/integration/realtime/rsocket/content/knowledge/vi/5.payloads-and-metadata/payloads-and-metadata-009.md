# Thiết kế DTO, giới hạn kích thước và kiểm tra dữ liệu đầu vào

RSocket cho phép truyền payload liên tục trên các tương tác request-response, request-stream và request-channel. Vì kết nối có thể được duy trì lâu dài và nhiều stream có thể hoạt động đồng thời, một payload không được kiểm soát có thể tiêu tốn bộ nhớ, làm tăng độ trễ hoặc khiến dịch vụ xử lý dữ liệu ngoài dự kiến.

Thiết kế payload an toàn bắt đầu từ hợp đồng dữ liệu rõ ràng. Ứng dụng Java nên dùng DTO chuyên biệt cho từng hướng giao tiếp, giới hạn kích thước data và metadata, kiểm tra cấu trúc lẫn ý nghĩa nghiệp vụ, đồng thời xác thực quyền thực hiện thao tác. Các lớp kiểm tra này bổ sung cho flow control của RSocket: backpressure điều tiết số phần tử được gửi theo demand, còn giới hạn kích thước và validation bảo vệ tài nguyên cũng như tính đúng đắn của dữ liệu.

## 1. Payload là ranh giới dữ liệu giữa hai peer

Một payload RSocket có thể mang hai phần:

- **Data:** nội dung nghiệp vụ, thường được codec chuyển đổi từ object Java sang JSON, CBOR hoặc định dạng nhị phân khác.
- **Metadata:** thông tin phụ trợ như route, MIME type, tracing hoặc dữ liệu xác thực theo quy ước của ứng dụng.

Data và metadata đều đến từ peer bên kia. Dù kết nối đã được thiết lập và được mã hóa bằng TLS, nội dung payload vẫn phải được coi là đầu vào cần kiểm tra. TLS bảo vệ kênh truyền và danh tính kết nối theo cấu hình; nó không bảo đảm rằng DTO hợp lệ hoặc người gửi có quyền sửa tài nguyên được chỉ định trong payload.

Một luồng xử lý điển hình:

~~~mermaid
flowchart LR
    A[Peer gửi] --> B[Transport / RSocket frame]
    B --> C[Giới hạn kích thước]
    C --> D[Decode payload]
    D --> E[Kiểm tra cấu trúc DTO]
    E --> F[Kiểm tra quy tắc nghiệp vụ]
    F --> G[Xác thực quyền]
    G --> H[Service xử lý]
    H --> I[Response hoặc stream]
~~~

Mỗi bước có mục tiêu riêng. Giới hạn kích thước cần được áp dụng trước khi ứng dụng phải giữ một payload quá lớn trong bộ nhớ. Decode chuyển byte thành kiểu dữ liệu. Validation cấu trúc kiểm tra trường bắt buộc, độ dài và định dạng. Validation nghiệp vụ kiểm tra các quan hệ như số lượng hợp lệ hoặc trạng thái có cho phép chuyển tiếp. Authorization xác nhận peer hiện tại có quyền thực hiện thao tác.

## 2. Thiết kế DTO theo hợp đồng giao tiếp

DTO (Data Transfer Object) mô tả dữ liệu đi qua ranh giới giữa client và server. DTO nên thể hiện đúng nhu cầu của một thao tác, có tên trường rõ ràng và kiểu dữ liệu phù hợp.

Không nên nhận trực tiếp entity persistence làm payload đầu vào. Entity thường chứa quan hệ nội bộ, trạng thái quản trị, trường audit hoặc thuộc tính không dành cho client. Nếu bind trực tiếp dữ liệu không tin cậy vào entity, client có thể thử thay đổi những trường mà API không định cho phép cập nhật.

### Tách DTO theo mục đích

Ví dụ một dịch vụ đơn hàng có thể định nghĩa:

- CreateOrderRequest: dữ liệu client gửi để tạo đơn.
- OrderLineRequest: một dòng hàng trong yêu cầu.
- OrderAccepted: phản hồi xác nhận đã tiếp nhận.
- OrderStatusUpdate: phần tử trong stream cập nhật trạng thái.

DTO request và response có thể có trường khác nhau. Client không nên được tự gửi các trường do server quản lý như **createdAt**, **approvedBy**, **internalStatus** hoặc tổng tiền đã được server tính lại.

### Dùng kiểu dữ liệu có giới hạn rõ ràng

| Dữ liệu | Kiểu nên cân nhắc | Lý do |
|---|---|---|
| Mã định danh | UUID hoặc String có giới hạn | Tránh chuỗi tùy ý, quá dài |
| Số lượng | int hoặc long với miền giá trị rõ | Tránh nhận số âm hoặc vượt giới hạn |
| Tiền | BigDecimal với precision/scale được kiểm soát | Tránh sai số nhị phân của floating point |
| Thời điểm | Instant hoặc kiểu thời gian có timezone rõ | Tránh diễn giải thời gian không nhất quán |
| Danh sách | List với giới hạn số phần tử | Kiểm soát kích thước request và công việc phát sinh |
| Nội dung tự do | String có giới hạn ký tự và byte | Giảm nguy cơ payload lớn |

Không dùng kiểu Object, map tùy ý hoặc cấu trúc polymorphic quá rộng cho những trường có hợp đồng cố định. Nếu cần mở rộng schema, hãy định nghĩa rõ trường, kiểu, phiên bản và quy tắc tương thích.

### Ví dụ DTO với Jakarta Bean Validation

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateOrderRequest(
    @NotBlank
    @Size(max = 40)
    String customerId,

    @NotEmpty
    @Size(max = 50)
    List<@Valid OrderLineRequest> items,

    @Size(max = 500)
    String note
) {}

public record OrderLineRequest(
    @NotBlank
    @Size(max = 40)
    String sku,

    @Positive
    int quantity
) {}
~~~

Các annotation thể hiện một phần hợp đồng:

- @NotBlank yêu cầu chuỗi có nội dung sau khi loại bỏ khoảng trắng.
- @NotEmpty yêu cầu danh sách không rỗng.
- @Size giới hạn độ dài chuỗi hoặc số phần tử trong collection.
- @Positive yêu cầu số lớn hơn 0.
- @Valid yêu cầu validator tiếp tục kiểm tra các phần tử lồng bên trong.

@Size trên String giới hạn số đơn vị ký tự theo cách validator định nghĩa, không phải số byte UTF-8. Với nội dung đa ngôn ngữ hoặc dữ liệu nhị phân, cần giới hạn byte riêng ở lớp payload.

## 3. Kiểm tra cấu trúc và quy tắc nghiệp vụ

Validation nên được chia thành nhiều lớp để lỗi được phát hiện ở nơi phù hợp.

### Kiểm tra cấu trúc

Kiểm tra DTO có đúng schema hay không:

- Trường bắt buộc có mặt.
- Chuỗi không rỗng và không vượt độ dài.
- Số nằm trong miền cho phép.
- Danh sách có số phần tử tối đa.
- Phần tử lồng nhau cũng được kiểm tra.
- Enum hoặc mã trạng thái thuộc tập giá trị đã định nghĩa.

Ví dụ, một request có 10.000 dòng hàng dù từng dòng đều hợp lệ vẫn có thể tạo ra lượng công việc quá lớn. Vì thế cần giới hạn cả collection ở cấp cha.

### Kiểm tra quy tắc nghiệp vụ

Một DTO có thể hợp lệ về cấu trúc nhưng không hợp lệ về nghiệp vụ. Ví dụ:

- Số lượng hàng không vượt tồn kho.
- Ngày kết thúc phải sau ngày bắt đầu.
- Mã khách hàng phải thuộc tenant hiện tại.
- Một trạng thái đơn hàng chỉ được chuyển sang trạng thái kế tiếp hợp lệ.
- Tổng giá trị đơn hàng không vượt hạn mức.

Các quy tắc phụ thuộc dữ liệu hiện tại nên được kiểm tra trong service hoặc domain layer, không chỉ trong annotation trên DTO. Kiểm tra quyền truy cập cũng phải dựa trên principal của phiên và tài nguyên thực tế; không tin một customerId hoặc tenantId do client tự khai báo.

### Thực hiện validation trong Spring

Spring có thể tích hợp Jakarta Bean Validation cho các message handler. Ví dụ minh họa một endpoint nhận request:

~~~java
import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderService orderService;

    public OrderRSocketController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("orders.create")
    public Mono<OrderAccepted> create(
            @Valid CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

Ứng dụng cần cấu hình Bean Validation provider và cơ chế validation phù hợp với phiên bản Spring đang sử dụng. Có thể kiểm tra thủ công bằng jakarta.validation.Validator khi cần điều khiển rõ ràng điểm phát sinh lỗi:

~~~java
Set<ConstraintViolation<CreateOrderRequest>> violations =
    validator.validate(request);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
~~~

Dù dùng validation tự động hay thủ công, không nên chờ đến khi ghi database mới phát hiện request sai cấu trúc.

## 4. Giới hạn kích thước payload và frame

Giới hạn kích thước là hàng rào bảo vệ tài nguyên. Một payload quá lớn có thể chiếm bộ nhớ khi nhận frame, ghép fragment, decode, tạo object và xử lý nghiệp vụ. Một request nhỏ về số lượng trường vẫn có thể rất lớn nếu chứa chuỗi hoặc byte array dài.

Cần phân biệt ít nhất ba giới hạn:

1. **Kích thước frame:** số byte tối đa cho một frame trên kết nối.
2. **Kích thước payload logic:** tổng số byte của payload sau khi ghép fragment.
3. **Giới hạn từng trường và cấu trúc:** độ dài chuỗi, kích thước blob, số phần tử trong list, độ sâu lồng nhau.

Fragmentation giúp chia một payload lớn thành nhiều frame nhỏ hơn. Nó không làm payload logic trở nên nhỏ hơn và không loại bỏ nhu cầu đặt giới hạn tổng kích thước. Một peer có thể gửi rất nhiều fragment để tạo thành payload vượt mức bộ nhớ mà ứng dụng có thể chấp nhận.

### Chọn giới hạn theo nghiệp vụ

| Loại tương tác | Ví dụ dữ liệu | Hướng kiểm soát |
|---|---|---|
| Request-response | Tra cứu một đơn hàng | DTO nhỏ, giới hạn tổng payload thấp |
| Fire-and-forget | Tín hiệu hoặc sự kiện | Giới hạn payload, tốc độ gửi và số request |
| Request-stream | Cập nhật trạng thái | Giới hạn kích thước từng phần tử và demand |
| Request-channel | Trao đổi dữ liệu hai chiều | Giới hạn từng payload, từng hướng và tổng tài nguyên phiên |
| Payload lớn | Tệp hoặc blob | Dùng truyền theo chunk có giới hạn hoặc object storage riêng |

Không có một con số tối đa phù hợp cho mọi ứng dụng. Hãy xác định kích thước bình thường, kích thước tối đa theo nghiệp vụ, số stream đồng thời và lượng bộ nhớ mỗi request có thể sử dụng. Sau đó đặt ngưỡng ở transport, codec và DTO sao cho nhất quán.

### Kiểm tra byte trước khi decode

Với payload dạng byte array, có thể kiểm tra kích thước trước khi chuyển sang object:

~~~java
public final class PayloadLimits {

    private PayloadLimits() {}

    public static void checkDataSize(byte[] data, int maxBytes) {
        if (data == null) {
            throw new IllegalArgumentException("Payload data is required");
        }
        if (data.length > maxBytes) {
            throw new PayloadTooLargeException(maxBytes);
        }
    }
}
~~~

Đây là ví dụ cho một ranh giới đã có byte array. Trong ứng dụng RSocket thực tế, nên cấu hình giới hạn ở transport hoặc tầng nhận payload để từ chối dữ liệu quá lớn trước khi tạo nhiều bản sao trong heap. Không nên chỉ kiểm tra sau khi codec đã decode toàn bộ nội dung.

### Đếm byte UTF-8 thay vì chỉ đếm ký tự

Một String có thể dùng nhiều byte UTF-8 cho mỗi ký tự. Khi hợp đồng quy định giới hạn theo byte, cần đo sau khi mã hóa:

~~~java
int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;
if (utf8Bytes > MAX_NOTE_BYTES) {
    throw new PayloadTooLargeException(MAX_NOTE_BYTES);
}
~~~

Trong code production, cân nhắc cách tránh tạo thêm bản sao byte array chỉ để đo kích thước nếu dữ liệu lớn. Giới hạn ký tự và giới hạn byte có thể cùng tồn tại vì chúng bảo vệ hai khía cạnh khác nhau.

## 5. Giới hạn metadata riêng với data

Metadata thường nhỏ hơn data nhưng có thể ảnh hưởng đến routing, codec và xử lý bảo mật. Metadata cũng cần giới hạn kích thước và kiểm tra định dạng.

Ví dụ, một route metadata có thể chứa tên route. Route nên thuộc tập route đã công bố, có độ dài giới hạn và không được dùng như biểu thức tùy ý để gọi class hoặc method. Tracing metadata nên có kích thước nhỏ và không chứa thông tin nhạy cảm không cần thiết.

Một số nguyên tắc:

- Giới hạn tổng metadata và từng trường metadata.
- Chỉ chấp nhận MIME type đã hỗ trợ.
- Kiểm tra route có nằm trong danh sách endpoint hợp lệ.
- Không ghi access token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm vào log.
- Không tin các giá trị tenant, user hoặc role chỉ vì chúng xuất hiện trong metadata.
- Xác thực thông tin định danh từ cơ chế bảo mật của phiên; sau đó kiểm tra quyền ở từng route.

Metadata là dữ liệu của giao thức và ứng dụng. Nó không tự động trở thành một vùng tin cậy.

## 6. Codec, schema và khả năng tương thích

Codec quyết định cách data được chuyển giữa byte và object. JSON dễ quan sát và tương thích rộng; CBOR hoặc định dạng nhị phân có thể giảm kích thước và chi phí encode/decode trong một số workload. Lựa chọn codec cần dựa trên yêu cầu tương thích, kích thước, tốc độ và công cụ vận hành.

Dù dùng định dạng nào, hai peer cần thống nhất:

- MIME type của data và metadata.
- Tên trường, kiểu dữ liệu và quy tắc bắt buộc.
- Cách xử lý trường không được nhận diện.
- Quy tắc biểu diễn số, thời gian, enum và null.
- Chiến lược versioning khi thay đổi hợp đồng.

Thay đổi schema nên ưu tiên tương thích ngược: thêm trường tùy chọn có default hợp lý thường an toàn hơn đổi kiểu hoặc đổi ý nghĩa trường hiện có. Khi cần thay đổi không tương thích, có thể version route hoặc payload contract, duy trì thời gian chuyển tiếp cho client cũ và mới.

Tránh bật cơ chế polymorphic deserialization quá rộng cho dữ liệu không tin cậy. Codec nên chỉ tạo các kiểu đã được cho phép, tránh để payload điều khiển việc khởi tạo class tùy ý.

## 7. Xử lý lỗi validation trong stream

Trong reactive pipeline, validation có thể phát sinh lỗi trước khi service thực hiện nghiệp vụ. Cần phân biệt lỗi dữ liệu đầu vào với lỗi hệ thống:

- **Invalid argument:** payload sai schema hoặc vi phạm ràng buộc trường.
- **Business rejection:** dữ liệu hợp lệ về cấu trúc nhưng không thỏa điều kiện nghiệp vụ.
- **Unauthorized/forbidden:** peer chưa được xác thực hoặc không có quyền.
- **Payload too large:** vượt giới hạn kích thước.
- **Unexpected error:** lỗi nội bộ, database hoặc hạ tầng.

Không nên trả stack trace, câu SQL hoặc thông tin nội bộ trong error payload. Response lỗi nên có mã ổn định, thông điệp an toàn và correlation ID để tra cứu log phía server.

Với request-stream và request-channel, lỗi có thể kết thúc stream tương ứng. Nếu một phần tử trong stream không hợp lệ, cần chọn rõ chính sách:

- Kết thúc stream và phát lỗi.
- Bỏ qua phần tử lỗi và ghi nhận kết quả xử lý.
- Phát một kiểu kết quả có trạng thái thành công/thất bại cho từng phần tử.

Không nên âm thầm bỏ dữ liệu lỗi nếu nghiệp vụ cần bảo đảm mọi sự kiện đều được xử lý. Với channel hai chiều, cần xác định lỗi ở một hướng có ảnh hưởng đến hướng còn lại và phiên như thế nào.

## 8. Bảo vệ tài nguyên khi nhận dữ liệu realtime

Validation đúng vẫn chưa đủ nếu một peer có thể mở quá nhiều stream hoặc gửi request quá nhanh. Cần kết hợp giới hạn payload với các biện pháp vận hành:

- Giới hạn số kết nối và stream đồng thời theo peer hoặc tenant.
- Đặt timeout cho request và các thao tác nghiệp vụ.
- Dùng backpressure và demand để điều tiết stream.
- Giới hạn concurrency khi gọi database hoặc dịch vụ bên ngoài.
- Giới hạn số phần tử trong collection và độ sâu cấu trúc lồng nhau.
- Giới hạn tốc độ request ở route nhạy cảm.
- Hủy subscription và giải phóng buffer khi stream kết thúc hoặc client disconnect.
- Theo dõi bộ nhớ, queue, số lần từ chối payload và độ trễ.

Backpressure kiểm soát số phần tử được phát theo nhu cầu; nó không tự giới hạn số byte của mỗi phần tử, không thay thế rate limit và không bảo đảm mọi nguồn ngoài đều có thể tạm dừng. Vì thế, cần các giới hạn độc lập ở từng tầng.

## 9. Checklist thiết kế một payload contract

Trước khi công bố route RSocket, hãy trả lời các câu hỏi sau:

| Câu hỏi | Kết quả cần xác định |
|---|---|
| Payload phục vụ thao tác nào? | Route và mục đích rõ ràng |
| DTO có chứa trường nội bộ không? | Chỉ giữ trường cần thiết cho hợp đồng |
| Trường nào bắt buộc? | Constraint và quy tắc null rõ |
| Collection tối đa bao nhiêu phần tử? | Giới hạn cardinality |
| Data và metadata tối đa bao nhiêu byte? | Giới hạn riêng cho từng phần |
| Payload có thể bị fragment không? | Giới hạn payload logic và reassembly |
| Ai được gọi route? | Authentication và authorization |
| Lỗi validation được biểu diễn thế nào? | Mã lỗi ổn định, không lộ chi tiết nội bộ |
| Schema thay đổi ra sao? | Quy tắc versioning và tương thích |
| Khi consumer chậm thì sao? | Demand, buffer, timeout và overflow policy |

## 10. Kết luận

DTO xác định hợp đồng dữ liệu giữa hai peer; giới hạn kích thước bảo vệ bộ nhớ và chi phí xử lý; validation xác nhận payload đúng cấu trúc và đúng quy tắc nghiệp vụ. Data và metadata cần được kiểm soát riêng, còn authorization phải dựa trên danh tính và quyền của phiên.

Trong ứng dụng Java/Spring Boot dùng RSocket, hãy kiểm tra kích thước trước decode, dùng DTO chuyên biệt với Bean Validation, xác thực quy tắc nghiệp vụ trong service và áp dụng giới hạn tài nguyên cho từng route. Kết hợp những biện pháp này với backpressure, timeout, concurrency limit và quan sát hệ thống để các stream realtime hoạt động an toàn khi tải tăng hoặc khi nhận dữ liệu không hợp lệ.

