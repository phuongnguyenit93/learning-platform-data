# Vẽ chuỗi thực thi và kiểm chứng thứ tự bằng sự kiện

Một lời gọi đến dependency trong Spring Cloud CircuitBreaker có thể đi qua nhiều chính sách bảo vệ: Rate Limiter, Bulkhead, Retry, Circuit Breaker, TimeLimiter và fallback. Mỗi chính sách kiểm soát một khía cạnh khác nhau. Tuy nhiên, kết quả thực tế phụ thuộc không chỉ vào việc bật chính sách nào mà còn vào thứ tự các lớp bao quanh lời gọi.

Ví dụ, đặt Bulkhead bên ngoài Rate Limiter có thể khiến một lời gọi giữ permit Bulkhead trong lúc chờ quyền gửi request. Đặt Rate Limiter bên ngoài Bulkhead có thể kiểm tra quota trước khi chiếm slot concurrency. Tương tự, Circuit Breaker đặt ngoài Retry thường thống kê kết quả cuối cùng của cả chuỗi thử lại; Circuit Breaker đặt trong Retry có thể ghi nhận từng lần thử riêng.

Vì vậy, khi thiết kế policy composition, cần vẽ rõ call path, xác định lớp nào nhìn thấy lỗi nào, rồi kiểm chứng bằng event publisher và log có thứ tự. Bài học này trình bày cách biểu diễn thứ tự, dự đoán hành vi và xác nhận bằng sự kiện trong ứng dụng Spring Cloud CircuitBreaker sử dụng Resilience4j.

## 1. Vì sao thứ tự thực thi quan trọng?

Các chính sách thường được triển khai như những lớp bao quanh một lời gọi gốc. Một lớp có thể kiểm tra điều kiện trước khi gọi lớp bên trong, ghi nhận kết quả sau khi lớp bên trong kết thúc, hoặc chuyển lỗi thành kết quả thay thế.

Ký hiệu:

\[
A(B(C(\text{HTTP})))
\]

được đọc từ ngoài vào trong khi request đi vào:

1. A bắt đầu xử lý.
2. A gọi B.
3. B gọi C.
4. C thực hiện HTTP.
5. Kết quả hoặc lỗi quay ngược qua C, B rồi A.

Vì thế, lớp ngoài cùng thường bắt đầu trước và kết thúc sau cùng. Lớp trong cùng tiếp cận HTTP gần nhất.

Ví dụ, cùng một tập chính sách nhưng hai thứ tự khác nhau có thể cho kết quả thống kê khác nhau:

- **CircuitBreaker(Retry(HTTP))**: Circuit Breaker bao toàn bộ chuỗi Retry và thường ghi nhận một kết quả cuối cùng cho một lời gọi logic.
- **Retry(CircuitBreaker(HTTP))**: mỗi lần Retry gọi lại sẽ đi qua Circuit Breaker; mỗi attempt có thể tạo một phép đo riêng trong sliding window.

Đây không phải khác biệt về cú pháp đơn thuần. Nó ảnh hưởng đến thời điểm mạch mở, số lần request được gửi, số permit được sử dụng và cách dashboard phản ánh lỗi.

## 2. Vẽ call path trước khi cấu hình

Trước khi viết YAML hoặc customizer, hãy xác định các câu hỏi:

- Có bao nhiêu lần thử tối đa cho một request logic?
- Rate Limiter được kiểm tra một lần hay mỗi attempt?
- Bulkhead giữ permit trong thời gian nào?
- Circuit Breaker đo kết quả cuối cùng hay đo từng attempt?
- TimeLimiter bao toàn bộ chuỗi Retry hay chỉ từng lần gọi?
- Fallback chạy bên trong hay bên ngoài phạm vi Circuit Breaker?
- Lỗi từ chính sách cục bộ như BulkheadFullException có bị tính nhầm thành lỗi của remote dependency không?

Một call path minh họa:

~~~mermaid
flowchart TD
    A[Request vào service] --> B[Deadline / TimeLimiter]
    B --> C[Circuit Breaker kiểm tra trạng thái]
    C --> D[Retry điều phối attempt]
    D --> E[Rate Limiter cấp quyền]
    E --> F[Bulkhead lấy permit]
    F --> G[HTTP connection pool]
    G --> H[Remote dependency]
    H --> I[Kết quả hoặc exception]
    I --> J[Giải phóng permit và cập nhật event]
    J --> K{Retry còn attempt và lỗi được retry?}
    K -- Có --> D
    K -- Không --> L[Circuit Breaker ghi nhận kết quả]
    L --> M[Trả kết quả hoặc fallback]
~~~

Sơ đồ này thể hiện một lựa chọn cụ thể: TimeLimiter ở ngoài cùng, Circuit Breaker bao Retry, rồi đến Rate Limiter và Bulkhead. Đây là một phương án để thảo luận, không phải thứ tự mặc định bắt buộc của mọi starter. Adapter Spring Cloud CircuitBreaker có thể tự áp dụng một số module và thứ tự decorator theo implementation, phiên bản và cấu hình. Khi cần kiểm soát thứ tự chính xác, phải xác định adapter thực tế đang tạo chuỗi nào.

## 3. Đọc thứ tự từ ngoài vào trong và từ trong ra ngoài

Với chuỗi:

\[
\text{TimeLimiter}(
  \text{CircuitBreaker}(
    \text{Retry}(
      \text{RateLimiter}(
        \text{Bulkhead}(\text{HTTP})
      )
    )
  )
)
\]

request đi vào theo thứ tự:

1. TimeLimiter bắt đầu ngân sách thời gian cho toàn bộ lời gọi.
2. Circuit Breaker kiểm tra trạng thái và cho phép hoặc từ chối.
3. Retry bắt đầu attempt đầu tiên.
4. Rate Limiter kiểm tra quyền gửi request.
5. Bulkhead lấy permit concurrency.
6. HTTP client lấy connection và gửi request.
7. Kết quả quay ngược qua các lớp.
8. Nếu lỗi thuộc nhóm được Retry cho phép và còn attempt, Retry bắt đầu lần tiếp theo.
9. Sau khi Retry kết thúc, Circuit Breaker ghi nhận kết quả cuối cùng.
10. TimeLimiter kết thúc theo kết quả hoặc deadline; nếu timeout, nó phát tín hiệu timeout và có thể yêu cầu hủy Future tùy API.

Trong chuỗi này, Rate Limiter và Bulkhead nằm bên trong Retry nên được gọi lại cho mỗi attempt. Circuit Breaker nằm ngoài Retry nên chỉ quan sát kết quả cuối của chuỗi thử lại. TimeLimiter ở ngoài cùng nên giới hạn toàn bộ thời gian, bao gồm thời gian chờ giữa các attempt nếu cơ chế Retry nằm trong phạm vi publisher hoặc Future được TimeLimiter bọc.

## 4. Circuit Breaker ngoài Retry hay Retry ngoài Circuit Breaker?

Đây là một quyết định quan trọng nhất khi phối hợp hai chính sách.

### Circuit Breaker bọc Retry

\[
\text{CircuitBreaker}(\text{Retry}(\text{HTTP}))
\]

Một lời gọi logic đi qua Circuit Breaker một lần. Bên trong, Retry có thể tạo nhiều attempt. Circuit Breaker thường chỉ nhìn thấy kết quả cuối cùng của chuỗi Retry.

Ví dụ:

- Attempt 1 thất bại do lỗi kết nối.
- Retry chờ rồi thực hiện attempt 2.
- Attempt 2 thành công.
- Circuit Breaker nhận kết quả cuối cùng là thành công.

Trong cách này, một request logic có một phép đo Circuit Breaker dù có nhiều attempt HTTP. Cách này phù hợp khi muốn đo tỷ lệ thành công cuối cùng mà caller nhận được sau chính sách Retry.

### Retry bọc Circuit Breaker

\[
\text{Retry}(\text{CircuitBreaker}(\text{HTTP}))
\]

Mỗi attempt đi qua Circuit Breaker. Nếu attempt đầu thất bại, Circuit Breaker ghi nhận lỗi của attempt đó. Retry có thể thử lại, nhưng attempt tiếp theo phải xin quyền từ Circuit Breaker lần nữa.

Ví dụ:

- Attempt 1 đi qua Circuit Breaker và thất bại.
- Circuit Breaker ghi nhận một lỗi.
- Retry bắt đầu attempt 2.
- Nếu Circuit Breaker vẫn CLOSED, attempt 2 được phép đi tiếp.
- Nếu mạch đã OPEN, attempt 2 bị từ chối bằng CallNotPermittedException.

Cách này làm Circuit Breaker phản ứng nhanh hơn với các lỗi của từng attempt, nhưng cần cấu hình Retry để không tiếp tục thử lại những lỗi từ chối do Circuit Breaker đang OPEN. Nếu không, retry có thể chỉ lặp lại những lần bị từ chối mà không gửi thêm request đến remote dependency.

| Tiêu chí | CircuitBreaker(Retry(HTTP)) | Retry(CircuitBreaker(HTTP)) |
|---|---|---|
| Số phép đo CB cho một request logic | Thường một kết quả cuối | Có thể một phép đo cho mỗi attempt |
| Một attempt lỗi nhưng lần sau thành công | CB thường ghi nhận thành công cuối | CB vẫn ghi nhận lỗi attempt đầu và thành công attempt sau |
| Tốc độ CB phản ứng với lỗi từng attempt | Phụ thuộc kết quả cuối và ngưỡng | Có thể nhanh hơn do ghi nhận từng attempt |
| Khi CB chuyển OPEN giữa các attempt | Retry bên trong có thể vẫn tiếp tục theo logic riêng | Attempt sau có thể bị CallNotPermittedException |
| Cần chú ý | Retry có thể che bớt lỗi tạm thời khỏi CB | Retry cần bỏ qua lỗi do CB từ chối |

Không có lựa chọn đúng cho mọi hệ thống. Hãy quyết định muốn Circuit Breaker đo sức khỏe của từng lần gọi đến dependency hay xác suất hoàn tất thành công của một request logic sau Retry.

## 5. Rate Limiter và Bulkhead: thứ tự quyết định lúc chiếm permit

Hai cách sắp xếp:

\[
\text{Bulkhead}(\text{RateLimiter}(\text{HTTP}))
\]

và

\[
\text{RateLimiter}(\text{Bulkhead}(\text{HTTP}))
\]

cho phép phân tích thời điểm lấy tài nguyên.

**Bulkhead ngoài Rate Limiter**:

1. Request lấy permit Bulkhead.
2. Request chờ hoặc xin quyền từ Rate Limiter.
3. Khi có quyền, request mới đi đến HTTP client.
4. Permit Bulkhead được giữ trong cả thời gian chờ Rate Limiter và thời gian gọi HTTP.

Nếu Rate Limiter có timeout chờ dài, slot Bulkhead có thể bị giữ dù request chưa gửi đến server.

**Rate Limiter ngoài Bulkhead**:

1. Request xin quyền Rate Limiter.
2. Sau khi được cấp quyền, request mới lấy permit Bulkhead.
3. Nếu hết permit Bulkhead, request bị từ chối dù đã tiêu thụ một quyền Rate Limiter.
4. Request không giữ permit Bulkhead trong lúc chờ Rate Limiter.

Với hệ thống có Rate Limiter chờ quyền trong một khoảng thời gian, đặt Rate Limiter ngoài Bulkhead thường tránh giữ slot concurrency trong lúc chờ quota. Tuy nhiên, nếu Bulkhead từ chối sau khi Rate Limiter đã cấp quyền, quota có thể bị tiêu thụ dù HTTP chưa được gửi. Cần đánh giá chính sách quota và hành vi admission control.

Nếu Rate Limiter được cấu hình từ chối ngay khi hết quyền, thời gian chờ không đáng kể và khác biệt về thời gian giữ permit giảm đi. Vẫn cần xem event để xác nhận request có đi qua Bulkhead hay không.

## 6. TimeLimiter bao toàn bộ chuỗi hay từng attempt?

TimeLimiter có thể được đặt ngoài Retry hoặc bên trong Retry. Hai lựa chọn tạo deadline khác nhau.

### TimeLimiter ngoài Retry

\[
\text{TimeLimiter}(\text{Retry}(\text{HTTP}))
\]

Deadline bao toàn bộ request logic. Ví dụ timeoutDuration là 3 giây, Retry cho phép hai attempt và có waitDuration 500 mili giây. Tổng thời gian của cả attempt và khoảng chờ vẫn phải nằm trong 3 giây. Nếu vượt deadline, caller nhận timeout dù Retry chưa hoàn thành.

Đây thường là cách phù hợp khi caller có một deadline nghiệp vụ cố định.

### TimeLimiter bên trong Retry

\[
\text{Retry}(\text{TimeLimiter}(\text{HTTP}))
\]

Mỗi attempt có thể nhận một timeout riêng. Nếu mỗi attempt được phép chờ 3 giây và Retry có ba attempt, tổng thời gian có thể gần 9 giây cộng thời gian chờ giữa các lần thử. Điều này có thể vượt deadline của request phía trên.

| Cách đặt | Phạm vi timeout | Tác động |
|---|---|---|
| TimeLimiter(Retry(HTTP)) | Toàn bộ chuỗi Retry | Có một ngân sách tổng thể |
| Retry(TimeLimiter(HTTP)) | Từng attempt | Tổng thời gian có thể nhân lên theo số attempt |

Cần phân biệt timeout của caller với việc tác vụ HTTP thực sự dừng. Khi TimeLimiter hết hạn, cancellation phụ thuộc Future, CompletionStage hoặc publisher mà adapter đang bọc. Đặt TimeLimiter ngoài Retry không tự đảm bảo tất cả request đã gửi trước đó đều bị server dừng xử lý.

## 7. Fallback nằm ở đâu trong chuỗi?

Fallback có thể thay đổi điều mà lớp ngoài nhìn thấy. Ví dụ:

\[
\text{CircuitBreaker}(\text{Fallback}(\text{HTTP}))
\]

Nếu Fallback chuyển exception thành một giá trị bình thường trước khi kết quả quay về Circuit Breaker, Circuit Breaker có thể ghi nhận thành công. Điều này làm tỷ lệ lỗi của dependency bị che khuất.

Ngược lại:

\[
\text{Fallback}(\text{CircuitBreaker}(\text{HTTP}))
\]

Circuit Breaker có thể ghi nhận lỗi trước khi fallback chuyển lỗi thành response suy giảm cho caller. Đây thường là mục tiêu khi muốn fallback phục vụ người dùng nhưng vẫn giữ metric phản ánh sự cố dependency.

Trong API Spring Cloud CircuitBreaker, fallback thường được truyền như một hàm xử lý lỗi cho phương thức run. Adapter chịu trách nhiệm áp dụng fallback theo contract của nó. Khi dùng decorator hoặc tự compose publisher, hãy xác định fallback được áp dụng ở tầng nào và liệu Circuit Breaker đã ghi nhận lỗi trước khi fallback phát ra giá trị thay thế hay chưa.

Cần theo dõi riêng số lần fallback. Một request trả HTTP 200 nhờ dữ liệu cache không nhất thiết có nghĩa dependency đang khỏe.

## 8. Lập bảng dự đoán event trước khi chạy

Trước khi chạy thử, hãy ghi rõ event nào dự kiến xuất hiện và lớp nào phát event đó.

| Lớp | Event cần quan sát | Ý nghĩa |
|---|---|---|
| Rate Limiter | Quyền được cấp hoặc request bị từ chối | Request có được phép đi tiếp theo quota |
| Bulkhead | Permit được cấp, bị từ chối hoặc được giải phóng | Mức concurrency thực tế |
| HTTP client | Request bắt đầu, response hoặc lỗi kết nối | Lời gọi có thực sự chạm đến transport |
| Retry | Attempt được thử lại, hoàn tất hoặc hết lượt | Số lần gọi thực tế |
| Circuit Breaker | Call permitted, success, error, not permitted, state transition | Quyết định và thống kê của mạch |
| TimeLimiter | Success, error hoặc timeout | Thời gian chờ của toàn bộ phạm vi được bọc |
| Fallback | Bắt đầu và kết thúc fallback | Caller nhận kết quả thay thế |

Tên event cụ thể có thể khác giữa phiên bản Resilience4j. Dùng event publisher của từng module để quan sát loại sự kiện mà phiên bản đang chạy cung cấp. Không nên suy luận một event không tồn tại chỉ từ tên gọi trong dashboard.

## 9. Đăng ký event publisher để ghi nhận thứ tự

Resilience4j cung cấp event publisher trên các thành phần như CircuitBreaker, Retry, Bulkhead, RateLimiter và TimeLimiter. Có thể đăng ký consumer để ghi lại event type, timestamp, request ID và tên instance.

Ví dụ minh họa:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.timelimiter.TimeLimiter;

public class PolicyEventLogger {

    private final AtomicLong sequence = new AtomicLong();

    public void observe(
            CircuitBreaker circuitBreaker,
            Retry retry,
            Bulkhead bulkhead,
            RateLimiter rateLimiter,
            TimeLimiter timeLimiter) {

        circuitBreaker.getEventPublisher().onEvent(event ->
                log("CB", event.getEventType().toString()));

        retry.getEventPublisher().onEvent(event ->
                log("RETRY", event.getEventType().toString()));

        bulkhead.getEventPublisher().onEvent(event ->
                log("BULKHEAD", event.getEventType().toString()));

        rateLimiter.getEventPublisher().onEvent(event ->
                log("RATE_LIMITER", event.getEventType().toString()));

        timeLimiter.getEventPublisher().onEvent(event ->
                log("TIME_LIMITER", event.getEventType().toString()));
    }

    private void log(String layer, String event) {
        long order = sequence.incrementAndGet();
        System.out.printf("%d layer=%s event=%s%n", order, layer, event);
    }
}
~~~

Đoạn code minh họa cách đăng ký listener. Constructor, kiểu event publisher và tập event có thể khác theo phiên bản Resilience4j; hãy dùng API của dependency thực tế. Trong ứng dụng chạy đồng thời, sequence toàn cục có thể trộn event từ nhiều request. Nên gắn correlation ID hoặc operation ID vào log để lọc sự kiện của cùng một request.

Để biết HTTP có thực sự được gọi hay không, thêm log ở biên HTTP client:

~~~java
Mono<Inventory> remoteCall = Mono.defer(() -> {
    log.info("HTTP_START operationId={}", operationId);

    return webClient.get()
            .uri("/inventory/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class)
            .doFinally(signal ->
                    log.info("HTTP_END operationId={} signal={}",
                            operationId, signal));
});
~~~

Log HTTP_START chứng minh publisher đã đi đến tầng tạo request. HTTP_END cho biết publisher kết thúc bằng complete, error hoặc cancel. Nó không chứng minh server đã dừng xử lý; muốn biết điều đó cần correlation ở server.

## 10. Đọc một trace event mẫu

Giả sử cấu hình chọn:

\[
\text{TimeLimiter}(
\text{CircuitBreaker}(
\text{Retry}(
\text{RateLimiter}(
\text{Bulkhead}(\text{HTTP})
))))
\]

Một request đầu tiên lỗi kết nối, attempt thứ hai thành công. Event log minh họa có thể như sau:

~~~text
001 TIME_LIMITER  execution_started
002 CIRCUIT_BREAKER call_permitted
003 RATE_LIMITER  permission_acquired
004 BULKHEAD      call_permitted
005 HTTP          request_started
006 HTTP          request_error: connection_reset
007 BULKHEAD      call_finished
008 RETRY         retry_scheduled: attempt=2
009 RATE_LIMITER  permission_acquired
010 BULKHEAD      call_permitted
011 HTTP          request_started
012 HTTP          response_received: 200
013 BULKHEAD      call_finished
014 RETRY         success
015 CIRCUIT_BREAKER success
016 TIME_LIMITER  success
~~~

Tên ở đây là nhãn minh họa để giải thích trace; event type thật cần lấy từ phiên bản đang chạy. Thứ tự có thể khác ở những điểm như event bắt đầu, callback hoàn tất, scheduler hoặc cách adapter phát event. Điều cần xác minh là các quan hệ nhân quả:

- Mỗi attempt có đi qua Rate Limiter và Bulkhead hay không?
- Bulkhead có được giải phóng sau mỗi attempt không?
- Retry có bắt đầu attempt mới sau lỗi không?
- Circuit Breaker có chỉ ghi nhận một kết quả cuối cùng không?
- TimeLimiter có bao trọn toàn bộ khoảng chờ Retry không?

Không nên dùng một trace mẫu để khẳng định thứ tự event tuyệt đối của mọi adapter. Hãy so sánh log thực tế với call path đã thiết kế.

## 11. Thiết kế các tình huống kiểm chứng

Một kiểm thử chỉ chạy request thành công chưa đủ để xác nhận policy composition. Nên tạo các tình huống có kết quả dự đoán được.

| Tình huống | Điều kiện giả lập | Điều cần xác minh |
|---|---|---|
| Thành công ngay | Dependency trả 200 nhanh | Một HTTP attempt; permit được giải phóng; CB ghi nhận success |
| Lỗi rồi Retry thành công | Attempt 1 lỗi, attempt 2 trả 200 | Retry event xuất hiện; số HTTP request bằng hai; CB đo một hay hai kết quả theo vị trí |
| Hết Rate Limiter | Không còn permission | Request không đi đến HTTP; event từ chối quota xuất hiện |
| Hết Bulkhead | Tất cả permit đang được giữ | Request bị từ chối hoặc chờ; HTTP không bắt đầu nếu bị từ chối |
| Circuit Breaker OPEN | CB được đặt hoặc chuyển sang OPEN | CallNotPermitted; không có HTTP_START |
| Timeout | Dependency chậm hơn deadline | TimeLimiter timeout; kiểm tra cancel và thời gian giải phóng permit |
| Fallback | Lời gọi chính lỗi hoặc bị từ chối | Fallback chạy; metric CB vẫn phản ánh lỗi theo vị trí fallback |
| Retry chạm CB OPEN | CB mở giữa các attempt | Attempt tiếp theo bị từ chối; Retry có bỏ qua CallNotPermitted hay không |

Dùng một dependency giả lập hoặc HTTP server test có thể điều khiển được response, độ trễ và lỗi kết nối. Mỗi tình huống nên có operation ID riêng để đối chiếu log và event.

## 12. Ví dụ kiểm chứng Circuit Breaker ngoài Retry và Retry ngoài Circuit Breaker

Giả sử Retry cho phép hai attempt, trong đó attempt đầu thất bại và attempt sau thành công.

**Trường hợp A — Circuit Breaker ngoài Retry**

~~~text
Request
  -> CircuitBreaker: permitted
      -> Retry: attempt 1
          -> HTTP: connection error
      -> Retry: attempt 2
          -> HTTP: 200 OK
  -> CircuitBreaker: success
~~~

Kỳ vọng:

- Có hai request HTTP.
- Retry ghi nhận một lần retry.
- Circuit Breaker ghi nhận kết quả cuối cùng là success.
- Failure rate của Circuit Breaker không tăng vì attempt đầu đã được Retry xử lý thành công.

**Trường hợp B — Retry ngoài Circuit Breaker**

~~~text
Request
  -> Retry: attempt 1
      -> CircuitBreaker: permitted
          -> HTTP: connection error
      -> CircuitBreaker: error
  -> Retry: attempt 2
      -> CircuitBreaker: permitted
          -> HTTP: 200 OK
      -> CircuitBreaker: success
~~~

Kỳ vọng:

- Có hai request HTTP nếu attempt thứ hai được cho phép.
- Circuit Breaker ghi nhận một error và một success.
- Retry ghi nhận một lần retry.
- Failure rate của Circuit Breaker phản ánh lỗi của từng attempt.

Nếu lỗi đầu tiên làm Circuit Breaker chuyển OPEN, attempt thứ hai có thể bị CallNotPermittedException. Khi đó, cấu hình Retry cần quyết định rõ có retry exception này hay không. Thông thường, không nên lặp lại một lời gọi chỉ vì Circuit Breaker đang từ chối.

## 13. Thứ tự Bulkhead và Rate Limiter qua event

Để kiểm chứng thứ tự admission control, có thể tạo tình huống Rate Limiter phải chờ quyền trong khi Bulkhead có một permit duy nhất.

Nếu chuỗi là:

\[
\text{Bulkhead}(\text{RateLimiter}(\text{HTTP}))
\]

event dự kiến:

1. Bulkhead cấp permit.
2. Rate Limiter bắt đầu chờ permission.
3. Permit Bulkhead vẫn đang được giữ.
4. Khi có permission hoặc hết timeout Rate Limiter, Bulkhead mới giải phóng permit.

Nếu chuỗi là:

\[
\text{RateLimiter}(\text{Bulkhead}(\text{HTTP}))
\]

event dự kiến:

1. Rate Limiter chờ và cấp permission.
2. Bulkhead sau đó mới cấp permit.
3. Nếu Bulkhead từ chối, HTTP không bắt đầu nhưng permission Rate Limiter có thể đã bị tiêu thụ.

Từ event và metric, hãy quan sát:

- Thời điểm permit Bulkhead được cấp.
- Thời gian từ lúc cấp permit đến lúc HTTP_START.
- Số lần Rate Limiter từ chối.
- Số lần Bulkhead từ chối.
- Thời gian giữ permit trung bình và p95.

Nếu thời gian giữ permit tăng trong khi HTTP_START không tăng tương ứng, có thể request đang chờ ở một lớp bên trong Bulkhead như Rate Limiter hoặc connection pool.

## 14. Những lưu ý khi đọc event

Event publisher giúp quan sát hành vi của từng policy nhưng không thay thế distributed tracing. Một event của Circuit Breaker không tự chứa toàn bộ call path của request. Cần gắn correlation ID hoặc operation ID vào log ở các lớp.

Một số lưu ý:

- Event có thể phát sinh ở thời điểm khác nhau tùy implementation và scheduler.
- Một request có thể tạo nhiều event cùng loại, đặc biệt khi có Retry.
- Event của Bulkhead có thể xuất hiện cả khi cấp permit và khi kết thúc lời gọi.
- Rate Limiter event cho biết permission được cấp hoặc không cấp, nhưng không chứng minh HTTP request đã gửi.
- Circuit Breaker event phản ánh kết quả mà lớp Circuit Breaker quan sát, không nhất thiết phản ánh từng response nếu Retry nằm bên trong.
- TimeLimiter timeout không chứng minh tác vụ HTTP phía server đã dừng.
- Fallback event cần được log riêng nếu muốn phân biệt kết quả remote với kết quả suy giảm.

Không nên chỉ dựa vào số event để suy ra số HTTP request. Hãy thêm log ở HTTP client hoặc đếm request tại server test để đối chiếu.

## 15. Checklist thiết kế và kiểm chứng

Trước khi đưa policy composition vào production, hãy xác nhận:

1. Call path đã được viết rõ từ lớp ngoài vào HTTP và đường quay về.
2. Vị trí Circuit Breaker so với Retry phản ánh đúng mục tiêu thống kê.
3. Rate Limiter và Bulkhead nằm theo thứ tự phù hợp với thời gian giữ permit.
4. TimeLimiter bao đúng phạm vi deadline: toàn bộ request logic hay từng attempt.
5. Retry chỉ thử lại các lỗi phù hợp và bỏ qua lỗi từ chối do policy cục bộ.
6. Fallback không làm che giấu lỗi của dependency trong metric Circuit Breaker.
7. Bulkhead permit và HTTP connection được giải phóng khi complete, error hoặc cancel.
8. Event publisher được đăng ký cho từng policy và log có correlation ID.
9. HTTP_START/HTTP_END được đối chiếu với số attempt và event Retry.
10. Các tình huống thành công, lỗi, timeout, từ chối và fallback đã được kiểm chứng.

## 16. Quy trình thực hiện

Khi xây dựng hoặc thay đổi thứ tự chính sách trong Spring Cloud CircuitBreaker với Resilience4j, có thể làm theo trình tự:

1. Xác định mục tiêu của từng policy và dependency được bảo vệ.
2. Viết call path bằng ký hiệu lồng nhau, ví dụ TimeLimiter(CircuitBreaker(Retry(RateLimiter(Bulkhead(HTTP))))).
3. Ghi rõ lớp nào bắt đầu trước, lớp nào nhìn thấy từng attempt và lớp nào ghi nhận kết quả cuối.
4. Xác định phạm vi timeout, thời gian giữ permit và vị trí fallback.
5. Kiểm tra cách starter hoặc adapter thực tế tạo decorator; không giả định thứ tự tự động nếu chưa xác minh.
6. Đăng ký event publisher cho Circuit Breaker, Retry, Bulkhead, Rate Limiter và TimeLimiter.
7. Thêm log HTTP ở biên client, correlation ID và operation ID.
8. Chạy từng tình huống kiểm chứng với kết quả dự kiến đã ghi trước.
9. So sánh event, số HTTP attempt, metric và trạng thái cuối.
10. Điều chỉnh thứ tự hoặc exception predicate nếu event cho thấy lỗi cục bộ bị tính nhầm thành lỗi remote.

Vẽ chuỗi thực thi giúp nhìn thấy chính sách nào giữ tài nguyên, chính sách nào nhìn thấy lỗi và phạm vi nào được tính thời gian. Event publisher cùng log ở HTTP client cung cấp bằng chứng để kiểm tra chuỗi đó trong runtime. Khi xác định rõ thứ tự Retry, Circuit Breaker, Rate Limiter, Bulkhead, TimeLimiter và fallback, nhóm phát triển có thể giải thích được vì sao một request bị từ chối, được thử lại, timeout hoặc nhận kết quả suy giảm, đồng thời giữ số liệu vận hành phản ánh đúng hành vi của dependency.
