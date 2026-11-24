# Ranh giới giữa khám phá và chọn instance bằng Spring Cloud LoadBalancer

Trong một hệ thống microservice, biết dịch vụ nào đang tồn tại và quyết định gửi một request đến bản sao nào là hai việc khác nhau. **Service discovery** trả lời câu hỏi “dịch vụ này hiện có những instance nào?”. **Load balancing** trả lời câu hỏi “với request này, nên gửi đến instance nào trong số đó?”.

Spring Cloud tách hai trách nhiệm này thành các abstraction riêng. Discovery adapter lấy dữ liệu từ registry như Eureka hoặc Consul; Spring Cloud LoadBalancer nhận danh sách instance, áp dụng supplier và thuật toán chọn, rồi phối hợp với HTTP client để gửi request. Hiểu ranh giới này giúp tránh tự chọn instance sai cách, cấu hình nhầm client hoặc kỳ vọng registry tự cân bằng tải.

## 1. Ba bước độc lập trong một lời gọi service-to-service

Giả sử consumer `order-service` cần gọi `catalog-service`, hiện có ba instance:

| Instance | Địa chỉ | Zone |
|---|---|---|
| catalog-a | `10.30.1.21:8080` | `zone-a` |
| catalog-b | `10.30.2.22:8080` | `zone-b` |
| catalog-c | `10.30.1.23:8080` | `zone-a` |

Một request đi qua ba bước:

1. **Khám phá (discovery):** tìm các instance đã đăng ký dưới serviceId `catalog-service`.
2. **Chọn instance (selection):** lọc hoặc sắp xếp danh sách ứng viên theo chính sách, sau đó chọn một instance cho request hiện tại.
3. **Gửi request (transport):** chuyển URI logic thành địa chỉ host/port của instance được chọn và thực hiện HTTP call.

Ba bước này có thể được mô tả như sau:

~~~mermaid
flowchart LR
    A["Consumer gọi<br/>catalog-service"] --> B["Discovery adapter"]
    R[("Eureka / Consul")] <--> B
    B --> C["Danh sách ServiceInstance"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Lọc / ưu tiên ứng viên"]
    E --> F["LoadBalancer chọn 1 instance"]
    F --> G["Load-balanced HTTP client"]
    G --> H["Host:port của instance"]
~~~

Registry giữ dữ liệu đăng ký. Discovery client chuyển dữ liệu đó thành các đối tượng instance mà ứng dụng có thể sử dụng. LoadBalancer quyết định chọn instance nào trong danh sách tại thời điểm gọi. HTTP client thực hiện kết nối mạng. Mỗi lớp có thể lỗi theo cách khác nhau và cần được quan sát riêng.

## 2. DiscoveryClient cung cấp danh sách, không quyết định request đi đâu

Trong Spring Cloud Commons, `DiscoveryClient` là abstraction tra cứu discovery theo serviceId. Với API đồng bộ, phương thức quan trọng là:

~~~java
List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");
~~~

Kết quả là một danh sách `ServiceInstance`. Mỗi phần tử mô tả một instance, thường có host, port, URI, service ID, instance ID, metadata và thông tin kết nối bảo mật. Discovery implementation có thể lấy dữ liệu từ registry trực tiếp hoặc từ cache nội bộ tùy tích hợp.

Ví dụ, consumer có thể kiểm tra danh sách:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogDiscovery {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> findAddresses() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(instance -> instance.getHost() + ":" + instance.getPort())
                .toList();
    }
}
~~~

Phương thức này chỉ trả về các địa chỉ đang được discovery client nhìn thấy. Nó không gửi HTTP request và cũng không chọn một instance tối ưu cho từng request. Nếu consumer lấy `instances.get(0)` rồi dùng mãi địa chỉ đó, ứng dụng đã tự tạo một chính sách chọn rất đơn giản và dễ gây lệch tải. Thứ tự phần tử trong danh sách không phải hợp đồng về ưu tiên hoặc độ khỏe.

Cũng cần phân biệt danh sách “đã đăng ký” với danh sách “có thể phục vụ request ngay lúc này”. Một bản ghi có thể còn tồn tại trong registry trong khoảng thời gian heartbeat hoặc TTL chưa hết hạn, trong khi tiến trình đã ngừng nhận traffic. Việc kiểm tra sức khỏe, lọc ứng viên và thời gian cache ảnh hưởng đến chất lượng danh sách mà LoadBalancer nhận được.

## 3. ServiceInstanceListSupplier là cầu nối giữa discovery và selection

Spring Cloud LoadBalancer không cần biết trực tiếp mọi chi tiết của Eureka hoặc Consul. Nó nhận các ứng viên qua abstraction `ServiceInstanceListSupplier`. Supplier chịu trách nhiệm cung cấp danh sách instance cho một serviceId; các supplier có thể bổ sung cache, health check, ưu tiên zone hoặc bộ lọc theo chính sách triển khai.

Một pipeline điển hình có thể gồm:

- **Discovery-backed supplier:** lấy instance từ discovery client.
- **Caching supplier:** giữ kết quả trong một khoảng thời gian để giảm số lần tra cứu và giảm tải cho registry.
- **Health-check supplier:** kiểm tra hoặc loại các instance không đạt điều kiện health, nếu ứng dụng bật và cấu hình cơ chế này.
- **Zone-preference supplier:** ưu tiên instance cùng zone với consumer khi metadata và cấu hình zone có sẵn.

Không phải ứng dụng nào cũng dùng tất cả các supplier trên. Danh sách thực tế phụ thuộc cấu hình và phiên bản Spring Cloud. Cache giúp giảm độ trễ và lưu lượng tra cứu, nhưng cache quá lâu có thể giữ instance đã rời hệ thống. Health check bổ sung tín hiệu sức khỏe nhưng cũng có chu kỳ và chi phí riêng; nó không đảm bảo instance sẽ còn khỏe tại đúng thời điểm request đến.

Ví dụ cấu hình supplier dùng discovery client và cache:

~~~java
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogServiceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Đây là ví dụ minh họa một cách tạo supplier. Tích hợp discovery starter và cấu hình LoadBalancer của ứng dụng phải tương thích với release train đang dùng. Nếu thêm health check hoặc zone preference, cần xem thứ tự wrapper trong supplier chain và xác nhận dữ liệu health/zone được cung cấp đúng.

## 4. Spring Cloud LoadBalancer chọn một instance

Sau khi có danh sách ứng viên, LoadBalancer áp dụng chiến lược chọn để trả về một `ServiceInstance`. Hai thuật toán thường gặp là:

| Chiến lược | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Round robin | Lần lượt chọn các ứng viên theo vòng | Các instance có năng lực gần tương đương và muốn phân phối request đơn giản |
| Random | Chọn ngẫu nhiên một ứng viên | Muốn phân phối ngẫu nhiên và chấp nhận dao động ngắn hạn |

Round robin không có nghĩa mỗi instance chắc chắn nhận số request bằng nhau trong mọi khoảng thời gian. Mỗi consumer có trạng thái chọn riêng; số lượng consumer, lưu lượng không đều, thời gian xử lý, retry và thay đổi danh sách instance đều ảnh hưởng phân phối thực tế. Nếu một instance xử lý chậm hơn, round robin vẫn có thể gửi request mới đến nó trừ khi có cơ chế lọc hoặc chính sách khác.

Selection cũng không đồng nghĩa với failover tự động trong mọi trường hợp. LoadBalancer có thể chọn một instance hợp lệ theo danh sách hiện có, nhưng kết nối vẫn có thể thất bại do mạng, tiến trình chết ngay sau health check hoặc ứng dụng trả lỗi. Retry là một cơ chế riêng cần được cấu hình có chủ đích; nó phải có giới hạn, timeout và cân nhắc tính idempotent của request.

### Phân biệt các abstraction chính

| Thành phần | Trách nhiệm |
|---|---|
| `DiscoveryClient` | Tra cứu danh sách instance theo serviceId |
| `ServiceRegistry` | Đăng ký, hủy đăng ký và quản lý trạng thái registration |
| `ServiceInstanceListSupplier` | Cung cấp danh sách ứng viên cho LoadBalancer |
| `LoadBalancerClient` | API đồng bộ để chọn instance và hỗ trợ thực thi request |
| `ReactiveLoadBalancer` | API reactive để chọn instance |
| `@LoadBalanced` HTTP client | Kích hoạt tích hợp phân giải serviceId qua LoadBalancer trước khi gửi request |

`ServiceRegistry` thuộc chiều đăng ký của provider. `DiscoveryClient` thuộc chiều tra cứu. `ServiceInstanceListSupplier` và LoadBalancer thuộc chiều chọn ứng viên của consumer. Không nên gộp các abstraction này thành một “registry client” duy nhất vì chúng có vòng đời và mục tiêu khác nhau.

## 5. Để HTTP client thực hiện selection thay vì tự chọn phần tử

Với lời gọi HTTP thông thường, cách đơn giản là đánh dấu bean HTTP client bằng `@LoadBalanced`. Ví dụ dùng `RestTemplate`:

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Consumer dùng serviceId trong URL:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
public class CatalogClient {

    private final RestTemplate restTemplate;

    public CatalogClient(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public CatalogItem findItem(String itemId) {
        return restTemplate.getForObject(
                "http://catalog-service/api/items/{id}",
                CatalogItem.class,
                itemId);
    }
}
~~~

Với bean được đánh dấu `@LoadBalanced`, tích hợp Spring Cloud bổ sung xử lý để phân giải `catalog-service`, lấy ứng viên và chọn instance trước khi HTTP request được gửi. URL vẫn dùng tên logic; consumer không cần tự ghép IP và port.

Nếu dùng một `RestTemplate` thông thường không có load-balancing interceptor, hostname `catalog-service` có thể được chuyển cho DNS resolver. Khi đó registry Eureka hoặc Consul không tự động tham gia vào quá trình phân giải URL. Cần kiểm tra đúng bean được inject và đúng client được sử dụng; trong ứng dụng có nhiều HTTP client, nên đặt qualifier hoặc tên bean rõ ràng để tránh dùng nhầm.

Có thể gọi trực tiếp `LoadBalancerClient` khi cần biết instance được chọn cho mục đích chẩn đoán hoặc tích hợp đặc biệt:

~~~java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogInstanceInspector {

    private final LoadBalancerClient loadBalancerClient;

    public CatalogInstanceInspector(LoadBalancerClient loadBalancerClient) {
        this.loadBalancerClient = loadBalancerClient;
    }

    public String selectedAddress() {
        ServiceInstance selected =
                loadBalancerClient.choose("catalog-service");

        if (selected == null) {
            throw new IllegalStateException(
                    "No available instance for catalog-service");
        }

        return selected.getHost() + ":" + selected.getPort();
    }
}
~~~

Lệnh `choose` minh họa quyết định selection tại thời điểm gọi. Nếu ứng dụng tự lấy instance theo cách này rồi tự gửi request đến địa chỉ vật lý, nó phải chịu trách nhiệm timeout, xử lý lỗi, URI và retry. Không nên gọi `choose` để ghi log rồi tiếp tục gửi request đến URL logic qua một HTTP client load-balanced khác, vì HTTP client có thể thực hiện một lần chọn mới và request thực tế đi đến instance khác.

## 6. Phạm vi cấu hình theo từng service

Một ứng dụng có thể gọi nhiều service với yêu cầu khác nhau. Ví dụ:

- `catalog-service` có các instance ở nhiều zone; ưu tiên zone gần consumer để giảm độ trễ.
- `payment-service` cần chính sách timeout và retry chặt chẽ do request có tác dụng phụ.
- `report-service` có thể phân phối tải ngẫu nhiên nếu các instance tương đương.

Spring Cloud LoadBalancer hỗ trợ cấu hình theo serviceId thông qua cơ chế cấu hình client riêng, chẳng hạn annotation `@LoadBalancerClient` hoặc `@LoadBalancerClients`. Cách này cho phép tùy chỉnh supplier hoặc bean LoadBalancer cho một service mà không thay đổi chính sách của mọi service trong ứng dụng.

Ví dụ khai báo điểm cấu hình riêng:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class)
public class CatalogLoadBalancerClientConfiguration {
}
~~~

Lớp cấu hình riêng cần tuân thủ hướng dẫn của phiên bản Spring Cloud đang dùng. Các bean cấu hình LoadBalancer dành riêng cho service không nên vô tình bị component scan như cấu hình mặc định toàn ứng dụng; nếu bị áp dụng rộng, một chính sách dành cho catalog có thể ảnh hưởng đến các client khác.

Chỉ tùy chỉnh thuật toán khi có yêu cầu đo lường được. Chẳng hạn, ưu tiên zone chỉ hữu ích khi metadata zone được đăng ký nhất quán và consumer có zone rõ ràng. Một cấu hình ưu tiên zone sai có thể làm danh sách ứng viên rỗng hoặc dồn tải vào một vùng.

## 7. Cache, health và tính nhất quán của quyết định

Selection dựa trên danh sách instance mà supplier cung cấp tại thời điểm request. Danh sách đó có thể cũ hơn trạng thái thực tế:

- Provider vừa tắt nhưng cache của consumer chưa hết hạn.
- Instance vừa đăng ký nhưng consumer chưa đồng bộ dữ liệu mới.
- Health check thành công, sau đó instance lỗi trước khi request đến.
- Consumer ở zone khác nhưng metadata zone chưa được khai báo hoặc bị sai.
- Registry tạm thời không truy cập được, trong khi cache vẫn giữ dữ liệu trước đó.

Do đó, cần xác định rõ độ mới dữ liệu mong muốn, TTL cache, chu kỳ health check và hành vi khi registry mất kết nối. TTL ngắn giúp cập nhật nhanh hơn nhưng tăng số lần truy vấn; TTL dài giảm tải nhưng kéo dài thời gian giữ dữ liệu cũ. Không có một giá trị TTL phù hợp cho mọi hệ thống.

Health check ở supplier cũng không thay thế readiness của ứng dụng. Provider cần thiết kế vòng đời đăng ký và health endpoint sao cho instance chỉ được xem là đủ điều kiện nhận traffic khi đã sẵn sàng theo tiêu chí của hệ thống. Nếu endpoint health chỉ xác nhận tiến trình còn sống mà không phản ánh dependency quan trọng, LoadBalancer có thể tiếp tục chọn instance chưa thể xử lý request.

Khi danh sách ứng viên rỗng, LoadBalancer không thể chọn instance. Consumer cần xử lý lỗi phụ thuộc dịch vụ rõ ràng, trả mã lỗi phù hợp, ghi log và phát metric. Không nên âm thầm chuyển sang một địa chỉ cố định không được quản lý vì điều đó phá vỡ chính sách discovery và selection.

## 8. Kiểm thử và quan sát LoadBalancer

Một bài kiểm thử tốt cần xác nhận cả danh sách ứng viên lẫn instance thực sự nhận request. Có thể kiểm tra theo các tình huống sau:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Một instance đăng ký | Request được gửi đến instance đó |
| Nhiều instance cùng serviceId | Selection sử dụng đúng tập ứng viên và phân phối theo chiến lược cấu hình |
| Một instance bị đánh dấu unhealthy | Instance bị loại hoặc giảm ưu tiên theo supplier/health policy đã cấu hình |
| Instance bị dừng đột ngột | Consumer xử lý lỗi kết nối; cache và health check cập nhật theo thời gian dự kiến |
| Không có instance | Request thất bại có kiểm soát, không chọn nhầm hostname hoặc địa chỉ cũ |
| Consumer ở zone cụ thể | Zone preference hoạt động đúng khi metadata và cấu hình hợp lệ |
| Retry được bật | Số lần retry bị giới hạn và hành vi chọn instance tiếp theo đúng cấu hình |

Nên ghi nhận serviceId, instance ID, zone, kết quả selection, thời gian kết nối và trạng thái HTTP. Các metric hữu ích gồm số lần chọn thành công/thất bại, số instance ứng viên, lỗi kết nối và thời gian request theo service. Tránh ghi access token, dữ liệu cá nhân hoặc payload nhạy cảm.

Khi điều tra sự cố, xác định lỗi nằm ở lớp nào:

1. Registry không có bản ghi hoặc provider chưa đăng ký.
2. Discovery client không trả về danh sách như mong đợi.
3. Supplier lọc hoặc cache khiến tập ứng viên không đúng.
4. LoadBalancer không chọn được instance hoặc chọn sai chính sách.
5. HTTP client không gửi đến địa chỉ được chọn hoặc kết nối thất bại.

Phân tách các lớp này giúp tránh điều chỉnh thuật toán selection khi nguyên nhân thật sự là provider đăng ký sai địa chỉ, health check sai hoặc consumer đang dùng HTTP client không có `@LoadBalanced`.

## 9. Nguyên tắc thiết kế

Khi thiết kế lời gọi giữa các microservice, hãy giữ rõ ranh giới trách nhiệm:

- Provider đăng ký và duy trì trạng thái instance trong registry.
- Discovery client cung cấp danh sách instance theo serviceId.
- Supplier chuẩn bị tập ứng viên, có thể bổ sung cache, health và zone.
- LoadBalancer chọn một instance theo chính sách.
- HTTP client gửi request và xử lý timeout, response hoặc lỗi kết nối.

**Discovery trả lời “có những instance nào”; LoadBalancer trả lời “request này đi đến instance nào”.** Registry không tự cân bằng tải cho consumer, và LoadBalancer cũng không thay thế vòng đời đăng ký của provider. Khi giữ rõ ranh giới đó, ứng dụng có thể thay registry, thay chiến lược selection hoặc thay HTTP client mà không trộn lẫn các trách nhiệm.

