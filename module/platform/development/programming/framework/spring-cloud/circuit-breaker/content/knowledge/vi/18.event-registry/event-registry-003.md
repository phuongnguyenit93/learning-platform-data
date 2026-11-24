# Đọc cấu hình, trạng thái và snapshot thống kê

Resilience4j quản lý các Circuit Breaker thông qua `CircuitBreakerRegistry`. Registry giúp ứng dụng tìm những mạch đã được tạo, xem các cấu hình dùng chung đã đăng ký và nhận sự kiện khi một mạch được thêm hoặc thay thế. Mỗi Circuit Breaker lại cung cấp trạng thái runtime và metrics của sliding window. Khi kết hợp Spring Cloud CircuitBreaker, cần phân biệt registry của Resilience4j với factory abstraction mà Feign hoặc service đang sử dụng để tránh đọc nhầm một mạch khác.

Ba nhóm thông tin cần quan sát có ý nghĩa khác nhau:

- **Cấu hình:** chính sách áp dụng khi Circuit Breaker được tạo, như kích thước sliding window, ngưỡng lỗi, ngưỡng lời gọi chậm và thời gian chờ ở `OPEN`.
- **Trạng thái:** trạng thái runtime hiện tại `CLOSED`, `OPEN`, `HALF_OPEN` hoặc trạng thái đặc biệt như `DISABLED`, `FORCED_OPEN`.
- **Snapshot thống kê:** số mẫu trong cửa sổ, số lời gọi thành công/thất bại, số lời gọi chậm, số lần bị từ chối và các tỷ lệ hiện tại.

Đọc riêng từng nhóm giúp trả lời đúng câu hỏi vận hành: mạch được cấu hình ra sao, hiện tại có cho phép gọi không, và dữ liệu nào khiến nó chuyển trạng thái.

## Registry quản lý những gì?

`CircuitBreakerRegistry` là nơi Resilience4j tạo và tra cứu các instance theo tên. Mỗi instance có trạng thái, event publisher và metrics riêng. Những instance cùng tên trong cùng registry được dùng chung, nhờ đó các lời gọi đến cùng dependency có thể chia sẻ một sliding window và cùng quyết định mở mạch.

Trong ứng dụng Spring Boot đã tích hợp Resilience4j, có thể inject registry do auto-configuration cung cấp:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Component;

@Component
class CircuitBreakerRegistryAccess {

    private final CircuitBreakerRegistry registry;

    CircuitBreakerRegistryAccess(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }
}
```

Không tự tạo một `CircuitBreakerRegistry.ofDefaults()` mới chỉ để đọc trạng thái nếu ứng dụng đã có registry được cấu hình. Registry mới là một vùng quản lý riêng; các mạch trong đó không tự động phản ánh những lời gọi mà Spring Cloud CircuitBreaker factory đang bảo vệ.

Một điểm cần chú ý: `registry.circuitBreaker("catalog")` là thao tác lấy hoặc tạo instance. Nếu tên chưa tồn tại, lời gọi này có thể tạo một Circuit Breaker mới với cấu hình mặc định. Khi chỉ muốn kiểm tra những instance đang hoạt động, hãy duyệt `getAllCircuitBreakers()` và tìm theo tên:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

CircuitBreaker findExisting(String name) {
    return registry.getAllCircuitBreakers().stream()
        .filter(circuitBreaker -> circuitBreaker.getName().equals(name))
        .findFirst()
        .orElse(null);
}
```

Nếu kết quả là `null`, registry đang được kiểm tra không có instance đó. Đừng gọi `circuitBreaker(name)` ngay trong code giám sát để làm mất dấu hiệu này; trước tiên hãy xác minh tên và registry mà factory thực tế sử dụng.

## Đọc cấu hình mặc định và cấu hình dùng chung

Registry cung cấp cấu hình mặc định và các cấu hình dùng chung đã đăng ký. Có thể đọc chúng bằng `getDefaultConfig()` và `getAllConfigurations()`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

void logRegisteredConfigurations() {
    CircuitBreakerConfig defaults = registry.getDefaultConfig();
    log.info("Default Circuit Breaker: windowType={}, windowSize={}, minimumCalls={}, "
            + "failureThreshold={}%, slowThreshold={}%, slowDuration={}",
        defaults.getSlidingWindowType(),
        defaults.getSlidingWindowSize(),
        defaults.getMinimumNumberOfCalls(),
        defaults.getFailureRateThreshold(),
        defaults.getSlowCallRateThreshold(),
        defaults.getSlowCallDurationThreshold());

    registry.getAllConfigurations().forEach((name, config) ->
        log.info("Shared config {}: windowType={}, windowSize={}, minimumCalls={}",
            name,
            config.getSlidingWindowType(),
            config.getSlidingWindowSize(),
            config.getMinimumNumberOfCalls()));
}
```

Có thể truy vấn một cấu hình dùng chung theo tên bằng `registry.getConfiguration("sharedProfile")`. Giá trị này là cấu hình đã đăng ký dưới tên profile đó. Không mặc định rằng tên instance `catalog` cũng là tên cấu hình dùng chung `catalog`; hai khái niệm có thể khác nhau.

Ví dụ properties khai báo instance và shared config:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      backendDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
    instances:
      catalog:
        baseConfig: backendDefault
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 3
```

Trong ví dụ, `backendDefault` là cấu hình dùng chung; `catalog` là instance dùng cấu hình cơ sở đó và bổ sung các giá trị riêng. Khi điều tra cấu hình thực tế, cần xem cả profile dùng chung, thuộc tính instance và mọi customizer áp dụng trong ứng dụng.

### Phân biệt cấu hình registry với cấu hình hiệu lực của factory

Spring Cloud CircuitBreaker tạo wrapper thông qua `Resilience4JCircuitBreakerFactory` hoặc reactive factory. Registry chỉ phản ánh các instance do chính registry đó quản lý. Nếu ứng dụng có nhiều registry hoặc customizer tạo cấu hình riêng cho factory, việc inject một registry bất kỳ không đảm bảo đang đọc đúng instance được Feign hay service sử dụng.

Ngoài ra, API registry cho phép đọc cấu hình mặc định và named shared configurations, nhưng không nên coi `getConfiguration("catalog")` là bản sao chắc chắn của mọi giá trị hiệu lực trên instance `catalog`. Với cấu hình instance-specific, hãy xác minh nguồn cấu hình mà ứng dụng đã nạp, tên Circuit Breaker thực tế và customizer áp dụng khi tạo mạch. Trong Spring Cloud CircuitBreaker, property-based configuration có độ ưu tiên cao hơn Java `Customizer`; vì vậy, một customizer không nhất thiết ghi đè được giá trị đã khai báo trong `application.yml`.

Một cách thực tế là ghi lại cấu hình đã chọn tại đúng nơi tạo instance hoặc customizer. Chỉ ghi các thuộc tính cần vận hành, tránh log predicate, object nội bộ hoặc dữ liệu có thể chứa thông tin nhạy cảm.

## Đọc trạng thái runtime

Sau khi tìm được instance hiện có, gọi `getState()` để đọc trạng thái:

```java
CircuitBreaker circuitBreaker = findExisting("catalog");
if (circuitBreaker == null) {
    log.warn("Không tìm thấy Circuit Breaker catalog trong registry này");
    return;
}

log.info("Circuit Breaker {} đang ở trạng thái {}",
    circuitBreaker.getName(), circuitBreaker.getState());
```

Các trạng thái thường gặp:

| Trạng thái | Ý nghĩa | Hành vi với lời gọi mới |
|---|---|---|
| `CLOSED` | Mạch đang theo dõi kết quả trong sliding window | Cho phép gọi và ghi nhận kết quả |
| `OPEN` | Mạch đang ngắt lời gọi vì điều kiện bảo vệ đã bị vi phạm | Từ chối nhanh, thường phát `CallNotPermittedException` |
| `HALF_OPEN` | Mạch đang thăm dò khả năng phục hồi | Chỉ cấp quyền cho số lời gọi thử đã cấu hình |
| `DISABLED` | Cơ chế bảo vệ bị vô hiệu hóa | Không áp dụng chặn theo ngưỡng thông thường |
| `FORCED_OPEN` | Mạch bị ép mở bằng thao tác quản trị | Từ chối lời gọi cho đến khi trạng thái được thay đổi |

`getState()` là ảnh chụp trạng thái tại thời điểm đọc. Một request khác có thể làm trạng thái thay đổi ngay sau đó. Vì vậy, không dùng kết quả đọc trạng thái như một khóa đồng bộ để quyết định có gọi dependency hay không; hãy để chính Circuit Breaker thực hiện phép kiểm tra quyền gọi.

## Đọc snapshot thống kê của sliding window

`getMetrics()` trả về metrics của Circuit Breaker. Các chỉ số hữu ích gồm số mẫu đang được lưu, số lời gọi thành công, thất bại, bị từ chối, số lời gọi chậm và failure/slow call rate:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

void logSnapshot(CircuitBreaker circuitBreaker) {
    CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

    int buffered = metrics.getNumberOfBufferedCalls();
    int successful = metrics.getNumberOfSuccessfulCalls();
    int failed = metrics.getNumberOfFailedCalls();
    int notPermitted = metrics.getNumberOfNotPermittedCalls();
    int slow = metrics.getNumberOfSlowCalls();
    float failureRate = metrics.getFailureRate();
    float slowCallRate = metrics.getSlowCallRate();

    log.info("CircuitBreaker {}: state={}, buffered={}, success={}, failed={}, "
            + "notPermitted={}, slow={}, failureRate={}%, slowCallRate={}%",
        circuitBreaker.getName(),
        circuitBreaker.getState(),
        buffered,
        successful,
        failed,
        notPermitted,
        slow,
        failureRate,
        slowCallRate);
}
```

`getNumberOfBufferedCalls()` phản ánh số kết quả được giữ trong cửa sổ thống kê. `getNumberOfNotPermittedCalls()` là số lời gọi bị từ chối; những lời gọi bị từ chối không phải là mẫu thành công hay thất bại của sliding window. Các lời gọi bị ignore cũng không đóng góp vào success/failure rate.

Khi chưa đủ `minimumNumberOfCalls`, failure rate hoặc slow call rate có thể trả về `-1.0`, biểu thị chưa đủ mẫu để tính tỷ lệ. Không hiển thị giá trị này như `-1%` lỗi; dashboard nên biểu diễn là “chưa đủ mẫu”. Khi đã đủ mẫu, các tỷ lệ được biểu diễn theo phần trăm từ 0 đến 100.

Các getter được đọc liên tiếp, nên snapshot trong log là ảnh chụp gần cùng một thời điểm chứ không phải giao dịch nguyên tử. Trong môi trường có nhiều request đồng thời, số liệu có thể thay đổi giữa hai lần đọc. Nếu cần một chuỗi quan sát theo thời gian, hãy lưu mẫu định kỳ hoặc dùng Micrometer metrics thay vì cố dùng snapshot đơn lẻ để tái dựng toàn bộ lịch sử.

## Tạo một DTO snapshot để trả cho trang quản trị

Không nên trả thẳng object Resilience4j ra REST API. Hãy chuyển các giá trị cần thiết thành DTO ổn định, để API không phụ thuộc cấu trúc nội bộ của thư viện:

```java
public record CircuitBreakerSnapshot(
    String name,
    String state,
    int bufferedCalls,
    int successfulCalls,
    int failedCalls,
    int notPermittedCalls,
    int slowCalls,
    float failureRate,
    float slowCallRate
) {}
```

```java
CircuitBreakerSnapshot snapshot(String name) {
    CircuitBreaker circuitBreaker = findExisting(name);
    if (circuitBreaker == null) {
        throw new IllegalArgumentException(
            "Không tìm thấy Circuit Breaker: " + name);
    }

    CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();
    return new CircuitBreakerSnapshot(
        circuitBreaker.getName(),
        circuitBreaker.getState().name(),
        metrics.getNumberOfBufferedCalls(),
        metrics.getNumberOfSuccessfulCalls(),
        metrics.getNumberOfFailedCalls(),
        metrics.getNumberOfNotPermittedCalls(),
        metrics.getNumberOfSlowCalls(),
        metrics.getFailureRate(),
        metrics.getSlowCallRate());
}
```

Endpoint quản trị chỉ nên cung cấp quyền đọc cho người vận hành được phép. Không cho client bên ngoài truy cập registry trực tiếp hoặc tự do truyền tên để tạo instance mới. Có thể liệt kê các tên đang tồn tại bằng `getAllCircuitBreakers()` và chỉ trả các trường đã được chọn trong DTO.

## Theo dõi thay đổi registry và trạng thái bằng event

Snapshot cho biết trạng thái tại thời điểm đọc; event giúp biết điều gì đã xảy ra giữa hai lần đọc. Registry event publisher phát thông báo khi instance được thêm, xóa hoặc thay thế:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerRegistryEvents {

    @Bean
    ApplicationRunner registerRegistryEvents(CircuitBreakerRegistry registry) {
        return args -> registry.getEventPublisher()
            .onEntryAdded(event -> log.info(
                "Registry thêm Circuit Breaker {}",
                event.getAddedEntry().getName()))
            .onEntryRemoved(event -> log.info(
                "Registry xóa Circuit Breaker {}",
                event.getRemovedEntry().getName()))
            .onEntryReplaced(event -> log.info(
                "Registry thay Circuit Breaker {}",
                event.getNewEntry().getName()));
    }
}
```

Ở cấp một Circuit Breaker, event publisher có thể theo dõi chuyển trạng thái, kết quả lời gọi và lời gọi bị từ chối:

```java
void registerCircuitBreakerEvents(CircuitBreaker circuitBreaker) {
    circuitBreaker.getEventPublisher()
        .onStateTransition(event -> log.info(
            "{} chuyển trạng thái: {}",
            event.getCircuitBreakerName(),
            event.getStateTransition()))
        .onSuccess(event -> log.debug(
            "{} ghi nhận lời gọi thành công",
            event.getCircuitBreakerName()))
        .onError(event -> log.warn(
            "{} ghi nhận lỗi: {}",
            event.getCircuitBreakerName(),
            event.getThrowable().toString()))
        .onCallNotPermitted(event -> log.debug(
            "{} từ chối lời gọi",
            event.getCircuitBreakerName()));
}
```

Đăng ký listener một lần khi instance được tạo hoặc khi registry báo `onEntryAdded`; không đăng ký lại listener ở mỗi request. Callback nên ngắn và không chặn thread thực thi. Nếu cần gửi event đến hệ thống khác, hãy chuyển sang hàng đợi hoặc cơ chế xử lý bất đồng bộ phù hợp. Không log toàn bộ payload hay thông tin xác thực trong exception.

## Quan sát bằng Actuator và Micrometer

Trong production, dashboard nên dùng metric để theo dõi xu hướng và dùng endpoint health để kiểm tra trạng thái tổng quát. Với Spring Boot Actuator, có thể expose các endpoint cần thiết:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

Resilience4j Micrometer integration xuất metrics cho số lời gọi theo loại kết quả, trạng thái Circuit Breaker và các tỷ lệ liên quan. Tên metric và tag cụ thể có thể thay đổi theo phiên bản, vì vậy hãy khám phá danh sách metric thực tế qua `/actuator/metrics` hoặc scrape endpoint Prometheus thay vì hard-code tên dựa trên một phiên bản khác.

Các metric cần quan sát gồm:

- Số lời gọi thành công, thất bại và bị từ chối.
- Trạng thái Circuit Breaker hiện tại.
- Failure rate và slow call rate.
- Số lời gọi đang được buffer trong sliding window.
- Số lần chuyển trạng thái và tần suất mạch dao động giữa `CLOSED` và `OPEN`.

Health indicator của Circuit Breaker có thể coi trạng thái `OPEN` là `DOWN`, tùy cấu hình và phiên bản tích hợp. Nếu đưa trạng thái này vào readiness/liveness của Kubernetes một cách thiếu cân nhắc, một dependency lỗi có thể khiến toàn bộ instance ứng dụng bị đánh dấu không sẵn sàng và tạo thêm hiệu ứng dây chuyền. Hãy quyết định riêng liệu Circuit Breaker `OPEN` có nên làm ứng dụng mất readiness hay chỉ là tín hiệu vận hành của một dependency.

## Ví dụ đọc và diễn giải snapshot

Giả sử dashboard hiển thị:

| Chỉ số | Giá trị |
|---|---:|
| State | `OPEN` |
| Buffered calls | 20 |
| Successful calls | 8 |
| Failed calls | 12 |
| Not permitted calls | 37 |
| Slow calls | 10 |
| Failure rate | 60% |
| Slow call rate | 50% |

Trong ví dụ, sliding window đang giữ 20 mẫu và có 12 mẫu lỗi, nên failure rate là 60%. Có 37 lời gọi bị từ chối sau khi mạch mở; chúng không làm tăng số mẫu trong cửa sổ. 10 lời gọi chậm là một chỉ số riêng; một lời gọi chậm cũng có thể đồng thời là lời gọi thất bại tùy kết quả và chính sách phân loại. Vì vậy, không cộng `slow calls` vào `failed calls` để suy ra tổng số lời gọi.

Nếu cấu hình `failureRateThreshold: 50`, tỷ lệ 60% giải thích vì sao mạch có thể chuyển sang `OPEN`, miễn là số mẫu tối thiểu đã đạt. Khi mạch đang `OPEN`, việc dashboard tiếp tục thấy `notPermitted` tăng là bình thường: request mới đang bị chặn nhanh. Sau `waitDurationInOpenState`, mạch có thể chuyển sang `HALF_OPEN` và cho phép số probe giới hạn. Snapshot tiếp theo cần được đọc cùng event chuyển trạng thái để hiểu chuỗi diễn biến.

## Những nhầm lẫn thường gặp

- **Đọc nhầm registry:** inject một registry mới hoặc registry không được factory sử dụng, dẫn đến không thấy instance thực tế.
- **Vô tình tạo instance khi chỉ muốn đọc:** gọi `registry.circuitBreaker(name)` cho một tên chưa tồn tại có thể tạo mạch mới với cấu hình mặc định.
- **Nhầm named config với instance config:** `getConfiguration(name)` truy vấn cấu hình đã đăng ký dưới tên đó; không đảm bảo tên trùng với instance là cấu hình hiệu lực của instance.
- **Coi trạng thái là lịch sử:** `getState()` chỉ trả trạng thái hiện tại; dùng event hoặc metric theo thời gian để xem diễn biến.
- **Coi lời gọi bị từ chối là failure trong cửa sổ:** `not permitted` là số liệu riêng, không phải mẫu thành công/thất bại của sliding window.
- **Hiểu `-1` là tỷ lệ âm:** failure/slow rate có thể là `-1` khi chưa đủ mẫu tối thiểu.
- **Đọc snapshot như dữ liệu nguyên tử:** các getter được đọc liên tiếp trong lúc hệ thống có thể tiếp tục xử lý request.
- **Dùng health status thay cho dashboard:** `OPEN` có thể ảnh hưởng health indicator; hãy cân nhắc tác động đến readiness và điều phối instance.

Khi điều tra một Circuit Breaker, hãy xác định đúng registry và tên instance trước, xem cấu hình mặc định cùng shared config, xác nhận nguồn cấu hình instance-specific, rồi đọc state và metrics. Kết hợp snapshot với event và metric theo thời gian sẽ cho biết mạch đang ở trạng thái nào, vì sao nó chuyển trạng thái và liệu dependency đã phục hồi đủ để nhận probe hay chưa.
