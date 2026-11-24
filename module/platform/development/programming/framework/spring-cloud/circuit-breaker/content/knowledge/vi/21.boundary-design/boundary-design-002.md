# Không dùng một ID chung cho các hệ thống độc lập

Trong Spring Cloud CircuitBreaker, ID dùng để xác định Circuit Breaker mà một lời gọi sẽ sử dụng. ID thường liên kết với trạng thái, cấu hình, sự kiện và metric của breaker. Nếu nhiều hệ thống độc lập cùng dùng một ID, chúng có thể chia sẻ cùng một ranh giới bảo vệ. Khi một dependency gặp sự cố, lỗi của nó có thể làm breaker mở và chặn cả những lời gọi đến dependency khác vốn vẫn khỏe mạnh.

Ví dụ, một service gọi cả Inventory và Payment. Nếu cả hai lời gọi đều tạo Circuit Breaker với ID **remote-service**, lỗi thanh toán có thể làm breaker mở. Lời gọi tồn kho sau đó cũng bị từ chối dù dịch vụ tồn kho vẫn hoạt động bình thường. Đây là lỗi thiết kế ranh giới: các dependency có failure domain khác nhau đang dùng chung một đơn vị trạng thái.

Nên chọn ID ổn định theo dependency hoặc nhóm thao tác thực sự có cùng đặc tính vận hành. Inventory và Payment cần ID riêng. Các endpoint của cùng một dependency chỉ nên dùng chung ID khi chúng có cùng yêu cầu về độ tin cậy, ngưỡng lỗi, timeout và cách phục hồi.

## 1. ID xác định ranh giới Circuit Breaker

Khi tạo breaker qua Spring Cloud CircuitBreaker, ứng dụng truyền một ID vào factory:

~~~java
CircuitBreaker inventoryBreaker =
        circuitBreakerFactory.create("inventory");
~~~

ID **inventory** cho factory biết breaker nào cần được tạo hoặc lấy ra theo implementation đang dùng. Với implementation dựa trên registry như Resilience4j, ID được dùng để tra cứu instance trong registry. Những lời gọi cùng sử dụng một ID có thể cùng đi qua trạng thái breaker được quản lý cho ID đó.

Một Circuit Breaker có trạng thái riêng:

- CLOSED: cho phép lời gọi và ghi nhận kết quả.
- OPEN: từ chối lời gọi mới trong thời gian mở mạch.
- HALF_OPEN: cho phép một số lời gọi thăm dò để kiểm tra khả năng phục hồi.

Breaker cũng có cấu hình riêng như sliding window, failure threshold, slow-call threshold và thời gian OPEN. Metric và event thường được gắn với tên instance để nhóm vận hành biết breaker nào đang gặp vấn đề.

Vì vậy, ID là một phần của ranh giới vận hành. Đặt cùng ID cho hai dependency độc lập có thể khiến trạng thái và thống kê của chúng bị trộn lẫn. Đặt ID riêng giúp mỗi dependency được đánh giá theo kết quả của chính nó.

Cách quản lý và cache instance cụ thể phụ thuộc implementation của Spring Cloud CircuitBreaker. Tuy nhiên, khi dùng Resilience4j, không nên coi ID chỉ là nhãn hiển thị: registry sử dụng ID để quản lý Circuit Breaker instance.

## 2. Lỗi của một dependency có thể chặn dependency khác

Giả sử Order Service gọi hai hệ thống:

- Inventory Service kiểm tra số lượng hàng.
- Payment Service xử lý thanh toán.

Hai hệ thống có độ trễ, tỷ lệ lỗi, giới hạn tải và lịch phục hồi khác nhau. Nếu cùng dùng ID **external**, các kết quả của cả hai lời gọi có thể tác động lên cùng breaker.

~~~mermaid
flowchart TD
    A[Order Service] --> B[Circuit Breaker ID: external]
    B --> C[Inventory Service]
    B --> D[Payment Service]
    D --> E[Payment gặp lỗi liên tục]
    E --> F[Breaker external chuyển OPEN]
    F --> G[Inventory cũng bị từ chối]
~~~

Trong tình huống này, Inventory có thể bị chặn dù chưa có lỗi nào từ Inventory. Order Service mất khả năng kiểm tra tồn kho chỉ vì Payment đang gặp sự cố.

Đây là hiệu ứng lan truyền do cấu hình ranh giới sai. Circuit Breaker vốn được dùng để giới hạn tác động của lỗi dependency, nhưng một ID dùng chung không phù hợp có thể biến lỗi cục bộ thành lỗi của nhiều dependency.

Cấu trúc phù hợp hơn:

~~~mermaid
flowchart TD
    A[Order Service] --> B[Circuit Breaker: inventory]
    A --> C[Circuit Breaker: payment]
    B --> D[Inventory Service]
    C --> E[Payment Service]
    E --> F[Payment breaker OPEN]
    B --> G[Inventory vẫn được đánh giá độc lập]
~~~

Khi Payment lỗi, chỉ breaker **payment** chuyển OPEN. Breaker **inventory** vẫn tiếp tục đánh giá các lời gọi tồn kho và có thể ở CLOSED.

## 3. Dùng ID riêng trong code

Ví dụ tạo hai breaker độc lập trong một service:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class OrderDependencyService {

    private final CircuitBreaker inventoryBreaker;
    private final CircuitBreaker paymentBreaker;

    private final InventoryClient inventoryClient;
    private final PaymentClient paymentClient;

    public OrderDependencyService(
            CircuitBreakerFactory<?, ?> factory,
            InventoryClient inventoryClient,
            PaymentClient paymentClient) {

        this.inventoryBreaker = factory.create("inventory");
        this.paymentBreaker = factory.create("payment");

        this.inventoryClient = inventoryClient;
        this.paymentClient = paymentClient;
    }

    public Inventory checkInventory(String sku) {
        return inventoryBreaker.run(
                () -> inventoryClient.check(sku),
                error -> Inventory.unavailable(sku)
        );
    }

    public PaymentResult charge(PaymentRequest request) {
        return paymentBreaker.run(
                () -> paymentClient.charge(request),
                error -> PaymentResult.temporarilyUnavailable()
        );
    }
}
~~~

Hai lời gọi sử dụng ID khác nhau. Lỗi của **payment** không làm thay đổi trạng thái của **inventory**. Mỗi breaker có thể có cấu hình và fallback phù hợp với nghiệp vụ tương ứng.

Các lớp InventoryClient, PaymentClient, Inventory, PaymentRequest và PaymentResult là kiểu minh họa của ứng dụng. Trong dự án thực tế, thay chúng bằng interface và model hiện có.

Không tạo breaker mới trong mỗi lần gọi bằng một ID ngẫu nhiên. ID nên ổn định để các request cùng dependency sử dụng cùng một chính sách bảo vệ và cùng metric.

## 4. Đồng bộ ID với cấu hình Resilience4j

Khi dùng Resilience4j, tên ID trong code cần khớp với tên instance trong **application.yml**.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 15
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Cấu hình cho thấy hai dependency có chính sách khác nhau:

| Thuộc tính | inventory | payment |
|---|---:|---:|
| Kiểu cửa sổ | COUNT_BASED | TIME_BASED |
| Kích thước cửa sổ | 30 lời gọi | 15 giây |
| Số mẫu tối thiểu | 10 | 20 |
| Ngưỡng lỗi | 50% | 30% |
| Ngưỡng lời gọi chậm | 1 giây | 2 giây |
| Thời gian OPEN | 10 giây | 30 giây |
| Lời gọi thăm dò HALF_OPEN | 3 | 2 |

Các con số chỉ nhằm minh họa cách tách chính sách. Hãy chọn giá trị dựa trên SLA, lưu lượng, latency và khả năng phục hồi thực tế của từng dependency.

Nếu code gọi factory.create("payment") nhưng YAML chỉ khai báo instances.billing, cấu hình billing không tự áp dụng cho ID payment. Cần thống nhất tên ID giữa nơi tạo breaker, cấu hình và dashboard.

## 5. Dùng ID riêng cho reactive Circuit Breaker

Với WebFlux và Reactor, cũng cần tách ID theo dependency. ReactiveCircuitBreakerFactory tạo breaker reactive theo ID:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderDependencyService {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;
    private final ReactiveCircuitBreaker paymentBreaker;

    public ReactiveOrderDependencyService(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.inventoryBreaker = factory.create("inventory");
        this.paymentBreaker = factory.create("payment");
    }

    public Mono<Inventory> checkInventory(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("http://inventory-service/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class);

        return inventoryBreaker.run(
                remoteCall,
                error -> Mono.just(Inventory.unavailable(sku))
        );
    }

    public Mono<PaymentResult> charge(PaymentRequest request) {
        Mono<PaymentResult> remoteCall = webClient.post()
                .uri("http://payment-service/charges")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResult.class);

        return paymentBreaker.run(
                remoteCall,
                error -> Mono.just(
                        PaymentResult.temporarilyUnavailable())
        );
    }
}
~~~

Mỗi publisher đi qua breaker của dependency tương ứng. Fallback của Inventory và Payment cũng được định nghĩa riêng để phản ánh đúng ý nghĩa nghiệp vụ.

Không dùng một ReactiveCircuitBreaker tên **remote** cho mọi publisher chỉ vì chúng đều được gọi bằng WebClient. WebClient là công cụ HTTP client; nó không quyết định hai remote service có cùng failure domain hay không.

Với Flux, nguyên tắc chọn ID vẫn như vậy. Tạo breaker riêng cho dependency hoặc nhóm thao tác có cùng chính sách, rồi truyền Flux tương ứng vào run.

## 6. Khi nào nhiều endpoint có thể dùng chung một ID?

Không phải cứ có hai URL là bắt buộc phải có hai Circuit Breaker. Ranh giới nên phản ánh failure domain và chính sách vận hành, không chỉ số lượng endpoint.

Có thể dùng chung ID khi các endpoint:

- Thuộc cùng một dependency và thường suy giảm cùng nhau.
- Có SLA, timeout và ngưỡng lỗi tương tự.
- Có cùng chính sách phân loại lỗi.
- Cần được bảo vệ như một đơn vị tải chung.
- Việc mở mạch cho toàn bộ nhóm endpoint là hành vi mong muốn.

Ví dụ, **/inventory/{sku}** và **/inventory/{sku}/availability** có thể dùng chung breaker **inventory** nếu chúng cùng phụ thuộc vào một Inventory Service và cùng chịu một failure domain.

Nên tách ID khi:

- Endpoint gọi các backend độc lập.
- Một thao tác chậm nhưng thao tác còn lại vẫn hoạt động tốt.
- SLA hoặc deadline khác nhau rõ rệt.
- Một thao tác có lưu lượng lớn và có thể lấn át thống kê của thao tác khác.
- Cách phân loại exception hoặc chính sách fallback khác nhau.
- Cần mở mạch một luồng mà vẫn cho phép luồng khác tiếp tục.

Ví dụ, một hệ thống Customer có API đọc hồ sơ và API tạo báo cáo. Nếu API báo cáo chạy truy vấn dài, lỗi hoặc độ trễ của nó có thể không đại diện cho API đọc hồ sơ. Có thể dùng **customer-profile** và **customer-report** để tách hai ranh giới.

| Tình huống | Cách chọn ID |
|---|---|
| Nhiều endpoint của cùng một backend, cùng SLA và failure domain | Có thể dùng chung một ID |
| Hai backend độc lập như Inventory và Payment | Dùng hai ID riêng |
| Một backend có luồng đọc nhanh và luồng báo cáo dài, chính sách khác nhau | Cân nhắc tách theo operation |
| Cùng backend nhưng một API có traffic vượt trội và cần bảo vệ riêng | Cân nhắc ID riêng |
| Mỗi tenant hoặc request tạo một ID động | Tránh; thường tạo cardinality và trạng thái quá lớn |

## 7. Tránh ID động và cardinality cao

ID cần ổn định và có số lượng hữu hạn. Không dùng user ID, request ID, order ID hoặc tenant ID làm Circuit Breaker ID nếu mỗi giá trị tạo ra một instance riêng.

Ví dụ không nên làm:

~~~java
String breakerId = "inventory-" + tenantId;
CircuitBreaker breaker = factory.create(breakerId);
~~~

Nếu hệ thống có hàng chục nghìn tenant, cách này có thể tạo hàng chục nghìn breaker instance. Mỗi instance có state, cấu hình, cửa sổ thống kê và metric riêng. Hậu quả có thể gồm:

- Tăng bộ nhớ và số lượng đối tượng trong registry.
- Tăng số time series trong hệ thống metric.
- Mỗi breaker có quá ít request để đủ minimumNumberOfCalls.
- Trạng thái của từng instance khó quan sát và quản lý.
- Khó thay đổi hoặc dọn dẹp instance động.

Nếu cần giới hạn theo tenant, hãy dùng Rate Limiter hoặc quota mechanism phù hợp với tenant, đồng thời giữ Circuit Breaker ở ranh giới dependency có số lượng hữu hạn. Nếu có một nhóm backend theo vùng hoặc cluster, có thể dùng ID theo nhóm backend khi chúng thực sự chia sẻ failure domain.

Tên ID nên dễ đọc và ổn định, ví dụ:

- inventory
- payment
- customer-profile
- customer-report
- shipping-provider-a

Không nên đưa hostname động, URL đầy đủ hoặc dữ liệu người dùng vào ID.

## 8. ID và cấu hình dùng chung không có nghĩa là dùng chung trạng thái

Resilience4j cho phép định nghĩa nhóm cấu hình chung trong **configs** và để nhiều instance tham chiếu qua **baseConfig**. Tái sử dụng cấu hình không đồng nghĩa với việc các instance phải dùng chung ID.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      standard:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s

    instances:
      inventory:
        baseConfig: standard

      customer:
        baseConfig: standard

      payment:
        baseConfig: standard
        failureRateThreshold: 30
~~~

**inventory** và **customer** kế thừa cùng cấu hình **standard**, nhưng vẫn là hai instance riêng với ID và trạng thái riêng. Payment cũng kế thừa cấu hình chung rồi ghi đè ngưỡng lỗi của chính nó.

Đây là cách tổ chức phù hợp khi muốn chuẩn hóa chính sách mà vẫn giữ ranh giới độc lập. Không cần sao chép toàn bộ thuộc tính cho từng instance, cũng không cần dùng một ID chung để tái sử dụng cấu hình.

Nếu một nhóm dependency thật sự cần cùng trạng thái Circuit Breaker, hãy xác định rõ đó là một failure domain chung và có chủ đích. Đừng dùng chung ID chỉ để giảm số dòng YAML.

## 9. Trạng thái Circuit Breaker thường là cục bộ trong từng ứng dụng

Một điểm quan trọng khác: cùng một ID ở hai process hoặc hai pod không mặc nhiên tạo ra một Circuit Breaker phân tán dùng chung trạng thái.

Với cách triển khai Resilience4j thông thường, registry và trạng thái breaker được quản lý trong bộ nhớ của từng instance ứng dụng. Ví dụ, hai pod Order Service cùng tạo ID **inventory** sẽ có breaker **inventory** riêng trong từng pod. Một pod có thể đang OPEN trong khi pod còn lại vẫn CLOSED, tùy kết quả lời gọi mà từng pod quan sát được.

~~~mermaid
flowchart TD
    A[Order Service] --> B[Pod 1]
    A --> C[Pod 2]
    B --> D[Breaker inventory: OPEN]
    C --> E[Breaker inventory: CLOSED]
    D --> F[Pod 1 từ chối lời gọi]
    E --> G[Pod 2 vẫn gọi Inventory]
~~~

Điều này không phải lý do để đặt ID khác nhau tùy pod. Các pod của cùng một service nên dùng cùng quy ước ID để cấu hình và metric nhất quán. Nhưng không nên hiểu ID giống nhau là một cơ chế đồng bộ trạng thái giữa các pod.

Nếu nghiệp vụ cần một quyết định bảo vệ phân tán hoặc quota dùng chung toàn cluster, cần một cơ chế phối hợp riêng. Circuit Breaker cục bộ chủ yếu bảo vệ tài nguyên và luồng gọi trong từng process.

## 10. Theo dõi metric theo ID

Metric của Circuit Breaker thường gắn với tên instance. Khi mỗi dependency có ID riêng, dashboard có thể phân biệt:

- Trạng thái hiện tại của từng breaker.
- Số lời gọi thành công, thất bại và bị từ chối.
- Failure rate và slow call rate.
- Số lần chuyển CLOSED, OPEN và HALF_OPEN.
- Tỷ lệ fallback theo dependency.

Nếu nhiều dependency dùng chung ID, metric không còn chỉ ra được dependency nào tạo ra lỗi. Ví dụ, dashboard chỉ hiển thị **remote-service** có failure rate 60%; nhóm vận hành không biết lỗi đến từ Payment hay Inventory nếu cả hai đã ghi vào cùng breaker.

Tên ID nên được dùng nhất quán trong log, metric và cấu hình. Không dùng ID động có cardinality cao làm nhãn. Có thể kết hợp ID với route hoặc operation ở log/tracing, nhưng cần giữ tập nhãn metric có giới hạn.

## 11. Kiểm thử tính độc lập giữa các ID

Một kiểm thử hữu ích là làm cho một dependency lỗi đủ lâu để breaker của nó mở, sau đó xác nhận dependency khác vẫn hoạt động.

Kịch bản minh họa:

1. Tạo hai breaker **inventory** và **payment**.
2. Cấu hình ngưỡng đủ nhỏ trong môi trường kiểm thử để dễ quan sát chuyển trạng thái.
3. Làm Payment Service trả lỗi liên tục.
4. Gọi Payment qua breaker **payment** cho đến khi mạch OPEN.
5. Xác nhận lời gọi Payment tiếp theo bị từ chối mà không gọi HTTP đến Payment.
6. Gọi Inventory qua breaker **inventory**.
7. Xác nhận Inventory vẫn được phép gọi và breaker của nó vẫn CLOSED nếu lời gọi thành công.
8. Kiểm tra metric và event có tên instance riêng.
9. Chờ thời gian OPEN và kiểm tra quá trình HALF_OPEN của Payment độc lập với Inventory.

Bảng kết quả mong đợi:

| Kiểm tra | Breaker payment | Breaker inventory |
|---|---|---|
| Dependency bị làm lỗi | Có | Không |
| Failure rate tăng | Có | Không |
| Chuyển OPEN | Có thể | Không |
| Lời gọi mới bị từ chối | Có | Không, nếu Inventory khỏe |
| Metric tách biệt | Có | Có |

Nếu cả hai breaker cùng chuyển OPEN sau khi chỉ Payment lỗi, hãy kiểm tra xem code có vô tình dùng cùng ID, dùng chung một đối tượng breaker hoặc bọc cả hai lời gọi trong cùng một breaker bên ngoài hay không.

## 12. Các lỗi thiết kế thường gặp

- **Dùng ID remote cho tất cả dependency**: state và metric có thể bị trộn lẫn, làm lỗi của một hệ thống chặn hệ thống khác.
- **Dùng cùng ID nhưng cấu hình khác nhau theo từng lời gọi**: cùng một registry instance không thể đồng thời đại diện cho hai chính sách độc lập.
- **Dùng ID theo từng request**: tạo quá nhiều instance và metric cardinality cao.
- **Tách ID chỉ vì có nhiều URL**: có thể tạo quá nhiều breaker dù các endpoint cùng failure domain và chính sách.
- **Gộp ID cho các thao tác có SLA khác nhau**: lỗi hoặc latency của thao tác này có thể ảnh hưởng thao tác khác.
- **Dùng chung fallback không phù hợp**: một dependency có thể cần cache, dependency khác cần trả lỗi tạm thời.
- **Không đồng bộ ID giữa code và YAML**: cấu hình mong muốn không được áp dụng cho instance được tạo.
- **Nhầm configs với instances**: cùng baseConfig chỉ tái sử dụng giá trị cấu hình, không làm các instance dùng chung state.
- **Cho rằng cùng ID giữa các pod chia sẻ state**: registry cục bộ không tự đồng bộ trạng thái giữa process.
- **Không kiểm thử cô lập lỗi**: chỉ kiểm tra từng lời gọi thành công không phát hiện lỗi ranh giới.

## 13. Quy trình chọn ID theo failure domain

Khi thiết kế Circuit Breaker ID cho Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự:

1. Liệt kê các dependency mà service gọi đến.
2. Xác định failure domain: hệ thống nào có thể suy giảm độc lập với hệ thống nào.
3. So sánh SLA, latency, lưu lượng, timeout và cách phân loại lỗi của từng dependency.
4. Dùng ID riêng khi các dependency có khả năng lỗi hoặc chính sách bảo vệ độc lập.
5. Chỉ dùng chung ID cho các endpoint thực sự cần cùng một trạng thái bảo vệ.
6. Giữ ID ổn định, có số lượng hữu hạn và dễ liên kết với tên dependency.
7. Đồng bộ ID giữa factory.create, cấu hình Resilience4j và dashboard.
8. Dùng baseConfig để tái sử dụng thuộc tính chung mà vẫn giữ instance riêng.
9. Kiểm thử khi một dependency lỗi để xác nhận breaker của dependency khác không bị ảnh hưởng.
10. Theo dõi state, failure rate, fallback và metric riêng theo từng ID.

ID của Circuit Breaker biểu diễn ranh giới bảo vệ. Khi hai dependency độc lập dùng cùng ID, lỗi và trạng thái của chúng có thể bị trộn lẫn, làm mất khả năng cô lập sự cố. Đặt ID riêng theo failure domain giúp mỗi dependency có state, cấu hình và metric phù hợp. Với các dependency có cùng đặc tính, có thể tái sử dụng cấu hình qua **baseConfig** nhưng vẫn giữ instance độc lập. Chọn ID ổn định, giới hạn cardinality và kiểm thử tình huống một dependency lỗi là cách bảo đảm ranh giới Circuit Breaker phản ánh đúng kiến trúc hệ thống.
