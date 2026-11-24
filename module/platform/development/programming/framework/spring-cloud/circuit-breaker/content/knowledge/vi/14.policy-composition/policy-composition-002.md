# Thử lại lỗi tạm thời và bỏ qua lỗi nghiệp vụ hoặc mạch đang mở

Trong ứng dụng Spring Cloud CircuitBreaker tích hợp Resilience4j, Retry và Circuit Breaker thường được phối hợp để xử lý hai tình huống khác nhau. Retry thử lại một lời gọi khi lỗi có khả năng chỉ xảy ra tạm thời; Circuit Breaker ngăn ứng dụng tiếp tục gọi một dịch vụ phụ thuộc đang có dấu hiệu không khỏe. Việc phân loại exception quyết định lỗi nào được thử lại, lỗi nào được ghi nhận vào failure rate và lỗi nào cần dừng ngay.

Lỗi nghiệp vụ như mã sản phẩm không hợp lệ hoặc không đủ hàng thường không thể khắc phục bằng cách gọi lại. Tương tự, **CallNotPermittedException** cho biết Circuit Breaker đang từ chối lời gọi vì mạch đã mở hoặc không cấp thêm lượt thăm dò. Nếu Retry tiếp tục thử loại lỗi này, ứng dụng chỉ tạo thêm công việc mà không giúp dependency phục hồi. Bài học này trình bày cách cấu hình exception policy và chọn thứ tự phối hợp hai cơ chế.

## 1. Phân biệt lỗi tạm thời và lỗi không nên thử lại

Trước khi cấu hình Retry, hãy xác định ý nghĩa của từng lỗi theo hợp đồng của dịch vụ phụ thuộc.

| Nhóm lỗi | Ví dụ | Hành vi thường phù hợp |
|---|---|---|
| Lỗi hạ tầng tạm thời | Kết nối bị reset, một số lỗi connect timeout, HTTP 503 tạm thời | Có thể thử lại với số lần giới hạn và khoảng nghỉ |
| Lỗi nghiệp vụ | SKU không tồn tại, số lượng không đủ, đơn hàng đã bị hủy | Trả kết quả hoặc lỗi nghiệp vụ; không retry |
| Lỗi xác thực/phân quyền | HTTP 401 hoặc 403 | Không retry nếu thông tin xác thực không thay đổi |
| Lỗi đầu vào | Thiếu SKU, quantity âm, định dạng sai | Từ chối request trước khi gọi dependency |
| Circuit Breaker từ chối | **CallNotPermittedException** | Dừng retry; chờ Circuit Breaker cho phép lại |
| Lỗi lập trình hoặc mapping nội bộ | NullPointerException do code ứng dụng, mapper lỗi | Điều tra và sửa nguyên nhân; không tự động retry mọi trường hợp |

Một lỗi chỉ nên được retry khi có khả năng lần thử tiếp theo thành công mà không cần thay đổi dữ liệu đầu vào hoặc trạng thái nghiệp vụ. Ví dụ, kết nối bị ngắt trong lúc dịch vụ Inventory vẫn khỏe có thể là lỗi tạm thời. Ngược lại, yêu cầu giữ 10 sản phẩm trong khi kho chỉ còn 4 sản phẩm là kết quả nghiệp vụ; gửi lại cùng yêu cầu không làm số hàng tăng lên.

Một số timeout cũng có thể được thử lại, nhưng phải cân nhắc liệu thao tác đã được dịch vụ đích thực hiện hay chưa. Với thao tác ghi, client có thể timeout sau khi server đã hoàn tất. Retry không có idempotency key có thể tạo giao dịch hoặc giữ hàng hai lần. Vì vậy, phân loại lỗi phải dựa trên cả tính chất exception và khả năng lặp an toàn của operation.

## 2. Cấu hình Retry chỉ cho exception tạm thời

Resilience4j Retry cho phép đặt số lần thử tối đa, khoảng chờ giữa các lần thử và danh sách exception cần retry hoặc bỏ qua. Ví dụ sau cho phép tối đa ba lần thực thi, tính cả lần đầu:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
          - java.net.ConnectException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
~~~

Trong ví dụ:

- **maxAttempts: 3** gồm lần gọi đầu tiên và tối đa hai lần thử lại.
- **waitDuration: 200ms** đặt khoảng chờ giữa các lần thử.
- **retryExceptions** liệt kê những lỗi có khả năng tạm thời và được phép thử lại.
- **ignoreExceptions** liệt kê lỗi nghiệp vụ và lỗi từ chối của Circuit Breaker mà Retry phải bỏ qua.

Khi khai báo danh sách **retryExceptions**, hãy xem đó là chính sách cho các loại lỗi được phép retry. Danh sách **ignoreExceptions** thể hiện rõ các trường hợp không được thử lại. Exception policy cần phù hợp với phiên bản Resilience4j đang dùng và các exception thực tế mà HTTP client hoặc service layer phát ra; đôi khi lỗi cần phân loại nằm ở cause bên trong exception bọc ngoài.

Không nên cấu hình retry cho mọi exception. Nếu Retry thử lại cả lỗi xác thực, dữ liệu sai, lỗi nghiệp vụ hoặc lỗi lập trình, ứng dụng sẽ tăng tải và kéo dài thời gian phản hồi mà không tăng khả năng thành công.

## 3. Bỏ qua lỗi nghiệp vụ ở cả Retry và Circuit Breaker

Retry và Circuit Breaker có bộ quy tắc ghi nhận exception riêng:

- Retry quyết định exception nào khiến nó thực hiện thêm một lần gọi.
- Circuit Breaker quyết định exception nào được tính là kết quả thất bại trong sliding window.

Vì vậy, nếu lỗi nghiệp vụ không nên làm tăng failure rate, chỉ thêm nó vào **ignoreExceptions** của Retry là chưa đủ. Cần khai báo bỏ qua lỗi đó ở cả hai cơ chế.

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
~~~

Khi Inventory trả **InsufficientStockException**, Retry không thử lại. Circuit Breaker cũng không tính exception này là một lần thất bại để đánh giá tỷ lệ lỗi. Kết quả nghiệp vụ vẫn được chuyển về tầng gọi để ứng dụng trả phản hồi phù hợp.

Các exception được bỏ qua bởi Circuit Breaker không được tính là thành công hoặc thất bại trong đánh giá tỷ lệ lỗi. Nhờ đó, lỗi nghiệp vụ không làm méo tín hiệu về sức khỏe của dependency. Những lỗi hạ tầng khác vẫn được ghi nhận theo chính sách Circuit Breaker.

**CallNotPermittedException** được thêm vào danh sách bỏ qua của Retry để ngăn retry khi exception này đi qua Retry. Bản thân Circuit Breaker phát sinh lỗi từ chối; đây không phải lỗi mới do Inventory trả về để bộ ngắt tự ghi nhận như một kết quả thất bại khác.

## 4. Phân biệt lỗi tạm thời với CallNotPermittedException

Khi Circuit Breaker ở OPEN, lời gọi mới bị từ chối trước khi supplier gọi dịch vụ phụ thuộc. Resilience4j thường phát sinh **CallNotPermittedException**. Trường hợp tương tự có thể xảy ra ở HALF_OPEN khi số lượt thăm dò được cấp đã được sử dụng hết.

Đây là tín hiệu cho biết cơ chế bảo vệ đang hoạt động. Retry không nên xem nó là lỗi kết nối tạm thời và tiếp tục thử lại sau vài trăm mili giây. Việc thử lại liên tục có thể:

- Tạo nhiều exception và log không cần thiết.
- Làm tăng độ trễ của request.
- Tạo tải cho ứng dụng gọi trong khi dependency vẫn chưa được cho phép nhận request.
- Gây thêm áp lực đúng lúc hệ thống đang cần giảm tải.

Thời điểm thử lại phù hợp do Circuit Breaker kiểm soát thông qua thời gian OPEN và quá trình chuyển sang HALF_OPEN. Khi mạch mở, ứng dụng nên chạy fallback hoặc trả lỗi có thể thử lại cho caller. Khi Circuit Breaker cho phép probe, một số lời gọi thăm dò sẽ kiểm tra khả năng phục hồi của dependency.

Nếu dùng Retry bên ngoài Circuit Breaker, cần đưa **CallNotPermittedException** vào **ignoreExceptions** của Retry để dừng ngay khi bộ ngắt từ chối. Nếu Circuit Breaker nằm ngoài Retry, exception từ chối được phát ra trước khi supplier chứa Retry chạy; Retry không nhìn thấy lỗi này. Hai thứ tự có hành vi khác nhau và cần được chọn có chủ đích.

## 5. Thứ tự phối hợp Retry và Circuit Breaker

Thứ tự lồng nhau quyết định Circuit Breaker ghi nhận từng lần thử hay ghi nhận một kết quả tổng hợp của cả lần gọi logic.

### Circuit Breaker bên ngoài, Retry bên trong

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> retry.executeSupplier(
        () -> inventoryClient.getStock(sku)
    ),
    error -> fallback(sku, error)
);
~~~

Luồng xử lý:

1. Circuit Breaker kiểm tra trạng thái trước khi chạy supplier.
2. Nếu đang OPEN, supplier không chạy và fallback được gọi.
3. Nếu được phép, Retry thực hiện lời gọi đầu tiên và thử lại các exception tạm thời theo cấu hình.
4. Khi Retry thành công, Circuit Breaker nhận một kết quả thành công.
5. Nếu Retry hết số lần mà vẫn thất bại, Circuit Breaker nhận exception cuối cùng của lần gọi logic.

Với thứ tự này, một request logic chỉ tạo một kết quả trong sliding window của Circuit Breaker, dù Retry có thể đã gọi dependency nhiều lần. Đây là lựa chọn phù hợp khi muốn Circuit Breaker đánh giá tỷ lệ thành công cuối cùng của operation sau chính sách retry.

### Retry bên ngoài, Circuit Breaker bên trong

~~~java
Supplier<Stock> circuitBreakerProtected =
    CircuitBreaker.decorateSupplier(
        circuitBreaker,
        () -> inventoryClient.getStock(sku)
    );

Supplier<Stock> retryAroundCircuitBreaker =
    Retry.decorateSupplier(retry, circuitBreakerProtected);

return retryAroundCircuitBreaker.get();
~~~

Luồng xử lý:

1. Retry bắt đầu một lần thử.
2. Mỗi lần thử đi qua Circuit Breaker.
3. Circuit Breaker ghi nhận kết quả của từng lần thực thi được cho phép.
4. Nếu Circuit Breaker chuyển OPEN, lần thử tiếp theo bị từ chối bằng **CallNotPermittedException**.
5. Retry bỏ qua exception này và dừng ngay.

Với thứ tự này, các lần thử lỗi có thể được ghi nhận riêng vào sliding window. Circuit Breaker có thể mở trong khi Retry vẫn đang hoạt động; lần thử tiếp theo bị chặn. Cấu hình **ignoreExceptions** cho **CallNotPermittedException** rất quan trọng trong trường hợp này.

| Tiêu chí | Circuit Breaker ngoài, Retry trong | Retry ngoài, Circuit Breaker trong |
|---|---|---|
| Circuit Breaker ghi nhận | Kết quả cuối cùng sau Retry | Kết quả từng lần thử được phép |
| Số mẫu trong sliding window | Thường một mẫu cho một operation logic | Có thể nhiều mẫu cho một operation logic |
| Khi Circuit Breaker OPEN | Supplier không chạy; Retry không bắt đầu | Retry nhận CallNotPermittedException và cần bỏ qua |
| Khả năng mở mạch trong chuỗi retry | Sau khi Retry kết thúc và kết quả được trả ra | Có thể mở giữa chuỗi retry |
| Phù hợp khi | Muốn đo kết quả cuối cùng của request | Muốn Circuit Breaker phản ứng với từng attempt |

Không có một thứ tự đúng cho mọi hệ thống. Hãy chọn dựa trên ý nghĩa của sliding window mà nhóm vận hành muốn quan sát. Dù chọn thứ tự nào, vẫn cần giới hạn số lần retry, đặt khoảng nghỉ phù hợp và tránh retry lỗi nghiệp vụ.

## 6. Ví dụ tích hợp Spring Cloud CircuitBreaker với Retry

Có thể dùng Spring Cloud CircuitBreaker factory làm lớp ngoài và Resilience4j Retry thực hiện các lần thử bên trong supplier. Ví dụ sau giả định ứng dụng đã có cấu hình Retry instance **inventory** trong properties và inject được **RetryRegistry**:

~~~java
import io.github.resilience4j.retry.Retry;
import io.github.resilience4j.retry.RetryRegistry;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RetryRegistry retryRegistry;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RetryRegistry retryRegistry,
            InventoryClient inventoryClient,
            InventoryCache inventoryCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.retryRegistry = retryRegistry;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Stock getStock(String sku) {
        Retry retry = retryRegistry.retry("inventory");

        return circuitBreakerFactory.create("inventory").run(
            () -> retry.executeSupplier(
                () -> inventoryClient.getStock(sku)
            ),
            error -> inventoryCache.findBySku(sku)
                .orElseThrow(() ->
                    new InventoryUnavailableException(sku, error)
                )
        );
    }
}
~~~

Ở đây, Circuit Breaker là lớp ngoài. Khi mạch OPEN, supplier không chạy nên Retry không bắt đầu. Khi mạch cho phép, Retry xử lý lỗi tạm thời. Nếu các lần thử đều thất bại, fallback lấy dữ liệu cache hoặc ném ngoại lệ nghiệp vụ.

Cách này cũng giúp phân biệt hai loại kết quả: lỗi tạm thời được Retry xử lý bên trong supplier và lỗi cuối cùng được Circuit Breaker ghi nhận cho operation logic. Nếu muốn Circuit Breaker quan sát từng attempt, hãy dùng thứ tự decorator ngược lại và cấu hình Retry bỏ qua **CallNotPermittedException**.

## 7. Cấu hình bằng Java

Nếu muốn cấu hình trực tiếp thay vì khai báo properties, có thể tạo RetryConfig và đăng ký Retry với RetryRegistry:

~~~java
import java.time.Duration;
import java.net.SocketTimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.retry.RetryConfig;
import io.github.resilience4j.retry.RetryRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryRetryConfiguration {

    @Bean
    RetryRegistry retryRegistry() {
        RetryConfig retryConfig = RetryConfig.custom()
            .maxAttempts(3)
            .waitDuration(Duration.ofMillis(200))
            .retryExceptions(
                TransientInventoryException.class,
                SocketTimeoutException.class
            )
            .ignoreExceptions(
                InvalidSkuException.class,
                InsufficientStockException.class,
                CallNotPermittedException.class
            )
            .build();

        return RetryRegistry.of(retryConfig);
    }
}
~~~

Nếu ứng dụng đã được Spring Boot auto-configure RetryRegistry từ Resilience4j starter, hãy cấu hình instance bằng properties hoặc tùy biến registry hiện có theo cách phù hợp với phiên bản đang dùng. Tránh tạo nhiều registry độc lập cho cùng một chính sách mà không có lý do, vì điều đó có thể khiến các thành phần sử dụng các Retry instance và metric khác nhau.

## 8. Dùng backoff và giới hạn tổng thời gian

Khoảng nghỉ cố định giúp tránh retry dồn dập, nhưng trong hệ thống có nhiều client cùng gặp sự cố, tất cả có thể thử lại gần như đồng thời. Backoff tăng dần và jitter giúp phân tán các lần thử.

Ví dụ properties có thể dùng khoảng nghỉ tăng dần:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        enableRandomizedWait: true
        randomizedWaitFactor: 0.5
        retryExceptions:
          - com.example.inventory.TransientInventoryException
          - java.net.SocketTimeoutException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
          - com.example.inventory.InsufficientStockException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
~~~

Với thời gian cơ sở 200 ms và hệ số tăng 2, khoảng nghỉ có thể tăng theo các lần thử; jitter làm biến thiên thời gian chờ quanh giá trị tính toán. Tên thuộc tính và cách kết hợp backoff phụ thuộc phiên bản Resilience4j, vì vậy hãy đối chiếu cấu hình với phiên bản dependency thực tế.

Tổng thời gian của operation phải nằm trong ngân sách phản hồi của API. Nếu mỗi lần thử mất tối đa hai giây, có ba lần thử và có thêm thời gian chờ giữa các lần, request có thể kéo dài hơn sáu giây. Hãy phối hợp Retry với TimeLimiter và timeout ở HTTP client. Timeout tổng thể phải bao gồm cả các lần thử và khoảng nghỉ, không chỉ thời gian của một lần gọi.

## 9. Fallback sau khi Retry kết thúc

Fallback nên được thực thi khi Circuit Breaker từ chối lời gọi hoặc khi Retry đã hết số lần thử mà vẫn thất bại. Không nên đặt fallback phục hồi lỗi ngay bên trong supplier trước Retry nếu mục tiêu là để Retry nhìn thấy lỗi gốc.

Ví dụ:

~~~java
Stock getStock(String sku) {
    Retry retry = retryRegistry.retry("inventory");

    return circuitBreakerFactory.create("inventory").run(
        () -> retry.executeSupplier(
            () -> inventoryClient.getStock(sku)
        ),
        error -> {
            if (error instanceof CallNotPermittedException) {
                log.warn("Circuit Breaker inventory đang OPEN, sku={}", sku);
            } else if (error instanceof InsufficientStockException) {
                throw (InsufficientStockException) error;
            } else {
                log.warn("Inventory không phản hồi thành công, sku={}", sku, error);
            }

            return inventoryCache.findBySku(sku)
                .orElseThrow(() ->
                    new InventoryUnavailableException(sku, error)
                );
        }
    );
}
~~~

Trong ví dụ, lỗi nghiệp vụ **InsufficientStockException** được chuyển tiếp để tầng gọi xử lý đúng ý nghĩa “không đủ hàng”, thay vì đổi thành “Inventory không khả dụng”. Lỗi bị từ chối do Circuit Breaker được ghi log riêng. Các lỗi hạ tầng còn lại có thể sử dụng cache nếu nghiệp vụ cho phép.

Fallback không nên gọi lại cùng dependency đang lỗi theo một đường đi khác. Nếu fallback tiếp tục gọi Inventory, ứng dụng có thể tái tạo chuỗi lỗi và làm mất tác dụng của Circuit Breaker. Cache hoặc một nguồn dự phòng độc lập thường phù hợp hơn.

## 10. Không retry thao tác ghi nếu chưa bảo đảm idempotency

Retry một thao tác đọc thường ít rủi ro hơn thao tác ghi. Với lệnh giữ hàng, thanh toán hoặc tạo đơn, timeout có thể xảy ra sau khi server đã thực hiện xong nhưng response chưa về đến client.

Ví dụ:

1. Client gửi lệnh giữ 2 sản phẩm.
2. Inventory nhận lệnh và cập nhật số lượng.
3. Response bị mất trên đường truyền.
4. Client nhận timeout và Retry gửi lại lệnh.
5. Nếu server không nhận diện yêu cầu trùng, số lượng có thể bị giữ hai lần.

Để retry an toàn, hãy dùng **idempotency key** hoặc request ID nghiệp vụ ổn định cho cùng một thao tác logic. Server cần lưu kết quả xử lý theo key và trả lại kết quả cũ khi nhận request trùng. Không dùng Circuit Breaker ID làm idempotency key: Circuit Breaker ID dùng chung cho nhiều request, còn idempotency key xác định một thao tác ghi cụ thể.

Chỉ retry lỗi có khả năng phục hồi và operation có thể lặp an toàn. Với lỗi không xác định kết quả của thao tác ghi, có thể cần truy vấn trạng thái giao dịch trước khi quyết định gửi lại.

## 11. Quan sát Retry và Circuit Breaker

Khi phối hợp hai cơ chế, cần theo dõi metric riêng để biết hệ thống đang retry vì lỗi tạm thời hay từ chối vì Circuit Breaker.

| Tín hiệu | Câu hỏi vận hành |
|---|---|
| Retry attempts | Một operation trung bình cần bao nhiêu lần thử? |
| Retry success | Bao nhiêu lỗi tạm thời được khắc phục ở lần thử sau? |
| Retry exhausted | Bao nhiêu operation đã hết số lần thử mà vẫn thất bại? |
| Retry ignored errors | Bao nhiêu lỗi nghiệp vụ hoặc CallNotPermittedException bị bỏ qua? |
| Circuit Breaker failure rate | Tỷ lệ lỗi cuối cùng hoặc từng attempt có đang vượt ngưỡng không? |
| CallNotPermitted count | Có bao nhiêu lời gọi bị từ chối khi mạch mở hoặc hết probe? |
| Fallback count | Ứng dụng đang phải dùng cache hoặc hành vi dự phòng thường xuyên đến mức nào? |
| Độ trễ tổng thể | Retry có làm request vượt ngân sách phản hồi không? |

Metric và tên tag cụ thể phụ thuộc phiên bản, Micrometer registry và cấu hình tích hợp. Dùng tên instance ổn định như **inventory** để nhóm số liệu. Không đưa SKU, order ID hoặc trace ID vào tên Retry/Circuit Breaker hay tag metric có cardinality cao.

Khi thấy Retry tăng nhưng Circuit Breaker vẫn CLOSED, hãy kiểm tra lỗi tạm thời, thời gian chờ và số lần thử. Khi CallNotPermitted tăng, Circuit Breaker đang từ chối lời gọi; cần kiểm tra trạng thái và tình trạng dependency thay vì tăng số lần Retry. Khi fallback tăng, cần đánh giá cache, chất lượng dữ liệu dự phòng và thời gian phục hồi dịch vụ.

## 12. Tình huống thực hành

Một dịch vụ đơn hàng gọi Inventory để kiểm tra tồn kho. Chính sách được cấu hình như sau:

- Retry cho phép tối đa ba lần thực thi, chỉ retry **TransientInventoryException** và **SocketTimeoutException**.
- **InvalidSkuException** và **InsufficientStockException** bị bỏ qua bởi Retry và Circuit Breaker.
- **CallNotPermittedException** bị bỏ qua bởi Retry để dừng ngay khi Circuit Breaker từ chối.
- Circuit Breaker sử dụng cửa sổ 20 mẫu, tối thiểu 10 lời gọi và ngưỡng lỗi 50%.
- Fallback đọc cache hoặc trả lỗi nghiệp vụ nếu không có dữ liệu phù hợp.

Xét các diễn biến:

| Kết quả lần gọi | Retry làm gì? | Circuit Breaker làm gì? |
|---|---|---|
| Lần đầu gặp **TransientInventoryException**, lần sau thành công | Thử lại rồi trả kết quả thành công | Ghi nhận theo thứ tự phối hợp đã chọn |
| Nhận **InsufficientStockException** | Bỏ qua, không thử lại | Bỏ qua exception, không tính vào failure rate |
| Circuit Breaker đang OPEN | Không tiếp tục thử lại sau **CallNotPermittedException** | Từ chối lời gọi trước khi Inventory được gọi |
| Ba lần thử đều gặp lỗi tạm thời | Dừng sau số lần tối đa và trả lỗi cuối cùng | Ghi nhận kết quả theo vị trí Circuit Breaker trong chuỗi decorator |
| Inventory phục hồi và Circuit Breaker chuyển HALF_OPEN | Không tự tạo retry liên tục cho lời gọi bị từ chối | Chỉ cho phép số probe được cấu hình |

Khi thực hành, hãy xác định được:

1. Exception nào thực sự có thể được retry.
2. Exception nào phải bị bỏ qua ở Retry và Circuit Breaker.
3. Circuit Breaker đang ở ngoài hay ở trong Retry.
4. Sliding window ghi nhận từng attempt hay kết quả cuối cùng của operation.
5. Fallback chạy sau khi nào và có tiếp tục gọi dependency đang lỗi hay không.
6. Thao tác ghi có idempotency key để tránh thực hiện lặp hay không.

## Kết luận

Retry nên thử lại có giới hạn những lỗi tạm thời có khả năng phục hồi. Lỗi nghiệp vụ như dữ liệu không hợp lệ hoặc không đủ hàng cần được bỏ qua ở cả Retry và Circuit Breaker nếu chúng không phản ánh sức khỏe của dependency. **CallNotPermittedException** phải dừng Retry để Circuit Breaker kiểm soát thời điểm thử lại qua HALF_OPEN. Thứ tự lồng nhau quyết định Circuit Breaker ghi nhận từng attempt hay kết quả cuối cùng; hãy chọn rõ semantics, phối hợp backoff với ngân sách timeout và bảo đảm thao tác ghi có tính idempotent trước khi retry.
