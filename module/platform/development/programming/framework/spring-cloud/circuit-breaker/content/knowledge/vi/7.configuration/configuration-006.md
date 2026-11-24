# Cấu hình Circuit Breaker và TimeLimiter có thể lấy từ nhóm khác nhau

Trong Spring Cloud CircuitBreaker tích hợp Resilience4j, Circuit Breaker và TimeLimiter là hai cơ chế có mục tiêu khác nhau. Circuit Breaker đánh giá sức khỏe của dịch vụ phụ thuộc qua kết quả lời gọi, tỷ lệ lỗi và tỷ lệ lời gọi chậm. TimeLimiter giới hạn thời gian chờ của một lần thực thi. Vì vậy, một dịch vụ có thể cần chính sách Circuit Breaker từ một nhóm cấu hình và chính sách TimeLimiter từ một nhóm khác.

Resilience4j tổ chức cấu hình của hai cơ chế trong hai nhánh độc lập: **resilience4j.circuitbreaker** và **resilience4j.timelimiter**. Mỗi nhánh có thể khai báo các nhóm dùng chung trong **configs** và ánh xạ từng instance trong **instances**. Bằng cách đặt **baseConfig** riêng cho cùng một instance ID ở từng nhánh, ứng dụng có thể ghép chính sách sức khỏe với chính sách timeout theo nhu cầu của dịch vụ.

## 1. Vì sao cần tách nhóm cấu hình?

Circuit Breaker và TimeLimiter giải quyết hai vấn đề riêng:

- **Circuit Breaker** quyết định có nên tiếp tục gửi lời gọi đến dịch vụ phụ thuộc hay không. Nó thu thập kết quả trong sliding window, tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm, rồi chuyển giữa CLOSED, OPEN và HALF_OPEN.
- **TimeLimiter** giới hạn thời gian chờ của một thao tác được bảo vệ. Nó giúp lời gọi không giữ tài nguyên quá lâu và cho phép ứng dụng chuyển sang fallback khi thời hạn bị vượt quá.

Một dịch vụ Catalog có thể cần timeout ngắn vì dữ liệu phải trả nhanh cho trang sản phẩm, nhưng ngưỡng Circuit Breaker có thể cần nhiều mẫu hơn để tránh mở mạch do một vài lỗi nhất thời. Ngược lại, dịch vụ thanh toán có thể cần timeout dài hơn vì quy trình xác nhận phức tạp, trong khi Circuit Breaker phải mở nhanh khi tỷ lệ lỗi tăng.

Nếu buộc hai cơ chế dùng chung một nhóm cấu hình, việc thay đổi timeout có thể kéo theo thay đổi không cần thiết về cửa sổ trượt hoặc ngưỡng lỗi. Tách nhóm cho phép nhóm vận hành điều chỉnh thời gian chờ độc lập với chính sách đánh giá sức khỏe.

## 2. Hiểu cấu trúc configs và instances

Mỗi loại cấu hình Resilience4j có hai phần chính:

| Phần | Ý nghĩa | Ví dụ |
|---|---|---|
| **configs** | Khai báo nhóm chính sách có thể tái sử dụng | **resilience4j.circuitbreaker.configs.inventory-health** |
| **instances** | Khai báo chính sách được gắn với một định danh thực tế trong ứng dụng | **resilience4j.circuitbreaker.instances.inventory** |
| **baseConfig** | Chỉ ra instance kế thừa nhóm cấu hình nào | **baseConfig: inventory-health** |

Cấu trúc tương tự được áp dụng độc lập cho TimeLimiter. Vì vậy, một instance tên **inventory** có thể kế thừa nhóm **inventory-health** trong nhánh Circuit Breaker và nhóm **short-timeout** trong nhánh TimeLimiter.

Tên instance phải trùng với ID mà code truyền vào factory. Nếu code gọi **create("inventory")**, cấu hình trong **instances.inventory** mới là cấu hình gắn với lời gọi đó. Tên nhóm trong **configs** có thể khác với ID instance, miễn là **baseConfig** tham chiếu đúng tên nhóm đã khai báo trong cùng nhánh cấu hình.

## 3. Ví dụ YAML: một instance, hai nhóm khác nhau

Giả sử ứng dụng có hai dịch vụ phụ thuộc là Inventory và Catalog. Inventory cần đánh giá lỗi theo cửa sổ 30 giây và timeout hai giây. Catalog dùng cửa sổ theo số lượng lời gọi và timeout bốn giây.

Có thể tổ chức **application.yml** như sau:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      inventory-health:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3

      catalog-health:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 70
        slowCallDurationThreshold: 1500ms
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2

    instances:
      inventory:
        baseConfig: inventory-health

      catalog:
        baseConfig: catalog-health

  timelimiter:
    configs:
      short-timeout:
        timeoutDuration: 2s
        cancelRunningFuture: true

      extended-timeout:
        timeoutDuration: 4s
        cancelRunningFuture: true

    instances:
      inventory:
        baseConfig: short-timeout

      catalog:
        baseConfig: extended-timeout
~~~

Cấu hình trên có hai cách ánh xạ độc lập:

| Instance ID | Nhóm Circuit Breaker | Nhóm TimeLimiter |
|---|---|---|
| **inventory** | **inventory-health** | **short-timeout** |
| **catalog** | **catalog-health** | **extended-timeout** |

Như vậy, Inventory không cần một nhóm tổng hợp có cả timeout và ngưỡng lỗi. Instance **inventory** tự chọn nhóm sức khỏe từ nhánh **circuitbreaker** và nhóm thời gian chờ từ nhánh **timelimiter**.

Các giá trị chỉ nhằm minh họa cách tổ chức. Ví dụ, **slidingWindowSize: 30** với kiểu TIME_BASED có nghĩa là cửa sổ theo 30 giây; với COUNT_BASED, kích thước là số lượng kết quả. **minimumNumberOfCalls** giới hạn số mẫu tối thiểu trước khi đánh giá tỷ lệ. Ngưỡng lỗi và ngưỡng lời gọi chậm cần dựa trên đặc tính vận hành của từng dịch vụ.

## 4. Factory lấy cấu hình theo ID như thế nào?

Khi dùng Spring Cloud CircuitBreaker, ứng dụng tạo Circuit Breaker theo đúng ID đã khai báo trong properties. Ví dụ blocking:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Stock getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> Stock.unavailable(sku)
        );
    }
}
~~~

ID **inventory** được dùng để tra cấu hình instance tương ứng. Tích hợp Resilience4j sử dụng cấu hình Circuit Breaker gắn với ID đó và cấu hình TimeLimiter tương ứng nếu thao tác được thực thi qua đường hỗ trợ TimeLimiter. Trong ví dụ YAML, hai cấu hình này kế thừa hai nhóm khác nhau.

Nếu dùng **create("catalog")**, factory sẽ tra các instance **catalog** trong cả hai nhánh. Không cần đặt tên nhóm Circuit Breaker và TimeLimiter giống nhau; điều quan trọng là mỗi **baseConfig** phải tham chiếu một nhóm tồn tại trong nhánh tương ứng.

Với ứng dụng reactive, dùng factory reactive tương ứng và giữ nguyên publisher:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveInventoryService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    ReactiveInventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    Mono<Stock> getStock(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getStock(sku),
            error -> Mono.just(Stock.unavailable(sku))
        );
    }
}
~~~

Fallback reactive phải trả về publisher phù hợp. Không gọi **block()** để biến lời gọi reactive thành blocking chỉ nhằm sử dụng một factory khác.

## 5. Nhóm cấu hình mặc định và cấu hình riêng theo instance

Có thể khai báo một nhóm **default** trong từng nhánh để dùng làm chính sách chung:

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
        permittedNumberOfCallsInHalfOpenState: 3
      inventory-health:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 10
        failureRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: inventory-health
      catalog:
        baseConfig: default

  timelimiter:
    configs:
      default:
        timeoutDuration: 3s
        cancelRunningFuture: true
      short-timeout:
        timeoutDuration: 2s
    instances:
      inventory:
        baseConfig: short-timeout
      catalog:
        baseConfig: default
~~~

Nhánh Circuit Breaker có nhóm **default** và nhóm **inventory-health**. Nhánh TimeLimiter cũng có nhóm **default** và nhóm **short-timeout**. Cấu hình của Inventory được lấy từ **inventory-health** và **short-timeout**, còn Catalog sử dụng nhóm mặc định ở cả hai nhánh.

Trong Resilience4j, nhóm cấu hình có thể kế thừa một cấu hình khác thông qua **baseConfig** nếu phiên bản và loại cấu hình đang dùng hỗ trợ. Cần bảo đảm nhóm cha tồn tại trong đúng nhánh cấu hình; nhóm Circuit Breaker không thể được tham chiếu từ nhánh TimeLimiter hoặc ngược lại.

Có thể đặt thêm thuộc tính trực tiếp trong instance để điều chỉnh một vài giá trị riêng. Khi đó cần xác định rõ giá trị nào đến từ nhóm và giá trị nào được ghi đè tại instance. Không nên tạo nhiều tầng kế thừa nếu chúng khiến người vận hành khó tìm ra giá trị cuối cùng.

## 6. Cách hiểu groupName của factory

Spring Cloud CircuitBreaker có overload cho phép tạo Circuit Breaker bằng **create(id, groupName)**. Cách này hữu ích khi muốn chọn một nhóm cấu hình ở cấp factory. Tuy nhiên, tham số **groupName** là một tên nhóm duy nhất trong lời gọi factory; nó không biểu diễn hai tên nhóm riêng biệt cho Circuit Breaker và TimeLimiter.

Khi yêu cầu là Circuit Breaker và TimeLimiter của cùng một instance phải lấy chính sách từ hai nhóm khác nhau, cách rõ ràng là khai báo **instances.<id>.baseConfig** độc lập dưới **resilience4j.circuitbreaker** và **resilience4j.timelimiter**, sau đó tạo Circuit Breaker bằng ID. Như vậy, mỗi loại cấu hình có thể chọn nhóm riêng theo cấu trúc properties của Resilience4j.

Ví dụ:

~~~java
CircuitBreaker inventoryBreaker =
    circuitBreakerFactory.create("inventory");
~~~

Với ID **inventory**, cấu hình instance của Circuit Breaker và TimeLimiter được ánh xạ độc lập theo YAML. Không cần truyền một groupName chung nếu việc ánh xạ theo từng nhánh đã được khai báo rõ.

Nếu ứng dụng đang sử dụng **create(id, groupName)** cho cấu hình khác, hãy kiểm tra cách release train Spring Cloud đang dùng áp dụng groupName và properties. Tránh trộn groupName của factory với **baseConfig** ở nhiều nơi mà không xác minh thứ tự ưu tiên, vì cấu hình hiệu lực có thể khó dự đoán khi có nhiều nguồn cùng khai báo.

## 7. Cấu hình bằng Java Customizer khi cần tạo chính sách trực tiếp

Ngoài properties, có thể cấu hình Circuit Breaker và TimeLimiter bằng Java. Cách này hữu ích khi chính sách được tạo từ code hoặc cần dùng logic để chọn tham số. Hai đối tượng cấu hình vẫn được truyền riêng vào builder:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class InventoryCircuitBreakerConfiguration {

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> inventoryConfig() {
        CircuitBreakerConfig circuitBreakerConfig =
            CircuitBreakerConfig.custom()
                .slidingWindowType(
                    CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
                .slidingWindowSize(30)
                .minimumNumberOfCalls(15)
                .failureRateThreshold(40)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(3)
                .build();

        TimeLimiterConfig timeLimiterConfig =
            TimeLimiterConfig.custom()
                .timeoutDuration(Duration.ofSeconds(2))
                .cancelRunningFuture(true)
                .build();

        return factory -> factory.configure(
            builder -> builder
                .circuitBreakerConfig(circuitBreakerConfig)
                .timeLimiterConfig(timeLimiterConfig),
            "inventory"
        );
    }
}
~~~

Trong builder, **circuitBreakerConfig** nhận cấu hình Circuit Breaker và **timeLimiterConfig** nhận cấu hình TimeLimiter. Chúng là hai đối tượng riêng nên có thể thay đổi độc lập. Java Customizer là một lựa chọn tổ chức cấu hình khác với YAML; không nên khai báo cùng một chính sách ở cả hai nơi nếu chưa xác định rõ quy tắc ưu tiên của phiên bản đang dùng.

## 8. TimeLimiter thực sự giới hạn điều gì?

TimeLimiter giới hạn thời gian chờ của thao tác được tích hợp với nó. Khi hết thời hạn, thao tác được xem là timeout và lỗi có thể được chuyển đến fallback. Thuộc tính **timeoutDuration** xác định thời lượng; **cancelRunningFuture** điều khiển việc cố gắng hủy Future đang chạy khi timeout xảy ra.

Cần phân biệt ba giới hạn:

| Giới hạn | Nơi cấu hình | Mục đích |
|---|---|---|
| TimeLimiter | **resilience4j.timelimiter** | Giới hạn thời gian chờ của thao tác được bọc |
| HTTP connect/read timeout | HTTP client | Giới hạn thời gian thiết lập kết nối và chờ dữ liệu từ máy chủ |
| Database query/connection timeout | Driver hoặc connection pool | Giới hạn thời gian truy vấn hoặc lấy kết nối |

TimeLimiter không đảm bảo mọi thao tác I/O bên dưới tự dừng ngay khi hết thời hạn. Việc hủy Future có hiệu quả hay không còn phụ thuộc vào client và khả năng hủy tác vụ. Vì vậy, vẫn cần timeout tại HTTP client hoặc database driver. Nếu TimeLimiter timeout nhưng request mạng vẫn tiếp tục chạy nền, tài nguyên vẫn có thể bị giữ lại.

Timeout cũng có thể được Circuit Breaker ghi nhận là lỗi, tùy cách tích hợp và cấu hình exception. Khi điều chỉnh hai nhóm, hãy xem xét quan hệ giữa **timeoutDuration**, **slowCallDurationThreshold** và **slowCallRateThreshold**. Nếu timeout luôn dài hơn ngưỡng slow call, lời gọi chậm có thể được Circuit Breaker ghi nhận trước khi TimeLimiter kết thúc thao tác. Nếu timeout quá ngắn so với độ trễ bình thường, ứng dụng có thể tạo nhiều lỗi timeout và mở mạch không cần thiết.

## 9. Kiểm tra cấu hình hiệu lực

Khi cấu hình hai nhóm khác nhau, lỗi thường gặp là instance tham chiếu nhầm tên nhóm hoặc ID trong code không trùng tên instance. Có thể kiểm tra theo trình tự:

1. Xác nhận code tạo Circuit Breaker bằng đúng ID, ví dụ **inventory**.
2. Xác nhận có **resilience4j.circuitbreaker.instances.inventory**.
3. Xác nhận **baseConfig** của instance Circuit Breaker trỏ đến một khóa trong **resilience4j.circuitbreaker.configs**.
4. Xác nhận có **resilience4j.timelimiter.instances.inventory**.
5. Xác nhận **baseConfig** của instance TimeLimiter trỏ đến một khóa trong **resilience4j.timelimiter.configs**.
6. Kiểm tra đơn vị thời gian và kiểu dữ liệu của các thuộc tính.
7. Khởi động ứng dụng và xem log cấu hình hoặc lỗi bind properties nếu có.
8. Thử một lời gọi chậm để quan sát timeout, rồi thử một chuỗi lỗi đủ dài để kiểm tra Circuit Breaker có chuyển OPEN theo ngưỡng không.

Có thể dùng Actuator và Micrometer nếu ứng dụng đã cấu hình các endpoint cùng registry phù hợp. Các metric về trạng thái, số lời gọi và timeout giúp xác nhận hành vi thực tế. Không bật endpoint quản trị công khai mà không có cơ chế bảo vệ truy cập.

## 10. Lỗi cấu hình thường gặp

- **Dùng chung tên nhóm theo thói quen:** hai nhánh không bắt buộc phải dùng cùng một group name. Hãy ánh xạ từng instance bằng baseConfig riêng.
- **Khai báo nhóm ở sai nhánh:** TimeLimiter phải tham chiếu nhóm trong **resilience4j.timelimiter.configs**, còn Circuit Breaker tham chiếu nhóm trong **resilience4j.circuitbreaker.configs**.
- **ID trong code không khớp instance:** code tạo **inventory** nhưng YAML chỉ khai báo **stock-service**, khiến cấu hình mong đợi không được áp dụng.
- **Nhầm groupName với baseConfig:** groupName của overload factory là một tham số ở cấp lời gọi; baseConfig là tham chiếu nhóm trong từng nhánh properties.
- **Chỉ cấu hình TimeLimiter mà không cấu hình timeout ở client:** thao tác I/O có thể tiếp tục giữ tài nguyên sau khi tầng gọi đã timeout.
- **Timeout ngắn hơn độ trễ bình thường:** ứng dụng tạo lỗi timeout liên tục và Circuit Breaker có thể mở sớm.
- **Khai báo chính sách ở nhiều nguồn:** YAML và Java Customizer cùng đặt một tham số có thể gây khó khăn khi xác định giá trị hiệu lực.
- **Không kiểm tra phiên bản:** tên thuộc tính, auto-configuration và cách kết hợp properties có thể khác giữa các release train; cần đối chiếu tài liệu đúng phiên bản Spring Cloud và Resilience4j.

## 11. Tình huống thực hành

Một ứng dụng đặt hàng gọi Inventory để kiểm tra tồn kho. Đội vận hành muốn Circuit Breaker đánh giá tỷ lệ lỗi trong cửa sổ 30 giây, nhưng timeout phải là hai giây vì giao diện cần phản hồi nhanh.

Chính sách được tách như sau:

- Nhóm **inventory-health** trong Circuit Breaker đặt cửa sổ TIME_BASED 30 giây, tối thiểu 15 lời gọi, ngưỡng lỗi 40%, thời gian OPEN 20 giây và ba probe HALF_OPEN.
- Nhóm **short-timeout** trong TimeLimiter đặt timeout hai giây và bật hủy Future khi có thể.
- Instance **inventory** tham chiếu **inventory-health** ở nhánh Circuit Breaker và **short-timeout** ở nhánh TimeLimiter.

Khi ứng dụng gọi **create("inventory")**, factory tạo Circuit Breaker gắn với ID đó. Một lời gọi chậm hơn hai giây có thể bị TimeLimiter kết thúc và đi vào fallback. Kết quả timeout có thể được Circuit Breaker tính là lỗi theo cấu hình tích hợp. Khi đủ mẫu và tỷ lệ lỗi vượt 40%, Circuit Breaker chuyển OPEN. Trong thời gian OPEN, lời gọi mới bị từ chối ngay và fallback có thể trả dữ liệu cache hoặc lỗi nghiệp vụ.

Khi phân tích kết quả, hãy tách biệt hai câu hỏi: thao tác riêng lẻ có vượt quá hai giây hay không, và tập hợp các kết quả trong cửa sổ 30 giây có đủ điều kiện mở mạch hay không. Câu hỏi thứ nhất thuộc TimeLimiter; câu hỏi thứ hai thuộc Circuit Breaker. Việc tách nhóm cấu hình giúp điều chỉnh từng mục tiêu mà không phải thay đổi chính sách còn lại.

## Kết luận

Circuit Breaker và TimeLimiter có thể dùng hai nhóm cấu hình riêng vì Resilience4j quản lý chúng ở hai nhánh properties độc lập. Hãy ánh xạ **instances.<id>.baseConfig** riêng dưới **resilience4j.circuitbreaker** và **resilience4j.timelimiter**, sau đó tạo Circuit Breaker bằng đúng ID trong ứng dụng. Cách tổ chức này giúp tách chính sách đánh giá sức khỏe khỏi giới hạn thời gian chờ, dễ điều chỉnh theo đặc tính từng dịch vụ và thuận tiện kiểm tra khi vận hành.
