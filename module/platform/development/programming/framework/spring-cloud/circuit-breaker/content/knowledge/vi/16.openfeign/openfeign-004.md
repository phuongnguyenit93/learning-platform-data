# Ánh xạ tên sinh ra với khóa cấu hình Resilience4j

Khi bật Circuit Breaker cho Spring Cloud OpenFeign, mỗi lời gọi phương thức của Feign client có thể được bảo vệ bằng một Circuit Breaker riêng. Spring Cloud tạo tên định danh cho Circuit Breaker từ thông tin client và phương thức được gọi. Resilience4j lại tìm cấu hình theo tên instance trong `resilience4j.circuitbreaker.instances`. Vì vậy, nếu tên được sinh ra và khóa cấu hình không khớp, lời gọi có thể chạy với cấu hình mặc định thay vì ngưỡng mà nhóm phát triển dự định.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, việc ánh xạ chính xác tên này giúp cấu hình CLOSED, OPEN, HALF_OPEN, sliding window, timeout và fallback theo từng phụ thuộc. Cần hiểu nguồn tạo tên, cách chuẩn hóa ký tự, ảnh hưởng của phiên bản Spring Cloud và cách xác minh tên thực tế trong runtime.

## 1. Tên Circuit Breaker được tạo từ đâu?

Khi bật Circuit Breaker cho OpenFeign, Spring Cloud OpenFeign dùng integration của Spring Cloud CircuitBreaker để bọc các phương thức Feign. Mỗi lần gọi được gắn với một định danh để factory tạo Circuit Breaker tương ứng.

Các yếu tố thường tham gia tạo tên:

- Tên Feign client được truyền vào cơ chế phân giải tên.
- Phương thức được gọi trên interface client.
- Quy tắc phân giải tên mặc định hoặc một `CircuitBreakerNameResolver` tùy chỉnh.
- Quy tắc chuẩn hóa ID, ví dụ loại bỏ ký tự không phải chữ và số trong một số phiên bản/cấu hình.

Ví dụ:

~~~java
@FeignClient(name = "inventory")
public interface InventoryClient {
    @GetMapping("/items/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);

    @GetMapping("/items/{sku}/availability")
    Availability getAvailability(@PathVariable("sku") String sku);
}
~~~

Client có hai phương thức. Nếu naming resolver tạo ID theo cặp tên client và tên phương thức, hai lời gọi sẽ có hai tên Circuit Breaker khác nhau. Điều này cho phép đặt ngưỡng riêng cho việc đọc tồn kho và kiểm tra khả năng cung ứng nếu hai thao tác có lưu lượng hoặc độ trễ khác nhau.

Tên được sinh ra là khóa định danh của Circuit Breaker. Nó không nhất thiết giống hoàn toàn với tên service trong registry, tên bean Java hoặc URL HTTP.

## 2. Bật Circuit Breaker cho OpenFeign

Trong cấu hình Spring Boot, cần bật hỗ trợ Circuit Breaker của OpenFeign:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Ứng dụng cũng cần dependency tích hợp Spring Cloud CircuitBreaker với implementation Resilience4j và các dependency OpenFeign phù hợp với release train đang dùng. Các phiên bản Spring Boot, Spring Cloud và Resilience4j cần tương thích với nhau.

Khi tính năng đã bật, các lời gọi Feign được bọc bởi Circuit Breaker. Tên instance cụ thể phụ thuộc naming resolver đang hoạt động. Vì vậy, cần xác định tên thực tế trước khi viết khóa trong YAML của Resilience4j.

## 3. Quy tắc chuẩn hóa ID và khác biệt phiên bản

Spring Cloud OpenFeign có hỗ trợ tùy chọn alphanumeric ID. Tùy phiên bản và cấu hình, tên được tạo theo quy tắc mặc định có thể được chuẩn hóa bằng cách loại bỏ các ký tự không phải chữ và số. Ví dụ, dấu gạch dưới hoặc dấu phân cách trong tên có thể không còn xuất hiện trong ID cuối cùng.

Thuộc tính liên quan:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        alphanumeric-ids:
          enabled: true
~~~

Khi dùng resolver mặc định, hãy kiểm tra tài liệu của release train Spring Cloud cụ thể để biết quy tắc tên và giá trị mặc định của `alphanumeric-ids.enabled`. Không nên sao chép khóa cấu hình từ ví dụ của phiên bản khác rồi giả định kết quả giống nhau.

Ví dụ minh họa sự khác nhau về chuẩn hóa:

| Tên trước chuẩn hóa | Sau khi bỏ ký tự phân cách |
| --- | --- |
| `inventory_getInventory` | `inventorygetInventory` |
| `catalog_findBySku` | `catalogfindBySku` |
| `payment_createOrder` | `paymentcreateOrder` |

Bảng trên minh họa thao tác loại ký tự phân cách; tên thực tế còn phụ thuộc resolver và phiên bản. Hãy dùng tên được runtime tạo ra làm căn cứ cho khóa Resilience4j.

## 4. Tạo tên ổn định bằng CircuitBreakerNameResolver

Nếu muốn kiểm soát tên và tránh phụ thuộc vào thay đổi quy tắc mặc định giữa các phiên bản, có thể cung cấp một bean `CircuitBreakerNameResolver`. Resolver nhận tên Feign client, target và method rồi trả về ID mong muốn.

Ví dụ chọn quy ước `<client>_<method>`:

~~~java
import feign.Target;
import java.lang.reflect.Method;
import org.springframework.cloud.openfeign.CircuitBreakerNameResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeignCircuitBreakerConfiguration {
    @Bean
    CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) ->
                feignClientName + "_" + method.getName();
    }
}
~~~

Với client có tên `inventory` và phương thức `getInventory`, resolver trên tạo tên `inventory_getInventory`. Nếu phương thức là `getAvailability`, tên sẽ là `inventory_getAvailability`.

Khi dùng resolver tùy chỉnh, khóa trong Resilience4j phải khớp chính xác chuỗi mà resolver trả về. Nếu resolver có thêm tiền tố, hậu tố hoặc dùng tên interface thay vì tên client, các khóa YAML cũng cần phản ánh đúng quy ước đó.

Không nên có nhiều bean `CircuitBreakerNameResolver` cùng cạnh tranh trong cùng context. Nếu có nhiều Feign client cần chính sách khác nhau, một resolver có thể phân nhánh theo tên client hoặc thông tin target để tạo ID nhất quán.

## 5. Ánh xạ ID với instances của Resilience4j

Giả sử resolver trả về:

- `inventory_getInventory` cho phương thức đọc tồn kho.
- `inventory_getAvailability` cho phương thức kiểm tra khả năng cung ứng.

Ta khai báo hai instance tương ứng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory_getInventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
      inventory_getAvailability:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 15
        failureRateThreshold: 40
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trong ví dụ:

- Lời gọi lấy tồn kho dùng cửa sổ 20 kết quả gần nhất và ngưỡng lỗi 50%.
- Lời gọi kiểm tra khả năng cung ứng dùng cửa sổ 10 giây và ngưỡng lỗi 40%.
- Mỗi instance có thời gian OPEN và số lời gọi thử nghiệm HALF_OPEN riêng.

Giá trị chỉ nhằm minh họa cách ánh xạ tên. Cần chọn ngưỡng dựa trên lưu lượng và độ trễ đo được của từng thao tác.

Nếu ID thực tế đã được chuẩn hóa thành `inventorygetInventory`, nhưng YAML chỉ khai báo `inventory_getInventory`, Resilience4j sẽ không tìm thấy instance theo tên dự kiến. Khi đó, cấu hình có thể không được áp dụng cho lời gọi đó và ứng dụng sử dụng cấu hình mặc định hoặc cấu hình fallback tùy cách thiết lập.

## 6. Dùng config chung và instance riêng

Nhiều phương thức Feign có thể dùng cùng một chính sách cơ sở. Có thể khai báo `configs` và tham chiếu bằng `baseConfig`:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      feign-read-default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory_getInventory:
        baseConfig: feign-read-default
      inventory_getAvailability:
        baseConfig: feign-read-default
        slowCallDurationThreshold: 800ms
        failureRateThreshold: 40
~~~

Hai instance dùng cùng chính sách cơ sở. Instance kiểm tra khả năng cung ứng ghi đè ngưỡng thời gian chậm và tỷ lệ lỗi vì thao tác đó cần phản hồi nhanh hơn.

Tên `feign-read-default` là tên config do ứng dụng đặt; nó không phải Circuit Breaker ID sinh ra từ OpenFeign. Chỉ các khóa dưới `instances` mới cần khớp với ID được resolver trả về.

## 7. Tách cấu hình theo từng Feign client

Khi một ứng dụng có nhiều Feign client, cần tránh nhầm tên service với ID của từng phương thức:

~~~java
@FeignClient(name = "inventory")
public interface InventoryClient {
    @GetMapping("/items/{sku}")
    Inventory getInventory(@PathVariable("sku") String sku);
}

@FeignClient(name = "payment")
public interface PaymentClient {
    @PostMapping("/payments")
    PaymentResult createPayment(@RequestBody PaymentRequest request);
}
~~~

Với resolver `feignClientName + "_" + method.getName()`, tên minh họa sẽ là `inventory_getInventory` và `payment_createPayment`. Khai báo instance tương ứng:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory_getInventory:
        slidingWindowSize: 20
        failureRateThreshold: 50
      payment_createPayment:
        slidingWindowSize: 10
        failureRateThreshold: 30
        waitDurationInOpenState: 30s
~~~

Thanh toán có thể cần ngưỡng và thời gian OPEN khác với đọc tồn kho. Với thao tác ghi như thanh toán, cần kết hợp idempotency key và quy trình đối soát; Circuit Breaker không tự xác định giao dịch đã được xử lý hay chưa khi request timeout.

## 8. Xác minh tên thực tế trong runtime

Khi cấu hình không có hiệu lực như mong đợi, hãy xác minh ID theo thứ tự:

1. Kiểm tra `spring.cloud.openfeign.circuitbreaker.enabled` đã bật trong profile thực tế.
2. Xác định có bean `CircuitBreakerNameResolver` tùy chỉnh hay không.
3. Ghi log giá trị `feignClientName`, tên method và chuỗi resolver trả về trong môi trường phát triển.
4. Kiểm tra tùy chọn `alphanumeric-ids.enabled` và quy tắc của phiên bản Spring Cloud đang dùng.
5. Đối chiếu ID runtime với khóa `resilience4j.circuitbreaker.instances.<id>`.
6. Kiểm tra metrics hoặc endpoint Actuator tương ứng nếu ứng dụng đã bật và bảo vệ các endpoint đó.

Có thể thêm log trong resolver để nhìn thấy kết quả:

~~~java
@Bean
CircuitBreakerNameResolver circuitBreakerNameResolver() {
    return (feignClientName, target, method) -> {
        String circuitBreakerId =
                feignClientName + "_" + method.getName();
        log.debug(
                "OpenFeign Circuit Breaker ID: client={}, method={}, id={}",
                feignClientName,
                method.getName(),
                circuitBreakerId);
        return circuitBreakerId;
    };
}
~~~

Trong ví dụ, `log` là logger của lớp cấu hình. Chỉ nên ghi log định danh và tên method cần thiết; không ghi dữ liệu request, token hoặc thông tin nhạy cảm. Sau khi xác nhận ID, có thể giảm log xuống mức phù hợp cho môi trường triển khai.

Metrics Resilience4j thường gắn tên instance trong tag `name`. Nếu đã bật Micrometer và endpoint metrics, có thể dùng tag đó để đối chiếu với khóa YAML. Endpoint Actuator cụ thể phụ thuộc dependency, cấu hình expose và phiên bản Spring Boot.

## 9. Phân biệt tên client, contextId và Circuit Breaker ID

Ba khái niệm sau có liên quan nhưng không nên coi là một:

| Giá trị | Mục đích |
| --- | --- |
| `@FeignClient(name = "inventory")` | Định danh dịch vụ/client dùng trong cấu hình và định tuyến Feign |
| `contextId` | Định danh context cấu hình riêng của Feign client, hữu ích khi nhiều client dùng cùng tên dịch vụ nhưng cần cấu hình khác nhau |
| Circuit Breaker ID | Tên được resolver tạo cho lời gọi và dùng để tra instance Resilience4j |

Nếu khai báo `contextId`, không nên tự giả định ID Circuit Breaker sẽ dùng `name` hay `contextId` trong mọi phiên bản. Resolver nhận tham số `feignClientName` do Spring Cloud OpenFeign truyền vào; hãy ghi log giá trị đó để biết chính xác đầu vào được dùng trong ứng dụng hiện tại.

Việc tách bạch các giá trị này giúp tránh lỗi phổ biến: cấu hình `instances.inventory` trong khi resolver thực tế trả về `inventory_getInventory`, hoặc dùng nhầm `contextId` làm khóa dù resolver không tạo tên theo giá trị đó.

## 10. Những lỗi thường gặp khi ánh xạ

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng tên Feign client làm khóa instance cho mọi phương thức | Khóa không khớp ID theo từng method | Dùng ID do resolver thực tế trả về |
| Bỏ qua chuẩn hóa alphanumeric | Dấu gạch dưới hoặc ký tự phân cách khác nhau giữa ID và YAML | Kiểm tra phiên bản và `alphanumeric-ids.enabled` |
| Copy khóa từ ví dụ của release train khác | ID có thể thay đổi theo quy tắc mặc định | Ghi log ID hoặc dùng resolver tùy chỉnh ổn định |
| Đổi method name nhưng quên đổi khóa YAML | Instance cũ không còn được lời gọi tham chiếu | Cập nhật cấu hình cùng lúc với interface Feign |
| Nhầm `contextId` với Circuit Breaker ID | Cấu hình đặt sai khóa | Kiểm tra giá trị resolver nhận và trả về |
| Có nhiều resolver không rõ thứ tự | Tên sinh ra khó dự đoán | Chỉ đăng ký một resolver có quy ước rõ ràng |
| Cấu hình chỉ có `configs` mà thiếu instance tham chiếu | Lời gọi không sử dụng config mong muốn | Khai báo `instances.<generated-id>.baseConfig` |
| Không kiểm tra metrics runtime | Không phát hiện cấu hình không được áp dụng | Đối chiếu tag tên instance và log resolver |

## 11. Quy trình ánh xạ tên cho một Feign client mới

Khi thêm một Feign client hoặc phương thức mới, hãy thực hiện:

1. Bật Circuit Breaker cho OpenFeign trong cấu hình ứng dụng.
2. Xác định naming resolver mặc định đang dùng hoặc đăng ký một resolver tùy chỉnh.
3. Liệt kê tên client và các phương thức cần bảo vệ.
4. Xác định chuỗi ID được tạo cho từng phương thức, tính cả bước chuẩn hóa nếu có.
5. Khai báo `resilience4j.circuitbreaker.instances` với khóa khớp ID đó.
6. Dùng `baseConfig` nếu nhiều instance chia sẻ chính sách, và chỉ ghi đè những tham số khác biệt.
7. Chạy thử lời gọi thành công, lỗi HTTP, timeout và trạng thái OPEN; kiểm tra metrics để xác nhận đúng instance được dùng.
8. Khi đổi tên client, method hoặc resolver, cập nhật các khóa cấu hình và kiểm tra lại runtime.

Ánh xạ chính xác tên sinh ra với khóa cấu hình Resilience4j giúp mỗi phương thức OpenFeign nhận đúng chính sách Circuit Breaker. Dùng resolver ổn định, hiểu quy tắc alphanumeric và xác minh ID qua log hoặc metrics sẽ giảm lỗi cấu hình âm thầm, đồng thời giúp nhóm vận hành điều chỉnh sliding window, ngưỡng lỗi và thời gian phục hồi theo từng lời gọi phụ thuộc.
