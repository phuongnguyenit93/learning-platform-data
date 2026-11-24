# Customizer sau khi tạo bộ ngắt mạch và bộ lắng nghe sự kiện

Spring Cloud CircuitBreaker cung cấp factory để tạo bộ ngắt mạch theo ID. Khi dùng Resilience4j, ứng dụng còn có thể tùy chỉnh instance sau khi factory tạo nó và đăng ký bộ lắng nghe sự kiện để biết khi nào lời gọi lỗi, bị từ chối hoặc trạng thái mạch thay đổi.

Hai việc này thường được thực hiện bằng một bean Spring kiểu `Customizer`. Cấu hình ngưỡng quyết định cách bộ ngắt mạch hoạt động; customizer sau khi tạo bổ sung hành vi cho instance đã được tạo, chẳng hạn gắn listener để ghi log hoặc cập nhật số liệu. Nhờ đó, mã nghiệp vụ không cần tự quản lý việc đăng ký listener mỗi lần gọi dịch vụ.

## Vòng đời tạo bộ ngắt mạch

Một lời gọi đi qua factory với một ID ổn định, ví dụ `inventory-read`. Factory chọn cấu hình tương ứng, tạo hoặc lấy instance bộ ngắt mạch và áp dụng các customizer đã đăng ký. Sau đó, factory trả về đối tượng Spring Cloud CircuitBreaker để mã ứng dụng thực thi lời gọi.

~~~mermaid
flowchart TD
    A[Ứng dụng gọi factory với ID] --> B[Factory chọn cấu hình]
    B --> C[Tạo instance Resilience4j]
    C --> D[Chạy post-creation customizer]
    D --> E[Đăng ký event listener]
    E --> F[Trả circuit breaker cho ứng dụng]
    F --> G[Thực hiện các lời gọi được bảo vệ]
    G --> H[Phát sự kiện khi có kết quả hoặc đổi trạng thái]
    H --> I[Listener ghi log hoặc cập nhật metrics]
~~~

Trong Spring Cloud CircuitBreaker tích hợp Resilience4j, factory đồng bộ thường dùng là `Resilience4JCircuitBreakerFactory`. Có thể khai báo một bean `Customizer<Resilience4JCircuitBreakerFactory>` để tùy chỉnh factory.

Điểm quan trọng là customizer được đăng ký ở cấp cấu hình ứng dụng. Factory áp dụng callback khi tạo circuit breaker phù hợp; ứng dụng không cần gắn listener lặp lại trong từng request. Với ID cụ thể, callback chỉ áp dụng cho những instance được chỉ định.

## Phân biệt cấu hình trước khi tạo và customizer sau khi tạo

Spring Cloud CircuitBreaker có nhiều điểm mở rộng. Hãy chọn đúng điểm theo mục đích:

| Cơ chế | Thời điểm và đối tượng | Mục đích |
|---|---|---|
| `configureDefault(...)` | Cấu hình mặc định cho các ID khi factory xây dựng cấu hình | Đặt chính sách chung như sliding window, tỷ lệ lỗi và timeout. |
| `configure(..., "id")` | Cấu hình cho một hoặc nhiều ID được chỉ định | Ghi đè hoặc bổ sung chính sách riêng cho luồng gọi cụ thể. |
| `addCircuitBreakerCustomizer(..., "id")` | Callback trên instance Resilience4j sau khi instance được tạo | Gắn event listener hoặc bổ sung hành vi cần truy cập instance đã tạo. |

Cấu hình trước khi tạo quyết định các tham số vận hành của circuit breaker. Post-creation customizer nhận instance Resilience4j để đăng ký listener. Không nên dùng listener để thay thế việc cấu hình failure rate, slow call rate, sliding window hay timeout.

## Đặt cấu hình cho một ID

Ví dụ dưới đây đặt cấu hình riêng cho lời gọi đọc tồn kho. ID trong factory và tên instance trong cấu hình phải nhất quán.

~~~java
import java.time.Duration;

import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;

@Configuration
public class InventoryCircuitBreakerConfiguration {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory>
            inventoryCircuitBreakerConfiguration() {

        CircuitBreakerConfig circuitBreakerConfig =
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(20)
                        .minimumNumberOfCalls(10)
                        .failureRateThreshold(50)
                        .slowCallDurationThreshold(Duration.ofMillis(800))
                        .slowCallRateThreshold(60)
                        .build();

        TimeLimiterConfig timeLimiterConfig =
                TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(2))
                        .build();

        return factory -> factory.configure(
                builder -> builder
                        .circuitBreakerConfig(circuitBreakerConfig)
                        .timeLimiterConfig(timeLimiterConfig)
                        .build(),
                "inventory-read"
        );
    }
}
~~~

Đây là ví dụ cấu hình bằng Java. Nếu dự án đã quản lý các tham số trong `application.yml`, hãy chọn một nguồn cấu hình rõ ràng và tránh vô tình tạo ra hai bộ giá trị mâu thuẫn. Cấu hình Java có thể phù hợp khi cần xây dựng cấu hình theo điều kiện hoặc dùng chung các đối tượng cấu hình.

Có thể đặt cấu hình mặc định cho mọi ID bằng `configureDefault`:

~~~java
@Bean
public Customizer<Resilience4JCircuitBreakerFactory> defaultCircuitBreakerConfiguration() {
    return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                    .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
                    .timeLimiterConfig(
                            TimeLimiterConfig.custom()
                                    .timeoutDuration(Duration.ofSeconds(3))
                                    .build()
                    )
                    .build()
    );
}
~~~

Khi có cấu hình riêng cho một ID, hãy kiểm tra thứ tự và cách các customizer được áp dụng theo phiên bản Spring Cloud CircuitBreaker đang dùng. Không nên dựa vào thứ tự khai báo bean một cách ngầm định nếu nhiều customizer cùng sửa một cấu hình.

## Đăng ký listener sau khi instance được tạo

Để gắn listener vào instance Resilience4j, dùng `addCircuitBreakerCustomizer`. Ví dụ sau đăng ký các listener cho ID `inventory-read`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerEventConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(CircuitBreakerEventConfiguration.class);

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory>
            inventoryCircuitBreakerEvents() {

        return factory -> factory.addCircuitBreakerCustomizer(
                circuitBreaker -> circuitBreaker.getEventPublisher()
                        .onStateTransition(event ->
                                log.info(
                                        "Circuit breaker {} changed state: {}",
                                        event.getCircuitBreakerName(),
                                        event.getStateTransition()
                                )
                        )
                        .onError(event ->
                                log.warn(
                                        "Circuit breaker {} recorded an error: {}",
                                        event.getCircuitBreakerName(),
                                        event.getThrowable().toString()
                                )
                        )
                        .onCallNotPermitted(event ->
                                log.warn(
                                        "Circuit breaker {} rejected a call",
                                        event.getCircuitBreakerName()
                                )
                        )
                        .onFailureRateExceeded(event ->
                                log.warn(
                                        "Circuit breaker {} exceeded failure rate",
                                        event.getCircuitBreakerName()
                                )
                        )
                        .onSlowCallRateExceeded(event ->
                                log.warn(
                                        "Circuit breaker {} exceeded slow call rate",
                                        event.getCircuitBreakerName()
                                )
                        ),
                "inventory-read"
        );
    }
}
~~~

Callback nhận instance Resilience4j sau khi factory tạo nó. `getEventPublisher()` cung cấp các điểm đăng ký listener. Tham số ID cuối cùng giới hạn customizer vào instance `inventory-read`; những circuit breaker khác không tự động nhận listener này.

Các phương thức listener trong ví dụ phản ánh những loại sự kiện khác nhau:

| Listener | Khi nào được gọi? | Có thể dùng để |
|---|---|---|
| `onStateTransition` | Khi mạch chuyển giữa CLOSED, OPEN và HALF_OPEN. | Theo dõi trạng thái và tạo cảnh báo khi mạch mở. |
| `onError` | Khi một lời gọi được ghi nhận là lỗi. | Ghi nhận lỗi phụ thuộc hoặc phân loại nguyên nhân. |
| `onCallNotPermitted` | Khi lời gọi bị từ chối vì mạch không cho phép thực thi. | Đếm số lần từ chối nhanh và theo dõi fallback. |
| `onFailureRateExceeded` | Khi tỷ lệ lỗi vượt ngưỡng. | Xác định nguyên nhân mở mạch do lỗi. |
| `onSlowCallRateExceeded` | Khi tỷ lệ lời gọi chậm vượt ngưỡng. | Phát hiện phụ thuộc suy giảm độ trễ dù vẫn trả kết quả. |

Sự kiện `onError` mô tả một kết quả lỗi của lời gọi. Sự kiện `onFailureRateExceeded` mô tả việc tỷ lệ lỗi trong cửa sổ đã vượt ngưỡng. Hai sự kiện có ý nghĩa khác nhau: một lỗi đơn lẻ không nhất thiết làm mạch mở.

Tương tự, một lời gọi chậm có thể hoàn tất thành công. Listener `onSlowCallRateExceeded` chỉ báo khi tỷ lệ lời gọi chậm vượt ngưỡng, còn `onStateTransition` cho biết trạng thái thực tế của mạch đã thay đổi hay chưa.

## Dùng listener để quan sát, không điều khiển luồng nghiệp vụ

Event listener phù hợp để ghi nhận hoạt động, cập nhật bộ đếm metrics hoặc gửi tín hiệu tới hệ thống quan sát. Không nên đặt logic nghiệp vụ quan trọng vào listener, vì listener được gọi như một phần của quá trình phát sự kiện và không phải điểm điều khiển chính của request.

Ví dụ, có thể tăng bộ đếm khi circuit breaker từ chối lời gọi:

~~~java
.onCallNotPermitted(event ->
        rejectedCallsCounter.increment()
)
~~~

Trong ví dụ này, `rejectedCallsCounter` là một đối tượng metrics đã được khởi tạo và gắn nhãn phù hợp trong ứng dụng. Nên dùng các nhãn có miền giá trị giới hạn, chẳng hạn tên ID circuit breaker và loại sự kiện. Không gắn user ID, order ID hoặc URL chứa tham số vào nhãn metrics vì cardinality có thể tăng rất nhanh.

Một số nguyên tắc khi triển khai listener:

- Giữ callback ngắn và không chặn luồng đang phát sự kiện.
- Tránh gọi lại chính dịch vụ phụ thuộc từ listener.
- Không thực hiện truy vấn cơ sở dữ liệu hoặc gọi HTTP đồng bộ trong callback.
- Không để lỗi ghi log hoặc lỗi metrics làm gián đoạn luồng xử lý chính.
- Dùng log có cấu trúc và nhãn metrics ổn định để tổng hợp theo ID.
- Hạn chế log từng sự kiện thành công ở hệ thống lưu lượng cao; ưu tiên metrics tổng hợp.

Nếu cần gửi sự kiện tới hệ thống bên ngoài, hãy chuyển công việc sang cơ chế bất đồng bộ có giới hạn hàng đợi và có chính sách xử lý khi hàng đợi đầy. Không nên biến event listener thành một phụ thuộc mạng mới nằm trên đường xử lý của request.

## Theo dõi trạng thái và kết quả của bộ ngắt mạch

Có thể kết hợp event listener với Spring Boot Actuator, Micrometer và các hệ thống thu thập log/metrics. Các sự kiện cho biết điều gì vừa xảy ra; metrics tổng hợp giúp quan sát xu hướng theo thời gian.

Nên theo dõi tối thiểu:

- Trạng thái hiện tại và số lần chuyển trạng thái của từng ID.
- Số lời gọi thành công, lỗi, chậm và bị từ chối.
- Failure rate, slow call rate và độ trễ.
- Số lần fallback được gọi.
- Thời gian circuit breaker ở trạng thái OPEN.
- Tần suất mở lại sau khi thử HALF_OPEN.

Khi mạch chuyển sang OPEN, cần phân biệt nguyên nhân do failure rate hay slow call rate. Nếu do lỗi, hãy kiểm tra ngoại lệ, lỗi kết nối hoặc lỗi nghiệp vụ. Nếu do lời gọi chậm, hãy xem độ trễ mạng, truy vấn cơ sở dữ liệu, tài nguyên của dịch vụ phụ thuộc và hàng đợi. Khi mạch liên tục chuyển OPEN rồi CLOSED, hãy đánh giá lại cửa sổ trượt, số mẫu tối thiểu, ngưỡng và thời gian chờ.

Event listener không thay thế health check hoặc metrics. Listener phản ánh các sự kiện đã phát sinh; health indicator cung cấp tín hiệu trạng thái phục vụ kiểm tra sức khỏe; metrics hỗ trợ phân tích xu hướng và cảnh báo. Kết hợp các nguồn này giúp nhóm vận hành hiểu cả trạng thái hiện tại lẫn lịch sử chuyển trạng thái.

## Phạm vi và vòng đời của listener

Post-creation customizer được đăng ký trên factory và áp dụng khi factory tạo instance phù hợp. Vì vậy, không nên đặt lệnh đăng ký listener trong mỗi phương thức controller hoặc service được gọi theo request. Làm như vậy có thể khiến việc đăng ký bị lặp, khó xác định vòng đời và gây nhiễu khi vận hành.

Nên đặt customizer trong lớp cấu hình Spring, giới hạn theo ID cụ thể và để factory quản lý vòng đời instance. Nếu có nhiều customizer cùng áp dụng cho một ID, hãy tổ chức chúng rõ ràng để tránh đăng ký trùng cùng một hành động hoặc ghi log hai lần.

Với ứng dụng chạy nhiều replica, mỗi tiến trình thường có instance circuit breaker và event publisher riêng. Listener trên replica này không tự động nhận sự kiện từ replica khác. Khi cần quan sát toàn hệ thống, hãy gửi log hoặc metrics từ mọi replica về một nền tảng tập trung và giữ cùng quy ước ID để tổng hợp.

Khi dùng reactive circuit breaker, factory và API cấu hình cụ thể phụ thuộc vào backend và phiên bản Spring Cloud CircuitBreaker. Hãy dùng reactive factory tương ứng cho lời gọi reactive và kiểm tra extension point mà phiên bản đó cung cấp; không bọc một lời gọi reactive bằng circuit breaker đồng bộ hoặc gọi `block()` chỉ để dùng chung listener.

## Kiểm thử customizer và event listener

Có thể kiểm thử tích hợp bằng cách tạo một phụ thuộc giả lập có thể trả thành công, ném lỗi hoặc phản hồi chậm. Dùng ID đã cấu hình và quan sát listener có nhận đúng sự kiện hay không.

| Tình huống | Sự kiện hoặc kết quả cần quan sát |
|---|---|
| Lời gọi hoàn tất thành công | Ghi nhận kết quả thành công; trạng thái vẫn CLOSED nếu chưa có điều kiện mở mạch. |
| Lời gọi ném lỗi | Listener `onError` nhận sự kiện lỗi. |
| Tỷ lệ lỗi vượt ngưỡng | Listener `onFailureRateExceeded` được gọi và mạch chuyển OPEN. |
| Tỷ lệ lời gọi chậm vượt ngưỡng | Listener `onSlowCallRateExceeded` được gọi và mạch chuyển OPEN. |
| Gọi khi mạch đang OPEN | Listener `onCallNotPermitted` nhận sự kiện từ chối. |
| Hết thời gian OPEN và thử phục hồi | Quan sát chuyển trạng thái sang HALF_OPEN, sau đó CLOSED hoặc OPEN tùy kết quả thăm dò. |
| Gọi một ID khác | Xác nhận listener giới hạn cho `inventory-read` không bị áp dụng nhầm cho ID khác. |

Ngoài việc kiểm tra sự kiện, hãy xác nhận rằng listener không làm tăng đáng kể độ trễ request, không tạo vòng gọi phụ thuộc và không làm phát sinh lượng log quá lớn. Nếu sử dụng metrics, kiểm tra số liệu tăng đúng theo sự kiện và nhãn không chứa dữ liệu định danh từng request.

## Checklist triển khai

1. Xác định ID ổn định cho từng luồng gọi cần bảo vệ.
2. Cấu hình failure rate, slow call rate, sliding window và timeout tại điểm cấu hình phù hợp.
3. Dùng `addCircuitBreakerCustomizer` để gắn listener sau khi factory tạo instance Resilience4j.
4. Chỉ đăng ký listener cho những ID cần theo dõi và tránh đăng ký lặp.
5. Giữ callback ngắn, không chặn và không thực hiện lời gọi mạng đồng bộ.
6. Kết hợp sự kiện với metrics, log và health indicator để theo dõi xu hướng.
7. Kiểm thử riêng lỗi nhanh, lời gọi chậm, từ chối nhanh và quá trình HALF_OPEN phục hồi.

Customizer sau khi tạo giúp bổ sung hành vi cho đúng instance circuit breaker; event listener cung cấp tín hiệu về kết quả lời gọi và thay đổi trạng thái. Khi đặt chúng ở lớp cấu hình, giới hạn theo ID ổn định và giữ callback nhẹ, ứng dụng Spring Cloud có thể quan sát Resilience4j rõ ràng mà không làm phức tạp mã nghiệp vụ.

