# Gọi tên dịch vụ bằng HTTP client đã tích hợp LoadBalancer

## Mục tiêu và bối cảnh

Trong chương **Cân bằng tải** của module **SPRING_CLOUD_KUBERNETES**, ứng dụng có thể gọi một dịch vụ bằng tên logic thay vì gắn cố định IP của từng Pod:

~~~text
http://catalog-api/products/42
~~~

HTTP client đã tích hợp Spring Cloud LoadBalancer sẽ sử dụng tên `catalog-api` để tìm ứng viên, chọn đích và gửi request. Bài này hướng dẫn cấu hình client, sử dụng đúng bean và kiểm tra đường gọi thực tế.

Ví dụ dùng ứng dụng `order-service` gọi Kubernetes Service `catalog-api` trong namespace `demo`. Các Pod đích phục vụ HTTP trên cổng `8080`. IP và kết quả trả về trong bài chỉ là minh họa.

Ví dụ chính dùng Java 17 và `RestClient`. Dự án cần bộ phiên bản Spring Boot/Spring Cloud tương thích, có Spring Framework từ 6.1 trở lên và phiên bản Spring Cloud hỗ trợ tích hợp LoadBalancer với `RestClient.Builder`. Phần `WebClient` là lựa chọn cho luồng reactive.

## 1. Một URL, hai cách xử lý tên rất khác nhau

Xét cùng URL:

~~~text
http://catalog-api/products/42
~~~

| Client thực hiện lời gọi | Cách hiểu phần host |
| --- | --- |
| HTTP client thông thường | Host cần được resolver/DNS xử lý |
| HTTP client đã tích hợp Spring Cloud LoadBalancer | Tên dịch vụ để LoadBalancer lấy và chọn đích |

Trong Kubernetes, HTTP client thông thường có thể phân giải `catalog-api` thành ClusterIP nếu namespace và DNS phù hợp. Request vẫn thành công, nhưng đó chưa phải bằng chứng Spring Cloud LoadBalancer đã chọn một instance.

Với client đã tích hợp, tên logic được xử lý trước khi transport kết nối tới đích được chọn:

~~~mermaid
sequenceDiagram
    participant App as Mã nghiệp vụ
    participant Client as HTTP client tích hợp LoadBalancer
    participant LB as Spring Cloud LoadBalancer
    participant Source as Nguồn danh sách instance
    participant Target as Đích được chọn
    App->>Client: GET http://catalog-api/products/42
    Client->>LB: Chọn đích cho catalog-api
    LB->>Source: Lấy danh sách ứng viên
    Source-->>LB: host, port và metadata
    LB-->>Client: Một instance được chọn
    Client->>Target: GET /products/42
    Target-->>Client: Phản hồi HTTP
    Client-->>App: Dữ liệu sản phẩm
~~~

Trong mô hình này, cần đủ ba phần: **HTTP client được tích hợp, LoadBalancer có mặt và nguồn ứng viên hoạt động**. Chỉ có một trong ba chưa đủ.

Spring Cloud Commons hỗ trợ client tích hợp qua `@LoadBalanced` cho các loại client tương ứng; URL dùng tên dịch vụ logic để tạo địa chỉ gọi thực tế. [Tài liệu tích hợp HTTP client của Spring Cloud Commons](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)

## 2. POD và SERVICE quyết định đích mà client chọn

Spring Cloud Kubernetes LoadBalancer có hai chế độ:

| Chế độ | Ý nghĩa trong đường gọi |
| --- | --- |
| `POD` | Dùng DiscoveryClient để tìm instance cho tên dịch vụ và chọn đích từ danh sách đó |
| `SERVICE` | Tìm Kubernetes Service phù hợp và tạo đích theo tên DNS cùng cổng Service |

Trong ví dụ POD:

~~~text
URL logic:
http://catalog-api/products/42

Ứng viên:
10.42.1.21:8080
10.42.2.35:8080

Một đích sau lựa chọn:
http://10.42.2.35:8080/products/42
~~~

Trong mô hình SERVICE, đích có thể có dạng:

~~~text
http://catalog-api.demo.svc.cluster.local:8080/products/42
~~~

Sau đó cơ chế Service của Kubernetes tham gia chuyển tiếp tới backend. Miền `cluster.local` ở đây là giả định; cụm có thể dùng miền khác. [Tài liệu Kubernetes LoadBalancer](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html)

Hai chế độ không đồng nghĩa Spring luôn lựa chọn trực tiếp từng Pod. Muốn giải thích phân phối request, phải biết chế độ và đích thực tế được tạo ra.

Cũng cần phân biệt `type: LoadBalancer` của Kubernetes Service với Spring Cloud LoadBalancer. Một bên là cách Kubernetes công bố Service qua hạ tầng tương ứng; bên kia là thành phần lựa chọn đích trong ứng dụng Spring. Ví dụ trong bài dùng Service loại ClusterIP.

## 3. Chuẩn bị dịch vụ và nguồn discovery

### 3.1. Service đích

Giả định đã có các Pod `catalog-api` mang label `app: catalog-api`, lắng nghe `8080` và triển khai API sản phẩm. Service có thể được khai báo:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-api
  namespace: demo
spec:
  type: ClusterIP
  selector:
    app: catalog-api
  ports:
    - name: http
      port: 8080
      targetPort: 8080
~~~

Manifest này chỉ tạo đối tượng Service; nó không tự tạo ứng dụng đích.

Tên logic trong URL là `metadata.name` của Service mà discovery tìm thấy. Không mặc định lấy tên Deployment hoặc `spring.application.name` của ứng dụng đích nếu các giá trị đó khác tên Service.

### 3.2. Dependency phía gọi

Ví dụ chọn triển khai Fabric8 của Kubernetes LoadBalancer và Spring MVC cho ứng dụng gọi:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-fabric8-loadbalancer</artifactId>
</dependency>
~~~

Version phải được quản lý bởi bộ dependency tương thích của dự án. Nếu dùng Kubernetes Java Client, chọn starter tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-kubernetes-client-loadbalancer</artifactId>
</dependency>
~~~

Hai starter Kubernetes trên là hai lựa chọn triển khai; không thêm cả hai theo thói quen. Kiểm tra dependency thực tế để bảo đảm có LoadBalancer và discovery cần thiết, tránh nhiều triển khai cùng được kích hoạt ngoài ý muốn.

Nếu kiến trúc dùng HTTP DiscoveryClient qua Discovery Server, nguồn discovery và dependency sẽ khác ví dụ Fabric8 trực tiếp này. Cần bảo đảm LoadBalancer lấy đúng danh sách từ nguồn đã chọn; không tự thêm một Kubernetes client trực tiếp chỉ để sửa mọi lỗi của đường HTTP discovery.

### 3.3. Cấu hình minh họa

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    kubernetes:
      discovery:
        all-namespaces: false
        namespaces:
          - demo
        use-endpoint-slices: true
        include-not-ready-addresses: false
        primary-port-name: http
      loadbalancer:
        mode: POD
~~~

Cấu hình chọn namespace `demo`, nguồn EndpointSlice ở phiên bản hỗ trợ và cổng chính có tên `http`. ServiceAccount của ứng dụng đọc trực tiếp Kubernetes API phải có quyền tương ứng với Service, EndpointSlice và những tài nguyên khác mà tính năng được bật yêu cầu.

Nếu chuyển sang Endpoints, quyền và cấu hình phải phù hợp với nguồn đó. Nếu dùng Discovery Server, cấu hình phạm vi đọc Kubernetes và quyền đọc nguồn nằm ở server. [Tài liệu Kubernetes DiscoveryClient](https://docs.spring.io/spring-cloud-kubernetes/reference/discovery-client.html)

Ví dụ giả định ứng dụng chạy trong môi trường kích hoạt cấu hình Kubernetes phù hợp. Laptop đọc được danh sách PodIP qua API không có nghĩa mạng của laptop gọi được các IP đó.

## 4. Ví dụ chính: RestClient đã tích hợp LoadBalancer

`RestClient` là HTTP client đồng bộ. `WebClient` phục vụ mô hình reactive; `RestTemplate` xuất hiện trong nhiều hệ thống cũ. Chọn theo bộ phiên bản và mô hình xử lý của ứng dụng. [Tài liệu REST client của Spring Framework](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)

### 4.1. Khai báo builder do Spring quản lý

Tạo configuration trong package thuộc phạm vi component scan:

~~~java
package example.catalog;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestClient;

@Configuration
public class HttpClientsConfiguration {

    @Bean("internalRestClientBuilder")
    @LoadBalanced
    public RestClient.Builder internalRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean("externalRestClientBuilder")
    @Primary
    public RestClient.Builder externalRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

`@LoadBalanced` đánh dấu builder cần được hạ tầng Spring tích hợp LoadBalancer. Builder còn lại dành cho URL được gọi theo resolver/DNS thông thường. `@Primary` chọn builder thông thường khi có injection không chỉ định qualifier; mã gọi nội bộ vẫn phải chỉ định rõ bean cần dùng.

Ví dụ giữ cấu hình tối thiểu để làm rõ đường gọi. Với ứng dụng thực tế, kết hợp các cơ chế cấu hình builder của Spring Boot phù hợp phiên bản để giữ timeout, observability và customizer cần thiết.

Không tạo mới builder ngoài container rồi kỳ vọng annotation ở một nơi khác sẽ tự áp dụng cho nó.

### 4.2. Tạo client nghiệp vụ từ đúng builder

~~~java
package example.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogClient {

    private final RestClient restClient;

    public CatalogClient(
            @Qualifier("internalRestClientBuilder")
            RestClient.Builder builder) {

        this.restClient = builder.clone()
                .baseUrl("http://catalog-api")
                .build();
    }

    public Product getProduct(long id) {
        return restClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
~~~

Đối tượng dữ liệu:

~~~java
package example.catalog;

public record Product(long id, String name) {
}
~~~

Giả định API đích có contract:

~~~http
GET /products/42
~~~

~~~json
{
  "id": 42,
  "name": "Bàn phím"
}
~~~

Các điểm chính:

- Constructor nhận builder đã được Spring quản lý và tích hợp.
- `@Qualifier` chỉ đích danh builder nội bộ.
- `clone()` tạo builder cho cấu hình client cụ thể, tránh sửa base URL trên builder dùng chung.
- `baseUrl("http://catalog-api")` giữ tên logic của Service.
- `/products/{id}` là đường dẫn API nghiệp vụ, không phải đường dẫn discovery.

Không tạo mới `RestClient` cho từng request. Ví dụ tạo một client dùng lại trong component.

### 4.3. Gọi từ controller phía order-service

~~~java
package example.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductLookupController {

    private final CatalogClient catalogClient;

    public ProductLookupController(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @GetMapping("/demo/products/{id}")
    public Product product(@PathVariable("id") long id) {
        return catalogClient.getProduct(id);
    }
}
~~~

Ứng dụng cần lớp khởi động Spring Boot thông thường quét được package `example.catalog` cùng cấu hình discovery tương ứng.

Khi người dùng gọi `GET /demo/products/42` vào `order-service`:

~~~text
ProductLookupController
    -> CatalogClient
    -> RestClient đã tích hợp
    -> LoadBalancer chọn đích cho catalog-api
    -> GET /products/42 tới đích
    -> giải mã JSON thành Product
~~~

Đoạn mã chưa bổ sung chính sách lỗi nghiệp vụ riêng. Mục đích là thể hiện đường gọi thành công và nơi diễn ra lựa chọn đích.

## 5. Phương án WebClient cho luồng reactive

Nếu dùng `WebClient`, dự án cần WebFlux client và Spring Cloud LoadBalancer phù hợp. Có thể dùng webflux starter theo kiến trúc dự án; việc dùng `WebClient` không tự buộc toàn bộ server phải đổi sang mô hình reactive.

Khai báo builder:

~~~java
package example.catalog;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReactiveHttpClientsConfiguration {

    @Bean("internalWebClientBuilder")
    @LoadBalanced
    public WebClient.Builder internalWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Client nghiệp vụ:

~~~java
package example.catalog;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Component
public class ReactiveCatalogClient {

    private final WebClient webClient;

    public ReactiveCatalogClient(
            @Qualifier("internalWebClientBuilder")
            WebClient.Builder builder) {

        this.webClient = builder.clone()
                .baseUrl("http://catalog-api")
                .build();
    }

    public Mono<Product> getProduct(long id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);
    }
}
~~~

Nếu dùng trong controller reactive, trả `Mono<Product>` để framework thực hiện subscription theo luồng xử lý. Chỉ tạo một `Mono` rồi bỏ đi không đồng nghĩa request HTTP đã được gửi.

Không gọi `block()` trên event loop để biến ví dụ thành đồng bộ. Nếu cần mô hình đồng bộ, dùng client đồng bộ ở nơi phù hợp.

Đây là lựa chọn thay thế cho `CatalogClient` chính khi xây luồng gọi tương ứng. Không cần triển khai cả hai chỉ để gọi cùng một API.

### Nhận diện RestTemplate trong mã hiện có

Với dự án đang dùng `RestTemplate`, nguyên tắc tương tự là tạo bean được đánh dấu `@LoadBalanced` và inject đúng bean:

~~~java
@Bean("internalRestTemplate")
@LoadBalanced
public RestTemplate internalRestTemplate() {
    return new RestTemplate();
}
~~~

Đoạn trên đặt trong lớp `@Configuration`, dùng `RestTemplate` từ `org.springframework.web.client` cùng các annotation đã nêu. Lời gọi có dạng:

~~~java
restTemplate.getForObject(
        "http://catalog-api/products/{id}",
        Product.class,
        id);
~~~

Chọn hướng dùng mới và lộ trình nâng cấp theo phiên bản framework của dự án. Tránh sao chép nhiều cơ chế client khi chỉ một cơ chế đáp ứng yêu cầu.

## 6. Tên dịch vụ, namespace, cổng và đường dẫn phải đúng

### 6.1. Tên logic không mặc nhiên là FQDN

Với ví dụ discovery, dùng:

~~~text
http://catalog-api/products/42
~~~

Không mặc định đổi thành:

~~~text
http://catalog-api.demo.svc.cluster.local/products/42
~~~

rồi kỳ vọng LoadBalancer vẫn tra tên `catalog-api`. Với client đã tích hợp, phần host có thể được lấy làm service ID nguyên vẹn; chuỗi FQDN đó không tự được tách thành Service và namespace như resolver Kubernetes.

Để chọn namespace, cấu hình nguồn discovery đúng phạm vi. Nếu muốn gọi một FQDN bằng DNS thông thường, sử dụng client phù hợp với đường gọi đó.

### 6.2. Không gắn cố định PodIP

URL sau bỏ qua ý nghĩa tra cứu Service mong muốn:

~~~text
http://10.42.1.21:8080/products/42
~~~

Nếu dùng client thông thường, nó gắn vào một Pod cụ thể và không tự theo việc Pod được thay thế. Nếu dùng client LoadBalancer, host IP còn có thể bị hiểu thành service ID cần tìm.

Dùng địa chỉ cụ thể chỉ khi đó là chủ đích của thao tác chẩn đoán hoặc thiết kế, với đúng loại client.

### 6.3. Cổng lấy từ đâu?

Trong chế độ POD, cần quan sát `host:port` của instance được discovery cung cấp. Trong chế độ SERVICE, cổng Service được lựa chọn theo cấu hình tương ứng.

Ví dụ Service `port: 80` và `targetPort: 8080` không có nghĩa bạn phải thêm `:80` vào mọi URL logic hoặc mọi URL PodIP. Điểm kết nối thực tế quyết định cổng hợp lệ.

Ở bài này, cả Service và backend đều dùng `8080` để tránh trộn vấn đề lựa chọn cổng vào ví dụ tích hợp client. Khi có nhiều cổng, đặt tên và cấu hình chọn cổng rõ ràng.

### 6.4. Đường dẫn và query vẫn là contract nghiệp vụ

LoadBalancer xử lý việc chọn đích, không tự biết API phải là `/products/42` hay `/api/v1/products/42`. Sai đường dẫn vẫn có thể gây 404 sau khi đã chọn instance thành công.

Dùng URI template và cơ chế tạo URI của client để truyền giá trị, thay vì nối chuỗi không kiểm soát:

~~~java
restClient.get()
        .uri("/products/{id}?currency={currency}", id, "VND")
        .retrieve()
        .body(Product.class);
~~~

Đây là biến thể lời gọi nếu API đích hỗ trợ query `currency`.

## 7. Những cách vô tình bỏ qua hoặc dùng sai tích hợp

### Tạo client mới ngay trong phương thức nghiệp vụ

~~~java
RestClient client = RestClient.create();
return client.get()
        .uri("http://catalog-api/products/42")
        .retrieve()
        .body(Product.class);
~~~

Đây là phản ví dụ so với cấu hình ở phần trước: client mới này không được tạo từ builder nội bộ đã tích hợp. Request có thể thành công nhờ DNS, khiến lỗi tích hợp bị che khuất.

### Đặt annotation trên một phương thức tùy ý

`@LoadBalanced` không phải lệnh cho mọi URL trong ứng dụng. Việc đánh dấu một phương thức nghiệp vụ hoặc có annotation ở một client khác không biến client được tạo thủ công thành client LoadBalancer.

### Inject nhầm builder

Nếu có builder nội bộ và builder thông thường, injection không rõ ràng có thể chọn builder `@Primary`. Với cấu hình trong bài, đó là builder bên ngoài, nên lời gọi nội bộ cần qualifier.

### Gọi URL bên ngoài bằng client nội bộ

~~~text
https://api.partner.example/payments
~~~

Nếu đưa URL này qua client LoadBalancer, host có thể bị coi là service ID `api.partner.example`. Discovery không nhất thiết có ID đó, dù DNS của host hoạt động bình thường.

Dùng client thông thường cho URL bên ngoài, trừ khi kiến trúc đã chủ động đăng ký và định tuyến tên đó qua discovery.

### Làm mất interceptor hoặc filter trong khi tùy biến

Việc thay danh sách interceptor/filter bằng một danh sách mới có thể làm mất tích hợp đã có. Khi bổ sung authentication, logging, timeout hoặc tracing, cần giữ các thành phần LoadBalancer và kiểm chứng đường chọn đích sau thay đổi.

## 8. Lựa chọn đích không thay thế readiness, timeout và xử lý lỗi

Một lần gọi qua LoadBalancer vẫn có thể thất bại tại các bước khác nhau:

| Dấu hiệu | Tầng cần xem trước |
| --- | --- |
| Không có instance cho tên dịch vụ | Tên logic, namespace, bộ lọc, RBAC và dữ liệu discovery |
| UnknownHostException của tên logic | Client chưa đi qua tích hợp, hoặc đích được chọn thực sự dùng DNS và DNS lỗi |
| Connection refused tới PodIP | Cổng, tiến trình ứng dụng và vòng đời Pod |
| Connect/read timeout | Đường mạng, tài nguyên và thời gian phản hồi đích |
| HTTP 404 | Đích đã nhận request nhưng contract đường dẫn có thể sai |
| HTTP 401/403 từ ứng dụng đích | Authentication/authorization của API nghiệp vụ |
| Lỗi giải mã JSON | Contract dữ liệu hoặc nội dung trả về không đúng kỳ vọng |

Kiểu exception hoặc HTTP status khi không tìm được instance có thể khác giữa client và phiên bản. Giữ nguyên nhân lỗi để chẩn đoán; không biến mọi lỗi thành `null` hoặc danh sách rỗng.

Readiness giúp nguồn discovery loại bớt backend chưa sẵn sàng theo chính sách, nhưng dữ liệu cập nhật có độ trễ. Một Pod vừa bị dừng vẫn có thể xuất hiện trong một bản danh sách cũ. Phải kết hợp cập nhật discovery, timeout và hành vi shutdown phù hợp.

Cần đặt timeout cho transport thực tế mà client dùng. `@LoadBalanced` không tự tạo một ngân sách thời gian chờ phù hợp với nghiệp vụ.

Retry cũng là cấu hình riêng. Không suy ra request thất bại sẽ luôn được chuyển sang Pod khác. Nếu bật retry, giới hạn số lần thử, tổng thời gian và loại lỗi; với thao tác tạo đơn hoặc thanh toán, phải xét tính idempotent để tránh lặp tác dụng nghiệp vụ.

HTTPS cần scheme, cổng, trạng thái secure của đích và chứng chỉ phù hợp. Gọi trực tiếp PodIP có thể tạo yêu cầu xác thực chứng chỉ khác với gọi tên Service; đổi thuật toán cân bằng tải không sửa lỗi TLS.

## 9. Kiểm chứng client thực sự dùng LoadBalancer

Các bước dưới đây dành cho môi trường thực hành đã có ứng dụng gọi, dịch vụ đích và quyền truy cập phù hợp.

### Bước 1: Xác nhận dữ liệu Kubernetes

~~~sh
kubectl -n demo get service catalog-api -o yaml
kubectl -n demo get pods -l app=catalog-api -o wide
kubectl -n demo get endpointslices -l kubernetes.io/service-name=catalog-api -o yaml
~~~

Đối chiếu selector, tên cổng, địa chỉ, điều kiện readiness và namespace. Nếu client đọc Endpoints, xem đúng tài nguyên đó thay vì chỉ kiểm tra EndpointSlice.

### Bước 2: Xem danh sách mà discovery cung cấp

Trong mã chẩn đoán, có thể đọc:

~~~java
List<ServiceInstance> candidates =
        discoveryClient.getInstances("catalog-api");
~~~

Các kiểu trên thuộc `java.util.List` và `org.springframework.cloud.client`; `discoveryClient` là bean `DiscoveryClient` được inject. Chỉ ghi các trường cần thiết như service ID, host và port.

Ở chế độ POD, danh sách này giúp đối chiếu nguồn đích cho LoadBalancer. Nếu có cache, bộ lọc hoặc supplier tùy chỉnh sau discovery, danh sách ứng viên cuối có thể đã thay đổi; cần xem cả cấu hình đó.

### Bước 3: Kiểm tra bean client đang được dùng

Xác nhận `CatalogClient` nhận `internalRestClientBuilder` và không có dòng tạo client mới trong đường gọi. Kiểm tra dependency và điều kiện auto-configuration nếu tích hợp không được kích hoạt.

Có thể tạm bật log phù hợp cho nhóm:

~~~yaml
logging:
  level:
    org.springframework.cloud.loadbalancer: DEBUG
~~~

Nội dung log phụ thuộc phiên bản; không mặc định log này luôn in URL cuối. Khi cần, dùng instrumentation hoặc điểm quan sát của client/LoadBalancer để ghi instance được chọn.

### Bước 4: Quan sát Pod nhận request

Ứng dụng đích có thể cung cấp endpoint quan sát trong môi trường thử nghiệm:

~~~java
package example.catalog;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReplicaInspectionController {

    @GetMapping("/internal/whoami")
    public ReplicaView whoAmI() {
        String hostname = System.getenv("HOSTNAME");
        return new ReplicaView(hostname == null ? "unknown" : hostname);
    }

    public record ReplicaView(String pod) {
    }
}
~~~

Đoạn này nằm ở ứng dụng `catalog-api`. Nó giả định `HOSTNAME` phản ánh tên host/Pod trong môi trường thực hành; nếu môi trường không cung cấp như vậy, truyền tên Pod bằng cơ chế phù hợp hoặc xem log backend.

Gửi request tới `/internal/whoami` qua đúng HTTP client đã tích hợp và đối chiếu kết quả với log lựa chọn đích. Không thay client bằng lệnh curl trực tiếp rồi coi đó là phép kiểm chứng cùng đường gọi.

### Bước 5: Quan sát nhiều lần và khi danh sách thay đổi

Gửi nhiều request qua `CatalogClient` hoặc đường quan sát tương đương. Xem đích được chọn, Pod nhận request và lỗi ở từng lần.

Không yêu cầu hai request liên tiếp luôn phải đi hai Pod khác nhau. Thuật toán, nhiều tiến trình caller, cache, retry, chế độ SERVICE và kết nối có thể làm kết quả quan sát khác một chuỗi luân phiên đơn giản.

Trong môi trường thử nghiệm, quan sát thêm khi một backend không còn đủ điều kiện nhận traffic. Chờ dữ liệu hội tụ theo cơ chế thực tế và xác nhận client cập nhật đích. Một lần gọi thành công không đủ chứng minh khả năng theo dõi thay đổi danh sách.

## 10. Áp dụng đúng phạm vi tính năng Spring Cloud Kubernetes

Để gọi tên dịch vụ qua HTTP client đã tích hợp LoadBalancer, cần có lý do cho việc ứng dụng lựa chọn đích, chẳng hạn dùng danh sách instance hoặc chính sách theo metadata.

Nếu chỉ cần gửi request qua một Kubernetes Service ổn định, HTTP client thông thường cùng DNS có thể đáp ứng yêu cầu. Khi đó, không dùng thành công của DNS để kết luận hạ tầng Spring Cloud LoadBalancer đã được tích hợp.

ConfigMap hoặc Secret có thể cung cấp base URL, cấu hình client hay thông tin xác thực khi kiến trúc cần. Tuy nhiên, cập nhật cấu hình không tự tạo bean đã tích hợp, và việc file cấu hình đổi không bảo đảm một client đã build sẽ tự nhận base URL mới. Configuration Watcher cần được xem xét theo cơ chế nạp lại cấu hình thực tế của ứng dụng.

Trước khi coi đường gọi đã hoàn tất, hãy kiểm tra bốn điểm: **URL dùng đúng service ID, mã nghiệp vụ inject đúng client, nguồn ứng viên cung cấp đích hợp lệ và request thực sự đi tới đích được chọn với đúng cổng cùng đường dẫn**.
