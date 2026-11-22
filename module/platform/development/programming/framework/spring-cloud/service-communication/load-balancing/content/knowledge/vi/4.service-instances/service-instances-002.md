# Danh sách tĩnh và danh sách lấy từ DiscoveryClient

Trong một hệ thống gồm nhiều dịch vụ, một service ID như `catalog-service` có thể đại diện cho nhiều tiến trình đang chạy ở các máy hoặc container khác nhau. Spring Cloud LoadBalancer cần biết các địa chỉ tương ứng để chọn một `ServiceInstance` cho mỗi request. Danh sách instance có thể được khai báo tĩnh trong cấu hình hoặc lấy từ một nguồn khám phá dịch vụ thông qua `DiscoveryClient`.

Trong module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, việc hiểu hai nguồn dữ liệu này giúp lựa chọn cách triển khai phù hợp với môi trường chạy: danh sách tĩnh hữu ích cho ứng dụng nhỏ và môi trường cố định; DiscoveryClient phù hợp khi số lượng hoặc địa chỉ instance thay đổi trong quá trình vận hành.

## 1. Service ID và ServiceInstance

**Service ID** là tên logic mà client sử dụng để gọi một dịch vụ. Ví dụ, ứng dụng đặt hàng gửi request đến:

~~~text
http://catalog-service/api/items/42
~~~

Trong URL này, `catalog-service` là service ID. Nó không nhất thiết là hostname có thể phân giải bằng DNS. Khi request đi qua một HTTP client được tích hợp với Spring Cloud LoadBalancer, load balancer sẽ phân giải service ID thành một instance cụ thể.

Một **ServiceInstance** mô tả một bản sao có thể nhận request của dịch vụ. Thông tin thường có gồm:

- `serviceId`: tên dịch vụ mà instance thuộc về.
- `host` và `port`: địa chỉ mạng để kết nối.
- `uri`: địa chỉ đầy đủ được tạo từ host, port và scheme.
- `instanceId`: định danh instance nếu nguồn dữ liệu cung cấp.
- `secure`: cho biết instance sử dụng kết nối bảo mật.
- `metadata`: các thuộc tính bổ sung như zone, version hoặc nhóm triển khai.

Ví dụ, một dịch vụ có hai bản sao:

| Service ID | Instance | Địa chỉ |
|---|---|---|
| catalog-service | catalog-1 | http://10.0.1.11:8080 |
| catalog-service | catalog-2 | http://10.0.1.12:8080 |

Hai bản sao có cùng service ID nhưng địa chỉ khác nhau. Load balancer chọn một bản sao trong danh sách để gửi request.

~~~mermaid
flowchart TD
    A["Client gọi catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["Danh sách ServiceInstance"]
    C --> D["catalog-1 · 10.0.1.11:8080"]
    C --> E["catalog-2 · 10.0.1.12:8080"]
    D --> F["Chọn một instance"]
    E --> F
    F --> G["Gửi HTTP request"]
~~~

Nguồn cung cấp danh sách instance và thuật toán chọn instance là hai phần khác nhau. Nguồn cung cấp trả về những instance mà nó biết; bộ chọn của Spring Cloud LoadBalancer quyết định instance nào được sử dụng cho request hiện tại.

## 2. Danh sách tĩnh với SimpleDiscoveryClient

Khi địa chỉ các instance đã biết trước và ít thay đổi, ứng dụng có thể khai báo chúng trong cấu hình. Spring Cloud cung cấp **SimpleDiscoveryClient** để đọc danh sách instance đơn giản từ cấu hình ứng dụng.

Ví dụ, khai báo hai bản sao của `catalog-service` trong file `application.yml`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Mỗi phần tử trong danh sách là một instance. Thuộc tính `uri` cung cấp địa chỉ đích; `metadata` chứa thông tin bổ sung có thể được dùng bởi bộ lọc hoặc chính sách lựa chọn instance.

Có thể khai báo tương đương bằng properties:

~~~properties
spring.cloud.discovery.client.simple.instances.catalog-service[0].uri=http://localhost:8081
spring.cloud.discovery.client.simple.instances.catalog-service[1].uri=http://localhost:8082
spring.cloud.discovery.client.simple.instances.catalog-service[0].metadata.zone=zone-a
spring.cloud.discovery.client.simple.instances.catalog-service[1].metadata.zone=zone-b
~~~

Trong cấu hình thông dụng, SimpleDiscoveryClient được dùng khi ứng dụng không có một triển khai DiscoveryClient khác cung cấp danh sách instance. Nó triển khai abstraction DiscoveryClient của Spring Cloud, vì vậy các thành phần cần DiscoveryClient có thể truy vấn danh sách được khai báo.

### Request được phân giải như thế nào?

Giả sử ứng dụng có một client được đánh dấu `@LoadBalanced`:

~~~java
@Configuration
class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Một service sử dụng builder đó có thể gọi bằng service ID:

~~~java
@Service
class CatalogClient {

    private final RestClient restClient;

    CatalogClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    ItemDto getItem(String itemId) {
        return restClient.get()
            .uri("http://catalog-service/api/items/{id}", itemId)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

Khi request được gửi, tích hợp load balancing truy vấn danh sách instance của `catalog-service`, chọn một instance và gửi request đến địa chỉ của instance đó. Caller vẫn chỉ làm việc với service ID.

### Ưu điểm và giới hạn của danh sách tĩnh

Danh sách tĩnh có một số ưu điểm:

- Dễ cấu hình, không cần cài đặt hoặc vận hành registry riêng.
- Phù hợp với môi trường phát triển cục bộ, demo, kiểm thử hoặc hệ thống có số instance cố định.
- Dễ đọc và dễ kiểm soát địa chỉ đích trong cấu hình triển khai.

Tuy nhiên, danh sách tĩnh có giới hạn rõ ràng:

- Khi instance đổi IP, port hoặc bị loại bỏ, cấu hình phải được cập nhật.
- Khi thêm bản sao mới, ứng dụng cần nhận được cấu hình mới theo cơ chế triển khai hoặc refresh đã thiết lập.
- Danh sách cấu hình không tự chứng minh tiến trình ở địa chỉ đó đang hoạt động.
- Nếu nhiều môi trường dùng địa chỉ khác nhau, cần tách cấu hình theo profile hoặc nguồn cấu hình tương ứng.

SimpleDiscoveryClient không tự đăng ký instance lên một registry tập trung. Nó cung cấp danh sách đã cấu hình cho ứng dụng đang chạy. Nếu một tiến trình bị dừng nhưng địa chỉ của nó vẫn còn trong cấu hình, instance đó vẫn có thể xuất hiện trong danh sách cho đến khi cấu hình được thay đổi hoặc có cơ chế lọc sức khỏe được bổ sung.

## 3. Danh sách lấy từ DiscoveryClient

Trong môi trường có nhiều instance thay đổi theo thời gian, khai báo địa chỉ thủ công gây tốn công và dễ lỗi. Một **service registry** có thể lưu thông tin về các instance đang đăng ký. Các dịch vụ đăng ký hoặc gia hạn trạng thái với registry; client truy vấn registry để biết những instance có thể được sử dụng.

Spring Cloud định nghĩa abstraction **DiscoveryClient** để ứng dụng truy vấn dịch vụ mà không phải phụ thuộc trực tiếp vào API riêng của từng registry.

Hai phương thức thường dùng là:

~~~java
List<String> getServices();

List<ServiceInstance> getInstances(String serviceId);
~~~

- `getServices()` trả về các service ID mà discovery client biết.
- `getInstances(serviceId)` trả về các instance thuộc service ID được chỉ định.

Các triển khai DiscoveryClient có thể kết nối với những hệ thống khác nhau, chẳng hạn Eureka, Consul hoặc một nền tảng discovery tương ứng. Chi tiết đăng ký, heartbeat, lease và cách loại bỏ instance phụ thuộc vào hệ thống được tích hợp.

### Luồng đăng ký và khám phá

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Service instance
    participant Registry as Service registry
    participant Client as Ứng dụng gọi
    participant LB as Spring Cloud LoadBalancer
    participant Target as Instance được chọn

    App->>Registry: Đăng ký service ID và địa chỉ
    App->>Registry: Gia hạn trạng thái theo cơ chế registry
    Client->>LB: Gửi request đến service ID
    LB->>Registry: Truy vấn các instance
    Registry-->>LB: Danh sách ServiceInstance
    LB->>LB: Lọc và chọn instance
    LB->>Target: Gửi HTTP request
    Target-->>Client: HTTP response
~~~

Luồng trên mô tả ý tưởng chung. Trong triển khai thực tế, DiscoveryClient có thể đọc dữ liệu từ registry trực tiếp hoặc qua cache của thư viện tích hợp. Thời điểm cập nhật danh sách phụ thuộc cấu hình cache, cơ chế làm mới và hệ thống registry.

### Ví dụ truy vấn DiscoveryClient

Có thể dùng abstraction DiscoveryClient để xem danh sách instance mà ứng dụng đang nhận được:

~~~java
@Service
class CatalogInstanceInspector {

    private final DiscoveryClient discoveryClient;

    CatalogInstanceInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    List<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }

    List<String> findKnownServices() {
        return discoveryClient.getServices();
    }
}
~~~

Đây là ví dụ quan sát danh sách instance. Trong luồng gọi HTTP thông thường, nên để Spring Cloud LoadBalancer lựa chọn instance thay vì tự lấy phần tử đầu tiên hoặc tự viết thuật toán phân phối trong service nghiệp vụ.

Nếu danh sách rỗng, ứng dụng chưa có instance nào được DiscoveryClient cung cấp cho service ID đó. Nguyên nhân có thể là service chưa đăng ký, tên service ID không khớp, registry chưa đồng bộ, instance đã bị loại bỏ hoặc cấu hình kết nối registry không đúng.

### DiscoveryClient đồng bộ và ReactiveDiscoveryClient

Spring Cloud có hai abstraction để phù hợp với kiểu xử lý của ứng dụng:

- **DiscoveryClient** cung cấp API đồng bộ. Lời gọi `getInstances()` trả về danh sách ngay trong luồng gọi; thao tác truy vấn có thể chặn thread tùy triển khai.
- **ReactiveDiscoveryClient** cung cấp API reactive, trả về `Flux<ServiceInstance>` cho danh sách instance. Cách này phù hợp với luồng reactive.

Ví dụ sử dụng ReactiveDiscoveryClient:

~~~java
@Service
class ReactiveCatalogInstanceInspector {

    private final ReactiveDiscoveryClient discoveryClient;

    ReactiveCatalogInstanceInspector(
            ReactiveDiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    Flux<ServiceInstance> findCatalogInstances() {
        return discoveryClient.getInstances("catalog-service");
    }
}
~~~

Không nên gọi một API discovery đồng bộ trực tiếp trên event loop của WebFlux nếu thao tác đó có thể chặn. Hãy sử dụng triển khai reactive tương ứng hoặc cô lập lời gọi blocking trên scheduler phù hợp.

## 4. Spring Cloud LoadBalancer nhận danh sách instance ra sao?

Spring Cloud LoadBalancer không cần biết mọi chi tiết riêng của Eureka, Consul hay SimpleDiscoveryClient. Nó làm việc thông qua abstraction cung cấp danh sách **ServiceInstanceListSupplier**.

Supplier là thành phần trả về danh sách instance cho một service ID. Tùy cấu hình, danh sách có thể đến từ DiscoveryClient, ReactiveDiscoveryClient, nguồn cấu hình tĩnh hoặc supplier tùy biến. Các supplier cũng có thể được kết hợp để cache, lọc hoặc kiểm tra instance trước khi bộ chọn sử dụng.

~~~mermaid
flowchart TD
    A["HTTP client có @LoadBalanced"] --> B["Spring Cloud LoadBalancer"]
    B --> C["ServiceInstanceListSupplier"]
    C --> D["SimpleDiscoveryClient"]
    C --> E["DiscoveryClient"]
    C --> F["ReactiveDiscoveryClient"]
    C --> G["Supplier tùy biến"]
    D --> H["Danh sách ServiceInstance"]
    E --> H
    F --> H
    G --> H
    H --> I["Bộ chọn instance"]
    I --> J["HTTP client gửi request"]
~~~

Trong cấu hình thông dụng, Spring Cloud LoadBalancer cung cấp tích hợp để lấy danh sách từ DiscoveryClient phù hợp với loại client đang sử dụng. Khi ứng dụng có nhiều nguồn discovery hoặc muốn thay đổi cách lọc, cache và sắp xếp instance, có thể cấu hình supplier tương ứng theo hướng dẫn của phiên bản Spring Cloud đang dùng.

Điều này tạo ra ranh giới rõ ràng:

- DiscoveryClient hoặc nguồn tĩnh trả lời câu hỏi **những instance nào được biết đến**.
- ServiceInstanceListSupplier cung cấp danh sách cho LoadBalancer và có thể áp dụng các bước xử lý bổ sung.
- Bộ chọn của LoadBalancer trả lời câu hỏi **instance nào sẽ nhận request này**.
- HTTP client thực hiện kết nối và gửi request đến địa chỉ được chọn.

Danh sách tĩnh và danh sách lấy từ DiscoveryClient đều có thể được dùng phía sau cùng một cơ chế load balancing. Khác biệt nằm ở cách danh sách được tạo và cập nhật.

## 5. So sánh danh sách tĩnh và DiscoveryClient

| Tiêu chí | Danh sách tĩnh (SimpleDiscoveryClient) | DiscoveryClient từ registry |
|---|---|---|
| Nguồn dữ liệu | File cấu hình hoặc properties của ứng dụng | Service registry hoặc hệ thống discovery |
| Cập nhật instance | Cần cập nhật cấu hình và áp dụng lại | Theo cơ chế đăng ký, gia hạn và đồng bộ của registry |
| Hạ tầng bổ sung | Không cần registry riêng | Thường cần registry hoặc nền tảng discovery |
| Khả năng thích nghi khi scale | Hạn chế nếu địa chỉ thay đổi thường xuyên | Phù hợp hơn với instance tăng giảm động |
| Độ phức tạp vận hành | Thấp | Cần vận hành và giám sát discovery |
| Trường hợp phù hợp | Local, demo, test, môi trường cố định | Hệ thống nhiều instance, triển khai phân tán, scale thường xuyên |

Không có nguồn danh sách nào tự bảo đảm mọi instance đều khỏe mạnh. Discovery registry có thể duy trì trạng thái bằng heartbeat hoặc lease, nhưng trạng thái trong registry có thể trễ so với tình trạng thực tế của tiến trình. Danh sách tĩnh càng cần cơ chế kiểm tra hoặc quy trình cập nhật khi instance ngừng hoạt động.

## 6. Cập nhật danh sách, cache và sức khỏe instance

Ba khái niệm cần phân biệt khi vận hành:

**Đăng ký và khám phá** xác định instance nào được ghi nhận trong nguồn dữ liệu. Với registry, instance có thể đăng ký, gia hạn lease hoặc bị loại bỏ theo cơ chế của registry. Với danh sách tĩnh, instance đến từ cấu hình ứng dụng.

**Cache danh sách** giảm số lần truy vấn nguồn discovery và độ trễ khi lấy instance. Tuy nhiên, cache quá lâu có thể khiến LoadBalancer tiếp tục thấy địa chỉ cũ sau khi instance đã thay đổi. Thời gian cache cần cân đối giữa tải lên registry và độ mới của dữ liệu.

**Health check** đánh giá instance có đáp ứng được yêu cầu hay không. Việc instance xuất hiện trong DiscoveryClient không đồng nghĩa endpoint nghiệp vụ chắc chắn đang khỏe. Có thể cấu hình cơ chế kiểm tra sức khỏe hoặc supplier lọc instance không đáp ứng điều kiện, tùy loại client và phiên bản Spring Cloud.

Khi cấu hình health check, cần xác định endpoint được gọi, chu kỳ kiểm tra, timeout, số lần lỗi trước khi loại bỏ và cách đưa instance trở lại danh sách. Kiểm tra quá thường xuyên có thể tạo tải không cần thiết; kiểm tra quá thưa có thể giữ instance lỗi trong danh sách lâu hơn.

Metadata cũng có thể hỗ trợ quyết định lựa chọn. Ví dụ, mỗi instance có thể khai báo `zone` hoặc `version`. Một supplier hoặc chính sách chọn tùy biến có thể dùng metadata để ưu tiên instance cùng vùng hoặc giới hạn phiên bản tương thích. Metadata chỉ có tác dụng khi thành phần lựa chọn được cấu hình để đọc và sử dụng nó; việc khai báo metadata không tự thay đổi thuật toán mặc định.

## 7. Lỗi thường gặp và cách kiểm tra

### Gọi sai service ID

Nếu URL dùng `catalog-service` nhưng registry đăng ký `catalog`, DiscoveryClient có thể trả danh sách rỗng. Kiểm tra chính xác tên service ID trong cấu hình ứng dụng cung cấp và tên mà client sử dụng.

### Registry chưa có instance

Một ứng dụng có thể khởi động trước khi service đích đăng ký xong. Khi đó, lần truy vấn đầu tiên có thể nhận danh sách rỗng. Cần xem log đăng ký, trạng thái registry và cơ chế retry của client; không nên mặc định rằng dịch vụ luôn có instance ngay lúc ứng dụng khởi động.

### Danh sách chứa địa chỉ không thể truy cập

Registry có thể ghi nhận địa chỉ nội bộ mà client không định tuyến được, hoặc instance khai báo hostname chỉ phân giải trong một mạng khác. Kiểm tra URI, DNS, port, security group, network policy và khả năng kết nối từ chính môi trường chạy của caller.

### Instance đã dừng nhưng vẫn xuất hiện

Với danh sách tĩnh, địa chỉ vẫn tồn tại cho đến khi cấu hình được cập nhật. Với registry, việc loại bỏ phụ thuộc heartbeat, lease, deregistration và cache. Kiểm tra cả trạng thái registry lẫn thời gian cache của supplier.

### Cấu hình static và registry cùng tồn tại gây nhầm lẫn

Nếu ứng dụng có nhiều triển khai discovery hoặc nhiều supplier, cần xác định rõ supplier nào đang cung cấp danh sách cho service ID. Đừng giả định rằng khai báo SimpleDiscoveryClient luôn được hợp nhất tự động với danh sách từ registry khác. Hãy kiểm tra cấu hình auto-configuration và supplier thực tế của phiên bản đang dùng.

### Tự chọn instance trong code nghiệp vụ

Lấy `getInstances(serviceId).get(0)` rồi tự tạo URL sẽ bỏ qua chính sách chọn instance, bộ lọc, cache và tích hợp retry của Spring Cloud LoadBalancer. Hãy dùng HTTP client được cấu hình `@LoadBalanced` cho request theo service ID; chỉ truy vấn DiscoveryClient trực tiếp khi cần quan sát hoặc xử lý nghiệp vụ chuyên biệt.

## 8. Chọn nguồn danh sách cho từng môi trường

Với môi trường local hoặc bài thực hành, SimpleDiscoveryClient giúp khai báo hai hoặc ba địa chỉ và quan sát cách LoadBalancer phân phối request mà không phải dựng registry. Mỗi instance có thể chạy trên một port khác nhau của cùng máy.

Với môi trường tích hợp hoặc production có nhiều bản sao được tạo và hủy thường xuyên, DiscoveryClient kết nối registry giúp client nhận được danh sách cập nhật theo vòng đời instance. Cần bổ sung cấu hình cache, timeout, health check và giám sát registry để danh sách có độ mới phù hợp.

Khi kiểm tra một request được định tuyến, hãy xác minh theo thứ tự:

1. URL của client chứa đúng service ID.
2. DiscoveryClient hoặc SimpleDiscoveryClient trả về danh sách instance như mong đợi.
3. ServiceInstanceListSupplier cung cấp đúng danh sách sau các bước cache và lọc.
4. Bộ chọn của LoadBalancer chọn một instance hợp lệ.
5. HTTP client kết nối được đến URI của instance.
6. Log và metric cho biết request đã đến instance nào, thời gian phản hồi và lỗi nếu có.

Việc quan sát cả danh sách đầu vào lẫn instance cuối cùng được chọn giúp phân biệt lỗi discovery với lỗi chọn instance hoặc lỗi kết nối. Khi đó, có thể xác định đúng lớp cần điều chỉnh thay vì thay đổi thuật toán load balancing khi dữ liệu instance ban đầu đã sai.

