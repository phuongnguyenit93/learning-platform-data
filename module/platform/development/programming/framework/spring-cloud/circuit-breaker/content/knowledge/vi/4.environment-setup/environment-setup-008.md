# Tổ chức profile và cấu hình để tái lập hành vi

Một circuit breaker chỉ bảo vệ dịch vụ đúng như dự kiến khi ứng dụng chạy với bộ cấu hình đã được xác định rõ. Cùng một mã nguồn có thể hoạt động rất khác giữa máy phát triển, môi trường kiểm thử và production nếu `minimumNumberOfCalls`, ngưỡng lỗi, thời gian chờ hoặc timeout thay đổi. Trong Spring Cloud Circuit Breaker với Resilience4j, ta tổ chức các giá trị này theo Spring profile, dùng cấu hình mặc định làm nền, ghi đè có chủ đích theo môi trường và xác minh cấu hình thực tế khi chạy.

Mục tiêu là để một nhóm phát triển có thể trả lời được ba câu hỏi: ứng dụng đang dùng profile nào, circuit breaker nào đang được cấu hình, và những giá trị nào quyết định thời điểm mạch mở. Khi có thể tái tạo các điều kiện đó, lỗi khó tái hiện ở production sẽ dễ được kiểm tra hơn trong môi trường phát triển và kiểm thử.

## 1. Profile và cấu hình ngoài mã nguồn

Spring profile là nhãn chọn một nhóm cấu hình theo môi trường hoặc mục đích chạy. Các profile thường gặp gồm:

| Profile | Mục đích | Đặc điểm cấu hình circuit breaker |
| --- | --- | --- |
| `dev` | Phát triển trên máy cá nhân | Có thể dùng dịch vụ giả lập, cửa sổ nhỏ và thời gian chờ ngắn để quan sát chuyển trạng thái nhanh. |
| `test` | Kiểm thử tự động | Dùng số mẫu nhỏ, ngưỡng xác định và dịch vụ giả lập để kết quả có thể lặp lại. |
| `staging` | Kiểm tra trước khi phát hành | Gần production về topology, timeout và ngưỡng; dùng dữ liệu thử nghiệm. |
| `prod` | Phục vụ người dùng thật | Chọn ngưỡng theo lưu lượng, SLO và khả năng chịu tải của dịch vụ phụ thuộc. |

Profile không nên thay đổi ý nghĩa của circuit breaker. Ví dụ, ID `inventory` luôn đại diện cho circuit breaker bảo vệ lời gọi đến dịch vụ kho hàng; chỉ các giá trị như kích thước cửa sổ hoặc thời gian mở mạch mới có thể khác nhau giữa các môi trường. Dùng ID ổn định giúp cấu hình, log, metric và mã gọi cùng tham chiếu một đối tượng.

Spring Boot nạp cấu hình chung từ `application.yml` và có thể nạp thêm file theo profile đang hoạt động, chẳng hạn `application-dev.yml` hoặc `application-prod.yml`. Giá trị trong file theo profile ghi đè giá trị tương ứng ở file chung. Biến môi trường và tham số dòng lệnh cũng có thể ghi đè cấu hình file, vì vậy chỉ nhìn vào `application.yml` chưa đủ để kết luận ứng dụng đang chạy với giá trị nào.

Một cấu trúc đơn giản có thể như sau:

```text
src/main/resources/
  application.yml
  application-dev.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

Kích hoạt profile từ môi trường chạy. Ví dụ với PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
./mvnw spring-boot:run
```

Với Linux hoặc macOS:

```bash
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run
```

Trong container, đặt `SPRING_PROFILES_ACTIVE` trong cấu hình triển khai hoặc biến môi trường của container. Không nên để mỗi máy tự chọn profile theo mặc định mà không ghi lại lựa chọn đó trong hướng dẫn chạy ứng dụng.

## 2. Đặt cấu hình mặc định làm nền

Khai báo các giá trị dùng chung trong `application.yml`. Ví dụ dưới đây tạo cấu hình mặc định cho circuit breaker và gắn cấu hình đó vào instance `inventory`:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
    instances:
      inventory:
        baseConfig: default
```

Trong ví dụ này:

- `configs.default` định nghĩa bộ giá trị nền có thể tái sử dụng.
- `instances.inventory` tạo cấu hình cho một circuit breaker cụ thể và kế thừa bộ giá trị nền qua `baseConfig`.
- `slidingWindowType` và `slidingWindowSize` chọn cách lấy mẫu.
- `minimumNumberOfCalls` quy định số lời gọi tối thiểu trước khi tính tỷ lệ.
- `failureRateThreshold` và `slowCallRateThreshold` quy định hai điều kiện có thể làm mạch chuyển từ `CLOSED` sang `OPEN`.
- `slowCallDurationThreshold` xác định thời gian từ đó một lời gọi được xem là chậm.
- `waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState` điều khiển giai đoạn thử phục hồi sau khi mạch mở.

Khi ứng dụng có nhiều dịch vụ phụ thuộc, có thể tạo các instance riêng như `payment`, `catalog` hoặc `shipping`. Chỉ tạo instance khi cần theo dõi hoặc bảo vệ độc lập. Nếu mọi lời gọi dùng chung một ID dù có đặc tính lưu lượng và mức độ quan trọng khác nhau, một dịch vụ gặp lỗi có thể làm ảnh hưởng quyết định bảo vệ của dịch vụ khác.

## 3. Ghi đè theo môi trường một cách có chủ đích

File `application-dev.yml` chỉ cần khai báo các giá trị khác với cấu hình nền:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        waitDurationInOpenState: 5s
```

Khi chạy với profile `dev`, các thuộc tính trên ghi đè giá trị tương ứng của instance `inventory`; những thuộc tính không được khai báo vẫn lấy từ cấu hình nền. Cửa sổ nhỏ và thời gian mở ngắn giúp quan sát luồng `CLOSED` → `OPEN` → `HALF_OPEN` nhanh hơn trong lúc phát triển. Đây là lựa chọn để thử nghiệm, không phải giá trị mặc định nên đưa thẳng lên production.

Với profile `test`, ta có thể chọn bộ số liệu nhỏ và cố định để một bài kiểm thử có thể kích hoạt circuit breaker bằng số lời gọi đã biết:

```yaml
# application-test.yml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 1s
        permittedNumberOfCallsInHalfOpenState: 1
```

Với bốn lời gọi được ghi nhận trong cửa sổ, hai lời gọi thất bại tạo tỷ lệ lỗi `50%` và đạt ngưỡng. Trong bài kiểm thử, có thể chủ động cho cả bốn lời gọi thất bại để kết quả rõ ràng hơn. `TIME_BASED` thường phù hợp khi muốn đánh giá hành vi theo khoảng thời gian thực tế; `COUNT_BASED` thường thuận tiện hơn cho kiểm thử vì số lượng mẫu được kiểm soát trực tiếp.

Profile `staging` nên gần với production về các giới hạn quan trọng. Nếu staging dùng timeout 1 giây trong khi production dùng 5 giây, kết quả thử nghiệm về tỷ lệ lời gọi chậm sẽ không phản ánh hành vi thực tế. Profile `prod` nên chỉ ghi đè những giá trị có lý do vận hành rõ ràng, chẳng hạn lưu lượng lớn hơn, độ trễ dịch vụ phụ thuộc hoặc mục tiêu SLO khác. Tránh tạo một bộ cấu hình hoàn toàn khác cho mỗi môi trường nếu không có nhu cầu cụ thể.

## 4. Giữ ID trong mã gọi khớp với ID cấu hình

Tên instance trong YAML phải khớp với tên circuit breaker được tạo trong mã. Ví dụ với Spring Cloud CircuitBreaker API dạng đồng bộ:

```java
@Service
public class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

Ở đây, `create("inventory")` dùng cùng ID với `resilience4j.circuitbreaker.instances.inventory`. Fallback trả về kết quả dự phòng khi lời gọi thất bại hoặc circuit breaker từ chối lời gọi do đang `OPEN`. Trong ứng dụng thực tế, fallback cần phân biệt dữ liệu dự phòng hợp lệ với lỗi không thể phục hồi; không nên trả về một giá trị giả khiến tầng gọi hiểu nhầm rằng dữ liệu là mới nhất.

Với lời gọi reactive, dùng `ReactiveCircuitBreakerFactory` và giữ nguyên ID `inventory`. Cấu hình theo ID vẫn là nơi quản lý ngưỡng của circuit breaker; kiểu API reactive chỉ thay đổi cách biểu diễn tác vụ và fallback bằng `Mono` hoặc `Flux`. Hãy kiểm tra đúng starter Spring Cloud CircuitBreaker Resilience4j và phiên bản tương thích với Spring Boot đang dùng.

## 5. Cấu hình timeout và bulkhead cùng một quy ước

Circuit breaker quyết định có cho phép lời gọi mới đi tiếp hay không. Timeout giới hạn thời gian chờ của một lời gọi; bulkhead giới hạn số tác vụ đồng thời hoặc số tài nguyên được cấp cho một nhóm lời gọi. Ba cơ chế giải quyết các vấn đề khác nhau và nên có cấu hình tường minh.

Ví dụ bổ sung cấu hình TimeLimiter và bulkhead cho instance `inventory`:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventory:
        timeoutDuration: 3s
        cancelRunningFuture: true
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0s
```

Các giá trị trên minh họa cách đặt cấu hình; cần điều chỉnh theo client, mô hình đồng bộ hoặc reactive và khả năng của dịch vụ phụ thuộc. Timeout 3 giây chỉ có ý nghĩa khi loại lời gọi và integration đang dùng thực sự áp dụng TimeLimiter. Tương tự, bulkhead chỉ bảo vệ đoạn xử lý được bọc bởi cơ chế bulkhead tương ứng. Không nên cho rằng khai báo thuộc tính trong YAML tự động giới hạn mọi luồng HTTP hoặc mọi tác vụ nền.

Khi thay đổi timeout, hãy xem lại `slowCallDurationThreshold`. Nếu timeout ngắn hơn ngưỡng lời gọi chậm, lời gọi có thể kết thúc bằng timeout trước khi được ghi nhận là lời gọi chậm theo ngưỡng đó. Nếu timeout dài hơn nhiều, các lời gọi chậm có thể chiếm tài nguyên lâu trước khi circuit breaker mở. Các giá trị cần được thiết kế cùng nhau dựa trên thời gian phản hồi mong muốn và ngân sách độ trễ của luồng nghiệp vụ.

## 6. Tái lập điều kiện trong kiểm thử

Một bài kiểm thử đáng tin cậy cần cố định profile, cấu hình, kết quả của dịch vụ phụ thuộc và dữ liệu đầu vào. Không nên dựa vào một dịch vụ bên ngoài đang hoạt động bình thường hay lỗi ngẫu nhiên trên mạng để kiểm tra circuit breaker.

Ví dụ kiểm thử dưới đây sử dụng profile `test` và `CircuitBreakerRegistry` của Resilience4j. Giả sử ứng dụng đã có dependency Spring Boot integration tương ứng để đăng ký registry thành bean:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@ActiveProfiles("test")
class InventoryCircuitBreakerConfigTest {

    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void opensWhenFailureRateReachesConfiguredThreshold() {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");
        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("simulated dependency failure");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
    }
}
```

Với `minimumNumberOfCalls: 4` và `failureRateThreshold: 50`, bốn kết quả lỗi làm tỷ lệ lỗi đạt `100%`; circuit breaker chuyển sang `OPEN`. Bài kiểm thử dùng exception được tạo ngay trong tiến trình nên không phụ thuộc mạng. Nếu cấu hình ứng dụng có quy tắc `recordExceptions` hoặc `ignoreExceptions`, cần bảo đảm exception thử nghiệm được phân loại là lỗi.

Để kiểm tra fallback, gọi lớp service qua API Spring Cloud CircuitBreaker và xác minh kết quả fallback khi circuit breaker đã mở. Để kiểm tra timeout, dùng tác vụ giả lập có thời gian chạy được kiểm soát và xác minh kết quả timeout. Để kiểm tra bulkhead, tạo nhiều tác vụ đồng thời có latch hoặc barrier để điều khiển thời điểm bắt đầu và kết thúc. Mỗi bài kiểm thử nên kiểm tra một cơ chế chính để dễ xác định nguyên nhân khi thất bại.

`waitDurationInOpenState` có thể khiến bài kiểm thử phụ thuộc thời gian nếu kiểm tra chuyển sang `HALF_OPEN`. Với bài kiểm thử trạng thái, đặt thời gian ngắn nhưng cố định và điều khiển thời điểm gọi; với kiểm thử logic khác, có thể dùng clock hoặc cơ chế đồng bộ mà phiên bản thư viện hỗ trợ. Tránh dùng `Thread.sleep` dài để chờ trạng thái nếu có cách đồng bộ rõ ràng hơn.

## 7. Xác minh cấu hình thực tế khi ứng dụng chạy

Khi một circuit breaker không mở như dự kiến, hãy kiểm tra lần lượt:

1. Profile đang hoạt động có đúng không? Xác nhận giá trị `spring.profiles.active` từ môi trường khởi chạy.
2. Instance ID có trùng nhau giữa mã gọi và YAML không? Ví dụ cả hai phải dùng `inventory`.
3. `minimumNumberOfCalls` đã đạt chưa? Nếu chưa đủ mẫu, tỷ lệ lỗi chưa kích hoạt chuyển trạng thái.
4. Các exception có được ghi nhận là lỗi không? Exception bị bỏ qua hoặc không thuộc nhóm ghi nhận có thể làm tỷ lệ khác dự kiến.
5. Có biến môi trường, tham số dòng lệnh hoặc nguồn cấu hình bên ngoài nào ghi đè YAML không?
6. Cấu hình timeout, slow-call và bulkhead có phù hợp với loại lời gọi thực tế không?

Spring Boot Actuator có thể hỗ trợ quan sát cấu hình và trạng thái. Trong môi trường phát triển, có thể bật các endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops,metrics
```

Endpoint `env` giúp kiểm tra nguồn thuộc tính và giá trị đang có hiệu lực; `configprops` hỗ trợ xem các cấu hình đã bind; `health` và `metrics` giúp quan sát tình trạng ứng dụng và số liệu được tích hợp. Chỉ expose các endpoint cần thiết, giới hạn quyền truy cập và không công khai `env` hoặc `configprops` ra Internet vì chúng có thể tiết lộ thông tin cấu hình nhạy cảm. Có thể dùng Micrometer cùng hệ thống giám sát để theo dõi trạng thái circuit breaker, số lời gọi thành công/thất bại/bị từ chối và tỷ lệ lỗi hoặc lời gọi chậm.

Khi dùng Spring Cloud Config hoặc một nguồn cấu hình tập trung, hãy ghi lại phiên bản hoặc nhãn cấu hình đã được ứng dụng nạp. Khi dùng container, ghi lại image tag, profile và các biến môi trường liên quan. Một bản ghi triển khai hữu ích nên cho biết phiên bản ứng dụng, phiên bản cấu hình, profile và ID instance circuit breaker. Nhờ vậy, nhóm có thể tái tạo cấu hình khi so sánh một lần chạy tốt với một lần chạy gặp sự cố.

## 8. Quy ước để cấu hình có thể tái lập

- Giữ một cấu hình nền trong `application.yml`; chỉ ghi đè ở profile khi có lý do cụ thể.
- Giữ ID circuit breaker ổn định giữa YAML, mã gọi, metric và log.
- Đặt tường minh cửa sổ, số mẫu tối thiểu, ngưỡng lỗi, ngưỡng lời gọi chậm và thời gian mở mạch.
- Chọn `COUNT_BASED` khi muốn kiểm soát số mẫu; chọn `TIME_BASED` khi cần đánh giá theo khoảng thời gian thực tế.
- Cố định profile và mô phỏng kết quả dịch vụ phụ thuộc trong kiểm thử tự động.
- Đồng bộ timeout, ngưỡng lời gọi chậm và giới hạn bulkhead theo ngân sách độ trễ và năng lực dịch vụ.
- Quản lý phiên bản Spring Boot, Spring Cloud và Resilience4j tương thích bằng dependency management; tránh để mỗi môi trường tự kéo một phiên bản khác nhau.
- Lưu cấu hình không bí mật trong kho mã nguồn; đưa mật khẩu, token và thông tin nhạy cảm vào biến môi trường hoặc secret manager.
- Theo dõi cấu hình có hiệu lực và trạng thái circuit breaker bằng Actuator, Micrometer hoặc hệ thống giám sát tương ứng.

Khi các quy ước này được áp dụng, nhóm có thể chạy lại cùng một kịch bản với cùng profile và cùng bộ cấu hình, kiểm tra chính xác lúc circuit breaker mở, lúc fallback được gọi và cách hệ thống phục hồi. Điều đó giúp việc phát triển, kiểm thử và vận hành Spring Cloud Circuit Breaker nhất quán hơn giữa các môi trường.
