# Khám phá dịch vụ theo môi trường local, máy ảo và container

Spring Cloud LoadBalancer chỉ có thể chọn một bản sao khi ứng dụng gọi biết danh sách các `ServiceInstance` có thể truy cập. Trong môi trường local, danh sách này thường được khai báo tĩnh để thử nghiệm. Khi chạy trên máy ảo hoặc container, địa chỉ và số lượng bản sao thay đổi theo quá trình triển khai, vì vậy ứng dụng thường cần một nguồn discovery động hoặc cơ chế discovery do nền tảng cung cấp.

Điểm cần giữ nhất quán ở mọi môi trường là **service ID**. Ứng dụng gọi dịch vụ dùng tên logic như `catalog-service`; discovery phân giải tên đó thành các instance có địa chỉ mạng cụ thể; LoadBalancer chọn một instance; HTTP client gửi request đến địa chỉ đã chọn. Khác biệt giữa local, máy ảo và container nằm ở cách các instance được tạo, công bố địa chỉ và giữ cho địa chỉ đó có thể truy cập từ ứng dụng gọi.

## 1. Service ID và địa chỉ instance trong từng môi trường

Một instance thường được biểu diễn bởi thông tin như host, port, trạng thái secure và metadata. Ví dụ:

| Thuộc tính | Ví dụ | Vai trò |
|---|---|---|
| Service ID | `catalog-service` | Tên logic để tra cứu nhóm bản sao |
| Host | `10.20.1.15` | Địa chỉ mà ứng dụng gọi có thể kết nối |
| Port | `8081` | Cổng ứng dụng đang lắng nghe |
| Secure | `false` | Cho biết instance dùng HTTP hay HTTPS theo thông tin instance |
| Metadata | `zone=az-a`, `version=v2` | Thông tin bổ sung có thể dùng để lọc hoặc định tuyến |

Service ID ổn định qua các lần triển khai, còn host và port có thể thay đổi. Một instance có thể được khởi động lại trên máy khác, chuyển sang IP khác hoặc được thay bằng container mới. Vì thế, không nên gắn địa chỉ IP của một bản sao vào mã nguồn client.

Địa chỉ được discovery công bố phải là địa chỉ mà **ứng dụng gọi** truy cập được. `localhost` chỉ trỏ về chính network namespace của tiến trình đang gọi. Nếu ứng dụng gọi chạy trong container, `localhost:8081` là cổng của container gọi, không phải cổng của container dịch vụ đích. Đây là một trong những nguyên nhân phổ biến khiến cấu hình discovery chạy được trên máy cá nhân nhưng thất bại sau khi đưa vào container.

## 2. Môi trường local: bắt đầu bằng danh sách tĩnh

Khi học hoặc kiểm tra LoadBalancer trên một máy phát triển, có thể chạy hai tiến trình của cùng dịch vụ trên hai cổng khác nhau. Ví dụ:

| Bản sao | Địa chỉ local |
|---|---|
| `catalog-service` A | `http://localhost:8081` |
| `catalog-service` B | `http://localhost:8082` |

Nếu chỉ cần kiểm tra cơ chế chọn instance, `SimpleDiscoveryClient` cho phép khai báo danh sách tĩnh mà không cần dựng thêm Eureka hay Consul:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
```

Ứng dụng gọi tạo HTTP client được tích hợp LoadBalancer. Ví dụ với `RestClient`:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Sau đó, request dùng service ID:

```java
Product findProduct(RestClient.Builder builder, String id) {
    return builder.build()
            .get()
            .uri("http://catalog-service/api/products/{id}", id)
            .retrieve()
            .body(Product.class);
}
```

Với danh sách hai địa chỉ tĩnh, LoadBalancer có thể chọn một trong hai địa chỉ theo chiến lược đang cấu hình. Khi muốn thử phân phối, hãy cho mỗi tiến trình trả về một định danh riêng như `instance=A` hoặc `instance=B`, rồi gửi nhiều request và quan sát response.

### Chạy nhiều tiến trình trên cùng máy

Mỗi tiến trình cần cổng lắng nghe riêng. Ví dụ, chạy cùng một ứng dụng với `server.port=8081` và `server.port=8082`. Nếu ứng dụng cần tự đăng ký vào registry, mỗi tiến trình còn cần một instance ID riêng để registry phân biệt chúng.

Ví dụ cấu hình một tiến trình:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081
```

Tiến trình thứ hai có thể dùng cùng cấu hình ứng dụng nhưng ghi đè cổng thành `8082`. Với registry, instance ID nên kết hợp service name với một giá trị phân biệt như cổng hoặc biến môi trường. Nếu hai tiến trình đăng ký cùng một instance ID, registry có thể coi lần đăng ký sau là cập nhật của instance trước, khiến danh sách chỉ còn một bản ghi.

Danh sách tĩnh phù hợp cho bài lab có topology ít thay đổi. Khi thêm hoặc xóa tiến trình, người vận hành phải cập nhật cấu hình và khởi động lại hoặc reload ứng dụng theo cơ chế đang dùng. Với môi trường có nhiều replica thường xuyên thay đổi, registry động sẽ phù hợp hơn.

## 3. Máy ảo: công bố địa chỉ có thể định tuyến

Trong môi trường máy ảo, mỗi bản sao thường có địa chỉ IP riêng trên mạng nội bộ hoặc hostname được DNS quản lý. Ứng dụng gọi và các instance cần kết nối được với nhau qua network mà hạ tầng cho phép.

Một registry như Eureka hoặc Consul có thể lưu các instance đã đăng ký. Khi ứng dụng `catalog-service` khởi động, nó đăng ký service ID cùng địa chỉ host, port và metadata. Ứng dụng gọi truy vấn registry thông qua discovery client; LoadBalancer nhận danh sách và chọn một instance.

Ví dụ cấu hình Eureka cho một instance:

```yaml
spring:
  application:
    name: catalog-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://registry.internal:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: ${spring.application.name}:${server.port}:${HOSTNAME:local}
```

Đây là ví dụ cấu hình minh họa; địa chỉ registry, cách xác định IP và instance ID cần điều chỉnh theo mạng và cách cấp phát máy ảo. Khi dùng Eureka, ứng dụng cũng cần dependency Eureka Client tương ứng và cấu hình kết nối đến registry. Với Consul, ứng dụng dùng Consul Discovery starter và cấu hình agent/server Consul theo môi trường.

### Chọn địa chỉ đăng ký đúng

Một instance có thể có nhiều network interface: IP quản trị, IP private, IP public hoặc interface chỉ dùng cho mạng nội bộ. Địa chỉ đăng ký phải thuộc mạng mà các consumer truy cập được. Ví dụ, nếu mọi dịch vụ giao tiếp qua private subnet, đăng ký private IP thường hợp lý hơn public IP.

Không đăng ký `127.0.0.1` hoặc `localhost` cho dịch vụ cần được gọi từ máy ảo khác. Địa chỉ loopback chỉ có ý nghĩa bên trong chính máy đang chạy tiến trình. Cũng cần kiểm tra:

- Security group, firewall và network ACL có cho phép consumer kết nối đến port ứng dụng không.
- DNS có phân giải hostname thành địa chỉ mà consumer truy cập được không.
- Registry có thể được truy cập từ tất cả ứng dụng cần đăng ký hoặc tra cứu không.
- Instance ID có duy nhất khi chạy nhiều tiến trình cùng service ID không.
- TLS, chứng thư và hostname có khớp nếu request dùng HTTPS không.

### Registry, heartbeat và instance hết hạn

Registry động thường theo dõi vòng đời đăng ký bằng heartbeat, lease hoặc cơ chế health tương đương. Khi tiến trình dừng đột ngột, registry có thể chưa xóa bản ghi ngay lập tức; trong một khoảng thời gian, consumer vẫn có thể nhận địa chỉ của instance không còn hoạt động.

Do đó, cần phân biệt ba trạng thái:

1. **Đã đăng ký:** registry đang lưu thông tin instance.
2. **Có thể kết nối:** consumer mở được kết nối đến host và port đã công bố.
3. **Sẵn sàng phục vụ:** ứng dụng đích có thể xử lý request theo yêu cầu nghiệp vụ.

Ba trạng thái này liên quan nhưng không đồng nhất. Heartbeat cho biết tiến trình còn duy trì đăng ký; health check hoặc readiness signal giúp đánh giá khả năng phục vụ; kiểm tra kết nối mạng xác nhận consumer có thể đến được địa chỉ đó.

## 4. Container: phân biệt địa chỉ nội bộ và địa chỉ host

Container có network namespace riêng. Vì vậy, địa chỉ `localhost` bên trong container không trỏ đến host hay container khác. Khi các dịch vụ chạy trong cùng Docker network, chúng thường giao tiếp qua tên dịch vụ hoặc địa chỉ nội bộ mà network cung cấp.

Ví dụ, một môi trường Docker Compose có các thành phần:

```yaml
services:
  registry:
    image: example/registry
    ports:
      - "8761:8761"

  catalog-service:
    image: example/catalog-service
    environment:
      SERVER_PORT: 8081
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://registry:8761/eureka/
    expose:
      - "8081"

  order-service:
    image: example/order-service
    environment:
      EUREKA_CLIENT_SERVICEURL_DEFAULTZONE: http://registry:8761/eureka/
```

Trong ví dụ, `registry` là tên service trên Docker network và có thể được các container cùng network phân giải qua DNS nội bộ. Biến môi trường minh họa cách truyền địa chỉ registry vào ứng dụng; tên property cần được đối chiếu với cấu hình của Eureka Client và cách ánh xạ biến môi trường của Spring Boot.

### Container đăng ký địa chỉ nào?

Nếu `order-service` gọi `catalog-service` qua registry, địa chỉ mà `catalog-service` đăng ký phải truy cập được từ network của `order-service`. Trong cùng Docker network, đó thường là địa chỉ container và port nội bộ của ứng dụng, không phải port đã publish ra host.

Ví dụ, cấu hình `ports: "18081:8081"` ánh xạ cổng 8081 trong container ra cổng 18081 trên host. Container khác trong cùng network thường gọi đến port 8081 của container đích. Nếu registry quảng bá `localhost:18081`, consumer container sẽ cố gọi chính nó; nếu quảng bá một host port chỉ có thể truy cập từ máy host, consumer container có thể không kết nối được.

`expose` trong Compose chỉ mô tả cổng nội bộ của container và không thay thế cấu hình firewall hay cơ chế publish port. Các container cần cùng một network hoặc có tuyến mạng phù hợp để giao tiếp.

### DNS của Docker và Spring Cloud LoadBalancer

Docker Compose cung cấp DNS cho tên service trên network. Tên như `catalog-service` có thể phân giải đến địa chỉ của dịch vụ trong network. Tuy nhiên, việc DNS phân giải một tên không đồng nghĩa Spring Cloud LoadBalancer đã nhận được một danh sách `ServiceInstance` riêng cho từng replica.

Nếu muốn LoadBalancer ở client chọn từng container, cần một discovery provider công bố các replica riêng biệt hoặc một supplier phù hợp. Nếu chỉ gọi qua tên DNS của một service có nhiều replica, việc phân phối có thể do cơ chế DNS hoặc proxy/network của nền tảng đảm nhiệm; không nên mặc định đó là lựa chọn instance của Spring Cloud LoadBalancer.

## 5. Kubernetes: discovery theo Pod hoặc dùng Service của nền tảng

Trong Kubernetes, mỗi Pod có IP riêng và vòng đời tương đối ngắn. Kubernetes Service cung cấp một địa chỉ ổn định cho một nhóm Pod; kube-proxy hoặc dataplane tương ứng chuyển tiếp lưu lượng đến các endpoint phù hợp.

Có hai cách tiếp cận thường gặp:

| Cách tiếp cận | Cơ chế chọn đích | Phù hợp khi |
|---|---|---|
| Gọi Kubernetes Service DNS | Ứng dụng gọi DNS/ClusterIP ổn định; Kubernetes network dataplane phân phối đến Pod | Muốn dùng cơ chế cân bằng tải của nền tảng và giữ ứng dụng đơn giản |
| Dùng Spring Cloud Kubernetes Discovery với LoadBalancer | Discovery cung cấp danh sách endpoint/Pod; Spring Cloud LoadBalancer chọn một instance phía client | Muốn ứng dụng áp dụng chiến lược client-side hoặc xử lý metadata instance |

Nếu dùng Spring Cloud Kubernetes Discovery, cần thêm dependency discovery tương thích với phiên bản Spring Cloud Kubernetes, cấu hình quyền đọc tài nguyên Kubernetes và xác định loại endpoint mà ứng dụng sẽ khám phá. Service account và RBAC phải cho phép đúng các thao tác cần thiết. Không nên cấp quyền rộng hơn yêu cầu chỉ để discovery hoạt động.

Một Kubernetes Service thông thường có thể che giấu danh sách Pod phía sau ClusterIP. Khi ứng dụng gọi Service DNS, request được gửi đến virtual IP của Service và nền tảng chọn endpoint. Nếu mục tiêu là để Spring Cloud LoadBalancer chọn Pod riêng lẻ, cần cấu hình discovery theo hướng trả về các instance/endpoint phù hợp, thay vì chỉ trả về địa chỉ ClusterIP duy nhất.

Headless Service là một lựa chọn khi cần DNS trả về địa chỉ Pod thay vì một ClusterIP. Tuy nhiên, DNS headless tự nó không bảo đảm mọi HTTP client sẽ nhận danh sách instance và áp dụng thuật toán LoadBalancer. Hãy kiểm tra chính xác discovery provider, dữ liệu mà nó trả về và cách HTTP client được tích hợp.

## 6. So sánh cách khám phá dịch vụ theo môi trường

| Tiêu chí | Local | Máy ảo | Container |
|---|---|---|---|
| Địa chỉ instance | `localhost` với các port khác nhau | Private IP hoặc hostname có thể định tuyến | Container IP/hostname trên network chung hoặc endpoint do nền tảng công bố |
| Nguồn discovery thường dùng | `SimpleDiscoveryClient`, hoặc registry chạy local | Eureka, Consul, DNS hoặc nền tảng hạ tầng | Docker DNS, registry như Eureka/Consul, Kubernetes discovery hoặc Kubernetes Service |
| Cập nhật danh sách | Thường cập nhật cấu hình thủ công | Registry nhận đăng ký và heartbeat | Theo vòng đời container/Pod hoặc registry |
| Vấn đề dễ gặp | Trùng port, instance ID trùng | Đăng ký loopback, firewall, IP sai interface | Nhầm localhost, nhầm host port với container port, IP container thay đổi |
| Cách kiểm tra | Gọi trực tiếp từng port và gọi qua service ID | Kiểm tra registry, route, DNS và firewall từ consumer | Kiểm tra network, DNS trong container và địa chỉ instance registry quảng bá |

Không có một nguồn discovery tốt nhất cho mọi môi trường. Local static list giúp bài lab dễ tái lập; registry động phù hợp khi bản sao được tạo và hủy độc lập; discovery của nền tảng container có thể giảm nhu cầu tự quản lý registry nếu nó đã đáp ứng yêu cầu định tuyến.

## 7. Health check và tính sẵn sàng trong từng môi trường

Khi discovery trả về một instance, LoadBalancer có thể xem instance đó là ứng viên. Nhưng một địa chỉ được đăng ký không đồng nghĩa ứng dụng đã sẵn sàng xử lý nghiệp vụ. Cần thiết kế trạng thái sẵn sàng phù hợp với môi trường:

- **Local:** kiểm tra tiến trình đã mở port và endpoint health phản hồi trước khi đưa instance vào danh sách thử nghiệm.
- **Máy ảo:** kết hợp trạng thái registry với health endpoint, giám sát tiến trình và khả năng kết nối qua private network.
- **Container:** dùng readiness/liveness probe của nền tảng và cấu hình discovery để không gửi request đến Pod chưa sẵn sàng hoặc đã bị loại khỏi endpoint.

Health check của Spring Cloud LoadBalancer, health indicator của Spring Boot Actuator và readiness probe của Kubernetes có vai trò khác nhau. Chúng có thể phối hợp nhưng không tự động thay thế lẫn nhau. Hãy xác định ai là nguồn sự thật về trạng thái instance, tần suất kiểm tra và khoảng thời gian loại instance lỗi để tránh gửi request vào bản sao không hoạt động hoặc loại nhầm bản sao chỉ đang khởi động.

## 8. Thực hành kiểm tra discovery từ consumer

Có thể dùng cùng một kịch bản để kiểm tra trên cả ba môi trường:

1. Khởi chạy ít nhất hai bản sao của `catalog-service`, mỗi bản sao có địa chỉ và instance ID riêng.
2. Xác nhận từng bản sao có thể được gọi trực tiếp từ môi trường mạng của consumer.
3. Kiểm tra registry hoặc nguồn discovery cho thấy đúng service ID và đúng địa chỉ instance.
4. Gửi request qua HTTP client có tích hợp `@LoadBalanced` bằng URL `http://catalog-service/...`.
5. Cho mỗi instance trả về tên hoặc ID riêng, sau đó gửi nhiều request và quan sát kết quả phân phối.
6. Dừng một bản sao hoặc làm readiness/health thất bại, rồi kiểm tra thời gian cần thiết để instance bị loại khỏi danh sách ứng viên.
7. Khởi động lại bản sao và xác nhận instance được đăng ký lại với địa chỉ hợp lệ.

Khi chạy trong container, thực hiện bước kiểm tra kết nối từ chính container consumer hoặc một container cùng network. Kiểm tra từ máy host thành công chưa chứng minh container consumer có thể truy cập địa chỉ đó.

Các lệnh kiểm tra mạng tùy image có sẵn công cụ nào. Nếu container không có `curl`, `wget`, `nslookup` hoặc `getent`, có thể dùng một container chẩn đoán cùng network hoặc công cụ của nền tảng để kiểm tra DNS và kết nối TCP. Không nên thêm công cụ debug vào image production chỉ để xử lý sự cố tạm thời.

## 9. Chẩn đoán các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Local gọi được nhưng container gọi thất bại | Registry quảng bá `localhost` hoặc host port không truy cập từ container | Xem host/port trong `ServiceInstance`, kiểm tra từ container consumer |
| Registry có service nhưng không kết nối được | Firewall, route, sai interface hoặc port | Thử kết nối trực tiếp từ consumer đến địa chỉ đã đăng ký |
| Nhiều replica nhưng registry chỉ có một bản ghi | Instance ID bị trùng hoặc các tiến trình ghi đè đăng ký | Kiểm tra instance ID, hostname và port của từng replica |
| Request đi đến Pod/container đã dừng | Registry chưa xóa instance, heartbeat/health chậm hoặc cache còn dữ liệu cũ | Đối chiếu registry, supplier cache và health check |
| Kubernetes Service hoạt động nhưng client-side selection không thấy Pod | Discovery đang trả về ClusterIP thay vì endpoint riêng | Kiểm tra cấu hình discovery và loại endpoint được trả về |
| Tên service không phân giải được | Service ID không khớp, provider không hoạt động hoặc client chưa tích hợp LoadBalancer | Kiểm tra service ID, dependency, discovery client và bean `@LoadBalanced` |

Khi điều tra, hãy ghi lại service ID, instance ID, host, port, metadata, nguồn discovery và thời điểm quan sát. So sánh địa chỉ registry công bố với địa chỉ mà consumer thực sự có thể kết nối. Cách này giúp phân biệt lỗi discovery, lỗi cấu hình mạng và lỗi ở HTTP client.

## 10. Chọn cách discovery phù hợp

Với bài lab trên một máy, bắt đầu bằng `SimpleDiscoveryClient` và hai cổng local để hiểu rõ cách service ID được ánh xạ thành các instance. Khi chuyển sang nhiều máy ảo, dùng registry hoặc DNS có thể truy cập từ các consumer và công bố private address phù hợp. Khi đóng gói bằng Docker, kiểm tra network namespace, service DNS và địa chỉ nội bộ được đăng ký. Trên Kubernetes, quyết định rõ muốn dùng Service routing của nền tảng hay muốn Spring Cloud LoadBalancer chọn endpoint phía client.

Ở mọi môi trường, quy trình vẫn bắt đầu bằng service ID và kết thúc bằng một địa chỉ instance có thể truy cập. Nếu request thất bại, hãy xác minh lần lượt nguồn discovery, danh sách instance mà supplier trả về, trạng thái sẵn sàng, địa chỉ mạng từ góc nhìn consumer và kết quả chọn của LoadBalancer. Khi các lớp này được cấu hình nhất quán, ứng dụng có thể giữ nguyên cách gọi dịch vụ dù số lượng và vị trí các bản sao thay đổi theo môi trường triển khai.
