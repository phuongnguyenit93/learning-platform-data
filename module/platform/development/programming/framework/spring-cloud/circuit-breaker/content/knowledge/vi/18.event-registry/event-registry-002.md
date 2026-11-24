# Lấy lại cùng instance so với tạo registry độc lập

Trong Resilience4j, **registry** quản lý các instance Circuit Breaker theo tên. Khi lấy một Circuit Breaker bằng cùng tên từ cùng một registry, ứng dụng nhận lại instance đã được quản lý, vì vậy trạng thái CLOSED, OPEN hoặc HALF_OPEN, sliding window, metrics và event listener đều thuộc cùng một đối tượng. Nếu tạo một registry độc lập rồi lấy lại cùng tên, ứng dụng nhận một Circuit Breaker khác với trạng thái và lịch sử riêng.

Sự khác biệt này quan trọng khi triển khai Circuit Breaker trong Spring Cloud. Nếu mỗi request lại tạo registry mới, ứng dụng vô tình chia nhỏ lịch sử lỗi thành nhiều instance, khiến ngưỡng failure rate khó đạt và trạng thái OPEN không được chia sẻ giữa các request. Thông thường, registry cần được quản lý dùng chung trong vòng đời ứng dụng; các thành phần gọi dịch vụ lấy instance theo tên từ registry đó.

## 1. Registry và Circuit Breaker instance

`CircuitBreakerRegistry` là nơi lưu trữ và tra cứu các Circuit Breaker. Mỗi Circuit Breaker có một tên, cấu hình và trạng thái riêng. Registry cho phép lấy một instance theo tên, liệt kê các instance đang quản lý và áp dụng cấu hình mặc định hoặc cấu hình được chỉ định.

Ba khái niệm cần phân biệt:

| Thành phần | Vai trò |
| --- | --- |
| Registry | Quản lý tập hợp Circuit Breaker và định danh của chúng |
| Circuit Breaker instance | Theo dõi trạng thái, sliding window, kết quả lời gọi và phát sự kiện |
| Tên instance | Khóa dùng để lấy lại Circuit Breaker tương ứng trong một registry |

Ví dụ, dịch vụ Đơn hàng gọi dịch vụ Kho. Ứng dụng lấy instance tên `inventory` từ registry và dùng instance đó để bọc các lời gọi đến Kho. Những request khác cũng cần lấy cùng instance `inventory` từ registry dùng chung để chia sẻ lịch sử lỗi và trạng thái mạch.

Một registry có thể quản lý nhiều instance:

~~~mermaid
flowchart TD
    A[CircuitBreakerRegistry dùng chung] --> B[Instance inventory]
    A --> C[Instance payment]
    A --> D[Instance customer-profile]
    B --> E[Sliding window và state của inventory]
    C --> F[Sliding window và state của payment]
    D --> G[Sliding window và state của customer-profile]
~~~

Các instance trong cùng registry có tên và trạng thái riêng. Việc dùng chung registry không có nghĩa mọi dịch vụ dùng chung một Circuit Breaker; mỗi tên vẫn đại diện cho một đối tượng độc lập.

## 2. Lấy lại cùng instance bằng cùng tên

Khi gọi `registry.circuitBreaker("inventory")` nhiều lần trên cùng một registry, Resilience4j trả về instance đã được đăng ký với tên đó nếu instance đã tồn tại. Nếu chưa có, registry tạo instance mới rồi quản lý nó.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import java.time.Duration;

public class InventoryCircuitBreakers {
    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakers() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        this.registry = CircuitBreakerRegistry.of(config);
    }

    public CircuitBreaker firstLookup() {
        return registry.circuitBreaker("inventory");
    }

    public CircuitBreaker secondLookup() {
        return registry.circuitBreaker("inventory");
    }
}
~~~

Hai phương thức trên tra cứu cùng một registry và cùng tên. Nếu gọi:

~~~java
CircuitBreaker first = inventoryCircuitBreakers.firstLookup();
CircuitBreaker second = inventoryCircuitBreakers.secondLookup();

boolean sameInstance = first == second; // true
~~~

`sameInstance` là `true` vì cả hai biến tham chiếu đến cùng một đối tượng. Do đó:

- Lời gọi qua `first` và `second` cập nhật cùng sliding window.
- Nếu một lời gọi làm instance chuyển sang OPEN, lần tra cứu tiếp theo vẫn thấy trạng thái OPEN.
- Event listener đăng ký trên instance đó nhận sự kiện từ các lời gọi đi qua cùng instance.
- Metrics của instance phản ánh tổng hợp hoạt động được ghi nhận bởi instance đó.

Đây là hành vi cần có khi nhiều request cùng bảo vệ một phụ thuộc. Circuit Breaker phải tích lũy đủ mẫu từ các request khác nhau để đánh giá failure rate và slow call rate.

## 3. Cùng tên nhưng khác registry là instance độc lập

Tên instance chỉ có ý nghĩa bên trong registry đang quản lý nó. Hai registry khác nhau có thể cùng chứa tên `inventory`, nhưng mỗi registry tạo và quản lý một Circuit Breaker riêng:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(10))
        .build();

CircuitBreakerRegistry registryA =
        CircuitBreakerRegistry.of(config);
CircuitBreakerRegistry registryB =
        CircuitBreakerRegistry.of(config);

CircuitBreaker inventoryA = registryA.circuitBreaker("inventory");
CircuitBreaker inventoryB = registryB.circuitBreaker("inventory");

boolean sameInstance = inventoryA == inventoryB; // false
~~~

`inventoryA` và `inventoryB` không chia sẻ trạng thái, sliding window hoặc event listener. Nếu `inventoryA` chuyển sang OPEN, `inventoryB` vẫn có thể ở CLOSED vì nó chưa ghi nhận những lời gọi làm instance A mở mạch.

Sơ đồ so sánh:

~~~mermaid
flowchart TD
    A[Registry A] --> B[Instance inventory A]
    C[Registry B] --> D[Instance inventory B]
    B --> E[State và sliding window A]
    D --> F[State và sliding window B]
    E -. Không chia sẻ .- F
~~~

Việc tạo registry độc lập phù hợp khi thực sự cần miền trạng thái tách biệt, chẳng hạn hai ứng dụng hoặc hai nhóm xử lý có vòng đời và chính sách riêng. Trong một ứng dụng phục vụ cùng phụ thuộc, tạo nhiều registry chỉ để lấy cùng tên thường là sai thiết kế vì mỗi registry sẽ tích lũy dữ liệu riêng.

## 4. Tạo registry mới theo từng request gây ra điều gì?

Ví dụ sau không nên dùng trong service:

~~~java
public Inventory getInventory(String sku) {
    CircuitBreakerRegistry registry =
            CircuitBreakerRegistry.ofDefaults();
    CircuitBreaker circuitBreaker =
            registry.circuitBreaker("inventory");

    return circuitBreaker.executeSupplier(
            () -> inventoryClient.get(sku));
}
~~~

Mỗi lần gọi `getInventory`, code tạo registry mới và Circuit Breaker mới. Giả sử 100 request cùng gọi dịch vụ Kho và 40 request gặp lỗi. Thay vì một instance nhìn thấy 100 kết quả và có thể đạt ngưỡng lỗi 50%, ứng dụng có thể tạo ra 100 instance riêng lẻ, mỗi instance chỉ thấy một kết quả. Không instance nào có đủ mẫu để mở mạch.

Các hệ quả khác:

- Trạng thái OPEN không được giữ lại cho request tiếp theo.
- Sliding window bị phân mảnh, làm tỷ lệ lỗi không phản ánh toàn bộ lưu lượng.
- Event listener phải đăng ký lặp lại và khó quản lý vòng đời.
- Metrics có thể thiếu nhất quán hoặc tạo ra nhiều đối tượng đo lường không cần thiết.
- Tạo registry và instance liên tục làm tăng chi phí cấp phát và gây khó khăn khi quan sát.

Hãy tạo registry một lần trong vòng đời ứng dụng hoặc dùng registry được Spring Boot/Resilience4j tự cấu hình. Mỗi lần xử lý request chỉ tra cứu instance theo tên từ registry dùng chung.

## 5. Quản lý registry như một thành phần dùng chung trong Spring

Khi ứng dụng sử dụng Resilience4j Spring Boot starter, registry thường được cấu hình và quản lý bởi cơ chế auto-configuration. Hãy inject registry đã được cấu hình thay vì tự tạo registry trong từng service hoặc request.

Ví dụ service nhận registry qua constructor:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreaker inventoryCircuitBreaker;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerRegistry registry,
            InventoryClient inventoryClient) {
        this.inventoryCircuitBreaker =
                registry.circuitBreaker("inventory");
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        return inventoryCircuitBreaker.executeSupplier(
                () -> inventoryClient.get(sku));
    }
}
~~~

Constructor chạy khi Spring tạo bean, nên instance được tra cứu một lần và dùng lại qua các request. Nếu service có nhiều phụ thuộc, có thể lấy một instance cho từng tên và lưu trong các field tương ứng.

Nếu ứng dụng tự cấu hình registry thay vì dùng auto-configuration, có thể khai báo một bean singleton:

~~~java
@Configuration
public class CircuitBreakerRegistryConfiguration {
    @Bean
    CircuitBreakerRegistry circuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();
        return CircuitBreakerRegistry.of(config);
    }
}
~~~

Chỉ chọn cách tự khai báo bean khi ứng dụng không có registry phù hợp do starter cung cấp hoặc khi có chủ đích thay thế cấu hình mặc định. Không tạo thêm nhiều bean registry với cùng mục tiêu mà không xác định rõ registry nào được inject.

## 6. Cấu hình instance và hành vi khi tra cứu

Có thể cấu hình instance trong `application.yml`:

~~~yaml
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
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
        failureRateThreshold: 30
        waitDurationInOpenState: 30s
~~~

Registry và integration của Spring sử dụng các tên instance để liên kết lời gọi với cấu hình tương ứng. Với `inventory`, mọi thành phần tra cứu cùng tên trong registry dùng chung sẽ dùng chung instance. `payment` là instance khác, có trạng thái và cửa sổ riêng.

Một điểm cần chú ý là cấu hình được gắn vào instance khi nó được tạo. Không nên tra cứu cùng một tên nhiều lần với các cấu hình khác nhau rồi kỳ vọng mỗi biến nhận một cấu hình riêng. Nếu cần chính sách khác nhau cho các thao tác có đặc tính khác nhau, hãy dùng tên instance khác nhau, ví dụ `inventory-read` và `inventory-reservation`.

Khi thay đổi cấu hình, hành vi cập nhật nóng phụ thuộc vào cách ứng dụng nạp cấu hình và phiên bản integration đang dùng. Không nên giả định một instance đã tồn tại tự động nhận mọi thay đổi YAML; cần xác minh cơ chế refresh hoặc khởi tạo lại được triển khai trong môi trường cụ thể.

## 7. Lấy instance hiện có hay tạo mới?

Trong cùng một registry, phương thức tra cứu theo tên thường có hành vi lấy hoặc tạo:

| Thao tác | Ý nghĩa |
| --- | --- |
| `registry.circuitBreaker("inventory")` | Lấy instance đã có; nếu chưa có thì tạo theo cấu hình mặc định |
| `registry.circuitBreaker("inventory", config)` | Lấy instance theo tên hoặc tạo instance mới bằng cấu hình được cung cấp nếu tên chưa tồn tại |
| `registry.find("inventory")` | Tìm instance đã tồn tại mà không yêu cầu tạo mới |
| `registry.getAllCircuitBreakers()` | Lấy tập hợp instance registry đang quản lý |

Khi instance `inventory` đã tồn tại, việc gọi lại phương thức tra cứu cùng tên không tạo một cửa sổ trượt mới. Vì vậy, hãy thống nhất cấu hình trước khi instance được sử dụng lần đầu. Nếu muốn một Circuit Breaker có trạng thái riêng, hãy chọn tên khác hoặc tạo registry riêng một cách có chủ đích.

## 8. Gắn event listener với instance dùng chung

Circuit Breaker cung cấp event publisher để quan sát các sự kiện như lời gọi thành công, lỗi, bị từ chối hoặc chuyển trạng thái. Listener nên được đăng ký một lần trên instance dùng chung, chẳng hạn khi Spring khởi tạo bean:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CircuitBreakerEventConfiguration {
    @Bean
    CircuitBreaker inventoryCircuitBreaker(
            CircuitBreakerRegistry registry) {
        CircuitBreaker circuitBreaker =
                registry.circuitBreaker("inventory");

        circuitBreaker.getEventPublisher()
                .onStateTransition(event ->
                        log.info("Inventory circuit breaker state transition: {}", event))
                .onError(event ->
                        log.warn("Inventory circuit breaker error: {}", event))
                .onSuccess(event ->
                        log.debug("Inventory circuit breaker success: {}", event));

        return circuitBreaker;
    }
}
~~~

Trong ví dụ, `log` là logger của lớp cấu hình. Listener gắn vào đúng instance `inventory`; các lời gọi qua cùng instance sẽ phát sự kiện đến listener này. Nếu mỗi request tạo registry và instance mới, listener không quan sát được một dòng sự kiện tập trung và ứng dụng có thể đăng ký rất nhiều listener trùng lặp.

Có thể dùng event để:

- Ghi nhận thời điểm mạch chuyển CLOSED sang OPEN hoặc OPEN sang HALF_OPEN.
- Đếm số lỗi và số lời gọi bị từ chối.
- Phát tín hiệu cho hệ thống quan sát hoặc cảnh báo.
- Hỗ trợ chẩn đoán khi phụ thuộc phục hồi hoặc tiếp tục lỗi.

Không nên thực hiện thao tác blocking hoặc gọi lại dịch vụ phụ thuộc trong event listener. Listener nên xử lý nhanh, tránh làm chậm luồng phát sự kiện. Nếu cần gửi sự kiện đến hệ thống khác, hãy đưa công việc sang một cơ chế bất đồng bộ có giới hạn và có xử lý lỗi riêng.

## 9. Registry event và Circuit Breaker event khác nhau

Hai loại sự kiện có phạm vi khác nhau:

| Loại sự kiện | Phạm vi | Ví dụ |
| --- | --- | --- |
| Registry event | Vòng đời các entry trong registry | Một Circuit Breaker được thêm hoặc thay thế trong registry |
| Circuit Breaker event | Hoạt động của một instance cụ thể | Lời gọi thành công, lỗi, bị từ chối hoặc chuyển trạng thái |

Nếu mục tiêu là quan sát sức khỏe của dịch vụ Kho, event publisher của instance `inventory` là nguồn phù hợp. Nếu mục tiêu là theo dõi việc tạo và quản lý các instance trong registry, dùng cơ chế registry event tương ứng của Resilience4j.

Không nên nhầm event “instance được thêm vào registry” với event “Circuit Breaker chuyển sang OPEN”. Event đầu tiên phản ánh vòng đời cấu hình; event thứ hai phản ánh tình trạng lời gọi và sức khỏe phụ thuộc.

## 10. Kiểm tra hai cách lấy instance

Có thể kiểm tra hành vi identity và state bằng một ví dụ đơn giản:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(5))
        .build();

CircuitBreakerRegistry sharedRegistry =
        CircuitBreakerRegistry.of(config);

CircuitBreaker first = sharedRegistry.circuitBreaker("inventory");
CircuitBreaker second = sharedRegistry.circuitBreaker("inventory");

assert first == second;

CircuitBreakerRegistry isolatedRegistry =
        CircuitBreakerRegistry.of(config);
CircuitBreaker isolated =
        isolatedRegistry.circuitBreaker("inventory");

assert first != isolated;
~~~

Để kiểm tra state, có thể tạo một số lời gọi thất bại qua `first` đủ để đạt ngưỡng. Sau đó, đọc trạng thái qua `second`; vì hai biến tham chiếu cùng instance, `second.getState()` sẽ phản ánh trạng thái vừa thay đổi. Đọc `isolated.getState()` vẫn phản ánh lịch sử riêng của registry độc lập.

Trong kiểm thử, nên dùng cấu hình cửa sổ nhỏ và thời gian OPEN ngắn để quan sát chuyển trạng thái nhanh. Không dùng các giá trị kiểm thử đó làm cấu hình sản xuất nếu chưa đánh giá lưu lượng và độ trễ thực tế.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo registry trong mỗi request | Mỗi request có trạng thái và sliding window riêng | Inject registry dùng chung và tra cứu instance theo tên |
| Tạo cùng tên trong hai registry rồi nghĩ chúng dùng chung state | Một instance OPEN nhưng instance kia vẫn CLOSED | Dùng cùng registry nếu cần chia sẻ trạng thái |
| Dùng một tên cho các thao tác cần chính sách riêng | Các thao tác dùng chung trạng thái và cấu hình | Tách tên instance theo phụ thuộc hoặc nhóm thao tác |
| Đăng ký event listener mỗi lần xử lý request | Listener trùng lặp, log hoặc metrics bị nhân bản | Đăng ký listener một lần trong vòng đời bean |
| Tra cứu cùng tên với cấu hình khác nhau và kỳ vọng thay thế cấu hình hiện có | Instance đã tạo tiếp tục được dùng | Chốt cấu hình trước khi tạo hoặc dùng tên khác |
| Tự tạo registry dù Spring đã cung cấp registry được cấu hình | Có nhiều nơi quản lý state và khó quan sát | Dùng registry auto-configured hoặc thay thế có chủ đích |
| Không theo dõi event chuyển trạng thái | Khó biết thời điểm mạch mở và phục hồi | Đăng ký listener và theo dõi metrics |

## 12. Quy trình chọn registry và instance

Khi triển khai Circuit Breaker cho một phụ thuộc, hãy thực hiện theo trình tự:

1. Xác định nhóm lời gọi nào cần chia sẻ cùng trạng thái và nhóm nào cần Circuit Breaker độc lập.
2. Dùng registry được Spring/Resilience4j quản lý hoặc tạo một registry singleton nếu ứng dụng tự cấu hình.
3. Chọn tên instance ổn định, ví dụ `inventory`, và khai báo cấu hình tương ứng.
4. Tra cứu instance một lần khi khởi tạo service hoặc bean; không tạo registry trong mỗi request.
5. Đăng ký event listener trên instance dùng chung nếu cần theo dõi chuyển trạng thái và kết quả lời gọi.
6. Kiểm tra rằng hai lần tra cứu cùng tên trong cùng registry trả về cùng instance, còn registry độc lập tạo instance riêng.
7. Quan sát metrics và event để xác nhận trạng thái cùng sliding window được chia sẻ đúng phạm vi.

Lấy lại cùng instance từ một registry dùng chung giúp các request cùng phụ thuộc chia sẻ trạng thái, sliding window và sự kiện. Tạo registry độc lập chỉ phù hợp khi muốn tách biệt miền trạng thái một cách có chủ đích. Quản lý registry theo vòng đời ứng dụng và đăng ký listener một lần giúp Circuit Breaker hoạt động nhất quán, dễ theo dõi và hỗ trợ bảo vệ dịch vụ Spring Cloud khỏi lỗi dây chuyền.
