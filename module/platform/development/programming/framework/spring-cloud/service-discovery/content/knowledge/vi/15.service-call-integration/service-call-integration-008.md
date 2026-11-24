# Dùng metadata để lọc instance theo vùng hoặc phiên bản

Một service trong microservice có thể chạy nhiều instance ở các zone, region hoặc phiên bản ứng dụng khác nhau. Consumer thường tra cứu service theo một service ID chung, nhưng không phải request nào cũng nên được gửi đến mọi instance. Ví dụ, order-service có thể ưu tiên inventory-service trong cùng zone để giảm độ trễ; một consumer đang dùng hợp đồng API v2 có thể chỉ gọi instance cung cấp version v2.

Service registry lưu metadata cùng thông tin định vị của instance. Spring Cloud đưa metadata đó vào ServiceInstance, để consumer hoặc Spring Cloud LoadBalancer có thể dùng làm tiêu chí lựa chọn. Tuy nhiên, metadata chỉ là dữ liệu mô tả. Muốn lọc theo zone hoặc version, ứng dụng phải cấu hình supplier hoặc chính sách định tuyến sử dụng các trường đó.

Bài viết này giải thích cách provider công bố metadata, cách bật ưu tiên zone có sẵn trong Spring Cloud LoadBalancer, cách xây dựng bộ lọc version, và cách xử lý khi không có instance phù hợp.

## 1. Metadata gắn với từng service instance

Service ID xác định dịch vụ logic, còn metadata mô tả thuộc tính của một instance cụ thể. Ví dụ, ba instance cùng đăng ký dưới service ID inventory-service nhưng chạy ở các zone và phiên bản khác nhau:

~~~text
inventory-service
  instance A: 10.0.1.11:8081  zone=zone-a  version=v1
  instance B: 10.0.1.12:8081  zone=zone-a  version=v2
  instance C: 10.0.2.21:8081  zone=zone-b  version=v2
~~~

Metadata thường là các cặp key-value dạng chuỗi. Một số key phổ biến:

| Key | Ví dụ | Mục đích |
|---|---|---|
| zone | zone-a | Khu vực triển khai của instance |
| region | ap-southeast-1 | Vùng địa lý hoặc vùng hạ tầng |
| version | v2 | Phiên bản ứng dụng hoặc API mà instance cung cấp |
| deployment-group | blue, green, canary | Nhóm rollout |
| protocol | https | Thuộc tính kết nối bổ sung nếu hệ thống cần |

Tên key và giá trị phải được thống nhất giữa provider và consumer. Nên chọn quy ước chữ thường, giá trị ổn định và tránh dùng các biến thể như Zone, availability-zone, AZ cho cùng một ý nghĩa nếu chưa có quy tắc ánh xạ.

Metadata không thay thế host, port hoặc URI. Nó cũng không tự tạo một ranh giới bảo mật. Consumer vẫn cần xác thực và phân quyền với provider theo cơ chế bảo mật của hệ thống.

## 2. Provider công bố metadata trong registry

Provider khai báo metadata khi đăng ký instance. Cách cấu hình phụ thuộc registry đang dùng.

### Với Eureka

Spring Cloud Netflix Eureka Client hỗ trợ metadata-map trong cấu hình instance:

~~~yaml
spring:
  application:
    name: inventory-service

eureka:
  instance:
    metadata-map:
      zone: zone-a
      region: ap-southeast-1
      version: v2
      deployment-group: green
~~~

Các cặp key-value này được công bố cùng bản ghi instance. Khi consumer nhận ServiceInstance, metadata có thể được đọc qua getMetadata().

### Với Consul

Spring Cloud Consul Discovery hỗ trợ metadata và tags cho service registration:

~~~yaml
spring:
  application:
    name: inventory-service
  cloud:
    consul:
      discovery:
        service-name: inventory-service
        metadata:
          zone: zone-a
          region: ap-southeast-1
          version: v2
          deployment-group: green
        tags:
          - version-v2
          - deployment-green
~~~

Metadata phù hợp để consumer đọc như thuộc tính của instance. Tags hữu ích cho truy vấn hoặc công cụ Consul cần lọc theo tag. Hai cơ chế có cách biểu diễn khác nhau; hãy chọn đúng loại dữ liệu và kiểm tra hành vi của phiên bản Spring Cloud Consul đang dùng.

### Kiểm tra metadata ở consumer

Consumer có thể xem metadata của các instance đã được phát hiện:

~~~java
List<ServiceInstance> instances =
    discoveryClient.getInstances("inventory-service");

for (ServiceInstance instance : instances) {
    String zone = instance.getMetadata().get("zone");
    String version = instance.getMetadata().get("version");

    log.info(
        "Instance {}:{} zone={} version={}",
        instance.getHost(),
        instance.getPort(),
        zone,
        version
    );
}
~~~

DiscoveryClient trả về danh sách instance mà implementation hiện biết. Nếu metadata bị thiếu, hãy kiểm tra provider đã đăng ký đúng cấu hình chưa, registry có lưu các trường đó không và consumer đang đọc đúng registry/service ID không.

## 3. Lọc theo zone: ưu tiên instance gần consumer

Trong hệ thống triển khai nhiều zone, gọi instance cùng zone có thể giảm độ trễ và chi phí truyền dữ liệu liên vùng. Spring Cloud LoadBalancer cung cấp ZonePreferenceServiceInstanceListSupplier để ưu tiên instance có metadata zone trùng với zone của consumer.

Ví dụ provider công bố:

~~~yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
~~~

Consumer khai báo zone của chính nó:

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

Sau đó cấu hình supplier dùng zone preference cho LoadBalancer:

~~~java
@Bean
ServiceInstanceListSupplier serviceInstanceListSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withZonePreference()
        .build(context);
}
~~~

Với cấu hình này, supplier ưu tiên các instance có metadata zone phù hợp với zone được cấu hình cho consumer. Hành vi zone preference là **ưu tiên**, không nhất thiết là bộ lọc cứng: nếu không tìm thấy instance cùng zone, supplier có thể trả về danh sách instance ở zone khác để request vẫn có cơ hội được xử lý.

Điều này thường phù hợp với định tuyến theo locality. Nếu yêu cầu nghiệp vụ bắt buộc không được gọi sang zone khác, cần một bộ lọc cứng riêng và phải chấp nhận trường hợp không có instance khả dụng.

### Zone preference khác với lọc region

Zone và region không phải lúc nào cũng cùng cấp. Một region có thể chứa nhiều zone. Nếu chỉ đặt zone, consumer thường ưu tiên zone cụ thể; nếu muốn giới hạn ở một region, cần metadata region và chính sách lọc tương ứng.

~~~text
region ap-southeast-1
  zone-a
    inventory instance A
  zone-b
    inventory instance B

region ap-southeast-2
  zone-c
    inventory instance C
~~~

Nếu consumer ở ap-southeast-1, chỉ so khớp zone mà không kiểm tra region có thể không diễn đạt đúng chính sách mong muốn trong một hệ thống có zone name không duy nhất giữa các region. Khi cần, dùng cặp region/zone hoặc một giá trị định danh zone toàn cục theo quy ước hạ tầng.

## 4. Lọc theo phiên bản ứng dụng hoặc API

Zone thường là tiêu chí ưu tiên để tối ưu vị trí. Version có thể là tiêu chí tương thích bắt buộc. Ví dụ, consumer sử dụng API v2 không nên gửi request đến instance chỉ hỗ trợ API v1 nếu hai hợp đồng không tương thích.

Một chính sách lọc version chính xác có thể là:

~~~text
Consumer yêu cầu version=v2
  Instance A version=v1  -> loại
  Instance B version=v2  -> giữ
  Instance C không có version -> loại
~~~

Nếu không có instance mang version phù hợp, danh sách kết quả nên rỗng để LoadBalancer báo không có instance khả dụng. Không nên âm thầm trả về mọi version khi version là điều kiện tương thích bắt buộc.

### Tạo supplier lọc metadata

Spring Cloud LoadBalancer cho phép tùy biến ServiceInstanceListSupplier. Ví dụ sau bọc một supplier lấy danh sách từ discovery và chỉ giữ các instance có metadata khớp version yêu cầu.

~~~java
public final class MetadataFilterServiceInstanceListSupplier
        implements ServiceInstanceListSupplier {

    private final ServiceInstanceListSupplier delegate;
    private final String metadataKey;
    private final String requiredValue;

    public MetadataFilterServiceInstanceListSupplier(
            ServiceInstanceListSupplier delegate,
            String metadataKey,
            String requiredValue) {
        this.delegate = delegate;
        this.metadataKey = metadataKey;
        this.requiredValue = requiredValue;
    }

    @Override
    public String getServiceId() {
        return delegate.getServiceId();
    }

    @Override
    public Flux<List<ServiceInstance>> get() {
        return delegate.get().map(this::filter);
    }

    @Override
    public Flux<List<ServiceInstance>> get(Request request) {
        return delegate.get(request).map(this::filter);
    }

    private List<ServiceInstance> filter(
            List<ServiceInstance> instances) {
        return instances.stream()
            .filter(instance -> requiredValue.equals(
                instance.getMetadata().get(metadataKey)))
            .collect(Collectors.toList());
    }
}
~~~

Supplier cấu hình cho inventory-service có thể bọc discovery supplier như sau:

~~~java
@Configuration(proxyBeanMethods = false)
public class InventoryLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context,
            Environment environment) {

        String requiredVersion = environment.getRequiredProperty(
            "app.discovery.inventory.required-version");

        ServiceInstanceListSupplier delegate =
            ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);

        return new MetadataFilterServiceInstanceListSupplier(
            delegate, "version", requiredVersion);
    }
}
~~~

Gắn cấu hình vào LoadBalancer dành riêng cho service:

~~~java
@SpringBootApplication
@LoadBalancerClient(
    name = "inventory-service",
    configuration = InventoryLoadBalancerConfiguration.class
)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Consumer khai báo version mong muốn:

~~~yaml
app:
  discovery:
    inventory:
      required-version: v2
~~~

Các import chính của supplier gồm ServiceInstance, Request, ServiceInstanceListSupplier, Flux, List và Collectors. Cấu hình LoadBalancer nên nằm ngoài phạm vi component scan mặc định của ứng dụng, hoặc được tổ chức trong package không bị scan như cấu hình toàn cục. Nếu bean supplier của riêng inventory-service bị scan như cấu hình mặc định toàn ứng dụng, nó có thể ảnh hưởng đến các service khác.

Đây là ví dụ lọc exact match cho một service ID. API cụ thể của Spring Cloud LoadBalancer có thể thay đổi theo release train; hãy dùng cùng phiên bản Spring Cloud BOM với ứng dụng và đối chiếu chữ ký interface khi triển khai. Nếu ứng dụng cần lựa chọn version khác nhau theo từng request hoặc từng nhóm caller, hãy đưa yêu cầu vào request context/hint và xây dựng supplier dựa trên request thay vì cố định một version trong cấu hình toàn service.

## 5. Kết hợp zone và version

Một chính sách thường gặp là lọc theo version trước, sau đó ưu tiên zone trong tập instance còn lại. Ví dụ consumer yêu cầu version=v2, ở zone-a:

~~~text
Danh sách discovery
  A: zone-a, version=v1
  B: zone-a, version=v2
  C: zone-b, version=v2
  D: zone-b, version=v1

Sau lọc version=v2
  B: zone-a, version=v2
  C: zone-b, version=v2

Sau zone preference zone-a
  B được ưu tiên
~~~

Thứ tự các supplier ảnh hưởng đến kết quả vì mỗi supplier nhận đầu ra của supplier trước. Nếu dùng version như điều kiện bắt buộc và zone như tiêu chí ưu tiên, cần bảo đảm bộ lọc version không bị một fallback phía sau làm rộng danh sách trở lại. Nếu không có v2 trong zone-a nhưng có v2 ở zone-b, zone preference có thể fallback sang zone-b; nếu không có v2 ở bất kỳ zone nào, kết quả vẫn rỗng.

Với zone preference tích hợp sẵn và version filter tùy chỉnh, hãy kiểm tra chuỗi supplier thực tế được tạo trong đúng phiên bản Spring Cloud. Có thể cấu hình một supplier tùy chỉnh kết hợp cả hai bước nếu cần kiểm soát chính xác thứ tự và fallback.

## 6. Lọc theo metadata khác

Cùng một kỹ thuật có thể áp dụng cho deployment-group, region, protocol hoặc các nhãn vận hành khác.

Ví dụ lọc riêng nhóm green:

~~~yaml
eureka:
  instance:
    metadata-map:
      deployment-group: green
      version: v2
      zone: zone-a
~~~

Consumer có thể dùng supplier lọc deployment-group=green trong một luồng kiểm thử hoặc rollout. Với canary, chỉ lọc theo nhãn canary chưa đủ để triển khai phần trăm lưu lượng; cần thêm chính sách phân phối có kiểm soát, quan sát kết quả và khả năng rollback.

Nếu metadata biểu diễn một giá trị dạng danh sách hoặc tập tính năng, hãy quy định định dạng và phép so sánh rõ ràng. Không nên nhét nhiều ý nghĩa vào một chuỗi khó phân tích như zone-a-v2-green.

## 7. Xử lý khi không có instance phù hợp

Lọc metadata có thể khiến danh sách rỗng. Đây là kết quả hợp lệ nếu không có instance đáp ứng điều kiện. Consumer cần xử lý trường hợp này như một tình trạng không có đích gọi.

| Tình huống | Hành vi nên cân nhắc |
|---|---|
| Không có instance cùng zone | Nếu zone chỉ là ưu tiên, fallback sang zone khác |
| Không có instance đúng version bắt buộc | Trả lỗi không có instance tương thích; không tự gọi version khác |
| Metadata bị thiếu | Loại instance nếu trường đó là điều kiện bắt buộc; cảnh báo cấu hình provider |
| Metadata sai chính tả hoặc sai quy ước | Không khớp filter; sửa quy ước và registration |
| Registry chưa cập nhật metadata mới | Chờ refresh hoặc làm mới discovery cache theo cơ chế triển khai |
| Cache giữ metadata cũ | Kiểm tra TTL và các lớp cache của registry client/LoadBalancer |

Không nên dùng fallback chung cho mọi loại metadata. Zone có thể là tiêu chí ưu tiên vì mục tiêu là giảm độ trễ; version có thể là điều kiện hợp đồng bắt buộc. Chính sách fallback phải phản ánh ý nghĩa của từng trường.

## 8. Metadata không thay thế bảo mật

Metadata do provider đăng ký là dữ liệu phục vụ discovery và định tuyến. Nó không phải bằng chứng xác thực. Một instance có thể khai báo version=v2 hoặc environment=production, nhưng consumer không nên dựa vào nhãn này để cấp quyền truy cập dữ liệu hoặc chức năng nhạy cảm.

Hãy tiếp tục sử dụng TLS, xác thực service-to-service, authorization và network policy. Nếu metadata được dùng để chọn endpoint có yêu cầu bảo mật khác nhau, cần xác minh chứng thư và danh tính service ở lớp kết nối.

## 9. Kiểm thử chính sách lọc

Trước khi triển khai, nên kiểm thử các trường hợp:

1. Tất cả instance có metadata đầy đủ và chỉ một version phù hợp.
2. Có nhiều instance cùng version nhưng khác zone.
3. Không có instance cùng zone nhưng vẫn có instance đúng version ở zone khác.
4. Không có instance đúng version ở bất kỳ zone nào.
5. Một instance thiếu metadata hoặc dùng giá trị sai quy ước.
6. Provider đổi metadata và consumer nhận dữ liệu mới sau refresh.
7. Cache chưa hết TTL trong khi metadata đã thay đổi.
8. Các service ID khác không bị ảnh hưởng bởi cấu hình LoadBalancer dành riêng cho inventory-service.

Nên kiểm tra cả danh sách supplier trả về và request thực tế được gửi tới instance nào. Log có thể ghi service ID, version/zone yêu cầu, số instance trước và sau lọc; tránh ghi thông tin nhạy cảm hoặc tạo metric label có cardinality quá cao.

## 10. Nguyên tắc thiết kế

- Provider công bố metadata nhất quán trong Eureka hoặc Consul.
- Dùng ServiceInstance.getMetadata() để đọc thuộc tính instance ở consumer.
- Dùng ZonePreferenceServiceInstanceListSupplier khi zone là tiêu chí ưu tiên và fallback liên vùng được chấp nhận.
- Dùng supplier lọc metadata tùy chỉnh khi version, region hoặc deployment group là điều kiện bắt buộc.
- Phân biệt lọc cứng với ưu tiên; không dùng fallback của zone cho điều kiện tương thích version.
- Xác định hành vi khi metadata thiếu hoặc không có instance phù hợp.
- Giữ cấu hình LoadBalancer riêng cho đúng service ID và kiểm tra thứ tự supplier.
- Làm mới cache khi metadata thay đổi và quan sát độ trễ đồng bộ.
- Không dùng metadata làm cơ chế xác thực hoặc phân quyền.

Metadata giúp consumer chọn instance theo thuộc tính triển khai thay vì chỉ dựa trên danh sách địa chỉ. Khi kết hợp metadata provider với ServiceInstanceListSupplier, Spring Cloud LoadBalancer có thể ưu tiên zone gần hoặc lọc đúng version. Điều quan trọng là xác định rõ trường nào chỉ mang tính ưu tiên, trường nào là điều kiện bắt buộc và hệ thống phải phản ứng ra sao khi không còn instance phù hợp.
