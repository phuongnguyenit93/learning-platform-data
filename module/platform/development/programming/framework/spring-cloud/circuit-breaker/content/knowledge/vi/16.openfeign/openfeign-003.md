# Tùy chỉnh tên bằng CircuitBreakerNameResolver

Khi bật Spring Cloud CircuitBreaker cho OpenFeign, mỗi phương thức của Feign client có thể được bảo vệ bởi một circuit breaker riêng. Framework cần tạo tên để nhận diện bộ ngắt mạch đó. Tên này được dùng khi tra cứu cấu hình Resilience4j, ghi nhận metrics, phát sự kiện và chẩn đoán lời gọi.

Spring Cloud OpenFeign cung cấp `CircuitBreakerNameResolver` để ứng dụng tùy chỉnh cách tạo tên từ client và phương thức được gọi. Một quy tắc đặt tên ổn định giúp ánh xạ chính xác cấu hình cho từng lời gọi, tránh nhầm lẫn giữa các client hoặc các phương thức overloaded, đồng thời giúp dashboard và log dễ đọc.

## Circuit breaker được đặt tên như thế nào?

Khi bật circuit breaker cho OpenFeign, framework tạo một tên cho từng lời gọi được bảo vệ. Quy tắc tên mặc định đã thay đổi giữa các thế hệ Spring Cloud. Một số phiên bản dùng tên kết hợp client và phương thức; các phiên bản mới hơn có thể đưa cả kiểu tham số vào tên để phân biệt các phương thức overloaded.

Vì vậy, không nên giả định tên được sinh ra luôn giống nhau giữa mọi phiên bản. Nếu ứng dụng cần một quy ước cụ thể, hãy cung cấp bean `CircuitBreakerNameResolver` và kiểm tra tên thực tế được tạo ra trong phiên bản đang sử dụng.

Resolver nhận ba thông tin:

| Tham số | Ý nghĩa |
|---|---|
| `feignClientName` | Tên client do OpenFeign chuyển vào resolver. |
| `target` | Feign Target mô tả interface và đích gọi của client. |
| `method` | Phương thức trên interface Feign đang được gọi. |

Hợp đồng resolver trả về một chuỗi tên. Chuỗi đó cần ổn định giữa các lần chạy và có thể dùng nhất quán trong cấu hình, metrics và log.

## Vì sao cần tùy chỉnh tên?

Giả sử ứng dụng có hai Feign client cùng gọi một dịch vụ tồn kho: một client đọc số lượng để hiển thị và một client giữ chỗ sản phẩm. Hai luồng này có đặc tính lỗi và chính sách fallback khác nhau. Nếu tên chỉ dựa vào phương thức `get` hoặc `execute`, các client có thể tạo ra tên trùng hoặc khó phân biệt.

Một quy tắc tên tốt cần đáp ứng:

- Có thành phần nhận diện Feign client.
- Có tên phương thức được bảo vệ.
- Phân biệt các phương thức overloaded khi cần.
- Không chứa dữ liệu thay đổi theo từng request như SKU, user ID hoặc order ID.
- Dễ ánh xạ sang tên instance trong cấu hình Resilience4j.
- Giữ ổn định khi ứng dụng khởi động lại và khi chạy nhiều replica.

Không nên tạo tên circuit breaker từ URL đầy đủ hoặc tham số request. Nếu mỗi SKU tạo một tên khác nhau, ứng dụng có thể tạo số lượng instance và chuỗi metrics rất lớn. Mỗi instance cũng chỉ nhận một phần lưu lượng, khiến sliding window thiếu mẫu để đánh giá lỗi và lời gọi chậm.

## Bật circuit breaker cho OpenFeign

Ứng dụng cần có starter OpenFeign và implementation Spring Cloud CircuitBreaker tương ứng, ví dụ Resilience4j. Sau đó bật tính năng circuit breaker của OpenFeign:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Ví dụ một Feign client:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory-service")
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryResponse getBySku(@PathVariable("sku") String sku);
}
~~~

Khi phương thức `getBySku` được gọi, OpenFeign tạo lời gọi được bảo vệ bằng circuit breaker theo cấu hình đang bật. Resolver cho phép ứng dụng kiểm soát tên gắn với lời gọi này.

## Cài đặt CircuitBreakerNameResolver

Ví dụ sau tạo tên theo client, phương thức và kiểu tham số. Việc thêm kiểu tham số giúp phân biệt các phương thức overloaded có cùng tên.

~~~java
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
    public CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) -> {
            String parameterTypes = Arrays.stream(method.getParameterTypes())
                    .map(Class::getTypeName)
                    .collect(Collectors.joining("_"));

            String rawName = feignClientName + "_" + method.getName()
                    + (parameterTypes.isEmpty() ? "" : "_" + parameterTypes);

            return rawName.replaceAll("[^A-Za-z0-9_-]", "_");
        };
    }
}
~~~

Resolver tạo tên từ ba thành phần:

1. Tên Feign client do framework truyền vào.
2. Tên phương thức.
3. Kiểu tham số theo thứ tự khai báo.

Sau đó, các ký tự ngoài chữ, số, dấu gạch dưới và dấu gạch ngang được thay bằng dấu gạch dưới để tên dễ dùng trong cấu hình. Đây là một quy ước minh họa; ứng dụng cần kiểm tra tên sau chuẩn hóa để tránh hai chữ ký khác nhau vô tình trở thành cùng một chuỗi.

Với phương thức `getBySku(String sku)` của client `inventory-service`, tên có thể là:

~~~text
inventory-service_getBySku_java_lang_String
~~~

Nếu interface có hai phương thức cùng tên nhưng khác kiểu tham số, phần chữ ký giúp tạo tên khác nhau. Không cần thêm giá trị SKU thực tế vào tên; kiểu tham số đã đủ để phân biệt ở cấp phương thức.

Tham số `target` cung cấp thêm thông tin về interface và đích Feign. Nếu hệ thống có các client dùng chung tên dịch vụ nhưng cần chính sách riêng, có thể sử dụng thông tin target phù hợp để tạo namespace riêng. Hãy chọn thành phần định danh ổn định, không phụ thuộc URL động hoặc dữ liệu runtime.

## Áp dụng resolver toàn cục hoặc cho một Feign client

Có hai cách tổ chức bean tùy phạm vi mong muốn.

**Resolver toàn cục:** đặt bean trong cấu hình Spring được ứng dụng quét. Khi đó resolver có thể được dùng cho các Feign client trong ứng dụng. Cách này phù hợp khi toàn bộ client dùng cùng một quy ước tên.

**Resolver theo client:** khai báo lớp cấu hình riêng và gắn vào thuộc tính `configuration` của `@FeignClient`. Ví dụ:

~~~java
@FeignClient(
        name = "inventory-service",
        configuration = InventoryFeignNamingConfiguration.class
)
public interface InventoryClient {

    @GetMapping("/inventory/{sku}")
    InventoryResponse getBySku(@PathVariable("sku") String sku);
}
~~~

Lớp cấu hình được tham chiếu:

~~~java
public class InventoryFeignNamingConfiguration {

    @Bean
    public CircuitBreakerNameResolver circuitBreakerNameResolver() {
        return (feignClientName, target, method) ->
                feignClientName + "_" + method.getName();
    }
}
~~~

Nếu cấu hình chỉ dành cho một client, hãy đặt lớp cấu hình ở package không bị component scan của ứng dụng chính quét như cấu hình toàn cục. Nếu vô tình đưa bean vào context chính, quy tắc có thể áp dụng rộng hơn dự định. Khi cần nhiều quy tắc riêng, hãy tổ chức rõ ràng theo client và kiểm tra phạm vi bean mà Spring tạo ra.

Không khai báo nhiều bean toàn cục cùng kiểu resolver mà không xác định rõ bean nào được dùng. Nếu có nhiều cấu hình, cần tránh xung đột bean hoặc điều kiện tạo bean khiến resolver dự kiến không được chọn.

## Ánh xạ tên resolver với cấu hình Resilience4j

Tên do resolver trả về là khóa quan trọng để tìm cấu hình instance. Ví dụ, nếu resolver tạo tên `inventory-service_getBySku_java_lang_String`, có thể cấu hình instance tương ứng trong `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-service_getBySku_java_lang_String:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Cần đảm bảo tên trong `instances` khớp chính xác với chuỗi resolver trả về sau bước chuẩn hóa. Nếu tên không khớp, cấu hình riêng có thể không được áp dụng như mong đợi và lời gọi có thể dùng cấu hình mặc định.

Khi thay đổi quy tắc đặt tên, hãy rà soát đồng bộ:

- Khóa instance trong `resilience4j.circuitbreaker.instances`.
- Cấu hình TimeLimiter hoặc các chính sách liên quan nếu chúng được gắn theo cùng tên.
- Dashboard, alert và truy vấn metrics đang lọc theo tên cũ.
- Log, trace hoặc tài liệu vận hành có tham chiếu tới tên circuit breaker.

Không nên đổi tên resolver tùy tiện giữa các lần phát hành. Đổi tên có thể khiến cấu hình cũ không còn được tìm thấy và tạo ra chuỗi metrics mới, làm đứt quãng biểu đồ lịch sử.

## Phân biệt tên client, contextId và tên circuit breaker

Các khái niệm này có liên quan nhưng không đồng nhất:

| Khái niệm | Vai trò |
|---|---|
| `name` trong `@FeignClient` | Tên dịch vụ hoặc client mà OpenFeign dùng để xác định đích. |
| `contextId` trong `@FeignClient` | Định danh context cấu hình riêng của Feign client, hữu ích khi có nhiều client cùng gọi một dịch vụ với cấu hình khác nhau. |
| Tên do `CircuitBreakerNameResolver` trả về | Tên instance circuit breaker cho lời gọi được bảo vệ. |

Không nên giả định `contextId` tự động là tên circuit breaker. Resolver nhận các tham số mà framework cung cấp; hãy kiểm tra `feignClientName`, `target` và `method` trong phiên bản đang dùng rồi chọn quy tắc phù hợp. Nếu hai client cần circuit breaker riêng, hãy bảo đảm thành phần định danh trong tên không bị trùng.

## Tránh tên trùng và cardinality cao

Tên trùng có thể khiến hai lời gọi khác nhau dùng chung một cấu hình hoặc trạng thái circuit breaker. Điều này đặc biệt nguy hiểm nếu một thao tác đọc có thể fallback bằng cache còn thao tác ghi phải trả lỗi khi không thể xác nhận kết quả.

Một số cách đặt tên dễ gây vấn đề:

| Quy tắc | Rủi ro |
|---|---|
| Chỉ dùng tên phương thức | Hai Feign client cùng có `getById` có thể trùng tên. |
| Chỉ dùng tên service | Các phương thức trong cùng client dùng chung một instance dù có thể cần chính sách khác nhau. |
| Dùng URL đầy đủ | URL có thể chứa biến đường dẫn, query hoặc thay đổi theo môi trường. |
| Dùng tham số runtime | Mỗi request có thể tạo tên mới và làm metrics cardinality tăng mạnh. |
| Dùng UUID hoặc timestamp | Tên không ổn định và không thể ánh xạ cấu hình nhất quán. |

Một quy tắc dễ quản lý thường kết hợp tên client với tên phương thức; thêm kiểu tham số nếu có overload. Nếu nhiều client có cùng tên dịch vụ nhưng chính sách khác nhau, hãy thêm một định danh client ổn định. Sau khi chuẩn hóa, cần kiểm tra tính duy nhất của các tên sinh ra.

## Quan sát tên circuit breaker khi vận hành

Tên resolver trả về có thể xuất hiện trong các metrics, sự kiện hoặc log liên quan tới circuit breaker. Hãy dùng tên này để trả lời các câu hỏi vận hành:

- Circuit breaker nào đang OPEN?
- Phương thức Feign nào có failure rate hoặc slow call rate tăng?
- Lời gọi nào bị từ chối nhanh vì mạch đang OPEN?
- Phương thức nào đang sử dụng fallback thường xuyên?
- Cấu hình instance nào cần điều chỉnh?

Nên theo dõi số lời gọi thành công, thất bại, chậm và bị từ chối, cùng trạng thái CLOSED, OPEN và HALF_OPEN. Với các client có lưu lượng khác nhau, việc tách tên theo phương thức giúp xác định chính xác luồng đang gặp sự cố.

Tên circuit breaker là nhãn có miền giá trị hữu hạn. Không thêm user ID, SKU, order ID, request ID hoặc giá trị query vào tên. Những dữ liệu chi tiết có thể được ghi trong log hoặc trace theo chính sách của ứng dụng; metrics cần nhãn ổn định để tổng hợp hiệu quả.

## Kiểm thử quy tắc đặt tên

Trước khi đưa resolver vào vận hành, hãy kiểm tra các trường hợp:

| Trường hợp | Kết quả cần xác nhận |
|---|---|
| Một client có một phương thức đơn giản | Tên chứa đúng client và phương thức. |
| Hai client có phương thức cùng tên | Tên không trùng nếu cần chính sách riêng. |
| Một interface có phương thức overloaded | Phần kiểu tham số phân biệt được các chữ ký. |
| Phương thức không có tham số | Tên không có phần chữ ký thừa hoặc ký tự phân cách khó hiểu. |
| Kiểu tham số là nested class hoặc array | Tên sau chuẩn hóa vẫn ổn định và không xung đột. |
| Tên client có dấu gạch ngang hoặc ký tự đặc biệt | Tên sau chuẩn hóa hợp lệ và cấu hình khớp. |
| Đổi quy tắc resolver | Cấu hình Resilience4j và dashboard được cập nhật đồng bộ. |
| Chạy nhiều replica | Cùng một client và phương thức sinh ra cùng một tên trên mọi replica. |

Có thể viết unit test trực tiếp cho resolver bằng cách tạo các giá trị giả lập cho client, target và method. Sau đó, kiểm tra chuỗi kết quả với các chữ ký khác nhau. Trong kiểm thử tích hợp, bật circuit breaker cho OpenFeign, gọi một phương thức và quan sát tên instance thực tế trong log hoặc metrics. Đây là cách xác nhận framework đã sử dụng đúng resolver thay vì chỉ kiểm tra riêng hàm tạo tên.

## Quy trình triển khai

1. Bật circuit breaker cho OpenFeign và xác nhận implementation Spring Cloud CircuitBreaker đang được sử dụng.
2. Chọn quy ước tên dựa trên client và phương thức; thêm kiểu tham số khi cần phân biệt overload.
3. Cài đặt bean `CircuitBreakerNameResolver` toàn cục hoặc trong cấu hình riêng của Feign client.
4. Chuẩn hóa tên theo quy tắc ổn định và kiểm tra khả năng trùng sau chuẩn hóa.
5. Dùng đúng tên được sinh ra làm khóa instance trong cấu hình Resilience4j.
6. Cập nhật metrics, dashboard, alert và tài liệu khi quy tắc tên thay đổi.
7. Kiểm thử nhiều client, phương thức overloaded, client có cùng tên dịch vụ và nhiều replica.

`CircuitBreakerNameResolver` là điểm mở rộng để kiểm soát danh tính của circuit breaker do OpenFeign tạo ra. Khi tên phản ánh ổn định client và phương thức, cấu hình Resilience4j có thể được ánh xạ chính xác, metrics dễ đọc và các luồng gọi có chính sách khác nhau không vô tình dùng chung trạng thái. Hãy giữ tên hữu hạn, xác định rõ phạm vi bean và kiểm tra tên thực tế theo phiên bản Spring Cloud của ứng dụng.

