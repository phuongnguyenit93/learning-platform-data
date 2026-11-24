# Phân biệt Circuit Breaker, timeout, retry, Bulkhead và Rate Limiter

Trong hệ thống microservices, một lời gọi đến dịch vụ phụ thuộc có thể chậm, lỗi hoặc bị quá tải. Nếu nhiều request tiếp tục chờ và thử gọi lại, tài nguyên của dịch vụ gọi cũng dần cạn kiệt; sự cố ban đầu có thể lan thành lỗi dây chuyền. Spring Cloud CircuitBreaker kết hợp Resilience4j cung cấp các cơ chế bảo vệ để giới hạn tác động đó.

Circuit Breaker, timeout, retry, Bulkhead và Rate Limiter thường được dùng cùng nhau, nhưng mỗi cơ chế giải quyết một vấn đề khác nhau:

- **Circuit Breaker** quan sát kết quả các lời gọi gần đây và tạm ngừng gọi một dependency khi tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng.
- **Timeout** giới hạn thời gian một lời gọi được phép chờ.
- **Retry** thực hiện lại lời gọi khi gặp lỗi có khả năng tạm thời.
- **Bulkhead** giới hạn số lời gọi đồng thời để một dependency không chiếm hết tài nguyên.
- **Rate Limiter** giới hạn số lời gọi được chấp nhận trong một khoảng thời gian.

Hiểu rõ ranh giới giữa chúng giúp chọn đúng cơ chế, cấu hình hợp lý và tránh vô tình khuếch đại sự cố.

## 1. Circuit Breaker: ngừng gọi khi dependency có dấu hiệu mất ổn định

Circuit Breaker theo dõi kết quả các lời gọi đến một dependency trong một cửa sổ thống kê. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng cấu hình, nó chuyển sang trạng thái OPEN và từ chối lời gọi mới trong một khoảng thời gian. Ứng dụng có thể trả về fallback hoặc thông báo lỗi có kiểm soát thay vì tiếp tục chờ một dịch vụ đang gặp sự cố.

Circuit Breaker thường có ba trạng thái:

| Trạng thái | Hành vi | Chuyển trạng thái |
|---|---|---|
| CLOSED | Cho phép lời gọi đi đến dependency và ghi nhận kết quả | Chuyển sang OPEN khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng |
| OPEN | Từ chối nhanh lời gọi mới; không gửi request đến dependency | Chuyển sang HALF_OPEN sau thời gian chờ đã cấu hình |
| HALF_OPEN | Chỉ cho phép một số lượng nhỏ lời gọi thăm dò | Trở về CLOSED nếu dependency phục hồi; chuyển lại OPEN nếu các lời gọi thăm dò vẫn thất bại hoặc quá chậm |

Ở trạng thái OPEN, lời gọi bị từ chối thường được biểu diễn bằng lỗi kiểu CallNotPermittedException trong Resilience4j. Đây là kết quả của cơ chế bảo vệ, không nhất thiết là một request đã được gửi đến dịch vụ đích.

### Sliding window hoạt động thế nào?

Circuit Breaker cần một tập kết quả gần đây để quyết định khi nào mở mạch. Resilience4j hỗ trợ hai kiểu cửa sổ:

- **COUNT_BASED**: thống kê trên N lời gọi gần nhất. Ví dụ, cửa sổ có 20 lời gọi sẽ giữ kết quả của tối đa 20 lời gọi gần nhất.
- **TIME_BASED**: thống kê trên một khoảng thời gian gần nhất. Ví dụ, cửa sổ 10 giây tính các kết quả được ghi nhận trong 10 giây vừa qua.

Cần phân biệt kích thước cửa sổ với số lời gọi tối thiểu. Nếu cấu hình cửa sổ 20 lời gọi nhưng chỉ có 3 lời gọi được thực hiện, Circuit Breaker có thể chưa đủ dữ liệu để tính tỷ lệ. Thuộc tính minimumNumberOfCalls quy định số mẫu tối thiểu trước khi đánh giá ngưỡng.

Circuit Breaker có thể mở mạch dựa trên hai nhóm tín hiệu:

- **Failure rate**: tỷ lệ lời gọi thất bại trong cửa sổ đạt failureRateThreshold.
- **Slow call rate**: tỷ lệ lời gọi vượt quá slowCallDurationThreshold đạt slowCallRateThreshold.

Ví dụ, slowCallDurationThreshold là 2 giây và slowCallRateThreshold là 50% nghĩa là nếu ít nhất một nửa số lời gọi trong cửa sổ mất từ 2 giây trở lên, Circuit Breaker có thể mở mạch, ngay cả khi các lời gọi đó cuối cùng vẫn thành công. Điều này hữu ích khi dependency chưa hỏng hoàn toàn nhưng phản hồi chậm đến mức gây áp lực lên luồng xử lý.

Thời gian OPEN được điều khiển bởi waitDurationInOpenState. Khi hết thời gian này, Circuit Breaker cho phép một số lời gọi thăm dò ở HALF_OPEN, được giới hạn bởi permittedNumberOfCallsInHalfOpenState. Cấu hình số lời gọi thăm dò nhỏ giúp kiểm tra khả năng phục hồi mà không tạo thêm tải lớn lên dependency.

## 2. Timeout: giới hạn thời gian chờ của một lời gọi

Timeout đặt giới hạn cho thời gian chờ một thao tác hoàn tất. Nếu quá thời hạn, lời gọi được xem là hết thời gian và tầng gọi có thể xử lý lỗi timeout hoặc chuyển sang fallback.

Ví dụ, dịch vụ đơn hàng gọi dịch vụ tồn kho với timeout 2 giây. Nếu dịch vụ tồn kho chưa phản hồi sau 2 giây, dịch vụ đơn hàng ngừng chờ kết quả theo chính sách đã cấu hình và tiếp tục xử lý lỗi. Timeout giúp request không giữ thread, connection hoặc tài nguyên liên quan quá lâu.

Timeout khác Circuit Breaker ở phạm vi quyết định:

- Timeout xử lý một lần chờ cụ thể. Nó không cần đợi nhiều request thất bại mới có tác dụng.
- Circuit Breaker quan sát nhiều kết quả gần đây. Khi dependency có dấu hiệu mất ổn định, nó ngăn các request tiếp theo tiếp tục đi vào dependency.

Hai cơ chế bổ trợ cho nhau. Timeout tạo ra giới hạn thời gian cho từng lần gọi; Circuit Breaker có thể dùng các lỗi timeout và số liệu lời gọi chậm làm tín hiệu để mở mạch.

Cần cấu hình timeout ở đúng tầng. Với HTTP client, nên đặt connect timeout và response/read timeout phù hợp với thư viện đang dùng. Với luồng Reactor, toán tử timeout có thể giới hạn thời gian phát tín hiệu của Mono hoặc Flux. Với Future hoặc CompletionStage, Resilience4j TimeLimiter có thể quản lý thời gian chờ.

Một timeout ở phía caller không phải lúc nào cũng bảo đảm công việc phía server đã bị dừng. Việc hủy request, ngắt Future hoặc dừng truy vấn phụ thuộc vào client, giao thức và cách triển khai phía server. Vì vậy, timeout cần được phối hợp với timeout ở các tầng mạng và dịch vụ đích.

## 3. Retry: thử lại khi lỗi có thể chỉ là tạm thời

Retry thực hiện lại một thao tác sau khi lần gọi trước thất bại. Cơ chế này phù hợp với lỗi ngắn hạn như mất kết nối thoáng qua, lỗi gateway tạm thời hoặc phản hồi 503 trong một khoảng thời gian ngắn.

Retry không làm dependency phục hồi và cũng không ngăn lỗi dây chuyền. Nếu dependency đang quá tải, nhiều caller cùng retry có thể tạo thêm request, khiến tình trạng quá tải nghiêm trọng hơn. Vì vậy, retry cần có giới hạn:

- Giới hạn tổng số lần thử. Trong Resilience4j, maxAttempts bao gồm cả lần gọi đầu tiên.
- Dùng khoảng chờ giữa các lần thử; với hệ thống có nhiều caller, nên cân nhắc exponential backoff và jitter để tránh tất cả caller retry cùng thời điểm.
- Chỉ retry các lỗi có khả năng tạm thời. Lỗi xác thực, dữ liệu không hợp lệ hoặc quy tắc nghiệp vụ thường không thể được khắc phục bằng cách gọi lại.
- Chỉ retry thao tác an toàn hoặc có cơ chế idempotency. Gửi lại một lệnh tạo đơn hàng hoặc trừ tiền có thể tạo tác động trùng lặp nếu lần đầu đã được xử lý nhưng response bị mất.
- Đặt ngân sách thời gian tổng thể cho cả chuỗi thử lại. Tổng thời gian retry không được vượt quá deadline mà request phía trên có thể chấp nhận.

Retry và Circuit Breaker có thể được kết hợp theo nhiều thứ tự. Thứ tự ảnh hưởng đến cách thống kê:

- Circuit Breaker bọc Retry: Circuit Breaker quan sát kết quả cuối cùng của cả thao tác logic. Một chuỗi có nhiều lần thử nhưng chỉ một kết quả cuối cùng được ghi nhận.
- Retry bọc Circuit Breaker: mỗi lần thử đi qua Circuit Breaker, do đó từng lần thất bại có thể được ghi nhận riêng. Khi mạch đã OPEN, lần thử tiếp theo có thể bị từ chối ngay.

Không có thứ tự duy nhất phù hợp cho mọi hệ thống. Hãy chọn dựa trên cách muốn đo lỗi, giới hạn số request phát sinh và deadline của nghiệp vụ. Dù chọn cách nào, retry vẫn cần giới hạn chặt để không làm tăng tải khi dependency đang suy giảm.

## 4. Bulkhead: cô lập tài nguyên và giới hạn lời gọi đồng thời

Bulkhead giới hạn số thao tác có thể chạy đồng thời trên một dependency hoặc một nhóm tài nguyên. Ý tưởng này tương tự các khoang kín trên tàu: sự cố ở một khoang không làm toàn bộ tàu bị ngập.

Giả sử dịch vụ tổng hợp gọi ba dependency: hồ sơ khách hàng, tồn kho và gợi ý sản phẩm. Nếu tất cả cùng dùng chung một nhóm thread không giới hạn, các lời gọi tồn kho bị treo có thể chiếm hết thread và làm cả hai dependency còn lại không thể được xử lý. Bulkhead tạo giới hạn riêng để một dependency không chiếm hết năng lực xử lý.

Resilience4j cung cấp các kiểu Bulkhead phổ biến:

- **SemaphoreBulkhead** giới hạn số lời gọi đồng thời bằng semaphore. Lời gọi có thể bị từ chối ngay hoặc chờ một khoảng thời gian ngắn để lấy quyền thực thi.
- **FixedThreadPoolBulkhead** dùng thread pool và hàng đợi có kích thước giới hạn. Nó tách việc thực thi khỏi thread gọi, nhưng cần cân nhắc kích thước pool, hàng đợi và chi phí chuyển đổi thread.

Bulkhead kiểm soát **số thao tác đang chạy cùng lúc**, còn Rate Limiter kiểm soát **số thao tác trong một khoảng thời gian**. Một hệ thống có thể nhận 100 request mỗi giây nhưng chỉ cho phép 10 request đồng thời đến một dependency. Hai giới hạn này giải quyết hai chiều tải khác nhau.

Bulkhead không phát hiện dependency đang lỗi. Nó chỉ giới hạn mức tài nguyên mà các lời gọi có thể tiêu thụ. Khi hết slot, ứng dụng cần quyết định từ chối nhanh, trả fallback hoặc chờ trong một thời gian rất ngắn. Hàng đợi chờ quá dài có thể chỉ chuyển điểm nghẽn sang nơi khác.

## 5. Rate Limiter: giới hạn tốc độ tiếp nhận lời gọi

Rate Limiter giới hạn số lần một thao tác được phép thực hiện trong một chu kỳ. Ví dụ, dịch vụ chỉ cấp tối đa 50 quyền gọi dịch vụ đối tác trong mỗi giây. Khi hết quyền, request mới có thể bị từ chối hoặc chờ đến khi có quyền tiếp theo, tùy cấu hình.

Trong Resilience4j, RateLimiter thường được cấu hình bằng các thuộc tính như:

- limitForPeriod: số quyền được cấp trong mỗi chu kỳ.
- limitRefreshPeriod: thời lượng của một chu kỳ cấp quyền.
- timeoutDuration: thời gian tối đa caller chờ để nhận quyền.

Rate Limiter hữu ích khi cần bảo vệ quota của API bên ngoài, giới hạn tốc độ theo chính sách sản phẩm hoặc điều tiết tải đến một dependency. Nó không tự đánh giá dependency có khỏe hay không. Một dịch vụ có thể đang hoạt động tốt nhưng caller vẫn bị giới hạn vì đã dùng hết quota.

Rate Limiter cũng không giới hạn số lời gọi đang chạy đồng thời. Nếu mỗi request mất 30 giây, ngay cả tốc độ 10 request mỗi giây vẫn có thể tạo ra hàng trăm request đồng thời. Khi cần giới hạn cả tốc độ và số thao tác đang chạy, hãy kết hợp Rate Limiter với Bulkhead.

## 6. So sánh nhanh năm cơ chế

| Cơ chế | Kiểm soát điều gì? | Tác dụng chính | Khi nên dùng |
|---|---|---|---|
| Circuit Breaker | Tỷ lệ lỗi và lời gọi chậm trong cửa sổ thống kê | Ngừng gửi request khi dependency có dấu hiệu mất ổn định | Dependency thường xuyên lỗi hoặc phản hồi chậm; cần ngăn lỗi dây chuyền |
| Timeout | Thời gian chờ của một lời gọi | Giải phóng luồng xử lý khỏi việc chờ vô hạn hoặc quá lâu | Mọi lời gọi mạng hoặc thao tác có thời gian phản hồi không chắc chắn |
| Retry | Số lần thử lại sau lỗi | Vượt qua lỗi tạm thời | Lỗi có khả năng tự hết, thao tác an toàn khi thực hiện lại |
| Bulkhead | Số lời gọi đồng thời hoặc tài nguyên thực thi | Cô lập tải và giới hạn mức chiếm dụng tài nguyên | Dependency chậm có thể chiếm thread, connection hoặc worker |
| Rate Limiter | Số lời gọi trong một chu kỳ | Điều tiết tốc độ và bảo vệ quota | API có giới hạn lưu lượng hoặc cần giới hạn tốc độ gửi request |

Có thể ghi nhớ bằng năm câu hỏi:

1. Dependency có đang lỗi hoặc chậm trên diện rộng không? Dùng Circuit Breaker.
2. Một lần gọi được phép chờ bao lâu? Dùng Timeout.
3. Lỗi này có thể tự hết nếu thử lại không? Dùng Retry.
4. Tối đa bao nhiêu lời gọi được chạy cùng lúc? Dùng Bulkhead.
5. Tối đa bao nhiêu lời gọi được gửi trong một giây hoặc một phút? Dùng Rate Limiter.

## 7. Tích hợp với Spring Cloud CircuitBreaker và Resilience4j

Trong ứng dụng Spring Boot, có thể dùng Spring Cloud CircuitBreaker với implementation Resilience4j. Với lời gọi reactive dựa trên Reactor, starter thường dùng là spring-cloud-starter-circuitbreaker-reactor-resilience4j. Hãy quản lý phiên bản Spring Cloud bằng BOM tương thích với phiên bản Spring Boot của dự án.

Ví dụ cấu hình một Circuit Breaker cho dependency tồn kho:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
  retry:
    instances:
      inventory:
        maxAttempts: 2
        waitDuration: 100ms
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
  ratelimiter:
    instances:
      inventory:
        limitForPeriod: 50
        limitRefreshPeriod: 1s
        timeoutDuration: 0s
~~~

Với cấu hình minh họa này, Circuit Breaker thống kê tối đa 20 lời gọi gần nhất và chỉ bắt đầu đánh giá sau ít nhất 10 lời gọi. Mạch mở khi tỷ lệ lỗi đạt 50% hoặc tỷ lệ lời gọi chậm đạt 50%, theo các ngưỡng đã đặt. Sau 10 giây ở OPEN, tối đa 3 lời gọi thăm dò được phép chạy ở HALF_OPEN. Retry cho phép tối đa 2 lần thử tổng cộng; Bulkhead giới hạn 20 lời gọi đồng thời; Rate Limiter cấp 50 quyền trong mỗi giây.

Các giá trị trên chỉ là ví dụ để giải thích cách cấu hình. Hãy điều chỉnh theo lưu lượng thực tế, SLA, độ trễ của dependency và deadline của request. Nếu timeout không được cấu hình phù hợp, một lời gọi có thể giữ slot Bulkhead quá lâu. Nếu retry quá nhiều, nó có thể làm tăng số request và thời gian xử lý vượt ngân sách của caller.

Ví dụ sau minh họa cách dùng ReactiveCircuitBreakerFactory để bảo vệ một lời gọi WebClient. Toán tử timeout giới hạn thời gian chờ của Mono; Circuit Breaker quan sát kết quả của lời gọi và chuyển sang fallback khi có lỗi hoặc khi lời gọi bị từ chối do mạch đang OPEN.

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryClient(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClient;
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }

    public Mono<Inventory> findInventory(String productId) {
        Mono<Inventory> request = webClient.get()
                .uri("/inventory/{productId}", productId)
                .retrieve()
                .bodyToMono(Inventory.class)
                .timeout(Duration.ofSeconds(2));

        return inventoryBreaker.run(
                request,
                error -> fallback(productId, error)
        );
    }

    private Mono<Inventory> fallback(String productId, Throwable cause) {
        // Có thể đọc cache hoặc trả kết quả suy giảm phù hợp với nghiệp vụ.
        return Mono.just(Inventory.unavailable(productId));
    }
}
~~~

Trong ví dụ, tên cấu hình inventory phải khớp với ID được truyền vào factory. Phương thức fallback cần trả về kiểu dữ liệu tương thích với luồng chính. Trong ứng dụng thực tế, hãy ghi log nguyên nhân fallback và phân biệt lỗi kỹ thuật với lỗi nghiệp vụ. Ví dụ, một response 404 có thể mang ý nghĩa sản phẩm không tồn tại; không nên tự động biến mọi 404 thành trạng thái dependency bị lỗi nếu đó là kết quả nghiệp vụ bình thường.

Fallback cũng cần được thiết kế cẩn thận. Một fallback đọc từ dịch vụ từ xa khác có thể tạo thêm một điểm lỗi mới. Ưu tiên dữ liệu cache, giá trị mặc định an toàn hoặc phản hồi suy giảm có ý nghĩa với người dùng. Không trả dữ liệu giả như thể đó là dữ liệu mới nhất nếu nghiệp vụ không cho phép.

## 8. Kết hợp các cơ chế trong một luồng gọi

Một luồng gọi đến dependency có thể được bảo vệ theo các lớp sau:

1. **Rate Limiter** kiểm tra caller còn quyền gửi request trong chu kỳ hiện tại hay không.
2. **Bulkhead** kiểm tra còn slot đồng thời để thực thi lời gọi hay không.
3. **Timeout** giới hạn thời gian chờ cho lần gọi đến dependency.
4. **Retry** chỉ thử lại khi gặp nhóm lỗi được cho phép và còn ngân sách thời gian.
5. **Circuit Breaker** quyết định có cho phép lời gọi đi tiếp dựa trên trạng thái và số liệu gần đây.
6. **Fallback** tạo phản hồi thay thế khi không thể lấy kết quả từ dependency.

Đây là cách phân chia trách nhiệm để thiết kế, không phải thứ tự bắt buộc cho mọi thư viện hoặc mọi cấu hình. Khi dùng decorator của Resilience4j, thứ tự lồng nhau quyết định lớp nào nhìn thấy từng lần thử và lớp nào chỉ nhìn thấy kết quả cuối cùng. Hãy kiểm tra thứ tự áp dụng trong cấu hình thực tế.

Đặc biệt, cần phân biệt timeout của từng lần thử với deadline tổng thể của request. Ví dụ, timeout mỗi lần gọi là 2 giây và retry thêm một lần có thể khiến thao tác kéo dài hơn 2 giây, chưa kể thời gian chờ giữa các lần thử. Nếu request phía trên chỉ cho phép 3 giây, phải giới hạn toàn bộ chuỗi xử lý trong deadline đó.

## 9. Theo dõi hiệu quả bảo vệ

Resilience4j có thể tích hợp với Micrometer và Spring Boot Actuator để xuất số liệu. Tùy dependency và cấu hình của ứng dụng, các số liệu có thể được đưa vào hệ thống giám sát như Prometheus và hiển thị bằng Grafana.

Nên theo dõi ít nhất:

- Trạng thái Circuit Breaker và số lần chuyển CLOSED, OPEN, HALF_OPEN.
- Số lời gọi thành công, thất bại, chậm và bị từ chối do Circuit Breaker đang OPEN.
- Số lần retry, số chuỗi retry cạn lượt và thời gian xử lý sau retry.
- Số timeout và độ trễ của dependency.
- Số lời gọi bị Bulkhead từ chối, mức sử dụng slot và thời gian chờ.
- Số quyền Rate Limiter được cấp, số request bị giới hạn.
- Tỷ lệ fallback và chất lượng phản hồi suy giảm mà người dùng nhận được.

Đừng chỉ nhìn vào tỷ lệ lỗi tổng thể. Nếu Circuit Breaker liên tục OPEN, cần kiểm tra sức khỏe dependency, timeout và ngưỡng cấu hình. Nếu Bulkhead thường xuyên từ chối, cần xem lại độ trễ, mức đồng thời và giới hạn tài nguyên. Nếu retry tăng mạnh, hãy kiểm tra lỗi gốc và khả năng khuếch đại lưu lượng. Nếu fallback tăng nhưng dashboard vẫn báo request thành công, cần hiển thị riêng tỷ lệ phản hồi fallback để tránh che khuất sự cố.

## 10. Những lỗi thiết kế thường gặp

- **Chỉ dùng Retry để xử lý dependency quá tải**: request được gửi thêm có thể làm dependency quá tải hơn. Hãy kết hợp timeout, Circuit Breaker và giới hạn retry.
- **Không đặt Timeout**: thread, connection hoặc slot Bulkhead có thể bị giữ quá lâu.
- **Dùng cùng một Circuit Breaker cho nhiều dependency không liên quan**: lỗi ở một dịch vụ có thể làm gián đoạn lời gọi đến dịch vụ khác. Nên chọn ID và cấu hình theo dependency hoặc nhóm thao tác có cùng đặc tính.
- **Mở Circuit Breaker vì lỗi nghiệp vụ bình thường**: cần phân loại exception để các lỗi như dữ liệu không tồn tại hoặc request không hợp lệ không làm sai tỷ lệ lỗi kỹ thuật.
- **Đặt Bulkhead quá lớn hoặc hàng đợi quá dài**: giới hạn mất tác dụng hoặc request tiếp tục tích tụ và hết hạn ở phía trên.
- **Chỉ dùng Rate Limiter để giới hạn concurrency**: tốc độ theo thời gian và số thao tác đồng thời là hai đại lượng khác nhau.
- **Fallback che giấu dữ liệu lỗi thời hoặc không chính xác**: phản hồi suy giảm phải được xác định rõ và có thể quan sát qua metric, log.
- **Cấu hình ngưỡng mà không dựa trên số liệu**: sliding window quá nhỏ dễ dao động; ngưỡng quá cao có thể mở mạch muộn, còn ngưỡng quá thấp có thể mở mạch khi chỉ có vài lỗi ngẫu nhiên.

## 11. Quy trình chọn và tinh chỉnh

Khi bảo vệ một lời gọi từ dịch vụ A sang dịch vụ B, có thể thực hiện theo trình tự:

1. Xác định deadline của request từ A và thời gian phản hồi mục tiêu của B.
2. Đặt timeout cho lời gọi, bảo đảm còn thời gian để A xử lý lỗi hoặc fallback.
3. Xác định lỗi nào có thể retry, kiểm tra tính idempotent và giới hạn số lần thử.
4. Đặt Bulkhead dựa trên khả năng chịu tải và tài nguyên dành cho B.
5. Đặt Rate Limiter nếu có quota hoặc giới hạn tốc độ cần tuân thủ.
6. Bật Circuit Breaker với sliding window, số mẫu tối thiểu, ngưỡng lỗi/lời gọi chậm và thời gian OPEN phù hợp.
7. Xây dựng fallback có ý nghĩa nghiệp vụ và đo riêng tỷ lệ sử dụng fallback.
8. Quan sát metric trong điều kiện tải bình thường và khi dependency suy giảm; điều chỉnh cấu hình dựa trên dữ liệu.

Các cơ chế này tạo thành nhiều lớp bảo vệ bổ sung cho nhau. Timeout giới hạn thời gian chờ; Retry xử lý một số lỗi tạm thời; Bulkhead giới hạn tài nguyên đồng thời; Rate Limiter điều tiết tốc độ; Circuit Breaker ngăn lời gọi tiếp tục dồn vào dependency đang mất ổn định. Kết hợp đúng cách giúp Spring Cloud bảo vệ dịch vụ gọi, giảm nguy cơ lỗi dây chuyền và duy trì phản hồi có kiểm soát khi hệ thống phụ thuộc gặp sự cố.
