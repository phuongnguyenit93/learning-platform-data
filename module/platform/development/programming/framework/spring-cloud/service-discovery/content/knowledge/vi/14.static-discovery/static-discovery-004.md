# Khám phá tĩnh không tự đăng ký hoặc tự phát hiện instance chết

Khám phá tĩnh (static discovery) là cách consumer tìm dịch vụ từ danh sách địa chỉ được khai báo sẵn trong cấu hình. Với Spring Cloud, SimpleDiscoveryClient có thể đọc danh sách URI theo service ID và trả về các ServiceInstance để ứng dụng hoặc Spring Cloud LoadBalancer sử dụng.

Ưu điểm của cách làm này là đơn giản: không cần triển khai Eureka Server, Consul hay một registry riêng chỉ để lưu danh sách instance. Tuy nhiên, danh sách tĩnh chỉ mô tả những địa chỉ đã được cấu hình. Nó không tự đăng ký khi provider khởi động, không tự hủy đăng ký khi provider dừng và cũng không tự xác định một instance đã chết.

Đây là giới hạn cần hiểu rõ khi chọn static discovery. Nếu địa chỉ hoặc trạng thái instance thay đổi, đội vận hành phải cập nhật nguồn cấu hình hoặc bổ sung một cơ chế health check và cập nhật endpoint khác. Bài viết giải thích cơ chế của SimpleDiscoveryClient, cách gọi dịch vụ, những điều nó không đảm nhiệm và cách vận hành an toàn.

## 1. Static discovery hoạt động như thế nào?

Trong mô hình static discovery, consumer biết trước danh sách URI của các instance. Danh sách được đặt trong file cấu hình, biến môi trường hoặc nguồn cấu hình được quản lý bên ngoài.

Ví dụ, order-service cần gọi inventory-service. Cấu hình chứa hai địa chỉ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
              - uri: http://10.0.2.16:8081
~~~

Service ID là inventory-service. Hai URI là hai instance mà consumer được cấu hình để biết. Khi consumer tra cứu service ID này, SimpleDiscoveryClient trả về danh sách ServiceInstance tương ứng.

~~~mermaid
flowchart LR
    CFG["Cấu hình tĩnh<br/>inventory-service"]
    D["SimpleDiscoveryClient"]
    LB["Spring Cloud LoadBalancer"]
    A["Instance A<br/>10.0.2.15:8081"]
    B["Instance B<br/>10.0.2.16:8081"]
    CFG --> D
    D -->|"Danh sách ServiceInstance"| LB
    LB -->|"Chọn một instance"| A
    LB -.->|"Request khác có thể chọn"| B
~~~

Danh sách này không được lấy từ quá trình provider đăng ký vào registry. Nó đến từ cấu hình của consumer. Do đó, provider có thể đang chạy nhưng không xuất hiện trong danh sách nếu chưa được khai báo; ngược lại, một địa chỉ có thể vẫn xuất hiện dù tiến trình ở đó đã dừng.

## 2. SimpleDiscoveryClient trong Spring Cloud

Spring Cloud Commons cung cấp abstraction DiscoveryClient để ứng dụng tra cứu dịch vụ theo service ID. SimpleDiscoveryClient là một implementation sử dụng thuộc tính cấu hình làm nguồn dữ liệu.

Các thành phần có vai trò như sau:

| Thành phần | Vai trò trong static discovery |
|---|---|
| SimpleDiscoveryClient | Đọc danh sách instance đã khai báo và trả về qua DiscoveryClient |
| Service ID | Khóa logic để consumer yêu cầu danh sách instance |
| ServiceInstance | Mô tả một URI instance cùng thông tin liên quan |
| Spring Cloud LoadBalancer | Chọn instance từ danh sách được discovery cung cấp |
| Provider | Ứng dụng thực sự xử lý request tại URI đã khai báo |

SimpleDiscoveryClient không phải một registry server. Nó không nhận lệnh đăng ký từ provider và không quản lý vòng đời instance trên các máy khác nhau.

### Cấu hình danh sách instance

Thuộc tính cấu hình có dạng:

~~~text
spring.cloud.discovery.client.simple.instances.<service-id>[<index>].uri
~~~

Ví dụ khai báo nhiều dịch vụ:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
              - uri: http://10.0.2.16:8081
            payment-service:
              - uri: https://10.0.4.20:8443
~~~

Mỗi service ID có thể có một hoặc nhiều URI. Danh sách chỉ có hiệu lực với ứng dụng đã nạp cấu hình đó. Nếu một consumer khác không có cùng cấu hình, nó có thể nhận danh sách khác hoặc không tìm thấy service.

Không cần cấu hình địa chỉ của mọi provider trên tất cả ứng dụng nếu kiến trúc đã dùng một nguồn cấu hình tập trung. Tuy nhiên, dù nguồn cấu hình được lưu ở đâu, SimpleDiscoveryClient vẫn cần nhận được danh sách URI hiện hành tại thời điểm nó tra cứu.

### Metadata tùy chọn

Instance có thể đi kèm metadata để mô tả zone hoặc nhóm triển khai:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://10.0.2.15:8081
                metadata:
                  zone: zone-a
                  version: v1
              - uri: http://10.0.3.21:8081
                metadata:
                  zone: zone-b
                  version: v2
~~~

Metadata là dữ liệu mô tả. Nó không tự tạo bộ lọc, không tự chọn zone gần nhất và không tự chuyển request sang phiên bản tương thích. Nếu muốn dùng zone hoặc version để định tuyến, cần có chính sách rõ ràng trong load balancer hoặc thành phần định tuyến của ứng dụng.

## 3. Static discovery không tự đăng ký provider

Trong mô hình registry động như Eureka hoặc Consul, provider thường đăng ký instance khi khởi động và hủy đăng ký khi dừng có kiểm soát. Registry giữ thông tin instance để consumer tra cứu.

Với SimpleDiscoveryClient, danh sách instance được consumer đọc từ cấu hình. Provider không cần gửi yêu cầu register tới SimpleDiscoveryClient, và SimpleDiscoveryClient cũng không cung cấp vòng đời đăng ký tương đương ServiceRegistry.

| Hoạt động | Registry động | Static discovery |
|---|---|---|
| Provider khởi động | Có thể tự đăng ký qua starter | Không tự thêm URI vào cấu hình consumer |
| Provider dừng có kiểm soát | Có thể deregister | Không tự xóa URI đã khai báo |
| Thêm instance | Provider hoặc nền tảng cập nhật registry | Người vận hành cập nhật danh sách cấu hình |
| Thay đổi host/port | Registry nhận registration mới | Phải cập nhật URI trong nguồn cấu hình |
| Consumer tra cứu | Đọc dữ liệu discovery từ registry/client cache | Đọc danh sách đã cấu hình |

Ví dụ, inventory-service được triển khai thêm instance tại 10.0.2.17:8081. Nếu cấu hình của consumer vẫn chỉ có hai URI cũ, SimpleDiscoveryClient không thể tự biết instance mới đã xuất hiện.

Tương tự, nếu instance 10.0.2.16:8081 dừng, URI đó vẫn nằm trong cấu hình cho đến khi nguồn cấu hình được cập nhật và ứng dụng nhận danh sách mới. Việc provider dừng không tự kích hoạt thao tác deregister trong static discovery.

## 4. Static discovery không tự phát hiện instance chết

SimpleDiscoveryClient trả về các instance được khai báo. Nó không mặc định gửi request định kỳ đến từng URI để kiểm tra tiến trình còn hoạt động hay không. Một lần tra cứu thành công chỉ chứng minh cấu hình có mục tương ứng; nó không chứng minh endpoint đang khỏe.

Giả sử danh sách có hai instance:

~~~text
inventory-service
  http://10.0.2.15:8081
  http://10.0.2.16:8081
~~~

Nếu instance thứ hai bị crash nhưng cấu hình chưa đổi, danh sách discovery vẫn có thể chứa cả hai URI. Khi LoadBalancer chọn instance thứ hai, request có thể thất bại vì connection refused, timeout hoặc lỗi TLS.

~~~mermaid
flowchart TD
    A["Danh sách URI tĩnh"] --> B["SimpleDiscoveryClient trả về hai instance"]
    B --> C["LoadBalancer chọn instance"]
    C --> D{"Endpoint có hoạt động?"}
    D -->|"Có"| E["Request được xử lý"]
    D -->|"Không"| F["Request lỗi hoặc timeout"]
    F --> G["Consumer xử lý lỗi theo timeout/retry/circuit breaker"]
    G --> H["Người vận hành hoặc cơ chế ngoài cập nhật cấu hình"]
~~~

Các khái niệm sau cần được phân biệt:

- **Discovery:** tìm địa chỉ mà ứng dụng được cấu hình để gọi.
- **Health check:** kiểm tra endpoint có đáp ứng tiêu chí sức khỏe hay không.
- **Failure detection:** phát hiện instance hoặc kết nối không còn hoạt động.
- **Deregistration:** loại instance khỏi nguồn đăng ký để consumer không tiếp tục nhận địa chỉ đó.

Static discovery giải quyết phần tra cứu từ cấu hình. Các hoạt động health check, failure detection và deregistration cần cơ chế bổ sung.

## 5. Gọi dịch vụ qua Spring Cloud LoadBalancer

Static discovery vẫn có thể kết hợp với Spring Cloud LoadBalancer. LoadBalancer nhận danh sách ServiceInstance từ discovery client và chọn instance cho request.

Ví dụ khai báo RestTemplate có tích hợp load balancing:

~~~java
@Configuration
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Consumer gọi bằng service ID:

~~~java
@Service
public class InventoryClient {

    private final RestTemplate restTemplate;

    public InventoryClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public ItemDto getItem(String itemId) {
        return restTemplate.getForObject(
            "http://inventory-service/api/items/{id}",
            ItemDto.class,
            itemId
        );
    }
}
~~~

Trong ví dụ, inventory-service là service ID. Spring Cloud LoadBalancer sử dụng DiscoveryClient để lấy các instance được cấu hình rồi chọn một instance cho request. Ứng dụng cần dependency Spring Cloud LoadBalancer tương thích với Spring Cloud release train đang dùng.

Load balancing không đồng nghĩa với health checking. Một thuật toán chọn instance có thể phân phối request qua các URI trong danh sách, nhưng nếu danh sách không được lọc hoặc cập nhật theo trạng thái sức khỏe, instance đã chết vẫn có thể được chọn.

### Truy vấn trực tiếp bằng DiscoveryClient

Khi cần quan sát danh sách instance, ứng dụng có thể gọi DiscoveryClient:

~~~java
@Service
public class InventoryDiscovery {

    private final DiscoveryClient discoveryClient;

    public InventoryDiscovery(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> getInstances() {
        return discoveryClient.getInstances("inventory-service");
    }
}
~~~

Kết quả phản ánh danh sách đã khai báo mà client đang biết. Không nên xem danh sách này là danh sách endpoint đã vượt qua health check.

## 6. Quản lý thay đổi địa chỉ và số lượng instance

Vì danh sách tĩnh không tự đồng bộ với vòng đời provider, đội vận hành cần một quy trình cập nhật rõ ràng.

Khi thêm instance:

1. Triển khai provider và xác nhận API có thể truy cập từ consumer.
2. Kiểm tra health endpoint hoặc cơ chế kiểm tra ngoài.
3. Thêm URI vào cấu hình của các consumer liên quan.
4. Phát hành hoặc refresh cấu hình theo cơ chế ứng dụng hỗ trợ.
5. Xác minh consumer đã nhận URI mới và LoadBalancer có thể chọn instance đó.

Khi loại bỏ instance:

1. Ngừng phân phối request mới tới instance theo quy trình rollout.
2. Chờ request đang xử lý hoàn tất nếu cần.
3. Xóa URI khỏi nguồn cấu hình.
4. Đảm bảo consumer đã nạp danh sách mới và cache liên quan được làm mới.
5. Sau đó mới dừng tiến trình provider.

Nếu dừng instance trước khi consumer cập nhật cấu hình, request vẫn có thể được gửi tới địa chỉ cũ. Vì vậy, thao tác cập nhật danh sách và thao tác dừng provider cần được phối hợp.

### Cấu hình trong file và cấu hình tập trung

Với hệ thống nhỏ, danh sách có thể nằm trực tiếp trong application.yml. Khi có nhiều consumer, việc sao chép cùng một danh sách vào từng repository dễ tạo sai lệch.

Có thể quản lý danh sách trong một nguồn cấu hình tập trung, ví dụ Spring Cloud Config hoặc hệ thống quản lý cấu hình nội bộ. Tuy nhiên, thay đổi ở nguồn cấu hình không đảm bảo mọi ứng dụng đang chạy tự động cập nhật danh sách ngay lập tức. Cần xác định cơ chế refresh, thời điểm rebind property, cách làm mới DiscoveryClient hoặc supplier, và cache của LoadBalancer theo phiên bản đang dùng.

Không nên chỉ thay file cấu hình trên máy chủ rồi giả định ứng dụng đã nhận URI mới. Hãy kiểm tra giá trị cấu hình sau refresh và kết quả getInstances từ consumer.

## 7. Bổ sung health check và failure detection

Nếu muốn phát hiện instance chết, có thể bổ sung một trong các cơ chế sau:

| Cơ chế | Cách hoạt động | Điều cần lưu ý |
|---|---|---|
| Health check từ load balancer/proxy | Thành phần định tuyến kiểm tra endpoint và loại đích không khỏe | Cần cấu hình probe, timeout và tiêu chí phục hồi |
| Health-check supplier phía client | Supplier kiểm tra instance và cung cấp danh sách đã lọc cho LoadBalancer | Cần cấu hình rõ ràng; không phải hành vi mặc định của SimpleDiscoveryClient |
| Orchestrator readiness probe | Nền tảng đánh giá readiness và cập nhật endpoint/service routing | Consumer phải đi qua cơ chế endpoint của orchestrator hoặc đồng bộ trạng thái tương ứng |
| Registry động | Provider đăng ký, health check hoặc heartbeat cập nhật trạng thái trong registry | Cần vận hành Eureka, Consul hoặc registry tương ứng |
| Giám sát ngoài | Monitor kiểm tra endpoint và cập nhật nguồn cấu hình | Cần tránh race condition và cập nhật sai instance |

Một health check đơn giản có thể gọi endpoint Actuator:

~~~bash
curl --fail --max-time 2 http://10.0.2.15:8081/actuator/health
~~~

Lệnh này chỉ minh họa phép kiểm tra thủ công. Muốn tự động kiểm tra, cần có thành phần chạy probe theo chu kỳ, diễn giải kết quả và cập nhật danh sách đích hoặc trạng thái định tuyến. Không nên đặt một đoạn script kiểm tra rời rạc rồi mặc định nó đã loại instance khỏi SimpleDiscoveryClient.

### Health check phía client với LoadBalancer

Spring Cloud LoadBalancer có thể được cấu hình với supplier hỗ trợ health check trong các phiên bản phù hợp. Cơ chế này cần được cấu hình rõ endpoint, chu kỳ kiểm tra và cách tạo HTTP client. Nó bổ sung bước lọc instance cho LoadBalancer, nhưng không biến SimpleDiscoveryClient thành registry có đăng ký/deregister.

Khi dùng health-check supplier, cần đánh giá:

- Endpoint health có phản ánh readiness của API cần gọi không?
- Probe chạy từ mạng của consumer có truy cập được instance không?
- Timeout và chu kỳ kiểm tra có phù hợp với số lượng instance không?
- Khi endpoint phục hồi, instance được đưa lại vào danh sách theo cách nào?
- Có cache nào khiến trạng thái mới được áp dụng chậm không?

Không dùng health check quá thường xuyên nếu số lượng consumer và instance lớn, vì tổng số probe có thể tạo tải đáng kể lên provider.

## 8. Timeout, retry và circuit breaker vẫn cần thiết

Ngay cả khi có health check, trạng thái instance có thể thay đổi giữa hai lần probe. Một instance khỏe ở thời điểm kiểm tra có thể dừng ngay trước khi nhận request. Vì vậy, consumer cần xử lý lỗi kết nối trong luồng request thực tế.

- **Connection timeout:** giới hạn thời gian chờ thiết lập kết nối.
- **Response timeout:** giới hạn thời gian chờ phản hồi.
- **Retry:** thử lại có giới hạn khi lỗi phù hợp và thao tác an toàn.
- **Circuit breaker:** tạm ngăn request tới một đích hoặc dependency đang lỗi liên tục.
- **Fallback:** trả kết quả thay thế hoặc thông báo lỗi có kiểm soát khi không thể gọi provider.

Retry cần chú ý tính idempotent. Nếu request tạo đơn hàng hoặc trừ tiền đã đến provider nhưng response bị mất, gửi lại request có thể gây thao tác trùng nếu không có idempotency key hoặc cơ chế chống lặp.

Không nên dùng retry vô hạn để che giấu danh sách URI cũ. Nếu một instance đã bị loại khỏi hệ thống, cần cập nhật nguồn cấu hình hoặc cơ chế health check để ngừng chọn địa chỉ đó.

## 9. Khi nào static discovery phù hợp?

Static discovery phù hợp khi:

- Số lượng instance ít và địa chỉ tương đối ổn định.
- Môi trường phát triển, demo hoặc integration test cần cấu hình đơn giản.
- Hệ thống có một số endpoint cố định được quản lý bởi đội vận hành.
- Consumer gọi một virtual IP hoặc DNS ổn định của load balancer bên ngoài.
- Không cần provider tự đăng ký và số lần thay đổi topology thấp.

Static discovery kém phù hợp khi:

- Instance được autoscale thường xuyên.
- Container hoặc pod liên tục được tạo mới và thay địa chỉ.
- Nhiều consumer cần cập nhật endpoint gần thời gian thực.
- Cần tự động loại instance chết khỏi danh sách discovery.
- Hệ thống cần health status, metadata và chính sách định tuyến phức tạp.

Trong các tình huống này, registry động hoặc một nền tảng orchestration có service endpoint cập nhật tự động thường phù hợp hơn.

## 10. So sánh static discovery và registry động

| Tiêu chí | Static discovery | Registry động |
|---|---|---|
| Nguồn danh sách instance | Cấu hình được khai báo | Registry nhận đăng ký từ provider |
| Đăng ký provider | Không tự động | Thường được tích hợp qua starter/API |
| Hủy đăng ký | Cập nhật cấu hình thủ công hoặc cơ chế ngoài | Có thể deregister khi shutdown |
| Phát hiện instance chết | Không tự có | Có thể dùng heartbeat/health check |
| Thay đổi địa chỉ | Cập nhật cấu hình và refresh consumer | Provider đăng ký địa chỉ mới |
| Hạ tầng bổ sung | Ít thành phần hơn | Cần registry hoặc nền tảng tương ứng |
| Vận hành | Đơn giản khi topology ổn định | Phù hợp topology thay đổi thường xuyên |

Static discovery không phải thiết kế sai. Nó chỉ có phạm vi trách nhiệm hẹp hơn. Nếu danh sách endpoint ổn định và được quản lý tốt, cách làm này có thể đơn giản, dễ kiểm thử và đủ dùng.

## 11. Checklist vận hành static discovery

Trước khi triển khai:

1. Xác nhận mỗi service ID có đúng danh sách URI cần dùng.
2. Kiểm tra host, port, scheme và chứng thư TLS từ mạng consumer.
3. Xác nhận từng provider đã sẵn sàng trước khi thêm URI.
4. Kiểm tra LoadBalancer thực sự sử dụng SimpleDiscoveryClient.
5. Đặt timeout kết nối và phản hồi phù hợp.
6. Xác định ai chịu trách nhiệm cập nhật danh sách khi thêm, thay hoặc xóa instance.
7. Nếu có health check, xác định thành phần thực hiện probe và cách loại đích lỗi.
8. Kiểm tra cache và cơ chế refresh để biết khi nào danh sách mới có hiệu lực.
9. Có quy trình rollback nếu cấu hình chứa địa chỉ sai.
10. Theo dõi lỗi kết nối, timeout, số lần retry và tỷ lệ request thất bại theo instance.

Khi có sự cố:

- Kiểm tra danh sách URI mà consumer thực sự đang sử dụng.
- Gọi trực tiếp endpoint từ môi trường chạy consumer.
- Phân biệt lỗi DNS, TCP, TLS, HTTP và lỗi nghiệp vụ.
- Kiểm tra instance có còn nằm trong cấu hình hay không.
- Nếu endpoint đã bị loại bỏ, cập nhật nguồn cấu hình và xác nhận consumer đã refresh.
- Nếu endpoint còn được giữ lại có chủ đích, bổ sung health check hoặc chính sách định tuyến phù hợp.

## 12. Nguyên tắc cần nhớ

- SimpleDiscoveryClient đọc danh sách instance từ cấu hình theo service ID.
- Static discovery không tự đăng ký provider và không tự deregister khi provider dừng.
- Danh sách URI không tự phản ánh tình trạng sống/chết của instance.
- Spring Cloud LoadBalancer chọn instance từ danh sách nhưng không mặc định biến danh sách tĩnh thành danh sách đã health check.
- Muốn phát hiện instance chết, phải bổ sung health check, load balancer/proxy có kiểm tra sức khỏe, orchestrator hoặc registry động.
- Khi thay đổi danh sách, cần cập nhật cấu hình, refresh discovery và xử lý cache theo phiên bản Spring Cloud đang dùng.
- Luôn có timeout và xử lý lỗi request vì health check không thể loại bỏ hoàn toàn race condition.

Khám phá tĩnh là một cách tra cứu dịch vụ đơn giản dựa trên danh sách địa chỉ đã biết. Nó phù hợp với topology ổn định và môi trường nhỏ, nhưng không thay thế vòng đời đăng ký, heartbeat hay health check. Khi hệ thống bắt đầu co giãn thường xuyên hoặc cần tự động loại instance lỗi, hãy bổ sung cơ chế quản lý endpoint phù hợp hoặc chuyển sang registry động như Eureka, Consul hay discovery của nền tảng triển khai.
