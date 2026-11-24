# Cô lập hai phụ thuộc bằng Bulkhead và ID ngắt mạch riêng

## Mục tiêu thực hành

Một service tổng hợp dữ liệu sản phẩm thường gọi nhiều dependency trong cùng một request. Ví dụ, trang chi tiết sản phẩm cần lấy số lượng tồn kho từ `inventory-service` và giá bán từ `pricing-service`. Hai hệ thống này có năng lực, latency và failure domain khác nhau. Nếu một dependency chậm, nó không nên chiếm hết tài nguyên khiến lời gọi đến dependency còn lại cũng không thể phục vụ.

Trong bài thực hành này, ta cấu hình hai lớp bảo vệ độc lập cho từng dependency:

- **Circuit Breaker ID riêng:** `inventory` theo dõi lỗi và trạng thái của inventory; `pricing` theo dõi pricing. Một dependency mở mạch không làm dependency kia bị từ chối.
- **Bulkhead riêng:** mỗi dependency có giới hạn worker và hàng đợi riêng. Tải tăng ở inventory không sử dụng hết pool dành cho pricing.
- **Fallback riêng:** khi một dependency không khả dụng, service trả trạng thái suy giảm đúng ngữ nghĩa cho phần dữ liệu đó. Phần còn lại vẫn có thể thành công.

Ta sử dụng Spring Cloud Circuit Breaker với Resilience4j trong một service đồng bộ. Ví dụ dùng `ThreadPoolBulkhead` để cô lập các lời gọi blocking. Với ứng dụng reactive, cách chọn Bulkhead và cách thực thi publisher sẽ khác; không đưa lời gọi blocking trực tiếp lên event-loop.

## Mô hình cần bảo vệ

Luồng nghiệp vụ có thể hình dung như sau:

```text
                  Product Summary API
                          |
                 ProductSummaryService
                    /           \
                   /             \
          ID: inventory        ID: pricing
          Bulkhead riêng       Bulkhead riêng
          Circuit Breaker      Circuit Breaker
                |                    |
                v                    v
        inventory-service      pricing-service
```

Hai nhánh được gọi độc lập. Nếu inventory chậm, các lời gọi inventory có thể xếp hàng trong queue riêng rồi bị từ chối khi pool đầy. Pricing vẫn dùng pool và breaker của nó. Khi Circuit Breaker inventory chuyển sang `OPEN`, lời gọi inventory mới được chuyển đến fallback của inventory; breaker pricing vẫn hoạt động theo kết quả riêng.

Điểm quan trọng là ID phải đại diện cho failure domain. Nếu cả hai lời gọi cùng dùng ID `remote-service`, trạng thái và thống kê có thể bị trộn. Sáu timeout ở inventory có thể làm breaker chung mở và chặn cả pricing dù pricing đang khỏe.

## 1. Khai báo dependency

Với Maven, thêm starter Spring Cloud Circuit Breaker Resilience4j:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
```

Starter này tích hợp abstraction `CircuitBreakerFactory` của Spring Cloud với Resilience4j. Quản lý phiên bản bằng Spring Cloud BOM tương thích với Spring Boot của dự án. Bulkhead support của Resilience4j cần module Bulkhead có trên runtime classpath; kiểm tra dependency graph để xác nhận starter/provider đang dùng đã đưa module cần thiết vào.

Ví dụ này dùng lời gọi blocking qua `RestTemplate`. Nếu dự án đã dùng `RestClient` của Spring Framework 6.1 trở lên, có thể thay client mà vẫn giữ nguyên ranh giới Circuit Breaker. Cần cấu hình connect timeout và response/read timeout ở HTTP client; Bulkhead không tự đặt thời hạn cho một request mạng.

## 2. Cấu hình breaker và Bulkhead theo từng dependency

Đặt hai instance riêng trong `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2

      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 40
        waitDurationInOpenState: 25s
        permittedNumberOfCallsInHalfOpenState: 1

  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 16
        keepAliveDuration: 20ms

      pricing:
        coreThreadPoolSize: 2
        maxThreadPoolSize: 4
        queueCapacity: 8
        keepAliveDuration: 20ms
```

Hai nhóm cấu hình dùng cùng ID `inventory` và `pricing`, nhưng mỗi nhóm có trách nhiệm riêng:

| Dependency | Circuit Breaker | ThreadPoolBulkhead |
| --- | --- | --- |
| Inventory | Cửa sổ 20 kết quả, tối thiểu 10 mẫu, ngưỡng lỗi 50%, mở 15 giây, 2 probe ở `HALF_OPEN`. | 4 worker cơ sở, tối đa 8 worker, queue 16 tác vụ. |
| Pricing | Cửa sổ 10 kết quả, tối thiểu 5 mẫu, ngưỡng lỗi 40%, mở 25 giây, 1 probe ở `HALF_OPEN`. | 2 worker cơ sở, tối đa 4 worker, queue 8 tác vụ. |

Các con số chỉ là cấu hình thực hành. Khi triển khai thật, chọn chúng dựa trên latency mục tiêu, lưu lượng, giới hạn connection, năng lực xử lý và SLA của từng dependency.

### ThreadPoolBulkhead giới hạn điều gì?

`coreThreadPoolSize` là số worker cơ sở; `maxThreadPoolSize` là giới hạn worker tối đa; `queueCapacity` là số tác vụ được phép chờ. Khi worker và hàng đợi đều đầy, tác vụ mới bị từ chối. Với cấu hình inventory ở trên, pool có thể chạy tối đa 8 tác vụ đồng thời và giữ tối đa 16 tác vụ chờ. Pricing có pool và queue riêng nên không bị inventory chiếm chỗ.

Spring Cloud Circuit Breaker Resilience4j hỗ trợ Bulkhead khi module tương ứng có mặt. Provider thường dùng `FixedThreadPoolBulkhead` làm mặc định. Nếu muốn chuyển sang `SemaphoreBulkhead`, cấu hình `spring.cloud.circuitbreaker.resilience4j.enableSemaphoreDefaultBulkhead=true` theo phiên bản đang dùng và khai báo `resilience4j.bulkhead.instances`. Semaphore giới hạn số lời gọi đồng thời nhưng không chuyển công việc blocking sang thread pool riêng. Với lời gọi blocking, cần hiểu rõ khác biệt này trước khi chọn.

Không cấu hình cả ThreadPoolBulkhead tự động và một Bulkhead thủ công thứ hai cho cùng một lời gọi nếu chưa có mục tiêu rõ ràng. Hai lớp giới hạn chồng nhau có thể làm số tác vụ được chấp nhận thấp hơn dự kiến và khiến việc chẩn đoán lỗi từ chối khó hơn. Chọn một nơi sở hữu chính sách Bulkhead cho mỗi dependency.

## 3. Tạo client cho hai dependency

Khai báo client riêng giúp ranh giới gọi mạng dễ đọc và dễ kiểm thử:

```java
public interface InventoryClient {
    InventoryResponse find(String sku);
}

public interface PricingClient {
    PricingResponse quote(String sku);
}
```

Một implementation có thể dùng `RestTemplate`:

```java
@Component
public class HttpInventoryClient implements InventoryClient {
    private final RestTemplate restTemplate;

    public HttpInventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    @Override
    public InventoryResponse find(String sku) {
        return restTemplate.getForObject(
            "http://inventory-service/items/{sku}",
            InventoryResponse.class,
            sku
        );
    }
}
```

Pricing có implementation tương tự nhưng gọi `pricing-service`. Trong production, base URL nên đến từ cấu hình hoặc service discovery; ví dụ dùng URL minh họa để làm rõ dependency đích.

## 4. Dùng ID riêng khi tạo Circuit Breaker

Inject `CircuitBreakerFactory` vào service tổng hợp. Mỗi supplier chỉ chứa lời gọi đến dependency tương ứng:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ProductSummaryService {
    private final InventoryClient inventoryClient;
    private final PricingClient pricingClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductSummaryService(
            InventoryClient inventoryClient,
            PricingClient pricingClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryClient = inventoryClient;
        this.pricingClient = pricingClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductSummary load(String sku) {
        InventoryView inventory = circuitBreakerFactory
            .create("inventory")
            .run(
                () -> InventoryView.current(inventoryClient.find(sku)),
                error -> InventoryView.unavailable()
            );

        PricingView pricing = circuitBreakerFactory
            .create("pricing")
            .run(
                () -> PricingView.current(pricingClient.quote(sku)),
                error -> PricingView.unavailable()
            );

        return new ProductSummary(sku, inventory, pricing);
    }
}
```

`create("inventory")` chọn breaker và Bulkhead instance inventory; `create("pricing")` chọn instance pricing. Cùng một request nghiệp vụ có thể nhận dữ liệu tồn kho hiện tại và trạng thái giá tạm thời không khả dụng, hoặc ngược lại. `ProductSummary` cần thể hiện rõ trạng thái từng phần để client không nhầm dữ liệu dự phòng với dữ liệu hiện tại.

Các kiểu `InventoryResponse`, `PricingResponse`, `InventoryView`, `PricingView` và `ProductSummary` là kiểu domain của ứng dụng. Có thể dùng enum trạng thái như `CURRENT`, `UNAVAILABLE` hoặc `UNKNOWN` thay vì gán số lượng bằng 0 hay giá bằng 0 khi không lấy được dữ liệu. Giá trị mặc định sai ngữ nghĩa có thể dẫn đến quyết định mua hàng hoặc thanh toán không chính xác.

## 5. Vì sao hai ID phải độc lập?

Hãy xem xét hai tình huống:

**Tình huống A — inventory lỗi, pricing khỏe:** inventory timeout liên tục và breaker `inventory` chuyển sang `OPEN`. Lời gọi mới đến inventory được từ chối và fallback inventory trả trạng thái unavailable. Breaker `pricing` vẫn `CLOSED`, vì vậy giá vẫn có thể được lấy bình thường.

**Tình huống B — pricing quá tải:** pool pricing đã dùng hết worker và queue. Các lời gọi pricing mới bị từ chối do Bulkhead đầy. Inventory vẫn có pool riêng và tiếp tục phục vụ. Khi pricing phục hồi, các tác vụ chờ được xử lý hoặc lời gọi mới được nhận theo capacity của pricing.

Nếu dùng chung ID và chung pool, lỗi hoặc tải tăng ở một dependency có thể tác động đến dependency còn lại. Tách ID Circuit Breaker và Bulkhead giúp cô lập cả trạng thái lỗi lẫn tài nguyên thực thi.

## 6. Phân biệt lỗi Bulkhead với lỗi Circuit Breaker

Hai loại từ chối thường gặp có ý nghĩa khác nhau:

| Lỗi | Ý nghĩa | Cần điều tra |
| --- | --- | --- |
| `BulkheadFullException` | Pool hoặc hàng đợi của dependency đã hết chỗ nhận tác vụ. | Worker, queue capacity, thời gian giữ worker, latency và lưu lượng. |
| `CallNotPermittedException` | Circuit Breaker đang `OPEN` và từ chối lời gọi mới. | Failure rate, slow-call rate, sliding window và thời gian mở. |

Không mặc định xem `BulkheadFullException` là bằng chứng dependency từ xa thất bại. Tác vụ có thể bị từ chối trước khi được gửi đến server vì ứng dụng gọi đã hết capacity. Nếu cấu hình predicate Circuit Breaker ghi nhận lỗi từ chối Bulkhead như lỗi dependency, breaker có thể mở do quá tải cục bộ. Hãy xác nhận thứ tự decorator và hành vi của provider đang dùng; theo dõi lỗi Bulkhead và lỗi Circuit Breaker bằng metric riêng.

Nếu provider có cấu hình tự động Bulkhead, kiểm tra đúng ID và loại Bulkhead được factory sử dụng. Không giả định cấu hình `resilience4j.bulkhead` đang điều khiển ThreadPoolBulkhead; SemaphoreBulkhead và ThreadPoolBulkhead có namespace cấu hình riêng.

## 7. Fallback độc lập và không tạo lỗi dây chuyền

Mỗi dependency cần fallback có ngữ nghĩa riêng. Inventory có thể trả `InventoryView.unavailable()`; pricing có thể trả `PricingView.unavailable()`. Không dùng một fallback chung tạo đối tượng giả hợp lệ cho cả hai.

Fallback nên nhanh và ít phụ thuộc. Nếu fallback inventory lại gọi pricing hoặc một dịch vụ khác đang quá tải, nó có thể tạo thêm một chuỗi lỗi. Nếu dùng cache, phải kiểm tra độ mới và đánh dấu rõ dữ liệu stale. Với dữ liệu quan trọng như giá giao dịch, không dùng cache quá hạn như giá xác nhận cuối cùng.

Trong ví dụ `run`, fallback được gọi khi supplier lỗi hoặc Circuit Breaker từ chối lời gọi theo hợp đồng của provider. Hãy kiểm tra thêm cách Bulkhead từ chối được chuyển đến fallback trong phiên bản đang dùng. Nếu muốn trả response riêng cho quá tải cục bộ, có thể xử lý `BulkheadFullException` ở lớp API hoặc dùng fallback tương ứng; tránh che nguyên nhân bằng một kết quả thành công giả.

## 8. Timeout cho từng dependency

Bulkhead giới hạn concurrency và queue, nhưng không kết thúc một HTTP request đang bị treo. Mỗi client cần timeout phù hợp với SLA của dependency:

- Inventory có thể dùng connect timeout 300 ms và response timeout 1,5 giây.
- Pricing có thể dùng connect timeout 300 ms và response timeout 1 giây nếu yêu cầu nghiệp vụ cần phản hồi nhanh hơn.

Các giá trị trên chỉ là ví dụ. Hãy cấu hình ở HTTP client đang sử dụng và đặt deadline tổng cho request nghiệp vụ. Với lời gọi blocking, không giả định `TimeLimiter` luôn có thể ngắt một supplier đồng bộ đang block. Việc interrupt thread không bảo đảm thư viện mạng hoặc server đã dừng xử lý request.

Khi một worker bị giữ quá lâu, pool của dependency đó có thể đầy dù server chỉ chậm tạm thời. Timeout hợp lý giúp giải phóng worker sớm hơn. Với thao tác ghi, timeout không chứng minh server chưa thực hiện thao tác; cần idempotency key hoặc cơ chế chống xử lý trùng trước khi retry.

## 9. Tính capacity theo số replica

ThreadPoolBulkhead được tạo trong từng tiến trình. Nếu một instance có tối đa 8 worker inventory và ứng dụng chạy 5 replica, tổng số worker inventory có thể lên tới 40. Pricing có tối đa 4 worker trên mỗi replica, tương đương 20 worker trên 5 replica.

| Dependency | Max worker mỗi replica | Queue mỗi replica | Với 5 replica: worker tối đa | Với 5 replica: queue tối đa |
| --- | ---: | ---: | ---: | ---: |
| Inventory | 8 | 16 | 40 | 80 |
| Pricing | 4 | 8 | 20 | 40 |

Đây là giới hạn lý thuyết từ service này; các ứng dụng khác và caller khác cũng tiêu thụ capacity của backend. Hãy phối hợp giới hạn per-instance với quota toàn hệ thống, connection pool và năng lực dependency. Queue lớn không làm backend khỏe hơn; nó chỉ giữ nhiều tác vụ chờ và có thể làm latency vượt deadline.

## 10. Kiểm thử cô lập hai dependency

Tạo hai server giả lập hoặc mock client có thể điều khiển độc lập. Một test nên xác nhận inventory lỗi không làm pricing bị chặn:

1. Cấu hình inventory giả lập trả timeout hoặc 503 đủ số lần để breaker inventory mở.
2. Gọi `ProductSummaryService.load(sku)`.
3. Xác nhận inventory trả trạng thái fallback.
4. Xác nhận pricing vẫn được gọi và trả giá hiện tại.
5. Kiểm tra breaker `inventory` ở `OPEN` và breaker `pricing` vẫn cho phép lời gọi.

Một test khác kiểm tra Bulkhead riêng:

1. Giữ các lời gọi inventory trong supplier bằng latch để chiếm worker và lấp queue inventory.
2. Gửi thêm lời gọi inventory và xác nhận bị từ chối khi pool cùng queue đã đầy.
3. Trong lúc inventory đang đầy, gọi pricing và xác nhận pricing vẫn được thực thi trên pool riêng.
4. Nhả latch, xác nhận worker và queue inventory được giải phóng.
5. Gửi lời gọi inventory mới và xác nhận pool tiếp tục nhận việc.

Khi test đồng thời, dùng `CountDownLatch` hoặc `CyclicBarrier` để biết chính xác supplier đã bắt đầu. Tránh dùng `Thread.sleep()` làm điều kiện đồng bộ vì thứ tự thread phụ thuộc scheduler của hệ điều hành. Luôn nhả latch và shutdown tài nguyên trong `finally` để test thất bại không để lại thread treo.

### Các kết quả cần quan sát

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Inventory lỗi liên tục | Chỉ breaker `inventory` chuyển `OPEN`. |
| Pricing vẫn khỏe | Breaker `pricing` tiếp tục cho phép gọi. |
| Pool inventory đầy | Lời gọi inventory mới bị từ chối; pricing không bị ảnh hưởng. |
| Pool pricing đầy | Lời gọi pricing mới bị từ chối; inventory không bị ảnh hưởng. |
| Supplier hoàn tất | Worker được trả lại và queue tiếp tục xử lý. |
| Circuit Breaker `HALF_OPEN` | Số probe không vượt `permittedNumberOfCallsInHalfOpenState` của ID tương ứng. |
| Fallback được gọi | Kết quả thể hiện đúng dependency nào đang unavailable hoặc quá tải. |

## 11. Metrics và log cần tách theo dependency

Theo dõi metrics theo breaker ID và Bulkhead ID để xác định đúng nơi xảy ra vấn đề:

- Trạng thái Circuit Breaker: `CLOSED`, `OPEN`, `HALF_OPEN`.
- Failure rate, slow-call rate, số lời gọi thành công/thất bại và số lời gọi bị từ chối.
- ThreadPoolBulkhead: số worker đang hoạt động, số task trong queue, số task bị từ chối.
- Latency và timeout của từng HTTP client.
- Số lần fallback và trạng thái kết quả fallback.

Dùng tag có giới hạn như `dependency=inventory` hoặc `dependency=pricing`. Không đưa SKU, user ID, request ID hoặc exception message vào metric tag vì cardinality sẽ tăng nhanh. Log có thể chứa correlation ID để truy vết một request cụ thể nhưng không ghi token hoặc dữ liệu nhạy cảm.

Khi dashboard báo lỗi, phân biệt các trường hợp:

- `inventory` có failure rate cao và `OPEN`: dependency inventory có thể đang suy giảm.
- `inventory` có queue đầy nhưng failure rate thấp: ứng dụng đang nhận tải vượt capacity hoặc worker giữ quá lâu; backend chưa chắc đã lỗi.
- `pricing` vẫn `CLOSED` và queue thấp: pricing đang hoạt động độc lập dù inventory gặp sự cố.
- Cả hai cùng đầy: xem xét tải tổng, connection pool, CPU và các dependency dùng chung ở tầng dưới.

## 12. Những lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng chung một Circuit Breaker ID cho inventory và pricing | Lỗi một dependency có thể mở breaker của dependency kia. | Tách ID theo failure domain. |
| Dùng chung Bulkhead cho hai dependency | Tải inventory có thể chiếm hết worker và queue của pricing. | Cấu hình Bulkhead riêng theo ID. |
| Cấu hình SemaphoreBulkhead nhưng nghĩ đang có thread isolation | Lời gọi blocking vẫn chạy trên thread caller. | Dùng ThreadPoolBulkhead khi cần pool riêng, hoặc hiểu rõ giới hạn của semaphore. |
| Queue quá lớn | Request chờ lâu, heap tăng và dễ hết deadline. | Đặt queue hữu hạn theo latency mục tiêu. |
| Không đặt HTTP timeout | Worker bị giữ lâu và pool nhanh chóng đầy. | Cấu hình connect/read timeout ở client. |
| Ghi nhận Bulkhead rejection như lỗi dependency | Circuit Breaker có thể mở do quá tải cục bộ. | Phân loại `BulkheadFullException` riêng và kiểm tra decorator order. |
| Fallback trả dữ liệu mặc định gây hiểu nhầm | Caller có thể coi dữ liệu chưa biết là giá trị thật. | Dùng trạng thái unavailable/unknown rõ nghĩa. |
| Chỉ tính capacity trên một replica | Tổng concurrency toàn cụm vượt sức chịu tải backend. | Nhân giới hạn theo số replica và caller khác. |

## Bài tập hoàn thiện

Hãy triển khai hai dependency `inventory` và `pricing` trong cùng service, với ID Circuit Breaker và Bulkhead riêng. Sau đó chứng minh bằng kiểm thử rằng:

- Inventory mở mạch không làm pricing mở mạch.
- Queue inventory đầy không làm lời gọi pricing bị từ chối.
- Queue pricing đầy không làm lời gọi inventory bị từ chối.
- Fallback của mỗi dependency trả trạng thái đúng ngữ nghĩa.
- Timeout giải phóng worker trong thời hạn dự kiến.
- Metrics phân biệt được lỗi dependency, breaker open và bulkhead full.

Nếu dự án chọn SemaphoreBulkhead thay vì ThreadPoolBulkhead, ghi rõ lý do và xác nhận lời gọi blocking vẫn tiêu thụ thread caller. Nếu dự án dùng reactive WebClient, giữ pipeline reactive và chọn Bulkhead phù hợp cho publisher; không chặn event-loop để chờ permit hoặc kết quả blocking.

Khi hai dependency được gắn với ID Circuit Breaker và Bulkhead riêng, hệ thống có thể cô lập cả trạng thái lỗi lẫn tài nguyên thực thi. Điều đó giúp một dịch vụ suy giảm không kéo dịch vụ còn lại vào cùng sự cố, đồng thời làm rõ số liệu, fallback và giới hạn capacity trong vận hành Spring Cloud Circuit Breaker.
