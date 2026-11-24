# Kiểm soát số lượng nhãn và ID trong metrics

Metrics giúp theo dõi trạng thái Circuit Breaker, tỷ lệ lỗi, lời gọi chậm và số request bị từ chối. Tuy nhiên, mỗi tổ hợp tên metric và tập nhãn có thể tạo thành một time series riêng trong hệ thống lưu trữ như Prometheus. Nếu nhãn chứa ID thay đổi theo từng request, khách hàng hoặc tài nguyên, số time series có thể tăng rất nhanh, làm tốn bộ nhớ, dung lượng lưu trữ và chi phí truy vấn.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, cần thiết kế tên instance và nhãn metrics có số lượng hữu hạn. Với Resilience4j và Micrometer, tên Circuit Breaker nên đại diện cho một phụ thuộc hoặc thao tác ổn định; các ID của request, người dùng, đơn hàng hay SKU nên được giữ trong log và trace. Mục tiêu là quan sát được tình trạng bảo vệ dịch vụ mà không biến metrics thành nơi lưu từng sự kiện riêng lẻ.

## 1. Cardinality của metrics là gì?

**Cardinality** là số lượng chuỗi giá trị khác nhau có thể xuất hiện trong một tập nhãn hoặc số lượng time series được tạo từ các tổ hợp nhãn. Trong Prometheus, một time series được nhận diện bởi tên metric và toàn bộ label set của nó. Chỉ cần một nhãn có giá trị mới, hệ thống có thể tạo một time series mới.

Ví dụ, một metric đếm lời gọi Circuit Breaker có các nhãn:

- `name`: tên instance Circuit Breaker.
- `outcome`: kết quả như thành công, thất bại hoặc bị từ chối.
- `kind`: loại lời gọi, tùy cách metric được instrument.

Nếu ứng dụng có 10 tên instance, 3 outcome và 2 kind, số tổ hợp tối đa về mặt lý thuyết là:

$$
10 \times 3 \times 2 = 60
$$

Đây là ví dụ minh họa số tổ hợp nếu metric có đủ các nhãn đó. Số time series thực tế phụ thuộc vào các tổ hợp đã xuất hiện và cách thư viện xuất metric.

Giả sử thêm nhãn `customerId` có 100.000 giá trị. Khi đó cardinality tiềm năng tăng theo số khách hàng, dù mỗi khách hàng chỉ phát sinh một vài lời gọi. Một nhãn có nhiều giá trị khác nhau thường nguy hiểm hơn nhiều nhãn có tập giá trị nhỏ và cố định.

## 2. Vì sao ID động làm cardinality tăng?

Không nên dùng các giá trị thay đổi liên tục làm label:

| Nhãn không nên dùng | Vì sao nguy hiểm | Thay thế phù hợp |
| --- | --- | --- |
| `requestId` hoặc `traceId` | Gần như mỗi request có một giá trị mới | Đưa ID vào trace hoặc log có liên kết |
| `customerId`, `userId`, `tenantId` | Số khách hàng có thể rất lớn và tăng theo thời gian | Dùng nhóm tenant có giới hạn nếu thực sự cần phân tích |
| `orderId`, `paymentId`, `transactionId` | Mỗi giao dịch tạo giá trị mới | Ghi ID trong log hoặc trace |
| `sku`, `productId`, `resourceId` | Tập tài nguyên có thể rất lớn | Dùng nhóm nghiệp vụ hữu hạn như `inventory-read` |
| URL đầy đủ chứa path variable hoặc query | Mỗi path/query khác nhau tạo label value mới | Dùng route template như `/items/{sku}` |
| Exception message | Nội dung có thể chứa ID, URL, dữ liệu đầu vào hoặc thông tin thay đổi | Dùng nhóm exception ổn định như `timeout`, `connection`, `other` |

Ví dụ, nếu mỗi request tạo một nhãn `sku`, một dịch vụ Kho có 500.000 SKU có thể tạo hàng trăm nghìn giá trị label. Nếu cùng metric còn có nhãn `outcome` và `region`, số tổ hợp có thể tăng thêm theo các chiều đó.

Metrics phù hợp để trả lời câu hỏi tổng hợp như “Circuit Breaker inventory có bao nhiêu lời gọi thất bại trong 5 phút?”. Câu hỏi “request nào liên quan đến SKU X?” phù hợp với log hoặc trace, nơi có thể truy xuất một số lượng sự kiện cụ thể.

## 3. Đặt tên Circuit Breaker ID ổn định

Tên instance được sử dụng trong cấu hình Resilience4j và thường xuất hiện dưới dạng tag trong metrics. Tên nên đại diện cho một phụ thuộc hoặc nhóm thao tác có vòng đời ổn định.

Ví dụ phù hợp:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-create:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
      customer-profile-read:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
~~~

Các tên trên có số lượng hữu hạn và tương ứng với các thao tác được xác định trong code. Mỗi instance có thể có cấu hình và state riêng, nhưng tên không phụ thuộc vào dữ liệu của request.

Ví dụ không phù hợp là tạo tên theo từng khách hàng:

~~~java
// Không nên tạo Circuit Breaker ID từ dữ liệu có cardinality lớn.
String circuitBreakerName = "inventory-" + customerId;
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker(circuitBreakerName);
~~~

Nếu có 50.000 khách hàng, registry có thể phát sinh hàng chục nghìn instance. Mỗi instance có state và sliding window riêng; lượng mẫu bị phân tán và metrics cũng có thể tạo rất nhiều time series.

Nên dùng tên cố định theo phụ thuộc:

~~~java
CircuitBreaker circuitBreaker =
        circuitBreakerRegistry.circuitBreaker("inventory-read");
~~~

Nếu cần phân tích theo nhóm khách hàng, hãy ánh xạ thành một số nhóm hữu hạn được định nghĩa trước, chẳng hạn `customer-tier=standard|premium`, và chỉ thêm nhãn này khi câu hỏi vận hành thực sự cần nó. Không đưa giá trị định danh duy nhất vào metrics.

## 4. Chọn nhãn có tập giá trị hữu hạn

Một label tốt thường có tập giá trị nhỏ, được kiểm soát và có ý nghĩa vận hành:

| Nhãn | Ví dụ giá trị hợp lệ | Ghi chú |
| --- | --- | --- |
| `service` | `order`, `inventory`, `payment` | Tên service cố định |
| `dependency` | `inventory-service`, `payment-provider` | Tên phụ thuộc được quản lý |
| `operation` | `inventory-read`, `payment-create` | Nhóm thao tác cố định |
| `environment` | `dev`, `staging`, `prod` | Không đưa build ID duy nhất vào nhãn |
| `region` | `ap-southeast-1`, `eu-west-1` | Tập vùng triển khai hữu hạn |
| `outcome` | `success`, `failure`, `not_permitted` | Kết quả được chuẩn hóa |
| `exception_group` | `timeout`, `connection`, `http_5xx`, `other` | Ánh xạ nhiều exception vào nhóm hữu hạn |
| `state` | `closed`, `open`, `half_open` | Trạng thái Circuit Breaker |

Không phải metric nào cũng cần tất cả nhãn trên. Mỗi nhãn bổ sung tạo thêm một chiều tổ hợp. Chỉ thêm nhãn khi nó giúp trả lời một câu hỏi cụ thể trong dashboard hoặc cảnh báo.

Tránh đưa các giá trị không được kiểm soát vào nhãn như exception message, URL đầy đủ, tên class được tạo động hoặc nội dung header. Nếu cần lưu thông tin chi tiết, ghi nó vào log hoặc trace có liên kết với metric qua trace ID hoặc exemplar khi hệ thống hỗ trợ.

## 5. Cardinality nhân lên theo tổ hợp nhãn

Giả sử một metric có:

- 40 tên Circuit Breaker.
- 3 outcome.
- 4 nhóm exception.
- 3 region.

Số tổ hợp tối đa về mặt lý thuyết là:

$$
40 \times 3 \times 4 \times 3 = 1.440
$$

Nếu metric đó được xuất dưới dạng histogram với nhiều bucket, số chuỗi lưu trữ có thể tăng thêm theo số bucket cộng các chuỗi tổng hợp như count và sum. Với histogram Prometheus, mỗi label set có thể tạo nhiều chuỗi bucket; vì vậy cardinality của histogram thường đắt hơn một counter đơn giản.

Đây là phép tính trần để hiểu tác động của từng chiều, không phải số time series chắc chắn được tạo. Metric thực tế chỉ có những label set đã phát sinh, và các metric khác nhau có thể dùng các tập nhãn khác nhau.

Một quy tắc thiết kế hữu ích là lập ngân sách cardinality trước khi thêm label:

1. Liệt kê các metric cần xuất.
2. Liệt kê label của từng metric.
3. Ước lượng số giá trị hợp lệ cho mỗi label.
4. Nhân các số lượng để ước lượng số tổ hợp tiềm năng.
5. Nhân thêm hệ số bucket nếu dùng histogram.
6. Xác định nhãn nào có thể bỏ hoặc thay bằng nhóm giá trị hữu hạn.

Không nên chỉ nhìn số lượng label keys. Hai label có 3 giá trị mỗi loại có thể rẻ hơn một label có hàng triệu giá trị.

## 6. Metrics của Resilience4j và Micrometer

Khi tích hợp Resilience4j với Micrometer, các metric Circuit Breaker thường cung cấp thông tin như:

- Số lời gọi theo kết quả.
- Số lời gọi bị từ chối vì mạch OPEN.
- Trạng thái hiện tại của instance.
- Failure rate và slow call rate.
- Số lời gọi được lưu trong sliding window và dung lượng cửa sổ.

Tên meter và tag cụ thể có thể khác theo phiên bản Resilience4j, module Micrometer và cách export. Thông thường, tên instance Circuit Breaker được dùng làm một tag để phân biệt các instance. Cần xem meter thực tế trong endpoint metrics của ứng dụng thay vì giả định mọi phiên bản có cùng tên hoặc cùng tập tag.

Ví dụ, với các instance cố định `inventory-read`, `payment-create` và `customer-profile-read`, dashboard có thể so sánh failure rate hoặc số lần từ chối theo tên. Không cần thêm `requestId`, `customerId` hoặc `sku` để tìm request riêng lẻ.

Nếu dùng Spring Boot Actuator, có thể expose endpoint metrics hoặc Prometheus theo chính sách bảo mật của ứng dụng. Chỉ expose các endpoint cần thiết và giới hạn quyền truy cập; endpoint metrics có thể tiết lộ tên phụ thuộc và chi tiết vận hành của hệ thống.

## 7. Giới hạn số giá trị tag bằng MeterFilter

Micrometer cung cấp `MeterFilter` để kiểm soát meter trước khi đăng ký vào registry. Có thể đặt giới hạn số giá trị khác nhau cho tag `name` của các meter Circuit Breaker:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsCardinalityConfiguration {
    @Bean
    MeterFilter circuitBreakerNameLimit() {
        return MeterFilter.maximumAllowableTags(
                "resilience4j.circuitbreaker",
                "name",
                50,
                MeterFilter.deny()
        );
    }
}
~~~

Ví dụ này giới hạn số giá trị tag `name` được chấp nhận cho các meter có prefix tương ứng. Khi vượt ngưỡng, filter từ chối đăng ký meter mới theo hành vi của filter được truyền vào. Cần xác nhận prefix và tag key bằng meter thực tế của phiên bản đang dùng; nếu tên meter khác, filter sẽ không áp dụng như mong đợi.

Giới hạn tag là lớp bảo vệ bổ sung. Nó không thay thế thiết kế ID ổn định. Nếu ứng dụng đã tạo hàng nghìn Circuit Breaker động trong registry, chỉ chặn meter mới không giải quyết được số lượng instance và state đang tồn tại trong bộ nhớ.

Không nên đặt giới hạn quá thấp đến mức các instance hợp lệ quan trọng bị mất metrics. Hãy chọn ngưỡng dựa trên số phụ thuộc và thao tác được quản lý, sau đó theo dõi cảnh báo khi có meter bị từ chối.

## 8. Chuẩn hóa exception thành nhóm hữu hạn

Không dùng exception message làm nhãn vì message có thể chứa URL, ID hoặc dữ liệu đầu vào. Thay vào đó, ánh xạ exception vào một số nhóm ổn định:

~~~java
import java.net.ConnectException;
import java.net.SocketTimeoutException;

public String classifyFailure(Throwable failure) {
    if (failure instanceof SocketTimeoutException) {
        return "timeout";
    }
    if (failure instanceof ConnectException) {
        return "connection";
    }
    if (failure instanceof DownstreamHttpException http
            && http.getStatusCode() >= 500) {
        return "http_5xx";
    }
    if (failure instanceof CallNotPermittedException) {
        return "circuit_open";
    }
    return "other";
}
~~~

Các nhóm `timeout`, `connection`, `http_5xx`, `circuit_open` và `other` có tập giá trị hữu hạn. Nếu dùng nhóm này làm tag của custom metric, không gắn kèm exception message hoặc stack trace. Với exception từ thư viện HTTP khác, hãy ánh xạ theo kiểu exception thực tế của client đang dùng.

Ví dụ trên chỉ minh họa hàm phân loại; không tự động thêm tag vào mọi metric Resilience4j. Việc tạo custom counter hoặc timer cần được thiết kế riêng, và phải giữ cùng quy tắc tập giá trị hữu hạn.

## 9. Dùng log và trace cho ID có cardinality cao

Metrics, logs và traces phục vụ các mục đích khác nhau:

| Loại dữ liệu | Phù hợp để lưu | Ví dụ |
| --- | --- | --- |
| Metrics | Số liệu tổng hợp, nhãn hữu hạn, xu hướng theo thời gian | Failure rate của `inventory-read` |
| Logs | Sự kiện chi tiết và ID để điều tra | Request ID, SKU, exception message đã lọc |
| Traces | Đường đi của một request qua nhiều service | Trace ID, span ID, thời gian từng lời gọi |

Ví dụ log có thể chứa ID để điều tra:

~~~java
log.warn(
        "Inventory dependency failed: circuitBreaker={}, requestId={}, sku={}, errorGroup={}",
        "inventory-read",
        requestId,
        sku,
        classifyFailure(failure)
);
~~~

Các giá trị như `requestId` và `sku` phù hợp với log có kiểm soát truy cập và thời hạn lưu trữ, nhưng không nên chuyển thành tag metrics. Cần lọc hoặc che dữ liệu nhạy cảm trước khi ghi log. Nếu hệ thống hỗ trợ trace exemplar, có thể liên kết một điểm dữ liệu metric với trace cụ thể mà không biến trace ID thành label của mọi time series.

## 10. Tránh tạo Circuit Breaker ID động trong OpenFeign

Với OpenFeign, naming resolver có thể tạo ID dựa trên tên client và phương thức. Đây là nguồn tên có thể kiểm soát nếu client và method là tập cố định:

~~~java
@Bean
CircuitBreakerNameResolver circuitBreakerNameResolver() {
    return (clientName, target, method) ->
            clientName + "_" + method.getName();
}
~~~

Ví dụ, `inventory_getInventory` là ID ổn định nếu tên client và method không đổi. Không thêm giá trị request vào resolver:

~~~java
// Không nên: mỗi SKU có thể tạo một instance và một chuỗi metrics riêng.
return (clientName, target, method) ->
        clientName + "_" + method.getName() + "_" + currentSku;
~~~

Circuit Breaker ID phải xác định nhóm lời gọi cần chia sẻ cùng state và sliding window. Nếu mỗi SKU có một instance, lịch sử lỗi bị chia nhỏ và mạch khó phản ánh tình trạng chung của dịch vụ Kho.

Khi đổi tên client hoặc method, ID có thể đổi theo. Hãy xem đó là thay đổi cấu hình cần cập nhật đồng bộ với khóa `resilience4j.circuitbreaker.instances` và dashboard đang lọc theo tên instance.

## 11. Theo dõi cardinality và phát hiện tăng bất thường

Trong môi trường chạy thật, nên theo dõi:

- Tổng số time series của ứng dụng và mức tăng theo thời gian.
- Số lượng giá trị tag `name` trong các meter Circuit Breaker.
- Số instance Circuit Breaker đang được registry quản lý.
- Số meter bị từ chối bởi giới hạn cardinality nếu hệ thống ghi nhận được.
- Mức sử dụng bộ nhớ và dung lượng lưu trữ metrics.
- Tỷ lệ meter mới xuất hiện sau mỗi lần triển khai.

Nếu số time series tăng đột biến sau một bản phát hành, hãy kiểm tra các thay đổi liên quan đến tag và ID. Đặc biệt tìm những nhãn mới lấy dữ liệu từ request, URL đầy đủ, tenant, SKU hoặc exception message.

Có thể dùng PromQL để nhóm và đếm series theo metric hoặc label sau khi xác nhận tên metric thực tế được exporter tạo ra. Tránh truy vấn có thể tạo thêm một lượng lớn kết quả chi tiết trong dashboard; mục tiêu là quan sát số lượng tổng hợp và xu hướng tăng.

Một dashboard hữu ích có thể hiển thị:

| Panel | Câu hỏi vận hành |
| --- | --- |
| Số instance theo tên | Có Circuit Breaker ID mới bất thường không? |
| Số time series theo metric family | Metric family nào chiếm nhiều series nhất? |
| Tốc độ tăng series | Cardinality tăng sau thời điểm nào? |
| Meter bị deny | Có giới hạn nào đang chặn metrics hợp lệ không? |
| Failure rate và state | Circuit Breaker đang bảo vệ phụ thuộc nào? |

## 12. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đưa request ID hoặc trace ID vào label | Gần như mỗi request tạo một time series mới | Dùng log hoặc trace để lưu ID |
| Tạo Circuit Breaker theo customer hoặc SKU | Registry và metrics tăng theo số tài nguyên | Dùng instance ID cố định theo phụ thuộc hoặc operation |
| Gắn URL đầy đủ làm tag | Path variable và query tạo giá trị không giới hạn | Dùng route template hoặc nhóm endpoint |
| Dùng exception message làm label | Message chứa dữ liệu động và nhạy cảm | Ánh xạ exception thành nhóm hữu hạn |
| Thêm nhiều label chỉ để tiện lọc | Tổ hợp label tăng nhanh | Chỉ giữ label phục vụ câu hỏi vận hành cụ thể |
| Bật histogram với quá nhiều chiều nhãn | Mỗi bucket nhân thêm số time series | Giới hạn nhãn và bucket theo nhu cầu |
| Chỉ dùng MeterFilter để chữa ID động | Instance động vẫn tồn tại trong registry | Sửa cách đặt tên và vòng đời instance |
| Đổi ID nhưng không cập nhật dashboard | Dashboard mất dữ liệu hoặc phân nhóm sai | Quản lý ID như một phần của hợp đồng metrics |

## 13. Quy trình thiết kế nhãn và ID

Khi thêm metrics cho Circuit Breaker, hãy thực hiện:

1. Xác định câu hỏi mà dashboard hoặc cảnh báo cần trả lời.
2. Chọn ID Circuit Breaker ổn định theo phụ thuộc hoặc operation, không lấy từ dữ liệu request.
3. Liệt kê nhãn cần thiết và số giá trị tối đa dự kiến cho từng nhãn.
4. Ước lượng số tổ hợp label set và chi phí histogram nếu có.
5. Đưa ID duy nhất, URL động và exception message sang log hoặc trace.
6. Dùng MeterFilter để đặt giới hạn bổ sung cho tag quan trọng, sau khi xác nhận tên meter và tag thực tế.
7. Theo dõi số instance, số time series, meter bị từ chối và xu hướng cardinality sau triển khai.
8. Khi đổi naming resolver hoặc tên instance, cập nhật cấu hình Resilience4j và dashboard cùng lúc.

Kiểm soát cardinality bắt đầu từ cách đặt tên instance và chọn nhãn. Khi ID đại diện cho nhóm lời gọi ổn định, label có tập giá trị hữu hạn và thông tin từng request được giữ trong log hoặc trace, metrics Resilience4j vẫn cung cấp đủ góc nhìn về trạng thái Circuit Breaker mà không tạo ra số lượng time series ngoài tầm kiểm soát.
