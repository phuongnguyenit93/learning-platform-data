# Triển khai cấu hình ngắt mạch theo profile và phạm vi dịch vụ

Trong hệ thống Spring Cloud, mỗi service gọi tới một hoặc nhiều dependency với lưu lượng, độ trễ và mức độ quan trọng khác nhau. Circuit breaker cần được cấu hình theo môi trường chạy và theo đúng ranh giới lời gọi mà nó bảo vệ. Profile giúp chọn bộ cấu hình phù hợp cho `dev`, `test`, `staging` hoặc `prod`; instance ID giúp tách chính sách cho từng dependency hoặc nhóm thao tác trong service gọi.

Với Resilience4j, cấu hình thường được nạp vào từng tiến trình Spring Boot. Vì vậy, cùng một profile có thể cung cấp ngưỡng giống nhau cho các replica, nhưng trạng thái `CLOSED`/`OPEN`/`HALF_OPEN` và sliding window vẫn là dữ liệu cục bộ của từng replica. Cấu hình theo profile không tạo ra một circuit breaker dùng chung toàn cluster.

## 1. Tách ba khái niệm: ứng dụng, profile và breaker instance

Ba khái niệm này giải quyết ba câu hỏi khác nhau:

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Tên ứng dụng (`spring.application.name`) | `order-service` | Xác định service đang chạy và thường được dùng để chọn cấu hình riêng của service trong môi trường triển khai hoặc Config Server |
| Spring profile | `dev`, `test`, `staging`, `prod` | Chọn các giá trị cấu hình phù hợp với môi trường hoặc mục đích chạy |
| Circuit breaker instance ID | `inventoryRead`, `inventoryReserve`, `paymentAuthorize` | Xác định ranh giới dependency hoặc thao tác mà một breaker bảo vệ trong tiến trình hiện tại |

Ví dụ, `order-service` có thể gọi Inventory Service để đọc tồn kho và giữ hàng. Hai thao tác có đặc tính khác nhau: đọc tồn kho có thể chấp nhận cache ngắn hạn, còn giữ hàng là command có side effect và cần chính sách timeout, retry, fallback chặt chẽ hơn. Có thể tạo hai breaker riêng là `inventoryRead` và `inventoryReserve`.

Không dùng profile để thay thế instance ID. Profile chọn bộ giá trị cho môi trường; instance ID tách các ranh giới gọi trong cùng service. Cũng không tạo breaker riêng cho từng user, order hoặc request vì điều đó làm số instance và metric tăng không kiểm soát, đồng thời mỗi breaker có quá ít mẫu để đánh giá.

## 2. Đặt cấu hình nền trong application.yml

Đặt các giá trị mặc định dùng chung trong `src/main/resources/application.yml`. Dùng `configs` để định nghĩa các bộ chính sách và `instances` để gán chính sách đó cho từng dependency:

```yaml
spring:
  application:
    name: order-service

resilience4j:
  circuitbreaker:
    configs:
      readDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
      writeDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 40
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
    instances:
      inventoryRead:
        baseConfig: readDefault
      inventoryReserve:
        baseConfig: writeDefault
      paymentAuthorize:
        baseConfig: writeDefault
```

Trong ví dụ:

- `readDefault` dùng cho thao tác đọc; cửa sổ có 20 lời gọi và cần ít nhất 10 mẫu trước khi tính tỷ lệ.
- `writeDefault` có ngưỡng thận trọng hơn cho thao tác ghi và số probe `HALF_OPEN` thấp hơn.
- `inventoryRead`, `inventoryReserve` và `paymentAuthorize` là các ID được mã gọi sử dụng.
- `baseConfig` giúp tái sử dụng chính sách, đồng thời cho phép mỗi instance ghi đè các thuộc tính riêng khi cần.

Các giá trị trên chỉ minh họa. Cần chọn cửa sổ, số mẫu tối thiểu, ngưỡng lỗi, ngưỡng lời gọi chậm và thời gian mở dựa trên lưu lượng, SLO, timeout client và năng lực của dependency. Không sao chép nguyên một bộ ngưỡng sang mọi service nếu đặc tính của các dependency khác nhau.

## 3. Ghi đè theo profile

Spring Boot có thể nạp file cấu hình theo profile như `application-dev.yml` hoặc `application-prod.yml`. Các thuộc tính được khai báo ở file profile có độ ưu tiên cao hơn giá trị tương ứng trong cấu hình chung. Những thuộc tính không được ghi đè tiếp tục dùng giá trị nền.

Ví dụ `application-dev.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 6
        minimumNumberOfCalls: 3
        waitDurationInOpenState: 3s
      inventoryReserve:
        slidingWindowSize: 6
        minimumNumberOfCalls: 3
        waitDurationInOpenState: 5s
```

Ở môi trường phát triển, cửa sổ nhỏ và thời gian mở ngắn giúp quan sát chuyển trạng thái nhanh. Những giá trị này phục vụ thử nghiệm, không nên tự động đưa lên production vì lưu lượng dev thường thấp và không đại diện cho phân phối request thực tế.

Ví dụ `application-test.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 1m
        permittedNumberOfCallsInHalfOpenState: 1
```

Profile test dùng số mẫu nhỏ, cố định để kiểm thử chuyển trạng thái có thể lặp lại. Ví dụ bốn lời gọi thất bại trong cửa sổ bốn mẫu tạo failure rate 100%, vượt ngưỡng 50% và mở breaker.

Ví dụ `application-prod.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowSize: 50
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      paymentAuthorize:
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30
        slowCallDurationThreshold: 900ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
```

Production dùng số mẫu và ngưỡng được chọn theo hành vi thật của từng dependency. Ví dụ payment có thể cần ngưỡng và số probe khác inventory vì hậu quả của command thanh toán và khả năng xử lý của dependency khác nhau. Cần đánh giá bằng metric và thử nghiệm tải trước khi phát hành thay đổi.

## 4. Kích hoạt profile đúng ở mỗi môi trường

Profile có thể được chọn bằng biến môi trường, tham số dòng lệnh hoặc cấu hình triển khai. Ví dụ PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
./mvnw spring-boot:run
```

Ví dụ Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
```

Có thể truyền profile qua tham số ứng dụng:

```bash
java -jar order-service.jar --spring.profiles.active=staging
```

Trong Kubernetes hoặc nền tảng container, đặt `SPRING_PROFILES_ACTIVE` trong manifest, Helm values hoặc cấu hình môi trường của deployment. Không nên để mỗi pod tự chọn profile khác nhau ngoài chủ đích; các replica của cùng một deployment thường cần cùng profile và cùng phiên bản cấu hình.

Thứ tự ưu tiên cấu hình còn chịu ảnh hưởng của biến môi trường, tham số dòng lệnh, nguồn cấu hình bên ngoài và cơ chế nạp cấu hình mà ứng dụng bật. Khi một giá trị không như dự kiến, hãy kiểm tra nguồn cấu hình có hiệu lực thay vì chỉ đọc file `application.yml`.

## 5. ID trong mã gọi phải khớp với instance cấu hình

Khi dùng Spring Cloud CircuitBreaker với Resilience4j backend, ID truyền vào factory phải trùng với tên trong `resilience4j.circuitbreaker.instances`:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

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
        return circuitBreakerFactory.create("inventoryRead").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

`create("inventoryRead")` dùng đúng instance đã khai báo trong YAML. Nếu mã gọi dùng `inventory` nhưng YAML chỉ có `inventoryRead`, ứng dụng có thể tạo hoặc sử dụng cấu hình mặc định ngoài dự kiến. Hãy thống nhất ID giữa YAML, mã gọi, fallback, log và dashboard.

Với Resilience4j native API hoặc annotation, nguyên tắc tương tự: tên truyền vào `registry.circuitBreaker("...")` hoặc `@CircuitBreaker(name = "...")` phải khớp ID được cấu hình. Trong một service, nên quản lý danh sách ID ở một nơi dễ kiểm tra và tránh viết tên rải rác không nhất quán.

## 6. Chọn phạm vi instance theo dependency và thao tác

Không phải lúc nào một dependency cũng chỉ cần một breaker. Hãy tách instance khi hai nhóm lời gọi có mục tiêu bảo vệ khác nhau rõ ràng:

| Ranh giới | Ví dụ ID | Lý do có thể tách |
| --- | --- | --- |
| Đọc dữ liệu inventory | `inventoryRead` | Có thể dùng cache và chấp nhận độ trễ khác với command ghi |
| Giữ hoặc giải phóng tồn kho | `inventoryReserve` | Có side effect, cần phân loại lỗi và fallback khác |
| Ủy quyền thanh toán | `paymentAuthorize` | Có idempotency và hậu quả nghiệp vụ riêng |
| Tra cứu trạng thái thanh toán | `paymentStatusRead` | Có thể có SLO và timeout khác command authorize |

Tách breaker giúp một luồng gọi chậm không làm tăng failure rate của một luồng khác. Tuy nhiên, tạo quá nhiều breaker cũng làm giảm số mẫu mỗi instance, tăng metric và khiến vận hành khó quản lý. Chỉ tách khi lưu lượng, SLO, loại lỗi hoặc chính sách phục hồi thực sự khác nhau.

Circuit breaker nằm ở caller và bảo vệ lời gọi từ caller đó. Một `inventoryRead` trong Order Service không tự bảo vệ Inventory Service trước các caller khác. Mỗi microservice cần quản lý cấu hình cho các dependency mà chính nó gọi; không dùng một file profile của service này như thể nó tự động áp dụng cho mọi service trong hệ thống.

## 7. Phối hợp circuit breaker với timeout và bulkhead

Profile nên quản lý các giới hạn có liên quan cùng nhau. Circuit breaker ngăn lời gọi mới sau khi phát hiện dependency suy giảm; timeout giới hạn thời gian chờ của request; bulkhead giới hạn tài nguyên đồng thời mà dependency có thể chiếm.

Ví dụ cấu hình cho `inventoryRead`:

```yaml
resilience4j:
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 900ms
        cancelRunningFuture: true
  bulkhead:
    instances:
      inventoryRead:
        maxConcurrentCalls: 30
        maxWaitDuration: 0ms
```

Các giá trị TimeLimiter có ý nghĩa với kiểu tác vụ bất đồng bộ mà integration hỗ trợ, chẳng hạn `Future` hoặc `CompletionStage`. Với HTTP client blocking, vẫn cần cấu hình connect/response/read timeout trực tiếp ở client; không giả định TimeLimiter tự dừng mọi thread đang block. Bulkhead semaphore giới hạn số lời gọi đồng thời qua instance; nếu dùng thread-pool bulkhead, cần cấu hình pool và queue theo mô hình thực thi.

Giữ các ID thống nhất giữa circuit breaker, TimeLimiter và bulkhead khi chúng cùng bảo vệ một ranh giới. Đồng thời kiểm tra thứ tự Retry/Bulkhead/TimeLimiter và không retry lỗi từ chối do hết permit hoặc `CallNotPermittedException` nếu việc retry không thể giúp ích.

## 8. Cấu hình tập trung và tính nhất quán giữa service

Trong hệ thống nhiều microservice, có thể quản lý cấu hình theo tên ứng dụng và profile bằng Spring Cloud Config hoặc cơ chế cấu hình tập trung của nền tảng. Ví dụ Order Service nhận bộ cấu hình cho `inventoryRead` và `paymentAuthorize`, trong khi Catalog Service có thể có ID và ngưỡng riêng cho các dependency mà nó gọi.

Một quy trình cấu hình tập trung nên có:

1. Tên ứng dụng rõ ràng, ổn định để chọn đúng cấu hình của service.
2. Profile được chọn rõ ràng theo môi trường.
3. Phiên bản hoặc label cấu hình có thể truy vết.
4. Thay đổi ngưỡng được review và kiểm thử trước khi phát hành.
5. Triển khai theo canary hoặc rollout có kiểm soát khi thay đổi ảnh hưởng tới tải dependency.
6. Kế hoạch rollback về phiên bản cấu hình trước đó.

Không giả định refresh cấu hình từ xa sẽ tự động cập nhật mọi circuit breaker instance đang tồn tại. Khả năng refresh phụ thuộc integration và phiên bản; cần xác minh cơ chế cập nhật runtime mà ứng dụng đang dùng. Nếu không có hỗ trợ cập nhật an toàn, áp dụng thay đổi bằng rollout/restart có kiểm soát để mọi replica nạp cùng phiên bản cấu hình.

Profile chỉ chọn giá trị cấu hình; nó không đồng bộ state hoặc sliding window giữa replica. Sau khi triển khai, các pod có thể cùng cấu hình nhưng vẫn ở trạng thái breaker khác nhau do lịch sử lời gọi khác nhau.

## 9. Kiểm tra cấu hình có hiệu lực

Khi breaker mở quá sớm, không mở khi cần hoặc không áp dụng đúng profile, kiểm tra lần lượt:

1. `spring.application.name` có đúng tên service đang triển khai không?
2. `spring.profiles.active` có đúng profile dự kiến không?
3. Nguồn cấu hình ngoài, biến môi trường hoặc tham số dòng lệnh có ghi đè thuộc tính không?
4. ID trong mã gọi có khớp `instances` trong YAML không?
5. Instance có kế thừa đúng `baseConfig` không?
6. `minimumNumberOfCalls` đã đạt chưa và sliding window có đủ lưu lượng không?
7. Exception có được ghi nhận hay bị ignore theo cấu hình không?
8. Timeout và bulkhead có cùng ranh giới với breaker không?

Trong môi trường phát triển, Spring Boot Actuator có thể hỗ trợ xem thuộc tính và metric đang hoạt động. Endpoint `env` hoặc `configprops` có thể tiết lộ giá trị cấu hình nhạy cảm; chỉ bật khi cần, giới hạn truy cập và không expose công khai. Với production, ưu tiên log startup có cấu trúc gồm application name, active profile, phiên bản cấu hình và danh sách breaker ID (không log secret).

Có thể kiểm tra metric theo breaker ID để xác nhận instance đang được sử dụng. Kết hợp metric với state transition event giúp biết một breaker đang mở vì tỷ lệ lỗi, tỷ lệ lời gọi chậm hay do thao tác quản trị.

## 10. Kiểm thử profile và chính sách breaker

Mỗi profile nên có mục đích rõ ràng. Dùng `@ActiveProfiles("test")` để bảo đảm bài kiểm thử nạp cấu hình test thay vì vô tình dùng `dev` hoặc `prod`:

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
class InventoryCircuitBreakerProfileTest {

    @Autowired
    CircuitBreakerRegistry registry;

    @Test
    void testProfileOpensInventoryBreakerAfterConfiguredSamples() {
        CircuitBreaker breaker = registry.circuitBreaker("inventoryRead");

        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("simulated inventory failure");
            })).isInstanceOf(IllegalStateException.class);
        }

        assertThat(breaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
    }
}
```

Ví dụ giả định Spring Boot Resilience4j integration đã đăng ký `CircuitBreakerRegistry` và `application-test.yml` đặt `minimumNumberOfCalls: 4`, `slidingWindowSize: 4`, `failureRateThreshold: 50`. Bốn supplier lỗi tạo tỷ lệ lỗi 100%, vì vậy breaker mở. Dùng exception được cấu hình là lỗi; nếu có `ignoreExceptions` hoặc `recordExceptions`, điều chỉnh test theo quy tắc phân loại thực tế.

Ngoài kiểm thử trạng thái, nên có kiểm thử xác nhận:

- Profile `dev` dùng cửa sổ nhỏ để thử nghiệm nhanh.
- Profile `prod` dùng giá trị được review và phù hợp với lưu lượng thực tế.
- ID trong mã gọi tạo đúng instance cấu hình.
- Hai dependency có chính sách riêng không dùng chung một breaker ngoài chủ đích.
- Fallback và timeout phản hồi đúng hợp đồng nghiệp vụ.
- Thay đổi cấu hình không tạo ra đợt probe hoặc request dồn dập ngoài khả năng dependency.

Không dùng chung breaker instance giữa các test nếu không reset trạng thái hoặc tạo fixture mới. Trạng thái `OPEN` từ test trước có thể làm test sau nhận `CallNotPermittedException` ngay cả khi test đang muốn kiểm tra supplier.

## 11. Triển khai thay đổi cấu hình an toàn

Thay đổi `failureRateThreshold`, `slowCallRateThreshold`, `minimumNumberOfCalls` hoặc `waitDurationInOpenState` có thể làm thay đổi đáng kể lượng request đi tới dependency. Nên triển khai theo quy trình:

1. Xác định dependency và breaker ID chịu ảnh hưởng.
2. Dùng metric hiện tại để xem lưu lượng, phân phối latency và tỷ lệ lỗi.
3. Thay đổi một nhóm thuộc tính có liên quan và ghi lại lý do.
4. Kiểm thử bằng profile test và thử nghiệm tải với phân phối request đại diện.
5. Phát hành canary hoặc một nhóm replica trước nếu nền tảng hỗ trợ.
6. Theo dõi state transition, call-not-permitted, fallback, p95/p99 và metric phía dependency.
7. Mở rộng rollout hoặc rollback nếu dependency bị tăng tải, breaker mở quá thường xuyên hoặc request đầu-cuối suy giảm.

Không đóng tất cả breaker hoặc reset thống kê chỉ để làm dashboard trông sạch sau khi đổi cấu hình. Reset làm mất số liệu tích lũy và mở lại đường gọi; chỉ thực hiện khi có lý do vận hành rõ ràng. Khi cấu hình mới được nạp, theo dõi hành vi thực tế và giữ log/audit về phiên bản cấu hình đã triển khai.

## 12. Những lỗi cấu hình thường gặp

- **Dùng một cấu hình cho mọi môi trường:** ngưỡng phù hợp với test hoặc dev có thể quá nhạy hoặc quá chậm trong production.
- **Dùng một breaker cho nhiều dependency:** lỗi của dependency này có thể làm mở breaker cho dependency khác.
- **ID YAML không khớp mã gọi:** instance dự kiến có thể không được sử dụng.
- **Đặt `minimumNumberOfCalls` quá cao:** lưu lượng không đủ mẫu khiến breaker không đánh giá tỷ lệ.
- **Đặt `minimumNumberOfCalls` quá thấp:** một vài lỗi ngẫu nhiên có thể làm breaker mở quá sớm.
- **Tưởng profile đồng bộ trạng thái:** các replica vẫn giữ state và sliding window riêng.
- **Tưởng Config refresh luôn cập nhật instance đang chạy:** phải xác minh hỗ trợ runtime của integration hoặc dùng rollout phù hợp.
- **Dùng `dev` profile trong production:** cửa sổ nhỏ và thời gian mở ngắn có thể tạo chuyển trạng thái liên tục.
- **Không quản lý phiên bản cấu hình:** khó truy vết vì sao hai replica có hành vi khác nhau.

## 13. Quy tắc vận hành

- Dùng `spring.application.name` để xác định service và Spring profile để chọn cấu hình môi trường.
- Dùng breaker ID ổn định theo dependency hoặc thao tác có SLO/chính sách lỗi riêng.
- Đặt cấu hình nền bằng `configs` và gán instance qua `baseConfig`; chỉ ghi đè profile khi có lý do.
- Giữ profile của các replica trong cùng deployment nhất quán, trừ khi đang thực hiện canary có chủ đích.
- Kiểm tra cấu hình có hiệu lực, ID instance và nguồn ghi đè khi điều tra sự cố.
- Quản lý timeout, bulkhead và retry cùng ranh giới với circuit breaker.
- Không xem profile là cơ chế chia sẻ trạng thái giữa các tiến trình.
- Quản lý cấu hình tập trung bằng phiên bản có thể truy vết, review và rollback.
- Theo dõi state, failure rate, slow-call rate, not-permitted, fallback và latency đầu-cuối sau mỗi lần thay đổi.

Triển khai theo profile và phạm vi dịch vụ giúp mỗi microservice dùng ngưỡng phù hợp với môi trường, đồng thời tách chính sách bảo vệ cho từng dependency. Khi ID được quản lý nhất quán, cấu hình có phiên bản và trạng thái cục bộ được quan sát riêng, nhóm vận hành có thể thay đổi chính sách circuit breaker mà vẫn kiểm soát được tác động lên dependency và trải nghiệm người dùng.
