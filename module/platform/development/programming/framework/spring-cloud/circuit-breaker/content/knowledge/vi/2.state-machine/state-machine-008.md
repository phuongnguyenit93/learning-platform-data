# FORCED_OPEN, DISABLED và METRICS_ONLY trong Resilience4j

Resilience4j triển khai Circuit Breaker bằng một máy trạng thái hữu hạn. Ba trạng thái thường gặp là CLOSED, OPEN và HALF_OPEN: mạch cho phép lời gọi và ghi nhận kết quả, ngắt lời gọi khi tỷ lệ lỗi vượt ngưỡng, rồi thăm dò khả năng phục hồi. Ngoài ba trạng thái này, Resilience4j còn có ba trạng thái đặc biệt là FORCED_OPEN, DISABLED và METRICS_ONLY.

Các trạng thái đặc biệt cho phép ứng dụng hoặc người vận hành chủ động thay đổi cách Circuit Breaker xử lý lời gọi. Chúng hữu ích khi cần tạm ngắt một dependency, tạm bỏ qua cơ chế bảo vệ hoặc quan sát chất lượng dịch vụ mà chưa muốn từ chối yêu cầu. Muốn sử dụng đúng, cần hiểu rõ mỗi trạng thái cho phép lời gọi đi qua ra sao, có ghi metrics hay không và phải làm gì để quay lại chế độ bảo vệ bình thường.

## 1. Vị trí của ba trạng thái đặc biệt

Ba trạng thái đặc biệt không phải là những bước tự động tiếp theo của CLOSED, OPEN hay HALF_OPEN. Chúng là các chế độ vận hành được kích hoạt bằng thao tác chuyển trạng thái tường minh.

| Trạng thái | Lời gọi đến dependency | Metrics và sự kiện lời gọi | Tự động chuyển trạng thái theo ngưỡng |
| --- | --- | --- | --- |
| CLOSED | Được phép | Có | Có thể chuyển sang OPEN |
| OPEN | Bị từ chối | Có ghi nhận các sự kiện liên quan đến trạng thái và lời gọi bị từ chối | Có thể chuyển sang HALF_OPEN sau thời gian chờ |
| HALF_OPEN | Chỉ một số lời gọi thăm dò được phép | Có | Có thể chuyển sang CLOSED hoặc OPEN |
| FORCED_OPEN | Tất cả lời gọi bị từ chối | Không ghi metrics và không phát sự kiện lời gọi; vẫn có sự kiện chuyển trạng thái | Không |
| DISABLED | Tất cả lời gọi được phép | Không ghi metrics và không phát sự kiện lời gọi; vẫn có sự kiện chuyển trạng thái | Không |
| METRICS_ONLY | Tất cả lời gọi được phép | Có ghi metrics và phát sự kiện | Không tự mở mạch dù ngưỡng bị vượt |

Điểm cần nhớ:

- FORCED_OPEN là chế độ chủ động chặn toàn bộ lời gọi.
- DISABLED cho phép toàn bộ lời gọi và bỏ qua việc thu thập metrics của Circuit Breaker.
- METRICS_ONLY cho phép toàn bộ lời gọi nhưng vẫn thu thập metrics để quan sát.

Với cả ba trạng thái đặc biệt, Circuit Breaker không tự quay lại CLOSED chỉ vì thời gian trôi qua hoặc dịch vụ phụ thuộc đã khỏe lại. Ứng dụng cần thực hiện một chuyển trạng thái tường minh để thoát khỏi chế độ đặc biệt.

## 2. FORCED_OPEN — chủ động ngắt mọi lời gọi

FORCED_OPEN buộc Circuit Breaker từ chối mọi lời gọi đi qua nó, bất kể tỷ lệ lỗi hiện tại, thời gian chờ OPEN hay tình trạng thực tế của dịch vụ phụ thuộc. Khác với OPEN thông thường, FORCED_OPEN không chờ hết thời gian để tự chuyển sang HALF_OPEN.

Khi lời gọi đi qua Circuit Breaker đang ở FORCED_OPEN, Resilience4j không cấp quyền thực thi lời gọi. Với cách sử dụng trực tiếp Resilience4j, tầng gọi thường nhận được CallNotPermittedException. Nếu ứng dụng bọc lời gọi bằng Spring Cloud CircuitBreaker và đã khai báo fallback, fallback có thể xử lý lỗi từ việc lời gọi bị từ chối. Nếu không có fallback, lỗi được truyền lên tầng gọi để xử lý.

### Khi nào nên dùng?

Một số tình huống phù hợp:

- **Dependency đang bảo trì:** chủ động ngừng gửi yêu cầu đến dịch vụ đang được nâng cấp hoặc bảo trì.
- **Sự cố đã được xác nhận:** đội vận hành muốn cách ly một dependency đang gây lỗi nghiêm trọng cho các dịch vụ gọi đến.
- **Ngăn tải tiếp tục đổ vào hệ thống phụ thuộc:** trong lúc phối hợp xử lý sự cố, có thể chủ động ngắt lời gọi để giảm áp lực lên dependency.

Ví dụ, dịch vụ Inventory đang gặp sự cố dữ liệu. Dịch vụ Order vẫn tiếp nhận yêu cầu, nhưng mọi lời gọi kiểm tra tồn kho cần được chặn trong thời gian đội vận hành xử lý. Nếu nghiệp vụ cho phép, Order có thể trả về thông báo tạm thời không thể xác nhận tồn kho. Nếu nghiệp vụ không cho phép xử lý tiếp khi thiếu dữ liệu tồn kho, Order cần trả lỗi có kiểm soát.

### Chuyển sang FORCED_OPEN và khôi phục

Resilience4j cung cấp phương thức chuyển trạng thái trực tiếp trên đối tượng CircuitBreaker:

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Chủ động chặn mọi lời gọi
inventory.transitionToForcedOpenState();

// Sau khi sự cố được xử lý, khôi phục cơ chế bảo vệ bình thường
inventory.transitionToClosedState();
~~~

Đoạn mã minh họa dùng một CircuitBreaker đã được lấy từ registry. Tên inventory phải trùng với tên instance mà đường gọi nghiệp vụ đang sử dụng. Nếu thao tác trên một instance khác, các lời gọi thực tế có thể không bị ảnh hưởng.

Khi khôi phục từ FORCED_OPEN, có thể chuyển tường minh về CLOSED để Circuit Breaker tiếp tục thu thập kết quả và tự mở mạch khi ngưỡng bị vượt. Việc chuyển về CLOSED có nghĩa là bắt đầu cho phép lời gọi theo cơ chế bảo vệ bình thường; nó không chứng minh dependency đã thực sự khỏe. Trước khi mở lại lưu lượng, đội vận hành vẫn cần dựa vào health check, log, metrics của dịch vụ phụ thuộc và tình trạng sự cố.

## 3. DISABLED — bỏ qua Circuit Breaker

DISABLED là chế độ Circuit Breaker không thực hiện chức năng bảo vệ. Mọi lời gọi đều được cho phép đi qua. Circuit Breaker không ghi metrics cho các lời gọi và không phát sự kiện lời gọi; sự kiện chuyển trạng thái vẫn được phát.

Ở trạng thái này, Circuit Breaker không tính failure rate hoặc slow call rate để mở mạch. Vì vậy, dù dependency liên tục trả lỗi hoặc phản hồi rất chậm, Circuit Breaker vẫn không tự chuyển sang OPEN.

### Khi nào nên dùng?

DISABLED có thể hữu ích trong những tình huống giới hạn:

- Tạm thời bỏ qua Circuit Breaker khi điều tra một vấn đề ở tầng tích hợp và cần xác định lỗi có đến từ cơ chế Circuit Breaker hay không.
- Thực hiện một thử nghiệm có kiểm soát trong môi trường phát triển hoặc kiểm thử.
- Tạm ngừng thu thập và xử lý của Circuit Breaker khi có quyết định vận hành rõ ràng.

DISABLED làm mất cả khả năng chặn lời gọi lẫn metrics của Circuit Breaker. Nếu dependency đang chậm, các lời gọi vẫn có thể chiếm thread, connection hoặc tài nguyên khác của dịch vụ gọi đến. Do đó, trước khi sử dụng, cần xác định rõ timeout, giới hạn đồng thời và cách xử lý lỗi ở các tầng khác.

### Chuyển sang DISABLED và khôi phục

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Bỏ qua Circuit Breaker: mọi lời gọi đều được cho phép
inventory.transitionToDisabledState();

// Bật lại cơ chế bảo vệ và ghi nhận kết quả
inventory.transitionToClosedState();
~~~

Không nên coi DISABLED là cách xử lý một dependency đang lỗi. Nếu mục tiêu là ngừng gửi lời gọi đến dependency, FORCED_OPEN mới là trạng thái phù hợp. Nếu muốn quan sát lỗi nhưng vẫn cho lời gọi đi qua, hãy cân nhắc METRICS_ONLY.

## 4. METRICS_ONLY — quan sát mà không chặn lời gọi

METRICS_ONLY cho phép tất cả lời gọi đi qua nhưng vẫn ghi nhận kết quả, metrics và các sự kiện của Circuit Breaker. Điểm khác biệt so với CLOSED là Circuit Breaker không tự chuyển sang OPEN, kể cả khi failure rate hoặc slow call rate vượt ngưỡng cấu hình.

Ví dụ, cấu hình failureRateThreshold là 50% và minimumNumberOfCalls là 10. Trong cửa sổ đánh giá có 8 lời gọi thất bại trên tổng số 10 lời gọi, tỷ lệ lỗi là 80%. Khi ở CLOSED, tỷ lệ này có thể làm Circuit Breaker chuyển sang OPEN. Khi ở METRICS_ONLY, Circuit Breaker vẫn cho phép các lời gọi tiếp tục đi đến dependency, ghi nhận tỷ lệ lỗi và phát sự kiện liên quan, nhưng không ngắt mạch.

### Khi nào nên dùng?

METRICS_ONLY đặc biệt hữu ích khi triển khai cơ chế bảo vệ theo từng giai đoạn:

1. Bắt đầu thu thập metrics để hiểu lưu lượng, tỷ lệ lỗi và độ trễ thực tế của dependency.
2. Quan sát trong điều kiện tải bình thường và các thời điểm cao điểm.
3. Đánh giá ngưỡng failure rate, slow call rate và số lời gọi tối thiểu.
4. Điều chỉnh cấu hình để giảm nguy cơ mở mạch quá sớm hoặc phản ứng quá muộn.
5. Khi đã hiểu hành vi của dependency, chuyển sang CLOSED để Circuit Breaker thực hiện bảo vệ tự động.

Chế độ này cũng hữu ích khi muốn đánh giá tác động tiềm năng của một cấu hình mới. Hệ thống có thể tiếp tục phục vụ lưu lượng trong khi đội phát triển theo dõi số lần vượt ngưỡng và so sánh với mục tiêu độ tin cậy.

### Chuyển sang METRICS_ONLY và bật lại bảo vệ

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Cho phép mọi lời gọi nhưng tiếp tục ghi nhận metrics
inventory.transitionToMetricsOnlyState();

// Khi ngưỡng đã được đánh giá, bật bảo vệ tự động
inventory.transitionToClosedState();
~~~

Trong METRICS_ONLY, việc vượt ngưỡng không có nghĩa là lưu lượng đã được bảo vệ. Dashboard có thể hiển thị failure rate cao nhưng Circuit Breaker vẫn không từ chối lời gọi. Vì vậy, cần phân biệt rõ trạng thái METRICS_ONLY với CLOSED khi đọc dashboard và cảnh báo vận hành.

## 5. Phân biệt các trạng thái dễ nhầm lẫn

### OPEN và FORCED_OPEN

Cả hai trạng thái đều từ chối lời gọi, nhưng mục đích và cách phục hồi khác nhau.

- OPEN là kết quả tự động của việc đánh giá lỗi hoặc lời gọi chậm. Sau thời gian chờ, Circuit Breaker có thể chuyển sang HALF_OPEN để thăm dò dependency.
- FORCED_OPEN là quyết định chuyển trạng thái chủ động. Circuit Breaker tiếp tục chặn lời gọi cho đến khi có thao tác chuyển trạng thái khác hoặc reset.

Vì vậy, không nên chờ hết waitDurationInOpenState để khôi phục FORCED_OPEN. Cần có thao tác vận hành tường minh.

### CLOSED và METRICS_ONLY

Cả hai đều cho phép lời gọi và ghi nhận kết quả. Khác biệt nằm ở phản ứng khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng.

- CLOSED có thể chuyển sang OPEN để ngắt lời gọi.
- METRICS_ONLY tiếp tục cho phép lời gọi và chỉ cung cấp dữ liệu quan sát.

METRICS_ONLY phù hợp để đo lường và tinh chỉnh. CLOSED phù hợp khi đã sẵn sàng thực hiện bảo vệ tự động.

### DISABLED và METRICS_ONLY

Cả hai đều cho phép mọi lời gọi. Tuy nhiên:

- DISABLED không ghi metrics và không phát sự kiện lời gọi.
- METRICS_ONLY vẫn ghi metrics và phát sự kiện, nhưng không tự mở mạch.

Nếu cần quan sát hành vi dependency, chọn METRICS_ONLY. DISABLED làm mất dữ liệu quan sát từ chính Circuit Breaker, vì vậy chỉ nên dùng khi có lý do cụ thể.

## 6. Quản lý trạng thái qua CircuitBreakerRegistry

Trong ứng dụng Spring Boot sử dụng Resilience4j, CircuitBreakerRegistry quản lý các instance Circuit Breaker theo tên. Có thể tiêm registry vào một bean quản trị để chuyển trạng thái của một dependency khi cần.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryCircuitBreakerControl {

    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakerControl(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void forceOpen() {
        breaker().transitionToForcedOpenState();
    }

    public void disable() {
        breaker().transitionToDisabledState();
    }

    public void observeOnly() {
        breaker().transitionToMetricsOnlyState();
    }

    public void resumeProtection() {
        breaker().transitionToClosedState();
    }

    public CircuitBreaker.State currentState() {
        return breaker().getState();
    }

    private CircuitBreaker breaker() {
        return registry.circuitBreaker("inventory");
    }
}
~~~

Ví dụ trên minh họa lớp quản trị trạng thái cho instance inventory. Trong ứng dụng thực tế, cần bảo đảm registry được tiêm vào là registry đang quản lý đúng Circuit Breaker được dùng trong đường gọi nghiệp vụ. Khi Spring Cloud CircuitBreaker tạo các instance qua provider Resilience4j, không nên tự tạo một registry độc lập rồi giả định rằng việc chuyển trạng thái ở registry mới sẽ tác động đến instance của factory.

Spring Cloud CircuitBreaker cung cấp API trừu tượng để thực hiện lời gọi đồng bộ hoặc reactive. Các thao tác chuyển sang FORCED_OPEN, DISABLED và METRICS_ONLY là API riêng của Resilience4j. Vì vậy, khi cần điều khiển các trạng thái đặc biệt, ứng dụng phải truy cập đúng instance Resilience4j ở tầng provider.

Tên instance phải nhất quán. Nếu mã nghiệp vụ gọi Circuit Breaker có tên inventory nhưng lớp quản trị lại điều khiển một instance có tên inventory-service, hai đối tượng có thể không phải cùng một Circuit Breaker. Khi đó, thao tác quản trị không thay đổi hành vi của lời gọi đang chạy.

## 7. Kết hợp với fallback và các cơ chế bảo vệ khác

Trạng thái đặc biệt chỉ thay đổi hành vi của Circuit Breaker. Các cơ chế khác trong chuỗi xử lý vẫn có thể hoạt động tùy cách ứng dụng cấu hình.

| Cơ chế | Ảnh hưởng khi Circuit Breaker ở trạng thái đặc biệt |
| --- | --- |
| Fallback | Có thể xử lý lỗi khi FORCED_OPEN từ chối lời gọi, nếu lời gọi được bọc bằng API có fallback. |
| Timeout / TimeLimiter | Vẫn có thể giới hạn thời gian xử lý theo cấu hình riêng. |
| Retry | Có thể tiếp tục thử lại nếu được cấu hình ở lớp khác; cần tránh tạo nhiều lần thử khi Circuit Breaker đang FORCED_OPEN. |
| Bulkhead | Vẫn giới hạn số lời gọi đồng thời nếu được áp dụng độc lập. |
| Metrics của ứng dụng | Metrics từ HTTP client, server hoặc hệ thống quan sát khác vẫn có thể tồn tại dù Circuit Breaker ở DISABLED hoặc FORCED_OPEN. |

Ví dụ với Spring Cloud CircuitBreaker, lời gọi đồng bộ có thể cung cấp fallback như sau:

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getInventory(sku),
    error -> Inventory.unavailable(sku)
);
~~~

Khi Circuit Breaker ở FORCED_OPEN, lời gọi đến inventoryClient không được thực hiện. Fallback nhận lỗi do lời gọi bị từ chối và trả về kết quả dự phòng. Kiểu kết quả fallback phải thể hiện rõ dữ liệu không khả dụng hoặc dữ liệu thay thế; không nên giả lập một kết quả nghiệp vụ thành công nếu hệ thống chưa thực sự xác nhận được điều kiện cần thiết.

Với lời gọi reactive, có thể áp dụng cùng ý tưởng bằng ReactiveCircuitBreakerFactory và fallback trả về Mono hoặc Flux phù hợp. Việc điều khiển trạng thái đặc biệt vẫn thực hiện trên đúng Circuit Breaker Resilience4j đứng sau provider.

## 8. Quy trình vận hành an toàn

Việc chuyển trạng thái có thể tác động trực tiếp đến lưu lượng giữa các dịch vụ. Nên xác định trước mục tiêu, người có quyền thao tác và cách khôi phục.

| Mục tiêu | Trạng thái nên chọn | Điều cần theo dõi |
| --- | --- | --- |
| Ngắt lời gọi đến dependency đang bảo trì | FORCED_OPEN | Số lời gọi bị từ chối, fallback, tình trạng bảo trì |
| Tạm bỏ qua Circuit Breaker trong thử nghiệm có kiểm soát | DISABLED | Timeout, lỗi client và mức sử dụng tài nguyên ở các tầng khác |
| Quan sát tỷ lệ lỗi mà không chặn lưu lượng | METRICS_ONLY | Failure rate, slow call rate, số mẫu và độ trễ |
| Bật lại cơ chế bảo vệ tự động | CLOSED | Tỷ lệ lỗi, lời gọi chậm, trạng thái dependency và phản ứng khi tải tăng |

Một quy trình vận hành có thể gồm:

1. Xác định dependency và tên Circuit Breaker chính xác.
2. Ghi nhận trạng thái hiện tại, lý do thay đổi và người thực hiện.
3. Chọn trạng thái phù hợp với mục tiêu vận hành.
4. Theo dõi fallback, tỷ lệ lỗi, độ trễ và tài nguyên của dịch vụ gọi.
5. Khi điều kiện thay đổi, chuyển trạng thái về chế độ mong muốn, thường là CLOSED để khôi phục bảo vệ tự động.
6. Xác nhận lời gọi thực tế đang đi qua đúng instance và dashboard hiển thị trạng thái mới.

Nếu cung cấp chức năng điều khiển trạng thái qua endpoint quản trị, cần giới hạn quyền truy cập và ghi audit log. Các thao tác này có thể khiến ứng dụng ngừng gọi một dependency hoặc bỏ cơ chế ngắt mạch, do đó không nên để người dùng thông thường hoặc endpoint công khai tùy ý thay đổi trạng thái.

## 9. Theo dõi và diễn giải metrics

METRICS_ONLY là trạng thái đặc biệt hữu ích cho giai đoạn quan sát vì nó tiếp tục ghi nhận metrics và phát các sự kiện liên quan đến lời gọi. Các thông tin nên theo dõi gồm:

- Tỷ lệ lời gọi thất bại và tỷ lệ lời gọi chậm.
- Số lượng lời gọi thành công, thất bại và bị từ chối.
- Thời gian phản hồi trung bình và các phân vị độ trễ.
- Các sự kiện vượt ngưỡng failure rate hoặc slow call rate.
- Trạng thái hiện tại của Circuit Breaker theo từng dependency.

Ở DISABLED và FORCED_OPEN, Resilience4j không ghi metrics và không phát sự kiện lời gọi; chỉ sự kiện chuyển trạng thái được phát. Vì thế, nếu dashboard chỉ dựa vào metrics của Circuit Breaker, dữ liệu có thể không phản ánh hoạt động của dependency trong hai trạng thái này. Có thể cần xem thêm metrics từ HTTP client, service mesh, server hoặc hệ thống giám sát bên ngoài.

Khi đọc dashboard, hãy xem cả trạng thái hiện tại và loại metrics đang có. Chẳng hạn, METRICS_ONLY cùng failure rate 90% có nghĩa là dependency đang có nhiều lỗi nhưng lời gọi vẫn được phép đi qua. FORCED_OPEN có nghĩa là Circuit Breaker chủ động chặn lời gọi; không có metrics lời gọi từ Circuit Breaker không đồng nghĩa dependency đã hết lỗi.

## 10. Những điểm cần ghi nhớ

- FORCED_OPEN chặn tất cả lời gọi và cần chuyển trạng thái tường minh để khôi phục.
- DISABLED cho phép tất cả lời gọi, đồng thời ngừng ghi metrics và phát sự kiện lời gọi.
- METRICS_ONLY cho phép tất cả lời gọi, vẫn ghi metrics và phát sự kiện, nhưng không tự chuyển sang OPEN khi vượt ngưỡng.
- OPEN là trạng thái ngắt mạch tự động và có thể chuyển sang HALF_OPEN sau thời gian chờ; FORCED_OPEN không có cơ chế tự thăm dò đó.
- METRICS_ONLY hữu ích khi triển khai theo từng giai đoạn và tinh chỉnh ngưỡng dựa trên dữ liệu thực tế.
- DISABLED không nên được dùng khi mục tiêu là quan sát; hãy chọn METRICS_ONLY cho mục tiêu đó.
- Các thao tác chuyển trạng thái phải tác động đến đúng instance Resilience4j mà đường gọi nghiệp vụ đang sử dụng.
- Fallback, timeout, retry và bulkhead có phạm vi riêng; cần kiểm tra cách chúng phối hợp khi Circuit Breaker chuyển trạng thái.

Khi triển khai Circuit Breaker trong Spring Cloud với Resilience4j, ba trạng thái đặc biệt giúp đội phát triển và vận hành chủ động kiểm soát lưu lượng và quan sát dependency trong những tình huống khác nhau. Chọn đúng trạng thái, theo dõi đúng metrics và có quy trình khôi phục rõ ràng giúp ứng dụng xử lý sự cố có kiểm soát mà không gây thêm tải hoặc che khuất tình trạng thật của dịch vụ phụ thuộc.

## Tài liệu tham khảo

- [Resilience4j CircuitBreaker — tài liệu chính thức](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j CircuitBreaker API — mã nguồn và mô tả trạng thái](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreaker.java)
- [Spring Cloud CircuitBreaker — tài liệu tham khảo](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)

