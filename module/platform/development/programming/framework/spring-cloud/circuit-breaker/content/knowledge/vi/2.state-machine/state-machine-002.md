# OPEN: từ chối lời gọi và lỗi CallNotPermittedException

Trong mô hình Circuit Breaker, trạng thái OPEN là cơ chế ngắt tạm thời đường gọi đến một dịch vụ đang có dấu hiệu không khỏe. Khi bộ ngắt chuyển sang OPEN, ứng dụng từ chối các lời gọi mới ngay tại phía gọi. Hàm gọi dịch vụ phụ thuộc không được thực thi, nhờ đó hệ thống tránh tiếp tục tạo tải lên một dịch vụ đang chậm hoặc không khả dụng.

Với Spring Cloud CircuitBreaker sử dụng Resilience4j, việc từ chối này thường được biểu diễn bằng ngoại lệ **CallNotPermittedException**. Hiểu đúng trạng thái OPEN và ngoại lệ này giúp phân biệt một lời gọi bị bộ ngắt chặn với một lời gọi đã đi qua mạng nhưng thất bại, đồng thời thiết kế fallback và giám sát phù hợp.

## 1. OPEN nằm ở đâu trong máy trạng thái?

Circuit Breaker thường vận hành qua ba trạng thái chính:

| Trạng thái | Hành vi | Điều kiện chuyển trạng thái |
|---|---|---|
| CLOSED | Cho phép lời gọi đi đến dịch vụ phụ thuộc và ghi nhận kết quả. | Tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng sau khi có đủ số mẫu tối thiểu thì chuyển sang OPEN. |
| OPEN | Từ chối lời gọi mới ngay tại phía gọi; không thực thi thao tác gọi dịch vụ phụ thuộc. | Sau khoảng chờ được cấu hình, bộ ngắt có thể chuyển sang HALF_OPEN. |
| HALF_OPEN | Chỉ cho phép một số lượng lời gọi thăm dò có giới hạn để kiểm tra dịch vụ đã phục hồi chưa. | Kết quả thăm dò đủ tốt thì trở về CLOSED; nếu vẫn xấu thì quay lại OPEN. |

Khi ở CLOSED, bộ ngắt quan sát kết quả lời gọi trong một sliding window. Cửa sổ có thể dựa trên số lượng lời gọi hoặc khoảng thời gian. Các tham số như số mẫu tối thiểu, ngưỡng tỷ lệ lỗi và ngưỡng tỷ lệ lời gọi chậm quyết định khi nào bộ ngắt mở. Vì vậy, OPEN là kết quả của việc đánh giá các mẫu đã thu thập, chứ không phải trạng thái được kích hoạt chỉ bởi một ngoại lệ bất kỳ.

Sau khi chuyển sang OPEN, bộ ngắt giữ trạng thái này trong khoảng thời gian cấu hình bằng **waitDurationInOpenState**. Hết thời gian chờ, nó cho phép kiểm tra phục hồi qua HALF_OPEN. Với cấu hình mặc định không bật chuyển trạng thái tự động, trạng thái thực tế thường được chuyển khi có lời gọi tiếp theo sau khi thời gian chờ đã hết. Nếu bật **automaticTransitionFromOpenToHalfOpenEnabled**, Resilience4j có thể tự chuyển trạng thái bằng bộ lập lịch mà không cần chờ một lời gọi mới.

Sơ đồ dưới đây mô tả luồng cơ bản:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng
    OPEN --> HALF_OPEN: Hết thời gian chờ
    HALF_OPEN --> CLOSED: Các lời gọi thăm dò đạt yêu cầu
    HALF_OPEN --> OPEN: Các lời gọi thăm dò tiếp tục thất bại
~~~

## 2. Điều gì xảy ra khi Circuit Breaker ở OPEN?

Giả sử dịch vụ đơn hàng gọi dịch vụ tồn kho. Dịch vụ tồn kho liên tục phản hồi chậm, khiến tỷ lệ lời gọi chậm hoặc tỷ lệ lỗi vượt ngưỡng. Circuit Breaker của lời gọi tồn kho chuyển từ CLOSED sang OPEN.

Kể từ thời điểm đó, một yêu cầu mới cần đọc tồn kho sẽ đi qua bước kiểm tra quyền thực thi của Circuit Breaker. Vì trạng thái đang là OPEN, bộ ngắt từ chối yêu cầu ngay lập tức. Hàm gọi HTTP, WebClient hoặc client tương ứng không được chạy. Ứng dụng không phải chờ kết nối, timeout hay phản hồi lỗi từ dịch vụ tồn kho cho yêu cầu bị từ chối này.

Hành vi đó có ba ý nghĩa:

- **Giảm tải cho dịch vụ phụ thuộc:** dịch vụ đang gặp sự cố không tiếp tục nhận thêm lưu lượng từ các lời gọi đã được bảo vệ.
- **Giải phóng tài nguyên phía gọi:** luồng xử lý, kết nối và thời gian chờ không bị tiêu tốn cho một lời gọi đã biết là chưa nên thực hiện.
- **Giới hạn lan truyền lỗi:** một dịch vụ đang lỗi không dễ kéo theo hàng loạt dịch vụ gọi nó bị cạn luồng hoặc tăng độ trễ.

OPEN không tự khôi phục dịch vụ phụ thuộc. Nó chỉ tạm ngừng gửi lời gọi và tạo khoảng nghỉ trước khi thử lại có kiểm soát. Trong thời gian đó, ứng dụng cần quyết định sẽ trả dữ liệu dự phòng, dùng cache, trả lỗi có ý nghĩa cho client hay áp dụng một hành vi phù hợp khác với nghiệp vụ.

## 3. Hiểu đúng CallNotPermittedException

Resilience4j ném **io.github.resilience4j.circuitbreaker.CallNotPermittedException** khi Circuit Breaker không cấp quyền thực thi lời gọi. Trường hợp thường gặp nhất là bộ ngắt đang ở OPEN. Ngoại lệ này cũng có thể xuất hiện khi bộ ngắt ở HALF_OPEN nhưng số lượt thăm dò được cấp đã được sử dụng hết và chưa có lượt nào hoàn tất để giải phóng khả năng kiểm tra tiếp theo.

Điểm quan trọng là ngoại lệ được phát sinh tại lớp Circuit Breaker, trước khi hàm gọi dịch vụ phụ thuộc được thực thi. Do đó:

| Tình huống | Dấu hiệu thường gặp | Ý nghĩa |
|---|---|---|
| Circuit Breaker đang OPEN | **CallNotPermittedException** | Lời gọi bị chặn cục bộ; không có lần gọi mới đến dịch vụ phụ thuộc. |
| Dịch vụ phụ thuộc không phản hồi kịp | Timeout hoặc lỗi tương ứng | Lời gọi đã được cho phép và quá trình thực thi gặp vấn đề. |
| Dịch vụ phụ thuộc trả lỗi | Ngoại lệ từ client hoặc lỗi nghiệp vụ | Lời gọi đã được thực hiện và nhận kết quả lỗi. |
| Bulkhead hết sức chứa | **BulkheadFullException** | Giới hạn đồng thời của Bulkhead từ chối lời gọi; đây là cơ chế bảo vệ khác với Circuit Breaker. |

Vì vậy, không nên ghi nhận **CallNotPermittedException** như thể dịch vụ phụ thuộc vừa trả về một lỗi mới. Lời gọi bị từ chối không phải một mẫu thất bại mới của dịch vụ phụ thuộc trong sliding window. Resilience4j có thể theo dõi riêng số lượt không được phép, giúp quan sát mức độ Circuit Breaker đang bảo vệ hệ thống.

Khi xử lý ngoại lệ, hãy ghi rõ tên Circuit Breaker và trạng thái hoặc ngữ cảnh lời gọi. Không nên chỉ ghi một thông báo chung như “dịch vụ tồn kho lỗi”, vì điều đó làm người vận hành khó phân biệt dịch vụ thực sự lỗi với việc ứng dụng chủ động ngăn lời gọi.

## 4. Cấu hình OPEN với Spring Cloud CircuitBreaker và Resilience4j

Spring Cloud CircuitBreaker cung cấp abstraction để ứng dụng gọi Circuit Breaker theo tên. Resilience4j là implementation có thể được cấu hình phía dưới abstraction đó. Ví dụ sau cấu hình riêng Circuit Breaker tên **catalog**:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreaker() {
        return factory -> factory.configure(
            builder -> builder.circuitBreakerConfig(
                CircuitBreakerConfig.custom()
                    .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                    .slidingWindowSize(20)
                    .minimumNumberOfCalls(10)
                    .failureRateThreshold(50)
                    .waitDurationInOpenState(Duration.ofSeconds(15))
                    .permittedNumberOfCallsInHalfOpenState(3)
                    .automaticTransitionFromOpenToHalfOpenEnabled(false)
                    .build()
            ),
            "catalog"
        );
    }
}
~~~

Các giá trị trong ví dụ có ý nghĩa như sau:

- **slidingWindowType(COUNT_BASED)** và **slidingWindowSize(20)** yêu cầu bộ ngắt đánh giá tối đa 20 kết quả gần nhất.
- **minimumNumberOfCalls(10)** yêu cầu có ít nhất 10 lời gọi được ghi nhận trước khi đánh giá tỷ lệ lỗi.
- **failureRateThreshold(50)** đặt ngưỡng mở mạch ở mức 50% lỗi.
- **waitDurationInOpenState(Duration.ofSeconds(15))** đặt thời gian chờ ở OPEN là 15 giây.
- **permittedNumberOfCallsInHalfOpenState(3)** giới hạn số lời gọi thăm dò khi sang HALF_OPEN.
- **automaticTransitionFromOpenToHalfOpenEnabled(false)** giữ cách chuyển sang HALF_OPEN theo lời gọi tiếp theo sau khi hết thời gian chờ.

Ví dụ: sau khi có đủ 10 lời gọi để đánh giá, nếu ít nhất 5 lời gọi thất bại thì tỷ lệ lỗi đạt 50% và bộ ngắt có thể chuyển sang OPEN. Trong 15 giây tiếp theo, các lời gọi mới bị từ chối. Sau thời gian chờ, bộ ngắt chuyển sang HALF_OPEN và chỉ cấp tối đa ba lượt thăm dò. Nếu kết quả thăm dò đạt yêu cầu, bộ ngắt đóng lại; nếu không, nó mở lại để tiếp tục bảo vệ dịch vụ.

Đây là cấu hình minh họa để hiểu cơ chế. Khi triển khai thực tế, cần chọn cửa sổ, số mẫu tối thiểu, ngưỡng và thời gian chờ theo lưu lượng, độ trễ bình thường, khả năng phục hồi và yêu cầu nghiệp vụ của từng dịch vụ. Một cửa sổ quá nhỏ có thể khiến trạng thái thay đổi do vài mẫu bất thường; thời gian OPEN quá ngắn có thể tạo nhiều đợt thử lại khi dịch vụ chưa kịp phục hồi.

## 5. Xử lý fallback khi lời gọi bị từ chối

Với API đồng bộ của Spring Cloud CircuitBreaker, có thể cung cấp hàm fallback cho **run**. Hàm này nhận ngoại lệ khiến lời gọi không thành công, trong đó có **CallNotPermittedException**:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.getProduct(id),
            error -> {
                if (error instanceof CallNotPermittedException) {
                    // Circuit Breaker đã chặn lời gọi trước khi gọi Catalog.
                    log.warn("Circuit Breaker catalog đang từ chối lời gọi, id={}", id);
                } else {
                    // Lời gọi được thực thi nhưng gặp lỗi khác.
                    log.warn("Không lấy được dữ liệu Catalog, id={}", id, error);
                }

                return productCache.findById(id)
                    .orElseThrow(
                        () -> new CatalogUnavailableException(id, error));
            }
        );
    }
}
~~~

Ví dụ giả định **ProductCache** trả về **Optional<Product>** và **CatalogUnavailableException** là ngoại lệ nghiệp vụ do ứng dụng định nghĩa. Khi Circuit Breaker đang OPEN, fallback tìm dữ liệu trong cache. Nếu cache không có dữ liệu, ứng dụng trả lỗi có chủ đích thay vì tạo ra một đối tượng rỗng có thể bị hiểu nhầm là dữ liệu hợp lệ.

Hàm fallback trong ví dụ nhận mọi lỗi từ lời gọi được bảo vệ, nên cần phân biệt **CallNotPermittedException** với timeout hoặc lỗi từ client. Nếu nghiệp vụ yêu cầu cách xử lý khác nhau, hãy phân nhánh theo loại lỗi như trên. Không nên mặc định mọi lỗi đều có nghĩa là Circuit Breaker đang OPEN.

Fallback cũng phải độc lập với dịch vụ đang gặp sự cố. Nếu fallback lại gọi chính dịch vụ Catalog qua cùng đường mạng, hoặc gọi một dịch vụ phụ thuộc đang lỗi theo chuỗi, nó có thể tái tạo vấn đề mà Circuit Breaker đang cố ngăn chặn. Dữ liệu cache hoặc phản hồi dự phòng phải có quy tắc về độ cũ và tính hợp lệ rõ ràng; không trả dữ liệu cũ một cách âm thầm nếu nghiệp vụ không cho phép.

## 6. Lời gọi reactive cũng phải xử lý trạng thái OPEN

Với ứng dụng WebFlux, Spring Cloud CircuitBreaker cung cấp ReactiveCircuitBreaker. Lời gọi bị từ chối được truyền trong reactive pipeline dưới dạng tín hiệu lỗi. Có thể xử lý **CallNotPermittedException** trong hàm fallback:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

class ReactiveCatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveCatalogClient catalogClient;
    private final ProductCache productCache;

    Mono<Product> getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            catalogClient.getProduct(id),
            error -> {
                if (error instanceof CallNotPermittedException) {
                    return productCache.findById(id)
                        .map(Mono::just)
                        .orElseGet(() -> Mono.error(
                            new CatalogUnavailableException(id, error)));
                }

                return Mono.error(error);
            }
        );
    }
}
~~~

Trong reactive pipeline, lỗi không nhất thiết được ném ngay tại dòng gọi phương thức; nó có thể được phát ra khi publisher được subscribe. Vì vậy, hãy xử lý lỗi bằng các toán tử reactive hoặc fallback mà abstraction cung cấp. Tránh gọi **block()** chỉ để bắt ngoại lệ, vì việc đó có thể làm mất lợi ích non-blocking và gây nghẽn luồng xử lý.

## 7. Phân biệt OPEN với timeout, retry và Bulkhead

Các cơ chế bảo vệ có thể được dùng cùng nhau nhưng phản ánh những tình huống khác nhau:

- **Circuit Breaker OPEN:** từ chối lời gọi vì các kết quả trước đó cho thấy dịch vụ phụ thuộc không khỏe.
- **Timeout hoặc TimeLimiter:** giới hạn thời gian chờ của một lời gọi đã được cho phép thực thi. Timeout có thể được tính là lỗi hoặc lời gọi chậm tùy cấu hình Circuit Breaker.
- **Retry:** thử lại một thao tác thất bại theo chính sách số lần và khoảng nghỉ. Khi Circuit Breaker OPEN, retry liên tục thường chỉ nhận thêm **CallNotPermittedException** mà không giúp dịch vụ phụ thuộc phục hồi.
- **Bulkhead:** giới hạn số lời gọi đồng thời hoặc tài nguyên dành cho một phần hệ thống. Khi hết sức chứa, Bulkhead có thể từ chối lời gọi bằng ngoại lệ riêng như **BulkheadFullException**.

Thứ tự kết hợp các decorator ảnh hưởng đến ngoại lệ mà lớp gọi nhận được và cách retry tương tác với Circuit Breaker. Hãy cấu hình và quan sát chúng như các cơ chế riêng, đồng thời tránh chính sách retry khiến một dịch vụ đang suy yếu nhận thêm tải ngay khi vừa phục hồi.

## 8. Theo dõi và vận hành trạng thái OPEN

Một Circuit Breaker hoạt động đúng có thể ở OPEN trong thời gian dịch vụ phụ thuộc gặp sự cố. Vì thế, chỉ nhìn thấy trạng thái OPEN chưa đủ để kết luận cấu hình sai. Cần theo dõi cả trạng thái, số lời gọi bị từ chối và tình trạng dịch vụ phụ thuộc.

Khi tích hợp Micrometer với Resilience4j, có thể quan sát các metric Circuit Breaker, chẳng hạn số lời gọi thành công, thất bại và không được phép; tỷ lệ lỗi hoặc lời gọi chậm; trạng thái hiện tại và số lần chuyển trạng thái. Tên metric và tag cụ thể phụ thuộc phiên bản, registry và cấu hình tích hợp. Nên gắn dữ liệu với tên Circuit Breaker, ví dụ **catalog**, để phân biệt từng dịch vụ phụ thuộc.

Một bảng theo dõi hữu ích thường gồm:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| Trạng thái hiện tại và số lần chuyển trạng thái | Bộ ngắt đang CLOSED, OPEN hay HALF_OPEN? Có liên tục mở và đóng không? |
| Số lượt không được phép | Bao nhiêu yêu cầu bị từ chối trong khoảng thời gian này? |
| Tỷ lệ lỗi và lời gọi chậm | Nguyên nhân mở mạch là lỗi hay độ trễ tăng? |
| Số lần fallback và tỷ lệ cache hit | Hành vi dự phòng có đang đáp ứng được nhu cầu không? |
| Độ trễ và tình trạng dịch vụ phụ thuộc | Dịch vụ đã phục hồi đủ ổn định để nhận lại lưu lượng chưa? |

Log chuyển trạng thái nên có tên Circuit Breaker, trạng thái trước và sau, cùng thời điểm chuyển. Với từng yêu cầu bị từ chối, có thể ghi log ở mức phù hợp hoặc dùng metric để tổng hợp; tránh ghi stack trace lặp lại cho mọi **CallNotPermittedException**, vì lưu lượng lớn có thể tạo thêm tải cho hệ thống ghi log.

Cảnh báo nên kết hợp thời gian duy trì OPEN, số lượt bị từ chối, lỗi của dịch vụ phụ thuộc và tỷ lệ fallback. Nếu OPEN chỉ xuất hiện trong một khoảng ngắn rồi trở về CLOSED ổn định, bộ ngắt có thể đang thực hiện đúng vai trò. Nếu nó liên tục chuyển CLOSED → OPEN → HALF_OPEN → OPEN, hãy kiểm tra sức khỏe dịch vụ, ngưỡng, cửa sổ trượt, thời gian chờ và kết quả thăm dò.

## 9. Những lỗi triển khai thường gặp

1. **Nhầm ngoại lệ bị từ chối với lỗi từ dịch vụ phụ thuộc.** **CallNotPermittedException** cho biết bộ ngắt không cho phép thực thi. Hãy dùng log và metric riêng để xác định số lời gọi thực sự đến dịch vụ.
2. **Retry dồn dập khi bộ ngắt đang OPEN.** Các lần thử lại tiếp tục bị từ chối, làm tăng tải xử lý và log mà không kiểm tra được khả năng phục hồi.
3. **Fallback gọi lại cùng dịch vụ đang lỗi.** Điều này làm mất ý nghĩa bảo vệ của OPEN và có thể tạo thêm chuỗi phụ thuộc lỗi.
4. **Thời gian OPEN không phù hợp.** Quá ngắn khiến hệ thống thử lại trước khi dịch vụ hồi phục; quá dài làm dịch vụ khỏe trở lại nhưng phải chờ lâu mới nhận lưu lượng.
5. **Không giới hạn lời gọi thăm dò ở HALF_OPEN.** Quá nhiều probe có thể tạo đột biến tải ngay khi dịch vụ bắt đầu phục hồi.
6. **Không xác định chất lượng dữ liệu fallback.** Cache cũ, dữ liệu mặc định hoặc phản hồi rỗng có thể gây sai lệch nghiệp vụ nếu không có quy tắc rõ ràng.

## 10. Tình huống thực hành

Một dịch vụ đặt hàng gọi dịch vụ Catalog để lấy thông tin sản phẩm. Circuit Breaker **catalog** có cấu hình cửa sổ 20 lời gọi, tối thiểu 10 mẫu, ngưỡng lỗi 50%, thời gian OPEN 15 giây và tối đa ba lời gọi thăm dò trong HALF_OPEN.

Diễn biến:

1. Ban đầu bộ ngắt ở CLOSED. Các lời gọi được chuyển đến Catalog và kết quả được ghi vào sliding window.
2. Sau khi đủ ít nhất 10 mẫu, tỷ lệ lỗi đạt 50%. Bộ ngắt chuyển sang OPEN.
3. Trong 15 giây tiếp theo, yêu cầu mới bị từ chối với **CallNotPermittedException**. Client Catalog không được gọi cho những yêu cầu này; ứng dụng thử dùng cache hoặc trả lỗi dự phòng.
4. Hết thời gian chờ, bộ ngắt chuyển sang HALF_OPEN. Tối đa ba yêu cầu thăm dò được phép đi đến Catalog. Các yêu cầu vượt quá số lượt được cấp vẫn có thể bị từ chối.
5. Nếu các kết quả thăm dò đạt ngưỡng cho phép, bộ ngắt trở về CLOSED và tiếp tục ghi nhận kết quả bình thường. Nếu tỷ lệ lỗi vẫn vượt ngưỡng, nó quay lại OPEN và bắt đầu một khoảng chờ mới.

Khi phân tích tình huống, hãy trả lời được ba câu hỏi: yêu cầu nào thực sự đến Catalog, yêu cầu nào bị Circuit Breaker từ chối, và điều kiện nào khiến bộ ngắt chuyển từ OPEN sang HALF_OPEN rồi trở về CLOSED hoặc OPEN. Đây là cơ sở để đọc log, metric và xác định fallback có được kích hoạt đúng hay không.

## Kết luận

OPEN là trạng thái ngắt tạm thời đường gọi đến một dịch vụ phụ thuộc đang có dấu hiệu không khỏe. **CallNotPermittedException** cho biết Circuit Breaker đã từ chối lời gọi trước khi thao tác gọi dịch vụ được thực thi. Khi kết hợp Spring Cloud CircuitBreaker với Resilience4j, cần cấu hình thời gian chờ và số lượt thăm dò hợp lý, xử lý fallback theo đúng loại lỗi, đồng thời theo dõi trạng thái và số lượt bị từ chối để đánh giá hiệu quả bảo vệ dịch vụ.
