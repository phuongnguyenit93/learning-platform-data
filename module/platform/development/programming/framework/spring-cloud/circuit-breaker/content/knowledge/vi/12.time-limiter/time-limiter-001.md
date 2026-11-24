# Ranh giới giữa ngắt mạch và giới hạn thời gian

## Mục tiêu của bài học

Circuit breaker và TimeLimiter thường được dùng cùng nhau để bảo vệ lời gọi đến dịch vụ phụ thuộc, nhưng chúng giải quyết hai vấn đề khác nhau. Circuit breaker quan sát kết quả của nhiều lần gọi và quyết định có cho phép lời gọi mới đi tiếp hay không. TimeLimiter giới hạn thời gian chờ của một lần thực thi bất đồng bộ. Nếu nhầm lẫn hai cơ chế, ứng dụng có thể vẫn chờ quá lâu dù breaker đã ghi nhận lời gọi chậm, hoặc mở breaker mà không có timeout thực sự cho thao tác đang chạy.

Trong Spring Cloud CircuitBreaker với Resilience4j, cần xác định rõ nơi thực hiện I/O, nơi giới hạn thời gian và nơi ghi nhận kết quả. Sau bài học, bạn có thể:

- Phân biệt vai trò của CircuitBreaker và TimeLimiter trong một lời gọi phụ thuộc.
- Giải thích vì sao ngưỡng slow call không tự hủy một thao tác đang chạy.
- Cấu hình timeout cho Future hoặc CompletionStage bằng Resilience4j TimeLimiter.
- Dùng timeout của Reactor cho lời gọi WebClient và đặt operator theo đúng thứ tự.
- Kết hợp timeout với CircuitBreaker để timeout được ghi nhận theo chính sách.
- Phân biệt timeout ở thư viện HTTP với việc hủy tác vụ hoặc hủy request từ xa.

## 1. Hai câu hỏi khác nhau: có nên gọi và chờ bao lâu?

Giả sử order-service cần gọi inventory-service để kiểm tra tồn kho. Có hai câu hỏi vận hành:

1. **Có nên gửi một lời gọi mới không?** Nếu các lần gọi gần đây liên tục thất bại hoặc quá chậm, circuit breaker có thể chuyển sang OPEN và từ chối nhanh những lần gọi tiếp theo.
2. **Một lời gọi được phép chạy tối đa bao lâu?** TimeLimiter hoặc timeout của HTTP client giới hạn thời gian chờ của lần gọi hiện tại.

Circuit breaker chủ yếu đưa ra quyết định dựa trên lịch sử gần đây. TimeLimiter đặt giới hạn thời gian cho một lần thực thi. Một lời gọi có thể được phép đi qua breaker đang CLOSED nhưng vẫn bị timeout vì phản hồi quá lâu.

| Cơ chế | Câu hỏi nó trả lời | Tác động chính |
| --- | --- | --- |
| CircuitBreaker | Có nên cho phép lời gọi mới đến phụ thuộc? | Cho phép, ghi nhận kết quả hoặc từ chối nhanh khi OPEN. |
| TimeLimiter | Ứng dụng chờ kết quả của tác vụ bất đồng bộ tối đa bao lâu? | Hoàn tất bằng timeout error khi quá hạn và có thể yêu cầu hủy Future. |
| HTTP client timeout | Kết nối hoặc chờ phản hồi mạng tối đa bao lâu? | Dừng chờ ở tầng client theo khả năng thư viện. |
| Reactor timeout | Publisher được phép không phát tín hiệu trong khoảng thời gian bao lâu? | Phát TimeoutException và gửi tín hiệu cancel upstream. |

Các cơ chế có thể bổ sung cho nhau. Circuit breaker không phải đồng hồ đếm ngược cho một lời gọi đang chạy. TimeLimiter cũng không đánh giá tỷ lệ lỗi của nhiều lần gọi để quyết định trạng thái OPEN.

## 2. Slow call threshold không phải timeout

Resilience4j CircuitBreaker có thể đánh dấu một lời gọi là chậm bằng slowCallDurationThreshold. Khi thời gian thực thi vượt ngưỡng, kết quả được phân loại là slow call. Nếu tỷ lệ slow call trong sliding window đạt slowCallRateThreshold sau khi có đủ mẫu, breaker có thể mở.

Ví dụ:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 50
            failureRateThreshold: 50

Với cấu hình này, lời gọi mất 1,8 giây có thể được ghi nhận là slow call dù vẫn trả kết quả thành công. Khi tỷ lệ lời gọi chậm vượt ngưỡng, breaker có thể chuyển OPEN để ngăn thêm yêu cầu dồn vào phụ thuộc đang suy giảm.

Tuy nhiên, slowCallDurationThreshold chỉ phân loại thời gian thực thi. Nó không tự ngắt kết nối HTTP, không tự interrupt thread và không tự kết thúc một Future đang chạy. Nếu một lời gọi mất 30 giây, breaker có thể ghi nhận nó là chậm sau khi lời gọi hoàn tất; việc chờ 30 giây vẫn cần timeout ở tầng thực thi.

Vì vậy, đừng dùng slowCallDurationThreshold thay cho timeout. Hãy cấu hình cả ngưỡng đánh giá sức khỏe và deadline của một lần gọi.

## 3. TimeLimiter giới hạn tác vụ bất đồng bộ

Resilience4j TimeLimiter hỗ trợ giới hạn thời gian chờ của Future hoặc CompletionStage. Khi tác vụ không hoàn tất trong timeoutDuration, TimeLimiter hoàn tất kết quả phía caller bằng lỗi timeout. Nếu cancelRunningFuture được bật, TimeLimiter yêu cầu hủy Future đang chạy.

Cấu hình cơ bản trong application.yml:

    resilience4j:
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true

timeoutDuration là khoảng thời gian tối đa chờ kết quả. cancelRunningFuture điều khiển việc yêu cầu hủy Future khi timeout xảy ra. Việc hủy có hiệu quả đến đâu phụ thuộc vào loại Future, executor và thư viện thực hiện tác vụ.

TimeLimiter không tự biến một phương thức đồng bộ thành bất đồng bộ. Nếu gọi một phương thức blocking ngay trên request thread rồi mới bọc kết quả đã hoàn tất vào Future, timeout không thể giúp ích. Tác vụ phải được khởi chạy dưới dạng Future hoặc CompletionStage để TimeLimiter theo dõi thời gian hoàn tất.

## 4. Ví dụ TimeLimiter với CompletionStage

Giả sử ứng dụng có một client blocking cũ, nhưng muốn thực hiện công việc trên executor riêng và giới hạn thời gian chờ bằng TimeLimiter. Có thể dùng CompletionStage:

    import io.github.resilience4j.timelimiter.TimeLimiter;
    import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
    import java.util.concurrent.CompletableFuture;
    import java.util.concurrent.CompletionStage;
    import java.util.concurrent.Executor;
    import java.util.concurrent.ScheduledExecutorService;
    import java.util.function.Supplier;

    public class InventoryAsyncGateway {

        private final BlockingInventoryClient client;
        private final TimeLimiter timeLimiter;
        private final Executor ioExecutor;
        private final ScheduledExecutorService timeoutScheduler;

        public InventoryAsyncGateway(
                BlockingInventoryClient client,
                TimeLimiterRegistry registry,
                Executor ioExecutor,
                ScheduledExecutorService timeoutScheduler) {
            this.client = client;
            this.timeLimiter = registry.timeLimiter("inventory");
            this.ioExecutor = ioExecutor;
            this.timeoutScheduler = timeoutScheduler;
        }

        public CompletionStage<InventoryResponse> find(String sku) {
            Supplier<CompletionStage<InventoryResponse>> source = () ->
                CompletableFuture.supplyAsync(
                    () -> client.find(sku),
                    ioExecutor
                );

            return timeLimiter.executeCompletionStage(
                timeoutScheduler,
                source
            );
        }
    }

Trong ví dụ:

- BlockingInventoryClient thực hiện lời gọi đồng bộ.
- CompletableFuture.supplyAsync đưa lời gọi sang ioExecutor, không chặn thread gọi phương thức find.
- TimeLimiter dùng timeoutScheduler để theo dõi thời hạn.
- executeCompletionStage trả về CompletionStage hoàn tất với kết quả hoặc lỗi timeout.

Trong ứng dụng thực tế, ioExecutor và timeoutScheduler cần được quản lý vòng đời bởi Spring, có giới hạn tài nguyên và được đóng đúng cách khi ứng dụng dừng. Không tạo một executor mới cho mỗi request. Cũng cần cấu hình timeout kết nối và phản hồi ngay trên HTTP client mà BlockingInventoryClient sử dụng.

Nếu client blocking không hỗ trợ interrupt hoặc hủy request, Future có thể bị đánh dấu hủy nhưng công việc bên dưới vẫn tiếp tục chạy trên worker cho đến khi client tự timeout hoặc trả về. TimeLimiter giới hạn thời gian caller chờ; nó không bảo đảm máy chủ từ xa đã dừng xử lý.

## 5. Kết hợp TimeLimiter với CircuitBreaker

Khi một lời gọi bị TimeLimiter timeout, timeout error có thể được circuit breaker ghi nhận như một thất bại. Để điều này xảy ra, CircuitBreaker cần quan sát CompletionStage đã được giới hạn thời gian.

Ví dụ kết hợp Resilience4j:

    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
    import io.github.resilience4j.timelimiter.TimeLimiter;
    import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
    import java.util.concurrent.CompletionStage;
    import java.util.concurrent.ScheduledExecutorService;
    import java.util.function.Supplier;

    public CompletionStage<InventoryResponse> find(String sku) {
        CircuitBreaker breaker = circuitBreakerRegistry
            .circuitBreaker("inventory");

        TimeLimiter limiter = timeLimiterRegistry
            .timeLimiter("inventory");

        Supplier<CompletionStage<InventoryResponse>> source = () ->
            CompletableFuture.supplyAsync(
                () -> blockingClient.find(sku),
                ioExecutor
            );

        Supplier<CompletionStage<InventoryResponse>> timedSource = () ->
            limiter.executeCompletionStage(timeoutScheduler, source);

        Supplier<CompletionStage<InventoryResponse>> protectedCall =
            CircuitBreaker.decorateCompletionStage(breaker, timedSource);

        return protectedCall.get();
    }

Thứ tự ở đây có ý nghĩa:

1. source khởi chạy thao tác từ xa trên executor.
2. TimeLimiter bọc CompletionStage để phát sinh lỗi nếu vượt thời hạn.
3. CircuitBreaker bọc stage đã giới hạn thời gian và quan sát kết quả cuối cùng.

Nếu source trả thành công trong thời hạn, breaker ghi nhận thành công. Nếu source lỗi hoặc TimeLimiter phát sinh timeout, breaker có thể ghi nhận thất bại theo cấu hình exception. Khi breaker OPEN, lời gọi bị từ chối trước khi source thực thi; do đó không tạo thêm tác vụ mới chỉ để rồi chờ timeout.

Cần cấu hình recordExceptions/ignoreExceptions phù hợp. Nếu TimeoutException bị bỏ qua, breaker sẽ không tính timeout vào failure rate. Nếu timeout phản ánh phụ thuộc không đáp ứng SLO, thông thường cần để breaker ghi nhận nó. Hãy xác minh exception thực tế được phát ra bởi lớp tích hợp và phiên bản thư viện đang dùng.

## 6. Cấu hình hai ngưỡng theo cùng ngân sách thời gian

Một cách thiết kế là đặt slow call threshold thấp hơn timeout. Như vậy, lời gọi đã có dấu hiệu chậm được thống kê trước khi chạm giới hạn tối đa.

Ví dụ:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 50
            failureRateThreshold: 50
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

      timelimiter:
        instances:
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true

Trong ví dụ này:

- Lời gọi hoàn tất sau 900 ms: thành công bình thường.
- Lời gọi hoàn tất sau 1,8 giây: có thể thành công nhưng được ghi nhận là slow call.
- Lời gọi không hoàn tất trong 2 giây: TimeLimiter phát sinh timeout.
- Khi tỷ lệ slow call hoặc failure rate vượt ngưỡng sau khi đủ mẫu: CircuitBreaker có thể mở.
- Khi CircuitBreaker OPEN: lời gọi mới bị từ chối nhanh và không khởi chạy tác vụ phụ thuộc.

Các con số chỉ để minh họa. Hãy chọn timeout dựa trên ngân sách thời gian tổng thể của request, độ trễ bình thường của phụ thuộc và SLO. Nếu timeout của inventory là 2 giây nhưng API order chỉ có ngân sách 1 giây, tầng gọi có thể hết thời gian trước khi TimeLimiter phát tín hiệu. Timeout phải được phối hợp từ ngoài vào trong, với ngân sách cho các bước tiếp theo và xử lý fallback.

## 7. Timeout cho lời gọi WebClient và Reactor

Với WebClient, lời gọi vốn đã bất đồng bộ và trả về Mono hoặc Flux. Có thể dùng operator timeout của Reactor để giới hạn thời gian chờ:

    Mono<InventoryResponse> request = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(2));

Nếu publisher không phát tín hiệu trong khoảng thời gian quy định, timeout operator phát TimeoutException và gửi cancellation upstream. Cần phân biệt timeout tổng thể của publisher với timeout connect/response của HTTP client. Hãy cấu hình các giới hạn kết nối và phản hồi phù hợp ở WebClient connector để xử lý đúng tầng mạng.

Có thể kết hợp với Resilience4j Reactor CircuitBreakerOperator:

    Mono<InventoryResponse> protectedRequest = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class)
        .timeout(Duration.ofSeconds(2))
        .transformDeferred(
            CircuitBreakerOperator.of(inventoryCircuitBreaker)
        )
        .onErrorResume(
            error -> Mono.just(InventoryResponse.unknown(sku))
        );

Timeout nằm trước CircuitBreakerOperator để breaker nhìn thấy TimeoutException như kết quả lỗi của publisher. Fallback đặt sau operator để không biến lỗi nguồn thành hoàn tất bình thường trước khi breaker ghi nhận. Trong ví dụ, fallback minh họa trả trạng thái chưa xác định; ứng dụng thực tế nên phân loại lỗi và chỉ chuyển những lỗi được nghiệp vụ cho phép thành kết quả thay thế.

Nếu dùng ReactiveCircuitBreakerFactory của Spring Cloud, có thể truyền Mono và fallback vào run. Việc cấu hình TimeLimiter được hỗ trợ và áp dụng ra sao phụ thuộc starter, phiên bản Spring Cloud CircuitBreaker và implementation đang dùng. Với một deadline rõ ràng trên chuỗi Reactor, Mono.timeout là cách trực tiếp để thể hiện giới hạn thời gian của publisher; hãy kiểm tra xem ứng dụng có thêm TimeLimiter tích hợp nào để tránh áp dụng hai timeout không cần thiết.

## 8. Timeout không đồng nghĩa với hủy xử lý ở máy chủ

Khi TimeLimiter hoặc Reactor timeout kích hoạt, caller có thể ngừng chờ và nhận lỗi timeout. Điều đó không có nghĩa dịch vụ từ xa đã dừng công việc.

Có ba phạm vi hủy cần phân biệt:

1. **Hủy kết quả chờ ở caller:** Future hoặc publisher phía ứng dụng hoàn tất bằng timeout/cancel.
2. **Hủy thao tác trong HTTP client:** thư viện client cố gắng đóng request, hủy subscription mạng hoặc ngắt kết nối.
3. **Dừng xử lý ở máy chủ:** server nhận biết client đã ngắt và chủ động dừng tác vụ; điều này phụ thuộc giao thức và cách triển khai server.

Không phải mọi thao tác đều có thể hủy an toàn. Một lệnh ghi dữ liệu có thể đã được máy chủ thực hiện trước khi client timeout. Nếu client thử lại ngay, có nguy cơ gửi lệnh ghi lần hai. Với thao tác thay đổi trạng thái, hãy dùng idempotency key, mã yêu cầu duy nhất hoặc cơ chế kiểm tra trạng thái để tránh tạo tác dụng phụ trùng lặp.

Nếu một API blocking không phản ứng với interrupt, worker có thể tiếp tục bị chiếm sau khi caller đã timeout. Timeout phía HTTP client và giới hạn concurrency vẫn rất quan trọng để giải phóng tài nguyên thực tế.

## 9. Chọn timeout theo loại thao tác

Không phải mọi endpoint cần cùng một timeout. Hãy dựa vào đặc tính nghiệp vụ và phân bố độ trễ của phụ thuộc:

| Thao tác | Cách chọn timeout |
| --- | --- |
| Tra cứu tồn kho đơn giản | Ngắn, dựa trên độ trễ p95/p99 và ngân sách request tạo đơn. |
| Tính giá có nhiều bước | Có thể dài hơn tra cứu đơn giản, nhưng vẫn phải nằm trong ngân sách request tổng thể. |
| Tải báo cáo hoặc dữ liệu lớn | Cần timeout phù hợp với kích thước dữ liệu, phân trang hoặc streaming; không dùng chung timeout ngắn của API tra cứu. |
| Gửi lệnh giữ hàng | Đặt deadline rõ ràng và xử lý idempotency vì timeout không cho biết server đã thực hiện lệnh hay chưa. |
| Stream sự kiện lâu dài | Không dùng một timeout tổng thể ngắn để cắt stream bình thường; cân nhắc timeout kết nối, heartbeat và timeout giữa các tín hiệu. |

Nếu nhiều thao tác dùng chung một breaker, hãy xem xét liệu chúng có cùng đặc tính độ trễ và cùng chính sách lỗi không. Một API báo cáo dài không nên làm ngưỡng slow call của một API tra cứu nhanh mất ý nghĩa. Có thể dùng id riêng và cấu hình riêng cho những thao tác có ngân sách thời gian khác nhau.

## 10. Quan sát timeout và breaker

Để biết hai cơ chế đang phối hợp đúng, hãy theo dõi riêng các loại sự kiện:

- Số lần TimeLimiter timeout theo tên thao tác.
- Số lần CircuitBreaker ghi nhận thành công, thất bại và slow call.
- Số lời gọi bị từ chối khi breaker OPEN.
- Thời gian phản hồi p50, p95 và p99 của phụ thuộc.
- Số Future hoặc tác vụ blocking còn chạy sau khi caller đã timeout, nếu ứng dụng có thể đo được.
- Tỷ lệ fallback và trạng thái suy giảm mà API trả về.

Nếu timeout tăng nhưng breaker vẫn ở CLOSED, có thể chưa đủ mẫu, failure rate chưa vượt ngưỡng hoặc timeout exception đang bị bỏ qua. Nếu breaker mở nhưng worker vẫn bị chiếm, cần xem lại khả năng hủy và timeout của HTTP client. Nếu API trả fallback nhưng server vẫn thực hiện lệnh ghi, cần xem lại idempotency và cách xử lý trạng thái không chắc chắn.

Các metric của Resilience4j có thể được xuất qua Spring Boot Actuator và Micrometer khi đã bật tích hợp phù hợp. Tên metric cụ thể phụ thuộc phiên bản và registry. Kiểm tra metric thực tế thay vì giả định tên luôn giống nhau giữa các bản.

## 11. Bài thực hành: tách timeout khỏi quyết định ngắt mạch

Tạo một gateway gọi inventory-service và thực hiện các bước:

1. Cấu hình HTTP client timeout để giới hạn thời gian kết nối và chờ phản hồi.
2. Với một lời gọi bất đồng bộ, thêm TimeLimiter có timeoutDuration 2 giây.
3. Cấu hình CircuitBreaker với slowCallDurationThreshold 1,5 giây và slowCallRateThreshold phù hợp.
4. Bọc CompletionStage đã được TimeLimiter giới hạn bằng CircuitBreaker.
5. Tạo một lời gọi phản hồi trong 800 ms và xác nhận thành công.
6. Tạo một lời gọi phản hồi trong 1,8 giây và xác nhận được ghi nhận là slow call nhưng chưa timeout.
7. Tạo một lời gọi kéo dài hơn 2 giây và xác nhận TimeLimiter phát sinh timeout.
8. Tạo nhiều lần gọi chậm/lỗi để breaker chuyển OPEN; xác nhận lời gọi mới bị từ chối nhanh.
9. Phục hồi inventory-service và quan sát các lời gọi thử ở HALF_OPEN.
10. Kiểm tra xem tác vụ blocking có còn chạy sau timeout hay không và điều chỉnh HTTP client timeout, executor hoặc concurrency nếu cần.

Với WebClient, lặp lại bài thực hành bằng Mono.timeout và CircuitBreakerOperator. Xác nhận timeout error đi qua breaker trước khi fallback xử lý. So sánh số liệu giữa hai cách để thấy TimeLimiter/timeout giới hạn từng lần gọi, còn CircuitBreaker sử dụng lịch sử kết quả để bảo vệ những lần gọi tiếp theo.

Khi hoàn thành, bạn cần giải thích được vì sao slow call threshold không phải timeout, TimeLimiter khác timeout của HTTP client ở đâu, cancellation không bảo đảm máy chủ đã dừng xử lý và vì sao breaker cần quan sát lỗi timeout. Phân tách đúng các trách nhiệm này giúp hệ thống giới hạn thời gian chờ của từng request và ngăn phụ thuộc không ổn định gây ra lỗi dây chuyền.

