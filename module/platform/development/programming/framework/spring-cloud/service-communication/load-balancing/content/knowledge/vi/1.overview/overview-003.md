# Tên dịch vụ, địa chỉ máy chủ, cổng và ServiceInstance

Trong hệ thống microservices, một dịch vụ thường chạy nhiều bản sao để tăng khả năng phục vụ và chịu lỗi. Khi một dịch vụ khác cần gọi đến, nó nên nhắm tới **tên logic của dịch vụ**. Spring Cloud LoadBalancer dùng tên đó để tìm các máy chủ đang cung cấp dịch vụ, chọn một máy chủ phù hợp rồi chuyển yêu cầu đến địa chỉ cụ thể.

Để hiểu luồng này, cần phân biệt bốn khái niệm: service ID, địa chỉ máy chủ (host), cổng (port) và đối tượng ServiceInstance.

## 1. Từ tên dịch vụ đến một máy chủ cụ thể

Giả sử hệ thống có dịch vụ đặt hàng và dịch vụ danh mục sản phẩm. Dịch vụ danh mục được triển khai thành hai bản sao:

| Thuộc tính | Bản sao thứ nhất | Bản sao thứ hai |
|---|---|---|
| Service ID | `catalog-service` | `catalog-service` |
| Instance ID | `catalog-1` | `catalog-2` |
| Host | `10.0.1.21` | `10.0.1.22` |
| Port | `8081` | `8081` |
| URI | `http://10.0.1.21:8081` | `http://10.0.1.22:8081` |

Cả hai bản sao cùng cung cấp một dịch vụ logic là `catalog-service`, nhưng có địa chỉ mạng khác nhau. Khi dịch vụ đặt hàng gọi:

~~~text
http://catalog-service/products/42
~~~

nó đang gọi theo **service ID**. Với HTTP client được tích hợp Spring Cloud LoadBalancer, tên logic này được phân giải thành danh sách các bản sao khả dụng. Bộ cân bằng tải chọn một bản sao, chẳng hạn `catalog-2`, rồi gửi yêu cầu đến URI tương ứng.

~~~mermaid
flowchart LR
    A["Order Service"] -->|"GET /products/42<br/>catalog-service"| B["Spring Cloud LoadBalancer"]
    B -->|"chọn một ServiceInstance"| C["catalog-1<br/>10.0.1.21:8081"]
    B -->|"hoặc chọn"| D["catalog-2<br/>10.0.1.22:8081"]
~~~

Trong một lần gọi thông thường, bộ cân bằng tải chọn một instance để xử lý yêu cầu. Nó không phát cùng một yêu cầu đến tất cả các bản sao.

## 2. Service ID là tên logic của dịch vụ

**Service ID** (còn gọi là service name trong nhiều hệ thống) là định danh mà client dùng để yêu cầu một dịch vụ. Ví dụ:

- `catalog-service`: dịch vụ danh mục sản phẩm.
- `order-service`: dịch vụ quản lý đơn hàng.
- `payment-service`: dịch vụ thanh toán.

Service ID đại diện cho một nhóm các instance cùng cung cấp chức năng. Nó không phải địa chỉ IP, hostname hay cổng của một máy chủ cụ thể.

Điểm khác biệt này cho phép hệ thống thay đổi số lượng và vị trí các instance mà không buộc mọi client phải sửa cấu hình. Nếu `catalog-service` có thêm bản sao thứ ba, client vẫn gọi cùng service ID; nguồn cung cấp instance cập nhật danh sách để LoadBalancer có thể chọn bản sao mới.

Service ID phải khớp với định danh mà nguồn discovery hoặc cấu hình instance sử dụng. Nếu client gọi `catalog-service` nhưng registry chỉ đăng ký `catalog`, bộ cân bằng tải có thể không tìm thấy instance nào.

### Service ID và Instance ID khác nhau thế nào?

Hai tên này trả lời hai câu hỏi khác nhau:

- **Service ID:** instance đang cung cấp dịch vụ logic nào?
- **Instance ID:** đây là bản triển khai cụ thể nào trong nhóm dịch vụ đó?

Ví dụ, `catalog-service` có thể gồm `catalog-1`, `catalog-2` và `catalog-3`. Các instance có cùng Service ID nhưng Instance ID cần phân biệt được từng bản sao trong phạm vi nguồn discovery đang dùng.

Instance ID hữu ích khi quan sát log, dashboard, registry hoặc xử lý sự kiện đăng ký và hủy đăng ký instance. Tùy nguồn discovery, giá trị này có thể được tạo tự động hoặc do ứng dụng/cấu hình cung cấp.

## 3. Host và port xác định nơi instance nhận kết nối

Khi đã chọn một instance, client cần biết phải kết nối đến đâu. Địa chỉ đó thường được tạo từ **scheme**, **host** và **port**.

### Host

Host là tên máy hoặc địa chỉ mạng mà client có thể dùng để tiếp cận instance. Một số dạng thường gặp:

- Địa chỉ IPv4, ví dụ `10.0.1.21`.
- Địa chỉ IPv6, ví dụ `2001:db8::21`.
- Tên DNS, ví dụ `catalog-2.internal.example`.
- Tên máy/container có thể phân giải trong mạng triển khai.

Host phải có ý nghĩa từ góc nhìn của **client đang gọi**. Một địa chỉ có thể truy cập được từ máy phát triển nhưng không truy cập được từ container hoặc một mạng Kubernetes khác. Vì vậy, host được công bố trong service registry phải là địa chỉ mà các client trong môi trường triển khai thực sự có thể định tuyến đến.

### Port

Port là cổng mạng mà tiến trình của instance đang lắng nghe. Ví dụ, ứng dụng Spring Boot có thể lắng nghe ở cổng `8081`.

Trong môi trường container, cần phân biệt cổng bên trong container và cổng được ánh xạ ra bên ngoài. Nếu client và server cùng nằm trong một mạng container, client thường phải dùng cổng mà dịch vụ lắng nghe trong mạng đó. Dùng nhầm cổng publish trên máy host có thể khiến kết nối thất bại.

### Scheme và URI

Scheme cho biết giao thức, thường là `http` hoặc `https`. Host và port kết hợp với scheme tạo thành URI gốc của instance:

~~~text
http://10.0.1.21:8081
https://catalog-2.internal.example:8443
~~~

Trong Spring Cloud, thông tin bảo mật của instance được thể hiện qua `isSecure()`; URI của instance thể hiện địa chỉ có thể dùng để tạo đích gọi. Không nên tự suy luận rằng mọi instance đều dùng HTTP hoặc cùng một port: mỗi instance có thể có cấu hình riêng.

Đường dẫn và query string của API thường được ghép vào URI gốc khi thực hiện request, ví dụ:

~~~text
http://10.0.1.21:8081/products/42?include=price
~~~

## 4. ServiceInstance biểu diễn một bản triển khai cụ thể

Trong Spring Cloud Commons, `org.springframework.cloud.client.ServiceInstance` là interface mô tả một instance của dịch vụ. Spring Cloud LoadBalancer làm việc với các đối tượng instance để lựa chọn đích gọi.

Một `ServiceInstance` thường cung cấp các thông tin sau:

| Phương thức | Ý nghĩa |
|---|---|
| `getServiceId()` | Service ID mà instance cung cấp |
| `getInstanceId()` | Định danh của bản triển khai; tùy implementation, giá trị có thể không được cung cấp |
| `getHost()` | Host của instance |
| `getPort()` | Port mà instance nhận kết nối |
| `isSecure()` | Cho biết instance sử dụng kết nối bảo mật |
| `getUri()` | URI của instance, kết hợp thông tin giao thức và địa chỉ |
| `getMetadata()` | Map metadata dạng key/value đi kèm instance |

Ví dụ đọc thông tin từ một instance:

~~~java
import java.net.URI;
import java.util.Map;

import org.springframework.cloud.client.ServiceInstance;

void inspect(ServiceInstance instance) {
    String serviceId = instance.getServiceId();
    String instanceId = instance.getInstanceId();
    String host = instance.getHost();
    int port = instance.getPort();
    boolean secure = instance.isSecure();
    URI uri = instance.getUri();
    Map<String, String> metadata = instance.getMetadata();

    System.out.println("serviceId = " + serviceId);
    System.out.println("instanceId = " + instanceId);
    System.out.println("address = " + uri);
    System.out.println("secure = " + secure);
    System.out.println("metadata = " + metadata);
}
~~~

Đây là ví dụ quan sát thông tin. Trong ứng dụng thực tế, client thường để Spring Cloud LoadBalancer chọn instance thông qua HTTP client đã được cấu hình tích hợp; không cần tự lấy danh sách rồi tự viết thuật toán chọn máy chủ.

### Metadata dùng để làm gì?

Metadata là các cặp key/value do nguồn discovery hoặc cấu hình instance cung cấp. Ví dụ:

~~~text
zone=ap-southeast-1a
version=v2
environment=staging
~~~

Metadata có thể hỗ trợ phân vùng theo vùng triển khai, phiên bản, môi trường hoặc tiêu chí vận hành khác. Tuy nhiên, chỉ khai báo metadata không tự làm thay đổi quyết định định tuyến. Muốn ưu tiên instance cùng zone, chỉ gọi phiên bản phù hợp hoặc áp dụng một tiêu chí riêng, ứng dụng cần có supplier, bộ lọc hoặc chính sách LoadBalancer tương ứng.

### Ai tạo ServiceInstance?

ServiceInstance là abstraction; đối tượng cụ thể có thể đến từ nhiều nguồn:

- **Service registry/discovery:** chẳng hạn Eureka hoặc Consul đăng ký các instance và cung cấp thông tin địa chỉ.
- **Nền tảng triển khai:** integration có thể lấy endpoint từ môi trường điều phối.
- **Danh sách cấu hình tĩnh:** hữu ích cho môi trường đơn giản, phát triển hoặc kiểm thử khi không cần registry riêng.

Một implementation phổ biến trong Spring Cloud Commons là `DefaultServiceInstance`. Các integration khác có thể cung cấp implementation riêng. Client nên làm việc qua interface `ServiceInstance` thay vì phụ thuộc vào cách một registry cụ thể lưu trữ dữ liệu.

## 5. Spring Cloud LoadBalancer sử dụng ServiceInstance như thế nào?

Ở mức khái niệm, quá trình phân giải service ID và chọn instance diễn ra theo các bước:

1. HTTP client gửi request tới một URI có hostname logic là service ID, ví dụ `http://catalog-service/products/42`.
2. Thành phần tích hợp LoadBalancer nhận biết service ID `catalog-service`.
3. `ServiceInstanceListSupplier` cung cấp danh sách instance ứng với service ID đó. Supplier có thể lấy dữ liệu từ discovery client, cấu hình tĩnh hoặc một nguồn được ứng dụng tùy biến.
4. Bộ cân bằng tải chọn một instance từ danh sách theo chính sách đang cấu hình, chẳng hạn round-robin.
5. HTTP client dùng địa chỉ của instance được chọn để thực hiện request.

`DiscoveryClient` và `ServiceInstanceListSupplier` có vai trò liên quan nhưng không đồng nghĩa. Discovery client là abstraction để truy vấn các instance đã được đăng ký. Supplier là thành phần cung cấp danh sách ứng viên cho Spring Cloud LoadBalancer; nó có thể dùng discovery client hoặc nguồn dữ liệu khác.

Có thể truy vấn instance từ discovery client để kiểm tra dữ liệu discovery:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

List<ServiceInstance> instances =
        discoveryClient.getInstances("catalog-service");

for (ServiceInstance instance : instances) {
    System.out.println(instance.getServiceId() + " -> " + instance.getUri());
}
~~~

Đoạn mã trên minh họa việc đọc danh sách instance. Nó không thực hiện cân bằng tải cho một HTTP request. Khi dùng client tích hợp LoadBalancer, việc lấy danh sách, chọn instance và chuyển request được thực hiện trong luồng tích hợp đó.

Nếu danh sách rỗng, nguyên nhân có thể là service ID không khớp, instance chưa đăng ký, registry chưa đồng bộ, cấu hình discovery sai hoặc không có instance nào được supplier cung cấp. Nếu danh sách có instance nhưng request vẫn lỗi, cần kiểm tra host, port, giao thức, khả năng định tuyến mạng và trạng thái thực tế của server.

## 6. Ví dụ tích hợp với HTTP client

Với `RestClient`, có thể đánh dấu builder bằng `@LoadBalanced` để các request dùng service ID được xử lý qua Spring Cloud LoadBalancer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Một client có thể gọi dịch vụ bằng tên logic:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    Product findProduct(long id) {
        return restClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}
~~~

Ví dụ giả định ứng dụng đã có dependency Spring Cloud LoadBalancer phù hợp với Spring Cloud release train đang sử dụng và builder được inject là builder có qualifier `@LoadBalanced`. Khi đó, `catalog-service` là service ID được phân giải thành một `ServiceInstance`. Nếu gọi trực tiếp URI chứa IP/host và port của một instance, request đã chỉ định đích cụ thể và không còn sử dụng service ID để chọn trong nhóm instance theo cách này.

WebClient và OpenFeign cũng có thể tích hợp Spring Cloud LoadBalancer khi được cấu hình đúng. Dù dùng HTTP client nào, ý tưởng vẫn giống nhau: client gửi theo service ID, LoadBalancer tìm instance, rồi request được gửi tới host và port của instance đã chọn.

## 7. Những lỗi thường gặp khi khai báo địa chỉ instance

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy server cho service ID | Sai tên dịch vụ hoặc không có instance được đăng ký | So sánh service ID trong request với tên trong registry/cấu hình; kiểm tra danh sách instance |
| Kết nối bị từ chối | Port sai hoặc tiến trình chưa lắng nghe | Kiểm tra port thực tế của ứng dụng và port được công bố |
| Không phân giải được host | Host không tồn tại trong DNS hoặc không dùng được từ mạng của client | Kiểm tra DNS và định tuyến từ chính môi trường chạy client |
| Chạy được trên máy cá nhân nhưng lỗi trong container | Địa chỉ `localhost` trỏ về container của client | Dùng hostname/IP có thể truy cập qua mạng giữa các container |
| Kết nối sai giao thức | Scheme hoặc cờ secure không khớp với server | Đối chiếu HTTP/HTTPS, chứng chỉ và cấu hình instance |
| Request đến instance đã ngừng hoạt động | Dữ liệu discovery cũ hoặc supplier chưa lọc instance lỗi | Kiểm tra heartbeat/health status, thời gian cập nhật registry và bộ lọc instance |
| Metadata không ảnh hưởng lựa chọn | Chưa có chính sách đọc và sử dụng metadata | Kiểm tra supplier, filter hoặc cấu hình thuật toán LoadBalancer |

Một lỗi dễ gặp là đăng ký `localhost` làm host của instance trong hệ thống nhiều máy hoặc nhiều container. `localhost` luôn được hiểu từ môi trường đang thực hiện kết nối. Vì vậy, khi client chạy ở container khác, `localhost:8081` thường trỏ về chính container client thay vì container cung cấp dịch vụ.

Cũng cần phân biệt **có trong danh sách** và **đang khỏe mạnh**. Một đối tượng ServiceInstance mô tả endpoint mà nguồn dữ liệu cung cấp; bản thân đối tượng đó không chứng minh server hiện vẫn nhận request thành công. Việc kiểm tra sức khỏe phụ thuộc vào registry, supplier, health check hoặc cơ chế lọc được cấu hình.

## 8. Checklist khi đọc hoặc cấu hình ServiceInstance

Trước khi kiểm tra một request được cân bằng tải, hãy lần lượt xác nhận:

1. Client đang gọi đúng service ID.
2. Nguồn discovery hoặc cấu hình cung cấp danh sách instance cho service ID đó.
3. Mỗi instance có host và port đúng với môi trường mạng của client.
4. Scheme/secure phù hợp với giao thức server đang phục vụ.
5. Instance được chọn còn hoạt động và có thể truy cập.
6. Nếu dùng metadata để định tuyến, chính sách LoadBalancer đã được cấu hình để đọc metadata đó.

Cần nhớ mối quan hệ cốt lõi: **service ID xác định nhóm dịch vụ; ServiceInstance mô tả một bản triển khai trong nhóm; host và port xác định địa chỉ mạng của bản triển khai đó**. Spring Cloud LoadBalancer dùng danh sách ServiceInstance để chọn đích cho request, giúp client giao tiếp với dịch vụ qua tên logic thay vì gắn cứng vào địa chỉ của một máy chủ.

