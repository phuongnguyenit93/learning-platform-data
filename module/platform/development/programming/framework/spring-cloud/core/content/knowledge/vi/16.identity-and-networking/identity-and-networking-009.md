# Địa chỉ bind, địa chỉ quảng bá và khác biệt khi chạy container

Một ứng dụng Spring Boot có thể lắng nghe trên một địa chỉ mạng, nhưng lại công bố một hostname hoặc IP khác cho các service gọi tới. Sự khác biệt này đặc biệt quan trọng khi ứng dụng chạy trong Docker hoặc Kubernetes: địa chỉ mà process nhìn thấy bên trong container không nhất thiết là địa chỉ mà client bên ngoài có thể truy cập.

Trong Spring Cloud, cần tách biệt ba khái niệm:

1. **Địa chỉ bind (bind address):** địa chỉ mà web server mở socket để nhận kết nối.
2. **Địa chỉ quảng bá (advertised address):** hostname/IP và port được công bố cho service registry, discovery client hoặc hệ thống gọi service.
3. **Địa chỉ truy cập từ phía client:** địa chỉ và port mà một consumer thực sự có thể phân giải, định tuyến và kết nối tới từ network namespace của nó.

Ba giá trị có thể giống nhau trong một máy ảo đơn giản, nhưng thường khác nhau khi có NAT, port mapping, service mesh, ingress, nhiều NIC hoặc nhiều network zone. Chọn đúng địa chỉ giúp tránh trường hợp server vẫn chạy nhưng service registry trả về endpoint không thể truy cập.

## 1. Địa chỉ bind là gì?

Địa chỉ bind cho biết server socket sẽ lắng nghe trên interface/địa chỉ nào của máy. Với Spring Boot, thuộc tính thường dùng là:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Ở đây, server lắng nghe trên port 8080 tại các địa chỉ IPv4 phù hợp của network namespace hiện tại. 0.0.0.0 là địa chỉ wildcard IPv4, không phải địa chỉ IP cụ thể để một service khác gọi tới.

Nếu bind vào một địa chỉ cụ thể:

~~~yaml
server:
  address: 10.20.4.15
  port: 8080
~~~

server chỉ có thể bind nếu địa chỉ 10.20.4.15 tồn tại và khả dụng trong network namespace của process. Nếu container được cấp IP động khác, ứng dụng có thể không khởi động được.

### 1.1. Wildcard address và địa chỉ cụ thể

| Địa chỉ | Ý nghĩa khi bind | Có nên quảng bá cho consumer? |
| --- | --- | --- |
| 0.0.0.0 | Lắng nghe trên các IPv4 interface phù hợp | Không |
| :: | Wildcard IPv6; hành vi dual-stack tùy OS/socket configuration | Không |
| 127.0.0.1 | Chỉ nhận kết nối loopback IPv4 trong cùng network namespace | Không cho consumer ở namespace khác |
| ::1 | Loopback IPv6 | Không cho consumer ở namespace khác |
| 10.20.4.15 | Lắng nghe trên địa chỉ IPv4 cụ thể nếu địa chỉ tồn tại | Có thể, nếu consumer có route tới địa chỉ đó |

Wildcard giúp server nhận kết nối đến các interface mà process được phép sử dụng. Nó không đại diện cho một địa chỉ đích có thể định tuyến. Khi đăng ký service, cần công bố một hostname/IP thực tế, hoặc một DNS/service name ổn định.

### 1.2. Bind vào loopback có thể làm container không nhận kết nối bên ngoài

Nếu ứng dụng chạy trong container và bind:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

chỉ process trong cùng network namespace mới có thể truy cập loopback đó. Một container khác hoặc host thường không thể kết nối qua địa chỉ container vì server không lắng nghe trên interface container.

Với ứng dụng web trong container, cấu hình phổ biến là bind wildcard trong container:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Điều này chỉ mở listener trong network namespace của container. Firewall, port publishing, Kubernetes Service, NetworkPolicy và security group vẫn quyết định ai có thể truy cập từ bên ngoài.

## 2. Địa chỉ quảng bá là gì?

Địa chỉ quảng bá là thông tin mà ứng dụng công bố để consumer biết cách gọi tới instance. Trong kiến trúc discovery, registry có thể lưu hostname/IP, port, scheme, metadata và trạng thái của instance.

Ví dụ một instance đăng ký:

~~~text
serviceId: catalog-service
host: catalog-7f8a
port: 8080
status: UP
~~~

Consumer lấy ServiceInstance từ discovery client rồi gửi request tới địa chỉ được trả về. Nếu host/port không truy cập được từ consumer, discovery vẫn có thể trả kết quả hợp lệ về mặt dữ liệu nhưng request sẽ thất bại ở tầng network.

Một địa chỉ quảng bá tốt phải đáp ứng:
- Consumer có thể phân giải hostname nếu dùng DNS.
- Consumer có route tới IP nếu dùng địa chỉ số.
- Port được công bố là port consumer thực sự có thể kết nối.
- Firewall, NetworkPolicy và security group cho phép luồng kết nối.
- Scheme, TLS và context path phù hợp với giao thức service.
- Địa chỉ không phải loopback hoặc wildcard ngoài trường hợp có proxy/gateway được thiết kế rõ.

### 2.1. Tên ứng dụng không phải địa chỉ mạng

spring.application.name xác định tên logic của ứng dụng trong nhiều integration, ví dụ tên service dùng trong discovery hoặc tên ứng dụng mà Config Client yêu cầu.

~~~yaml
spring:
  application:
    name: catalog-service
~~~

Giá trị catalog-service không tự động cho biết IP hoặc port. Địa chỉ instance được xác định bởi cấu hình server, discovery client, DNS hoặc hạ tầng triển khai.

Phân biệt:

| Thuộc tính/khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| Application name | catalog-service | Tên logic của ứng dụng |
| Bind address | 0.0.0.0 | Interface/address mà server lắng nghe |
| Server port | 8080 | Port nội bộ của listener |
| Advertised hostname | catalog-7f8a | Tên mà consumer dùng để truy cập instance |
| Advertised IP | 10.20.4.15 | Địa chỉ số được công bố |
| Published/Service port | 18080 hoặc 80 | Port được ánh xạ hoặc cung cấp qua hạ tầng |

## 3. Vì sao địa chỉ bind và địa chỉ quảng bá thường khác nhau?

Một server có thể bind wildcard để nhận kết nối trên mọi interface, trong khi chỉ quảng bá một interface dành cho mạng ứng dụng.

Ví dụ máy có:
- eth0: 10.20.4.15 cho mạng ứng dụng.
- tun0: 10.99.0.5 cho VPN quản trị.
- docker0: 172.17.0.1 cho bridge của Docker.

Server có thể bind 0.0.0.0:8080, nhưng registry nên quảng bá 10.20.4.15:8080 nếu consumer nằm trong mạng ứng dụng. Quảng bá 127.0.0.1, 0.0.0.0 hoặc 172.17.0.1 có thể khiến consumer không thể kết nối.

Sơ đồ:

~~~mermaid
flowchart TD
    APP["Spring Boot process"]
    BIND["Bind: 0.0.0.0:8080"]
    ETH["eth0: 10.20.4.15"]
    VPN["tun0: 10.99.0.5"]
    DOCKER["docker0: 172.17.0.1"]
    REG["Registry: 10.20.4.15:8080"]
    CLIENT["Consumer trong mạng ứng dụng"]

    APP --> BIND
    BIND --> ETH
    BIND --> VPN
    BIND --> DOCKER
    ETH --> REG
    REG --> CLIENT
~~~

Sơ đồ chỉ mô tả nguyên tắc. Server có thể lắng nghe trên nhiều interface, nhưng ứng dụng/registry cần chọn một endpoint mà nhóm consumer mục tiêu có thể truy cập.

## 4. Cấu hình Spring Boot cho bind address

Spring Boot dùng server.address và server.port để cấu hình địa chỉ và port của web server nhúng. Ví dụ:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Nếu không chỉ định server.address, embedded server thường bind trên địa chỉ wildcard theo mặc định của server/OS. Hãy kiểm tra log khởi động và socket thực tế thay vì suy đoán từ file YAML.

Trong môi trường cần giới hạn interface, có thể bind một địa chỉ cụ thể:

~~~yaml
server:
  address: 10.20.4.15
  port: 8080
~~~

Cách này phù hợp khi địa chỉ ổn định và đã được gán cho network namespace. Trong container, IP thường được cấp động; hard-code Pod IP hoặc container IP vào server.address dễ gây lỗi khi container được tạo lại.

### 4.1. Bind wildcard trong container, kiểm soát truy cập ở hạ tầng

Một cấu hình thường dùng:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Sau đó giới hạn truy cập bằng:
- Docker network và port publishing.
- Kubernetes Service và NetworkPolicy.
- Firewall/security group.
- Ingress hoặc API gateway.
- Authentication và authorization ở ứng dụng.

Bind wildcard không có nghĩa phải mở port ra Internet. Nó chỉ làm listener nhận kết nối trên interface trong namespace của process; đường đi bên ngoài còn phụ thuộc cấu hình mạng.

## 5. Spring Cloud InetUtils và thông tin host

Spring Cloud Commons cung cấp InetUtils để tìm host info từ các network interface. Một số integration có thể dùng hostname/IP mà InetUtils phát hiện làm giá trị mặc định cho thông tin instance.

Các thuộc tính thường gặp:

| Thuộc tính | Tác dụng |
| --- | --- |
| spring.cloud.inetutils.ignored-interfaces | Bỏ qua interface có tên khớp regex |
| spring.cloud.inetutils.preferred-networks | Ưu tiên địa chỉ IP khớp regex |
| spring.cloud.inetutils.use-only-site-local-interfaces | Giới hạn lựa chọn theo phân loại site-local của Java |
| spring.cloud.inetutils.default-ip-address | Giá trị IP dự phòng khi không tìm được địa chỉ phù hợp |
| spring.cloud.inetutils.default-hostname | Hostname dự phòng |

Ví dụ bỏ qua Docker bridge và ưu tiên dải mạng ứng dụng:

~~~yaml
spring:
  cloud:
    inetutils:
      ignored-interfaces:
        - docker0
        - veth.*
      preferred-networks:
        - '^10\.20\..*'
~~~

Các giá trị preferred-networks là regex, không phải CIDR notation. Cần kiểm tra tên interface và IP mà JVM trong môi trường thực tế nhìn thấy.

### 5.1. InetUtils không cấu hình server bind

Đây là ranh giới quan trọng:

- server.address điều khiển địa chỉ listener của embedded server.
- spring.cloud.inetutils.* điều khiển cách Spring Cloud tìm host info.
- Discovery client có thể có thuộc tính riêng để override hostname/IP được đăng ký.
- Routing table và policy routing của OS quyết định đường đi outbound.

Đặt preferred-networks không tự đổi server.address. Bỏ qua interface docker0 trong InetUtils cũng không làm interface đó biến mất khỏi OS hoặc thay đổi routing table.

### 5.2. Host info được tìm thấy chưa chắc là endpoint cuối cùng trong registry

Một discovery client có thể nhận host info mặc định rồi áp dụng cấu hình riêng. Vì vậy, khi debug phải so sánh:
1. Interface và IP mà OS cung cấp.
2. Host info InetUtils tìm được.
3. Giá trị discovery client dùng sau khi áp dụng override.
4. Instance record thực tế được gửi tới registry.
5. Endpoint mà consumer nhận về từ DiscoveryClient.

Không chỉ nhìn log InetUtils để kết luận registry đang lưu đúng địa chỉ.

## 6. Địa chỉ quảng bá trong Eureka

Với Eureka client, các thuộc tính thường dùng để điều khiển hostname/IP của instance gồm:
- eureka.instance.hostname
- eureka.instance.ip-address
- eureka.instance.prefer-ip-address

Ví dụ công bố hostname:

~~~yaml
eureka:
  instance:
    hostname: catalog-service
    prefer-ip-address: false
~~~

Hostname catalog-service phải phân giải được từ các consumer cần gọi instance. Trong Docker Compose, đó có thể là tên service trên cùng Docker network. Trong Kubernetes, đó có thể là DNS Service nếu đăng ký một endpoint ổn định thay vì từng Pod.

Ví dụ công bố IP rõ ràng:

~~~yaml
eureka:
  instance:
    prefer-ip-address: true
    ip-address: 10.20.4.15
~~~

Địa chỉ 10.20.4.15 phải được cấp bởi môi trường triển khai và phải reachable từ consumer. Không dùng địa chỉ 0.0.0.0, loopback hoặc IP của một bridge chỉ tồn tại trên host.

Khi cấu hình tường minh, hãy xác minh giá trị cuối trong Eureka InstanceInfo và các ServiceInstance mà consumer nhận được. Các chi tiết mặc định có thể thay đổi theo phiên bản Spring Cloud Netflix/Eureka và cấu hình của ứng dụng.

### 6.1. Port được quảng bá

Địa chỉ host đúng nhưng port sai vẫn làm discovery thất bại. Ví dụ server lắng nghe port 8080 trong container, Docker publish 18080:8080 ra host. Consumer trong cùng Docker network thường gọi container service ở port 8080; client bên ngoài Docker network có thể cần host port 18080 hoặc một load balancer/gateway.

Một registry chỉ lưu một host/port không tự hiểu mọi network zone. Nếu có consumer bên trong và bên ngoài container network, cần chọn một endpoint dùng chung có thể route, hoặc thiết kế gateway/DNS/registry theo zone.

Không giả định discovery client tự suy ra port publish từ Docker. Port mapping là cấu hình của Docker daemon; ứng dụng trong container thường chỉ biết port nội bộ mà server đang listen.

## 7. Chạy trong Docker bridge network

Docker bridge tạo network namespace riêng cho mỗi container. Ứng dụng trong container thường nhìn thấy interface eth0 với IP nội bộ của Docker network. Host và container khác có thể truy cập IP này tùy topology và firewall.

Ví dụ Compose:

~~~yaml
services:
  catalog-service:
    image: example/catalog-service:1.0
    environment:
      SERVER_PORT: "8080"
    ports:
      - "18080:8080"
    networks:
      - app-net

  order-service:
    image: example/order-service:1.0
    networks:
      - app-net

networks:
  app-net:
    driver: bridge
~~~

Trong cấu hình này:
- Catalog server bind port 8080 bên trong container.
- Docker publish host port 18080 tới container port 8080.
- order-service cùng network có thể gọi http://catalog-service:8080 qua DNS/service name của Compose.
- Client từ host có thể gọi http://localhost:18080.
- Client từ một mạng ngoài host cần địa chỉ host/LB có thể truy cập và port được publish tương ứng.

Nếu Eureka chạy cùng Docker network và các consumer cũng ở network đó, có thể quảng bá hostname catalog-service cùng port nội bộ 8080. Nếu consumer ở ngoài Docker network, hostname đó có thể không phân giải được; cần một endpoint ngoài có thể truy cập và port tương ứng.

### 7.1. Không quảng bá địa chỉ host sai phạm vi

Một số lỗi thường gặp:
- Quảng bá 127.0.0.1: consumer khác sẽ gọi loopback của chính nó.
- Quảng bá 0.0.0.0: đây là wildcard bind, không phải destination address.
- Quảng bá 172.17.0.1: địa chỉ bridge của host, không nhất thiết là IP của service container.
- Quảng bá container IP cho consumer ngoài bridge: có thể không có route.
- Quảng bá host port 18080 cho consumer cùng bridge: consumer có thể cần container port 8080.

Chọn endpoint theo vị trí consumer, không theo địa chỉ đầu tiên mà container nhìn thấy.

### 7.2. Docker host network

Khi dùng host networking trên Linux, container chia sẻ network namespace của host. Server có thể bind trực tiếp vào địa chỉ/port của host; port publishing kiểu bridge không còn có cùng ý nghĩa như cấu hình bridge network.

Cách này thay đổi isolation và có thể gây xung đột port giữa process. Hành vi host networking trên Docker Desktop cũng phụ thuộc phiên bản/nền tảng. Không dùng host network chỉ để né bài toán chọn advertised address; trước tiên hãy xác định yêu cầu kết nối và ranh giới bảo mật.

## 8. Chạy trong Kubernetes

Trong Kubernetes, một Pod có network namespace riêng và thường nhận Pod IP. Ứng dụng trong container nên lắng nghe trên interface có thể nhận traffic từ Pod network, thường là:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Kubernetes Service cung cấp một địa chỉ ổn định và DNS name cho nhóm Pod được chọn. Ví dụ:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
spec:
  selector:
    app: catalog-service
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Consumer trong cluster gọi DNS Service:

~~~text
http://catalog-service.default.svc.cluster.local:80
~~~

Trong cùng namespace, thường có thể dùng tên ngắn catalog-service. Service chuyển tiếp tới các Pod endpoint phù hợp; consumer không cần biết Pod IP cụ thể.

### 8.1. Pod IP và Service DNS là hai lựa chọn khác nhau

| Địa chỉ | Đặc điểm | Trường hợp sử dụng |
| --- | --- | --- |
| Pod IP | Gắn với một Pod, có thể đổi khi Pod được tạo lại | Discovery tới từng instance trong cluster nếu consumer route được |
| ClusterIP | Địa chỉ ổn định của Kubernetes Service | Gọi nhóm Pod qua service abstraction |
| Service DNS | Tên ổn định phân giải tới Service | Cách gọi phổ biến giữa các workload trong cluster |
| Node IP | Địa chỉ của node chạy Pod | Không phải endpoint mặc định cho service nội bộ |
| Ingress/LoadBalancer address | Endpoint công bố cho client ngoài cluster | Truy cập từ mạng ngoài theo kiến trúc ingress/LB |

Nếu dùng Kubernetes Service discovery, thường không cần đăng ký từng Pod trong Eureka để các service nội bộ gọi nhau; DNS Service và dataplane của cluster đã cung cấp discovery/load balancing. Nếu ứng dụng vẫn dùng Eureka, cần quyết định rõ registry đại diện cho Pod instance hay endpoint ổn định phía Service.

### 8.2. Eureka trong Kubernetes

Nếu Eureka đăng ký từng Pod, Pod IP và container port có thể phù hợp khi mọi consumer đều nằm trong cluster và có route tới Pod network. Nhưng Pod IP thay đổi khi Pod được thay thế, nên client cần refresh registry và xử lý instance lifecycle đúng.

Nếu công bố ClusterIP/Service DNS cho từng replica trong Eureka, mọi record có thể trỏ về cùng một Service thay vì từng instance. Điều đó có thể làm mất ý nghĩa client-side load balancing hoặc health riêng theo instance. Chọn một mô hình nhất quán:
- Kubernetes Service DNS cho service-level discovery.
- Pod IP cho instance-level discovery trong cluster.
- Ingress/LoadBalancer/gateway cho consumer ngoài cluster.

Không đăng ký Node IP hoặc host IP chỉ vì nó ổn định nếu port/route tới Pod không được ánh xạ đúng.

### 8.3. Readiness và endpoint đăng ký

Một Pod có thể đã bind port nhưng chưa sẵn sàng xử lý request. Kubernetes readiness probe quyết định Pod có được đưa vào EndpointSlice/Service endpoints hay không. Nếu dùng Eureka song song, discovery registration/health cần được đồng bộ với trạng thái ứng dụng.

Bind thành công chỉ chứng minh socket đã mở; không chứng minh dependency đã sẵn sàng, registry đã cập nhật hoặc request có thể hoàn tất.

## 9. Khi có reverse proxy, ingress hoặc load balancer

Một ứng dụng có thể bind nội bộ 0.0.0.0:8080, trong khi client truy cập qua:
- Nginx/Envoy reverse proxy.
- Kubernetes Ingress.
- Cloud Load Balancer.
- API Gateway.
- Service mesh sidecar.

Trong trường hợp này, địa chỉ public/consumer-facing có thể là hostname và port của proxy/LB, không phải IP của Pod hoặc container.

Cần xác định discovery đang đại diện cho:
- Mỗi instance backend.
- Một service endpoint ổn định.
- Một gateway chung.
- Một endpoint nội bộ chỉ dùng trong cluster.

Không quảng bá địa chỉ proxy cho registry instance-level nếu client cần kết nối trực tiếp tới từng instance. Ngược lại, không quảng bá Pod IP cho client ngoài cluster nếu chỉ gateway mới có thể truy cập.

### 9.1. Host header và forwarded headers không thay thế advertised address

Reverse proxy có thể truyền Host, X-Forwarded-Host, X-Forwarded-Proto hoặc header chuẩn Forwarded để ứng dụng biết URL bên ngoài của request. Các header này giúp ứng dụng dựng redirect hoặc link phù hợp, nhưng không tự thay đổi địa chỉ mà discovery client đăng ký.

Nếu service cần công bố endpoint bên ngoài, hãy cấu hình discovery/metadata hoặc gateway theo cách tường minh. Đừng suy luận rằng server.forward-headers-strategy sẽ tự đổi Eureka hostname/IP.

## 10. Nhiều network zone và nhiều loại consumer

Một service có thể được gọi từ:
- Container cùng Docker network.
- Pod trong cùng Kubernetes cluster.
- Workload ở VPC khác.
- Hệ thống on-premises qua VPN.
- Client ngoài Internet qua gateway.

Một địa chỉ duy nhất không phải lúc nào cũng reachable từ mọi zone. Ví dụ Pod IP có thể dùng được trong cluster nhưng không có route từ on-premises. Host port có thể dùng được từ LAN nhưng không truy cập được từ Pod network.

Trong hệ thống nhiều zone, cân nhắc:
- DNS name có view/zone phù hợp.
- Internal/external load balancer.
- Gateway hoặc ingress.
- Registry tách theo network zone.
- Service mesh hoặc network routing được quản lý tập trung.
- Metadata endpoint/port riêng theo nhóm consumer nếu kiến trúc discovery hỗ trợ.

Đừng công bố nhiều địa chỉ trong một record nếu client không biết cách chọn đúng endpoint. Chính sách chọn địa chỉ phải nằm ở DNS, gateway, registry hoặc client routing được thiết kế rõ.

## 11. Kiểm tra socket bind và endpoint quảng bá

Khi chẩn đoán, kiểm tra hai phía riêng biệt.

### 11.1. Kiểm tra server đang listen ở đâu

Trên Linux/container:

~~~bash
ss -lntp
ip -br address
~~~

Trên Windows:

~~~powershell
Get-NetTCPConnection -State Listen
Get-NetIPAddress
~~~

Kiểm tra:
- Process có listen port mong muốn không?
- Listener gắn với 0.0.0.0, ::, loopback hay IP cụ thể?
- Địa chỉ bind có tồn tại trong namespace không?
- Port container có đúng với targetPort hoặc Docker mapping không?

Lệnh chạy trên host không nhất thiết cho thấy listener trong container. Hãy kiểm tra từ đúng container/Pod hoặc dùng công cụ debug phù hợp.

### 11.2. Kiểm tra địa chỉ quảng bá

Kiểm tra discovery registry hoặc DiscoveryClient để biết host/port consumer thực sự nhận được. Ví dụ đọc các instance:

~~~java
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class CatalogDiscoveryDiagnostics {

    private final DiscoveryClient discoveryClient;

    public CatalogDiscoveryDiagnostics(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<String> instances() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(instance -> instance.getHost() + ":" + instance.getPort())
                .collect(Collectors.toList());
    }
}
~~~

Đây là ví dụ chẩn đoán nội bộ; không expose danh sách địa chỉ nội bộ qua endpoint công khai. Đối chiếu host/port ở đây với registry server và cấu hình discovery client.

### 11.3. Kiểm tra từ consumer

Phép thử quan trọng nhất là từ đúng network namespace của consumer:

~~~bash
getent hosts catalog-service
nc -vz catalog-service 8080
curl -v http://catalog-service:8080/actuator/health
~~~

Trong Kubernetes, có thể dùng kubectl exec vào một Pod consumer hoặc một debug Pod cùng namespace/network policy. Trong Docker, dùng docker exec hoặc một container cùng network.

Một lệnh curl localhost chạy trong container provider chỉ chứng minh listener hoạt động qua loopback của chính container. Nó không chứng minh consumer khác có thể kết nối.

## 12. Kiểm thử theo môi trường

| Kiểm thử | Môi trường | Điều cần xác nhận |
| --- | --- | --- |
| Bind test | JVM/process local | Listener mở đúng địa chỉ và port |
| Host-info test | OS/VM/container | InetUtils tìm host info theo policy |
| Registry test | Discovery server/client | Instance record chứa hostname/IP/port mong muốn |
| Docker network test | Hai container cùng network | Consumer phân giải service name và kết nối container port |
| Host-to-container test | Docker host | Published port chuyển tới đúng container port |
| Kubernetes Service test | Pod consumer | Service DNS và port dẫn tới Pod endpoint |
| External ingress test | Client ngoài cluster | Hostname, TLS, ingress/LB và backend route hoạt động |
| Multi-zone test | Các mạng khác nhau | Tất cả consumer mục tiêu có reachability theo thiết kế |

### 12.1. Không hard-code IP động trong test

Container IP và Pod IP có thể thay đổi qua mỗi lần chạy. Test chung nên xác minh:
- Hostname/port thuộc endpoint mong đợi.
- DNS resolve được trong network test.
- Consumer kết nối thành công.
- Registry không chứa loopback/wildcard hoặc endpoint ngoài phạm vi.

Chỉ assert IP cụ thể khi test environment cố định và có chủ đích. Với CI dùng Docker hoặc Kubernetes ephemeral, ưu tiên service name/DNS hoặc endpoint được test harness cấp.

### 12.2. Test cấu hình bind riêng với advertised address

Một test cấu hình có thể xác nhận server.address và discovery override được bind vào đúng property. Tuy nhiên, test binding không chứng minh socket đã mở hoặc địa chỉ reachable. Cần integration test khởi động server và test từ consumer.

Không dùng một unit test đọc YAML để thay thế kiểm tra network path.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Server khởi động nhưng container khác không gọi được | Bind vào loopback | Kiểm tra server.address và socket listener |
| Registry công bố 0.0.0.0 | Nhầm wildcard bind với destination | Cấu hình hostname/IP quảng bá riêng |
| Registry công bố 127.0.0.1 | InetUtils fallback hoặc discovery override sai | Kiểm tra host info và eureka.instance.* |
| Docker consumer gọi host port nhưng thất bại | Consumer cùng bridge cần container port | Dùng service DNS và port nội bộ |
| Client ngoài Docker không truy cập được container IP | Không có route tới bridge IP | Dùng host/LB address và published port |
| Kubernetes Pod đăng ký Node IP | Chọn sai lớp địa chỉ | Dùng Pod IP cho instance discovery hoặc Service DNS cho service discovery |
| Pod bind đúng nhưng Service không truy cập được | Selector/targetPort/EndpointSlice/NetworkPolicy sai | Kiểm tra Service và endpoints |
| Registry trả địa chỉ đúng nhưng TCP timeout | Route/firewall/security group chặn | Test từ network namespace consumer |
| Hostname đăng ký đúng nhưng DNS không resolve | DNS scope/search domain khác nhau | Kiểm tra resolver từ consumer |
| Port đúng trong container nhưng sai bên ngoài | Nhầm container port với published/Service port | Đối chiếu port mapping hoặc Service port/targetPort |
| URL bên ngoài bị sai scheme/host | Reverse proxy forwarded headers chưa đúng | Kiểm tra proxy và cấu hình forwarded headers |
| Một số replica truy cập được, một số không | Interface/IP hoặc rollout khác nhau | Kiểm tra registry record theo từng instance |

## 14. Quy trình chọn bind và advertised address

Khi triển khai một Spring Cloud service, có thể thực hiện theo trình tự:

1. Xác định process chạy trên host, Docker bridge, host network hay Kubernetes Pod.
2. Xác định port mà ứng dụng listen bên trong namespace.
3. Chọn bind address phù hợp; trong container thường dùng wildcard và giới hạn truy cập ở hạ tầng.
4. Xác định consumer nằm ở network zone nào.
5. Chọn hostname/IP mà consumer có thể resolve và route tới.
6. Xác định port consumer cần gọi: container port, Kubernetes Service port hay host/LB port.
7. Cấu hình discovery client để quảng bá đúng endpoint.
8. Dùng InetUtils filters nếu cần chọn host info tự động.
9. Kiểm tra record đã đăng ký và giá trị DiscoveryClient trả về.
10. Test DNS/TCP/HTTP từ consumer thật.
11. Kiểm tra readiness, firewall, TLS, gateway và NetworkPolicy.
12. Lặp lại khi thay đổi container runtime, CNI, network interface hoặc release train.

Nếu một service có cả consumer nội bộ và bên ngoài, hãy thiết kế endpoint/gateway/DNS theo zone thay vì cố ép một IP container phục vụ mọi mạng.

## 15. Nguyên tắc vận hành và bảo mật

- Không quảng bá 0.0.0.0, ::, 127.0.0.1 hoặc ::1 cho consumer từ xa.
- Không hard-code IP container/Pod nếu địa chỉ có thể đổi khi reschedule.
- Không nhầm bind address với advertised address hoặc outbound source address.
- Bind wildcard trong container cần đi cùng firewall, network policy và authentication phù hợp.
- Chỉ expose port cần thiết; không publish management port ra ngoài nếu không có yêu cầu.
- Không đăng ký địa chỉ của bridge/VPN/virtual interface nếu consumer không có route.
- Dùng DNS/service name ổn định khi hạ tầng cung cấp.
- Kiểm tra registry record từ phía consumer, không chỉ từ provider.
- Quản lý server.port, Docker published port và Kubernetes port/targetPort như các khái niệm riêng.
- Kiểm tra lại địa chỉ quảng bá sau mỗi lần thay đổi topology hoặc nền tảng triển khai.
- Không công khai danh sách interface/IP nội bộ qua endpoint chẩn đoán không được bảo vệ.

## Ghi nhớ

server.address điều khiển nơi web server lắng nghe; địa chỉ quảng bá điều khiển host/port mà discovery hoặc consumer nhận được; còn địa chỉ truy cập thực tế phụ thuộc DNS, route, NAT, firewall và network namespace của client. Trong Docker, phân biệt container port với host published port và dùng service DNS cho các container cùng network. Trong Kubernetes, phân biệt Pod IP với Service DNS/ClusterIP và endpoint ingress. Hãy xác minh cả listener, registry record và kết nối từ consumer trước khi kết luận địa chỉ của service đã được cấu hình đúng.

