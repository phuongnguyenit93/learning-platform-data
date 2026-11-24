# Khi nào cần sổ đăng ký và khi nào có thể dùng DNS

Trong một hệ thống microservice, consumer cần tìm được địa chỉ để gọi provider. Có hai cách phổ biến: tra cứu instance từ **sổ đăng ký dịch vụ (service registry)** hoặc phân giải **tên DNS** thành địa chỉ mạng. Cả hai đều giúp ứng dụng tránh phải ghi cứng IP của máy chủ, nhưng cung cấp mức thông tin và khả năng điều khiển khác nhau.

Không phải hệ thống nào dùng Spring Cloud cũng bắt buộc phải triển khai Eureka hay Consul. Nếu nền tảng đã cung cấp DNS ổn định cho dịch vụ, DNS có thể đáp ứng đầy đủ nhu cầu khám phá. Ngược lại, khi ứng dụng cần danh sách instance, metadata, trạng thái và chính sách chọn instance chi tiết, một registry chuyên dụng thường phù hợp hơn.

## 1. Hai cách khám phá dịch vụ

### Service registry

Service registry là nơi lưu thông tin về các dịch vụ và những instance đang cung cấp chúng. Khi một instance khởi động, discovery client đăng ký service ID, instance ID, host, port, metadata và thông tin trạng thái. Registry duy trì các bản ghi bằng heartbeat, lease hoặc health check tùy implementation.

Consumer hỏi registry để lấy các instance của một service ID. Với Spring Cloud, các abstraction thường gặp là:

- `ServiceRegistry`: đăng ký, hủy đăng ký và cập nhật trạng thái registration.
- `DiscoveryClient`: truy vấn service ID và danh sách `ServiceInstance`.
- `Spring Cloud LoadBalancer`: chọn một instance từ danh sách để gửi request.

Ví dụ, `order-service` có thể tra cứu `inventory-service` và nhận ba instance với địa chỉ khác nhau. LoadBalancer lựa chọn một instance phù hợp cho request.

### DNS

DNS ánh xạ tên miền hoặc tên dịch vụ sang dữ liệu địa chỉ. Consumer gửi truy vấn tới DNS resolver; resolver trả về bản ghi như A (IPv4), AAAA (IPv6), hoặc SRV (dịch vụ và cổng). Tên có thể được giữ ổn định trong khi địa chỉ phía sau thay đổi theo cập nhật DNS.

Ví dụ, thay vì gọi IP trực tiếp, ứng dụng kết nối tới:

```text
inventory.internal.example
```

DNS phân giải tên đó thành địa chỉ IP. Ứng dụng và hệ điều hành có thể lưu kết quả trong cache theo TTL và chính sách resolver.

Trong Kubernetes, Service thông thường có DNS name ổn định trỏ tới địa chỉ ClusterIP của Service. Với headless Service, DNS có thể trả về địa chỉ của các Pod endpoint thay vì một ClusterIP. Kubernetes cập nhật dữ liệu DNS dựa trên trạng thái Service và EndpointSlice theo cơ chế của nền tảng.

## 2. So sánh Service Registry và DNS

| Tiêu chí | Service registry | DNS |
|---|---|---|
| Định danh tra cứu | Service ID hoặc tên dịch vụ | DNS name |
| Kết quả | Danh sách instance và thông tin registration | Các bản ghi DNS như A, AAAA, SRV |
| Metadata | Thường hỗ trợ metadata tùy provider | Bản ghi DNS tiêu chuẩn không phải kho metadata tùy ý |
| Trạng thái instance | Có thể lưu trạng thái, heartbeat, lease hoặc health check | DNS cơ bản không phải health registry; có thể kết hợp health-aware DNS của nền tảng |
| Cân bằng tải | Có thể để client-side LoadBalancer chọn instance | Có thể dùng nhiều bản ghi, resolver hoặc load balancer phía hạ tầng |
| Cache và độ trễ | Có thể có cache ở registry client và LoadBalancer | Có TTL và cache tại resolver, hệ điều hành, runtime |
| Phụ thuộc nền tảng | Cần registry và discovery client tương ứng | Cần DNS resolver và quy ước tên |
| Tích hợp Spring Cloud | DiscoveryClient, ServiceRegistry, LoadBalancer | Phân giải tên thông qua network stack hoặc DNS-based discovery integration |

DNS không chỉ là một bảng ánh xạ tĩnh. DNS có thể được cập nhật tự động và được dùng để khám phá các endpoint động. Tuy vậy, DNS tiêu chuẩn tập trung vào phân giải tên; nó không cung cấp đầy đủ mô hình registration, trạng thái và metadata của một service registry chuyên dụng.

Ngược lại, registry cũng không tự động giải quyết mọi vấn đề kết nối. Consumer vẫn cần địa chỉ mạng có thể truy cập, cơ chế timeout, retry, load balancing và bảo vệ lưu lượng.

## 3. Khi nào DNS là đủ?

DNS thường là lựa chọn phù hợp khi nhu cầu khám phá đơn giản và hạ tầng đã quản lý tên dịch vụ.

### Dịch vụ có địa chỉ ổn định hoặc có lớp cân bằng tải phía trước

Nếu một dịch vụ có một hostname ổn định trỏ tới load balancer, consumer không cần biết từng replica phía sau. Ví dụ:

```text
https://payment.internal.example
```

Load balancer hoặc hạ tầng service phía sau hostname chịu trách nhiệm phân phối request tới các backend. Consumer chỉ cần kết nối tới tên ổn định đó.

Cách này phù hợp với:

- Hệ thống có ít dịch vụ và endpoint ít thay đổi.
- Các dịch vụ đã được expose qua internal load balancer.
- Ứng dụng không cần tự lựa chọn từng instance.
- Nền tảng vận hành đã cung cấp DNS và health-aware routing.

### Nền tảng đã có service discovery tích hợp

Trong Kubernetes, một Service cung cấp tên DNS ổn định cho các workload trong cluster. Ví dụ:

```text
http://inventory-service
http://inventory-service.shop.svc.cluster.local
```

Tên ngắn thường được phân giải trong namespace hiện tại theo search domain của Pod. Tên đầy đủ có dạng:

```text
<service>.<namespace>.svc.cluster.local
```

Service ClusterIP tạo một điểm truy cập ổn định; Kubernetes Service routing chuyển traffic tới các endpoint phù hợp. Với mô hình này, ứng dụng có thể gọi tên Service qua DNS mà không cần triển khai thêm Eureka hoặc Consul chỉ để tìm Pod.

Headless Service phù hợp khi client cần biết địa chỉ endpoint cụ thể, ví dụ một số hệ thống stateful hoặc giao thức cần kết nối trực tiếp tới từng member. Cần hiểu rõ hành vi DNS và cách client xử lý nhiều địa chỉ trả về.

### Các endpoint không cần metadata để lựa chọn

Nếu mọi backend tương đương nhau và hạ tầng đã xử lý health check, phân phối tải, loại bỏ endpoint lỗi, consumer thường không cần metadata như zone, phiên bản hoặc nhóm triển khai. Một hostname duy nhất có thể đáp ứng nhu cầu.

## 4. Khi nào nên dùng Service Registry?

Registry hữu ích khi ứng dụng cần hiểu nhiều hơn một tên có thể phân giải thành IP.

### Cần danh sách instance ở phía client

Một consumer có thể cần xem từng instance để tự chọn đích hoặc để Spring Cloud LoadBalancer thực hiện lựa chọn. Ví dụ, `DiscoveryClient.getInstances("inventory-service")` trả về danh sách `ServiceInstance` mà discovery client nhìn thấy.

Điều này hữu ích khi:

- Nhiều replica được thêm hoặc gỡ thường xuyên.
- Ứng dụng cần client-side load balancing.
- Có nhiều địa chỉ instance và muốn áp dụng chiến lược chọn riêng.
- Cần quan sát instance nào đang được registry công bố.

### Cần metadata để định tuyến

Một instance có thể mang metadata như:

```yaml
metadata:
  zone: zone-a
  version: v2
  capability: bulk-read
```

Consumer hoặc LoadBalancer có thể dùng thông tin này để ưu tiên cùng zone, chọn phiên bản phù hợp hoặc lọc theo năng lực. DNS A/AAAA tiêu chuẩn không cung cấp cơ chế metadata tùy ý tương đương; SRV bổ sung target và port nhưng không thay thế một kho metadata dịch vụ.

Nếu dùng metadata để định tuyến, cần quy định rõ ai ghi, ai đọc và cách xử lý khi metadata cũ hoặc sai lệch. Metadata không nên chứa bí mật hoặc dữ liệu nhạy cảm.

### Cần quản lý vòng đời instance

Registry chuyên dụng thường hỗ trợ các thao tác như:

- Đăng ký instance khi ứng dụng khởi động.
- Gia hạn heartbeat hoặc lease.
- Health check và cập nhật trạng thái.
- Hủy đăng ký khi ứng dụng dừng bình thường.
- Loại instance không còn khỏe khỏi danh sách có thể khám phá.

DNS động cũng có thể cập nhật record theo vòng đời workload, nhưng cơ chế phát hiện lỗi và thời gian loại record phụ thuộc nền tảng DNS hoặc controller quản lý record. Nếu yêu cầu vận hành cần trạng thái instance rõ ràng và API quản lý thống nhất, registry thường thuận tiện hơn.

### Cần chính sách chọn instance ở phía ứng dụng

Với Spring Cloud LoadBalancer, consumer có thể kết hợp danh sách instance từ DiscoveryClient với bộ lọc hoặc chiến lược lựa chọn. Ví dụ, hệ thống có thể ưu tiên instance cùng zone để giảm độ trễ, rồi fallback sang zone khác khi cần.

DNS thông thường để resolver hoặc hạ tầng mạng quyết định cách trả về và phân phối địa chỉ. Nếu ứng dụng cần quyết định ở cấp instance dựa trên metadata, registry cùng LoadBalancer là lựa chọn phù hợp hơn.

## 5. Ví dụ DNS trong Kubernetes và registry trong Spring Cloud

### Gọi Kubernetes Service bằng DNS

Giả sử namespace `shop` có Service tên `inventory-service`. Một Pod trong cùng namespace có thể gọi:

```java
String url = "http://inventory-service/api/items/42";
```

Nếu gọi từ namespace khác, có thể dùng tên đầy đủ:

```java
String url =
    "http://inventory-service.shop.svc.cluster.local/api/items/42";
```

DNS trả về địa chỉ của Service. Với Service dạng ClusterIP, client kết nối tới virtual IP ổn định và Kubernetes xử lý việc chuyển tiếp tới backend. Ứng dụng không cần tra cứu từng Pod IP.

Với headless Service, DNS trả về địa chỉ các endpoint. Client cần xử lý nhiều địa chỉ và hành vi cache phù hợp. Không nên giả định hai loại Service có cùng cơ chế phân phối request.

### Tra cứu qua Spring Cloud DiscoveryClient

Khi ứng dụng dùng Eureka hoặc Consul, có thể tra cứu danh sách instance theo service ID:

```java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class InventoryLookup {

    private final DiscoveryClient discoveryClient;

    public InventoryLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
```

Consumer nhận danh sách instance và thông tin như host, port, URI, metadata. Nếu chỉ cần gọi HTTP theo service ID, có thể dùng HTTP client được cấu hình với Spring Cloud LoadBalancer thay vì tự chọn phần tử trong danh sách.

Ví dụ với `RestTemplate`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

Sau đó gọi:

```java
String url = "http://inventory-service/api/items/42";
Item item = restTemplate.getForObject(url, Item.class);
```

Trong trường hợp này, `inventory-service` được xử lý như service ID bởi LoadBalancer và discovery client đã cấu hình. Cùng một chuỗi URL nhìn bề ngoài giống gọi DNS, nhưng cơ chế phân giải có thể khác: với DNS thuần, resolver tìm IP; với client có `@LoadBalanced`, LoadBalancer tìm instance qua discovery integration.

## 6. Kubernetes DNS có thay thế Eureka hoặc Consul không?

Trong một cluster Kubernetes, câu trả lời thường là **có thể**, nếu nhu cầu chỉ là tìm Service và để Kubernetes điều phối traffic. Kubernetes Service, DNS và EndpointSlice đã cung cấp một mô hình discovery tích hợp với nền tảng.

Tuy nhiên, cần đánh giá các yêu cầu sau trước khi bỏ registry riêng:

- Ứng dụng có cần khám phá instance ngoài cluster hoặc ở nhiều cluster không?
- Có cần metadata và bộ lọc instance tùy chỉnh không?
- Có cần client-side load balancing hoặc zone-aware selection ở tầng ứng dụng không?
- Có cần một registry chung cho workload chạy trên VM, bare metal và Kubernetes không?
- Các công cụ quan sát và quy trình vận hành hiện tại phụ thuộc API của Eureka/Consul không?
- Có yêu cầu kiểm soát registration độc lập với vòng đời Kubernetes Service không?

Nếu các yêu cầu này không tồn tại, thêm Eureka hoặc Consul có thể tạo thêm một thành phần cần triển khai, bảo vệ, giám sát và xử lý tính nhất quán mà không mang lại lợi ích tương xứng.

Nếu cần discovery thống nhất giữa nhiều môi trường, một registry chuyên dụng có thể bổ sung giá trị. Spring Cloud Kubernetes cũng cung cấp discovery integration để ứng dụng sử dụng thông tin Service/Endpoint của Kubernetes thông qua abstraction Spring Cloud; lựa chọn này cần được phân biệt với việc chạy một Eureka/Consul server riêng.

## 7. Có thể kết hợp DNS và Service Registry không?

Hai cơ chế có thể bổ trợ nhau.

Một mô hình thường gặp là dùng DNS để tìm địa chỉ của chính registry, sau đó discovery client kết nối tới registry và tra cứu các service instance. Ví dụ:

```yaml
eureka:
  client:
    service-url:
      defaultZone: http://eureka.internal.example:8761/eureka/
```

Tên `eureka.internal.example` được DNS phân giải thành địa chỉ Eureka server. Sau khi kết nối, consumer dùng DiscoveryClient để tra cứu `inventory-service`.

Một mô hình khác là dùng DNS cho các dịch vụ hạ tầng hoặc endpoint ổn định, còn registry dùng cho các microservice cần metadata và lựa chọn instance. Ví dụ, database có thể được truy cập qua DNS hoặc endpoint do nền tảng quản lý, trong khi các dịch vụ nghiệp vụ dùng Eureka/Consul.

Cần tránh thiết kế hai nguồn sự thật không đồng bộ cho cùng một nhóm instance. Nếu DNS và registry đều công bố danh sách backend, phải xác định hệ thống nào là nguồn dữ liệu gốc, thành phần nào cập nhật record, và cách xử lý khi một nguồn đã loại instance nhưng nguồn còn lại vẫn giữ địa chỉ cũ.

## 8. Các giới hạn cần cân nhắc

### TTL và cache DNS

Khi record DNS thay đổi, resolver và client có thể tiếp tục sử dụng kết quả đã cache cho đến khi TTL hết hạn hoặc cache bị làm mới theo chính sách của hệ thống. Một số runtime có thể có cache riêng. Vì vậy, cập nhật DNS không đảm bảo mọi consumer lập tức thấy địa chỉ mới.

TTL thấp giúp thay đổi có thể được nhìn thấy nhanh hơn nhưng làm tăng số truy vấn DNS. TTL cao giảm truy vấn nhưng kéo dài thời gian sử dụng bản ghi cũ. Hành vi thực tế còn phụ thuộc resolver, runtime và hạ tầng.

### Cache và độ trễ của registry

Registry cũng có thể có độ trễ: discovery client có cache, registry đồng bộ giữa các node hoặc LoadBalancer lưu danh sách instance trong một khoảng thời gian. Do đó, registry không đồng nghĩa với cập nhật tức thời.

Cần kiểm tra chu kỳ refresh, cache, heartbeat, health check và lease expiration theo từng implementation. Cả DNS lẫn registry đều cần chiến lược xử lý địa chỉ cũ và lỗi kết nối.

### Khả năng sẵn sàng của thành phần khám phá

Nếu DNS resolver không truy cập được, consumer có thể không phân giải được tên. Nếu registry không truy cập được, consumer có thể không lấy được danh sách instance mới. Một số discovery client vẫn sử dụng dữ liệu cache gần nhất, nhưng hành vi phụ thuộc implementation và cấu hình.

Cần giám sát thành phần khám phá như một phần của hạ tầng ứng dụng. Cấu hình timeout, retry và cache phải phù hợp với yêu cầu sẵn sàng; không nên retry vô hạn hoặc làm cho lỗi discovery gây nghẽn toàn bộ request thread.

## 9. Bảng quyết định lựa chọn

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Một hostname ổn định trỏ tới load balancer | DNS | Hạ tầng đã che giấu danh sách backend |
| Gọi Kubernetes Service trong cùng cluster | Kubernetes Service DNS | Nền tảng đã quản lý endpoint và routing |
| Khám phá các instance cụ thể bằng service ID | Service registry | Trả về danh sách instance và thông tin registration |
| Lọc instance theo zone, version hoặc metadata | Service registry | Có metadata và tích hợp client-side selection |
| Microservice nhỏ, endpoint ổn định, không cần metadata | DNS | Ít thành phần vận hành hơn |
| Workload nằm trên nhiều nền tảng và cần registry chung | Service registry | Có thể cung cấp một giao diện discovery thống nhất |
| Tìm địa chỉ của Eureka/Consul server | DNS | Registry vẫn có thể được định vị bằng hostname ổn định |
| Cần kết hợp endpoint ổn định và chọn instance ở client | DNS + registry | DNS định vị registry hoặc hạ tầng; registry cung cấp instance |

## 10. Quy trình ra quyết định

Trước khi thêm registry vào kiến trúc, hãy trả lời các câu hỏi theo thứ tự:

1. **Tên DNS hiện có đã đủ chưa?** Nếu hostname trỏ tới một load balancer có health check và phân phối tải phù hợp, consumer có thể không cần danh sách instance.
2. **Consumer có cần biết từng instance không?** Nếu cần, hãy xác định DNS hiện tại có cung cấp endpoint đủ chi tiết và client có thể xử lý nhiều địa chỉ hay không.
3. **Có cần metadata hoặc bộ lọc riêng không?** Nếu cần zone, version, capability hoặc chính sách lựa chọn ở tầng ứng dụng, registry thường đáp ứng tốt hơn.
4. **Nền tảng có service discovery sẵn không?** Kiểm tra Kubernetes Service/EndpointSlice hoặc khả năng của nền tảng trước khi triển khai registry thứ hai.
5. **Ai chịu trách nhiệm health và dọn dẹp endpoint?** Xác định rõ controller, agent, registry hay nền tảng sẽ cập nhật endpoint khi instance lỗi hoặc dừng.
6. **Độ trễ hội tụ có đáp ứng yêu cầu không?** Đánh giá TTL, cache, heartbeat, health check và thời gian refresh.
7. **Chi phí vận hành có tương xứng không?** Registry bổ sung khả năng nhưng cũng cần triển khai, bảo mật, backup/HA, giám sát và xử lý sự cố.

Không nên chọn registry chỉ vì kiến trúc có nhiều microservice. Cũng không nên chọn DNS chỉ vì DNS đã tồn tại. Hãy dựa trên dữ liệu mà consumer cần, nơi thực hiện cân bằng tải và khả năng mà nền tảng cung cấp.

## 11. Kết luận qua một tình huống thực tế

Giả sử hệ thống thương mại điện tử chạy toàn bộ workload trong Kubernetes. `order-service` gọi `inventory-service`, và Kubernetes Service đã cung cấp DNS ổn định, health/readiness được quản lý qua Pod và EndpointSlice, traffic được chuyển qua Service. Nếu consumer không cần chọn Pod theo metadata, Kubernetes DNS có thể là đủ; triển khai Eureka riêng chỉ để phân giải tên Service sẽ tăng thêm độ phức tạp.

Sau đó hệ thống mở rộng sang VM ở một trung tâm dữ liệu khác, cần tra cứu instance giữa nhiều nền tảng và ưu tiên cùng zone. Lúc này, một registry thống nhất như Eureka hoặc Consul có thể hữu ích vì consumer cần danh sách instance và metadata để lựa chọn. DNS vẫn có thể được dùng để tìm địa chỉ registry hoặc các endpoint hạ tầng ổn định.

Service discovery là bài toán tìm đích có thể phục vụ. DNS giải quyết tốt việc phân giải tên và là nền tảng discovery tự nhiên của nhiều môi trường; service registry mở rộng khả năng quản lý vòng đời, trạng thái và metadata của từng instance. Chọn cơ chế phù hợp giúp kiến trúc giữ được sự đơn giản cần thiết mà vẫn đáp ứng yêu cầu định tuyến và vận hành.
