# timeoutDuration và cancelRunningFuture

Trong tích hợp Spring Cloud CircuitBreaker với Resilience4j, TimeLimiter giới hạn thời gian chờ của một thao tác được bảo vệ. Hai thuộc tính quan trọng nhất là **timeoutDuration** và **cancelRunningFuture**. Thuộc tính thứ nhất đặt thời hạn tối đa mà ứng dụng chờ kết quả; thuộc tính thứ hai quyết định TimeLimiter có yêu cầu hủy Future đang chạy khi thời hạn bị vượt quá hay không.

Hai thuộc tính này giải quyết hai việc khác nhau. Hết thời gian chờ có thể giúp request hiện tại tiếp tục bằng fallback, nhưng điều đó không đồng nghĩa tác vụ phía dưới đã dừng. Hiểu rõ sự khác biệt giữa timeout và cancellation giúp tránh giữ tài nguyên quá lâu, tránh gửi retry trong khi tác vụ cũ vẫn chạy và chọn thời hạn phù hợp với ngân sách độ trễ của hệ thống.

## 1. timeoutDuration là gì?

**timeoutDuration** là khoảng thời gian tối đa TimeLimiter cho phép thao tác được bảo vệ hoàn tất trước khi phát sinh timeout. Trong Resilience4j, giá trị này được biểu diễn bằng **java.time.Duration**. Với cấu hình YAML, có thể dùng dạng thời lượng dễ đọc như **2s**, **500ms** hoặc **1m**.

Ví dụ, nếu **timeoutDuration** được đặt là hai giây, ứng dụng chờ kết quả trong thời hạn đó. Nếu thao tác chưa hoàn tất, TimeLimiter báo timeout để tầng gọi xử lý lỗi hoặc chạy fallback.

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Trong ví dụ, instance TimeLimiter tên **inventory** đặt thời hạn chờ hai giây. Tên instance phải khớp với ID Circuit Breaker mà ứng dụng tạo, chẳng hạn **create("inventory")**, khi sử dụng cấu hình Spring Cloud CircuitBreaker theo ID.

Timeout là giới hạn thời gian chờ của thao tác trong phạm vi tích hợp. Nó không tự động đặt mọi timeout ở tầng mạng hoặc cơ sở dữ liệu. HTTP client vẫn cần connect timeout và response/read timeout phù hợp; JDBC hoặc database driver vẫn cần giới hạn thời gian truy vấn. Những giới hạn ở tầng dưới giúp thao tác I/O thực sự kết thúc thay vì chỉ làm request phía gọi ngừng chờ.

## 2. Khi timeout xảy ra, ứng dụng nhận được gì?

Khi thao tác không hoàn tất trong thời hạn, TimeLimiter phát sinh lỗi timeout, thường được biểu diễn bằng **java.util.concurrent.TimeoutException** trong đường thực thi đồng bộ. Với Spring Cloud CircuitBreaker, lỗi này được chuyển đến hàm fallback của lời gọi nếu ứng dụng cung cấp fallback.

~~~java
import java.util.concurrent.TimeoutException;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> {
                if (error instanceof TimeoutException) {
                    log.warn("Inventory vượt thời gian chờ, sku={}", sku);
                    return inventoryCache.findBySku(sku)
                        .orElseThrow(() ->
                            new InventoryUnavailableException(sku, error)
                        );
                }

                log.warn("Không lấy được tồn kho, sku={}", sku, error);
                return inventoryCache.findBySku(sku)
                    .orElseThrow(() ->
                        new InventoryUnavailableException(sku, error)
                    );
            }
        );
    }
}
~~~

Ví dụ dùng cache khi thao tác lấy tồn kho timeout. Nếu cache không có dữ liệu, ứng dụng ném ngoại lệ nghiệp vụ để tầng API có thể trả phản hồi phù hợp. Không nên trả số lượng bằng 0 chỉ để tránh lỗi nếu số 0 có nghĩa là kho đã được kiểm tra và thực sự hết hàng.

Tùy phiên bản và lớp tích hợp, ngoại lệ timeout có thể được bọc trong một ngoại lệ khác. Khi phân loại lỗi trong fallback, hãy kiểm tra cả nguyên nhân gốc qua **getCause()** nếu cần. Nên log tên Circuit Breaker, loại lỗi và định danh trace để phân biệt timeout với lời gọi bị từ chối do trạng thái OPEN.

## 3. cancelRunningFuture điều khiển điều gì?

**cancelRunningFuture** là cờ cho biết TimeLimiter có yêu cầu hủy Future đang chạy sau khi timeout hay không.

| Giá trị | Hành vi khi hết timeout | Hệ quả cần lưu ý |
|---|---|---|
| **true** | TimeLimiter yêu cầu hủy Future đang chạy. | Có thể giải phóng công việc hoặc tài nguyên sớm hơn nếu tác vụ hỗ trợ hủy. |
| **false** | TimeLimiter không yêu cầu hủy Future đang chạy. | Tác vụ có thể tiếp tục chạy dù caller đã nhận timeout hoặc fallback. |

Ví dụ bật hủy:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Ví dụ không yêu cầu hủy:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      report-generation:
        timeoutDuration: 5s
        cancelRunningFuture: false
~~~

Với **true**, TimeLimiter cố gắng hủy Future khi hết thời hạn. Với **false**, nó kết thúc việc chờ theo giới hạn thời gian nhưng để Future tiếp tục theo cơ chế thực thi của nó. Lựa chọn nào phù hợp phụ thuộc vào tính chất công việc: thao tác đọc có thể hủy an toàn hay tác vụ ghi đã bắt đầu và cần hoàn tất theo quy trình nghiệp vụ.

Điều quan trọng là cancellation là một yêu cầu hủy, không phải cam kết cưỡng chế dừng mọi mã lệnh. Khả năng dừng thực tế phụ thuộc vào loại Future, executor, thư viện client và việc tác vụ có phản ứng với tín hiệu hủy hay không.

## 4. Hủy Future không đồng nghĩa dừng chắc chắn thao tác I/O

Với Future hỗ trợ interrupt, việc hủy thường có thể yêu cầu ngắt thread đang thực thi. Tuy nhiên, thread chỉ dừng đúng cách khi đoạn code và thư viện bên dưới hợp tác với interrupt hoặc có cơ chế hủy riêng.

Một số tình huống thường gặp:

- Một tác vụ Java kiểm tra trạng thái interrupt và thoát có kiểm soát có thể dừng sớm.
- Một lời gọi HTTP đang chờ socket có thể cần connect/read timeout hoặc API hủy request của HTTP client để giải phóng tài nguyên.
- Một truy vấn cơ sở dữ liệu có thể tiếp tục ở database server nếu driver không gửi lệnh cancel hoặc server không xử lý lệnh đó.
- Một yêu cầu đã tới dịch vụ từ xa có thể vẫn được xử lý ở phía server dù client đã ngừng chờ hoặc đóng kết nối.

Đặc biệt, **CompletableFuture.cancel(true)** không đảm bảo thread đang thực thi tác vụ bên dưới bị interrupt. **CompletableFuture** quản lý trạng thái hoàn tất của computation; tham số **mayInterruptIfRunning** không phải cơ chế dừng cưỡng chế computation như nhiều người thường suy luận từ Future truyền thống.

Vì vậy, hãy xem **cancelRunningFuture: true** là nỗ lực hủy công việc phía gọi. Để giới hạn thời gian thực thi thực tế, cần cấu hình timeout ở client, driver hoặc dịch vụ đích. Với thao tác ghi như tạo giao dịch hoặc giữ hàng, cần thêm idempotency key hoặc cơ chế tra cứu trạng thái để xử lý trường hợp caller timeout nhưng server đã hoàn thành thao tác.

## 5. Cấu hình TimeLimiter bằng Java

Có thể cấu hình TimeLimiter trực tiếp bằng **TimeLimiterConfig** và đưa vào builder của Spring Cloud CircuitBreaker Resilience4j.

~~~java
import java.time.Duration;

import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryTimeLimiterConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryTimeLimiter() {
        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .cancelRunningFuture(true)
                .build();

        return factory -> factory.configure(
            builder -> builder.timeLimiterConfig(timeLimiterConfig),
            "inventory"
        );
    }
}
~~~

Trong ví dụ:

- **timeoutDuration(Duration.ofSeconds(2))** đặt thời hạn hai giây.
- **cancelRunningFuture(true)** yêu cầu hủy Future khi timeout.
- **configure(..., "inventory")** áp dụng cấu hình cho Circuit Breaker có ID **inventory**.

Nếu cần một chính sách mặc định cho nhiều ID, có thể dùng **configureDefault** và tạo **Resilience4JConfigBuilder** theo ID. Nếu dùng đồng thời YAML và Java Customizer, cần hiểu thứ tự ưu tiên của phiên bản Spring Cloud/Resilience4j đang triển khai. Tránh khai báo cùng tham số ở nhiều nơi khi chưa xác định nguồn cấu hình hiệu lực.

## 6. Chọn timeoutDuration theo ngân sách độ trễ

Không nên chọn timeout chỉ bằng một con số tùy ý. Hãy bắt đầu từ thời gian phản hồi mà API bên ngoài cam kết, sau đó chia ngân sách cho các bước xử lý và các dependency.

Ví dụ một API đặt hàng có ngân sách phản hồi ba giây:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Xác thực và xử lý nghiệp vụ tại service | 300 ms |
| Gọi Inventory | 900 ms |
| Gọi Pricing | 700 ms |
| Gọi Payment | 800 ms |
| Dự phòng cho serialization và mạng | 300 ms |
| **Tổng** | **3.000 ms** |

Trong ví dụ, TimeLimiter cho Inventory có thể đặt khoảng 900 ms nếu luồng xử lý tuần tự và phần còn lại cần dành cho các bước khác. Nếu các lời gọi chạy song song, ngân sách cần được tính theo thời gian chờ tổng thể và cách kết hợp các Publisher/Future. Không cộng thời lượng một cách máy móc khi các tác vụ thực sự chạy đồng thời.

Cần cân nhắc:

- Độ trễ bình thường và độ trễ ở percentile cao (p95, p99) của dependency.
- Ngân sách phản hồi của API gọi nó.
- Thời gian connect, TLS handshake, gửi request và nhận response.
- Thời gian retry nếu có; retry phải nằm trong tổng ngân sách.
- Thời gian cần cho fallback và trả phản hồi cho caller.

Nếu timeout quá ngắn so với độ trễ bình thường, ứng dụng tạo nhiều timeout giả và có thể mở Circuit Breaker dù dependency vẫn hoạt động. Nếu timeout quá dài, thread, connection và request context có thể bị giữ lâu, làm giảm khả năng phục vụ khi tải tăng.

## 7. Phân biệt TimeLimiter timeout với slow call của Circuit Breaker

TimeLimiter và Circuit Breaker cùng quan tâm đến thời gian nhưng có vai trò khác nhau:

- **TimeLimiter** giới hạn thời gian chờ cho một lần thực thi.
- **Circuit Breaker** quan sát kết quả và độ chậm của nhiều lời gọi trong sliding window để quyết định chuyển trạng thái.

Circuit Breaker có thể cấu hình **slowCallDurationThreshold** và **slowCallRateThreshold**. Một lời gọi vượt ngưỡng thời gian chậm có thể được ghi nhận là slow call dù chưa timeout. Nếu lời gọi vượt **timeoutDuration**, TimeLimiter kết thúc việc chờ và phát lỗi timeout.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        failureRateThreshold: 50
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 2s
        cancelRunningFuture: true
~~~

Ở đây, lời gọi mất 900 ms đã vượt ngưỡng slow call 700 ms nhưng chưa chạm timeout hai giây. Circuit Breaker có thể ghi nhận nó là lời gọi chậm. Nếu lời gọi kéo dài quá hai giây, TimeLimiter báo timeout. Việc timeout có được tính là failure trong Circuit Breaker phụ thuộc vào cách tích hợp và cấu hình ghi nhận exception.

Không đặt timeout ngắn hơn ngưỡng slow call một cách thiếu chủ ý. Nếu TimeLimiter kết thúc lời gọi ở 500 ms nhưng **slowCallDurationThreshold** là một giây, Circuit Breaker có thể chỉ thấy exception timeout thay vì một slow call đủ thời gian. Hãy chọn các ngưỡng theo mục tiêu đo lường: TimeLimiter bảo vệ ngân sách của request; slow-call threshold phát hiện xu hướng độ trễ suy giảm.

## 8. Timeout và retry cần được phối hợp

Retry có thể làm tăng số lần gọi và kéo dài tổng thời gian xử lý. Nếu mỗi lần thử có timeout hai giây và ứng dụng thử ba lần tuần tự, tổng thời gian có thể vượt sáu giây, chưa kể khoảng nghỉ giữa các lần thử.

Một số nguyên tắc:

- Đặt timeout cho từng lần gọi và giới hạn tổng thời gian cho toàn bộ chuỗi retry.
- Chỉ retry lỗi có khả năng phục hồi, chẳng hạn một số lỗi kết nối tạm thời.
- Không retry vô hạn hoặc tiếp tục retry khi Circuit Breaker đã OPEN.
- Với thao tác ghi, dùng idempotency key hoặc cơ chế chống xử lý lặp.
- Tránh để lần gọi cũ tiếp tục chạy sau timeout trong khi retry đã khởi động một lần gọi mới.

Khi **cancelRunningFuture** là **false**, tác vụ cũ có thể tiếp tục chạy sau khi caller timeout. Retry ngay có thể khiến hai thao tác cùng thực hiện đồng thời. Ngay cả khi bật **true**, vẫn phải kiểm tra client có thực sự dừng request cũ hay không.

## 9. TimeLimiter trong lời gọi reactive

Với ứng dụng WebFlux, lời gọi thường trả về **Mono** hoặc **Flux** và việc giới hạn thời gian có thể được biểu diễn trực tiếp trong reactive pipeline bằng toán tử **timeout**. Spring Cloud CircuitBreaker có factory reactive tương ứng để bọc Publisher và xử lý fallback.

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku)
                .timeout(Duration.ofSeconds(2)),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Trong ví dụ, toán tử Reactor **timeout** phát lỗi nếu Publisher không phát tín hiệu cần thiết trong thời hạn. Reactive subscription có thể bị cancel khi timeout hoặc khi subscriber hủy. Đây là cơ chế hủy theo Reactive Streams, khác với việc hủy một Future trong API blocking.

Không nên suy luận rằng **cancelRunningFuture** có cùng tác động đối với mọi reactive client. Với WebClient, cancellation của subscription thường được truyền xuống connector để hủy hoặc đóng request nếu connector hỗ trợ. Dịch vụ từ xa vẫn có thể đã nhận và tiếp tục xử lý request. Hãy kiểm tra hành vi của client/connector và đặt timeout ở tầng HTTP khi cần giới hạn thời gian mạng.

Nếu dùng toán tử **timeout** trước Circuit Breaker, lỗi timeout nằm trong Publisher được bảo vệ và có thể được bộ ngắt ghi nhận. Nếu phục hồi bằng **onErrorResume** trước khi đưa Publisher vào Circuit Breaker, bộ ngắt có thể chỉ quan sát kết quả fallback thành công. Vị trí đặt timeout và fallback vì vậy ảnh hưởng đến metric.

## 10. Quan sát và kiểm chứng timeout

Để biết timeout có đang bảo vệ ứng dụng hiệu quả hay không, hãy theo dõi cả số lần timeout và tình trạng tài nguyên thực thi.

| Tín hiệu | Điều cần quan sát |
|---|---|
| Số lần timeout theo Circuit Breaker ID | Dependency nào thường vượt thời hạn |
| Độ trễ p50, p95 và p99 | Timeout có phù hợp với phân bố độ trễ thực tế không |
| Số Future bị hủy hoặc tác vụ tiếp tục chạy | Cancellation có giải phóng công việc hay không |
| Số thread hoạt động và hàng đợi executor | Tác vụ chậm có làm cạn executor không |
| Kết nối HTTP đang sử dụng | Request timeout có giải phóng connection pool không |
| Số lần fallback | Ứng dụng đang dựa vào dữ liệu dự phòng ở mức nào |
| Trạng thái Circuit Breaker | Timeout có góp phần làm bộ ngắt chuyển OPEN không |

Có thể kiểm chứng với một dependency thử nghiệm có thời gian phản hồi điều khiển được:

1. Gọi endpoint phản hồi trong 300 ms với timeout hai giây; request phải hoàn tất bình thường.
2. Gọi endpoint phản hồi trong ba giây với timeout hai giây; caller phải nhận timeout hoặc fallback trước khi có kết quả bình thường.
3. Bật **cancelRunningFuture: true**, quan sát log và thread để xem tác vụ có phản ứng với cancellation không.
4. Lặp lại với **false** để so sánh tác vụ còn chạy sau khi caller đã timeout.
5. Kiểm tra connection pool, executor và trạng thái dịch vụ đích để xác định tài nguyên có được giải phóng thực tế không.

Không chỉ dựa vào thời điểm caller nhận fallback để kết luận thao tác đã dừng. Hãy quan sát cả phía client và dependency. Đặc biệt với thao tác ghi, kiểm tra trạng thái dữ liệu để biết server có hoàn thành công việc sau khi client timeout hay không.

## 11. Những lỗi cấu hình thường gặp

1. **Đặt timeout quá thấp.** Các lời gọi hợp lệ bị timeout, fallback tăng và Circuit Breaker có thể mở do lỗi nhân tạo.
2. **Đặt timeout quá cao.** Request giữ thread hoặc connection lâu, làm giảm thông lượng khi dependency suy giảm.
3. **Cho rằng cancelRunningFuture=true chắc chắn dừng request từ xa.** Hủy Future là nỗ lực ở phía gọi; client và server phải hỗ trợ việc dừng thực tế.
4. **Để cancelRunningFuture=false nhưng retry ngay.** Tác vụ cũ có thể tiếp tục chạy song song với lần thử mới.
5. **Chỉ dùng TimeLimiter mà bỏ timeout ở HTTP client hoặc database.** I/O bên dưới có thể tiếp tục chiếm tài nguyên sau khi caller đã timeout.
6. **Không phân biệt timeout với Circuit Breaker OPEN.** Timeout là một thao tác được phép nhưng vượt thời hạn; **CallNotPermittedException** là lời gọi bị bộ ngắt từ chối.
7. **Không xem xét slow-call threshold.** TimeLimiter và Circuit Breaker có thể đánh giá độ trễ theo hai ngưỡng khác nhau.
8. **Không xử lý tính không chắc chắn của thao tác ghi.** Caller timeout không chứng minh server chưa thực hiện thao tác; cần idempotency hoặc tra cứu trạng thái.

## 12. Tình huống thực hành

Một ứng dụng đơn hàng gọi Inventory để đọc số lượng tồn kho. Đội vận hành đặt **timeoutDuration = 2s** và **cancelRunningFuture = true**.

Diễn biến:

1. Request đọc tồn kho hoàn tất trong 500 ms. TimeLimiter không can thiệp và response được trả bình thường.
2. Request khác kéo dài hơn hai giây. TimeLimiter báo timeout; Spring Cloud CircuitBreaker gọi fallback để thử lấy dữ liệu cache.
3. TimeLimiter yêu cầu hủy Future đang chạy. Nếu client hỗ trợ cancellation, request hoặc tác vụ có thể dừng sớm; nếu không, thao tác có thể tiếp tục ở nền.
4. Nếu timeout được tích hợp và ghi nhận là lỗi của Circuit Breaker, kết quả này đóng góp vào failure rate theo exception policy.
5. Nếu nhiều lần timeout làm tỷ lệ lỗi vượt ngưỡng sau khi đủ mẫu, Circuit Breaker có thể chuyển OPEN và từ chối các lời gọi tiếp theo.

Khi đổi **cancelRunningFuture** thành **false**, caller vẫn có thể nhận timeout và fallback sau hai giây, nhưng Future được phép tiếp tục chạy. Nếu ứng dụng lập tức retry, có nguy cơ tạo thêm tải trong lúc tác vụ cũ chưa kết thúc.

Qua tình huống này, cần xác định riêng ba kết quả: thời điểm caller ngừng chờ, trạng thái thực tế của tác vụ phía client và trạng thái xử lý ở dịch vụ Inventory. Ba thời điểm đó có thể khác nhau.

## Kết luận

**timeoutDuration** đặt thời gian tối đa mà ứng dụng chờ thao tác được bảo vệ; **cancelRunningFuture** quyết định TimeLimiter có yêu cầu hủy Future khi timeout hay không. Hãy chọn timeout theo ngân sách độ trễ của request, đồng bộ với timeout của HTTP client hoặc database, và kiểm chứng khả năng cancellation của thư viện thực thi. Timeout giúp caller tiếp tục bằng fallback, còn việc tác vụ thật sự dừng cần được xác nhận ở tầng client và dịch vụ phụ thuộc.
