# Lắng nghe chuyển trạng thái và tránh đăng ký listener lặp

Circuit breaker không chỉ cung cấp kết quả cho từng lời gọi. Nó còn phát ra sự kiện khi có lời gọi thành công, thất bại, bị từ chối hoặc khi trạng thái chuyển từ `CLOSED` sang `OPEN`, `HALF_OPEN` và ngược lại. Lắng nghe các sự kiện này giúp nhóm phát triển biết khi nào một phụ thuộc bắt đầu suy giảm, khi nào circuit breaker chặn request và khi nào dịch vụ có dấu hiệu phục hồi.

Với Spring Cloud CircuitBreaker sử dụng Resilience4j, có thể đăng ký listener trên event publisher của từng `CircuitBreaker`. Khi dùng `CircuitBreakerRegistry` trực tiếp, có thể lắng nghe sự kiện thêm instance vào registry rồi gắn listener cho instance mới. Điều quan trọng là đăng ký listener theo vòng đời của circuit breaker, thường tại cấu hình hoặc lúc registry tạo entry, thay vì đăng ký lại mỗi lần xử lý request. Nếu cùng một listener được gắn lặp nhiều lần, một lần chuyển trạng thái có thể tạo nhiều log, nhiều thông báo hoặc nhiều tác vụ phụ.

## 1. Các sự kiện của CircuitBreaker

Resilience4j phát ra các sự kiện mô tả hoạt động của circuit breaker. Những loại thường hữu ích khi vận hành gồm:

| Sự kiện | Ý nghĩa | Giá trị vận hành |
|---|---|---|
| `onSuccess` | Một lời gọi được bảo vệ kết thúc thành công. | Theo dõi số lần gọi thành công và độ trễ. |
| `onError` | Một lời gọi kết thúc bằng lỗi được ghi nhận. | Điều tra exception từ supplier và lỗi của phụ thuộc. |
| `onIgnoredError` | Supplier phát sinh exception được cấu hình bỏ qua. | Phân biệt lỗi nghiệp vụ không ảnh hưởng failure rate. |
| `onCallNotPermitted` | Circuit breaker từ chối lời gọi trước khi supplier chạy. | Biết có request bị chặn khi mạch mở hoặc hết quyền thăm dò. |
| `onStateTransition` | Trạng thái circuit breaker thay đổi. | Theo dõi thời điểm mạch mở, bắt đầu thăm dò hoặc đóng lại. |
| `onFailureRateExceeded` | Tỷ lệ lỗi vượt ngưỡng cấu hình. | Điều tra nguyên nhân khiến mạch chuyển sang `OPEN`. |
| `onSlowCallRateExceeded` | Tỷ lệ lời gọi chậm vượt ngưỡng. | Phát hiện phụ thuộc phản hồi chậm dù chưa có nhiều exception. |
| `onReset` | Circuit breaker được reset. | Nhận biết thao tác reset trong vận hành hoặc kiểm thử. |

Sự kiện `onStateTransition` đặc biệt hữu ích vì nó mô tả thay đổi trạng thái thực tế. Ví dụ, `CLOSED_TO_OPEN` cho biết circuit breaker đã ngắt lời gọi; `OPEN_TO_HALF_OPEN` cho biết mạch bắt đầu giai đoạn thăm dò; `HALF_OPEN_TO_CLOSED` cho biết các lời gọi thăm dò đạt yêu cầu theo cấu hình.

Một số phiên bản Resilience4j còn có các trạng thái đặc biệt như `METRICS_ONLY`, `DISABLED` hoặc `FORCED_OPEN`. Khi xây dựng dashboard và cảnh báo, cần tính đến các trạng thái này thay vì giả định circuit breaker chỉ có ba trạng thái thông thường.

## 2. Đăng ký listener bằng Spring Cloud CircuitBreaker Customizer

Khi dùng starter Resilience4j của Spring Cloud CircuitBreaker, có thể sử dụng `Customizer<Resilience4JCircuitBreakerFactory>` để gắn listener vào circuit breaker theo ID. Factory gọi customizer khi tạo instance tương ứng; listener được đăng ký trên event publisher của instance đó.

Ví dụ chỉ lắng nghe chuyển trạng thái của circuit breaker `inventory`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CircuitBreakerEventConfiguration {
    private static final Logger log =
        LoggerFactory.getLogger(CircuitBreakerEventConfiguration.class);

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryStateListener() {
        return factory -> factory.addCircuitBreakerCustomizer(
            circuitBreaker -> circuitBreaker.getEventPublisher()
                .onStateTransition(event -> log.warn(
                    "Circuit breaker {} chuyển trạng thái: {}",
                    event.getCircuitBreakerName(),
                    event.getStateTransition()
                )),
            "inventory"
        );
    }
}
```

Trong ví dụ, listener chỉ gắn cho circuit breaker có ID `inventory`. Khi trạng thái thay đổi, log chứa tên circuit breaker và chuyển trạng thái. Có thể áp dụng cùng cách cho một danh sách ID hoặc tạo customizer riêng theo từng nhóm phụ thuộc.

Nếu ứng dụng tạo circuit breaker với ID khác, chẳng hạn `payment` hoặc `shipping`, customizer gắn cho `inventory` không tự động áp dụng cho các ID đó. Hãy dùng đúng định danh được truyền vào `CircuitBreakerFactory.create(...)` và thống nhất với cấu hình Resilience4j.

## 3. Lắng nghe nhiều loại sự kiện trên cùng một instance

Một listener có thể đăng ký nhiều event consumer trên cùng event publisher. Ví dụ:

```java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> inventoryEventListeners() {
    return factory -> factory.addCircuitBreakerCustomizer(
        circuitBreaker -> circuitBreaker.getEventPublisher()
            .onStateTransition(event -> log.warn(
                "{} state transition: {}",
                event.getCircuitBreakerName(),
                event.getStateTransition()
            ))
            .onCallNotPermitted(event -> log.info(
                "{} từ chối lời gọi vì circuit breaker không cấp quyền",
                event.getCircuitBreakerName()
            ))
            .onError(event -> log.debug(
                "{} ghi nhận lỗi lời gọi: {}",
                event.getCircuitBreakerName(),
                event.getThrowable().toString()
            )),
        "inventory"
    );
}
```

Đoạn mã minh họa cách kết hợp listener cho chuyển trạng thái, rejection và lỗi thực thi. Khi triển khai, chỉ bật mức log cần thiết. Không ghi toàn bộ request body, token, thông tin cá nhân hoặc dữ liệu nhạy cảm vào event log.

Lưu ý rằng `onError` và `onCallNotPermitted` mô tả hai tình huống khác nhau. `onError` phản ánh một lần thực thi đã bắt đầu và kết thúc bằng lỗi được ghi nhận; `onCallNotPermitted` phản ánh circuit breaker đã từ chối trước khi supplier chạy. Nếu gộp hai sự kiện thành một loại “downstream error”, dashboard có thể khiến nhóm vận hành hiểu nhầm rằng dịch vụ đích vừa nhận thêm request và thất bại.

## 4. Lắng nghe entry được thêm vào CircuitBreakerRegistry

Khi ứng dụng sử dụng Resilience4j `CircuitBreakerRegistry` trực tiếp, registry có event publisher riêng. Có thể lắng nghe khi một circuit breaker mới được thêm rồi gắn listener cho instance đó:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class Resilience4jRegistryConfiguration {

    @Bean
    CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

        registry.getEventPublisher().onEntryAdded(event -> {
            CircuitBreaker circuitBreaker = event.getAddedEntry();
            circuitBreaker.getEventPublisher().onStateTransition(stateEvent ->
                System.out.printf(
                    "Circuit breaker %s chuyển trạng thái: %s%n",
                    stateEvent.getCircuitBreakerName(),
                    stateEvent.getStateTransition()
                )
            );
        });

        return registry;
    }
}
```

Registry listener được đăng ký một lần khi bean registry được tạo. Mỗi khi registry thêm một entry mới, callback nhận instance vừa được thêm và gắn listener chuyển trạng thái cho instance đó. Các circuit breaker đã tồn tại trước khi đăng ký `onEntryAdded` không phát lại sự kiện thêm; nếu registry được khởi tạo trước đó, cần gắn listener cho các entry hiện có bằng API truy vấn registry phù hợp.

Ví dụ trên minh họa cách làm việc với registry trực tiếp. Trong ứng dụng Spring Cloud CircuitBreaker, factory có thể quản lý việc tạo và cache circuit breaker riêng. Không tạo một registry độc lập rồi giả định các breaker do factory tạo tự động xuất hiện trong registry đó. Hãy chọn đúng cơ chế quản lý instance mà ứng dụng thực sự sử dụng.

## 5. Vì sao listener bị đăng ký lặp?

Lỗi thường gặp là gọi `getEventPublisher().onStateTransition(...)` bên trong phương thức nghiệp vụ hoặc mỗi lần xử lý request. Ví dụ không nên làm:

```java
public Stock getStock(String sku) {
    var circuitBreaker = circuitBreakerFactory.create("inventory");

    circuitBreaker.getEventPublisher().onStateTransition(event ->
        log.warn("Inventory state: {}", event.getStateTransition())
    );

    return circuitBreaker.run(
        () -> inventoryClient.getStock(sku),
        error -> Stock.unavailable(sku)
    );
}
```

Mỗi lần gọi `getStock` lại thêm một event consumer. Nếu một instance circuit breaker tồn tại lâu dài và được tái sử dụng, các listener cũ vẫn có thể nhận sự kiện. Sau 100 request, một lần chuyển trạng thái có thể tạo 100 dòng log giống nhau. Nếu listener còn gửi alert hoặc ghi dữ liệu, một sự kiện có thể kích hoạt nhiều tác vụ trùng.

Các nguyên nhân phổ biến:

- Đăng ký listener bên trong controller, service method hoặc request filter.
- Tạo bean cấu hình nhiều lần do nhiều application context hoặc cấu hình bị import lặp.
- Gắn listener ở cả registry event consumer và factory customizer cho cùng một circuit breaker mà không chủ đích.
- Một component tự đăng ký listener khi được khởi tạo lại nhưng không kiểm soát vòng đời.
- Đăng ký listener trong vòng lặp mỗi lần lấy instance từ registry.

## 6. Đặt listener ở đúng vòng đời

Đối với Spring Cloud CircuitBreaker, lựa chọn phù hợp thường là bean `Customizer` được Spring quản lý. Đối với Resilience4j registry trực tiếp, lựa chọn phù hợp thường là một registry event consumer đăng ký lúc tạo registry hoặc listener được gắn ngay khi tạo instance.

| Vị trí đăng ký | Khi nào phù hợp | Cần tránh |
|---|---|---|
| Bean `Customizer<Resilience4JCircuitBreakerFactory>` | Ứng dụng dùng Spring Cloud CircuitBreaker factory. | Khai báo nhiều customizer cùng gắn một listener vào cùng ID. |
| `CircuitBreakerRegistry` event publisher | Ứng dụng quản lý Resilience4j instance trực tiếp. | Tạo registry riêng không chứa instance đang được ứng dụng sử dụng. |
| Hàm tạo instance hoặc component quản lý registry | Ứng dụng tự kiểm soát vòng đời circuit breaker. | Đăng ký lại mỗi lần gọi nghiệp vụ. |
| Controller/service request method | Không phù hợp để đăng ký listener. | Gắn consumer trong đường xử lý request. |

Một bean cấu hình Spring thông thường có scope singleton. Đặt việc đăng ký listener trong bean cấu hình giúp listener được thiết lập theo vòng đời ứng dụng thay vì vòng đời request. Nếu ứng dụng có nhiều application context, cần hiểu context nào tạo factory và tránh nạp cùng cấu hình nhiều lần vào cùng một factory.

## 7. Bảo đảm đăng ký idempotent khi tạo instance động

Với hệ thống tạo circuit breaker động theo tenant, endpoint hoặc dịch vụ mới, có thể cần cơ chế bảo vệ để cùng một instance không bị gắn listener lặp. Một registry quản lý listener có thể lưu các ID đã được đăng ký:

```java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class CircuitBreakerListenerRegistrar {
    private final Set<String> registeredIds = ConcurrentHashMap.newKeySet();

    public void registerOnce(
            String id,
            io.github.resilience4j.circuitbreaker.CircuitBreaker circuitBreaker) {
        if (!registeredIds.add(id)) {
            return;
        }

        circuitBreaker.getEventPublisher().onStateTransition(event ->
            logStateTransition(id, event.getStateTransition().toString())
        );
    }

    private void logStateTransition(String id, String transition) {
        // Chuyển tiếp tới logger hoặc event sink đã cấu hình.
    }
}
```

`ConcurrentHashMap.newKeySet()` giúp thao tác thêm ID an toàn khi nhiều thread cùng yêu cầu đăng ký. Chỉ thread thêm ID thành công mới gắn listener. Ví dụ này phù hợp khi vòng đời ID không thay đổi và một circuit breaker chỉ có một listener theo chính sách.

Nếu registry cho phép thay thế hoặc xóa rồi tạo lại entry cùng ID, chỉ lưu ID là chưa đủ. Khi đó, cần xác định danh tính instance hoặc vòng đời entry, xử lý `onEntryRemoved`/`onEntryAdded` tương ứng và loại bỏ trạng thái đăng ký cũ khi instance bị thay thế. Không nên giữ một tập ID không giới hạn nếu hệ thống tạo hàng triệu ID động; cần chính sách thu hồi hoặc giới hạn vòng đời.

Với ứng dụng thông thường có số circuit breaker cố định, không cần tự xây registrar. Một customizer tập trung và được tạo một lần thường đơn giản hơn.

## 8. Listener không nên làm chậm lời gọi được bảo vệ

Event consumer thường được gọi trong luồng phát sự kiện của Resilience4j. Vì vậy, listener nên ngắn, không chặn và không gọi lại chính dịch vụ phụ thuộc đang được bảo vệ. Một listener thực hiện HTTP request, truy vấn cơ sở dữ liệu hoặc chờ một queue đồng bộ có thể làm tăng độ trễ của request hoặc làm thay đổi hành vi mà circuit breaker đang đo.

Các nguyên tắc thực hành:

- Chỉ trích xuất các trường cần thiết từ event và ghi log ngắn gọn.
- Không gọi lại dependency đang có sự cố từ listener.
- Không thực hiện thao tác I/O chậm hoặc chờ lock dài trong callback.
- Nếu cần gửi thông báo ra hệ thống khác, đẩy một event nhỏ vào queue có giới hạn hoặc dùng cơ chế metrics/monitoring phù hợp.
- Có xử lý lỗi cho event sink để lỗi ghi log hoặc gửi alert không làm hỏng đường xử lý chính.
- Không tạo metric tag từ dữ liệu có cardinality cao như request ID, user ID hoặc URL chứa tham số động.

Sự kiện chuyển trạng thái không phải nơi phù hợp để xử lý fallback cho request. Fallback thuộc đường thực thi của lời gọi; listener chỉ nên phục vụ quan sát và phản ứng vận hành không chặn.

## 9. Dùng sự kiện để quan sát trạng thái và không thay thế metrics

Event listener phù hợp cho log, audit và thông báo chuyển trạng thái. Metrics phù hợp để tổng hợp theo thời gian, tạo dashboard và cảnh báo dựa trên tỷ lệ. Không nên dùng event listener làm cơ chế duy nhất để tính số lần thành công hoặc failure rate vì Resilience4j và Micrometer đã có các metrics dành cho mục đích đó.

Một cách phân vai:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Ghi nhận thời điểm `CLOSED` chuyển `OPEN` | `onStateTransition` và log có cấu trúc. |
| Đếm số lần lời gọi thành công/thất bại | Resilience4j Micrometer metrics. |
| Theo dõi số lời gọi bị từ chối | Metric not-permitted và/hoặc event `onCallNotPermitted`. |
| Cảnh báo mạch mở lâu | Metrics trạng thái, thời gian và alert rule. |
| Điều tra một request cụ thể | Distributed trace và log có correlation ID. |
| Thông báo cho đội vận hành khi có thay đổi trạng thái | Event listener gửi thông điệp bất đồng bộ qua event sink có giới hạn. |

Khi một circuit breaker liên tục chuyển `OPEN` rồi `HALF_OPEN` rồi `OPEN`, log state transition giúp xác định thời điểm dao động. Metrics về failure rate, slow call rate và số lời gọi thăm dò giúp tìm nguyên nhân. Kết hợp cả hai sẽ hữu ích hơn việc tạo một alert cho mọi exception.

## 10. Tránh thông báo trùng khi ứng dụng chạy nhiều replica

Listener được đăng ký một lần trong mỗi process, nhưng hệ thống production thường có nhiều replica. Nếu có 5 replica và mỗi replica có circuit breaker instance riêng, cùng một phụ thuộc suy giảm có thể khiến cả 5 instance phát ra sự kiện `CLOSED_TO_OPEN`. Đây không phải đăng ký listener lặp trong một process; đó là năm circuit breaker cục bộ cùng quan sát một dependency.

Hãy phân biệt:

- **Duplicate listener trong một process:** một circuit breaker phát một sự kiện nhưng nhiều callback giống nhau chạy do đăng ký lặp.
- **Sự kiện từ nhiều replica:** mỗi process có circuit breaker và listener riêng, nên cùng một thay đổi có thể tạo nhiều log/event.

Không nên loại bỏ sự kiện hợp lệ từ các replica chỉ vì nội dung giống nhau. Nếu hệ thống cần một cảnh báo tổng hợp, có thể gom theo service, circuit breaker ID và trạng thái trong alerting system; dùng deduplication key và khoảng thời gian hợp lý ở tầng thông báo. Log vẫn nên giữ thông tin instance/replica để điều tra phân bố lỗi.

Circuit breaker của Resilience4j thường giữ trạng thái cục bộ trong từng process. Listener cục bộ không tạo ra một trạng thái breaker dùng chung toàn cụm. Nếu cần điều phối trạng thái toàn hệ thống, đó là một thiết kế riêng với yêu cầu nhất quán và độ sẵn sàng khác.

## 11. Kiểm thử listener chỉ được đăng ký một lần

Nên kiểm thử cả hai điều kiện: listener nhận được sự kiện khi trạng thái thay đổi và một lần chuyển trạng thái chỉ tạo đúng một lần xử lý ở listener.

Với Resilience4j, có thể tạo một circuit breaker kiểm thử, đăng ký listener một lần, rồi đưa instance vào trạng thái mở bằng cấu hình và kết quả lời gọi phù hợp. Một cách đơn giản hơn trong unit test là dùng `AtomicInteger` đếm số callback:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.junit.jupiter.api.Test;

class CircuitBreakerEventListenerTest {

    @Test
    void invokesOneListenerForOneStateTransition() {
        CircuitBreaker circuitBreaker = CircuitBreaker.ofDefaults("inventory");
        AtomicInteger transitionCount = new AtomicInteger();

        circuitBreaker.getEventPublisher().onStateTransition(event ->
            transitionCount.incrementAndGet()
        );

        circuitBreaker.transitionToOpenState();

        assertEquals(1, transitionCount.get());
    }
}
```

Test trên minh họa một listener được đăng ký một lần và đếm một sự kiện chuyển trạng thái. Khi kiểm thử hành vi tích hợp thực tế, nên kiểm tra thêm rằng bean `Customizer` chỉ được nạp một lần trong application context và nhiều request không làm tăng số callback đã đăng ký.

Các ca kiểm thử hữu ích:

1. Chuyển `CLOSED` sang `OPEN`: listener nhận một event với đúng breaker ID.
2. Chuyển `OPEN` sang `HALF_OPEN`: listener nhận event tiếp theo.
3. Gửi nhiều request trong cùng trạng thái: không phát sinh thêm state transition và không nhân số callback.
4. Tạo nhiều breaker ID: listener chỉ được gắn cho các ID đã cấu hình.
5. Khởi tạo registry có entry mới: registry listener gắn consumer cho entry mới đúng một lần.
6. Chạy nhiều replica: phân biệt event từ các instance khác nhau với callback bị đăng ký trùng trong một process.

## 12. Xử lý lỗi và thay đổi vòng đời listener

Event publisher giữ các consumer đã đăng ký trên instance. Vì vậy, listener nên có vòng đời tương ứng với circuit breaker. Nếu một instance bị xóa hoặc thay thế, hãy kiểm tra API của phiên bản Resilience4j để xử lý listener và tham chiếu liên quan. Tránh để registrar giữ tham chiếu đến instance đã bị loại bỏ vô thời hạn.

Nếu listener gửi thông điệp sang hệ thống khác, hãy xử lý trường hợp hệ thống nhận thông báo không khả dụng. Có thể dùng queue giới hạn, retry riêng cho event sink hoặc chấp nhận mất một số thông báo không quan trọng. Không để lỗi thông báo làm thay đổi kết quả của lời gọi nghiệp vụ hoặc làm cạn tài nguyên của thread phát sự kiện.

Đối với cảnh báo quan trọng, không chỉ dựa vào một event callback trong bộ nhớ. Kết hợp metrics được scrape định kỳ và alert rule để trạng thái có thể được phát hiện lại sau khi process khởi động lại hoặc event sink tạm thời lỗi. Event listener bổ sung thông tin thời điểm và ngữ cảnh; metrics cung cấp bức tranh tổng hợp bền vững hơn.

## 13. Quy trình triển khai trong ứng dụng Spring

Có thể triển khai theo trình tự sau:

1. Xác định circuit breaker ID cần theo dõi, ví dụ `inventory` và `payment`.
2. Nếu dùng Spring Cloud CircuitBreaker, tạo một bean `Customizer<Resilience4JCircuitBreakerFactory>` để gắn listener theo ID.
3. Nếu dùng Resilience4j registry trực tiếp, đăng ký registry event consumer một lần khi tạo registry và gắn listener cho entry mới.
4. Chỉ lắng nghe các event thực sự cần thiết; ưu tiên state transition cho thông báo trạng thái và metrics cho số liệu định lượng.
5. Đảm bảo callback ngắn, không chặn và không gọi lại dependency đang suy giảm.
6. Kiểm thử số lần callback, ID, state transition và hành vi khi có nhiều request.
7. Khi chạy nhiều replica, gắn nhãn instance vào log/trace và xử lý deduplication ở hệ thống alert nếu cần.

## 14. Checklist tránh listener lặp

- [ ] Listener được đăng ký trong cấu hình hoặc lúc tạo registry, không nằm trong request method.
- [ ] Mỗi circuit breaker ID chỉ có listener cần thiết theo thiết kế.
- [ ] Không đồng thời gắn cùng listener từ factory customizer và registry event consumer cho một instance.
- [ ] Bean cấu hình không bị import hoặc tạo nhiều lần ngoài dự kiến.
- [ ] Nếu tạo ID động, có cơ chế kiểm soát đăng ký và vòng đời instance.
- [ ] Listener không chặn, không gọi lại dependency và không làm I/O chậm.
- [ ] Event log phân biệt lỗi thực thi với lời gọi bị từ chối.
- [ ] Metrics vẫn được dùng cho dashboard và alert định lượng.
- [ ] Log có thông tin breaker ID và replica nhưng không chứa dữ liệu nhạy cảm.
- [ ] Kiểm thử chứng minh một lần chuyển trạng thái chỉ kích hoạt đúng số callback mong muốn.

Lắng nghe sự kiện chuyển trạng thái giúp ứng dụng Spring Cloud CircuitBreaker giải thích được khi nào mạch mở, bắt đầu thăm dò và phục hồi. Hãy gắn listener theo vòng đời của factory hoặc registry, chỉ đăng ký một lần cho mỗi instance, giữ callback ngắn và dùng metrics cho số liệu tổng hợp. Khi phân biệt được lỗi thực thi, lời gọi bị từ chối và sự kiện từ nhiều replica, nhóm vận hành có thể theo dõi circuit breaker chính xác mà không tạo thêm log hoặc tác vụ trùng lặp.
