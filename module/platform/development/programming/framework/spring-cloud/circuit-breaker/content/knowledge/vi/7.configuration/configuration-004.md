# Phân biệt nhóm cấu hình và ID bộ ngắt mạch thực tế

## Mục tiêu

Khi tích hợp Spring Cloud CircuitBreaker với Resilience4j, mỗi bộ ngắt mạch được tạo theo một ID. Factory còn có overload nhận thêm `groupName`. Hai giá trị này phục vụ hai mục đích cấu hình khác nhau. Nếu nhầm chúng với tên profile dùng chung trong YAML, ứng dụng có thể áp dụng sai timeout, dùng chung trạng thái ngoài ý muốn hoặc khó quan sát từng dependency.

Sau bài học, bạn có thể:

- Xác định ID nào đại diện cho Circuit Breaker thực tế trong mã ứng dụng.
- Giải thích `groupName` được dùng như thế nào khi tạo Circuit Breaker với integration Resilience4j.
- Phân biệt ID instance, group name và profile `configs` được kế thừa qua `baseConfig`.
- Thiết kế tên cho nhiều dependency có thể chia sẻ timeout nhưng vẫn cần trạng thái Circuit Breaker độc lập.
- Đối chiếu cấu hình YAML, factory, metric và kiểm thử để phát hiện ánh xạ sai.

## Ba loại tên cần phân biệt

Trong một ứng dụng có nhiều dịch vụ phụ thuộc, có thể gặp ba loại tên:

| Loại tên | Ví dụ | Vai trò |
|---|---|---|
| Circuit Breaker ID | `catalog-read`, `inventory-read` | Định danh bộ ngắt mạch cụ thể; dùng để chọn cấu hình Circuit Breaker và nhận diện trạng thái/metric của nó. |
| `groupName` truyền vào factory | `slow-remote`, `fast-remote` | Với integration Resilience4j của Spring Cloud CircuitBreaker, dùng để chọn cấu hình TimeLimiter cho lời gọi. |
| Tên profile cấu hình | `remote-default`, `payment-strict` | Profile tái sử dụng được khai báo trong `resilience4j.circuitbreaker.configs` hoặc `resilience4j.timelimiter.configs`, sau đó được instance kế thừa bằng `baseConfig`. |

Ba loại tên có thể trùng nhau về mặt chuỗi, nhưng ý nghĩa không giống nhau. Nên đặt tên riêng theo mục đích để người đọc dễ xác định khóa nào đang được tra cứu.

Một điểm đặc biệt quan trọng: `groupName` trong `create(id, groupName)` không phải là tên nhóm trạng thái Circuit Breaker dùng chung. Các Circuit Breaker có ID khác nhau vẫn có trạng thái riêng. Trong integration Resilience4j, tham số này được dùng để chọn cấu hình TimeLimiter. Muốn tái sử dụng một tập thuộc tính Circuit Breaker, hãy khai báo profile trong `configs` rồi cho nhiều instance dùng chung `baseConfig`.

## ID là định danh của Circuit Breaker thực tế

Với Spring Cloud CircuitBreaker, mã đồng bộ thường tạo bộ ngắt mạch qua `CircuitBreakerFactory`:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findById(String id) {
        CircuitBreaker breaker = circuitBreakerFactory.create("catalog-read");

        return breaker.run(
                () -> catalogClient.findById(id),
                error -> Product.unavailable(id));
    }
}
```

Trong ví dụ, `catalog-read` là ID của Circuit Breaker. ID này nên ổn định và mô tả dependency hoặc nhóm thao tác có cùng đặc tính lỗi. Nó không nên chứa dữ liệu biến thiên theo request như mã sản phẩm, mã người dùng hay correlation ID.

Nếu mọi request tới cùng dịch vụ danh mục đều tạo ID khác nhau, hệ thống có thể tạo ra nhiều bộ ngắt mạch và nhiều chuỗi metric thay vì tích lũy kết quả trên một bộ bảo vệ có ý nghĩa. Ngược lại, nếu dùng chung một ID cho hai dependency có đặc tính lỗi khác nhau, một dịch vụ lỗi có thể làm mạch của dịch vụ còn lại mở theo.

Hãy chọn ID theo ranh giới lỗi mà bạn muốn cô lập. Ví dụ `catalog-read` và `catalog-search` có thể là hai ID riêng nếu chúng gọi các endpoint hoặc cụm dịch vụ có khả năng lỗi độc lập. Nếu hai thao tác luôn đi qua cùng một dependency và cần cùng quyết định bảo vệ, một ID chung có thể phù hợp hơn.

## groupName trong factory của Resilience4j

Spring Cloud CircuitBreaker cung cấp overload nhận cả ID và group name:

```java
CircuitBreaker breaker = circuitBreakerFactory.create("catalog-read", "slow-remote");
```

Trong integration Resilience4j:

- `catalog-read` được dùng để xác định cấu hình và instance Circuit Breaker.
- `slow-remote` được dùng để xác định cấu hình TimeLimiter.

Điều này cho phép nhiều Circuit Breaker có trạng thái độc lập nhưng cùng dùng một thời hạn chờ. Ví dụ, `catalog-read` và `inventory-read` có thể đều dùng nhóm `slow-remote`, trong khi mỗi ID vẫn có cửa sổ thống kê, ngưỡng lỗi và trạng thái riêng.

Ví dụ reactive sử dụng cùng quy tắc ánh xạ:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public class ReactiveCatalogGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final CatalogClient catalogClient;

    public ReactiveCatalogGateway(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            CatalogClient catalogClient) {
        this.factory = factory;
        this.catalogClient = catalogClient;
    }

    public Mono<Product> findById(String id) {
        ReactiveCircuitBreaker breaker = factory.create("catalog-read", "slow-remote");

        return breaker.run(
                catalogClient.findById(id),
                error -> Mono.just(Product.unavailable(id)));
    }
}
```

`groupName` là tùy chọn theo overload của factory. Chỉ thêm tham số này khi cần chọn cấu hình TimeLimiter theo một khóa khác với ID Circuit Breaker. Cách ánh xạ cụ thể cần được xác nhận với implementation và phiên bản Spring Cloud CircuitBreaker đang sử dụng; không suy ra rằng implementation khác cũng dùng tham số này giống Resilience4j.

TimeLimiter cũng không phải cơ chế có thể dừng tùy ý mọi đoạn mã đồng bộ. Với overload chạy một `Supplier<T>` đồng bộ trực tiếp, không nên kỳ vọng `timeoutDuration` tự ngắt thao tác đang chiếm luồng. Hãy đặt timeout ở HTTP client, driver cơ sở dữ liệu hoặc thư viện gọi tương ứng. TimeLimiter phù hợp với các dạng thực thi bất đồng bộ/reactive mà integration hỗ trợ, chẳng hạn `CompletionStage` hoặc publisher; vẫn cần kiểm tra việc hủy tác vụ thực tế vì client bên dưới có thể không dừng công việc ngay khi future bị hủy.

## Profile configs và baseConfig

Resilience4j cho phép định nghĩa các profile có thể tái sử dụng trong phần `configs`. Mỗi instance khai báo trong `instances` có thể kế thừa một profile bằng `baseConfig`, rồi ghi đè những thuộc tính cần riêng.

Ví dụ, hai Circuit Breaker dùng chung chính sách thống kê cơ bản nhưng có ngưỡng lỗi khác nhau:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remote-default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 1s
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      catalog-read:
        baseConfig: remote-default
      inventory-read:
        baseConfig: remote-default
        failureRateThreshold: 40
```

`remote-default` là tên profile cấu hình, không phải ID được truyền vào factory. `catalog-read` và `inventory-read` là ID instance. Cả hai kế thừa các giá trị chung từ profile, nhưng `inventory-read` ghi đè `failureRateThreshold` thành 40%.

Có thể tạo nhiều profile cho các nhóm dependency khác nhau:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remote-default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-strict:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
    instances:
      catalog-read:
        baseConfig: remote-default
      inventory-read:
        baseConfig: remote-default
      payment-authorize:
        baseConfig: payment-strict
```

Các instance vẫn độc lập dù cùng kế thừa một profile. `baseConfig` tái sử dụng giá trị cấu hình; nó không hợp nhất trạng thái runtime, cửa sổ thống kê hoặc metric giữa các ID.

## Cấu hình TimeLimiter theo groupName

TimeLimiter có profile và instance riêng trong namespace `resilience4j.timelimiter`. Khi gọi `create(id, groupName)`, integration Resilience4j dùng ID đầu tiên cho Circuit Breaker và group name cho TimeLimiter.

```yaml
resilience4j:
  timelimiter:
    configs:
      timeout-default:
        timeoutDuration: 2s
        cancelRunningFuture: true
    instances:
      slow-remote:
        baseConfig: timeout-default
        timeoutDuration: 4s
      fast-remote:
        baseConfig: timeout-default
        timeoutDuration: 800ms
```

Trong ví dụ, mọi lời gọi dùng group `slow-remote` có thể kế thừa thời hạn bốn giây; nhóm `fast-remote` dùng 800 mili giây. Đây là cấu hình TimeLimiter. Nó không làm các Circuit Breaker có cùng group dùng chung tỷ lệ lỗi hoặc trạng thái.

Kết hợp hai phần cấu hình:

```java
CircuitBreaker catalogBreaker = factory.create("catalog-read", "slow-remote");
CircuitBreaker inventoryBreaker = factory.create("inventory-read", "slow-remote");
CircuitBreaker paymentBreaker = factory.create("payment-authorize", "fast-remote");
```

| Lời gọi factory | Cấu hình Circuit Breaker | Cấu hình TimeLimiter |
|---|---|---|
| `create("catalog-read", "slow-remote")` | `circuitbreaker.instances.catalog-read` | `timelimiter.instances.slow-remote` |
| `create("inventory-read", "slow-remote")` | `circuitbreaker.instances.inventory-read` | `timelimiter.instances.slow-remote` |
| `create("payment-authorize", "fast-remote")` | `circuitbreaker.instances.payment-authorize` | `timelimiter.instances.fast-remote` |

Bảng này mô tả cách ánh xạ ID và group name của integration Resilience4j. Hãy kiểm tra starter và phiên bản đang dùng để xác nhận overload factory tương ứng có sẵn và các thuộc tính TimeLimiter được bind như mong đợi.

## Phân biệt groupName với baseConfig qua một tình huống

Giả sử hệ thống có ba dependency:

- Catalog phản hồi chậm, cần timeout bốn giây.
- Inventory cũng phản hồi chậm, cần cùng timeout bốn giây nhưng có ngưỡng lỗi riêng.
- Payment phải phản hồi nhanh, cần timeout 800 mili giây và ngưỡng lỗi chặt hơn.

Ta có thể cấu hình như sau:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      slow-dependency:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-dependency:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
    instances:
      catalog-read:
        baseConfig: slow-dependency
      inventory-read:
        baseConfig: slow-dependency
        failureRateThreshold: 40
      payment-authorize:
        baseConfig: payment-dependency
  timelimiter:
    configs:
      timeout-default:
        timeoutDuration: 2s
    instances:
      slow-remote:
        baseConfig: timeout-default
        timeoutDuration: 4s
      fast-remote:
        baseConfig: timeout-default
        timeoutDuration: 800ms
```

Và mã gọi:

```java
CircuitBreaker catalog = factory.create("catalog-read", "slow-remote");
CircuitBreaker inventory = factory.create("inventory-read", "slow-remote");
CircuitBreaker payment = factory.create("payment-authorize", "fast-remote");
```

Kết quả thiết kế:

- Catalog và inventory dùng chung profile `slow-dependency` làm nền cho Circuit Breaker, nhưng vẫn có instance riêng. Inventory ghi đè ngưỡng lỗi.
- Catalog và inventory dùng chung group `slow-remote`, do đó dùng cùng cấu hình TimeLimiter.
- Payment dùng profile Circuit Breaker `payment-dependency` và group TimeLimiter `fast-remote`.
- Không có trạng thái Circuit Breaker nào được chia sẻ chỉ vì hai lời gọi dùng cùng `baseConfig` hoặc cùng `groupName`.

## Những điểm cần kiểm tra khi cấu hình

**Tên phải khớp:** ID trong `factory.create` cần khớp tên instance Circuit Breaker trong YAML. Group name cần khớp khóa instance TimeLimiter được integration tra cứu. Sai một ký tự có thể khiến cấu hình riêng không được áp dụng và ứng dụng rơi về cấu hình mặc định.

**Profile phải tồn tại:** `baseConfig` phải trỏ tới profile trong đúng namespace. Profile Circuit Breaker nằm dưới `resilience4j.circuitbreaker.configs`; profile TimeLimiter nằm dưới `resilience4j.timelimiter.configs`. Không dùng profile của Circuit Breaker làm `baseConfig` cho TimeLimiter.

**Không nhầm profile với instance:** `configs` là nơi định nghĩa giá trị tái sử dụng; `instances` là nơi định nghĩa cấu hình cho tên cụ thể được runtime sử dụng. Tên profile không tự tạo một Circuit Breaker.

**Hiểu phạm vi timeout:** TimeLimiter giới hạn thời gian chờ theo cách integration hỗ trợ. Nó không thay thế timeout kết nối hoặc timeout phản hồi của HTTP client trong mọi trường hợp. Cần phối hợp các thời hạn và kiểm tra việc hủy tác vụ, đặc biệt với lời gọi reactive.

**Không tạo ID theo request:** dùng ID ổn định theo dependency hoặc thao tác có cùng ranh giới lỗi. Dữ liệu request nên nằm trong log/trace, không nằm trong tên instance Circuit Breaker.

**Kiểm tra cấu hình hiệu lực:** khi có nhiều nguồn cấu hình như YAML và `Customizer`, hãy xác định nguồn nào đang có hiệu lực theo phiên bản integration. Tránh khai báo cùng một thuộc tính ở nhiều nơi với giá trị mâu thuẫn; nếu cần ghi đè, hãy kiểm tra bằng thử nghiệm hoặc quan sát runtime.

## Theo dõi ID và group trong vận hành

ID Circuit Breaker là nhãn quan trọng để phân biệt trạng thái và số liệu của từng dependency. Với Resilience4j và Micrometer, metric thường mang tag `name` tương ứng với instance Circuit Breaker. Group TimeLimiter không nên được xem là nhãn trạng thái Circuit Breaker; nó mô tả nhóm cấu hình thời hạn chờ được chọn cho lời gọi.

Khi điều tra một dependency, cần đối chiếu:

- ID Circuit Breaker xuất hiện trong metric và log.
- Profile `baseConfig` mà instance kế thừa và các thuộc tính bị ghi đè.
- Group name được truyền vào factory.
- Cấu hình TimeLimiter instance mà group name ánh xạ tới.
- Thời lượng lời gọi thực tế, timeout, lỗi được ghi nhận và kết quả fallback.

Nếu nhiều ID cùng dùng một group TimeLimiter, dashboard vẫn cần tách metric Circuit Breaker theo từng ID. Việc chúng có cùng timeout không có nghĩa chúng có cùng tỷ lệ lỗi hoặc cùng tình trạng sức khỏe.

## Thực hành kiểm chứng ánh xạ

Thực hiện trong môi trường thử nghiệm với ba endpoint giả lập có độ trễ khác nhau:

1. Tạo hai Circuit Breaker `catalog-read` và `inventory-read` cùng dùng group `slow-remote`; tạo `payment-authorize` dùng group `fast-remote`.
2. Khai báo ba instance Circuit Breaker và hai instance TimeLimiter tương ứng trong YAML; cho các instance kế thừa profile `baseConfig` phù hợp.
3. Gửi yêu cầu thành công tới cả ba dependency và quan sát metric theo từng ID.
4. Làm catalog trả lỗi liên tục để mạch `catalog-read` chuyển `OPEN`; xác nhận `inventory-read` vẫn giữ trạng thái riêng dù cùng group timeout.
5. Cho inventory phản hồi chậm hơn bốn giây và payment phản hồi chậm hơn 800 mili giây; xác nhận TimeLimiter của từng group được áp dụng theo cấu hình.
6. Thay đổi ngưỡng lỗi riêng của inventory nhưng giữ nguyên `baseConfig` và group; quan sát quyết định Circuit Breaker thay đổi mà timeout vẫn giữ nguyên.
7. Đổi group của payment sang `slow-remote` trong môi trường thử nghiệm; xác nhận timeout được chọn thay đổi trong khi ID Circuit Breaker vẫn là `payment-authorize`.

Ghi lại ID, group, profile, thời lượng phản hồi, kết quả và trạng thái cho mỗi lần thử. Nếu timeout không khớp, kiểm tra tên group, cấu hình instance TimeLimiter và phiên bản integration trước khi thay đổi ngưỡng Circuit Breaker.

## Lỗi thường gặp

- **Cho rằng groupName là ID Circuit Breaker:** trong integration Resilience4j, ID đầu tiên xác định Circuit Breaker; group name dùng để chọn cấu hình TimeLimiter.
- **Cho rằng groupName chia sẻ trạng thái:** các ID Circuit Breaker khác nhau vẫn có trạng thái và số liệu riêng.
- **Dùng tên profile làm ID runtime:** profile trong `configs` chỉ cung cấp giá trị nền; phải có instance được tạo với ID phù hợp.
- **Nhầm `baseConfig` với groupName:** `baseConfig` là cơ chế kế thừa cấu hình YAML; groupName là tham số khi gọi factory.
- **Đặt cùng một ID cho dependency độc lập:** sự cố của một dependency có thể ảnh hưởng quyết định của bộ ngắt mạch dùng chung.
- **Tạo ID động theo request:** tạo nhiều instance và làm metric phân mảnh.
- **Đặt sai namespace:** profile Circuit Breaker và TimeLimiter phải nằm trong phần cấu hình tương ứng.
- **Giả định mọi implementation dùng groupName giống nhau:** cách ánh xạ được mô tả ở đây áp dụng cho integration Resilience4j; hãy xác minh implementation khác trước khi chuyển đổi.

Hãy dùng ID để định danh từng Circuit Breaker cần quan sát và cô lập trạng thái. Dùng `groupName` của integration Resilience4j khi muốn chọn cấu hình TimeLimiter theo một nhóm lời gọi. Dùng `configs` và `baseConfig` để tái sử dụng các thuộc tính trong YAML. Ba cơ chế này phối hợp với nhau nhưng không thay thế lẫn nhau.
