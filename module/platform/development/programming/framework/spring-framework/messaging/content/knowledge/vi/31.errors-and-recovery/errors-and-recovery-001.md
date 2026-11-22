# Phân loại lỗi kết nối, giao thức, chuyển đổi và nghiệp vụ

## Mục tiêu

Một hệ thống messaging có thể nhận được kết nối thành công nhưng vẫn thất bại khi đọc frame, giải mã payload, tìm handler hoặc thực hiện nghiệp vụ. Mỗi lỗi xuất hiện ở một giai đoạn khác nhau và cần một cách phục hồi khác nhau. Nếu gom tất cả vào một nhánh catch Exception rồi retry, ứng dụng có thể lặp vô hạn một thông điệp sai định dạng, tạo giao dịch trùng hoặc che mất nguyên nhân thật.

Bài này xây dựng cách phân loại lỗi theo bốn nhóm: **kết nối, giao thức, chuyển đổi và nghiệp vụ**. Đồng thời, bài giải thích các kiểu lỗi trong Spring Messaging, vị trí xử lý phù hợp, chính sách retry, idempotency và cách kiểm thử.

Sau bài này, bạn có thể:

- Xác định lỗi xảy ra ở tầng transport, protocol, conversion hay business.
- Phân biệt lỗi tạm thời với lỗi cố định và lỗi có kết quả xử lý chưa xác định.
- Hiểu vai trò của MessagingException, MessageDeliveryException, MessageHandlingException, MessageConversionException và ErrorMessage.
- Dùng @MessageExceptionHandler để ánh xạ ngoại lệ từ message handler thành phản hồi ứng dụng.
- Thiết kế retry có giới hạn, backoff, idempotency và dead-letter handling.
- Ghi log, đo lường và kiểm thử lỗi mà không làm lộ dữ liệu nhạy cảm.

## 1. Nhìn lỗi theo đường đi của một message

Spring Messaging cung cấp mô hình Message, MessageChannel, MessageHandler và các adapter cho giao thức cụ thể. Một message thường đi qua nhiều tầng trước khi hoàn tất:

~~~text
Producer / Client
       |
       v
Transport: TCP, WebSocket, ...
       |
       v
Protocol: RSocket, STOMP, ...
       |
       v
Spring Message: headers + payload
       |
       v
Conversion / argument binding / validation
       |
       v
Destination or route matching
       |
       v
Message handler
       |
       v
Business service / database / external API
       |
       v
Response, broker delivery or acknowledgement
~~~

Một lỗi cần được phân loại theo **điểm phát sinh** và **trạng thái xử lý tại thời điểm lỗi**. Hai câu hỏi này giúp xác định liệu có thể gửi lại hay không.

| Nhóm lỗi | Giai đoạn | Ví dụ điển hình |
|---|---|---|
| Kết nối | Thiết lập hoặc duy trì transport/session | Connection refused, socket reset, TLS handshake failure, timeout khi kết nối |
| Giao thức | Đọc và kiểm tra frame hoặc thông điệp giao thức | Frame sai cấu trúc, phiên bản không tương thích, SETUP bị từ chối, route hoặc command không hợp lệ |
| Chuyển đổi | Chuyển payload/header thành kiểu dữ liệu mà handler yêu cầu | JSON sai, MIME type không khớp, không chuyển được String sang enum, thiếu header bắt buộc |
| Nghiệp vụ | Thực thi quy tắc của ứng dụng sau khi message đã được hiểu | Đơn hàng đã hủy, số dư không đủ, trạng thái không cho phép chuyển tiếp |
| Giao nhận và xử lý | Chuyển message giữa channel, handler, broker và client | Handler lỗi, consumer quá tải, hết thời gian chờ, kết quả gửi chưa được xác nhận |

Bốn nhóm đầu là trọng tâm của bài. Nhóm giao nhận và xử lý là phần cắt ngang: nó có thể xuất hiện cùng lỗi kết nối, giao thức hoặc nghiệp vụ. Ví dụ, một handler ném exception là lỗi xử lý; nguyên nhân gốc bên dưới có thể là database timeout hoặc một quy tắc nghiệp vụ bị vi phạm.

Một nguyên tắc quan trọng: **lỗi xảy ra trước khi handler chạy không thể được sửa bằng cách thêm try/catch trong thân handler**. Cần xử lý tại đúng tầng đã phát sinh lỗi.

## 2. Lỗi kết nối (connection / transport)

### 2.1. Bản chất

Lỗi kết nối xuất hiện khi hai đầu chưa thiết lập được hoặc không còn duy trì được kênh truyền. Những nguyên nhân phổ biến gồm:

- Host hoặc port sai, DNS không phân giải được, máy chủ chưa khởi động.
- Firewall, proxy hoặc load balancer chặn kết nối.
- TCP bị từ chối, reset hoặc đóng bất ngờ.
- TLS certificate không hợp lệ, hostname không khớp hoặc hai bên không thống nhất cấu hình TLS.
- WebSocket handshake thất bại hoặc session bị đóng.
- Keepalive/heartbeat phát hiện peer không còn phản hồi.
- Server quá tải, hết connection slot hoặc tài nguyên mạng.

Ở tầng này, ứng dụng thường chưa nhận được một message hoàn chỉnh để chuyển tới @MessageMapping. Vì vậy, lỗi có thể xuất hiện dưới dạng exception của transport, Reactor hoặc thư viện client; không có một kiểu exception Spring Messaging duy nhất đại diện cho mọi lỗi kết nối.

### 2.2. Phân biệt kết nối transport và thiết lập protocol

Mở được TCP socket chưa có nghĩa là phiên messaging đã sẵn sàng.

Với RSocket, client trước tiên mở transport như TCP hoặc WebSocket, sau đó gửi frame SETUP để thỏa thuận tham số kết nối. Server có thể từ chối SETUP. Trường hợp này transport đã được mở nhưng RSocket session không được thiết lập thành công.

Với STOMP trên WebSocket, WebSocket handshake và STOMP CONNECT là hai giai đoạn khác nhau. WebSocket có thể kết nối thành công nhưng STOMP session vẫn thất bại do xác thực, phiên bản hoặc header của CONNECT.

Phân biệt hai giai đoạn giúp tìm đúng log và đúng cấu hình cần sửa:

| Quan sát | Nên kiểm tra |
|---|---|
| Không mở được socket | DNS, port, firewall, server process, TLS và proxy |
| WebSocket handshake bị từ chối | HTTP endpoint, origin, authentication, TLS và cấu hình upgrade |
| TCP/WebSocket đã mở nhưng RSocket SETUP thất bại | MIME type, tham số SETUP, authentication và khả năng tương thích |
| WebSocket mở nhưng STOMP CONNECT thất bại | STOMP version, login/token, heartbeat và header CONNECT |
| Session đang chạy rồi bị ngắt | Network stability, keepalive, server restart, idle timeout và giới hạn tài nguyên |

### 2.3. Cách phục hồi

Lỗi kết nối có thể tạm thời, nhưng không phải lúc nào cũng vậy. Connection reset có thể hồi phục sau khi mạng ổn định; certificate sai hoặc port sai sẽ tiếp tục thất bại cho đến khi cấu hình được sửa.

Một chính sách phù hợp thường gồm:

1. Dùng connect timeout và request timeout hữu hạn để không giữ tài nguyên vô thời hạn.
2. Thử kết nối lại với exponential backoff và jitter.
3. Giới hạn số lần thử và tổng thời gian phục hồi.
4. Dùng circuit breaker hoặc giới hạn đồng thời nếu dependency liên tục không sẵn sàng.
5. Chỉ gửi lại command khi có idempotency hoặc đã xác định chắc chắn request trước chưa được xử lý.
6. Theo dõi số kết nối đang mở, số lần reconnect, thời gian thiết lập session và tỷ lệ disconnect.

RSocket có cơ chế session resumption ở cấp protocol để hỗ trợ mất kết nối. Cơ chế này cần được cấu hình và duy trì trạng thái phù hợp; không nên giả định mọi RSocket client, transport hoặc cấu hình Spring đều tự động resume. Khi dùng STOMP/WebSocket, reconnect và resubscribe cũng cần được thiết kế ở client; sau khi kết nối lại, subscription cũ có thể phải được tạo lại.

### 2.4. Kết quả request có thể chưa xác định

Giả sử client gửi lệnh tạo đơn hàng. Server đã ghi đơn hàng vào database nhưng kết nối bị đứt trước khi response về client. Client chỉ nhìn thấy timeout hoặc disconnect, nhưng đơn hàng có thể đã được tạo.

Đây là **unknown outcome** (không biết kết quả), không đồng nghĩa với việc server chưa thực hiện. Gửi lại ngay có thể tạo đơn hàng thứ hai. Hãy dùng messageId hoặc idempotency key để server nhận diện request lặp, rồi trả lại kết quả đã lưu hoặc từ chối bản sao theo hợp đồng ứng dụng.

## 3. Lỗi giao thức (protocol)

### 3.1. Bản chất

Lỗi giao thức xuất hiện khi hai bên không thể hiểu hoặc không chấp nhận cấu trúc hay quy tắc của thông điệp trên wire. Ví dụ:

- Frame bị thiếu phần bắt buộc, sai độ dài hoặc sai cấu trúc.
- Client và server không thống nhất phiên bản protocol.
- STOMP command hoặc header không hợp lệ.
- RSocket SETUP bị từ chối hoặc frame không phù hợp với trạng thái session.
- Metadata hoặc MIME type không được hỗ trợ theo hợp đồng giao thức.
- Destination/route không tồn tại hoặc không được phép dùng theo quy tắc routing.
- Client sử dụng interaction model hoặc frame type mà peer không hỗ trợ.

Không phải mọi lỗi route đều là lỗi protocol. Nếu frame hợp lệ nhưng route không có handler, đó có thể là lỗi định tuyến của ứng dụng. Nếu frame sai cấu trúc hoặc không tuân theo protocol, lỗi thuộc tầng giao thức. Cần dựa vào vị trí lỗi và loại phản hồi của adapter để phân biệt.

### 3.2. Đặc điểm của lỗi protocol

Lỗi protocol thường không tự biến mất khi gửi lại cùng một frame. Nó thường chỉ hết khi một bên sửa cấu hình hoặc dữ liệu:

- Sai version cần thống nhất version hoặc triển khai tương thích ngược.
- Sai frame cần sửa producer/client.
- MIME type không được hỗ trợ cần bổ sung codec hoặc cập nhật hợp đồng.
- SETUP bị từ chối cần sửa tham số, authentication hoặc policy.
- Destination sai cần sửa route hoặc cấu hình mapping.

Với RSocket, lỗi được truyền qua cơ chế ERROR của protocol; mã lỗi và phạm vi lỗi cho biết vấn đề liên quan request hay connection. Với STOMP, lỗi ở tầng sub-protocol có thể được biểu diễn bằng STOMP ERROR frame hoặc dẫn đến đóng session tùy tình huống và adapter.

Spring WebSocket cung cấp **StompSubProtocolErrorHandler** để tùy chỉnh xử lý lỗi ở tầng STOMP sub-protocol. Đây là điểm xử lý protocol của adapter, khác với @MessageExceptionHandler trong controller. Không nên dùng handler nghiệp vụ để xử lý frame sai định dạng khi controller chưa được gọi.

### 3.3. Cách phục hồi

- Ghi lại protocol, phiên bản, command/frame type và trạng thái session tại thời điểm lỗi.
- Kiểm tra hợp đồng giữa producer và consumer: destination, header bắt buộc, MIME type, metadata và version.
- Đóng hoặc loại bỏ session không còn trạng thái hợp lệ nếu protocol yêu cầu.
- Cập nhật client/server theo chiến lược tương thích ngược.
- Không retry vô hạn một frame sai cấu trúc hoặc một cấu hình sai.
- Nếu cần hỗ trợ nhiều phiên bản, kiểm thử tương thích theo ma trận client/server thay vì chỉ kiểm tra hai phiên bản mới nhất.

Lưu ý: lỗi xác thực trong SETUP hoặc STOMP CONNECT xảy ra ở giai đoạn thiết lập session. Dù thông báo có thể xuất hiện dưới dạng protocol rejection, nguyên nhân gốc vẫn có thể là credential hết hạn hoặc policy từ chối. Phân loại theo cả tầng phát sinh lẫn nguyên nhân để đội phụ trách sửa đúng chỗ.

## 4. Lỗi chuyển đổi (conversion / binding)

### 4.1. Bản chất

Lỗi chuyển đổi xuất hiện khi message đã đến được tầng Spring nhưng payload hoặc header không thể chuyển thành kiểu dữ liệu mà handler yêu cầu.

Ví dụ:

- Client gửi JSON thiếu dấu ngoặc hoặc có giá trị không hợp lệ.
- JSON gửi trường quantity là chuỗi trong khi DTO yêu cầu số.
- Client gửi MIME type khác với codec mà server hỗ trợ.
- Enum hoặc ngày tháng có định dạng khác hợp đồng.
- Header bắt buộc như tenantId bị thiếu.
- Giá trị header có tồn tại nhưng không thể convert sang kiểu tham số.
- Payload giải mã được nhưng không vượt qua validation.

Spring Messaging có các exception hữu ích để nhận diện nhóm lỗi này:

- **MessageConversionException**: quá trình chuyển payload/message thất bại.
- **MethodArgumentResolutionException**: Spring không thể phân giải hoặc bind một tham số của message handler.
- **MethodArgumentNotValidException**: dữ liệu không vượt qua bước validation tham số, khi validation được kích hoạt.
- **MessageHandlingException**: lỗi phát sinh trong quá trình xử lý message; có thể bao bọc nguyên nhân sâu hơn.

Các kiểu exception trên giúp phân loại nhanh nhưng không thay thế việc đọc cause chain. Một exception có thể được bọc nhiều lớp trước khi tới log hoặc caller.

### 4.2. Phân biệt conversion và business validation

Hai loại lỗi thường bị nhầm lẫn:

| Trường hợp | Phân loại |
|---|---|
| JSON không parse được | Conversion |
| quantity là chuỗi "many" trong khi DTO yêu cầu int | Conversion hoặc type binding |
| quantity là số âm nhưng đã parse thành int | Validation hoặc nghiệp vụ, tùy quy tắc |
| tenantId bị thiếu trong header bắt buộc | Argument binding |
| tenantId tồn tại nhưng người gửi không có quyền truy cập tenant đó | Authorization/business policy |
| Đơn hàng hợp lệ về cấu trúc nhưng đã ở trạng thái không cho phép hủy | Business |

Conversion trả lời câu hỏi: "Dữ liệu có thể được biểu diễn thành kiểu mà handler cần không?" Business trả lời: "Dữ liệu hợp lệ về kiểu rồi, nhưng hành động này có được phép hoặc có thể thực hiện theo quy tắc domain không?"

### 4.3. Cách phục hồi

- Kiểm tra MIME type/content type và codec ở hai phía.
- Dùng schema hoặc DTO rõ ràng, tránh thay đổi kiểu field đột ngột.
- Trả lỗi đầu vào có mã ổn định và chỉ ra field sai nếu có thể.
- Dùng validation trước khi gọi service nghiệp vụ.
- Không retry cùng một payload sai định dạng: dữ liệu không thay đổi thì kết quả cũng không đổi.
- Với hệ thống broker, chuyển message không thể xử lý vào dead-letter queue hoặc vùng quarantine theo chính sách của broker/adapter, kèm thông tin lỗi và message gốc được bảo vệ.
- Giữ lại mẫu dữ liệu cần điều tra theo chính sách bảo mật; không ghi token hoặc payload nhạy cảm vào log.

Nếu lỗi do producer và consumer không đồng bộ schema, cần sửa hợp đồng hoặc triển khai chiến lược schema evolution. Không nên tự động bỏ qua field bắt buộc hay thay mọi giá trị sai thành default vì điều đó có thể tạo dữ liệu nghiệp vụ sai mà không phát hiện.

## 5. Lỗi nghiệp vụ (business / domain)

### 5.1. Bản chất

Lỗi nghiệp vụ xuất hiện sau khi message đã được nhận diện, giải mã và chuyển thành đối tượng ứng dụng. Dữ liệu có thể hoàn toàn hợp lệ về cú pháp, nhưng hành động không được phép theo trạng thái hoặc chính sách domain.

Ví dụ:

- Không đủ số dư để thanh toán.
- Đơn hàng đã được hủy nên không thể tiếp tục giao.
- Người dùng không có quyền thực hiện thao tác.
- Sản phẩm hết hàng tại thời điểm xử lý.
- Một yêu cầu trùng với trạng thái hiện tại.
- Trạng thái chuyển đổi không hợp lệ theo state machine.

Cần phân biệt lỗi nghiệp vụ được dự đoán trước với lỗi hệ thống bất ngờ. "Không đủ số dư" có thể là kết quả hợp lệ của nghiệp vụ; database connection reset là lỗi hạ tầng. Không nên biến mọi business rejection thành exception hệ thống hoặc log ở mức ERROR như sự cố vận hành.

### 5.2. Chọn cách biểu diễn lỗi

Có hai lựa chọn phổ biến:

**Kết quả nghiệp vụ có trạng thái từ chối**

Dùng khi từ chối là một kết quả bình thường mà client cần xử lý:

~~~java
public record PaymentResult(
        boolean accepted,
        String code,
        String message) {
}

public PaymentResult authorize(PaymentCommand command) {
    if (!accountHasEnoughBalance(command)) {
        return new PaymentResult(
                false,
                "INSUFFICIENT_BALANCE",
                "The account does not have enough balance");
    }

    return new PaymentResult(true, "APPROVED", "Payment approved");
}
~~~

Đây là một phương thức nghiệp vụ minh họa, giả định các hàm kiểm tra tài khoản đã được triển khai. Client đọc accepted và code để quyết định cách hiển thị hoặc yêu cầu thao tác khác.

**Exception nghiệp vụ được ánh xạ thành phản hồi**

Dùng khi luồng xử lý đang sử dụng exception cho trường hợp từ chối và adapter hỗ trợ message exception handler:

~~~java
public record MessagingError(
        String code,
        String message) {
}

@Controller
public class PaymentMessageController {

    @MessageMapping("payments.authorize")
    public Mono<PaymentResult> authorize(
            @Payload PaymentCommand command) {
        return paymentService.authorize(command);
    }

    @MessageExceptionHandler(PaymentRejectedException.class)
    public MessagingError handlePaymentRejected(
            PaymentRejectedException exception) {
        return new MessagingError(
                "PAYMENT_REJECTED",
                "The payment cannot be approved");
    }
}
~~~

Đây là ví dụ cấu trúc controller; PaymentCommand, PaymentResult, PaymentRejectedException và paymentService là kiểu/bean thuộc ứng dụng. Thông báo trả về được cố ý giới hạn ở nội dung an toàn cho client. Không gửi stack trace, SQL, tên bảng, thông tin credential hoặc chi tiết nội bộ trong error response.

**@MessageExceptionHandler** xử lý exception phát sinh từ các phương thức @MessageMapping trong phạm vi controller tương ứng. Có thể tổ chức handler dùng chung bằng @ControllerAdvice ở những adapter hỗ trợ. Cơ chế này không bắt được lỗi DNS, TLS, socket, frame parse hoặc mọi lỗi xảy ra trước khi message handler được gọi. Cách adapter chuyển kết quả thành response cụ thể phụ thuộc giao thức đang dùng.

### 5.3. Có nên retry lỗi nghiệp vụ?

Thông thường không retry các kết quả từ chối xác định như insufficient balance, invalid state hoặc permission denied. Retry cùng một command trong cùng điều kiện chỉ tạo thêm tải và lặp lại cùng kết quả.

Một số lỗi phụ thuộc trạng thái có thể tạm thời, ví dụ lock contention hoặc dependency nghiệp vụ tạm không sẵn sàng. Khi đó phải xác định rõ điều kiện retry, thời hạn, số lần thử và tính idempotent. Không suy luận rằng mọi exception từ service nghiệp vụ đều là transient.

## 6. Exception và ErrorMessage trong Spring Messaging

### 6.1. MessagingException

**MessagingException** là lớp cơ sở cho các lỗi liên quan tới messaging trong Spring. Khi có message liên quan, exception có thể giữ tham chiếu tới message thất bại thông qua getFailedMessage().

Một số lớp con đáng chú ý:

| Exception | Ý nghĩa |
|---|---|
| MessagingException | Lỗi chung liên quan tới messaging |
| MessageDeliveryException | Lỗi trong quá trình giao message |
| MessageHandlingException | Lỗi trong quá trình xử lý message |
| MessageConversionException | Không chuyển đổi được message/payload |
| MethodArgumentResolutionException | Không phân giải được tham số của handler |
| DestinationResolutionException | Không phân giải được destination |

Không nên phân loại chỉ dựa trên tên exception. Ví dụ, MessageHandlingException có thể bao bọc một database timeout, lỗi nghiệp vụ hoặc bug trong handler. Luôn kiểm tra cause, failed message và giai đoạn thực thi.

### 6.2. ErrorMessage

**ErrorMessage** trong package org.springframework.messaging.support là một GenericMessage có payload kiểu Throwable. Payload thường là MessagingException; nếu có thể, nó giữ failedMessage. ErrorMessage cũng có thể giữ originalMessage để đối chiếu message tại thời điểm tạo lỗi với message đã được biến đổi trước khi thất bại.

Điều này hữu ích trong một pipeline có error handling flow: hệ thống có thể chuyển exception và message liên quan sang một thành phần xử lý lỗi, ghi nhận hoặc đưa vào hàng đợi điều tra.

Tuy nhiên, ErrorMessage tự nó không tạo ra một error channel toàn cục cho mọi transport. Cách tạo, định tuyến và tiêu thụ ErrorMessage phụ thuộc hạ tầng messaging đang dùng. Spring Integration có mô hình error channel riêng; không nên nhầm tính năng của Spring Integration với hợp đồng cơ bản của Spring Framework Messaging.

## 7. Chọn chiến lược phục hồi theo loại lỗi

Bảng sau là điểm bắt đầu để xây dựng policy. Thực tế cần kết hợp loại lỗi với khả năng lặp an toàn của command và trạng thái giao nhận.

| Loại lỗi | Có thể tạm thời? | Hành động ưu tiên | Retry cùng message? |
|---|---|---|---|
| Kết nối | Có, ví dụ socket reset hoặc server restart | Reconnect có backoff, kiểm tra health và session | Chỉ khi request có thể lặp an toàn hoặc biết chắc chưa xử lý |
| Giao thức | Thường không với cùng frame/cấu hình | Sửa version, frame, route, metadata hoặc cấu hình | Không retry nguyên trạng |
| Chuyển đổi | Thường không với cùng payload/schema | Sửa codec/schema/dữ liệu; quarantine hoặc dead-letter | Không retry nguyên trạng |
| Nghiệp vụ | Thường là từ chối xác định; đôi khi phụ thuộc trạng thái | Trả lỗi domain có mã ổn định hoặc chờ điều kiện được thay đổi | Chỉ khi có quy tắc transient rõ ràng |
| Giao nhận/timeout | Có thể; kết quả có thể chưa xác định | Kiểm tra trạng thái, deduplicate và xác nhận delivery | Chỉ với idempotency hoặc cơ chế xác định trạng thái |

### 7.1. Exponential backoff và jitter

Khi nhiều client cùng retry ngay sau một lần server mất kết nối, tất cả có thể quay lại cùng lúc và tạo một đợt tải lớn. Exponential backoff tăng khoảng chờ theo số lần thử; jitter thêm độ lệch ngẫu nhiên để phân tán các lần retry.

Một policy cần xác định:

- Số lần retry tối đa.
- Thời gian chờ ban đầu và mức tối đa.
- Jitter.
- Tổng deadline của request.
- Nhóm exception được phép retry.
- Điều kiện dừng ngay khi lỗi là permanent.
- Số lần retry tối đa ở từng tầng để tránh retry chồng lặp.

Không nên để client retry 5 lần, gateway retry 5 lần và broker retry thêm 5 lần mà không có ngân sách chung. Một request có thể bị nhân thành rất nhiều lần xử lý.

### 7.2. Ví dụ retry có lọc lỗi với Reactor

RSocketRequester trả về các reactive type như Mono hoặc Flux. Reactor cung cấp retryWhen để retry theo policy. Ví dụ sau chỉ retry khi hàm phân loại của ứng dụng xác định lỗi là transient ở tầng transport:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<OrderResult> response = requester
        .route("orders.create")
        .data(command)
        .retrieveMono(OrderResult.class)
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                        .maxBackoff(Duration.ofSeconds(2))
                        .filter(this::isKnownTransientTransportFailure));
~~~

Đây là đoạn code trong một bean/service đã có requester, command và hàm isKnownTransientTransportFailure. Hàm phân loại phải kiểm tra cả cause chain vì exception của transport có thể bị bọc bởi các lớp ở phía trên. Nó chỉ nên nhận diện những lỗi đã được xác định là có thể phục hồi; không trả true cho mọi RuntimeException hoặc mọi MessagingException.

Retry operator đăng ký lại publisher. Điều đó không tự chứng minh request trước chưa đến server, cũng không bảo đảm luôn tạo được connection mới. Vòng đời connection, reconnect và session resumption phụ thuộc cấu hình client, connector và transport. Với command có side effect, hãy bổ sung idempotency trước khi bật retry.

### 7.3. Timeout không đồng nghĩa với rollback

Timeout có thể xảy ra ở nhiều vị trí:

- Connect timeout: không thiết lập được transport/session trong thời gian cho phép.
- Request timeout: không nhận được response trong deadline.
- Processing timeout: handler hoặc dependency xử lý quá lâu.
- Idle timeout: session không có hoạt động trong một khoảng thời gian.
- Broker/consumer timeout: message chưa được xác nhận hoặc consumer không phản hồi.

Khi client hết thời gian chờ, server có thể đã hoàn tất nghiệp vụ. Việc hủy subscription hoặc đóng connection không tự động rollback một transaction đã commit. Vì vậy, timeout cần đi cùng idempotency key, trạng thái xử lý và khả năng truy vấn kết quả khi client không biết request đã thành công hay chưa.

## 8. Idempotency, duplicate và dead-letter handling

### 8.1. Vì sao cần idempotency?

Trong hệ thống phân tán, một message có thể được gửi lại khi producer không nhận được xác nhận, consumer bị restart hoặc broker redeliver sau timeout. Đây là hành vi có thể xảy ra tùy delivery semantics của broker và adapter.

Nếu handler thực hiện thao tác không idempotent, ví dụ trừ tiền hoặc tạo đơn hàng, xử lý lặp có thể gây side effect trùng.

Một cách thiết kế phổ biến:

1. Producer tạo idempotency key duy nhất cho một ý định nghiệp vụ.
2. Consumer kiểm tra key trong kho lưu trữ có unique constraint.
3. Nếu key đã hoàn tất, trả lại kết quả đã lưu.
4. Nếu chưa có, thực hiện nghiệp vụ và lưu kết quả cùng trạng thái xử lý trong một transaction phù hợp.
5. Nếu có lỗi, xác định trạng thái xử lý để lần gửi sau không tạo side effect trùng.

Không chỉ dựa vào cache trong bộ nhớ vì cache có thể mất khi ứng dụng restart hoặc khi message được xử lý bởi instance khác.

### 8.2. Retry queue và dead-letter queue

Với broker hỗ trợ, có thể tách message cần thử lại khỏi message không thể xử lý:

- Retry queue/topic: message được chờ một khoảng thời gian trước khi xử lý lại.
- Dead-letter queue (DLQ): message đã vượt quá số lần thử hoặc bị xác định không thể xử lý tự động.
- Quarantine: vùng lưu message cần điều tra thủ công hoặc sửa dữ liệu trước khi phát lại.

Spring Framework Messaging cung cấp abstraction Message và exception, nhưng không áp đặt một cơ chế DLQ, retry queue hay acknowledgement chung cho tất cả transport. Các khả năng đó thuộc broker và adapter cụ thể, ví dụ Spring for Apache Kafka, Spring AMQP hoặc Spring Integration.

Khi đưa message vào DLQ, nên lưu messageId, correlationId, destination/route, loại lỗi, số lần thử, thời điểm và phiên bản schema. Payload gốc có thể chứa dữ liệu nhạy cảm; cần giới hạn quyền truy cập và thời gian lưu.

### 8.3. Phân biệt gửi thành công và xử lý thành công

Một lệnh send được chấp nhận bởi local MessageChannel không tự chứng minh consumer từ xa đã hoàn tất nghiệp vụ. Tương tự, broker receipt hoặc protocol acknowledgement có thể xác nhận một giai đoạn giao nhận nhưng chưa chắc chứng minh transaction nghiệp vụ đã commit.

Nếu client cần biết nghiệp vụ đã hoàn tất, hãy thiết kế response, receipt hoặc trạng thái có thể truy vấn theo idempotency key. Với RSocket Fire-and-Forget, client không nhận response nghiệp vụ như Request-Response; hãy chọn interaction model phù hợp nếu cần xác nhận kết quả.

## 9. Quan sát và ghi nhận lỗi

Một log lỗi hữu ích cần đủ thông tin để tái dựng luồng xử lý, nhưng không ghi toàn bộ payload một cách vô điều kiện.

Các trường nên cân nhắc:

- errorCategory: CONNECTION, PROTOCOL, CONVERSION, BUSINESS hoặc DELIVERY.
- exceptionClass và rootCause.
- messageId và correlationId.
- destination hoặc RSocket route / STOMP destination.
- sessionId hoặc connectionId nếu adapter cung cấp.
- protocol và protocolVersion.
- retryAttempt, maxAttempts và thời gian chờ.
- processingStage và elapsedTime.
- deliveryState nếu biết: chưa nhận, đã nhận, đã xử lý, đã xác nhận hoặc chưa rõ.

Dùng metric có cardinality thấp: số lỗi theo category, tỷ lệ reconnect, timeout, conversion failure, business rejection, retry exhaustion và DLQ count. Không dùng messageId, userId hoặc sessionId làm label metric có số lượng không giới hạn.

Distributed tracing giúp nối producer, gateway, broker và consumer. Giữ correlationId xuyên suốt luồng message, nhưng không xem correlationId là thông tin xác thực.

Không ghi access token, session cookie, mật khẩu, dữ liệu thanh toán hoặc payload cá nhân vào log. Nếu cần lưu payload để điều tra, phải có chính sách che dữ liệu, phân quyền và retention rõ ràng.

## 10. Kiểm thử lỗi và phục hồi

Một bài kiểm thử messaging chỉ kiểm tra đường thành công là chưa đủ. Nên có kiểm thử riêng cho từng tầng:

| Tình huống | Điều cần xác minh |
|---|---|
| Server không lắng nghe tại port | Client nhận lỗi kết nối; retry có giới hạn và log đúng category |
| Socket bị ngắt khi request đang chạy | Client nhận trạng thái không chắc chắn; command không tạo side effect trùng khi retry |
| RSocket SETUP hoặc STOMP CONNECT bị từ chối | Lỗi được phân loại là setup/protocol/authentication theo nguyên nhân |
| Frame hoặc header protocol sai | Handler nghiệp vụ không được gọi; không retry vô hạn frame lỗi |
| JSON sai hoặc MIME type không hỗ trợ | Conversion failure được ghi nhận; message được xử lý theo chính sách reject/quarantine |
| Thiếu header bắt buộc hoặc sai kiểu | Argument binding thất bại rõ ràng; không gọi business service |
| Business rule từ chối | Client nhận mã lỗi nghiệp vụ ổn định; không retry tự động |
| Database timeout trong handler | Root cause được giữ; retry chỉ khi thao tác và transaction an toàn |
| Consumer xử lý lặp cùng messageId | Side effect chỉ xảy ra một lần theo idempotency contract |
| Response chậm hơn request deadline | Timeout không làm client kết luận sai rằng nghiệp vụ chắc chắn chưa chạy |
| Stream bị hủy hoặc mất demand | Resource được giải phóng và hành vi cancellation/backpressure đúng hợp đồng |

Có thể kiểm thử bằng mock server, test transport cục bộ, broker test container hoặc fault injection. Hãy kiểm tra cả log/metric, response của client, số lần gọi service và dữ liệu đã commit. Không chỉ assert rằng một exception được ném ra.

## 11. Quy trình chẩn đoán thực tế

Khi nhận được một lỗi messaging, có thể đi theo thứ tự sau:

1. **Message có tới được transport không?** Kiểm tra DNS, socket, TLS, handshake và session.
2. **Protocol có chấp nhận message không?** Kiểm tra frame, version, command, route/destination, SETUP/CONNECT và protocol error code.
3. **Spring có tạo được Message và bind được tham số không?** Kiểm tra converter, MIME type, header, DTO, validation và argument resolver.
4. **Handler có được gọi không?** Nếu chưa, tìm lỗi routing hoặc binding. Nếu đã, kiểm tra exception và root cause trong service.
5. **Nghiệp vụ đã commit chưa?** Kiểm tra transaction, messageId, idempotency record và kết quả có thể truy vấn.
6. **Client hoặc broker đã nhận xác nhận nào?** Phân biệt local send, broker receipt, protocol response và business completion.
7. **Có nên retry không?** Chỉ quyết định sau khi biết lỗi transient/permanent và trạng thái side effect.

Quy trình này tránh việc sửa sai tầng. Ví dụ, nếu JSON parse thất bại trước khi handler chạy, thêm retry cho business service không giải quyết được. Nếu client timeout sau khi database đã commit, retry không có idempotency có thể gây giao dịch trùng.

## 12. Ghi nhớ

- **Connection error** nói rằng transport hoặc session không thiết lập/duy trì được. Phục hồi bằng reconnect có giới hạn; kiểm tra trạng thái request trước khi gửi lại.
- **Protocol error** nói rằng hai phía không thống nhất cách diễn giải frame hoặc quy tắc giao thức. Sửa hợp đồng, version hoặc cấu hình; không retry nguyên trạng.
- **Conversion error** nói rằng payload/header không thể bind thành kiểu dữ liệu yêu cầu. Sửa codec/schema/dữ liệu; message lỗi cố định cần reject hoặc quarantine.
- **Business error** nói rằng request đã được hiểu nhưng domain không chấp nhận hành động. Trả kết quả nghiệp vụ có mã ổn định hoặc ánh xạ exception thành response an toàn.
- **MessagingException** là abstraction lỗi messaging; MessageDeliveryException, MessageHandlingException và các exception chuyên biệt giúp xác định giai đoạn, nhưng cần đọc root cause.
- **ErrorMessage** mang Throwable cùng message liên quan khi một error handling flow sử dụng nó; nó không tự tạo error channel toàn cục.
- **Retry cần idempotency** vì timeout hoặc disconnect không chứng minh rằng side effect chưa xảy ra.
- **Spring Messaging không định nghĩa một chính sách retry/DLQ chung**; delivery guarantee và cơ chế acknowledgement phụ thuộc transport, broker và adapter.

Phân loại đúng lỗi giúp chọn đúng điểm xử lý, giảm retry vô ích, tránh xử lý trùng và giữ được bằng chứng cần thiết để điều tra sự cố.

## Tài liệu tham khảo

- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html)
- [Annotated Controllers và @MessageExceptionHandler](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [MessagingException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessagingException.html)
- [MessageDeliveryException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageDeliveryException.html)
- [MessageHandlingException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHandlingException.html)
- [MessageConversionException — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/converter/MessageConversionException.html)
- [ErrorMessage — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ErrorMessage.html)
- [MessageExceptionHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html)
- [StompSubProtocolErrorHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
