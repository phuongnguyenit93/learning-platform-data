# Thời điểm an toàn để sử dụng `EurekaClient` trong vòng đời Spring

## 1. Vì sao thời điểm gọi EurekaClient quan trọng?

`EurekaClient` là client của Netflix Eureka, được Spring Cloud cấu hình và quản lý trong vòng đời ứng dụng. Nó duy trì kết nối với Eureka Server, đăng ký instance, gửi heartbeat và tải registry vào cache cục bộ. Vì vậy, thời điểm một bean Spring có thể inject được `EurekaClient` không đồng nghĩa registry đã có đầy đủ dữ liệu để tra cứu.

Một lỗi thường gặp là gọi `eurekaClient.getApplication(...)` ngay trong constructor hoặc `@PostConstruct` của một service. Lúc đó Spring có thể vẫn đang tạo các bean khác, Eureka Client có thể chưa hoàn tất lần fetch registry đầu tiên, hoặc các service phụ thuộc chưa đăng ký xong. Kết quả có thể là danh sách rỗng, không tìm thấy service hoặc lỗi khởi động không cần thiết.

Để sử dụng an toàn, cần phân biệt ba mốc:

1. **Bean đã được inject:** Spring đã cung cấp tham chiếu tới `EurekaClient`.
2. **Application context đã refresh:** các singleton bean đã được tạo và cấu hình; nhưng các tác vụ khởi động và cập nhật registry vẫn có thể đang diễn ra.
3. **Ứng dụng đã sẵn sàng phục vụ:** Spring Boot phát `ApplicationReadyEvent` sau khi context refresh và các `ApplicationRunner`/`CommandLineRunner` hoàn tất. Đây thường là mốc thích hợp để chạy logic discovery phụ thuộc vào ứng dụng đã khởi động.

Ngay cả `ApplicationReadyEvent` cũng không bảo đảm mọi instance trong cụm đã xuất hiện trong registry. Eureka có cache, heartbeat, fetch interval và replication; dữ liệu có thể chưa hội tụ. Logic quan trọng vẫn phải kiểm tra kết quả, có timeout/retry hữu hạn và xử lý trường hợp service chưa khả dụng.

## 2. `EurekaClient` được Spring quản lý như thế nào?

Khi thêm Spring Cloud Netflix Eureka Client starter, auto-configuration tạo các bean cần thiết, trong đó có Eureka Client và adapter discovery. Ứng dụng nên inject interface `EurekaClient` qua constructor hoặc field injection do Spring quản lý; không tự khởi tạo một client mới bằng `new` trong business code.

```java
@Service
public class InventoryLookup {

    private final EurekaClient eurekaClient;

    public InventoryLookup(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }
}
```

Constructor injection ở đây chỉ nhận và lưu tham chiếu. Đây là cách phù hợp để khai báo dependency. Điều cần tránh là thực hiện network/discovery logic ngay trong constructor:

```java
// Không nên: gọi registry khi bean còn đang được tạo.
public InventoryLookup(EurekaClient eurekaClient) {
    this.eurekaClient = eurekaClient;
    Application app = eurekaClient.getApplication("PAYMENT-SERVICE");
}
```

Việc tạo bean không phải tín hiệu cho biết Eureka Client đã fetch được registry hoặc ứng dụng đã hoàn tất startup. Hãy giữ constructor nhẹ, chỉ gán dependency và khởi tạo trạng thái nội bộ đơn giản.

## 3. Đánh giá các mốc trong vòng đời Spring

| Mốc vòng đời | Có thể inject `EurekaClient`? | Có nên tra cứu registry? | Lý do |
|---|---|---|---|
| Constructor của bean | Có, nếu bean được Spring quản lý | Không nên | Các dependency và tác vụ khởi động khác có thể chưa sẵn sàng |
| `@PostConstruct` | Có | Thường không nên | Chỉ bảo đảm bean hiện tại đã được khởi tạo; context và registry chưa chắc sẵn sàng |
| `InitializingBean.afterPropertiesSet()` | Có | Thường không nên | Vẫn nằm trong giai đoạn khởi tạo bean |
| `ContextRefreshedEvent` | Có | Chưa phải mốc chắc chắn | Context đã refresh nhưng runner và trạng thái sẵn sàng của ứng dụng có thể chưa hoàn tất |
| `ApplicationRunner` / `CommandLineRunner` | Có | Có thể, nhưng cần xử lý cache chưa sẵn sàng | Chạy sau context refresh và trước `ApplicationReadyEvent` |
| `ApplicationReadyEvent` | Có | Thường là mốc phù hợp | Spring Boot báo ứng dụng đã hoàn tất startup và runner |
| Request xử lý sau khi ứng dụng sẵn sàng | Có | Có | Có thể tra cứu theo nhu cầu, nhưng dữ liệu vẫn có thể cũ hoặc thay đổi |
| Giai đoạn shutdown | Bean có thể vẫn còn tham chiếu | Tránh bắt đầu discovery mới | Client/context có thể đang đóng và mạng có thể không còn sẵn sàng |

`ApplicationReadyEvent` là mốc phù hợp cho logic cần chờ ứng dụng hoàn tất khởi động, nhưng không phải cam kết rằng registry đã có mọi service. Nếu một thao tác cần sự hiện diện của service khác, hãy kiểm tra kết quả và quyết định ứng dụng sẽ chờ có giới hạn, chạy degraded mode hay báo trạng thái chưa sẵn sàng.

## 4. Vì sao `@PostConstruct` thường quá sớm?

`@PostConstruct` chạy sau khi dependency của bean hiện tại đã được inject, nhưng trước khi toàn bộ quá trình khởi động Spring Boot kết thúc. Một số tình huống khiến tra cứu Eureka ở thời điểm này không đáng tin cậy:

- Eureka Client có thể đang khởi tạo scheduler cho heartbeat và registry fetch.
- Lần tải registry đầu tiên có thể chưa hoàn tất hoặc chưa có dữ liệu.
- Service mà ứng dụng muốn tìm có thể chưa đăng ký, hoặc thay đổi chưa được replication tới server mà client đang dùng.
- Các bean phụ thuộc khác có thể chưa hoàn tất khởi tạo hoặc chưa chuyển sang trạng thái sẵn sàng.
- Nếu tra cứu thất bại làm ném exception khỏi `@PostConstruct`, toàn bộ Spring context có thể không khởi động được dù chức năng discovery đó không phải điều kiện bắt buộc.

Ví dụ không nên dùng:

```java
@Component
public class StartupProbe {

    private final EurekaClient eurekaClient;

    public StartupProbe(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @PostConstruct
    public void init() {
        // Có thể chưa có registry cache hoặc service chưa đăng ký.
        Application application = eurekaClient.getApplication("PAYMENT-SERVICE");
        // Không nên giả định application luôn khác null ở đây.
    }
}
```

Nếu chỉ cần xác minh cấu hình cục bộ, có thể thực hiện trong quá trình khởi tạo. Nhưng tra cứu service khác hoặc quyết định luồng nghiệp vụ dựa trên registry nên được thực hiện sau khi ứng dụng sẵn sàng và có xử lý trường hợp chưa tìm thấy instance.

## 5. Dùng `ApplicationReadyEvent` cho logic sau startup

Spring Boot phát `ApplicationReadyEvent` khi ứng dụng đã hoàn tất quá trình startup, bao gồm các runner. Có thể dùng event này để thực hiện một lần kiểm tra discovery ban đầu:

```java
import com.netflix.discovery.EurekaClient;
import com.netflix.discovery.shared.Application;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class DiscoveryStartupListener {

    private final EurekaClient eurekaClient;

    public DiscoveryStartupListener(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void onApplicationReady() {
        Application application = eurekaClient.getApplication("PAYMENT-SERVICE");

        if (application == null || application.getInstances().isEmpty()) {
            // Registry chưa có instance: ghi nhận và để cơ chế retry/health
            // phù hợp xử lý tiếp, thay vì giả định service chắc chắn tồn tại.
            return;
        }

        application.getInstances().forEach(instance ->
                System.out.println(instance.getHostName() + ":" + instance.getPort()));
    }
}
```

Ví dụ dùng `getApplication` để đọc application từ dữ liệu Eureka Client đang giữ. Tên application thường được lưu ở dạng chữ hoa, ví dụ `PAYMENT-SERVICE`; hãy dùng đúng app name thực tế trong registry. Phần `return` chỉ minh họa cách xử lý khi chưa có instance; hệ thống thực tế nên ghi log/metric và có chính sách retry hoặc degraded mode rõ ràng.

Không nên biến event listener thành một vòng chờ vô hạn. Nếu ứng dụng phải chờ một service quan trọng mới được nhận traffic, hãy dùng một readiness gate có thời hạn, retry với backoff và quan sát được trạng thái. Nếu service chỉ cần cho một chức năng tùy chọn, nên cho ứng dụng khởi động và xử lý lỗi khi chức năng đó được gọi.

## 6. `ApplicationReadyEvent` không đồng nghĩa registry đã hội tụ

Eureka Client thường duy trì bản cache cục bộ. Các phương thức như `getApplication(...)` và `getApplications()` đọc dữ liệu mà client đang có; chúng không nên được hiểu là một truy vấn đồng bộ bảo đảm trả về trạng thái mới nhất của toàn cụm tại từng lần gọi.

Một số nguyên nhân khiến service chưa xuất hiện ngay cả sau `ApplicationReadyEvent`:

1. Service đích chưa khởi động hoặc chưa đăng ký với Eureka Server.
2. Eureka Client của consumer chưa hoàn tất lần fetch registry hoặc đang chờ chu kỳ fetch tiếp theo.
3. Thay đổi registry chưa được replication tới peer mà consumer đang kết nối.
4. Service đích có trạng thái không phù hợp hoặc chưa được công bố dưới app name mà consumer tra cứu.
5. Mạng, DNS hoặc Eureka Server đang có sự cố khiến lần cập nhật registry thất bại.

Vì vậy, không nên dùng sự kiện `ApplicationReadyEvent` làm bằng chứng duy nhất rằng một service cụ thể đã sẵn sàng. Nó nói về trạng thái startup của ứng dụng hiện tại, không xác nhận trạng thái của toàn bộ hệ thống microservice.

### 6.1. Retry có giới hạn khi service là dependency bắt buộc

Nếu `payment-service` phải tìm được `inventory-service` trước khi xử lý traffic, có thể xây dựng bước kiểm tra readiness riêng. Quy tắc nên có:

- Thời hạn chờ tối đa được cấu hình theo SLO startup.
- Retry có khoảng nghỉ hoặc exponential backoff, tránh gọi registry liên tục.
- Ghi log và metric cho số lần thử, thời gian chờ và kết quả.
- Khi hết thời hạn, quyết định rõ fail startup hay chuyển sang trạng thái degraded.
- Không giữ thread startup vô thời hạn; bảo đảm shutdown vẫn có thể hoàn tất.

Ví dụ logic kiểm tra một lần:

```java
private boolean hasInventoryInstance() {
    Application application = eurekaClient.getApplication("INVENTORY-SERVICE");
    return application != null && !application.getInstances().isEmpty();
}
```

Hàm trên chỉ kiểm tra cache hiện tại. Phần retry nên được điều phối bởi một thành phần readiness/startup riêng và dùng giới hạn thời gian, thay vì đặt vòng lặp không giới hạn trong constructor hoặc `@PostConstruct`.

## 7. Khi nào nên gọi EurekaClient trong request hoặc tác vụ nền?

Sau khi ứng dụng đã sẵn sàng, có thể sử dụng `EurekaClient` trong service nghiệp vụ nếu thực sự cần dữ liệu riêng của Eureka. Tuy nhiên, cần nhớ registry là dữ liệu động:

- Một instance có thể bị dừng ngay sau khi được trả về.
- Cache có thể chưa phản ánh lần đăng ký hoặc hủy đăng ký mới nhất.
- Network partition có thể khiến registry tạm thời không cập nhật.
- `InstanceInfo` không chứng minh endpoint còn phục vụ request thành công tại thời điểm gọi.

Do đó, không nên tra cứu một lần khi startup rồi lưu địa chỉ instance vĩnh viễn. Nếu cần gọi service theo tên, thường nên dùng Spring Cloud LoadBalancer cùng `DiscoveryClient` abstraction để lấy instance và chọn đích theo từng request. Cách này giữ logic gọi service ít phụ thuộc Eureka hơn.

Nếu cần dùng API riêng của Eureka như `getApplication`, `getApplications`, tra cứu theo VIP hoặc đọc `InstanceInfo`, hãy giới hạn phần code phụ thuộc vào `EurekaClient` trong adapter/service chuyên biệt. Xử lý trường hợp `null`, danh sách rỗng và lỗi kết nối; không giả định registry luôn có dữ liệu.

## 8. An toàn khi shutdown

Spring Cloud quản lý vòng đời Eureka Client. Khi application context đóng bình thường, client được dọn dẹp và có thể gửi yêu cầu deregistration tới Eureka Server. Không nên tự tạo hoặc tự đóng một Eureka Client khác trong business bean, cũng không nên gọi `shutdown()` thủ công lên bean do Spring quản lý.

Nếu cần rút instance khỏi traffic một cách có kiểm soát, có thể chuyển trạng thái instance sang `OUT_OF_SERVICE` trước khi đóng context, chờ consumer cập nhật registry và drain request đang xử lý, sau đó để Spring đóng ứng dụng:

```java
applicationInfoManager.setInstanceStatus(InstanceInfo.InstanceStatus.OUT_OF_SERVICE);
```

Thao tác trên dùng `ApplicationInfoManager` của Eureka để thay đổi trạng thái local và gửi cập nhật theo cơ chế client. Cần thiết kế thời gian drain, timeout và xử lý khi Eureka Server không truy cập được. Việc chuyển trạng thái không thay thế quy trình đóng ứng dụng.

Không nên bắt đầu một tác vụ discovery mới trong `@PreDestroy` hoặc khi context đã đóng. Ở giai đoạn này, các thành phần có thể đang dừng, scheduler có thể bị hủy và kết nối mạng có thể không còn sẵn sàng. Nếu quy trình shutdown cần cập nhật trạng thái, hãy điều phối nó trước khi đóng context bằng một lifecycle/shutdown coordinator rõ ràng; sau đó để Spring quản lý việc đóng Eureka Client và deregistration.

## 9. Những cách làm nên tránh

| Cách làm | Rủi ro | Cách làm phù hợp hơn |
|---|---|---|
| Gọi `getApplication()` trong constructor | Bean được tạo trước khi startup hoàn tất | Constructor chỉ lưu dependency; tra cứu sau readiness |
| Gọi registry trong `@PostConstruct` | Registry cache hoặc service đích có thể chưa sẵn sàng | Dùng `ApplicationReadyEvent` và kiểm tra kết quả |
| Giả định `ApplicationReadyEvent` bảo đảm registry mới nhất | Event chỉ nói ứng dụng hiện tại đã hoàn tất startup | Xử lý cache, replication và retry hữu hạn |
| Vòng lặp chờ service vô hạn khi startup | Có thể treo startup và gây khó shutdown | Dùng timeout, backoff và readiness policy |
| Lưu host/port lấy được lúc startup vô thời hạn | Instance có thể thay đổi hoặc bị loại khỏi registry | Tra cứu/chọn instance theo request qua LoadBalancer |
| Tự tạo `EurekaClient` bằng `new` | Tạo client ngoài lifecycle và scheduler do Spring quản lý | Inject bean `EurekaClient` do auto-configuration cung cấp |
| Tự gọi `shutdown()` lên bean Spring | Có thể đóng client trong khi bean khác vẫn cần dùng | Để Spring quản lý lifecycle và đóng context |
| Gọi discovery trong `@PreDestroy` | Client hoặc network có thể đang đóng | Điều phối cập nhật trạng thái trước giai đoạn đóng context |

## 10. Sơ đồ thời điểm sử dụng

```mermaid
sequenceDiagram
    autonumber
    participant Spring as Spring ApplicationContext
    participant Bean as Business Bean
    participant Eureka as EurekaClient
    participant Server as Eureka Server

    Spring->>Bean: Tạo bean và constructor injection
    Note over Bean: Chỉ lưu tham chiếu EurekaClient
    Spring->>Bean: @PostConstruct
    Note over Bean: Không tra cứu registry ở giai đoạn này
    Spring->>Eureka: Khởi tạo client và tác vụ nền
    Eureka->>Server: Register / heartbeat / fetch registry
    Spring->>Spring: Context refresh và chạy runners
    Spring-->>Bean: ApplicationReadyEvent
    Bean->>Eureka: getApplication / getApplications
    Eureka-->>Bean: Dữ liệu cache hiện tại (có thể rỗng/cũ)
    Note over Bean: Kiểm tra kết quả; retry hữu hạn nếu cần
    Spring->>Spring: Shutdown bắt đầu
    Note over Eureka,Server: Spring quản lý đóng client và deregistration
```

Sơ đồ thể hiện thứ tự khái niệm. Eureka Client có thể đăng ký và fetch registry bằng các tác vụ nền trong quá trình startup; thời điểm chính xác phụ thuộc phiên bản và cấu hình. `ApplicationReadyEvent` là mốc an toàn hơn cho logic ứng dụng, nhưng không loại bỏ tính bất đồng bộ của registry.

## 11. Checklist trước khi sử dụng EurekaClient

Trước khi thêm logic phụ thuộc `EurekaClient`, hãy kiểm tra:

1. Bean được inject từ Spring auto-configuration, không được tự khởi tạo.
2. Constructor và `@PostConstruct` không gọi registry hoặc chờ service từ xa.
3. Logic discovery khởi động sau `ApplicationReadyEvent` hoặc trong request/tác vụ đã được quản lý sau readiness.
4. Kết quả `getApplication`/`getApplications` có thể null, rỗng hoặc cũ; code xử lý các trường hợp đó.
5. Nếu dependency bắt buộc, readiness policy có timeout, retry/backoff và trạng thái lỗi rõ ràng.
6. Không giữ địa chỉ instance lấy lúc startup như một endpoint bất biến.
7. Ưu tiên `DiscoveryClient` và Spring Cloud LoadBalancer cho nhu cầu discovery/load balancing chung; chỉ dùng `EurekaClient` khi cần API riêng của Eureka.
8. Để Spring quản lý shutdown và deregistration; điều phối drain hoặc `OUT_OF_SERVICE` trước khi đóng context.

## 12. Kết luận

Có thể inject `EurekaClient` ngay khi Spring tạo bean, nhưng nên trì hoãn việc tra cứu registry cho đến khi ứng dụng đã hoàn tất startup, thường là từ `ApplicationReadyEvent` hoặc trong luồng xử lý sau readiness. Không nên gọi discovery trong constructor hay `@PostConstruct` vì registry cache, các service phụ thuộc và vòng đời ứng dụng có thể chưa sẵn sàng.

Ngay cả sau `ApplicationReadyEvent`, registry vẫn có thể đang hội tụ. Hãy kiểm tra dữ liệu trả về, dùng retry có giới hạn khi cần và xử lý service tạm thời không khả dụng. Khi shutdown, để Spring quản lý Eureka Client; nếu cần drain traffic, cập nhật trạng thái instance trước khi đóng context.
