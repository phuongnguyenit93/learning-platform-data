# Rate Limiter giới hạn tốc độ khác Bulkhead giới hạn đồng thời

Rate Limiter và Bulkhead đều kiểm soát tải trong ứng dụng Spring Cloud, nhưng chúng bảo vệ hai giới hạn khác nhau. **Rate Limiter** giới hạn số lời gọi được chấp nhận trong một khoảng thời gian. **Bulkhead** giới hạn số lời gọi đang thực thi cùng lúc. Một dịch vụ có thể cần cả hai: Rate Limiter kiểm soát tốc độ yêu cầu đi vào, còn Bulkhead giữ cho số tác vụ đang chiếm tài nguyên không vượt quá năng lực xử lý.

Nếu chỉ dùng Rate Limiter, các lời gọi được cấp quyền ở những chu kỳ liên tiếp vẫn có thể tích lũy khi dịch vụ phản hồi chậm. Nếu chỉ dùng Bulkhead, ứng dụng giới hạn được số lời gọi đồng thời nhưng vẫn có thể gửi một lượng yêu cầu rất lớn trong một giây khi mỗi lời gọi hoàn tất nhanh. Hiểu đúng sự khác nhau giúp chọn ngưỡng và phối hợp chúng với circuit breaker, timeout và fallback.

## Hai câu hỏi khác nhau: bao nhiêu lời gọi mỗi giây và bao nhiêu lời gọi cùng lúc?

Rate Limiter trả lời câu hỏi: **Trong một khoảng thời gian, có bao nhiêu lời gọi được phép bắt đầu?**

Bulkhead trả lời câu hỏi: **Tại một thời điểm, có bao nhiêu lời gọi được phép chiếm tài nguyên xử lý?**

| Tiêu chí | Rate Limiter | Bulkhead |
|---|---|---|
| Giới hạn | Số quyền gọi trong một chu kỳ thời gian. | Số lời gọi đang chạy đồng thời. |
| Mục tiêu | Điều tiết tốc độ, quota và bảo vệ giới hạn của phụ thuộc. | Cô lập tài nguyên và ngăn một phụ thuộc chiếm hết năng lực xử lý. |
| Khi hết giới hạn | Từ chối hoặc chờ đến khi có quyền gọi mới. | Từ chối hoặc chờ đến khi có vị trí thực thi trống. |
| Tham số tiêu biểu | `limitForPeriod`, `limitRefreshPeriod`, `timeoutDuration`. | `maxConcurrentCalls`, `maxWaitDuration`. |
| Không đảm bảo | Không giới hạn số lời gọi đang chạy. | Không giới hạn tổng số lời gọi trong một khoảng thời gian. |

Ví dụ, dịch vụ tồn kho cho phép tối đa 50 lời gọi mỗi giây và ứng dụng muốn chỉ có tối đa 20 lời gọi đang chờ hoặc thực thi ở một thời điểm. Rate Limiter có thể đặt 50 quyền gọi mỗi giây; Bulkhead đặt 20 vị trí đồng thời.

Nếu mỗi lời gọi chỉ mất 10 ms, giới hạn đồng thời 20 có thể cho phép nhiều lượt gọi liên tiếp trong một giây. Bulkhead không thay thế quota 50 lời gọi/giây. Ngược lại, nếu mỗi lời gọi mất 2 giây, Rate Limiter cấp 50 quyền trong một giây có thể khiến nhiều lời gọi vẫn đang chạy cùng lúc. Bulkhead giúp chặn số tác vụ tích lũy.

## Rate Limiter trong Resilience4j

Resilience4j RateLimiter cấp một số lượng quyền gọi trong mỗi chu kỳ làm mới. Các tham số chính:

- `limitForPeriod`: số quyền gọi được cấp trong một chu kỳ.
- `limitRefreshPeriod`: thời lượng của chu kỳ cấp quyền.
- `timeoutDuration`: thời gian tối đa một lời gọi chờ quyền trước khi bị từ chối.

Ví dụ cấu hình tối đa 50 quyền gọi mỗi giây:

~~~yaml
resilience4j:
  ratelimiter:
    instances:
      inventory-read:
        limitForPeriod: 50
        limitRefreshPeriod: 1s
        timeoutDuration: 0s
~~~

Với `timeoutDuration: 0s`, lời gọi không chờ khi hết quyền mà bị từ chối ngay. Nếu đặt thời gian chờ lớn hơn 0, caller có thể chờ quyền ở chu kỳ kế tiếp. Thời gian chờ cần nằm trong deadline của request; không nên giữ thread lâu chỉ để đợi quota.

RateLimiter của Resilience4j làm mới quyền theo chu kỳ cấu hình. Nó không phải một bộ đếm toàn cục dùng chung giữa mọi máy chủ, và cũng không nên được hiểu là bộ giới hạn sliding-window chính xác từng mili giây. Lưu lượng có thể dồn gần ranh giới giữa hai chu kỳ. Nếu cần giới hạn toàn hệ thống hoặc chống burst theo thuật toán token bucket/leaky bucket ở gateway, hãy chọn cơ chế phù hợp tại tầng đó.

Khi hết quyền, Resilience4j ném `RequestNotPermitted`. Đây là quyết định điều tiết tải ở ứng dụng gọi, không phải bằng chứng dịch vụ tồn kho bị lỗi. Có thể ánh xạ nó thành HTTP 429 hoặc một phản hồi quá tải phù hợp với hợp đồng API.

## Bulkhead trong Resilience4j

Bulkhead giới hạn số lời gọi được phép thực thi đồng thời. Resilience4j có hai kiểu chính:

| Kiểu | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Semaphore Bulkhead | Dùng semaphore để giới hạn số lời gọi cùng lúc trên luồng gọi hiện tại. | Lời gọi đồng bộ hoặc khi chỉ cần giới hạn số tác vụ đang đi qua. |
| Thread Pool Bulkhead | Chạy tác vụ trong thread pool riêng với hàng đợi có giới hạn. | Cần tách nhóm luồng thực thi, đặc biệt khi cô lập tác vụ blocking. |

Ví dụ semaphore bulkhead cho dịch vụ tồn kho:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory-read:
        maxConcurrentCalls: 20
        maxWaitDuration: 0s
~~~

`maxConcurrentCalls` đặt số vị trí thực thi tối đa. `maxWaitDuration` xác định thời gian chờ vị trí trống; đặt 0 để từ chối ngay khi đã đủ tải. Khi không còn vị trí, Resilience4j ném `BulkheadFullException`.

Với Thread Pool Bulkhead, cấu hình các tham số riêng:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory-refresh:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Thread Pool Bulkhead có thread pool và hàng đợi riêng. Hàng đợi cần có giới hạn nhỏ phù hợp với deadline; hàng đợi quá lớn chỉ trì hoãn việc từ chối và làm tăng độ trễ. Khi hàng đợi đầy, tác vụ mới bị từ chối. Không nên dùng Thread Pool Bulkhead chỉ vì muốn có giới hạn đồng thời; semaphore bulkhead đơn giản hơn nếu không cần chuyển tác vụ sang nhóm thread riêng.

## Cùng nhìn một tình huống thực tế

Giả sử dịch vụ đặt hàng gọi dịch vụ tồn kho. Phụ thuộc có khả năng xử lý khoảng 50 lời gọi/giây và ứng dụng chỉ muốn tối đa 20 lời gọi tồn kho đang thực thi cùng lúc.

- Rate Limiter cấp tối đa 50 quyền trong một chu kỳ một giây.
- Bulkhead giữ tối đa 20 lời gọi đồng thời.
- Timeout giới hạn thời gian chờ của từng lời gọi.
- Circuit breaker ngừng gửi lời gọi khi phụ thuộc liên tục lỗi hoặc phản hồi quá chậm.
- Fallback quyết định phản hồi phù hợp khi lời gọi thất bại hoặc bị từ chối.

~~~mermaid
flowchart TD
    A[Yêu cầu đến dịch vụ đặt hàng] --> B[Rate Limiter]
    B -->|Có quyền gọi| C[Bulkhead]
    B -->|Hết quota| R[Từ chối / phản hồi quá tải]
    C -->|Còn vị trí| D[Circuit Breaker]
    C -->|Đầy tải| R
    D -->|Cho phép| E[Timeout + lời gọi tồn kho]
    D -->|OPEN| F[Fallback]
    E -->|Thành công| G[Kết quả bình thường]
    E -->|Lỗi hoặc timeout| F
    F --> H[Kết quả dự phòng]
~~~

Sơ đồ minh họa thứ tự phối hợp thường hữu ích: Rate Limiter và Bulkhead kiểm soát khả năng nhận việc trước khi lời gọi đi qua circuit breaker. Các lỗi từ chối do hết quota hoặc hết vị trí không bị nhầm thành lỗi của dịch vụ tồn kho.

## Kết hợp Rate Limiter, Bulkhead và Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker cung cấp abstraction cho circuit breaker; RateLimiter và Bulkhead có thể được dùng trực tiếp từ Resilience4j để bổ sung chính sách giới hạn tải. Ví dụ dưới đây dùng factory của Spring Cloud để tạo circuit breaker, đồng thời bọc lời gọi bằng RateLimiter và semaphore Bulkhead.

~~~java
import java.util.function.Supplier;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.ratelimiter.RateLimiter;
import io.github.resilience4j.ratelimiter.RateLimiterConfig;
import io.github.resilience4j.ratelimiter.RequestNotPermitted;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryQueryService {

    private final InventoryClient inventoryClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RateLimiter rateLimiter;
    private final Bulkhead bulkhead;

    public InventoryQueryService(
            InventoryClient inventoryClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryClient = inventoryClient;
        this.circuitBreakerFactory = circuitBreakerFactory;

        this.rateLimiter = RateLimiter.of(
                "inventory-read",
                RateLimiterConfig.custom()
                        .limitForPeriod(50)
                        .limitRefreshPeriod(java.time.Duration.ofSeconds(1))
                        .timeoutDuration(java.time.Duration.ZERO)
                        .build()
        );

        this.bulkhead = Bulkhead.of(
                "inventory-read",
                BulkheadConfig.custom()
                        .maxConcurrentCalls(20)
                        .maxWaitDuration(java.time.Duration.ZERO)
                        .build()
        );
    }

    public Inventory find(String sku) {
        Supplier<Inventory> circuitProtected = () ->
                circuitBreakerFactory.create("inventory-read").run(
                        () -> inventoryClient.fetch(sku),
                        error -> Inventory.unavailable(sku)
                );

        Supplier<Inventory> bulkheadProtected =
                Bulkhead.decorateSupplier(bulkhead, circuitProtected);

        Supplier<Inventory> rateLimited =
                RateLimiter.decorateSupplier(rateLimiter, bulkheadProtected);

        try {
            return rateLimited.get();
        } catch (RequestNotPermitted ex) {
            throw new InventoryRateLimitedException(
                    "Inventory request rate exceeded", ex
            );
        } catch (BulkheadFullException ex) {
            throw new InventoryBusyException(
                    "Inventory concurrency limit reached", ex
            );
        }
    }
}
~~~

Các lớp `InventoryClient`, `Inventory`, `InventoryRateLimitedException` và `InventoryBusyException` là kiểu minh họa. Trong ứng dụng thực tế, nên tạo RateLimiter và Bulkhead dưới dạng bean hoặc lấy từ registry để chia sẻ cùng instance trong phạm vi ứng dụng, đồng thời dùng cấu hình application.yml thay vì tạo mới ở mỗi service instance.

Thứ tự thực thi của ví dụ là:

1. RateLimiter kiểm tra quyền gọi.
2. Bulkhead lấy một vị trí đồng thời.
3. Spring Cloud CircuitBreaker kiểm tra trạng thái và thực hiện lời gọi.
4. Nếu lời gọi được phép, InventoryClient gọi dịch vụ từ xa.

Với thứ tự này, `RequestNotPermitted` và `BulkheadFullException` phát sinh bên ngoài circuit breaker. Vì vậy, chúng không làm tăng failure rate của circuit breaker đang bảo vệ dịch vụ tồn kho. Circuit breaker tập trung ghi nhận lỗi và độ trễ của phụ thuộc.

Nếu đặt circuit breaker ở ngoài cùng, các lỗi từ chối của RateLimiter hoặc Bulkhead có thể đi vào bộ phân loại lỗi của circuit breaker. Khi đó, cần cấu hình ignore predicate cho các ngoại lệ chính sách này hoặc thay đổi thứ tự decorator. Nếu không, ứng dụng có thể mở mạch vì chính nó đang giới hạn tải.

## Chọn thứ tự phối hợp chính sách

Thứ tự các decorator ảnh hưởng đến tài nguyên nào được cấp trước và lỗi nào được circuit breaker ghi nhận.

| Thứ tự | Tác động |
|---|---|
| RateLimiter → Bulkhead → CircuitBreaker → lời gọi | Kiểm tra quota trước, lấy vị trí đồng thời sau đó; circuit breaker chủ yếu quan sát lỗi của phụ thuộc. |
| Bulkhead → RateLimiter → CircuitBreaker → lời gọi | Có thể giữ một vị trí bulkhead trong khi chờ quota, làm lãng phí năng lực đồng thời. |
| CircuitBreaker → RateLimiter → Bulkhead → lời gọi | Circuit breaker có thể ghi nhận lỗi từ chối của RateLimiter/Bulkhead nếu không cấu hình ignore phù hợp. |

Với lời gọi đồng bộ, thứ tự RateLimiter → Bulkhead → CircuitBreaker thường là lựa chọn dễ hiểu khi muốn từ chối tải cục bộ trước và chỉ thống kê lỗi phụ thuộc ở circuit breaker. Tuy nhiên, nếu RateLimiter phải chờ permit lâu, request vẫn giữ thread trong thời gian chờ. Hãy đặt `timeoutDuration` ngắn hoặc bằng 0 khi cần từ chối nhanh.

Đối với thao tác reactive, dùng các operator tương ứng của Resilience4j Reactor và kiểm tra thứ tự khi áp dụng `transformDeferred`. Không gọi `block()` để kết hợp các chính sách đồng bộ vào một chuỗi reactive.

## Tính toán sơ bộ giới hạn đồng thời

Có thể ước lượng số lời gọi đang chạy trung bình bằng quan hệ giữa throughput và thời gian xử lý:

`Số lời gọi đồng thời trung bình ≈ số lời gọi mỗi giây × thời gian xử lý trung bình tính bằng giây`

Nếu dịch vụ xử lý 40 lời gọi/giây và thời gian phản hồi trung bình là 250 ms (0,25 giây), số lời gọi đang chạy trung bình xấp xỉ 10. Nếu thời gian phản hồi tăng lên 800 ms, cùng throughput đó cần khoảng 32 lời gọi đồng thời.

Đây là ước lượng theo tải trung bình, không phải giới hạn an toàn. Cần xem thêm p95/p99, burst, thời gian giữ kết nối và năng lực thread/connection pool. Bulkhead quá thấp sẽ từ chối cả lưu lượng bình thường; quá cao sẽ không bảo vệ được hệ thống khi phụ thuộc chậm.

Rate Limiter cũng cần được chọn theo năng lực thật của phụ thuộc và quota của nhà cung cấp. Nếu mỗi replica có RateLimiter riêng đặt 50 quyền/giây và có 4 replica, tổng lưu lượng có thể xấp xỉ 200 quyền/giây trên toàn cụm. Nếu quota là toàn hệ thống, cần phân bổ quota theo replica hoặc dùng gateway/distributed rate limiter có phối hợp.

Tương tự, Bulkhead trong từng JVM là giới hạn cục bộ. Bốn replica, mỗi replica cho phép 20 lời gọi đồng thời, có thể tạo tối đa khoảng 80 lời gọi đồng thời tới phụ thuộc. Hãy tính tổng giới hạn ở cấp cụm và để lại khoảng dự phòng cho các caller khác.

## Phân biệt lỗi từ chối và lỗi phụ thuộc

RateLimiter và Bulkhead có thể từ chối lời gọi trước khi request đến dịch vụ nguồn. Các lỗi này nên được phân biệt với timeout, lỗi kết nối và lỗi máy chủ.

| Ngoại lệ hoặc kết quả | Nguyên nhân | Cách phản hồi gợi ý |
|---|---|---|
| `RequestNotPermitted` | Hết quyền gọi trong chu kỳ RateLimiter. | HTTP 429 hoặc phản hồi quá tải có thể thử lại sau. |
| `BulkheadFullException` | Đã đạt giới hạn lời gọi đồng thời. | HTTP 503 hoặc phản hồi quá tải tạm thời. |
| `CallNotPermittedException` | Circuit breaker đang OPEN. | Fallback hoặc phản hồi phụ thuộc tạm thời không sẵn sàng. |
| Timeout hoặc lỗi kết nối | Phụ thuộc chậm hoặc không thể truy cập. | Fallback phù hợp và ghi nhận vào circuit breaker. |
| Lỗi nghiệp vụ | Yêu cầu không hợp lệ hoặc không thỏa quy tắc. | Trả lỗi nghiệp vụ, không tính nhầm là lỗi hạ tầng. |

Mã HTTP cụ thể phụ thuộc hợp đồng API và cách hệ thống phân biệt quota với quá tải tài nguyên. Nếu trả `Retry-After`, hãy đưa ra thời gian có cơ sở từ chính sách quota hoặc trạng thái hệ thống. Không nên hướng client retry liên tục vì điều đó có thể làm tải tăng thêm.

## Kết hợp timeout, retry và fallback

Bulkhead và RateLimiter không thay thế timeout. Bulkhead giới hạn số lời gọi đang chạy; nếu một lời gọi giữ vị trí quá lâu, các request mới vẫn có thể bị từ chối. Timeout giải phóng thời gian chờ ở phía caller và giúp vị trí bulkhead được trả lại khi tác vụ thực sự kết thúc hoặc hủy được.

Retry có thể tiêu thụ thêm quota và vị trí đồng thời. Nếu retry được đặt bên trong RateLimiter, mỗi lần thử có thể cần một permit mới tùy cách bọc. Nếu retry nằm ngoài RateLimiter, toàn bộ chuỗi có thể chỉ lấy một permit dù tạo nhiều lần gọi tới phụ thuộc. Hãy chọn chính sách theo quota của phụ thuộc: quota thường cần tính từng request thực sự gửi đi.

Không retry `RequestNotPermitted` hoặc `BulkheadFullException` ngay lập tức. Đây là tín hiệu ứng dụng đang đạt giới hạn; retry tức thời sẽ làm tăng áp lực. Có thể trả phản hồi để caller thử lại sau một khoảng thời gian có kiểm soát. Với lỗi phụ thuộc, retry chỉ nên dùng cho lỗi tạm thời và phải nằm trong deadline tổng.

Fallback cũng cần phân biệt nguyên nhân. Dữ liệu cache có thể phù hợp khi circuit breaker mở vì phụ thuộc lỗi, nhưng nếu RateLimiter từ chối do caller vượt quota, việc trả cache có thể vô tình cho phép caller lách giới hạn. Hãy quyết định rõ liệu quota áp dụng cho mọi phản hồi hay chỉ lời gọi tới phụ thuộc.

## Theo dõi hiệu quả của từng chính sách

Không nên gộp mọi lần từ chối thành một chỉ số “circuit breaker failure”. Mỗi cơ chế có mục tiêu riêng và cần metrics riêng:

- RateLimiter: số permit được cấp, số lời gọi bị từ chối, thời gian chờ permit và mức sử dụng quota.
- Bulkhead: số lời gọi đang chạy, số vị trí còn trống, số lần từ chối và độ dài hàng đợi nếu dùng thread pool.
- Circuit breaker: trạng thái CLOSED/OPEN/HALF_OPEN, số lỗi, tỷ lệ lỗi, tỷ lệ lời gọi chậm và số lời gọi bị từ chối.
- Timeout: số lần hết hạn, độ trễ trước timeout và số tác vụ chưa dừng sau cancellation.
- Fallback: số lần fallback theo nguyên nhân và loại dữ liệu trả về.

Dùng nhãn có miền giá trị giới hạn như tên dependency, policy ID và loại kết quả. Không gắn user ID, order ID hoặc URL chứa tham số vào nhãn metrics. Với RateLimiter và Bulkhead cục bộ, hãy quan sát theo replica và tổng hợp ở cấp cụm để phát hiện tổng tải vượt quota của dịch vụ nguồn.

## Kiểm thử phối hợp Rate Limiter và Bulkhead

Có thể kiểm thử từng cơ chế độc lập rồi kiểm thử thứ tự kết hợp:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Gửi ít lời gọi hơn quota trong một chu kỳ | RateLimiter cấp quyền cho lời gọi. |
| Vượt quota với timeoutDuration bằng 0 | Lời gọi bị từ chối nhanh bằng RequestNotPermitted. |
| Lời gọi chậm và đạt maxConcurrentCalls | Bulkhead từ chối lời gọi mới bằng BulkheadFullException. |
| Một lời gọi hoàn tất | Vị trí semaphore bulkhead được giải phóng. |
| Circuit breaker OPEN | Lời gọi bị từ chối bởi circuit breaker và fallback được xử lý. |
| RateLimiter từ chối trước circuit breaker | Circuit breaker không ghi nhận lỗi phụ thuộc cho lần bị giới hạn này. |
| Bulkhead từ chối trước circuit breaker | Failure rate của phụ thuộc không tăng vì lỗi giới hạn đồng thời. |
| Retry gặp RateLimiter hoặc Bulkhead từ chối | Không retry tức thời; tuân thủ deadline và chính sách thử lại. |
| Chạy nhiều replica | Tổng quota và tổng concurrency được tính ở cấp cụm. |

Dùng clock hoặc cấu hình chu kỳ nhỏ trong kiểm thử để quan sát RateLimiter làm mới permit. Với Bulkhead, dùng lời gọi giả lập có latch để giữ một số vị trí đồng thời, sau đó xác nhận lời gọi tiếp theo bị từ chối và vị trí được giải phóng khi tác vụ hoàn tất.

## Quy trình chọn chính sách

1. Xác định quota theo thời gian của dịch vụ phụ thuộc và chọn RateLimiter phù hợp.
2. Đo thời gian xử lý, throughput và giới hạn thread/connection để chọn maxConcurrentCalls.
3. Quyết định từ chối ngay hay chờ permit/vị trí; giữ thời gian chờ trong deadline của request.
4. Đặt RateLimiter và Bulkhead trước circuit breaker nếu muốn lỗi giới hạn tải không bị tính thành lỗi phụ thuộc.
5. Cấu hình timeout để lời gọi chậm không giữ vị trí Bulkhead vô hạn.
6. Phân biệt RequestNotPermitted, BulkheadFullException và CallNotPermittedException khi trả lỗi.
7. Giới hạn retry, tránh retry tức thời khi bị từ chối và cân nhắc quota cho từng lần gọi thật.
8. Tính tổng quota và concurrency trên tất cả replica.
9. Theo dõi metrics riêng và kiểm thử cả tải bình thường lẫn tình huống phụ thuộc chậm.

Rate Limiter kiểm soát tốc độ lời gọi theo chu kỳ; Bulkhead kiểm soát số lời gọi đang chiếm tài nguyên cùng lúc. Khi phối hợp chúng trước circuit breaker, ứng dụng có thể điều tiết lưu lượng, cô lập tài nguyên và để circuit breaker tập trung phản ánh sức khỏe của dịch vụ phụ thuộc. Chọn giới hạn dựa trên quota, độ trễ và năng lực thực tế, đồng thời tính cả tổng tải khi triển khai nhiều replica.

