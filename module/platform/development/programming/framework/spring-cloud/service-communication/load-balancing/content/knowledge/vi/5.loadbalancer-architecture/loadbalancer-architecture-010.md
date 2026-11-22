# Ranh giới giữa việc chọn bản sao và thực thi HTTP

Trong kiến trúc **Spring Cloud LoadBalancer**, có hai quyết định rất khác nhau khi một microservice gọi microservice khác:

1. **Chọn bản sao (instance selection):** dịch vụ logic được yêu cầu là gì, có những `ServiceInstance` nào và nên chọn instance nào?
2. **Thực thi HTTP (HTTP execution):** sau khi biết địa chỉ đích, mở kết nối thế nào, gửi request ra sao, chờ phản hồi bao lâu và xử lý lỗi mạng hoặc mã trạng thái HTTP như thế nào?

Việc phân biệt hai phần này giúp xác định đúng nơi cấu hình thuật toán định tuyến, discovery, health check, retry, timeout và quan sát lỗi. Spring Cloud LoadBalancer phụ trách **lựa chọn đích** ở phía client; việc truyền dữ liệu HTTP tới đích được thực hiện bởi HTTP client và tầng vận chuyển tương ứng.

## 1. Một yêu cầu đi qua những thành phần nào?

Giả sử `order-service` gọi dịch vụ danh mục theo URL logic:

~~~http
GET http://catalog-service/products/42
~~~

Trong hệ thống có hai bản sao của `catalog-service`:

| Service ID | Instance ID | URI vật lý |
|---|---|---|
| `catalog-service` | `catalog-1` | `http://10.0.1.21:8081` |
| `catalog-service` | `catalog-2` | `http://10.0.1.22:8082` |

Khi HTTP client đã tích hợp LoadBalancer, nó nhận diện `catalog-service` là **service ID**, yêu cầu chọn một `ServiceInstance`, rồi gửi request đến URI của instance được chọn. Ví dụ, nếu chọn `catalog-2`, đích gọi sẽ trở thành:

~~~http
GET http://10.0.1.22:8082/products/42
~~~

Dù URL ban đầu trông giống một URL HTTP bình thường, phần hostname `catalog-service` ở đây là định danh logic để LoadBalancer tra cứu instance; không cần DNS của hệ điều hành phân giải `catalog-service` thành địa chỉ IP theo cách thông thường khi integration hoạt động đúng.

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ<br/>GET http://catalog-service/products/42"]
    B["Tích hợp LoadBalancer<br/>interceptor / filter / HTTP adapter"]
    C["ServiceInstanceListSupplier<br/>danh sách ứng viên"]
    D["Bộ chọn LoadBalancer<br/>chọn catalog-2"]
    E["Tích hợp HTTP<br/>tạo URI đích"]
    F["HTTP transport<br/>DNS, TCP, TLS nếu cần"]
    G["Máy chủ catalog-2<br/>10.0.1.22:8082"]
    H["HTTP response hoặc lỗi"]
    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> A
~~~

Sơ đồ mô tả trách nhiệm ở mức khái niệm. Trong hiện thực, integration có thể phối hợp bước lựa chọn và thực thi qua nhiều interface hoặc adapter khác nhau.

## 2. Phần chọn bản sao: từ service ID tới ServiceInstance

**Đầu vào** của quá trình lựa chọn thường là service ID (ví dụ `catalog-service`), có thể kèm ngữ cảnh request để áp dụng chính sách định tuyến. **Đầu ra** là một `ServiceInstance` đại diện cho endpoint đã được chọn, hoặc kết quả cho biết không có instance phù hợp.

Ba trách nhiệm chính ở phần này:

1. **Cung cấp ứng viên:** `ServiceInstanceListSupplier` trả về danh sách instance cho service ID. Dữ liệu có thể đến từ `DiscoveryClient`, cấu hình tĩnh hoặc một nguồn tùy biến.
2. **Lọc hoặc sắp xếp ứng viên:** supplier hoặc chính sách bổ sung có thể áp dụng health check, ưu tiên zone, hint, metadata hay cache.
3. **Chọn một instance:** bộ chọn có thể dùng round-robin hoặc một chiến lược khác phù hợp với ứng dụng.

Ví dụ danh sách supplier cung cấp:

~~~text
catalog-service
  ├─ catalog-1  10.0.1.21:8081
  └─ catalog-2  10.0.1.22:8082

Kết quả chọn: catalog-2
~~~

Kết quả này cho biết **nên gọi đích nào**, nhưng chưa khẳng định rằng kết nối đã được thiết lập hay request HTTP đã đến máy chủ.

### API thể hiện ranh giới lựa chọn

Trong mô hình reactive, LoadBalancer cho phép thực hiện lựa chọn với `ReactorServiceInstanceLoadBalancer`, trả về một `Mono<Response<ServiceInstance>>`:

~~~java
// Minh họa dạng API, không phải ứng dụng hoàn chỉnh.
Mono<Response<ServiceInstance>> result = loadBalancer.choose();
~~~

`Response<ServiceInstance>` ở đây là **kết quả lựa chọn instance của LoadBalancer**, không phải `ClientResponse`, `ResponseEntity` hay mã HTTP do máy chủ trả về. Việc nhận được `Response<ServiceInstance>` hợp lệ không có nghĩa backend đã xử lý request thành công.

Với phần tích hợp blocking, các API như `LoadBalancerClient.choose(serviceId)` cũng cho phép chọn đích. Một số API của integration còn có phương thức điều phối thực thi request, nhưng trách nhiệm chọn instance và trách nhiệm gửi HTTP vẫn cần được phân biệt khi thiết kế, kiểm thử và chẩn đoán lỗi.

## 3. Phần thực thi HTTP: từ instance tới phản hồi

Khi đã có `ServiceInstance`, thành phần tích hợp HTTP xây dựng địa chỉ đích rồi chuyển request cho HTTP client bên dưới. Các công việc thường thuộc phần này gồm:

- Ghép địa chỉ `scheme://host:port` của instance với path, query và dữ liệu của request.
- Tạo và gửi HTTP headers, body, cookies, thông tin xác thực phù hợp.
- Thiết lập kết nối TCP, thực hiện TLS handshake nếu dùng HTTPS và quản lý connection pool.
- Đọc response headers, response body, mã trạng thái hoặc lỗi trong quá trình truyền.
- Áp dụng timeout, hủy request và đóng/thu hồi tài nguyên theo cơ chế HTTP client.

Các thao tác này được thực hiện bởi HTTP client và transport đang sử dụng, ví dụ hạ tầng HTTP bên dưới `RestClient`, Reactor Netty hoặc một `Client` của OpenFeign. Spring Cloud LoadBalancer không tự biến thành một HTTP server hoặc một network transport cho mọi loại client.

Điểm cần lưu ý: một supplier có thể tự thực hiện **HTTP health check** để thăm dò trạng thái instance. Đây là những request kiểm tra riêng của supplier, không đồng nghĩa LoadBalancer chịu trách nhiệm vận chuyển request nghiệp vụ đã chọn đích.

## 4. Bảng phân định trách nhiệm

| Vấn đề | Thành phần chịu trách nhiệm chính | Ý nghĩa thực tế |
|---|---|---|
| Service ID ánh xạ sang bản sao nào | Discovery và `ServiceInstanceListSupplier` | Kiểm tra dữ liệu registry và danh sách ứng viên |
| Instance nào được chọn | Thuật toán/policy LoadBalancer | Cấu hình round-robin, ưu tiên zone hoặc thuật toán khác |
| URL logic được chuyển thành URL đích | Adapter/interceptor/filter tích hợp LoadBalancer | Giữ thông tin request và thay địa chỉ service ID bằng URI instance |
| Mở kết nối, TCP và TLS | HTTP client/transport | Xem cấu hình network, SSL, connection pool |
| Connect timeout, response/read timeout | HTTP client/transport và cấu hình tương ứng | Timeout phù hợp với hành vi gọi dịch vụ |
| Mã 4xx/5xx từ backend | HTTP server và tầng xử lý response của client | Phân biệt lỗi ứng dụng và lỗi kết nối |
| Retry một lần gọi | Cơ chế retry được cấu hình | Có thể cần gọi lại HTTP và chọn instance khác |
| Lọc instance không khỏe | Registry/supplier/health check theo cấu hình | Không mặc định bảo đảm mọi instance đăng ký đều sẵn sàng |
| Metrics, logs, tracing | Tầng LoadBalancer và HTTP client/observability | Ghi nhận cả đích đã chọn lẫn kết quả request |

Một ứng dụng thường cần cấu hình **cả hai phía**: lựa chọn instance hợp lý và HTTP client có timeout, pool, giám sát lỗi phù hợp.

## 5. Vì sao cần adapter cho RestClient, WebClient và OpenFeign?

Ba HTTP client đều có thể gọi bằng service ID nhưng sử dụng cơ chế tích hợp khác nhau. Điểm chung là adapter nằm giữa API HTTP client và bộ chọn instance.

### RestClient: chọn đích trước khi HTTP client thực hiện request

Với Spring Framework `RestClient`, một `RestClient.Builder` được đánh dấu `@LoadBalanced` có thể được Spring Cloud tích hợp cơ chế cân bằng tải cho các request có hostname logic.

Ví dụ cấu hình:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class CatalogHttpConfiguration {

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Sử dụng builder này để gọi theo service ID:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient restClient;

    CatalogGateway(
            @Qualifier("catalogRestClientBuilder") RestClient.Builder builder
    ) {
        this.restClient = builder.baseUrl("http://catalog-service").build();
    }

    ProductDto getProduct(long id) {
        return restClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);
    }
}

record ProductDto(long id, String name) {}
~~~

Ví dụ giả định dự án dùng các phiên bản Spring Boot/Spring Cloud có hỗ trợ `RestClient` và có dependency `spring-cloud-starter-loadbalancer` cùng nguồn cung cấp instance phù hợp. Cấu hình `@LoadBalanced` gắn hành vi chọn instance vào luồng request; mã nghiệp vụ chỉ cần sử dụng URL logic.

Sau bước lựa chọn, HTTP request vẫn được gửi qua request factory và HTTP transport mà `RestClient` sử dụng. Đổi thuật toán LoadBalancer không tự thay đổi connect timeout hoặc cách quản lý connection pool.

### WebClient: chọn đích trong chuỗi filter reactive

Với `WebClient`, integration thường sử dụng `@LoadBalanced WebClient.Builder` hoặc các thành phần filter tương ứng. Filter nhận request theo URL logic, trao đổi với LoadBalancer để chọn instance, dựng URL đích rồi cho request tiếp tục qua chuỗi `ExchangeFunction` và HTTP connector.

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveClientConfiguration {

    @Bean("catalogWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`WebClient` quản lý bất đồng bộ và backpressure ở phần HTTP client/connector; LoadBalancer cung cấp kết quả lựa chọn instance cho luồng đó. Nếu request bị timeout khi chờ response từ backend, đây không mặc nhiên là lỗi ở thuật toán chọn instance.

### OpenFeign: LoadBalancer phối hợp với Feign Client

Với Spring Cloud OpenFeign, interface Feign mô tả API bằng annotation. Khi cấu hình sử dụng service name và có Spring Cloud LoadBalancer, integration có thể dùng `FeignBlockingLoadBalancerClient` để chọn instance và chuyển request tới Feign `Client` thực thi HTTP.

Ví dụ:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/products/{id}")
    ProductDto getProduct(@PathVariable("id") long id);
}
~~~

Feign phụ trách xây dựng request từ interface và chuyển việc truyền HTTP cho `Client` được cấu hình. LoadBalancer quyết định đích instance cho request đó. Khi điều chỉnh `connectTimeout` và `readTimeout` của Feign, người phát triển đang cấu hình hành vi gọi HTTP, không thay đổi thuật toán chọn instance.

## 6. Thử nghiệm đơn giản để quan sát ranh giới

Để hình dung rõ hai giai đoạn, có thể chạy hai bản sao của dịch vụ trên localhost và cấu hình `SimpleDiscoveryClient` cho ứng dụng gọi:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
~~~

Giả sử cả hai bản sao đều phục vụ `GET /products/42`, nhưng mỗi bản sao ghi log một instance ID khác nhau.

Khi `CatalogGateway` dùng `RestClient` được tích hợp LoadBalancer, một request có thể trải qua các sự kiện:

~~~text
1. Ứng dụng gọi        http://catalog-service/products/42
2. Supplier cung cấp   [127.0.0.1:8081, 127.0.0.1:8082]
3. LoadBalancer chọn   127.0.0.1:8082
4. HTTP client gửi     http://127.0.0.1:8082/products/42
5. Server xử lý        GET /products/42
6. HTTP client nhận    HTTP/1.1 200 OK + response body
~~~

Bước 3 cho biết **instance được chọn**. Bước 6 cho biết **kết quả thực thi HTTP**. Hai kết quả có thể thành công hoặc thất bại độc lập theo những cách khác nhau.

Với ví dụ localhost, các bản sao và client phải chạy trên cùng máy hoặc cùng không gian mạng có thể truy cập `127.0.0.1`. Trong Docker/Kubernetes, cần thay URI bằng host và port có thể truy cập từ chính môi trường của client.

## 7. Phân loại lỗi theo giai đoạn

Một lỗi “không gọi được dịch vụ” có thể xảy ra trước hoặc sau khi đã chọn được instance.

| Hiện tượng | Giai đoạn dễ phát sinh | Hướng điều tra |
|---|---|---|
| Không có instance cho service ID | Discovery, supplier hoặc selection | Kiểm tra service ID, registry, health filtering, cache |
| Danh sách còn instance đã dừng | Discovery/cache/health filtering | Kiểm tra thời gian hết hạn, đồng bộ và sức khỏe instance |
| URI đích không hợp lệ | Adapter hoặc dữ liệu `ServiceInstance` | Kiểm tra host, port, scheme và path |
| `Connection refused` | HTTP transport | Kiểm tra server có lắng nghe cổng tương ứng hay không |
| DNS/TLS handshake lỗi | HTTP transport | Kiểm tra DNS, cấu hình TLS và chứng chỉ cho đích được gọi |
| Connect timeout | HTTP transport | Kiểm tra đường mạng, connect timeout, độ trễ mở kết nối |
| Read/response timeout | HTTP transport hoặc xử lý chậm ở backend | Kiểm tra request, tải backend và thời gian chờ |
| HTTP 404 từ server | Thực thi HTTP/ứng dụng backend | Kiểm tra đường dẫn và API thực tế; không quy ngay cho LoadBalancer |
| HTTP 500 từ server | Xử lý nghiệp vụ backend | Quan sát log/traces phía server |
| HTTP 503 do không có server | Có thể do adapter LoadBalancer trả về | Xác minh request có thực sự đến backend hay bị chặn vì danh sách rỗng |

Tùy loại client và cấu hình, lỗi không có instance có thể được thể hiện thành HTTP 503, 404 (khi cấu hình dùng 404), hoặc exception ở phía client. Vì vậy, cần dựa vào loại HTTP client, exception và log của integration để xác định nguyên nhân, thay vì suy ra giai đoạn lỗi chỉ từ mã trạng thái.

### Trường hợp 1: Chọn được instance, backend trả HTTP 500

Nếu LoadBalancer đã chọn `catalog-2` và HTTP client nhận `500 Internal Server Error`, việc lựa chọn đích đã diễn ra. Lỗi 500 đến từ một lần thực thi HTTP hoặc từ hệ thống trung gian/backend trên đường đi. Hướng xử lý là truy vết response, log ứng dụng và chính sách retry nếu có.

### Trường hợp 2: Danh sách instance rỗng

Nếu supplier cung cấp danh sách rỗng, LoadBalancer không có đích để lựa chọn. Adapter có thể trả lỗi ngay trước khi tạo kết nối HTTP tới `catalog-service`. Tăng read timeout của HTTP client sẽ không giúp tìm ra instance mới; cần kiểm tra discovery, supplier và trạng thái đăng ký.

### Trường hợp 3: Chọn đúng instance nhưng mất kết nối

Nếu instance còn được liệt kê nhưng đã dừng, LoadBalancer có thể chọn một endpoint không còn truy cập được. Lỗi kết nối phát sinh tại transport. Cần sửa dữ liệu discovery/cache hoặc tăng khả năng lọc endpoint lỗi; đồng thời dùng timeout và retry hợp lý để giới hạn tác động của sự cố.

## 8. Retry và timeout nằm ở ranh giới nào?

**Timeout** thường giới hạn thời gian cho các hoạt động HTTP, ví dụ mở kết nối hoặc chờ phản hồi. Tên thuộc tính và ngữ nghĩa chính xác phụ thuộc HTTP client (RestClient request factory, WebClient connector hay Feign client). Một timeout kết nối ngắn không có nghĩa thuật toán round-robin sẽ đổi instance nhanh hơn; đây là hai cơ chế khác nhau.

**Retry** là hành vi có điều kiện thực hiện lại request sau lỗi. Tùy tầng retry được cấu hình, một lần thử lại có thể:

- Gọi lại cùng instance.
- Yêu cầu LoadBalancer chọn instance khác.
- Bị bỏ qua vì lỗi không nằm trong nhóm được phép retry.

Một lần gọi HTTP **không tự động** được retry chỉ vì ứng dụng có Spring Cloud LoadBalancer. Phải xem cấu hình retry của integration, retry policy và HTTP client thực tế.

Ví dụ, nếu request tới `catalog-2` bị timeout, chiến lược retry có thể chọn `catalog-1` ở lần sau **khi đã bật và cấu hình retry phù hợp**. Với thao tác có tác dụng phụ như tạo đơn hàng hoặc thanh toán, retry có thể tạo xử lý trùng nếu request đầu tiên đã được server tiếp nhận; cần cân nhắc tính idempotent, idempotency key và điều kiện retry.

### Health check khác retry

Health check được dùng để đánh giá hoặc lọc ứng viên **trước những lần chọn đích**. Retry phản ứng với lỗi **trong một quá trình gọi**. Health check không thay thế retry, còn retry không chữa được danh sách discovery liên tục chứa instance sai địa chỉ.

## 9. Quan sát cả quyết định định tuyến lẫn kết quả HTTP

Một hệ thống có thể ghi nhận LoadBalancer chọn instance thành công nhưng HTTP request vẫn thất bại. Để phân tích chính xác, nên phân biệt dữ liệu theo từng giai đoạn:

| Tại thời điểm lựa chọn | Tại thời điểm thực thi HTTP |
|---|---|
| Service ID được gọi | URI đích thực tế |
| Số lượng ứng viên | Thời gian kết nối và thời gian phản hồi |
| Instance ID/host/port được chọn | HTTP status hoặc loại exception |
| Chính sách chọn hoặc bộ lọc áp dụng | Số lần retry, timeout và tổng thời gian gọi |
| Có hay không có instance phù hợp | Endpoint nào thực sự nhận request |

Ví dụ log mong muốn ở mức minh họa:

~~~text
requestId=abc123 serviceId=catalog-service candidates=2 selected=catalog-2
requestId=abc123 target=http://10.0.1.22:8082/products/42 status=200 durationMs=45
~~~

Nếu lần gọi thất bại, log theo dạng tương tự giúp phân biệt “không có instance” với “đã chọn instance nhưng kết nối bị từ chối”. Trace ID/correlation ID cho phép ghép các sự kiện ở phía client, proxy và backend nếu hệ thống observability được cấu hình đầy đủ.

Không nên ghi các giá trị nhạy cảm như access token, cookie hoặc toàn bộ payload chứa dữ liệu cá nhân chỉ để chẩn đoán LoadBalancer.

## 10. Ranh giới này giúp thiết kế và kiểm thử thế nào?

Khi viết kiểm thử, có thể kiểm tra các phần tương đối độc lập:

1. **Selection test:** cung cấp danh sách instance giả định cho supplier và xác minh bộ chọn dùng đúng chính sách. Không cần gọi HTTP thật.
2. **Adapter test:** xác minh URL chứa service ID được chuyển sang endpoint vật lý phù hợp trong luồng tích hợp.
3. **HTTP client test:** dùng server giả lập trả 200, 404, 500 hoặc mô phỏng chậm để kiểm tra parsing, timeout và xử lý lỗi.
4. **Integration test:** chạy nhiều instance, thử dừng một instance và quan sát danh sách discovery, quyết định chọn instance và kết quả request.

Không nên dùng chỉ số “request thành công” để kết luận LoadBalancer đã chọn đúng instance theo chính sách. Request có thể thành công dù thuật toán định tuyến lệch, hoặc thất bại do backend dù quyết định chọn instance hoàn toàn hợp lệ.

Khi hệ thống có lỗi, một chuỗi câu hỏi hữu ích là: **Service ID có được phân giải thành danh sách ứng viên không? LoadBalancer chọn instance nào? Adapter dựng URL nào? HTTP transport kết nối và nhận response ra sao?** Mỗi câu hỏi định vị một ranh giới trách nhiệm cụ thể, giúp điều chỉnh đúng thành phần để giao tiếp giữa các dịch vụ ổn định hơn.

Spring Cloud LoadBalancer cung cấp sự linh hoạt để thay đổi thuật toán và nguồn `ServiceInstance` mà vẫn giữ cách gọi theo service ID của mã nghiệp vụ. HTTP client tiếp tục chịu trách nhiệm kết nối, timeout và truyền request/response. Tách bạch hai phần là nền tảng để cấu hình discovery, health check, retry và quan sát lỗi chính xác trong hệ thống microservices.

