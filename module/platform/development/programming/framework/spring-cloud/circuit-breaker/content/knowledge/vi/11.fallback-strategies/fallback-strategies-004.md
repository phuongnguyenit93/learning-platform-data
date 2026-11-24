# Từ chối thao tác quan trọng thay vì tạo kết quả thành công giả

Fallback giúp ứng dụng tiếp tục phản hồi khi dịch vụ phụ thuộc lỗi hoặc circuit breaker đang `OPEN`. Tuy nhiên, không phải yêu cầu nào cũng có thể thay bằng một giá trị mặc định. Với thao tác làm thay đổi trạng thái nghiệp vụ như thanh toán, tạo đơn hàng, giữ tồn kho, chuyển tiền hoặc cấp quyền, trả về một kết quả thành công giả có thể khiến người dùng và hệ thống phía sau tin rằng thao tác đã hoàn tất dù chưa có bằng chứng.

Trong các trường hợp này, fallback an toàn thường là từ chối thao tác có kiểm soát, trả lỗi tạm thời hoặc thông báo kết quả chưa xác định để caller tra cứu bằng mã giao dịch. Circuit breaker bảo vệ dependency bằng cách ngăn lời gọi mới khi mạch mở; nó không tự hoàn tất nghiệp vụ, không lưu yêu cầu để chạy lại và không đảm bảo rollback một thao tác đã tới hệ thống phụ thuộc.

## 1. Phân biệt thao tác đọc và thao tác ghi

Một giá trị dự phòng có thể hữu ích cho truy vấn đọc. Ví dụ, khi dịch vụ danh mục không phản hồi, ứng dụng có thể trả dữ liệu cache cũ kèm thông tin thời điểm cập nhật. Với thao tác ghi quan trọng, trả về dữ liệu mặc định hoặc giả lập trạng thái thành công có thể làm sai lệch trạng thái nghiệp vụ.

| Loại thao tác | Ví dụ | Fallback thường phù hợp |
| --- | --- | --- |
| Đọc có thể chấp nhận dữ liệu cũ | Xem tên sản phẩm, nội dung trang, cấu hình không nhạy thời gian | Cache có giới hạn tuổi, kèm dấu hiệu dữ liệu cũ |
| Đọc cần dữ liệu mới nhất | Kiểm tra số dư hiện tại, kiểm tra tồn kho trước khi xác nhận | Báo không thể xác minh hoặc yêu cầu thử lại sau |
| Ghi tạo trạng thái nghiệp vụ | Thanh toán, tạo đơn, giữ hàng, chuyển tiền | Từ chối tạm thời hoặc báo trạng thái chưa xác định; không tạo thành công giả |
| Ghi có thể xếp hàng theo hợp đồng nghiệp vụ | Gửi yêu cầu xử lý nền, tạo tác vụ xuất báo cáo | Chỉ xác nhận đã tiếp nhận sau khi lưu bền vững vào hàng đợi hoặc outbox |

Quyết định fallback phải dựa trên ý nghĩa của thao tác và hợp đồng API. Một kết quả `true`, một đối tượng đơn hàng giả, số tiền bằng 0 hoặc `Optional.empty()` không thể thay thế xác nhận từ hệ thống có thẩm quyền.

## 2. Vì sao thành công giả gây sai lệch dữ liệu?

Giả sử Order Service gọi Payment Service để ủy quyền thanh toán. Payment Service không phản hồi và circuit breaker mở. Nếu fallback trả về `PaymentResult.approved()`, Order Service có thể:

- Chuyển đơn hàng sang trạng thái đã thanh toán.
- Giảm tồn kho hoặc phát lệnh giao hàng.
- Gửi email xác nhận thanh toán.
- Báo cáo doanh thu ghi nhận một giao dịch chưa được xác nhận.

Các bước tiếp theo có thể không thể tự sửa bằng cách thử lại request ban đầu. Dữ liệu ở nhiều dịch vụ đã lệch nhau, trong khi người dùng nhìn thấy thông báo thành công.

Với command quan trọng, cần bảo toàn sự thật của trạng thái: chỉ đánh dấu hoàn tất khi nhận được xác nhận hợp lệ hoặc khi hệ thống đã lưu bền vững một yêu cầu xử lý bất đồng bộ theo hợp đồng rõ ràng. Khi không thể xác nhận, trả lỗi hoặc trạng thái chờ xác minh thay vì đoán kết quả.

## 3. Phân biệt circuit breaker OPEN với timeout sau khi đã gọi

Hai tình huống thường dẫn đến fallback nhưng mang ý nghĩa khác nhau:

| Tình huống | Supplier có chạy không? | Điều có thể kết luận | Cách phản hồi an toàn |
| --- | --- | --- | --- |
| Breaker đang `OPEN` | Không | Lần gọi hiện tại bị chặn trước khi gửi request qua supplier | Báo dependency tạm thời không khả dụng; yêu cầu thử lại theo chính sách |
| Supplier chạy và nhận lỗi từ chối rõ ràng | Có | Dependency đã trả một kết quả lỗi cụ thể | Ánh xạ lỗi theo hợp đồng nghiệp vụ, không tự đổi thành thành công |
| Supplier chạy nhưng timeout hoặc mất kết nối | Có | Không biết chắc dependency đã xử lý command hay chưa | Báo kết quả chưa xác định và cho phép tra cứu bằng operation ID/idempotency key |
| Breaker ở `HALF_OPEN` và cho phép lời gọi thử | Có | Đây là một request thật được phép thử dependency | Chỉ xác nhận theo kết quả thực tế; bảo vệ command bằng idempotency |

Khi breaker `OPEN`, `CallNotPermittedException` cho biết supplier không được chạy trong lần gọi đó. Ngược lại, timeout sau khi gửi request không chứng minh thao tác chưa được thực hiện. Ví dụ, Payment Service có thể đã ghi nhận thanh toán nhưng phản hồi bị mất trên mạng. Nếu caller gửi lại một command mới, khách hàng có nguy cơ bị tính tiền hai lần.

Không gộp mọi exception thành cùng một thông báo “chưa xử lý”. Hãy phân biệt lỗi từ chối chắc chắn, dependency không khả dụng trước khi gửi request, và kết quả không xác định sau khi request có thể đã tới nơi.

## 4. Fallback cho command quan trọng nên từ chối rõ ràng

Với Spring Cloud CircuitBreaker, fallback của `run(...)` có thể ném một exception nghiệp vụ thể hiện dependency không khả dụng. Ví dụ dưới đây bảo vệ thao tác ủy quyền thanh toán:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final PaymentClient paymentClient;

    public PaymentService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            PaymentClient paymentClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.paymentClient = paymentClient;
    }

    public PaymentAuthorization authorize(PaymentCommand command) {
        return circuitBreakerFactory.create("paymentAuthorization").run(
            () -> paymentClient.authorize(
                command,
                command.idempotencyKey()
            ),
            cause -> {
                if (cause instanceof CallNotPermittedException) {
                    throw new PaymentDependencyUnavailableException(
                        "Payment service is temporarily unavailable", cause
                    );
                }

                if (isTimeout(cause)) {
                    throw new PaymentOutcomeUnknownException(
                        command.operationId(), cause
                    );
                }

                throw new PaymentDependencyUnavailableException(
                    "Payment authorization could not be confirmed", cause
                );
            }
        );
    }

    private boolean isTimeout(Throwable cause) {
        for (Throwable current = cause; current != null; current = current.getCause()) {
            if (current instanceof java.util.concurrent.TimeoutException
                    || current instanceof java.net.SocketTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
```

Đây là ví dụ minh họa; các exception nghiệp vụ cần được định nghĩa trong ứng dụng. `CallNotPermittedException` được xử lý như trường hợp breaker chặn trước khi supplier chạy. Timeout được tách riêng vì kết quả của command có thể chưa xác định. Những lỗi còn lại được báo là không thể xác nhận ủy quyền; trong triển khai thật, nên phân loại thêm các lỗi từ chối rõ ràng theo hợp đồng của Payment Service.

Fallback không trả về `PaymentAuthorization` giả. Vì fallback ném exception, caller không thể nhầm một thao tác chưa xác nhận thành thanh toán thành công.

## 5. Ánh xạ lỗi thành HTTP response có ý nghĩa

Lớp API nên chuyển exception nghiệp vụ thành HTTP status phù hợp và nội dung đủ để caller quyết định bước tiếp theo. Ví dụ với Spring MVC trên Spring Framework 6:

```java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class PaymentExceptionHandler {

    @ExceptionHandler(PaymentDependencyUnavailableException.class)
    ResponseEntity<ProblemDetail> dependencyUnavailable(
            PaymentDependencyUnavailableException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Payment authorization is temporarily unavailable. No success was confirmed."
        );
        problem.setTitle("Payment service unavailable");
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }

    @ExceptionHandler(PaymentOutcomeUnknownException.class)
    ResponseEntity<ProblemDetail> outcomeUnknown(
            PaymentOutcomeUnknownException ex) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.GATEWAY_TIMEOUT,
            "The payment result could not be confirmed. Check the operation status before retrying."
        );
        problem.setTitle("Payment outcome unknown");
        problem.setProperty("operationId", ex.operationId());
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT).body(problem);
    }
}
```

`503 Service Unavailable` phù hợp khi breaker từ chối lời gọi vì dependency đang không khả dụng. `504 Gateway Timeout` có thể phù hợp khi ứng dụng chờ dependency quá thời hạn và không nhận được phản hồi. Tùy kiến trúc API, có thể dùng một mã lỗi nghiệp vụ thống nhất, nhưng nội dung phải nói rõ kết quả đã được xác nhận hay chưa. Không trả `200 OK` với trường `success: true` chỉ vì fallback đã chạy.

Không đưa stack trace, thông tin xác thực hoặc chi tiết nội bộ của dependency vào response công khai. Ghi nguyên nhân đầy đủ trong log có kiểm soát và liên kết log với operation ID để điều tra.

## 6. Idempotency bảo vệ khi kết quả không xác định

Timeout không đồng nghĩa command thất bại. Khi request có thể đã được xử lý, caller cần một khóa idempotency ổn định để truy vấn hoặc gửi lại cùng một thao tác mà không tạo hiệu ứng phụ lần thứ hai.

Một luồng thanh toán có thể hoạt động như sau:

1. Caller tạo `operationId` hoặc idempotency key duy nhất cho ý định thanh toán.
2. Payment Service lưu khóa cùng trạng thái xử lý và kết quả nếu đã nhận command.
3. Caller gửi command kèm khóa đó.
4. Nếu phản hồi bị timeout, caller giữ nguyên khóa và tra cứu trạng thái bằng operation ID.
5. Nếu cần gửi lại, caller dùng lại khóa cũ; Payment Service phải nhận diện request trùng và trả trạng thái đã lưu hoặc tiếp tục xử lý theo quy tắc đã định.

Ví dụ request:

```http
POST /payments/authorizations
Idempotency-Key: pay-order-8472
Content-Type: application/json

{
  "orderId": "order-8472",
  "amount": 1250000,
  "currency": "VND"
}
```

Khóa phải được tạo từ ý định nghiệp vụ và giữ nguyên qua các lần thử lại của cùng thao tác. Không tạo khóa mới mỗi khi nhận timeout. Idempotency chỉ hiệu quả nếu phía nhận lưu và thực thi quy tắc chống trùng một cách bền vững; chỉ gửi header mà không có xử lý ở server không đủ bảo đảm.

Idempotency cũng không thay thế tra cứu trạng thái. Khi kết quả chưa rõ, cung cấp endpoint như `GET /operations/{operationId}` hoặc một luồng đối soát để caller biết command đang chờ, đã hoàn tất, bị từ chối hay cần can thiệp.

## 7. Khi nào có thể tiếp nhận command để xử lý bất đồng bộ?

Một số nghiệp vụ cho phép hệ thống xác nhận đã tiếp nhận yêu cầu trước khi công việc hoàn tất. Ví dụ, người dùng gửi yêu cầu xuất báo cáo hoặc tạo lệnh xử lý nền. Trong trường hợp đó, phản hồi `202 Accepted` không phải thành công giả nếu ứng dụng đã lưu command bền vững và hợp đồng API nói rõ đây là xác nhận tiếp nhận.

Một mô hình thường dùng là transactional outbox:

1. Trong một transaction cục bộ, lưu bản ghi operation và thông điệp outbox.
2. Chỉ sau khi transaction commit thành công, API trả `202 Accepted` cùng `operationId`.
3. Worker đọc outbox và gửi command tới dependency.
4. Nếu dependency tạm thời không khả dụng, worker retry theo backoff có giới hạn và circuit breaker bảo vệ lời gọi.
5. Khi xử lý xong, cập nhật trạng thái operation để caller tra cứu.

```text
HTTP command
     |
     v
Database transaction
  - operation record
  - outbox message
     |
   COMMIT
     |
     +------> 202 Accepted + operationId
     |
     v
Outbox worker
     |
     v
Circuit breaker -> Dependency
     |
     +---- success / rejected / retryable failure
     |
     v
Update operation status
```

Chỉ xác nhận `202` sau khi dữ liệu tiếp nhận đã được lưu bền vững. Nếu database hoặc hàng đợi bền vững cũng không khả dụng, hãy từ chối yêu cầu. Một message chỉ nằm trong bộ nhớ của process không đủ để hứa rằng command sẽ được xử lý sau khi ứng dụng khởi động lại.

Không phải mọi command đều có thể chuyển sang xử lý bất đồng bộ. Chỉ dùng cách này khi nghiệp vụ cho phép eventual completion, caller có thể tra cứu trạng thái và có quy trình xử lý thất bại hoặc đối soát rõ ràng.

## 8. Tránh retry mù quáng trong fallback

Fallback không nên lập tức gọi lại cùng dependency qua một client khác hoặc lặp lại command với khóa mới. Hành vi đó có thể vượt qua circuit breaker và tăng tải lên hệ thống đang suy giảm. Với command có side effect, retry chỉ an toàn khi:

- Có idempotency key được phía nhận thực thi bền vững.
- Loại lỗi cho biết có thể thử lại, hoặc trạng thái được tra cứu trước khi gửi lại.
- Có giới hạn số lần thử, exponential backoff và jitter.
- Deadline của request hoặc workflow còn đủ thời gian.
- Retry được đặt ở một tầng có trách nhiệm rõ ràng, tránh nhiều tầng cùng retry nhân số lần gọi.

Khi breaker `OPEN`, supplier không được chạy. Nếu fallback tự gọi một đường khác tới cùng dependency, nó làm mất tác dụng bảo vệ. Hãy trả lỗi tạm thời hoặc ghi nhận một command bền vững theo mô hình bất đồng bộ đã được thiết kế.

## 9. Kiểm thử để chắc chắn không có thành công giả

Kiểm thử cần xác minh cả response và số lần gọi dependency. Với breaker đang `OPEN`, client không được gọi và service phải trả lỗi hoặc trạng thái chờ phù hợp. Với timeout sau khi supplier đã chạy, service không được tự kết luận command thất bại hay thành công nếu chưa có bằng chứng.

Ví dụ kiểm thử ý tưởng với Mockito:

```java
// Giả sử breaker paymentAuthorization đã được mở trong fixture.
assertThatThrownBy(() -> paymentService.authorize(command))
    .isInstanceOf(PaymentDependencyUnavailableException.class);

// Supplier không chạy khi breaker OPEN.
verifyNoInteractions(paymentClient);
```

Với tình huống timeout:

```java
when(paymentClient.authorize(command, command.idempotencyKey()))
    .thenThrow(new SocketTimeoutException("response timed out"));

assertThatThrownBy(() -> paymentService.authorize(command))
    .isInstanceOf(PaymentOutcomeUnknownException.class);

verify(paymentClient, times(1))
    .authorize(command, command.idempotencyKey());
```

Các đoạn mã trên giả định test đã cấu hình cùng breaker ID và mock tương ứng. Bổ sung kiểm thử cho những trường hợp sau:

- Fallback không trả về đối tượng `approved`, `completed` hoặc giá trị mặc định thể hiện command đã thành công.
- Breaker `OPEN` từ chối trước khi client được gọi.
- Timeout trả về operation ID để caller tra cứu trạng thái.
- Gửi lại cùng idempotency key không tạo hiệu ứng thanh toán hoặc tạo đơn trùng.
- Nếu dùng outbox, API chỉ trả `202` sau khi transaction lưu operation và outbox đã commit.
- Khi breaker `HALF_OPEN`, lời gọi thử là request thật; command phải được bảo vệ bằng idempotency như mọi lần gọi khác.

## 10. Quy tắc chọn fallback cho thao tác quan trọng

- Với thao tác ghi cần xác nhận ngay, trả lỗi tạm thời khi breaker mở; không giả lập thành công.
- Với timeout sau khi request có thể đã tới dependency, biểu diễn kết quả chưa xác định và cung cấp operation ID để tra cứu.
- Giữ nguyên idempotency key qua các lần thử lại của cùng một ý định nghiệp vụ.
- Chỉ trả `202 Accepted` khi command đã được lưu bền vững và hệ thống có cơ chế theo dõi, retry, đối soát.
- Không để fallback gọi lại cùng dependency ngoài circuit breaker.
- Phân biệt lỗi từ chối chắc chắn, lỗi dependency và kết quả chưa xác định trong log, metric và API response.
- Chỉ dùng cache hoặc dữ liệu mặc định cho thao tác đọc khi nghiệp vụ chấp nhận độ cũ và API thể hiện rõ điều đó.

Fallback tốt bảo vệ cả dependency lẫn tính đúng đắn của nghiệp vụ. Với command quan trọng, từ chối rõ ràng hoặc xác nhận tiếp nhận bền vững giúp caller biết phải làm gì tiếp theo; một phản hồi thành công giả chỉ che giấu sự cố và có thể tạo ra dữ liệu sai khó khắc phục.
