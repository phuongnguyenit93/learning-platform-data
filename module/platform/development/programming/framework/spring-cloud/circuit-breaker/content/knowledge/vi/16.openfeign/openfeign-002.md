# Quy tắc đặt tên theo client, method và chữ ký

Khi tích hợp Spring Cloud OpenFeign với CircuitBreaker, mỗi lời gọi trong Feign client cần được gắn với một định danh circuit breaker ổn định. Định danh đó quyết định lời gọi dùng chính sách nào, được thống kê dưới tên nào và liên kết với instance cấu hình Resilience4j ra sao. Nếu chỉ dùng tên dịch vụ mà không xét client interface và method, nhiều lời gọi có thể dùng chung một breaker ngoài ý muốn. Nếu tạo tên từ dữ liệu của từng request, ứng dụng lại có thể sinh quá nhiều breaker và metric.

Để đặt tên có chủ đích, cần phân biệt ba lớp: **client** xác định nhóm lời gọi Feign, **method** xác định thao tác được gọi, còn **chữ ký method** giúp phân biệt các phương thức cùng tên nhưng nhận tham số khác nhau. Spring Cloud OpenFeign cho phép tùy chỉnh tên circuit breaker bằng `CircuitBreakerNameResolver`, từ đó đồng bộ tên được tạo với cấu hình và quan sát runtime.

## 1. Ba loại tên cần phân biệt

Trong một ứng dụng có nhiều Feign client, một tên có thể xuất hiện ở nhiều nơi nhưng mang ý nghĩa khác nhau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| `@FeignClient(name = ...)` | `inventory-service` | Tên dịch vụ/đích mà Feign client gọi, thường được dùng với service discovery hoặc load balancing |
| `contextId` | `inventoryReadClient` | Định danh context cấu hình riêng của Feign client trong ứng dụng, hữu ích khi có nhiều client cùng gọi một dịch vụ nhưng cần cấu hình khác nhau |
| Circuit breaker ID | `inventoryserviceInventoryClientfindBySkuString` | Định danh policy bảo vệ cho một client method hoặc nhóm lời gọi được chọn |

`name` không tự động là tên duy nhất cho mọi method. `contextId` cũng không phải tên circuit breaker theo mặc định trong mọi phiên bản. Circuit breaker ID được tạo bởi cơ chế tích hợp OpenFeign, và có thể tùy chỉnh qua resolver. Không nên đồng nhất ba khái niệm này khi cấu hình.

Ví dụ hai client cùng gọi dịch vụ tồn kho nhưng có mục đích và cấu hình khác nhau:

```java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient")
public interface InventoryReadClient {
    // Các API chỉ đọc tồn kho.
}

@FeignClient(
        name = "inventory-service",
        contextId = "inventoryAdminClient")
public interface InventoryAdminClient {
    // Các API quản trị tồn kho.
}
```

Hai client có cùng `name` để gọi cùng service, nhưng `contextId` khác nhau để Spring Cloud OpenFeign tạo các context cấu hình riêng. Nếu cả hai cần chính sách circuit breaker khác nhau, tên breaker phải phân biệt được hai nhóm lời gọi. Một resolver có thể dùng loại target interface cùng method để tạo ID riêng.

## 2. Bật tích hợp CircuitBreaker cho OpenFeign

Spring Cloud OpenFeign có thể tích hợp Spring Cloud CircuitBreaker để bao quanh các lời gọi Feign. Cần bật tính năng này bằng thuộc tính:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
```

Khi được bật và có implementation CircuitBreaker phù hợp trên classpath, Feign builder sử dụng cơ chế tích hợp circuit breaker cho các method được hỗ trợ. Với Resilience4j, ứng dụng thường thêm starter Spring Cloud CircuitBreaker Resilience4j và quản lý phiên bản qua Spring Cloud release train tương thích với Spring Boot.

Nếu không bật `spring.cloud.openfeign.circuitbreaker.enabled`, việc đặt `@FeignClient` hoặc khai báo `fallback` không tự chứng minh rằng lời gọi đã được bao bởi circuit breaker. Cần kiểm tra cấu hình hiệu lực, dependency và metric runtime.

## 3. Tên breaker gắn với client method

Một Feign interface thường khai báo nhiều method. Ví dụ:

```java
@FeignClient(name = "inventory-service", contextId = "inventoryClient")
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryView findBySku(@PathVariable("sku") String sku);

    @GetMapping("/inventory/{sku}/availability")
    AvailabilityView checkAvailability(@PathVariable("sku") String sku);

    @PostMapping("/inventory/reservations")
    ReservationView reserve(@RequestBody ReservationRequest request);
}
```

Client này có ba method với mục đích và đặc tính lỗi khác nhau. Lời gọi đọc tồn kho, kiểm tra khả dụng và tạo reservation có thể cần timeout, fallback hoặc ngưỡng lỗi khác nhau. Nếu tất cả method dùng cùng một breaker ID, lỗi ở một thao tác có thể ảnh hưởng đến các thao tác còn lại.

Một quy tắc đặt tên phổ biến là kết hợp định danh client với tên method. Khi cần phân biệt overload, thêm kiểu tham số của method vào tên. Ví dụ:

| Client | Method | Tham số | Ý nghĩa ID |
|---|---|---|---|
| `InventoryClient` | `findBySku` | `String` | Đọc tồn kho theo SKU |
| `InventoryClient` | `checkAvailability` | `String` | Kiểm tra khả dụng |
| `InventoryClient` | `reserve` | `ReservationRequest` | Tạo reservation |
| `PricingClient` | `findBySku` | `String` | Lấy giá; tách biệt với thao tác cùng tên ở InventoryClient |

Tên cụ thể phụ thuộc resolver và phiên bản Spring Cloud OpenFeign. Nên xem định danh được tạo thực tế hoặc chủ động cung cấp resolver, thay vì hardcode theo một định dạng mặc định không được xác nhận trong phiên bản đang dùng.

## 4. Vai trò của CircuitBreakerNameResolver

Spring Cloud OpenFeign cung cấp `CircuitBreakerNameResolver` để tùy chỉnh cách tạo tên breaker. Resolver nhận thông tin về tên Feign client, target và Java `Method`, rồi trả về ID dùng cho circuit breaker.

Ví dụ dưới đây tạo ID từ tên client, interface đích, method và kiểu tham số:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

import feign.Target;
import org.springframework.cloud.openfeign.CircuitBreakerNameResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeignCircuitBreakerNamingConfiguration {

    @Bean
    CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) -> {
            String parameterTypes = Arrays.stream(method.getParameterTypes())
                    .map(Class::getSimpleName)
                    .collect(Collectors.joining(""));

            String rawName = feignClientName
                    + target.type().getSimpleName()
                    + method.getName()
                    + parameterTypes;

            return rawName.replaceAll("[^A-Za-z0-9]", "");
        };
    }
}
```

Resolver trên sử dụng:

- `feignClientName`: tên client mà OpenFeign chuyển cho resolver.
- `target.type()`: interface Feign đích, giúp phân biệt các client interface khác nhau.
- `method.getName()`: tên thao tác Java.
- `method.getParameterTypes()`: các kiểu tham số trong chữ ký method, giúp phân biệt overload.

Với `InventoryClient.findBySku(String sku)` và client name `inventory-service`, ID sau chuẩn hóa sẽ có dạng `inventoryserviceInventoryClientfindBySkuString`. Một method khác hoặc một interface khác sẽ có ID riêng.

Đây là quy tắc minh họa. Trong ứng dụng thật, nên xác nhận resolver được Spring nạp cho đúng Feign clients và kiểm tra tên runtime. Nếu tên client có thể thay đổi giữa môi trường, hãy cân nhắc dùng `contextId` hoặc một mapping tường minh khi API resolver và phiên bản đang dùng cung cấp đủ thông tin. Không giả định `contextId` luôn được truyền như `feignClientName`; resolver nhận đúng các đối số được định nghĩa trong API của phiên bản hiện tại.

## 5. Vì sao chữ ký method quan trọng?

Chỉ dùng `method.getName()` có thể không đủ khi interface có các method overload. Ví dụ:

```java
public interface ReportClient {
    @GetMapping("/reports/by-id")
    ReportView find(@RequestParam("id") String id);

    @GetMapping("/reports/by-code")
    ReportView find(@RequestParam("code") Long code);
}
```

Hai method có cùng tên Java là `find`, nhưng tham số lần lượt là `String` và `Long`. Nếu resolver chỉ ghép tên client và tên method, cả hai có thể tạo cùng ID. Khi đó chúng dùng chung một breaker và chung sliding window dù gọi hai endpoint khác nhau.

Đưa kiểu tham số vào ID giúp phân biệt:

```text
reportclientReportClientfindString
reportclientReportClientfindLong
```

Trong Java, chữ ký dùng cho overload được xác định bởi tên method và danh sách kiểu tham số; kiểu trả về không đủ để tạo overload riêng. Do đó, resolver nên dựa vào `getParameterTypes()` khi cần phân biệt các overload.

### Giới hạn của kiểu tham số đơn giản

`Class.getSimpleName()` dễ đọc nhưng có thể không đủ duy nhất nếu hai kiểu đến từ package khác nhau có cùng tên đơn giản. Với dự án lớn hoặc các interface kế thừa phức tạp, có thể dùng tên đầy đủ đã chuẩn hóa:

```java
String parameterTypes = Arrays.stream(method.getParameterTypes())
        .map(Class::getName)
        .collect(Collectors.joining(""));
```

Sau đó loại bỏ dấu chấm, dấu `$`, dấu ngoặc vuông và ký tự không phải chữ/số nếu muốn ID chỉ gồm ký tự alphanumeric. Cần chú ý kiểu mảng, primitive và nested class để tên sau chuẩn hóa vẫn ổn định và không tạo va chạm ngoài ý muốn.

Java generic type bị type erasure. `List<String>` và `List<Long>` đều có raw parameter type là `List.class`; `getParameterTypes()` không phân biệt generic argument. Nếu thiết kế có các hợp đồng generic kế thừa phức tạp và cần tên khác nhau, hãy dùng mapping ID tường minh hoặc kiểm tra `getGenericParameterTypes()` cùng target method đã được resolve. Tránh dựa vào tên tham số Java vì tên tham số có thể không được giữ trong bytecode nếu không bật compiler parameter metadata.

## 6. Tách policy theo client và method

Không phải lúc nào mỗi method cũng cần một breaker riêng. Chọn mức phân tách dựa trên việc các method có cùng phụ thuộc, đặc tính lỗi, SLA và cách phục hồi hay không.

| Cách đặt tên | Khi phù hợp | Tác động |
|---|---|---|
| Một breaker cho toàn client | Các method cùng phụ thuộc và có chính sách lỗi tương tự | Dễ quản lý, nhưng lỗi một method có thể ảnh hưởng các method khác |
| Một breaker cho từng method | Method có SLA, timeout hoặc fallback khác nhau | Cô lập tốt hơn, cần quản lý nhiều instance hơn |
| Một breaker cho từng method signature | Có overload với semantics hoặc backend khác nhau | Tránh trùng ID giữa các overload |
| Một breaker theo nhóm thao tác | Nhiều method có thể dùng chung một chính sách nghiệp vụ | Giảm số instance, cần mapping nhóm rõ ràng |

Ví dụ, hai method `findBySku` và `checkAvailability` đều đọc dữ liệu tồn kho, có thể dùng chung breaker nếu cùng backend và cùng chính sách. Method `reserve` ghi dữ liệu và có yêu cầu idempotency, có thể cần policy riêng. Không nên tách chỉ vì method khác tên nếu chúng thực sự có cùng ranh giới lỗi và cùng mục tiêu bảo vệ.

Khi dùng chung breaker, một method có lưu lượng cao có thể chi phối sliding window và khiến breaker mở cho các method còn lại. Khi tách riêng, mỗi breaker có ít mẫu hơn và có thể cần thời gian dài hơn để đạt `minimumNumberOfCalls`. Cần cân nhắc cả mức cô lập lẫn chất lượng thống kê.

## 7. Cấu hình alphanumeric ID và tương thích phiên bản

Các phiên bản Spring Cloud OpenFeign mới có hỗ trợ chuẩn hóa ID circuit breaker thành ký tự alphanumeric. Thuộc tính điều khiển hành vi này là:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        alphanumeric-ids:
          enabled: true
```

Việc chuẩn hóa giúp ID tương thích với các hệ thống cấu hình và metric có giới hạn về ký tự. Tên được tạo ra có thể khác định dạng của các phiên bản cũ. Nếu nâng Spring Cloud release train, hãy kiểm tra tài liệu của phiên bản và ID runtime trước khi đổi tên instance trong cấu hình Resilience4j.

Nếu dùng `CircuitBreakerNameResolver` tùy chỉnh, hãy quyết định rõ resolver có tự chuẩn hóa tên hay không và kiểm tra tương tác với tùy chọn alphanumeric ID của phiên bản đang chạy. Không nên giả định resolver tùy chỉnh luôn được biến đổi giống resolver mặc định.

Đổi quy tắc tên có thể khiến ứng dụng tạo breaker instance mới thay vì sử dụng instance đã cấu hình. Khi đó, cấu hình cũ có thể không còn được áp dụng, metric bị chia thành các chuỗi tên khác nhau và dashboard/alert không tìm thấy instance. Hãy thay đổi resolver, cấu hình `resilience4j.circuitbreaker.instances` và dashboard trong cùng một kế hoạch.

## 8. Đồng bộ ID với cấu hình Resilience4j

Resilience4j dùng ID của breaker làm khóa dưới `resilience4j.circuitbreaker.instances`. ID trong cấu hình phải trùng chính xác với kết quả resolver.

Với resolver ở phần trên, giả sử ID runtime của `InventoryClient.findBySku(String)` là `inventoryserviceInventoryClientfindBySkuString`. Cấu hình có thể khai báo:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryserviceInventoryClientfindBySkuString:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
```

Nếu ID trong YAML không khớp, instance có thể nhận cấu hình mặc định thay vì policy mong muốn, tùy cấu hình factory và phiên bản tích hợp. Vì vậy, cần ghi lại ID thực tế trong log khi khởi tạo hoặc quan sát qua metric và đối chiếu với cấu hình.

Để giảm rủi ro do tên dài hoặc thay đổi theo chữ ký, có thể dùng mapping tường minh trong resolver:

```java
@Bean
CircuitBreakerNameResolver circuitBreakerNameResolver() {
    return (clientName, target, method) -> {
        String clientType = target.type().getSimpleName();
        String operation = clientType + "_" + method.getName();

        if (clientType.equals("InventoryClient")
                && method.getName().equals("findBySku")) {
            return "inventoryRead";
        }
        if (clientType.equals("InventoryClient")
                && method.getName().equals("reserve")) {
            return "inventoryReserve";
        }
        return (clientName + "_" + operation)
                .replaceAll("[^A-Za-z0-9]", "");
    };
}
```

Mapping tường minh giúp tên ngắn và ổn định qua một số thay đổi refactor. Tuy nhiên, cần cập nhật mapping khi method đổi tên hoặc đổi interface; nếu không, resolver có thể rơi về quy tắc dự phòng mà cấu hình không dự kiến. Dự án nên có test xác nhận tên cho các method quan trọng.

## 9. Fallback thuộc về Feign client, không phải tên breaker

OpenFeign hỗ trợ `fallback` và `fallbackFactory` để cung cấp kết quả thay thế khi lời gọi thất bại theo cơ chế tích hợp. Fallback không phải một phần của tên breaker, nhưng thường được cấu hình trên cùng `@FeignClient`.

Ví dụ dùng `fallbackFactory` để ghi nhận nguyên nhân:

```java
@FeignClient(
        name = "inventory-service",
        contextId = "inventoryClient",
        fallbackFactory = InventoryFallbackFactory.class)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryView findBySku(@PathVariable("sku") String sku);
}
```

```java
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryFallbackFactory implements FallbackFactory<InventoryClient> {

    @Override
    public InventoryClient create(Throwable cause) {
        return sku -> {
            // Ghi nhận cause và trả trạng thái không có dữ liệu xác nhận.
            return InventoryView.unavailable(sku);
        };
    }
}
```

Fallback factory nhận nguyên nhân lỗi để ứng dụng có thể phân loại timeout, lỗi kết nối hoặc breaker từ chối. Trong thực tế, nên log nguyên nhân có cấu trúc và trả trạng thái nghiệp vụ phù hợp. Không trả số lượng bằng 0 nếu ứng dụng chưa đọc được tồn kho; `UNAVAILABLE` khác với `OUT_OF_STOCK`.

Fallback của Feign cũng không nên gọi lại cùng client hoặc cùng phụ thuộc đang lỗi. Nếu fallback tiếp tục gọi cùng dịch vụ, ứng dụng có thể tạo vòng lặp lỗi và làm tăng tải. Nếu dùng cache, hãy biểu diễn rõ dữ liệu cũ và thời điểm cập nhật.

## 10. Những lỗi đặt tên thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nhiều method dùng chung một breaker ngoài ý muốn | Resolver chỉ dùng tên client hoặc chỉ dùng tên method không đủ phân biệt | Thêm target type và method signature hoặc mapping riêng |
| Hai client cùng gọi một service dùng chung ID | Chỉ dựa vào service name, không xét interface/client context | Dùng target type hoặc quy tắc client riêng |
| YAML không áp dụng ngưỡng mong muốn | ID trong `instances` khác tên resolver trả về | Kiểm tra tên runtime và đồng bộ chính xác |
| Overload chia sẻ thống kê | Resolver chỉ ghép `method.getName()` | Thêm kiểu tham số vào ID |
| Tên breaker thay đổi sau khi nâng phiên bản | Quy tắc mặc định/alphanumeric ID thay đổi | Kiểm tra release train, resolver và metric sau nâng cấp |
| Metric tăng cardinality | Tên breaker chứa SKU, user ID hoặc request data | Chỉ dùng metadata tĩnh của client/method |
| Hai client cùng `name` khó phân biệt | Dùng service name làm định danh duy nhất | Đặt `contextId` riêng và dùng target interface trong resolver khi phù hợp |
| Fallback chạy nhưng không rõ nguyên nhân | Dùng fallback chung và bỏ qua cause | Dùng `FallbackFactory` để ghi log/metric theo loại lỗi |

Không đưa giá trị tham số runtime như `sku`, `orderId`, user ID hoặc URL path thực tế vào circuit breaker ID. ID là định danh policy lâu dài, không phải khóa cho từng lần gọi. Dùng dữ liệu động sẽ làm số breaker tăng không kiểm soát, gây tốn bộ nhớ và tạo metric cardinality rất lớn.

## 11. Kiểm thử quy tắc đặt tên

Tên breaker cần được kiểm tra như một phần hợp đồng cấu hình. Có thể viết unit test trực tiếp cho resolver hoặc kiểm thử tích hợp qua Feign client.

Các trường hợp nên xác nhận:

1. Hai method khác tên trong cùng client tạo ID khác nhau khi cần policy riêng.
2. Hai overload cùng tên nhưng khác kiểu tham số tạo ID khác nhau.
3. Hai client interface gọi cùng service name vẫn được phân biệt khi chính sách cần tách.
4. Method kế thừa từ interface cha được đặt tên ổn định theo target type và method thực tế.
5. Method có tham số primitive, array, nested class hoặc kiểu package khác nhau không tạo va chạm ngoài ý muốn.
6. Tên resolver trả về phù hợp với quy tắc alphanumeric của phiên bản đang dùng.
7. Tên trong YAML `resilience4j.circuitbreaker.instances` trùng chính xác ID runtime.
8. Fallback hoặc fallbackFactory được gọi khi breaker mở hay lời gọi Feign thất bại theo policy.
9. Không có tên breaker nào chứa dữ liệu động của request.

Ví dụ test đơn giản cho một hàm tạo ID thuần có thể kiểm tra hai chữ ký khác nhau trả về hai tên khác nhau. Với tích hợp thực tế, nên xác nhận ID thông qua log hoặc metric của Resilience4j khi gọi Feign client. Chỉ test annotation `@FeignClient` bằng reflection không chứng minh resolver được dùng trong runtime.

## 12. Quy trình thiết kế tên cho một Feign client

Khi thêm một Feign client vào hệ thống Spring Cloud CircuitBreaker, có thể thực hiện theo trình tự sau:

1. Đặt `name` theo dịch vụ đích hoặc service discovery name.
2. Đặt `contextId` riêng khi nhiều Feign client cùng gọi một dịch vụ nhưng cần context cấu hình khác nhau.
3. Liệt kê method và nhóm các thao tác có cùng ranh giới lỗi, timeout và fallback.
4. Quyết định dùng một breaker cho cả client, từng method hay từng method signature.
5. Bật `spring.cloud.openfeign.circuitbreaker.enabled` và thêm starter tương thích.
6. Dùng `CircuitBreakerNameResolver` nếu định dạng mặc định không đáp ứng yêu cầu hoặc cần phân biệt overload/client.
7. Giữ ID ổn định, chỉ dựa trên metadata tĩnh của client, target và method.
8. Đồng bộ ID với `resilience4j.circuitbreaker.instances` và dashboard/alert.
9. Viết test xác nhận tên được tạo, cấu hình được áp dụng và fallback hoạt động.
10. Khi nâng Spring Cloud, kiểm tra thay đổi về resolver và alphanumeric IDs trước khi triển khai.

Quy tắc đặt tên theo client, method và chữ ký giúp mỗi Feign operation nhận đúng chính sách bảo vệ. `name` xác định dịch vụ đích, `contextId` phân biệt context cấu hình của client, còn `CircuitBreakerNameResolver` quyết định ID của breaker. Kết hợp target interface với method signature giúp tránh va chạm giữa các thao tác, đồng thời giữ tên ổn định để cấu hình Resilience4j, metric và cảnh báo luôn tham chiếu cùng một instance.
