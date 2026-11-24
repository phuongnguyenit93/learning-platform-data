# Giới hạn thời gian trong luồng reactive và xử lý cancellation

Trong ứng dụng Spring Cloud dùng WebClient và Reactor, lời gọi đến dịch vụ phụ thuộc thường trả về Mono hoặc Flux. Một publisher có thể chưa phát kết quả trong thời gian dài, hoặc tiếp tục phát dữ liệu nhưng không hoàn tất. Nếu request phía trên đã hết ngân sách thời gian mà lời gọi vẫn chạy, tài nguyên có thể bị giữ lại và kết quả trả về cũng không còn hữu ích.

Với luồng reactive, cần đặt giới hạn thời gian phù hợp và hiểu cách cancellation lan truyền. Reactor cung cấp toán tử `timeout` để phát lỗi khi publisher không đáp ứng đúng hạn và hủy subscription ở upstream. Spring Cloud CircuitBreaker có thể bao quanh publisher để ghi nhận lỗi timeout và chuyển sang fallback. Tuy nhiên, cancellation chỉ yêu cầu các thành phần phía trên dừng công việc; nó không bảo đảm máy chủ từ xa đã ngừng xử lý.

## Timeout trong luồng reactive là gì?

Timeout xác định khoảng thời gian tối đa mà một lời gọi được phép chờ theo chính sách của ứng dụng. Khi hết thời hạn, luồng phát tín hiệu lỗi timeout thay vì tiếp tục chờ vô hạn.

Với `Mono`, `timeout(Duration)` giới hạn thời gian từ lúc subscription bắt đầu cho đến khi Mono phát kết quả hoặc hoàn tất. Ví dụ:

~~~java
Mono<Product> product = webClient.get()
        .uri("/products/{sku}", sku)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));
~~~

Nếu Mono không hoàn tất trong hai giây, Reactor phát lỗi `TimeoutException` và hủy subscription của publisher nguồn. Thời hạn này bao gồm thời gian chờ kết nối, phản hồi và xử lý trong chuỗi publisher tính từ lúc subscription bắt đầu. Các timeout riêng của HTTP client vẫn cần được cấu hình để giới hạn từng giai đoạn mạng và bảo vệ cả những đường gọi không đi qua toán tử này.

Với `Flux`, cần phân biệt timeout giữa các phần tử và deadline cho toàn bộ luồng. `Flux.timeout(Duration)` thường giới hạn khoảng thời gian chờ tín hiệu tiếp theo; nếu luồng phát dữ liệu đều đặn, nó có thể tiếp tục lâu hơn Duration. Nếu cần deadline tổng thể, hãy đặt giới hạn ở ranh giới request hoặc bao một luồng có kích thước hữu hạn thành Mono rồi áp dụng timeout cho toàn bộ thao tác. Không nên dùng timeout giữa các phần tử như thể đó là giới hạn tổng thời gian của một stream dài hạn.

## Cancellation là gì và xảy ra khi nào?

Reactive Streams cho phép subscriber hủy subscription bằng tín hiệu `cancel()`. Khi cancellation được gửi xuống upstream, các publisher và operator được yêu cầu dừng phát dữ liệu và giải phóng tài nguyên mà chúng đang quản lý.

Cancellation có thể xảy ra trong một số trường hợp:

- Người dùng đóng trang hoặc client HTTP ngắt kết nối.
- Request phía trên hết deadline và hủy luồng xử lý.
- Toán tử `timeout` hết thời hạn và hủy publisher nguồn.
- Một operator như `take` hoặc logic nghiệp vụ quyết định không cần thêm dữ liệu.
- Một publisher tổng hợp bị hủy khi một nhánh khác đã đủ kết quả.

Cancellation là tín hiệu điều khiển luồng riêng biệt. Nó không giống một ngoại lệ được phát ra bằng `onError`, cũng không đồng nghĩa lời gọi đã thất bại theo nghĩa nghiệp vụ. Vì vậy, không nên mặc định rằng mọi cancellation đều làm tăng failure count của circuit breaker. Cần theo dõi cancellation riêng và kiểm tra hành vi cụ thể của phiên bản operator/backend đang sử dụng.

## Timeout và cancellation phối hợp như thế nào?

Khi một Mono bị timeout, Reactor thực hiện hai việc theo trình tự:

1. Hủy subscription của publisher nguồn để yêu cầu upstream dừng công việc.
2. Phát lỗi timeout xuống subscriber phía dưới, trừ khi ứng dụng đã chỉ định publisher thay thế ngay trong toán tử timeout.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant T as Timeout operator
    participant W as WebClient publisher
    participant S as Dịch vụ phụ thuộc
    C->>T: subscribe
    T->>W: subscribe upstream
    W->>S: Gửi HTTP request
    Note over T: Hết thời hạn
    T-->>W: cancel()
    T-->>C: onError(TimeoutException)
    Note over S: Máy chủ có thể vẫn đang xử lý
~~~

Reactor có thể hủy request ở phía client và giải phóng tài nguyên kết nối khi HTTP client hỗ trợ cancellation. Tuy nhiên, nếu máy chủ đã nhận request và bắt đầu xử lý, việc client đóng kết nối không đảm bảo máy chủ dừng tác vụ. Một giao dịch ghi có thể đã được thực hiện dù client không nhận được phản hồi.

Với thao tác ghi như thanh toán hoặc giữ chỗ tồn kho, timeout tạo ra kết quả chưa xác định: caller không biết giao dịch đã hoàn thành ở phía server hay chưa. Không được tự động gửi lại một thao tác không idempotent chỉ vì client đã timeout. Hãy dùng idempotency key, mã giao dịch hoặc API tra cứu trạng thái để xác định kết quả trước khi thử lại.

## Đặt timeout trong WebClient và Spring Cloud CircuitBreaker

Có thể kết hợp Reactor `timeout` với `ReactiveCircuitBreaker`. Toán tử timeout được đặt trên publisher mà circuit breaker bảo vệ, để lỗi timeout đi qua circuit breaker và được ghi nhận theo chính sách phân loại.

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;

@Service
public class ReactiveInventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public ReactiveInventoryClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();

        this.inventoryBreaker =
                circuitBreakerFactory.create("inventory-read");
    }

    public Mono<InventoryResult> find(String sku) {
        Mono<Inventory> request = Mono.defer(() ->
                webClient.get()
                        .uri("/inventory/{sku}", sku)
                        .retrieve()
                        .bodyToMono(Inventory.class)
        )
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                // Ghi nhận upstream subscription đã bị hủy.
            }
        })
        .timeout(Duration.ofMillis(900));

        return inventoryBreaker.run(
                request.map(InventoryResult::fresh),
                error -> {
                    if (error instanceof TimeoutException) {
                        return Mono.just(InventoryResult.unavailable(sku));
                    }
                    return Mono.just(InventoryResult.unavailable(sku));
                }
        );
    }
}
~~~

`Inventory` và `InventoryResult` là các kiểu dữ liệu minh họa. Trong ứng dụng thực tế, hãy thay bằng mô hình dữ liệu và chính sách fallback của dự án.

Một số điểm cần chú ý:

- `Mono.defer` tạo lời gọi khi có subscription, tránh khởi chạy công việc từ trước khi publisher được đăng ký.
- `timeout` được đặt bên trong publisher truyền cho circuit breaker, nên timeout phát ra dưới dạng lỗi của lời gọi được bảo vệ.
- `doFinally` nằm trước `timeout`, vì vậy nó quan sát cancellation được timeout gửi xuống upstream. Nếu caller hủy toàn bộ request, tín hiệu CANCEL cũng có thể đi qua đây.
- Fallback trả một kết quả suy giảm có chủ đích. Không nên giả định rằng timeout có nghĩa sản phẩm không tồn tại hoặc tồn kho bằng 0.
- Circuit breaker và timeout có hai trách nhiệm: timeout giới hạn thời gian một lần gọi; circuit breaker quyết định có cho phép các lần gọi tiếp theo đi đến phụ thuộc hay không.

Nếu dùng overload `timeout(Duration, fallbackPublisher)` để tự thay thế lỗi timeout bằng dữ liệu dự phòng trước khi publisher tới circuit breaker, circuit breaker có thể chỉ nhìn thấy kết quả thành công và không ghi nhận timeout như một lỗi. Khi cần timeout đóng góp vào failure rate, hãy để lỗi timeout đi qua circuit breaker rồi xử lý ở fallback của circuit breaker hoặc ở tầng phía trên.

## TimeLimiter và Reactor timeout khác nhau ở đâu?

Tên gọi TimeLimiter thường được dùng cho cơ chế Resilience4j giới hạn thời gian của tác vụ dựa trên Future hoặc CompletionStage. Với reactive publisher, cancellation được điều khiển bằng Reactive Streams và các operator của Reactor.

| Cơ chế | Đối tượng chính | Hành vi khi hết hạn |
|---|---|---|
| Resilience4j TimeLimiter | Future hoặc CompletionStage được bảo vệ | Hoàn tất tác vụ bọc bằng lỗi timeout; có thể yêu cầu hủy Future theo cấu hình. |
| Reactor `Mono.timeout` | Một Mono | Hủy subscription nguồn và phát TimeoutException nếu không có kết quả đúng hạn. |
| Reactor `Flux.timeout` | Một Flux | Theo dõi thời gian chờ tín hiệu; thường là thời gian giữa các phần tử. |
| HTTP client timeout | Kết nối, phản hồi hoặc thao tác mạng | Giới hạn giai đoạn mạng theo khả năng của client. |

Ví dụ cấu hình TimeLimiter cho đường gọi dựa trên Future:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory-lookup:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

`cancelRunningFuture` yêu cầu hủy Future đang chạy khi TimeLimiter hết hạn. Khả năng dừng công việc thực tế phụ thuộc vào Future, executor và tác vụ bên dưới có phản hồi với interrupt hay không. Với WebClient và Reactor, hãy dùng cancellation của publisher và cấu hình timeout của HTTP client; không nên giả định rằng `cancelRunningFuture` tự động hủy mọi hoạt động reactive hoặc dừng xử lý trên máy chủ từ xa.

Một số phiên bản hoặc cấu hình Spring Cloud CircuitBreaker có thể tích hợp timeout theo backend. Hãy xác định rõ đường gọi đang dùng API đồng bộ, Future hay reactive và kiểm tra extension point của đúng phiên bản. Tránh đặt nhiều timeout chồng lấn mà không biết timeout nào sẽ phát lỗi trước hoặc lỗi nào circuit breaker thực sự ghi nhận.

## Phân bổ ngân sách thời gian cho cả request

Timeout của một lời gọi phụ thuộc cần nằm trong ngân sách thời gian của request phía trên. Nếu API phải phản hồi trong hai giây, không thể dành toàn bộ hai giây cho dịch vụ tồn kho rồi mới xử lý cache, cơ sở dữ liệu và serialize response.

Ví dụ về ngân sách:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Xác thực và xử lý đầu vào | 100 ms |
| Gọi dịch vụ tồn kho | 700 ms |
| Đọc dữ liệu cục bộ và tạo phản hồi | 300 ms |
| Dự phòng cho scheduler, mạng và serialize | 400 ms |
| Tổng deadline phía API | 1.500 ms |

Các con số cần được điều chỉnh theo SLA và phân phối độ trễ thực tế. Đặt timeout cho từng phụ thuộc thấp hơn phần ngân sách còn lại của request. Nếu có nhiều lời gọi tuần tự, hãy tính tổng thời gian; nếu các lời gọi chạy song song, tính theo nhánh chậm nhất và thời gian tổng hợp.

Có thể cấu hình nhiều lớp timeout:

- Connect timeout để giới hạn thời gian thiết lập kết nối.
- Response hoặc read timeout để giới hạn thời gian chờ phản hồi theo HTTP client.
- Reactor timeout để đặt deadline cho chuỗi publisher.
- Deadline của request phía trên để bảo vệ toàn bộ quá trình xử lý.

Các timeout cần phối hợp với nhau. Nếu timeout ở HTTP client dài hơn nhiều so với deadline reactive, Reactor có thể hủy publisher trước, nhưng client vẫn cần xử lý việc đóng tài nguyên. Nếu timeout của tầng dưới ngắn hơn quá nhiều, ứng dụng có thể phát sinh lỗi dù request phía trên còn đủ ngân sách.

## Kết hợp timeout với retry và circuit breaker

Retry có thể giúp vượt qua lỗi tạm thời, nhưng mỗi lần thử lại đều tiêu tốn thời gian và tạo thêm tải. Cần giới hạn số lần retry và tổng deadline.

Ví dụ, đặt timeout cho mỗi lần thử và timeout tổng cho toàn bộ chuỗi:

~~~java
Mono<Product> request = Mono.defer(this::callProductService)
        .timeout(Duration.ofMillis(400))
        .retryWhen(
                Retry.max(1)
                        .filter(this::isTransientFailure)
        )
        .timeout(Duration.ofMillis(900));
~~~

Trong ví dụ, mỗi lần gọi có giới hạn 400 ms và toàn bộ chuỗi retry có deadline 900 ms. Retry chỉ được áp dụng cho lỗi tạm thời đã xác định. Cần thêm backoff và jitter nếu hệ thống cho phép, đồng thời tránh retry khi circuit breaker đang OPEN hoặc khi lỗi không thể phục hồi bằng cách thử lại.

Vị trí circuit breaker so với retry làm thay đổi đơn vị được thống kê. Nếu retry nằm bên trong publisher được circuit breaker bảo vệ, circuit breaker thường quan sát kết quả cuối cùng của cả chuỗi thử lại như một lời gọi logic. Nếu mỗi lần retry đi qua một circuit breaker riêng, các lần thử có thể được thống kê riêng. Hãy chọn cách bố trí theo mục tiêu đo lường và bảo vệ của ứng dụng.

Đối với thao tác ghi, chỉ retry khi API hỗ trợ idempotency hoặc ứng dụng có thể xác định chắc chắn rằng lần thử trước chưa được thực hiện. Cancellation và timeout ở client không phải bằng chứng rằng server chưa xử lý request.

## Cancellation không đồng nghĩa tác vụ nền đã dừng

Cancellation là yêu cầu dừng từ subscriber xuống publisher. Các operator reactive hợp tác sẽ giải phóng subscription và tài nguyên của chúng. Nhưng tác vụ blocking hoặc mã gọi thư viện không hỗ trợ cancellation có thể tiếp tục chạy.

Ví dụ không nên dùng blocking call trực tiếp trên event-loop:

~~~java
Mono.fromCallable(() -> blockingInventoryClient.find(sku))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(1));
~~~

Đưa blocking call sang boundedElastic giúp tránh chặn event-loop, nhưng timeout vẫn không bảo đảm phương thức blocking lập tức dừng. Việc hủy subscription có thể yêu cầu interrupt thread; thư viện blocking có thể bỏ qua interrupt hoặc tiếp tục chờ socket. Cần cấu hình timeout ở chính HTTP client hoặc JDBC driver, giới hạn thread và connection pool, đồng thời kiểm tra khả năng hủy của thư viện.

Với WebClient, cancellation thường được truyền tới Reactor Netty để hủy trao đổi HTTP ở phía client. Dù vậy, server có thể đã nhận và tiếp tục xử lý. Với thao tác đọc, điều này thường chỉ lãng phí một phần tài nguyên. Với thao tác ghi, cần cơ chế idempotency hoặc tra cứu trạng thái để xử lý kết quả chưa xác định.

## Quan sát timeout và cancellation

Nên phân biệt các tín hiệu khi vận hành:

- Timeout: deadline của operator hoặc client đã hết.
- Cancellation từ caller: client phía trên không còn cần kết quả.
- Circuit breaker OPEN: lời gọi bị từ chối trước khi đi tới phụ thuộc.
- Lỗi kết nối hoặc phản hồi: HTTP client phát lỗi trước khi timeout của ứng dụng hết hạn.
- Hoàn tất bình thường: publisher phát kết quả và hoàn thành.

Có thể dùng `doFinally` để quan sát loại tín hiệu kết thúc:

~~~java
publisher.doFinally(signalType -> {
    switch (signalType) {
        case CANCEL:
            // Tăng bộ đếm cancellation.
            break;
        case ON_ERROR:
            // Ghi nhận lỗi.
            break;
        case ON_COMPLETE:
            // Ghi nhận hoàn tất.
            break;
        default:
            break;
    }
});
~~~

Đoạn mã minh họa cách phân biệt tín hiệu. Metrics nên có nhãn giới hạn như circuit breaker ID, dependency và loại tín hiệu. Không đưa request ID, SKU hoặc user ID vào nhãn metrics. Có thể ghi correlation ID trong log hoặc trace để nối các sự kiện của một request.

Các chỉ số hữu ích:

- Số timeout theo từng phụ thuộc và endpoint.
- Số cancellation từ caller và cancellation do timeout.
- Độ trễ p50, p95, p99 của lời gọi reactive.
- Số lời gọi bị circuit breaker từ chối.
- Số lần fallback và kết quả fallback.
- Số tác vụ blocking còn chạy sau khi caller đã hủy.
- Số kết nối hoặc luồng bị giữ quá lâu.

Nếu timeout tăng nhưng tỷ lệ lỗi từ server không tăng, có thể phụ thuộc đang chậm hoặc timeout quá thấp. Nếu cancellation tăng đột biến, kiểm tra client disconnect, deadline ở gateway hoặc frontend và các request bị hủy do người dùng điều hướng đi nơi khác.

## Kiểm thử timeout và cancellation

Dùng publisher giả lập có thể trì hoãn, phát lỗi, phát dữ liệu hoặc ghi nhận cancellation để kiểm tra hành vi. Không chỉ kiểm tra response cuối cùng; cần xác nhận publisher nguồn có nhận cancellation và tài nguyên được giải phóng.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Mono hoàn tất trước timeout | Trả kết quả bình thường. |
| Mono không hoàn tất trong thời hạn | Phát TimeoutException và hủy subscription nguồn. |
| Caller hủy subscription trước khi hoàn tất | Upstream nhận cancellation; ghi nhận tín hiệu CANCEL. |
| WebClient bị timeout | Client hủy trao đổi nếu có thể; không giả định server chắc chắn dừng xử lý. |
| Circuit breaker đang OPEN | Không gọi dịch vụ nguồn; fallback xử lý lời gọi bị từ chối. |
| Timeout nằm bên trong circuit breaker | Timeout được ghi nhận theo chính sách lỗi của circuit breaker. |
| Timeout đã được đổi thành fallback trước circuit breaker | Xác nhận circuit breaker có thể chỉ thấy kết quả thay thế thành công. |
| Flux phát đều nhưng kéo dài | Xác nhận timeout giữa các phần tử không bị nhầm là deadline tổng. |
| Blocking call bị hủy | Xác nhận thư viện có phản hồi interrupt hoặc timeout riêng. |
| Thao tác ghi bị timeout | Dùng idempotency key hoặc tra cứu trạng thái trước khi thử lại. |

Trong kiểm thử, dùng Clock hoặc publisher timer có thể điều khiển thời gian và tránh chờ lâu. Với WebClient, dùng server giả lập có thể trì hoãn phản hồi hoặc đóng kết nối để xác nhận timeout, cancellation và xử lý lỗi mạng.

## Quy trình triển khai

1. Xác định deadline của request và phần ngân sách dành cho từng lời gọi phụ thuộc.
2. Dùng Reactor `timeout` cho Mono hoặc chuỗi reactive cần deadline; hiểu rõ timeout giữa các phần tử của Flux.
3. Cấu hình connect/read/response timeout ở HTTP client để giới hạn các giai đoạn mạng.
4. Đặt publisher đã giới hạn thời gian bên trong ReactiveCircuitBreaker để timeout được ghi nhận đúng.
5. Giữ fallback riêng với timeout operator khi cần circuit breaker thống kê timeout là lỗi.
6. Xử lý cancellation bằng cách giải phóng tài nguyên và đo tín hiệu CANCEL; không giả định máy chủ từ xa đã dừng.
7. Giới hạn retry theo ngân sách tổng và chỉ retry lỗi tạm thời có thể phục hồi.
8. Với thao tác ghi, dùng idempotency hoặc tra cứu trạng thái để xử lý kết quả chưa xác định sau timeout.
9. Kiểm thử timeout, cancellation từ caller, circuit breaker OPEN, blocking call và Flux dài hạn.

Trong luồng reactive, timeout tạo ra giới hạn thời gian và cancellation yêu cầu publisher nguồn dừng công việc. Khi kết hợp đúng với Spring Cloud CircuitBreaker, ứng dụng có thể chuyển sang fallback kịp thời và giảm tài nguyên bị giữ bởi lời gọi chậm. Hãy thiết kế deadline theo ngân sách request, theo dõi cancellation riêng và nhớ rằng dừng chờ ở client không đồng nghĩa giao dịch ở máy chủ đã bị hủy.

