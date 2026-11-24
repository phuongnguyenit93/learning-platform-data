# Đặt tên instance và liên kết với cấu hình YAML

Trong Resilience4j, mỗi Circuit Breaker được định danh bằng một tên instance. Tên này giúp ứng dụng phân biệt các dependency như Inventory, Payment hoặc Shipping, đồng thời liên kết lời gọi được bảo vệ với cấu hình tương ứng trong application.yml.

Khi dùng annotation AOP, tên trong thuộc tính name của @CircuitBreaker là khóa để Resilience4j tìm instance trong registry. Ví dụ, @CircuitBreaker(name = "inventory") liên kết với cấu hình resilience4j.circuitbreaker.instances.inventory. Nếu tên trong annotation và tên khóa YAML không khớp, phương thức có thể chạy với cấu hình mặc định thay vì các ngưỡng mà nhóm phát triển mong đợi.

Bài học tập trung vào cách đặt tên instance nhất quán, cách kế thừa cấu hình dùng chung, cách viết fallback và cách Spring AOP áp dụng Circuit Breaker cho phương thức. Nội dung cũng phân biệt annotation của Resilience4j với API CircuitBreakerFactory của Spring Cloud để tránh nhầm lẫn giữa hai cách tích hợp.

## 1. Tên instance là khóa liên kết

Một ứng dụng có thể gọi nhiều dependency từ cùng một service. Mỗi dependency nên có Circuit Breaker riêng để theo dõi tỷ lệ lỗi, lời gọi chậm và trạng thái độc lập.

Ví dụ:

| Dependency | Tên instance | Đường dẫn cấu hình |
| --- | --- | --- |
| Inventory | inventory | resilience4j.circuitbreaker.instances.inventory |
| Payment | payment | resilience4j.circuitbreaker.instances.payment |
| Shipping | shipping | resilience4j.circuitbreaker.instances.shipping |

Tên instance được dùng ở hai nơi:

1. Trong mã Java, tại annotation hoặc API tạo Circuit Breaker.
2. Trong application.yml, dưới khóa instances của cấu hình Circuit Breaker.

Với annotation:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Resilience4j sử dụng tên inventory để tìm cấu hình của instance tương ứng. Khóa YAML cần có cùng tên:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        failureRateThreshold: 40
        slidingWindowSize: 20
~~~

Nên dùng tên ngắn, ổn định, viết thường và thể hiện dependency hoặc thao tác được bảo vệ. Không nên dùng tên lớp Java hoặc tên phương thức làm tên instance nếu chúng không mô tả rõ dependency.

Tên inventory và Inventory không nên được xem là hai cách viết thay thế cho nhau. Hãy giữ chính xác cùng một chuỗi giữa annotation, cấu hình và dashboard.

## 2. Chuẩn bị dependency cho annotation AOP

Resilience4j có hai cách tích hợp thường gặp trong ứng dụng Spring:

- **Annotation AOP:** dùng các annotation như @CircuitBreaker, @Retry và @Bulkhead. Resilience4j tạo aspect để chặn lời gọi phương thức và áp dụng chính sách.
- **Spring Cloud CircuitBreaker API:** dùng CircuitBreakerFactory để tạo đối tượng Circuit Breaker rồi bao lời gọi bằng run hoặc execute.

Để sử dụng annotation trong Spring Boot 3, ứng dụng thường cần Actuator, Spring AOP và Resilience4j Spring Boot integration:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-aop</artifactId>
    </dependency>

    <dependency>
        <groupId>io.github.resilience4j</groupId>
        <artifactId>resilience4j-spring-boot3</artifactId>
    </dependency>
</dependencies>
~~~

Sử dụng dependency management phù hợp với phiên bản Spring Boot và Resilience4j của dự án để chọn phiên bản tương thích. Với Spring Boot 2, artifact tích hợp có tên khác; không sao chép dependency Spring Boot 3 vào dự án Spring Boot 2.

Nếu dự án dùng Spring Cloud CircuitBreaker, starter Resilience4j của Spring Cloud cung cấp API CircuitBreakerFactory. Starter đó và phần tích hợp annotation AOP của Resilience4j phục vụ hai kiểu sử dụng khác nhau. Không nên giả định rằng chỉ thêm Spring Cloud CircuitBreaker starter là mọi annotation AOP đã được kích hoạt. Khi muốn dùng @CircuitBreaker, hãy bảo đảm dependency tạo aspect Resilience4j có mặt.

## 3. Khai báo cấu hình dùng chung và instance riêng trong YAML

Resilience4j cho phép khai báo cấu hình dùng chung trong configs và cấu hình theo từng instance trong instances. Mỗi instance có thể kế thừa cấu hình cơ sở rồi ghi đè những thuộc tính cần khác biệt.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3

    instances:
      inventory:
        baseConfig: default
        failureRateThreshold: 40
        waitDurationInOpenState: 8s

      payment:
        baseConfig: default
        slidingWindowSize: 50
        minimumNumberOfCalls: 20

      shipping:
        baseConfig: default
~~~

Cấu hình trên tạo một bộ quy tắc mặc định và ba instance:

- inventory kế thừa các thuộc tính mặc định, nhưng mở mạch ở failure rate 40% và chờ 8 giây trước khi thăm dò.
- payment kế thừa cấu hình mặc định, nhưng sử dụng cửa sổ 50 lời gọi và cần tối thiểu 20 mẫu.
- shipping sử dụng toàn bộ cấu hình mặc định.

Cấu trúc có thể hình dung như sau:

~~~text
resilience4j.circuitbreaker
        |
        +-- configs
        |     |
        |     +-- default
        |
        +-- instances
              |
              +-- inventory ---> baseConfig: default
              |                    + ghi đè một số thuộc tính
              |
              +-- payment -----> baseConfig: default
              |                    + ghi đè cửa sổ
              |
              +-- shipping ----> baseConfig: default
~~~

Khi thêm một dependency mới, hãy quyết định rõ dependency đó dùng cấu hình mặc định hay cần instance riêng. Việc khai báo một khóa YAML không tự động bảo vệ mọi lời gọi HTTP đến dependency đó; mã ứng dụng vẫn phải gọi phương thức qua annotation hoặc CircuitBreakerFactory tương ứng.

## 4. Liên kết tên YAML với @CircuitBreaker

Annotation @CircuitBreaker thuộc package io.github.resilience4j.circuitbreaker.annotation. Thuộc tính name xác định tên instance mà aspect sử dụng.

Ví dụ một service gọi Inventory:

~~~java
package com.example.order.inventory;

import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(
        name = "inventory",
        fallbackMethod = "inventoryFallback"
    )
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }

    public InventoryResponse inventoryFallback(
            String sku,
            Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }
}
~~~

Tên inventory trong annotation liên kết đến:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        baseConfig: default
        failureRateThreshold: 40
~~~

Khi phương thức getInventory được gọi qua Spring proxy, aspect của Resilience4j áp dụng Circuit Breaker mang tên inventory. Nếu instance đã được cấu hình trong YAML, các thuộc tính của instance đó được dùng khi khởi tạo Circuit Breaker.

Fallback trong ví dụ có cùng kiểu trả về với phương thức gốc. Nó nhận các tham số ban đầu theo cùng thứ tự, sau đó nhận thêm exception ở tham số cuối. Dùng Throwable giúp minh họa chữ ký tổng quát; trong ứng dụng thực tế có thể dùng loại exception cụ thể để phân biệt lỗi kết nối, lỗi bị Circuit Breaker từ chối hoặc lỗi nghiệp vụ.

## 5. Quy tắc viết fallback method

Fallback là phương thức thay thế được gọi khi lời gọi được bảo vệ thất bại hoặc bị Circuit Breaker từ chối. Resilience4j tìm fallback dựa trên tên được khai báo trong annotation và chữ ký phương thức.

Với phương thức gốc:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
public InventoryResponse getInventory(String sku, boolean includeReserved) {
    return inventoryClient.getInventory(sku, includeReserved);
}
~~~

Fallback có thể khai báo:

~~~java
public InventoryResponse inventoryFallback(
        String sku,
        boolean includeReserved,
        Throwable cause) {
    return InventoryResponse.unavailable(sku);
}
~~~

Các quy tắc cần nhớ:

- Fallback có cùng kiểu trả về hoặc kiểu tương thích với phương thức gốc.
- Các tham số nghiệp vụ của phương thức gốc được giữ nguyên thứ tự.
- Tham số exception được đặt cuối cùng.
- Có thể dùng loại exception cụ thể nếu muốn fallback chỉ xử lý một nhóm lỗi.
- Nếu không khai báo fallback, exception có thể được truyền về caller.
- Nếu fallback tiếp tục ném exception, lỗi từ fallback cũng được truyền lên tầng gọi.

Không nên trả về dữ liệu giả như tồn kho bằng 0 rồi để caller hiểu đó là số liệu thật. Hãy biểu diễn rõ trạng thái UNAVAILABLE, dữ liệu cache hoặc kết quả suy giảm. Fallback cần phản ánh đúng yêu cầu nghiệp vụ.

Ví dụ fallback chuyên biệt:

~~~java
public InventoryResponse inventoryFallback(
        String sku,
        io.github.resilience4j.circuitbreaker.CallNotPermittedException cause) {
    return InventoryResponse.unavailable(sku);
}
~~~

Nếu dùng fallback chuyên biệt, cần bảo đảm loại exception đó thực sự có thể được truyền vào fallback theo phiên bản thư viện đang dùng. Nếu muốn xử lý nhiều loại lỗi trong cùng một phương thức, có thể dùng Throwable rồi phân loại bên trong.

## 6. Một tên instance có thể được dùng ở nhiều phương thức

Có thể dùng cùng một instance cho nhiều phương thức nếu các phương thức đó cùng bảo vệ một dependency và cần chia sẻ trạng thái thống kê.

~~~java
@Service
public class InventoryService {

    private final InventoryClient inventoryClient;

    public InventoryService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public InventoryResponse getBySku(String sku) {
        return inventoryClient.getBySku(sku);
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "inventoryFallback")
    public InventorySummary getSummary(String warehouseId) {
        return inventoryClient.getSummary(warehouseId);
    }

    public InventoryResponse inventoryFallback(String sku, Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }

    public InventorySummary inventoryFallback(
            String warehouseId,
            Throwable cause) {
        return InventorySummary.unavailable(warehouseId);
    }
}
~~~

Trong ví dụ, cả hai phương thức dùng cùng tên inventory. Điều này có nghĩa chúng cùng đóng góp kết quả vào một Circuit Breaker instance nếu cùng được aspect liên kết với instance đó. Một thao tác lỗi nhiều có thể ảnh hưởng trạng thái bảo vệ của thao tác còn lại.

Nếu hai endpoint có đặc tính độ trễ, lưu lượng hoặc mức độ quan trọng khác nhau, hãy cân nhắc đặt tên instance riêng, ví dụ inventory-read và inventory-summary. Khi đó YAML có thể cấu hình hai cửa sổ và ngưỡng riêng.

Không nên tạo instance riêng cho từng phương thức một cách máy móc. Nếu tất cả phương thức đều gọi cùng một dependency và cần được ngắt cùng nhau, chia sẻ một instance có thể phù hợp hơn.

## 7. Tránh lỗi do Spring AOP proxy và self-invocation

Annotation AOP hoạt động thông qua Spring proxy. Lời gọi đến bean từ bên ngoài đi qua proxy để aspect có thể áp dụng Circuit Breaker.

Một lỗi phổ biến là gọi một phương thức được gắn annotation từ phương thức khác trong cùng lớp:

~~~java
@Service
public class InventoryService {

    public InventoryResponse load(String sku) {
        return getInventory(sku);
    }

    @CircuitBreaker(name = "inventory")
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }
}
~~~

Trong ví dụ, load gọi getInventory thông qua this nội bộ của đối tượng. Lời gọi self-invocation không đi qua Spring proxy, vì vậy aspect có thể không được thực thi. Khi đó, Circuit Breaker không được áp dụng như mong đợi.

Cách rõ ràng hơn là đặt phương thức được bảo vệ trong một bean khác và gọi bean đó qua dependency injection:

~~~java
@Service
public class InventoryGateway {

    private final InventoryClient inventoryClient;

    public InventoryGateway(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "fallback")
    public InventoryResponse getInventory(String sku) {
        return inventoryClient.getInventory(sku);
    }

    public InventoryResponse fallback(String sku, Throwable cause) {
        return InventoryResponse.unavailable(sku);
    }
}
~~~

Một service khác gọi InventoryGateway qua bean được Spring quản lý. Lời gọi sẽ đi qua proxy của InventoryGateway.

Nên đặt phương thức cần áp dụng AOP ở phạm vi public và gọi qua bean proxy. Các phương thức private không thể được Spring proxy-based AOP chặn như một lời gọi bên ngoài; phương thức final cũng có giới hạn với class-based proxy. Hãy kiểm tra kiểu proxy được ứng dụng sử dụng và tránh thiết kế dựa trên lời gọi nội bộ.

## 8. Phân biệt annotation Resilience4j và Spring Cloud CircuitBreakerFactory

Hai cách tích hợp có thể dùng cùng tên instance và cùng nhóm cấu hình Resilience4j, nhưng API gọi khác nhau.

| Tiêu chí | Resilience4j annotation | Spring Cloud CircuitBreaker |
| --- | --- | --- |
| Cách gọi | Gắn @CircuitBreaker lên phương thức | Tạo đối tượng qua CircuitBreakerFactory |
| Cơ chế áp dụng | Spring AOP aspect | Bao supplier hoặc function bằng API |
| Nơi đặt tên | Thuộc tính name của annotation | Tham số create(name) |
| Fallback | fallbackMethod trong annotation | Hàm fallback truyền vào run |
| Phù hợp | Phương thức Spring bean cần khai báo chính sách bằng annotation | Muốn thể hiện rõ ranh giới bảo vệ trong code |

Ví dụ Spring Cloud CircuitBreaker API:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

Tên truyền vào create là inventory. Với Resilience4j provider, Spring Cloud CircuitBreaker liên kết tên này với cấu hình instance tương ứng trong application.yml.

Không nên bọc cùng một lời gọi bằng cả annotation và CircuitBreakerFactory nếu không có chủ đích rõ ràng. Việc lồng hai Circuit Breaker có thể tạo hai sliding window, hai trạng thái OPEN và hai fallback khác nhau, khiến chẩn đoán khó hơn. Hãy chọn một ranh giới bảo vệ rõ ràng cho mỗi dependency.

Nếu một ứng dụng sử dụng cả annotation và factory ở các phần khác nhau, hãy kiểm tra cách auto-configuration tạo registry và instance trong phiên bản đang dùng. Cùng tên cấu hình không tự chứng minh hai đường tích hợp chia sẻ cùng một vòng đời instance hoặc cùng trạng thái.

## 9. Đặt tên instance theo quy ước của nhóm

Một quy ước đặt tên tốt giúp cấu hình, dashboard và log dễ đọc. Có thể dùng tên theo dependency:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
      shipping:
        baseConfig: default
~~~

Nếu một dependency có nhiều loại thao tác cần ngưỡng khác nhau, có thể đặt tên theo dependency và mục đích:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        baseConfig: default
      inventory-reservation:
        baseConfig: default
        failureRateThreshold: 30
~~~

Trong code:

~~~java
@CircuitBreaker(name = "inventory-read")
public InventoryResponse readInventory(String sku) {
    return inventoryClient.read(sku);
}

@CircuitBreaker(name = "inventory-reservation")
public ReservationResult reserve(String sku, int quantity) {
    return inventoryClient.reserve(sku, quantity);
}
~~~

Không nên đặt tên quá dài hoặc chứa thông tin thay đổi theo request như user ID, order ID hay tenant ID. Instance là đơn vị cấu hình và thống kê ở cấp ứng dụng; tạo một instance cho từng request có thể làm tăng số lượng đối tượng và metrics không kiểm soát.

## 10. Kiểm tra cấu hình có được liên kết đúng không

Khi phương thức không mở mạch theo ngưỡng đã khai báo, hãy kiểm tra theo thứ tự:

1. Annotation có import đúng package io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker không?
2. Thuộc tính name có trùng chính xác với khóa dưới resilience4j.circuitbreaker.instances không?
3. Dependency AOP và Resilience4j Spring Boot integration đã có trên classpath chưa?
4. Phương thức có được gọi qua Spring proxy không?
5. Có đang gọi self-invocation từ cùng một bean không?
6. Cấu hình có nằm đúng dưới resilience4j.circuitbreaker không?
7. Instance có kế thừa baseConfig đúng tên không?
8. Có một cấu hình khác hoặc customizer ghi đè các giá trị mong đợi không?
9. Fallback có chữ ký và kiểu trả về phù hợp không?

Ví dụ cấu hình có tên inventory:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
~~~

Annotation phải dùng đúng tên:

~~~java
@CircuitBreaker(name = "inventory")
public InventoryResponse getInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Nếu annotation dùng name = "inventoryService" trong khi YAML chỉ có instances.inventory, cấu hình riêng inventory không được liên kết với phương thức đó. Hãy sửa tên ở nguồn khai báo phù hợp thay vì tạo thêm khóa YAML trùng lặp không cần thiết.

Có thể kiểm tra metrics và trạng thái qua Actuator nếu đã bật tích hợp Micrometer và expose endpoint cần thiết. Không nên expose toàn bộ endpoint quản trị ra mạng công khai. Tên metric cụ thể phụ thuộc phiên bản Resilience4j và Micrometer; hãy truy vấn endpoint metrics của ứng dụng thay vì giả định một tên cố định.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Phương thức vẫn gọi dependency dù đã vượt ngưỡng | Annotation không được AOP chặn hoặc gọi self-invocation | Kiểm tra proxy, dependency AOP và đường gọi qua bean |
| YAML không được áp dụng | Tên annotation khác tên instance trong YAML | Đồng bộ chính xác giá trị name và khóa instances |
| Không tìm thấy annotation | Thiếu Resilience4j Spring Boot integration hoặc import sai package | Bổ sung dependency phù hợp và dùng annotation của Resilience4j |
| Fallback không chạy | Sai tên, sai chữ ký hoặc kiểu trả về không tương thích | Kiểm tra tham số gốc và exception ở cuối chữ ký |
| Hai phương thức ảnh hưởng trạng thái của nhau | Cùng dùng một tên instance | Tách instance nếu cần chính sách độc lập |
| Dashboard có nhiều instance ngoài dự kiến | Tên được tạo động hoặc không theo quy ước | Dùng tên ổn định ở cấp dependency hoặc thao tác |
| Circuit Breaker chạy hai lần | Cùng lời gọi bị bọc bởi annotation và factory | Chọn một lớp bảo vệ rõ ràng |
| Cấu hình mới không phản ánh ngay | Instance đã được tạo trước khi cấu hình thay đổi | Xác định cơ chế reload hoặc vòng đời instance của ứng dụng |

## 12. Nguyên tắc thiết kế

- Dùng tên instance ổn định, ngắn gọn và phản ánh dependency hoặc thao tác.
- Giữ tên trong annotation hoặc create(name) trùng chính xác với khóa YAML.
- Dùng configs để chia sẻ quy tắc và instances để tinh chỉnh từng dependency.
- Chỉ chia sẻ một instance giữa các phương thức khi chúng thực sự cần cùng trạng thái thống kê.
- Khai báo fallback có kiểu trả về và tham số tương thích với phương thức gốc.
- Đặt phương thức được bảo vệ trong Spring bean và gọi qua proxy.
- Phân biệt annotation AOP của Resilience4j với API CircuitBreakerFactory của Spring Cloud.
- Tránh bọc lặp cùng một lời gọi bằng nhiều Circuit Breaker ngoài ý muốn.
- Theo dõi metrics theo tên instance để biết dependency nào đang lỗi.
- Kiểm tra dependency và cấu hình theo đúng phiên bản Spring Boot, Spring Cloud và Resilience4j của dự án.

Tên instance là cầu nối giữa mã ứng dụng và cấu hình YAML. Khi name trong @CircuitBreaker trùng với khóa instances, Resilience4j có thể áp dụng đúng sliding window, failure threshold, slow-call threshold và thời gian chờ OPEN cho dependency tương ứng. Kết hợp quy ước đặt tên, fallback có chữ ký rõ ràng và hiểu đúng Spring AOP giúp Circuit Breaker hoạt động nhất quán, dễ theo dõi và dễ vận hành trong ứng dụng Spring Cloud.

## Tài liệu tham khảo

- [Resilience4j Spring Boot 3 integration](https://resilience4j.readme.io/docs/getting-started-3)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Framework AOP proxying mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)

