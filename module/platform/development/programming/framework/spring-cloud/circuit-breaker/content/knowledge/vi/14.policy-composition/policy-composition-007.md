# Thứ tự Rate Limiter, Bulkhead, TimeLimiter và Circuit Breaker

Rate Limiter, Bulkhead, TimeLimiter và Circuit Breaker đều bảo vệ ứng dụng khi tải tăng hoặc dịch vụ phụ thuộc gặp sự cố, nhưng mỗi cơ chế kiểm soát một giới hạn khác nhau. Khi kết hợp chúng, thứ tự bọc lời gọi quyết định cơ chế nào nhận request trước, thời gian chờ nào được tính vào timeout và loại lỗi nào được Circuit Breaker ghi nhận.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, mục tiêu là ngăn lỗi dây chuyền khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Một cách phối hợp thường dùng là để Circuit Breaker kiểm tra trạng thái trước, Rate Limiter kiểm soát tốc độ, TimeLimiter đặt thời hạn cho toàn bộ tác vụ được đưa vào Bulkhead, rồi ThreadPoolBulkhead giới hạn số tác vụ chạy và chờ trước khi gọi dịch vụ phụ thuộc. Đây là một thứ tự tham khảo; cần điều chỉnh theo mục tiêu đo thời gian và cách phân loại lỗi của hệ thống.

## 1. Mỗi policy bảo vệ một giới hạn khác nhau

| Cơ chế | Giới hạn được kiểm soát | Câu hỏi chính |
| --- | --- | --- |
| Rate Limiter | Tốc độ tiếp nhận lời gọi trong một khoảng thời gian | Có được phép gửi thêm request ở thời điểm này không? |
| Bulkhead | Số lời gọi đồng thời và số tác vụ đang chờ | Còn năng lực thực thi hoặc vị trí trong queue không? |
| TimeLimiter | Thời gian tối đa chờ một tác vụ bất đồng bộ | Khi nào cần kết thúc chờ vì đã hết ngân sách thời gian? |
| Circuit Breaker | Tình trạng sức khỏe của dịch vụ phụ thuộc | Có nên tiếp tục gọi phụ thuộc đang lỗi hoặc chậm không? |

Ví dụ, Rate Limiter giới hạn dịch vụ Kho nhận tối đa 30 lời gọi mỗi giây. Bulkhead giới hạn số tác vụ lấy tồn kho đang chạy và đang chờ. TimeLimiter giới hạn thời gian chờ mỗi tác vụ. Circuit Breaker theo dõi tỷ lệ lỗi và lời gọi chậm để mở mạch khi dịch vụ Kho suy giảm.

Không cơ chế nào thay thế hoàn toàn cơ chế còn lại. Rate Limiter không giới hạn số tác vụ đang chạy nếu thời gian xử lý kéo dài; Bulkhead không phát hiện phụ thuộc liên tục trả lỗi; TimeLimiter không tự giới hạn tốc độ request; Circuit Breaker không đặt giới hạn tổng số tác vụ có thể chờ trong hàng đợi.

## 2. Thứ tự tham khảo cho một lời gọi

Với lời gọi bất đồng bộ dùng ThreadPoolBulkhead, một thứ tự thường hữu ích là:

1. **Circuit Breaker** kiểm tra trạng thái. Nếu đang OPEN, từ chối nhanh mà không chiếm slot trong pool hoặc queue.
2. **Rate Limiter** kiểm tra ngân sách request. Nếu vượt giới hạn, từ chối hoặc chờ trong khoảng được cấu hình.
3. **TimeLimiter** bắt đầu ngân sách thời gian cho tác vụ, bao gồm thời gian chờ trong queue và thời gian thực thi.
4. **ThreadPoolBulkhead** giới hạn số luồng và hàng đợi, sau đó thực hiện lời gọi đến dịch vụ phụ thuộc.
5. Kết quả hoặc exception truyền ngược ra ngoài; Circuit Breaker ghi nhận kết quả theo chính sách exception và sliding window.

Sơ đồ theo đường đi của request:

~~~mermaid
flowchart TD
    A[Request đến] --> B[Circuit Breaker]
    B -->|OPEN| X[Từ chối nhanh]
    B -->|CLOSED hoặc HALF_OPEN| C[Rate Limiter]
    C -->|Hết quota| Y[Từ chối hoặc chờ có giới hạn]
    C -->|Được cấp phép| D[TimeLimiter bắt đầu deadline]
    D --> E[ThreadPoolBulkhead]
    E -->|Pool và queue đầy| Z[Từ chối do quá tải]
    E -->|Có chỗ| F[Gọi dịch vụ phụ thuộc]
    F --> G[Kết quả hoặc lỗi]
    G --> H[Circuit Breaker ghi nhận]
~~~

Trong cách sắp xếp này, Circuit Breaker ở ngoài cùng để mạch OPEN từ chối trước khi request tiêu thụ quota của Rate Limiter hoặc chiếm chỗ trong Bulkhead. Rate Limiter đứng trước Bulkhead để request vượt tốc độ bị loại trước khi dùng tài nguyên thread pool. TimeLimiter bao quanh việc gửi tác vụ vào ThreadPoolBulkhead nên thời gian chờ queue cũng nằm trong ngân sách của request.

Thứ tự không phải quy tắc cứng cho mọi ứng dụng. Nếu Rate Limiter được đặt ngoài Circuit Breaker, mọi request vẫn tiêu thụ quota ngay cả khi mạch đã OPEN. Điều đó có thể phù hợp nếu quota dùng để giới hạn lưu lượng đầu vào của API, nhưng thường không phù hợp nếu quota chỉ nhằm kiểm soát số request thực sự gửi đến dịch vụ phụ thuộc.

## 3. Vì sao Circuit Breaker thường đặt trước các giới hạn tài nguyên?

Khi Circuit Breaker đang OPEN, nó đã có bằng chứng rằng phụ thuộc đang không đáp ứng ngưỡng sức khỏe. Request mới nên bị từ chối ngay. Nếu Bulkhead được sử dụng trước Circuit Breaker, request có thể chiếm một slot hoặc được đưa vào queue trước khi phát hiện mạch OPEN.

Đặt Circuit Breaker ở ngoài cùng giúp:

- Từ chối sớm khi phụ thuộc đang được bảo vệ bởi trạng thái OPEN.
- Không tiêu thụ quota Rate Limiter cho request chắc chắn không được gửi đến phụ thuộc.
- Không chiếm luồng hoặc vị trí chờ của Bulkhead cho một lời gọi sẽ bị Circuit Breaker chặn.
- Giảm thời gian phản hồi cho request bị từ chối.

Tuy nhiên, Circuit Breaker ở ngoài sẽ nhìn thấy exception do các policy bên trong phát ra. Ví dụ, Rate Limiter có thể ném `RequestNotPermitted`, còn Bulkhead có thể ném `BulkheadFullException`. Đây là tình trạng từ chối do giới hạn cục bộ, không nhất thiết là lỗi của dịch vụ phụ thuộc. Cần bỏ qua các exception này trong phép tính failure rate hoặc đặt policy sao cho chúng không bị tính như lỗi của phụ thuộc.

## 4. Rate Limiter đứng trước Bulkhead

Rate Limiter giới hạn số lời gọi trong một khoảng thời gian. Resilience4j thường dùng các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `limitForPeriod` | Số quyền gọi được cấp trong một chu kỳ |
| `limitRefreshPeriod` | Thời lượng của chu kỳ cấp lại quyền |
| `timeoutDuration` | Thời gian tối đa chờ quyền gọi nếu chưa được cấp |

Ví dụ, giới hạn 30 lời gọi trong mỗi giây và từ chối ngay khi hết quota:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
~~~

Đặt Rate Limiter trước Bulkhead giúp loại request vượt quota trước khi chúng chiếm luồng hoặc queue. Nếu Rate Limiter được cấu hình chờ quyền, thời gian chờ đó cũng tiêu thụ ngân sách phản hồi tổng thể. Hãy giữ `timeoutDuration` phù hợp với deadline của request; với API cần phản hồi nhanh, từ chối ngay thường dễ dự đoán hơn chờ không rõ thời điểm.

Rate Limiter không đảm bảo giới hạn số tác vụ đang chạy. Nếu mỗi lời gọi mất 10 giây, ngay cả tốc độ 30 request/giây cũng có thể tạo ra hàng trăm tác vụ đồng thời. Vì vậy vẫn cần Bulkhead.

## 5. Bulkhead giới hạn đồng thời và hàng đợi

Có hai kiểu Bulkhead thường gặp trong Resilience4j:

| Kiểu | Cách giới hạn | Khi phù hợp |
| --- | --- | --- |
| SemaphoreBulkhead | Giới hạn số lời gọi đồng thời bằng semaphore | Lời gọi đồng bộ hoặc muốn giới hạn concurrency mà không chuyển sang thread pool riêng |
| ThreadPoolBulkhead | Dùng thread pool riêng, số luồng tối đa và queue hữu hạn | Tách biệt tác vụ bất đồng bộ hoặc tác vụ blocking khỏi luồng xử lý khác |

Ví dụ ThreadPoolBulkhead:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

Pool có thể chạy tối đa 8 tác vụ và giữ tối đa 16 tác vụ chờ. Khi cả hai giới hạn đã đầy, tác vụ mới bị từ chối. Queue hữu hạn ngăn số request chờ tăng không kiểm soát, còn giới hạn luồng ngăn một phụ thuộc chiếm hết năng lực thực thi của ứng dụng.

Rate Limiter và Bulkhead giải quyết hai đại lượng khác nhau. Rate Limiter giới hạn tốc độ tiếp nhận theo thời gian; Bulkhead giới hạn số tác vụ đồng thời và đang chờ. Có thể cần cả hai nếu dịch vụ phụ thuộc vừa có giới hạn request mỗi giây, vừa có giới hạn số kết nối hoặc tác vụ đồng thời.

## 6. TimeLimiter bao quanh tác vụ để tính cả thời gian chờ queue

TimeLimiter giới hạn thời gian chờ một thao tác bất đồng bộ. Với Resilience4j, nó thường làm việc với `Future` hoặc `CompletionStage`; với WebFlux, có thể dùng timeout của Reactor hoặc cơ chế tương thích reactive.

Ví dụ:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Nếu TimeLimiter bắt đầu trước khi tác vụ được gửi vào ThreadPoolBulkhead, deadline bao gồm cả thời gian đợi queue và thời gian gọi dịch vụ Kho. Điều này phù hợp khi ứng dụng muốn giới hạn tổng thời gian từ lúc nhận request đến lúc có kết quả.

Nếu TimeLimiter chỉ bắt đầu bên trong worker sau khi tác vụ đã rời queue, nó chỉ giới hạn thời gian thực thi và không giới hạn thời gian chờ. Một request có thể hết hạn từ phía client trong lúc vẫn đang chờ trong queue. Vì vậy, cần xác định rõ deadline muốn đo là thời gian end-to-end hay riêng thời gian gọi phụ thuộc.

TimeLimiter không đảm bảo dừng được mọi thao tác đang chạy. `cancelRunningFuture` có thể yêu cầu hủy Future, nhưng HTTP client hoặc tác vụ bên dưới cần hỗ trợ cancellation/interrupt để thực sự giải phóng tài nguyên. Cần cấu hình timeout ở HTTP client phù hợp và kiểm tra hành vi hủy trong môi trường thực tế.

Với lời gọi đồng bộ không trả về Future hoặc CompletionStage, TimeLimiter không tự biến nó thành thao tác bất đồng bộ. Có thể dùng timeout của HTTP client hoặc chuyển tác vụ sang một executor có giới hạn rồi quản lý deadline rõ ràng.

## 7. Circuit Breaker ghi nhận timeout và lỗi phụ thuộc

Circuit Breaker nên ghi nhận những kết quả phản ánh sức khỏe của dịch vụ phụ thuộc:

- HTTP 5xx, lỗi kết nối và lỗi phụ thuộc được ánh xạ thành exception.
- Timeout của lời gọi phụ thuộc.
- Lời gọi hoàn tất quá chậm theo `slowCallDurationThreshold`.

Ngược lại, các lỗi từ chối do giới hạn cục bộ thường không nên làm tăng failure rate của phụ thuộc:

| Exception hoặc kết quả | Nguồn | Xử lý gợi ý trong Circuit Breaker |
| --- | --- | --- |
| `RequestNotPermitted` | Rate Limiter hết quota | Bỏ qua trong failure rate; theo dõi riêng số lần bị giới hạn |
| `BulkheadFullException` | Pool và queue đã đầy | Bỏ qua trong failure rate; theo dõi tình trạng quá tải cục bộ |
| `TimeoutException` | TimeLimiter hết thời gian chờ | Ghi nhận là lỗi phụ thuộc nếu timeout đại diện cho lời gọi đã được nhận |
| HTTP 5xx hoặc lỗi kết nối | Dịch vụ phụ thuộc | Ghi nhận là lỗi theo chính sách exception |
| `CallNotPermittedException` | Chính Circuit Breaker đang OPEN | Request bị chặn; không phải một lần gọi mới đến phụ thuộc |
| Lỗi nghiệp vụ như tài nguyên không tồn tại | Kết quả nghiệp vụ | Bỏ qua nếu không phản ánh sức khỏe hạ tầng |

Có thể khai báo exception cục bộ trong `ignoreExceptions`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        ignoreExceptions:
          - io.github.resilience4j.ratelimiter.RequestNotPermitted
          - io.github.resilience4j.bulkhead.BulkheadFullException
~~~

Khi dùng `recordExceptions`, cần rà soát toàn bộ loại exception cần tính để tránh vô tình bỏ sót lỗi phụ thuộc. Exception được ignore không làm tăng failure rate. Tuy nhiên, việc bỏ qua trong Circuit Breaker không có nghĩa là bỏ qua ở API: ứng dụng vẫn cần trả mã quá tải phù hợp và theo dõi riêng số lần Rate Limiter hoặc Bulkhead từ chối.

Đặt `slowCallDurationThreshold` thấp hơn hoặc bằng deadline phù hợp nếu muốn nhận diện các lời gọi chậm trước khi TimeLimiter kết thúc chúng. Nếu timeout xảy ra trước ngưỡng slow-call, Circuit Breaker vẫn có thể ghi nhận lỗi timeout nhưng không nhất thiết ghi nhận lời gọi đó là slow call.

## 8. Ví dụ cấu hình phối hợp

Một cấu hình tổng hợp có thể khai báo mỗi policy dưới prefix riêng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        ignoreExceptions:
          - io.github.resilience4j.ratelimiter.RequestNotPermitted
          - io.github.resilience4j.bulkhead.BulkheadFullException
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 30
        limitRefreshPeriod: 1s
        timeoutDuration: 0
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms
~~~

Trong cấu hình này:

- Circuit Breaker theo dõi tỷ lệ lỗi và lời gọi chậm.
- Rate Limiter cấp tối đa 30 quyền gọi trong một giây và từ chối ngay khi hết quota.
- TimeLimiter đặt deadline 2 giây cho tác vụ bất đồng bộ.
- ThreadPoolBulkhead giới hạn tối đa 8 tác vụ chạy và 16 tác vụ chờ.
- Circuit Breaker bỏ qua lỗi từ chối do Rate Limiter và Bulkhead để không nhầm quá tải cục bộ với lỗi dịch vụ Kho.

Các giá trị chỉ là ví dụ. Cần điều chỉnh theo năng lực dịch vụ phụ thuộc, ngân sách thời gian của API, lưu lượng thực tế và tài nguyên của ứng dụng gọi.

## 9. Minh họa thứ tự bằng CompletionStage

Với Resilience4j, có thể bọc một thao tác bất đồng bộ bằng các decorator. Ví dụ dưới đây minh họa thứ tự thực thi: Circuit Breaker ở ngoài, tiếp theo là Rate Limiter, TimeLimiter, ThreadPoolBulkhead và cuối cùng là lời gọi HTTP.

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.timelimiter.TimeLimiter;

import java.util.concurrent.CompletionStage;
import java.util.concurrent.ScheduledExecutorService;
import java.util.function.Supplier;

public CompletionStage<Inventory> getInventory(String sku) {
    Supplier<CompletionStage<Inventory>> bulkheaded =
            () -> threadPoolBulkhead.executeSupplier(
                    () -> inventoryClient.fetch(sku));

    Supplier<CompletionStage<Inventory>> timed =
            TimeLimiter.decorateCompletionStage(
                    timeLimiter,
                    scheduler,
                    bulkheaded);

    Supplier<CompletionStage<Inventory>> rateLimited =
            RateLimiter.decorateCompletionStage(
                    rateLimiter,
                    timed);

    Supplier<CompletionStage<Inventory>> protectedCall =
            CircuitBreaker.decorateCompletionStage(
                    circuitBreaker,
                    rateLimited);

    return protectedCall.get();
}
~~~

Các biến `threadPoolBulkhead`, `timeLimiter`, `scheduler`, `rateLimiter`, `circuitBreaker` và `inventoryClient` được tạo hoặc inject một lần từ cấu hình/registry phù hợp; không tạo registry hay executor mới cho mỗi request. Đoạn mã tập trung minh họa cách lồng decorator. Cần kiểm tra overload API theo phiên bản Resilience4j mà dự án sử dụng.

Đọc từ ngoài vào trong, request phải qua Circuit Breaker trước. Nếu mạch OPEN, phần còn lại không chạy. Nếu được phép, Rate Limiter cấp quota. TimeLimiter bắt đầu deadline rồi gửi tác vụ vào ThreadPoolBulkhead. Nếu pool và queue đầy, bulkhead từ chối; nếu tác vụ được nhận nhưng không hoàn tất đúng hạn, TimeLimiter hoàn tất stage bằng lỗi timeout. Circuit Breaker quan sát lỗi từ các policy bên trong và áp dụng chính sách ghi nhận.

Trong ví dụ, `RequestNotPermitted` và `BulkheadFullException` cần được ignore trong Circuit Breaker. Timeout và lỗi HTTP phụ thuộc được tính là lỗi theo chính sách đã chọn. Cách này giúp Circuit Breaker đo sức khỏe của phụ thuộc thay vì đo cả tình trạng giới hạn tài nguyên nội bộ.

## 10. Khi nào cần thay đổi thứ tự?

Không có một thứ tự duy nhất phù hợp với mọi mục tiêu. Hãy bắt đầu từ câu hỏi muốn giới hạn điều gì và muốn metrics đo phần thời gian nào:

| Mục tiêu | Điều chỉnh có thể cân nhắc | Đánh đổi |
| --- | --- | --- |
| Giới hạn toàn bộ request đầu vào kể cả khi Circuit Breaker OPEN | Đặt Rate Limiter trước Circuit Breaker | Request bị chặn bởi mạch vẫn tiêu thụ quota |
| Từ chối sớm khi phụ thuộc đang OPEN | Đặt Circuit Breaker trước Rate Limiter và Bulkhead | Cần ignore lỗi từ chối cục bộ phát ra từ các policy bên trong |
| Deadline bao gồm thời gian chờ queue | Đặt TimeLimiter bên ngoài thao tác gửi vào ThreadPoolBulkhead | Thời gian queue cũng tiêu thụ ngân sách timeout |
| Chỉ giới hạn thời gian thực thi sau khi worker bắt đầu | Bắt đầu timeout bên trong tác vụ worker hoặc cấu hình timeout của HTTP client | Thời gian chờ queue cần có deadline riêng |
| Không muốn Bulkhead từ chối ảnh hưởng failure rate | Đặt Bulkhead bên ngoài Circuit Breaker hoặc ignore BulkheadFullException | Circuit Breaker có thể phải kiểm tra OPEN sau khi đã lấy slot nếu Bulkhead ở ngoài |

Nếu Bulkhead đặt ngoài Circuit Breaker, request có thể chiếm slot trước khi Circuit Breaker từ chối do OPEN, nhưng lỗi Bulkhead đầy sẽ không đi qua Circuit Breaker. Nếu Circuit Breaker đặt ngoài Bulkhead, nó từ chối OPEN sớm hơn nhưng phải ignore exception từ Bulkhead để tránh mở mạch sai. Hãy chọn theo mức ưu tiên giữa fail-fast và phân loại metrics.

Khi dùng annotation/AOP, thứ tự thực tế còn phụ thuộc thứ tự aspect của thư viện và cấu hình ứng dụng. Không nên suy ra thứ tự chỉ từ vị trí annotation trên phương thức. Cần xác nhận bằng test hoặc log có định danh từng policy, nhất là khi nhiều aspect cùng bọc một lời gọi.

## 11. Những lỗi thường gặp khi phối hợp policy

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đặt Bulkhead sau một hàng đợi không giới hạn | Tác vụ đã tích tụ trước khi đến vùng cách ly | Đặt giới hạn sớm và dùng queue hữu hạn |
| Rate Limiter đứng sau Bulkhead | Request vượt quota vẫn chiếm slot hoặc queue trước khi bị từ chối | Kiểm tra quota trước khi cấp tài nguyên thực thi |
| TimeLimiter chỉ đo thời gian worker chạy nhưng bỏ qua queue | Request có thể hết hạn khi còn chờ | Đặt deadline quanh thao tác submit hoặc có deadline riêng cho queue |
| Circuit Breaker tính `RequestNotPermitted` là lỗi phụ thuộc | Mạch mở do quota nội bộ bị cạn | Ignore exception và theo dõi Rate Limiter riêng |
| Circuit Breaker tính `BulkheadFullException` là lỗi phụ thuộc | Mạch mở do pool cục bộ đầy dù phụ thuộc có thể khỏe | Ignore exception hoặc điều chỉnh thứ tự |
| Không đặt timeout cho HTTP client | Hủy Future không chắc dừng request mạng | Cấu hình timeout/cancellation ở HTTP client |
| Retry ngay sau khi Bulkhead đầy | Tạo thêm áp lực trong lúc hệ thống quá tải | Từ chối có kiểm soát hoặc retry có backoff |
| Không theo dõi từng policy | Khó phân biệt lỗi phụ thuộc với giới hạn nội bộ | Ghi metrics và log theo từng policy |

## 12. Kiểm thử và quan sát thứ tự thực tế

Nên kiểm tra các kịch bản sau với client giả hoặc môi trường thử nghiệm:

1. Circuit Breaker OPEN: xác nhận request bị từ chối trước khi Rate Limiter và Bulkhead cấp tài nguyên.
2. Rate Limiter hết quota: xác nhận không có request đến dịch vụ phụ thuộc và failure rate của Circuit Breaker không tăng.
3. Bulkhead đầy: xác nhận tác vụ bị từ chối, không vượt số luồng hoặc queue đã cấu hình và exception không làm tăng failure rate phụ thuộc.
4. Tác vụ chờ queue quá lâu: xác nhận TimeLimiter hết hạn theo deadline end-to-end.
5. Dịch vụ phụ thuộc trả HTTP 5xx hoặc timeout: xác nhận Circuit Breaker ghi nhận lỗi và cập nhật sliding window.
6. Dịch vụ phụ thuộc phục hồi: xác nhận HALF_OPEN chỉ cho phép số lời gọi thử nghiệm đã cấu hình và mạch chuyển trạng thái theo kết quả.

Theo dõi tối thiểu:

- Rate Limiter: số quyền được cấp, số request bị từ chối và thời gian chờ.
- Bulkhead: số luồng đang chạy, số tác vụ trong queue và số lần từ chối.
- TimeLimiter: số timeout, thời gian hoàn tất và số tác vụ được hủy.
- Circuit Breaker: trạng thái, failure rate, slow call rate, số lời gọi bị từ chối và số lần chuyển trạng thái.

Khi dashboard cho thấy failure rate tăng cùng lúc với BulkheadFullException, hãy kiểm tra chính sách ignore trước khi kết luận dịch vụ phụ thuộc đang lỗi. Nếu timeout tăng nhưng queue wait chiếm phần lớn thời gian, cần xem lại kích thước pool, queue và deadline thay vì chỉ tăng timeout.

## 13. Quy trình chọn thứ tự

Khi phối hợp Rate Limiter, Bulkhead, TimeLimiter và Circuit Breaker, hãy thực hiện theo trình tự:

1. Xác định giới hạn của phụ thuộc: tốc độ request, concurrency, thời gian phản hồi và ngưỡng lỗi.
2. Chọn Bulkhead phù hợp: semaphore cho giới hạn đồng thời hoặc ThreadPoolBulkhead cho pool riêng và queue hữu hạn.
3. Chọn deadline: xác định timeout có bao gồm thời gian chờ queue hay chỉ thời gian thực thi.
4. Đặt Rate Limiter trước vùng tiêu thụ tài nguyên nếu mục tiêu là không để request vượt quota chiếm slot.
5. Đặt Circuit Breaker ở vị trí đáp ứng mục tiêu fail-fast; thường đặt ngoài để kiểm tra OPEN trước khi cấp quota và tài nguyên.
6. Phân loại exception: timeout và lỗi phụ thuộc được ghi nhận; lỗi từ chối do Rate Limiter/Bulkhead được ignore hoặc xử lý riêng.
7. Kiểm thử thứ tự thực tế, đo metrics từng policy và điều chỉnh dựa trên lưu lượng cùng ngân sách thời gian.

Phối hợp đúng thứ tự giúp mỗi policy làm đúng nhiệm vụ: Rate Limiter kiểm soát tốc độ, Bulkhead giới hạn tài nguyên đồng thời, TimeLimiter đặt deadline và Circuit Breaker ngừng gọi phụ thuộc khi sức khỏe suy giảm. Quan trọng nhất là xác định rõ loại thời gian và loại lỗi mà từng cơ chế quan sát để tránh mở mạch vì quá tải nội bộ hoặc giữ request chờ lâu hơn mức hệ thống có thể đáp ứng.
