# Phân biệt RestTemplate gọi tên dịch vụ và gọi URL trực tiếp

Trong ứng dụng Spring Boot sử dụng `RestTemplate`, hai lời gọi có vẻ giống nhau có thể đi qua **hai cơ chế định tuyến khác nhau**:

- **Gọi theo tên dịch vụ:** client sử dụng service ID như `catalog-service` và một `RestTemplate` được tích hợp **Spring Cloud LoadBalancer**. LoadBalancer lấy danh sách `ServiceInstance`, chọn một bản sao rồi chuyển request đến địa chỉ cụ thể.
- **Gọi URL trực tiếp:** client sử dụng địa chỉ đích thực tế, chẳng hạn `http://10.0.1.21:8081`, thông qua một `RestTemplate` thông thường. Địa chỉ trong URL được HTTP client và hạ tầng DNS/mạng xử lý mà không cần Spring Cloud LoadBalancer chọn `ServiceInstance`.

Điểm quyết định **không chỉ nằm ở chuỗi URL**. Cùng một URL `http://catalog-service/products` có thể được diễn giải khác nhau tùy **bean `RestTemplate` đang dùng**: bean có `@LoadBalanced` coi `catalog-service` là service ID; bean thông thường coi đó là hostname cần phân giải bằng các cơ chế mạng đang có.

Bài học thuộc chương **RestTemplate**, tập trung vào cách nhận biết luồng gọi, cấu hình bean đúng, kiểm chứng kết quả và tránh nhầm lẫn giữa client-side load balancing với gọi một endpoint cố định.

## 1. Hai URL và hai cách xác định đích

Giả sử `order-service` cần gọi `catalog-service`. Hệ thống đang chạy hai instance:

| Thuộc tính | Instance 1 | Instance 2 |
|---|---|---|
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-1` | `catalog-2` |
| URI | `http://10.0.1.21:8081` | `http://10.0.1.22:8081` |

Lời gọi theo service ID:

~~~java
Product product = loadBalancedRestTemplate.getForObject(
        "http://catalog-service/products/{id}",
        Product.class,
        42L
);
~~~

Mã gọi không chỉ định instance nào sẽ nhận request. LoadBalancer dựa vào service ID `catalog-service`, lấy danh sách ứng viên, rồi lựa chọn một instance. Ví dụ request có thể đi tới `http://10.0.1.22:8081/products/42`.

Lời gọi theo địa chỉ vật lý:

~~~java
Product product = directRestTemplate.getForObject(
        "http://10.0.1.21:8081/products/{id}",
        Product.class,
        42L
);
~~~

Client đã chỉ định đích `10.0.1.21:8081`. Trong lời gọi này, Spring Cloud LoadBalancer không chọn giữa `catalog-1` và `catalog-2` vì `directRestTemplate` là bean thông thường.

~~~mermaid
flowchart TD
    A["Ứng dụng Order Service"]
    B["RestTemplate có @LoadBalanced"]
    C["RestTemplate thông thường"]
    D["http://catalog-service/products/42"]
    E["Spring Cloud LoadBalancer"]
    F["ServiceInstanceListSupplier"]
    G["catalog-1 hoặc catalog-2"]
    H["http://10.0.1.21:8081/products/42"]
    I["HTTP transport, DNS/TCP/TLS"]
    J["Instance được chọn"]
    A --> B --> D --> E
    E --> F --> E
    E --> G --> I
    A --> C --> H --> I
    I --> J
~~~

Sơ đồ diễn tả sự khác nhau ở **bước xác định endpoint**. Cả hai cách cuối cùng đều dùng HTTP transport để gửi request; riêng cách gọi theo service ID có thêm bước chọn `ServiceInstance` ở phía client.

## 2. Vai trò thực sự của @LoadBalanced

Spring Cloud Commons cho phép khai báo `RestTemplate` là một load-balanced client bằng annotation `@LoadBalanced` trên bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Với cấu hình phù hợp và dependency `spring-cloud-starter-loadbalancer`, Spring Cloud tích hợp interceptor LoadBalancer vào bean này. Interceptor lấy hostname của URL logic làm **service ID** và phối hợp với `BlockingLoadBalancerClient` để chọn địa chỉ vật lý.

Khi gọi:

~~~text
http://catalog-service/products/42
~~~

hostname `catalog-service` là tên logic. HTTP transport không cần tự phân giải hostname đó qua DNS thành một máy chủ duy nhất; adapter LoadBalancer chọn instance và tạo đích thực tế trước khi request được truyền.

Để cơ chế này hoạt động, cần có cả **bean được cấu hình load-balanced** và **nguồn cung cấp instance** tương ứng. Nguồn đó có thể đến từ Eureka, Consul, một integration discovery khác hoặc danh sách tĩnh dùng `SimpleDiscoveryClient`.

### Điều gì xảy ra với một RestTemplate không có @LoadBalanced?

~~~java
@Bean
RestTemplate directRestTemplate() {
    return new RestTemplate();
}
~~~

`directRestTemplate` không tự tích hợp Spring Cloud LoadBalancer chỉ vì project có dependency LoadBalancer. Nếu gọi `http://catalog-service/products/42` qua bean này, hostname `catalog-service` sẽ được xử lý như tên mạng bình thường. Request chỉ thành công nếu DNS, hosts file, service mesh hoặc hạ tầng khác giúp truy cập hostname đó.

Nếu hệ thống Kubernetes cung cấp DNS cho `catalog-service`, bean trực tiếp vẫn có thể gọi thành công, nhưng việc chọn đích là chức năng của DNS/Kubernetes Service hoặc proxy liên quan, **không phải quá trình chọn `ServiceInstance` của Spring Cloud LoadBalancer trong bean này**.

## 3. Cấu hình hai RestTemplate song song trong một ứng dụng

Trên thực tế, một ứng dụng có thể cần cả hai kiểu gọi: gọi microservice bằng service ID và gọi URL cố định của một hệ thống bên ngoài hoặc một endpoint quản trị.

Có thể khai báo rõ hai bean:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class HttpClientConfiguration {

    @Bean("serviceRestTemplate")
    @LoadBalanced
    RestTemplate serviceRestTemplate() {
        return new RestTemplate();
    }

    @Bean("directRestTemplate")
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

`@Primary` làm bean thường được ưu tiên nếu một vị trí inject `RestTemplate` mà không có qualifier. Với những thành phần cần chắc chắn dùng đúng hành vi, nên **inject bằng `@Qualifier`**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
class ProductGateway {

    private final RestTemplate serviceRestTemplate;
    private final RestTemplate directRestTemplate;

    ProductGateway(
            @Qualifier("serviceRestTemplate") RestTemplate serviceRestTemplate,
            @Qualifier("directRestTemplate") RestTemplate directRestTemplate
    ) {
        this.serviceRestTemplate = serviceRestTemplate;
        this.directRestTemplate = directRestTemplate;
    }

    Product getViaServiceId(long id) {
        return serviceRestTemplate.getForObject(
                "http://catalog-service/products/{id}",
                Product.class,
                id
        );
    }

    Product getFromSpecificInstance(long id) {
        return directRestTemplate.getForObject(
                "http://10.0.1.21:8081/products/{id}",
                Product.class,
                id
        );
    }
}

record Product(long id, String name) {}
~~~

Hai phương thức trên minh họa hai mục đích khác nhau:

- `getViaServiceId()` thích hợp khi muốn client tự cân bằng giữa các bản sao đang được cung cấp.
- `getFromSpecificInstance()` phù hợp khi cố ý nhắm tới một endpoint xác định, ví dụ kiểm tra một instance đang cần chẩn đoán.

Ví dụ giả định endpoint trả JSON tương thích với record `Product` và ứng dụng dùng Java hỗ trợ record. `RestTemplate` cũng có thể được tạo bằng `RestTemplateBuilder` để tận dụng cấu hình của Spring Boot; điều quan trọng vẫn là phân biệt builder/client có tích hợp LoadBalancer với builder/client thông thường.

### Vì sao không dùng một bean cho cả hai loại URL?

Bean được gắn `@LoadBalanced` có interceptor xử lý hostname như service ID. Vì vậy, nếu truyền `http://10.0.1.21:8081/products` hoặc `http://localhost:8081/products` cho bean này, đừng mặc định nó sẽ bỏ qua LoadBalancer: interceptor có thể cố phân giải `10.0.1.21` hoặc `localhost` như một service ID và báo không tìm thấy instance.

Hãy dùng **RestTemplate thường cho URL vật lý**. Nếu yêu cầu đặc biệt cần kết hợp hai kiểu trong một client, phải thiết kế rõ cơ chế lựa chọn đường đi thay vì dựa vào giả định interceptor tự nhận biết URL nào là “trực tiếp”.

## 4. Cơ chế từ service ID tới HTTP request

Với bean `@LoadBalanced`, luồng gọi thông thường diễn ra như sau:

1. Mã nghiệp vụ truyền URL `http://catalog-service/products/42`.
2. `RestTemplate` tạo request và chuyển qua các interceptor đã cấu hình.
3. Interceptor LoadBalancer nhận service ID từ hostname logic.
4. `BlockingLoadBalancerClient` yêu cầu LoadBalancer chọn `ServiceInstance`; chuỗi `ServiceInstanceListSupplier` cung cấp các ứng viên phù hợp từ discovery/cache/filter.
5. Thành phần tích hợp xây dựng URL đích theo host, port và thông tin secure của instance đã chọn, đồng thời giữ path, query và các phần request cần thiết.
6. HTTP request factory và transport của `RestTemplate` thực hiện kết nối, gửi dữ liệu và nhận response.

~~~mermaid
sequenceDiagram
    participant App as ProductGateway
    participant RT as @LoadBalanced RestTemplate
    participant LB as BlockingLoadBalancerClient
    participant Supplier as ServiceInstanceListSupplier
    participant HTTP as HTTP transport
    participant Catalog as Catalog instance
    App->>RT: GET http://catalog-service/products/42
    RT->>LB: Chọn instance cho catalog-service
    LB->>Supplier: Lấy danh sách ứng viên
    Supplier-->>LB: catalog-1, catalog-2
    LB-->>RT: catalog-2: 10.0.1.22:8081
    RT->>HTTP: GET http://10.0.1.22:8081/products/42
    HTTP->>Catalog: Gửi HTTP request
    Catalog-->>HTTP: HTTP response
    HTTP-->>App: Dữ liệu hoặc exception
~~~

Điểm cốt lõi là **chọn instance và thực thi HTTP là hai giai đoạn khác nhau**. LoadBalancer chọn từ danh sách ứng viên; nó không tự thay thế cơ chế TCP, TLS, socket hoặc đọc body của `RestTemplate`.

## 5. Khi gọi trực tiếp, URL được giải quyết ra sao?

Trong một `RestTemplate` thường, phần scheme, host và port của URL xác định nơi gửi request:

~~~text
https://api.partner.example:8443/v1/items/42
│       │                    │    └─ Path
│       │                    └────── Port
│       └─────────────────────────── Hostname
└─────────────────────────────────── Scheme
~~~

Với hostname, transport hoặc hệ điều hành có thể dùng DNS/hosts để phân giải địa chỉ; với IP literal, không cần bước DNS cho chính hostname đó. Proxy, service mesh và network load balancer vẫn có thể định tuyến tiếp ở tầng hạ tầng.

Điều này tạo ra một phân biệt quan trọng:

| Tình huống | Có dùng chọn `ServiceInstance` của Spring Cloud? | Ai xác định đích? |
|---|---|---|
| `@LoadBalanced RestTemplate` gọi `http://catalog-service` | Có | LoadBalancer và supplier theo service ID |
| `RestTemplate` thường gọi `http://10.0.1.21:8081` | Không | Địa chỉ IP/port trong URL |
| `RestTemplate` thường gọi `https://api.partner.example` | Không | DNS, proxy hoặc hạ tầng mạng |
| `RestTemplate` thường gọi Kubernetes Service DNS | Không ở client này | Kubernetes Service/DNS/network |
| `@LoadBalanced RestTemplate` gọi một host vật lý không được đăng ký là service ID | Vẫn có thể đi qua LoadBalancer | Có nguy cơ lookup sai service ID và thất bại |

Không phải mọi lần gọi trực tiếp đều “không có cân bằng tải”. URL trực tiếp có thể chỉ tới một reverse proxy, API gateway hoặc network load balancer. Khác biệt là **Spring Cloud LoadBalancer của `RestTemplate` không chọn instance trong lời gọi đó**.

## 6. Ví dụ chạy hai bản sao mà không cần registry riêng

Để học cơ chế gọi theo tên dịch vụ, có thể dùng `SimpleDiscoveryClient` khai báo danh sách `ServiceInstance` tĩnh:

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

Giả sử hai tiến trình `catalog-service` chạy trên cùng máy với ứng dụng gọi, lần lượt ở cổng `8081` và `8082`. Cả hai đều có endpoint `GET /whoami` trả instance ID.

Gọi theo tên dịch vụ:

~~~java
String selectedInstance = serviceRestTemplate.getForObject(
        "http://catalog-service/whoami",
        String.class
);
~~~

Khi LoadBalancer dùng round-robin và hai instance đều ở danh sách ứng viên, các lần gọi liên tiếp có thể trả về luân phiên hai ID. Thứ tự chính xác còn phụ thuộc trạng thái thuật toán, danh sách instance và concurrency; không nên khẳng định lần gọi thứ nhất chắc chắn tới `8081`.

Gọi đích cụ thể:

~~~java
String fixedInstance = directRestTemplate.getForObject(
        "http://127.0.0.1:8081/whoami",
        String.class
);
~~~

Lời gọi này luôn yêu cầu kết nối tới `127.0.0.1:8081`. Nếu instance ở cổng đó ngừng phục vụ, `directRestTemplate` không tự chuyển sang `8082` nhờ Spring Cloud LoadBalancer.

**Lưu ý về môi trường:** `127.0.0.1` trỏ về chính máy hoặc network namespace của client. Với Docker hoặc Kubernetes, cần dùng hostname/địa chỉ có thể truy cập từ môi trường chạy ứng dụng gọi; `localhost` trong container không tự trỏ sang container khác.

### Sự khác biệt khi một instance dừng

| Điều kiện | Gọi bằng service ID | Gọi URL cố định |
|---|---|---|
| Cả hai instance hoạt động | Có thể phân phối qua nhiều bản sao | Luôn gọi endpoint được chỉ định |
| `8081` dừng và đã bị loại khỏi supplier | Có thể chọn `8082` | Gọi `8081` vẫn lỗi |
| `8081` dừng nhưng còn trong cache | Vẫn có khả năng chọn `8081` và lỗi | Gọi `8081` lỗi |
| Discovery trả danh sách rỗng | Không có `ServiceInstance` để chọn | Vẫn thử kết nối URL được chỉ định |
| Cấu hình zone/hint trong LoadBalancer thay đổi | Có thể thay đổi danh sách ứng viên | Không chịu ảnh hưởng bởi policy này |

Trong cấu hình tĩnh `SimpleDiscoveryClient`, việc dừng một server **không tự loại URI của nó khỏi YAML**. Muốn quan sát danh sách được cập nhật theo vòng đời instance, dùng service registry động hoặc supplier tùy biến phục vụ kiểm thử.

## 7. Các lỗi thường gặp và ý nghĩa của chúng

Hai loại `RestTemplate` có thể thất bại vì các nguyên nhân khác nhau, dù cùng gọi một đường dẫn API.

| Triệu chứng | Khi gọi service ID bằng bean load-balanced | Khi gọi URL bằng bean thường |
|---|---|---|
| Không tìm thấy instance | Sai service ID, discovery rỗng, supplier lọc hết ứng viên | Không có bước lookup instance |
| `UnknownHostException` | Có thể là hostname thật của instance được chọn không phân giải được; cần kiểm tra đích | Host trong URL không phân giải được qua DNS/hosts |
| `Connection refused` | Instance đã chọn không lắng nghe đúng host:port | Đích chỉ định không lắng nghe |
| Connect/read timeout | HTTP transport bị chậm hoặc backend không phản hồi đúng hạn | HTTP transport bị chậm hoặc backend không phản hồi |
| HTTP 404/500 | Đã nhận response từ backend hoặc trung gian; cần trace đích được chọn | Đã nhận response từ backend hoặc trung gian |
| Instance dừng nhưng vẫn được gọi | Có thể do discovery/cache/health check chưa cập nhật | URL vẫn cố định vào instance đã dừng |

Khi dùng `RestTemplate` với `DefaultResponseErrorHandler`, các HTTP status 4xx/5xx thường được chuyển thành exception, ví dụ `HttpClientErrorException` hoặc `HttpServerErrorException`. Lỗi transport thường được bọc thành `ResourceAccessException`, còn lỗi không có instance có thể đến từ tầng LoadBalancer dưới dạng exception hoặc response do integration xử lý tùy phiên bản/cấu hình.

Không nên kết luận lỗi “không có server” chỉ dựa trên HTTP 503: một proxy hoặc chính backend cũng có thể trả 503. Cần kiểm tra thông tin service ID, instance được chọn, loại exception và HTTP response thực tế.

### Sai bean RestTemplate

Một lỗi điển hình là inject `RestTemplate` thường rồi kỳ vọng URL logic tự chạy qua LoadBalancer:

~~~java
// Nếu đây là bean thường, host "catalog-service" được xử lý như DNS host.
directRestTemplate.getForObject(
        "http://catalog-service/whoami",
        String.class
);
~~~

Nếu không có DNS/hosts phù hợp, lời gọi sẽ thất bại vì không phân giải được hostname. Cách sửa là dùng bean `@LoadBalanced` và bảo đảm discovery cung cấp instance cho service ID.

### Dùng bean load-balanced với URL localhost hoặc IP

~~~java
// Không nên coi đây là lời gọi vật lý nếu bean có @LoadBalanced.
serviceRestTemplate.getForObject(
        "http://localhost:8081/whoami",
        String.class
);
~~~

Tùy cách integration hoạt động, `localhost` có thể bị coi là service ID. Cách sửa là sử dụng bean `directRestTemplate` cho endpoint cố định.

## 8. Timeout, retry và health check: khác biệt về phạm vi

Gọi theo service ID bổ sung bước chọn instance, nhưng điều đó **không tự cấu hình connect timeout, read timeout hoặc retry** cho mọi HTTP request.

Timeout của `RestTemplate` phụ thuộc `ClientHttpRequestFactory` và HTTP transport được chọn. Ví dụ minh họa khi dùng request factory đơn giản:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestTemplate;

SimpleClientHttpRequestFactory factory =
        new SimpleClientHttpRequestFactory();
factory.setConnectTimeout(2000); // 2 giây
factory.setReadTimeout(3000);    // 3 giây

RestTemplate restTemplate = new RestTemplate(factory);
~~~

Đoạn code cho thấy timeout thuộc phần thực thi HTTP; nó chưa tạo bean load-balanced. Muốn dùng trong LoadBalancer, có thể tạo bean `@LoadBalanced RestTemplate` với request factory được cấu hình phù hợp.

**Retry** phải được cấu hình và kiểm tra theo integration. Khi retry được hỗ trợ và bật, lần thử lại có thể cùng instance hoặc khác instance, tùy chính sách. Retry không tự đồng nghĩa danh sách discovery đã được làm mới; nếu cache vẫn còn instance chết, yêu cầu có thể tiếp tục chọn endpoint đó.

**Health check** thuộc nguồn cung cấp danh sách `ServiceInstance` hoặc registry/supplier đã cấu hình. Nếu endpoint không khỏe bị loại trước khi chọn, request có thể tránh bản sao lỗi. Nhưng chỉ gắn `@LoadBalanced` không có nghĩa mọi instance đều được probe HTTP health check ở mỗi request.

Khi gọi API thay đổi dữ liệu (như thanh toán, tạo đơn hàng), cần tính đến idempotency trước khi bật retry để tránh gửi lại tác vụ đã được backend xử lý.

## 9. Lựa chọn kiểu gọi theo yêu cầu thực tế

| Nhu cầu | Cách gọi phù hợp | Lý do |
|---|---|---|
| Giao tiếp giữa các microservice có nhiều instance | `@LoadBalanced RestTemplate` + service ID | Không phụ thuộc một IP/port cố định |
| Hệ thống thay đổi số lượng instance theo autoscaling | `@LoadBalanced RestTemplate` + discovery động | Supplier có thể nhận danh sách mới |
| Gọi API đối tác qua hostname công khai | `RestTemplate` thường + URL thực tế | Dùng DNS/TLS/proxy theo cấu hình mạng |
| Kiểm tra riêng một instance đang gặp lỗi | `RestTemplate` thường + URI instance | Đảm bảo request tới đúng endpoint cần chẩn đoán |
| Gọi một reverse proxy hoặc API gateway cố định | `RestTemplate` thường + URL gateway | Việc chọn backend có thể do gateway đảm nhiệm |
| Muốn dùng health, zone, hint routing theo Spring Cloud LoadBalancer | Bean load-balanced + service ID + supplier phù hợp | Chính sách tác động đến danh sách ứng viên |
| Muốn bỏ qua discovery để gọi địa chỉ đã biết | Bean thường + URL vật lý | HTTP client dùng địa chỉ chỉ định |

Một ứng dụng có thể kết hợp hai kiểu gọi, nhưng cần đặt tên bean và inject rõ ràng để tránh chọn nhầm client.

## 10. Thực hành kiểm tra luồng request

Có thể thực hành trong một ứng dụng đơn giản với hai server `catalog-service` ở cổng `8081`, `8082` và một client `order-service`:

1. Cấu hình hai bean `serviceRestTemplate` (`@LoadBalanced`) và `directRestTemplate` (`@Primary`) như mục 3.
2. Cấu hình `SimpleDiscoveryClient` cho service ID `catalog-service` trỏ tới hai instance.
3. Tạo endpoint `GET /whoami` ở mỗi instance để trả về tên hoặc cổng của nó.
4. Dùng `serviceRestTemplate.getForObject("http://catalog-service/whoami", String.class)` và ghi lại kết quả qua nhiều request.
5. Dùng `directRestTemplate.getForObject("http://127.0.0.1:8081/whoami", String.class)` và đối chiếu.
6. Thử cố ý gọi URL `http://catalog-service/whoami` qua bean thường trong môi trường không có DNS tương ứng để thấy sự khác biệt.
7. Tắt server `8081`, kiểm tra hành vi của lời gọi trực tiếp và lời gọi theo service ID. Cần nhớ danh sách tĩnh vẫn có URI `8081`; để thử failover sau khi cập nhật discovery, sửa cấu hình và khởi động lại client hoặc dùng discovery động.
8. Ghi log service ID, URI instance được chọn (nếu có), HTTP status, exception và thời gian gọi để phân biệt lỗi chọn đích với lỗi thực thi HTTP.

Khi kiểm tra kết quả, tránh suy luận “request thành công” tức là LoadBalancer đã được dùng. Request bằng bean thường qua DNS hoặc proxy cũng có thể thành công. Bằng chứng đúng nằm ở **bean được inject, interceptor LoadBalancer, service ID, danh sách ứng viên và endpoint thực sự được chọn**.

## 11. Checklist khi RestTemplate gọi sai đích

Trước khi sửa cấu hình, hãy xác minh lần lượt:

- Bean `RestTemplate` đang dùng có `@LoadBalanced` hay là bean thường?
- URL là service ID logic hay hostname/IP vật lý? Nó có đang được dùng với đúng bean không?
- Dependency `spring-cloud-starter-loadbalancer` và nguồn discovery có được cấu hình cho lời gọi theo service ID?
- Service ID trong URL có khớp tên đã đăng ký và supplier có trả danh sách instance không?
- Instance được chọn có host, port và scheme phù hợp môi trường mạng của client không?
- Lỗi phát sinh ở bước tìm instance, dựng URI, mở kết nối hay xử lý HTTP response?
- Retry, timeout và health check đã được cấu hình phù hợp và có thể quan sát hay chưa?
- Nếu có cả hai bean, `@Qualifier` hoặc `@Primary` đã được dùng rõ ràng để tránh injection sai?

**Nguyên tắc cần nhớ:** `@LoadBalanced RestTemplate` nhận service ID làm hostname logic để Spring Cloud LoadBalancer chọn một `ServiceInstance`. `RestTemplate` thông thường gửi request theo URL cụ thể và dùng các cơ chế mạng như DNS, proxy hoặc gateway để tới đích. Phân biệt đúng hai hành vi giúp ứng dụng gọi dịch vụ ổn định hơn và chẩn đoán chính xác lỗi discovery, cân bằng tải, timeout và kết nối.

**Tài liệu chính thức:**

- [Spring Cloud Commons – Spring RestTemplate as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#spring-resttemplate-as-a-loadbalancer-client)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

