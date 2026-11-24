# Giới hạn cập nhật cấu hình của instance đã tồn tại trong registry

Trong Resilience4j, `CircuitBreakerRegistry` quản lý các instance Circuit Breaker theo tên. Registry giúp nhiều thành phần trong ứng dụng lấy lại cùng một instance, nhờ đó trạng thái, sliding window và metrics của một dependency được chia sẻ nhất quán.

Cách quản lý theo tên này có một hệ quả quan trọng: cấu hình được dùng khi instance được tạo. Nếu một Circuit Breaker đã tồn tại trong registry, gọi lại phương thức lấy instance với một `CircuitBreakerConfig` mới thường chỉ trả về instance đang được quản lý; nó không tự thay cấu hình của instance đó. Thay đổi YAML, shared configuration hoặc Java `Customizer` vì thế không đồng nghĩa với việc các instance đang chạy được cập nhật ngay.

Bài học giải thích giới hạn này, phân biệt cấu hình dùng để tạo instance với instance đang hoạt động, và trình bày cách thay thế có kiểm soát khi thực sự cần áp dụng cấu hình mới.

## 1. Registry quản lý instance theo tên

`CircuitBreakerRegistry` là factory kiêm nơi lưu trữ các Circuit Breaker. Khi yêu cầu một instance theo tên, registry sẽ:

1. Tìm instance có tên đó trong registry.
2. Nếu đã có, trả về instance hiện có.
3. Nếu chưa có, tạo instance mới với cấu hình được chọn và lưu vào registry.

Ví dụ:

~~~java
CircuitBreakerRegistry registry = CircuitBreakerRegistry.ofDefaults();

CircuitBreaker inventory = registry.circuitBreaker("inventory");
CircuitBreaker payment = registry.circuitBreaker("payment");
~~~

Hai tên `inventory` và `payment` đại diện cho hai dependency khác nhau. Mỗi instance có trạng thái, bộ đếm và sliding window riêng.

Có thể yêu cầu registry lấy hoặc tạo instance với một cấu hình cụ thể:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .failureRateThreshold(40)
    .waitDurationInOpenState(Duration.ofSeconds(15))
    .build();

CircuitBreaker inventory = registry.circuitBreaker("inventory", config);
~~~

Phương thức này có ý nghĩa **lấy instance đã quản lý hoặc tạo instance mới**. Nếu tên `inventory` đã tồn tại, registry trả về instance đó. Cấu hình truyền vào không phải lệnh cập nhật cấu hình cho instance hiện có.

Đây là điểm dễ gây nhầm lẫn khi ứng dụng khởi tạo Circuit Breaker ở nhiều nơi. Một thành phần có thể tạo `inventory` trước với cấu hình A; thành phần khác gọi cùng tên với cấu hình B và nghĩ rằng B sẽ được áp dụng. Trên thực tế, cả hai có thể đang nhận cùng một instance được tạo bằng cấu hình A.

## 2. Cấu hình và instance là hai đối tượng khác nhau

`CircuitBreakerConfig` mô tả các quy tắc như:

- `failureRateThreshold`: ngưỡng tỷ lệ lỗi để chuyển sang OPEN.
- `slowCallRateThreshold`: ngưỡng tỷ lệ lời gọi chậm.
- `slowCallDurationThreshold`: thời lượng từ đó một lời gọi được xem là chậm.
- `slidingWindowType` và `slidingWindowSize`: cách tính và kích thước cửa sổ đánh giá.
- `minimumNumberOfCalls`: số mẫu tối thiểu trước khi đánh giá tỷ lệ.
- `waitDurationInOpenState`: thời gian chờ trước khi cho phép thăm dò phục hồi.

Cấu hình được xây dựng bằng builder và được dùng như một bản mô tả tại thời điểm tạo Circuit Breaker. Instance đang chạy giữ cấu hình mà nó được khởi tạo cùng. Thay đổi một nguồn cấu hình bên ngoài không tự biến instance cũ thành một instance mới.

Có thể hình dung luồng khởi tạo như sau:

~~~text
application.yml / Java configuration
                 |
                 v
       CircuitBreakerConfig
                 |
                 v
       CircuitBreakerRegistry
                 |
          tạo theo tên
                 |
                 v
       CircuitBreaker instance
       - state
       - sliding window
       - metrics
       - event publisher
~~~

Vì vậy, cần phân biệt hai việc:

- **Thay đổi cấu hình nguồn:** cập nhật giá trị trong YAML, shared configuration hoặc đoạn Java tạo config.
- **Thay đổi instance đang hoạt động:** làm cho lời gọi thực tế sử dụng một Circuit Breaker được tạo với cấu hình mới.

Việc thứ nhất không tự bảo đảm việc thứ hai.

## 3. Vì sao gọi lại registry với cấu hình mới không cập nhật instance?

Giả sử `inventory` đã được tạo với ngưỡng lỗi 50%:

~~~java
CircuitBreakerConfig firstConfig = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)
    .build();

CircuitBreaker first = registry.circuitBreaker("inventory", firstConfig);
~~~

Sau đó, ứng dụng tạo cấu hình mới với ngưỡng lỗi 30% và gọi registry lần nữa:

~~~java
CircuitBreakerConfig secondConfig = CircuitBreakerConfig.from(firstConfig)
    .failureRateThreshold(30)
    .build();

CircuitBreaker second = registry.circuitBreaker("inventory", secondConfig);
~~~

`second` vẫn là instance đã được registry quản lý dưới tên `inventory`. Không nên suy luận rằng ngưỡng của instance đã chuyển từ 50% sang 30% chỉ vì lời gọi thứ hai truyền `secondConfig`.

Có thể kiểm tra bằng cách đọc cấu hình hiện tại của instance:

~~~java
float currentThreshold = second.getCircuitBreakerConfig()
    .getFailureRateThreshold();

System.out.println(currentThreshold);
~~~

Kết quả phản ánh cấu hình gắn với instance được trả về, không phải nhất thiết là cấu hình vừa truyền trong lời gọi gần nhất.

Quy tắc này áp dụng cho các overload lấy instance theo tên: cấu hình chỉ được dùng khi registry cần tạo entry mới. Nếu cần đổi cấu hình, phải có một chiến lược thay thế instance hoặc một cơ chế cập nhật được thư viện và phiên bản đang dùng hỗ trợ rõ ràng.

## 4. Shared configuration cũng không tự sửa instance cũ

Resilience4j cho phép đăng ký cấu hình dùng chung để nhiều instance mới có thể tái sử dụng:

~~~java
CircuitBreakerConfig standardConfig = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .build();

registry.addConfiguration("standard", standardConfig);

CircuitBreaker inventory = registry.circuitBreaker("inventory", "standard");
CircuitBreaker shipping = registry.circuitBreaker("shipping", "standard");
~~~

Trong ví dụ, `inventory` và `shipping` được tạo từ cấu hình `standard`.

Nếu ứng dụng đăng ký lại một cấu hình có cùng tên với giá trị mới, thay đổi đó tác động đến cấu hình được registry lưu dưới tên `standard`. Các Circuit Breaker đã được tạo từ cấu hình trước đó vẫn giữ cấu hình mà chúng đã nhận lúc khởi tạo.

Một lời gọi lấy lại instance hiện có bằng tên và shared configuration cũng không phải thao tác refresh instance:

~~~java
registry.addConfiguration("standard", updatedConfig);

// Nếu inventory đã tồn tại, registry vẫn trả instance đã quản lý.
CircuitBreaker inventoryAgain = registry.circuitBreaker("inventory", "standard");
~~~

Do đó, shared configuration giúp chuẩn hóa cách tạo instance, nhưng không phải cơ chế tự đồng bộ cấu hình đến mọi instance đang chạy.

## 5. Cấu hình trong Spring Boot và Spring Cloud

Trong Spring Boot, Resilience4j thường nhận cấu hình từ `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s

      cautious:
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30

    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: cautious
~~~

`configs` khai báo các cấu hình có thể dùng chung. `instances` khai báo cấu hình theo từng instance và có thể kế thừa bằng `baseConfig`.

Spring Cloud CircuitBreaker với Resilience4j còn cho phép cấu hình mặc định bằng `Customizer<Resilience4JCircuitBreakerFactory>` và cấu hình theo properties. Theo tài liệu Spring Cloud, cấu hình properties có độ ưu tiên cao hơn Java `Customizer` khi xác định cấu hình Circuit Breaker.

Tuy nhiên, độ ưu tiên khi hợp nhất cấu hình lúc khởi tạo không có nghĩa là tự cập nhật một instance đã được tạo. Ví dụ:

- Ứng dụng khởi động, registry tạo `inventory` từ properties.
- Một nguồn cấu hình bên ngoài thay đổi `failureRateThreshold`.
- Environment hoặc bean chứa properties có thể nhận giá trị mới tùy cơ chế refresh đang dùng.
- Instance `inventory` trong registry vẫn là đối tượng đang tồn tại cho đến khi ứng dụng thay thế hoặc tạo lại nó theo một quy trình cụ thể.

Không nên coi việc sửa `application.yml`, cập nhật Config Server hoặc gọi refresh endpoint là bằng chứng rằng Circuit Breaker đang chạy đã nhận cấu hình mới. Cần xác định rõ thành phần nào nạp lại properties, thành phần nào tạo registry và cách thay instance trong phiên bản thư viện đang sử dụng.

## 6. Cách đơn giản nhất: khởi động lại ứng dụng

Với ứng dụng không yêu cầu thay đổi ngưỡng ngay khi đang chạy, khởi động lại là cách dễ kiểm soát nhất:

1. Cập nhật `application.yml` hoặc nguồn cấu hình tương ứng.
2. Kiểm tra cấu hình mới hợp lệ và tương thích với phiên bản thư viện.
3. Triển khai hoặc khởi động lại ứng dụng theo quy trình vận hành.
4. Để Spring Boot khởi tạo registry và Circuit Breaker từ cấu hình mới.
5. Kiểm tra cấu hình thực tế của instance sau khi khởi động.

Khi ứng dụng khởi tạo lại, các instance mới được tạo từ cấu hình mới. Trạng thái hiện tại và sliding window của instance cũ cũng không được giữ nguyên như một phần của instance mới. Nếu trạng thái bảo vệ hoặc lịch sử metrics có ý nghĩa với vận hành, cần tính đến việc này khi lập kế hoạch triển khai.

Đối với nhiều hệ thống, rolling deployment với nhiều replica giúp thay đổi cấu hình lần lượt mà vẫn duy trì khả năng phục vụ. Cần bảo đảm các replica không chạy cấu hình khác nhau lâu hơn mức chấp nhận được.

## 7. Thay thế instance trong registry khi cần cập nhật lúc chạy

Resilience4j Registry cung cấp các thao tác quản lý entry như `remove(name)` và `replace(name, newEntry)`. Chúng cho phép ứng dụng chủ động thay instance đang được registry quản lý. Hãy xác nhận các phương thức này có trong phiên bản `resilience4j-core` mà dự án đang dùng trước khi triển khai.

Có thể xây dựng cấu hình mới từ cấu hình hiện tại để chỉ thay đổi một vài thuộc tính:

~~~java
CircuitBreaker current = registry.circuitBreaker("inventory");

CircuitBreakerConfig updatedConfig = CircuitBreakerConfig
    .from(current.getCircuitBreakerConfig())
    .failureRateThreshold(30)
    .waitDurationInOpenState(Duration.ofSeconds(20))
    .build();

CircuitBreaker replacement = CircuitBreaker.of("inventory", updatedConfig);

registry.replace("inventory", replacement)
    .orElseThrow(() -> new IllegalStateException(
        "Circuit Breaker inventory was not present in the registry"
    ));
~~~

Ví dụ tạo một instance mới với cấu hình mới và thay entry có tên `inventory` trong registry. `replace` trả về entry cũ nếu có thể thay thế.

Trong ví dụ, `CircuitBreaker.of` tạo đối tượng trực tiếp. Nếu ứng dụng dựa vào registry tags, customizer hoặc registry event consumer để gắn metrics và listener lúc tạo entry, cần bảo đảm các metadata và listener đó cũng được áp dụng cho instance thay thế. Hãy kiểm tra cách registry xử lý sự kiện `REPLACED` trong đúng phiên bản đang dùng.

Nếu phiên bản đang dùng không có `replace`, có thể cân nhắc `remove` rồi tạo lại:

~~~java
registry.remove("inventory")
    .orElseThrow(() -> new IllegalStateException(
        "Circuit Breaker inventory was not present"
    ));

CircuitBreaker replacement = registry.circuitBreaker("inventory", updatedConfig);
~~~

Cách `remove` rồi tạo lại có một khoảng thời gian tên instance chưa tồn tại. Nếu nhiều luồng có thể truy cập registry cùng lúc, một luồng khác có thể tạo instance mới trong khoảng đó. Vì vậy, không nên thực hiện chuỗi thao tác này tùy tiện trong đường xử lý request đang có lưu lượng.

`replace` cũng cần được triển khai có kiểm soát. Việc thay entry trong registry không tự chuyển các tham chiếu Java đang giữ instance cũ sang instance mới.

## 8. Tham chiếu cũ và lời gọi đang chạy

Giả sử một service lấy Circuit Breaker một lần trong constructor:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreaker inventoryBreaker;

    public InventoryGateway(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public InventoryResponse getInventory(String sku) {
        return inventoryBreaker.executeSupplier(
            () -> loadInventoryFromRemote(sku)
        );
    }

    private InventoryResponse loadInventoryFromRemote(String sku) {
        // Gọi HTTP đến dịch vụ Inventory
        return new InventoryResponse(sku, 25);
    }
}
~~~

Nếu registry thay entry `inventory` bằng một instance mới, trường `inventoryBreaker` trong service vẫn trỏ đến đối tượng cũ. Các lời gọi qua trường này tiếp tục sử dụng cấu hình và trạng thái của instance cũ.

Có thể tránh giữ tham chiếu cũ bằng cách tra cứu registry tại thời điểm gọi:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreakerRegistry registry;

    public InventoryGateway(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public InventoryResponse getInventory(String sku) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        return breaker.executeSupplier(
            () -> loadInventoryFromRemote(sku)
        );
    }

    private InventoryResponse loadInventoryFromRemote(String sku) {
        // Gọi HTTP đến dịch vụ Inventory
        return new InventoryResponse(sku, 25);
    }
}
~~~

Với cách này, mỗi lần gọi service sẽ lấy entry hiện đang có trong registry. Sau khi thay entry thành công, các lần tra cứu sau có thể nhận instance mới.

Một cách khác là dùng một lớp indirection như `AtomicReference<CircuitBreaker>` để quản lý tham chiếu hiện hành. Khi thay instance, ứng dụng cập nhật reference bằng một thao tác nguyên tử. Cách này phù hợp khi muốn kiểm soát chính xác thời điểm chuyển đổi mà không tra cứu registry ở mọi request.

Dù dùng cách nào, các lời gọi đã bắt đầu trước khi thay instance có thể tiếp tục chạy trên Circuit Breaker cũ. Không có thao tác thay entry nào tự di chuyển lời gọi đang thực thi sang đối tượng mới.

## 9. Những hệ quả khi thay instance

Thay một Circuit Breaker bằng instance mới có thể làm thay đổi nhiều hơn ngưỡng cấu hình.

| Thành phần | Khi thay bằng instance mới |
| --- | --- |
| Cấu hình | Instance mới sử dụng cấu hình mới. |
| State | Instance mới có trạng thái khởi tạo; trạng thái OPEN hoặc HALF_OPEN của instance cũ không tự được chuyển sang. |
| Sliding window | Lịch sử lời gọi của instance cũ không tự chuyển sang cửa sổ mới. |
| Metrics | Bộ đếm và dữ liệu gắn với instance cũ không tự được gộp vào instance mới. |
| Event publisher | Listener đăng ký trực tiếp trên instance cũ không tự chuyển sang instance mới; cần đăng ký lại theo cơ chế quản lý của ứng dụng. |
| Tham chiếu Java | Thành phần đang giữ instance cũ tiếp tục sử dụng nó cho đến khi được cập nhật. |

Vì vậy, thay instance có thể làm mất lịch sử cần thiết để ra quyết định. Ví dụ, nếu Circuit Breaker cũ đang OPEN do tỷ lệ lỗi cao, tạo instance mới ở CLOSED sẽ cho phép lời gọi đi qua theo cấu hình mới. Điều này có thể là chủ đích khi phục hồi, nhưng cũng có thể làm hệ thống gửi tải trở lại dependency đang chưa ổn định.

Trước khi thay instance, cần xác định có nên:

- Chờ các lời gọi đang chạy trên instance cũ hoàn tất.
- Tạm ngừng hoặc giới hạn lưu lượng trong thời gian chuyển đổi.
- Giữ lại state hiện tại bằng một quy trình vận hành riêng nếu yêu cầu nghiệp vụ đòi hỏi.
- Đăng ký lại metrics publisher và event consumer cho instance mới.
- Cập nhật mọi tham chiếu đã lưu giữ instance cũ.

## 10. Ví dụ một dịch vụ quản lý thay đổi cấu hình

Một lớp quản trị có thể tạo cấu hình mới, tạo instance thay thế và cập nhật registry. Ví dụ sau minh họa ý tưởng; phần xác thực quyền thay đổi, kiểm soát đồng thời, metrics và event consumer cần được bổ sung theo hệ thống thực tế.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

import java.time.Duration;

@Service
public class CircuitBreakerConfigurationManager {

    private final CircuitBreakerRegistry registry;

    public CircuitBreakerConfigurationManager(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void updateInventoryThreshold(float failureThreshold) {
        if (failureThreshold <= 0 || failureThreshold > 100) {
            throw new IllegalArgumentException(
                "failureThreshold must be greater than 0 and at most 100"
            );
        }

        CircuitBreaker current = registry.find("inventory")
            .orElseThrow(() -> new IllegalStateException(
                "Circuit Breaker inventory does not exist"
            ));

        CircuitBreakerConfig newConfig = CircuitBreakerConfig
            .from(current.getCircuitBreakerConfig())
            .failureRateThreshold(failureThreshold)
            .waitDurationInOpenState(Duration.ofSeconds(20))
            .build();

        CircuitBreaker replacement = CircuitBreaker.of(
            "inventory",
            newConfig
        );

        registry.replace("inventory", replacement)
            .orElseThrow(() -> new IllegalStateException(
                "Circuit Breaker inventory could not be replaced"
            ));
    }
}
~~~

Phương thức kiểm tra ngưỡng trước khi tạo config để tránh đưa giá trị không hợp lệ vào hệ thống. Cấu hình mới kế thừa các thuộc tính còn lại từ cấu hình hiện tại và thay đổi hai thuộc tính được chỉ định.

Trong hệ thống production, không nên để mọi request tùy ý gọi phương thức này. Hãy giới hạn quyền quản trị, ghi lại giá trị trước và sau khi thay đổi, xác định phiên bản cấu hình, và bảo đảm các replica nhận cùng một quyết định. Nếu dùng Spring Cloud CircuitBreaker factory, cần chắc chắn factory và các service lấy Circuit Breaker đều sử dụng đúng registry được thay thế.

## 11. Lựa chọn chiến lược theo nhu cầu

| Nhu cầu | Chiến lược phù hợp | Điểm cần chú ý |
| --- | --- | --- |
| Cập nhật cấu hình định kỳ, ít thay đổi | Cập nhật properties và triển khai lại ứng dụng | Đơn giản, dễ kiểm soát phiên bản và vòng đời instance |
| Cần thay đổi ngưỡng khi ứng dụng đang chạy | Tạo config mới và thay entry trong registry | Quản lý tham chiếu cũ, state, metrics và lời gọi đang thực thi |
| Cần nhiều dịch vụ dùng chung bộ quy tắc | Dùng named shared configuration | Cấu hình dùng chung chủ yếu phục vụ tạo instance; không tự cập nhật instance cũ |
| Muốn giữ instance và state hiện tại | Chỉ dùng cơ chế cập nhật trực tiếp nếu phiên bản thư viện có API hỗ trợ chính thức cho thuộc tính cần đổi | Kiểm tra tài liệu và API đúng phiên bản; không giả định mọi thuộc tính đều có thể thay đổi |
| Cần thay đổi đồng bộ nhiều replica | Quản lý cấu hình tập trung và triển khai quy trình rollout | Tránh các replica áp dụng ngưỡng khác nhau ngoài dự kiến |

Không phải mọi ứng dụng đều cần thay Circuit Breaker lúc chạy. Nếu cấu hình chỉ thay đổi trong các lần phát hành, khởi động lại ứng dụng thường dễ vận hành và kiểm chứng hơn. Chỉ nên xây dựng cơ chế thay instance động khi có yêu cầu thực tế, có cách kiểm soát lưu lượng và có thể quan sát kết quả.

## 12. Checklist kiểm tra sau khi cập nhật

Sau khi áp dụng cấu hình mới, kiểm tra theo thứ tự:

1. **Đúng tên instance:** service và registry cùng sử dụng một tên Circuit Breaker.
2. **Đúng registry:** factory, service và lớp quản trị cùng thao tác trên registry do ứng dụng quản lý.
3. **Đúng cấu hình mới:** đọc `getCircuitBreakerConfig()` từ instance hiện hành và kiểm tra các giá trị quan trọng.
4. **Đúng tham chiếu:** các service không tiếp tục giữ instance cũ ngoài dự kiến.
5. **Đúng trạng thái:** xác định instance mới bắt đầu ở trạng thái nào và hành vi khi dependency lỗi.
6. **Đúng metrics:** xác nhận metrics publisher và event consumer theo dõi instance hiện hành.
7. **Đúng lưu lượng:** kiểm tra request mới đi qua instance mới, còn request đang chạy trên instance cũ đã được xử lý theo kế hoạch.
8. **Đúng khả năng khôi phục:** chuẩn bị cách quay lại cấu hình trước nếu ngưỡng mới làm Circuit Breaker mở quá thường xuyên hoặc không mở khi cần.

Một phép thử hữu ích là ghi lại `failureRateThreshold` trước và sau khi thay instance, sau đó gửi chuỗi request có tỷ lệ lỗi được kiểm soát để quan sát thời điểm mở mạch. Cần nhớ rằng cửa sổ của instance mới bắt đầu với lịch sử mới; không thể so sánh trực tiếp số mẫu của instance cũ và mới như thể chúng là cùng một cửa sổ liên tục.

## Kết luận

Registry của Resilience4j quản lý Circuit Breaker theo tên và trả lại instance đã tồn tại khi tên được yêu cầu lần nữa. Truyền cấu hình mới vào một lời gọi lấy instance không tự cập nhật đối tượng đang chạy. Shared configuration và Spring Boot properties giúp chuẩn hóa quá trình khởi tạo, nhưng vẫn cần một quy trình rõ ràng để áp dụng thay đổi cho instance hiện hữu.

Với cấu hình ít thay đổi, triển khai lại ứng dụng là cách đơn giản để tạo các instance mới nhất quán. Nếu cần thay đổi khi đang chạy, có thể thay entry trong registry bằng một instance mới, đồng thời quản lý tham chiếu cũ, lời gọi đang thực thi, sliding window, state, metrics và event listener. Hiểu rõ giới hạn này giúp ứng dụng Spring Cloud CircuitBreaker dùng Resilience4j cập nhật cấu hình có kiểm soát và tránh tình trạng YAML đã đổi nhưng hành vi bảo vệ thực tế vẫn giữ cấu hình cũ.

## Tài liệu tham khảo

- [Resilience4j CircuitBreaker — Registry và cấu hình](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Registry API — remove và replace](https://javadoc.io/doc/io.github.resilience4j/resilience4j-core/latest/io/github/resilience4j/core/Registry.html)
- [Resilience4j CircuitBreakerRegistry API](https://javadoc.io/doc/io.github.resilience4j/resilience4j-circuitbreaker/latest/io/github/resilience4j/circuitbreaker/CircuitBreakerRegistry.html)
- [Spring Cloud CircuitBreaker — cấu hình Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)

